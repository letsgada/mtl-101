# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Emit a Leaflet map of a school's zone as a raw HTML fragment for a Quarto post.

    uv run scripts/zone_map.py "Laurier" > map.html
    uv run scripts/zone_map.py 762103 762087 762089 --anchor -73.6235 45.5405 --out posts/x-map.html

The first school is the subject (accent-coloured pin and the zone circle); the others are
comparators (zone-coloured pins). --anchor moves the circle to another point, for a school that
is temporarily relocated. Paste the fragment into a post inside a ```{=html} block; no Python
runs at render time. Leaflet comes from cdnjs, tiles from OpenStreetMap with attribution, and
colours are read from the site's CSS variables (--accent, --zone, --zone-soft) so the map follows
the light and dark themes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import typer
from loguru import logger
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zone_stats import CRS, Data, find_schools  # noqa: E402

LEAFLET = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4"
app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


TEMPLATE = """<link rel="stylesheet" href="{leaflet}/leaflet.min.css">
<script src="{leaflet}/leaflet.min.js"></script>
<div id="{div_id}" class="zone-map" style="height:{height}px;border:1px solid var(--zone-soft);border-radius:4px"></div>
<script>
(function () {{
  var css = getComputedStyle(document.documentElement);
  var accent = css.getPropertyValue('--accent').trim() || '#c1272d';
  var zone = css.getPropertyValue('--zone').trim() || '#5b6b7a';
  var soft = css.getPropertyValue('--zone-soft').trim() || '#dfe4ea';
  var data = {data};
  var map = L.map('{div_id}', {{scrollWheelZoom: false}});
  L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }}).addTo(map);
  var circle = L.circle([data.anchor.lat, data.anchor.lon], {{
    radius: data.radius, color: zone, weight: 2, fillColor: soft, fillOpacity: 0.35
  }}).addTo(map);
  data.comparators.forEach(function (s) {{
    L.circleMarker([s.lat, s.lon], {{radius: 6, color: zone, weight: 2, fillColor: soft, fillOpacity: 1}})
      .bindPopup('<b>' + s.name + '</b><br>' + s.address).addTo(map);
  }});
  L.circleMarker([data.subject.lat, data.subject.lon], {{radius: 8, color: accent, weight: 3, fillColor: accent, fillOpacity: 1}})
    .bindPopup('<b>' + data.subject.name + '</b><br>' + data.subject.address).addTo(map);
  if (data.anchor.label) {{
    L.circleMarker([data.anchor.lat, data.anchor.lon], {{radius: 5, color: accent, weight: 2, fillColor: '#fff', fillOpacity: 1}})
      .bindPopup(data.anchor.label).addTo(map);
  }}
  var bounds = circle.getBounds();
  if (data.mark) {{
    L.circleMarker([data.mark.lat, data.mark.lon], {{radius: 7, color: accent, weight: 2, dashArray: '3 3', fillColor: '#fff', fillOpacity: 1}})
      .bindPopup(data.mark.label).addTo(map);
    bounds.extend([data.mark.lat, data.mark.lon]);
  }}
  map.fitBounds(bounds.pad(0.15));
}})();
</script>
"""


@app.command()
def main(
    schools: Annotated[list[str], typer.Argument(help="subject school first, then comparators (names or codes)")],
    radius: Annotated[float, typer.Option(help="zone radius in metres")] = 1000.0,
    anchor: Annotated[Optional[tuple[float, float]], typer.Option("--anchor", metavar="LON LAT",
                                                                  help="centre the circle elsewhere (temporary site)")] = None,
    anchor_label: Annotated[Optional[str], typer.Option(help="popup text for the anchor point")] = None,
    mark: Annotated[Optional[tuple[float, float]], typer.Option("--mark", metavar="LON LAT",
                                                                help="an extra marker (e.g. a temporary site) without moving the circle")] = None,
    mark_label: Annotated[Optional[str], typer.Option(help="popup text for --mark")] = None,
    height: Annotated[int, typer.Option(help="map height in pixels")] = 420,
    out: Annotated[Optional[Path], typer.Option(help="write the fragment here instead of stdout")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Write a Leaflet map fragment for a school zone."""
    setup_logging(verbose)
    d = Data()
    rows = find_schools(d, schools)
    subj = rows.iloc[0]
    to_ll = lambda r: dict(lon=float(r.COORD_X_LL84_IMM), lat=float(r.COORD_Y_LL84_IMM),  # noqa: E731
                           name=r.NOM_OFFCL_ORGNS, address=f"{r.NOM_IMM}, {r.ADRS_GEO_L1_GDUNO_IMM}")
    subject = to_ll(subj)
    if anchor:
        a = dict(lon=anchor[0], lat=anchor[1], label=anchor_label or "zone centre (temporary site)")
    else:
        a = dict(lon=subject["lon"], lat=subject["lat"], label=None)
    data = dict(subject=subject, anchor=a, radius=radius,
                comparators=[to_ll(r) for r in rows.iloc[1:].itertuples()],
                mark=dict(lon=mark[0], lat=mark[1], label=mark_label or "marker") if mark else None)
    div_id = f"zone-map-{subj.CD_ORGNS}"
    html = TEMPLATE.format(leaflet=LEAFLET, div_id=div_id, height=height, data=json.dumps(data, ensure_ascii=False))
    if out:
        out.write_text(html)
        logger.success("-> {}", out)
    else:
        typer.echo(html)


if __name__ == "__main__":
    app()
