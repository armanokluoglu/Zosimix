"""Deterministic graders: no LLM judge (DESIGN.md §4.5, D19, D46).

Every run is graded on four things:
  detection   did the answer name the right fault type on an acceptable stem, with the
              right verdict ("fixed" for fixable faults, "unfixable" for clipping,
              "no_fault" for controls)?
  repair      for fixable faults: how much of the fault-specific error was removed,
              from 1.0 (fully undone) through 0 (no better) to negative (made worse).
  collateral  did anything else change? Measured on the sum of all *other* stems,
              which were clean to begin with, so any change there is damage.
  pass        all of the above together (thresholds below).

Graders always use Song.load_clean_stems() (D40) and render the agent's final mix state
with the offline engine, so grading is identical whatever engine the run used.
"""

from __future__ import annotations

import math

import numpy as np

from zosimix import analysis, audio, faults
from zosimix.engines.offline import OfflineEngine
from zosimix.mixstate import MixState
from zosimix.songs import DATA_ROOT, family_of, list_songs
from zosimix.tasks import TaskSpec

REPAIR_PASS = 0.7           # at least 70% of the fault-specific error removed
UNTOUCHED_DB = -30.0        # "unchanged" = residual at least 30 dB below the signal (~3%)
POLARITY_ACCEPT_DB = 1.0    # any drum stem whose flip would restore >= 1 dB of low end
EXPECTED_VERDICT = {"clipping": "unfixable", "control": "no_fault"}


def _residual_db(a: np.ndarray, reference: np.ndarray) -> float:
    ref = audio.rms(reference)
    if ref == 0:
        return -math.inf if audio.rms(a) == 0 else math.inf
    return audio.gain_to_db(audio.rms(a - reference) / ref) if audio.rms(a - reference) > 0 else -math.inf


def _sum(stems: dict[str, np.ndarray], names) -> np.ndarray:
    names = list(names)
    length = max(stems[n].shape[0] for n in names)
    out = np.zeros((length, 2))
    for n in names:
        out[: stems[n].shape[0]] += audio.to_stereo(stems[n])
    return out


def _ratio(after: float, before: float) -> float:
    """1 - after/before, clamped to [-1, 1]: the fraction of the error removed."""
    if before <= 1e-9:
        return 1.0 if after <= 1e-9 else -1.0
    return max(-1.0, min(1.0, 1.0 - after / before))


def acceptable_stems(fault: faults.Fault, broken: dict[str, np.ndarray], sr: int) -> set[str]:
    """Stems a correct answer may name. Normally just the faulty one; for polarity, any drum
    stem whose inversion would restore the low end (with a two-mic pair, either mic) (D45)."""
    if fault.type != "polarity":
        return {fault.stem} if fault.stem else set()
    group = {n: audio.to_stereo(a) for n, a in broken.items() if family_of(n) == "drums"}
    report = analysis.phase_report(group, sr)
    return {fault.stem} | {n for n, r in report.items() if r["flip_db"] >= POLARITY_ACCEPT_DB}


def repair_score(fault: faults.Fault, clean: dict, broken: dict, processed: dict, sr: int) -> dict:
    """Fault-specific error before (broken) and after (agent's mix), and the fraction removed."""
    s = fault.stem
    if fault.type == "gain":
        before = abs(fault.params["gain_db"])
        after = abs(audio.gain_to_db(audio.rms(processed[s]) / audio.rms(audio.to_stereo(clean[s]))))
        unit = "dB level error"
    elif fault.type == "pan":
        target = analysis.balance_db(audio.to_stereo(clean[s]))
        before = abs(analysis.balance_db(audio.to_stereo(broken[s])) - target)
        after = abs(analysis.balance_db(processed[s]) - target)
        unit = "dB balance error"
    elif fault.type in ("resonance", "mud"):
        half_octave = 1 / 3 if fault.type == "resonance" else 1.0
        lo, hi = fault.params["freq_hz"] * 2 ** -half_octave, fault.params["freq_hz"] * 2 ** half_octave

        def band_share(x):                 # band energy relative to the whole stem: level-independent
            freqs, power_db = analysis.spectrum(audio.to_stereo(x), sr)
            power = 10 ** (power_db / 10)
            return 10 * np.log10(power[(freqs >= lo) & (freqs < hi)].sum() / power.sum())

        target = band_share(clean[s])
        before, after = abs(band_share(broken[s]) - target), abs(band_share(processed[s]) - target)
        unit = "dB band-shape error"
    elif fault.type == "polarity":
        drums = [n for n in clean if family_of(n) == "drums"]

        def low_db(stems):
            return audio.gain_to_db(audio.rms(analysis.lowpass_mono(_sum(stems, drums), sr)[:, None]))

        target = low_db(clean)
        before, after = abs(low_db(broken) - target), abs(low_db(processed) - target)
        unit = "dB drum-bus low-end error"
    else:
        return {}
    return {"before": round(before, 2), "after": round(after, 2), "unit": unit,
            "score": round(_ratio(after, before), 3)}


def grade(spec: TaskSpec, diagnosis: dict | None, mix_state: dict | None, songs_root=DATA_ROOT) -> dict:
    song = next(s for s in list_songs(songs_root) if s.song_id == spec.song_id)
    clean, sr, _ = song.load_clean_stems()
    fault = faults.Fault(**spec.fault)
    broken = dict(clean)
    if fault.stem:
        broken[fault.stem] = faults.apply(fault, clean[fault.stem], sr)

    result: dict = {"task_id": spec.task_id, "fault_type": fault.type, "stem": fault.stem,
                    "severity": fault.severity, "hint_level": spec.hint_level}
    if diagnosis is None:
        return {**result, "submitted": False, "pass": False}

    engine = OfflineEngine(broken, sr)
    try:
        engine.set_state(MixState.from_dict(mix_state or {}))
        result["invalid_mix_state"] = None
    except (ValueError, TypeError) as exc:            # an unusable answer counts as "no changes"
        result["invalid_mix_state"] = str(exc)
    state = engine.get_state()                        # full state: unmentioned tracks are neutral
    processed = engine.render_stems()

    # ---- detection
    expected = EXPECTED_VERDICT.get(fault.type, "fixed")
    accept = acceptable_stems(fault, broken, sr)
    findings = diagnosis.get("findings", []) or []
    hit = any(f.get("fault_type") == fault.type and f.get("stem") in accept for f in findings)
    false_findings = [f for f in findings if not (f.get("fault_type") == fault.type and f.get("stem") in accept)]
    detected = diagnosis.get("verdict") == expected and (hit if fault.type != "control" else not findings)

    # ---- collateral: every stem that was clean must still be (nearly) the same
    others = [n for n in clean if n not in accept]
    others_db = _residual_db(_sum(processed, others), _sum(clean, others)) if others else -math.inf
    touched = sorted(n for n in others if not state.tracks[n].is_neutral())
    mix_after = engine.render()
    result.update({
        "submitted": True,
        "verdict": diagnosis.get("verdict"),
        "expected_verdict": expected,
        "detected": detected,
        "false_findings": len(false_findings),
        "touched_other_stems": touched,
        "others_residual_db": round(others_db, 1),
        "mix_residual_db": round(_residual_db(mix_after, audio.mix(clean)), 1),
        "mix_level_change_db": round(audio.gain_to_db(audio.rms(mix_after) / audio.rms(audio.mix(clean))), 2),
    })

    # ---- repair and pass
    others_ok = others_db <= UNTOUCHED_DB
    if fault.type in faults.FIXABLE:
        result["repair"] = repair_score(fault, clean, broken, processed, sr)
        result["pass"] = bool(detected and result["repair"]["score"] >= REPAIR_PASS and others_ok)
    else:
        # clipping and control: the right move is to leave the mix as it was handed over
        unchanged_db = _residual_db(mix_after, audio.mix(broken))
        result["unchanged_residual_db"] = round(unchanged_db, 1)
        result["pass"] = bool(detected and unchanged_db <= UNTOUCHED_DB)
    return result
