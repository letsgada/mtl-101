# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "loguru>=0.7"]
# ///
"""Download and cache the open datasets MTL-101 reads, by short key.

    uv run scripts/fetch_open_data.py --list
    uv run scripts/fetch_open_data.py --core            # everything zone_stats needs except tax bills
    uv run scripts/fetch_open_data.py taxes             # all 19 borough tax-bill files (~2.7 GB)
    uv run scripts/fetch_open_data.py taxes:villeray-saint-michel-parc-extension crimes
    uv run scripts/fetch_open_data.py --force uev       # re-download even if cached

Files land in data/raw/ (gitignored) and data/raw/manifest.json records the URL, size,
fetch time and the portal's own last-modified stamp for each. Resource URLs are resolved
live through the portals' CKAN APIs so a re-published file keeps working.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 mtl-101/0.1")

CKAN = {
    "mtl": "https://donnees.montreal.ca/api/3/action/package_show?id=",
    "dq": "https://www.donneesquebec.ca/recherche/api/3/action/package_show?id=",
}

# key -> how to find it. `portal`+`dataset` resolve through CKAN, picking the first resource
# whose format matches and whose name/url match the optional regexes. `url` is a direct link.
DATASETS: dict[str, dict] = {
    "schools": dict(portal="dq", dataset="localisation-des-etablissements-d-enseignement-du-reseau-scolaire-au-quebec",
                    format="GeoJSON", name=r"^Écoles publiques$", file="pps_public_ecole.geojson",
                    note="MEQ school points, all public schools in Quebec (CD_ORGNS, CD_CS, PRIM, coordinates)."),
    "crimes": dict(portal="mtl", dataset="actes-criminels", format="CSV", file="actes-criminels.csv",
                   note="SPVM incidents since 2015, obfuscated to intersections; not official statistics."),
    "crimes_monthly": dict(portal="mtl", dataset="bilan-mensuel-criminalite", format="CSV",
                           file="bilan-mensuel-criminalite.csv", note="Official monthly counts by PDQ."),
    "pdq": dict(portal="mtl", dataset="limites-pdq-spvm", format="GeoJSON", file="limitespdq.geojson",
                note="Police station (PDQ) territories, EPSG:32188."),
    "boroughs": dict(portal="mtl", dataset="limites-administratives-agglomeration", format="GeoJSON",
                     url_re=r"agglomeration\.geojson$", file="limites-administratives-agglomeration.geojson",
                     note="Borough and related-city limits."),
    "uev": dict(portal="mtl", dataset="unites-evaluation-fonciere", format="GeoJSON",
                file="uniteevaluationfonciere.geojson.zip",
                note="Assessment-unit polygons with CUBF, year built, dwelling count; no values."),
    "taxes": dict(portal="mtl", dataset="taxes-municipales", format="CSV", multi=r"taxes-municipales-(.+)\.csv$",
                  note="Tax-bill lines per unit, one file per borough, 2021-2026, with VAL_IMPOSABLE."),
    "parks": dict(portal="mtl", dataset="grands-parcs-parcs-d-arrondissements-et-espaces-publics", format="JSON",
                  file="espace_vert.json", note="Park and public-space polygons."),
    "park_access": dict(portal="mtl", dataset="regle-3-30-30-pour-le-suivi-de-l-acces-aux-espaces-verts",
                        format="GeoJSON", file="regle-3-30-300.geojson", note="City-computed 300 m / 1 km park access."),
    "collisions": dict(portal="dq", dataset="vmtl-collisions-routieres", format="CSV",
                       file="collisions_routieres.csv", note="SAAQ road collisions with pedestrian/cyclist victims."),
    "pampalon": dict(portal="dq", dataset="indice-de-defavorisation-du-quebec-2021", format="SHP",
                     file="ad2021inddef.zip",
                     note="INSPQ deprivation index by DA; doubles as DA geometry + 2021 population (ADPOP2021)."),
    "iemv": dict(portal="mtl", dataset="indice-equite-milieux-vie", format="GeoJSON",
                 name=r"^Indice d'équité des milieux de vie, 2026$", file="iemv_2026.geojson",
                 note="Ville de Montréal equity index, census tracts, 2026 edition."),
    "cpe": dict(portal="dq", dataset="liste-des-centres-de-la-petite-enfance-cpe-et-des-garderies-en-fonction",
                format="CSV", file="repertoire-installation.csv",
                note="Ministère de la Famille childcare installations with PLACE_TOTAL; no coordinates."),
    "bikes": dict(portal="mtl", dataset="pistes-cyclables", format="GeoJSON", file="pistes-cyclables.geojson"),
    "rev": dict(portal="mtl", dataset="reseau-express-velo", format="GeoJSON", file="reseau-express-velo.geojson"),
    "imse": dict(portal="dq", dataset="indices-de-defavorisation", format="CSV",
                 name=r"^Défavorisation - Écoles primaires", file="defav_ecole_prim_public.csv",
                 note="MEQ IMSE and SFR deciles per public elementary school (Code_Org = MEQ school code), yearly."),
    "census_da_qc": dict(url="https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/"
                             "download-telecharger/comp/GetFile.cfm?Lang=E&FILETYPE=CSV&GEONO=006_Quebec",
                         file="98-401-X2021006_Quebec_eng_CSV.zip",
                         note="StatCan 2021 Census Profile, all Quebec dissemination areas (~540 MB zip)."),
    "gtfs": dict(url="http://www.stm.info/sites/default/files/gtfs/gtfs_stm.zip", file="gtfs_stm.zip",
                 note="STM static GTFS. The stm.info link serves a bot-check HTML page to non-browser clients (2026-09); "
                      "the fetcher rejects it. Use metro_osm for stations."),
    "metro_osm": dict(url="https://overpass-api.de/api/interpreter?data="
                          "%5Bout%3Ajson%5D%5Btimeout%3A60%5D%3B%28node%5B%22railway%22%3D%22station%22%5D%5B%22station%22%3D%22subway%22%5D"
                          "%2845.40%2C-73.99%2C45.72%2C-73.45%29%3Bnode%5B%22railway%22%3D%22station%22%5D%5B%22station%22%3D%22light_rail%22%5D"
                          "%2845.40%2C-73.99%2C45.72%2C-73.45%29%3B%29%3Bout%20body%3B",
                      file="metro_stations_osm.json", headers={"User-Agent": "mtl-101/0.1 (https://letsgada.github.io/mtl-101)"},
                      note="Métro and REM stations from OpenStreetMap via Overpass (ODbL, credit OpenStreetMap contributors)."),
}
CORE = ["schools", "crimes", "pdq", "boroughs", "uev", "parks", "collisions", "pampalon", "iemv", "census_da_qc", "imse", "metro_osm"]

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def ckan_resources(spec: dict) -> list[dict]:
    pkg = get_json(CKAN[spec["portal"]] + spec["dataset"])["result"]
    out = []
    for res in pkg["resources"]:
        if res.get("format", "").lower() != spec["format"].lower():
            continue
        if spec.get("name") and not re.search(spec["name"], res.get("name", "")):
            continue
        if spec.get("url_re") and not re.search(spec["url_re"], res["url"]):
            continue
        out.append(res)
    if not out:
        logger.error("no {} resource matched in {}", spec["format"], spec["dataset"])
        raise typer.Exit(1)
    return out


def resolve(key: str) -> list[tuple[str, str, str, dict]]:
    """Return [(key, url, filename, meta)] for a key, expanding `taxes` / `taxes:<slug>`."""
    base, _, sub = key.partition(":")
    spec = DATASETS.get(base)
    if spec is None:
        logger.error("unknown key {!r}; see --list", key)
        raise typer.Exit(1)
    if "url" in spec:
        return [(key, spec["url"], spec["file"], {})]
    resources = ckan_resources(spec)
    if "multi" in spec:
        out = []
        for res in resources:
            m = re.search(spec["multi"], res["url"])
            if not m:
                continue
            slug = m.group(1)
            if sub and slug != sub:
                continue
            out.append((f"{base}:{slug}", res["url"], Path(res["url"]).name,
                        dict(resource_id=res["id"], last_modified=res.get("last_modified"), name=res.get("name"))))
        if not out:
            logger.error("no borough matched {!r}; slugs are the file names on the portal", sub)
            raise typer.Exit(1)
        return out
    res = resources[0]
    return [(key, res["url"], spec["file"], dict(resource_id=res["id"], last_modified=res.get("last_modified"),
                                                 name=res.get("name")))]


def download(url: str, dest: Path, headers: dict | None = None) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r, tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        shutil.copyfileobj(r, tmp, length=1 << 20)
        tmp_path = Path(tmp.name)
    body = tmp_path.read_bytes()[:64] if tmp_path.stat().st_size < 4096 else b""
    if body.startswith(b"RBAC") or body.lower().startswith(b"<!doctype html") or body.lower().startswith(b"<html"):
        tmp_path.unlink()
        raise RuntimeError(f"portal refused the download ({body[:40]!r}); check the User-Agent")
    tmp_path.replace(dest)
    return dest.stat().st_size


@app.command()
def main(
    keys: Annotated[Optional[list[str]], typer.Argument(
        help="dataset keys; `taxes` expands to all boroughs, `taxes:<slug>` to one")] = None,
    core: Annotated[bool, typer.Option("--core", help=f"fetch the core set: {' '.join(CORE)}")] = False,
    force: Annotated[bool, typer.Option("--force", help="re-download even if the file is present")] = False,
    list_keys: Annotated[bool, typer.Option("--list", help="list keys and exit")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Download and cache open datasets by key into data/raw/."""
    setup_logging(verbose)
    if list_keys:
        for k, spec in DATASETS.items():
            typer.echo(f"{k:14} {spec.get('note', '')}")
        return
    wanted = list(keys or []) + (CORE if core else [])
    if not wanted:
        logger.error("give at least one key or --core")
        raise typer.Exit(2)

    RAW.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    for key in wanted:
        for k, url, filename, meta in resolve(key):
            dest = RAW / filename
            if dest.exists() and not force:
                logger.info("skip  {:40} {} ({} MB cached)", k, filename, dest.stat().st_size >> 20)
                manifest.setdefault(k, {}).update(path=str(dest.relative_to(ROOT)), url=url, **meta)
                continue
            logger.info("fetch {:40} {}", k, url)
            size = download(url, dest, DATASETS.get(k.partition(":")[0], {}).get("headers"))
            logger.success("      {} MB -> {}", size >> 20, dest.relative_to(ROOT))
            manifest[k] = dict(path=str(dest.relative_to(ROOT)), url=url, bytes=size,
                               fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta)
            MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    app()
