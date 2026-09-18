# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9"]
# ///
"""Extract the 2021 Census Profile variables MTL-101 uses, for every dissemination area (DA)
on the island of Montreal, from the StatCan bulk file (all Quebec DAs, 6.4 GB uncompressed).

    uv run scripts/census_da.py            # streams the zip once (a few minutes), caches the result

Island DAs are those whose census subdivision code starts with 2466 (census division 66 =
the agglomeration), taken from the INSPQ deprivation shapefile so the DA list matches the
geometry zone_stats.py uses. Writes data/derived/census_da_island.parquet, one row per DA,
one column per variable named below. Counts are randomly rounded to a multiple of 5 by
StatCan and small DAs may be suppressed (NaN); aggregate before dividing.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"
ZIP = RAW / "98-401-X2021006_Quebec_eng_CSV.zip"
DA_SHP = RAW / "ad2021inddef.zip"

# CHARACTERISTIC_ID -> column name (ids from 98-401-X2021006_English_meta.txt)
VARS = {
    1: "pop2021", 2: "pop2016", 3: "pop_change_pct",
    8: "age_total", 9: "age_0_14",
    41: "dwell_total", 42: "dwell_single_detached", 46: "dwell_apt_lt5", 47: "dwell_apt_ge5",
    78: "fam_total", 81: "fam_married_with_children", 84: "fam_commonlaw_with_children", 86: "fam_one_parent",
    89: "pop_private_hh",
    100: "hh_total", 103: "hh_couple_with_children", 105: "hh_one_parent",
    243: "median_hh_income", 244: "median_hh_income_at",
    345: "lim_at_pct",
    735: "lang_home_total", 738: "lang_home_english", 739: "lang_home_french",
    1414: "tenure_total", 1415: "owner", 1416: "renter",
    1527: "imm_total", 1529: "immigrants",
    1983: "mob5_total", 1985: "movers5",
    2014: "educ_25_64_total", 2015: "no_diploma_25_64",
}


def island_dguids() -> pd.Series:
    da = gpd.read_file(f"/vsizip/{DA_SHP}/Ad_2021_IndDef.shp", engine="pyogrio", read_geometry=False)
    isl = da[da.SDRIDU.astype(str).str.startswith("2466")]
    return "2021S0512" + isl.ADIDU.astype(str)


def main() -> None:
    for p in (ZIP, DA_SHP):
        if not p.exists():
            sys.exit(f"missing {p.name}; run: uv run scripts/fetch_open_data.py census_da_qc pampalon")
    dguids = set(island_dguids())
    print(f"{len(dguids)} island DAs", file=sys.stderr)
    inner = next(n for n in zipfile.ZipFile(ZIP).namelist() if n.endswith("_data_Quebec.csv"))
    # Column positions: 1 DGUID, 8 CHARACTERISTIC_ID, 11 C1_COUNT_TOTAL (the SYMBOL columns share a
    # name, so select by position and rename by position).
    keep = []
    with zipfile.ZipFile(ZIP).open(inner) as fh:
        reader = pd.read_csv(fh, usecols=[1, 8, 11], header=0, encoding="latin-1",
                             dtype=str, chunksize=2_000_000, low_memory=False)
        for i, chunk in enumerate(reader):
            chunk.columns = ["DGUID", "CHARACTERISTIC_ID", "C1_COUNT_TOTAL"]
            hit = chunk[chunk.DGUID.isin(dguids)]
            hit = hit[hit.CHARACTERISTIC_ID.astype(int).isin(VARS)]
            keep.append(hit)
            print(f"  chunk {i + 1}: {len(hit)} rows kept", file=sys.stderr, flush=True)
    rows = pd.concat(keep, ignore_index=True)
    rows["CHARACTERISTIC_ID"] = rows.CHARACTERISTIC_ID.astype(int)
    rows["value"] = pd.to_numeric(rows.C1_COUNT_TOTAL, errors="coerce")
    wide = rows.pivot_table(index="DGUID", columns="CHARACTERISTIC_ID", values="value", aggfunc="first",
                            dropna=False)
    # Variables not published at DA level (e.g. 2016 population, because DA boundaries changed)
    # stay as all-NaN columns rather than disappearing.
    wide = wide.reindex(columns=list(VARS)).rename(columns=VARS).reset_index()
    wide["ADIDU"] = wide.DGUID.str[-8:]
    DERIVED.mkdir(parents=True, exist_ok=True)
    dest = DERIVED / "census_da_island.parquet"
    wide.to_parquet(dest, index=False)
    print(f"{len(wide)} DAs x {len(VARS)} variables -> {dest.relative_to(ROOT)}", file=sys.stderr)
    print(wide[["pop2021", "median_hh_income", "lim_at_pct", "no_diploma_25_64", "age_0_14"]].describe().round(1).to_string(),
          file=sys.stderr)


if __name__ == "__main__":
    main()
