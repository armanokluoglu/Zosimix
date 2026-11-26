"""Tonal targets: "what normal looks like", learned from the other songs' clean mixes (D23).

For a task on song X, the target is computed from every song *except* X (leave-one-out),
so it never contains the task's own ground truth. It is safe to put in the workspace.

A target holds, per band (analysis.BANDS), the mean and spread of the band's share of
total energy:
  - for whole mixes, and
  - for each instrument family's stems (vocals, drums, bass, ...).

Profiles of each song are cached in data/targets/profiles.json because computing them
means analysing every stem of every song.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from zosimix import analysis, audio
from zosimix.songs import DATA_ROOT, family_of, list_songs

PROFILES_PATH = DATA_ROOT.parent / "targets" / "profiles.json"


def shape(x: np.ndarray, sr: int) -> dict[str, float]:
    """Band levels relative to the signal's total energy (dB). Level-independent."""
    freqs, power_db = analysis.spectrum(x, sr)
    bands = analysis.band_levels(freqs, power_db)
    total = 10.0 * np.log10(sum(10.0 ** (v / 10.0) for v in bands.values()) + 1e-20)
    return {name: round(v - total, 2) for name, v in bands.items()}


def song_profile(song) -> dict:
    stems, sr, _ = song.load_clean_stems()
    families: dict[str, list[dict]] = {}
    for name, a in stems.items():
        if audio.rms(a) > audio.db_to_gain(analysis.SILENCE_DB):
            families.setdefault(family_of(name), []).append(shape(audio.to_stereo(a), sr))
    return {"mix": shape(audio.mix(stems), sr), "families": families}


def load_profiles(rebuild: bool = False) -> dict[str, dict]:
    cached = json.loads(PROFILES_PATH.read_text(encoding="utf-8")) if PROFILES_PATH.exists() else {}
    songs = list_songs()
    missing = [s for s in songs if s.song_id not in cached]
    if rebuild or missing:
        for s in songs if rebuild else missing:
            print(f"profiling {s.song_id}")
            cached[s.song_id] = song_profile(s)
        PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILES_PATH.write_text(json.dumps(cached), encoding="utf-8")
    return cached


def _stats(shapes: list[dict[str, float]]) -> dict[str, list[float]]:
    """{band: [mean, spread]}; spread has a 1.5 dB floor so tiny samples aren't overconfident."""
    out = {}
    for name, _, _ in analysis.BANDS:
        values = np.array([s[name] for s in shapes])
        out[name] = [round(float(values.mean()), 1), round(max(float(values.std()), 1.5), 1)]
    return out


def target_for(song_id: str, profiles: dict[str, dict] | None = None) -> dict:
    """Leave-one-out target for a task on `song_id`."""
    profiles = profiles if profiles is not None else load_profiles()
    others = [p for sid, p in profiles.items() if sid != song_id]
    families: dict[str, list[dict]] = {}
    for p in others:
        for family, shapes in p["families"].items():
            families.setdefault(family, []).extend(shapes)
    return {
        "bands": [name for name, _, _ in analysis.BANDS],
        "songs_used": len(others),
        "mix": _stats([p["mix"] for p in others]),
        "families": {f: {"n": len(s), **_stats(s)} for f, s in families.items() if len(s) >= 3},
    }


LIVE_TARGET = Path(__file__).with_name("data") / "tonal_target.json"


def export_live_target(path: Path = LIVE_TARGET) -> Path:
    """The tonal target for live mode (D84): built from every benchmark song, since a user's own
    song is never one of them. Only per-band averages and spreads are stored, no audio."""
    target = target_for("__live__")
    target["about"] = ("Typical band shapes of professionally mixed songs and their instrument families, from the "
                       "Zosimix benchmark songs (MoisesDB, AlbumDB; see CITATIONS.md). Averages only, no audio.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(target, indent=1), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(f"wrote {export_live_target()}")
