# Held-out test: harness vs plain Claude Code on unseen songs (Sonnet 5.5), 2026-11-27

The final measurement after the tuning rounds (D72–D81). 30 tasks on six AlbumDB songs (03, 04, 05, 06, 07, 09) that were downloaded, turned into tasks (seed 81) and committed **before** the last round of changes, and never used for tuning (D81). **Three repeats** per task, run `holdout-1`. Repeat 1 ran on commit cfabd46, repeats 2–3 on 9fda067: same harness, with a faster polarity check that shows the agent identical numbers, and readable tool error messages (D84, D85). Four workers; no timeouts, no integrity flags.

| | Zosimix harness | Plain Claude Code |
|---|---|---|
| **Pass rate, in scope** (D83) | **56/69 = 81%** (95% interval 70–89%) | 37/69 = 54% (42–65%) |
| Pass rate, every task | 56/90 = 62% | 37/90 = 41% |
| In scope, per repeat | 19, 19, 18 | 13, 12, 12 |
| Partial credit (in scope) | 0.84 | 0.55 |
| Output tokens per task | 812 | 2,482 |
| Median time per task | 46 s | 81 s |

**Task by task** (passes out of 3, in-scope tasks): the harness did better on 10 tasks and worse on 2, with 11 tied (sign test p ≈ 0.04). The intervals are Wilson intervals over runs. They overstate certainty a little, because repeats of one task are correlated; the task-by-task test doesn't have that problem.

| Fault (in scope) | Harness | Plain |
|---|---|---|
| Clipping | 15/15 | 10/15 |
| No fault (leave it alone) | 15/15 | 12/15 |
| Pan | 14/15 | 10/15 |
| Resonance (with a note) | 6/9 | 1/9 |
| Gain | 6/15 | 4/15 |

With a vague client note, the harness passed 45/51 runs (plain 31/51); with no note, 11/39 (plain 6/39).

## In scope

Mud and resonance are matters of taste: the harness only treats them as faults when the client's note mentions them (D72, D73). Seven held-out tasks have such a fault and no note: all five mud tasks and two resonance tasks. Under the intended policy, leaving them alone is correct, so they're left out of the headline rate, for both configurations alike (D83). The every-task rate is given beside it.

## What this does and doesn't show

- **The tuning generalised.** On full-v2, whose failures guided the last rounds, the revised harness reached 20/30 on one repeat (D78). On unseen songs it holds about 81% in scope over three repeats, with the three repeats agreeing within one task.
- **It's cheaper and faster:** a third of the output tokens, and a median run time of 46 s against 81 s.
- **No polarity tasks:** AlbumDB's drum stems can't host a polarity fault (no multi-mic drum pairs). Polarity was the harness's strong suit on full-v2.
- **Mud with a note is untested here:** all five held-out mud tasks happen to have no note. On the tuning tasks given a note, the harness passed 7 of 16 (D81).
- **Gain is the weakest scored category** (6/15). Without a level note or an L/R twin, nothing in the stems says where a track should sit.
- **flstudio-mcp wasn't run on these songs.** They have 29–35 stems and the FL template has 24 slots (D85); the owner chose not to build a larger one. Its full-v2 result stands: 15% in scope over 3 repeats.

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
