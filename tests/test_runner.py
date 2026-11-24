"""Runner tests with a fake agent instead of Claude, so they cost nothing.

The fake agent is a tiny Python script that writes an answer into the workspace's output
folder, exactly where the real MCP server or plain baseline would. This checks the whole
pipeline: workspace outside the repo, grading, checkpoint/resume and integrity scanning.
Needs the real songs in data/songs (skipped otherwise).
"""

from __future__ import annotations

import json
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
(out / "mix_state.json").write_text(json.dumps(answer["mix_state"]))
print(json.dumps({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": answer.get("peek", "stems/bass.wav")}}]}}))
print(json.dumps({"type": "result", "num_turns": 3, "is_error": False, "total_cost_usd": 0.0,
                  "usage": {"output_tokens": 42}}))
"""


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RUNS", tmp_path / "runs")
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
