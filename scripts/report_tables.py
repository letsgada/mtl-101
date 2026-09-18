# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Turn a zone_stats CSV into the six captioned Quarto tables a school report uses.

    uv run scripts/zone_stats.py "Laurier" 762087 --format csv --out data/derived/laurier.csv
    uv run scripts/report_tables.py data/derived/laurier.csv > tables.md

Each metric cell is the value followed by its island decile as a span in the site's helper
classes ([d2]{.decile-low}, [d5]{.decile-mid}, [d9]{.decile-high}); the last column is the
island median. Deciles and medians come from data/derived/zone_stats_all.parquet, the same
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
    ("tbl-parks", ["park_pct", "park_ha_per_1000"], "Parks within {r} (large parks and borough parks only)"),
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


def header_name(row: pd.Series) -> str:
    if isinstance(row.get("label"), str) and row["label"]:
        return row["label"]
    name = re.sub(r"^École\s+", "", str(row["school"]))
    return re.sub(r",\s*pavillon.*$", "", name)


@app.command()
def main(
    csv: Annotated[Path, typer.Argument(help="CSV written by zone_stats.py --format csv")],
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
    heads = [header_name(r) for _, r in df.iterrows()]
    blocks = []
    for tid, keys, caption in TABLES:
        L = ["::: {.column-page}", "| Metric | Unit | " + " | ".join(heads) + " | Island median |",
             "|:---|:---|" + "---:|" * len(heads) + "---:|"]
        for key, label, unit, _ in METRICS:
            if key not in keys:
                continue
            label = LABELS.get(key, label.strip())
            cells = [cell(ref, key, df.loc[i, key]) for i in range(len(df))]
            L.append(f"| {label} | {unit} | " + " | ".join(cells) + f" | {fmt(key, ref[key].median())} |")
        L += ["", f": {caption.format(r=radius_label)} {{#{tid}}}", ":::", ""]
        blocks.append("\n".join(L))
    text = "\n".join(blocks)
    text += (f"\nDeciles are among {len(ref)} francophone public elementary schools on the island outside the "
             "West Island (1 = lowest tenth, 10 = highest); the island median is over the same set.\n")
    if out:
        out.write_text(text)
        logger.success("-> {}", out)
    else:
        typer.echo(text)


if __name__ == "__main__":
    app()
