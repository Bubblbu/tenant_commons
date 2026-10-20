# raw/boundaries — hand-drawn boundary layers

## DTES_sub_zoning/

- **Source:** TODO — who drew it and from what reference (the QGIS metadata in `DTES_sub_zoning.qmd` is blank). Added 2026-10-20.
- **Method:** manual (QGIS shapefile), no fetch script.
- **File:** `DTES_sub_zoning.shp` (+ sidecars). BC Albers (EPSG:3005). Seven named polygons (`name`): Gastown, DEOD, Victory Square, Chinatown, Thornton Park, Strathcona, Industrial. `id` is empty.
- **Quirks:** Gastown and Industrial have small self-intersections (repaired with `make_valid` on read); neighbouring zones overlap or gap by a few m² along shared edges.
- **Used by:** the map's Chinatown and DEOD overlay areas (`config.toml` `[[overlay_areas]]`, `tc_core/overlay_areas.py`). Other zones can be added there by name.

## SRO/

- Predates this manifest; not read by the pipeline.
