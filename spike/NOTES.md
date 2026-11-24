# Day 1–2 spike: FL Studio go/no-go

Goal: prove that FL Studio 20.9.2 can be (a) rendered from the command line, unattended, and (b) controlled from outside over SysEx, with read-back. See DESIGN.md §7 and §8.

## Machine inventory (2026-11-24)
- FL Studio Producer **20.9.2.2963** at `C:\Program Files\Image-Line\FL Studio 20\FL64.exe`
- Existing hardware scripts in user settings: Arturia KeyLab/MiniLab, so MIDI scripting is already in use on this machine
- **loopMIDI: not installed** (needed for the SysEx bridge test)
- Windows MIDI Services (`midisrv`): not present
- Python 3.15.2 (default) and 3.11; **uv not installed**. The spike uses `py -3.11` with the standard library only

## Status
| Step | State | Result |
|---|---|---|
| CLI render, variant `plain` (`/R /Ewav project.flp`) | **pass** | WAV written next to the project. FL **exited by itself**, with no dialogs and no watchdog kill. 80 s wall time for a 132.5 s song, including FL startup. Output: 24-bit, 44.1 kHz stereo. |
| CLI render, variant `outdir` (`/O<folder>`) | **pass** | `/O` works on 20.9.2 (research had flagged it as uncertain). 82 s. |
| Determinism (same project rendered twice) | **inconclusive** | Not bit-identical. There is no time offset (best lag is 0 samples, correlation 0.927), and the residual sits 8.4 dB below the signal. The demo song contains synths and effects with randomness, so this says nothing about a stems-only project. Retest on the bridge test project. |
| SysEx bridge: set/read fader, polarity, PEQ2 | **pass (5/5)** | Scripting API version **20**, confirmed. Round trip over loopMIDI takes **1.7 ms median** (1.8 ms max, 30 calls). Fader, pan and polarity all work. **Mixer writes are applied after the script callback returns**, so the setter's own read-back is stale. A separate `get` sees the new value 1–2 ms later. Fruity Parametric EQ 2 exposes 36 parameters. All 22 continuous ones (level, frequency and width for 7 bands, plus main level) **take exact values**. The 14 stepped ones (band type, filter order) snap to the nearest step, which is the intended behaviour. None ignore writes, which contradicts an earlier community report about band widths. |

## Verdict: GO
FL Studio 20.9.2 can be driven from outside and rendered unattended. The FL engine stays in the plan as designed.

**Moved to days 9–10 (FL engine):** both remaining checks need the hand-built stem templates.
- Determinism of a **stems-only** project: render twice and run a null test.
- Whether a command-line render can run while the agent's FL session is open.

## Findings that affect the design
- **Rendering is GO.** Command-line rendering on 20.9.2 works unattended. The watchdog is kept as insurance.
- **About 80 s per FL render (mostly startup).** That is too slow to run on every `commit_changes`. Proposal: in FL mode, the verification hook renders the current mix state with the offline engine (milliseconds), and FL renders only once at the end for grading. This relies on the parity check (DESIGN §3.3) to keep the offline render honest. → log as a decision once confirmed.
- **Open question:** can a command-line render run while the agent's FL session is open (FL is single-instance by default)? The answer decides between "save → close → render" and a second instance.

## Bridge test setup (one time, by hand)
The bridge script is already copied to `Documents\Image-Line\FL Studio\Settings\Hardware\Zosimix\device_Zosimix.py`. The source lives in `fl_bridge/`.
1. Install **loopMIDI** from tobias-erichsen.de. Create two ports named exactly **`Zosimix In`** and **`Zosimix Out`**, and leave loopMIDI running.
2. Open FL Studio, then go to **Options → MIDI settings**:
   - **Input** list: select `Zosimix In`, tick **Enable**, set **Controller type** to **Zosimix Bridge (user)**, and set **Port** to **200**.
   - **Output** list: select `Zosimix Out` and set its **Port** to **200** as well. This is how the script's replies find their way out.
   - Optional: open **View → Script output**. It should print "Zosimix bridge ready, API version …".
3. In an empty project, put **Fruity Parametric EQ 2** in the **first slot of mixer Insert 1**.
4. Run `.venv/Scripts/python spike/bridge_test.py`. Everything it changes is restored at the end.

## How to resume
1. Close FL Studio (save your work first).
2. `py -3.11 spike/render_test.py "C:/Program Files/Image-Line/FL Studio 20/Data/Demo projects/Product demos/nucleon - Harmless Galactic.flp" --variant plain`
3. Repeat with `--variant outdir`.
