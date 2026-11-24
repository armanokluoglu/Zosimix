"""Pick a handful of MoisesDB songs and copy them into Zosimix's song layout.

MoisesDB (Pereira et al. 2023, arXiv:2307.15913; CC BY-NC-SA 4.0) ships as one ~83 GB zip.
We only need about 5 songs, so this module works directly on the zip: it surveys all songs
by reading only their small data.json members, ranks them by how well they suit the
benchmark, and extracts audio for the chosen songs only.

Layout inside the zip:
    moisesdb/moisesdb_v0.1/<track_id>/data.json
    moisesdb/moisesdb_v0.1/<track_id>/<stemName>/<file_id>.wav
data.json lists stems; each stem has tracks with a trackType ("kick_drum", "overheads", ...).
The dataset defines the mixture as the plain sum of all tracks; there is no mix file.

Usage:
    python -m zosimix.datasets.moisesdb survey <moisesdb.zip>
    python -m zosimix.datasets.moisesdb import <moisesdb.zip> <track_id> [<track_id> ...]
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import soundfile as sf

from zosimix import audio
from zosimix.songs import DATA_ROOT

ATTRIBUTION = ("MoisesDB by Pereira, Araújo, Korzeniowski and Vogl (2023), arXiv:2307.15913, "
               "licensed CC BY-NC-SA 4.0")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass
class Candidate:
    track_id: str
    artist: str
    song: str
    genre: str
    # our stem name -> zip members that get summed into it
    stems: dict[str, list[str]] = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def drum_mics(self) -> list[str]:
        return [s for s in self.stems if s.startswith("drums_")]

    @property
    def has_overheads(self) -> bool:
        return any("overhead" in s for s in self.drum_mics)

    @property
    def has_lead_vocal(self) -> bool:
        return any(s.startswith("vocals_") and "lead" in s for s in self.stems)

    def score(self) -> int:
        """Higher is better. What the benchmark needs (DESIGN.md §4.1-4.2, D41):
        separate drum mics incl. overheads (polarity faults), a lead vocal (pan, gain),
        8-14 stems (rich enough for an agent, small enough to build an FL template by hand),
        and a length of 2.5-5 minutes."""
        return ((3 if len(self.drum_mics) >= 3 and self.has_overheads else 0)
                + (2 if self.has_lead_vocal else 0)
                + (2 if 8 <= len(self.stems) <= 14 else 0)
                + (1 if 150 <= self.seconds <= 300 else 0))


def _our_stem_name(stem_name: str, track_type: str) -> str:
    """'drums' + 'kick_drum' -> 'drums_kick_drum'. The family prefix drives eligibility rules.

    Track types are cut to their first three words: these names show up in FL's mixer and
    in every agent tool call, and MoisesDB has types like
    'fx_processed_sound_scratches_gun_shots_explosions_etc'.
    """
    words = _slug(track_type).split("-")[:3]
    return f"{_slug(stem_name)}_{'_'.join(words)}".replace("-", "_")


def _read_candidate(z: zipfile.ZipFile, data_member: str) -> Candidate:
    folder = data_member.rsplit("/", 1)[0]
    data = json.loads(z.read(data_member))
    c = Candidate(folder.rsplit("/", 1)[1], data.get("artist", ""), data.get("song", ""), data.get("genre", ""))
    for stem in data.get("stems", []):
        for track in stem.get("tracks", []):
            name = _our_stem_name(stem["stemName"], track["trackType"])
            c.stems.setdefault(name, []).append(f"{folder}/{stem['stemName']}/{track['id']}.{track['extension']}")
    first = next(iter(c.stems.values()))[0]
    with z.open(first) as f:
        c.seconds = sf.info(f).duration
    return c


def survey(zip_path: Path) -> list[Candidate]:
    with zipfile.ZipFile(zip_path) as z:
        candidates = [_read_candidate(z, n) for n in z.namelist() if n.endswith("/data.json")]
    return sorted(candidates, key=lambda c: (-c.score(), c.genre, c.song))


def import_song(zip_path: Path, c: Candidate) -> Path:
    """Write every source file as its own stem in the common layout (32-bit float).

    When one part has several files (e.g. two overhead mics), they stay separate as
    <name>_1, <name>_2, ... Summing them would destroy exactly the mic pairs where real
    polarity problems happen (D42).
    """
    song_id = f"moisesdb-{_slug(c.artist)[:20]}-{_slug(c.song)[:30]}".strip("-")
    folder = DATA_ROOT / song_id
    rate = None
    with zipfile.ZipFile(zip_path) as z:
        for name, members in c.stems.items():
            for index, member in enumerate(members, start=1):
                with z.open(member) as f:
                    a, sr = sf.read(f, dtype="float64", always_2d=True)
                if rate is None:
                    rate = sr
                if sr != rate:
                    raise ValueError(f"{c.track_id}/{member}: {sr} Hz, expected {rate} Hz (no resampling yet)")
                stem_name = name if len(members) == 1 else f"{name}_{index}"
                audio.write(folder / "stems" / f"{stem_name}.wav", a, rate)
    (folder / "song.json").write_text(json.dumps({
        "song_id": song_id,
        "title": c.song,
        "artist": c.artist,
        "genre": c.genre,
        "dataset": "MoisesDB",
        "moisesdb_track_id": c.track_id,
        "license": "CC BY-NC-SA 4.0",
        "attribution": ATTRIBUTION,
        "reference": "none: MoisesDB defines the mixture as the plain stem sum",
    }, indent=2), encoding="utf-8")
    return folder


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey")
    s.add_argument("zip", type=Path)
    s.add_argument("--top", type=int, default=40)
    i = sub.add_parser("import")
    i.add_argument("zip", type=Path)
    i.add_argument("track_ids", nargs="+")
    args = ap.parse_args()

    candidates = survey(args.zip)
    if args.cmd == "survey":
        print(f"{len(candidates)} songs found\n")
        for c in candidates[: args.top]:
            print(f"score {c.score()}  {c.track_id}  {c.genre[:14]:<14} {c.artist[:18]:<18} {c.song[:26]:<26} "
                  f"{len(c.stems):2d} stems  {len(c.drum_mics)} drum mics  {c.seconds / 60:4.1f} min")
    else:
        by_id = {c.track_id: c for c in candidates}
        for track_id in args.track_ids:
            print(f"imported {import_song(args.zip, by_id[track_id])}")


if __name__ == "__main__":
    main()
