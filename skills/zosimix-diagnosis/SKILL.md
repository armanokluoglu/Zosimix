---
name: zosimix-diagnosis
description: Playbook for diagnosing and repairing a multitrack mix with the Zosimix MCP tools when you cannot listen. Use whenever the zosimix tools are available and a mix needs checking or fixing.
---

# Diagnosing a mix you cannot hear

You are standing in for a mix engineer. Your job is to find what is genuinely wrong, fix it with the smallest change, and leave everything else exactly as it is. A healthy mix that you change is a mix you damaged.

## Workflow

1. Read the brief and any client note. A note points at a symptom and an instrument family, never at a file. Treat it as a lead to verify, not as a fact.
2. Call `triage` first: it runs every objective check at once. Then `overview` once, plus `tonal_balance` for the whole mix.
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
| "muddy", "boxy" | broad low-mid excess (about 150–500 Hz) | `scan` with measure "lowmid" |
| "harsh", "ringy", "whistling" | a narrow resonance | `scan` with measure "peaks" and the family named in the note |
| "distorted", "crunchy" | clipping baked into a recording | overview clips/min |
| "check it over" | possibly nothing | everything, with a high bar |

With no note, run through all of these anyway. Polarity (`phase`) and clipping (clips/min) are cheap to rule out, so always rule them out. `scan` checks every stem for mud or a resonance in one call; don't stop after spot-checking two or three stems.

## Fault versus artistic choice

- **These almost always sit in the centre:** bass, kick, snare, and the lead vocal. If one of them is mono or nearly mono (corr above about 0.95) and its balance is more than about 1 dB off centre, it is very likely a pan fault, even if the lean looks deliberate.
- **These are often off-centre on purpose:** guitars, keys, backing vocals, percussion, horns, strings, effects, and room or overhead mics. Leave their placement alone. The exception is a stem named as one half of a pair (`_l`/`_r`, `_1`/`_2`): if one half is badly out of line with the other, that one is the suspect.
- **A mono stem off centre with no twin is a mistaken pan.** A stem whose two channels are the same signal (corr 0.99 or more) but sit at different levels, with no `_l`/`_r` partner, was panned by mistake: parts panned on purpose are stereo or come in pairs. `triage` and `scan` "pan" list exactly these. Re-centre such a stem even without a note, using the pan value they give. Leave every other stem's placement alone.
- **Real mixes don't match the target exactly.** In `tonal_balance`, a z-score within ±2 is normal variety. A single stem's band at about ±2.5 is still common. Look for a clear outlier that the rest of the evidence agrees with.
- **Natural resonances exist.** Guitar bodies, drum shells and vocal formants show up as persistent bumps in clean recordings. A bump is a fault only if it is clearly stronger than the stem's other bumps, and it lines up with the symptom or an outlying band.

## Fixing each kind of problem

- **Level.** First decide where the stem *should* sit. Compare it with its peers in the song (the other guitars, the other vocals, the other drum mics). Also check whether the MIX band it dominates is off target in `tonal_balance`. Move it in one step towards that point, then check again. When you are unsure between two amounts, choose the smaller: overshooting is as wrong as undershooting.
- **Pan.** `set_pan` is a balance control. To bring a stem whose balance (R−L) is *b* dB back to the centre, use `pan = (4/π)·atan(10^(−b/20)) − 1`. For example, b = −4.3 gives pan ≈ +0.30. Re-centring with a balance control also lowers the stem's level, so after committing, raise its gain until its LUFS is back to what it was before the pan move.
- **Polarity.** A drum stem whose flip value is about +1 dB or more (`triage` lists them; `phase` gives the detail) is fighting the rest of the kit. Invert that one stem, even if the client said nothing about the drums: a polarity flip is a measurable fault, not a matter of taste. If both mics of a pair show it, invert the one with the larger flip value. A small flip value means leave it alone: some mics, such as a snare bottom mic, are naturally opposed.
- **Resonance.** In a clean mix, some stem always has the strongest bump, and a guitar body or drum shell can stand well above its other bumps. So only treat a resonance as a fault when the client's note says something sounds harsh, ringy or whistling, and look in the family the note names. With no such note, leave bumps alone. `scan` "peaks" ranks stems by how audible their bumps are in the mix (height times the stem's share of the mix at that frequency); the suspect is the stem at the top in the family the note names, at the bump `scan` reports. Cut it with one peaking band at the bump's frequency, Q 8. The reported height is measured against the bump's surroundings, so it understates the boost by about half: cut by about **twice** the reported height (at most 18 dB). Afterwards, check `spectrum` again: the bump should now be no higher than the stem's other bumps, and nothing else should have changed.
- **Mud.** Some instruments, acoustic guitars and snares especially, are naturally heavy in the low-mids, so a stem at the top of `scan` "lowmid" is not evidence on its own: in clean mixes there is always a leader. Only treat mud as a fault when the client's note says the mix is muddy or boxy. Then the suspect is the stem at the top of `scan` "lowmid": mud in a mix comes from a stem that fills the mix's low-mids and is heavier there than its kind usually is. Use the cut `scan` suggests for it (one peaking band at the bump's centre, Q 1, the suggested depth). Commit and run `scan` again: its bump should be near 0. Don't cut several stems. With no such note, leave low-mids alone.
- **Clipping.** A stem with many flat-topped runs per minute, while comparable stems show almost none, has clipping baked into the recording. No fader or EQ can restore the missing peaks, so turning it down only hides the problem. Submit verdict `unfixable` with a clipping finding on that stem, and change nothing.

## Restraint rules

- Only change the stems you diagnosed. Never "fix" one stem by moving all the others.
- One clear problem with a clean fix beats several speculative ones. Every extra change risks damaging a healthy part of the mix.
- If your best evidence is weak, don't change anything. If nothing clearly stands out after checking everything, the right answer is `no_fault` with no findings. A request to "check it over" is not evidence that something is wrong.
- Confidence means how sure you are. Below about 0.6, don't act on a finding: keep looking for evidence, or leave it out.
