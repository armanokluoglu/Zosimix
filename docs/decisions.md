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

**D51 — Tighter isolation for the plain baseline (refines D25 and D48)** · 2026-11-25 · accepted
- *Problem:* the plain configuration has shell and file tools, so the only protection was scanning tool-call **inputs** for forbidden strings. The workspace sat inside the run folder, so `cat ../../../results*` would reach `results.jsonl`. That file holds earlier tasks' grades, and with repeats, this task's own answer. A path like `~/Desktop/Harness` also didn't match the literal repo path.
- *Now:*
  - **Workspaces live in `%LOCALAPPDATA%\zosimix\ws\<random hex>`**, apart from `runs\`. Their names say nothing about the task.
  - **Tool results are scanned too.** Any result containing a key that exists only in ground-truth files (`"expected_verdict"`, `"hint_level"`, `"severity":`) is flagged. This catches a leak however the path was spelled.
  - `zosimix\runs` was added to the forbidden input strings.
- *Checked:* the smoke run 1 transcripts contain 42 tool results and produce no flags under the new scan. The scan also reads Claude Code's real stream-json format.
- *Still detection, not prevention, for `plain`.* A script that reads a results file and prints only a stem name would avoid both scans. Real prevention needs a filesystem sandbox, for example running the baseline as a separate Windows user with no access to the repo or `runs\`. That is deferred until the plain baseline shows any flags or suspicious scores. The `zosimix` configuration is unaffected: it has no file tools at all.

## Day 8: diagnosis skill

**D52 — The diagnosis skill: how it's delivered and what it may contain** · 2026-11-25 · accepted
- *Where it lives:* `skills/zosimix-diagnosis/SKILL.md`, in Claude Code's skill format, so anyone using the MCP server interactively can drop it into `.claude/skills/`.
- *How evals get it:* eval runs turn every built-in tool off (`--tools ""`), so the agent has no Skill tool to load a skill when it needs one. Instead, the runner appends the skill's body to the system prompt with `--append-system-prompt-file`. A probe run confirmed that the CLI applies it. A file in the system prompt is always present and costs the same on every run, which also makes the ablation clean.
- *Configurations:* `zosimix` is the full layer (tools, verification and skill). `zosimix-noskill` is the ablation, the same setup smoke run 1 used under the name `zosimix`. `plain` is unchanged.
- *Content rule:* the skill may contain only general mixing knowledge and procedure: no song ids, no dataset stem names, no severities, and nothing about how tasks are generated (for example, not "there is exactly one fault"). A test enforces the names part. *Why:* the skill is tuned on the smoke set (the development set), and the full set is the test set. Both use the same 7 songs, so anything song-specific in the skill would inflate the full results.
- *Overlap:* three full tasks repeat a smoke task (same song, fault, stem and size): `full-005`, `full-015` and `full-029`. Full-set reports will give the pass rate with and without them.
- *Seen in passing:* the CLI has a `--restricted` mode that confines the file tools to the working directory. It doesn't stop Bash, but it is a cheap extra layer to add when the plain baseline is set up (see D51).

**D53 — Smoke run 2 with the skill: 4/6 (was 3/6). Skill tuning on the smoke set stops here** · 2026-11-25 · accepted
- *Result:* the pan task now passes (the centre convention plus the pan formula). The mud task fails without a false positive (no change made; before, a healthy guitar was EQ'd). The gain task is unchanged: +8 dB applied against a true −6 dB. Details are in `results/smoke-2.md`.
- *Why stop:* six single runs can't separate the skill's effect from run-to-run noise, and more rounds would fit the wording to these six tasks (the smoke set is the development set; D52). The full run with repeats measures it properly.
- *Open lever, not taken yet:* a data-derived "typical loudness relative to the mix" per instrument family, leave-one-out like the tonal target. Measured spreads across the 7 songs: bass ±3.0 dB, vocals ±1.9, guitars ±1.8, drums ±1.3. That is enough to help on 6 and 10 dB gain faults, not on 3 dB ones. It's a tool change and needs the owner's call.

**D54 — Per-family level reference: tried and rejected** · 2026-11-25 · rejected (owner's call after the evidence)
- *Tried:* a `level_balance` tool comparing each instrument family's loudness relative to the mix with a leave-one-out "typical" value from the other 6 songs (the open lever from D53).
- *Smoke run 3:* still 4/6, but the gain task got worse (repair 0.667 → 0.333). The agent used the tool as intended and stopped short of the "typical" value, yet still overshot, because this song's clean bass sits 11.8 LU under the mix against a typical −6.0 ± 2.4.
- *Offline check over all 31 song/family pairs:*
  - "Typical" is a median 1.8 dB and up to 7.3 dB away from the true clean level.
  - Aiming at it would pass 16% of 3 dB gain faults, 55% of 6 dB faults and 74% of 10 dB faults.
  - 4 of 31 clean family levels already read as outliers (|z| > 2), a false-alarm risk on control tasks.
- *Decision:* removed completely, including the tool, the skill text and the target fields. With only 6 reference songs, a level reference is weak and sometimes misleading evidence. Revisit only if the song pool grows substantially. Write-up: `results/smoke-3.md`.
- *Consequence:* gain faults, especially small ones, stay a judgement call based on peer stems. That is an honest limitation of "restore the intended balance" without a reference.

**D55 — One generic 24-slot FL template, at a fixed path** · 2026-11-25 · accepted
- *Change from DESIGN.md §4.4:* instead of one hand-built FL project per song, there is one project, `C:\zosimix\fl\Zosimix24.flp`. Its 24 audio clips point at `C:\zosimix\fl\slots\slot01.wav` .. `slot24.wav`, clip N is routed to mixer insert N, and Fruity Parametric EQ 2 sits in the first effect slot of every insert. Build guide: `fl_bridge/TEMPLATE.md`.
- *How a song gets in:* the harness overwrites the slot WAVs before FL opens the project (`zosimix.fl.slots.write_song`), then names and sets the inserts through the bridge. Unused slots get 1 s of silence. We still never edit `.flp` files (D14).
- *Why:* the owner builds the template once instead of seven times, and every song gets the same routing and plugin layout, so one calibration covers all of them.
- *Why a fixed path:* the project stores absolute file paths. `C:\zosimix\fl` has no spaces (FL's command-line render can't handle them) and no user name (the template is committed to a public repo).
- *Limit:* 24 stems at most, which is the largest song in the pool. The placeholders are 300 s, longer than any song (243 s at most), so every clip is long enough.

**D56 — Separate SysEx headers for requests and replies** · 2026-11-25 · accepted
- *Found:* after the template was built, FL's MIDI settings had both loopMIDI outputs ("Zosimix In" and "Zosimix Out") on port 200. FL sent its replies to "Zosimix In", loopMIDI fed them straight back into the script, and the script answered each with `err unknown_command`, which looped again. That's about 3,800 messages a second, and nothing reached the client.
- *Fix in code:* requests keep `7D 5A` ('Z') and replies now use `7D 7A` ('z'). The script drops anything with the reply header, so a misrouted reply dies instead of feeding back.
- *Fix in FL:* only the "Zosimix Out" output may carry the bridge's port number. `fl_bridge/TEMPLATE.md` now says so.
- *Also found:* the first message on a freshly opened connection is often lost (3 of 4 new connections lost their first ping; every later message arrived). `Bridge` now pings when it connects, with a 0.5 s timeout and up to 5 tries, before returning. A late reply to an earlier ping carries an old id and is ignored.

**D57 — FL's value scales, read by the probe** · 2026-11-25 · accepted (data: `fl_bridge/calibration/probe.json`)
These are what FL 20.9.2 *reports* for each knob position. What the knobs do to the sound is measured separately with renders (calibration step 2).
- *Fader:* position 0.8 is 0 dB, and 1.0 is +5.59 dB, the most the fader can boost. The curve isn't a simple formula, so the engine inverts it from the 41-point table and then fine-tunes against FL's own dB readout (`get_volume_db`). Boost above +5.59 dB goes on PEQ2's main level (D43).
- *Pan:* -1..+1, continuous, and FL holds exactly what is set.
- *Stereo separation:* -1..+1 in steps of 1/64, so values snap by up to about 0.008. Which direction narrows and which widens is left to the renders.
- *Parametric EQ 2 (36 parameters):*
  - Parameters 0–6 are the band levels and 35 is the main level. All are linear, ±18 dB, with 0.5 = 0 dB.
  - Parameters 7–13 are the band frequencies, logarithmic: Hz = 20 · 1000^x.
  - Parameters 14–20 are the band widths, shown as 0–100%. Their relation to Q is left to the renders.
  - Parameters 21–27 are the band types, in steps of 1/7: Disabled, Low pass, Band pass, High pass, Notch, Low shelf, Peaking, High shelf.
  - Parameters 28–34 are the band orders (slopes), in steps of 1/6: Steep 8, Steep 6, Steep 4, 2 (default), Gentle 4, Gentle 6, Gentle 8.
- *Defaults:* band 1 is a low shelf, bands 2–6 are peaking, and band 7 is a high shelf, all at 0 dB. A band whose type is "Disabled" does nothing, which gives the engine a clean "unused band".

**D58 — Bridge replies come back on "Zosimix In"; supersedes D56's FL-side fix** · 2026-11-25 · accepted
- *Found:* FL links a script's input to the MIDI output **of the same name**, and restores that link every time it starts. Clearing the port on the "Zosimix In" output by hand, or even in the registry with FL closed, is undone at the next launch. With D56's separate reply header that is harmless: the script ignores its own looped-back replies, and loopMIDI delivers them to us on "Zosimix In" too.
- *Change:* the client sends on "Zosimix In" and reads replies from both "Zosimix In" and "Zosimix Out". It ignores everything that isn't a reply, including its own requests echoed by loopMIDI. D56's instruction to give only "Zosimix Out" the port is withdrawn.
- *Preflight:* before launching FL, `session.check_midi_settings` reads FL's MIDI settings from the registry. It requires the "Zosimix In" input to be enabled with the Zosimix Bridge script and a port number, and some Zosimix output to share that port. It only reads; Zosimix never changes FL's settings itself. (While diagnosing this, the port on the "Zosimix In" output was cleared once in the registry, as the owner had asked in FL's own dialog. FL restored it at its next start.)

**D59 — The FL cycle, and what it costs** · 2026-11-25 · accepted
- *Cycle (`zosimix.fl.session`):*
  1. Copy the template into `C:\zosimix\fl\work`.
  2. Launch FL on the copy.
  3. Wait until the bridge answers and insert 1 holds Parametric EQ 2.
  4. Set values over the bridge.
  5. Switch to song mode.
  6. Save.
  7. Close FL gracefully.
  8. Render the saved copy with `FL64.exe /R /Ewav /O<folder>`.
- *Song mode is required:* the command-line render plays the mode the project was saved in, and in pattern mode that is one empty bar (1.71 s at 140 BPM).
- *Safety:* refuse to start while any FL64.exe is running, because FL is single-instance and would hand our project to the owner's window. Only ever stop the process IDs we started; close gracefully first, and force only our own process as a fallback.
- *Cost, measured:* about 2 s to launch and connect, 1 s to save, 0.5 s to close, and 3 s to render a 10 s project. A 60 s calibration project takes about 9 s from start to finish. The 80 s from the spike (D35) was the heavy demo song, not FL startup. That makes mid-run FL renders much cheaper than D36 assumed. D36 stays as it is until real songs are timed.
- *Render facts:* 24-bit, 44.1 kHz, no latency (lag 0 samples). A clip takes the length of whatever WAV is in its slot, so the render is as long as the longest stem.

**D60 — Audio calibration: what FL's controls do** · 2026-11-25 · findings accepted; engine changes pending the owner's call
- *Method (`zosimix.fl.calibrate`):* each slot plays its own 2 s burst of stereo noise in its own time window, and insert k gets setting k. So one render measures 24 settings. Per window we fit a 2×2 matrix (out = in @ M) and the magnitude response from 20 Hz to 20 kHz. The data is in `fl_bridge/calibration/audio-{mixer,pan,eq}.json`. Matrix residuals of about −92 dB are 24-bit rounding.
- *Exact matches with the offline engine:*
  - Unity is 0.9998 (−0.002 dB).
  - The fader's displayed dB is the real gain (−12 → 0.2512, +3 → 1.4123, maximum +5.59 dB).
  - PEQ2's main level is exact (+6 → +6.00 dB).
  - Polarity is an exact sign flip.
  - **Channel-rack pan is exactly `audio.pan_gains`**, a constant-power balance with no crossfeed (all 7 positions within 0.01 dB).
- *Mixer pan is not a balance:* it moves one channel into the other. For p ≤ 0: L→L = (√2·cos θ + cos(pπ/2))/2, R→L = (√2·cos θ − cos(pπ/2))/2, R→R = √2·sin θ, with θ = (p+1)·π/4; p > 0 is the mirror image. The formula fits 8 positions to within 0.0002. **Decision:** the FL engine realizes the mix state's pan with the channel-rack pan, and leaves the mixer pan at centre.
- *Stereo separation is pure mid/side scaling,* the offline engine's width:
  - For sep ≤ 0, width = 1 − sep (exact).
  - For sep > 0, it is a smooth curve with no obvious formula (0.125 → 0.944, 0.5 → 0.691, 0.875 → 0.228, 1 → 0).
  - FL moves the knob in steps of 1/64, so the engine uses a measured table of all steps.
- *Order matters for one pair:* FL applies the channel pan *before* the mixer insert (EQ, separation, fader). The offline engine applies width before pan, and the two don't commute. Polarity, EQ and gain commute with everything.
- *PEQ2 peaks and shelves are analog-matched:* one Q per width fits the ideal analog shape at 100 Hz, 1 kHz and 8 kHz (Q 0.664–0.692 at the default 39%, within 0.37 dB). Pedalboard's filters need a different Q at 8 kHz (0.40) than at 1 kHz (0.66) for the same setting, and still miss by up to 1.7 dB. Below about 4 kHz, pedalboard matches within 0.03–0.3 dB. Width maps to Q smoothly (peaks: 5% → 4.2, 20% → 1.3, 39% → 0.66, 100% → 0.16). Shelves follow their own curve.
- *PEQ2 high-pass and low-pass are resonant:* order "2" is 12 dB/octave, and the width knob sets the resonance (+4.5 dB at the cutoff by default, +10.9 dB at 20%, −11.7 dB at 70%). The offline engine's high-pass and low-pass are first order (6 dB/octave) and ignore Q. The other order settings need more measurement.

**D61 — The offline engine and the faults follow FL: matched EQ filters, pan before width** · 2026-11-25 · accepted (owner's call after D60)
- *Why:* the offline engine previews every commit (D36) and must sound like FL, and the faults must be undoable with FL's own controls. D60 showed two gaps: pedalboard's EQ drifts from PEQ2 near the top of the spectrum (up to 1.7 dB at 8 kHz, inside the 300 Hz–8 kHz range of resonance faults), and the offline engine applied width before pan while FL does the opposite.
- *EQ (`zosimix.eq`, shared by `faults` and the offline engine):* each band is a magnitude-matched biquad (Vicanek 2016). It maps the analog poles exactly and picks the zeros so the response equals the analog one at 0 Hz, at Nyquist and at the band frequency.
  - The meaning of gain and Q stays the Audio EQ Cookbook (RBJ) one that pedalboard uses, so below about 4 kHz nothing audible changes.
  - Against FL's measurements, one Q per width now fits at 100 Hz, 1 kHz and 8 kHz (Q 0.667 at the default 39%), within 0.33 dB from 20 Hz to 20 kHz. Low and high shelves share one width→Q curve.
  - Every filter stays within 0.06 dB of the ideal analog shape. The exception is a low-pass's roll-off above about 15 kHz, which drifts by up to 0.9 dB where it is already 20 dB down; FL's does too.
  - A boost undone by the mirror cut leaves −45 dB or less in the worst case (12 dB, Q 8, 8 kHz), and −76 to −117 dB below 2 kHz. The −40 dB guarantee from D43 holds.
- *High-pass and low-pass become second order (12 dB/octave), like PEQ2's default slope, and Q now sets the bump at the cutoff (0.707 = none).* Before, they were first order and ignored Q. With the fitted Q they match FL within 0.27 dB (high-pass) and 1.4 dB (low-pass, near 17 kHz). The tool description and the plain-baseline prompt say so.
- *Processing order:* polarity → EQ → **pan → width** → gain, replacing D43's order. FL applies the channel-rack pan before the mixer insert's stereo separation, and those two don't commute.
- *Effect on the benchmark:* the task specs, which hold the ground truth, are unchanged; `smoke.json` and `full.json` regenerate byte-identical. The audio of resonance and mud faults changes slightly near the top of the spectrum, because the fault filter changed. That counts as a change to how faults are applied, so the commit message calls it out. Smoke runs 1–3 used the old filters; they aren't rerun, because the gaps were in judgement, not in the last fraction of a dB.
- *Still to do for the FL engine:* dense width→Q tables per band type and every 1/64 step of stereo separation (day 10).

**D62 — Fixes from the codebase review** · 2026-11-25 · accepted (owner: "fix all 7")
- *Fader (`fl.controls.set_fader_db`):* bisection now covers the fader's whole travel, and it raises instead of returning a value it never reached. Before, it searched only ±0.01 around the probe table's guess. The table stops at −42 dB but the mix state allows −60, so a −60 dB request would have stopped near −47 dB without an error.
- *Render (`fl.session.render`):* done now means FL exited by itself. A WAV that stopped growing counts only after 60 s, as the fallback for an FL that finished but stayed open. Callers pass `min_seconds`, and a shorter render raises. Before, 5 s without growth counted as done and FL was then killed, which could have accepted a render cut short.
- *Launch (`fl.session.FLSession`):* a message lost while FL loads the project is retried, and every connection that isn't kept is closed. Before, one lost reply aborted the launch and left MIDI ports open.
- *Default Q:* `EqBand.q` left out means 0.707 for highpass/lowpass (no bump at the cutoff) and 1.0 for the other types. This applies to the tools, the MCP server and hand-written mix states alike. Before, a high-pass without q got a +1.25 dB bump, because D61 made Q matter for these filters.
- *Runner timeout:* the agent starts in its own process group, and a timeout stops the whole process tree (`taskkill /T /F`). Before, only `claude` was killed, and its MCP server child kept running with the workspace open.
- *Runner answers:* diagnosis.json and mix_state.json are read separately. A broken mix state now counts as "no changes" (D50) instead of also discarding a valid diagnosis.
- *Polarity picker (task generator):* `faults._polarity_candidates` now measures lost low end with `analysis.lowpass_mono`, the same brick-wall 500 Hz low-pass the grader and the `phase` tool use, instead of pedalboard's first-order filter. Checked on all 7 songs: the candidate stems are identical, and `smoke.json` and `full.json` regenerate byte-identical. The offline code no longer uses pedalboard; the plain baseline still gets it in its own Python.

**D63 — The FL engine and its calibration tables** · 2026-11-25 · accepted
- *Engine (`zosimix.engines.fl.FLEngine`):* one render is one FL cycle (D59). The stems go into the template's slots, every insert is set over the bridge, FL saves and closes, and the command line renders. A 4-minute, 13-stem song takes about 16 s. Per-stem renders aren't possible in FL, so `render_stems` refuses, and the agent's previews stay on the offline engine (D36).
- *Mapping:*
  - **Gain:** the insert fader goes as close as it can. It tops out at +5.59 dB and holds only certain positions (−11.9986 dB for −12). The exact remainder goes on PEQ2's main level, which takes exact values.
  - **Pan:** the channel-rack pan (exactly `audio.pan_gains`, D60). The mixer pan stays centred.
  - **Polarity:** the insert switch.
  - **Width:** the nearest 1/64 step of stereo separation, matched to within about 0.008.
  - **EQ:** PEQ2 bands 1–7 in order, with unused and neutral bands disabled. Q is converted to PEQ2's width knob through the measured tables.
  - **Master:** pulled down 12 dB while rendering, so a loud mix can't clip FL's 24-bit file. The render is scaled back by the master level FL reports, and divided by FL's constant 0.99984 on every path.
- *Calibration tables (`fl_bridge/calibration/mapping.json`, built by `python -m zosimix.fl.calibrate table` from 6 more renders):*
  - **Width→Q:** 24 widths for peaking, 20 for shelves, and 12 each for high-pass and low-pass. Q is fitted per width against `zosimix.eq` from the full-resolution response. Fits are within 0.17 dB for narrow peaks, 0.49 dB for the widest peak, 0.07 dB for shelves, and 1.2 dB for high-pass. Low-pass is within 1.45 dB, all of it in the deep roll-off.
  - **Shelves:** their Q depends slightly on gain (−12 dB at the default width fits Q 0.876, against 0.842 at +6). The table is built at +6 dB; the error elsewhere is a few hundredths of a dB.
  - **Stereo separation:** all 63 positive steps were measured. The mid level is exactly constant, so separation is pure width.
- *Action space narrowed to what FL can make (consistent with D12):* Q is now limited per type. Peaking 0.2–14 (FL: 0.18–14.4), shelves 0.41–1.04 (FL: 0.40–1.05; PEQ2 has no resonant shelves), high-pass/low-pass 0.1–6.5 (FL: 0.07–6.8). Before, every type allowed 0.1–18. The faults use Q 8 (resonance) and Q 1 (mud), well inside the range. The tool description and the plain-baseline prompt list the ranges.

**D64 — Parity check: FL and the offline engine agree** · 2026-11-25 · accepted
- *Method (`python -m zosimix.fl.parity`, results in `results/parity.md`):* one task per song from the full set (7 songs, all 7 fault types). The faulty stems are built exactly as the agent receives them, and four mix states are rendered on both engines:
  - **neutral:** the mix as handed over
  - **repair:** the ideal fix
  - **busy:** six stems using gain past the fader's range, cuts, pan, width both ways, polarity, and peaking, shelf and high-pass bands
  - **lowpass:** a low-pass on one stem
- *Tolerances, set before the results:* a residual of −40 dB or less relative to the mix, every one of the 8 analysis bands within 0.1 dB, and loudness within 0.05 LU.
- *Results: 27 of 28 pass.*
  - Neutral and repair, all 7 songs: residual −77 to −116 dB, bands identical. This is the case that matters for grading: on a handed-over or properly repaired mix, FL and the offline engine produce effectively the same audio.
  - Busy, all 7 songs: −56 to −67 dB, bands within 0.02 dB.
  - Low-pass: band levels match within 0.1 dB on 6 of 7 songs, and one sits exactly on the limit (0.100 dB). The waveform residual is −21 to −50 dB.
- *The known exception: PEQ2's low-pass phase.* Its magnitude matches `zosimix.eq` (D63), but its phase lags by about one sample at high frequencies. A least-squares fit of FL's response shows a nearly symmetric numerator. A symmetric-numerator model matched FL better at low cutoffs (−38 dB at 500 Hz) but not at 9 kHz (−17 dB), and even a free five-coefficient biquad fit reaches only −30 to −35 dB. So FL's low-pass isn't a plain biquad, and modelling it further isn't worth it now. No fault needs a low-pass, and graders judge EQ repairs by spectra. A low-passed *healthy* stem already fails collateral on either engine. Low-pass rows are judged on the spectrum only, and the report says so.
- *What this settles:* grading with the offline engine (D36) is faithful to FL for everything except a low-pass's phase. An earlier run found that the low-pass, inside the busy state, was why 4 of 7 busy renders failed; it was then split into its own state.
- *Smaller fixes found on the way:* FL renders a few samples short (35 samples on a 243 s song), so `session.render` allows 10 ms of slack. A track's fader is finished exactly with PEQ2's main level (D63).
- *Cost:* each FL render takes 12–17 s per song, so the whole check (28 FL renders) takes about 8 minutes.
- *Citations:* `results/parity.md` ends with the MoisesDB and AlbumDB citations, read from `CITATIONS.md` so they stay identical, as CLAUDE.md requires for results pages. The earlier `results/smoke-1..3.md` lacked them and now have the same block.

**D65 — Setting up the full run** · 2026-11-25 · accepted
- *Runner home moves to `C:\zosimix`* (runs, workspaces and the baseline Python, beside the FL root `C:\zosimix\fl`). The Claude desktop app redirects writes under `%LOCALAPPDATA%` into its own sandbox folder (`...\Packages\Claude_...\LocalCache\Local`), so a run started from the app and one started from a terminal would land in two different places, and resuming would silently start over. `C:\zosimix` isn't redirected, and it is still outside the repo and away from the workspaces (D51). The three smoke runs were copied over; `ZOSIMIX_HOME` still overrides.
- *Plain baseline's Python:* `C:\zosimix\baseline-venv` (Python 3.11) with the same library versions the harness uses: numpy 2.4.6, scipy 1.17.1, soundfile 0.14.0, pyloudnorm 0.2.0 and pedalboard 0.9.26. The runner prints the exact commands if it's missing.
- *Plain baseline isolation:* `--restricted` confines the file tools to the workspace; Bash stays because `--tools` names it. This is an extra layer on top of D51's scans, still not a sandbox.
- *Model:* the default is the full id `claude-sonnet-5-5`, not the alias `sonnet`, so an alias change can't mix models within one run. Sonnet 5.5 produces the headline numbers (DESIGN §4.6).
- *Order:* repeats are now the outer loop. Every task gets its first run before any gets a second, so a run cut short by a usage limit still holds one complete pass.
- *Provenance:* each start or resume appends to `run_info.jsonl` the commit, whether there were uncommitted changes, the set, configs, repeats, model and CLI version.
- *Plan for the first full run (`full-1`):* the 30-task full set × `zosimix` and `plain` × 3 repeats = 180 runs. The third configuration (Claude Code + rosasynthesiz/flstudio-mcp, DESIGN §4.6) isn't included yet: it means downloading and installing third-party code, which needs the owner's OK, and grading it needs the final mix read back from FL. It will be added to the same run id as a further config. Check runs on full-003 (pan): both configs passed in 22–42 s at about $0.04–0.06 API-equivalent, so the whole run should be roughly $10 equivalent and about 2 hours. The plain run's transcript was read by hand: a level meter written in Python, not a leak.

**D66 — The third baseline: flstudio-mcp, ported to FL 20.9.2** · 2026-11-25 · in progress (owner chose "port it")
- *What:* rosasynthesiz/flstudio-mcp (MIT licence), the existing FL MCP that DESIGN §4.6 names, at commit `2b2d664`. It is cloned to `C:\zosimix\baselines\flstudio-mcp` with its own Python 3.11 environment and no optional extras. The code was read before installing it. It makes no network calls; it starts subprocesses only for a process check and macOS-only commands; on Windows it sends keystrokes to FL's window only to trigger piano-roll scripts.
- *It doesn't run on FL 20.9.2 unmodified.* It is built for FL 2025+ (scripting API 40), and its FL script fails at `import base64`: FL 20.9.2's Python has neither `base64` nor `json`. A probe through our bridge (a new read-only `has` command) checked all 5 modules and 100 FL functions the script uses. Missing: only `base64` and `json`, plus 3 FL functions for pattern and arrangement editing (`arrangement.selectionIsActive`, `patterns.clonePattern`, `ui.getStepEditMode`).
- *The port (`zosimix.fl.port_flstudio_mcp`):* the only change is that `import base64` / `import json` fall back to `fl_bridge/flstudio_mcp_compat.py`. That file is a small pure-Python JSON encoder and parser, plus base64 through `binascii`, which FL 20.9.2 does have. The builder checks the upstream file's hash (line endings normalized, equal to the committed blob) and keeps FL's `# name=` header first. Tests show the stand-in matches the standard library's output on varied data, and that the ported script equals upstream's byte for byte apart from the import block.
- *Tested against FL 20.9.2 with their real MCP server* (our FL instance; our bridge checks the results). Connection, `fl_ping` (reports "Producer Edition v20.9.2"), mixer state, `fl_set_mixer_pan`, `fl_plugin_list`, `fl_plugin_find_params` and `fl_plugin_set_param` on Parametric EQ 2 all work, and FL holds the values. FL's same-name output link (D58) didn't get in the way; their default ports work.
- *An upstream bug, kept as is:* `fl_set_mixer_volume(unit="db")` converts with position = 0.8 × 10^(dB/20), so −6 dB lands at −12.67 dB on FL's real fader curve. Its dB readouts are wrong the same way: a true −6 dB shows as −2.5 dB. The formula's maximum (+1.9 dB) doesn't match any FL fader (+5.6 dB), so this looks like a bug in every version, not a porting artefact. The port changes only what's needed to load, so the bug stays. It is the tool as it ships.
- *Fairness choices (planned):* the agent gets only flstudio-mcp's mixing tools (mixer, channels, plugin parameters, meters, transport, mix doctor, EQ intent, snapshot and rollback). Not the composition tools, which send keystrokes to FL, nor `fl_screenshot`, which can capture the desktop. Its meters and mix doctor need the song playing, which is audible on this machine.

**D67 — full-1 interrupted by a scanner crash, fixed and resumed** · 2026-11-25 · accepted
- *What happened:* after 71 of 180 runs (all of repeat 1, 11 of repeat 2), the integrity scan crashed on `full-006-plain-2`. That transcript holds a `permission_denied` event, where dontAsk mode refused one Bash command, and the event's `message` is a string, not an object. The crash stopped the run before the row was written, so the resume redoes that run.
- *Fix:* the scan skips any event whose `message` isn't an object (test added with the real event). It changes no flag that was raised before.
- *Is dontAsk handicapping the plain baseline?* No: 1 refused command in 36 plain transcripts. It was an unusual command that tried two Pythons in a row, and the agent carried on another way.
- *Provenance:* the resumed part runs from the fix commit; `run_info.jsonl` records both commits.

**D68 — full-1 results** · 2026-11-25 · accepted
- *Result:* the harness (`zosimix`) passed 42/90 runs (47%), plain Claude Code 27/90 (30%), on Sonnet 5.5 over 30 tasks × 3 repeats. Without the three smoke-overlap tasks it is 36/81 against 23/81. By task, the harness did better on 9 and worse on 2 (sign test p ≈ 0.065). The harness also changed healthy stems far less often (11 runs against 30). Full page: `results/full-1.md`.
- *Where the gap comes from:* clipping (12/12 against 4/12), gain (4/12 against 0/12) and polarity (8/15 against 5/15). Pan and the no-fault controls are about even.
- *Benchmark finding:* mud (0/15 each) and resonance (0/12 each) are at the floor for both configs. On mud, the harness answered `no_fault` every time, because the injected 1.2–2.1 dB band-shape errors look like normal variation to its tools. Until either the fault sizes or the tools change, these two families can't separate configs. Which one to change is open, and a generator change would be called out as an eval-integrity change.
- *How the numbers are reported:* Wilson intervals over runs, labelled as overstating certainty because repeats are correlated, plus the paired sign test by task.

**D69 — Mud and resonance sized by their effect on the mix; full set revised to `full-v2`** · 2026-11-25 · accepted (owner chose "size by mix effect" and "replace 9, rerun 9")
- *Why:* in full-1 neither config passed any mud or resonance task (D68). Measuring the injected faults showed why: they barely changed what a listener hears. Across all 7 songs and every eligible stem, a severe (9 dB) mud boost moved the mix's low-mid share by a median 0.25 dB, a subtle one by 0.05 dB. On the full set's 9 tasks, the mix moved 0.0–0.8 dB. Two causes: the stem often plays a small part in the mix (an outro guitar audible 15% of the song), and resonance frequencies were drawn anywhere within 30 dB of the stem's loudest point, often in a dip between harmonics where a boost has nothing to ring with (full-004: a 12 dB boost only brought a −8 dB dip up to the level around it).
- *New rule (`faults._choose_eq_fault`):* severity is how much the fault raises its band *against the rest of the mix*: mud 1 / 2 / 3 dB in the low-mid band (150–400 Hz), resonance 2 / 4 / 6 dB in the 1/3 octave around the peak. The generator tries stems in random order, draws up to 3 frequencies on each, and solves by bisection for the smallest filter gain (to 0.1 dB) that reaches the target. Filter gain is capped at 12 dB (mud) and 18 dB (resonance): a stem that needs more plays too small a part in the mix to carry the fault. Resonances go on the stem's own peaks (local maxima of its 1/6-octave-smoothed spectrum, 300–8000 Hz, within 30 dB of its loudest point). The achieved mix change is stored as `mix_rise_db` in the fault's params (ground truth, like the rest).
- *Band against the rest, not share of the total:* the first version measured the band's share of the mix's total energy. One song's low-mids already hold almost half its energy, so a share can't rise 3 dB there. Band against the rest of the mix has no ceiling.
- *`full-v2`:* `python -m zosimix.tasks revise --from full --set full-v2 --seed 69`. The 21 tasks of other types are copied unchanged (same song, fault, stem, size and hint). The 9 mud and resonance tasks keep their song, severity and hint level and are redrawn under the new rule. Task numbers are kept (`full-002` → `full-v2-002`). The redrawn faults use boosts of 4.3–12 dB (mud) and 15–17 dB (resonance), and change the mix by their target.
- *Graders unchanged.* Repair is still the fraction of the stem's band-shape error removed. On the 9 new tasks, an exact counter-cut scores 0.99–1.00, half a counter-cut scores 0.29–0.58 (fail), and no change fails. On snare and viola the stem's band-share error is small (0.21 and 0.62 dB) because those bands already dominate the stem, but the ratio still separates good repairs from partial ones.
- *Reruns:* the runner gets `--tasks` to run only listed task ids; `run_info.jsonl` records the list. Run `full-2` covers the 9 new tasks × 2 configs × 3 repeats. Results on `full-v2` combine full-2 for those 9 with full-1 for the 21 unchanged tasks.
- *Left alone:* `tasks/full.json` stays as full-1's record; it can no longer be regenerated from `generate` at this commit, because the mud and resonance sizes changed. The smoke set keeps its old mud task, since it is only used for tuning. The harness's tools aren't changed: tuning them on full-set failures would leak the test set into the harness.

**D70 — The flstudio-mcp configuration (`flmcp`), graded from FL renders** · 2026-11-25 · accepted (owner: "Yes, set it up", then "Mud/resonance first, and then FL-MCP")
- *What the agent gets:* the task's stems (one faulty) are written into the template's slots, FL opens a fresh copy, and each used insert is named after its stem (`zosimix.fl.baseline.open_task`). Faders, pans and the flat Parametric EQ 2 in slot 0 stay as the template has them. The workspace holds only the brief and `output/`: the agent meets the song through FL. The prompt lists the inserts, says the mix left in FL is the fix, that meters only move during playback, and to leave the master alone; the agent writes `output/diagnosis.json` with the same schema as the plain baseline.
- *Tools:* 44 of flstudio-mcp's 91 tools: reading the mix, faders, pans, mutes and solos, plugin parameters and the EQ intent, meters, Mix Doctor and gain staging, transport, snapshots and rollback, and read-only routing. The other 47 go to `--disallowedTools`, which removes them from the agent's view: composition and arrangement, tempo, audio-file analysis and reference matching, routing changes, renaming and colours, presets, plugin loading (FL's API can't load plugins anyway), reverb/delay/compression intents (no such plugin is loaded), dry-run and `fl_screenshot` (it can capture the desktop). Built-in tools: only `Write`, with `--restricted`. A test checks that the two lists together are exactly the server's tools at the pinned commit. There is no polarity or stereo-width control in flstudio-mcp, so polarity faults can't be fixed through it: that is the tool as it ships.
- *Reading the mix back (`read_back`):* FL renders only whole mixes, so after the agent stops, the agent's mix is rendered in groups with every track outside the group muted. `graders.render_groups` names them: the faulty stem (for polarity, the acceptable drum mics), all other stems, and for polarity the remaining drum mics. The pieces add up because the mix is linear (faders, pans, Parametric EQ 2), so the whole mix is the sum of the first two groups. Before rendering, playback is stopped, the agent's mutes are kept, and solos become mutes ("only these play"). The master is set 12 dB down for every grading render, as in the FL engine, whatever the agent did to it. The agent's mutes, solos and master level are recorded in the row as `fl_agent_state`.
- *Graders refactored, scoring unchanged:* `grade` (mix state, offline engine) and the new `grade_renders` both fill a `Rendered` record (whole mix, the others, the faulty stem, the drum bus) and score it with the same `_score`. `touched_other_stems` is `null` for flmcp, since FL can't say which settings changed. Checked three ways. First, all 180 full-1 answers regraded with the refactored code give identical grades. Second, unit tests show that exact group renders give the same grade as the mix state for gain, polarity, clipping and control tasks. Third, a live FL check without an agent: known fixes made over our bridge (a control left alone, a −10 dB fader on a +10 dB gain fault, a polarity flip on a three-group task) all passed, with the other stems matching to −109 to −113 dB.
- *Bridge additions:* `get_mute`/`set_mute`, `get_solo`/`set_solo` and `stop`. On FL 20.9.2, `mixer.muteTrack(track)` without a value doesn't toggle (like `revTrackPolarity`), and FL applies a mute a moment after the call. So mutes are written with an explicit value, polled until FL holds them, retried up to 3 times (the first mute of one session was dropped), and the read-back waits 1 s for the agent's last change to land.
- *Integrity scan:* the `"severity":` marker now needs a number after it. flstudio-mcp's Mix Doctor labels its own findings `"severity": "low"`, which raised three false flags on the first agent run. Ground truth stores severity as 0–2. Rescanning all of full-1 changes no flag. Task files are now forbidden by prefix (`tasks/full`, `tasks/smoke`), so `tasks/full-v2.json` is covered.
- *A failed FL cycle* (`FLError`/`BridgeError`) gives an ungraded `fl_error` row and stops the run, like a usage limit: it is about the setup, not the agent, and it tends to repeat.
- *First agent run (full-v2-020, +10 dB on a backing vocal, no hint):* 92 s, 25 turns. The agent played the song, used the peak watch, Mix Doctor and gain staging, then cut the bass by 17 dB on Mix Doctor's "clipping" finding and named the bass. That's a fail on detection and collateral. Its meter readings disagreed with each other: the watch reported the bass peaking at +11.6 dBFS, while its own level reading showed −5.7 dB. `fl_apply_mix_fix` returned `applied: false`. These are flstudio-mcp's behaviours, left as they ship (see D66 on its fader formula).
- *Playback is audible* on this machine whenever the agent presses play.

**D71 — full-v2 results with all three configurations** · 2026-11-26 · accepted
- *Result:* on full-v2 (30 tasks × 3 repeats, Sonnet 5.5) the harness passed 46/90 (51%), plain Claude Code 31/90 (34%) and flstudio-mcp 12/90 (13%). By task, harness vs flstudio-mcp is 15 better, 0 worse (sign test p < 0.001); plain vs flstudio-mcp 13 to 1 (p ≈ 0.002); harness vs plain 10 to 4 (p ≈ 0.18). Page: `results/full-v2.md`.
- *How the rows combine:* `zosimix` and `plain` take full-1 for the 21 tasks that full-v2 kept unchanged and full-2 for the 9 redrawn ones; `flmcp` ran all 30 in `full-2-flmcp`. That run was paused once at 20 of 90 at the owner's request and resumed the next day from the same commit; the interrupted task left no row and was redone.
- *"Damaged healthy stems"* on the page is the others-residual test (worse than −30 dB) for every config, because FL can't report which settings changed. It replaces the "touched other stems" count used in D68.
- *Why flstudio-mcp scores low:* its agent can only read levels: one peak per track, with no left/right split, spectrum or phase. It named the right fault 0 times in 39 pan, polarity and clipping runs. It placed resonance cuts by guesswork (repair at most 0.05). It worked on a 6 dB gain fault (repair 0.93 in all 3 runs), and it left 10 of 12 healthy mixes alone.
- *Mud stays at 0/45* for everyone after the redraw: agents now find the stem more often, but cut 4–9 dB against 8–12 dB boosts (D69 follow-up, checked: the grader's measure isn't the cause). Resonance moved from 0 to 4/12 for both Claude Code configs.
- *Also weak for everyone:* the smallest gain (3 dB) and pan (0.3) faults, 0 of 36 runs.

**D72 — Raising scores honestly: oracle check, dev set, `scan`, targeted rerun** · 2026-11-26 · accepted (owner: "do all of these but don't run a full run and do targeted runs instead, keep it fast")
- *Method:* tune only on a development set, measure once on the test set. `full-v2` is the test set. The test-set measurement reran only the 17 tasks the changes target (harness, 3 repeats). The other 13 tasks keep their earlier results. Page: `results/harness-v2.md`.
- *Oracle check (`zosimix.oracle`):* ranks the faulty stem on the measurement that fits each fault, with no agent runs. On full-v2 it puts the faulty stem first for clipping 4/4, polarity 5/5, pan 3/4 and mud 3/5, but resonance 0/4 and gain 0/4. So the polarity, pan and mud failures are about how the agent uses the tools. Gain without a reference is a real ceiling: even a 10 dB fault isn't singled out.
- *Dev set:* AlbumDB songs 02 and 08 (owner approved the ~2 GB download), in `data/dev_songs`. They're kept apart from `data/songs` so the leave-one-out tonal targets on test tasks don't change. `find_song` searches both folders. `tasks/dev.json` holds 18 tasks, 3 per type; there are no polarity tasks, because these songs have no qualifying drum mics. The generator gained `--songs-root` and `--types`.
- *Findings on dev songs (injected faults, no agent):*
  - A resonance cut sized at the reported height passes 11%; twice the height passes 78%. The detector finds the right bump 94% of the time.
  - A centre-excluded detector is worse (0% ranked first, against 17%), so it is not used.
  - The best reference-free mud policy passes about 44% even given the right stem.
  - Clean mixes balance within 0.13 dB even with stems panned on purpose.
- *Changes:*
  - **Tool:** `scan` ranks every stem on one measure in one call. `peaks` gives each stem's strongest bump. `lowmid` gives its low-mid excess against the rest of the stem, compared with the family's typical value, plus a suggested 300 Hz cut. It is listed in the MCP instructions.
  - **Skill:** cut resonances by about twice the reported height; use `scan` for mud and resonance; look for pan faults only when the MIX leans (more than about 0.5 dB) or the client says the image is lopsided; treat mud as a fault only with a muddy note.
  - **Reports:** a partial-credit average.
- *Dev results (one repeat):* before 8/18 (partial 0.50); first version 6/18 (0.33), where the looser mud and pan rules cut a naturally heavy acoustic guitar and re-centred toms panned on purpose; final version 10/18 (0.56).
- *Test result (targeted):*
  - Resonance improved from 4/12 to 8/12.
  - Two controls from one song (full-v2-019, -026) dropped from 6/6 to 0/6. Its clean guitar has a natural 8.5 dB bump at 732 Hz, which `scan peaks` surfaces and the agent cut.
  - Whole set: 46/90 → 44/90 (partial credit 0.53 → 0.50).
  - Reported as measured; the regression is not fixed on the test set.
- *Opus 5.5* (harness before the changes, 12 test tasks, 1 repeat) passed 7/12 (partial 0.61), the same as Sonnet's 21/36 (0.62) on those tasks.
- *Open, for the owner:* gating resonance on a harsh or ringy note, like mud, would very likely undo the regression. Since the regression was seen on the test set, a rerun after that fix has to be labelled as tuned on the test set, unless the fix is first validated on a dev song with a natural standout bump.
