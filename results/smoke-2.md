# Smoke run 2: Claude Code + Zosimix + diagnosis skill (Sonnet 5.5), 2026-11-25

This uses the same 6-task smoke set as run 1. The only change is the diagnosis skill, which is appended to the system prompt (D52). Run 1 is the `zosimix-noskill` baseline.

```
run smoke-2-skill: 6 graded runs

[zosimix] pass 4/6, detected 5/6, median 34 s, 7 turns avg, 912 output tokens avg, $0.27 API-equivalent total
  smoke-001 clipping  sev 0 hint vague PASS  verdict unfixable/unfixable detected True others -inf dB
  smoke-002 control   sev 0 hint none  PASS  verdict no_fault/no_fault detected True others -inf dB
  smoke-003 pan       sev 0 hint vague PASS  verdict fixed/fixed detected True repair 1.0 (4.25->0.0 dB balance error) others -inf dB
  smoke-004 gain      sev 1 hint vague fail  verdict fixed/fixed detected True repair 0.667 (6.0->2.0 dB level error) others -inf dB
  smoke-005 mud       sev 0 hint vague fail  verdict no_fault/fixed detected False repair 0.0 (0.76->0.76 dB band-shape error) others -inf dB
  smoke-006 polarity  sev 0 hint vague PASS  verdict fixed/fixed detected True repair 0.995 (2.59->0.01 dB drum-bus low-end error) others -inf dB
```

## Against run 1 (no skill): 3/6 → 4/6

| Task | Run 1 (no skill) | Run 2 (skill) | What changed |
|---|---|---|---|
| 001 clipping | PASS | PASS | — |
| 002 control | PASS | PASS | — |
| 003 pan on bass | fail: called the lean intentional, moved a sax | **PASS**, repair 1.0 | The skill's centre convention (bass, kick, snare and lead vocal sit in the centre) and the pan formula |
| 004 gain, bass −6 dB | fail: +8 dB, repair 0.667 | fail: +8 dB, repair 0.667 | Nothing. It matched the bass to the kick, picked +8 although it estimated a 7 dB gap, and didn't re-measure |
| 005 mud on overheads, smallest size | fail: EQ'd a guitar resonance it wrongly suspected (others −26 dB) | fail: `no_fault`, mix untouched | The restraint rules worked: no false positive. But the fault went undetected |
| 006 polarity | PASS | PASS | — |

## Reading this carefully

- **This is one run per task, so it's an anecdote, not a measurement.** The pan change is clearly caused by the skill: the agent applied the convention and the formula. Whether the overall rate really moved needs repeats, which the full run (day 11) has.
- **smoke-005 is close to undetectable.** A +3 dB broad bump on the overheads changes that stem's band shape by only 0.76 dB, and the mix's low-mid band stays inside normal variation (z +0.4). Declining is the honest answer to what it can measure. A failure on the smallest mud size is expected.
- **smoke-004 is a reference problem, not a skill problem.** Nothing tells the agent where a bass *should* sit. Measured across the 7 songs, each family's loudness relative to the whole mix varies by: bass ±3.0 dB, vocals ±1.9, guitars ±1.8, drums ±1.3. A leave-one-out "typical level for this family" reference would help with the 6 and 10 dB faults and do little for the 3 dB ones. That would be a tool change, not more wording in the skill.

## Decision

Stop tuning the skill on the smoke set here (D53). More rounds of 6 single runs would just fit the wording to these six tasks.
