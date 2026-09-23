"""Geometry parsing helpers.

Forked from `src/sica_mapping/data/geometry.py` (see normalize.py's
provenance note; `sica_mapping` is retired). Only `parse_geom` is needed
here — `export.py`'s `_blocks_feature_collection` emits the stored GeoJSON
string directly rather than round-tripping through shapely.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from shapely.geometry import base as shapely_base, shape


def parse_geom(raw: Any) -> Optional[shapely_base.BaseGeometry]:
    if raw is None:
        return None
    try:
        return shape(json.loads(raw))
    except Exception:
        return None
