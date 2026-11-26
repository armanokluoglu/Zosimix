"""Zosimix MCP server: exposes a MixSession's tools to Claude Code or any MCP client.

The tool descriptions below are what the agent reads, so they are written for it.

Run (normally started by Claude Code from an MCP config, one server per task workspace):
    python -m zosimix.mcp_server --workspace <task workspace> [--no-verify]

The workspace is the folder built by zosimix.tasks.materialize: stems/*.wav, brief.md and,
optionally, tonal_target.json. Results are written to <workspace>/output/.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from zosimix.engines.offline import OfflineEngine
from zosimix.tools import MixSession

INSTRUCTIONS = """\
You are repairing a multitrack mix you cannot hear. These tools measure it for you.
Workflow: triage -> overview -> investigate suspicious stems (scan, spectrum, compare, phase, tonal_balance)
-> make changes with set_* -> commit_changes (applies them and reports what moved)
-> re-measure if needed -> submit_diagnosis once. Measurements always describe the
committed mix. Make the smallest change that fixes the problem; leave healthy stems alone.
Some problems (e.g. clipping baked into a recording) cannot be fixed with these tools:
report them with verdict "unfixable" instead of changing anything."""


def build_server(session: MixSession) -> MCPServer:
    server = MCPServer(name="zosimix", instructions=INSTRUCTIONS)

    @server.tool()
    def overview() -> str:
        """Measure every stem and the mix. Columns: integrated loudness (LUFS), sample peak (dBFS),
        crest factor (dB), stereo balance R-L (dB, + = leans right), L/R correlation (1 = mono),
        clipped flat-top runs per minute, then each band's share of the stem's energy (dB)."""
        return session.overview()

    @server.tool()
    def spectrum(stem: str, lo_hz: float = 20.0, hi_hz: float = 20000.0) -> str:
        """Spectrum of one stem (or "MIX") between lo_hz and hi_hz: bumps that stay at the same
        frequency throughout the song (resonance candidates; note that instruments also have
        natural fixed resonances) and coarse 1/3-octave levels."""
        return session.spectrum(stem, lo_hz, hi_hz)

    @server.tool()
    def compare(stem_a: str, stem_b: str) -> str:
        """Band-by-band levels of two stems; flags bands where both are strong (masking)."""
        return session.compare(stem_a, stem_b)

    @server.tool()
    def phase(stems: list[str] | None = None) -> str:
        """Polarity check across related stems (default: all drum stems). For each stem: low-end
        correlation with the rest of the group, the lag, and how the group's low end would change
        if that stem were inverted. A clearly positive value means inverting would restore low end."""
        return session.phase(stems)

    @server.tool()
    def tonal_balance(stem: str | None = None) -> str:
        """Compare the mix's band shape (or one stem's, against its instrument family) with a
        target learned from other professionally mixed songs. Reports z-scores per band."""
        return session.tonal_balance(stem)

    @server.tool()
    def triage() -> str:
        """Start here. Runs every objective check at once (clipping, drum polarity, mistaken pans)
        and lists the top mud and resonance suspects. Clipping, polarity and pan findings are
        evidence on their own; mud and resonance only count with a matching client note."""
        return session.triage()

    @server.tool()
    def scan(measure: str, family: str | None = None) -> str:
        """Rank every stem (or one instrument family's: vocals, drums, bass, guitars, keys, ...) on
        one measure, to find the outlier in one call.
        measure="peaks": each stem's strongest persistent spectral bump, 300-8000 Hz (resonances).
        measure="lowmid": stems ranked by their part in the MIX's low-mids and how far above
        typical they are, with the cut that would undo the top suspects' bump (mud).
        measure="pan": the MIX's balance and every mono stem that sits off centre with no twin,
        with the pan setting that re-centres it (mistaken pans)."""
        return session.scan(measure, family)

    @server.tool()
    def get_mix_state() -> str:
        """Show the current settings of every non-neutral track, and whether changes are pending."""
        return session.get_mix_state()

    @server.tool()
    def set_gain(stem: str, gain_db: float) -> str:
        """Set a track's gain in dB (total, -60..+18; 0 = unchanged). Pending until commit_changes."""
        return session.set_gain(stem, gain_db)

    @server.tool()
    def set_pan(stem: str, pan: float) -> str:
        """Set a track's balance: -1 hard left, 0 centre, +1 hard right. Pending until commit.
        Moving a centred signal back to the centre with this control also changes its level."""
        return session.set_pan(stem, pan)

    @server.tool()
    def set_polarity(stem: str, inverted: bool) -> str:
        """Invert (true) or restore (false) a track's polarity. Pending until commit_changes."""
        return session.set_polarity(stem, inverted)

    @server.tool()
    def set_width(stem: str, width: float) -> str:
        """Set a track's stereo width: 0 mono, 1 unchanged, 2 double. Pending until commit."""
        return session.set_width(stem, width)

    @server.tool()
    def set_eq_band(stem: str, band: int, type: str, freq_hz: float, gain_db: float = 0.0,
                    q: float | None = None) -> str:
        """Set EQ band 1-7 of a track (Parametric EQ 2 style). type: peaking, low_shelf,
        high_shelf, highpass, lowpass. gain -18..+18 dB. q (higher = narrower): peaking
        0.2..14 (default 1), shelves 0.41..1.04 (default 1). highpass/lowpass are 12 dB/octave
        and ignore gain; their q (0.1..6.5) sets the bump at the cutoff (default 0.707 = no
        bump). Pending until commit_changes."""
        return session.set_eq_band(stem, band, type, freq_hz, gain_db, q)

    @server.tool()
    def clear_eq_band(stem: str, band: int) -> str:
        """Reset EQ band 1-7 of a track to flat. Pending until commit_changes."""
        return session.clear_eq_band(stem, band)

    @server.tool()
    def commit_changes() -> str:
        """Apply all pending changes, re-render, and report what measurably moved."""
        return session.commit_changes()

    @server.tool()
    def submit_diagnosis(verdict: str, findings: list[dict], summary: str = "") -> str:
        """Submit your final answer, once. verdict: "fixed", "unfixable" or "no_fault".
        findings: one object per problem: {"stem": <stem name>, "fault_type": one of gain,
        polarity, resonance, mud, pan, clipping, "confidence": 0..1}. Use [] for no_fault.
        Refused while changes are uncommitted."""
        return session.submit_diagnosis(verdict, findings, summary)

    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--no-verify", action="store_true", help="ablation: commit_changes reports nothing")
    args = ap.parse_args()
    target_path = args.workspace / "tonal_target.json"
    target = json.loads(target_path.read_text(encoding="utf-8")) if target_path.exists() else None
    session = MixSession(OfflineEngine.from_workspace(args.workspace), target,
                         output_dir=args.workspace / "output", verify=not args.no_verify)
    build_server(session).run("stdio")


if __name__ == "__main__":
    main()
