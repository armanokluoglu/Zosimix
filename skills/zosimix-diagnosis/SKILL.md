---
name: zosimix-diagnosis
description: Playbook for diagnosing and repairing a multitrack mix with the Zosimix MCP tools when you cannot listen. Use whenever the zosimix tools are available and a mix needs checking or fixing.
---

# Diagnosing a mix you cannot hear

You are standing in for a mix engineer. Your job is to find what is genuinely wrong, fix it with the smallest change, and leave everything else exactly as it is. A healthy mix that you change is a mix you damaged.

## Workflow

1. Read the brief and any client note. A note points at a symptom and an instrument family, never at a file. Treat it as a lead to verify, not as a fact.
2. Call `overview` once, plus `tonal_balance` for the whole mix.
3. Make a short list of suspects. Use the symptom table below and look for stems that stand out from their peers.
4. Investigate each suspect with the tool that measures that problem. Look for evidence from at least two directions, for example a stem's own numbers plus how it compares with its peers or with the target.
5. If the evidence is clear, make the fix, `commit_changes`, and read the report. If the report says the wrong thing moved, or nothing moved, undo the change or adjust it.
6. Re-measure the thing you fixed, with the same tool that found it.
7. Call `submit_diagnosis` once, with honest confidences.

## Symptom → where to look

| Client says | Most likely | Check with |
|---|---|---|
| "too loud" / "can barely hear X" | level of a stem in that family | overview LUFS vs peers, MIX `tonal_balance` |
| "lopsided", "leans to one side" | pan of a stem that belongs in the centre | overview bal(R−L) and corr |
| "thin", "lacks punch" (drums) | polarity of one drum mic | `phase` |
| "muddy", "boxy" | broad low-mid excess (about 150–500 Hz) | MIX and per-stem `tonal_balance`, overview lmid share |
| "harsh", "ringy", "whistling" | a narrow resonance | `spectrum` on the family's stems |
| "distorted", "crunchy" | clipping baked into a recording | overview clips/min |
| "check it over" | possibly nothing | everything, with a high bar |

With no note, run through all of these anyway. Polarity (`phase`) and clipping (clips/min) are cheap to rule out, so always rule them out.

## Fault versus artistic choice

- **These almost always sit in the centre:** bass, kick, snare, and the lead vocal. If one of them is mono or nearly mono (corr above about 0.95) and its balance is more than about 1 dB off centre, it is very likely a pan fault, even if the lean looks deliberate.
- **These are often off-centre on purpose:** guitars, keys, backing vocals, percussion, horns, strings, effects, and room or overhead mics. Leave their placement alone. The exception is a stem named as one half of a pair (`_l`/`_r`, `_1`/`_2`): if one half is badly out of line with the other, that one is the suspect.
- **Real mixes don't match the target exactly.** In `tonal_balance`, a z-score within ±2 is normal variety. A single stem's band at about ±2.5 is still common. Look for a clear outlier that the rest of the evidence agrees with.
- **Natural resonances exist.** Guitar bodies, drum shells and vocal formants show up as persistent bumps in clean recordings. A bump is a fault only if it is clearly stronger than the stem's other bumps, and it lines up with the symptom or an outlying band.

## Fixing each kind of problem

- **Level.** First decide where the stem *should* sit. Compare it with its peers in the song (the other guitars, the other vocals, the other drum mics). Also check whether the MIX band it dominates is off target in `tonal_balance`. Move it in one step towards that point, then check again. When you are unsure between two amounts, choose the smaller: overshooting is as wrong as undershooting.
- **Pan.** `set_pan` is a balance control. To bring a stem whose balance (R−L) is *b* dB back to the centre, use `pan = (4/π)·atan(10^(−b/20)) − 1`. For example, b = −4.3 gives pan ≈ +0.30. Re-centring with a balance control also lowers the stem's level, so after committing, raise its gain until its LUFS is back to what it was before the pan move.
- **Polarity.** In `phase`, a drum stem with negative low-end correlation and a clearly positive flip value (about +1 dB or more) is fighting the rest of the kit. Invert that one stem. If both mics of a pair show it, invert the one with the larger flip value. A small flip value means leave it alone: some mics, such as a snare bottom mic, are naturally opposed.
- **Resonance.** Cut with one peaking band at the bump's frequency. Use the reported Q (or a little wider), and set the cut to about the reported excess. Afterwards, check `spectrum` again: the bump should be gone or much smaller, and nothing else should have changed.
- **Mud.** Find which stem carries the excess: compare `tonal_balance` per stem for the lowmid band. Cut that stem with one wide peaking band (Q around 1) at the centre of its excess, by roughly the excess in dB. Then confirm that the band moves towards the target.
- **Clipping.** A stem with many flat-topped runs per minute, while comparable stems show almost none, has clipping baked into the recording. No fader or EQ can restore the missing peaks, so turning it down only hides the problem. Submit verdict `unfixable` with a clipping finding on that stem, and change nothing.

## Restraint rules

- Only change the stems you diagnosed. Never "fix" one stem by moving all the others.
- One clear problem with a clean fix beats several speculative ones. Every extra change risks damaging a healthy part of the mix.
- If your best evidence is weak, don't change anything. If nothing clearly stands out after checking everything, the right answer is `no_fault` with no findings. A request to "check it over" is not evidence that something is wrong.
- Confidence means how sure you are. Below about 0.6, don't act on a finding: keep looking for evidence, or leave it out.
