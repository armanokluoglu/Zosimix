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

## Round 2: mud and resonance, a grader fix, faster runs (D73)

Done afterwards on the owner's go-ahead: apply the resonance gate, look for bigger gains on mud and resonance, and don't rerun the test tasks yet. Everything below was tuned and checked on the dev songs only, so **the current harness has no new test-set numbers.**

### What changed

| Change | Why (dev songs, injected faults, no agent) |
|---|---|
| A resonance counts as a fault only with a harsh, ringy or whistling note | Some stem always has the biggest bump in a clean mix; the D72 regression cut one. |
| `scan peaks` ranks a stem's bump by its height × the stem's share of the MIX's energy around it | Faulty stem ranked first in 24/24, against 12% by raw height and 67% by lead over the stem's next bump. A tom's natural bump under loud guitars isn't what makes a mix ring. |
| Resonance cuts at Q 8 | Median repair 0.89, against 0.76 with the reported Q. |
| `scan lowmid` ranks stems by their share of the MIX's low-mid energy × their low-mid z | Faulty stem ranked first in 24/24, against 21% by the stem's own shape. |
| The suggested mud cut sits on the stem's broad low-mid bump, at twice the bump's height | 58% repair pass given the right stem, against 44% for "cut at 300 Hz to typical". |

**Caveat on both 24/24 results:** the benchmark sizes mud and resonance by their effect on the mix (D69). So the stems that can carry those faults are the ones already strong in that band, and that makes mix-share rankings look as good as they do here. "Which track fills the mix in this band?" is how an engineer starts looking, but on real mixes it won't be perfect.

### The grader fix (eval-integrity change)

Mud and resonance repair is now measured as the band's level against the rest of the stem, not as its share of the stem's energy. A share flattens out on stems the band already dominates. On a snare, a 10 dB mud boost moved it by only 0.1 dB, so any slightly imperfect cut scored as damage. On all 15 mud and resonance tasks (full-v2 and dev):

- an exact undo still scores 1.00;
- half an undo scores 0.51–0.61 and fails;
- doing nothing fails.

Every stored answer was regraded into a separate `regraded.jsonl`, and the original grades stay in `results.jsonl`. Only mud and resonance rows changed:

- plain gains 2 resonance passes on full-2;
- the revised harness gains 1 on full-3-targeted;
- full-1's passes are unchanged.

flstudio-mcp can't be regraded, because its FL renders weren't kept; its mud and resonance repairs were all near zero, so its pass counts can't change.

With the regraded grades, full-v2 stands at:

| | Harness as on full-v2 | Harness v2 (D72) | Plain | flstudio-mcp |
|---|---|---|---|---|
| Pass rate | 46/90 = 51% | 45/90 = 50% | 33/90 = 37% | 12/90 = 13% |
| Partial credit | 0.54 | 0.51 | 0.40 | 0.14 |

### The current harness on the dev set

| Dev run (regraded) | Pass | Partial credit | Mud | Resonance | Controls |
|---|---|---|---|---|---|
| Before any changes (1 repeat) | 8/18 = 44% | 0.51 | 0/3 | 0/3 | 3/3 |
| **Current harness** (2 repeats) | **23/36 = 64%** | **0.64** | **4/6** | **4/6** | 6/6 |

Mud and resonance both went from 0 to two thirds, with no false alarms on the healthy mixes. The remaining misses:

- **Resonance on a lead vocal:** a moving pitch hides a fixed boost from the detector, which reports +0.6 dB for an 11.7 dB boost.
- **Mud on a snare:** the stem is found, but the cut doesn't repair it.
- **Gain:** still 0 without a reference mix.
- **Pan:** varies from run to run.

The next step is the targeted test rerun (resonance, mud and controls), held until the owner says so.

### Faster runs

Most of a run's time is the agent itself (about 35 s); building the workspace and grading take about 6 s. The runner now takes `--workers N` and runs several tasks at once (flstudio-mcp stays at 1, since there's one FL). The 36-run dev check took 12 minutes with 4 workers, about half the time one at a time. Each run took longer when four ran together, because their measurement servers competed for cores. So each server's threads are now capped at its share of the cores.

## Round 3: triage, mistaken pans, twin levels (D74)

Before the test rerun, the owner asked to dig deeper. Again everything was tuned and checked on the dev songs only, so **there are no new test-set numbers.**

- **`triage`**: one call that runs every objective check: clipping, drum polarity, mistaken pans and twin levels, plus the top mud and resonance suspects. The skill starts every task with it. On full-v2 the harness failed both polarity tasks that had no client note, while passing the ones with a note. The phase tool already points at the right mic (oracle 5/5), so the check now always runs, and a clear flip is acted on without a note.
- **Mistaken pan = mono, off centre, no twin.** A pan fault leaves a stem exactly mono at unequal levels. Parts panned on purpose in these songs are stereo or come as `_l`/`_r` pairs. On injected dev faults the faulty stem was the only suspect in 24/24, and nothing was flagged in either clean mix. This replaces the "mix leans" gate, which caught only about half of the pan faults.
- **Twin levels.** `_l`/`_r` twins more than 5 LU apart; clean twins in the dev songs sit within 4 LU. Without a note, the twin further from its family's typical level is the faulty one 71% of the time. The skill acts with a level note, or without one when the gap is 8 LU or more.
- **4× faster polarity check:** the lag search runs on every 10th sample of the low-passed signals, 21.4 s → 4.9 s, with identical results. The flip value the grader uses doesn't change.
- **Polarity can't be tuned on dev:** every polarity-capable mic setup in our songs is already used by a test task, and AlbumDB has no multi-mic drums. The smoke polarity task passed 3/3, a sanity check only.

| Dev set (regraded) | Pass | Partial | Mud | Resonance | Pan | Control | Clipping | Gain |
|---|---|---|---|---|---|---|---|---|
| Before D72 (1 repeat) | 8/18 = 44% | 0.51 | 0/3 | 0/3 | 2/3 | 3/3 | 3/3 | 0/3 |
| After D73 (2 repeats) | 23/36 = 64% | 0.64 | 4/6 | 4/6 | 3/6 | 6/6 | 6/6 | 0/6 |
| **After D74 (2 repeats)** | **25/36 = 69%** | **0.70** | 3/6 | 4/6 | **6/6** | 6/6 | 6/6 | 0/6 |

Without the dev set's three gain tasks, which need a reference mix, the current harness passes 25/30 = 83% on dev. Mud is 3/6 against 4/6 in round 2. Both rounds miss the same snare task every time, and the other two mud tasks pass most runs, so the difference is within run-to-run noise at 2 repeats. What's still out of reach, and why:

| Weak spot | Why |
|---|---|
| Gain without a level note | Nothing in the stems says where a stem should sit; only twin pairs give a reference. |
| Mud on a snare | The snare's natural low-mid hump hides where the boost is centred. Finer per-family profiles could fix this. |
| Resonance on a lead vocal | A moving pitch hides a fixed boost from the detector. |

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
