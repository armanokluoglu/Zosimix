# Improving the harness: oracle, dev set, targeted rerun (Sonnet 5.5), 2026-11-26

After full-v2 (harness 51%, plain Claude Code 34%, flstudio-mcp 13%; [full-v2.md](full-v2.md)) the question was how to raise the scores honestly. The rule throughout: **tune only on a separate development set, then measure once on the test set.** `full-v2` stays the test set. To keep it fast, the test-set measurement reran only the 17 tasks the changes target, not all 30 (D72).

**Result in one line:** resonance doubled (4/12 → 8/12), but `scan` surfaced a natural resonance on one test song's healthy guitar, and the agent cut it on both controls from that song (6/6 runs). Overall the harness went from 46/90 to 44/90. Opus 5.5 does no better than Sonnet 5.5 on the same tasks.

## 1. Oracle check: can the measurements find the fault at all?

`python -m zosimix.oracle --set full-v2` scores every stem of each faulty song on the measurement that fits the task's fault, and reports the faulty stem's rank. No agent runs. Rank 1 means a perfect reader of that measurement would single out the right stem.

| Fault | Ranked 1st | In top 3 | Harness pass rate (full-v2) | What it means |
|---|---|---|---|---|
| Clipping | 4/4 | 4/4 | 12/12 | Measurement and agent both work. |
| Polarity | 5/5 | 5/5 | 8/15 | The phase tool points at the right mic every time; the agent doesn't always act on it. |
| Pan | 3/4 | 4/4 | 6/12 | Mostly visible; the agent dismisses some leans as artistic. |
| Mud | 3/5 | 3/5 | 0/15 | Often visible, but under-cut or not acted on. |
| Resonance | 0/4 | 2/4 | 4/12 | The detector is weak across all stems; usable within the hinted family. |
| Gain (level vs typical) | 0/4 | 0/4 | 4/12 | **A real ceiling.** Without a reference mix even a 10 dB level fault doesn't stand out; the harness's gain passes come from the hint. |

## 2. Development set

Two more AlbumDB songs ("No More Mr Nice Guy", "An Evening To Myself"; 25 and 23 stems), kept in `data/dev_songs`, apart from the benchmark's songs so the tonal targets the harness shows on test tasks don't change. `tasks/dev.json` has 18 tasks: 3 each of gain, resonance, mud, pan, clipping and control. These songs have no drum mics that qualify for a polarity fault, so there are no polarity tasks.

What the dev songs showed, by injecting many faults and checking candidate measurements without agent runs:

- **Resonance depth.** The skill said to cut by "about the reported excess". The detector reports about half the real boost, so given the right stem that policy passes 11% of the time. Cutting **twice** the reported height passes 78%. The detector's top bump is the injected one 94% of the time, so finding the frequency isn't the problem.
- **A centre-excluded detector**, which I had suspected would help, is clearly worse (0% ranked first, against 17%), so the detector is unchanged.
- **Mud is hard by nature.** Even given the right stem, the best reference-free policy, cutting at 300 Hz until the stem looks typical for its family, passes about 44%. Cutting the exact boost at the wrong centre frequency passes only half the time.
- **Pan.** Near-mono stems sit off centre on purpose in clean songs (toms +7 dB, an acoustic guitar +4 dB), but the clean mixes as a whole balance within 0.13 dB. A pan fault makes the whole mix lean.

## 3. What changed in the harness

- **New tool `scan`** ranks every stem, or one family's, on one measure in a single call:
  - **`peaks`** gives each stem's strongest persistent bump.
  - **`lowmid`** gives each stem's low-mid excess over its family's typical value, measured against the rest of the stem so it doesn't flatten out, plus the 300 Hz cut that would bring the top suspects back to typical.
- **Skill changes:**
  - cut a resonance by about twice the reported height;
  - use `scan` for mud and resonance;
  - only look for a pan fault when the MIX leans or the client says the image is lopsided;
  - only treat mud as a fault when the client says the mix is muddy.
- **Partial credit** in every report. A pass counts 1, a correct but incomplete repair counts its repair score, and anything else counts 0.

The last two skill rules came from the first dev rerun, where earlier, looser versions fired on healthy stems. Dev results, one repeat each:

| Dev run | Pass | Partial credit |
|---|---|---|
| Before (harness as on full-v2) | 8/18 | 0.50 |
| First version of the changes | 6/18 | 0.33 |
| Final version (pan and mud gated) | **10/18** | **0.56** |

## 4. Targeted rerun on the test set

The 17 full-v2 tasks the changes target were rerun with the harness, 3 repeats each: resonance, mud, pan, and the four no-fault controls to catch new false alarms. No run timed out or raised an integrity flag. The other 13 tasks (clipping, gain, polarity) keep their earlier harness results, and plain and flstudio-mcp are unchanged.

| Targeted task | Fault | Before (of 3) | After (of 3) |
|---|---|---|---|
| full-v2-004 | resonance | 0 | **2** |
| full-v2-018 | resonance | 1 | **3** |
| full-v2-025 | resonance | 3 | 3 |
| full-v2-011 | resonance (smallest) | 0 | 0 |
| full-v2-003, -024 | pan | 3, 3 | 3, 3 |
| full-v2-010, -017 | pan (smaller) | 0, 0 | 0, 0 |
| all 5 | mud | 0 | 0 |
| full-v2-005, -012 | control | 3, 3 | 3, 3 |
| full-v2-019, -026 | control | 3, 3 | **0, 0** |

**The regression:** -019 and -026 are healthy mixes of the same song. Its clean electric guitar has a natural, steady bump at 732 Hz, 8.5 dB high and well above its other bumps. `scan peaks` puts it at the top, and the agent cut it 14–16 dB as a "resonance" in all 6 runs. It's the same trap the dev set showed for mud, where some stem always leads the ranking. The dev songs happen to have no such standout bump on a healthy stem, so the dev controls didn't catch it.

### Whole set, with the revised harness

| | Harness before | Harness after | Plain | flstudio-mcp |
|---|---|---|---|---|
| Pass rate | 46/90 = 51% | 44/90 = 49% | 31/90 = 34% | 12/90 = 13% |
| Partial credit | 0.53 | 0.50 | 0.39 | 0.14 |
| Resonance | 4/12 | **8/12** | 4/12 | 0/12 |
| Control | 12/12 | **6/12** | 11/12 | 10/12 |

By task, the revised harness against plain is 12 better and 4 worse (sign test p ≈ 0.077), and against flstudio-mcp 15 to 2 (p ≈ 0.002). Against the harness before the changes it's 2 better and 2 worse.

## 5. Opus 5.5 on the same harness

The harness as it ran on full-v2 (before the changes), with `claude-opus-5-5`, on 12 test tasks (two per fault type, one repeat):

| | Pass | Partial credit |
|---|---|---|
| Opus 5.5 | 7/12 = 58% | 0.61 |
| Sonnet 5.5, same tasks (3 repeats) | 21/36 = 58% | 0.62 |

The two models score the same, and Opus took more turns. A stronger model doesn't lift these scores; the measurements and how they're presented do.

## What would help next

- **Gate resonance on a symptom.** Only treat a resonance as a fault when the client mentions harshness or ringing, like mud. Every resonance task in the benchmark carries such a note, so on these tasks this would most likely keep the resonance gains and undo the control regression. But this regression was found on the test set, so a rerun after that fix is no longer a clean held-out measurement and would have to be reported as such. Alternatively, find a dev song with a natural standout bump to validate the fix first.
- **Gain** without a reference mix is at its ceiling. A level reference was tried and removed (D54); a per-song reference, such as a rough mix, would change what the benchmark asks.
- **Mud** has a real but low ceiling (about 44% even given the right stem). The agents also pick the wrong stem when another stem is naturally low-mid heavy.
- **Polarity and pan:** the measurements already point at the right stem (oracle 5/5 and 3/4). What's left is the agent acting on them consistently. That needs dev tasks with polarity faults, so dev songs with multi-mic drums.

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
