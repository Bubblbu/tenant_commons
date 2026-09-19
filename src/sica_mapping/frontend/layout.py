from __future__ import annotations

from html import escape
from importlib import resources
from string import Template

import folium
import numpy as np
import pandas as pd
from shapely.geometry import shape

from .colors import greens_color


def _load_template(name: str) -> str:
    return resources.files(__package__).joinpath(f"templates/{name}").read_text()


SIDEBAR_HTML_TEMPLATE = Template(_load_template("sidebar.html"))
WIRING_JS_TEMPLATE = Template(_load_template("wiring.js"))
LEGEND_BLOCKS_TEMPLATE = Template(_load_template("legend_blocks.html"))
LEGEND_FILTERS_TEMPLATE = Template(_load_template("legend_filters.html"))


def add_blocks_layer(m: folium.Map, feature_collection: dict) -> folium.GeoJson:
    features = feature_collection.get("features") or []
    max_total_units = 0
    for feat in features:
        props = feat.get("properties") or {}
        try:
            units_count = int(props.get("total_units") or 0)
        except (TypeError, ValueError):
            units_count = 0
        if units_count > max_total_units:
            max_total_units = units_count

    def block_style(feat):
        props = feat.get("properties") or {}
        try:
            buildings = int(props.get("buildings") or 0)
        except (TypeError, ValueError):
            buildings = 0
        if buildings <= 0:
            # Empty blocks carry no meaningful data — leave them transparent
            # rather than painting them into the color scale.
            return {
                "fillColor": "transparent",
                "color": "#b8b8b8",
                "weight": 1,
                "fillOpacity": 0,
            }
        total_units = props.get("total_units") or 0
        try:
            total_units = float(total_units)
        except (TypeError, ValueError):
            total_units = 0.0
        if max_total_units > 0:
            scaled = min(max(total_units / max_total_units, 0.0), 1.0)
        else:
            scaled = 0.0
        return {
            "fillColor": greens_color(scaled),
            "color": "#b8b8b8",
            "weight": 1,
            "fillOpacity": 0.7,
        }

    popup = None
    if feature_collection.get("features"):
        popup = folium.GeoJsonPopup(
            fields=[
                "block_label",
                "buildings",
                "total_units",
                "median_year_built",
                "member_buildings",
                "total_members",
            ],
            aliases=[
                "Block",
                "Buildings",
                "# Units",
                "Median year",
                "Buildings w/ VTU",
                "Total VTU members",
            ],
            localize=True,
        )
    g = folium.GeoJson(
        data=feature_collection,
        name="Blocks: Total units (green gradient)",
        style_function=block_style,
        popup=popup,
    )
    g.add_to(m)
    return g


def _neighbourhood_style(feat):
    return {
        "color": "#ff8c00",
        "weight": 2,
        "opacity": 0.9,
        "fill": False,
    }


def add_neighbourhoods_layer(m: folium.Map, feature_collection: dict) -> folium.FeatureGroup:
    """Vancouver's 22 local-area boundaries — a static reference overlay (name
    + outline only, no data join). Boundary lines and name labels both in
    orange, grouped into one togglable layer.
    """
    layer = folium.FeatureGroup(
        name="Neighbourhoods (orange boundaries)", show=True, overlay=True
    )
    for feat in feature_collection.get("features") or []:
        props = feat.get("properties") or {}
        name = str(props.get("name", ""))
        folium.GeoJson(data=feat, style_function=_neighbourhood_style).add_to(layer)
        geom = shape(feat["geometry"])
        centroid = geom.centroid
        folium.Marker(
            location=[centroid.y, centroid.x],
            icon=folium.DivIcon(
                html=(
                    '<div style="color:#ff8c00;font-weight:700;font-size:12px;'
                    "text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,"
                    '1px 1px 0 #fff;white-space:nowrap;pointer-events:none;">'
                    f"{escape(name)}</div>"
                ),
                icon_size=(0, 0),
            ),
        ).add_to(layer)
    layer.add_to(m)
    return layer


def marker_radius(units) -> float:
    if pd.isna(units) or units <= 0:
        return 3.2
    u = float(units)
    capped = min(max(u, 1.0), 600.0)
    ratio = float(np.log1p(capped) / np.log1p(600.0))
    return 2.5 + 7.0 * ratio


# Housing-type ring colors (a building's stroke when it matches exactly one
# type; the first type wins the stroke on a rare dual match, see below).
COOP_RING_COLOR = "#d97706"
SRO_RING_COLOR = "#3182bd"
RING_STROKE_WEIGHT = 2.2
DEFAULT_STROKE_COLOR = "#ffffff"
DEFAULT_STROKE_WEIGHT = 0.6

def add_buildings_layers(m: folium.Map, pts_df):
    layer_vtu = folium.FeatureGroup(
        name="VTU member buildings", show=True, overlay=True
    )
    layer_non = folium.FeatureGroup(
        name="Other buildings (gray)", show=True, overlay=True
    )
    marker_metadata: list[dict[str, object]] = []

    for _, r in pts_df.iterrows():
        has_vtu_member = bool(r["has_vtu_member"])
        # Binary indicator only — has a VTU member or not, no gradient by count.
        color = "#cc4778" if has_vtu_member else "#9e9e9e"
        neutral_color = "#9e9e9e"
        opacity = 0.75 if has_vtu_member else 0.35
        radius_val = marker_radius(r["units"])
        member_share = r.get("member_share_building", 0.0)
        units_val = None if pd.isna(r["units"]) else int(r["units"])

        housing_name = str(r.get("housing_name") or "").strip()
        name_line = f"{escape(housing_name)}<br>" if housing_name else ""
        popup_html = (
            f"<b>{escape(str(r['address']))}</b><br>"
            f"{name_line}"
            f"Units: {'' if pd.isna(r['units']) else int(r['units'])}<br>"
            f"VTU members: {int(r['member_count'])}<br>"
            f"Member share: {member_share * 100:.0f}%<br>"
            f"Owner: {escape(str(r['owner_group']))}<br>"
            f"Year built: {'' if pd.isna(r['year_built']) else int(r['year_built'])}"
        )

        # Claims-derived portfolio (see sica_core/portfolios.py) — for now,
        # the Owner line above already shows the portfolio name directly
        # (export.py folds it into owner_group when one exists), so this
        # only adds the size detail, not the name again.
        portfolio_name = r.get("portfolio_name")
        # pd.isna() first, not `if portfolio_name and ...` -- the cached-data
        # path runs convert_dtypes(), which turns a missing value into
        # pandas' nullable pd.NA, and bool(pd.NA) raises before pd.isna()
        # ever runs.
        if not pd.isna(portfolio_name):
            building_count = r.get("portfolio_building_count")
            building_count_val = None if pd.isna(building_count) else int(building_count)
            buildings_label = "building" if building_count_val == 1 else "buildings"
            entities_raw = r.get("portfolio_entities")
            entity_count = len(entities_raw) if isinstance(entities_raw, list) else 0
            popup_html += (
                f"<br><b>Portfolio:</b> "
                f"{'' if building_count_val is None else building_count_val} "
                f"{buildings_label}, {entity_count} linked entities"
            )

        # Housing type (SRO/co-op) — ring color, not mutually exclusive: a
        # building matching both gets the first type as its own stroke and an
        # extra outer ring in the second type's color (one known case today:
        # 853 e pender st).
        is_coop = bool(r.get("is_coop", False))
        is_sro = bool(r.get("is_sro", False))

        housing_types: list[tuple[str, str]] = []
        if is_coop:
            housing_types.append(("coop", COOP_RING_COLOR))
        if is_sro:
            housing_types.append(("sro", SRO_RING_COLOR))

        if housing_types:
            stroke_color = housing_types[0][1]
            stroke_weight = RING_STROKE_WEIGHT
        else:
            stroke_color = DEFAULT_STROKE_COLOR
            stroke_weight = DEFAULT_STROKE_WEIGHT

        if is_coop:
            coop_status = str(r.get("coop_status") or "").strip()
            coop_ownership_model = str(r.get("coop_ownership_model") or "").strip()
            popup_html += "<br><b>Co-op</b>"
            if coop_status:
                popup_html += f": {escape(coop_status)}"
            if coop_ownership_model:
                popup_html += f" ({escape(coop_ownership_model)})"
            coop_url = str(r.get("coop_url") or "").strip()
            if coop_url:
                popup_html += (
                    f' (<a href="{escape(coop_url)}" target="_blank" '
                    f'rel="noopener">more info</a>)'
                )
        if is_sro:
            sro_owner = str(r.get("sro_owner") or "").strip()
            sro_operator = str(r.get("sro_operator") or "").strip()
            sro_occupancy = str(r.get("sro_occupancy_status") or "").strip()
            popup_html += (
                f"<br><b>SRO/SRA:</b> Owner {escape(sro_owner)} · "
                f"Operator {escape(sro_operator)}"
            )
            if sro_occupancy:
                popup_html += f" · {escape(sro_occupancy)}"
            sro_rooms = str(r.get("sro_registered_rooms") or "").strip()
            if sro_rooms:
                popup_html += f"<br>Registered rooms: {escape(sro_rooms)}"
        block_id_val = r.get("block_id")
        block_id = int(block_id_val) if pd.notna(block_id_val) else None

        target_layer = layer_vtu if has_vtu_member else layer_non

        # Extra concentric ring(s) for every housing type beyond the first —
        # added before the building marker so they paint underneath it as a
        # halo (same insertion-order-is-paint-order rule wiring.js documents
        # for blocks vs buildings).
        extra_rings: list[dict[str, str]] = []
        for i, (htype, hcolor) in enumerate(housing_types[1:], start=1):
            ring = folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=radius_val + 3.0 * i,
                fill=False,
                color=hcolor,
                weight=2.0,
                opacity=0.9,
            )
            target_layer.add_child(ring)
            extra_rings.append({"housing_type": htype, "marker_var": ring.get_name()})

        mk = folium.CircleMarker(
            location=[r["lat"], r["lon"]],
            radius=radius_val,
            fill=True,
            fill_opacity=opacity,
            color=stroke_color,
            weight=stroke_weight,
            fill_color=color,
        ).add_child(folium.Popup(popup_html, max_width=320))
        target_layer.add_child(mk)

        marker_metadata.append(
            {
                "marker_var": mk.get_name(),
                "b_id": int(r["b_id"]),
                "owner_key": r["owner_key"],
                "block_id": block_id,
                "base_radius": radius_val,
                "base_opacity": opacity,
                "base_color": color,
                "neutral_color": neutral_color if has_vtu_member else color,
                "is_vtu": has_vtu_member,
                "member_count": int(r["member_count"]) if pd.notna(r["member_count"]) else 0,
                "units": units_val,
                "local_area": r.get("local_area"),
                "year_built": None if pd.isna(r["year_built"]) else int(r["year_built"]),
                "housing_type": r.get("housing_type") or "",
                "primary_housing_type": housing_types[0][0] if housing_types else "",
                "stroke_color": stroke_color,
                "stroke_weight": stroke_weight,
                "extra_rings": extra_rings,
            }
        )

    layer_non.add_to(m)
    layer_vtu.add_to(m)
    layer_vtu_name = layer_vtu.get_name()
    layer_non_name = layer_non.get_name()

    return layer_vtu, layer_non, layer_vtu_name, layer_non_name, marker_metadata


def sidebar_html(
    buildings_rows: str,
    blocks_rows: str,
    landlords_rows: str,
    neighbourhoods_rows: str,
    sidebar_width: int,
) -> str:
    return SIDEBAR_HTML_TEMPLATE.safe_substitute(
        sidebar_width=sidebar_width,
        buildings_rows=buildings_rows,
        blocks_rows=blocks_rows,
        landlords_rows=landlords_rows,
        neighbourhoods_rows=neighbourhoods_rows,
    )


def wiring_js(
    blocks_layer_var: str,
    layer_vtu_var: str,
    layer_non_var: str,
    layer_neighbourhoods_var: str,
    filter_config_url: str,
    marker_metadata_url: str,
    building_records_url: str,
) -> str:
    return WIRING_JS_TEMPLATE.safe_substitute(
        blocks_layer_var=blocks_layer_var,
        layer_vtu_var=layer_vtu_var,
        layer_non_var=layer_non_var,
        layer_neighbourhoods_var=layer_neighbourhoods_var,
        filter_config_url=filter_config_url,
        marker_metadata_url=marker_metadata_url,
        building_records_url=building_records_url,
    )


def legends_html(
    sidebar_width: int, filter_config: dict[str, object]
) -> tuple[str, str]:
    neighbourhoods = filter_config.get("neighbourhoods") or []
    hood_entries: list[str] = []
    for nei in neighbourhoods:
        name = str(nei.get("name", ""))
        count_val = int(nei.get("count", 0))
        units_val = int(nei.get("units", 0))
        hood_entries.append(
            f'<label class="filter-tag"><input type="checkbox" class="filter-neighbourhood-option" '
            f'value="{escape(name.lower())}" checked> {escape(name)} '
            f'<span class="filter-tag-count">({format(count_val, ",")} bldgs · {format(units_val, ",")} units)</span></label>'
        )
    if hood_entries:
        hood_html = "".join(hood_entries)
    else:
        hood_html = '<em class="filter-none">No neighbourhood data</em>'

    block_max_raw = filter_config.get("blocks_total_units_max")
    if block_max_raw is None:
        block_max_raw = filter_config.get("blocks_member_building_max")
    try:
        block_max = int(block_max_raw)
    except (TypeError, ValueError):
        block_max = 0
    block_max = max(block_max, 0)
    if block_max == 0:
        block_ticks = ["0"] * 6
    else:
        fractions = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
        block_ticks = []
        for frac in fractions:
            value = int(round(block_max * frac))
            if frac == 1.0:
                value = block_max
            block_ticks.append(format(value, ","))
    try:
        sidebar_width_px = int(sidebar_width)
    except (TypeError, ValueError):
        sidebar_width_px = 0
    legend_left_offset = max(sidebar_width_px, 0) + 20

    block_ticks_html = "".join(f"<span>{escape(tick)}</span>" for tick in block_ticks)
    legend_map = LEGEND_BLOCKS_TEMPLATE.substitute(
        block_ticks_html=block_ticks_html,
        block_max_label=format(block_max, ","),
        legend_left_offset=legend_left_offset,
    )

    legend_filters = LEGEND_FILTERS_TEMPLATE.substitute(
        hood_html=hood_html,
    )

    return legend_map, legend_filters
