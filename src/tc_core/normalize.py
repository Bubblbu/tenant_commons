"""Address/owner normalization utilities.

Forked from `src/sica_mapping/core/normalization.py` (as of the tc_core
scaffold, 2026-07) rather than imported. `sica_mapping` was deleted once
`tc_core` + `frontend/` fully replaced it (see git history before f6dea9b
for the original); this file is now the only copy.
"""

from __future__ import annotations

import ast
import math
import re
import unicodedata
from typing import Any, Tuple


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def normalize_street(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"[.]", "", s)
    s = re.sub(r"\s+", " ", s)
    repl = {
        "street": "st",
        "avenue": "ave",
        "road": "rd",
        "drive": "dr",
        "boulevard": "blvd",
        "place": "pl",
        "court": "ct",
        "highway": "hwy",
        "av": "ave",
    }
    for k, v in repl.items():
        s = re.sub(rf"\b{k}\b", v, s)
    return s


def addr_key_from_freeform(addr: str) -> str:
    addr = str(addr).strip().lower()
    m = re.match(r"^(\d+)\s+(.+)$", addr)
    return (
        f"{m.group(1)} {normalize_street(m.group(2))}" if m else normalize_street(addr)
    )


_DIRECTIONS = {"e", "w", "n", "nw", "ne", "s", "sw", "se"}


def move_trailing_direction(street_name: str | None) -> str | None:
    """'Georgia W' -> 'w georgia': moves a trailing direction abbreviation
    (as used in the City's property-tax-report `street_name` field) to the
    front, matching the leading-direction convention used elsewhere.
    Passes the input through unchanged if it doesn't end in one."""
    if street_name is None:
        return None
    parts = street_name.lower().split(" ")
    if parts and parts[-1] in _DIRECTIONS:
        return " ".join(parts[-1:] + parts[:-1])
    return street_name


_DIRECTION_RE = re.compile(r"^(\d+)\s+(east|west|north|south)\b")
_DIRECTION_ABBR = {"east": "e", "west": "w", "north": "n", "south": "s"}
# "#800 - 1047 Barclay St", "100-2950 Heather St": a unit number in front of
# the civic number, not a civic-number range like "2165-2195 W 45th Av".
_UNIT_PREFIX_RE = re.compile(r"^#?\s*\w+\s*-\s*(\d+\s.+)$")
# "7401 - 7469 Talon Square", "500 & 502 Alexander St": a range of civic
# numbers; keyed by the first.
_RANGE_RE = re.compile(r"^(\d+)\s*(?:-|&|and)\s*\d+\s+(.+)$")


def address_key_variants(street: str) -> list[str]:
    """Candidate addr_keys for a source address, most literal first.

    addr_key_from_freeform takes exactly one leading civic number and one
    street string, so it can't handle spelled-out directions ("1865 East
    10th Avenue" vs the abbreviated "1865 e 10th ave" convention buildings
    are keyed with), a unit-number prefix ("#800 - 1047 Barclay St"), or a
    civic-number range ("7401 - 7469 Talon Square") on its own. This
    generates every variant worth trying against a known-keys index, most
    literal first; callers pick the first hit.
    """
    base = re.sub(r"\s+", " ", str(street)).strip().lower().rstrip("*").strip()
    raw = [base]
    m = _UNIT_PREFIX_RE.match(base)
    if m:
        raw.append(m.group(1))
    m = _RANGE_RE.match(base)
    if m:
        raw.append(f"{m.group(1)} {m.group(2)}")
    keys: list[str] = []
    for text in raw:
        text = _DIRECTION_RE.sub(lambda d: f"{d.group(1)} {_DIRECTION_ABBR[d.group(2)]}", text)
        key = addr_key_from_freeform(text)
        if key not in keys:
            keys.append(key)
    return keys


def parse_lat_lon(s: Any) -> Tuple[float, float]:
    if _is_missing(s):
        return (math.nan, math.nan)
    m = re.match(r"\s*([\-0-9.]+)\s*,\s*([\-0-9.]+)\s*$", str(s))
    return (float(m.group(1)), float(m.group(2))) if m else (math.nan, math.nan)


def clean_owner_label(name: Any) -> str:
    if _is_missing(name):
        return "(Unknown)"
    s = str(name).strip()
    if not s:
        return "(Unknown)"
    parsed = None
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
        except (ValueError, SyntaxError):
            parsed = None
    if parsed is None and s.startswith("(") and s.endswith(")"):
        try:
            parsed = ast.literal_eval(s)
        except (ValueError, SyntaxError):
            parsed = None
    if isinstance(parsed, (list, tuple, set)):
        cleaned = [
            str(item).strip().strip("'\"") for item in parsed if str(item).strip()
        ]
        if cleaned:
            return ", ".join(cleaned)
        return "(Unknown)"
    if isinstance(parsed, str):
        s = parsed.strip()
    if s.startswith(("'", '"')) and s.endswith(("'", '"')) and len(s) >= 2:
        s = s[1:-1]
    stripped = s.strip()
    if stripped.startswith("[") and stripped.endswith("]") and "," not in stripped:
        stripped = stripped[1:-1].strip()
    return stripped or "(Unknown)"


def sanitize_owner(name: Any) -> str:
    if _is_missing(name) or str(name).strip() == "":
        return "unknown"
    s = str(name).lower()
    s = unicodedata.normalize("NFKD", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"
