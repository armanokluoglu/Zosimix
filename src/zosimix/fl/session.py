"""Start FL Studio on a project, drive it, save, close it, and render it (D55, D59).

FL's scripting API can't open a project, can't "save as" and can't render. So one cycle is:

    copy the template -> launch FL on the copy -> set values over the bridge -> save
    -> close FL -> render the saved copy from the command line

Safety rules, because this runs on the owner's own machine:
  - Refuse to start while any FL that we didn't start is running. FL is single-instance,
    so launching it would hand our project to the owner's window.
  - Only ever stop the process IDs we started. Close gracefully first (like clicking the
    window's X); force-kill only our own process if it doesn't exit.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import time
from pathlib import Path
from typing import Self

from zosimix.fl.bridge import Bridge, BridgeError
from zosimix.fl.slots import FL_ROOT, TEMPLATE

FL_EXE = Path(r"C:\Program Files\Image-Line\FL Studio 20\FL64.exe")
WORK_DIR = FL_ROOT / "work"            # no spaces: FL's command line can't handle them
LAUNCH_TIMEOUT_S = 180                 # cold start of FL with 24 audio clips
CLOSE_TIMEOUT_S = 30
RENDER_TIMEOUT_S = 600
RENDER_STABLE_S = 5                    # WAV size unchanged this long => render finished


class FLError(RuntimeError):
    """FL didn't start, save, close or render as expected."""


def fl_pids() -> set[int]:
    """Process IDs of every running FL64.exe."""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FL64.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, check=False).stdout
    return {int(row[1]) for row in csv.reader(io.StringIO(out)) if len(row) > 1 and row[0] == "FL64.exe"}


def _refuse_if_fl_running() -> None:
    if fl_pids():
        raise FLError("FL Studio is already running. Close it first: Zosimix never touches an FL window "
                      "it didn't start.")


def check_midi_settings() -> None:
    """Refuse to start if FL's saved MIDI settings can't carry the bridge (D58).

    FL sends a script's replies to an output with the same port number as the script's
    input; it links the same-named "Zosimix In" output by itself. FL reads these settings
    from the registry at startup (stored as text). We only read them, never change them.
    """
    import winreg  # Windows-only, like FL

    def read(kind: str, device: str) -> dict[str, str]:
        path = rf"Software\Image-Line\FL Studio 20\Devices\MIDI {kind}\{device}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                return {name: str(winreg.QueryValueEx(key, name)[0]) for name in ("Port", "Enabled", "ScriptFolder")
                        if _has_value(key, name)}
        except FileNotFoundError:
            return {}

    fix = " Fix it in FL under Options > MIDI settings (see fl_bridge/TEMPLATE.md), then close FL."
    script_in = read("input", "Zosimix In")
    if script_in.get("Enabled") != "1" or not script_in.get("ScriptFolder", "").startswith("Zosimix Bridge"):
        raise FLError("FL's 'Zosimix In' input isn't enabled with the Zosimix Bridge script." + fix)
    port = script_in.get("Port", "-1")
    if port == "-1":
        raise FLError("FL's 'Zosimix In' input has no port number." + fix)
    if port not in (read("output", "Zosimix In").get("Port"), read("output", "Zosimix Out").get("Port")):
        raise FLError(f"No Zosimix MIDI output uses port {port}, so FL's replies go nowhere." + fix)


def _has_value(key, name: str) -> bool:
    import winreg

    try:
        winreg.QueryValueEx(key, name)
        return True
    except FileNotFoundError:
        return False


def _stop(proc: subprocess.Popen, timeout_s: float = CLOSE_TIMEOUT_S) -> bool:
    """Close our own FL gracefully, then force it if needed. Returns True if it closed by itself."""
    if proc.poll() is not None:
        return True
    subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True, check=False)   # = clicking X
    try:
        proc.wait(timeout=timeout_s)
        return True
    except subprocess.TimeoutExpired:
        proc.kill()                                   # only the process we started
        proc.wait(timeout=30)
        return False


def new_project(name: str = "project") -> Path:
    """A fresh copy of the template in the work folder, ready to open."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    project = WORK_DIR / f"{name}.flp"
    shutil.copy2(TEMPLATE, project)
    return project


class FLSession:
    """FL open on one project, with the bridge connected. Use as a context manager.

    Leaving the `with` block closes FL. Call `save()` first to keep the changes.
    """

    def __init__(self, project: Path, launch_timeout_s: float = LAUNCH_TIMEOUT_S) -> None:
        _refuse_if_fl_running()
        check_midi_settings()
        self.project = project
        self.proc = subprocess.Popen([str(FL_EXE), str(project)])
        self.fl: Bridge | None = None
        try:
            self.fl = self._connect(launch_timeout_s)
        except Exception:
            _stop(self.proc)
            raise

    def _connect(self, timeout_s: float) -> Bridge:
        """Wait until the bridge answers and the project's plugins are loaded."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise FLError(f"FL exited during startup (code {self.proc.returncode})")
            try:
                fl = Bridge()
            except BridgeError:
                time.sleep(1.0)
                continue
            # The script can answer before the project has finished loading.
            while time.monotonic() < deadline:
                if "parametric" in fl.call("plugin_name", 1, 0)[0].lower():
                    return fl
                time.sleep(0.5)
            fl.close()
        raise FLError(f"FL didn't come up with the project within {timeout_s:.0f}s")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def save(self) -> None:
        """Save the project in place (FL's Ctrl+S) and wait until the file has been written.

        Switches FL to song mode first: the command-line render plays the mode the project
        was saved in, and pattern mode renders one empty bar.
        """
        before = self.project.stat().st_mtime_ns
        if self.fl.call("song_mode")[0] != "1":
            raise FLError("FL didn't switch to song mode")
        self.fl.call("save")
        deadline = time.monotonic() + 30
        while self.project.stat().st_mtime_ns == before:
            if time.monotonic() > deadline:
                raise FLError(f"FL didn't save {self.project}")
            time.sleep(0.2)
        time.sleep(1.0)                               # let FL finish writing and release the file

    def close(self) -> bool:
        """Close FL. Returns True if it closed by itself (no unsaved-changes prompt). Safe to call twice."""
        if self.fl is not None:
            self.fl.close()
            self.fl = None
        return _stop(self.proc)


def render(project: Path, timeout_s: float = RENDER_TIMEOUT_S) -> Path:
    """Render a saved project to WAV with FL's command line (/R). Returns the WAV's path.

    "Done" means the WAV exists and has stopped growing. FL normally exits by itself
    (spike/NOTES.md); if it stays open, we stop it, since it is our own process.
    """
    _refuse_if_fl_running()
    outdir = project.parent / f"{project.stem}_render"
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)
    proc = subprocess.Popen([str(FL_EXE), "/R", "/Ewav", f"/O{outdir}", str(project)])
    start = time.monotonic()
    last_size, stable_since = -1, start
    try:
        while time.monotonic() - start < timeout_s:
            time.sleep(0.5)
            wavs = list(outdir.glob("*.wav"))
            exited = proc.poll() is not None
            if wavs:
                size = wavs[0].stat().st_size
                if size != last_size:
                    last_size, stable_since = size, time.monotonic()
                elif size > 0 and (exited or time.monotonic() - stable_since >= RENDER_STABLE_S):
                    return wavs[0]
            elif exited:
                raise FLError(f"FL exited without rendering {project} (code {proc.returncode})")
        raise FLError(f"render of {project} didn't finish within {timeout_s:.0f}s")
    finally:
        _stop(proc, timeout_s=10)
