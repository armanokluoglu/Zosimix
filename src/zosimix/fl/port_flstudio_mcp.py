"""Port flstudio-mcp's FL script to FL Studio 20.9.2 for the third baseline (D66).

flstudio-mcp (github.com/rosasynthesiz/flstudio-mcp, MIT licence) is the existing FL Studio
MCP that DESIGN.md §4.6 names as the strongest alternative. It is built for FL 2025+ and its
FL script fails to load on 20.9.2: `import base64` (and `json`) don't exist in FL 20.9.2's
embedded Python. A probe through our bridge found nothing else missing that mixing needs
(3 of its 100 FL calls are absent, all for pattern/arrangement editing).

So the port changes exactly one thing: the two import lines become "use the real modules
if they exist, otherwise fl_bridge/flstudio_mcp_compat.py". Everything else is upstream's
code, byte for byte, at a pinned commit whose hash is checked here.

Usage:
    python -m zosimix.fl.port_flstudio_mcp        # writes the ported script into FL's Hardware folder
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
UPSTREAM = Path("C:/zosimix/baselines/flstudio-mcp")
UPSTREAM_COMMIT = "2b2d664"
SCRIPT = UPSTREAM / "fl_controller" / "FLStudioMCP" / "device_FLStudioMCP.py"
SCRIPT_SHA256 = "75c7814f077b1637f3280e7da72bd714a1f5a3d57c5f08f5b277dd8d3b5f9af6"   # the reviewed file, as committed
COMPAT = REPO / "fl_bridge" / "flstudio_mcp_compat.py"
TARGET = Path.home() / "Documents" / "Image-Line" / "FL Studio" / "Settings" / "Hardware" / "FLStudioMCP" \
    / "device_FLStudioMCP.py"
IMPORTS = "import base64\nimport json\n"


def check_upstream(expected_sha256: str) -> str:
    """The upstream script's text, after checking it is the file we reviewed.

    Line endings are normalized first: git may check the file out with Windows line
    endings, and the hash should mean the same file on any machine.
    """
    raw = SCRIPT.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise SystemExit(f"{SCRIPT} changed (sha256 {digest}); re-review it before porting")
    return raw.decode("utf-8")


def port(upstream: str, compat: str) -> str:
    """Upstream's script with the two imports replaced by a fallback to the compat block."""
    if upstream.count(IMPORTS) != 1:
        raise ValueError("expected exactly one 'import base64' / 'import json' pair in the upstream script")
    indented = "".join("    " + line if line.strip() else line for line in compat.splitlines(keepends=True))
    fallback = ("try:\n    import base64\n    import json\n"
                "except ImportError:  # FL 20.9.2 has neither: Zosimix compatibility block (D66)\n"
                + indented)
    note = (f"# Ported for FL Studio 20.9.2 by Zosimix (D66) from rosasynthesiz/flstudio-mcp @ {UPSTREAM_COMMIT}\n"
            "# (MIT licence). The only change: the `import base64` / `import json` lines fall back to\n"
            "# fl_bridge/flstudio_mcp_compat.py. Everything else is upstream's code.\n")
    # FL reads the leading `# name=...` lines to identify the script, so the note goes after them.
    lines = upstream.replace(IMPORTS, fallback, 1).splitlines(keepends=True)
    header_end = next(i for i, line in enumerate(lines) if not line.startswith("#"))
    return "".join(lines[:header_end]) + note + "".join(lines[header_end:])


def main() -> None:
    text = port(check_upstream(SCRIPT_SHA256), COMPAT.read_text(encoding="utf-8"))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET} ({len(text)} chars) from upstream {UPSTREAM_COMMIT}")


if __name__ == "__main__":
    main()
