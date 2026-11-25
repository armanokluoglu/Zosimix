"""The agent's tools, independent of MCP (DESIGN.md §3.2, D23, D24).

MixSession holds one task's engine plus two mix states:
  - pending:   what the agent has asked for with set_* calls, not yet heard
  - committed: what the engine renders, and what every measurement describes
commit_changes() moves pending -> committed, re-renders, and reports what moved.
submit_diagnosis() is refused while anything is still pending, so the agent can never
claim a fix it hasn't verified.

Every tool returns a short plain-text answer. Output size is part of the design:
tests enforce a budget per tool (TOKEN_BUDGETS) so context stays small.
"""

from __future__ import annotations

import copy
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from zosimix import analysis, audio
from zosimix.engines.base import MixEngine
from zosimix.mixstate import MAX_EQ_BANDS, EqBand, MixState
from zosimix.songs import family_of

FAULT_TYPES = ("gain", "polarity", "resonance", "mud", "pan", "clipping")
VERDICTS = ("fixed", "unfixable", "no_fault")

# Rough budgets in characters (about 4 characters per token). Enforced by tests.
TOKEN_BUDGETS = {"overview": 4000, "spectrum": 900, "compare": 900, "phase": 900,
                 "tonal_balance": 1200, "commit_changes": 600, "get_mix_state": 2400}

BAND_LABELS = "sub low lmid mid hmid pres bril air"


def _fmt(v: float, digits: int = 1) -> str:
    return "-inf" if not math.isfinite(v) else f"{v:.{digits}f}"


class MixSession:
    def __init__(self, engine: MixEngine, target: dict | None = None, output_dir: Path | None = None,
                 verify: bool = True) -> None:
        self.engine = engine
        self.target = target
        self.output_dir = output_dir
        self.verify = verify                              # False = ablation: commit reports nothing
        self.committed = engine.get_state()
        self.pending = copy.deepcopy(self.committed)
        self._stem_cache: dict[tuple[str, str], dict] = {}
        self.submitted = False

    # ------------------------------------------------------------ measurement helpers

    def _key(self, stem: str) -> str:
        return json.dumps(MixState({stem: self.committed.tracks[stem]}).to_dict(), sort_keys=True)

    def _measure(self, name: str, x: np.ndarray) -> dict:
        sr = self.engine.sample_rate
        freqs, power_db = analysis.spectrum(x, sr)
        bands = analysis.band_levels(freqs, power_db)
        total = 10.0 * np.log10(sum(10.0 ** (v / 10.0) for v in bands.values()) + 1e-20)
        return {
            "lufs": analysis.loudness_lufs(x, sr),
            "peak_db": audio.gain_to_db(audio.peak(x)),
            "crest_db": analysis.crest_db(x),
            "balance_db": analysis.balance_db(x),
            "corr": analysis.lr_correlation(x),
            "clips_per_min": analysis.flat_top_runs_per_min(x, sr),
            "shape": {b: v - total for b, v in bands.items()},      # band share of total energy
            "freqs": freqs, "power_db": power_db,
        }

    def _stem_metrics(self) -> dict[str, dict]:
        """Measurements of every stem, cached per track setting. Stems that need measuring
        are measured in parallel threads (numpy and scipy release the GIL while working)."""
        rendered = self.engine.render_stems()
        keys = {name: (name, self._key(name)) for name in rendered}
        todo = [name for name in rendered if keys[name] not in self._stem_cache]
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
            for name, result in zip(todo, pool.map(lambda n: self._measure(n, rendered[n]), todo)):
                self._stem_cache[keys[name]] = result
        return {name: self._stem_cache[keys[name]] for name in rendered}

    def _mix_metrics(self) -> dict:
        key = ("__mix__", json.dumps(self.committed.to_dict(), sort_keys=True))
        if key not in self._stem_cache:
            self._stem_cache[key] = self._measure("mix", self.engine.render())
        return self._stem_cache[key]

    def _check_stem(self, stem: str) -> None:
        if stem not in self.committed.tracks:
            raise ValueError(f"unknown stem {stem!r}. Stems: {', '.join(self.engine.stem_names)}")

    # ------------------------------------------------------------ perception tools

    def overview(self) -> str:
        """One line per stem and one for the mix: level, peak, dynamics, stereo, clipping, band shape."""
        stems = self._stem_metrics()
        mix = self._mix_metrics()
        lines = [f"cols: LUFS peak crest bal(R-L) corr clips/min | band share dB: {BAND_LABELS}"]
        for name, m in [*stems.items(), ("MIX", mix)]:
            shape = " ".join(f"{m['shape'][b]:.0f}" for b, _, _ in analysis.BANDS)
            lines.append(f"{name}: {_fmt(m['lufs'])} {_fmt(m['peak_db'])} {_fmt(m['crest_db'])} "
                         f"{m['balance_db']:+.1f} {m['corr']:.2f} {m['clips_per_min']:.0f} | {shape}")
        return "\n".join(lines)

    def spectrum(self, stem: str, lo_hz: float = 20.0, hi_hz: float = 20000.0) -> str:
        """Narrow peaks (resonance candidates) and 1/3-octave levels of one stem (or 'MIX')."""
        if stem == "MIX":
            m = self._mix_metrics()
        else:
            self._check_stem(stem)
            m = self._stem_metrics()[stem]
        freqs, power_db = m["freqs"], m["power_db"]
        signal = self.engine.render() if stem == "MIX" else self.engine.render_stems()[stem]
        peaks = analysis.persistent_peaks(signal, self.engine.sample_rate, lo_hz, hi_hz)
        smooth = analysis.smooth_db(freqs, power_db)
        centres = [c for c in 1000.0 * 2.0 ** (np.arange(-17, 15) / 3.0) if lo_hz <= c <= hi_hz]
        step = max(1, len(centres) // 12)
        ref = smooth.max()
        levels = " ".join(f"{c:.0f}:{smooth[np.argmin(np.abs(freqs - c))] - ref:.0f}" for c in centres[::step])
        peak_txt = "; ".join(f"{p.freq_hz:.0f} Hz +{p.excess_db:.1f} dB Q~{p.q:.0f}" for p in peaks) or "none"
        return (f"{stem} {lo_hz:.0f}-{hi_hz:.0f} Hz\npersistent bumps (resonance candidates): {peak_txt}\n"
                f"1/3-oct level re max (Hz:dB): {levels}")

    def compare(self, stem_a: str, stem_b: str) -> str:
        """Band-by-band levels of two stems, to spot masking (both strong in the same band)."""
        self._check_stem(stem_a)
        self._check_stem(stem_b)
        metrics = self._stem_metrics()
        a, b = (analysis.band_levels(metrics[s]["freqs"], metrics[s]["power_db"]) for s in (stem_a, stem_b))
        lines = [f"band: {stem_a} / {stem_b} (dB, absolute)"]
        for name, lo, hi in analysis.BANDS:
            both = a[name] > max(a.values()) - 6 and b[name] > max(b.values()) - 6
            lines.append(f"{name} {lo}-{hi}: {a[name]:.0f} / {b[name]:.0f}{'  <- both strong' if both else ''}")
        return "\n".join(lines)

    def phase(self, stems: list[str] | None = None) -> str:
        """Low-end polarity check within a group of related stems (default: all drum stems)."""
        group = stems or [n for n in self.engine.stem_names if family_of(n) == "drums"]
        for s in group:
            self._check_stem(s)
        if len(group) < 2:
            return "need at least 2 related stems (no drum group found; pass stems explicitly)"
        rendered = self.engine.render_stems()
        report = analysis.phase_report({s: rendered[s] for s in group}, self.engine.sample_rate)
        lines = ["stem: corr-with-rest lag_ms | group low end if this stem were flipped (dB)"]
        lines += [f"{s}: {r['corr']:+.2f} {r['lag_ms']:+.1f} | {r['flip_db']:+.1f}" for s, r in report.items()]
        lines.append("(clearly positive flip value = flipping would restore low end)")
        return "\n".join(lines)

    def tonal_balance(self, stem: str | None = None) -> str:
        """Band shape of the mix (or one stem) against the data-derived target, in spreads (z)."""
        if not self.target:
            return "no tonal target available for this task"
        if stem:
            self._check_stem(stem)
            family = family_of(stem)
            ref = self.target["families"].get(family)
            if not ref:
                return f"no target for family {family!r} (too few examples)"
            shape, label = self._stem_metrics()[stem]["shape"], f"{stem} vs typical {family} (n={ref['n']})"
        else:
            ref = self.target["mix"]
            shape, label = self._mix_metrics()["shape"], f"MIX vs {self.target['songs_used']} other songs"
        lines = [f"{label}: band actual / target mean +/- spread -> z"]
        for name, _, _ in analysis.BANDS:
            mean, spread = ref[name]
            z = (shape[name] - mean) / spread
            flag = "  <- high" if z > 2 else "  <- low" if z < -2 else ""
            lines.append(f"{name}: {shape[name]:.1f} / {mean:.1f} +/- {spread:.1f} -> {z:+.1f}{flag}")
        return "\n".join(lines)

    # ------------------------------------------------------------ actions (pending until commit)

    def get_mix_state(self) -> str:
        changed = {n: t for n, t in self.pending.to_dict().items() if not self.pending.tracks[n].is_neutral()}
        status = "uncommitted changes pending" if self.has_pending else "all changes committed"
        return f"{status}. Non-neutral tracks (others are 0 dB, centred, flat):\n{json.dumps(changed)}"

    @property
    def has_pending(self) -> bool:
        return self.pending.to_dict() != self.committed.to_dict()

    def _update(self, stem: str, **changes) -> str:
        self._check_stem(stem)
        trial = copy.deepcopy(self.pending)
        for field_name, value in changes.items():
            setattr(trial.tracks[stem], field_name, value)
        trial.validate()
        self.pending = trial
        return f"pending: {stem} {changes}. Call commit_changes to apply and hear the result."

    def set_gain(self, stem: str, gain_db: float) -> str:
        return self._update(stem, gain_db=float(gain_db))

    def set_pan(self, stem: str, pan: float) -> str:
        return self._update(stem, pan=float(pan))

    def set_polarity(self, stem: str, inverted: bool) -> str:
        return self._update(stem, polarity=bool(inverted))

    def set_width(self, stem: str, width: float) -> str:
        return self._update(stem, width=float(width))

    def set_eq_band(self, stem: str, band: int, type: str, freq_hz: float, gain_db: float = 0.0,
                    q: float | None = None) -> str:
        """q=None means the type's default: 0.707 for highpass/lowpass, 1.0 otherwise."""
        self._check_stem(stem)
        if not 1 <= band <= MAX_EQ_BANDS:
            raise ValueError(f"band must be 1..{MAX_EQ_BANDS}")
        eq = copy.deepcopy(self.pending.tracks[stem].eq)
        while len(eq) < band:
            eq.append(EqBand())
        eq[band - 1] = EqBand(type, float(freq_hz), float(gain_db), None if q is None else float(q))
        return self._update(stem, eq=eq)

    def clear_eq_band(self, stem: str, band: int) -> str:
        self._check_stem(stem)
        eq = copy.deepcopy(self.pending.tracks[stem].eq)
        if 1 <= band <= len(eq):
            eq[band - 1] = EqBand()
        return self._update(stem, eq=eq)

    # ------------------------------------------------------------ verification

    def commit_changes(self) -> str:
        """Apply pending changes, re-render, and report only what measurably moved (D24)."""
        if not self.has_pending:
            return "nothing to commit"
        before_stems, before_mix = self._stem_metrics(), self._mix_metrics()
        changed = [n for n in self.engine.stem_names
                   if self.pending.to_dict()[n] != self.committed.to_dict()[n]]
        self.engine.set_state(self.pending)
        self.committed = copy.deepcopy(self.pending)
        if not self.verify:
            return f"committed ({len(changed)} track(s) changed)"
        after_stems, after_mix = self._stem_metrics(), self._mix_metrics()
        lines = [f"committed {len(changed)} track(s). What moved:"]
        for n in changed[:5]:
            lines.append(f"{n}: {self._delta(before_stems[n], after_stems[n])}")
        lines.append(f"MIX: {self._delta(before_mix, after_mix)}")
        return "\n".join(lines)

    @staticmethod
    def _delta(b: dict, a: dict) -> str:
        parts = []
        if math.isfinite(b["lufs"]) and math.isfinite(a["lufs"]) and abs(a["lufs"] - b["lufs"]) >= 0.3:
            parts.append(f"LUFS {b['lufs']:.1f}->{a['lufs']:.1f}")
        if abs(a["balance_db"] - b["balance_db"]) >= 0.5:
            parts.append(f"bal {b['balance_db']:+.1f}->{a['balance_db']:+.1f}")
        band_moves = sorted(((a["shape"][k] - b["shape"][k], k) for k in a["shape"]), key=lambda t: -abs(t[0]))
        parts += [f"{k} {d:+.1f}" for d, k in band_moves[:3] if abs(d) >= 1.0]
        return ", ".join(parts) or "no measurable change"

    def submit_diagnosis(self, verdict: str, findings: list[dict], summary: str = "") -> str:
        """Final answer. Refused while changes are uncommitted (D24)."""
        if self.has_pending:
            return "REFUSED: you have uncommitted changes. Call commit_changes first, then submit."
        if verdict not in VERDICTS:
            return f"REFUSED: verdict must be one of {VERDICTS}"
        for f in findings:
            if f.get("fault_type") not in FAULT_TYPES:
                return f"REFUSED: fault_type must be one of {FAULT_TYPES}"
            if f.get("stem") not in self.committed.tracks:
                return f"REFUSED: unknown stem {f.get('stem')!r}"
        if verdict == "no_fault" and findings:
            return "REFUSED: verdict no_fault cannot have findings"
        if verdict != "no_fault" and not findings:
            return "REFUSED: list at least one finding, or use verdict no_fault"
        self.submitted = True
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            (self.output_dir / "diagnosis.json").write_text(json.dumps(
                {"verdict": verdict, "findings": findings, "summary": summary}, indent=2), encoding="utf-8")
            (self.output_dir / "mix_state.json").write_text(self.committed.to_json(), encoding="utf-8")
        return "diagnosis submitted. The task is complete."
