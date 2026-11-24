# Smoke run 1: Claude Code + Zosimix (Sonnet 5.5), 2026-11-24

First real run of the 6-task smoke set (tasks/smoke.json, seed 7). The agent skill (day 8) did not exist yet.

```
run smoke-1: 6 graded runs

[zosimix] pass 3/6, detected 4/6, median 33 s, 8 turns avg, 1239 output tokens avg, $0.24 API-equivalent total
  smoke-001 clipping  sev 0 hint vague PASS  verdict unfixable/unfixable detected True others -inf dB
  smoke-002 control   sev 0 hint none  PASS  verdict no_fault/no_fault detected True others -inf dB
  smoke-003 pan       sev 0 hint vague fail  verdict fixed/fixed detected False repair 0.0 (4.25->4.25 dB balance error) others -18.5 dB
  smoke-004 gain      sev 1 hint vague fail  verdict fixed/fixed detected True repair 0.667 (6.0->2.0 dB level error) others -inf dB
  smoke-005 mud       sev 0 hint vague fail  verdict fixed/fixed detected False repair 0.0 (0.76->0.76 dB band-shape error) others -26.2 dB
  smoke-006 polarity  sev 0 hint vague PASS  verdict fixed/fixed detected True repair 0.995 (2.59->0.01 dB drum-bus low-end error) others -inf dB
```

## What the failures say

- **smoke-003 (pan on bass, subtle):** the agent saw the bass leaning left (−4.3 dB) but treated it as intentional, then "fixed" a sax that sits right naturally. The missing knowledge is a mixing convention: bass, kick and lead vocal belong in the centre. The diagnosis skill (day 8) should teach it.
- **smoke-004 (bass −6 dB):** correct diagnosis, but it overshot (+8 dB). Repair score 0.667, just under the 0.7 pass line. Without a reference, level is a judgment call.
- **smoke-005 (mud +3 dB on overheads, subtlest size):** it went after a natural 732 Hz guitar resonance instead, a false positive, and changed the mix at only 0.5 confidence. This is the resonance ambiguity from D44, plus a restraint problem.
