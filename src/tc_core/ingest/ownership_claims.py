"""Bulk-import ownership_claims from a CSV of manually-curated research.

Not a `raw_<source>.py` module: unlike raw_buildings/raw_addresses,
ownership_claims isn't merged into a separate derived table afterward — it's
already the final, curated layer (same category as membership.py's source).

Each row is upserted via claims.record_claim() by its required `claim_key`
column — re-running against an edited version of the same research
spreadsheet updates existing rows in place rather than duplicating them, so
this is safe to re-run repeatedly as the spreadsheet evolves. Retraction is
just editing a row's status/retracted_reason and re-importing — never a
delete, so "never deleted, only retracted" (CLAUDE.md Section 3) holds
regardless of how many times a row is touched before that.

See docs/DATA_SOURCES.md's "Manual curation" section for why this source
isn't cataloged there — it's not an acquisition source with a URL/cadence,
it's the curated layer itself.
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from ..claims import find_similar_entity, record_claim
from ..io import normalize_cols, read_any_csv

logger = logging.getLogger("tc_core.ingest")

REQUIRED_CLAIM_COLUMNS = {"claim_key", "entity_a", "entity_b", "relationship", "source_type"}
OPTIONAL_CLAIM_COLUMNS = {
    "source_note",
    "reported_by",
    "date_reported",
    "confidence",
    "status",
    "retracted_at",
    "retracted_reason",
}
ALLOWED_CLAIM_COLUMNS = REQUIRED_CLAIM_COLUMNS | OPTIONAL_CLAIM_COLUMNS


def load_ownership_claims_frame(path: str) -> pd.DataFrame:
    df = normalize_cols(read_any_csv(path))
    unexpected = set(df.columns) - ALLOWED_CLAIM_COLUMNS
    if unexpected:
        raise RuntimeError(
            f"ownership_claims CSV has unexpected columns: {sorted(unexpected)}. "
            "Add them to ALLOWED_CLAIM_COLUMNS/schema.sql, don't drop silently."
        )
    missing = REQUIRED_CLAIM_COLUMNS - set(df.columns)
    if missing:
        raise RuntimeError(f"ownership_claims CSV missing required columns: {sorted(missing)}")
    return df


def _cell(row, col: str) -> str | None:
    if col not in row.index:
        return None
    value = row[col]
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def ingest_ownership_claims(conn: sqlite3.Connection, path: str) -> int:
    df = load_ownership_claims_frame(path)

    count = 0
    for _, row in df.iterrows():
        claim_key = _cell(row, "claim_key")
        if claim_key is None:
            raise RuntimeError(
                f"ownership_claims CSV row missing required claim_key: {row.to_dict()}"
            )
        entity_a = _cell(row, "entity_a")
        entity_b = _cell(row, "entity_b")

        # Informational only — record_claim() itself now auto-collapses this
        # exact case (same sanitize_owner() key, different spelling) onto the
        # existing stored label, so this is a paper trail for that automatic
        # collapse, not a prompt for a human decision. Genuine entity
        # resolution (different sanitize_owner() keys, same real owner) still
        # requires a same_entity/common_owner claim — see claims.py's module
        # docstring.
        for entity in (entity_a, entity_b):
            if entity is None:
                continue
            similar = find_similar_entity(conn, entity)
            if similar is not None:
                logger.info(
                    "ownership_claims: %r auto-collapsed onto existing entity %r "
                    "(claim_key=%s) — same entity, formatting difference only.",
                    entity, similar, claim_key,
                )

        kwargs = {
            col: _cell(row, col)
            for col in OPTIONAL_CLAIM_COLUMNS
            if _cell(row, col) is not None
        }
        record_claim(
            conn,
            entity_a=entity_a,
            entity_b=entity_b,
            relationship=_cell(row, "relationship"),
            source_type=_cell(row, "source_type"),
            claim_key=claim_key,
            **kwargs,
        )
        count += 1
    return count
