# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Layer 2 of MTL-101: describe the neighbourhood around a school as a place to live.

    uv run scripts/zone_stats.py "Saint-Barthélemy" "La Vérendrye" "Charles-Lemoyne"
    uv run scripts/zone_stats.py --point -73.5978 45.4838 --label "NDG permanent site"
    uv run scripts/zone_stats.py --all            # every francophone public elementary school on the island
    uv run scripts/zone_stats.py --radius 800 --format csv --out data/derived/seed.csv "Saint-Nom-de-Jésus"

The zone is a circle of --radius metres (default 1 000) around the school building, because
no per-school catchment polygon exists as open data (project_brief.md, Layer 2). Everything
with point, parcel or dissemination-area (DA) granularity is aggregated to that circle:
DAs by centroid, assessment units and incidents by location. Collisions use a tighter
--collision-radius (default 500 m) because they are about the walk to school.

Each metric is reported with its decile among all island francophone public elementary
schools (1 = lowest tenth, 10 = highest), computed by --all and cached in
data/derived/zone_stats_all.parquet. The script computes no composite score.

Inputs (see fetch_open_data.py, prep_taxes.py, prep_uev.py, census_da.py):
  data/raw/pps_public_ecole.geojson         MEQ school points
  data/raw/ad2021inddef.zip                 INSPQ DA polygons, 2021 population, deprivation quintiles
  data/derived/census_da_island.parquet     2021 Census Profile variables per DA
  data/raw/iemv_2026.geojson                Ville de Montréal equity index per DA (city territory only)
  data/raw/actes-criminels.csv              SPVM incidents (points obfuscated to intersections)
  data/raw/collisions_routieres.csv         SAAQ collisions 2012-2021 with pedestrian/cyclist victims
  data/derived/uev_points.parquet           assessment units as points
  data/derived/taxes_2026.parquet           one row per tax account: assessed value, bill, class
  data/raw/espace_vert.json                 parks
  data/raw/limites-administratives-agglomeration.geojson
"""
from __future__ import annotations

import json
import math
import sys
import unicodedata
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import typer
from loguru import logger
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DERIVED = ROOT / "data" / "derived"
ALL_CACHE = DERIVED / "zone_stats_all.parquet"
CRS = 32188  # MTM zone 8, metres

CRIME_YEARS = (2023, 2024, 2025)          # last three complete years in the SPVM file
COLLISION_YEARS = (2017, 2018, 2019, 2020, 2021)  # last five years the SAAQ extract covers
VIOLENT = {"Vols qualifiés", "Infractions entrainant la mort"}
VEHICLE = {"Vol dans / sur véhicule à moteur", "Vol de véhicule à moteur"}
PARK_TYPES = {"Grand parc", "Parc d'arrondissement"}
# Out of scope per project_brief.md: the West Island (boroughs and related cities west of Lachine /
# Saint-Laurent). Schools there are excluded from the decile reference.
WEST_ISLAND = {"Pierrefonds-Roxboro", "L'Île-Bizard-Sainte-Geneviève", "Dollard-des-Ormeaux", "Pointe-Claire",
               "Beaconsfield", "Kirkland", "Dorval", "L'Île-Dorval", "Baie-D'Urfé", "Sainte-Anne-de-Bellevue",
               "Senneville"}

# key, label, unit, format. Order is the report order.
METRICS = [
    ("pop_2021", "Residents (2021 census)", "people", "{:,.0f}"),
    ("children_0_14_pct", "Children 0 to 14", "% of residents", "{:.1f}"),
    ("hh_with_children_pct", "Households with children", "% of households", "{:.1f}"),
    ("median_hh_income", "Median household income (2020)", "$", "{:,.0f}"),
    ("lim_at_pct", "Low income (LIM-AT)", "% of residents", "{:.1f}"),
    ("no_diploma_25_64_pct", "No diploma, ages 25 to 64", "%", "{:.1f}"),
    ("immigrants_pct", "Immigrants", "% of residents", "{:.1f}"),
    ("french_home_pct", "French most often at home", "% of residents", "{:.1f}"),
    ("renter_pct", "Renter households", "%", "{:.1f}"),
    ("movers5_pct", "Moved in the last five years", "% of residents", "{:.1f}"),
    ("pampalon_material_q45_pct", "In materially deprived DAs (INSPQ Q4-5)", "% of residents", "{:.0f}"),
    ("pampalon_social_q45_pct", "In socially deprived DAs (INSPQ Q4-5)", "% of residents", "{:.0f}"),
    ("iemv_mean", "Equity index IEMV 2026 (0 best, 6 worst)", "score", "{:.1f}"),
    ("crime_total", "Crime incidents per 1 000 residents per year", "/1000/yr", "{:.1f}"),
    ("crime_violent", "  violent (robbery, homicide)", "/1000/yr", "{:.2f}"),
    ("crime_breakins", "  break-ins", "/1000/yr", "{:.1f}"),
    ("crime_vehicle", "  vehicle theft and theft from vehicles", "/1000/yr", "{:.1f}"),
    ("crime_mischief", "  mischief", "/1000/yr", "{:.1f}"),
    ("ped_cycl_victims_per_yr", "Pedestrian and cyclist victims within 500 m", "/yr", "{:.1f}"),
    ("dwellings", "Dwellings", "units", "{:,.0f}"),
    ("single_pct", "Single-family houses", "% of dwellings", "{:.0f}"),
    ("plex_pct", "Plex units (2 to 5 per building)", "% of dwellings", "{:.0f}"),
    ("condo_pct", "Condominium units", "% of dwellings", "{:.0f}"),
    ("apt6_pct", "Rental buildings, 6+ units", "% of dwellings", "{:.0f}"),
    ("median_year_built", "Median year built", "year", "{:.0f}"),
    ("value_single_median", "Assessed value, single-family", "$", "{:,.0f}"),
    ("value_plex_median", "Assessed value, plex", "$", "{:,.0f}"),
    ("value_condo_median", "Assessed value, condo", "$", "{:,.0f}"),
    ("bill_single_median", "2026 tax bill, single-family", "$", "{:,.0f}"),
    ("bill_plex_median", "2026 tax bill, plex", "$", "{:,.0f}"),
    ("bill_condo_median", "2026 tax bill, condo", "$", "{:,.0f}"),
    ("tax_rate_pct", "Effective tax rate (bill / value)", "%", "{:.2f}"),
    ("park_pct", "Park area", "% of zone", "{:.1f}"),
    ("park_ha_per_1000", "Park area per 1 000 residents", "ha", "{:.2f}"),
]


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower()


def wmedian(values: pd.Series, weights: pd.Series) -> float:
    m = values.notna() & weights.notna() & (weights > 0)
    if not m.any():
        return float("nan")
    v, w = values[m].to_numpy(float), weights[m].to_numpy(float)
    o = np.argsort(v)
    cw = np.cumsum(w[o])
    return float(v[o][np.searchsorted(cw, cw[-1] / 2)])


def ratio(num: float, den: float, scale: float = 100.0) -> float:
    return float(num) / float(den) * scale if den and not math.isnan(den) and den > 0 else float("nan")


class Data:
    """Lazy loaders; each dataset is read once per process."""

    @cached_property
    def schools(self) -> gpd.GeoDataFrame:
        s = gpd.read_file(RAW / "pps_public_ecole.geojson", engine="pyogrio")
        s = s[(s.PRIM == 1) & (s.TYPE_CS == "Franco") & s.CD_MUNCP_GDUNO_IMM.astype(str).str.startswith("66")]
        s = s.sort_values(["CD_ORGNS", "PRESC"], ascending=[True, False]).drop_duplicates("CD_ORGNS")
        s = s.to_crs(CRS)
        joined = gpd.sjoin(s, self.boroughs[["NOM", "geometry"]], how="left", predicate="within")
        s = s[~joined.NOM.reindex(s.index).isin(WEST_ISLAND).values]
        return s

    @cached_property
    def das(self) -> gpd.GeoDataFrame:
        da = gpd.read_file(f"/vsizip/{RAW / 'ad2021inddef.zip'}/Ad_2021_IndDef.shp", engine="pyogrio")
        da = da[da.SDRIDU.astype(str).str.startswith("2466")].to_crs(CRS)
        da["geometry"] = da.geometry.centroid
        da = da[["ADIDU", "ADPOP2021", "QuintMat", "QuintSoc", "SDRNOM", "geometry"]]
        census = pd.read_parquet(DERIVED / "census_da_island.parquet")
        for col in ["pop2021", "pop2016", "age_total", "age_0_14", "hh_total", "hh_couple_with_children",
                    "hh_one_parent", "median_hh_income", "lim_at_pct", "pop_private_hh", "no_diploma_25_64",
                    "educ_25_64_total", "immigrants", "imm_total", "lang_home_french", "lang_home_total",
                    "renter", "tenure_total", "movers5", "mob5_total"]:
            if col not in census:
                census[col] = np.nan  # not published at DA level in this census release
        da = da.merge(census.drop(columns="DGUID"), on="ADIDU", how="left")
        iemv = gpd.read_file(RAW / "iemv_2026.geojson", engine="pyogrio", read_geometry=False)
        iemv = iemv[["ADIDU", "Indice_emv", "niveau"]].astype({"ADIDU": str})
        da["ADIDU"] = da.ADIDU.astype(str)
        da = da.merge(iemv, on="ADIDU", how="left")
        da["pop"] = da.pop2021.fillna(da.ADPOP2021)
        return gpd.GeoDataFrame(da, geometry="geometry", crs=CRS)

    @cached_property
    def crimes(self) -> gpd.GeoDataFrame:
        c = pd.read_csv(RAW / "actes-criminels.csv", usecols=["CATEGORIE", "DATE", "LONGITUDE", "LATITUDE"])
        c["year"] = c.DATE.str[:4].astype(int)
        c = c[c.year.isin(CRIME_YEARS) & c.LONGITUDE.notna()]
        c["group"] = np.select([c.CATEGORIE.isin(VIOLENT), c.CATEGORIE.eq("Introduction"),
                                c.CATEGORIE.isin(VEHICLE), c.CATEGORIE.eq("Méfait")],
                               ["violent", "breakins", "vehicle", "mischief"], "other")
        return gpd.GeoDataFrame(c, geometry=gpd.points_from_xy(c.LONGITUDE, c.LATITUDE), crs=4326).to_crs(CRS)

    @cached_property
    def collisions(self) -> gpd.GeoDataFrame:
        k = pd.read_csv(RAW / "collisions_routieres.csv", low_memory=False,
                        usecols=["AN", "LOC_LONG", "LOC_LAT", "NB_VICTIMES_PIETON", "NB_VICTIMES_VELO"])
        k = k[k.AN.isin(COLLISION_YEARS) & k.LOC_LONG.notna()]
        k["victims"] = k.NB_VICTIMES_PIETON.fillna(0) + k.NB_VICTIMES_VELO.fillna(0)
        k = k[k.victims > 0]
        return gpd.GeoDataFrame(k, geometry=gpd.points_from_xy(k.LOC_LONG, k.LOC_LAT), crs=4326).to_crs(CRS)

    @cached_property
    def units(self) -> gpd.GeoDataFrame:
        u = pd.read_parquet(DERIVED / "uev_points.parquet")
        t = pd.read_parquet(DERIVED / "taxes_2026.parquet")[["ID_CUM", "cls", "value", "bill"]]
        u = u.merge(t, left_on="ID_UEV", right_on="ID_CUM", how="left")
        res = u.CODE_UTILISATION.astype(str).str.startswith("1")  # CUBF 1xxx = residential
        n = u.NOMBRE_LOGEMENT
        u["kind"] = np.select(
            [u.CATEGORIE_UEF.eq("Condominium") & res,
             u.CATEGORIE_UEF.eq("Régulier") & res & n.eq(1),
             u.CATEGORIE_UEF.eq("Régulier") & res & n.between(2, 5),
             u.CATEGORIE_UEF.eq("Régulier") & res & n.ge(6)],
            ["condo", "single", "plex", "apt6"], "other")
        u["dwellings"] = np.where(u.kind.eq("condo"), 1, n.fillna(0))
        return gpd.GeoDataFrame(u, geometry=gpd.points_from_xy(u.x, u.y), crs=CRS)

    @cached_property
    def parks(self) -> gpd.GeoDataFrame:
        p = gpd.read_file(RAW / "espace_vert.json", engine="pyogrio").to_crs(CRS)
        return p[p.TYPO1.isin(PARK_TYPES)][["Nom", "TYPO1", "geometry"]]

    @cached_property
    def boroughs(self) -> gpd.GeoDataFrame:
        return gpd.read_file(RAW / "limites-administratives-agglomeration.geojson", engine="pyogrio").to_crs(CRS)


def zone_stats(d: Data, x: float, y: float, radius: float, collision_radius: float) -> dict:
    buf = Point(x, y).buffer(radius)
    out: dict = {}

    b = d.boroughs[d.boroughs.contains(Point(x, y))]
    out["borough"] = b.NOM.iloc[0] if len(b) else None

    das = d.das.iloc[d.das.sindex.query(buf, predicate="contains")]
    out["n_da"] = len(das)
    pop = das["pop"].sum()
    out["pop_2021"] = pop
    out["children_0_14_pct"] = ratio(das.age_0_14.sum(), das.age_total.sum())
    out["hh_with_children_pct"] = ratio(das.hh_couple_with_children.sum() + das.hh_one_parent.sum(), das.hh_total.sum())
    out["median_hh_income"] = wmedian(das.median_hh_income, das.hh_total)
    lim = das.lim_at_pct.notna() & das.pop_private_hh.notna()
    out["lim_at_pct"] = ratio((das.lim_at_pct[lim] * das.pop_private_hh[lim]).sum(), das.pop_private_hh[lim].sum(), 1)
    out["no_diploma_25_64_pct"] = ratio(das.no_diploma_25_64.sum(), das.educ_25_64_total.sum())
    out["immigrants_pct"] = ratio(das.immigrants.sum(), das.imm_total.sum())
    out["french_home_pct"] = ratio(das.lang_home_french.sum(), das.lang_home_total.sum())
    out["renter_pct"] = ratio(das.renter.sum(), das.tenure_total.sum())
    out["movers5_pct"] = ratio(das.movers5.sum(), das.mob5_total.sum())
    qm = das[das.QuintMat > 0]
    out["pampalon_material_q45_pct"] = ratio(qm.loc[qm.QuintMat >= 4, "pop"].sum(), qm["pop"].sum())
    qs = das[das.QuintSoc > 0]
    out["pampalon_social_q45_pct"] = ratio(qs.loc[qs.QuintSoc >= 4, "pop"].sum(), qs["pop"].sum())
    ie = das[das.Indice_emv.notna()]
    out["iemv_mean"] = ratio((ie.Indice_emv * ie["pop"]).sum(), ie["pop"].sum(), 1)
    out["iemv_coverage_pct"] = ratio(ie["pop"].sum(), pop)

    cr = d.crimes.iloc[d.crimes.sindex.query(buf, predicate="contains")]
    per_year = len(CRIME_YEARS)
    out["crime_total"] = ratio(len(cr) / per_year, pop, 1000)
    for g in ["violent", "breakins", "vehicle", "mischief"]:
        out[f"crime_{g}"] = ratio((cr.group == g).sum() / per_year, pop, 1000)

    cbuf = Point(x, y).buffer(collision_radius)
    co = d.collisions.iloc[d.collisions.sindex.query(cbuf, predicate="contains")]
    out["ped_cycl_victims_per_yr"] = co.victims.sum() / len(COLLISION_YEARS)

    un = d.units.iloc[d.units.sindex.query(buf, predicate="contains")]
    resu = un[un.kind != "other"]
    dw = resu.dwellings.sum()
    out["dwellings"] = dw
    for k in ["single", "plex", "condo", "apt6"]:
        out[f"{k}_pct"] = ratio(resu.loc[resu.kind == k, "dwellings"].sum(), dw)
    yb = resu.ANNEE_CONSTRUCTION.where(resu.ANNEE_CONSTRUCTION.between(1600, 2030))
    out["median_year_built"] = wmedian(yb, resu.dwellings)
    tx = resu[resu.cls.eq("res_le5") & resu.value.gt(0)]
    for k in ["single", "plex", "condo"]:
        sub = tx[tx.kind == k]
        out[f"value_{k}_median"] = sub.value.median() if len(sub) >= 10 else float("nan")
        out[f"bill_{k}_median"] = sub.bill.median() if len(sub) >= 10 else float("nan")
    out["tax_rate_pct"] = ratio(tx.bill.median(), tx.value.median()) if len(tx) >= 10 else float("nan")
    out["tax_coverage_pct"] = ratio(resu.cls.notna().sum(), len(resu))

    pk = d.parks.iloc[d.parks.sindex.query(buf, predicate="intersects")]
    park_area = pk.geometry.intersection(buf).area.sum()
    out["park_pct"] = ratio(park_area, buf.area)
    out["park_ha_per_1000"] = ratio(park_area / 10_000, pop, 1000)
    return out


def find_schools(d: Data, queries: list[str]) -> gpd.GeoDataFrame:
    rows = []
    for q in queries:
        s = d.schools
        if q.isdigit():
            hit = s[s.CD_ORGNS.astype(str) == q]
        else:
            key = strip_accents(q)
            hit = s[s.NOM_OFFCL_ORGNS.map(strip_accents).str.contains(key, regex=False)
                    | s.NOM_COURT_ORGNS.map(strip_accents).str.contains(key, regex=False)]
        if len(hit) == 0:
            logger.error("no francophone public elementary school on the island matches {!r}", q)
            raise typer.Exit(1)
        if len(hit) > 1:
            names = "; ".join(f"{r.NOM_OFFCL_ORGNS} [{r.CD_ORGNS}]" for r in hit.itertuples())
            logger.error("{!r} is ambiguous: {}. Use the code in brackets.", q, names)
            raise typer.Exit(1)
        rows.append(hit)
    return pd.concat(rows)


def school_row(s) -> dict:
    return dict(code=str(s.CD_ORGNS), school=s.NOM_OFFCL_ORGNS, building=s.NOM_IMM,
                address=s.ADRS_GEO_L1_GDUNO_IMM, css=s.NOM_CS, lon=s.COORD_X_LL84_IMM, lat=s.COORD_Y_LL84_IMM)


def run_all(d: Data, radius: float, collision_radius: float) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(d.schools.itertuples(), 1):
        row = school_row(s)
        row.update(zone_stats(d, s.geometry.x, s.geometry.y, radius, collision_radius))
        rows.append(row)
        if i % 25 == 0:
            logger.info("  {}/{}", i, len(d.schools))
    df = pd.DataFrame(rows)
    df.attrs.update(radius=radius, collision_radius=collision_radius)
    DERIVED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(ALL_CACHE, index=False)
    df.to_csv(ALL_CACHE.with_suffix(".csv"), index=False)
    return df


def deciles(ref: pd.DataFrame, key: str, value: float) -> float:
    col = ref[key].dropna()
    if len(col) < 10 or value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    return float(min(10, math.floor((col < value).mean() * 10) + 1))


def fmt(key: str, value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "n/a"
    f = next(f for k, _, _, f in METRICS if k == key)
    return f.format(value)


def markdown(results: list[dict], ref: pd.DataFrame | None, radius: float) -> str:
    heads = [r.get("label") or r["school"] for r in results]
    lines = ["| Metric | Unit | " + " | ".join(heads) + (" | Island median |" if ref is not None else "|"),
             "|---|---|" + "---:|" * len(results) + ("---:|" if ref is not None else "")]
    for key, label, unit, _ in METRICS:
        cells = []
        for r in results:
            v = r.get(key)
            cell = fmt(key, v)
            if ref is not None:
                dec = deciles(ref, key, v)
                if not math.isnan(dec):
                    cell += f" (d{int(dec)})"
            cells.append(cell)
        med = fmt(key, ref[key].median()) if ref is not None else None
        lines.append(f"| {label} | {unit} | " + " | ".join(cells) + (f" | {med} |" if ref is not None else " |"))
    notes = [f"Zone = {radius:.0f} m circle around the school building; collisions within 500 m. "
             f"(dN) = decile among {len(ref)} island francophone public elementary schools, 1 = lowest tenth."
             if ref is not None else f"Zone = {radius:.0f} m circle around the school building."]
    for r in results:
        where = ", ".join(str(v) for v in (r.get("building"), r.get("address")) if v)
        where = f"{where} " if where else ""
        notes.append(f"{r.get('label') or r['school']}: {where}({r.get('borough') or 'outside borough limits'}); "
                     f"{r['n_da']} DAs; IEMV covers {fmt('park_pct', r['iemv_coverage_pct'])}% of residents; "
                     f"tax bills matched for {fmt('park_pct', r['tax_coverage_pct'])}% of units.")
    return "\n".join(lines) + "\n\n" + "\n".join(notes) + "\n"


class Format(str, Enum):
    md = "md"
    csv = "csv"
    json = "json"


app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


@app.command()
def main(
    schools: Annotated[Optional[list[str]], typer.Argument(
        help="school name fragments or MEQ organisation codes")] = None,
    point: Annotated[Optional[tuple[float, float]], typer.Option(
        "--point", metavar="LON LAT", help="evaluate an arbitrary point")] = None,
    label: Annotated[Optional[str], typer.Option(help="label for --point")] = None,
    radius: Annotated[float, typer.Option(help="zone radius in metres")] = 1000.0,
    collision_radius: Annotated[float, typer.Option(help="radius for pedestrian/cyclist victims, metres")] = 500.0,
    all_schools: Annotated[bool, typer.Option(
        "--all", help="compute every island school and refresh the decile cache")] = False,
    no_deciles: Annotated[bool, typer.Option("--no-deciles", help="omit deciles even if the cache exists")] = False,
    fmt_: Annotated[Format, typer.Option("--format", help="output format")] = Format.md,
    out: Annotated[Optional[Path], typer.Option(help="write the output here instead of stdout")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Describe the neighbourhood around a school (or a point) from open data, with island deciles."""
    setup_logging(verbose)
    d = Data()
    if all_schools:
        logger.info("computing {} schools ...", len(d.schools))
        run_all(d, radius, collision_radius)
        logger.success("-> {} and .csv", ALL_CACHE.relative_to(ROOT))
        if not schools and not point:
            return
    ref = None
    if not no_deciles and ALL_CACHE.exists():
        ref = pd.read_parquet(ALL_CACHE)
        logger.debug("deciles against {} schools", len(ref))
    elif not no_deciles:
        logger.warning("no decile cache; run with --all once to get deciles")

    results = []
    if schools:
        for s in find_schools(d, schools).itertuples():
            row = school_row(s)
            row.update(zone_stats(d, s.geometry.x, s.geometry.y, radius, collision_radius))
            results.append(row)
    if point:
        lon, lat = point
        p = gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(CRS).iloc[0]
        row = dict(label=label or f"{lon:.4f}, {lat:.4f}", school=label or "point", lon=lon, lat=lat)
        row.update(zone_stats(d, p.x, p.y, radius, collision_radius))
        results.append(row)
    if not results:
        logger.error("give school names, --point, or --all")
        raise typer.Exit(2)

    if fmt_ is Format.md:
        text = markdown(results, ref, radius)
    elif fmt_ is Format.json:
        text = json.dumps(results, indent=1, ensure_ascii=False, default=lambda v: None if pd.isna(v) else v)
    else:
        text = pd.DataFrame(results).to_csv(index=False)
    if out:
        out.write_text(text)
        logger.success("-> {}", out)
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
