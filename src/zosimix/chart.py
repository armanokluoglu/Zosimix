"""The README's results charts: pass rate per configuration, and per fault type (D76, D87).

Two charts, each from its own set of graded runs (regraded grades where they exist, D73):
  results/chart.svg          the held-out set, 3 repeats: harness vs plain Claude Code
  results/chart-full-v2.svg  the full-v2 benchmark, 3 repeats, all three configurations
Hand-written SVG, so no plotting library, and the colours follow the page's light or dark theme.
A configuration keeps its colour in both charts. Re-run after a new evaluation run.

Usage:
    python -m zosimix.chart            # both charts
"""

from __future__ import annotations

import argparse
import collections
import json
from html import escape
from pathlib import Path

from zosimix import graders, tasks

REPO = Path(__file__).resolve().parents[2]
RUNS = Path("C:/zosimix/runs")
OUT = REPO / "results" / "chart.svg"
OUT_FULL_V2 = REPO / "results" / "chart-full-v2.svg"
HOLDOUT_RUN = "holdout-1"

# Which runs make up full-v2 for each configuration (results/full-v2.md). full-1 holds the
# 21 tasks full-v2 kept unchanged; full-2 the 9 redrawn mud and resonance tasks (D69).
SOURCES = {
    "zosimix": [("full-1", "unchanged"), ("full-2", "all")],
    "plain": [("full-1", "unchanged"), ("full-2", "all")],
    "flmcp": [("full-2-flmcp", "all")],
}
LABELS = {"zosimix": "Zosimix harness", "plain": "Plain Claude Code", "flmcp": "flstudio-mcp"}
FAULT_ORDER = ["clipping", "control", "polarity", "pan", "gain", "resonance", "mud"]


def _rows(run: str) -> list[dict]:
    path = RUNS / run / "regraded.jsonl"
    if not path.exists():
        path = RUNS / run / "results.jsonl"
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r.get("status") == "done"]


def full_v2_rows(sources: dict = SOURCES) -> dict[str, list[dict]]:
    """Each configuration's graded rows on full-v2, keyed by task number."""
    v1 = {s.task_id.rsplit("-", 1)[1]: s for s in tasks.load("full")}
    v2 = {s.task_id.rsplit("-", 1)[1]: s for s in tasks.load("full-v2")}
    unchanged = {n for n in v2 if (v1[n].song_id, v1[n].fault, v1[n].hint) == (v2[n].song_id, v2[n].fault, v2[n].hint)}
    out: dict[str, list[dict]] = {}
    for config, parts in sources.items():
        rows = []
        for run, which in parts:
            for r in _rows(run):
                n = r["task_id"].rsplit("-", 1)[1]
                if r["config"] == config and (which == "all" or n in unchanged):
                    rows.append(r)
        out[config] = rows
    return out


def holdout_rows(run: str = HOLDOUT_RUN) -> dict[str, list[dict]]:
    """The held-out run's graded rows per configuration (D86)."""
    rows = _rows(run)
    return {c: [r for r in rows if r["config"] == c] for c in LABELS if any(r["config"] == c for r in rows)}


def summarise(rows: dict[str, list[dict]]) -> dict:
    """Pass counts over in-scope runs only: a no-note mud or resonance task asks for something
    the harness is designed not to do, for every configuration alike (D83)."""
    rows = {c: [r for r in rs if graders.in_scope(r["grade"])] for c, rs in rows.items()}
    overall = {c: (sum(r["grade"]["pass"] for r in rs), len(rs)) for c, rs in rows.items()}
    by_fault: dict[str, dict[str, tuple[int, int]]] = {}
    for c, rs in rows.items():
        counts = collections.defaultdict(lambda: [0, 0])
        for r in rs:
            counts[r["grade"]["fault_type"]][0] += r["grade"]["pass"]
            counts[r["grade"]["fault_type"]][1] += 1
        by_fault[c] = {f: tuple(v) for f, v in counts.items()}
    return {"overall": overall, "by_fault": by_fault}


STYLE = """
  .surface { fill: #fcfcfb; } .t1 { fill: #0b0b0b; } .t2 { fill: #52514e; } .grid { stroke: #e4e2dc; }
  .s1 { fill: #2a78d6; } .s2 { fill: #eb6834; } .s3 { fill: #1baf7a; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19; } .t1 { fill: #f0efec; } .t2 { fill: #c3c2b7; } .grid { stroke: #34332f; }
    .s1 { fill: #3987e5; } .s2 { fill: #d95926; } .s3 { fill: #199e70; }
  }
  text { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
"""


def _bar(x: float, y: float, w: float, h: float, cls: str, horizontal: bool) -> str:
    """A bar with a 4 px rounded data end and a square end on the baseline."""
    r = min(4.0, w / 2, h / 2)
    if w <= 0 or h <= 0:
        return ""
    if horizontal:              # baseline on the left, rounded on the right
        d = (f"M{x},{y} H{x + w - r} Q{x + w},{y} {x + w},{y + r} V{y + h - r} Q{x + w},{y + h} {x + w - r},{y + h}"
             f" H{x} Z")
    else:                       # baseline at the bottom, rounded on top
        d = (f"M{x},{y + h} V{y + r} Q{x},{y} {x + r},{y} H{x + w - r} Q{x + w},{y} {x + w},{y + r} V{y + h} Z")
    return f'<path class="{cls}" d="{d}"/>'


def svg(summary: dict, title: str, caption: list[str]) -> str:
    width, pad = 760, 24
    configs = [c for c in LABELS if c in summary["overall"]]
    cls = {c: f"s{i + 1}" for i, c in enumerate(LABELS)}       # a configuration keeps its colour in every chart
    faults = [f for f in FAULT_ORDER if any(summary["by_fault"][c].get(f, (0, 0))[1] for c in configs)]
    rows_h = len(configs) * 34
    top = 60 + rows_h + 88
    bottom = top + 250
    height = bottom + 20 + 18 * len(caption) + 12
    parts = [(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{escape(title)}"><style>{STYLE}</style>'),
             f'<rect class="surface" x="0" y="0" width="{width}" height="{height}" rx="8"/>',
             f'<text class="t1" x="{pad}" y="36" font-size="18" font-weight="600">{escape(title)}</text>']

    # --- panel 1: overall pass rate, horizontal bars
    x0, x1, y = 200, width - 130, 60
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gx = x0 + frac * (x1 - x0)
        parts.append(f'<line class="grid" x1="{gx}" y1="{y}" x2="{gx}" y2="{y + rows_h}" stroke-width="1"/>')
        parts.append(f'<text class="t2" x="{gx}" y="{y + rows_h + 16}" font-size="11" text-anchor="middle">'
                     f'{int(frac * 100)}%</text>')
    for i, c in enumerate(configs):
        k, n = summary["overall"][c]
        by = y + 6 + i * 34
        parts.append(f'<text class="t1" x="{x0 - 12}" y="{by + 15}" font-size="13" text-anchor="end">{LABELS[c]}</text>')
        parts.append(_bar(x0, by, (x1 - x0) * k / n, 22, cls[c], horizontal=True))
        parts.append(f'<text class="t1" x="{x0 + (x1 - x0) * k / n + 8}" y="{by + 15}" font-size="13" '
                     f'font-weight="600">{100 * k / n:.0f}%</text>')
        parts.append(f'<text class="t2" x="{x0 + (x1 - x0) * k / n + 46}" y="{by + 15}" font-size="11">'
                     f'{k}/{n} runs</text>')

    # --- panel 2: pass rate per fault type, grouped vertical bars
    left, right = 64, width - pad
    parts.append(f'<text class="t1" x="{pad}" y="{top - 22}" font-size="14" font-weight="600">By fault type</text>')
    for j, c in enumerate(configs):           # legend: swatch + name, always present for 2+ series
        lx = 200 + j * 170
        parts.append(f'<rect class="{cls[c]}" x="{lx}" y="{top - 33}" width="12" height="12" rx="2"/>')
        parts.append(f'<text class="t2" x="{lx + 18}" y="{top - 22}" font-size="12">{LABELS[c]}</text>')
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gy = bottom - frac * (bottom - top)
        parts.append(f'<line class="grid" x1="{left}" y1="{gy}" x2="{right}" y2="{gy}" stroke-width="1"/>')
        parts.append(f'<text class="t2" x="{left - 8}" y="{gy + 4}" font-size="11" text-anchor="end">'
                     f'{int(frac * 100)}%</text>')
    group = (right - left) / len(faults)
    bar_w, gap = min(40.0, (group - 24) / len(configs)), 2
    for g, fault in enumerate(faults):
        gx = left + g * group + (group - bar_w * len(configs)) / 2
        for j, c in enumerate(configs):
            k, n = summary["by_fault"][c].get(fault, (0, 0))
            h = (bottom - top) * (k / n if n else 0)
            if n and k == 0:     # a 0% result still shows, as a stub on the baseline, so it reads as zero
                parts.append(f'<rect class="{cls[c]}" x="{gx + j * bar_w + gap / 2}" y="{bottom - 2}" '
                             f'width="{bar_w - gap}" height="2"/>')
            else:
                parts.append(_bar(gx + j * bar_w + gap / 2, bottom - h, bar_w - gap, h, cls[c], horizontal=False))
        parts.append(f'<text class="t1" x="{left + g * group + group / 2}" y="{bottom + 18}" font-size="12" '
                     f'text-anchor="middle">{fault}</text>')
    for n, line in enumerate(caption):
        parts.append(f'<text class="t2" x="{pad}" y="{bottom + 44 + 16 * n}" font-size="11">{escape(line)}</text>')
    parts.append("</svg>")
    return "\n".join(p for p in parts if p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    pass_rule = "Pass = right fault on the right stem, repaired, and nothing else changed."
    charts = [
        (OUT, holdout_rows(), "Pass rate on six held-out songs (in-scope tasks)",
         ["30 tasks on songs never used for tuning x 3 repeats, Claude Sonnet 5.5. Mud and resonance count when",
          "the client mentions them (no held-out mud task had a note). flstudio-mcp wasn't run on these songs.",
          pass_rule]),
        (OUT_FULL_V2, full_v2_rows(), "Pass rate on the full-v2 benchmark (in-scope tasks)",
         ["30 injected-fault tasks x 3 repeats, Claude Sonnet 5.5, before the harness's tuning rounds.",
          "Mud and resonance count when the client mentions them.", pass_rule]),
    ]
    for path, rows, title, caption in charts:
        summary = summarise(rows)
        path.write_text(svg(summary, title, caption), encoding="utf-8")
        print(f"{path.name}: " + ", ".join(f"{LABELS[c]} {k}/{n} = {100 * k / n:.0f}%"
                                           for c, (k, n) in summary["overall"].items()))


if __name__ == "__main__":
    main()
