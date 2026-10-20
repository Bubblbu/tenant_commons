"""Boundary overlays a building can belong to alongside its local_area.

Chinatown, the Downtown Eastside/Oppenheimer District, the Villages Plan
Areas: each is an `OverlayArea` in config.toml's `[[overlay_areas]]`, read
from a shapefile or GeoJSON. They're flags of their own (a building is in a
real neighbourhood *and* any number of these), not alternative local_area
values — see export.export_artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas
from shapely.geometry.base import BaseGeometry

WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class OverlayArea:
    # Filter value and the `areas` entry on buildings and blocks
    # ("chinatown", "deod"). Stable: it's in shared ?hood= links.
    key: str
    # What the map calls it.
    name: str
    # Shapefile or GeoJSON, any CRS.
    source: str
    # The one feature to take, by its `name` property; None takes them all.
    feature: str | None = None


def load_area_features(source: str, feature: str | None = None) -> list[tuple[str | None, BaseGeometry]]:
    """(name, WGS84 polygon) for each feature of `source`, or only the one
    whose `name` is `feature`. Repaired with make_valid: hand-drawn layers
    carry small self-intersections (DTES_sub_zoning's Gastown, Industrial).
    """
    gdf = geopandas.read_file(source)
    if gdf.crs is not None:
        gdf = gdf.to_crs(WGS84)
    names = gdf["name"] if "name" in gdf.columns else [None] * len(gdf)
    out = [
        (None if n is None or n != n else str(n), geom)
        for n, geom in zip(names, gdf.geometry.make_valid())
        if geom is not None and not geom.is_empty
    ]
    if feature is None:
        return out
    picked = [(n, g) for n, g in out if n == feature]
    if not picked:
        raise ValueError(f"{source}: no feature named {feature!r}")
    return picked
