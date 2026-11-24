"""Spike: can FL Studio 20.9.2 render a project to WAV from the command line, unattended?

This answers the biggest open question in DESIGN.md §8 (risk #1). Standard library only.

What it does:
  1. Copies a project into a work folder whose path has no spaces (FL's CLI can't
     handle spaces in paths).
  2. Launches FL64.exe with the render flags.
  3. Watches the run with a watchdog. FL is known to sometimes render fine and then
     stay open (for example on a save prompt), so "done" means the WAV exists and
     has stopped growing, not that the process exited.
  4. Kills only the FL process this script started, never one the user had open.

Usage:
  py -3.11 spike/render_test.py "<path to .flp>" [--variant plain|outdir]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

FL_EXE = Path(r"C:\Program Files\Image-Line\FL Studio 20\FL64.exe")
WORK = Path(__file__).resolve().parent / "work"
TIMEOUT_S = 300          # give up after 5 minutes
STABLE_S = 8             # WAV size unchanged this long => render finished
POLL_S = 1.0


def fl_already_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FL64.exe"], capture_output=True, text=True).stdout
    return "FL64.exe" in out


def build_command(project: Path, outdir: Path, variant: str) -> list[str]:
    # The manual documents: FL.exe /R[filename] /E<ext> /F<folder> /O<outfolder> [project.flp]
    # Research says /O may not exist on 20.x, so we try two variants.
    if variant == "plain":
        return [str(FL_EXE), "/R", "/Ewav", str(project)]          # output lands next to the project
    if variant == "outdir":
        return [str(FL_EXE), "/R", "/Ewav", f"/O{outdir}", str(project)]
    raise ValueError(variant)


def newest_wav(folders: list[Path], since: float) -> Path | None:
    candidates = [p for f in folders if f.exists() for p in f.glob("*.wav") if p.stat().st_mtime >= since]
    return max(candidates, key=lambda p: p.stat().st_mtime, default=None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path)
    ap.add_argument("--variant", choices=["plain", "outdir"], default="plain")
    args = ap.parse_args()

    if fl_already_running():
        print("ABORT: FL Studio is already running. Close it first; this script never touches your own FL window.")
        return 2

    run_dir = WORK / f"render_{args.variant}"
    shutil.rmtree(run_dir, ignore_errors=True)
    outdir = run_dir / "out"
    outdir.mkdir(parents=True)
    project = run_dir / "project.flp"             # short, space-free name
    shutil.copy2(args.project, project)

    cmd = build_command(project, outdir, args.variant)
    print("RUN:", " ".join(cmd))
    start = time.time()
    proc = subprocess.Popen(cmd)

    last_size, stable_since, wav = -1, None, None
    outcome = "timeout"
    while time.time() - start < TIMEOUT_S:
        time.sleep(POLL_S)
        wav = newest_wav([outdir, run_dir], since=start)
        exited = proc.poll() is not None
        if wav:
            size = wav.stat().st_size
            if size != last_size:
                last_size, stable_since = size, time.time()
            elif size > 0 and time.time() - stable_since >= STABLE_S:
                outcome = "rendered_fl_exited" if exited else "rendered_fl_stuck_open"
                break
        if exited and not wav:
            outcome = f"fl_exited_without_wav (code {proc.returncode})"
            break

    elapsed = time.time() - start
    if proc.poll() is None:
        proc.kill()                                  # only our own process
        proc.wait(timeout=30)
        killed = True
    else:
        killed = False

    print(f"OUTCOME: {outcome}")
    print(f"ELAPSED: {elapsed:.1f}s   killed_by_watchdog: {killed}")
    if wav:
        print(f"WAV: {wav}  ({wav.stat().st_size / 1e6:.1f} MB)")
    return 0 if outcome.startswith("rendered") else 1


if __name__ == "__main__":
    sys.exit(main())
