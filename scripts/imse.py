# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "typer>=0.12", "loguru>=0.7"]
# ///
"""Look up a school's MEQ deprivation indices (IMSE and SFR) from the yearly open file.

    uv run scripts/imse.py "Laurier"
    uv run scripts/imse.py 762103 762071 --format json
    uv run scripts/imse.py "Saint-Clément" --all-quebec

Reads data/raw/defav_ecole_prim_public.csv (fetch key `imse`). By default only the three
in-scope service centres are searched: CSSDM 762000, CSSMB 763000, CSSPI 761000.

The IMSE is a socioeconomic index, not an academic ranking: two thirds mother's education,
one third parental employment, assigned by the pupils' home address and averaged per school,
ranked in deciles from 1 (most advantaged) to 10 (most disadvantaged). Deciles 8 to 10 are the
official "milieu défavorisé" and bring extra funding. The SFR is the low-income-threshold share
of families, same decile convention. Both describe the enrolled pupils, not the residents of
the zone around the school.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "defav_ecole_prim_public.csv"
IN_SCOPE_CSS = {"762000": "CSSDM", "763000": "CSSMB", "761000": "CSSPI"}
CAVEAT = ("IMSE and SFR are socioeconomic indices of the enrolled pupils (deciles 1 = most advantaged, "
          "10 = most disadvantaged; 8-10 = milieu défavorisé), not measures of academic performance.")

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


class Format(str, Enum):
    md = "md"
    json = "json"


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()


def load(all_quebec: bool) -> pd.DataFrame:
    if not SRC.exists():
        logger.error("missing {}; run: uv run scripts/fetch_open_data.py imse", SRC.name)
        raise typer.Exit(1)
    df = pd.read_csv(SRC, dtype=str, encoding="utf-8-sig")
    df["school_name"] = df.Nom_Org.str.replace(r"\s*\(\d+\)\s*$", "", regex=True)
    df["css"] = df.Code_Cs.map(IN_SCOPE_CSS).fillna(df.Nom_Cs)
    if not all_quebec:
        df = df[df.Code_Cs.isin(IN_SCOPE_CSS)]
    for c in ["IMSE", "SFR"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["Rang_Decile_IMSE", "Rang_Decile_SFR", "Nbre_Eleves"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def find(df: pd.DataFrame, q: str) -> pd.DataFrame:
    if q.isdigit():
        return df[df.Code_Org == q]
    key = strip_accents(q)
    return df[df.school_name.map(strip_accents).str.contains(key, regex=False)]


def row_dict(r) -> dict:
    dec = r.Rang_Decile_IMSE
    return dict(
        code=r.Code_Org, school=r.school_name, css=r.css, year=r.Annee_Scol, published=r.Diffusion == "OUI",
        imse=None if pd.isna(r.IMSE) else round(float(r.IMSE), 2),
        imse_decile=None if pd.isna(dec) else int(dec),
        milieu_defavorise=None if pd.isna(dec) else bool(dec >= 8),
        sfr=None if pd.isna(r.SFR) else round(float(r.SFR), 2),
        sfr_decile=None if pd.isna(r.Rang_Decile_SFR) else int(r.Rang_Decile_SFR),
        pupils=None if pd.isna(r.Nbre_Eleves) else int(r.Nbre_Eleves),
    )


def markdown(rows: list[dict]) -> str:
    out = ["| School | Code | CSS | Year | IMSE | IMSE decile | SFR | SFR decile | Pupils |",
           "|:---|:---|:---|:---|---:|---:|---:|---:|---:|"]
    for r in rows:
        if not r["published"]:
            out.append(f"| {r['school']} | {r['code']} | {r['css']} | {r['year']} | not published | | | | |")
            continue
        flag = " (milieu défavorisé)" if r["milieu_defavorise"] else ""
        out.append(f"| {r['school']} | {r['code']} | {r['css']} | {r['year']} | {r['imse']:.2f} | "
                   f"{r['imse_decile']}{flag} | {r['sfr']:.2f} | {r['sfr_decile']} | {r['pupils']:,} |")
    out += ["", f"Source: MEQ, *Indices de défavorisation*, Données Québec, school year {rows[0]['year']}. {CAVEAT}"]
    return "\n".join(out) + "\n"


@app.command()
def main(
    schools: Annotated[list[str], typer.Argument(help="MEQ school codes or name fragments")],
    fmt_: Annotated[Format, typer.Option("--format")] = Format.md,
    all_quebec: Annotated[bool, typer.Option("--all-quebec", help="search every service centre, not only the three in scope")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Print IMSE and SFR deciles for one or more public elementary schools."""
    setup_logging(verbose)
    df = load(all_quebec)
    rows = []
    for q in schools:
        hit = find(df, q)
        if len(hit) == 0:
            logger.error("no school matches {!r} in {}", q, "Quebec" if all_quebec else "CSSDM/CSSMB/CSSPI")
            raise typer.Exit(1)
        if len(hit) > 1:
            names = "; ".join(f"{r.school_name} [{r.Code_Org}]" for r in hit.itertuples())
            logger.error("{!r} is ambiguous: {}. Use the code in brackets.", q, names)
            raise typer.Exit(1)
        r = hit.iloc[0]
        d = row_dict(r)
        if not d["published"]:
            logger.warning("{} has no published index this year (Diffusion = NON)", d["school"])
        rows.append(d)
    typer.echo(markdown(rows) if fmt_ is Format.md else json.dumps(rows, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    app()
