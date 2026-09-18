# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Resolve a school and describe it: buildings, borough, deprivation deciles, program, and the
schools a parent might compare it with.

    uv run scripts/school_info.py "Laurier"
    uv run scripts/school_info.py 762103 --nearest 8 --same-program --format json

Scope is the francophone public elementary schools on the island of Montreal outside the West
Island (the same set zone_stats.py uses for deciles). A query that matches a school outside that
set is refused with the reason (anglophone board, secondary only, West Island, off-island).

Program and admission data come from data/schools_programs.csv, a hand-checked table grown one
school at a time by the school-report skill; a school with no row has an unknown program, which
is not the same as a regular one.
"""
from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import pandas as pd
import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zone_stats import CRS, RAW, ROOT, WEST_ISLAND, Data, strip_accents  # noqa: E402

PROGRAMS = ROOT / "data" / "schools_programs.csv"
IMSE_CSV = RAW / "defav_ecole_prim_public.csv"

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


class Format(str, Enum):
    md = "md"
    json = "json"


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def all_buildings() -> gpd.GeoDataFrame:
    """Every MEQ school-building point in Quebec, untouched, for out-of-scope explanations."""
    return gpd.read_file(RAW / "pps_public_ecole.geojson", engine="pyogrio").to_crs(CRS)


def programs() -> pd.DataFrame:
    if not PROGRAMS.exists():
        logger.warning("no {} yet; program and same-program are unknown", PROGRAMS.relative_to(ROOT))
        return pd.DataFrame(columns=["code", "school", "css", "program_type", "admission_model", "notes",
                                     "source_url", "checked_on"])
    return pd.read_csv(PROGRAMS, dtype=str).fillna("")


def imse_row(code: str) -> dict | None:
    if not IMSE_CSV.exists():
        return None
    df = pd.read_csv(IMSE_CSV, dtype=str, encoding="utf-8-sig")
    hit = df[df.Code_Org == code]
    if hit.empty:
        return None
    r = hit.iloc[0]
    if r.Diffusion != "OUI":
        return dict(year=r.Annee_Scol, published=False)
    return dict(year=r.Annee_Scol, published=True, imse=round(float(r.IMSE), 2), imse_decile=int(r.Rang_Decile_IMSE),
                sfr=round(float(r.SFR), 2), sfr_decile=int(r.Rang_Decile_SFR), pupils=int(r.Nbre_Eleves),
                milieu_defavorise=int(r.Rang_Decile_IMSE) >= 8)


def explain_out_of_scope(raw: gpd.GeoDataFrame, boroughs: gpd.GeoDataFrame, q: str) -> str | None:
    key = strip_accents(q)
    m = raw[raw.CD_ORGNS.astype(str).eq(q) | raw.NOM_OFFCL_ORGNS.map(strip_accents).str.contains(key, regex=False)]
    if m.empty:
        return None
    r = m.iloc[0]
    if r.TYPE_CS != "Franco":
        return f"{r.NOM_OFFCL_ORGNS} belongs to an anglophone board ({r.NOM_CS}); out of scope"
    if r.PRIM != 1:
        return f"{r.NOM_OFFCL_ORGNS} is not an elementary school ({r.ORDRE_ENS}); out of scope"
    if not str(r.CD_MUNCP_GDUNO_IMM).startswith("66"):
        return f"{r.NOM_OFFCL_ORGNS} is off the island ({r.NOM_MUNCP_GDUNO_IMM}); out of scope"
    b = boroughs[boroughs.contains(r.geometry)]
    if len(b) and b.NOM.iloc[0] in WEST_ISLAND:
        return f"{r.NOM_OFFCL_ORGNS} is in the West Island ({b.NOM.iloc[0]}); out of scope"
    return f"{r.NOM_OFFCL_ORGNS} is out of scope for an unlisted reason"


def resolve(d: Data, raw: gpd.GeoDataFrame, q: str):
    s = d.schools
    if q.isdigit():
        hit = s[s.CD_ORGNS.astype(str) == q]
    else:
        key = strip_accents(q)
        hit = s[s.NOM_OFFCL_ORGNS.map(strip_accents).str.contains(key, regex=False)
                | s.NOM_COURT_ORGNS.map(strip_accents).str.contains(key, regex=False)]
    if len(hit) == 0:
        why = explain_out_of_scope(raw, d.boroughs, q)
        logger.error(why or f"no francophone public elementary school on the island matches {q!r}")
        raise typer.Exit(1)
    if len(hit) > 1:
        names = "; ".join(f"{r.NOM_OFFCL_ORGNS} [{r.CD_ORGNS}]" for r in hit.itertuples())
        logger.error("{!r} is ambiguous: {}. Use the code in brackets.", q, names)
        raise typer.Exit(1)
    return hit.iloc[0]


def describe(d: Data, raw: gpd.GeoDataFrame, prog: pd.DataFrame, school, nearest: int, same_program: bool) -> dict:
    code = str(school.CD_ORGNS)
    blds = raw[raw.CD_ORGNS.astype(str) == code]
    buildings = [dict(name=b.NOM_IMM, address=b.ADRS_GEO_L1_GDUNO_IMM, postal=b.CD_POSTL_GDUNO_IMM,
                      levels=b.ORDRE_ENS, lon=b.COORD_X_LL84_IMM, lat=b.COORD_Y_LL84_IMM,
                      code=str(b.CD_IMM)) for b in blds.itertuples()]
    b = d.boroughs[d.boroughs.contains(school.geometry)]
    out = dict(code=code, school=school.NOM_OFFCL_ORGNS, short=school.NOM_COURT_ORGNS, css=school.NOM_CS,
               css_code=str(school.CD_CS), website=school.SITE_WEB_ORGNS, borough=b.NOM.iloc[0] if len(b) else None,
               riding=school.NOM_CEP, point_building=school.NOM_IMM, point_address=school.ADRS_GEO_L1_GDUNO_IMM,
               lon=school.COORD_X_LL84_IMM, lat=school.COORD_Y_LL84_IMM, buildings=buildings)
    out["imse"] = imse_row(code)
    p = prog[prog.code == code]
    out["program"] = p.iloc[0].to_dict() if len(p) else None

    others = d.schools[d.schools.CD_ORGNS.astype(str) != code].copy()
    others["distance_m"] = others.geometry.distance(school.geometry)
    bj = gpd.sjoin(others[["geometry"]], d.boroughs[["NOM", "geometry"]], how="left", predicate="within")
    others["borough"] = bj.NOM.reindex(others.index).values
    others = others.merge(prog[["code", "program_type", "admission_model"]], left_on=others.CD_ORGNS.astype(str),
                          right_on="code", how="left").drop(columns="code")
    cols = ["CD_ORGNS", "NOM_OFFCL_ORGNS", "borough", "distance_m", "program_type", "admission_model"]

    def rows(df):
        return [dict(code=str(r.CD_ORGNS), school=r.NOM_OFFCL_ORGNS, borough=r.borough, distance_m=round(r.distance_m),
                     program_type=r.program_type if isinstance(r.program_type, str) else None,
                     admission_model=r.admission_model if isinstance(r.admission_model, str) else None)
                for r in df[cols].itertuples()]

    out["nearest"] = rows(others.nsmallest(nearest, "distance_m")) if nearest else []
    if same_program:
        pt = out["program"]["program_type"] if out["program"] else None
        if pt and pt != "regular":
            out["same_program"] = rows(others[others.program_type == pt].sort_values("distance_m"))
        else:
            out["same_program"] = []
            out["same_program_note"] = ("program unknown: no row in schools_programs.csv" if not pt
                                        else "regular program: same-program comparison not meaningful")
    return out


def markdown(info: dict) -> str:
    L = [f"## {info['school']} [{info['code']}]", "",
         f"- Service centre: {info['css']} ({info['css_code']})",
         f"- Borough: {info['borough']}; provincial riding: {info['riding']}",
         f"- Website: {info['website']}",
         f"- MEQ point: {info['point_building']}, {info['point_address']} ({info['lon']:.6f}, {info['lat']:.6f})", ""]
    L.append("| Building | Address | Postal | Levels | Lon | Lat |")
    L.append("|:---|:---|:---|:---|---:|---:|")
    for b in info["buildings"]:
        L.append(f"| {b['name']} | {b['address']} | {b['postal']} | {b['levels']} | {b['lon']:.6f} | {b['lat']:.6f} |")
    L.append("")
    im = info["imse"]
    if im is None:
        L.append("IMSE: not in the fetched file (run fetch_open_data.py imse).")
    elif not im["published"]:
        L.append(f"IMSE: not published for {im['year']}.")
    else:
        flag = " (milieu défavorisé)" if im["milieu_defavorise"] else ""
        L.append(f"IMSE {im['year']}: {im['imse']:.2f}, decile {im['imse_decile']}{flag}; SFR {im['sfr']:.2f}, "
                 f"decile {im['sfr_decile']}; {im['pupils']:,} pupils. Socioeconomic index of enrolled pupils, "
                 "not an academic ranking.")
    p = info["program"]
    L.append("" if not p else f"Program (schools_programs.csv, checked {p['checked_on']}): {p['program_type']}, "
             f"admission {p['admission_model']}; {p['notes']} ({p['source_url']})")
    if p is None:
        L.append("Program: unknown (no row in data/schools_programs.csv).")
    L.append("")

    def table(title, rows):
        L.append(f"### {title}")
        L.append("| Code | School | Borough | Distance (m) | Program | Admission |")
        L.append("|:---|:---|:---|---:|:---|:---|")
        for r in rows:
            L.append(f"| {r['code']} | {r['school']} | {r['borough']} | {r['distance_m']:,} | "
                     f"{r['program_type'] or ''} | {r['admission_model'] or ''} |")
        L.append("")

    if info["nearest"]:
        table("Nearest in-scope schools", info["nearest"])
    if "same_program" in info:
        if info["same_program"]:
            table("Same program", info["same_program"])
        else:
            L.append(f"Same program: none listed ({info.get('same_program_note', '')}).")
    return "\n".join(L) + "\n"


@app.command()
def main(
    schools: Annotated[list[str], typer.Argument(help="school name fragments or MEQ organisation codes")],
    nearest: Annotated[int, typer.Option(help="how many nearest in-scope schools to list (0 = none)")] = 8,
    same_program: Annotated[bool, typer.Option("--same-program", help="also list schools with the same program type")] = False,
    fmt_: Annotated[Format, typer.Option("--format")] = Format.md,
    out: Annotated[Optional[Path], typer.Option(help="write here instead of stdout")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Resolve schools and print their facts, buildings, deciles and comparator candidates."""
    setup_logging(verbose)
    d = Data()
    raw = all_buildings()
    prog = programs()
    infos = [describe(d, raw, prog, resolve(d, raw, q), nearest, same_program) for q in schools]
    text = "\n".join(markdown(i) for i in infos) if fmt_ is Format.md else json.dumps(infos, indent=1, ensure_ascii=False)
    if out:
        out.write_text(text)
        logger.success("-> {}", out)
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
