"""The City's SRO inventory came out of a PDF. Text extraction split words
("N on-Profit"), and let a sector label spill into the neighbouring operator
cell together with a stray letter or two of the owner name ("vP rivate").
raw_sro keeps the text as published; this module reads it."""

from __future__ import annotations

import re

_SECTORS = {
    "private": "private",
    "nonprofit": "non_profit",
    "government": "government",
    "chinesesociety": "chinese_society",
}
# Letters of a neighbouring cell that may precede a spilled label.
_MAX_SPILL = 2


def _squash(text: object) -> str:
    return re.sub(r"[^a-z]", "", str(text).lower()) if text is not None else ""


def sector(text: object) -> str | None:
    """The sector a cell names, tolerating split words and a short spill."""
    squashed = _squash(text)
    for word, code in _SECTORS.items():
        if squashed.endswith(word) and len(squashed) - len(word) <= _MAX_SPILL:
            return code
    return None


def is_leaked_label(text: object) -> bool:
    """True when a name cell holds only a sector label (and spill), not a name."""
    return sector(text) is not None
