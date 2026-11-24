"""Small audio helpers shared across Zosimix.

Convention: audio arrays are float64 numpy arrays shaped (frames, channels), even for
mono, so every function can treat stems the same way.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def read(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(str(path), dtype="float64", always_2d=True)
    return audio, sr


def write(path: Path, audio: np.ndarray, sr: int) -> None:
    """Write 32-bit float WAV so injected faults never get rounded or clipped on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sr, subtype="FLOAT")


def db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def gain_to_db(gain: float) -> float:
    return 20.0 * np.log10(max(gain, 1e-12))


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio))))


def peak(audio: np.ndarray) -> float:
    return float(np.max(np.abs(audio)))


def to_stereo(audio: np.ndarray) -> np.ndarray:
    """Mono stems are summed into a stereo mix as identical left/right channels."""
    return audio if audio.shape[1] == 2 else np.repeat(audio, 2, axis=1)


def mix(stems: dict[str, np.ndarray]) -> np.ndarray:
    """The clean reference mix is the plain sum of the stems (DESIGN.md §4.1)."""
    length = max(a.shape[0] for a in stems.values())
    out = np.zeros((length, 2))
    for audio in stems.values():
        out[: audio.shape[0]] += to_stereo(audio)
    return out


def long_term_spectrum(audio: np.ndarray, sr: int, n_fft: int = 8192) -> tuple[np.ndarray, np.ndarray]:
    """Average magnitude spectrum in dB (Welch-style, Hann window, 50% overlap).

    Returns (frequencies_hz, magnitude_db). Used to decide where a stem has energy,
    so faults are only injected where they can actually be heard.
    """
    mono = audio.mean(axis=1)
    if mono.shape[0] < n_fft:
        mono = np.pad(mono, (0, n_fft - mono.shape[0]))
    window = np.hanning(n_fft)
    hop = n_fft // 2
    frames = range(0, mono.shape[0] - n_fft + 1, hop)
    power = np.zeros(n_fft // 2 + 1)
    for start in frames:
        power += np.abs(np.fft.rfft(mono[start:start + n_fft] * window)) ** 2
    power /= max(len(frames), 1)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    return freqs, 10.0 * np.log10(power + 1e-20)
