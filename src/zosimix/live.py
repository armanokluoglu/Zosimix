"""Live mode: the harness on your own song, for the Claude Code plugin (D84).

In the benchmark, the runner prepares a workspace and the MCP server opens it at start-up.
In live mode the server starts empty, and `open_mix` loads a folder of stems exported from a
DAW (in FL Studio: File > Export > WAV with "Split mixer tracks").

Exported file names follow the project ("My Song_Kick In.wav") and say nothing the tools can
use to tell a kick from a vocal. So each stem gets a working name: the common project prefix is
dropped and, when a keyword shows what the part is, its family goes in front
("drums_Kick_In"), which the tools read to group drum mics, find twins and pick the right
typical shape. The original name is kept to find the right mixer insert when applying the fix.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from zosimix import audio
from zosimix.engines.offline import OfflineEngine

TARGET = Path(__file__).with_name("data") / "tonal_target.json"
SKIP = re.compile(r"(^|[^a-z])master($|[^a-z])", re.IGNORECASE)        # FL also exports the master: that's the mix
KEYWORDS = [   # (family, words): the first family with a matching word wins
    ("drums", ["kick", "snare", "tom", "hat", "hihat", "overhead", "oh", "cymbal", "ride", "crash", "room", "drum",
               "kit", "rim", "clap"]),
    ("bass", ["bass", "sub", "808"]),
    ("vocals", ["vox", "vocal", "voc", "voice", "bv", "backing", "choir", "harmony", "adlib", "lead vox"]),
    ("guitars", ["gtr", "guitar", "acoustic"]),
    ("keys", ["keys", "piano", "synth", "pad", "organ", "rhodes", "lead", "pluck", "arp"]),
    ("strings", ["string", "violin", "viola", "cello"]),
    ("percussion", ["perc", "shaker", "tamb", "conga", "bongo"]),
]


def _family(name: str) -> str | None:
    words = set(re.findall(r"[a-z0-9]+", name.lower()))
    joined = " ".join(re.findall(r"[a-z0-9]+", name.lower()))
    for family, keys in KEYWORDS:
        if any((k in words) if " " not in k else (k in joined) for k in keys):
            return family
    return None


def working_names(file_stems: list[str]) -> dict[str, str]:
    """File stem -> working name. Drops the shared "<project>_" prefix and adds a family prefix."""
    prefix = os.path.commonprefix(file_stems) if len(file_stems) > 1 else ""
    cut = max(prefix.rfind("_"), prefix.rfind(" - "))
    out = {}
    for f in file_stems:
        core = f[cut + 1:].strip(" -_") if cut >= 0 else f
        core = re.sub(r"\s+", "_", core) or f
        family = _family(core)
        name = f"{family}_{core}" if family and not core.lower().startswith(family) else core
        while name in out.values():
            name += "_2"
        out[f] = name
    return out


def load_folder(folder: Path) -> tuple[OfflineEngine, dict[str, str], dict]:
    """The stems in `folder` (or `folder/stems`) as an engine, plus working name -> original name,
    plus the shipped tonal target."""
    folder = Path(folder)
    where = folder / "stems" if (folder / "stems").is_dir() else folder
    files = sorted(p for p in where.glob("*.wav") if not SKIP.search(p.stem))
    if not files:
        raise ValueError(f"no .wav stems in {where} (the master file is skipped)")
    names = working_names([p.stem for p in files])
    stems, rates = {}, set()
    for p in files:
        stems[names[p.stem]], sr = audio.read(p)
        rates.add(sr)
    if len(rates) != 1:
        raise ValueError(f"the stems have different sample rates: {sorted(rates)}; export them all at one rate")
    target = json.loads(TARGET.read_text(encoding="utf-8")) if TARGET.exists() else None
    return OfflineEngine(stems, rates.pop()), {names[p.stem]: p.stem for p in files}, target
