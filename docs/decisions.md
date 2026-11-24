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
