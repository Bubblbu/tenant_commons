"""SQLite-backed data layer for SICA Mapping v2.

Backend for `frontend/`: ingest, merge, and export produce the JSON/GeoJSON
artifacts the Vite/TypeScript map reads. See CLAUDE.md for the v2 rebuild
rationale.
"""

from __future__ import annotations

from .db import get_connection, init_db

__all__ = ["get_connection", "init_db"]
