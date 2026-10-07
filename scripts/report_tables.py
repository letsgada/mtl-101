# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Turn a zone_stats CSV into the captioned Quarto tables a report uses.

    uv run scripts/zone_stats.py "Laurier" 762087 --format csv --out data/derived/laurier.csv
    uv run scripts/report_tables.py data/derived/laurier.csv > tables.md                     # schools as columns
    uv run scripts/report_tables.py data/derived/area_villeray.csv --layout rows \
        --info data/derived/area_villeray_schools.csv > tables.md                              # schools as rows (quartier report)

Layout `columns` (default) is the school report: one column per zone, metrics as rows.
Layout `rows` is the quartier report: an overview table (tbl-overview) with one row per
school and eight headline columns, then the six metric-group tables with schools as rows,
metrics as columns (▲/▼ in the header), the area row (role `area`) and the island median
row at the bottom, and the most favourable school per directional column shaded. `--info`
supplies program, admission, IMSE and report links per school code from area_info.py.

Each metric cell is the value followed by its island decile as a span in the site's helper
classes ([d2]{.decile-low}, [d5]{.decile-mid}, [d9]{.decile-high}); the last column is the
island median. Metrics with a direction (zone_stats.METRICS: "up" = higher is favourable,
"down" = lower is favourable) get a ▲/▼ glyph on the label and the most favourable compared
zone in a shaded `.best` span (site.scss); descriptive metrics get neither. Deciles and medians come from data/derived/zone_stats_all.parquet, the same
reference zone_stats.py uses. Tables carry the ids tbl-people, tbl-indices, tbl-safety,
tbl-stock, tbl-cost and tbl-parks so prose can reference them. Column headers use the school's
short name (the "École " prefix dropped) or the `label` column when present.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Annotated, Optional

import pandas as pd
import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zone_stats import ALL_CACHE, METRICS, deciles, fmt  # noqa: E402

app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)

TABLES = [
    ("tbl-people", ["pop_2021", "children_0_14_pct", "hh_with_children_pct", "median_hh_income", "lim_at_pct",
                    "no_diploma_25_64_pct", "immigrants_pct", "french_home_pct", "renter_pct", "movers5_pct"],
     "Who lives within {r} of the school (2021 census, aggregated over dissemination areas whose centroid falls in the circle)"),
    ("tbl-indices", ["pampalon_material_q45_pct", "pampalon_social_q45_pct", "iemv_mean"],
     "Two composite indices computed by others: INSPQ material and social deprivation (share of residents in the two most deprived quintiles) and the city's 2026 equity index (population-weighted mean, 0 least vulnerable to 6 most)"),
    ("tbl-safety", ["crime_total", "crime_violent", "crime_breakins", "crime_vehicle", "crime_mischief", "ped_cycl_victims_per_yr"],
     "Safety: SPVM incidents 2023 to 2025 per 1 000 residents per year within {r}, and SAAQ pedestrian and cyclist victims 2017 to 2021 within 500 m of the school, per year"),
    ("tbl-stock", ["dwellings", "single_pct", "plex_pct", "condo_pct", "apt6_pct", "median_year_built"],
     "Housing stock within {r}, from the assessment roll"),
    ("tbl-cost", ["value_single_median", "value_plex_median", "value_condo_median", "bill_single_median",
                  "bill_plex_median", "bill_condo_median", "tax_rate_pct"],
     "What it costs to own: median 2026 assessed value and median 2026 municipal tax bill per unit within {r}, residential accounts with five dwellings or fewer"),
    ("tbl-parks", ["park_pct", "park_ha_per_1000", "metro_m", "metro_in_zone"],
     "Parks and rapid transit within {r}: large parks and borough parks (Ville de Montréal), métro and REM stations (OpenStreetMap contributors)"),
]
LABELS = {"crime_violent": "Violent (robbery, homicide)", "crime_breakins": "Break-ins",
          "crime_vehicle": "Vehicle theft and theft from vehicles", "crime_mischief": "Mischief"}


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO", format="<level>{level: <7}</level> {message}")


def cls(d: float) -> str:
    return "decile-low" if d <= 3 else ("decile-high" if d >= 8 else "decile-mid")


def cell(ref: pd.DataFrame, key: str, v) -> str:
    s = fmt(key, v)
    d = deciles(ref, key, v)
    return s if math.isnan(d) else f"{s} [d{int(d)}]{{.{cls(d)}}}"


def best_indices(values: pd.Series, direction: str) -> set[int]:
    """Positions of the most favourable value(s) among the compared zones; empty for descriptive rows."""
    if not direction or len(values) < 2:
        return set()
    v = pd.to_numeric(values, errors="coerce")
    if v.notna().sum() < 2:
        return set()
    target = v.max() if direction == "up" else v.min()
    return {i for i, x in enumerate(v) if pd.notna(x) and x == target}


OVERVIEW = ["children_0_14_pct", "median_hh_income", "crime_total", "ped_cycl_victims_per_yr",
            "value_plex_median", "metro_m"]
SHORT = {"pop_2021": "Residents", "children_0_14_pct": "Children 0-14 %", "hh_with_children_pct": "HH with children %",
         "median_hh_income": "Median HH income $", "lim_at_pct": "Low income %", "no_diploma_25_64_pct": "No diploma %",
         "immigrants_pct": "Immigrants %", "french_home_pct": "French at home %", "renter_pct": "Renters %",
         "movers5_pct": "Moved <5 yrs %", "pampalon_material_q45_pct": "Materially deprived %",
         "pampalon_social_q45_pct": "Socially deprived %", "iemv_mean": "IEMV (0-6)",
         "crime_total": "Crime /1000", "crime_violent": "Violent /1000", "crime_breakins": "Break-ins /1000",
         "crime_vehicle": "Vehicle /1000", "crime_mischief": "Mischief /1000", "ped_cycl_victims_per_yr": "Ped+cycl victims /yr (500 m)",
         "dwellings": "Dwellings", "single_pct": "Single-family %", "plex_pct": "Plex %", "condo_pct": "Condo %",
         "apt6_pct": "6+ unit rental %", "median_year_built": "Median year built",
         "value_single_median": "Value single $", "value_plex_median": "Value plex $", "value_condo_median": "Value condo $",
         "bill_single_median": "Tax single $", "bill_plex_median": "Tax plex $", "bill_condo_median": "Tax condo $",
         "tax_rate_pct": "Tax rate %", "metro_m": "Métro m", "metro_in_zone": "Stations in zone",
         "park_pct": "Park % of zone", "park_ha_per_1000": "Park ha /1000"}


def norm_code(x) -> str:
    """Codes arrive as int, float (when an area row makes the column float) or str; compare as digits."""
    try:
        return str(int(float(x)))
    except (TypeError, ValueError):
        return str(x or "")


def glyph(direction: str) -> str:
    return "▲ " if direction == "up" else ("▼ " if direction == "down" else "")


def school_cell(r: pd.Series, info: pd.DataFrame | None) -> str:
    """Name cell for a row layout: short name, dagger for edge schools, link to an existing report."""
    name = header_name(r)
    code = norm_code(r.get("code", ""))
    if info is not None and code in set(info.code.map(norm_code)):
        rp = info.loc[info.code.map(norm_code) == code, "report_path"].iloc[0]
        if isinstance(rp, str) and rp:
            name = f"[{name}]({Path(rp).name.replace('.qmd', '.qmd')})"
    if str(r.get("role", "")) == "edge":
        name += "†"
    return name


def rows_layout(df: pd.DataFrame, ref: pd.DataFrame, info: pd.DataFrame | None, radius_label: str) -> str:
    schools = df[df.role.isin(["school", "edge"])].reset_index(drop=True) if "role" in df else df.reset_index(drop=True)
    area = df[df.role == "area"] if "role" in df else df.iloc[0:0]
    area_name = area.iloc[0]["label"] if len(area) and isinstance(area.iloc[0].get("label"), str) else "Whole area"
    blocks = []

    # overview
    head = ["School", "Program, admission", "IMSE decile", "Pupils"] + [glyph(dict((m[0], m[4]) for m in METRICS)[k]) + SHORT[k] for k in OVERVIEW]
    L = ["::: {.column-page}", "| " + " | ".join(head) + " |", "|:---|:---|---:|---:|" + "---:|" * len(OVERVIEW)]
    dirs = {m[0]: m[4] for m in METRICS}
    best_cols = {k: best_indices(schools[k], dirs[k]) for k in OVERVIEW}
    for i, r in schools.iterrows():
        code = norm_code(r.get("code", ""))
        prog, imse, pupils = "unknown", "n/a", ""
        if info is not None and code in set(info.code.map(norm_code)):
            x = info[info.code.map(norm_code) == code].iloc[0]
            prog = (x.program_type if isinstance(x.program_type, str) and x.program_type else "unknown") + \
                   (f", {x.admission_model}" if isinstance(x.admission_model, str) and x.admission_model else "")
            imse = "n/a" if pd.isna(x.imse_decile) else f"d{int(x.imse_decile)}"
            pupils = "" if pd.isna(x.pupils) else f"{int(x.pupils):,}"
        cells = [school_cell(r, info), prog, imse, pupils]
        for k in OVERVIEW:
            c = cell(ref, k, r[k])
            cells.append(f"[{c}]{{.best}}" if i in best_cols[k] else c)
        L.append("| " + " | ".join(cells) + " |")
    if len(area):
        a = area.iloc[0]
        L.append("| *" + area_name + "* | | | | " + " | ".join(cell(ref, k, a[k]) for k in OVERVIEW) + " |")
    L.append("| *Island median* | | | | " + " | ".join(fmt(k, ref[k].median()) for k in OVERVIEW) + " |")
    L += ["", f": The schools at a glance: IMSE decile from the MEQ file (socioeconomic, not academic), zone metrics "
          f"within {radius_label} of each building with island deciles; † = outside the area but within the margin {{#tbl-overview}}", ":::", ""]
    blocks.append("\n".join(L))

    for tid, keys, caption in TABLES:
        head = ["School"] + [glyph(dirs[k]) + SHORT[k] for k in keys]
        L = ["::: {.column-page}", "| " + " | ".join(head) + " |", "|:---|" + "---:|" * len(keys)]
        best_cols = {k: best_indices(schools[k], dirs[k]) for k in keys}
        for i, r in schools.iterrows():
            cells = [school_cell(r, info)]
            for k in keys:
                c = cell(ref, k, r[k])
                cells.append(f"[{c}]{{.best}}" if i in best_cols[k] else c)
            L.append("| " + " | ".join(cells) + " |")
        if len(area):
            a = area.iloc[0]
            L.append("| *" + area_name + "* | " + " | ".join(cell(ref, k, a[k]) for k in keys) + " |")
        L.append("| *Island median* | " + " | ".join(fmt(k, ref[k].median()) for k in keys) + " |")
        cap = caption.format(r=radius_label)
        if tid == "tbl-safety" or tid == "tbl-parks":
            cap += "; the area row is computed over the whole polygon, so its point-relative cells are blank"
        L += ["", f": {cap} {{#{tid}}}", ":::", ""]
        blocks.append("\n".join(L))
    text = "\n".join(blocks)
    text += (f"\nDeciles are among {len(ref)} francophone public elementary schools on the island outside the "
             "West Island (1 = lowest tenth, 10 = highest); the island median is over the same set. "
             "▲ marks a column where a higher value is favourable for a family, ▼ one where lower is favourable; "
             "in those columns the most favourable school is shaded. Columns without a glyph are descriptive. "
             "† = a school outside the area but within the margin.\n")
    return text


def header_name(row: pd.Series) -> str:
    if isinstance(row.get("label"), str) and row["label"]:
        return row["label"]
    name = re.sub(r"^École\s+", "", str(row["school"]))
    return re.sub(r",\s*pavillon.*$", "", name)


@app.command()
def main(
    csv: Annotated[Path, typer.Argument(help="CSV written by zone_stats.py --format csv")],
    layout: Annotated[str, typer.Option(help="columns (school report) or rows (quartier report)")] = "columns",
    info: Annotated[Optional[Path], typer.Option(help="area_<slug>_schools.csv from area_info.py (rows layout)")] = None,
    radius_label: Annotated[str, typer.Option(help="how the zone is described in captions")] = "1 km",
    out: Annotated[Optional[Path], typer.Option(help="write here instead of stdout")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Emit the six captioned tables for a school report."""
    setup_logging(verbose)
    if not ALL_CACHE.exists():
        logger.error("missing {}; run: uv run scripts/zone_stats.py --all", ALL_CACHE)
        raise typer.Exit(1)
    df = pd.read_csv(csv)
    ref = pd.read_parquet(ALL_CACHE)
    if layout == "rows":
        inf = pd.read_csv(info, dtype={"code": str}) if info else None
        text = rows_layout(df, ref, inf, radius_label)
        if out:
            out.write_text(text)
            logger.success("-> {}", out)
        else:
            typer.echo(text)
        return
    heads = [header_name(r) for _, r in df.iterrows()]
    blocks = []
    for tid, keys, caption in TABLES:
        L = ["::: {.column-page}", "| Metric | Unit | " + " | ".join(heads) + " | Island median |",
             "|:---|:---|" + "---:|" * len(heads) + "---:|"]
        for key, label, unit, _, direction in METRICS:
            if key not in keys:
                continue
            label = LABELS.get(key, label.strip())
            if direction:
                label = ("▲ " if direction == "up" else "▼ ") + label
            cells = [cell(ref, key, df.loc[i, key]) for i in range(len(df))]
            best = best_indices(df[key], direction)
            cells = [f"[{c}]{{.best}}" if i in best else c for i, c in enumerate(cells)]
            L.append(f"| {label} | {unit} | " + " | ".join(cells) + f" | {fmt(key, ref[key].median())} |")
        L += ["", f": {caption.format(r=radius_label)} {{#{tid}}}", ":::", ""]
        blocks.append("\n".join(L))
    text = "\n".join(blocks)
    text += (f"\nDeciles are among {len(ref)} francophone public elementary schools on the island outside the "
             "West Island (1 = lowest tenth, 10 = highest); the island median is over the same set. "
             "▲ marks a metric where a higher value is favourable for a family, ▼ one where lower is favourable; "
             "on those rows the most favourable of the compared zones is shaded. Rows without a glyph are descriptive.\n")
    if out:
        out.write_text(text)
        logger.success("-> {}", out)
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
