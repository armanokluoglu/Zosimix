# Zosimix — Design

> An agentic mix-repair harness for FL Studio, with a measured benchmark.
>
> *Zosimix: an agent that repairs mixes it can't hear, and a benchmark that proves it.* Named after Zosimos of Panopolis, the alchemist who wrote about distillation and the apparatus for purifying impure material (see D34).
> Status: design agreed 2026-11-24, nothing built yet. Decisions and their reasoning live in [docs/decisions.md](docs/decisions.md).

## 1. What this is

Claude can't hear. Zosimix gives it a way to "hear" a multitrack mix through measurement tools, lets it repair problems inside FL Studio, and then **measures** how well it did on a benchmark of injected faults with known ground truth.

Controlling FL Studio with an LLM is not new: there are community MCP servers and FL's own Gopher assistant. What has not been published is **an FL Studio benchmark built on injected faults, run in the real DAW and scored on rendered audio**, which compares a general-purpose agent against a specialized harness. The evals are the product. The agent is what they measure.

### Audience

- **Primary:** applied-AI engineering roles. The project shows tool design, context budgeting, verification, eval methodology, and guarding against reward hacking.
- **Secondary:** developer-tools and general SWE roles. The project shows an MCP server, an engine abstraction with a parity check, a resumable runner, and a clean repo.

### Headline claim, once results exist

> Same model, same tasks: plain Claude Code finds and fixes X% of injected faults, Claude Code + the existing FL MCP finds Y%, and Claude Code + Zosimix finds Z%. Here is which design choice earned each point, and the fault size at which each one starts to see the problem.

## 2. Constraints

| Constraint | Consequence |
|---|---|
| Budget = Claude Pro subscription only, no API spend | Claude Code is the agent loop, driven headless via `claude -p` with the subscription login. Never pass `--bare`, which switches to an API key. |
| Pro has 5-hour and weekly usage limits, shared between building and evals | Eval runs are tiered and resumable, and they run in quiet windows such as overnight. |
| FL Studio **Producer Edition 20.9.2** (scripting API ≈ v20, embedded Python 3.9) | No mixer-EQ API and no send-level API. The templates pre-load Fruity Parametric EQ 2 and the agent drives it through plugin parameters. |
| FL's script API cannot add plugins, load audio, open projects or render | The templates are built by hand. Faults are swapped in as WAV files. Rendering goes through FL's command line with a watchdog. |
| The builder directs Claude Code and does not hand-write the Python | The code must be clean and easy to explain. Milestone walkthroughs and a decision log are deliverables. |

## 3. Architecture

```
                 ┌───────────────────────────────────────────┐
  eval runner ──▶│ claude -p  (Claude Code = the agent loop) │
  (resumable)    │   + Zosimix skill (diagnosis playbook)    │
                 │   + commit_changes verification hook      │
                 └──────────────┬────────────────────────────┘
                                │ MCP
                 ┌──────────────▼────────────────────────────┐
                 │ Zosimix MCP server (Python)               │
                 │  perception tools │ action tools │ commit │
                 └──────┬───────────────────────┬────────────┘
                        │ MixEngine interface   │
          ┌─────────────▼─────────┐   ┌─────────▼──────────────────────┐
          │ Offline engine        │   │ FL engine                      │
          │ pedalboard + JSON     │   │ loopMIDI + SysEx ─▶ device     │
          │ mix state, ms renders │   │ script in FL 20.9.2; CLI render│
          └───────────────────────┘   └────────────────────────────────┘
```

### 3.1 Agent loop

We use Claude Code (`claude -p --output-format stream-json`) and do not write our own loop for now. The MCP server and eval harness stay agent-agnostic, so a custom Messages-API loop can be added later if API credit ever becomes available.

### 3.2 Zosimix layer: what makes it a specialized harness

1. **Perception tools.** These return compact numbers first, with detail on request, and each tool has a token budget for its output.
   - `overview`: LUFS, true peak, crest factor and stereo correlation for each stem and for the mix, plus energy in about 8 frequency bands for each stem.
   - Drill-downs the agent calls only when something looks off:
     - a fine spectrum for one stem over one frequency range
     - a masking matrix between two stems
     - polarity correlation between related stems
   - **Data-derived tonal target:** the average band balance of the held-out clean mixes. It gives the agent "what normal looks like" without relying on anyone's ears.
2. **Action tools.** A deliberately small set of about 10:
   - gain
   - pan
   - polarity
   - stereo separation
   - Parametric EQ 2 band settings (frequency, gain, Q, enable)
   - a `get_state` read-back
3. **`commit_changes` plus the verification hook.** The agent batches several moves and then commits. The hook re-renders, re-analyzes, and injects only a **difference report of at most about 150 tokens**: the metrics that moved past a threshold. A **hard rule** applies: the final diagnosis report is refused unless the last change was committed and verified.
4. **Diagnosis skill.** This is the playbook: what to check, in what order, how to tell a fault from an artistic choice, and when to answer "unfixable".
5. **Structured final output.** The agent ends with a JSON diagnosis: `[{stem, fault_type, confidence, actions}]`, or `unfixable`, or `no_fault`.

### 3.3 Engines: two engines behind one `MixEngine` interface

- **Mix state** is JSON, one entry per stem: `{gain_db, pan, polarity, stereo_sep, eq:[{freq, gain_db, q, on}]}`. The same object is also the human-readable "mix recipe".
- **Offline engine.** Applies the mix state to the stem WAVs with `pedalboard` and sums them. It is fast, deterministic, has no GUI, and can run in CI. Daily iteration happens here.
- **FL engine.** Converts the mix state into SysEx commands sent to a small `device_zosimix.py` script running inside FL.
  - Every write is read back to confirm it, because some parameters snap to steps or ignore writes.
  - Rendering uses `FL.exe /R /Ewav` with a watchdog that applies a timeout, kills the process, retries, and copies files to paths without spaces.
  - The script inside FL stays small. It runs in FL's restricted Python 3.9 and only does simple command dispatch. All the logic lives in the external MCP server, which runs on modern Python.
- **Calibration.** A script measures FL's fader curve, pan law and PEQ2 filter shapes, so the offline engine matches FL.
- **Same-results check.** Apply the same mix state on both engines, render both, subtract one from the other, and assert that the residual is below a tolerance on a subset of tasks.
- **Bridge.** We write our own minimal bridge and credit prior art such as rosasynthesiz/flstudio-mcp and Flapi. We don't fork those projects.

## 4. Benchmark

### 4.1 Data

- **MoisesDB**, about 5 songs with 8–12 stems each, is the core. Its stems sum exactly to the mix: a static balance with no bus processing and no mastering. License: CC BY-NC-SA 4.0.
- **AlbumDB**, 1–2 songs, mixed by real engineers. License: CC BY 4.0. It supplies all audio used publicly, including the demo video.
- When a song is loaded, the harness checks that the stems sum to the released mixture and rejects any song that doesn't.
- Raw dataset audio is never committed. The repo ships download scripts and task definitions only.
- **Framing:** the benchmark measures *restoring the intended state*, not *making it sound professional*.

### 4.2 Faults (v1)

Faults are **baked into one stem's audio** by the injector, and FL opens with a neutral mixer.

| # | Fault | Severities | Fix available | Graded by |
|---|---|---|---|---|
| 1 | Gain error | ±3 / 6 / 10 dB | fader | residual level error vs clean |
| 2 | Polarity flip on a correlated stem (multi-mic drums) | — | polarity | correlation and low-end energy restored |
| 3 | Narrow resonance at a random frequency | +4 / 8 / 12 dB | EQ cut | band spectral distance |
| 4 | Low-mid mud, a broad boost in the 200–400 Hz range | 2–3 levels | EQ cut | broadband spectral distance |
| 5 | Pan error on a centered element | 2–3 levels | pan | residual pan error |
| U | **Unfixable**: hard clipping | 2–3 levels | none. The agent must report it and must not fake a fix | did it say "unfixable" and leave the stem alone? |
| C | **Control**: no fault | — | none. The agent should change nothing meaningful | size of the changes it made (false positives) |

**Hint levels:** each task carries either a vague client note (for example, "vocals sound harsh") or no hint at all. The agent never gets the clean mix.

**Sampling:** a fixed seed picks from the song × fault × severity × hint grid, giving a **full set of about 30 tasks** and a **smoke set of 6**.

### 4.3 Why faults live in the audio, not in the mixer

If a fault were a bad mixer setting, the agent could simply *read* it through the API, and "reset everything" would score perfectly. Real problems live in recordings, so the agent has to diagnose from what it measures. Unfixable tasks test honesty, and control tasks test restraint.

### 4.4 One task, end to end

1. **Generate.** Song X, a resonance of +8 dB at 3.1 kHz with Q 6 on `vocals`, hint "vocals sound harsh", seed 42.
2. **Inject.** Python renders a faulty `vocals.wav`, and the other stems are copied clean. The ground truth (clean stems plus the fault spec) is stored **outside** the agent's workspace.
3. **Set up.**
   - In offline mode, the engine loads the stems.
   - In FL mode, the harness copies the stems to the fixed paths that the song's hand-built 20.9.2 template points to, then launches FL. The template has its faders at 0 dB and a flat PEQ2 on every track.
4. **Agent.**
   - `overview` shows the 2.8–3.4 kHz region of `vocals` sitting well above the tonal target.
   - A drill-down confirms a narrow peak.
   - The agent sets an EQ cut near 3.1 kHz.
   - `commit_changes` reports: "peak gone, nothing else moved".
   - The agent submits its diagnosis JSON.
5. **Grade.**
   - Did it name the right stem and fault type?
   - What fraction of the band error was removed?
   - What was the whole-mix distance from the clean render, and were other stems touched?
   - How many tokens and how much wall time did it use?

### 4.5 Grading

- Grading is **deterministic only, with no LLM judge.**
  - **Detection:** does the JSON diagnosis match the injected fault (stem and type)?
  - **Repair:** how much of the fault-specific metric recovered toward the clean render, with tolerances.
  - **Collateral:** whole-mix distance between the repaired render and the clean render, using a multi-resolution STFT and LUFS, plus any edits to unaffected stems.
  - **Cost:** tokens, number of turns and wall time. Pro hides the dollar cost, so these stand in for it.
- **Results charts:**
  - detection rate and fix rate per configuration
  - **detection by fault size**, one curve per configuration
  - unfixable honesty and control false positives
  - tokens per task
- The graders are the code interviewers ask about most, so they get the most careful milestone walkthrough (see D30 in the decision log).

### 4.6 Configurations (baselines)

1. Plain Claude Code (Python and shell, no audio tools)
2. Claude Code + rosasynthesiz/flstudio-mcp, the strongest existing alternative
3. Claude Code + Zosimix

**Sonnet 5.5** produces the headline numbers. One Opus 5.5 data point may be added later.

### 4.7 Running evals within Pro limits

- **Smoke set:** 6 tasks, Zosimix only, 1 run each. Run daily.
- **Full run:** all 3 configurations, about 30 tasks, at milestones. Each run spans several Pro windows. Use 3 runs per task when producing headline numbers.
- **The runner checkpoints after every task and resumes after a usage limit.** It records tokens and time per task.
- Building and evals share one quota. Build during the day and run evals in quiet windows. Check `/usage` before starting a full run.

### 4.8 Eval integrity

- Each run gets a **fresh workspace that contains only the faulted stems and the hint.**
- Ground truth lives outside the workspace, and Claude Code permission rules deny reads of that path.
- Graders flag any run whose log shows an attempt to reach the ground truth.
- The review subagent flags any commit that touches the graders, the task generator, the ground-truth layout, or anything else that could leak answers.

### 4.9 Blind listening (a sanity check, not a study)

- A tiny web page with a randomized A/B order compares clean, broken and repaired versions.
- The listeners are the builder, plus one friend if they are available.
- The page includes hidden control pairs (identical clips, and clean vs. badly broken) to measure listener consistency.
- It answers one question: "Do the metrics agree with ears?"

## 5. Ablations (week 3+)

Each one is measured as a difference in accuracy and in tokens per task.

- Verification hook on vs. off
- Spectrogram-image tool on vs. off (Claude has vision, but it's unknown whether images help)
- Tonal target on vs. off
- A "critical listener" subagent (deferred; not in v1)

## 6. Repository and process

- The repo is **public from day 1**, with frequent commits.
- Code is **MIT licensed**. Modified audio is CC BY-NC-SA, with attribution.
- `CLAUDE.md` holds the project conventions. Code is clean and explainable. Default tooling is uv, ruff and pytest.
- `docs/decisions.md` is the decision log, which doubles as interview prep.
- A **review subagent** reads commits, with an eval-integrity focus (see 4.8).
- **Milestone walkthroughs:** the builder reads the code after each milestone and asks clarifying questions. Nothing merges that cannot be explained.
- **README:** the demo video sits at the top, with the results chart directly under it. The README states plainly: "designed by me, implemented by directing Claude Code."
- **Blog post:** one technical post once the first full 3-baseline results exist, around week 3. Working title: "Building an eval for an agent that can't hear."

## 7. Plan (flexible)

| When | Milestone |
|---|---|
| Days 1–2 | **FL go/no-go spike.** loopMIDI plus a device script that sets a fader, polarity and a PEQ2 band and reads each one back. CLI render on 20.9.2 with a watchdog. *Fallback:* render through GUI automation, or make FL demo-only while the offline engine carries the evals. |
| Day 3 | Dataset download, stems-sum check, fault injector, seeded task generator |
| Day 4 | Offline engine plus the JSON mix state |
| Day 5 | Perception tools, tonal target, MCP server |
| Days 6–7 | Eval runner (`claude -p`, checkpoint and resume, 3 configurations), graders, first smoke run |
| Day 8 | Diagnosis skill and the commit/verify hook; iterate on the smoke set |
| Days 9–10 | FL engine behind `MixEngine`, calibration, same-results check, the 20.9.2 templates |
| Day 11 | Start the full 3-configuration run in the background, spread across Pro windows |
| Day 12 | Blind A/B listening page and the listening session |
| Days 13–14 | README, results chart, demo video |
| Week 3+ | Ablations, the blog post, v2 faults |

If time runs short, cut demo-video polish first. Keep the same-results check and the listening test, because they are what make the numbers credible.

## 8. Risks

| Risk | Mitigation |
|---|---|
| FL 20.9.2 CLI render is flaky. Known problems: spaces in paths, save prompts, renders that wait for a click, an `/O` flag that may not exist. | Days 1–2 spike, the watchdog, then the fallbacks in §7 |
| PEQ2 or other parameter writes snap to steps or are ignored | Read back after every write, plus calibration |
| Offline and FL engines diverge | Calibration, residual tolerances, and reporting headline numbers from FL |
| Pro quota contention | Tiered evals, a resumable runner, quiet-window scheduling |
| Datasets say "research use only" | Non-commercial repo, no raw audio committed, public audio from AlbumDB (CC BY) only. Reasonable but not certain; not legal advice. |
| Headless `claude -p` might default to `--bare` in a future release | Pin the CLI version and make the runner fail loudly if it falls back to API-key authentication |

## 9. Later (explicitly out of v1)

- v2 faults: stereo-width faults, compression faults, several faults in one task
- A custom Messages-API agent loop
- Applying a mix state to an existing user FL project
- A "critical listener" subagent
- An Opus 5.5 data point
- Upgrading the FL engine to FL 2026 (free with Lifetime Free Updates, and installs side by side)
