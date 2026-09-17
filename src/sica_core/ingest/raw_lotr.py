"""Ingest a Samwise (BC Land Owner Transparency Registry research tool)
export verbatim into raw_lotr_ownership.

Raw storage only, same rationale as raw_sro.py/raw_coops.py — one row per
(property, reporting corporation, disclosed interest holder) declaration,
kept browsable and unmodified. The entity-pair extraction that turns this
into ownership_claims rows lives in ingest/lotr_claims.py, which reads from
this table rather than re-parsing the CSV.

Unlike raw_sro/raw_coops, this table is PERSISTENT (see its schema.sql
comment) since it isn't wired into run_ingest()'s REBUILDABLE-table
lifecycle. ingest_raw_lotr() replaces its own contents on every call
instead, so re-running scripts/import_lotr_claims.py against a refreshed
Samwise export is safe to repeat.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pandas as pd

from ..io import normalize_cols, read_any_csv

RAW_LOTR_COLUMNS = [
    "pid",
    "reporting_body_name",
    "reporting_body_kind",
    "reporting_body_capacity",
    "reporting_body_category",
    "reporting_body_party_type",
    "type_of_interest",
    "holder_type",
    "holder_name",
    "obscure_message",
    "individual_last_name",
    "individual_given_names",
    "individual_is_full_name_omitted",
    "individual_is_canadian_citizen_or_pr",
    "individual_principal_residence_city",
    "individual_principal_residence_province",
    "individual_principal_residence_country",
    "individual_is_principal_residence_canada",
    "individual_citizenship_country_codes",
    "corporation_legal_name",
    "corporation_registered_business_name",
    "corporation_partnership_type",
    "corporation_partnership_type_other",
    "corporation_registered_address_line1",
    "corporation_registered_address_line2",
    "corporation_registered_address_city",
    "corporation_registered_address_province_code",
    "corporation_registered_address_province_name",
    "corporation_registered_address_country_code",
    "corporation_registered_address_country_name",
    "corporation_registered_address_postal_code",
    "corporation_is_head_office_different_from_registered",
    "corporation_has_head_office",
    "corporation_governing_laws_jurisdiction",
    "corporation_incorporation_jurisdiction",
    "corporation_continued_jurisdiction",
    "order_id",
    "order_created_date",
    "search_by",
    "search_text",
    "is_exact_match",
    "data_fetch_status",
    "item_row_identifier",
    "source_path",
]


def load_raw_lotr_frame(path: str) -> pd.DataFrame:
    df = normalize_cols(read_any_csv(path))

    unexpected = set(df.columns) - set(RAW_LOTR_COLUMNS)
    if unexpected:
        raise RuntimeError(
            f"Samwise LOTR export has columns with no raw_lotr_ownership mapping: "
            f"{sorted(unexpected)}. Add them to RAW_LOTR_COLUMNS/schema.sql, don't drop silently."
        )

    for col in RAW_LOTR_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[RAW_LOTR_COLUMNS]


def ingest_raw_lotr(conn: sqlite3.Connection, path: str) -> int:
    df = load_raw_lotr_frame(path)
    ingested_at = datetime.now(timezone.utc).isoformat()
    rows = [
        (*(None if pd.isna(v) else v for v in row), ingested_at)
        for row in df.itertuples(index=False)
    ]
    placeholders = ", ".join(["?"] * (len(RAW_LOTR_COLUMNS) + 1))
    columns_sql = ", ".join(RAW_LOTR_COLUMNS + ["ingested_at"])
    with conn:
        conn.execute("DELETE FROM raw_lotr_ownership")
        conn.executemany(
            f"INSERT INTO raw_lotr_ownership ({columns_sql}) VALUES ({placeholders})",
            rows,
        )
    return len(rows)
