# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Attribute a quartier report's listings to their nearest school and emit the two tables.

    uv run scripts/listings_assign.py data/derived/area_villeray_listings.csv data/derived/area_villeray_schools.csv

The listings CSV is filled by hand during the skill's Layer 3 with these columns:
side (buy|rent), type, bedrooms, street_or_sector, address, price, url, source, date_seen.
`address` is geocoded through geocode.py (Nominatim, cached, one request per second); a row
whose address cannot be geocoded keeps the school named in an optional `school_hint` column
(a code) or is listed under "unassigned". Duplicates by URL are dropped. Output: two captioned
Quarto tables grouped by school (tbl-for-sale, tbl-for-rent) and a line per school that
received no listing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import pandas as pd
import typer
from loguru import logger
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geocode import CACHE, geocode  # noqa: E402
from zone_stats import CRS  # noqa: E402

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="<level>{level: <7}</level> {message}")


def table(rows: pd.DataFrame, side: str, schools: pd.DataFrame) -> str:
    price_head = "Asking price" if side == "buy" else "Monthly rent"
    tid = "tbl-for-sale" if side == "buy" else "tbl-for-rent"
    cap = ("For sale, 3+ bedrooms, each listing under the school whose building is nearest"
           if side == "buy" else "For rent, 3+ bedrooms, each listing under the school whose building is nearest")
    L = ["::: {.column-page}", f"| School | Type | Bedrooms | Street or sector | {price_head} | Source, date seen |",
         "|:---|:---|---:|:---|---:|:---|"]
    got = set()
    for r in rows.sort_values(["school_short", "price"]).itertuples():
        got.add(r.school_code)
        L.append(f"| {r.school_short} | {r.type} | {r.bedrooms} | {r.street_or_sector} | {r.price} | "
                 f"[{r.source}]({r.url}), {r.date_seen} |")
    missing = [s.short for s in schools.itertuples() if s.code not in got]
    L += ["", f": {cap} {{#{tid}}}", ":::", ""]
    if missing:
        L.append(f"No {'sale' if side == 'buy' else 'rental'} listing with three or more bedrooms turned up nearest to: "
                 + ", ".join(missing) + ".\n")
    return "\n".join(L)


@app.command()
def main(
    listings: Annotated[Path, typer.Argument(help="CSV filled during Layer 3")],
    schools: Annotated[Path, typer.Argument(help="area_<slug>_schools.csv from area_info.py")],
    out: Annotated[Optional[Path], typer.Option(help="write the tables here instead of stdout")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Geocode listings, attribute each to its nearest school, drop duplicates, emit tables."""
    setup_logging(verbose)
    li = pd.read_csv(listings, dtype=str).fillna("")
    sc = pd.read_csv(schools, dtype={"code": str})
    sc = sc[sc.role.isin(["school", "edge"])]
    spts = gpd.GeoSeries([Point(x, y) for x, y in zip(sc.lon, sc.lat)], crs=4326).to_crs(CRS)
    before = len(li)
    li = li.drop_duplicates("url")
    if len(li) < before:
        logger.info("dropped {} duplicate listing(s) by URL", before - len(li))
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    codes, shorts = [], []
    for r in li.itertuples():
        hit = geocode(f"{r.address}, Montréal", cache) if r.address else None
        if hit:
            p = gpd.GeoSeries([Point(hit["lon"], hit["lat"])], crs=4326).to_crs(CRS).iloc[0]
            i = spts.distance(p).idxmin()
            codes.append(str(sc.loc[i, "code"])); shorts.append(sc.loc[i, "short"])
        elif getattr(r, "school_hint", ""):
            code = str(r.school_hint)
            m = sc[sc.code == code]
            codes.append(code); shorts.append(m.short.iloc[0] if len(m) else code)
            logger.warning("{} not geocoded; using school_hint {}", r.address, code)
        else:
            codes.append(""); shorts.append("unassigned")
            logger.warning("{} not geocoded and no school_hint; listed as unassigned", r.address)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    li["school_code"], li["school_short"] = codes, shorts
    text = table(li[li.side == "buy"], "buy", sc) + "\n" + table(li[li.side == "rent"], "rent", sc)
    if out:
        out.write_text(text)
        logger.success("-> {}", out)
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
