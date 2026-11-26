"""Zosimix MCP server: exposes a MixSession's tools to Claude Code or any MCP client.

The tool descriptions below are what the agent reads, so they are written for it.

Run (normally started by Claude Code from an MCP config, one server per task workspace):
    python -m zosimix.mcp_server --workspace <task workspace> [--no-verify] [--no-triage] [--no-spectrogram]
    python -m zosimix.mcp_server                # live mode, for the Claude Code plugin (D84)

The flags switch parts on or off for the ablations (DESIGN.md §5, D78).

The workspace is the folder built by zosimix.tasks.materialize: stems/*.wav, brief.md and,
optionally, tonal_target.json. Results are written to <workspace>/output/.
"""

from __future__ import annotations

import argparse
import functools
import json
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from zosimix import live as live_mode
from zosimix.engines.offline import OfflineEngine
from zosimix.mixstate import MixState
from zosimix.tools import MixSession

INSTRUCTIONS = """\
You are repairing a multitrack mix you cannot hear. These tools measure it for you.
Workflow: triage -> overview -> investigate suspicious stems (scan, spectrogram, spectrum, compare, phase, tonal_balance)
-> make changes with set_* -> commit_changes (applies them and reports what moved)
-> re-measure if needed -> submit_diagnosis once. Measurements always describe the
committed mix. Make the smallest change that fixes the problem; leave healthy stems alone.
Some problems (e.g. clipping baked into a recording) cannot be fixed with these tools:
report them with verdict "unfixable" instead of changing anything."""


def build_server(session: MixSession | None, triage_tools: bool = True, spectrogram_tool: bool = True,
                 live: bool = False) -> MCPServer:
    """All the agent's tools. triage_tools=False leaves out triage and scan, and spectrogram_tool=True adds
    the spectrogram picture (part of the default harness since D81): both are ablation switches (D78).
    live=True is the plugin's mode (D84): no mix at start, open_mix loads one, and the fix can be
    applied to the FL project that is open."""
    holder: dict = {"session": session, "originals": {}, "undo": []}

    def tool(fn):
        """Register a tool whose input errors reach the agent. This MCP SDK hides an ordinary
        exception's message from the client ("Error executing tool"); a ToolError's text is sent.
        So a wrong stem name or an out-of-range value comes back as a readable reason (D84)."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except ValueError as exc:
                raise ToolError(str(exc)) from exc
        return server.tool()(wrapper)

    def current() -> MixSession:
        if holder["session"] is None:
            raise ValueError("No mix is open yet: call open_mix with the folder of exported stems first.")
        return holder["session"]

    instructions = INSTRUCTIONS if triage_tools else INSTRUCTIONS.replace("triage -> ", "").replace("scan, ", "")
    server = MCPServer(name="zosimix", instructions=instructions)

    @tool
    def overview() -> str:
        """Measure every stem and the mix. Columns: integrated loudness (LUFS), sample peak (dBFS),
        crest factor (dB), stereo balance R-L (dB, + = leans right), L/R correlation (1 = mono),
        clipped flat-top runs per minute, then each band's share of the stem's energy (dB)."""
        return current().overview()

    @tool
    def spectrum(stem: str, lo_hz: float = 20.0, hi_hz: float = 20000.0) -> str:
        """Spectrum of one stem (or "MIX") between lo_hz and hi_hz: bumps that stay at the same
        frequency throughout the song (resonance candidates; note that instruments also have
        natural fixed resonances) and coarse 1/3-octave levels."""
        return current().spectrum(stem, lo_hz, hi_hz)

    @tool
    def compare(stem_a: str, stem_b: str) -> str:
        """Band-by-band levels of two stems; flags bands where both are strong (masking)."""
        return current().compare(stem_a, stem_b)

    @tool
    def phase(stems: list[str] | None = None) -> str:
        """Polarity check across related stems (default: all drum stems). For each stem: low-end
        correlation with the rest of the group, the lag, and how the group's low end would change
        if that stem were inverted. A clearly positive value means inverting would restore low end."""
        return current().phase(stems)

    @tool
    def tonal_balance(stem: str | None = None) -> str:
        """Compare the mix's band shape (or one stem's, against its instrument family) with a
        target learned from other professionally mixed songs. Reports z-scores per band."""
        return current().tonal_balance(stem)

    if triage_tools:
        @tool
        def triage() -> str:
            """Start here. Runs every objective check at once (clipping, drum polarity, mistaken pans)
            and lists the top mud and resonance suspects. Clipping, polarity and pan findings are
            evidence on their own; mud and resonance only count with a matching client note."""
            return current().triage()

        @tool
        def scan(measure: str, family: str | None = None) -> str:
            """Rank every stem (or one instrument family's: vocals, drums, bass, guitars, keys, ...) on
            one measure, to find the outlier in one call.
            measure="peaks": each stem's strongest persistent spectral bump, 300-8000 Hz (resonances).
            measure="lowmid": stems ranked by their part in the MIX's low-mids and how far above
            typical they are, with the cut that would undo the top suspects' bump (mud).
            measure="pan": the MIX's balance and every mono stem that sits off centre with no twin,
            with the pan setting that re-centres it (mistaken pans)."""
            return current().scan(measure, family)

    if spectrogram_tool:
        @tool
        def spectrogram(stem: str, lo_hz: float = 20.0, hi_hz: float = 20000.0) -> Image:
            """A picture of one stem (or "MIX") over the whole song: time left to right, frequency
            bottom to top on a log scale from lo_hz to hi_hz, brightness = loudness (80 dB range).
            Faint horizontal lines mark 100 Hz, 1 kHz and 10 kHz. A resonance shows as a bright
            horizontal line that stays at one frequency while the notes move; mud as a bright band
            low down; clipping as smeared vertical streaks."""
            return Image(data=current().spectrogram(stem, lo_hz, hi_hz), format="png")


    if live:
        @tool
        def open_mix(folder: str) -> str:
            """Load a song to work on: a folder of stems exported from the DAW, one WAV per track
            (in FL Studio: File > Export > WAV with "Split mixer tracks"). The master file is
            skipped. Returns the stems' working names: the family a name starts with (drums_,
            bass_, vocals_, ...) is how the other tools group them."""
            engine, originals, target = live_mode.load_folder(Path(folder))
            holder["session"] = MixSession(engine, target, output_dir=Path(folder) / "zosimix-output")
            holder["originals"], holder["undo"] = originals, []
            lines = [f"opened {len(originals)} stems from {folder} (working name <- file name):"]
            lines += [f"{w} <- {o}" for w, o in originals.items()]
            return "\n".join(lines)

        @tool
        def apply_to_fl(dry_run: bool = True) -> str:
            """Put the committed fix into the FL Studio project that is open, over the Zosimix MIDI
            bridge. Each change is relative to what the mixer insert holds now, because the stems
            were exported after its fader, pan and effects. Always call it with dry_run=True
            first, show the user the plan, and only apply (dry_run=False) once they agree.
            revert_fl undoes it."""
            session = current()
            if session.has_pending:
                return "There are uncommitted changes: call commit_changes first."
            renamed = MixState({holder["originals"][n]: t for n, t in session.committed.tracks.items()})
            from zosimix.fl import live as fl_live
            from zosimix.fl.bridge import Bridge, BridgeError
            try:
                fl = Bridge()
            except (ImportError, BridgeError, OSError) as exc:   # MIDI packages or ports missing: say how to connect
                return (f"Can't reach FL Studio ({exc}). FL must be open with the Zosimix MIDI script enabled "
                        "on the loopMIDI ports 'Zosimix In'/'Zosimix Out' (see fl_bridge/TEMPLATE.md), and the "
                        "plugin's Python needs the 'fl' extra (mido, python-rtmidi).")
            try:
                changes, unmatched = fl_live.plan(fl, renamed)
                lines = [c.detail for c in changes] or ["nothing to change"]
                if unmatched:
                    lines.append("no mixer insert matched these stems, so they are left alone: " + ", ".join(unmatched))
                if dry_run:
                    return "PLAN (nothing changed yet):\n" + "\n".join(lines)
                holder["undo"] = fl_live.apply(fl, changes) + holder["undo"]
                return "APPLIED to the open FL project:\n" + "\n".join(lines) + "\n(revert_fl undoes this)"
            finally:
                fl.close()

        @tool
        def revert_fl() -> str:
            """Undo everything apply_to_fl changed in the open FL project, newest first."""
            if not holder["undo"]:
                return "Nothing to revert."
            from zosimix.fl import live as fl_live
            from zosimix.fl.bridge import Bridge
            fl = Bridge()
            try:
                n = fl_live.revert(fl, holder["undo"])
            finally:
                fl.close()
            holder["undo"] = []
            return f"Reverted {n} settings in the open FL project."

    @tool
    def get_mix_state() -> str:
        """Show the current settings of every non-neutral track, and whether changes are pending."""
        return current().get_mix_state()

    @tool
    def set_gain(stem: str, gain_db: float) -> str:
        """Set a track's gain in dB (total, -60..+18; 0 = unchanged). Pending until commit_changes."""
        return current().set_gain(stem, gain_db)

    @tool
    def set_pan(stem: str, pan: float) -> str:
        """Set a track's balance: -1 hard left, 0 centre, +1 hard right. Pending until commit.
        Moving a centred signal back to the centre with this control also changes its level."""
        return current().set_pan(stem, pan)

    @tool
    def set_polarity(stem: str, inverted: bool) -> str:
        """Invert (true) or restore (false) a track's polarity. Pending until commit_changes."""
        return current().set_polarity(stem, inverted)

    @tool
    def set_width(stem: str, width: float) -> str:
        """Set a track's stereo width: 0 mono, 1 unchanged, 2 double. Pending until commit."""
        return current().set_width(stem, width)

    @tool
    def set_eq_band(stem: str, band: int, type: str, freq_hz: float, gain_db: float = 0.0,
                    q: float | None = None) -> str:
        """Set EQ band 1-7 of a track (Parametric EQ 2 style). type: peaking, low_shelf,
        high_shelf, highpass, lowpass. gain -18..+18 dB. q (higher = narrower): peaking
        0.2..14 (default 1), shelves 0.41..1.04 (default 1). highpass/lowpass are 12 dB/octave
        and ignore gain; their q (0.1..6.5) sets the bump at the cutoff (default 0.707 = no
        bump). Pending until commit_changes."""
        return current().set_eq_band(stem, band, type, freq_hz, gain_db, q)

    @tool
    def clear_eq_band(stem: str, band: int) -> str:
        """Reset EQ band 1-7 of a track to flat. Pending until commit_changes."""
        return current().clear_eq_band(stem, band)

    @tool
    def commit_changes() -> str:
        """Apply all pending changes, re-render, and report what measurably moved."""
        return current().commit_changes()

    @tool
    def submit_diagnosis(verdict: str, findings: list[dict], summary: str = "") -> str:
        """Submit your final answer, once. verdict: "fixed", "unfixable" or "no_fault".
        findings: one object per problem: {"stem": <stem name>, "fault_type": one of gain,
        polarity, resonance, mud, pan, clipping, "confidence": 0..1}. Use [] for no_fault.
        Refused while changes are uncommitted."""
        return current().submit_diagnosis(verdict, findings, summary)

    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", type=Path, help="a benchmark task's workspace; without it: live mode (D84)")
    ap.add_argument("--no-verify", action="store_true", help="ablation: commit_changes reports nothing")
    ap.add_argument("--no-triage", action="store_true", help="ablation: leave out the triage and scan tools")
    ap.add_argument("--no-spectrogram", action="store_true", help="ablation: leave out the spectrogram picture")
    args = ap.parse_args()
    if args.workspace is None:
        build_server(None, triage_tools=not args.no_triage, spectrogram_tool=not args.no_spectrogram,
                     live=True).run("stdio")
        return
    target_path = args.workspace / "tonal_target.json"
    target = json.loads(target_path.read_text(encoding="utf-8")) if target_path.exists() else None
    session = MixSession(OfflineEngine.from_workspace(args.workspace), target,
                         output_dir=args.workspace / "output", verify=not args.no_verify)
    build_server(session, triage_tools=not args.no_triage, spectrogram_tool=not args.no_spectrogram).run("stdio")


if __name__ == "__main__":
    main()
