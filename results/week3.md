# Week 3: the revised harness on the test set, two ablations, a pan fix that didn't work (Sonnet 5.5), 2026-11-26

All runs are 1 repeat of the 30 full-v2 tasks, run with 4 workers. With one repeat, a difference of a few tasks is within noise. Every task-by-task comparison below gives its sign test.

## 1. The revised harness on the test set

The harness after D72–D74 (`triage`, mix-aware `scan`, resonance and mud gated on a client note, the mistaken-pan check, the twin-level check), run `full-4-r1` on commit 2fe81d2:

| | Pass | Partial credit |
|---|---|---|
| Harness as on full-v2, repeat 1 | 15/30 | – |
| Harness as on full-v2, all 3 repeats | 46/90 = 51% | 0.54 |
| **Revised harness (1 repeat)** | **20/30 = 67%** | **0.69** |

By fault type: clipping 4/4, resonance 4/4, pan 4/4, polarity 4/5, control 2/4, gain 1/4, mud 1/5. No integrity flags.

Four of the ten failures share one cause. In one test song (juniper-triangles), the toms and an acoustic guitar are mono, panned on purpose, and have no twin. That is the same signature as the mistaken pan the new check looks for, and the dev songs had no such stems. The agent "re-centred" them on both healthy controls, on a mud task, and on a polarity task whose polarity it had fixed perfectly (repair 0.98).

## 2. Two ablations (DESIGN.md §5)

Each is the revised harness with one change, compared task by task with `full-4-r1`:

| Configuration | Pass | Partial credit | Output tokens per task | vs the revised harness |
|---|---|---|---|---|
| Revised harness | 20/30 | 0.69 | 1,015 | – |
| Without `triage` and `scan` | 17/30 | 0.58 | 1,212 | better on 1 task, worse on 4 (p ≈ 0.38) |
| With the spectrogram picture tool | 20/30 | 0.69 | 1,019 | identical on every task |

- **`triage` and `scan` help, but one repeat can't prove it.** Without them the agent lost a task each in mud, polarity, pan and resonance, gained one in gain, and used about 20% more tokens.
- **The spectrogram ablation measured nothing.** The agent never called the tool, in 0 of 30 runs. The skill describes a workflow without it, and the agent follows the skill. The tool itself works: on a snare with an injected 5 kHz ring it shows a bright horizontal line through every hit. A fair test needs the skill to say when to look at the picture.
- The skill, verification and tonal-target ablations were cut to save usage. Their first 5 tasks are in run `ablations-r1`.

## 3. A pan fix found on the test set (D79), and why it failed

The obvious fix for section 1 was to act on a pan suspect without a client note only when the stem belongs in the centre (bass, kick, snare, lead vocal), or when the whole mix leans its way. On the dev songs, clean mixes balance within 0.13 dB. Because it came from a test-set failure, it was labelled test-informed. Run `full-5-r1`:

| Pan rule | Pass | Pan faults fixed | Healthy mixes left alone |
|---|---|---|---|
| Signature only (D74, tuned on dev) | **20/30** | 4/4 | 2/4 |
| Centre stem or leaning mix (D79) | 18/30 | 1/4 | 2/4 |

It fixed the polarity task, now free of stray pan changes. But the controls still failed: this song's clean mix leans 0.6 dB toward its deliberately panned toms, so "the mix leans this way" fired anyway. And three real pan faults with no note (a backing vocal, an effects track, another non-centre stem) were now left alone.

**The lesson:** from the audio alone, a mono part panned on purpose and one panned by mistake can look identical. Neither rule separates them. Without a client note, a pan fault on a stem that could reasonably sit off centre is a judgement call, as it would be for a human engineer handed only the stems. The benchmark treats every such move as a fault, because the generator only pans stems that were centred in the original.

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
