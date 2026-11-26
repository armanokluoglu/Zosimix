---
description: Diagnose and repair a mix from its exported stems, then put the fix into the open FL Studio project
argument-hint: <folder of exported stems> [what sounds wrong]
---

Check and repair this mix: $ARGUMENTS

The first argument is a folder of stems exported from the DAW, one WAV per mixer track (in FL Studio: File > Export > WAV with "Split mixer tracks"). Anything after it is the client's note about what sounds wrong; treat it like a client note in the zosimix-diagnosis skill. If there's no note, say so and look for objective faults only.

1. Call `open_mix` with the folder. Tell the user which stems were loaded and flag any working name that looks like the wrong family.
2. Diagnose and repair following the zosimix-diagnosis skill: `triage` first, measure, change only what the evidence supports, `commit_changes`, and re-measure.
3. Report in plain language what you found and what you changed, track by track, with the numbers (dB, Hz, pan). Say what you left alone and why.
4. Call `submit_diagnosis` so the findings and settings are saved next to the stems (in `zosimix-output`).
5. If FL Studio is open with the Zosimix MIDI script, call `apply_to_fl` with dry_run=true, show the user the plan, and ask before applying. Apply only on a clear yes, then tell them `revert_fl` undoes it. If FL can't be reached, give the settings so they can set them by hand.
