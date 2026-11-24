"""Songs on disk, and the check that their stems really add up to the mix.

Every dataset is normalized to the same layout so nothing downstream cares where a
song came from:

    data/songs/<song_id>/
        stems/<stem_name>.wav     one file per stem
        reference.wav             the dataset's own mix or master (optional)
        song.json                 source, license, attribution

The clean ground truth for every task is the plain sum of the stems (audio.mix).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from zosimix import audio

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "songs"

# Instrument families, used for stem selection and for vague client hints.
# Order matters: the first prefix that matches a stem name wins.
FAMILIES = [
    ("vox", "vocals"), ("vocal", "vocals"),
    ("drums", "drums"), ("kick", "drums"), ("snare", "drums"), ("overhead", "drums"),
    ("bass", "bass"),
    ("guitar", "guitars"),
    ("keys", "keys"), ("piano", "keys"), ("synth", "keys"), ("organ", "keys"),
    ("violin", "strings"), ("viola", "strings"), ("cello", "strings"), ("strings", "strings"),
]


def family_of(stem_name: str) -> str:
    lowered = stem_name.lower()
    for prefix, family in FAMILIES:
        if lowered.startswith(prefix):
            return family
    return "other"


@dataclass
class Song:
    song_id: str
    folder: Path

    @property
    def stem_paths(self) -> dict[str, Path]:
        return {p.stem: p for p in sorted((self.folder / "stems").glob("*.wav"))}

    def load_stems(self) -> tuple[dict[str, np.ndarray], int]:
        stems, rates = {}, set()
        for name, path in self.stem_paths.items():
            stems[name], sr = audio.read(path)
            rates.add(sr)
        if len(rates) != 1:
            raise ValueError(f"{self.song_id}: stems have mixed sample rates {rates}")
        return stems, rates.pop()

    @property
    def info(self) -> dict:
        return json.loads((self.folder / "song.json").read_text(encoding="utf-8"))


def list_songs(root: Path = DATA_ROOT) -> list[Song]:
    return [Song(p.name, p) for p in sorted(root.iterdir()) if (p / "stems").is_dir()] if root.exists() else []


@dataclass
class SumCheck:
    """How well the stem sum matches the dataset's own mix.

    gain_db: level offset that best aligns the sum to the reference (a master is often louder).
    correlation: 1.0 means identical shape after gain matching.
    residual_db: energy of what's left after gain matching, relative to the reference.
    """
    song_id: str
    gain_db: float
    correlation: float
    residual_db: float

    @property
    def exact(self) -> bool:
        return self.residual_db < -60.0

    @property
    def plausible(self) -> bool:
        """Mastered references won't null, but they must clearly be the same music."""
        return self.correlation > 0.9


def check_stem_sum(song: Song) -> SumCheck:
    stems, sr = song.load_stems()
    total = audio.mix(stems)
    reference, ref_sr = audio.read(song.folder / "reference.wav")
    if ref_sr != sr:
        raise ValueError(f"{song.song_id}: reference is {ref_sr} Hz, stems are {sr} Hz")
    reference = audio.to_stereo(reference)
    n = min(len(total), len(reference))
    s, r = total[:n].ravel(), reference[:n].ravel()
    gain = float(np.dot(s, r) / max(np.dot(s, s), 1e-20))          # least-squares gain match
    residual = r - gain * s
    correlation = float(np.dot(s, r) / np.sqrt(max(np.dot(s, s) * np.dot(r, r), 1e-20)))
    return SumCheck(
        song_id=song.song_id,
        gain_db=audio.gain_to_db(abs(gain)),
        correlation=correlation,
        residual_db=audio.gain_to_db(audio.rms(residual) / max(audio.rms(r), 1e-20)),
    )
