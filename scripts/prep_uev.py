# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio>=0.9", "pyarrow>=16"]
# ///
"""Reduce the 780 MB assessment-unit GeoJSON to one point per unit with the attributes we use.

    uv run scripts/prep_uev.py

Reads data/raw/uniteevaluationfonciere.geojson.zip once (a few minutes: GeoJSON has no
spatial index) and writes data/derived/uev_points.parquet with ID_UEV, dwelling count, year
built, CUBF code and label, regular/condo category, borough code, and the polygon centroid as
lon/lat plus MTM zone 8 (EPSG:32188) x/y. zone_stats.py joins this to the tax bills on
ID_UEV = ID_CUM and selects units by distance to the school.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "uniteevaluationfonciere.geojson.zip"
DEST = ROOT / "data" / "derived" / "uev_points.parquet"
KEEP = ["ID_UEV", "NOMBRE_LOGEMENT", "ANNEE_CONSTRUCTION", "CODE_UTILISATION", "LIBELLE_UTILISATION",
        "CATEGORIE_UEF", "NO_ARROND_ILE_CUM", "SUPERFICIE_TERRAIN", "SUPERFICIE_BATIMENT", "ETAGE_HORS_SOL"]


def main() -> None:
    if not SRC.exists():
        sys.exit("missing assessment units; run: uv run scripts/fetch_open_data.py uev")
    inner = next(n for n in zipfile.ZipFile(SRC).namelist() if n.endswith(".geojson"))
    print(f"reading {SRC.name} ...", file=sys.stderr, flush=True)
    g = gpd.read_file(f"/vsizip/{SRC}/{inner}", engine="pyogrio", columns=KEEP)
    print(f"{len(g)} units; computing centroids", file=sys.stderr, flush=True)
    m = g.to_crs(32188)
    cent = m.geometry.centroid
    out = pd.DataFrame(g.drop(columns="geometry"))
    out["x"] = cent.x.values
    out["y"] = cent.y.values
    ll = cent.to_crs(4326)
    out["lon"] = ll.x.values
    out["lat"] = ll.y.values
    out["area_m2"] = m.geometry.area.values
    DEST.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(DEST, index=False)
    print(f"-> {DEST.relative_to(ROOT)} ({DEST.stat().st_size >> 20} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
