"""Readers for v2 artifacts, so export tests state intent, not JSON paths."""

from __future__ import annotations

import json
from pathlib import Path


def records(out: Path) -> dict[str, dict]:
    """Building records keyed by address."""
    data = json.loads((out / "building_records.json").read_text())
    return {r["address"]: r for r in data["records"].values()}


def networks(out: Path) -> dict[str, dict]:
    return json.loads((out / "networks.json").read_text())["networks"]


def parties(rec: dict, role: str) -> list[dict]:
    return [p for p in rec["parties"] if p["role"] == role]


def owner(rec: dict) -> dict | None:
    found = parties(rec, "owner")
    return found[0] if found else None


def network(out: Path, rec: dict) -> dict | None:
    return networks(out).get(rec["network_id"]) if rec["network_id"] else None
