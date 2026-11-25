# Full run 1: harness vs plain Claude Code (Sonnet 5.5), 2026-11-25

The full set's 30 tasks, each run 3 times by two configurations, 180 runs in all:

- **`zosimix`**: Claude Code with the Zosimix MCP server and the diagnosis skill.
- **`plain`**: Claude Code with file tools and Bash in a Python environment with the same audio libraries, and no Zosimix tools (D65).

The model is `claude-sonnet-5-5` for both. The run started at commit `6002662` and resumed at `f43d781` after a scanner crash (D67). Both commits are recorded in `run_info.jsonl`. No run timed out, no run raised an integrity flag, and every graded row is in `C:\zosimix\runs\full-1\results.jsonl`.

## Headline

| | Harness (`zosimix`) | Plain Claude Code |
|---|---|---|
| Pass rate, all 30 tasks | **42/90 = 47%** (95% CI 37–57%) | **27/90 = 30%** (22–40%) |
| Pass rate, without the 3 smoke-overlap tasks | 36/81 = 44% (34–55%) | 23/81 = 28% (20–39%) |
| Passes per repeat (1, 2, 3) | 14, 13, 15 | 8, 8, 11 |
| Fault correctly identified | 44/90 | 36/90 |
| Runs that changed a healthy stem | 11/90 | 30/90 |
| Runs with a false finding | 11/90 | 32/90 |
| Answer submitted | 90/90 | 88/90 |
| Median time per task | 27 s | 35 s |
| Average turns / output tokens | 7.1 / 1,045 | 4.7 / 2,218 |
| API-equivalent cost (not billed; Claude Pro) | $4.00 | $4.02 |

The confidence intervals are Wilson intervals over the 90 runs. They treat the repeats as independent, which overstates certainty, because repeats of one task are correlated. A paired view by task is stricter. The harness passed more repeats than plain on 9 tasks and fewer on 2, with 19 ties. A two-sided sign test on 9 against 2 gives p ≈ 0.065. So the direction is consistent but this one run, on 30 tasks, isn't conclusive on its own.

The three overlap tasks (`full-005`, `full-015`, `full-029`) repeat a smoke task the skill was tuned on (D52). Leaving them out changes neither config's rate by more than 3 points.

## By fault type

| Fault | Harness | Plain | What happened |
|---|---|---|---|
| Clipping | 12/12 | 4/12 | The harness's peak check makes "unfixable" easy to call. Plain missed it: 5 of its 8 failures answered `no_fault`, and 3 answered `fixed` without naming the clipped stem. |
| Control (no fault) | 12/12 | 11/12 | Both mostly leave a healthy mix alone. |
| Gain | 4/12 | 0/12 | Only the 6 dB and 10 dB faults were fixed. Neither config found a 3 dB fault. |
| Polarity | 8/15 | 5/15 | The drum-bus phase check helps, but it misses on some songs. |
| Pan | 6/12 | 7/12 | About even. Both fail the smallest pan fault (`full-010`, 0/3 each). |
| Mud | **0/15** | **0/15** | Nobody named the right stem in any of the 30 runs (see below). |
| Resonance | **0/12** | **0/12** | 5 detections in 24 runs, and only 1 real repair (`full-025`, repair 0.68). |

By hint level, the harness passed 22/48 with no hint and 20/42 with a vague hint. Plain passed 12/48 and 15/42.

## Mud and resonance are at the floor for both configs

This is the run's main finding about the benchmark itself, not about the agents.

On all 15 mud tasks the harness answered `no_fault`. Its summaries say why, for example: "Mix low-mid z=+1.6 (normal). No stem is a clear low-mid outlier". The injected mud is a band-shape error of 1.2–2.1 dB on one stem. That falls inside what the harness's analysis treats as normal variation between songs. Plain answered `fixed` on 9 of 15 mud tasks, but always on the wrong stem.

Resonance looks the same. The narrow boosts on the small and medium sizes don't stand out in the tools' readings, and only the largest one was found once.

So for these two families, the benchmark can't currently tell the configs apart. Either the injected sizes are too small to find from the stems alone, or the analysis tools need a finer per-stem spectral view. Telling those apart is the next decision. It touches the task generator or the tools, so it is the owner's call, and a change to the generator would be called out as an eval-integrity change.

## Per task

Passes out of 3 repeats.

| Task | Fault | Size | Hint | Harness | Plain |
|---|---|---|---|---|---|
| full-001 | polarity | 0 | vague | 2/3 | 1/3 |
| full-002 | mud | 2 | vague | 0/3 | 0/3 |
| full-003 | pan | 2 | vague | 3/3 | 3/3 |
| full-004 | resonance | 2 | vague | 0/3 | 0/3 |
| full-005 ⁱ | control | 0 | none | 3/3 | 2/3 |
| full-006 | gain | 0 | vague | 0/3 | 0/3 |
| full-007 | clipping | 0 | vague | 3/3 | 3/3 |
| full-008 | polarity | 0 | none | 3/3 | 1/3 |
| full-009 | mud | 0 | none | 0/3 | 0/3 |
| full-010 | pan | 0 | none | 0/3 | 0/3 |
| full-011 | resonance | 0 | vague | 0/3 | 0/3 |
| full-012 | control | 0 | vague | 3/3 | 3/3 |
| full-013 | gain | 1 | vague | 3/3 | 0/3 |
| full-014 | clipping | 1 | none | 3/3 | 0/3 |
| full-015 ⁱ | polarity | 0 | none | 0/3 | 0/3 |
| full-016 | mud | 1 | vague | 0/3 | 0/3 |
| full-017 | pan | 1 | none | 0/3 | 1/3 |
| full-018 | resonance | 1 | vague | 0/3 | 0/3 |
| full-019 | control | 0 | none | 3/3 | 3/3 |
| full-020 | gain | 2 | none | 1/3 | 0/3 |
| full-021 | clipping | 2 | none | 3/3 | 0/3 |
| full-022 | polarity | 0 | none | 0/3 | 1/3 |
| full-023 | mud | 2 | none | 0/3 | 0/3 |
| full-024 | pan | 2 | none | 3/3 | 3/3 |
| full-025 | resonance | 2 | vague | 0/3 | 0/3 |
| full-026 | control | 0 | vague | 3/3 | 3/3 |
| full-027 | gain | 0 | none | 0/3 | 0/3 |
| full-028 | clipping | 0 | none | 3/3 | 1/3 |
| full-029 ⁱ | polarity | 0 | vague | 3/3 | 2/3 |
| full-030 | mud | 0 | none | 0/3 | 0/3 |

ⁱ Repeats a smoke task (same song, fault, stem and size).

## Not in this run yet

The third configuration, Claude Code with flstudio-mcp (D66), isn't included. It has been ported to FL 20.9.2, but it needs a runner configuration graded from FL renders. It will be added to the same run id.

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
