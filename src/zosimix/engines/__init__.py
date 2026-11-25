"""Mix engines: things that turn (stems + MixState) into audio.

Two engines implement the same interface (DESIGN.md §3.3, D11):
  - OfflineEngine: pure Python (numpy/scipy), fast and reproducible. Used for development,
    for the verification hook's previews (D36), and by anyone without FL Studio.
  - FLEngine (engines/fl.py): drives FL Studio over the SysEx bridge and renders the whole mix
    through FL. Too slow for previews; used for final renders and the parity check (D63, D64).
"""

from zosimix.engines.base import MixEngine

__all__ = ["MixEngine"]
