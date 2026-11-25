"""Client for the SysEx bridge to FL Studio (D31, D35).

The script inside FL (fl_bridge/device_Zosimix.py) answers plain-text commands sent as
SysEx over two loopMIDI ports. This module sends a command, waits for the reply with
the same id, and returns the reply's values as strings.

Two quirks found in the spike shape this API:
  - Mixer writes take effect only after FL's script callback returns, so a setter's own
    read-back is stale. `set_and_confirm` polls a separate getter until it matches.
  - Some plugin parameters are stepped (PEQ2 band type and order) and snap to the
    nearest step, so callers compare stepped values with a looser tolerance.

Needs the "fl" extra (mido + python-rtmidi) and loopMIDI with ports "Zosimix In" and
"Zosimix Out".
"""

from __future__ import annotations

import time
from typing import Self

HEADER = [0x7D, 0x5A]          # mido strips F0/F7; 7D = non-commercial ID, 5A = 'Z'
IN_PORT, OUT_PORT = "Zosimix In", "Zosimix Out"


class BridgeError(RuntimeError):
    """FL answered with an error, or didn't answer at all."""


class Bridge:
    def __init__(self, timeout_s: float = 2.0) -> None:
        import mido  # here, not at the top, so the rest of zosimix works without the extra

        self._mido = mido
        self.timeout_s = timeout_s
        self.out = mido.open_output(self._find(mido.get_output_names(), IN_PORT))
        self.inp = mido.open_input(self._find(mido.get_input_names(), OUT_PORT))
        self.next_id = 0

    @staticmethod
    def _find(names: list[str], prefix: str) -> str:
        for n in names:
            if n.startswith(prefix):
                return n
        raise BridgeError(f"MIDI port starting with {prefix!r} not found (is loopMIDI running?). "
                          f"Available: {names}")

    def close(self) -> None:
        self.out.close()
        self.inp.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def call(self, command: str, *args: object) -> list[str]:
        """Send one command and return the reply's values. Raises BridgeError on 'err' or timeout."""
        self.next_id += 1
        req_id = str(self.next_id)
        text = " ".join([req_id, command, *map(str, args)])
        self.out.send(self._mido.Message("sysex", data=HEADER + list(text.encode("ascii"))))
        deadline = time.perf_counter() + self.timeout_s
        while time.perf_counter() < deadline:
            for msg in self.inp.iter_pending():
                if msg.type != "sysex" or list(msg.data[:2]) != HEADER:
                    continue
                parts = bytes(msg.data[2:]).decode("ascii", "replace").split()
                if parts and parts[0] == req_id:
                    if len(parts) < 2 or parts[1] != "ok":
                        raise BridgeError(f"{text}: {' '.join(parts[2:])}")
                    return parts[2:]
            time.sleep(0.001)
        raise BridgeError(f"no reply to {text!r} within {self.timeout_s}s (is FL open with the Zosimix script?)")

    def set_and_confirm(self, setter: str, getter: str, track: int, value: float,
                        tol: float = 1e-4, timeout_s: float = 1.0) -> float:
        """Write a mixer value, then poll the getter until FL holds it (see module docstring)."""
        self.call(setter, track, value)
        deadline = time.perf_counter() + timeout_s
        while True:
            held = float(self.call(getter, track)[0])
            if abs(held - value) <= tol:
                return held
            if time.perf_counter() > deadline:
                raise BridgeError(f"{setter} {track} {value}: FL still holds {held}")
            time.sleep(0.002)

    def ping(self) -> str:
        return " ".join(self.call("ping"))
