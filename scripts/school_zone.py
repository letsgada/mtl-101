# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio>=0.9", "pyarrow>=16", "shapely>=2.1", "scipy>=1.11",
#                 "typer>=0.12", "loguru>=0.7"]
# ///
"""Draw the catchment ("territoire de l'école de quartier") of an island elementary school.

    uv run scripts/school_zone.py "Saint-Barthélemy"
    uv run scripts/school_zone.py 762103 --out data/derived/zone_762103
    uv run scripts/school_zone.py "Adélard-Desrosiers" --method probe

Writes <out>.geojson (the polygon, carrying `source` and `as_of`) and <out>_postal.csv (one row
per postal code, with its residential address units). Prints a summary on stdout.

There are two very different sources, and the output always says which one it used:

  official-probe   The CSS publishes an address lookup and we asked it. Only the CSS de la
                   Pointe-de-l'Île (761) does: a postal code goes in, its schools come back.
  modelled-nearest No lookup exists, so this is a MODEL: each postal code goes to the nearest
                   school of the same service centre that can hold a catchment. The CSS de
                   Montréal (762) publishes nothing, so all 131 of its elementary schools land
                   here. A modelled zone is an estimate and must be labelled as one in any post.

Schools whose program is island-wide libre choix (alternative, specialised, gifted in
data/schools_programs.csv) hold no territory of their own and are left out of the competition, as
are the six that run through to secondary, which the MEQ file identifies and which take referred
pupils from the whole service centre. Every other school, including the ones whose program is not
yet recorded, is treated as territorial — the main soft spot in the model.
Distances are measured to a school's nearest building, so a maison-mère and its annexe share one
zone rather than splitting it.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import typer
from loguru import logger
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint

sys.path.insert(0, str(Path(__file__).resolve().parent))
from school_info import all_buildings, programs  # noqa: E402
from zone_stats import CRS, DERIVED, ROOT, Data, find_schools, strip_accents  # noqa: E402

POSTAL = DERIVED / "postal_points.parquet"
PROBE_CACHE = DERIVED / "csspi_postal_cache.json"
PROBE_SCHOOLS = DERIVED / "csspi_schools.json"
CSSPI_BASE = ("https://www.csspi.gouv.qc.ca/ecoles-centres/prescolaire-et-primaire/"
              "bottins-des-ecoles-primaires/carte")
CSSPI_PRIMARY_CATEGORY = "15"
# The CSSPI site refuses a plain script User-Agent with 403, like the city portal does.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 mtl-101/0.1")
# Programs that draw island-wide by libre choix and therefore hold no territory of their own.
NON_TERRITORIAL = {"alternative", "specialised", "gifted"}
PROBE_CSS = {"761"}  # the only service centre with a public postal-code lookup
RING = 400.0  # metres: the probe grows a ring at a time until the school stops appearing

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


class Method(str, Enum):
    auto = "auto"
    model = "model"
    probe = "probe"


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def postal_points() -> pd.DataFrame:
    if not POSTAL.exists():
        logger.error("missing postal codes; run: uv run scripts/prep_postal.py")
        raise typer.Exit(1)
    return pd.read_parquet(POSTAL)


def territorial(d: Data, prog: pd.DataFrame) -> gpd.GeoDataFrame:
    """Schools that can hold a catchment, i.e. everything but island-wide libre choix."""
    s = d.schools
    kinds = dict(zip(prog.code.astype(str), prog.program_type)) if len(prog) else {}
    kind = s.CD_ORGNS.astype(str).map(kinds).fillna("")
    # A school that runs from preschool or primary right through secondary is a specialised
    # school (Le Prélude, Le Tournesol, the Sainte-Justine hospital school): it takes referred
    # pupils from across the service centre and has no elementary catchment. Six on the island,
    # and the MEQ file says so directly, so this needs no hand-curation.
    all_ages = s.SEC == 1
    keep = ~kind.isin(NON_TERRITORIAL) & ~all_ages
    dropped = sorted(s.loc[~keep.values, "NOM_OFFCL_ORGNS"])
    logger.info("{} schools can hold a catchment; {} left out as island-wide libre choix or "
                "specialised", int(keep.sum()), len(dropped))
    for n in dropped:
        logger.debug("  not territorial: {}", n)
    unknown = int((kind[keep] == "").sum())
    if unknown:
        logger.warning("{} of them have no program recorded in data/schools_programs.csv and are "
                       "assumed territorial", unknown)
    return s[keep.values]


def nearest_school(pts: pd.DataFrame, buildings: gpd.GeoDataFrame) -> np.ndarray:
    """Code of the school whose nearest building is closest to each postal point."""
    tree = cKDTree(np.c_[buildings.geometry.x.values, buildings.geometry.y.values])
    _, idx = tree.query(np.c_[pts.x.values, pts.y.values], k=1)
    return buildings.CD_ORGNS.astype(str).values[idx]


def zone_polygon(pts: pd.DataFrame, mask: np.ndarray, island) -> "shapely.Geometry":
    """Dissolve the Voronoi cells of the selected postal points, clipped to the island.

    Several postal-code parts can share one point (a tower with its own codes, a code split
    across dissemination areas), and the Voronoi builder rejects repeated coordinates, so cells
    are built over distinct points and a cell is kept when any part standing on it is selected.
    """
    xy = np.c_[pts.x.values, pts.y.values]
    _, uid = np.unique(xy, axis=0, return_inverse=True)
    order = np.argsort(uid, kind="stable")
    first = order[np.unique(uid[order], return_index=True)[1]]  # one row per distinct point
    cells = shapely.voronoi_polygons(MultiPoint(xy[first]), extend_to=island.envelope, ordered=True)
    keep = np.zeros(len(first), dtype=bool)
    keep[uid[mask]] = True
    chosen = [cells.geoms[i] for i in np.flatnonzero(keep)]
    if not chosen:
        return None
    return shapely.union_all(chosen).intersection(island)


@lru_cache(maxsize=1)
def opener() -> urllib.request.OpenerDirector:
    """A session that holds the site's cookie; its listing endpoint 303-loops without one."""
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    o.addheaders = [("User-Agent", UA), ("Accept-Language", "fr-CA,fr;q=0.9"),
                    ("Referer", CSSPI_BASE)]  # the listing endpoint redirects away without it
    with o.open(CSSPI_BASE, timeout=30) as r:
        r.read()
    time.sleep(1.1)
    return o


def get(url: str, headers: dict | None = None, tries: int = 4) -> str:
    """One request per second, with a short backoff on the server's occasional 5xx."""
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in range(1, tries + 1):
        try:
            with opener().open(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            time.sleep(1.1)
            return body
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == tries:
                raise
            logger.warning("HTTP {} from the lookup; retrying in {}s", e.code, 3 * attempt)
            time.sleep(3 * attempt)
    raise RuntimeError("unreachable")


@lru_cache(maxsize=1)
def csrf() -> dict[str, str]:
    """Joomla's per-session form token; the listing's later pages are empty without it."""
    found = re.findall(r'<input type="hidden" name="([0-9a-f]{32})" value="1">', get(CSSPI_BASE))
    if not found:
        logger.warning("no form token found; the school list may come back short")
        return {}
    return {found[0]: "1"}


def probe_crosswalk() -> dict[str, dict]:
    """data-id -> {name, slug} for every CSSPI elementary school, cached on disk."""
    if PROBE_SCHOOLS.exists():
        return json.loads(PROBE_SCHOOLS.read_text())
    out: dict[str, dict] = {}
    for page in range(1, 12):
        # page 1 comes from filterPage; the later pages answer only to paginatePage.
        q = urllib.parse.urlencode({"option": "com_gdwgestion", "view": "buildings",
                                    "task": f"buildings.{'filterPage' if page == 1 else 'paginatePage'}",
                                    "filter_category[]": CSSPI_PRIMARY_CATEGORY, "page": page, **csrf()})
        html = get(f"{CSSPI_BASE}?{q}")
        found = re.findall(r'data-id="(\d+)">\s*<a href="[^"]*/etablissement/([a-z0-9\-]+)"[^>]*>'
                           r'.*?<h3>(.*?)</h3>', html, re.S)
        fresh = [f for f in found if f[0] not in out]
        if not fresh:
            break
        for sid, slug, name in fresh:
            out[sid] = dict(slug=slug, name=re.sub(r"\s+", " ", name).strip())
        logger.debug("crosswalk page {}: {} new entries", page, len(fresh))
    if not out:
        logger.error("could not read the CSSPI school list; the site's markup may have changed")
        raise typer.Exit(1)
    PROBE_SCHOOLS.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    logger.success("CSSPI crosswalk: {} elementary schools -> {}", len(out), PROBE_SCHOOLS.relative_to(ROOT))
    return out


def probe_postal(cp: str, cache: dict) -> list[str]:
    """Ask the CSSPI lookup which schools serve a postal code. One request per second, cached."""
    if cp in cache:
        return cache[cp]
    q = urllib.parse.urlencode({"option": "com_gdwgestion", "view": "buildings",
                                "task": "buildings.getPointers", "search": cp})
    body = get(f"{CSSPI_BASE}?{q}", {"X-Requested-With": "XMLHttpRequest"}).strip()
    try:
        ids = [str(i) for i in json.loads(body)]
    except json.JSONDecodeError:
        logger.warning("unparseable answer for {}: {!r}", cp, body[:60])
        ids = []
    cache[cp] = ids
    return ids


def csspi_base_name(name: str) -> str:
    """Strip the annexe / pavillon suffix so a school's buildings collapse to one name."""
    n = strip_accents(name)
    n = re.sub(r"\s*\((?:pavillon|annexe)[^)]*\)", "", n)
    n = re.sub(r"\s+(?:annexe|pavillon)\b.*$", "", n)
    return n.strip()


def match_school_ids(crosswalk: dict[str, dict], school) -> set[str]:
    """Every CSSPI data-id belonging to a MEQ school, its annexes and pavilions included."""
    want = re.sub(r"^ecole\s+", "", strip_accents(school.NOM_OFFCL_ORGNS)).strip()
    ids = {sid for sid, meta in crosswalk.items() if csspi_base_name(meta["name"]) == want}
    if not ids:
        ids = {sid for sid, meta in crosswalk.items()
               if want in csspi_base_name(meta["name"]) or csspi_base_name(meta["name"]) in want}
    if not ids:
        logger.error("cannot match {!r} to a CSSPI school; its lookup list has {} entries",
                     school.NOM_OFFCL_ORGNS, len(crosswalk))
        raise typer.Exit(1)
    logger.debug("matched {!r} to CSSPI ids {}", want, sorted(ids))
    return ids


@app.command()
def main(
    school: Annotated[str, typer.Argument(help="school name or MEQ code")],
    method: Annotated[Method, typer.Option(help="auto picks probe where a lookup exists")] = Method.auto,
    out: Annotated[Optional[Path], typer.Option(help="output stem; default data/derived/zone_<code>")] = None,
    radius: Annotated[float, typer.Option(help="probe only: how far out to search before giving up")] = 3000.0,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Build one school's catchment polygon and its list of postal codes."""
    setup_logging(verbose)
    d = Data()
    s = find_schools(d, [school]).iloc[0]
    code, css = str(s.CD_ORGNS), str(s.CD_CS)[:3]
    logger.info("{} [{}], {}", s.NOM_OFFCL_ORGNS, code, s.NOM_CS)

    pts = postal_points()
    pts = pts[pts.CO_CSF == css].reset_index(drop=True)
    if pts.empty:
        logger.error("no postal codes for service centre {}", css)
        raise typer.Exit(1)
    logger.info("{} postal-code parts in this service centre's territory", len(pts))

    use_probe = method is Method.probe or (method is Method.auto and css in PROBE_CSS)
    if method is Method.probe and css not in PROBE_CSS:
        logger.error("no public lookup for {} ({}); only {} has one", s.NOM_CS, css, ", ".join(PROBE_CSS))
        raise typer.Exit(1)

    if use_probe:
        source = "official-probe"
        crosswalk = probe_crosswalk()
        wanted = match_school_ids(crosswalk, s)
        cache = json.loads(PROBE_CACHE.read_text()) if PROBE_CACHE.exists() else {}
        dist = np.hypot(pts.x - s.geometry.x, pts.y - s.geometry.y).values
        # Walk outwards a ring at a time and stop at the first ring the school never appears in,
        # so the edge is the zone's own rather than an artefact of how far we searched.
        keep_cp, asked, misses, inner = set(), 0, 0, 0.0
        try:
            while inner < radius:
                outer = min(inner + RING, radius)
                ring = pts[(dist >= inner) & (dist < outer)]
                if len(ring):
                    found = 0
                    for cp in ring.CP:
                        ids = probe_postal(cp, cache)
                        asked += 1
                        if not ids:
                            misses += 1
                        elif wanted & set(ids):
                            keep_cp.add(cp)
                            found += 1
                    logger.info("ring {:.0f}-{:.0f} m: {} of {} postal codes are this school's",
                                inner, outer, found, len(ring))
                    if keep_cp and not found:
                        logger.info("the school reaches no further; zone closed")
                        break
                inner = outer
        finally:
            PROBE_CACHE.write_text(json.dumps(cache, indent=0, ensure_ascii=False))
        if inner >= radius and keep_cp:
            logger.warning("hit the {:.0f} m cap with the zone still growing; raise --radius", radius)
        if misses:
            logger.warning("{} of {} postal codes returned no school at all", misses, asked)
        mask = pts.CP.isin(keep_cp).values
    else:
        source = "modelled-nearest"
        schools = territorial(d, programs())
        blds = all_buildings()
        blds = blds[blds.CD_ORGNS.astype(str).isin(set(schools.CD_ORGNS.astype(str)))]
        logger.info("no public lookup for {}; modelling against {} buildings of {} schools",
                    s.NOM_CS, len(blds), len(schools))
        assigned = nearest_school(pts, blds)
        mask = assigned == code

    if not mask.any():
        logger.error("no postal code resolved to this school; nothing to draw")
        raise typer.Exit(1)

    island = d.boroughs.geometry.union_all()
    poly = zone_polygon(pts, mask, island)
    zone = pts[mask]
    per_cp = (zone.groupby("CP", as_index=False)
                  .agg(residential_units=("R", "sum"), parts=("CP", "size"), da=("ADIDU", "first")))

    stem = out or DERIVED / f"zone_{code}"
    stem.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame([dict(code=code, school=s.NOM_OFFCL_ORGNS, css=s.NOM_CS, source=source,
                                 as_of=date.today().isoformat(), postal_codes=len(per_cp),
                                 residential_units=int(zone.R.sum()),
                                 area_km2=round(poly.area / 1e6, 3))],
                           geometry=[poly], crs=CRS).to_crs(4326)
    gdf.to_file(f"{stem}.geojson", driver="GeoJSON")
    per_cp.sort_values("CP").to_csv(f"{stem}_postal.csv", index=False)
    shown = stem.relative_to(ROOT) if stem.is_relative_to(ROOT) else stem
    logger.success("{} postal codes, {} residential units, {:.2f} km2 ({}) -> {}.geojson",
                   len(per_cp), f"{int(zone.R.sum()):,}", poly.area / 1e6, source, shown)
    typer.echo(json.dumps(dict(code=code, school=s.NOM_OFFCL_ORGNS, css=s.NOM_CS, source=source,
                               postal_codes=len(per_cp), residential_units=int(zone.R.sum()),
                               area_km2=round(poly.area / 1e6, 3),
                               geojson=f"{stem}.geojson", postal_csv=f"{stem}_postal.csv"),
                          indent=1, ensure_ascii=False))


if __name__ == "__main__":
    app()
