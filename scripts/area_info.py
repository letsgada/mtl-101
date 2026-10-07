# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Resolve a Montreal quartier and list the schools in it, for the quartier-report skill.

    uv run scripts/area_info.py "Villeray"
    uv run scripts/area_info.py "Mont-Royal" --margin 300 --format json

The polygon comes from the city's Quartiers sociologiques file (32 units over the 19 boroughs,
fetch key `quartiers`). A name that is not a quartier is tried against the agglomeration limits
(a related city such as Mont-Royal or Westmount, or a borough), and the post must then say the
area is the municipality rather than a quartier. West Island units are refused (project scope).

Output: the in-scope schools (francophone public elementary, outside the West Island) whose
building lies inside the polygon, plus those within --margin metres outside it (role `edge`),
each with its program row, IMSE/SFR line and the path of an existing school report; and a note
of the other MEQ buildings inside the polygon (anglophone boards, secondary, adult, private,
and schools whose program row says `specialised`). Writes data/derived/area_<slug>.geojson and
data/derived/area_<slug>_schools.csv for zone_stats.py, zone_map.py and listings_assign.py.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import pandas as pd
import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from school_info import all_buildings, imse_row, programs  # noqa: E402
from zone_stats import CRS, DERIVED, RAW, ROOT, WEST_ISLAND, Data, strip_accents  # noqa: E402

QUARTIERS = RAW / "quartiers-sociologiques.geojson"
PRIVATE = RAW / "pps_prive_etablissement.geojson"
POSTS = ROOT / "posts"
app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


class Format(str, Enum):
    md = "md"
    json = "json"


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def slugify(name: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", name) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def report_path(school_name: str) -> str | None:
    slug = slugify(re.sub(r"^École\s+", "", school_name).split(",")[0]) + "-report"
    for cand in (POSTS / f"{slug}.qmd", POSTS / f"ecole-{slug}.qmd"):
        if cand.exists():
            return str(cand.relative_to(ROOT))
    return None


def resolve_area(d: Data, query: str) -> tuple[str, str, object, str]:
    """Return (name, source, geometry in CRS, borough label). Exact names win over substrings,
    and a quartier wins over a borough or municipality of the same name."""
    key = strip_accents(query)
    q = gpd.read_file(QUARTIERS, engine="pyogrio").to_crs(CRS) if QUARTIERS.exists() else None
    if q is None:
        logger.warning("no {}; run fetch_open_data.py quartiers", QUARTIERS.name)
    b = d.boroughs

    def quartier(r):
        if "Nord-Ouest" in r.Q_sociologique or any(w in str(r.Arrondissement) for w in WEST_ISLAND):
            logger.error("{} is in the West Island; out of scope", r.Q_sociologique)
            raise typer.Exit(1)
        return r.Q_sociologique, "quartier sociologique (Ville de Montréal)", r.geometry, r.Arrondissement

    def municipality(r):
        if r.NOM in WEST_ISLAND:
            logger.error("{} is in the West Island; out of scope", r.NOM)
            raise typer.Exit(1)
        logger.warning("{} is not a quartier in the city file; using the {} boundary instead", r.NOM, r.TYPE.lower())
        return r.NOM, f"{r.TYPE} boundary (agglomeration limits)", r.geometry, r.NOM

    if q is not None:
        exact = q[q.Q_sociologique.map(strip_accents) == key]
        if len(exact) == 1:
            return quartier(exact.iloc[0])
    exact_b = b[b.NOM.map(strip_accents) == key]
    if len(exact_b) == 1:
        return municipality(exact_b.iloc[0])
    if q is not None:
        hit = q[q.Q_sociologique.map(strip_accents).str.contains(key, regex=False)]
        if len(hit) > 1:
            names = "; ".join(f"{r.Q_sociologique} ({r.Arrondissement})" for r in hit.itertuples())
            logger.error("{!r} matches several quartiers: {}. Use the full name.", query, names)
            raise typer.Exit(1)
        if len(hit) == 1:
            return quartier(hit.iloc[0])
    hit = b[b.NOM.map(strip_accents).str.contains(key, regex=False)]
    if len(hit) > 1:
        logger.error("{!r} matches several municipalities or boroughs: {}", query, "; ".join(hit.NOM))
        raise typer.Exit(1)
    if len(hit) == 1:
        return municipality(hit.iloc[0])
    logger.error("no quartier, borough or related city matches {!r}", query)
    raise typer.Exit(1)


def private_inside(geom) -> list[dict]:
    if not PRIVATE.exists():
        return []
    p = gpd.read_file(PRIVATE, engine="pyogrio").to_crs(CRS)
    p = p[p.within(geom)]
    name_col = next((c for c in p.columns if "NOM" in c.upper() and "ORGNS" in c.upper()), None) or \
        next((c for c in p.columns if "NOM" in c.upper()), None)
    out = []
    for r in p.itertuples():
        d = r._asdict()
        out.append(dict(name=d.get(name_col, "?"), kind="private",
                        levels=d.get("ORDRE_ENS", ""), address=d.get("ADRS_GEO_L1_GDUNO_IMM", "")))
    return out


def describe(d: Data, query: str, margin: float) -> dict:
    name, source, geom, borough = resolve_area(d, query)
    slug = slugify(name)
    s = d.schools
    inside = s[s.within(geom)]
    dist = s.distance(geom)
    edge = s[~s.within(geom) & (dist <= margin)]
    prog = programs()
    rows, note = [], []
    for role, part in (("school", inside), ("edge", edge)):
        for r in part.itertuples():
            code = str(r.CD_ORGNS)
            p = prog[prog.code == code]
            ptype = p.iloc[0].program_type if len(p) else None
            im = imse_row(code) or {}
            row = dict(code=code, school=r.NOM_OFFCL_ORGNS, short=re.sub(r"^École\s+", "", r.NOM_OFFCL_ORGNS).split(",")[0],
                       address=r.ADRS_GEO_L1_GDUNO_IMM, lon=float(r.COORD_X_LL84_IMM), lat=float(r.COORD_Y_LL84_IMM),
                       role=role, distance_outside_m=round(float(dist[r.Index])) if role == "edge" else 0,
                       program_type=ptype, admission_model=p.iloc[0].admission_model if len(p) else None,
                       program_notes=p.iloc[0].notes if len(p) else None,
                       imse_decile=im.get("imse_decile"), sfr_decile=im.get("sfr_decile"), pupils=im.get("pupils"),
                       imse_year=im.get("year"), report_path=report_path(r.NOM_OFFCL_ORGNS))
            if ptype == "specialised":
                note.append(dict(name=r.NOM_OFFCL_ORGNS, kind="specialised", levels=r.ORDRE_ENS,
                                 address=r.ADRS_GEO_L1_GDUNO_IMM, mandate=p.iloc[0].notes))
            else:
                rows.append(row)
    raw = all_buildings()
    others = raw[raw.within(geom) & ~raw.CD_ORGNS.astype(str).isin([x["code"] for x in rows])]
    seen = set()
    for r in others.itertuples():
        key = (r.NOM_OFFCL_ORGNS, r.ORDRE_ENS)
        if key in seen or str(r.CD_ORGNS) in {n.get("code") for n in note}:
            continue
        seen.add(key)
        kind = ("anglophone" if r.TYPE_CS != "Franco" else
                "secondary" if r.PRIM != 1 and r.SEC == 1 else
                "adult" if r.ADULTE == 1 else "other")
        if kind == "other" and r.PRIM == 1:
            continue  # a francophone elementary that is in scope would already be in rows
        note.append(dict(name=r.NOM_OFFCL_ORGNS, kind=kind, levels=r.ORDRE_ENS, address=r.ADRS_GEO_L1_GDUNO_IMM,
                         board=r.NOM_CS))
    note.extend(private_inside(geom))
    DERIVED.mkdir(parents=True, exist_ok=True)
    gj = DERIVED / f"area_{slug}.geojson"
    gpd.GeoDataFrame([{"name": name, "source": source, "borough": borough}], geometry=[geom], crs=CRS).to_crs(4326) \
        .to_file(gj, driver="GeoJSON")
    csv = DERIVED / f"area_{slug}_schools.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    return dict(name=name, slug=slug, source=source, borough=borough, area_km2=round(geom.area / 1e6, 2),
                margin_m=margin, schools=rows, also=note, geojson=str(gj.relative_to(ROOT)), csv=str(csv.relative_to(ROOT)))


def markdown(info: dict) -> str:
    L = [f"## {info['name']}", "",
         f"- Polygon: {info['source']}; borough: {info['borough']}; {info['area_km2']} km²",
         f"- In-scope schools: {sum(r['role'] == 'school' for r in info['schools'])} inside, "
         f"{sum(r['role'] == 'edge' for r in info['schools'])} within {info['margin_m']:.0f} m outside (edge)",
         f"- Files: {info['geojson']}, {info['csv']}", "",
         "| Code | School | Role | Address | Program | Admission | IMSE | SFR | Pupils | Report |",
         "|:---|:---|:---|:---|:---|:---|---:|---:|---:|:---|"]
    for r in info["schools"]:
        role = "edge, %d m outside" % r["distance_outside_m"] if r["role"] == "edge" else "inside"
        L.append(f"| {r['code']} | {r['school']} | {role} | {r['address']} | {r['program_type'] or 'unknown'} | "
                 f"{r['admission_model'] or ''} | {r['imse_decile'] if r['imse_decile'] is not None else 'n/a'} | "
                 f"{r['sfr_decile'] if r['sfr_decile'] is not None else ''} | {r['pupils'] or ''} | {r['report_path'] or ''} |")
    L += ["", "### Also in the area (out of scope, no metrics)"]
    if not info["also"]:
        L.append("none")
    for n in info["also"]:
        extra = f" — {n['mandate']}" if n.get("mandate") else (f" ({n['board']})" if n.get("board") else "")
        L.append(f"- {n['name']}: {n['kind']}, {n.get('levels', '')}, {n.get('address', '')}{extra}")
    return "\n".join(L) + "\n"


@app.command()
def main(
    area: Annotated[str, typer.Argument(help="quartier name (city file), or a borough / related city")],
    margin: Annotated[float, typer.Option(help="include schools up to this many metres outside the polygon")] = 300.0,
    fmt_: Annotated[Format, typer.Option("--format")] = Format.md,
    out: Annotated[Optional[Path], typer.Option(help="write here instead of stdout")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Resolve an area and list its in-scope schools, edge schools and the out-of-scope note."""
    setup_logging(verbose)
    info = describe(Data(), area, margin)
    text = markdown(info) if fmt_ is Format.md else json.dumps(info, indent=1, ensure_ascii=False, default=str)
    if out:
        out.write_text(text)
        logger.success("-> {}", out)
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
