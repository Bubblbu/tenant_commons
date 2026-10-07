"""Derives active-membership metrics from vtu_membership's allow-listed columns.

Forked from the parts of the retired `src/sica_mapping/data/vtu.py` that only touch
`tag_list`/`updated_at` (everything else there reads columns this project
deliberately never ingests). Used by both the validation checkpoint and,
eventually, the real public/internal export.

"now" is an explicit parameter, not a bare `datetime.now()` call, so
two runs being compared (e.g. the checkpoint vs. a reference run) can't
disagree over a 365-day recency window crossed mid-comparison.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import polars as pl

MEMBERSHIP_YEAR_RE = re.compile(r"membership-(\d{4})", re.IGNORECASE)
RECENT_ACTIVITY_WINDOW = timedelta(days=365)


def _extract_tags(raw: object) -> list[str]:
    if not isinstance(raw, str):
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def _latest_membership_year(tags: list[str]) -> int | None:
    years = []
    for tag in tags:
        match = MEMBERSHIP_YEAR_RE.search(tag)
        if match:
            years.append(int(match.group(1)))
    return max(years) if years else None


def _parse_updated_at(raw: object) -> datetime | None:
    """An ISO 8601 updated_at in UTC (no offset means UTC); None otherwise."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def prepare_membership_metrics(members_df: pl.DataFrame, now: datetime) -> pl.DataFrame:
    tags = [_extract_tags(raw) for raw in members_df["tag_list"].to_list()]
    df = members_df.with_columns(
        tags=pl.Series(tags, dtype=pl.List(pl.String)),
        has_member_tag=pl.Series([any(t.lower() == "member" for t in ts) for ts in tags], dtype=pl.Boolean),
        latest_membership_year=pl.Series([_latest_membership_year(ts) for ts in tags], dtype=pl.Int64),
        updated_at_parsed=pl.Series(
            [_parse_updated_at(raw) for raw in members_df["updated_at"].to_list()],
            dtype=pl.Datetime("us", "UTC"),
        ),
    )
    df = df.with_columns(
        updated_recently=pl.col("updated_at_parsed").is_not_null()
        & ((pl.lit(now) - pl.col("updated_at_parsed")) <= RECENT_ACTIVITY_WINDOW).fill_null(False)
    )
    return df.with_columns(
        is_active_default=pl.col("has_member_tag")
        & (
            pl.col("latest_membership_year").is_null()
            | (pl.col("latest_membership_year") >= now.year - 1).fill_null(False)
            | pl.col("updated_recently")
        )
    )


def compute_building_member_metrics(members_df: pl.DataFrame, now: datetime) -> pl.DataFrame:
    """members_df: vtu_membership rows with a non-null building_id."""
    columns = [
        "building_id",
        "member_count",
        "member_count_all",
        "has_vtu_member",
        "members_payload",
        "latest_membership_year",
    ]
    if members_df.is_empty():
        return pl.DataFrame(
            schema={
                "building_id": pl.Int64, "member_count": pl.Int64, "member_count_all": pl.Int64,
                "has_vtu_member": pl.Boolean, "members_payload": pl.Object,
                "latest_membership_year": pl.Int64,
            }
        )

    metrics = prepare_membership_metrics(members_df, now)
    out = (
        metrics.group_by("building_id")
        .agg(
            member_count=pl.col("is_active_default").sum().cast(pl.Int64),
            member_count_all=pl.len().cast(pl.Int64),
            latest_membership_year=pl.col("latest_membership_year")
            .filter(pl.col("has_member_tag"))
            .max(),
        )
        .sort("building_id")
    )

    payload: dict[int, list[dict[str, object]]] = {}
    for row in metrics.sort("building_id", maintain_order=True).iter_rows(named=True):
        updated = row["updated_at_parsed"]
        payload.setdefault(row["building_id"], []).append(
            {
                "tags": list(row["tags"]),
                "updated_at": updated.isoformat() if updated is not None else None,
                "has_member_tag": bool(row["has_member_tag"]),
                "latest_membership_year": row["latest_membership_year"],
                "is_active_default": bool(row["is_active_default"]),
            }
        )

    return out.with_columns(
        has_vtu_member=pl.col("member_count") > 0,
        members_payload=pl.Series([payload[b] for b in out["building_id"]], dtype=pl.Object),
    ).select(columns)


def membership_filter_config(members_df: pl.DataFrame, now: datetime) -> dict[str, object]:
    if members_df.is_empty():
        year_counts: dict[int, int] = {}
        year_min = None
        year_max = None
        top_tags: list[dict[str, object]] = []
    else:
        metrics = prepare_membership_metrics(members_df, now)
        years = metrics["latest_membership_year"].drop_nulls()
        if years.is_empty():
            year_counts = {}
            year_min = None
            year_max = None
        else:
            counts = Counter(years.to_list())
            year_counts = {year: counts[year] for year in sorted(counts, reverse=True)[:8]}
            year_min = int(years.min())
            year_max = int(years.max())
        tag_counter: Counter[str] = Counter()
        for tags in metrics["tags"].to_list():
            tag_counter.update(t for t in tags if "member" in t.lower())
        top_tags = [
            {"name": tag, "count": count} for tag, count in tag_counter.most_common(12)
        ]
    default_since = (now - RECENT_ACTIVITY_WINDOW).date().isoformat()
    return {
        "membership_years": year_counts,
        "top_tags": top_tags,
        "default_updated_since": default_since,
        "updated_year_min": year_min,
        "updated_year_max": year_max,
    }
