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


# Canonical spelling rules. They run on every key on both sides of every
# join (source addresses and the City's register alike), so they may only
# make spellings agree, never guess. See docs/ADDRESS_MATCHING.md (rules C1-C8).
_TYPE_ABBR = {
    "street": "st",
    "avenue": "ave",
    "road": "rd",
    "drive": "dr",
    "boulevard": "blvd",
    "place": "pl",
    "court": "ct",
    "highway": "hwy",
    "av": "ave",
    "crescent": "cres",  # C6
    "cr": "cres",
    "crt": "ct",
    "southwest": "sw",  # C5
    "southeast": "se",
    "northwest": "nw",
    "northeast": "ne",
}
_DIRECTIONS = {"e", "w", "n", "nw", "ne", "s", "sw", "se"}
_DIRECTION_WORDS = {"north": "n", "south": "s", "east": "e", "west": "w"}
# Final-token street types: what loose_key ignores and what C7 de-duplicates.
_STREET_TYPES = {"st", "ave", "rd", "dr", "blvd", "pl", "ct", "hwy", "cres"}
_GLUED_DIRECTION_RE = re.compile(r"\b([nsew])(\d+(?:st|nd|rd|th)?)\b")
_BARE_NUMBER_RE = re.compile(r"\b(\d+)(?=\s+(?:ave|st)\b)")
_DASHES_RE = re.compile("â€“|â€”|–|—")


def _ordinal(n: str) -> str:
    if 11 <= int(n) % 100 <= 13:
        return f"{n}th"
    return n + {"1": "st", "2": "nd", "3": "rd"}.get(n[-1], "th")


def normalize_street(s: str) -> str:
    s = str(s).strip().lower()
    s = re.sub(r"[.]", "", s)
    s = re.sub(r"\s+", " ", s)
    for k, v in _TYPE_ABBR.items():
        s = re.sub(rf"\b{k}\b", v, s)
    s = _GLUED_DIRECTION_RE.sub(r"\1 \2", s)  # C2 "w49th" -> "w 49th"
    s = _BARE_NUMBER_RE.sub(lambda m: _ordinal(m.group(1)), s)  # C1 "e 18 ave" -> "e 18th ave"
    tokens = s.split(" ")
    if tokens and tokens[-1] in _DIRECTION_WORDS:  # C4 "kent ave north" -> "kent ave n"
        tokens[-1] = _DIRECTION_WORDS[tokens[-1]]
    if len(tokens) >= 3 and tokens[-1] in _STREET_TYPES and tokens[-2] in _STREET_TYPES:
        tokens.pop()  # C7 "cordova st st" -> "cordova st"
    leading = tokens[0] in _DIRECTIONS or tokens[0] in _DIRECTION_WORDS
    if len(tokens) >= 2 and tokens[-1] in _DIRECTIONS and not leading:
        tokens = tokens[-1:] + tokens[:-1]  # C3 "16th ave e" -> "e 16th ave"
    return " ".join(tokens)


def addr_key_from_freeform(addr: str) -> str:
    # Trailing "*" is a footnote marker the City's FOI rental list uses on
    # some addresses (e.g. "1155 Thurlow St*") -- strip it before keying,
    # same as address_key_variants already does, so it doesn't silently
    # split a real address from its own key.
    addr = _DASHES_RE.sub("-", str(addr))  # C8
    addr = addr.strip().lower().rstrip("*").strip()
    m = re.match(r"^(\d+)\s+(.+)$", addr)
    return (
        f"{m.group(1)} {normalize_street(m.group(2))}" if m else normalize_street(addr)
    )


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
# Two numbers before a street: "429 - 433 W Pender St" (a civic range),
# "303-1210 Jervis St" / "#800 - 1047 Barclay St" (a unit, then the civic
# number), "7430 & 7460 Heather St" (two civic numbers). _civic_pair decides.
_PAIR_RE = re.compile(r"^(#)?\s*([a-z]*\d+[a-z]?)\s*(-|&|and)\s*(\d+)\s+(.+)$")
# "3306 E 5th Ave / 3350 E 5th Ave", "407 Heatley Ave ; 684 E Hastings St":
# several addresses in one field.
_MULTI_SPLIT_RE = re.compile(r"\s*[/;]\s*")
_MAX_RANGE_SPAN = 200


def _civic_pair(text: str) -> tuple[str, int, int, str] | None:
    """("range", A, B, street) or ("unit", 0, B, street) for a two-number
    address, None otherwise (rule V1/V2 in docs/ADDRESS_MATCHING.md).

    A range is B > A on the same side of the street (same parity) and at
    most 200 apart, or an explicit "&"/"and" list. Everything else -- a "#",
    letters ("PH1"), B < A, an odd/even mix, a wider gap -- reads as a unit
    number in front of civic number B. An abbreviated end ("3335-45") is
    expanded first.
    """
    m = _PAIR_RE.match(text)
    if not m:
        return None
    hash_, a, sep, b, street = m.groups()
    if hash_ or not a.isdigit():
        return ("unit", 0, int(b), street) if sep == "-" else None
    a_n, b_n = int(a), int(b)
    if len(b) < len(a):
        b_n = int(a[: len(a) - len(b)] + b)
    if sep != "-":
        return ("range", a_n, b_n, street)
    if b_n > a_n and (b_n - a_n) % 2 == 0 and b_n - a_n <= _MAX_RANGE_SPAN:
        return ("range", a_n, b_n, street)
    return ("unit", 0, int(b), street)


def _base(street: Any) -> str:
    s = _DASHES_RE.sub("-", str(street))
    return re.sub(r"\s+", " ", s).strip().lower().rstrip("*").strip()


def address_key_variants(street: str) -> list[str]:
    """Candidate addr_keys for a source address, most literal first.

    addr_key_from_freeform takes exactly one leading civic number and one
    street string, so it can't handle spelled-out directions ("1865 East
    10th Avenue" vs the abbreviated "1865 e 10th ave" convention buildings
    are keyed with), a unit-number prefix ("#800 - 1047 Barclay St"), a
    civic-number range ("7401 - 7469 Talon Square") or several addresses in
    one field on its own. This generates every variant worth trying against
    a known-keys index, most literal first; callers pick the first hit (or
    use AddressMatcher, which also tries the guesses that need that index).
    """
    base = _base(street)
    raw = [base]
    first = _MULTI_SPLIT_RE.split(base, maxsplit=1)[0]
    if first and first != base:
        raw.append(first)
    pair = _civic_pair(raw[-1])
    if pair:
        kind, a, b, rest = pair
        raw += [f"{a} {rest}", f"{b} {rest}"] if kind == "range" else [f"{b} {rest}"]
    keys: list[str] = []
    for text in raw:
        text = _DIRECTION_RE.sub(lambda d: f"{d.group(1)} {_DIRECTION_ABBR[d.group(2)]}", text)
        key = addr_key_from_freeform(text)
        if key not in keys:
            keys.append(key)
    return keys


_LOOSE_RE = re.compile(rf"^(\d+ .+?)(?: (?:{'|'.join(sorted(_STREET_TYPES))}))?$")
# M2: where a building name may follow the street ("1266 W 12TH AVE Appolloni
# Court"). Broadway and Kingsway carry no type, so they end a street themselves.
_TRUNCATE_TYPES = _STREET_TYPES | {"way", "sq"}
_TYPELESS_STREETS = {"broadway", "kingsway"}


def loose_key(key: str) -> str:
    """addr_key without its final street type ("404 hawks av" ~ "404 hawks st")."""
    m = _LOOSE_RE.match(key)
    return m.group(1) if m else key


def _name_cut(street_tokens: list[str]) -> int | None:
    """Index of the token a building name follows, in normalized street
    tokens: the first street type after a street name (so a leading "St" --
    Saint -- is never a cut point), or Broadway/Kingsway. None when only
    directions follow it ("e kent ave n"). A stray type after Broadway or
    Kingsway ("1265 kingsway ave") is cut, which is what lets it match."""
    for i, tok in enumerate(street_tokens[:-1]):
        named_before = any(t not in _DIRECTIONS for t in street_tokens[:i])
        if tok in _TYPELESS_STREETS or (tok in _TRUNCATE_TYPES and named_before):
            if all(t in _DIRECTIONS for t in street_tokens[i + 1:]):
                return None
            return i
    return None


def _drop_trailing_name(key: str) -> str | None:
    """'1266 w 12th ave appolloni ct' -> '1266 w 12th ave'; None if nothing to cut."""
    m = re.match(r"^(\d+) (.+)$", key)
    if not m:
        return None
    tokens = m.group(2).split(" ")
    i = _name_cut(tokens)
    return None if i is None else f"{m.group(1)} {' '.join(tokens[: i + 1])}"


def split_trailing_name(address: Any) -> tuple[str, str | None]:
    """'1005 JERVIS ST Mathew Court' -> ('1005 JERVIS ST', 'Mathew Court').

    Same cut point as AddressMatcher's M2, but on the source text, keeping
    its spelling. Returns (address, None) when no name follows the street.
    For sources that put a building name in the address field (the 2024 FOI
    extract) and need it split off before any known-keys index exists.
    """
    raw = re.sub(r"\s+", " ", str(address)).strip()
    tokens = raw.split(" ")
    if len(tokens) < 3 or not tokens[0][:1].isdigit():
        return raw, None
    street = tokens[1:]
    norm = [normalize_street(t) for t in street]
    i = _name_cut(norm)
    # Only street types left over ("309 E CORDOVA ST St") is no name.
    if i is None or all(t in _STREET_TYPES or t in _DIRECTIONS for t in norm[i + 1:]):
        return raw, None
    return " ".join(tokens[: i + 2]), " ".join(street[i + 1:])


class AddressMatcher:
    """Resolves source addresses to one of a fixed set of known addr_keys.

    Tiers, first hit wins (M1-M4 in docs/ADDRESS_MATCHING.md):
      M1 a variant (address_key_variants) is a known key or an alias of one;
      M2 the same after dropping a building name that follows the street;
      M3 ignoring the street type, when exactly one known key fits;
      M4 for a civic range whose ends aren't known, the one known civic
         number inside it on the same side of the street.
    match() returns None rather than guess between several candidates.
    """

    def __init__(self, known_keys, aliases: dict[str, str] | None = None) -> None:
        self.known = {k for k in known_keys if isinstance(k, str)}
        self.aliases = dict(aliases or {})
        seen: dict[str, set[str]] = {}
        self._civics: dict[str, list[int]] = {}
        for key in self.known:
            seen.setdefault(loose_key(key), set()).add(key)
            m = re.match(r"^(\d+) (.+)$", key)
            if m:
                self._civics.setdefault(m.group(2), []).append(int(m.group(1)))
        self._loose = {lk: next(iter(ks)) for lk, ks in seen.items() if len(ks) == 1}

    def _exact(self, key: str) -> str | None:
        return key if key in self.known else self.aliases.get(key)

    def match(self, address: Any) -> str | None:
        if _is_missing(address) or not str(address).strip():
            return None
        variants = address_key_variants(address)
        for key in variants:  # M1
            if hit := self._exact(key):
                return hit
        trimmed = [t for t in map(_drop_trailing_name, variants) if t]
        for key in trimmed:  # M2
            if hit := self._exact(key):
                return hit
        for key in variants + trimmed:  # M3
            if hit := self._loose.get(loose_key(key)):
                return hit
        return self._inside_range(address)  # M4

    def _inside_range(self, address: Any) -> str | None:
        base = _base(address)
        pair = _civic_pair(_MULTI_SPLIT_RE.split(base, maxsplit=1)[0])
        if not pair or pair[0] != "range":
            return None
        _, a, b, rest = pair
        street = address_key_variants(f"{a} {rest}")[0][len(f"{a} "):]
        inside = {c for c in self._civics.get(street, ()) if a < c < b and c % 2 == a % 2}
        return f"{inside.pop()} {street}" if len(inside) == 1 else None


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
