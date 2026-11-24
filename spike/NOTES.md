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
| CLI render, variant `plain` (`/R /Ewav project.flp`) | blocked: FL was already open | — |
| CLI render, variant `outdir` (`/O<folder>`) | pending | — |
| SysEx bridge: set/read fader, polarity, PEQ2 | pending (needs loopMIDI) | — |

## How to resume
1. Close FL Studio (save your work first).
2. `py -3.11 spike/render_test.py "C:/Program Files/Image-Line/FL Studio 20/Data/Demo projects/Product demos/nucleon - Harmless Galactic.flp" --variant plain`
3. Repeat with `--variant outdir`.
