# Blind listening check (the builder, 2026-11-26)

One listener, blind A/B, 12 s loudness-matched clips from AlbumDB songs (DESIGN.md §4.9, D75).
A sanity check of whether the graders agree with ears, not a study.

| Pair | What was heard | Expected if the graders are right |
|---|---|---|
| Same clip twice (control) | 'no difference' 3/3 | all 'no difference' |
| Clean vs badly broken (control) | clean preferred 3/3 | clean every time |
| Passed repair vs broken | repaired preferred 4/6, no difference 1/6 | repaired mostly |
| Failed repair vs broken | repaired preferred 3/6, no difference 1/6 | repaired less often than above |
| Clean vs passed repair | 'no difference' 6/6, clean 0/6, repaired 0/6 | hard to tell apart |

## What it says

- **The listener was consistent.** Identical clips were heard as identical (3/3), and clean beat a badly broken mix every time (3/3). So the differences heard elsewhere weren't imagined.
- **Repairs the grader passes sound like the original mix.** In 6 of 6 clean-vs-passed-repair pairs the listener heard no difference. This is the direct test of "do the metrics agree with ears", and they did.
- **Passed repairs mostly sounded better than the broken mix** (4 of 6; one no difference, on a 0.6 pan of a bass; one preferred broken).
- **A failed repair can still sound better.** A failed repair was preferred over the broken mix 3 times in 6. One was a genuine partial fix (a 10 dB gain fault, 60% repaired; the pass line is 70%). The other two were mud tasks where the agent's low-mid cut barely touched the faulty stem (repair 0.06 and 0.0), yet the mix sounded better: on a muddy mix, cutting low-mids almost anywhere makes the whole mix less muddy. The ear judges the mix, while the grader asks whether the faulty stem itself was restored and nothing else was changed. That difference is by design: a fix on the wrong stem changes the engineer's balance elsewhere.
- **"Better" isn't the same as "restored".** In both pairs on dev-016, a 5 kHz ring added to a snare, the broken version was preferred, both over a passed repair and over a failed one. A boosted top end can sound brighter and more exciting over 12 seconds. The page asked which sounds *better*; the grader measures how close the mix is to the engineer's original. The clean-vs-repair pairs are the ones that line up with what the grader measures, and those agreed 6 of 6.

## Limits

One listener (the builder), 24 trials, one session, laptop and headphone listening, 12-second excerpts. The listener reported that most differences were hard to judge. This is a sanity check that the metrics don't contradict ears, not a measurement of how audible each fault is. A second listener, and a question closer to the grader ("which is closer to the reference?" with the clean mix as a known reference), would make it stronger.

## Every trial

| # | Pair | Fault (task) | Grader | Heard as better |
|---|---|---|---|---|
| 1 | passed repair vs broken | mud, severity 1 (dev-014) | pass | repaired |
| 2 | passed repair vs broken | resonance, severity 1 (dev-016) | pass | broken |
| 3 | clean vs passed repair | pan, severity 2 (dev-003) | pass | no difference |
| 4 | same clip twice | gain, severity 2 (full-020) | pass | no difference |
| 5 | passed repair vs broken | pan, severity 2 (dev-003) | pass | repaired |
| 6 | failed repair vs broken | gain, severity 2 (full-020) | fail | repaired |
| 7 | clean vs passed repair | mud, severity 2 (dev-002) | pass | no difference |
| 8 | failed repair vs broken | pan, severity 0 (full-010) | fail | broken |
| 9 | failed repair vs broken | resonance, severity 1 (dev-016) | fail | broken |
| 10 | clean vs passed repair | pan, severity 1 (dev-015) | pass | no difference |
| 11 | failed repair vs broken | mud, severity 0 (dev-008) | fail | repaired |
| 12 | clean vs broken | gain, severity 2 (full-020) | fail | clean |
| 13 | clean vs passed repair | resonance, severity 2 (full-v2-025) | pass | no difference |
| 14 | passed repair vs broken | mud, severity 2 (dev-002) | pass | repaired |
| 15 | failed repair vs broken | mud, severity 2 (dev-002) | fail | repaired |
| 16 | clean vs passed repair | resonance, severity 1 (dev-016) | pass | no difference |
| 17 | clean vs broken | mud, severity 2 (full-v2-002) | fail | clean |
| 18 | clean vs broken | pan, severity 2 (dev-003) | pass | clean |
| 19 | passed repair vs broken | gain, severity 2 (full-020) | pass | repaired |
| 20 | clean vs passed repair | mud, severity 1 (dev-014) | pass | no difference |
| 21 | passed repair vs broken | pan, severity 1 (dev-015) | pass | no difference |
| 22 | same clip twice | mud, severity 2 (dev-002) | pass | no difference |
| 23 | failed repair vs broken | resonance, severity 2 (dev-004) | fail | no difference |
| 24 | same clip twice | pan, severity 0 (dev-009) | pass | no difference |

Clips, key and page: `C:\zosimix\listening\session-1` (not in git). Rebuild with `python -m zosimix.listening build --out <dir>` (seed 75).

## Data

The clips come from AlbumDB.

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
