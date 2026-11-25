"""The flstudio-mcp port (D66): the compatibility block must behave exactly like the standard
library for what the FL script sends, and the port must change nothing else."""

import ast
import base64
import importlib.util
import json
import math
from pathlib import Path

import pytest

from zosimix.fl import port_flstudio_mcp as port

COMPAT = Path(__file__).resolve().parents[1] / "fl_bridge" / "flstudio_mcp_compat.py"


def compat():
    spec = importlib.util.spec_from_file_location("flstudio_mcp_compat", COMPAT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLES = [
    {"ok": True, "result": {"tracks": [{"i": 1, "name": "Kick", "vol": 0.8, "pan": -0.25, "mute": False}]}},
    {"s": "quote \" backslash \\ newline \n tab \t ctrl \x01 del \x7f", "n": None, "e": [], "o": {}},
    {"unicode": "café – ✓ 🎛️ Ω", "big": 2 ** 40, "neg": -17, "f": 1e-7, "g": 123456.789, "h": 0.1 + 0.2},
    [1, [2, [3, {"deep": [True, False, None]}]], "end"],
    {"param": "Band 2 level", "v": 0.5, "s": "0.0dB"},
    "just a string", 42, 3.5, None, True,
]


@pytest.mark.parametrize("obj", SAMPLES)
@pytest.mark.parametrize("separators", [None, (",", ":")])
def test_dumps_matches_the_standard_library(obj, separators):
    j = compat().json
    assert j.dumps(obj, ensure_ascii=True, separators=separators) == json.dumps(obj, ensure_ascii=True, separators=separators)


@pytest.mark.parametrize("obj", SAMPLES)
@pytest.mark.parametrize("ensure_ascii", [True, False])
def test_loads_reads_what_the_standard_library_writes(obj, ensure_ascii):
    text = json.dumps(obj, ensure_ascii=ensure_ascii, indent=2 if ensure_ascii else None)
    assert compat().json.loads(text) == json.loads(text)


def test_non_finite_floats_follow_allow_nan():
    j = compat().json
    with pytest.raises(ValueError):
        j.dumps({"x": math.inf}, allow_nan=False)
    assert j.dumps([math.inf, -math.inf]) == json.dumps([math.inf, -math.inf])


def test_dict_keys_are_converted_like_json():
    obj = {7: "a", True: "b", None: "c", 2.5: "d"}
    assert compat().json.dumps(obj) == json.dumps(obj)


@pytest.mark.parametrize("data", [b"", b"f", b"fo", b"foo", bytes(range(256)), b'{"ok":true}' * 50])
def test_base64_matches_the_standard_library(data):
    b = compat().base64
    assert b.b64encode(data) == base64.b64encode(data)
    assert b.b64decode(base64.b64encode(data)) == data


def test_port_changes_only_the_imports_and_keeps_fls_header_first():
    upstream = port.SCRIPT.read_text(encoding="utf-8") if port.SCRIPT.exists() else None
    if upstream is None:
        pytest.skip("flstudio-mcp is not cloned on this machine")
    ported = port.port(upstream, COMPAT.read_text(encoding="utf-8"))
    assert ported.startswith("# name=FLStudioMCP\n")                       # FL still recognises it
    assert ported.count("except ImportError:  # FL 20.9.2") == 1
    ast.parse(ported, feature_version=(3, 9))                               # FL 20.9.2 runs Python 3.9
    # Remove what the port added; the rest must be upstream's text exactly.
    added_note = ported.splitlines(keepends=True)[4:7]
    restored = ported.replace("".join(added_note), "", 1)
    fallback_start = restored.index("try:\n    import base64")
    fallback_end = restored.index("json = _JsonCompat\n") + len("json = _JsonCompat\n")
    assert restored[:fallback_start] + port.IMPORTS + restored[fallback_end:] == upstream
