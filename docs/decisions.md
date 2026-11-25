# Decision log

This log has one short entry per decision. Each entry says what was chosen, what the alternatives were, and why.
The first 33 entries come from the design session on 2026-11-24. Add new entries at the bottom, and never edit old ones. When a decision changes, write a new entry that says which entry it supersedes.

Format: **D## — Title** · date · status (`accepted` / `superseded by D##`)

---

## Goal and positioning

**D01 — Target audience: applied-AI engineering, with dev-tools and general SWE second** · 2026-11-24 · accepted
- *Alternatives:* dev-tools first; general SWE; a single target company.
- *Why:* A harness project demonstrates applied-AI skills most directly. Many general engineering listings now mention AI, so the secondary audiences come along for free.

**D02 — Build an agent plus an eval suite, not just one of them** · 2026-11-24 · accepted
- *Alternatives:* an agent harness only; an eval harness only.
- *Why:* Plenty of people build agent demos. Few can show measured improvements from specific design choices. The evals make the work credible, and the agent gives the evals something worth measuring.

**D03 — Ship a demo-able version in about 2 weeks, then keep building in public** · 2026-11-24 · accepted
- *Why:* A finished narrow project is worth more than an unfinished ambitious one, and the timeline is soft. A results chart that improves over time is a good signal in itself.

**D04 — Domain: mixing and mastering audio** · 2026-11-24 · accepted
- *Alternatives:* Godot game-QA playtesting agent (recommended at the time; dropped because the builder has little Godot experience); fintech ops agent (builder not interested); training-plan coach for running and cycling (crowded market, hard to grade).
- *Why:* The builder has production experience. Audio quality can be measured objectively. Giving a text model a way to "hear" is an interesting tool-design problem.

**D05 — Task shape: mix repair with injected faults** · 2026-11-24 · accepted
- *Alternatives:* mastering only (too few agent steps); open-ended mixing (hard to grade); sound design (a different project).
- *Why:* Injecting known faults gives an unlimited supply of graded tasks with known answers, and the agent has to diagnose, not just turn knobs.

**D06 — Keep mixing repair even though the builder is not a strong mixer** · 2026-11-24 · accepted
- *Alternatives:* switch to a domain where the builder is stronger.
- *Why:* The evals carry the authority, because faults are injected and the clean ground truth comes from datasets, so nobody's ears decide the score. The builder can still reliably tell which of two mixes is better in an A/B test.

## Budget and agent loop

**D07 — Budget: Claude Pro subscription only, no API spend** · 2026-11-24 · accepted
- *Facts:* Pro includes no API credits. Claude Code is included and can be scripted with `claude -p`. Using the Agent SDK with a Pro login is not allowed for products. Usage is capped by 5-hour and weekly limits, which are not published.

**D08 — Claude Code is the agent loop, and Zosimix is the specialized layer on top** · 2026-11-24 · accepted
- *Alternatives:* our own Messages-API loop (needs paid API usage); our own loop on a local model plus an API top-up.
- *Why:* This is the only option that fits D07. What applied-AI interviewers probe (tool design, context budgets, verification, eval methodology) is still our own work. The MCP server and eval harness stay agent-agnostic so our own loop can be added later.

**D09 — Python** · 2026-11-24 · accepted
- *Alternatives:* Java, Node.js, C# (the builder knows these better).
- *Why:* The audio ecosystem (`pedalboard`, `librosa`, `pyloudnorm`) is in Python, and Python is the default language for AI work.

## DAW and engines

**D10 — Integrate with FL Studio from the start** · 2026-11-24 · accepted
- *Alternatives:* render offline only and add a DAW later.
- *Why:* An offline-only tool isn't practical for a producer. The builder uses FL Studio.

**D11 — Two engines behind one `MixEngine` interface: offline (pedalboard) and FL** · 2026-11-24 · accepted
- *Alternatives:* FL only (slow and fragile, and no reviewer can reproduce it without an FL license); offline only.
- *Why:* Iteration is fast and reproducible offline, while headline numbers come from FL. A calibration step and a same-results check keep the two engines consistent. The engine interface is good engineering for the dev-tools audience.

**D12 — Write our own minimal FL bridge (about 10 actions), crediting prior art** · 2026-11-24 · accepted
- *Alternatives:* fork or depend on rosasynthesiz/flstudio-mcp (67 tools, beta).
- *Why:* That would put a large dependency in the most fragile part of the system. A small action set is a deliberate design choice we can measure.

**D13 — Target FL Studio Producer 20.9.2, the version the builder owns** · 2026-11-24 · accepted
- *Alternatives:* install FL 2026 side by side as a dedicated agent/eval install (recommended; free with Lifetime Free Updates).
- *Consequences:* Scripting API ≈ v20 with embedded Python 3.9. No mixer-EQ API and no send-level API, so the templates pre-load Fruity Parametric EQ 2 and the agent drives it through plugin parameters. Polarity is available (added in 20.9.1). The command-line renderer is the biggest risk, so it is tested first (D31).

**D14 — Faults are baked into the stem audio, and FL opens with a neutral mixer** · 2026-11-24 · accepted
- *Alternatives:* put faults in mixer settings.
- *Why:* A fault stored as a mixer setting can be read straight from the API, and "reset everything" would score perfectly. Baking faults into the audio forces the agent to diagnose by measuring. It also means we never edit `.flp` files: the harness swaps WAV files into fixed paths that the hand-built templates point to.

## Benchmark

**D15 — Clean references come from public multitrack datasets, not the builder's own projects** · 2026-11-24 · accepted
- *Why:* The builder doesn't consider their own mixes good enough to serve as ground truth.

**D16 — Datasets: MoisesDB as the core (about 5 songs) plus 1–2 AlbumDB songs** · 2026-11-24 · accepted
- *Alternatives:* MUSDB18-HQ (only 4 stems, most licenses restricted); MedleyDB (mixes are only approximate); Cambridge-MT (raw tracks with no ground-truth mix).
- *Why:* MoisesDB stems sum exactly to the mix, and stems are split per instrument. AlbumDB is mixed by real engineers under CC BY, so its audio is safe to publish. When loading a song, check that the stems sum to the mix. The benchmark measures restoring the intended state, not making a mix sound professional.

**D17 — v1 fault set** · 2026-11-24 · accepted
- Gain, polarity (on multi-mic drums), narrow resonance, mud, and pan. Plus **unfixable** hard clipping (tests honesty) and a **no-fault control** (tests false positives).
- *Deferred to v2:* stereo-width faults, compression faults, and several faults in one task.

**D18 — Every task has a hint level and a fault size; the agent never gets the clean mix** · 2026-11-24 · accepted
- Each task gets either a vague client note or no hint, and 2–3 fault sizes per type. A fixed seed samples about 30 full tasks and a 6-task smoke set.
- *Why:* Varying the size lets us chart detection rate against fault size. Giving the agent the clean mix would turn diagnosis into simple matching.

**D19 — Deterministic grading, no LLM judge** · 2026-11-24 · accepted
- The grade combines the structured JSON diagnosis (right stem and fault type), how much each fault-specific metric recovered, collateral damage measured as whole-mix distance from the clean mix, and cost in tokens and time.
- *Why:* An LLM grading another LLM's prose about audio neither of them can hear is weak evidence.

**D20 — Add blind A/B listening as a sanity check** · 2026-11-24 · accepted
- The builder listens, plus one friend if available. Hidden control pairs measure how consistent the listener is.
- *Why:* It answers the question "do your metrics match what people hear?" It is presented honestly as a check, not a study.

**D21 — Compare three configurations** · 2026-11-24 · accepted
- Plain Claude Code; Claude Code + rosasynthesiz/flstudio-mcp; Claude Code + Zosimix.
- *Why:* Beating the strongest existing tool convinces more than beating a strawman. If Zosimix loses on some faults, the chart shows exactly where.

**D22 — Tiered eval runs with a resumable runner; Sonnet 5.5 for headline numbers** · 2026-11-24 · accepted
- A 6-task smoke set runs daily. A full 3-configuration run happens at milestones. The runner checkpoints and resumes after usage limits. Opus 5.5 is available on the builder's Pro plan, but Sonnet is enough for this.

## Zosimix layer

**D23 — Perception: compact numbers first, a tonal target derived from data, and forced re-measurement** · 2026-11-24 · accepted
- The overview tool gives compact numbers, with drill-downs on request. Every tool's output has a token budget. The tonal target comes from the held-out clean mixes. Spectrogram images are an ablation, not part of the core.

**D24 — Verification is batched through `commit_changes` with a difference report under ~150 tokens** · 2026-11-24 · accepted
- *Alternatives:* verify after every move (too expensive in tokens); verify only at the end.
- *Why:* This keeps the guarantee that the agent can't claim an unverified fix, at a fraction of the token cost. The final diagnosis is refused unless the last change was verified. The token cost is measured in an ablation.

## Integrity and operations

**D25 — Eval isolation** · 2026-11-24 · accepted
- Each run gets a fresh workspace holding only the faulted stems and the hint. Ground truth lives outside that workspace, and permission rules block reading it. Graders flag any attempt to reach it.
- *Why:* The plain Claude Code baseline has shell access and could otherwise read the answers.

**D26 — Development and evals share the Pro quota** · 2026-11-24 · accepted
- Build during the day, run evals in quiet windows, and check `/usage` before a full run.

## Presentation and process

**D27 — The README leads with the demo video, with the results chart directly below** · 2026-11-24 · accepted

**D28 — One technical blog post once the first full results exist (around week 3)** · 2026-11-24 · accepted

**D29 — Public repo from day 1; code under MIT, modified audio under CC BY-NC-SA with attribution** · 2026-11-24 · accepted

**D30 — Claude Code implements; the process is part of the portfolio** · 2026-11-24 · accepted
- The README says: "designed by me, implemented by directing Claude Code."
- `CLAUDE.md`, this decision log, and a commit-review subagent are part of the repo.
- Code must be clean and explainable. The builder reads the code at each milestone and asks questions, and nothing merges that the builder can't explain.
- *Note:* hand-writing the graders was suggested as optional Python practice, but the builder chose not to.

**D31 — Plan order: FL go/no-go spike first (days 1–2)** · 2026-11-24 · accepted
- *Why:* The command-line render on 20.9.2 is the biggest unknown.
- *Fallback:* use GUI automation to render, or make FL demo-only and let the offline engine carry the evals.
- If time runs short, cut demo-video polish before the same-results check or the listening test.

**D32 — The commit-review subagent focuses on eval integrity** · 2026-11-24 · accepted
- It flags any change to the graders, the task generator, or the ground-truth layout, or anything else that could leak answers to the agent under test.

**D33 — Deferred** · 2026-11-24 · accepted
- Our own agent loop, applying a mix state to a user's existing FL project, a "critical listener" subagent, an Opus data point, v2 faults, and moving the FL engine to FL 2026.

## Naming

**D34 — Project name: Zosimix** · 2026-11-24 · accepted
- *Alternatives:* Earshot (the working title), Nulltest, Fresh Ears, Mixbench, Zosimos.
- *Why:* The name comes from Zosimos of Panopolis, an early alchemist who wrote about distillation and the equipment for purifying impure material. That is the project's idea: put a contaminated mix through careful apparatus and recover the clean version. Adding "mix" makes the audio connection obvious. On 2026-11-24 the name had 0 GitHub repositories and was free on PyPI. Plain "Zosimos" had 46 unrelated repositories.
- *Consequence:* The name doesn't describe the project on its own, so the tagline must always appear next to it: *"Zosimix: an agent that repairs mixes it can't hear, and a benchmark that proves it."*

## Spike results

**D35 — FL go/no-go spike: GO on FL 20.9.2** · 2026-11-24 · accepted
- *Evidence (spike/NOTES.md):*
  - Command-line render (`/R /Ewav`, and `/O<folder>`) runs unattended, and FL exits by itself. A 132 s song takes about 80 s.
  - The SysEx bridge over loopMIDI has a 1.7 ms round trip on scripting API version 20.
  - Fader, pan and polarity work.
  - All continuous Parametric EQ 2 parameters accept exact values.
- *Implementation rules this establishes:*
  1. Mixer writes take effect only after the script callback returns, so the FL engine confirms each write with a separate `get` and polls until it matches (1–2 ms in practice).
  2. PEQ2 band type and filter order are stepped parameters. The engine maps them to named choices, not raw floats.
  3. The bridge protocol is plain text, not JSON, because FL's embedded Python lacks most of the standard library.

**D36 — In FL mode, the verification hook previews through the offline engine** · 2026-11-24 · accepted (approved by owner 2026-11-24)
- *Problem:* an FL render costs about 80 s, mostly startup, which is too slow for every `commit_changes` (D24).
- *Proposal:* the hook renders the current mix state with the offline engine, which takes milliseconds. FL renders once at the end, and only that render is graded.
- *Depends on:* the parity check (DESIGN §3.3) keeping the offline preview faithful to FL. If parity turns out poor, fall back to FL renders at the end plus a smaller number of mid-run FL renders.

## Day 3: data, faults, tasks

**D37 — Start with AlbumDB, fetched song by song; MoisesDB once access is granted** · 2026-11-24 · accepted
- *Facts:* AlbumDB's Zenodo zips support HTTP range requests, so single songs can be pulled out of the 5 GB stems archive (`remotezip`). MoisesDB downloads sit behind a sign-up form on music.ai, which the owner has to fill in.
- *Consequence:* AlbumDB's reference is a mastered stereo file, so it cannot null against the stem sum. Its check is "plausible" (gain-matched correlation > 0.9), not "exact". The ground truth is still the plain stem sum (D16).

**D38 — Workspaces are short-lived and uniform** · 2026-11-24 · accepted
- Each run's workspace is built just before the run and deleted afterwards. A full copy of a song is 0.6–2 GB, so 30 tasks cannot all sit on disk at once.
- Every stem in a workspace is written as stereo, 32-bit float, with its original name. Format, channel count or file name must not give away which stem was changed. Float format also stops a +10 dB gain fault from accidentally turning into clipping.
- Task specs, which contain the answers, are committed under `tasks/`. That makes it mandatory for the runner to put workspaces **outside the repo** and deny reads of it (D25).

**D39 — Dataset citations are mandatory** · 2026-11-24 · accepted
- Any public output that uses MoisesDB or AlbumDB data (README results, blog post, demo video, a paper) cites them using the BibTeX in `CITATIONS.md`. For MoisesDB that is Pereira et al. 2023, arXiv:2307.15913, as specified by the owner. Each song's `song.json` also carries its attribution.

**D40 — Every song's clean mix is scaled to peak at −1 dBFS** · 2026-11-24 · accepted
- *Finding:* AlbumDB song 01's stems sum to a peak of **+8.2 dBFS**, because the stems are pre-master and a limiter brought the released master down. Left alone, FL's 24-bit renders would clip, and the agent might report "clipping" that is really just the dataset's level.
- *Rule:* `Song.load_clean_stems()` scales all stems of a song by one shared gain (−9.7 dB for song 01, −5.2 dB for song 10). The balance, which is the ground truth, is unchanged. Workspaces and graders must both use these scaled stems.

**D41 — Polarity faults only on drum mics whose flip audibly and unambiguously thins the drum bus** · 2026-11-24 · accepted
- *Finding:* in AlbumDB song 01 the kick mic is essentially uncorrelated with the overheads (|r| ≈ 0.01), and the snare is already anti-correlated in the clean mix (r ≈ −0.16 at a 4.4 ms lag). The stems are processed, so flipping one mic is either inaudible or has no clear correct answer.
- *Rule:* a non-overhead drum mic qualifies only if flipping it lowers the low-passed (< 500 Hz) drum-bus RMS by **≥ 1 dB**. With that rule, neither AlbumDB song has any eligible mic, so polarity tasks will come from MoisesDB's raw multi-mic drums.
- *Implication for day 5:* plain broadband correlation is too weak to detect polarity. The perception tool needs low-passed, lag-searched correlation, or a bus-energy-on-flip test like this one.

**D42 — MoisesDB picks, and polarity faults sourced from the only songs that support them** · 2026-11-24 · accepted (owner chose option A)
- *Finding:* MoisesDB records each drum part with a single mic, with very little bleed. Flipping any one mic changes the drum bus by under 0.6 dB in 10 songs across 7 genres. Across all 240 songs there are only 11 multi-file drum or bass parts, and all but one are layered synths.
  - The exception is Firefly "Big Life", which has two overhead mics. Flipping either one costs 3.1 dB below 250 Hz in the full drum bus.
  - After the overhead exception was removed, Juniper "Triangles" also qualifies: its overhead blends with the close mics.
- *Chosen:* keep polarity in v1, with tasks drawn only from Big Life and Triangles. Rejected alternative: move polarity to v2. The README will explain why polarity faults are rare.
- *Songs (5):* Firefly – Big Life (pop), Holy Magick – Stolen Car (electronic), Centenary – By Now (reggae), The Followers – Kryptonite (rock), Juniper – Triangles (world/folk). All were picked from the 240 using the survey score: full drum kit, lead vocal, 8–14 stems, 2.5–5 minutes. With AlbumDB that makes 7 songs, about 6 GB as 32-bit float.
- *Implementation:*
  - The importer keeps multiple files of the same part as separate stems (`_1`, `_2`), because summing them destroys exactly the mic pairs where polarity problems live.
  - The polarity rule no longer excludes overheads. The ≥ 1 dB low-end-loss test (D41) is the only criterion.
  - Track-type names are cut to 3 words, since they appear in FL's mixer and in every tool call.

## Day 4: offline engine

**D43 — The mix state is stored in real units; the offline engine renders it with per-track caching** · 2026-11-24 · accepted
- *Mix state:* for each track, gain (dB), pan (a −1..1 balance control), polarity, stereo width (0 = mono .. 1 = unchanged .. 2), and up to 7 EQ bands (peaking, low shelf, high shelf, high-pass, low-pass), stored in Hz, dB and Q. Converting to FL's 0..1 knob positions is the FL engine's job, guided by calibration. Values outside the action space are rejected with a readable error.
- *The gain limit is the total gain, −60..+18 dB:* FL's fader tops out at +5.6 dB, but a −10 dB gain fault needs +10 dB to undo. The FL engine will put any boost above the fader's range onto PEQ2's main level. PEQ2's real range must be confirmed during calibration.
- *Processing order:* polarity → EQ → width → pan → gain. Every step is linear, so the order only matters numerically.
- *Pan law:* one shared function, `audio.pan_gains`, used by both the pan fault and the engine, so the two always agree. Undoing a pan fault takes panning back *and* raising the fader by −20·log10(cos(p·π/2)), as in FL. **Open question for the graders (days 6–7):** should repairs be scored after gain-matching the whole mix? An agent that fixes the balance but leaves the overall level slightly off shouldn't be punished like one that broke the balance.
- *Known mismatch:* pedalboard's high-pass and low-pass filters are first order (6 dB/oct). PEQ2's slope is configurable. To be resolved during calibration. No v1 fault needs them.
- *Speed, measured on real songs:* one fader or EQ move re-renders in 0.1–0.3 s, and 2 EQ bands on every track takes 2–3 s, against about 80 s for an FL render. That confirms D36: the offline preview is fast enough for every `commit_changes`.
- *Guarantee, enforced by tests:* every fixable v1 fault can be undone in this engine (residual < −100 dB for gain, polarity and pan; < −40 dB for the EQ faults). If that ever breaks, the benchmark would contain unsolvable tasks.

## Day 5: perception tools and MCP server

**D44 — Resonance detection uses "persistent bumps"; resonance is expected to be the hardest fault** · 2026-11-24 · accepted
- *Finding:* on real stems, a long-term spectrum's sharpest peaks are **sustained notes**: a piano's top five peaks were all notes, with Q ≈ 150–300, and the injected +8 dB resonance at 1475 Hz didn't appear. Smoothing at different widths found only 4–5 of 12 test cases, and some of those "hits" were natural resonances already present in the clean recording (an acoustic guitar body at about 960 Hz).
- *Method chosen:* for each loud frame, take the height of a bump above its 1-octave neighbourhood (1/12-octave smoothing), then take the **median over the song**. Notes move and mostly cancel out; a fixed EQ boost doesn't. It found 7/12 cases, including all three severities on an AlbumDB lead vocal, with little false signal in clean vocals. It still can't tell a piano's or guitar's natural body resonance from an injected one.
- *Stance:* the agent gets this as evidence, not proof, and can test a hypothesis by cutting and checking what moved. The detection-by-severity chart is expected to show resonance as the hardest fault. That is a finding to report, not something to hide.

**D45 — Tool-layer design** · 2026-11-24 · accepted
- *Verification lives in the MCP server, not in a Claude Code hook.* `commit_changes` applies pending changes, re-renders offline (D36), and returns the short difference report. `submit_diagnosis` refuses while anything is pending. This works in any MCP client and with either engine. The "hook on/off" ablation becomes `--no-verify`, where commit just returns "committed".
- *Measurements always describe the committed mix.* `set_*` calls only change a pending state, so the agent cannot "hear" a change it hasn't committed.
- *Tools:* overview, spectrum, compare, phase, tonal_balance, get_mix_state, set_gain, set_pan, set_polarity, set_width, set_eq_band, clear_eq_band, commit_changes, submit_diagnosis (14 in total). Every answer is plain text with a character budget enforced by tests (the overview of a 24-stem song is about 1.2k characters).
- *Tonal target:* leave-one-out over the other 6 songs, written into the workspace as `tonal_target.json`. The mix-level target is tight (band spread 1.5–3.3 dB). Family targets are useful for vocals and too loose for drums and keys, because a kick and a hi-hat share the "drums" family.
- *Speed:* stems are measured in parallel threads and cached per track setting. The first overview takes 4–6 s, repeats are instant, and a commit with its difference report takes about 1.7 s.
- *Grading note for days 6–7:* when a polarity fault is on one mic of a two-mic pair (Big Life's overheads), flipping *either* mic restores coherence, and `phase` shows both at +2.6 dB. Detection grading must accept any stem whose flip restores the low end, not only the injected one.

## Days 6–7: graders and runner

**D46 — Grading rules** · 2026-11-24 · accepted (owner may revisit the level rule)
- *Detection:* the verdict must match the fault class: "fixed" for fixable faults, "unfixable" for clipping, "no_fault" for controls. At least one finding must name the right fault type on an *acceptable* stem. Normally that is only the faulty stem. For polarity it is any drum stem whose flip restores ≥ 1 dB of low end, so with a two-mic pair either mic counts (D45).
- *Repair:* the fraction of the fault-specific error removed, `1 − after/before`, clamped to [−1, 1]. It must be ≥ **0.7** to pass. The error measure depends on the fault:
  - gain: level error in dB
  - pan: L/R balance error in dB
  - resonance and mud: band-shape error, meaning the band's share of the stem's energy, over ±1/3 octave for resonance and ±1 octave for mud
  - polarity: low-end error of the drum bus
- *Overall level (the open question from D43):* repair is measured **without penalizing overall level**, except for gain faults, where level *is* the fault. Panning a vocal back without raising its fader still counts as fixing the pan. The level change is reported (`mix_level_change_db`) but does not fail a task.
- *Collateral:* all stems that were clean, summed, must stay within **−30 dB** of their original (about 3%). That catches "fixing" a loud vocal by turning everything else up. The grader also lists every other stem that was touched.
- *Clipping and controls:* pass only with the right verdict **and** a final mix within −30 dB of the mix as handed over. Any change counts against the agent: a fake fix, or a false alarm acted on.
- *No submission, or an unusable mix state:* the task fails. An invalid mix state is treated as "no changes", and the reason is recorded.

**D47 — Task sampling** · 2026-11-24 · accepted
- Cycle through fault types. Among the songs that can host a fault, prefer the least-used one. Cycle severity through the three sizes per fault type, starting at a random point. Never emit the same (song, fault, stem, severity, hint) twice.
- *Why:* the first draw repeated the same Big Life polarity task 4 times and put 8 of 30 tasks on one song. Polarity has only 3 possible stems in the whole dataset.
- *Result:* `full` has 30 distinct tasks, 4–5 per song, every fixable type spread across all three sizes, and 15/15 hint / no hint. `smoke` has 6 tasks covering 6 fault types; resonance is not in it.

**D48 — Runner setup** · 2026-11-24 · accepted
- *Command:* `claude -p` with `--permission-mode dontAsk`, `--setting-sources ""` (no personal settings, hooks or memory in evals), `--strict-mcp-config`, `--no-session-persistence` and stream-json output. Never `--bare`. A probe run confirmed that it uses the Pro login, runs Sonnet 5.5, and exposes only the 14 Zosimix tools.
- *Configurations:*
  - `zosimix`: `--tools ""` plus only `mcp__zosimix__*`
  - `plain`: shell and file tools, plus a separate Python environment with numpy, scipy, soundfile, pyloudnorm and pedalboard, but **not** the Zosimix package. It gets the same action space, written as `output/mix_state.json`, so both configurations are graded identically.
  - The third baseline (Claude Code + an existing FL MCP) needs FL running, so it waits for the FL engine (days 9–10).
- *Isolation:* workspaces live under `%LOCALAPPDATA%\zosimix\runs`, outside the repo. Every tool call is scanned for the repo path, task files and other runs. Workspace audio is deleted after grading; transcripts and answers are kept.
- *Resilience:* every task is graded and appended to `results.jsonl` immediately. Re-running with `--run <id>` skips finished tasks. A usage-limit error stops the run without grading that task.
- *Per-task timeout:* 20 minutes. The CLI has no max-turns flag.

**D49 — Plainer fault-type rotation in task sampling (refines D47)** · 2026-11-24 · accepted
- The rotation index was `(tasks so far + attempts // 20)`. It was meant to move past a fault type that keeps drawing duplicates, but `attempts` also counts successful draws, so the rotation slipped by one every 20 loop passes even when nothing went wrong. In the old `full` set, task 17 skipped `pan`.
- *Now:* a `turn` counter advances after each new task. A type that draws `MAX_DUPLICATE_DRAWS` (20) duplicates in a row gives its turn to the next type. The overall `50 × n` attempt limit stays.
- *Effect:* `smoke` regenerates byte-for-byte identical, so smoke run 1 stays comparable. `full` was regenerated with the same seed (42). No full run had used it yet. It still has 30 distinct tasks: types 5/5/4/4/4/4/4, 4–5 per song, every fixable type covering all three sizes, and hints at 14 vague / 16 none.

## Walkthrough fixes

**D50 — Malformed answers are graded, never crash the run** · 2026-11-25 · accepted
- *Problem:* the plain baseline writes `mix_state.json` and `diagnosis.json` by hand. Valid JSON in the wrong shape (a list at the top, `null` for a track, findings as text) raised `AttributeError` inside the grader, which would stop the whole eval run. Also, `"polarity": "false"` (a string) was accepted as true, because a non-empty string counts as true in Python.
- *Mix state:* `MixState.from_dict` checks the shape and `validate()` checks types. Numbers must be numbers (not bools), polarity must be a real boolean, and EQ must be a list of band objects. Wrong shapes or types raise `TypeError`; out-of-range values raise `ValueError`. Both carry a readable message. The grader already graded either error as "no changes" and records the reason in `invalid_mix_state`.
- *Diagnosis:* `graders.read_diagnosis` normalizes the answer into (verdict, findings, problem) and never raises. Anything that isn't a string becomes `None`. A finding that isn't an object, or a `findings` value that isn't a list, counts as one **malformed finding** that matches nothing. A badly formatted false alarm therefore still fails a control task, and a single finding object without the list around it gets no credit. The reason is recorded in `invalid_diagnosis`.
- *Effect on existing results:* none. Smoke run 1 answers were all well-formed.
