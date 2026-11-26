"""Start the Zosimix MCP server in live mode for the Claude Code plugin (D84).

Claude Code runs this with its own `python`, which may not have Zosimix's packages. So it hands
over to an interpreter that does:
  1. the plugin folder's own .venv, if it exists (set up once, see the README), or
  2. uv, which builds that environment from pyproject.toml on first use.
The server speaks MCP over stdin/stdout, which the child process inherits.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = f"""Zosimix needs its Python packages. Either install uv (https://docs.astral.sh/uv/), or once, in
{ROOT}
run:
  python -m venv .venv
  .venv{os.sep}{'Scripts' if os.name == 'nt' else 'bin'}{os.sep}pip install -e ".[fl]"
"""


def main() -> int:
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    server = ["-m", "zosimix.mcp_server", *sys.argv[1:]]
    if venv_python.exists():
        cmd = [str(venv_python), *server]
    elif shutil.which("uv"):
        cmd = ["uv", "run", "--project", str(ROOT), "--extra", "fl", "python", *server]
    else:
        sys.stderr.write(SETUP)
        return 1
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
