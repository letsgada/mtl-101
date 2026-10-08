# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "pyarrow>=16", "geopandas>=1.0", "pyogrio>=0.9", "shapely>=2.0", "typer>=0.12", "loguru>=0.7"]
# ///
"""Emit an interactive map of a school's zone as a raw HTML fragment for a Quarto post.

    uv run scripts/zone_map.py "Laurier" > map.html
    uv run scripts/zone_map.py 762103 762087 762089 --mark -73.6175 45.5404 --mark-label "Temporary site" --out map.html

The first school is the subject (accent-coloured pin and the zone circle); the others are
comparators (zone-coloured pins). Métro and REM stations are drawn as M / R squares from
data/raw/metro_stations_osm.json (OpenStreetMap); --stations chooses how many: `zone` keeps the
old behaviour (inside the circle or polygon, else the nearest one), `bounds` (the default) adds
every station in view, so comparator schools show their own stations too, and `all` embeds the
whole island network, which is ~90 stations and a few kilobytes. Stations outside the zone are
drawn smaller and lighter so the zone's own keep the emphasis. --anchor moves
the circle to another point; --mark adds a dashed marker (a temporary site) without moving it.
--area draws a quartier polygon instead of a circle and, since no single school is chosen, every
school becomes a zone-coloured pin (--edge codes dashed); stations inside the polygon are drawn.

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
from shapely.geometry import Point, box, mapping

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
    if (data.circle) {{
      map.addSource('zone', {{type: 'geojson', data: data.circle}});
      map.addLayer({{id: 'zone-fill', type: 'fill', source: 'zone', paint: {{'fill-color': soft, 'fill-opacity': 0.35}}}});
      map.addLayer({{id: 'zone-line', type: 'line', source: 'zone', paint: {{'line-color': zone, 'line-width': 2}}}});
    }}
    if (data.area) {{
      map.addSource('area', {{type: 'geojson', data: data.area}});
      map.addLayer({{id: 'area-fill', type: 'fill', source: 'area', paint: {{'fill-color': soft, 'fill-opacity': 0.2}}}});
      map.addLayer({{id: 'area-line', type: 'line', source: 'area', paint: {{'line-color': zone, 'line-width': 2.5}}}});
    }}
    data.stations.forEach(function (st) {{
      var near = st.in_zone !== false;
      var s = near ? 18 : 13;
      pin([st.lon, st.lat], 'width:' + s + 'px;height:' + s + 'px;border-radius:3px;background:#fff;border:' +
          (near ? '2px solid ' + zone : '1px solid ' + soft) + ';color:' + (near ? zone : soft) +
          ';font:bold ' + (near ? 11 : 9) + 'px/' + (near ? 14 : 11) + 'px sans-serif;text-align:center;cursor:pointer' +
          (near ? '' : ';opacity:0.85'),
          '<b>' + st.name + '</b><br>' + (st.kind === 'light_rail' ? 'REM' : 'Métro') + ' station',
          st.kind === 'light_rail' ? 'R' : 'M');
    }});
    data.comparators.forEach(function (s) {{
      var border = (s.edge ? '2px dashed ' : '2px solid ') + zone;
      var size = data.subject ? 12 : 14;
      pin([s.lon, s.lat], 'width:' + size + 'px;height:' + size + 'px;border-radius:50%;background:' + soft + ';border:' + border + ';cursor:pointer',
          '<b>' + s.name + '</b><br>' + s.address + (s.edge ? '<br><i>outside the area, within the margin</i>' : ''));
    }});
    if (data.mark) {{
      pin([data.mark.lon, data.mark.lat], 'width:14px;height:14px;border-radius:50%;background:#fff;border:2px dashed ' + accent + ';cursor:pointer',
          data.mark.label);
    }}
    if (data.anchor.label) {{
      pin([data.anchor.lon, data.anchor.lat], 'width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid ' + accent, data.anchor.label);
    }}
    if (data.subject) {{
      pin([data.subject.lon, data.subject.lat], 'width:16px;height:16px;border-radius:50%;background:' + accent + ';border:3px solid ' + accent + ';cursor:pointer',
          '<b>' + data.subject.name + '</b><br>' + data.subject.address);
    }}
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
    area: Annotated[Optional[Path], typer.Option("--area", help="GeoJSON polygon from area_info.py: draw its outline")] = None,
    no_circle: Annotated[bool, typer.Option("--no-circle", help="do not draw the kilometre circle")] = False,
    edge: Annotated[Optional[list[str]], typer.Option("--edge", help="codes drawn as dashed pins (edge schools)")] = None,
    stations_mode: Annotated[str, typer.Option("--stations", metavar="zone|bounds|all",
                                               help="which métro/REM stations to draw")] = "bounds",
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
    area_m = area_ll = None
    if area:
        g = gpd.read_file(area, engine="pyogrio")
        area_ll = g.to_crs(4326).geometry.union_all()
        area_m = g.to_crs(CRS).geometry.union_all()
    pts = ([area_ll] if area_ll is not None else [] if no_circle else [circle_ll]) + \
          ([Point(*mark)] if mark else []) + \
          [Point(float(r.COORD_X_LL84_IMM), float(r.COORD_Y_LL84_IMM)) for r in rows.itertuples()]
    bounds = gpd.GeoSeries(pts, crs=4326).total_bounds  # minx, miny, maxx, maxy

    if stations_mode not in {"zone", "bounds", "all"}:
        logger.error(f"--stations must be zone, bounds or all, not {stations_mode!r}")
        raise typer.Exit(1)

    stations = []
    if d.metro is not None:
        # the zone's own stations: inside the polygon or the circle, falling back to the nearest one
        in_zone: set = set()
        if area_m is not None:
            inside = d.metro[d.metro.within(area_m)]
            in_zone.update(inside.index.tolist() or [d.metro.geometry.distance(area_m.centroid).idxmin()])
        else:
            for c in [centre_m] + ([to_m(*mark)] if mark else []):
                dist = d.metro.geometry.distance(c)
                in_zone.update(dist[dist <= radius].index.tolist() or [dist.idxmin()])
        keep = set(in_zone)
        if stations_mode == "all":
            keep = set(d.metro.index)
        elif stations_mode == "bounds":
            view_m = gpd.GeoSeries([box(*bounds)], crs=4326).to_crs(CRS).iloc[0].buffer(300)
            keep |= set(d.metro[d.metro.within(view_m)].index)
        stations = [dict(lon=float(st.lon), lat=float(st.lat), name=st.name, kind=st.kind,
                         in_zone=st.Index in in_zone)
                    for st in d.metro.loc[sorted(keep)].itertuples()]
        logger.debug(f"stations: {len(stations)} drawn ({len(in_zone)} in the zone), mode {stations_mode}")
    else:
        logger.warning("no metro_stations_osm.json; run fetch_open_data.py metro_osm to show stations")

    edge_codes = set(edge or [])
    if area_ll is not None:
        # an area map has no chosen school: every school is a zone-coloured pin, edge schools dashed
        pins = [dict(to_ll(r), edge=str(r.CD_ORGNS) in edge_codes) for r in rows.itertuples()]
        subject = None
    else:
        pins = [dict(to_ll(r), edge=str(r.CD_ORGNS) in edge_codes) for r in rows.iloc[1:].itertuples()]
    data = dict(subject=subject, anchor=a, radius=radius,
                circle=None if (no_circle or area_ll is not None) else {"type": "Feature", "properties": {}, "geometry": mapping(circle_ll)},
                area={"type": "Feature", "properties": {}, "geometry": mapping(area_ll)} if area_ll is not None else None,
                bounds=[[float(bounds[0]), float(bounds[1])], [float(bounds[2]), float(bounds[3])]],
                comparators=pins,
                mark=dict(lon=mark[0], lat=mark[1], label=mark_label or "marker") if mark else None,
                stations=stations)
    div_id = f"zone-map-{area.stem if area else subj.CD_ORGNS}"
    html = TEMPLATE.format(maplibre=MAPLIBRE, style=STYLE, div_id=div_id, height=height,
                           data=json.dumps(data, ensure_ascii=False))
    if out:
        out.write_text(html)
        logger.success("-> {}", out)
    else:
        typer.echo(html)


if __name__ == "__main__":
    app()
