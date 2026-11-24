"""Measurements: how the agent "hears" (DESIGN.md §3.2, D23).

Everything here turns audio into a few numbers. The tool layer (zosimix.tools) decides
which numbers to show the agent and keeps every answer short.

All functions take (frames, 2) float arrays at sample rate `sr`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyloudnorm

from zosimix import audio

# Eight broad bands used in overviews and tonal targets (Hz, lower edge inclusive).
BANDS = [
    ("sub", 20, 60), ("low", 60, 150), ("lowmid", 150, 400), ("mid", 400, 1000),
    ("highmid", 1000, 2500), ("presence", 2500, 5000), ("brilliance", 5000, 10000), ("air", 10000, 20000),
]
SILENCE_DB = -70.0


# ---------------------------------------------------------------- spectra

def spectrum(x: np.ndarray, sr: int, n_fft: int = 8192, max_frames: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Long-term average power spectrum in dB, vectorized.

    To keep long songs fast, at most `max_frames` evenly spaced frames are averaged;
    for a 4-minute song that is still every other hop. Returns (freqs_hz, power_db).
    """
    mono = x.mean(axis=1)
    if len(mono) < n_fft:
        mono = np.pad(mono, (0, n_fft - len(mono)))
    hop = n_fft // 2
    starts = np.arange(0, len(mono) - n_fft + 1, hop)
    if len(starts) > max_frames:
        starts = starts[np.linspace(0, len(starts) - 1, max_frames).astype(int)]
    window = np.hanning(n_fft)
    power = np.zeros(n_fft // 2 + 1)
    for chunk in np.array_split(starts, max(1, len(starts) // 128)):
        frames = np.stack([mono[s:s + n_fft] for s in chunk]) * window
        power += (np.abs(np.fft.rfft(frames, axis=1)) ** 2).sum(axis=0)
    power /= len(starts)
    return np.fft.rfftfreq(n_fft, 1.0 / sr), 10.0 * np.log10(power + 1e-20)


def band_levels(freqs: np.ndarray, power_db: np.ndarray) -> dict[str, float]:
    """Energy per BANDS entry in dB (absolute, from a `spectrum` result)."""
    power = 10.0 ** (power_db / 10.0)
    out = {}
    for name, lo, hi in BANDS:
        sel = (freqs >= lo) & (freqs < hi)
        out[name] = float(10.0 * np.log10(power[sel].sum() + 1e-20))
    return out


def smooth_db(freqs: np.ndarray, power_db: np.ndarray, octave_fraction: float = 3.0) -> np.ndarray:
    """Smooth a spectrum over a moving 1/N-octave window (in the power domain)."""
    power = 10.0 ** (power_db / 10.0)
    out = np.empty_like(power)
    half = 2.0 ** (1.0 / (2.0 * octave_fraction))
    cumsum = np.concatenate([[0.0], np.cumsum(power)])
    lo_idx = np.searchsorted(freqs, freqs / half)
    hi_idx = np.searchsorted(freqs, freqs * half, side="right")
    counts = np.maximum(hi_idx - lo_idx, 1)
    out = (cumsum[hi_idx] - cumsum[lo_idx]) / counts
    return 10.0 * np.log10(out + 1e-20)


@dataclass
class Peak:
    freq_hz: float
    excess_db: float          # typical height above the 1-octave neighbourhood, across the song
    q: float                  # rough width: centre / (-3 dB bandwidth of the excess)


def persistent_peaks(x: np.ndarray, sr: int, lo: float, hi: float, limit: int = 5,
                     n_fft: int = 4096, max_frames: int = 300) -> list[Peak]:
    """Resonance candidates: bumps that stay at the same frequency all song long.

    For each loud frame, take the 1/12-octave-smoothed spectrum minus the 1-octave-smoothed
    one (a bump's height above its neighbourhood), then take the median over frames.
    Notes move with the music and mostly cancel out in the median; a fixed EQ boost does not.
    Natural fixed resonances (a guitar body, a vocal formant) survive too, so a peak is
    evidence, not proof (D44).
    """
    mono = x.mean(axis=1)
    hop = n_fft // 2
    starts = np.arange(0, max(len(mono) - n_fft, 1), hop)
    starts = starts[np.linspace(0, len(starts) - 1, min(max_frames, len(starts))).astype(int)]
    frames = np.stack([np.pad(mono[s:s + n_fft], (0, max(0, n_fft - len(mono[s:s + n_fft])))) for s in starts])
    power_db = 10.0 * np.log10(np.abs(np.fft.rfft(frames * np.hanning(n_fft), axis=1)) ** 2 + 1e-20)
    power_db = power_db[power_db.max(axis=1) > power_db.max() - 40.0]          # skip near-silent frames
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    excess = np.median([smooth_db(freqs, p, 12.0) - smooth_db(freqs, p, 1.0) for p in power_db], axis=0)
    sel = np.where((freqs >= lo) & (freqs <= hi))[0]
    candidates = sorted(((excess[i], i) for i in sel[1:-1]
                         if excess[i] > 0.5 and excess[i] >= excess[i - 1] and excess[i] >= excess[i + 1]),
                        reverse=True)
    peaks: list[Peak] = []
    for height, i in candidates:
        if any(abs(np.log2(freqs[i] / p.freq_hz)) <= 0.25 for p in peaks):
            continue                                             # near-duplicate of a stronger peak
        left, right = i, i
        while left > 0 and excess[left] > height - 3.0:
            left -= 1
        while right < len(excess) - 1 and excess[right] > height - 3.0:
            right += 1
        peaks.append(Peak(float(freqs[i]), float(height), float(freqs[i] / max(freqs[right] - freqs[left], 1.0))))
        if len(peaks) == limit:
            break
    return peaks


# ---------------------------------------------------------------- level, stereo, clipping

def loudness_lufs(x: np.ndarray, sr: int) -> float:
    if audio.rms(x) < audio.db_to_gain(SILENCE_DB):
        return float("-inf")
    value = pyloudnorm.Meter(sr).integrated_loudness(x)
    return float(value) if np.isfinite(value) else float("-inf")


def balance_db(x: np.ndarray) -> float:
    """Right minus left level in dB: positive = leans right. 0 for a centred stem."""
    left, right = audio.rms(x[:, :1]), audio.rms(x[:, 1:])
    return audio.gain_to_db(right / max(left, 1e-20)) if left > 0 or right > 0 else 0.0


def lr_correlation(x: np.ndarray) -> float:
    """+1 = mono, 0 = unrelated channels (very wide), negative = out-of-phase channels."""
    left, right = x[:, 0], x[:, 1]
    denom = np.sqrt(np.dot(left, left) * np.dot(right, right))
    return float(np.dot(left, right) / denom) if denom > 0 else 1.0


def crest_db(x: np.ndarray) -> float:
    r = audio.rms(x)
    return audio.gain_to_db(audio.peak(x) / r) if r > 0 else 0.0


def flat_top_runs_per_min(x: np.ndarray, sr: int, min_run: int = 4) -> float:
    """Runs of >= min_run consecutive samples sitting at the stem's own peak level.

    Natural audio almost never repeats its maximum value; hard clipping does so constantly.
    """
    p = audio.peak(x)
    if p == 0:
        return 0.0
    at_peak = np.abs(x).max(axis=1) >= p * 0.9999
    edges = np.diff(np.concatenate([[0], at_peak.astype(np.int8), [0]]))
    run_lengths = np.where(edges == -1)[0] - np.where(edges == 1)[0]
    runs = int((run_lengths >= min_run).sum())
    return runs / (len(x) / sr / 60.0)


# ---------------------------------------------------------------- relationships between stems

def lowpass_mono(x: np.ndarray, sr: int, cutoff_hz: float = 500.0) -> np.ndarray:
    spec = np.fft.rfft(x.mean(axis=1))
    spec[np.fft.rfftfreq(len(x), 1.0 / sr) > cutoff_hz] = 0
    return np.fft.irfft(spec, len(x))


def phase_report(stems: dict[str, np.ndarray], sr: int, max_lag_ms: float = 10.0) -> dict[str, dict]:
    """For each stem in a group (e.g. the drum mics), against the sum of the others:
      corr      best low-end correlation within +-max_lag_ms (sign matters: negative = opposed)
      lag_ms    the lag where that happens (mic distance)
      flip_db   how the group's low end (< 500 Hz) would change if this stem were inverted.
                Clearly positive = flipping it would *restore* low end = likely polarity problem.
    """
    names = list(stems)
    length = min(len(a) for a in stems.values())
    low = {n: lowpass_mono(stems[n][:length], sr) for n in names}
    bus = sum(low.values())
    bus_rms = np.sqrt(np.mean(bus ** 2))
    max_lag = int(sr * max_lag_ms / 1000)
    out = {}
    for n in names:
        rest = bus - low[n]
        a, b = low[n][max_lag:-max_lag], rest
        best_corr, best_lag = 0.0, 0
        for lag in range(-max_lag, max_lag + 1, max(1, max_lag // 100)):
            seg = b[max_lag + lag: len(b) - max_lag + lag]
            denom = np.sqrt(np.dot(a, a) * np.dot(seg, seg))
            c = float(np.dot(a, seg) / denom) if denom > 0 else 0.0
            if abs(c) > abs(best_corr):
                best_corr, best_lag = c, lag
        flipped_rms = np.sqrt(np.mean((bus - 2 * low[n]) ** 2))
        out[n] = {
            "corr": round(best_corr, 3),
            "lag_ms": round(1000 * best_lag / sr, 2),
            "flip_db": round(audio.gain_to_db(flipped_rms / max(bus_rms, 1e-20)), 2),
        }
    return out
