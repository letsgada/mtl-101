# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Emit an interactive map of a school's zone as a raw HTML fragment for a Quarto post.

    uv run scripts/zone_map.py "Laurier" > map.html
    uv run scripts/zone_map.py 762103 762087 762089 --mark -73.6175 45.5404 --mark-label "Temporary site" --out map.html

The first school is the subject (accent-coloured pin and the zone circle); the others are
comparators (zone-coloured pins). Métro and REM stations inside the circle, or the nearest one,
are drawn as M / R squares from data/raw/metro_stations_osm.json (OpenStreetMap). --anchor moves
the circle to another point; --mark adds a dashed marker (a temporary site) without moving it.

Paste the fragment into a post inside a ```{=html} block; no Python runs at render time. The map
is MapLibre GL (cdnjs) over OpenFreeMap's Positron vector style: no API key, no usage cap, OSM
data with OpenStreetMap and OpenFreeMap attribution. OpenStreetMap's own raster tiles refuse
third-party sites and CARTO's now require a key, both verified in a headless browser on
2026-09-18. Circle geometry is computed here in metres; marker colours are the site's CSS
variables (--accent, --zone, --zone-soft) so the map follows both themes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Optional

import geopandas as gpd
import typer
from loguru import logger
from shapely.geometry import Point, mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zone_stats import CRS, Data, find_schools  # noqa: E402

MAPLIBRE = "https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1"
STYLE = "https://tiles.openfreemap.org/styles/positron"
app = typer.Typer(add_completion=False, help=__doc__, rich_markup_mode=None)


def setup_logging(verbose: bool) -> None:
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<level>{level: <7}</level> {message}")


TEMPLATE = """<link rel="stylesheet" href="{maplibre}/maplibre-gl.min.css">
<script src="{maplibre}/maplibre-gl.min.js"></script>
<div id="{div_id}" class="zone-map" style="height:{height}px;border:1px solid var(--zone-soft);border-radius:4px"></div>
<script>
(function () {{
  var css = getComputedStyle(document.documentElement);
  var accent = css.getPropertyValue('--accent').trim() || '#c1272d';
  var zone = css.getPropertyValue('--zone').trim() || '#5b6b7a';
  var soft = css.getPropertyValue('--zone-soft').trim() || '#dfe4ea';
  var data = {data};
  var map = new maplibregl.Map({{
    container: '{div_id}', style: '{style}', bounds: data.bounds,
    fitBoundsOptions: {{padding: 24}}, scrollZoom: false, attributionControl: false
  }});
  map.addControl(new maplibregl.NavigationControl({{showCompass: false}}), 'top-left');
  map.addControl(new maplibregl.AttributionControl({{compact: true,
    customAttribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; <a href="https://openfreemap.org">OpenFreeMap</a>'}}));
  function pin(lonlat, style, html, text) {{
    var el = document.createElement('div');
    el.style.cssText = style;
    if (text) {{ el.textContent = text; }}
    var m = new maplibregl.Marker({{element: el}}).setLngLat(lonlat).addTo(map);
    if (html) {{ m.setPopup(new maplibregl.Popup({{offset: 12, closeButton: false}}).setHTML(html)); }}
    return m;
  }}
  map.on('load', function () {{
    map.addSource('zone', {{type: 'geojson', data: data.circle}});
    map.addLayer({{id: 'zone-fill', type: 'fill', source: 'zone', paint: {{'fill-color': soft, 'fill-opacity': 0.35}}}});
    map.addLayer({{id: 'zone-line', type: 'line', source: 'zone', paint: {{'line-color': zone, 'line-width': 2}}}});
    data.stations.forEach(function (st) {{
      pin([st.lon, st.lat], 'width:18px;height:18px;border-radius:3px;background:#fff;border:2px solid ' + zone +
          ';color:' + zone + ';font:bold 11px/14px sans-serif;text-align:center;cursor:pointer',
          '<b>' + st.name + '</b><br>' + (st.kind === 'light_rail' ? 'REM' : 'Métro') + ' station',
          st.kind === 'light_rail' ? 'R' : 'M');
    }});
    data.comparators.forEach(function (s) {{
      pin([s.lon, s.lat], 'width:12px;height:12px;border-radius:50%;background:' + soft + ';border:2px solid ' + zone + ';cursor:pointer',
          '<b>' + s.name + '</b><br>' + s.address);
    }});
    if (data.mark) {{
      pin([data.mark.lon, data.mark.lat], 'width:14px;height:14px;border-radius:50%;background:#fff;border:2px dashed ' + accent + ';cursor:pointer',
          data.mark.label);
    }}
    if (data.anchor.label) {{
      pin([data.anchor.lon, data.anchor.lat], 'width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid ' + accent, data.anchor.label);
    }}
    pin([data.subject.lon, data.subject.lat], 'width:16px;height:16px;border-radius:50%;background:' + accent + ';border:3px solid ' + accent + ';cursor:pointer',
        '<b>' + data.subject.name + '</b><br>' + data.subject.address);
  }});
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
    """Write a MapLibre map fragment for a school zone."""
    setup_logging(verbose)
    d = Data()
    rows = find_schools(d, schools)
    subj = rows.iloc[0]

    def to_ll(r) -> dict:
        return dict(lon=float(r.COORD_X_LL84_IMM), lat=float(r.COORD_Y_LL84_IMM),
                    name=r.NOM_OFFCL_ORGNS, address=f"{r.NOM_IMM}, {r.ADRS_GEO_L1_GDUNO_IMM}")

    subject = to_ll(subj)
    a = (dict(lon=anchor[0], lat=anchor[1], label=anchor_label or "zone centre (temporary site)") if anchor
         else dict(lon=subject["lon"], lat=subject["lat"], label=None))

    def to_m(lon: float, lat: float):
        return gpd.GeoSeries([Point(lon, lat)], crs=4326).to_crs(CRS).iloc[0]

    centre_m = to_m(a["lon"], a["lat"])
    circle_m = centre_m.buffer(radius, quad_segs=32)
    circle_ll = gpd.GeoSeries([circle_m], crs=CRS).to_crs(4326).iloc[0]
    pts = [circle_ll] + ([Point(*mark)] if mark else [])
    bounds = gpd.GeoSeries(pts, crs=4326).total_bounds  # minx, miny, maxx, maxy

    stations = []
    if d.metro is not None:
        centres = [centre_m] + ([to_m(*mark)] if mark else [])
        keep: set = set()
        for c in centres:
            dist = d.metro.geometry.distance(c)
            keep.update(dist[dist <= radius].index.tolist() or [dist.idxmin()])  # in the circle, or the nearest one
        stations = [dict(lon=float(st.lon), lat=float(st.lat), name=st.name, kind=st.kind)
                    for st in d.metro.loc[sorted(keep)].itertuples()]
    else:
        logger.warning("no metro_stations_osm.json; run fetch_open_data.py metro_osm to show stations")

    data = dict(subject=subject, anchor=a, radius=radius,
                circle={"type": "Feature", "properties": {}, "geometry": mapping(circle_ll)},
                bounds=[[float(bounds[0]), float(bounds[1])], [float(bounds[2]), float(bounds[3])]],
                comparators=[to_ll(r) for r in rows.iloc[1:].itertuples()],
                mark=dict(lon=mark[0], lat=mark[1], label=mark_label or "marker") if mark else None,
                stations=stations)
    div_id = f"zone-map-{subj.CD_ORGNS}"
    html = TEMPLATE.format(maplibre=MAPLIBRE, style=STYLE, div_id=div_id, height=height,
                           data=json.dumps(data, ensure_ascii=False))
    if out:
        out.write_text(html)
        logger.success("-> {}", out)
    else:
        typer.echo(html)


if __name__ == "__main__":
    app()
