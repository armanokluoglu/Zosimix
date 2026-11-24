"""Spike: can we drive FL Studio 20.9.2 from outside over SysEx, and trust what it reports back?

Requirements (see spike/NOTES.md, "Bridge test setup"):
  - loopMIDI running with two ports: "Zosimix In" and "Zosimix Out"
  - fl_bridge/device_Zosimix.py installed and enabled in FL's MIDI settings
  - an FL project open with Fruity Parametric EQ 2 in the FIRST effect slot of mixer insert 1

Usage:  .venv/Scripts/python spike/bridge_test.py
Everything this script changes is restored at the end.
"""

from __future__ import annotations

import statistics
import sys
import time

import mido

HEADER = [0x7D, 0x5A]          # mido strips F0/F7; 7D = non-commercial ID, 5A = 'Z'
TIMEOUT_S = 2.0
TRACK, SLOT = 1, 0


class Bridge:
    def __init__(self) -> None:
        self.out = mido.open_output(self._find(mido.get_output_names(), "Zosimix In"))
        self.inp = mido.open_input(self._find(mido.get_input_names(), "Zosimix Out"))
        self.next_id = 0

    @staticmethod
    def _find(names: list[str], prefix: str) -> str:
        for n in names:
            if n.startswith(prefix):
                return n
        sys.exit(f"MIDI port starting with '{prefix}' not found. Available: {names}")

    def call(self, command: str, *args: object) -> list[str]:
        self.next_id += 1
        req_id = str(self.next_id)
        text = " ".join([req_id, command, *map(str, args)])
        self.out.send(mido.Message("sysex", data=HEADER + list(text.encode("ascii"))))
        deadline = time.perf_counter() + TIMEOUT_S
        while time.perf_counter() < deadline:
            for msg in self.inp.iter_pending():
                if msg.type != "sysex" or list(msg.data[:2]) != HEADER:
                    continue
                parts = bytes(msg.data[2:]).decode("ascii").split()
                if parts and parts[0] == req_id:
                    if parts[1] != "ok":
                        raise RuntimeError(f"{command}: {' '.join(parts[2:])}")
                    return parts[2:]
            time.sleep(0.001)
        raise TimeoutError(f"no reply to '{text}' within {TIMEOUT_S}s")


results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def close(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


def settle(fl: Bridge, getter: str, track: int, target: float, timeout_s: float = 1.0) -> tuple[float, float]:
    """Mixer writes are applied after the script callback returns, so the setter's own
    read-back is stale. Poll the getter until it matches; return (value, ms until it did)."""
    t0 = time.perf_counter()
    while True:
        value = float(fl.call(getter, track)[0])
        elapsed = (time.perf_counter() - t0) * 1000
        if close(value, target) or elapsed > timeout_s * 1000:
            return value, elapsed
        time.sleep(0.005)


def main() -> int:
    fl = Bridge()

    # 1. Round trip + latency
    timings = []
    version = None
    for _ in range(30):
        t0 = time.perf_counter()
        version = fl.call("ping")[1]
        timings.append((time.perf_counter() - t0) * 1000)
    check("ping", True, f"API version {version}; round trip median {statistics.median(timings):.1f} ms, "
                        f"max {max(timings):.1f} ms over 30 calls")

    # 2. Fader
    orig_vol = float(fl.call("get_volume", TRACK)[0])
    immediate = float(fl.call("set_volume", TRACK, 0.5)[0])
    got, ms = settle(fl, "get_volume", TRACK, 0.5)
    db = fl.call("get_volume_db", TRACK)[0]
    check("fader write+readback", close(got, 0.5),
          f"set 0.5 -> immediate {immediate:.3f}, settled {got:.3f} after {ms:.0f} ms ({float(db):.2f} dB)")
    fl.call("set_volume", TRACK, orig_vol)
    settle(fl, "get_volume", TRACK, orig_vol)

    # 3. Pan
    orig_pan = float(fl.call("get_pan", TRACK)[0])
    immediate = float(fl.call("set_pan", TRACK, 0.3)[0])
    got, ms = settle(fl, "get_pan", TRACK, 0.3)
    check("pan write+readback", close(got, 0.3),
          f"set 0.3 -> immediate {immediate:.3f}, settled {got:.3f} after {ms:.0f} ms")
    fl.call("set_pan", TRACK, orig_pan)
    settle(fl, "get_pan", TRACK, orig_pan)

    # 4. Polarity
    orig_pol = fl.call("get_polarity", TRACK)[0]
    on = fl.call("set_polarity", TRACK, 1)[0]
    off = fl.call("set_polarity", TRACK, 0)[0]
    check("polarity write+readback", on == "1" and off == "0", f"set 1 -> {on}, set 0 -> {off}")
    fl.call("set_polarity", TRACK, orig_pol)

    # 5. Plugin in slot: discover Parametric EQ 2's parameters
    name = fl.call("plugin_name", TRACK, SLOT)[0]
    if name == "none":
        check("plugin in slot", False, f"no plugin in insert {TRACK}, slot {SLOT + 1}; add Fruity Parametric EQ 2 there")
    else:
        count = int(fl.call("param_count", TRACK, SLOT)[0])
        print(f"\nPlugin '{name}' has {count} parameters. First 60:")
        params = []
        for i in range(min(count, 60)):
            pname, value, shown = fl.call("param_info", TRACK, SLOT, i)
            params.append((i, pname, float(value)))
            print(f"  {i:3d}  {pname:<28} {value:<22} {shown}")
        print()

        # Try writing every named parameter to a test value, read back, restore.
        # Stepped parameters (band type, filter order) snap to the nearest step by design;
        # that counts as honoured as long as the value actually moved off the original.
        exact = snapped = ignored = 0
        for i, pname, value in params:
            if pname == "-":
                continue
            target = 0.25 if value > 0.5 else 0.75
            got = float(fl.call("set_param", TRACK, SLOT, i, target)[0])
            if close(got, target, tol=0.02):
                exact += 1
            elif not close(got, value, tol=1e-6):
                snapped += 1
                print(f"  stepped: #{i} {pname}: set {target} -> snapped to {got:.4f}")
            else:
                ignored += 1
                print(f"  IGNORED: #{i} {pname}: set {target} -> still {got}")
            fl.call("set_param", TRACK, SLOT, i, value)
        check("plugin param write+readback", ignored == 0,
              f"'{name}': {exact} exact, {snapped} stepped (snap to nearest step), {ignored} ignored")

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
