"""The offline engine: renders stems + MixState in pure Python (DESIGN.md §3.3, D11).

Per track, in FL's order (D61):
    polarity -> EQ bands -> pan (balance) -> stereo width -> gain
then every track is summed into the stereo mix. There is no master processing.
Polarity, EQ and gain treat both channels alike, so their position doesn't matter. Pan
and width don't commute: FL applies the channel-rack pan before the mixer insert's
stereo separation, so pan comes first here too.

Rendering is fast because processed stems are cached: changing one track's settings only
re-renders that track. A full song with no EQ renders in well under a second.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from zosimix import audio, eq
from zosimix.engines.base import MixEngine
from zosimix.mixstate import MixState, TrackState


def process_track(stem: np.ndarray, t: TrackState, sr: int) -> np.ndarray:
    """Apply one track's settings to one stereo stem. Returns a new (frames, 2) array."""
    x = -stem if t.polarity else stem.copy()

    active = [(b.type, b.freq_hz, b.gain_db, b.q) for b in t.eq if not b.is_neutral()]
    if active:
        x = eq.apply(x, active, sr)

    if t.pan != 0.0:
        left, right = audio.pan_gains(t.pan)
        x = x * np.array([left, right])

    if t.width != 1.0:
        mid = (x[:, 0] + x[:, 1]) / 2.0
        side = (x[:, 0] - x[:, 1]) / 2.0 * t.width
        x = np.stack([mid + side, mid - side], axis=1)

    if t.gain_db != 0.0:
        x = x * audio.db_to_gain(t.gain_db)
    return x


class OfflineEngine(MixEngine):
    def __init__(self, stems: dict[str, np.ndarray], sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self._stems = {name: audio.to_stereo(a) for name, a in stems.items()}
        self._state = MixState.neutral(list(self._stems))
        self._cache: dict[str, tuple[str, np.ndarray]] = {}       # stem -> (settings key, processed)

    @classmethod
    def from_workspace(cls, workspace: Path) -> OfflineEngine:
        """Load every stems/*.wav of a task workspace (see zosimix.tasks.materialize)."""
        stems, rates = {}, set()
        for path in sorted((workspace / "stems").glob("*.wav")):
            stems[path.stem], sr = audio.read(path)
            rates.add(sr)
        if len(rates) != 1:
            raise ValueError(f"stems have mixed sample rates: {rates}")
        return cls(stems, rates.pop())

    @property
    def stem_names(self) -> list[str]:
        return list(self._stems)

    def get_state(self) -> MixState:
        return copy.deepcopy(self._state)

    def set_state(self, state: MixState) -> None:
        state.validate()
        unknown = set(state.tracks) - set(self._stems)
        if unknown:
            raise ValueError(f"unknown stems in mix state: {sorted(unknown)}")
        merged = MixState.neutral(self.stem_names)          # stems not mentioned stay neutral
        merged.tracks.update(copy.deepcopy(state.tracks))
        self._state = merged

    def render_stems(self) -> dict[str, np.ndarray]:
        out = {}
        for name, stem in self._stems.items():
            settings = self._state.tracks[name]
            key = json.dumps(MixState({name: settings}).to_dict(), sort_keys=True)
            cached = self._cache.get(name)
            if cached is None or cached[0] != key:
                processed = stem if settings.is_neutral() else process_track(stem, settings, self.sample_rate)
                cached = (key, processed)
                self._cache[name] = cached
            out[name] = cached[1]
        return out
