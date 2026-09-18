# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "typer>=0.12", "loguru>=0.7"]
# ///
"""Collapse the borough tax-bill files (one line per tax per unit) to one row per account.

    uv run scripts/prep_taxes.py            # all data/raw/taxes-municipales-*.csv, latest year
    uv run scripts/prep_taxes.py --year 2025

Writes data/derived/taxes_<year>.parquet with, per account: ID_CUM (joins to ID_UEV in the
assessment-unit geometry), borough, assessed value, total bill, and a class derived from the
general-tax line: res_le5 (residential, 5 dwellings or fewer, code B00), res_6plus (C00),
nonres (LNR/MNR/BRR), vacant (D00), other. The assessed value is the VAL_IMPOSABLE on the
general-tax line, which is the value the roll assigns to the unit; a few accounts carry
different values on other lines (partial exemptions), which is why the max is not used.
The city notes these are the bills as first issued; later corrections are absent.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"

GENERAL = {"B00": "res_le5", "C00": "res_6plus", "LNR": "nonres", "MNR": "nonres", "BRR": "nonres", "D00": "vacant"}
USECOLS = ["ARRONDISSEMENT", "NOM_ARRONDISSEMENT", "ANNEE_EXERCICE", "ID_CUM", "NO_COMPTE",
           "CODE_DESCR_LONGUE", "VAL_IMPOSABLE", "MONTANT_DETAIL"]

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def one_borough(path: Path, year: str) -> pd.DataFrame:
    parts = []
    for chunk in pd.read_csv(path, usecols=USECOLS, dtype=str, encoding="utf-8-sig", chunksize=500_000):
        parts.append(chunk[chunk.ANNEE_EXERCICE == year])
    t = pd.concat(parts, ignore_index=True)
    t["MONTANT_DETAIL"] = pd.to_numeric(t.MONTANT_DETAIL, errors="coerce")
    t["VAL_IMPOSABLE"] = pd.to_numeric(t.VAL_IMPOSABLE, errors="coerce")
    total = t.groupby("NO_COMPTE", sort=False).agg(
        ID_CUM=("ID_CUM", "first"), borough_no=("ARRONDISSEMENT", "first"),
        borough=("NOM_ARRONDISSEMENT", "first"), bill=("MONTANT_DETAIL", "sum"),
        val_any=("VAL_IMPOSABLE", "max"), n_lines=("MONTANT_DETAIL", "size"))
    gen = t[t.CODE_DESCR_LONGUE.isin(GENERAL)].drop_duplicates("NO_COMPTE").set_index("NO_COMPTE")
    total["cls"] = gen.CODE_DESCR_LONGUE.map(GENERAL).reindex(total.index).fillna("other")
    # Residential general-tax lines carry the full value; non-residential ones are tiered
    # (<= / > 900 000) so their line value is capped. Use the line value for residential only.
    total["value"] = gen.VAL_IMPOSABLE.reindex(total.index).where(
        total.cls.isin(["res_le5", "res_6plus"]), total.val_any).fillna(total.val_any)
    total["year"] = int(year)
    return total.drop(columns="val_any").reset_index()


@app.command()
def main(
    year: Annotated[str, typer.Option(help="taxation year to keep")] = "2026",
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Collapse borough tax-bill CSVs to one row per account."""
    setup_logging(verbose)
    files = sorted(RAW.glob("taxes-municipales-*.csv"))
    if not files:
        logger.error("no tax files; run: uv run scripts/fetch_open_data.py taxes")
        raise typer.Exit(1)
    DERIVED.mkdir(parents=True, exist_ok=True)
    frames = []
    for f in files:
        slug = re.sub(r"^taxes-municipales-|\.csv$", "", f.name)
        df = one_borough(f, year)
        df["borough_slug"] = slug
        logger.info("{:45} {:7} accounts, median res_le5 value {:>12,.0f}", slug, len(df),
                    df.loc[df.cls == "res_le5", "value"].median())
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    dest = DERIVED / f"taxes_{year}.parquet"
    out.to_parquet(dest, index=False)
    logger.success("{} accounts -> {}", len(out), dest.relative_to(ROOT))


if __name__ == "__main__":
    app()
