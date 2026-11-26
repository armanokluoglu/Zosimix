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
  flmcp            Claude Code working in FL Studio through rosasynthesiz/flstudio-mcp (ported to
                   FL 20.9.2), graded from FL renders of the agent's mix (D66, D70). Needs FL closed
                   and the Zosimix and FLStudioMCP MIDI scripts set up; playback is audible.

Usage:
    python -m zosimix.runner run --set smoke --config zosimix
    python -m zosimix.runner run --set dev --config zosimix --repeats 3 --workers 4
    python -m zosimix.runner report --run <run_id>
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from zosimix import graders, targets, tasks

REPO = Path(__file__).resolve().parents[2]
# Not under %LOCALAPPDATA%: the Claude desktop app redirects writes there into its own
# sandbox folder, so runs started from the app and from a terminal would land in two
# different places (D65). C:\zosimix is outside the repo, like before, and next to the FL root.
HOME = Path(os.environ.get("ZOSIMIX_HOME", "C:/zosimix" if os.name == "nt" else Path.home() / "zosimix"))
RUNS = HOME / "runs"
WORKSPACES = HOME / "ws"       # kept apart from RUNS, so no "../.." from a workspace leads to grades (D51)
BASELINE_PY = HOME / "baseline-venv" / "Scripts" / "python.exe"
# The plain baseline's audio libraries: the same versions the harness itself uses (D65).
BASELINE_PACKAGES = ["numpy==2.4.6", "scipy==1.17.1", "soundfile==0.14.0", "pyloudnorm==0.2.0", "pedalboard==0.9.26"]
TIMEOUT_S = 20 * 60
DEFAULT_MODEL = "claude-sonnet-5-5"   # headline numbers use Sonnet 5.5 (DESIGN §4.6); the full id, not the alias,
                                      # so a later alias change can't silently mix models in one run
SKILL_PATH = REPO / "skills" / "zosimix-diagnosis" / "SKILL.md"

# Which parts of the Zosimix layer each configuration gets (D52). "zosimix" is the full layer;
# the others switch one part off, so the difference measures what that part is worth.
CONFIGS = {
    "zosimix":         {"tools": "zosimix", "skill": True},
    "zosimix-noskill": {"tools": "zosimix", "skill": False},
    # Ablations (DESIGN.md §5, D78): the full layer with one part switched off, or the picture tool added.
    "zosimix-noverify": {"tools": "zosimix", "skill": True, "server_args": ["--no-verify"]},
    "zosimix-notarget": {"tools": "zosimix", "skill": True, "target": False},
    "zosimix-notriage": {"tools": "zosimix", "skill": True, "server_args": ["--no-triage"]},
    "zosimix-nospectrogram": {"tools": "zosimix", "skill": True, "server_args": ["--no-spectrogram"]},
    "plain":           {"tools": "plain", "skill": False},
    "flmcp":           {"tools": "flmcp", "skill": False},
}

# Strings that should never appear in an agent's tool calls: they point at answers (D25, D51).
# Task files are matched by prefix, so revised sets (tasks/full-v2.json, D69) are covered too.
FORBIDDEN = [str(REPO).lower(), str(REPO).lower().replace("\\", "/"), "groundtruth", "tasks\\smoke",
             "tasks/smoke", "tasks\\full", "tasks/full", "tasks\\dev", "tasks/dev", "tasks\\holdout",
             "tasks/holdout", "results.jsonl", "zosimix\\runs", "zosimix/runs"]

# Keys that only exist in ground-truth files (task specs, results.jsonl). Nothing the agent is
# given contains them, so seeing one in a tool *result* means answers reached the agent,
# however the path was spelled (D51).
# Regular expressions. Severity counts only with a number after it: ground truth stores it as
# 0-2, while flstudio-mcp's Mix Doctor labels its own findings "severity": "low" (D70).
GROUND_TRUTH_MARKERS = ['"expected_verdict"', '"hint_level"', r'"severity":\s*\d']

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
      and 1.0 for the other types. q ranges: peaking 0.2..14, shelves 0.41..1.04, highpass/lowpass
      0.1..6.5. freq_hz 20..20000, gain_db -18..18.
Tracks you leave out stay unchanged.

When you are done, write exactly these two files:
  output/mix_state.json  {{"<stem name>": {{"gain_db": 0, "pan": 0, "polarity": false, "width": 1, "eq": []}}, ...}}
  output/diagnosis.json  {{"verdict": "fixed" | "unfixable" | "no_fault",
                          "findings": [{{"stem": "<stem name>", "fault_type": "gain|polarity|resonance|mud|pan|clipping",
                                        "confidence": 0.0-1.0}}],
                          "summary": "<one or two sentences>"}}
Use "unfixable" for problems these controls cannot fix, and "no_fault" with no findings if nothing is wrong."""

FLMCP_PROMPT = """{brief}

The song is open in FL Studio. Each stem plays on its own mixer insert, named after the stem:
{inserts}
Every one of these inserts has Fruity Parametric EQ 2 in effect slot 0, set flat. Use the FL Studio
tools to inspect and fix the mix: the mix as you leave it in FL is your fix. You cannot listen, so
measure; FL's meters only move while the song is playing. Leave the master track alone: its level
is not part of the task.

When you are done, stop playback and write exactly this file:
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
        # --restricted confines the file tools to the workspace (Bash, named in --tools, stays
        # available). An extra layer on top of the integrity scans, not a sandbox (D51, D65).
        tools = "Bash,Read,Write,Edit,Glob,Grep"
        return [_claude(), *common, "--restricted", "--tools", tools, "--allowedTools", tools]
    if setup["tools"] == "flmcp":
        # flstudio-mcp's mixing tools, plus Write (confined to the workspace) for diagnosis.json.
        # The other flstudio-mcp tools are removed from the agent's view (D70).
        from zosimix.fl import baseline as fl_baseline
        mcp = {"mcpServers": {"flstudio": {"command": str(fl_baseline.FLMCP_SERVER), "args": []}}}
        mcp_path = workspace.parent / "mcp.json"
        mcp_path.write_text(json.dumps(mcp), encoding="utf-8")
        allowed = ",".join(["Write", *(f"mcp__flstudio__{t}" for t in fl_baseline.MIXING_TOOLS)])
        hidden = ",".join(f"mcp__flstudio__{t}" for t in fl_baseline.EXCLUDED_TOOLS)
        return [_claude(), *common, "--restricted", "--mcp-config", str(mcp_path), "--tools", "Write",
                "--allowedTools", allowed, "--disallowedTools", hidden]
    mcp = {"mcpServers": {"zosimix": {"command": sys.executable,
                                      "args": ["-m", "zosimix.mcp_server", "--workspace", str(workspace),
                                               *setup.get("server_args", [])]}}}
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
        # Not every event has an object-shaped "message": a permission_denied event's is a string.
        message = msg.get("message") if isinstance(msg, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
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
                flags += [f"tool result: {m}" for m in GROUND_TRUTH_MARKERS if re.search(m, text)]
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
    tools = CONFIGS[config]["tools"]
    if tools == "flmcp":
        return _run_one_fl(spec, config, repeat, run_dir, model, work)
    # The no-target ablation gets no tonal_target.json, so tonal_balance and scan lowmid's z have nothing to
    # compare with (D78).
    target = targets.target_for(spec.song_id, profiles) if CONFIGS[config].get("target", True) else None
    tasks.materialize(spec, workspace, target=target)
    (workspace / "output").mkdir(exist_ok=True)
    brief = spec.brief
    prompt = (ZOSIMIX_PROMPT.format(brief=brief) if tools == "zosimix"
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
    row = _row(spec, config, repeat, model, transcript, result, wall, timed_out)
    if _hit_limit(result, stderr):
        row["status"] = "usage_limit"                       # not graded: resuming re-runs this task
    else:
        row["grade"] = graders.grade(spec, diagnosis, mix_state)
        _save_answer(run_dir, spec, config, repeat, diagnosis, {"mix_state": mix_state})
    shutil.rmtree(work, ignore_errors=True)                 # audio is regenerated from the spec on demand
    return row


def _row(spec, config, repeat, model, transcript: Path, result: dict, wall: float, timed_out: bool) -> dict:
    return {
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


def _hit_limit(result: dict, stderr: str) -> bool:
    return bool((not result or result.get("is_error")) and _looks_like_usage_limit(result, stderr))


def _save_answer(run_dir: Path, spec, config: str, repeat: int, diagnosis, extra: dict) -> None:
    if diagnosis is not None:
        (run_dir / "answers").mkdir(exist_ok=True)
        (run_dir / "answers" / f"{spec.task_id}-{config}-{repeat}.json").write_text(
            json.dumps({"diagnosis": diagnosis, **extra}, indent=1), encoding="utf-8")


def _run_one_fl(spec: tasks.TaskSpec, config: str, repeat: int, run_dir: Path, model: str, work: Path) -> dict:
    """The flstudio-mcp baseline (D70): the song is open in FL while the agent works; its mix is
    then read back from FL as group renders and graded from those. The workspace holds only the
    brief and the output folder: the agent meets the song through FL, not as files."""
    from zosimix.fl import baseline as fl_baseline
    from zosimix.fl.bridge import BridgeError
    from zosimix.fl.session import FLError

    workspace = work / "ws"
    tasks.write_brief(spec, workspace)
    (workspace / "output").mkdir(exist_ok=True)
    transcript = run_dir / "transcripts" / f"{spec.task_id}-{config}-{repeat}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    stems, sr = tasks.faulty_stems(spec)
    try:
        with fl_baseline.open_task(stems, sr) as fl_task:
            inserts = "\n".join(f"  insert {i}: {name}" for i, name in fl_task.inserts.items())
            prompt = FLMCP_PROMPT.format(brief=spec.brief, inserts=inserts)
            started = time.time()
            with open(transcript, "w", encoding="utf-8") as out:
                stderr, timed_out = _run_agent(build_command(config, workspace, model, prompt), workspace, out)
            wall = time.time() - started
            result = _final_result(transcript)
            diagnosis = _read_answer(workspace / "output" / "diagnosis.json")
            row = _row(spec, config, repeat, model, transcript, result, wall, timed_out)
            if _hit_limit(result, stderr):
                row["status"] = "usage_limit"
                return row
            renders = fl_baseline.read_back(fl_task, graders.render_groups(spec)) if diagnosis is not None else {}
            row["fl_agent_state"] = fl_task.agent_state
    except (FLError, BridgeError) as exc:
        # Not graded: FL itself failed, which says nothing about the agent. Resuming re-runs it.
        return {"task_id": spec.task_id, "config": config, "repeat": repeat, "model": model,
                "status": "fl_error", "error": str(exc)}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    row["grade"] = graders.grade_renders(spec, diagnosis, renders)
    _save_answer(run_dir, spec, config, repeat, diagnosis, {"fl_agent_state": row["fl_agent_state"]})
    return row


def _record_run_info(run_dir: Path, set_name: str, configs: list[str], repeats: int, model: str,
                     only: list[str] | None = None) -> None:
    """Which code, model and settings produced this run, appended once per start or resume (D65).
    A resume from different code shows up here as a second entry with another commit."""
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                            check=False).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO,
                                capture_output=True, text=True, check=False).stdout.strip())
    entry = {"started": dt.datetime.now().isoformat(timespec="seconds"), "commit": commit,
             "uncommitted_changes": dirty, "set": set_name, "configs": configs, "repeats": repeats,
             "model": model, "claude_cli": None, **({"only_tasks": only} if only else {})}
    exe = shutil.which("claude")
    if exe:
        entry["claude_cli"] = subprocess.run([exe, "--version"], capture_output=True, text=True,
                                             check=False).stdout.strip()
    with open(run_dir / "run_info.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run(set_name: str, configs: list[str], repeats: int, model: str, run_id: str | None,
        only: list[str] | None = None, workers: int = 1) -> Path:
    """Run every task of a set, or just the task ids in `only` (D69: after a set revision,
    only the changed tasks need new runs; the unchanged ones keep their earlier results)."""
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
        venv = BASELINE_PY.parents[1]
        sys.exit(f"baseline Python not found at {BASELINE_PY}. Create it (D65):\n"
                 f"  py -3.11 -m venv {venv}\n"
                 f"  {BASELINE_PY} -m pip install {' '.join(BASELINE_PACKAGES)}")
    specs = tasks.load(set_name)
    if only:
        unknown = set(only) - {s.task_id for s in specs}
        if unknown:
            sys.exit(f"not in set {set_name}: {', '.join(sorted(unknown))}")
        specs = [s for s in specs if s.task_id in only]
    profiles = targets.load_profiles()
    _record_run_info(run_dir, set_name, configs, repeats, model, only)
    # Repeats outermost: every task gets its first run before any task gets a second, so a
    # run cut short by a usage limit still holds one complete pass over the set (D65).
    jobs = [(spec, config, repeat) for repeat in range(1, repeats + 1) for spec in specs for config in configs
            if (spec.task_id, config, repeat) not in done]
    if "flmcp" in configs and workers > 1:
        print("flmcp drives the one FL instance on this machine: running with 1 worker")
        workers = 1
    print(f"run {run_id}: {len(specs)} tasks x {configs} x {repeats} repeat(s); {len(done)} already done, "
          f"{len(jobs)} to run with {workers} worker(s)")
    # Each agent's measurement server gets its share of the cores; inherited by every agent
    # process and the MCP server it starts.
    os.environ["ZOSIMIX_MEASURE_THREADS"] = str(max(1, (os.cpu_count() or 1) // workers))
    stop = threading.Event()
    lock = threading.Lock()

    def one(job) -> None:
        spec, config, repeat = job
        if stop.is_set():
            return
        row = run_one(spec, config, repeat, run_dir, model, profiles)
        with lock:                                    # one writer at a time, whole lines only
            with open(results_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            label = f"  {spec.task_id} [{config} #{repeat}]"
            if row["status"] == "usage_limit":
                stop.set()
                print(f"{label} USAGE LIMIT reached. Resume later with the same command plus --run {run_id}")
            elif row["status"] == "fl_error":
                # FL failing is about the setup, not the agent, and it tends to repeat.
                stop.set()
                print(f"{label} FL ERROR: {row['error']}\nFix FL, then resume with the same command plus --run {run_id}")
            else:
                g = row["grade"]
                print(f"{label} {'PASS' if g['pass'] else 'fail'}  ({row['wall_s']:.0f} s, {row['turns']} turns)"
                      + (f"  INTEGRITY: {row['integrity_flags']}" if row["integrity_flags"] else ""), flush=True)

    # Runs are independent (own workspace, own agent, own MCP server), and almost all of a run's
    # time is the agent thinking, so several at once finish proportionally sooner (D73).
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, jobs))
    print(("stopped early: " if stop.is_set() else "finished: ") + str(results_path))
    return run_dir


def regrade(run_id: str) -> Path:
    """Grade a finished run's saved answers again with the current graders, into regraded.jsonl.

    results.jsonl is left as it was, so a run's original grades stay on record (D73). flmcp
    answers can't be regraded: they were graded from FL renders, which aren't kept. Those rows
    are copied with their original grade and marked."""
    run_dir = RUNS / run_id
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    specs = {}
    for name in {r["task_id"].rsplit("-", 1)[0] for r in rows}:
        specs.update({s.task_id: s for s in tasks.load(name)})
    out = []
    for r in rows:
        if r["status"] != "done":
            continue
        if r["config"] == "flmcp":
            out.append({**r, "regraded": False})
            continue
        answer = _read_answer(run_dir / "answers" / f"{r['task_id']}-{r['config']}-{r['repeat']}.json") or {}
        out.append({**r, "grade": graders.grade(specs[r["task_id"]], answer.get("diagnosis"), answer.get("mix_state")),
                    "regraded": True})
    path = run_dir / "regraded.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    return path


def partial_credit(rows: list[dict]) -> float:
    """Average credit per run, between 0 and 1, so a half-done repair isn't scored like doing
    nothing (D72). A passed run scores 1. A failed run on a fixable fault scores its repair
    score (clamped to 0..1), but only if it named the fault correctly and left the other stems
    alone. Any other failed run scores 0."""
    credit = []
    for r in rows:
        g = r["grade"]
        repair = (g.get("repair") or {}).get("score")
        if g["pass"]:
            credit.append(1.0)
        elif repair is not None and g.get("detected") and (g.get("others_residual_db") or 0) <= graders.UNTOUCHED_DB:
            credit.append(min(1.0, max(0.0, repair)))
        else:
            credit.append(0.0)
    return sum(credit) / len(credit) if credit else 0.0


def report(run_id: str) -> str:
    rows = [json.loads(line) for line in (RUNS / run_id / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r["status"] == "done"]
    lines = [f"run {run_id}: {len(rows)} graded runs"]
    for config in sorted({r["config"] for r in rows}):
        rs = [r for r in rows if r["config"] == config]
        passed = sum(r["grade"]["pass"] for r in rs)
        detected = sum(bool(r["grade"].get("detected")) for r in rs)
        tokens = [r["usage"].get("output_tokens", 0) for r in rs]
        scoped = [r for r in rs if graders.in_scope(r["grade"])]
        lines.append(f"\n[{config}] pass {sum(r['grade']['pass'] for r in scoped)}/{len(scoped)} in scope (D83), "
                     f"{passed}/{len(rs)} all, detected {detected}/{len(rs)}, "
                     f"partial credit {partial_credit(rs):.2f}, "
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
    r.add_argument("--model", default=DEFAULT_MODEL)
    r.add_argument("--run", dest="run_id", help="resume this run id")
    r.add_argument("--tasks", help="comma-separated task ids: run only these")
    r.add_argument("--workers", type=int, default=1, help="runs at once (flmcp always uses 1)")
    p = sub.add_parser("report")
    p.add_argument("--run", dest="run_id", required=True)
    g = sub.add_parser("regrade", help="grade a run's saved answers again into regraded.jsonl (D73)")
    g.add_argument("--run", dest="run_id", required=True)
    args = ap.parse_args()
    if args.cmd == "run":
        only = [t.strip() for t in args.tasks.split(",")] if args.tasks else None
        run(args.set, args.config, args.repeats, args.model, args.run_id, only, args.workers)
    elif args.cmd == "regrade":
        print(f"wrote {regrade(args.run_id)}")
    else:
        print(report(args.run_id))


if __name__ == "__main__":
    main()
