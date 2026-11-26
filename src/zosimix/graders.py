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

The one exception is the flstudio-mcp baseline (D70). Its agent changes the mix inside FL
with controls that have no mix-state equivalent, so its mix is read back as FL renders of
a few groups of tracks (`render_groups`) and graded by `grade_renders`. Both paths score
the same `Rendered` pieces with the same code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from zosimix import analysis, audio, faults
from zosimix.engines.offline import OfflineEngine
from zosimix.mixstate import MixState
from zosimix.songs import DATA_ROOT, family_of, find_song
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


@dataclass
class Rendered:
    """The agent's mix, in the pieces grading needs. All stereo, processed by the agent."""
    mix: np.ndarray                     # the whole mix
    others: np.ndarray | None           # every stem a correct answer may not name, summed (None: none)
    fault_stem: np.ndarray | None       # the faulty stem alone (gain, pan, mud, resonance)
    drum_bus: np.ndarray | None         # every drum stem summed (polarity)
    touched: list[str] | None           # healthy stems whose settings changed; None = not known (FL)
    invalid_mix_state: str | None = None


def repair_score(fault: faults.Fault, clean: dict, broken: dict, rendered: Rendered, sr: int) -> dict:
    """Fault-specific error before (broken) and after (agent's mix), and the fraction removed."""
    s = fault.stem
    if fault.type == "gain":
        before = abs(fault.params["gain_db"])
        after = abs(audio.gain_to_db(audio.rms(rendered.fault_stem) / audio.rms(audio.to_stereo(clean[s]))))
        unit = "dB level error"
    elif fault.type == "pan":
        target = analysis.balance_db(audio.to_stereo(clean[s]))
        before = abs(analysis.balance_db(audio.to_stereo(broken[s])) - target)
        after = abs(analysis.balance_db(rendered.fault_stem) - target)
        unit = "dB balance error"
    elif fault.type in ("resonance", "mud"):
        half_width_octaves = 1 / 3 if fault.type == "resonance" else 1.0
        f0 = fault.params["freq_hz"]
        lo, hi = f0 * 2 ** -half_width_octaves, f0 * 2 ** half_width_octaves

        def band_vs_rest(x):
            """Band energy against the rest of the stem: level-independent, and unlike a share of
            the total it doesn't flatten out when the band already holds most of the stem's energy.
            On a snare, a 10 dB mud boost moved the band's share by only 0.1 dB, so any slightly
            imperfect cut scored as damage (D73)."""
            freqs, power_db = analysis.spectrum(audio.to_stereo(x), sr)
            power = 10 ** (power_db / 10)
            inside = (freqs >= lo) & (freqs < hi)
            return 10 * np.log10(power[inside].sum() / power[~inside].sum())

        target = band_vs_rest(clean[s])
        before, after = abs(band_vs_rest(broken[s]) - target), abs(band_vs_rest(rendered.fault_stem) - target)
        unit = "dB band-vs-rest error"
    elif fault.type == "polarity":
        drums = [n for n in clean if family_of(n) == "drums"]

        def low_db(bus):
            return audio.gain_to_db(audio.rms(analysis.lowpass_mono(bus, sr)[:, None]))

        target = low_db(_sum(clean, drums))
        before, after = abs(low_db(_sum(broken, drums)) - target), abs(low_db(rendered.drum_bus) - target)
        unit = "dB drum-bus low-end error"
    else:
        return {}
    return {"before": round(before, 2), "after": round(after, 2), "unit": unit,
            "score": round(_ratio(after, before), 3)}


def read_diagnosis(diagnosis: object) -> tuple[str | None, list[dict], str | None]:
    """Turn whatever the agent wrote into (verdict, findings, problem), never raising.

    The plain baseline writes diagnosis.json by hand, so it can have any shape (D50).
    Values that aren't strings become None. A malformed finding is kept as an empty
    finding rather than dropped, so it still counts as a (false) finding: an agent
    shouldn't pass a control task just because its false alarm was badly formatted."""
    if not isinstance(diagnosis, dict):
        return None, [], f"diagnosis must be an object, got {type(diagnosis).__name__}"

    def text(value):
        return value if isinstance(value, str) else None

    problem = None
    raw = diagnosis.get("findings") or []
    if not isinstance(raw, list):                       # counted as one malformed finding
        raw, problem = [None], "findings must be a list"
    findings = []
    for f in raw:
        if isinstance(f, dict):
            findings.append({"stem": text(f.get("stem")), "fault_type": text(f.get("fault_type"))})
        else:
            findings.append({"stem": None, "fault_type": None})
            problem = problem or "every finding must be an object"
    return text(diagnosis.get("verdict")), findings, problem


@dataclass
class _Task:
    """One task's audio and answer key, as grading sees it."""
    fault: faults.Fault
    clean: dict[str, np.ndarray]
    broken: dict[str, np.ndarray]
    sr: int
    accept: set[str]                    # stems a correct answer may name

    @property
    def others(self) -> list[str]:
        return [n for n in self.clean if n not in self.accept]

    @property
    def drums(self) -> list[str]:
        return [n for n in self.clean if family_of(n) == "drums"]


def _load_task(spec: TaskSpec, songs_root) -> _Task:
    song = find_song(spec.song_id, songs_root)
    clean, sr, _ = song.load_clean_stems()
    fault = faults.Fault(**spec.fault)
    broken = dict(clean)
    if fault.stem:
        broken[fault.stem] = faults.apply(fault, clean[fault.stem], sr)
    return _Task(fault, clean, broken, sr, acceptable_stems(fault, broken, sr))


def _header(spec: TaskSpec) -> dict:
    return {"task_id": spec.task_id, "fault_type": spec.fault["type"], "stem": spec.fault["stem"],
            "severity": spec.fault["severity"], "hint_level": spec.hint_level}


def grade(spec: TaskSpec, diagnosis: dict | None, mix_state: dict | None, songs_root=DATA_ROOT) -> dict:
    """Grade an answer given as a mix state, rendered with the offline engine."""
    if diagnosis is None:
        return {**_header(spec), "submitted": False, "pass": False}
    task = _load_task(spec, songs_root)
    engine = OfflineEngine(task.broken, task.sr)
    invalid = None
    try:
        engine.set_state(MixState.from_dict(mix_state or {}))
    except (ValueError, TypeError) as exc:            # an unusable answer counts as "no changes"
        invalid = str(exc)
    state = engine.get_state()                        # full state: unmentioned tracks are neutral
    processed = engine.render_stems()
    s = task.fault.stem
    rendered = Rendered(
        mix=engine.render(),
        others=_sum(processed, task.others) if task.others else None,
        fault_stem=processed[s] if s else None,
        drum_bus=_sum(processed, task.drums) if task.drums else None,
        touched=sorted(n for n in task.others if not state.tracks[n].is_neutral()),
        invalid_mix_state=invalid,
    )
    return _score(spec, task, diagnosis, rendered)


def render_groups(spec: TaskSpec, songs_root=DATA_ROOT) -> list[frozenset[str]]:
    """The groups of tracks FL must render on their own to grade this task (D70).

    FL renders only whole mixes, so each piece in `Rendered` is a render with every track
    outside one group muted. The pieces add up because the mix is linear (faders, pans and
    Parametric EQ 2 only), so the whole mix is the sum of the first two groups.
      control:  every stem (one render: the mix is also "the others")
      polarity: the acceptable drum mics, everything else, the remaining drum mics
      others:   the faulty stem, everything else
    """
    task = _load_task(spec, songs_root)
    if not task.accept:
        return [frozenset(task.clean)]
    groups = [frozenset(task.accept), frozenset(task.others)]
    if task.fault.type == "polarity" and set(task.drums) - task.accept:
        groups.append(frozenset(set(task.drums) - task.accept))
    return [g for g in groups if g]


def grade_renders(spec: TaskSpec, diagnosis: dict | None, renders: dict[frozenset[str], np.ndarray],
                  songs_root=DATA_ROOT) -> dict:
    """Grade an agent whose mix was read back as FL renders of `render_groups` (D70)."""
    if diagnosis is None:
        return {**_header(spec), "submitted": False, "pass": False}
    task = _load_task(spec, songs_root)
    if not task.accept:
        mix = renders[frozenset(task.clean)]
        rendered = Rendered(mix=mix, others=mix, fault_stem=None, drum_bus=None, touched=None)
    else:
        picked = renders[frozenset(task.accept)]
        others = renders.get(frozenset(task.others))
        mix = picked + others if others is not None else picked
        drum_bus = None
        if task.fault.type == "polarity":
            rest = renders.get(frozenset(set(task.drums) - task.accept))
            drum_bus = picked + rest if rest is not None else picked
        rendered = Rendered(mix=mix, others=others, fault_stem=picked, drum_bus=drum_bus, touched=None)
    return _score(spec, task, diagnosis, rendered)


def _score(spec: TaskSpec, task: _Task, diagnosis: object, rendered: Rendered) -> dict:
    fault, clean, broken, sr, accept = task.fault, task.clean, task.broken, task.sr, task.accept
    result = {**_header(spec), "invalid_mix_state": rendered.invalid_mix_state}

    # ---- detection
    expected = EXPECTED_VERDICT.get(fault.type, "fixed")
    verdict, findings, result["invalid_diagnosis"] = read_diagnosis(diagnosis)
    hit = any(f["fault_type"] == fault.type and f["stem"] in accept for f in findings)
    false_findings = [f for f in findings if not (f["fault_type"] == fault.type and f["stem"] in accept)]
    detected = verdict == expected and (hit if fault.type != "control" else not findings)

    # ---- collateral: every stem that was clean must still be (nearly) the same
    others = task.others
    others_db = _residual_db(rendered.others, _sum(clean, others)) if others else -math.inf
    mix_after = rendered.mix
    result.update({
        "submitted": True,
        "verdict": verdict,
        "expected_verdict": expected,
        "detected": detected,
        "false_findings": len(false_findings),
        "touched_other_stems": rendered.touched,
        "others_residual_db": round(others_db, 1),
        "mix_residual_db": round(_residual_db(mix_after, audio.mix(clean)), 1),
        "mix_level_change_db": round(audio.gain_to_db(audio.rms(mix_after) / audio.rms(audio.mix(clean))), 2),
    })

    # ---- repair and pass
    others_ok = others_db <= UNTOUCHED_DB
    if fault.type in faults.FIXABLE:
        result["repair"] = repair_score(fault, clean, broken, rendered, sr)
        result["pass"] = bool(detected and result["repair"]["score"] >= REPAIR_PASS and others_ok)
    else:
        # clipping and control: the right move is to leave the mix as it was handed over
        unchanged_db = _residual_db(mix_after, audio.mix(broken))
        result["unchanged_residual_db"] = round(unchanged_db, 1)
        result["pass"] = bool(detected and unchanged_db <= UNTOUCHED_DB)
    return result
