#!/usr/bin/env python3
"""Download the CC0 PBR textures used by the forest scene from Poly Haven.

Files land in assets/textures/<asset>/<map>.jpg and are verified against the
MD5 published by the Poly Haven API. Files that already match are skipped.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com/files/{asset}"
USER_AGENT = "rpg-nopoke-forest/1.0"
ROOT = Path(__file__).resolve().parent.parent / "assets" / "textures"

# Poly Haven map key -> local file stem.
MAPS = {
    "Diffuse": "diff",
    "nor_gl": "nor_gl",
    "Rough": "rough",
    "Displacement": "disp",
}

ASSETS = (
    "forest_leaves_02",      # main forest floor: moss, leaf litter, twigs
    "brown_mud_leaves_01",   # damp ground variation
    "forest_ground_04",      # compacted path dirt
    "mossy_rock",            # boulders
    "lichen_rock",           # rune stones
    "bark_brown_02",         # ancient hero tree
    "jolcham_oak_bark_01",   # forest trees
    "rough_pine_door",       # chest planks
)


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def md5_of(path):
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, path, expected_md5):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    partial = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    actual = md5_of(partial)
    if actual != expected_md5:
        partial.unlink()
        raise RuntimeError(f"MD5 mismatch for {url}: {actual} != {expected_md5}")
    partial.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--res", default="2k", choices=("1k", "2k", "4k"),
                        help="texture resolution (default: 2k)")
    args = parser.parse_args()

    for asset in ASSETS:
        files = fetch_json(API.format(asset=asset))
        folder = ROOT / asset
        folder.mkdir(parents=True, exist_ok=True)
        for key, stem in MAPS.items():
            entry = files[key][args.res]["jpg"]
            path = folder / f"{stem}.jpg"
            if path.exists() and md5_of(path) == entry["md5"]:
                print(f"ok        {asset}/{path.name}")
                continue
            print(f"download  {asset}/{path.name} ({entry['size'] / 1e6:.1f} MB)")
            download(entry["url"], path, entry["md5"])
    print(f"Textures ready in {ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
