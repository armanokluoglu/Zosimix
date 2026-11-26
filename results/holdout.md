# Held-out test: harness vs plain Claude Code on unseen songs (Sonnet 5.5), 2026-11-26

The final measurement after the tuning rounds (D72–D81). 30 tasks on six AlbumDB songs (03, 04, 05, 06, 07, 09) that were downloaded, turned into tasks (seed 81) and committed **before** the last round of changes, and never used for tuning (D81). One repeat per task, run `holdout-1` on commit cfabd46, with 4 workers. No run timed out or raised an integrity flag.

| | Zosimix harness | Plain Claude Code |
|---|---|---|
| **Pass rate, in scope** (D83) | **19/23 = 83%** | 13/23 = 57% |
| Pass rate, every task | 19/30 = 63% | 13/30 = 43% |
| Partial credit | 0.66 | 0.45 |
| Right fault named on the right stem | 20/30 | 15/30 |
| Runs that damaged healthy stems | 1 | 1 |
| Output tokens per task | 815 | 2,521 |
| Median time per task | 75 s | 82 s |

**Task by task:** the harness passed 6 tasks that plain Claude Code failed, and plain Claude Code passed none that the harness failed (sign test p ≈ 0.03). With one repeat a single task can swing either way, but this is the first harness-vs-plain comparison that clears the usual 5% bar. It also costs a third of the output tokens.

| Fault | Harness | Plain |
|---|---|---|
| Clipping | 5/5 | 3/5 |
| No fault (leave it alone) | 5/5 | 5/5 |
| Pan | 5/5 | 3/5 |
| Gain | 2/5 | 1/5 |
| Resonance | 2/5 | 1/5 |
| Mud | 0/5 | 0/5 |

With a vague client note, the harness passed 15/17 (plain 11/17); with no note, 4/13 (plain 2/13).

## In scope

Mud and resonance are matters of taste: the harness only treats them as faults when the client's note mentions them (D72, D73). Seven held-out tasks have such a fault and no note: all five mud tasks and two resonance tasks. Both setups answered "no fault" on all seven. Under the intended policy that's correct behaviour, so these tasks are left out of the headline rate, for both configurations (D83). With a note, the harness passed 15 of 17 tasks.

## What this does and doesn't show

- **It's the honest number.** On full-v2, whose failures guided the last rounds, the harness reached 20/30 (D78); on unseen songs it gets 19/30. The tuning generalised, rather than fitting the test.
- **No polarity tasks:** AlbumDB's drum stems can't host a polarity fault (no multi-mic drum pairs). Polarity was the harness's strong suit on full-v2 (8/15 against 5/15 for plain).
- **Mud with a note is untested here:** all five held-out mud tasks happen to have no note. On the tuning tasks given a note, the harness passed 7 of 16 (D81).
- **One repeat, one model.** flstudio-mcp wasn't run on these songs: it runs one task at a time through FL, about an hour.

## Data

The songs come from AlbumDB.

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
