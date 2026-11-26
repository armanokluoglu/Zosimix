# Zosimix

**An agent that repairs mixes it can't hear, and a benchmark that proves it.**

<!-- The demo video goes here (DESIGN.md §6). -->

![Pass rate on the full-v2 benchmark: Zosimix harness 51%, plain Claude Code 37%, flstudio-mcp 13%, overall and by fault type](results/chart.svg)

Claude can't listen to audio. Zosimix gives it a way to "hear" a multitrack mix through measurement tools, lets it repair what it finds (offline or inside FL Studio), and grades every repair against a known answer. The test set is made of faults injected into professionally mixed multitrack recordings, so the correct diagnosis and the correct fix are always known.

## Results

Every configuration runs the same model (Claude Sonnet 5.5) on the same 30 tasks, 3 times each. The difference between them is the tools the model is given.

| | Zosimix harness | Plain Claude Code | [flstudio-mcp](https://github.com/rosasynthesiz/flstudio-mcp) |
|---|---|---|---|
| **Pass rate** | **51%** (46/90) | 37% (33/90) | 13% (12/90) |
| Partial credit | 0.54 | 0.40 | 0.14 |
| Clipping | 12/12 | 4/12 | 0/12 |
| No fault (leave it alone) | 12/12 | 11/12 | 10/12 |
| Polarity | 8/15 | 5/15 | 0/15 |
| Pan | 6/12 | 7/12 | 0/12 |
| Gain | 4/12 | 0/12 | 2/12 |
| Resonance | 4/12 | 6/12 | 0/12 |
| Mud | 0/15 | 0/15 | 0/15 |

A run **passes** only if it names the right fault on the right stem, removes at least 70% of the fault-specific error, and leaves every healthy stem unchanged. Clipping is the exception: baked-in clipping can't be repaired, so the right answer is to report it and change nothing. Partial credit counts a correct but incomplete repair at its repair score.

- Comparing task by task, the harness beats flstudio-mcp on 15 tasks and loses on none (sign test p < 0.001). Against plain Claude Code it wins 10 tasks and loses 4 (p ≈ 0.18): ahead in every repeat, but not yet conclusive on 30 tasks. Details: [results/full-v2.md](results/full-v2.md).
- flstudio-mcp is an FL Studio MCP built for producing: its agent can read levels but not spectra, stereo balance or phase, so most faults are invisible to it.
- **Work in progress:** a revised harness passes 69% on a separate development set, up from 44%: a `triage` tool, mix-aware mud and resonance rankings, and a mistaken-pan check. It hasn't been measured on the test set yet. How it was tuned without touching the test set, and what didn't work: [results/harness-v2.md](results/harness-v2.md).

## How it works

**The harness** is an MCP server plus a diagnosis skill for Claude Code ([skills/zosimix-diagnosis](skills/zosimix-diagnosis/SKILL.md)). The agent never hears audio; it measures it:

| Tool | What it tells the agent |
|---|---|
| `triage` | Every objective check at once: clipping, drum polarity, mistaken pans, twin levels, and the top mud and resonance suspects |
| `overview` | Loudness, peak, dynamics, stereo balance and band shape of every stem and the mix |
| `scan` | All stems ranked on one measure (audible resonances, low-mid excess, pan) |
| `spectrum`, `compare`, `phase`, `tonal_balance` | A closer look: persistent bumps, masking, drum-mic polarity, shape against other professionally mixed songs |
| `set_gain`, `set_pan`, `set_polarity`, `set_width`, `set_eq_band` | Changes, held as pending until committed |
| `commit_changes` | Applies the changes, re-renders, and reports what measurably moved |
| `submit_diagnosis` | The final answer: refused while changes are uncommitted |

**The benchmark** injects one fault into one stem of a real multitrack: gain, pan, polarity, resonance, mud or clipping, or nothing at all as a control. Mud and resonance are sized by how much they change the mix, so they can actually be heard in it (D69). Tasks come from a seeded generator, and each task's brief carries at most a vague client note ("the mix feels muddy").

**Two engines** render a mix state: a fast offline engine for the agent's previews and for grading, and FL Studio 20.9.2 driven over a MIDI SysEx bridge. A parity check rendered the same mixes through both: 27 of 28 match to within −40 dB residual, 0.1 dB per band and 0.05 LU. The exception is a known phase difference in FL's low-pass, which no fault needs ([results/parity.md](results/parity.md)).

**Graders are deterministic:** no LLM judge. They check the diagnosis, how much of the fault-specific error the repair removed, and that nothing else changed.

**Eval integrity:**
- Each run gets a fresh workspace outside the repo, holding only the faulty stems and the brief.
- Transcripts are scanned for attempts to reach the answers, and for answers showing up in tool output.
- The harness was tuned only on a separate development set of songs.
- Any commit that touches the graders or the task generator says so.

## Running it

Python 3.11+ with [uv](https://docs.astral.sh/uv/):

```
uv sync --extra dev
uv run pytest
```

Audio is never committed. Fetch AlbumDB songs straight from Zenodo with `python -m zosimix.datasets.albumdb fetch 01 10`. MoisesDB needs its zip from [music.ai](https://music.ai/research/) and `python -m zosimix.datasets.moisesdb import <zip> <track ids>`. The task sets in [tasks/](tasks) are committed.

```
python -m zosimix.runner run --set full-v2 --config zosimix --config plain --repeats 3 --workers 4
python -m zosimix.runner report --run <run id>
python -m zosimix.oracle --set full-v2        # can the measurements single out each fault at all?
python -m zosimix.chart                       # redraws results/chart.svg
```

Runs use the Claude Code CLI with a Claude subscription login, never an API key. The FL Studio parts (FL engine, parity check, flstudio-mcp baseline) need FL Studio 20.9.2 on Windows, loopMIDI, and the template described in [fl_bridge/TEMPLATE.md](fl_bridge/TEMPLATE.md).

## Repository

- [DESIGN.md](DESIGN.md): architecture, benchmark design, grading and plan
- [docs/decisions.md](docs/decisions.md): every design decision, with the alternatives and the reasons (75+ entries)
- [results/](results): every evaluation write-up
- `src/zosimix/`: harness, engines, faults, graders, runner
- `fl_bridge/`: the script that runs inside FL Studio, and the template

## Credits

The benchmark uses [MoisesDB](https://github.com/moises-ai/moises-db) (Pereira et al., 2023; CC BY-NC-SA 4.0) and [AlbumDB](https://doi.org/10.5281/zenodo.19683001) (McKenzie et al., 2026; CC BY 4.0). Full citations are in [CITATIONS.md](CITATIONS.md). Code is MIT licensed.

Designed by me, implemented by directing [Claude Code](https://claude.com/claude-code). The process, from design to decision log to review, is part of the project.

The name comes from Zosimos of Panopolis, an early alchemist who wrote about distillation and the equipment used to purify impure material.
