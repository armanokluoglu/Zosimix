# Smoke run 3: skill + per-family level reference (Sonnet 5.5), 2026-11-25

This is the same setup as run 2, plus a `level_balance` tool. It shows each instrument family's loudness relative to the mix, compared with a leave-one-out "typical" value from the other 6 songs (D54, proposed).

```
run smoke-3-levels: 6 graded runs

[zosimix] pass 4/6, detected 5/6, median 37 s, 7 turns avg, 937 output tokens avg, $0.27 API-equivalent total
  smoke-001 clipping  sev 0 hint vague PASS  verdict unfixable/unfixable detected True others -inf dB
  smoke-002 control   sev 0 hint none  PASS  verdict no_fault/no_fault detected True others -inf dB
  smoke-003 pan       sev 0 hint vague PASS  verdict fixed/fixed detected True repair 1.0 (4.25->0.0 dB balance error) others -inf dB
  smoke-004 gain      sev 1 hint vague fail  verdict fixed/fixed detected True repair 0.333 (6.0->4.0 dB level error) others -inf dB
  smoke-005 mud       sev 0 hint vague fail  verdict no_fault/fixed detected False repair 0.0 (0.76->0.76 dB band-shape error) others -inf dB
  smoke-006 polarity  sev 0 hint vague PASS  verdict fixed/fixed detected True repair 0.995 (2.59->0.01 dB drum-bus low-end error) others -inf dB
```

## The gain task got worse: repair 0.667 → 0.333

On smoke-004 the bass is 6 dB too quiet. The agent used the new tool exactly as intended. It saw the bass at z −4.8, aimed for "typical", deliberately stopped short (+10 dB instead of the full gap of about 11.6), re-checked, and correctly left the slightly quiet guitars alone. It still overshot by 4 dB.

The cause is the reference, not the agent. In this song, even the *clean* bass sits 11.8 LU under the mix, far below the other songs' −6.0 ± 2.4. The intended mix is just unusual, so "typical" points to the wrong place.

## Checked offline across all 7 songs (31 song/family pairs, no agent runs)

- **How far "typical" is from each song's true level:** median 1.8 dB, maximum 7.3 dB.
- **If an agent aimed exactly at "typical", it would pass a gain task** (residual error within 30% of the fault) in this share of pairs:
  - 3 dB faults: 16%
  - 6 dB faults: 55%
  - 10 dB faults: 74%
- **False alarms:** 4 of the 31 *clean* family levels already show as outliers (|z| > 2). On a control task, that tempts the agent into a level "fix".

With only 6 reference songs, the per-family level reference is weak evidence. It helps with the largest gain faults, misleads on unusual mixes like this one, and adds a false-alarm risk.

## Decision

Removed (D54). The tool, its skill guidance and its target data are not in the codebase. The `zosimix` configuration is back to the run 2 setup.
