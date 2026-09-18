# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Geocode a Montreal address with OpenStreetMap's Nominatim (one request per second, cached).

    uv run scripts/geocode.py "7081 avenue des Érables, Montréal"
    uv run scripts/geocode.py --json "2001 rue Mullins, Montréal" "4131 rue Adam, Montréal"

Prints `lon lat display_name` per address (or JSON with --json). Results are cached in
data/derived/geocode_cache.json so re-runs cost nothing. Nominatim's usage policy allows
about one request per second with an identifying User-Agent; this script sleeps between
calls and is meant for a handful of candidate addresses, not for bulk work. For bulk
geocoding (e.g. the childcare list) use the city's address points instead.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "derived" / "geocode_cache.json"
UA = "mtl-101/0.1 (https://letsgada.github.io/mtl-101)"
VIEWBOX = "-73.99,45.40,-73.47,45.71"  # island of Montreal, lon/lat


def geocode(address: str, cache: dict) -> dict | None:
    if address in cache:
        return cache[address]
    q = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1, "countrycodes": "ca",
                                "viewbox": VIEWBOX, "bounded": 1})
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        hits = json.load(r)
    time.sleep(1.1)
    hit = None
    if hits:
        h = hits[0]
        hit = {"lon": float(h["lon"]), "lat": float(h["lat"]), "display_name": h["display_name"]}
    cache[address] = hit
    return hit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("addresses", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    out = {}
    for a in args.addresses:
        out[a] = geocode(a, cache)
        if not args.json:
            h = out[a]
            print(f"{h['lon']:.6f} {h['lat']:.6f} {h['display_name']}" if h else f"NOT FOUND {a}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    if args.json:
        json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
        print()


if __name__ == "__main__":
    main()
