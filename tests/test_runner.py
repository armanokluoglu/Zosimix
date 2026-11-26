"""Runner tests with a fake agent instead of Claude, so they cost nothing.

The fake agent is a tiny Python script that writes an answer into the workspace's output
folder, exactly where the real MCP server or plain baseline would. This checks the whole
pipeline: workspace outside the repo, grading, checkpoint/resume and integrity scanning.
Needs the real songs in data/songs (skipped otherwise).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from zosimix import faults, runner, tasks
from zosimix.songs import list_songs

SONG = "moisesdb-centenary-by-now"
pytestmark = pytest.mark.skipif(SONG not in {s.song_id for s in list_songs()}, reason="real songs not present")

FAKE_AGENT = r"""
import json, pathlib, sys
out = pathlib.Path("output"); out.mkdir(exist_ok=True)
answer = json.loads(sys.argv[1])
(out / "diagnosis.json").write_text(json.dumps(answer["diagnosis"]))
(out / "mix_state.json").write_text(answer.get("mix_state_raw") or json.dumps(answer["mix_state"]))
print(json.dumps({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": answer.get("peek", "stems/bass.wav")}}]}}))
print(json.dumps({"type": "user", "message": {"content": [
    {"type": "tool_result", "content": [{"type": "text", "text": answer.get("seen", "RIFF....WAVE")}]}]}}))
print(json.dumps({"type": "result", "num_turns": 3, "is_error": False, "total_cost_usd": 0.0,
                  "usage": {"output_tokens": 42}}))
"""


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(runner, "WORKSPACES", tmp_path / "ws")
    monkeypatch.setattr(tasks, "TASKS_DIR", tmp_path / "tasks")
    fault = faults.Fault("gain", "bass_bass_guitar", 1, {"gain_db": 6.0})
    tasks.save("t", 1, [tasks.TaskSpec("t-001", SONG, fault.to_dict(), "none", "")])
    return tmp_path


def fake(answer: dict):
    return lambda config, workspace, model, prompt: [sys.executable, "-c", FAKE_AGENT, json.dumps(answer)]


def results(tmp_path) -> list[dict]:
    path = next((tmp_path / "runs").glob("*/results.jsonl"))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_perfect_fake_agent_passes_and_workspace_is_outside_the_repo(isolated, monkeypatch):
    seen = {}

    def capture(config, workspace, model, prompt):
        seen["workspace"] = workspace
        return fake({"diagnosis": {"verdict": "fixed", "findings": [{"stem": "bass_bass_guitar", "fault_type": "gain"}]},
                     "mix_state": {"bass_bass_guitar": {"gain_db": -6.0}}})(config, workspace, model, prompt)

    monkeypatch.setattr(runner, "build_command", capture)
    runner.run("t", ["zosimix"], 1, "sonnet", "r1")
    row = results(isolated)[0]
    assert row["grade"]["pass"] and row["turns"] == 3 and not row["integrity_flags"]
    assert runner.REPO not in seen["workspace"].parents
    assert runner.RUNS not in seen["workspace"].parents         # grades are not a "../" away
    assert "t-001" not in str(seen["workspace"])               # the path says nothing about the task
    assert not seen["workspace"].exists()                      # audio cleaned up after grading


def test_resume_skips_finished_tasks(isolated, monkeypatch):
    monkeypatch.setattr(runner, "build_command", fake({"diagnosis": {"verdict": "no_fault", "findings": []},
                                                       "mix_state": {}}))
    runner.run("t", ["zosimix"], 1, "sonnet", "r2")
    runner.run("t", ["zosimix"], 1, "sonnet", "r2")            # second call finds it done
    assert len(results(isolated)) == 1


def test_peeking_at_the_repo_is_flagged(isolated, monkeypatch):
    peek = str(runner.REPO / "tasks" / "full.json")
    monkeypatch.setattr(runner, "build_command", fake({"diagnosis": {"verdict": "no_fault", "findings": []},
                                                       "mix_state": {}, "peek": peek}))
    runner.run("t", ["zosimix"], 1, "sonnet", "r3")
    assert results(isolated)[0]["integrity_flags"]


def test_ground_truth_in_a_tool_result_is_flagged_however_it_was_reached(isolated, monkeypatch):
    leaked = '{"task_id": "t-001", "fault": {"type": "gain", "stem": "bass", "severity": 1}, "hint_level": "none"}'
    monkeypatch.setattr(runner, "build_command", fake({"diagnosis": {"verdict": "no_fault", "findings": []},
                                                       "mix_state": {}, "peek": "../../*/res*", "seen": leaked}))
    runner.run("t", ["zosimix"], 1, "sonnet", "r4")
    flags = results(isolated)[0]["integrity_flags"]
    assert flags and all(f.startswith("tool result") for f in flags)     # the path itself matched nothing


def test_events_without_an_object_message_are_skipped(tmp_path):
    """A real event from full-1: permission_denied carries "message" as a string. It used to
    crash the scan, which stopped the whole run."""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "system", "subtype": "permission_denied", "tool_name": "Bash",
                    "message": "Permission to use Bash has been denied because Claude Code is running in don't ask mode."}),
        json.dumps(["not", "an", "object"]),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "tasks/full.json"}}]}}),
    ]), encoding="utf-8")
    assert runner.integrity_flags(transcript) == ["Read: tasks/full"]


def test_ordinary_tool_results_are_not_flagged(isolated, monkeypatch):
    monkeypatch.setattr(runner, "build_command", fake({"diagnosis": {"verdict": "no_fault", "findings": []},
                                                       "mix_state": {}, "seen": "bass: -18.2 LUFS, severity looks mild"}))
    runner.run("t", ["zosimix"], 1, "sonnet", "r5")
    assert not results(isolated)[0]["integrity_flags"]


def test_a_broken_mix_state_does_not_discard_a_good_diagnosis(isolated, monkeypatch):
    """D62: each answer file is read on its own; the mix state then counts as 'no changes'."""
    monkeypatch.setattr(runner, "build_command", fake({
        "diagnosis": {"verdict": "fixed", "findings": [{"stem": "bass_bass_guitar", "fault_type": "gain"}]},
        "mix_state": {}, "mix_state_raw": '{"bass_bass_guitar": {"gain_db": -6.0},}'}))
    runner.run("t", ["zosimix"], 1, "sonnet", "r6")
    grade = results(isolated)[0]["grade"]
    assert grade["submitted"] and grade["detected"] and not grade["pass"]     # found, but nothing repaired


HANGING_AGENT = r"""
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path(sys.argv[1]).write_text(str(child.pid))
time.sleep(120)
"""


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                         check=False, capture_output=True, text=True)
    return f'"{pid}"' in out.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="checks Windows process-tree cleanup")
def test_a_timeout_stops_the_agents_child_processes_too(isolated, monkeypatch):
    """D62: the MCP server is a child of claude; killing claude alone would leave it running."""
    pid_file = isolated / "child.pid"
    monkeypatch.setattr(runner, "TIMEOUT_S", 5)
    monkeypatch.setattr(runner, "build_command",
                        lambda config, workspace, model, prompt: [sys.executable, "-c", HANGING_AGENT, str(pid_file)])
    runner.run("t", ["zosimix"], 1, "sonnet", "r7")
    row = results(isolated)[0]
    assert row["timed_out"] and not row["grade"]["submitted"]
    assert not _alive(int(pid_file.read_text()))


def test_skill_goes_into_the_system_prompt_only_for_the_full_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_claude", lambda: "claude")
    ws = tmp_path / "work" / "ws"
    ws.mkdir(parents=True)
    full = runner.build_command("zosimix", ws, "sonnet", "brief")
    bare = runner.build_command("zosimix-noskill", ws, "sonnet", "brief")
    assert "--append-system-prompt-file" in full and "--append-system-prompt-file" not in bare
    skill = (tmp_path / "work" / "skill.md").read_text(encoding="utf-8")
    assert skill.startswith("# Diagnosing") and "name: zosimix-diagnosis" not in skill
    assert "--bare" not in full + bare


def test_skill_contains_no_benchmark_specifics():
    """The skill is tuned on the smoke set, so it must hold general mixing knowledge only:
    no song ids, no dataset stem names and no task-generator internals (D52)."""
    text = runner.skill_text().lower()
    specifics = {s.song_id for s in list_songs()}
    specifics |= {n.lower() for s in list_songs() for n in s.stem_paths if "_" in n}
    specifics |= {"severity", "smoke-", "full-", "seed"}
    assert not [w for w in specifics if w in text]


def test_only_the_listed_tasks_run(isolated, monkeypatch):
    """D69: after a set revision only the changed tasks get new runs."""
    fault = faults.Fault("gain", "bass_bass_guitar", 1, {"gain_db": 6.0})
    tasks.save("t", 1, [tasks.TaskSpec(f"t-00{i}", SONG, fault.to_dict(), "none", "") for i in (1, 2)])
    monkeypatch.setattr(runner, "build_command", fake({"diagnosis": {"verdict": "no_fault", "findings": []},
                                                       "mix_state": {}}))
    runner.run("t", ["zosimix"], 1, "sonnet", "r8", only=["t-002"])
    assert [r["task_id"] for r in results(isolated)] == ["t-002"]
    info = json.loads((isolated / "runs" / "r8" / "run_info.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert info["only_tasks"] == ["t-002"]


def test_revised_task_sets_are_forbidden_too(tmp_path):
    """D69 added tasks/full-v2.json; the scan matches task files by prefix."""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "../../tasks/full-v2.json"}}]}}), encoding="utf-8")
    assert runner.integrity_flags(transcript) == ["Read: tasks/full"]


def test_a_tools_own_severity_label_is_not_ground_truth(tmp_path):
    """flstudio-mcp's Mix Doctor reports "severity": "low"; ground truth stores a number (D70)."""
    transcript = tmp_path / "t.jsonl"
    lines = [{"type": "user", "message": {"content": [{"type": "tool_result", "content": text}]}}
             for text in ['{"rule": "clipping", "severity": "high"}', '{"fault": {"severity": 2}}']]
    transcript.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert runner.integrity_flags(transcript) == [r'tool result: "severity":\s*\d']


def test_parallel_workers_write_one_row_per_run(isolated, monkeypatch):
    """D73: with several workers every (task, config, repeat) still gets exactly one whole line."""
    fault = faults.Fault("gain", "bass_bass_guitar", 1, {"gain_db": 6.0})
    tasks.save("t", 1, [tasks.TaskSpec(f"t-00{i}", SONG, fault.to_dict(), "none", "") for i in (1, 2, 3)])
    monkeypatch.setattr(runner, "build_command", fake({"diagnosis": {"verdict": "no_fault", "findings": []},
                                                       "mix_state": {}}))
    runner.run("t", ["zosimix"], 2, "sonnet", "r9", workers=4)
    keys = sorted((r["task_id"], r["repeat"]) for r in results(isolated))
    assert keys == [(f"t-00{i}", rep) for i in (1, 2, 3) for rep in (1, 2)]


@pytest.mark.parametrize("config, flag", [("zosimix-noverify", "--no-verify"), ("zosimix-notriage", "--no-triage"),
                                          ("zosimix-nospectrogram", "--no-spectrogram")])
def test_ablation_configs_pass_their_switch_to_the_server(tmp_path, monkeypatch, config, flag):
    monkeypatch.setattr(runner, "_claude", lambda: "claude")
    ws = tmp_path / "work" / "ws"
    ws.mkdir(parents=True)
    runner.build_command(config, ws, "sonnet", "brief")
    args = json.loads((tmp_path / "work" / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["zosimix"]["args"]
    assert flag in args and "--append-system-prompt-file" in runner.build_command(config, ws, "sonnet", "brief")


def test_no_target_ablation_gets_no_tonal_target(isolated, monkeypatch):
    seen = {}

    def capture(config, workspace, model, prompt):
        seen["target"] = (workspace / "tonal_target.json").exists()
        return fake({"diagnosis": {"verdict": "no_fault", "findings": []}, "mix_state": {}})(config, workspace, model, prompt)

    monkeypatch.setattr(runner, "build_command", capture)
    runner.run("t", ["zosimix-notarget"], 1, "sonnet", "r10")
    assert seen["target"] is False
