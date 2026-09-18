# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "loguru>=0.7"]
# ///
"""Geocode a Montreal address with OpenStreetMap's Nominatim (one request per second, cached).

    uv run scripts/geocode.py "7081 avenue des Érables, Montréal"
    uv run scripts/geocode.py --json "2001 rue Mullins, Montréal" "4131 rue Adam, Montréal"

Prints `lon lat display_name` per address (or JSON with --json) on stdout. Results are cached
in data/derived/geocode_cache.json so re-runs cost nothing. Nominatim's usage policy allows
about one request per second with an identifying User-Agent; this script sleeps between
calls and is meant for a handful of candidate addresses, not for bulk work. For bulk
geocoding (e.g. the childcare list) use the city's address points instead.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "derived" / "geocode_cache.json"
UA = "mtl-101/0.1 (https://letsgada.github.io/mtl-101)"
VIEWBOX = "-73.99,45.40,-73.47,45.71"  # island of Montreal, lon/lat

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def geocode(address: str, cache: dict) -> dict | None:
    if address in cache:
        logger.debug("cache hit: {}", address)
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
    else:
        logger.warning("no match: {}", address)
    cache[address] = hit
    return hit


@app.command()
def main(
    addresses: Annotated[list[str], typer.Argument(help="one or more street addresses")],
    as_json: Annotated[bool, typer.Option("--json", help="emit a JSON object keyed by address")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Geocode addresses with Nominatim, one request per second, cached."""
    setup_logging(verbose)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    out = {}
    for a in addresses:
        out[a] = geocode(a, cache)
        if not as_json:
            h = out[a]
            typer.echo(f"{h['lon']:.6f} {h['lat']:.6f} {h['display_name']}" if h else f"NOT FOUND {a}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    if as_json:
        typer.echo(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    app()
