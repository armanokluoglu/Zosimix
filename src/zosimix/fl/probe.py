"""Read FL's own value scales through the bridge: calibration step 1 of 2 (D55).

FL's API works in normalized 0..1 knob positions. This sweeps each control on insert 1
and records what FL says that position means (dB, Hz, ...), so the FL engine can convert
the mix state's real units into knob positions. Step 2 (audio) measures what the
controls actually do to sound, using command-line renders.

Needs FL open with the Zosimix24 template (fl_bridge/TEMPLATE.md). Everything it changes
is put back at the end.

Usage:
    python -m zosimix.fl.probe            # writes fl_bridge/calibration/probe.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from zosimix.fl.bridge import Bridge, BridgeError

OUT = Path(__file__).resolve().parents[3] / "fl_bridge" / "calibration" / "probe.json"
TRACK, SLOT = 1, 0
STEPS = np.linspace(0.0, 1.0, 41)
BIPOLAR = np.linspace(-1.0, 1.0, 41)    # pan and stereo separation run -1..+1, centre 0


def sweep_mixer(fl: Bridge, setter: str, getter: str, reader: str | None = None,
                positions: np.ndarray = STEPS, tol: float = 1e-3) -> list[list]:
    """Positions and what FL reports for each. `reader` is an extra getter (e.g. dB).

    `tol` is how far FL may snap a value. Stereo separation moves in steps of 1/32, so it
    needs a looser tolerance than the fader and pan.
    """
    original = float(fl.call(getter, TRACK)[0])
    rows = []
    try:
        for x in positions:
            held = fl.set_and_confirm(setter, getter, TRACK, float(x), tol=tol)
            rows.append([round(float(x), 4), held, *(fl.call(reader, TRACK) if reader else [])])
    finally:
        fl.set_and_confirm(setter, getter, TRACK, original, tol=tol)
    return rows


def sweep_plugin(fl: Bridge) -> dict:
    """For every PEQ2 parameter: its name, default and the display string at each position."""
    count = int(fl.call("param_count", TRACK, SLOT)[0])
    params = {}
    for p in range(count):
        name, default, shown = fl.call("param_info", TRACK, SLOT, p)
        rows = []
        try:
            for x in STEPS:
                held = float(fl.call("set_param", TRACK, SLOT, p, float(x))[0])
                rows.append([round(float(x), 4), held, fl.call("param_info", TRACK, SLOT, p)[2]])
        finally:
            fl.call("set_param", TRACK, SLOT, p, float(default))
        params[p] = {"name": name, "default": float(default), "default_shown": shown, "sweep": rows}
    return params


def main() -> None:
    with Bridge() as fl:
        print("FL:", fl.ping())
        plugin = fl.call("plugin_name", TRACK, SLOT)[0]
        if "parametric" not in plugin.lower():          # FL reports "Fruity parametric EQ 2"
            raise SystemExit(f"insert {TRACK} slot {SLOT} holds {plugin!r}, expected Fruity Parametric EQ 2")
        result: dict = {"plugin": plugin}
        result["volume"] = sweep_mixer(fl, "set_volume", "get_volume", "get_volume_db")
        result["pan"] = sweep_mixer(fl, "set_pan", "get_pan", positions=BIPOLAR)
        try:
            result["stereo_sep"] = sweep_mixer(fl, "set_sep", "get_sep", positions=BIPOLAR, tol=0.02)
        except BridgeError as exc:          # older API without stereo separation
            result["stereo_sep"] = f"unavailable: {exc}"
        result["peq2"] = sweep_plugin(fl)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {OUT}: volume, pan, stereo_sep and {len(result['peq2'])} PEQ2 parameters")


if __name__ == "__main__":
    main()
