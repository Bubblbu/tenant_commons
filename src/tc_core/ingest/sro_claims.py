"""Ownership claims from the curated SRO inventory names (sro_names.txt).

Each `behind:` pair (a company and the person the City's inventory names
with it) becomes a confirmed common_owner claim with source_type
city_record, upserted by a stable claim_key so re-running after editing
sro_names.txt updates rather than duplicates. Mirrors lotr_claims.py.
"""

from __future__ import annotations

import sqlite3

from ..claims import record_claim
from ..sro_names import SroName, sro_name_claims


def import_sro_name_claims(conn: sqlite3.Connection, names: dict[str, SroName]) -> int:
    claims = sro_name_claims(names)
    for claim in claims:
        record_claim(conn, status="active", **claim)
    conn.commit()
    return len(claims)
