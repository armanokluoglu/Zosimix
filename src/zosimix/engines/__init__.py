"""Mix engines: things that turn (stems + MixState) into audio.

Two engines implement the same interface (DESIGN.md §3.3, D11):
  - OfflineEngine: pure Python (pedalboard), fast and reproducible. Used for development,
    for the verification hook's previews (D36), and by anyone without FL Studio.
  - FLEngine (days 9-10): drives FL Studio over the SysEx bridge and renders through FL.
"""

from zosimix.engines.base import MixEngine

__all__ = ["MixEngine"]
