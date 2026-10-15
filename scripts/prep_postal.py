# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio>=0.9", "pyarrow>=16", "typer>=0.12", "loguru>=0.7"]
# ///
"""Reduce the ISQ postal-code table to the island of Montreal with the attributes we use.

    uv run scripts/prep_postal.py

Reads data/raw/cp_territoires.csv (105 MB, ~241k Quebec postal codes) and writes
data/derived/postal_points.parquet: one row per postal-code part on the island with its
coordinates, its count of residential address units, its census dissemination area and its
francophone service centre. school_zone.py uses the points as the sample grid for a school's
catchment and the residential counts as the weight.

A postal code that straddles two municipalities or two dissemination areas appears once per
part, each with its own point and its share of the code's addresses (PRC_REP); the catchment
scripts aggregate back to one row per code on output. The island has about 44k parts over
about 42k distinct codes.

Source: Institut de la statistique du Québec, *Codes postaux et territoires*, derived from the
Référentiel québécois des adresses (CC-BY 4.0). "Code postal" is an official mark of Canada Post.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import geopandas as gpd
import pandas as pd
import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "cp_territoires.csv"
DEST = ROOT / "data" / "derived" / "postal_points.parquet"
CRS = 32188  # MTM zone 8, metres, as in zone_stats.py
ISLAND_MRC = "66"  # agglomeration of Montreal, the 16 municipalities on the island
# R: residential address units, our weight. ADIDU: census DA, joins to census_da.py output.
# CO_CSF / NOM_CSF: francophone service centre, which routes a code to CSSDM / CSSMB / CSSPI.
KEEP = ["CPCGADIDU", "CP", "R", "NB_UNITE_AD", "PRC_REP", "ADIDU", "CO_CSF", "NOM_CSF",
        "CO_SDR", "NOM_SDR", "CO_MRC", "CO_ARR", "LAT", "LONG", "RET_DATE"]
NUM = {"R": "int32", "NB_UNITE_AD": "int32"}

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


@app.command()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    """Convert the Quebec postal-code table to island points."""
    setup_logging(verbose)
    if not SRC.exists():
        logger.error("missing postal codes; run: uv run scripts/fetch_open_data.py cp_territoires")
        raise typer.Exit(1)
    logger.info("reading {} ...", SRC.name)
    df = pd.read_csv(SRC, usecols=KEEP, dtype=str, encoding="utf-8-sig", low_memory=False)
    logger.info("{} postal-code parts in Quebec", len(df))

    df = df[(df.CO_MRC == ISLAND_MRC) & df.RET_DATE.isna()].drop(columns=["CO_MRC", "RET_DATE"])
    if df.empty:
        logger.error("no island rows; has the file's structure changed?")
        raise typer.Exit(1)
    df["CP"] = df.CP.str.replace(r"\s+", "", regex=True).str.upper()
    for col, kind in NUM.items():
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(kind)
    df["PRC_REP"] = pd.to_numeric(df.PRC_REP, errors="coerce").fillna(0.0)
    df["lon"] = pd.to_numeric(df.LONG, errors="coerce")
    df["lat"] = pd.to_numeric(df.LAT, errors="coerce")
    bad = df.lon.isna() | df.lat.isna()
    if bad.any():
        logger.warning("dropping {} parts with no coordinates", int(bad.sum()))
        df = df[~bad]

    g = gpd.GeoDataFrame(df.drop(columns=["LAT", "LONG"]),
                         geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326).to_crs(CRS)
    out = pd.DataFrame(g.drop(columns="geometry"))
    out["x"] = g.geometry.x.values
    out["y"] = g.geometry.y.values

    DEST.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DEST, index=False)
    logger.success("{} parts / {} codes / {} residential units -> {}",
                   len(out), out.CP.nunique(), f"{out.R.sum():,}", DEST.relative_to(ROOT))
    for (code, name), grp in out.groupby(["CO_CSF", "NOM_CSF"]):
        logger.info("  {} {:<28} {:>6} codes {:>10} residential units",
                    code, name, grp.CP.nunique(), f"{grp.R.sum():,}")


if __name__ == "__main__":
    app()
