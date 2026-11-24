"""Fault injection: bake one known problem into one stem's audio (DESIGN.md §4.2, D14, D17).

Faults live in the audio, never in mixer settings, so the agent has to find them by
measuring rather than by reading a bad knob position.

Each fault type has:
  - a rule for which stems it can be applied to (so the fault is actually audible), and
  - an `apply` function that turns clean stem audio into faulty stem audio.

Severity levels are indices 0 (subtle) .. 2 (severe) into each fault's SEVERITIES table.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

import numpy as np
from pedalboard import LowpassFilter, PeakFilter

from zosimix import audio
from zosimix.songs import family_of

FAULT_TYPES = ["gain", "polarity", "resonance", "mud", "pan", "clipping", "control"]
FIXABLE = {"gain", "polarity", "resonance", "mud", "pan"}

# Per-severity parameters. The comments say what the agent has to undo.
SEVERITIES = {
    "gain": [3.0, 6.0, 10.0],              # dB off from the intended level, sign chosen randomly
    "polarity": [1.0],                     # only one "size": the stem is inverted
    "resonance": [4.0, 8.0, 12.0],         # dB of a narrow peak (Q 8)
    "mud": [3.0, 6.0, 9.0],                # dB of a broad 200-400 Hz bump (Q 1)
    "pan": [0.3, 0.6, 0.9],                # pan position away from centre, side chosen randomly
    "clipping": [6.0, 12.0, 18.0],         # dB of the stem's peaks that get hard-clipped off
    "control": [0.0],                      # no fault
}
RESONANCE_Q = 8.0
MUD_Q = 1.0


@dataclass
class Fault:
    """Everything needed to reproduce the fault and to grade a repair. This is ground truth:
    it must never be visible to the agent under test (DESIGN.md §4.8)."""
    type: str
    stem: str | None                       # None for control tasks
    severity: int
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- stem eligibility

def _is_silent(a: np.ndarray) -> bool:
    return audio.rms(a) < audio.db_to_gain(-60)


def _energy_band(a: np.ndarray, sr: int, lo: float, hi: float, within_db: float = 30.0) -> np.ndarray:
    """Frequencies in [lo, hi] where the stem is within `within_db` of its loudest bin."""
    freqs, mag = audio.long_term_spectrum(a, sr)
    in_range = (freqs >= lo) & (freqs <= hi)
    loud = mag >= mag.max() - within_db
    return freqs[in_range & loud]


def _is_centred(a: np.ndarray) -> bool:
    """A stem that sits in the centre: mono, or stereo with near-identical channels."""
    if a.shape[1] == 1:
        return True
    left, right = a[:, 0], a[:, 1]
    corr = np.dot(left, right) / np.sqrt(max(np.dot(left, left) * np.dot(right, right), 1e-20))
    balance_db = abs(audio.gain_to_db(audio.rms(left[:, None]) / max(audio.rms(right[:, None]), 1e-20)))
    return corr > 0.95 and balance_db < 1.0


POLARITY_MIN_LOSS_DB = 1.0     # flipping the mic must cost the drum bus at least this much low end
POLARITY_LOWPASS_HZ = 500.0


def _polarity_candidates(stems: dict[str, np.ndarray], sr: int, audible: list[str]) -> list[str]:
    """Drum mics whose inversion audibly and unambiguously damages the kit sound.

    Inverting one mic only matters against the other mics that pick up the same drum.
    In processed or sample-replaced stems the mics may barely correlate (flipping changes
    nothing audible), or the clean mix may already be "out of phase" (then the correct
    answer is ambiguous). So a mic qualifies only if flipping it makes the summed drum bus
    lose at least POLARITY_MIN_LOSS_DB of low end, where polarity problems are heard (D41).
    Overheads are candidates too: a two-mic overhead pair is the classic real-world case
    (D42), and the loss test alone decides.
    """
    drums = [n for n in audible if family_of(n) == "drums"]
    if len(drums) < 2:
        return []
    lowpass = LowpassFilter(cutoff_frequency_hz=POLARITY_LOWPASS_HZ)
    low = {n: lowpass(stems[n].mean(axis=1).astype(np.float32)[None, :], sr)[0].astype(np.float64)
           for n in drums}
    length = min(len(x) for x in low.values())
    bus = sum(x[:length] for x in low.values())
    clean_rms = np.sqrt(np.mean(bus ** 2))
    out = []
    for n in drums:
        flipped_rms = np.sqrt(np.mean((bus - 2 * low[n][:length]) ** 2))
        if audio.gain_to_db(clean_rms / max(flipped_rms, 1e-20)) >= POLARITY_MIN_LOSS_DB:
            out.append(n)
    return out


def eligible_stems(fault_type: str, stems: dict[str, np.ndarray], sr: int) -> list[str]:
    audible = [n for n, a in stems.items() if not _is_silent(a)]
    if fault_type in ("gain", "clipping"):
        return audible
    if fault_type == "polarity":
        return _polarity_candidates(stems, sr, audible)
    if fault_type == "resonance":
        return [n for n in audible if len(_energy_band(stems[n], sr, 300, 8000)) > 0]
    if fault_type == "mud":
        return [n for n in audible if len(_energy_band(stems[n], sr, 200, 400, within_db=20)) > 0]
    if fault_type == "pan":
        return [n for n in audible if _is_centred(stems[n])]
    if fault_type == "control":
        return []
    raise ValueError(fault_type)


# ---------------------------------------------------------------- choosing a concrete fault

def choose(fault_type: str, severity: int, stems: dict[str, np.ndarray], sr: int, rng: random.Random) -> Fault:
    """Pick the stem and concrete parameters for one fault, reproducibly from `rng`."""
    if fault_type == "control":
        return Fault("control", None, 0)
    candidates = eligible_stems(fault_type, stems, sr)
    if not candidates:
        raise ValueError(f"no stem in this song is eligible for a {fault_type} fault")
    stem = rng.choice(candidates)
    size = SEVERITIES[fault_type][severity]
    params: dict = {}
    if fault_type == "gain":
        params = {"gain_db": size * rng.choice([-1, 1])}
    elif fault_type == "resonance":
        band = _energy_band(stems[stem], sr, 300, 8000)
        params = {"freq_hz": round(float(rng.choice(list(band))), 1), "gain_db": size, "q": RESONANCE_Q}
    elif fault_type == "mud":
        params = {"freq_hz": round(rng.uniform(200, 400), 1), "gain_db": size, "q": MUD_Q}
    elif fault_type == "pan":
        params = {"pan": size * rng.choice([-1, 1])}
    elif fault_type == "clipping":
        params = {"depth_db": size}
    return Fault(fault_type, stem, severity, params)


# ---------------------------------------------------------------- applying it

def _peak_filter(a: np.ndarray, sr: int, freq: float, gain_db: float, q: float) -> np.ndarray:
    board = PeakFilter(cutoff_frequency_hz=freq, gain_db=gain_db, q=q)
    out = board(a.T.astype(np.float32), sr)        # pedalboard wants (channels, frames)
    return out.T.astype(np.float64)


def apply(fault: Fault, a: np.ndarray, sr: int) -> np.ndarray:
    """Return the faulty version of stem audio `a`. The input is not modified."""
    p = fault.params
    if fault.type == "control":
        return a.copy()
    if fault.type == "gain":
        return a * audio.db_to_gain(p["gain_db"])
    if fault.type == "polarity":
        return -a
    if fault.type in ("resonance", "mud"):
        return _peak_filter(a, sr, p["freq_hz"], p["gain_db"], p["q"])
    if fault.type == "pan":
        left, right = audio.pan_gains(p["pan"])
        mono = a.mean(axis=1)
        return np.stack([mono * left, mono * right], axis=1)
    if fault.type == "clipping":
        threshold = audio.peak(a) * audio.db_to_gain(-p["depth_db"])
        return np.clip(a, -threshold, threshold)
    raise ValueError(fault.type)
