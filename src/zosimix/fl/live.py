"""Apply the harness's fix to the FL Studio project you have open (D84).

The plugin's workflow: export the project's mixer tracks from FL ("Split mixer tracks"),
let the agent diagnose and repair them, then push the repair back into the open project
over the Zosimix MIDI bridge. Those stems were exported *after* each insert's fader, pan and
effects, so every change here is relative to what the insert holds now:

  gain      the insert's fader moves by the fix's gain (it tops out at +5.6 dB)
  pan       the insert's pan knob moves by the fix's pan value. FL's mixer pan law isn't the
            harness's balance control (D57), so this is close but not exact: check by ear
  polarity  the insert's polarity switch flips if the fix inverts the track
  eq        bands go into a Fruity Parametric EQ 2 on the insert whose bands are all still
            flat. FL's scripting API can't add plugins, so without one, the plan says where to
            add it
  width     not applied (the stereo separation knob would need the insert's current setting);
            the plan says so

`plan` reads the project and returns the changes as data, without touching anything;
`apply` makes them and returns what it needs to undo them; `revert` puts them back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from zosimix.fl import controls
from zosimix.fl.bridge import Bridge
from zosimix.mixstate import MixState

N_INSERTS = 125                  # FL 20's mixer: master + 125 inserts (+ the current track)
N_SLOTS = 10
PEQ2 = "fruity parametric eq 2"
BANDS = 7


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def match_inserts(stem_names: list[str], insert_names: dict[int, str]) -> dict[str, int]:
    """Stem file name -> mixer insert, by name. FL names split-export files after the project
    and the insert ("My Song_Bass.wav"), so a stem matches the insert whose name it ends with.
    The longest such name wins, so "Bass 2" isn't taken for "Bass"."""
    out = {}
    for stem in stem_names:
        s = _norm(stem)
        best = None
        for insert, name in insert_names.items():
            n = _norm(name)
            if n and (s == n or s.endswith(" " + n)) and (best is None or len(n) > len(_norm(insert_names[best]))):
                best = insert
        if best is not None:
            out[stem] = best
    return out


@dataclass
class Change:
    stem: str
    insert: int
    what: str                    # "gain", "pan", "polarity", "eq", "note"
    detail: str                  # plain language for the user
    calls: list[tuple] = field(default_factory=list)      # (command, *args) to apply it
    undo: list[tuple] = field(default_factory=list)       # (command, *args) to undo it


def _fresh_peq2(fl: Bridge, insert: int) -> int | None:
    """The effect slot of a Parametric EQ 2 on this insert whose seven bands are all at 0 dB."""
    flat = controls.eq_level_pos(0.0)
    for slot in range(N_SLOTS):
        name = fl.call("plugin_name", insert, slot)[0].replace("_", " ").lower()
        if PEQ2 not in name:
            continue
        levels = [float(fl.call("param_info", insert, slot, controls.level_param(b))[1]) for b in range(1, BANDS + 1)]
        if all(abs(v - flat) < 1e-3 for v in levels):
            return slot
    return None


def plan(fl: Bridge, state: MixState) -> tuple[list[Change], list[str]]:
    """What applying `state` to the open project would change, plus stems that matched no insert."""
    names = {i: fl.call("get_name", i)[0].replace("_", " ") for i in range(1, N_INSERTS + 1)}
    changed = {n: t for n, t in state.tracks.items() if not t.is_neutral()}
    inserts = match_inserts(list(changed), names)
    unmatched = sorted(set(changed) - set(inserts))
    changes: list[Change] = []
    for stem, t in changed.items():
        if stem not in inserts:
            continue
        i = inserts[stem]
        label = f"insert {i} ({names[i]})"
        if abs(t.gain_db) > 1e-6:
            now = float(fl.call("get_volume_db", i)[0])
            target = min(now + t.gain_db, controls.FADER_MAX_DB)
            short = (now + t.gain_db) - target
            detail = f"{label}: fader {now:+.1f} -> {target:+.1f} dB"
            if short > 0.05:
                detail += f" (the fader stops at +5.6 dB: {short:.1f} dB short)"
            pos_now = float(fl.call("get_volume", i)[0])
            changes.append(Change(stem, i, "gain", detail, [("fader_db", i, target)], [("set_volume", i, pos_now)]))
        if abs(t.pan) > 1e-6:
            now = float(fl.call("get_pan", i)[0])
            target = max(-1.0, min(1.0, now + t.pan))
            changes.append(Change(stem, i, "pan", f"{label}: pan {now:+.2f} -> {target:+.2f} (FL's pan law differs "
                                  "slightly from the harness's; check by ear)",
                                  [("set_pan", i, target)], [("set_pan", i, now)]))
        if t.polarity:
            now = int(fl.call("get_polarity", i)[0])
            changes.append(Change(stem, i, "polarity", f"{label}: polarity {'normal' if now else 'inverted'}",
                                  [("set_polarity", i, 1 - now)], [("set_polarity", i, now)]))
        if abs(t.width - 1.0) > 1e-6:
            changes.append(Change(stem, i, "note", f"{label}: stereo width x{t.width:.2f} is not applied "
                                  "automatically; set the insert's stereo separation by hand"))
        bands = [b for b in t.eq if not b.is_neutral()]
        if bands:
            slot = _fresh_peq2(fl, i)
            text = ", ".join(f"{b.type} {b.freq_hz:.0f} Hz {b.gain_db:+.1f} dB Q {b.q:.2f}" for b in bands)
            if slot is None:
                changes.append(Change(stem, i, "note", f"{label}: EQ ({text}) needs a Fruity Parametric EQ 2 with "
                                      "flat bands on this insert; add one to any empty slot and apply again"))
                continue
            calls, undo = [], []
            for n, b in enumerate(bands[:BANDS], start=1):
                passes = b.type in ("highpass", "lowpass")
                for param, pos in ((controls.type_param(n), controls.eq_type_pos(b.type)),
                                   (controls.freq_param(n), controls.eq_freq_pos(b.freq_hz)),
                                   (controls.level_param(n), controls.eq_level_pos(0.0 if passes else b.gain_db)),
                                   (controls.width_param(n), controls.eq_width_pos(b.type, b.q)),
                                   (controls.order_param(n), controls.eq_order_pos("2"))):
                    old = float(fl.call("param_info", i, slot, param)[1])
                    calls.append(("set_param", i, slot, param, pos))
                    undo.append(("set_param", i, slot, param, old))
            changes.append(Change(stem, i, "eq", f"{label}: EQ in slot {slot + 1}: {text}", calls, undo))
    return changes, unmatched


def apply(fl: Bridge, changes: list[Change]) -> list[tuple]:
    """Make the changes. Returns the undo calls, newest first."""
    undo: list[tuple] = []
    for c in changes:
        for call in c.calls:
            if call[0] == "fader_db":
                controls.set_fader_db(fl, call[1], call[2], tol_db=0.05)
            else:
                fl.call(*call)
        undo = list(c.undo) + undo
    return undo


def revert(fl: Bridge, undo: list[tuple]) -> int:
    for call in undo:
        if call[0] == "set_volume":
            fl.set_and_confirm("set_volume", "get_volume", call[1], call[2])
        else:
            fl.call(*call)
    return len(undo)
