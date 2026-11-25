"""The eval runner: runs Claude Code headless on a task set, grades each run, and survives
usage limits (DESIGN.md §4.6-4.8, D22, D25, D26).

For every (task, configuration, repeat):
  1. build a fresh workspace OUTSIDE the repo and away from the run's results (the agent
     must never see task specs or grades)
  2. launch `claude -p` in it with only that configuration's tools
  3. grade the answer immediately and append one line to results.jsonl
  4. delete the workspace audio (transcript and answer files are kept)
A run can be stopped at any time and resumed: finished tasks are skipped. If Claude reports
a usage limit, the runner stops cleanly and says how to resume.

Configurations:
  zosimix          Claude Code + the Zosimix MCP server + the diagnosis skill; built-in tools off
  zosimix-noskill  the same without the skill (ablation; smoke run 1 used this setup)
  plain            Claude Code with shell + file tools and Python audio libraries; no Zosimix tools
  (the third baseline, Claude Code + an existing FL Studio MCP, needs the FL engine: days 9-10)

Usage:
    python -m zosimix.runner run --set smoke --config zosimix
    python -m zosimix.runner report --run <run_id>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from zosimix import graders, targets, tasks

REPO = Path(__file__).resolve().parents[2]
HOME = Path(os.environ.get("ZOSIMIX_HOME", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "zosimix"))
RUNS = HOME / "runs"
WORKSPACES = HOME / "ws"       # kept apart from RUNS, so no "../.." from a workspace leads to grades (D51)
BASELINE_PY = HOME / "baseline-venv" / "Scripts" / "python.exe"
TIMEOUT_S = 20 * 60
SKILL_PATH = REPO / "skills" / "zosimix-diagnosis" / "SKILL.md"

# Which parts of the Zosimix layer each configuration gets (D52). "zosimix" is the full layer;
# the others switch one part off, so the difference measures what that part is worth.
CONFIGS = {
    "zosimix":         {"tools": "zosimix", "skill": True},
    "zosimix-noskill": {"tools": "zosimix", "skill": False},
    "plain":           {"tools": "plain", "skill": False},
}

# Strings that should never appear in an agent's tool calls: they point at answers (D25, D51).
FORBIDDEN = [str(REPO).lower(), str(REPO).lower().replace("\\", "/"), "groundtruth", "tasks\\smoke.json",
             "tasks/smoke.json", "tasks\\full.json", "tasks/full.json", "results.jsonl",
             "zosimix\\runs", "zosimix/runs"]

# Keys that only exist in ground-truth files (task specs, results.jsonl). Nothing the agent is
# given contains them, so seeing one in a tool *result* means answers reached the agent,
# however the path was spelled (D51).
GROUND_TRUTH_MARKERS = ['"expected_verdict"', '"hint_level"', '"severity":']

ZOSIMIX_PROMPT = """{brief}

You have the zosimix tools to measure and change the mix. You cannot listen, so measure.
When you are done, call submit_diagnosis exactly once."""

PLAIN_PROMPT = """{brief}

The stems are in ./stems: one stereo 32-bit float WAV per instrument track, all the same length.
You cannot listen, so analyse them with code. A Python with numpy, scipy, soundfile, pyloudnorm and
pedalboard is at: {python}

Express your fix as a mix state, which is rendered as follows for each track:
polarity (invert) -> EQ bands -> pan -> stereo width -> gain, then all tracks are summed.
  gain_db: -60..18 (0 = unchanged)
  pan: -1..1, a balance control with gains L = sqrt(2)*cos((pan+1)*pi/4), R = sqrt(2)*sin((pan+1)*pi/4)
  polarity: true inverts the track
  width: 0 mono, 1 unchanged, 2 double side signal (mid/side)
  eq: up to 7 bands {{"type": peaking|low_shelf|high_shelf|highpass|lowpass, "freq_hz", "gain_db", "q"}}
      Second-order filters with the Audio EQ Cookbook (RBJ) meaning of gain and q, matched to the
      analog shape up to 20 kHz. Below about 4 kHz they equal pedalboard's PeakFilter, LowShelfFilter
      and HighShelfFilter. highpass/lowpass are 12 dB/octave; their q sets the bump at the cutoff
      (0.707 = none) and their gain_db is ignored. Leaving q out means 0.707 for highpass/lowpass
      and 1.0 for the other types.
Tracks you leave out stay unchanged.

When you are done, write exactly these two files:
  output/mix_state.json  {{"<stem name>": {{"gain_db": 0, "pan": 0, "polarity": false, "width": 1, "eq": []}}, ...}}
  output/diagnosis.json  {{"verdict": "fixed" | "unfixable" | "no_fault",
                          "findings": [{{"stem": "<stem name>", "fault_type": "gain|polarity|resonance|mud|pan|clipping",
                                        "confidence": 0.0-1.0}}],
                          "summary": "<one or two sentences>"}}
Use "unfixable" for problems these controls cannot fix, and "no_fault" with no findings if nothing is wrong."""


def _claude() -> str:
    exe = shutil.which("claude")
    if not exe:
        sys.exit("claude CLI not found on PATH")
    return exe


def skill_text() -> str:
    """The diagnosis skill without its frontmatter (the name/description header)."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip() + "\n"


def build_command(config: str, workspace: Path, model: str, prompt: str) -> list[str]:
    # Never --bare: it switches from the Pro login to API-key billing (D07). User, project and
    # local settings are skipped so personal hooks, plugins and memory can't leak into evals.
    common = ["-p", prompt, "--model", model, "--permission-mode", "dontAsk", "--setting-sources", "",
              "--no-session-persistence", "--output-format", "stream-json", "--verbose", "--strict-mcp-config"]
    setup = CONFIGS[config]
    if setup["tools"] == "plain":
        tools = "Bash,Read,Write,Edit,Glob,Grep"
        return [_claude(), *common, "--tools", tools, "--allowedTools", tools]
    mcp = {"mcpServers": {"zosimix": {"command": sys.executable,
                                      "args": ["-m", "zosimix.mcp_server", "--workspace", str(workspace)]}}}
    mcp_path = workspace.parent / "mcp.json"            # beside the workspace, not in it
    mcp_path.write_text(json.dumps(mcp), encoding="utf-8")
    cmd = [_claude(), *common, "--mcp-config", str(mcp_path), "--tools", "", "--allowedTools", "mcp__zosimix__*"]
    if setup["skill"]:
        # Built-in tools are off (--tools ""), so the agent couldn't load a skill on demand.
        # The playbook goes into the system prompt instead, always present (D52).
        skill_path = workspace.parent / "skill.md"
        skill_path.write_text(skill_text(), encoding="utf-8")
        cmd += ["--append-system-prompt-file", str(skill_path)]
    return cmd


def _result_text(content) -> str:
    """A tool result's content is either a string or a list of {"type": "text", "text": ...}."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def integrity_flags(transcript: Path) -> list[str]:
    """Two checks over the transcript (D25, D51):
      - a tool call whose input mentions a forbidden path (answers, the repo, other runs)
      - a tool result containing a ground-truth key, i.e. answers actually reached the agent.
    The second one catches leaks the first misses, like relative paths or wildcards."""
    flags = []
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = msg.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if msg.get("type") == "assistant" and block.get("type") == "tool_use":
                text = json.dumps(block.get("input", {})).lower().replace("\\\\", "\\")
                flags += [f"{block.get('name')}: {f}" for f in FORBIDDEN if f in text]
            elif msg.get("type") == "user" and block.get("type") == "tool_result":
                text = _result_text(block.get("content"))
                flags += [f"tool result: {m}" for m in GROUND_TRUTH_MARKERS if m in text]
    return flags


def _final_result(transcript: Path) -> dict:
    for line in reversed(transcript.read_text(encoding="utf-8", errors="replace").splitlines()):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "result":
            return msg
    return {}


def _looks_like_usage_limit(result: dict, stderr: str) -> bool:
    text = (json.dumps(result) + stderr).lower()
    return any(s in text for s in ("usage limit", "rate limit", "limit reached", "rate_limit_error"))


def _run_agent(cmd: list[str], cwd: Path, out) -> tuple[str, bool]:
    """Run the agent with a time limit. Returns (stderr, timed_out).

    On a timeout the whole process tree is stopped, not just `claude`: the MCP server it
    started (and node, if `claude` is a .cmd shim) would otherwise keep running, keep
    workspace files open and maybe keep writing output after the task was graded.
    """
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=subprocess.PIPE, text=True,
                            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        _, stderr = proc.communicate(timeout=TIMEOUT_S)
        return stderr or "", False
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            proc.kill()
        proc.communicate()
        return "", True


def _read_answer(path: Path) -> object | None:
    """One answer file, or None if it's missing or isn't valid JSON. Each file is read on
    its own, so a broken mix_state.json doesn't throw away a good diagnosis.json (D62)."""
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def run_one(spec: tasks.TaskSpec, config: str, repeat: int, run_dir: Path, model: str,
            profiles: dict) -> dict:
    # A random folder away from run_dir: the path says nothing about the task, and the
    # results, transcripts and other runs are not one "../" away (D51).
    work = WORKSPACES / secrets.token_hex(8)
    workspace = work / "ws"
    tasks.materialize(spec, workspace, target=targets.target_for(spec.song_id, profiles))
    (workspace / "output").mkdir(exist_ok=True)
    brief = spec.brief
    prompt = (ZOSIMIX_PROMPT.format(brief=brief) if CONFIGS[config]["tools"] == "zosimix"
              else PLAIN_PROMPT.format(brief=brief, python=BASELINE_PY))
    transcript = run_dir / "transcripts" / f"{spec.task_id}-{config}-{repeat}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    with open(transcript, "w", encoding="utf-8") as out:
        stderr, timed_out = _run_agent(build_command(config, workspace, model, prompt), workspace, out)
    wall = time.time() - started

    result = _final_result(transcript)
    diagnosis = _read_answer(workspace / "output" / "diagnosis.json")
    mix_state = _read_answer(workspace / "output" / "mix_state.json")

    row = {
        "task_id": spec.task_id, "config": config, "repeat": repeat, "model": model,
        "status": "done",
        "timed_out": timed_out,
        "wall_s": round(wall, 1),
        "turns": result.get("num_turns"),
        "cost_usd_equiv": result.get("total_cost_usd"),
        "usage": result.get("usage", {}),
        "agent_error": result.get("is_error"),
        "integrity_flags": integrity_flags(transcript),
    }
    hit_limit = (not result or result.get("is_error")) and _looks_like_usage_limit(result, stderr)
    if hit_limit:
        row["status"] = "usage_limit"                       # not graded: resuming re-runs this task
    else:
        row["grade"] = graders.grade(spec, diagnosis, mix_state)
        if diagnosis is not None:
            (run_dir / "answers").mkdir(exist_ok=True)
            (run_dir / "answers" / f"{spec.task_id}-{config}-{repeat}.json").write_text(
                json.dumps({"diagnosis": diagnosis, "mix_state": mix_state}, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)                 # audio is regenerated from the spec on demand
    return row


def run(set_name: str, configs: list[str], repeats: int, model: str, run_id: str | None) -> Path:
    run_id = run_id or f"{dt.datetime.now():%Y%m%d-%H%M}-{set_name}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["status"] == "done":
                done.add((r["task_id"], r["config"], r["repeat"]))
    if "plain" in configs and not BASELINE_PY.exists():
        sys.exit(f"baseline Python not found at {BASELINE_PY}; create it first (see README)")
    specs = tasks.load(set_name)
    profiles = targets.load_profiles()
    print(f"run {run_id}: {len(specs)} tasks x {configs} x {repeats} repeat(s); {len(done)} already done")
    for spec in specs:
        for config in configs:
            for repeat in range(1, repeats + 1):
                if (spec.task_id, config, repeat) in done:
                    continue
                print(f"  {spec.task_id} [{config} #{repeat}] ...", end=" ", flush=True)
                row = run_one(spec, config, repeat, run_dir, model, profiles)
                with open(results_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
                if row["status"] == "usage_limit":
                    print("USAGE LIMIT reached. Resume later with the same command plus --run", run_id)
                    return run_dir
                g = row["grade"]
                print(f"{'PASS' if g['pass'] else 'fail'}  ({row['wall_s']:.0f} s, {row['turns']} turns)"
                      + (f"  INTEGRITY: {row['integrity_flags']}" if row["integrity_flags"] else ""))
    print(f"finished: {results_path}")
    return run_dir


def report(run_id: str) -> str:
    rows = [json.loads(line) for line in (RUNS / run_id / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r["status"] == "done"]
    lines = [f"run {run_id}: {len(rows)} graded runs"]
    for config in sorted({r["config"] for r in rows}):
        rs = [r for r in rows if r["config"] == config]
        passed = sum(r["grade"]["pass"] for r in rs)
        detected = sum(bool(r["grade"].get("detected")) for r in rs)
        tokens = [r["usage"].get("output_tokens", 0) for r in rs]
        lines.append(f"\n[{config}] pass {passed}/{len(rs)}, detected {detected}/{len(rs)}, "
                     f"median {sorted(r['wall_s'] for r in rs)[len(rs) // 2]:.0f} s, "
                     f"{sum(r['turns'] or 0 for r in rs) / len(rs):.0f} turns avg, "
                     f"{sum(tokens) / len(rs):.0f} output tokens avg, "
                     f"${sum(r['cost_usd_equiv'] or 0 for r in rs):.2f} API-equivalent total")
        for r in rs:
            g = r["grade"]
            repair = g.get("repair", {})
            lines.append(f"  {r['task_id']} {g['fault_type']:<9} sev {g['severity']} hint {g['hint_level']:<5} "
                         f"{'PASS' if g['pass'] else 'fail'}  verdict {g.get('verdict')}/{g.get('expected_verdict')} "
                         f"detected {g.get('detected')} "
                         + (f"repair {repair.get('score')} ({repair.get('before')}->{repair.get('after')} "
                            f"{repair.get('unit')}) " if repair else "")
                         + f"others {g.get('others_residual_db')} dB"
                         + (f"  FLAGS {r['integrity_flags']}" if r["integrity_flags"] else ""))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--set", required=True)
    r.add_argument("--config", action="append", choices=list(CONFIGS), required=True)
    r.add_argument("--repeats", type=int, default=1)
    r.add_argument("--model", default="sonnet")
    r.add_argument("--run", dest="run_id", help="resume this run id")
    p = sub.add_parser("report")
    p.add_argument("--run", dest="run_id", required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.set, args.config, args.repeats, args.model, args.run_id)
    else:
        print(report(args.run_id))


if __name__ == "__main__":
    main()
