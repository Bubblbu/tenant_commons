"""Address cleaning used by the prepare steps (ported from vhd, unchanged)."""

from __future__ import annotations

import re

NON_ALPHA_NUM = r"[^a-z0-9 ]"
DIRECTIONS = ["e", "w", "n", "nw", "ne", "s", "sw", "se"]


def clean_address(address: str | None) -> str | None:
    if address is None:
        return None
    address = address.lower()
    address = re.sub(NON_ALPHA_NUM, "", address)
    address = (
        address.replace(" street", " st")
        .replace(" avenue", " av")
        .replace(" drive", " dr")
        .replace(" road", " rd")
        .replace(" way", " w")
        .replace(" drive", " dr")
    )
    address = address.replace(" str", " st").replace(" ave", " av")
    return address


def fix_street_names(street_name: str | None) -> str | None:
    if street_name is None:
        return None
    parts = street_name.lower().split(" ")
    if parts and parts[-1] in DIRECTIONS:
        return " ".join(parts[-1:] + parts[:-1])
    return street_name
