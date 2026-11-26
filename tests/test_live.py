"""Live mode for the Claude Code plugin (D84): a folder of DAW-exported stems instead of a
benchmark workspace, and matching the fix back to the DAW's mixer inserts."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from zosimix import audio, live
from zosimix.fl.live import match_inserts
from zosimix.mcp_server import build_server
from zosimix.songs import family_of

SR = 44100


def test_working_names_drop_the_project_prefix_and_add_a_family():
    names = live.working_names(["My Song_Kick In", "My Song_Snare Top", "My Song_Lead Vox", "My Song_Bass DI",
                                "My Song_Gtr L", "My Song_FX riser"])
    assert names["My Song_Kick In"] == "drums_Kick_In" and family_of(names["My Song_Kick In"]) == "drums"
    assert family_of(names["My Song_Lead Vox"]) == "vocals"
    assert family_of(names["My Song_Bass DI"]) == "bass"
    assert family_of(names["My Song_Gtr L"]) == "guitars" and names["My Song_Gtr L"].endswith("Gtr_L")
    assert names["My Song_FX riser"] == "FX_riser"                      # no keyword: name kept, family "other"


@pytest.fixture
def export_folder(tmp_path):
    rng = np.random.default_rng(0)
    t = np.arange(SR * 3) / SR
    files = {"Song_Kick": 0.3 * np.sin(2 * np.pi * 55 * t), "Song_Vox": 0.05 * rng.standard_normal(len(t)),
             "Song_Bass": 0.2 * np.sin(2 * np.pi * 82 * t), "Song_Master": 0.4 * np.sin(2 * np.pi * 55 * t)}
    for name, x in files.items():
        audio.write(tmp_path / f"{name}.wav", np.stack([x, x], axis=1), SR)
    return tmp_path


def test_load_folder_skips_the_master_and_keeps_the_original_names(export_folder):
    engine, originals, target = live.load_folder(export_folder)
    assert sorted(originals.values()) == ["Song_Bass", "Song_Kick", "Song_Vox"]
    assert set(engine.stem_names) == set(originals)
    assert target is not None and "families" in target                 # the shipped typical-mix reference


def test_live_server_needs_open_mix_first_then_works(export_folder):
    server = build_server(None, live=True)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert {"open_mix", "apply_to_fl", "revert_fl", "triage"} <= names
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match="open_mix"):                   # the reason reaches the agent
        asyncio.run(server.call_tool("overview", {}))
    opened = asyncio.run(server.call_tool("open_mix", {"folder": str(export_folder)}))
    assert "opened 3 stems" in str(opened)
    assert "MIX" in str(asyncio.run(server.call_tool("overview", {})))


def test_benchmark_server_has_no_live_tools():
    server = build_server(None)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert not {"open_mix", "apply_to_fl", "revert_fl"} & names


def test_stems_match_inserts_by_the_name_they_end_with():
    inserts = {1: "Kick", 2: "Bass", 3: "Bass 2", 4: "Lead Vox", 5: "Insert 5"}
    m = match_inserts(["My Song_Kick", "My Song_Bass 2", "My Song_Bass", "My Song_Lead_Vox", "My Song_Pad"], inserts)
    assert m == {"My Song_Kick": 1, "My Song_Bass 2": 3, "My Song_Bass": 2, "My Song_Lead_Vox": 4}
