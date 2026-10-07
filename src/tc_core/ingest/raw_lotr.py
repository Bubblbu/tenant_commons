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

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

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


def load_raw_lotr_frame(path: str) -> pl.DataFrame:
    return conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_LOTR_COLUMNS,
        source="Samwise LOTR export",
        table="raw_lotr_ownership",
        columns_name="RAW_LOTR_COLUMNS",
    )


def ingest_raw_lotr(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_lotr_ownership", load_raw_lotr_frame(path), replace=True)
