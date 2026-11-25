"""Fault injection: bake one known problem into one stem's audio (DESIGN.md §4.2, D14, D17).

Faults live in the audio, never in mixer settings, so the agent has to find them by
measuring rather than by reading a bad knob position.

Each fault type has:
  - a rule for which stems it can be applied to (so the fault is actually audible), and
  - an `apply` function that turns clean stem audio into faulty stem audio.

Severity levels are indices 0 (subtle) .. 2 (severe) into each fault's SEVERITIES table.
Mud and resonance are sized by what they do to the *mix*, not by their filter gain (D69):
the same 9 dB boost is obvious on a lead vocal and inaudible on an outro guitar.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

import numpy as np

from zosimix import analysis, audio, eq
from zosimix.songs import family_of

FAULT_TYPES = ["gain", "polarity", "resonance", "mud", "pan", "clipping", "control"]
FIXABLE = {"gain", "polarity", "resonance", "mud", "pan"}

# Per-severity parameters. The comments say what the agent has to undo.
SEVERITIES = {
    "gain": [3.0, 6.0, 10.0],              # dB off from the intended level, sign chosen randomly
    "polarity": [1.0],                     # only one "size": the stem is inverted
    "resonance": [2.0, 4.0, 6.0],          # dB the mix's 1/3 octave at the peak rises against the rest of the mix (Q 8)
    "mud": [1.0, 2.0, 3.0],                # dB the mix's low-mids rise against the rest of the mix (Q 1 at 200-400 Hz)
    "pan": [0.3, 0.6, 0.9],                # pan position away from centre, side chosen randomly
    "clipping": [6.0, 12.0, 18.0],         # dB of the stem's peaks that get hard-clipped off
    "control": [0.0],                      # no fault
}
RESONANCE_Q = 8.0
MUD_Q = 1.0
# The most filter gain a mix-sized fault may use. A stem that needs more to reach the
# severity's mix change plays too small a part in the mix to carry that fault (D69).
MAX_FILTER_GAIN_DB = {"resonance": 18.0, "mud": 12.0}
MUD_BAND = next((lo, hi) for name, lo, hi in analysis.BANDS if name == "lowmid")
FREQ_DRAWS_PER_STEM = 3        # frequencies tried on one stem before moving to the next


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
    # The same low-pass as the grader and the phase tool (analysis.phase_report), so a mic
    # that qualifies here is measured the same way when an answer is graded (D62).
    length = min(len(stems[n]) for n in drums)
    low = {n: analysis.lowpass_mono(stems[n][:length], sr, POLARITY_LOWPASS_HZ) for n in drums}
    bus = sum(low.values())
    clean_rms = np.sqrt(np.mean(bus ** 2))
    out = []
    for n in drums:
        flipped_rms = np.sqrt(np.mean((bus - 2 * low[n]) ** 2))
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
    size = SEVERITIES[fault_type][severity]
    if fault_type in MAX_FILTER_GAIN_DB:
        return _choose_eq_fault(fault_type, severity, size, candidates, stems, sr, rng)
    stem = rng.choice(candidates)
    params: dict = {}
    if fault_type == "gain":
        params = {"gain_db": size * rng.choice([-1, 1])}
    elif fault_type == "pan":
        params = {"pan": size * rng.choice([-1, 1])}
    elif fault_type == "clipping":
        params = {"depth_db": size}
    return Fault(fault_type, stem, severity, params)


# ---------------------------------------------------------------- mix-sized EQ faults (D69)

def fault_band(fault_type: str, freq_hz: float) -> tuple[float, float]:
    """Where a mix-sized fault is measured: the whole low-mid band for mud, the 1/3 octave
    around the peak for resonance."""
    return MUD_BAND if fault_type == "mud" else (freq_hz * 2 ** (-1 / 6), freq_hz * 2 ** (1 / 6))


def band_vs_rest_db(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    """Energy in [lo, hi) against the energy outside it, in dB. Level-independent, and unlike a
    band's share of the total it has no ceiling: a mix whose low-mids already hold half its
    energy can still get 3 dB muddier (D69)."""
    freqs, power_db = analysis.spectrum(audio.to_stereo(x), sr)
    power = 10.0 ** (power_db / 10.0)
    inside = (freqs >= lo) & (freqs < hi)
    return float(10.0 * np.log10(power[inside].sum() / power[~inside].sum()))


def mix_rise_db(fault_type: str, stem: np.ndarray, others: np.ndarray, sr: int, freq_hz: float,
                gain_db: float) -> float:
    """How much a boost on `stem` raises the fault's band against the rest of the mix.
    `others` is the sum of every other stem (stereo, at least as long as the stem)."""
    q = RESONANCE_Q if fault_type == "resonance" else MUD_Q
    lo, hi = fault_band(fault_type, freq_hz)
    clean = audio.to_stereo(stem)
    boosted = eq.apply(clean, [("peaking", freq_hz, gain_db, q)], sr)

    def with_stem(x: np.ndarray) -> np.ndarray:
        out = others.copy()
        out[: len(x)] += x
        return out

    return band_vs_rest_db(with_stem(boosted), sr, lo, hi) - band_vs_rest_db(with_stem(clean), sr, lo, hi)


def _gain_for_rise(fault_type: str, stem: np.ndarray, others: np.ndarray, sr: int, freq_hz: float,
                   target_db: float) -> float | None:
    """The smallest filter gain (to 0.1 dB, rounded up) whose mix rise reaches `target_db`,
    or None if even MAX_FILTER_GAIN_DB falls short. Bisection: more boost, more rise."""
    cap = MAX_FILTER_GAIN_DB[fault_type]
    if mix_rise_db(fault_type, stem, others, sr, freq_hz, cap) < target_db:
        return None
    lo, hi = 0.0, cap
    while hi - lo > 0.05:
        mid = (lo + hi) / 2
        if mix_rise_db(fault_type, stem, others, sr, freq_hz, mid) >= target_db:
            hi = mid
        else:
            lo = mid
    return float(np.ceil(hi * 10) / 10)


def own_peaks(a: np.ndarray, sr: int) -> np.ndarray:
    """Frequencies (300-8000 Hz) where the stem's 1/6-octave-smoothed long-term spectrum has a
    local maximum within 30 dB of its loudest point. A resonance boost placed in a dip of the
    spectrum has little there to ring with, so it would barely be heard (D69)."""
    freqs, power_db = analysis.spectrum(audio.to_stereo(a), sr)
    smooth = analysis.smooth_db(freqs, power_db, 6.0)
    i = np.arange(1, len(freqs) - 1)
    is_peak = (smooth[i] >= smooth[i - 1]) & (smooth[i] > smooth[i + 1])
    loud = smooth[i] >= smooth.max() - 30.0
    in_range = (freqs[i] >= 300) & (freqs[i] <= 8000)
    return freqs[i][is_peak & loud & in_range]


def _choose_eq_fault(fault_type: str, severity: int, target_db: float, candidates: list[str],
                     stems: dict[str, np.ndarray], sr: int, rng: random.Random) -> Fault:
    """Try stems in random order. On each, draw a few frequencies and solve for the filter gain
    that changes the mix by `target_db`; the first stem that can do it carries the fault."""
    order = candidates[:]
    rng.shuffle(order)
    full_mix = audio.mix(stems)
    q = RESONANCE_Q if fault_type == "resonance" else MUD_Q
    for stem in order:
        clean = audio.to_stereo(stems[stem])
        others = full_mix.copy()
        others[: len(clean)] -= clean
        peaks = list(own_peaks(stems[stem], sr)) if fault_type == "resonance" else None
        if peaks == []:
            continue
        for _ in range(FREQ_DRAWS_PER_STEM):
            freq = round(float(rng.choice(peaks)) if peaks else rng.uniform(200, 400), 1)
            gain = _gain_for_rise(fault_type, stems[stem], others, sr, freq, target_db)
            if gain is not None:
                rise = mix_rise_db(fault_type, stems[stem], others, sr, freq, gain)
                return Fault(fault_type, stem, severity,
                             {"freq_hz": freq, "gain_db": gain, "q": q, "mix_rise_db": round(rise, 2)})
    raise ValueError(f"no stem in this song can carry a {fault_type} fault that changes the mix by {target_db} dB")


# ---------------------------------------------------------------- applying it

def _peak_filter(a: np.ndarray, sr: int, freq: float, gain_db: float, q: float) -> np.ndarray:
    """The same peaking filter the engines use (D61), so an exact counter-cut can undo it."""
    return eq.apply(a, [("peaking", freq, gain_db, q)], sr)


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
