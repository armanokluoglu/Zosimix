# Full set v2: harness vs plain Claude Code vs flstudio-mcp (Sonnet 5.5), 2026-11-26

> Later: mud and resonance repairs were re-measured with a grader that doesn't flatten out (D73). Regraded, plain passes 33/90 and the harness 46/90; see [harness-v2.md](harness-v2.md).

All 30 tasks of `full-v2` (D69), 3 repeats each, for three configurations:

- **`zosimix`**: Claude Code with the Zosimix MCP server and the diagnosis skill.
- **`plain`**: Claude Code with file tools and Bash in a Python environment with the same audio libraries (D65).
- **`flmcp`**: Claude Code working in FL Studio 20.9.2 through rosasynthesiz/flstudio-mcp. It is the existing FL Studio MCP, ported to 20.9.2 (D66), given its 44 mixing tools, and graded from FL renders of the mix it leaves in FL (D70).

The model is `claude-sonnet-5-5` throughout. No run timed out, none raised an integrity flag, and no FL cycle failed.

## Where the numbers come from

`full-v2` is `full` with its 9 mud and resonance tasks redrawn, because the original ones barely changed the mix (D68, D69). The other 21 tasks are byte-for-byte the same task, so their earlier runs still describe them.

| Config | 21 unchanged tasks | 9 redrawn tasks |
|---|---|---|
| `zosimix`, `plain` | run `full-1` (commits `6002662`, `f43d781`) | run `full-2` (commit `1600a1c`) |
| `flmcp` | run `full-2-flmcp` (commit `41a2650`) | run `full-2-flmcp` (commit `41a2650`) |

Each run's `run_info.jsonl` records its commits. The grader used by the later runs was checked against full-1: all 180 full-1 answers regrade identically (D70).

## Headline

| | Harness (`zosimix`) | Plain Claude Code | flstudio-mcp |
|---|---|---|---|
| Pass rate, all 30 tasks | **46/90 = 51%** (95% CI 41–61%) | **31/90 = 34%** (25–45%) | **12/90 = 13%** (8–22%) |
| Without the 3 smoke-overlap tasks | 40/81 = 49% (39–60%) | 27/81 = 33% (24–44%) | 10/81 = 12% (7–21%) |
| Passes per repeat (1, 2, 3) | 15, 15, 16 | 9, 10, 12 | 4, 4, 4 |
| Fault correctly identified | 52/90 | 44/90 | 20/90 |
| Runs that damaged healthy stems* | 6/90 | 23/88 | 13/90 |
| Answer submitted | 90/90 | 88/90 | 90/90 |
| Median agent time per task | 33 s | 35 s | 73 s (+ about 1 min of FL renders for grading) |
| Average turns / output tokens | 7.5 / 1,116 | 4.7 / 2,258 | 24.7 / 2,524 |
| API-equivalent cost (not billed; Claude Pro) | $4.16 | $4.10 | $10.23 |

\* The sum of the stems a correct answer may not name changed by more than −30 dB residual. This is the same measure for all three configs; FL can't report which settings changed, so the older "touched other stems" count isn't used here.

The confidence intervals are Wilson intervals over runs. They overstate certainty, because repeats of one task are correlated. So the pairs are also compared by task: how many tasks each config passed more often than the other.

| Comparison, by task | Better | Worse | Tied | Sign test |
|---|---|---|---|---|
| Harness vs plain | 10 | 4 | 16 | p ≈ 0.18 |
| Harness vs flstudio-mcp | 15 | 0 | 15 | p < 0.001 |
| Plain vs flstudio-mcp | 13 | 1 | 16 | p ≈ 0.002 |

Both Claude Code configs are clearly ahead of flstudio-mcp on these tasks. The harness is ahead of plain in every repeat and overall, but over 30 tasks the by-task test doesn't rule out chance (p ≈ 0.18). On full-1's original tasks the same comparison gave p ≈ 0.065 (D68).

## By fault type

Passes, with the number of runs that named the right fault on the right stem in brackets.

| Fault | Harness | Plain | flstudio-mcp |
|---|---|---|---|
| Clipping | 12/12 (12) | 4/12 (4) | 0/12 (0) |
| Control (no fault) | 12/12 (12) | 11/12 (11) | 10/12 (10) |
| Gain | 4/12 (5) | 0/12 (4) | 2/12 (3) |
| Polarity | 8/15 (8) | 5/15 (6) | 0/15 (0) |
| Pan | 6/12 (6) | 7/12 (7) | 0/12 (0) |
| Resonance (redrawn) | 4/12 (8) | 4/12 (7) | 0/12 (6) |
| Mud (redrawn) | 0/15 (1) | 0/15 (5) | 0/15 (1) |

By hint level: with no hint the harness passed 22/48, plain 12/48 and flstudio-mcp 5/48. With a vague hint: 24/42, 19/42 and 7/42.

## Why flstudio-mcp scores low

Its agent can see levels and nothing else. Every one of the 90 runs played the song and read meters (935 level readings in all), and its meters give one peak per track: no left/right split, no spectrum, no phase. So:

- **Pan, polarity and in-stem clipping are invisible.** It named the right fault on the right stem 0 times in 39 runs. Its own summaries say so: on full-v2-003 the agent concluded the lopsided image was "probably baked into a stem's stereo audio", but its meters couldn't say which stem. Mix Doctor's "clipping" rule looks at a track's peak level (risk above −1 dBFS, clipping at 0), and the injected clipping flattens a stem's peaks well below that.
- **Resonance is guessed, not measured.** It named the right stem in 6 of 12 runs, from the hint's instrument family, but its EQ intent cuts at a generic frequency. On full-v2-004 it cut 3 kHz against a resonance at 2.46 kHz and wrote that it "picked that frequency without measuring the spectrum". Repair scores were −0.00 to 0.05.
- **Gain is where it can work.** The 6 dB fault on full-v2-013 was found and fixed in all 3 runs (repair 0.93). One of them also changed other stems, so 2 passed.
- **No-fault controls mostly pass** (10/12): it usually leaves a healthy mix alone.
- **Its level tools mislead it sometimes.** In the first check run it cut a bass by 17 dB on a Mix Doctor "clipping" finding that its own direct reading contradicted (D70). The fader dB formula is off as shipped (D66).
- It tried Bash 28 times. Bash isn't available in this configuration, so those calls were refused, and it carried on with its FL tools.

This compares the *tools*, not the model: all three configs run the same model. flstudio-mcp is built for producing in FL, with composition, arrangement and plugin control, and only part of it is about mixing. These results say that for diagnosing a broken mix, measurements of the audio matter more than control over FL.

## Mud and resonance after the redraw

The redrawn faults change the mix by 1–3 dB (mud) and 2–6 dB (resonance) against the rest of the mix (D69).

- **Resonance is no longer at the floor.** The harness passed 4/12 and named the right stem in 8, plain 4/12 and 7. On the largest one (full-v2-025) the harness passed 3 of 3.
- **Mud still passes 0 times in 45 runs, now for a different reason.** The agents find the stem more often (harness 1/15, plain 5/15, flstudio-mcp 1/15), but they cut too little: −4 to −9 dB against an 8–12 dB boost. That removes 23–58% of the error, and the bar is 70%. Scoring those repairs with a measure that doesn't flatten out would raise them by only 0.1–0.15, so the grader isn't what holds them back. Without a reference, nothing in the stems says how big the boost was.

## Per task

Passes out of 3 repeats.

| Task | Fault | Size | Hint | Harness | Plain | flstudio-mcp |
|---|---|---|---|---|---|---|
| full-v2-001 | polarity | 0 | vague | 2/3 | 1/3 | 0/3 |
| full-v2-002 ʳ | mud | 2 | vague | 0/3 | 0/3 | 0/3 |
| full-v2-003 | pan | 2 | vague | 3/3 | 3/3 | 0/3 |
| full-v2-004 ʳ | resonance | 2 | vague | 0/3 | 1/3 | 0/3 |
| full-v2-005 ⁱ | control | 0 | none | 3/3 | 2/3 | 2/3 |
| full-v2-006 | gain | 0 | vague | 0/3 | 0/3 | 0/3 |
| full-v2-007 | clipping | 0 | vague | 3/3 | 3/3 | 0/3 |
| full-v2-008 | polarity | 0 | none | 3/3 | 1/3 | 0/3 |
| full-v2-009 ʳ | mud | 0 | none | 0/3 | 0/3 | 0/3 |
| full-v2-010 | pan | 0 | none | 0/3 | 0/3 | 0/3 |
| full-v2-011 ʳ | resonance | 0 | vague | 0/3 | 0/3 | 0/3 |
| full-v2-012 | control | 0 | vague | 3/3 | 3/3 | 3/3 |
| full-v2-013 | gain | 1 | vague | 3/3 | 0/3 | 2/3 |
| full-v2-014 | clipping | 1 | none | 3/3 | 0/3 | 0/3 |
| full-v2-015 ⁱ | polarity | 0 | none | 0/3 | 0/3 | 0/3 |
| full-v2-016 ʳ | mud | 1 | vague | 0/3 | 0/3 | 0/3 |
| full-v2-017 | pan | 1 | none | 0/3 | 1/3 | 0/3 |
| full-v2-018 ʳ | resonance | 1 | vague | 1/3 | 2/3 | 0/3 |
| full-v2-019 | control | 0 | none | 3/3 | 3/3 | 3/3 |
| full-v2-020 | gain | 2 | none | 1/3 | 0/3 | 0/3 |
| full-v2-021 | clipping | 2 | none | 3/3 | 0/3 | 0/3 |
| full-v2-022 | polarity | 0 | none | 0/3 | 1/3 | 0/3 |
| full-v2-023 ʳ | mud | 2 | none | 0/3 | 0/3 | 0/3 |
| full-v2-024 | pan | 2 | none | 3/3 | 3/3 | 0/3 |
| full-v2-025 ʳ | resonance | 2 | vague | 3/3 | 1/3 | 0/3 |
| full-v2-026 | control | 0 | vague | 3/3 | 3/3 | 2/3 |
| full-v2-027 | gain | 0 | none | 0/3 | 0/3 | 0/3 |
| full-v2-028 | clipping | 0 | none | 3/3 | 1/3 | 0/3 |
| full-v2-029 ⁱ | polarity | 0 | vague | 3/3 | 2/3 | 0/3 |
| full-v2-030 ʳ | mud | 0 | none | 0/3 | 0/3 | 0/3 |

ʳ Redrawn in full-v2 (D69). ⁱ Repeats a smoke task the skill was tuned on (D52).

## Still weak for everyone

- **Mud:** 0 of 45 runs, for the reason above.
- **The smallest gain (3 dB) and pan (0.3) faults:** 0 of 36 runs between them (full-v2-006, -010 and -027). Without a reference mix, a 3 dB level difference or a slight lean looks like an artistic choice.

## Data

The songs come from MoisesDB and AlbumDB.

## MoisesDB

- License: CC BY-NC-SA 4.0 (non-commercial; derivatives must use the same license)
- Source: https://music.ai/research/ · https://github.com/moises-ai/moises-db

```bibtex
@misc{pereira2023moisesdb,
  title={Moisesdb: A dataset for source separation beyond 4-stems},
  author={Igor Pereira and Felipe Araújo and Filip Korzeniowski and Richard Vogl},
  year={2023},
  eprint={2307.15913},
  archivePrefix={arXiv},
  primaryClass={cs.SD}
}
```

## AlbumDB

- License: CC BY 4.0
- Source: https://doi.org/10.5281/zenodo.19683001

```bibtex
@dataset{mckenzie_2026_19683001,
  author    = {McKenzie, Thomas and Moliner Juanpere, Eloi and Wright, Alec},
  title     = {AlbumDB: A multitrack dataset of a ten-song album with stereo and immersive 7.1.4 masters},
  month     = apr,
  year      = 2026,
  publisher = {Zenodo},
  version   = {1.0},
  doi       = {10.5281/zenodo.19683001},
  url       = {https://doi.org/10.5281/zenodo.19683001}
}
```
