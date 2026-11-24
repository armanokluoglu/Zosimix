"""Fetch individual AlbumDB songs without downloading the whole 5 GB archive.

AlbumDB (McKenzie, Moliner, Wright; AES Europe 2026) is CC BY 4.0. Zenodo supports
HTTP range requests, so `remotezip` can pull single files out of the zip.

Usage:
    python -m zosimix.datasets.albumdb list
    python -m zosimix.datasets.albumdb fetch 01 10
"""

from __future__ import annotations

import argparse
import json
import re
import shutil

from remotezip import RemoteZip

from zosimix.songs import DATA_ROOT

RECORD = "https://zenodo.org/records/19683001/files/"
STEMS_ZIP = RECORD + "stems_mixed.zip?download=1"
MASTERS_ZIP = RECORD + "masters_stereo.zip?download=1"
ATTRIBUTION = ("AlbumDB by McKenzie, Moliner and Wright (AES Europe 2026), "
               "https://zenodo.org/records/19683001, licensed CC BY 4.0")


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def list_songs() -> dict[str, dict]:
    """Track number ("01".."10") -> {title, stems: [member names], bytes}."""
    songs: dict[str, dict] = {}
    with RemoteZip(STEMS_ZIP) as z:
        for info in z.infolist():
            parts = info.filename.split("/")
            if len(parts) != 3 or not parts[2].endswith(".wav"):
                continue
            number, title = parts[1].split(" ", 1)
            entry = songs.setdefault(number, {"title": title, "stems": [], "bytes": 0})
            entry["stems"].append(info.filename)
            entry["bytes"] += info.file_size
    return dict(sorted(songs.items()))


def fetch(numbers: list[str]) -> None:
    catalog = list_songs()
    with RemoteZip(STEMS_ZIP) as stems_zip, RemoteZip(MASTERS_ZIP) as masters_zip:
        master_names = {m.split("/")[-1].split(" - ")[0]: m for m in masters_zip.namelist() if m.endswith(".wav")}
        for number in numbers:
            song = catalog[number]
            song_id = f"albumdb-{number}-{_slug(song['title'])}"
            folder = DATA_ROOT / song_id
            (folder / "stems").mkdir(parents=True, exist_ok=True)
            for member in song["stems"]:
                target = folder / "stems" / member.split("/")[-1]
                if target.exists():
                    continue
                print(f"  {song_id}: {target.name}")
                with stems_zip.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            if not (folder / "reference.wav").exists():
                with masters_zip.open(master_names[number]) as src, open(folder / "reference.wav", "wb") as dst:
                    shutil.copyfileobj(src, dst)
            (folder / "song.json").write_text(json.dumps({
                "song_id": song_id,
                "title": song["title"],
                "dataset": "AlbumDB",
                "license": "CC BY 4.0",
                "attribution": ATTRIBUTION,
                "reference": "stereo master (mastered, so it is not an exact stem sum)",
            }, indent=2), encoding="utf-8")
            print(f"done: {song_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("fetch")
    f.add_argument("numbers", nargs="+", help='track numbers, e.g. "01 10"')
    args = ap.parse_args()
    if args.cmd == "list":
        for number, song in list_songs().items():
            print(f"{number}  {song['title']:<40} {len(song['stems']):3d} stems  {song['bytes'] / 1e6:6.0f} MB")
    else:
        fetch(args.numbers)


if __name__ == "__main__":
    main()
