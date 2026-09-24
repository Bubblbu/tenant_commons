"""Histogram-binning for the sidebar's value/units filter sliders.

Forked verbatim from `src/sica_mapping/data/pipeline.py`'s (retired) `BUILDING_METRICS`/
`_summarize_metric`/`build_building_metrics` (see normalize.py's provenance
note). Pure, no I/O — `wiring.js`'s `buildMetricControls()` silently omits
the filter section when `filter_config.json` lacks a `building_metrics` key,
so this needs to be a real, faithful port, not a "close enough" summary.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BUILDING_METRICS = {
    "value_land": {
        "label": "Assessed land value",
        "format": "currency",
        "unit": "$",
        "type": "float",
        "step": 5000,
        "attr": "value-land",
        "bins": 24,
        # A handful of $1 placeholder-looking values sit far below where
        # real assessments start; without a floor they'd waste roughly half
        # the bins on an empty gap (see _summarize_metric's log_floor).
        "log_floor": 10000,
    },
    "value_bldg": {
        "label": "Assessed building value",
        "format": "currency",
        "unit": "$",
        "type": "float",
        "step": 5000,
        "attr": "value-bldg",
        "bins": 24,
        "log_floor": 10000,
    },
    "units": {
        "label": "Units",
        "format": "number",
        "type": "int",
        "step": 1,
        "attr": "units",
        "bins": 18,
        "force_log": True,
    },
    "year_built": {
        "label": "Year built",
        "format": "year",
        "type": "int",
        "step": 1,
        "attr": "year-built",
        "bins": 24,
    },
}


def _summarize_metric(series: pd.Series, *, meta: dict) -> dict | None:
    data = series.dropna()
    if data.empty:
        return None
    data = data.astype(float)
    min_val = float(np.min(data))
    max_val = float(np.max(data))
    if not np.isfinite(min_val) or not np.isfinite(max_val):
        return None
    positive_min = None
    if np.any(data > 0):
        positive_min = float(np.min(data[data > 0]))
    span = max_val - min_val
    bins = meta.get("bins")
    if bins is None:
        bins = min(24, max(6, int(np.sqrt(len(data)))))
    use_log: bool = False
    can_use_log = (
        positive_min is not None and positive_min > 0.0 and max_val > positive_min
    )
    force_log = bool(meta.get("force_log"))
    if can_use_log:
        explicit = meta.get("use_log")
        if explicit is not None:
            use_log = bool(explicit)
        elif force_log:
            use_log = True
        elif meta.get("type") != "int":
            threshold = float(meta.get("log_threshold", 25.0))
            ratio = max_val / positive_min if positive_min else float("inf")
            use_log = meta.get("format") == "currency" or ratio >= threshold
    if force_log and not use_log and can_use_log:
        use_log = True
    if use_log:
        safe_min = max(
            positive_min if positive_min and positive_min > 0 else max_val, 1e-6
        )
        # log_floor (BUILDING_METRICS, e.g. value_land/value_bldg's $10k): a
        # handful of placeholder-looking values (a literal $1 assessed land
        # value, mixed with genuine variation down near $0 for value_bldg)
        # sit far below where real data starts, so an unfloored log range
        # wastes roughly half its bins on an empty gap. Values at or below
        # the floor collapse into one explicit bin instead of being spread
        # (thinly, near-emptily) across the low end of the log range.
        log_floor = meta.get("log_floor")
        if log_floor is not None:
            safe_min = max(safe_min, float(log_floor))
        # The frontend's slider reads min_positive as its own log-scale
        # floor (see wiring.js's renderMetricControl) — keeping it in sync
        # with safe_min here is what keeps the slider's positions aligned
        # with the histogram bars/ticks under it, floor bucket included.
        positive_min = safe_min
        below_mask = data <= safe_min
        below_count = int(below_mask.sum())
        above = data[~below_mask]
        if below_count and not above.empty:
            log_data = np.log(above)
            above_bins = max(1, bins - 1)
            # Explicit range (rather than np.histogram's default of the
            # data's own min/max) so the log-spaced bins start exactly at
            # the floor — tiling contiguously against the floor bucket
            # below, with no unlabelled gap between them.
            above_counts, log_edges = np.histogram(
                log_data, bins=above_bins, range=(np.log(safe_min), np.log(max_val))
            )
            above_edges = np.exp(log_edges)
            above_edges[0] = float(safe_min)
            above_edges[-1] = float(max_val)
            counts = np.concatenate(([below_count], above_counts))
            edges = np.concatenate(([float(min_val)], above_edges))
        else:
            # Nothing below the floor (or everything is): behaves exactly as
            # before — one continuous log range over the whole series.
            clipped = data.copy()
            clipped[below_mask] = safe_min
            log_data = np.log(clipped)
            counts, log_edges = np.histogram(log_data, bins=bins)
            edges = np.exp(log_edges)
            edges[0] = float(min_val if min_val < safe_min else safe_min)
            edges[-1] = float(max_val)
    else:
        counts, edges = np.histogram(data, bins=bins)
    max_count = int(counts.max()) if counts.size else 0
    bins_list = [
        {"start": float(edges[i]), "end": float(edges[i + 1]), "count": int(counts[i])}
        for i in range(len(counts))
    ]
    if len(data) >= 20:
        suggested_min = float(np.percentile(data, 5))
        suggested_max = float(np.percentile(data, 95))
    else:
        suggested_min = min_val
        suggested_max = max_val
    suggested_min = max(min_val, min(suggested_min, max_val))
    suggested_max = min(max_val, max(suggested_max, min_val))
    if suggested_min >= suggested_max:
        suggested_min = min_val
        suggested_max = max_val
    step = meta.get("step")
    if step is None:
        if meta.get("type") == "int":
            step = 1
        else:
            step = span / 200 if span > 0 else max_val / 200 if max_val > 0 else 0.01
    if step == 0:
        step = 1 if meta.get("type") == "int" else 0.01
    decimals = meta.get("decimals")
    if decimals is None:
        decimals = 0 if meta.get("type") == "int" else 2
    attr = meta.get("attr") or meta.get("column", "").replace("_", "-")
    return {
        "label": meta.get("label", meta.get("column")),
        "min": float(min_val),
        "max": float(max_val),
        "suggested_min": float(suggested_min),
        "suggested_max": float(suggested_max),
        "step": float(step),
        "bins": bins_list,
        "max_count": max_count,
        "format": meta.get("format", "number"),
        "unit": meta.get("unit"),
        "type": meta.get("type", "float"),
        "decimals": int(decimals),
        "attr": attr,
        "min_positive": positive_min,
        "use_log": use_log,
    }


def build_building_metrics(pts_df: pd.DataFrame) -> dict[str, dict]:
    summaries: dict[str, dict] = {}
    for column, meta in BUILDING_METRICS.items():
        if column not in pts_df.columns:
            continue
        summary = _summarize_metric(pts_df[column], meta={"column": column, **meta})
        if summary:
            summaries[column] = summary
    return summaries
