"""Tests for the agent's tools (MixSession) and the MCP server wrapper.

These check three things:
  1. the measurements point at the injected problem (a resonance shows up as a peak,
     an inverted drum mic shows up as a positive flip value),
  2. the rules hold (no submitting with uncommitted changes, valid answers only), and
  3. every tool's answer stays inside its size budget, because context is the agent's
     scarcest resource.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest

from zosimix import analysis, faults
from zosimix.engines.offline import OfflineEngine
from zosimix.mcp_server import build_server
from zosimix.tools import TOKEN_BUDGETS, MixSession

SR = 44100


def _stems():
    rng = np.random.default_rng(0)
    t = np.arange(SR * 4) / SR
    kick = 0.3 * np.sin(2 * np.pi * 55 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
    vox = 0.05 * rng.standard_normal(len(t))                      # broadband, smooth spectrum
    return {
        "drums_kick": kick[:, None],
        "drums_overheads": (0.6 * kick + 0.02 * rng.standard_normal(len(t)))[:, None],
        "bass": (0.2 * np.sin(2 * np.pi * 82 * t))[:, None],
        "vox_lead": vox[:, None],
    }


@pytest.fixture
def target():
    flat = {name: [-9.0, 3.0] for name, _, _ in analysis.BANDS}
    return {"bands": [b for b, _, _ in analysis.BANDS], "songs_used": 6, "mix": flat,
            "families": {"vocals": {"n": 12, **flat}}}


def session_with(fault: faults.Fault | None, target=None, tmp_path=None) -> MixSession:
    stems = _stems()
    if fault:
        stems[fault.stem] = faults.apply(fault, stems[fault.stem], SR)
    return MixSession(OfflineEngine(stems, SR), target, output_dir=tmp_path)


def test_resonance_shows_up_as_a_narrow_peak():
    s = session_with(faults.Fault("resonance", "vox_lead", 2, {"freq_hz": 2000.0, "gain_db": 12.0, "q": 8.0}))
    out = s.spectrum("vox_lead", 500, 8000)
    first_peak_hz = float(out.split("persistent bumps (resonance candidates): ")[1].split(" Hz")[0])
    assert abs(first_peak_hz - 2000) < 100


def test_inverted_drum_mic_shows_positive_flip_value():
    s = session_with(faults.Fault("polarity", "drums_overheads", 0))
    line = next(row for row in s.phase().splitlines() if row.startswith("drums_overheads:"))
    assert float(line.split("|")[1]) > 3.0


def test_cannot_submit_with_uncommitted_changes(tmp_path):
    s = session_with(None, tmp_path=tmp_path)
    s.set_gain("bass", -2.0)
    assert s.submit_diagnosis("fixed", [{"stem": "bass", "fault_type": "gain"}]).startswith("REFUSED")
    s.commit_changes()
    assert "submitted" in s.submit_diagnosis("fixed", [{"stem": "bass", "fault_type": "gain", "confidence": 0.8}])
    saved = json.loads((tmp_path / "diagnosis.json").read_text(encoding="utf-8"))
    assert saved["verdict"] == "fixed"
    assert json.loads((tmp_path / "mix_state.json").read_text(encoding="utf-8"))["bass"]["gain_db"] == -2.0


@pytest.mark.parametrize("verdict,findings", [
    ("maybe", []),
    ("fixed", [{"stem": "bass", "fault_type": "loudness"}]),
    ("fixed", [{"stem": "tuba", "fault_type": "gain"}]),
    ("no_fault", [{"stem": "bass", "fault_type": "gain"}]),
    ("fixed", []),
])
def test_invalid_diagnoses_are_refused(verdict, findings):
    assert session_with(None).submit_diagnosis(verdict, findings).startswith("REFUSED")


def test_measurements_describe_the_committed_mix_only():
    s = session_with(None)
    before = s.overview()
    s.set_gain("vox_lead", -12.0)
    assert s.overview() == before                     # pending changes are not "heard" yet
    report = s.commit_changes()
    assert "vox_lead" in report and "LUFS" in report
    assert s.overview() != before


def test_commit_without_verification_reports_nothing():
    s = session_with(None)
    s.verify = False
    s.set_gain("bass", 3.0)
    assert s.commit_changes() == "committed (1 track(s) changed)"


def test_every_tool_answer_fits_its_budget(target):
    s = session_with(faults.Fault("gain", "bass", 2, {"gain_db": 10.0}), target)
    answers = {
        "overview": s.overview(),
        "spectrum": s.spectrum("vox_lead"),
        "compare": s.compare("bass", "drums_kick"),
        "phase": s.phase(),
        "tonal_balance": s.tonal_balance(),
        "scan": s.scan("peaks") + s.scan("lowmid")[:0],
        "get_mix_state": s.get_mix_state(),
    }
    s.set_eq_band("vox_lead", 1, "peaking", 3000, -4, 2)
    s.set_gain("bass", -10)
    answers["commit_changes"] = s.commit_changes()
    for tool, text in answers.items():
        assert len(text) <= TOKEN_BUDGETS[tool], f"{tool} answer is {len(text)} chars"


def test_mcp_server_exposes_all_tools_and_calls_them(target):
    server = build_server(session_with(None, target))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"overview", "spectrum", "phase", "commit_changes", "submit_diagnosis", "set_eq_band"} <= names
    assert len(names) == 16
    result = asyncio.run(server.call_tool("overview", {}))
    assert "MIX" in str(result)


def test_scan_peaks_puts_the_resonant_stem_first():
    """D72: one call ranks every stem's strongest bump."""
    s = session_with(faults.Fault("resonance", "vox_lead", 2, {"freq_hz": 2000.0, "gain_db": 12.0, "q": 8.0}))
    out = s.scan("peaks")
    assert out.splitlines()[1].startswith("vox_lead: ")
    assert abs(float(out.splitlines()[1].split(": ")[1].split(" Hz")[0]) - 2000) < 100


def test_scan_lowmid_ranks_the_muddy_stem_and_suggests_a_cut():
    """D73: ranked by the stem's part in the mix's low-mids; the cut sits on its broad bump."""
    from zosimix import audio, targets
    clean = targets.shape(audio.to_stereo(_stems()["vox_lead"]), SR)          # "typical" = the clean vocal
    target = {"families": {"vocals": {"n": 12, **{b: [v, 1.5] for b, v in clean.items()}}}}
    s = session_with(faults.Fault("mud", "vox_lead", 2, {"freq_hz": 300.0, "gain_db": 9.0, "q": 1.0}), target)
    out = s.scan("lowmid")
    first = out.splitlines()[1]
    assert first.startswith("vox_lead: ") and "; cut " in first
    cut = float(first.split("; cut ")[1].split(" dB")[0])
    centre = float(first.split(" dB at ")[-1].split(" Hz")[0])
    assert 200 <= centre <= 420 and 3.0 < cut <= 12.0


def test_scan_rejects_unknown_measures_and_families():
    s = session_with(None)
    with pytest.raises(ValueError):
        s.scan("loudness")
    with pytest.raises(ValueError, match="Families"):
        s.scan("peaks", family="horns")


def test_scan_pan_flags_a_mistakenly_panned_mono_stem_only():
    """D74: mono, off centre, no twin is the signature of a mistaken pan."""
    assert session_with(None).scan("pan").splitlines()[1] == "none"
    s = session_with(faults.Fault("pan", "vox_lead", 1, {"pan": 0.6}))
    line = s.scan("pan").splitlines()[1]
    assert line.startswith("vox_lead: balance +") and "centre with pan -0.6" in line


def test_triage_runs_every_objective_check(target):
    s = session_with(faults.Fault("polarity", "drums_overheads", 0), target)
    out = s.triage()
    assert "polarity" in out and "drums_overheads flip +" in out
    for check in ("clipping", "pan (mono", "mud suspects", "resonance suspects"):
        assert check in out
    assert len(out) <= TOKEN_BUDGETS["triage"]


def test_spectrogram_is_a_png_and_shows_a_ring_as_a_bright_row():
    """D78: the picture tool. A fixed 2 kHz boost should light up the rows around 2 kHz."""
    import struct
    import zlib

    from zosimix import spectrogram
    s = session_with(faults.Fault("resonance", "vox_lead", 2, {"freq_hz": 2000.0, "gain_db": 18.0, "q": 8.0}))
    data = s.spectrogram("vox_lead", 200, 20000)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (spectrogram.WIDTH, spectrogram.HEIGHT)
    idat = data[data.index(b"IDAT") + 4: data.index(b"IEND") - 8]
    rows = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(height, 1 + width * 3)[:, 1:]
    brightness = rows.reshape(height, width, 3).astype(float).mean(axis=(1, 2))
    freqs = np.geomspace(20000, 200, height)
    near = brightness[np.abs(np.log2(freqs / 2000)) < 0.05].mean()
    away = brightness[np.abs(np.log2(freqs / 2000)) > 0.5].mean()
    assert near > away + 20


def test_ablation_switches_add_and_remove_tools():
    def names(**kw):
        return {t.name for t in asyncio.run(build_server(session_with(None), **kw).list_tools())}
    full = names()
    assert {"triage", "scan"} <= full and "spectrogram" not in full
    assert not {"triage", "scan"} & names(triage_tools=False)
    assert "spectrogram" in names(spectrogram_tool=True)
