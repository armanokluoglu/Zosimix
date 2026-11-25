"""The fixed WAV paths the FL template points to (D55).

FL's scripting API can't load audio or open files, and we never edit .flp files (D14).
So one hand-built template, Zosimix24.flp, has 24 audio clips that point at
C:\\zosimix\\fl\\slots\\slot01.wav .. slot24.wav, each routed to mixer insert 1..24 with
Fruity Parametric EQ 2 in its first effect slot. To put a song into FL, we overwrite
those WAV files before FL opens the project.

The root is a fixed, short path because the template stores absolute paths. It has no
spaces (FL's command line can't handle them) and no user name (the template is
committed to a public repo).

Usage:
    python -m zosimix.fl.slots placeholders     # once, before building the template
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from zosimix import audio

FL_ROOT = Path("C:/zosimix/fl")
SLOTS_DIR = FL_ROOT / "slots"
TEMPLATE = FL_ROOT / "Zosimix24.flp"
N_SLOTS = 24                     # the largest song has 24 stems
PLACEHOLDER_SECONDS = 300        # longer than any song (max 243 s), so every clip is long enough
SR = 44100


def slot_path(i: int) -> Path:
    """Slot i (1-based) = audio clip i = mixer insert i."""
    return SLOTS_DIR / f"slot{i:02d}.wav"


def write_placeholders(seconds: int = PLACEHOLDER_SECONDS, sr: int = SR) -> None:
    """Silent WAVs to build the template with. Their length sets each clip's length in FL."""
    SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    silence = np.zeros((seconds * sr, 1), dtype=np.int16)          # mono 16-bit keeps them small
    for i in range(1, N_SLOTS + 1):
        sf.write(slot_path(i), silence, sr, subtype="PCM_16")


def write_song(stems: dict[str, np.ndarray], sr: int) -> dict[int, str]:
    """Write a song's stems into slots 1..n (in the given order) and silence the rest.

    Returns {slot: stem name}. Stems are written as stereo 32-bit float, so nothing is lost
    on the way into FL.
    """
    if len(stems) > N_SLOTS:
        raise ValueError(f"{len(stems)} stems, but the template has only {N_SLOTS} slots")
    if sr != SR:
        raise ValueError(f"the template runs at {SR} Hz, the song at {sr} Hz")
    mapping = {}
    for i, (name, a) in enumerate(stems.items(), start=1):
        audio.write(slot_path(i), audio.to_stereo(np.asarray(a)), sr)
        mapping[i] = name
    for i in range(len(stems) + 1, N_SLOTS + 1):
        sf.write(slot_path(i), np.zeros((sr, 2), dtype=np.float32), sr, subtype="FLOAT")    # 1 s of silence
    return mapping


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["placeholders"])
    ap.parse_args()
    write_placeholders()
    print(f"wrote {N_SLOTS} placeholder WAVs ({PLACEHOLDER_SECONDS} s of silence each) to {SLOTS_DIR}")


if __name__ == "__main__":
    main()
