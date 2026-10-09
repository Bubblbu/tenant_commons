"""Curated corrections to the City's SRO inventory names (sro_names.txt).

The inventory came out of a PDF with names cut off, misspelt, or written as
"person - numbered company". sro_names.txt maps each published name to what
it means: a corrected name, joint owners, the person behind a company, or who
runs the building. The export reads the names; scripts/update_sro_claims.py
turns the `behind:` pairs into ownership claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .sro_text import is_leaked_label

DEFAULT_PATH = Path(__file__).with_name("sro_names.txt")
CITY_RECORD = "city_record"


# The inventory abbreviates some names; expand the ones that recur. Applied
# before sro_names.txt, whose keys are these expanded forms.
SRO_NAME_ALIASES = {
    "BCH": "BC Housing",
    "COV": "City of Vancouver",
    "Atira Property Managem": "Atira Property Management",
    "PHS": "PHS Community Services Society",
    "Lookout": "Lookout Housing and Health Society",
}


def clean_sro_name(name: object) -> str | None:
    """Display form of an SRO owner/operator name as published; None when it
    names no one (a sector label such as "Private" — the owner runs the
    building — or one split or spilled by the PDF extraction, see sro_text.py)."""
    if name is None:
        return None
    text = str(name).strip()
    if not text or is_leaked_label(text):
        return None
    return SRO_NAME_ALIASES.get(text, text)


@dataclass(frozen=True)
class SroName:
    owners: list[str]
    behind: list[str] = field(default_factory=list)
    manager: str | None = None


def _names(text: str) -> list[str]:
    return [n.strip() for n in text.split(";") if n.strip()]


def parse_sro_names(text: str) -> dict[str, SroName]:
    """{name as published: SroName} for every `published => meaning` line."""
    result: dict[str, SroName] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=>" not in line:
            continue
        published, meaning = (part.strip() for part in line.split("=>", 1))
        head, *extras = (part.strip() for part in meaning.split("|"))
        owners = _names(head.removeprefix("owners:")) if head.startswith("owners:") else [head]
        behind: list[str] = []
        manager = None
        for extra in extras:
            key, _, value = extra.partition(":")
            if key.strip() == "behind":
                behind = _names(value)
            elif key.strip() == "manager":
                manager = value.strip() or None
            else:
                raise ValueError(f"sro_names: unknown field {key.strip()!r} in {line!r}")
        result[published] = SroName(owners=owners, behind=behind, manager=manager)
    return result


def load_sro_names(path: str | Path = DEFAULT_PATH) -> dict[str, SroName]:
    return parse_sro_names(Path(path).read_text(encoding="utf-8"))


def sro_name_claims(names: dict[str, SroName]) -> list[dict]:
    """record_claim() keyword arguments for each (company, person behind it)
    pair: confirmed common_owner claims sourced to the City's records, with a
    claim_key stable across runs so re-importing updates instead of adding."""
    claims: dict[str, dict] = {}
    for name in names.values():
        for company in name.owners:
            for person in name.behind:
                key = f"sro_names:{company}|{person}"
                claims[key] = dict(
                    claim_key=key, entity_a=company, entity_b=person,
                    relationship="common_owner", source_type=CITY_RECORD,
                    confidence="confirmed",
                    source_note="City of Vancouver SRO inventory (FOI), owner column",
                )
    return list(claims.values())


def corrected_owner_names(published: object, names: dict[str, SroName] | None = None) -> list[str]:
    """Every owner an SRO owner cell names, after cleaning and sro_names.txt."""
    names = load_sro_names() if names is None else names
    text = clean_sro_name(published)
    if text is None:
        return []
    return list(names[text].owners) if text in names else [text]
