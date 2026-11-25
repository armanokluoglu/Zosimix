"""The FL side of the flstudio-mcp baseline (D66, D70).

The third configuration is Claude Code working in FL Studio through rosasynthesiz/flstudio-mcp,
ported to FL 20.9.2 (zosimix.fl.port_flstudio_mcp). For each task:

  1. `open_task` writes the task's stems (one of them faulty) into the template's slots, opens
     a fresh copy of the template in FL, and names each used insert after its stem. Everything
     else stays as the template has it: faders at 0 dB, pans centred, Parametric EQ 2 flat in
     effect slot 0 of every insert. FL stays open while the agent works.
  2. The agent changes the mix in FL through flstudio-mcp. Our own bridge stays connected on
     its own MIDI ports and doesn't touch anything meanwhile.
  3. `read_back` turns the agent's mix into the renders the graders need
     (graders.render_groups): it stops playback, notes the agent's mutes and solos, and for each
     group of tracks mutes everything outside it, saves and keeps a copy of the project. Then FL
     is closed and each copy is rendered from the command line.

Two settings belong to grading, not to the agent's mix:
  - the master fader is set RENDER_HEADROOM_DB down for every grading render, whatever the agent
    did to it. The master's level is not part of any task, the prompt asks the agent to leave it
    alone, and the headroom keeps a loud mix from clipping FL's 24-bit file (as in the FL engine).
  - solos are cleared and turned into mutes: a soloed track means "only these play".
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from zosimix.engines.fl import FADER_TOL_DB, MASTER, RENDER_HEADROOM_DB, render_project
from zosimix.fl import controls, session, slots
from zosimix.fl.bridge import Bridge, BridgeError

FLMCP_DIR = Path("C:/zosimix/baselines/flstudio-mcp")
FLMCP_SERVER = FLMCP_DIR / ".venv" / "Scripts" / "fl-studio-mcp.exe"
SETTLE_S = 1.0          # FL applies a mute a moment after the call returns (seen in the live check)

# The flstudio-mcp tools the agent gets (D70): reading the mix, faders, pans, mutes and solos,
# plugin parameters (the Parametric EQ 2 on every insert), its EQ intent, meters and Mix Doctor,
# transport (meters only move during playback), snapshots and rollback.
# Left out: composition and arrangement (piano roll, patterns, playlist, MIDI, tempo), audio
# file analysis and reference matching (they read files, and there is no reference), routing
# changes, renaming and colours, presets and plugin loading (FL's API can't load plugins),
# reverb/delay/compression intents (no such plugin is loaded), dry-run mode and screenshots
# (fl_screenshot can capture the whole desktop).
MIXING_TOOLS = [
    "fl_ping", "fl_capabilities", "fl_get_project_state",
    "fl_play", "fl_stop", "fl_toggle_play", "fl_get_play_state", "fl_get_song_position", "fl_set_song_position",
    "fl_get_mixer_state", "fl_get_channel_state",
    "fl_set_mixer_volume", "fl_set_mixer_pan", "fl_set_mixer_mute", "fl_set_mixer_solo",
    "fl_set_channel_volume", "fl_set_channel_pan", "fl_set_channel_mute", "fl_set_channel_solo",
    "fl_solo_tracks", "fl_mute_tracks", "fl_clear_mute_solo",
    "fl_take_snapshot", "fl_rollback_last_change",
    "fl_plugin_list", "fl_plugin_get_params", "fl_plugin_find_params", "fl_plugin_overview",
    "fl_plugin_set_param", "fl_plugin_set_params", "fl_plugin_calibrate_param", "fl_plugin_set_param_value",
    "fl_plugin_intent", "fl_apply_eq_intent",
    "fl_get_track_level", "fl_diagnose_mix", "fl_apply_mix_fix", "fl_gain_stage",
    "fl_mix_watch_start", "fl_mix_watch_status", "fl_mix_watch_stop",
    "fl_get_routing", "fl_get_routing_all", "fl_get_channel_routing",
]
# The rest of the server's 91 tools at commit 2b2d664. They are passed to --disallowedTools,
# which removes them from the agent's view entirely (a tool that is merely not allowed would
# still be listed, and calling it would just be refused). A test checks that the two lists
# together are exactly what the server offers.
EXCLUDED_TOOLS = [
    "fl_get_tempo", "fl_set_tempo", "fl_record", "fl_set_mixer_name", "fl_set_dry_run",
    "fl_write_piano_roll_notes", "fl_quantize_pattern",
    "fl_apply_reverb_intent", "fl_apply_delay_intent", "fl_apply_compression_intent",
    "fl_detect_cleanup_candidates", "fl_set_route", "fl_group_tracks", "fl_set_track_color", "fl_set_channel_color",
    "fl_arrange_new_pattern", "fl_arrange_select_channel", "fl_arrange_clone_pattern", "fl_arrange_add_marker",
    "fl_analyze_audio", "fl_extract_melody", "fl_extract_chords", "fl_write_raga_melody", "fl_write_raga_chords",
    "fl_list_chains", "fl_list_installed_plugins", "fl_setup_chain", "fl_export_midi", "fl_list_presets",
    "fl_suggest_preset", "fl_reference_match", "fl_get_step_grid", "fl_set_step_grid", "fl_extract_drums",
    "fl_pattern_list", "fl_pattern_select", "fl_pattern_rename", "fl_pattern_get_length", "fl_load_plugin",
    "fl_playlist_tracks", "fl_playlist_mute_track", "fl_playlist_solo_track", "fl_playlist_rename_track",
    "fl_playlist_set_track_color", "fl_arrangement_selection", "fl_arrangement_markers", "fl_screenshot",
]


@dataclass
class OpenTask:
    fl_session: session.FLSession
    inserts: dict[int, str]               # mixer insert -> stem name (insert k plays slot k)
    length: int                           # frames
    sample_rate: int
    agent_state: dict = field(default_factory=dict)   # what the agent left behind, for the record

    @property
    def fl(self) -> Bridge:
        return self.fl_session.fl


@contextmanager
def open_task(stems: dict[str, np.ndarray], sample_rate: int) -> Iterator[OpenTask]:
    """FL open on a fresh template copy holding these stems, inserts named after them."""
    inserts = slots.write_song(stems, sample_rate)
    project = session.new_project("flmcp")
    with session.FLSession(project) as s:
        for insert, name in inserts.items():
            s.fl.call("set_name", insert, name.replace(" ", "_"))
        s.save()
        yield OpenTask(s, inserts, max(len(a) for a in stems.values()), sample_rate)


def _set_flag(fl: Bridge, command: str, insert: int, on: bool, tries: int = 3) -> None:
    """Set a mute or solo and wait until FL holds it. FL applies a mute a moment later, and in
    a live check the first mute of a session was dropped altogether, so the write is retried."""
    getter = command.replace("set_", "get_")
    for attempt in range(tries):
        try:
            fl.set_and_confirm(command, getter, insert, int(on), tol=0.5)
            return
        except BridgeError:
            if attempt == tries - 1:
                raise


def read_back(task: OpenTask, groups: list[frozenset[str]]) -> dict[frozenset[str], np.ndarray]:
    """Render each group of stems as the agent left it, every other track muted. Closes FL."""
    fl = task.fl
    fl.call("stop")
    time.sleep(SETTLE_S)                          # let the agent's last mute or solo land (D70)
    slot_of = {name: insert for insert, name in task.inserts.items()}
    muted = {i for i in task.inserts if fl.call("get_mute", i)[0] == "1"}
    soloed = {i for i in task.inserts if fl.call("get_solo", i)[0] == "1"}
    task.agent_state = {
        "muted": sorted(task.inserts[i] for i in muted),
        "soloed": sorted(task.inserts[i] for i in soloed),
        "master_db": round(float(fl.call("get_volume_db", MASTER)[0]), 2),
    }
    if soloed:                                    # "only the soloed tracks play"
        muted |= set(task.inserts) - soloed
    for i in soloed:
        _set_flag(fl, "set_solo", i, False)
    master_db = controls.set_fader_db(fl, MASTER, -RENDER_HEADROOM_DB, tol_db=FADER_TOL_DB)

    project = task.fl_session.project
    copies = {}
    for n, group in enumerate(groups):
        audible = {slot_of[name] for name in group}
        for i in task.inserts:
            _set_flag(fl, "set_mute", i, i not in audible or i in muted)
        task.fl_session.save()
        copies[group] = project.with_name(f"{project.stem}_group{n}.flp")
        shutil.copy2(project, copies[group])
    task.fl_session.close()
    return {g: render_project(path, task.length, task.sample_rate, master_db) for g, path in copies.items()}
