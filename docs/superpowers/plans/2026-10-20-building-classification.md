# Building Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify every owner entity (legal form, institutional flag) and every building (owner type, market status, operator type, scale), publish it in contract v5, and expose it in the popup and sidebar filters, with two "Landlord portfolio" sliders.

**Architecture:** Pure classification functions in `src/tc_core/metrics/sector.py` run at export time over the parties `export_parties.py` already builds. Corrections and institutional flags are `ownership_claims` rows with the value in `entity_b` (the `network_label` precedent). A new raw table holds the City-owned properties dataset. The frontend reads the new contract fields and filters on them the way it filters housing types and value metrics today.

**Tech Stack:** Python 3.11+, polars, Pydantic v2, SQLite, pytest (`uv run pytest`); Vite + TypeScript, vitest (`cd frontend && npm test`).

**Spec:** `docs/superpowers/specs/2026-10-20-building-classification-design.md` (Task 11 amends it with the refinements listed under "Spec refinements" below).

## Global Constraints

- **Never run `git commit`, `git add`, or any other git write without asking the author first.** Every "Commit" step means: show the proposed message and file list, and wait for a yes. No Claude attribution in commit messages.
- Public contract models use `_Model` (`extra="forbid"`); missing is `null`, never a sentinel string.
- `source_note` and `reported_by` never reach any artifact. Claim provenance in public output is bucketed via `metrics/portfolios.py::EVIDENCE_BUCKET`.
- `scripts/rebuild_data.py --skip-ingest` must never write to the database. Classification outputs therefore go to CSV under `data/derived/classification/`, not to SQLite tables.
- Schema stays Postgres-compatible: no SQLite-only column types.
- Thresholds: `small_portfolio_min = 2`, `large_portfolio_min = 10`, in `config.toml` under `[classification]`.
- `SCHEMA_VERSION` becomes 5 in both `src/tc_core/contract.py` and `frontend/src/config.ts` (`EXPECTED_SCHEMA_VERSION`).
- Follow surrounding code style: short docstrings that say *why*, no new abstractions beyond what a task names.

## Spec refinements (decided while planning; Task 11 writes them into the spec)

1. **Derived outputs are CSV, not SQLite tables** (`--skip-ingest` must not write to the DB). `scripts/classification_report.py` reads `building_records.json` and writes `data/derived/classification/buildings.csv` and `entities.csv`.
2. **Registry holder type is evidence for `individual`.** `raw_lotr_ownership.holder_type = 'INDIVIDUAL'` → `individual` (basis `registry`, not inferred). `CORPORATION` → the name rules choose among the non-person kinds. The spec's "settlor → trust" is dropped: a settlor is whoever created the trust, not the trust itself. `trust` comes from the name or from a claim.
3. **What `inferred` means on the owner axis:** true when the owner type comes from anything other than a registry owner, a claim or the City-owned dataset (licence, SRO inventory, co-op list, non-market list). Name rules applied to a registry owner don't make the building's owner type "inferred". The per-entity basis (`name_rule` vs `registry` vs claim) is still listed in `basis`.
4. **Portfolio sliders read network totals.** The frontend takes `portfolio_units` / `portfolio_value` from `networks[network_id].totals` (`units`, new `assessed_value`). There are no per-building portfolio fields in `building_records.json`. Python computes the same numbers as `points_df` columns only for the histogram summaries.
5. **No facet counts** in `filter_config.json`: the new chips are static HTML like the housing chips.
6. **`Basis` vocabulary:** `name_rule`, `registry`, `licence`, `listing`, `city_owned`, `non_market_list`, `chf_bc`, `sro_inventory`, `claim_registry`, `claim_city_records`, `vtu_research`. `listing` is added for operators from manager listings. `network` is dropped because scale isn't an axis.

## Review Focus

1. **A licence-only building whose licensee is a property manager.** Its owner type must say "inferred, from licence holder", never read as confirmed. Test in Task 3 (`test_licence_only_owner_is_inferred`) and Task 10 (popup shows the inferred styling).
2. **A building with no owner, no licensee and no lists.** Every axis is `unknown`/null, the popup headline is omitted rather than reading "Unknown · unknown", and filters with "Include inferred" on or off neither crash nor match it to a chosen type. Tests in Task 3 (`test_nothing_known_is_unknown`), Task 8 (`unknown building passes only when no type is ticked`) and Task 10 (`headline is empty when nothing is known`).
3. **Retracting an `entity_kind` claim.** After re-import with `status = retracted`, the name rules apply again. Test in Task 1 (`test_retracted_attribute_claim_stops_applying`).
4. **An entity_kind claim with a typo'd value** (e.g. `numbered company` with a space) must fail loudly at import, not silently store junk. Test in Task 1 (`test_attribute_value_outside_vocabulary_is_rejected`).
5. **Joint owners of different types on one parcel** (e.g. a society and a numbered company) → `mixed`, with both parts, matching either chip. Tests in Task 3 (`test_owners_of_different_types_are_mixed`) and Task 8 (`mixed matches any of its parts`).

---

### Task 1: Attribute claims (`entity_kind`, `institutional`)

**Files:**
- Modify: `src/tc_core/claims.py` (constants near line 50; `record_claim()` lines 97–108; `list_known_entities()` lines 152–164; new resolver at end of file)
- Test: `tests/test_claims_attributes.py` (create)

**Interfaces:**
- Produces:
  - `ENTITY_KIND = "entity_kind"`, `INSTITUTIONAL = "institutional"`
  - `ENTITY_KINDS: tuple[str, ...] = ("government", "non_profit", "coop", "individual", "company", "numbered_company", "trust", "partnership", "unknown")`
  - `INSTITUTIONAL_KINDS: tuple[str, ...] = ("reit", "pension_fund", "insurer", "asset_manager", "other")`
  - `ATTRIBUTE_RELATIONSHIPS: dict[str, tuple[str, ...]] = {ENTITY_KIND: ENTITY_KINDS, INSTITUTIONAL: INSTITUTIONAL_KINDS}`
  - `entity_attribute_claims(conn, relationship: str, *, include_unconfirmed: bool = False) -> dict[str, tuple[str, str]]`: `{sanitize_owner(entity_a): (value, source_type)}`, latest `updated_at` wins among active claims.

- [ ] **Step 1: Write the failing tests**

```python
"""entity_kind / institutional claims: a claim about one entity, with the
value in entity_b (the network_label precedent, spec 2026-10-20)."""

from __future__ import annotations

import pytest

from tc_core.claims import (
    ENTITY_KIND,
    INSTITUTIONAL,
    entity_attribute_claims,
    find_similar_entity,
    list_known_entities,
    record_claim,
)
from tc_core.db import get_connection, init_db
from tc_core.normalize import sanitize_owner


def _conn():
    conn = get_connection(":memory:")
    init_db(conn)
    return conn


def test_attribute_value_is_stored_lowercase_and_validated():
    conn = _conn()
    record_claim(conn, "Sun Life Assurance Company of Canada", " Insurer ", INSTITUTIONAL,
                 "manual_research", confidence="confirmed")
    assert conn.execute("SELECT entity_b FROM ownership_claims").fetchone()[0] == "insurer"


def test_attribute_value_outside_vocabulary_is_rejected():
    conn = _conn()
    with pytest.raises(ValueError, match="entity_kind"):
        record_claim(conn, "0733603 BC Ltd", "numbered company", ENTITY_KIND, "manual_research")


def test_attribute_values_are_not_entities():
    conn = _conn()
    record_claim(conn, "Mennonite Senior Citizens Society of BC", "non_profit", ENTITY_KIND,
                 "manual_research", confidence="confirmed")
    assert list_known_entities(conn) == ["Mennonite Senior Citizens Society of BC"]
    assert find_similar_entity(conn, "NON PROFIT") is None


def test_latest_confirmed_claim_wins_and_unconfirmed_is_ignored():
    conn = _conn()
    record_claim(conn, "Acme Ltd", "company", ENTITY_KIND, "manual_research",
                 confidence="confirmed", claim_key="a")
    record_claim(conn, "Acme Ltd", "trust", ENTITY_KIND, "tenant_report",
                 confidence="confirmed", claim_key="b")
    record_claim(conn, "Acme Ltd", "partnership", ENTITY_KIND, "manual_research", claim_key="c")
    assert entity_attribute_claims(conn, ENTITY_KIND) == {sanitize_owner("Acme Ltd"): ("trust", "tenant_report")}
    assert entity_attribute_claims(conn, ENTITY_KIND, include_unconfirmed=True)[sanitize_owner("Acme Ltd")][0] == "partnership"


def test_retracted_attribute_claim_stops_applying():
    conn = _conn()
    record_claim(conn, "Acme Ltd", "trust", ENTITY_KIND, "manual_research",
                 confidence="confirmed", claim_key="a")
    record_claim(conn, "Acme Ltd", "trust", ENTITY_KIND, "manual_research",
                 confidence="confirmed", status="retracted", claim_key="a")
    assert entity_attribute_claims(conn, ENTITY_KIND) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_claims_attributes.py -v`
Expected: FAIL with `ImportError: cannot import name 'ENTITY_KIND'`

- [ ] **Step 3: Implement**

In `claims.py`, after `NETWORK_LABEL`:

```python
# Claims about one entity (spec 2026-10-20): entity_a is the entity, entity_b
# a value from the relationship's vocabulary — never an entity.
ENTITY_KIND = "entity_kind"
INSTITUTIONAL = "institutional"
ENTITY_KINDS = (
    "government", "non_profit", "coop", "individual", "company",
    "numbered_company", "trust", "partnership", "unknown",
)
INSTITUTIONAL_KINDS = ("reit", "pension_fund", "insurer", "asset_manager", "other")
ATTRIBUTE_RELATIONSHIPS = {ENTITY_KIND: ENTITY_KINDS, INSTITUTIONAL: INSTITUTIONAL_KINDS}
# entity_b values that are text, not entities.
_VALUE_RELATIONSHIPS = (NETWORK_LABEL, *ATTRIBUTE_RELATIONSHIPS)
```

In `record_claim()`, replace the `if relationship == NETWORK_LABEL:` block:

```python
    entity_a = _resolve_entity_label(conn, entity_a)
    if relationship == NETWORK_LABEL:
        entity_b = " ".join(str(entity_b).split())
    elif relationship in ATTRIBUTE_RELATIONSHIPS:
        entity_b = str(entity_b).strip().lower()
        if entity_b not in ATTRIBUTE_RELATIONSHIPS[relationship]:
            raise ValueError(
                f"record_claim: {relationship} value {entity_b!r} is not one of "
                f"{', '.join(ATTRIBUTE_RELATIONSHIPS[relationship])}"
            )
    else:
        entity_b = _resolve_entity_label(conn, entity_b)
```

In `list_known_entities()`:

```python
    placeholders = ", ".join("?" * len(_VALUE_RELATIONSHIPS))
    rows = conn.execute(
        "SELECT entity_a AS entity FROM ownership_claims "
        f"UNION SELECT entity_b FROM ownership_claims WHERE relationship NOT IN ({placeholders}) "
        "ORDER BY 1",
        _VALUE_RELATIONSHIPS,
    ).fetchall()
```

At the end of the file:

```python
def entity_attribute_claims(
    conn: sqlite3.Connection, relationship: str, *, include_unconfirmed: bool = False
) -> dict[str, tuple[str, str]]:
    """{sanitize_owner(entity): (value, source_type)} from the most recently
    updated active claim of `relationship` (entity_kind or institutional).
    Confirmed-only unless include_unconfirmed, like the cluster resolvers."""
    confidences = ("confirmed", "unconfirmed") if include_unconfirmed else ("confirmed",)
    placeholders = ", ".join("?" * len(confidences))
    rows = conn.execute(
        f"""
        SELECT entity_a, entity_b, source_type FROM ownership_claims
        WHERE relationship = ? AND status = 'active' AND confidence IN ({placeholders})
        ORDER BY updated_at, claim_id
        """,
        (relationship, *confidences),
    ).fetchall()
    return {sanitize_owner(a): (value, source) for a, value, source in rows}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_claims_attributes.py tests/test_claims_network_labels.py tests/test_claims_entity_resolution.py -v`
Expected: all PASS

- [ ] **Step 5: Commit (ask first)**

```bash
git add src/tc_core/claims.py tests/test_claims_attributes.py
git commit -m "Claims: entity_kind and institutional claims about one entity"
```

---

### Task 2: Entity classifier

**Files:**
- Create: `src/tc_core/metrics/sector.py`
- Test: `tests/test_classification_rules.py` (create)

**Interfaces:**
- Consumes: `claims.ENTITY_KIND`, `claims.INSTITUTIONAL`, `claims.entity_attribute_claims`, `normalize.sanitize_owner`, `metrics.portfolios.EVIDENCE_BUCKET`
- Produces:
  - `@dataclass(frozen=True) class EntityClass: kind: str; basis: str; inferred: bool; institutional: str | None = None`
  - `kind_from_name(name: str) -> str` (one of `claims.ENTITY_KINDS`)
  - `CLAIM_BASIS: dict[str, str]` = `{"registry": "claim_registry", "city_records": "claim_city_records", "vtu_research": "vtu_research"}`
  - `claim_basis(source_type: str) -> str`
  - `registry_holder_types(conn) -> dict[str, str]`: `{sanitize_owner(name): "individual" | "corporation"}`
  - `class EntityClassifier`: `__init__(self, registry: Mapping[str, str] | None = None, kinds: Mapping[str, tuple[str, str]] | None = None, institutional: Mapping[str, tuple[str, str]] | None = None)`; `from_conn(cls, conn) -> EntityClassifier`; `__call__(self, name: str) -> EntityClass`

- [ ] **Step 1: Write the failing tests**

```python
"""Entity kinds from names, the registry and claims (spec 2026-10-20)."""

from __future__ import annotations

import pytest

from tc_core.metrics.sector import EntityClass, EntityClassifier, kind_from_name
from tc_core.normalize import sanitize_owner


@pytest.mark.parametrize("name, kind", [
    ("City of Vancouver", "government"),
    ("BC Housing", "government"),
    ("Provincial Rental Housing Corporation", "government"),
    ("Vancouver Public Housing Corp", "government"),
    ("Mennonite Senior Citizens Society of British Columbia", "non_profit"),
    ("YWCA BRITISH COLUMBIA", "non_profit"),
    ("Young Women's Christian Association", "non_profit"),
    ("CLT 0005 COMMUNITY SOCIETY", "non_profit"),
    ("Helen's Court Co-op Housing Association", "coop"),
    ("0888189 B.C. Ltd.", "numbered_company"),
    ("372328 BC Ltd", "numbered_company"),
    ("1566283 B.C. LTD.", "numbered_company"),
    ("Sun Life Assurance Company of Canada", "company"),
    ("bcIMC Realty Corporation", "company"),
    ("5908 Holdings Ltd.", "company"),
    ("Rei-Mar Investments Ltd & Manytree Holdings Ltd", "company"),
    ("Westbank Limited Partnership", "partnership"),
    ("Kerrisdale Family Trust", "trust"),
    ("Computershare Trust Company of Canada", "company"),
    ("Moore, Kathleen Frances", "individual"),
    ("George Rener & Alenka Rener", "unknown"),
    ("", "unknown"),
])
def test_kind_from_name(name, kind):
    assert kind_from_name(name) == kind


def test_registry_individual_is_evidence_not_inference():
    c = EntityClassifier(registry={sanitize_owner("Paul Y Mansion"): "individual"})
    assert c("Paul Y Mansion") == EntityClass(kind="individual", basis="registry", inferred=False)


def test_registry_corporation_never_becomes_an_individual():
    c = EntityClassifier(registry={sanitize_owner("Smith, John"): "corporation"})
    assert c("Smith, John").kind == "company"


def test_name_rule_is_inferred():
    assert EntityClassifier()("0792203 BC Ltd") == EntityClass(
        kind="numbered_company", basis="name_rule", inferred=True
    )


def test_claim_overrides_name_rule_and_basis_is_bucketed():
    key = sanitize_owner("Mennonite Senior Citizens Society of British Columbia")
    c = EntityClassifier(kinds={key: ("non_profit", "tenant_report")},
                         institutional={key: ("other", "public_registry")})
    got = c("Mennonite Senior Citizens Society of British Columbia")
    assert (got.kind, got.basis, got.inferred, got.institutional) == ("non_profit", "vtu_research", False, "other")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_classification_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tc_core.metrics.sector'`

- [ ] **Step 3: Implement `src/tc_core/metrics/sector.py` (entity half)**

```python
"""Who owns and runs a building, by kind (spec 2026-10-20).

Entities get a kind (government / non-profit / co-op / individual / company /
numbered company / trust / partnership) from, in order: a confirmed
entity_kind claim, the registry's own individual-or-corporation record, then
name rules. Buildings get an owner type, market status, operator type and
scale from their parties plus City lists. Pure functions apart from the two
loaders, so the rules are testable without a database.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from ..claims import ENTITY_KIND, INSTITUTIONAL, entity_attribute_claims
from ..normalize import sanitize_owner
from .portfolios import EVIDENCE_BUCKET

# Ordered: the first match wins. Government bodies are named outright, so
# "...Society of British Columbia" stays a society.
_NAME_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("government", re.compile(
        r"^(the )?city of vancouver\b|\bbc housing\b|british columbia housing management commission|"
        r"provincial rental housing corp|vancouver public housing corp|vancouver affordable housing agency|"
        r"\b(his|her) majesty\b|government of canada|canada mortgage and housing|"
        r"^province of british columbia$|board of parks and recreation|^school district",
        re.I)),
    ("coop", re.compile(r"\bco-?op(erative)?\b", re.I)),
    ("non_profit", re.compile(
        r"\b(society|foundation|church|parish|diocese|synod|ywca|ymca|benevolent|legion|"
        r"young (wo)?men'?s christian association)\b", re.I)),
    ("numbered_company", re.compile(r"^\d{6,}\s*b\.?\s*c\.?\s*(ltd|limited|inc|corp)", re.I)),
    ("partnership", re.compile(r"\b(limited partnership|l\.?p\.?|partnership)\s*$|\bpartnership\b", re.I)),
    ("company", re.compile(r"\btrust company\b", re.I)),
    ("trust", re.compile(r"\btrust\b", re.I)),
    ("company", re.compile(
        r"\b(ltd|limited|inc|incorporated|corp|corporation|company|holdings?|properties|"
        r"investments?|enterprises|developments?|realty|assurance|insurance|bank|reit|ulc)\b\.?",
        re.I)),
    # "Surname, Given Names" as the registry files people.
    ("individual", re.compile(r"^[A-Za-z' -]+, [A-Za-z' .-]+$")),
]

CLAIM_BASIS = {"registry": "claim_registry", "city_records": "claim_city_records", "vtu_research": "vtu_research"}


def claim_basis(source_type: str) -> str:
    """A claim's public basis: provincial registry, City records or VTU research."""
    return CLAIM_BASIS[EVIDENCE_BUCKET.get(source_type, "vtu_research")]


def kind_from_name(name: str) -> str:
    name = (name or "").strip()
    for kind, pattern in _NAME_RULES:
        if pattern.search(name):
            return kind
    return "unknown"


@dataclass(frozen=True)
class EntityClass:
    kind: str
    basis: str  # a contract Basis value
    inferred: bool
    institutional: str | None = None


def registry_holder_types(conn: sqlite3.Connection) -> dict[str, str]:
    """{sanitize_owner(holder name): "individual" | "corporation"} from the
    registry's own record of each holder (reporting bodies included)."""
    out: dict[str, str] = {}
    for name, holder_type in conn.execute(
        "SELECT DISTINCT TRIM(holder_name), holder_type FROM raw_lotr_ownership "
        "WHERE holder_name IS NOT NULL AND TRIM(holder_name) != '' AND holder_type IS NOT NULL"
    ):
        out[sanitize_owner(name)] = "individual" if holder_type == "INDIVIDUAL" else "corporation"
    return out


class EntityClassifier:
    """name -> EntityClass. Claims beat the registry, the registry beats names."""

    def __init__(
        self,
        registry: Mapping[str, str] | None = None,
        kinds: Mapping[str, tuple[str, str]] | None = None,
        institutional: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        self._registry = registry or {}
        self._kinds = kinds or {}
        self._institutional = institutional or {}
        self._cache: dict[str, EntityClass] = {}

    @classmethod
    def from_conn(cls, conn: sqlite3.Connection) -> EntityClassifier:
        return cls(
            registry=registry_holder_types(conn),
            kinds=entity_attribute_claims(conn, ENTITY_KIND),
            institutional=entity_attribute_claims(conn, INSTITUTIONAL),
        )

    def __call__(self, name: str) -> EntityClass:
        if name not in self._cache:
            self._cache[name] = self._classify(name)
        return self._cache[name]

    def _classify(self, name: str) -> EntityClass:
        key = sanitize_owner(name)
        institutional = self._institutional.get(key, (None, None))[0]
        if key in self._kinds:
            kind, source = self._kinds[key]
            return EntityClass(kind, claim_basis(source), False, institutional)
        by_name = kind_from_name(name)
        holder = self._registry.get(key)
        if holder == "individual":
            return EntityClass("individual", "registry", False, institutional)
        if holder == "corporation" and by_name in ("individual", "unknown"):
            return EntityClass("company", "registry", False, institutional)
        return EntityClass(by_name, "name_rule", True, institutional)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_classification_rules.py -v`
Expected: all PASS. If a parametrized name fails, fix the rule order or pattern, not the expectation. The expectations are the spec's tricky names.

- [ ] **Step 5: Commit (ask first)**

```bash
git add src/tc_core/metrics/sector.py tests/test_classification_rules.py
git commit -m "Classification: entity kinds from claims, registry holder type and names"
```

---

### Task 3: Contract classification models and the building classifier

**Files:**
- Modify: `src/tc_core/contract.py` (after `Sector` on line 36; `Party` lines 49–57)
- Modify: `src/tc_core/metrics/sector.py` (append building half)
- Test: `tests/test_classification_rules.py` (append)

**Interfaces:**
- Consumes: `EntityClass`, `EntityClassifier`, `claim_basis` (Task 2); `contract.Party`, `contract.Source`
- Produces (contract.py):
  - `Kind`, `Institutional`, `OwnerType = Literal["government","non_profit","coop","private","mixed","unknown"]`, `Basis` (vocabulary in "Spec refinements" 6), `Scale = Literal["single","small_portfolio","large_portfolio"]`
  - `OwnerAxis(value: OwnerType, legal_forms: list[Kind] = [], parts: list[OwnerType] = [], reason: Literal["owners_differ","public_land_private_leasehold"] | None = None, basis: list[Basis], inferred: bool)`
  - `MarketAxis(value: Literal["non_market","market","unknown"], basis: list[Basis], inferred: bool)`
  - `OperatorAxis(value: OwnerType, basis: list[Basis])`
  - `Classification(owner: OwnerAxis, market: MarketAxis, operator: OperatorAxis | None, scale: Scale | None)`
  - `Party.kind: Kind | None = None`, `Party.institutional: Institutional | None = None`
- Produces (sector.py):
  - `OWNER_TYPE_OF_KIND: dict[str, str]`
  - `@dataclass(frozen=True) class BuildingFacts: city_owned: bool = False; coop_model: str | None = None; sro_owner_sector: str | None = None; sro_operator_sector: str | None = None; on_non_market_list: bool = False; network_buildings: int | None = None`
  - `@dataclass(frozen=True) class ScaleThresholds: small_portfolio_min: int = 2; large_portfolio_min: int = 10`
  - `scale_for(n: int | None, t: ScaleThresholds) -> str | None`
  - `classify_building(parties: Sequence[Party], classify: Callable[[str], EntityClass], facts: BuildingFacts, thresholds: ScaleThresholds = ScaleThresholds()) -> Classification`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_classification_rules.py`)

```python
from tc_core.contract import Party, Source
from tc_core.metrics.sector import BuildingFacts, ScaleThresholds, classify_building, scale_for


def _p(role, name, source, **kw):
    return Party(role=role, name=name, entity_key=sanitize_owner(name), sources=[Source(type=source)], **kw)


CLASSIFY = EntityClassifier()


def test_registry_numbered_company_is_private_market_inferred():
    c = classify_building([_p("owner", "0792203 BC Ltd", "registry")], CLASSIFY, BuildingFacts())
    assert c.owner.value == "private" and c.owner.legal_forms == ["numbered_company"]
    assert c.owner.inferred is False and c.owner.basis == ["registry", "name_rule"]
    assert (c.market.value, c.market.inferred) == ("market", True)


def test_owners_of_different_types_are_mixed():
    parties = [_p("owner", "New Chelsea Society", "registry"), _p("owner", "0792203 BC Ltd", "registry")]
    c = classify_building(parties, CLASSIFY, BuildingFacts())
    assert (c.owner.value, c.owner.reason) == ("mixed", "owners_differ")
    assert c.owner.parts == ["non_profit", "private"] and c.owner.legal_forms == ["numbered_company"]


def test_city_land_under_private_leasehold_is_mixed():
    c = classify_building([_p("owner", "VLC Leaseholds Ltd", "registry")], CLASSIFY, BuildingFacts(city_owned=True))
    assert (c.owner.value, c.owner.reason) == ("mixed", "public_land_private_leasehold")
    assert c.owner.parts == ["government", "private"] and "city_owned" in c.owner.basis


def test_city_owned_without_registry_owner_is_government_non_market():
    c = classify_building([], CLASSIFY, BuildingFacts(city_owned=True))
    assert (c.owner.value, c.owner.inferred, c.owner.basis) == ("government", False, ["city_owned"])
    assert (c.market.value, c.market.inferred) == ("non_market", False)


def test_licence_only_owner_is_inferred():
    parties = [_p("owner", "Willow Lane Apartments Inc", "licence"),
               _p("licensee", "Willow Lane Apartments Inc", "licence", same_as="owner")]
    c = classify_building(parties, CLASSIFY, BuildingFacts())
    assert (c.owner.value, c.owner.inferred, c.owner.basis) == ("private", True, ["licence", "name_rule"])


def test_non_profit_coop_is_coop_and_non_market():
    c = classify_building([], CLASSIFY, BuildingFacts(coop_model="non_profit"))
    assert (c.owner.value, c.owner.inferred) == ("coop", True)
    assert (c.market.value, c.market.inferred, c.market.basis) == ("non_market", False, ["chf_bc"])


def test_equity_coop_is_market_inferred():
    c = classify_building([], CLASSIFY, BuildingFacts(coop_model="equity"))
    assert (c.market.value, c.market.inferred) == ("market", True)


def test_non_market_list_beats_private_owner_for_market():
    c = classify_building([_p("owner", "0792203 BC Ltd", "registry")], CLASSIFY,
                          BuildingFacts(on_non_market_list=True))
    assert (c.market.value, c.market.inferred, c.market.basis) == ("non_market", False, ["non_market_list"])


def test_sro_with_non_profit_operator_is_non_market_inferred():
    c = classify_building([_p("owner", "Hotel Holdings Ltd", "sro_inventory")], CLASSIFY,
                          BuildingFacts(sro_owner_sector="private", sro_operator_sector="non_profit"))
    assert (c.owner.value, c.owner.inferred) == ("private", True)
    assert (c.market.value, c.market.inferred, c.market.basis) == ("non_market", True, ["sro_inventory"])


def test_operator_from_manager_then_unlinked_licensee():
    parties = [_p("owner", "0792203 BC Ltd", "registry"), _p("manager", "Atira Women's Resource Society", "listing")]
    assert classify_building(parties, CLASSIFY, BuildingFacts()).operator.value == "non_profit"
    parties = [_p("owner", "0792203 BC Ltd", "registry"),
               _p("licensee", "Urban Vision Housing Society", "licence")]
    op = classify_building(parties, CLASSIFY, BuildingFacts()).operator
    assert (op.value, op.basis) == ("non_profit", ["licence"])


def test_nothing_known_is_unknown():
    c = classify_building([], CLASSIFY, BuildingFacts())
    assert (c.owner.value, c.market.value, c.operator, c.scale) == ("unknown", "unknown", None, None)
    assert c.owner.basis == [] and c.market.basis == []


@pytest.mark.parametrize("n, scale", [(None, None), (1, "single"), (2, "small_portfolio"),
                                      (9, "small_portfolio"), (10, "large_portfolio")])
def test_scale_thresholds(n, scale):
    assert scale_for(n, ScaleThresholds()) == scale
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_classification_rules.py -v`
Expected: FAIL with `ImportError: cannot import name 'BuildingFacts'`

- [ ] **Step 3: Add the contract models**

In `contract.py`, after `Sector = ...`:

```python
Kind = Literal[
    "government", "non_profit", "coop", "individual", "company",
    "numbered_company", "trust", "partnership", "unknown",
]
Institutional = Literal["reit", "pension_fund", "insurer", "asset_manager", "other"]
OwnerType = Literal["government", "non_profit", "coop", "private", "mixed", "unknown"]
# Where a classification came from. Claims show only as their bucket.
Basis = Literal[
    "name_rule", "registry", "licence", "listing", "city_owned", "non_market_list",
    "chf_bc", "sro_inventory", "claim_registry", "claim_city_records", "vtu_research",
]
Scale = Literal["single", "small_portfolio", "large_portfolio"]
```

Replace `kind: None = None  # reserved for the sector project` in `Party` with:

```python
    kind: Kind | None = None
    institutional: Institutional | None = None
```

After `class Rezoning`:

```python
class OwnerAxis(_Model):
    value: OwnerType
    legal_forms: list[Kind] = []  # the private owners' kinds
    parts: list[OwnerType] = []  # when mixed
    reason: Literal["owners_differ", "public_land_private_leasehold"] | None = None
    basis: list[Basis]
    # True when the owner is not confirmed on title, a claim or the City's
    # own land list (licence holder, SRO inventory, co-op or non-market list).
    inferred: bool


class MarketAxis(_Model):
    value: Literal["non_market", "market", "unknown"]
    basis: list[Basis]
    inferred: bool


class OperatorAxis(_Model):
    value: OwnerType
    basis: list[Basis]


class Classification(_Model):
    owner: OwnerAxis
    market: MarketAxis
    operator: OperatorAxis | None
    scale: Scale | None
```

- [ ] **Step 4: Append the building half to `sector.py`**

Add imports at the top: `from collections.abc import Callable, Mapping, Sequence` and `from ..contract import Classification, MarketAxis, OperatorAxis, OwnerAxis, Party`.

```python
OWNER_TYPE_OF_KIND = {
    "government": "government", "non_profit": "non_profit", "coop": "coop",
    "individual": "private", "company": "private", "numbered_company": "private",
    "trust": "private", "partnership": "private", "unknown": "unknown",
}
_SECTOR_OWNER_TYPE = {"private": "private", "non_profit": "non_profit",
                      "government": "government", "chinese_society": "non_profit"}
# Owner sources that confirm who holds title (spec 2026-10-20, refinement 3).
_CONFIRMED_SOURCES = {"registry"}


@dataclass(frozen=True)
class BuildingFacts:
    city_owned: bool = False
    coop_model: str | None = None  # Coop.ownership_model
    sro_owner_sector: str | None = None
    sro_operator_sector: str | None = None
    on_non_market_list: bool = False
    network_buildings: int | None = None


@dataclass(frozen=True)
class ScaleThresholds:
    small_portfolio_min: int = 2
    large_portfolio_min: int = 10


def scale_for(n: int | None, t: ScaleThresholds) -> str | None:
    if not n:
        return None
    if n >= t.large_portfolio_min:
        return "large_portfolio"
    return "small_portfolio" if n >= t.small_portfolio_min else "single"


def _unique(items) -> list:
    return list(dict.fromkeys(i for i in items if i))


def _owner_axis(parties: Sequence[Party], classify: Callable[[str], EntityClass], facts: BuildingFacts) -> OwnerAxis:
    owners = [p for p in parties if p.role == "owner"]
    on_title = [p for p in owners if p.sources[0].type in _CONFIRMED_SOURCES]
    if on_title:
        classes = [classify(p.name) for p in on_title]
        types = _unique(OWNER_TYPE_OF_KIND[c.kind] for c in classes)
        known = [t for t in types if t != "unknown"]
        forms = sorted({c.kind for c in classes if OWNER_TYPE_OF_KIND[c.kind] == "private"})
        basis = _unique(["registry", *(c.basis for c in classes)])
        if facts.city_owned and known and set(known) - {"government"}:
            parts = sorted({"government", *known})
            return OwnerAxis(value="mixed", legal_forms=forms, parts=parts,
                             reason="public_land_private_leasehold",
                             basis=_unique([*basis, "city_owned"]), inferred=False)
        if len(known) > 1:
            return OwnerAxis(value="mixed", legal_forms=forms, parts=sorted(known),
                             reason="owners_differ", basis=basis, inferred=False)
        if known:
            return OwnerAxis(value=known[0], legal_forms=forms, basis=basis, inferred=False)
    if facts.city_owned:
        return OwnerAxis(value="government", basis=["city_owned"], inferred=False)
    if facts.coop_model == "non_profit":
        return OwnerAxis(value="coop", basis=["chf_bc"], inferred=True)
    sro_owner = next((p for p in owners if p.sources[0].type == "sro_inventory"), None)
    if sro_owner or facts.sro_owner_sector:
        kind = classify(sro_owner.name) if sro_owner else None
        value = (OWNER_TYPE_OF_KIND[kind.kind] if kind and kind.kind != "unknown"
                 else _SECTOR_OWNER_TYPE.get(facts.sro_owner_sector or "", "unknown"))
        if value != "unknown":
            forms = [kind.kind] if kind and value == "private" and kind.kind != "unknown" else []
            return OwnerAxis(value=value, legal_forms=forms, basis=["sro_inventory"], inferred=True)
    if facts.on_non_market_list:
        operator = next((p for p in parties if p.role in ("manager", "licensee")), None)
        value = OWNER_TYPE_OF_KIND[classify(operator.name).kind] if operator else "unknown"
        if value in ("non_profit", "coop", "government"):
            return OwnerAxis(value=value, basis=["non_market_list"], inferred=True)
    licensed = next((p for p in owners if p.sources[0].type == "licence"), None) or next(
        (p for p in parties if p.role == "licensee"), None)
    if licensed:
        c = classify(licensed.name)
        value = OWNER_TYPE_OF_KIND[c.kind]
        if value != "unknown":
            forms = [c.kind] if value == "private" else []
            return OwnerAxis(value=value, legal_forms=forms, basis=_unique(["licence", c.basis]), inferred=True)
    return OwnerAxis(value="unknown", basis=[], inferred=False)


def _market_axis(owner: OwnerAxis, facts: BuildingFacts) -> MarketAxis:
    if facts.on_non_market_list:
        return MarketAxis(value="non_market", basis=["non_market_list"], inferred=False)
    if facts.coop_model == "non_profit":
        return MarketAxis(value="non_market", basis=["chf_bc"], inferred=False)
    if owner.value == "government" and not owner.inferred:
        return MarketAxis(value="non_market", basis=owner.basis, inferred=False)
    if {facts.sro_owner_sector, facts.sro_operator_sector} & {"non_profit", "government"}:
        return MarketAxis(value="non_market", basis=["sro_inventory"], inferred=True)
    if facts.coop_model == "equity":
        return MarketAxis(value="market", basis=["chf_bc"], inferred=True)
    if owner.value == "private":
        return MarketAxis(value="market", basis=owner.basis, inferred=True)
    return MarketAxis(value="unknown", basis=[], inferred=False)


def _operator_axis(parties: Sequence[Party], classify: Callable[[str], EntityClass]) -> OperatorAxis | None:
    operator = next((p for p in parties if p.role == "manager"), None) or next(
        (p for p in parties if p.role == "licensee" and p.same_as is None), None)
    if operator is None:
        return None
    value = OWNER_TYPE_OF_KIND[classify(operator.name).kind]
    if value == "unknown":
        return None
    return OperatorAxis(value=value, basis=_unique(s.type for s in operator.sources))


def classify_building(
    parties: Sequence[Party],
    classify: Callable[[str], EntityClass],
    facts: BuildingFacts,
    thresholds: ScaleThresholds = ScaleThresholds(),
) -> Classification:
    owner = _owner_axis(parties, classify, facts)
    return Classification(
        owner=owner,
        market=_market_axis(owner, facts),
        operator=_operator_axis(parties, classify),
        scale=scale_for(facts.network_buildings, thresholds),
    )
```

Note: `_operator_axis` puts `listing`, `licence` or `sro_inventory` in `basis`. All three are in `Basis`.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_classification_rules.py tests/test_contract.py -v`
Expected: all PASS. `test_contract.py` must still pass with `Party.kind` widened.

- [ ] **Step 6: Commit (ask first)**

```bash
git add src/tc_core/contract.py src/tc_core/metrics/sector.py tests/test_classification_rules.py
git commit -m "Classification: owner type, market status, operator and scale per building"
```

---

### Task 4: City-owned properties raw source

**Files:**
- Create: `src/tc_core/ingest/raw_city_owned.py`
- Modify: `src/tc_core/schema.sql` (new table after `raw_rezoning`, around line 164)
- Modify: `src/tc_core/config.py` (`IngestConfig` field + loader line)
- Modify: `src/tc_core/ingest/__init__.py` (`run_ingest`, after the `rezoning_applications` block around line 116)
- Modify: `config.toml` (`[paths]`)
- Modify: `src/tc_core/metrics/sector.py` (append `city_owned_buildings`)
- Test: `tests/test_city_owned.py` (create)

**Interfaces:**
- Produces:
  - table `raw_city_owned_properties(raw_city_owned_id INTEGER PRIMARY KEY, building_no TEXT, sap_address TEXT, geom TEXT, geo_local_area TEXT, land_coord TEXT, type TEXT, geo_point_2d TEXT, ingested_at TEXT NOT NULL)`
  - `ingest_raw_city_owned(conn, path: str) -> int`
  - `IngestConfig.city_owned_properties: str | None = None`
  - `sector.city_owned_buildings(conn) -> set[int]`: building_ids with any folio whose first 8 digits match a `land_coord`

- [ ] **Step 1: Write the failing test**

```python
"""City-owned land: buildings whose folio's land coordinate (its first 8
digits) is on the City's list (spec 2026-10-20)."""

from __future__ import annotations

from tc_core.db import get_connection, init_db
from tc_core.ingest.raw_city_owned import ingest_raw_city_owned
from tc_core.metrics.sector import city_owned_buildings


def test_buildings_on_city_land_are_found_by_land_coordinate(tmp_path):
    conn = get_connection(":memory:")
    init_db(conn)
    src = tmp_path / "city-owned-properties.csv"
    src.write_text(
        "﻿building_no;sap_address;geom;geo_local_area;land_coord;type;geo_point_2d\n"
        '1;1800 BEACH;"{}";West End;61210904;CAPITAL FUND;"49.2, -123.1"\n'
        '2;5900 BALACLAVA;"{}";Kerrisdale;05475575;VAHEF;"49.2, -123.1"\n',
        encoding="utf-8",
    )
    assert ingest_raw_city_owned(conn, str(src)) == 2
    conn.executemany(
        "INSERT INTO raw_buildings (raw_building_id, address, folio, ingested_at) VALUES (?, ?, ?, 'now')",
        [(1, "1800 beach ave", "612109040000"), (2, "5900 balaclava st", "054755750000;999999990000"),
         (3, "1 private st", "111111110000")],
    )
    conn.executemany(
        "INSERT INTO buildings (building_id, addr_key, address, source_row_ids, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'now', 'now')",
        [(10, "a", "a", "[1]"), (11, "b", "b", "[2]"), (12, "c", "c", "[3]")],
    )
    assert city_owned_buildings(conn) == {10, 11}
```

The leading-zero `land_coord` `05475575` must survive the read as text. If `read_any_csv` infers integers, pass string dtypes the way other raw loaders do (check `io.read_any_csv`'s signature) so it stays `05475575`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_city_owned.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tc_core.ingest.raw_city_owned'`

- [ ] **Step 3: Implement**

`schema.sql`, after `raw_rezoning`:

```sql
-- The City's own land (Open Data city-owned-properties): joins to buildings
-- on land_coord = a folio's first 8 digits. type is the holding fund
-- (CAPITAL FUND, PROPERTY ENDOWMENT FUND, VAHEF, Vancouver Public Housing Corp).
CREATE TABLE raw_city_owned_properties (
    raw_city_owned_id INTEGER PRIMARY KEY,
    building_no TEXT,
    sap_address TEXT,
    geom TEXT,
    geo_local_area TEXT,
    land_coord TEXT,
    type TEXT,
    geo_point_2d TEXT,
    ingested_at TEXT NOT NULL
);
```

`src/tc_core/ingest/raw_city_owned.py`:

```python
"""Ingest data/raw/cov_open_data/city-owned-properties.csv verbatim into
raw_city_owned_properties. Read by metrics/sector.py, which marks buildings
on City land (spec 2026-10-20)."""

from __future__ import annotations

import sqlite3

import polars as pl

from ..io import normalize_cols, read_any_csv
from .raw_table import conform_columns, insert_rows

RAW_CITY_OWNED_COLUMNS = [
    "building_no", "sap_address", "geom", "geo_local_area", "land_coord", "type", "geo_point_2d",
]


def load_raw_city_owned_frame(path: str) -> pl.DataFrame:
    df = conform_columns(
        normalize_cols(read_any_csv(path)),
        RAW_CITY_OWNED_COLUMNS,
        source="city-owned-properties.csv",
        table="raw_city_owned_properties",
        columns_name="RAW_CITY_OWNED_COLUMNS",
    )
    # Land coordinates are 8-digit keys with leading zeros.
    return df.with_columns(pl.col("land_coord").cast(pl.String).str.zfill(8))


def ingest_raw_city_owned(conn: sqlite3.Connection, path: str) -> int:
    return insert_rows(conn, "raw_city_owned_properties", load_raw_city_owned_frame(path))
```

`config.py`: add `city_owned_properties: str | None = None` to `IngestConfig` (beside `rezoning_applications`), and to `load_ingest_config`:

```python
        city_owned_properties=(
            str(flat["city_owned_properties"]) if flat.get("city_owned_properties") else None
        ),
```

`config.toml` `[paths]`: `city_owned_properties = "data/raw/cov_open_data/city-owned-properties.csv"`

`ingest/__init__.py`: import `from .raw_city_owned import ingest_raw_city_owned` and, after the rezoning block:

```python
    if config.city_owned_properties:
        counts["raw_city_owned_properties"] = run_source(
            conn, run_id, "raw_city_owned_properties", ingest_raw_city_owned, conn,
            config.city_owned_properties,
        )
```

`sector.py`, append:

```python
def city_owned_buildings(conn: sqlite3.Connection) -> set[int]:
    """building_ids with a folio on City land: a folio's first 8 digits are
    its land coordinate, the key of the City-owned properties list."""
    coords = {r[0] for r in conn.execute(
        "SELECT land_coord FROM raw_city_owned_properties WHERE land_coord IS NOT NULL")}
    found: set[int] = set()
    for building_id, folios in conn.execute(
        "SELECT b.building_id, r.folio FROM buildings b, json_each(b.source_row_ids) j "
        "JOIN raw_buildings r ON r.raw_building_id = j.value WHERE r.folio IS NOT NULL"
    ):
        if any(f.strip()[:8] in coords for f in folios.split(";")):
            found.add(building_id)
    return found
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_city_owned.py tests/test_rebuild_data.py tests/test_data_layout.py -v`
Expected: all PASS

- [ ] **Step 5: Document the source**

- `data/raw/cov_open_data/MANIFEST.md`: add a `city-owned-properties.csv` line in the existing format. It's now used by `ingest/raw_city_owned.py`.
- `docs/DATA_SOURCES.md`: add a `city-owned-properties` entry under Vancouver Open Data covering what it is, the `land_coord` join, the fund `type` values and counts (CAPITAL FUND 1,170; PROPERTY ENDOWMENT FUND 2,664; VAHEF 617; Vancouver Public Housing Corp 4), fetch method (same as the other Open Data files) and consumers (`metrics/sector.py::city_owned_buildings`).

- [ ] **Step 6: Commit (ask first)**

```bash
git add src/tc_core/ingest/raw_city_owned.py src/tc_core/schema.sql src/tc_core/config.py \
  src/tc_core/ingest/__init__.py config.toml src/tc_core/metrics/sector.py tests/test_city_owned.py \
  data/raw/cov_open_data/MANIFEST.md docs/DATA_SOURCES.md
git commit -m "Ingest the City-owned properties list; find buildings on City land"
```

---

### Task 5: Export: contract v5 wiring

**Files:**
- Modify: `src/tc_core/contract.py` (`NetworkEntity.kind` line 147, `NetworkTotals` lines 135–139, `Building` add `classification`, `SCHEMA_VERSION = 5`)
- Modify: `src/tc_core/export_parties.py` (`_party`, `build_parties`)
- Modify: `src/tc_core/export_contract.py` (`build_building`, `_network_entities`, `build_networks`; remove `_COMPANY_WORDS`, `_guess_kind`)
- Modify: `src/tc_core/export.py` (`export_artifacts` signature; `_contract_records`; add `city_owned` column)
- Modify: `src/tc_core/config.py` (`IngestConfig.classification: ScaleThresholds`), `config.toml` (`[classification]`)
- Modify: `scripts/rebuild_data.py` (pass thresholds)
- Modify: `tests/contract_helpers.py` and any test that builds `Party`/`NetworkEntity`/`Building` by hand with `kind="person"`
- Modify: `frontend/src/config.ts` (`EXPECTED_SCHEMA_VERSION = 5`), regenerate `frontend/src/contract.schema.json` and `frontend/src/contract.gen.ts`
- Test: `tests/test_export_ownership.py` (append)

**Interfaces:**
- Consumes: `EntityClassifier`, `classify_building`, `BuildingFacts`, `ScaleThresholds`, `city_owned_buildings` (Tasks 2–4)
- Produces:
  - `NetworkEntity.kind: Kind`; `NetworkTotals.assessed_value: Int | None`; `Building.classification: Classification`
  - `build_parties(row, clusters, classify: Callable[[str], EntityClass] | None = None) -> list[Party]`: sets `kind`/`institutional` when `classify` is given
  - `build_building(row, *, shares, clusters, classify, thresholds) -> Building`
  - `build_networks(rows, clusters=None, classify=None) -> dict[str, Network]` (the `kinds` parameter is replaced)
  - `export_artifacts(..., classification: ScaleThresholds = ScaleThresholds())`
  - points_df column `city_owned: bool`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_export_ownership.py`)

```python
from tc_core.claims import ENTITY_KIND, INSTITUTIONAL

KIND_CANARY = "CANARY-kind-91c2"


def _kind_claims(conn):
    record_claim(conn, "GLR PROPERTIES LTD.", "trust", ENTITY_KIND, "tenant_report",
                 confidence="confirmed", source_note=KIND_CANARY, reported_by="organizer-x")
    record_claim(conn, "GLR PROPERTIES LTD.", "reit", INSTITUTIONAL, "manual_research",
                 confidence="confirmed", source_note=KIND_CANARY)
    conn.commit()


def test_classification_claim_notes_and_reporters_never_reach_any_artifact(tmp_path):
    out = _export(tmp_path, extra=_kind_claims)
    text = _all_artifact_text(out)
    assert KIND_CANARY not in text and "organizer-x" not in text


def test_claimed_kind_reaches_parties_with_a_bucketed_basis(tmp_path):
    out = _export(tmp_path, extra=_kind_claims)
    recs = records(out)
    glr = next(p for r in recs.values() for p in r["parties"] if p["name"] == "GLR PROPERTIES LTD.")
    assert (glr["kind"], glr["institutional"]) == ("trust", "reit")
    building = next(r for r in recs.values() if any(p["name"] == "GLR PROPERTIES LTD." for p in r["parties"]))
    assert "vtu_research" in building["classification"]["owner"]["basis"]
    assert "tenant_report" not in json.dumps(building)


def test_every_building_is_classified_and_networks_use_the_new_kinds(tmp_path):
    out = _export(tmp_path)
    for r in records(out).values():
        assert r["classification"]["owner"]["value"] in (
            "government", "non_profit", "coop", "private", "mixed", "unknown")
    kinds = {e["kind"] for n in networks(out).values() for e in n["entities"]}
    assert kinds <= {"government", "non_profit", "coop", "individual", "company",
                     "numbered_company", "trust", "partnership", "unknown"}
    assert all("assessed_value" in n["totals"] for n in networks(out).values())


def test_unknown_basis_fails_the_export():
    import pytest
    from pydantic import ValidationError
    from tc_core.contract import MarketAxis
    with pytest.raises(ValidationError):
        MarketAxis(value="market", basis=["tenant_report"], inferred=True)
```

Check `contract_helpers.records()` / `networks()` return dicts keyed by id (they're used that way in the existing tests). If `records()` returns a list, use it as one.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_export_ownership.py -v`
Expected: the new tests FAIL (`KeyError: 'classification'` / `'kind'`). Existing tests still PASS.

- [ ] **Step 3: Contract changes**

`contract.py`: `SCHEMA_VERSION = 5`. In `NetworkTotals` add `assessed_value: Int | None` after `units`. In `NetworkEntity` set `kind: Kind`. In `Building` add `classification: Classification` after `rezoning`. Move the classification models above `Building` if they aren't already.

- [ ] **Step 4: Parties carry kinds**

`export_parties.py`: add `from collections.abc import Callable, Mapping` and `from .metrics.sector import EntityClass`. Give `build_parties` the parameter `classify: Callable[[str], EntityClass] | None = None`. At its end, before `return parties`:

```python
    if classify is not None:
        for p in parties:
            c = classify(p.name)
            p.kind = None if c.kind == "unknown" else c.kind
            p.institutional = c.institutional
```

(`Party` is a Pydantic model and not frozen, so attribute assignment validates against `Kind`. If `_Model` sets `validate_assignment=False`, assignment still works; the final `Building` validation happens at JSON dump through `BuildingRecordsFile`.)

- [ ] **Step 5: Buildings get a classification**

`export_contract.py`, imports: `from .metrics.sector import BuildingFacts, EntityClassifier, ScaleThresholds, classify_building`.

```python
def _facts(row: Mapping[str, object], coop: Coop | None, sro: Sro | None, listed_in: list[str]) -> BuildingFacts:
    return BuildingFacts(
        city_owned=bool(row.get("city_owned")),
        coop_model=coop.ownership_model if coop else None,
        sro_owner_sector=sro.owner_sector if sro else None,
        sro_operator_sector=sro.operator_sector if sro else None,
        on_non_market_list="non_market_list" in listed_in,
        network_buildings=_int(row.get("network_buildings_on_map")),
    )


def build_building(
    row: Mapping[str, object], *, shares: LandShares, clusters: Mapping[str, str],
    classify: EntityClassifier | None = None, thresholds: ScaleThresholds = ScaleThresholds(),
) -> Building:
    classify = classify or EntityClassifier()
    parties = build_parties(row, clusters, classify)
    listed_in, coop, sro = _listed_in(row), _coop(row), _sro(row)
    return Building(
        ...  # every existing field unchanged, except:
        listed_in=listed_in,
        parties=parties,
        coop=coop,
        sro=sro,
        classification=classify_building(parties, classify, _facts(row, coop, sro, listed_in), thresholds),
    )
```

Keep every other `Building(...)` argument exactly as it is now. If `network_buildings_on_map` is empty for buildings whose network is a licence-name group, use the network's member count instead: compute `{network_key: count}` in `_contract_records` and put it in the row as `network_buildings_on_map` before `build_building`.

- [ ] **Step 6: Networks use the new kinds and total assessed value**

In `export_contract.py`, delete `_COMPANY_WORDS` and `_guess_kind`. Change `_network_entities(names, members, clusters, classify)`:

```python
        kind = classify(name).kind
        entities.append(NetworkEntity(
            name=name, also_named=sorted(n for n in spellings if n != name), kind=kind, buildings=owned[key],
        ))
    return sorted(entities, key=lambda e: (e.kind != "individual", -e.buildings, e.name))
```

`build_networks(rows, clusters=None, classify=None)`: `classify = classify or EntityClassifier()`, pass it to `_network_entities`, and in `NetworkTotals` add:

```python
                assessed_value=_assessed_total(members),
```

with

```python
def _assessed_total(members: list[Mapping[str, object]]) -> int | None:
    """Land + building assessed value of the network's buildings on the map;
    null when none has a value. A lower bound on the landlord's holdings."""
    values = [(_num(r.get("value_land")) or 0) + (_num(r.get("value_bldg")) or 0)
              for r in members if _num(r.get("value_land")) is not None or _num(r.get("value_bldg")) is not None]
    return int(round(sum(values))) if values else None
```

The registry person/company distinction from `registry_owners.entity_kinds()` is now covered by `EntityClassifier`'s registry lookup. Remove the `kinds=entity_kinds(conn)` argument in `export.py`, and delete `entity_kinds` from `registry_owners.py` if nothing else imports it (`grep -rn entity_kinds src tests scripts`).

- [ ] **Step 7: Export wiring**

`export.py`:
- imports: `from .metrics.sector import EntityClassifier, ScaleThresholds, city_owned_buildings`
- `export_artifacts(..., classification: ScaleThresholds = ScaleThresholds())`
- after `points_df = reconstruct_points(...)`:

```python
    on_city_land = city_owned_buildings(conn)
    points_df = points_df.with_columns(
        city_owned=pl.col("b_id").cast(pl.Int64).is_in(list(on_city_land))
        & (pl.col("source") == "building")
    )
```

(`b_id` is the `buildings.building_id` for `source == "building"` rows. Confirm in `reconstruct_points` before relying on it; if `b_id` is renumbered, join on `addr_key` instead.)
- `_contract_records(conn, points_df, classification)`: build `classify = EntityClassifier.from_conn(conn)` once and pass `classify=classify, thresholds=classification` to `build_building` and `classify=classify` to `build_networks`.

`config.py`: `from .metrics.sector import ScaleThresholds`. Add `classification: ScaleThresholds = field(default_factory=ScaleThresholds)` to `IngestConfig`, and in the loader:

```python
        classification=ScaleThresholds(**raw.get("classification", {})),
```

`config.toml`:

```toml
[classification]
# Network size in buildings on the map (spec 2026-10-20).
small_portfolio_min = 2
large_portfolio_min = 10
```

`scripts/rebuild_data.py`: pass `classification=config.classification` to `export_artifacts`.

- [ ] **Step 8: Fix fixtures and helpers**

Run: `grep -rn "kind=\"person\"\|kind=\"company\"\|'person'\|\"person\"" tests src`. Change `person` → `individual`. Where a test builds `Building(...)` directly, add a `classification` (import `Classification, OwnerAxis, MarketAxis` and use `Classification(owner=OwnerAxis(value="unknown", basis=[], inferred=False), market=MarketAxis(value="unknown", basis=[], inferred=False), operator=None, scale=None)`, ideally via one helper in `tests/contract_helpers.py` named `unknown_classification()`).

- [ ] **Step 9: Regenerate the frontend contract**

Run:

```bash
uv run python scripts/write_contract_schema.py
cd frontend && npm run gen:types
```

Set `EXPECTED_SCHEMA_VERSION = 5` in `frontend/src/config.ts`. Update `frontend/src/popup/fixtures.ts`: entity `kind: 'person'` → `'individual'` and `'company'` stays; add `classification` to fixture buildings (owner unknown as above) and `assessed_value: null` to fixture network totals.

- [ ] **Step 10: Run all tests**

Run: `uv run pytest -q && cd frontend && npm run typecheck && npm test`
Expected: Python all PASS. Frontend typecheck fails only in `popup/ownership.ts` on `'person'` / `'company'` comparisons (fixed in Task 10). To keep this task green, change those two comparisons to `'individual'` and `e.kind !== 'individual'` now; Task 10 replaces the grouping.

- [ ] **Step 11: Commit (ask first)**

```bash
git add src/tc_core tests config.toml scripts/rebuild_data.py frontend/src/config.ts \
  frontend/src/contract.schema.json frontend/src/contract.gen.ts frontend/src/popup
git commit -m "Contract v5: party kinds, building classification, network assessed value"
```

---

### Task 6: Portfolio slider summaries in `filter_config.json`

**Files:**
- Modify: `src/tc_core/metrics/building_metrics.py` (`BUILDING_METRICS`)
- Modify: `src/tc_core/export.py` (`export_artifacts`: add `portfolio_units`, `portfolio_value` columns before `reconstruct_filter_config`)
- Test: `tests/test_export_artifacts.py` (append)

**Interfaces:**
- Produces: `filter_config.building_metrics.portfolio_units` / `.portfolio_value` with `attr` `portfolio-units` / `portfolio-value`, listed in `building_metric_order` after the existing metrics.

- [ ] **Step 1: Write the failing test**

Follow the existing export fixture in `tests/test_export_artifacts.py` (use its seeding helper; read the file's top to find it). Then:

```python
def test_filter_config_summarises_portfolio_size(tmp_path):
    out = _export(tmp_path)  # the file's existing export helper
    cfg = json.loads((out / "filter_config.json").read_text())
    for key, attr in (("portfolio_units", "portfolio-units"), ("portfolio_value", "portfolio-value")):
        assert cfg["building_metrics"][key]["attr"] == attr
        assert key in cfg["building_metric_order"]
```

If that file has no export helper, put the test in `tests/test_export_ownership.py` and use its `_export`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_export_artifacts.py -k portfolio -v`
Expected: FAIL with `KeyError: 'portfolio_units'`

- [ ] **Step 3: Implement**

`BUILDING_METRICS`, append:

```python
    # A building's landlord network on the map (spec 2026-10-20): lower
    # bounds, since only rental buildings on this map count.
    "portfolio_units": {
        "label": "Landlord's units on the map",
        "format": "number",
        "type": "int",
        "step": 1,
        "attr": "portfolio-units",
        "bins": 18,
        "force_log": True,
        "log_floor": 2.5,
    },
    "portfolio_value": {
        "label": "Landlord's assessed value on the map",
        "format": "currency",
        "unit": "$",
        "type": "float",
        "step": 5000,
        "attr": "portfolio-value",
        "bins": 24,
        "log_floor": 100000,
    },
```

`export.py`, in `export_artifacts` before `reconstruct_filter_config`:

```python
    # Same totals as networks.json's NetworkTotals (units, assessed_value),
    # per building, for the portfolio sliders' histograms.
    value = pl.col("value_land").fill_null(0) + pl.col("value_bldg").fill_null(0)
    has_value = pl.col("value_land").is_not_null() | pl.col("value_bldg").is_not_null()
    points_df = points_df.with_columns(
        portfolio_units=pl.when(pl.col("network_key").is_not_null())
        .then(pl.col("units").fill_null(0).sum().over("network_key")),
        portfolio_value=pl.when(pl.col("network_key").is_not_null() & has_value.any().over("network_key"))
        .then(pl.when(has_value).then(value).otherwise(0).sum().over("network_key")),
    )
```

(The frontend computes the same from `networks.json`, refinement 4. These columns feed only the histograms.)

- [ ] **Step 4: Run tests**

Run: `uv run pytest -q`
Expected: all PASS

- [ ] **Step 5: Commit (ask first)**

```bash
git add src/tc_core/metrics/building_metrics.py src/tc_core/export.py tests/test_export_artifacts.py
git commit -m "Filter config: landlord portfolio units and assessed value summaries"
```

---

### Task 7: Classification report and research CSVs

**Files:**
- Create: `scripts/classification_report.py`
- Modify: `data/README.md` (one line on `derived/classification/`)

**Interfaces:**
- Consumes: `data/derived/artifacts/building_records.json` (contract v5)
- Produces: `data/derived/classification/buildings.csv` (b_id, address, local_area, units, owner_type, owner_legal_forms, owner_parts, owner_reason, owner_basis, owner_inferred, market, market_basis, market_inferred, operator_type, scale, network_id); `data/derived/classification/entities.csv` (name, entity_key, role, kind, institutional, buildings); a printed report

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Building classification: research CSVs and an eyeball report (spec 2026-10-20).

Reads the exported building_records.json, so it sees exactly what the map
publishes. Writes data/derived/classification/{buildings,entities}.csv and
prints counts per axis, the most common name-rule kinds to spot-check, every
mixed building, and owners whose kind differs from the licence holder's.

Usage: uv run python scripts/classification_report.py [--config config.toml]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.config import load_ingest_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    args = parser.parse_args()
    config = load_ingest_config(args.config)
    records = json.loads((Path(config.artifacts) / "building_records.json").read_text())["records"]

    rows, entities = [], Counter()
    for r in records.values():
        c = r["classification"]
        op = c["operator"]
        rows.append({
            "b_id": r["id"], "address": r["address"], "local_area": r["local_area"], "units": r["units"],
            "owner_type": c["owner"]["value"], "owner_legal_forms": ";".join(c["owner"]["legal_forms"]),
            "owner_parts": ";".join(c["owner"]["parts"]), "owner_reason": c["owner"]["reason"],
            "owner_basis": ";".join(c["owner"]["basis"]), "owner_inferred": c["owner"]["inferred"],
            "market": c["market"]["value"], "market_basis": ";".join(c["market"]["basis"]),
            "market_inferred": c["market"]["inferred"], "operator_type": op["value"] if op else None,
            "scale": c["scale"], "network_id": r["network_id"],
        })
        for p in r["parties"]:
            entities[(p["name"], p["entity_key"], p["role"], p["kind"], p["institutional"])] += 1

    out = Path(config.artifacts).parent / "classification"
    out.mkdir(parents=True, exist_ok=True)
    buildings = pl.DataFrame(rows)
    buildings.write_csv(out / "buildings.csv")
    pl.DataFrame(
        [{"name": n, "entity_key": k, "role": role, "kind": kind, "institutional": inst, "buildings": count}
         for (n, k, role, kind, inst), count in entities.items()]
    ).sort("buildings", descending=True).write_csv(out / "entities.csv")

    for axis in ("owner_type", "owner_inferred", "market", "market_inferred", "operator_type", "scale"):
        print(f"\n{axis}:")
        print(buildings.group_by(axis).agg(buildings=pl.len(), units=pl.col("units").sum())
              .sort("buildings", descending=True))
    print("\nMixed buildings:")
    print(buildings.filter(pl.col("owner_type") == "mixed").select("address", "owner_parts", "owner_reason"))
    print("\nMost common owner kinds from name rules (spot-check these):")
    name_rule = [(n, kind) for (n, _, role, kind, _), _c in entities.most_common()
                 if role == "owner" and kind is not None]
    for name, kind in name_rule[:50]:
        print(f"  {kind:17} {name}")
    print("\nOwner vs licence holder kind disagreements:")
    for r in records.values():
        owners = {p["kind"] for p in r["parties"] if p["role"] == "owner" and p["kind"]}
        lic = next((p for p in r["parties"] if p["role"] == "licensee" and p["same_as"] is None), None)
        if owners and lic and lic["kind"] and lic["kind"] not in owners:
            print(f"  {r['address']}: owner {sorted(owners)} vs licensee {lic['name']} ({lic['kind']})")
    print(f"\nWrote {out / 'buildings.csv'} and {out / 'entities.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it against a fresh export**

Run: `uv run python scripts/rebuild_data.py && uv run python scripts/classification_report.py`
Expected: the report prints. `owner_type` counts should be roughly: government ≥ 200 (the 226 City-land buildings plus BC Housing), private in the thousands, unknown well under the earlier 2,330 thanks to the licence fallback. Read the name-rule list and fix any wrong rule in `sector.py` with a new parametrized case in `tests/test_classification_rules.py` first (TDD).

- [ ] **Step 3: Document the output**

`data/README.md`, under derived: `classification/: buildings.csv and entities.csv from scripts/classification_report.py, for research queries (spec 2026-10-20). Not public.`

- [ ] **Step 4: Commit (ask first)**

```bash
git add scripts/classification_report.py data/README.md
git commit -m "Classification report and research CSVs"
```

---

### Task 8: Frontend: flat fields and filter logic

**Files:**
- Modify: `frontend/src/types.ts` (`BuildingRecord` gains the fields below)
- Modify: `frontend/src/flat.ts` (`FLAT_COLUMNS`, `flatten`)
- Modify: `frontend/src/tables.ts` (`FilterFields`, `filterFields`)
- Modify: `frontend/src/wiring/filter-state.ts` (`FilterState`, defaults, `clearSection`, `sectionCounts`)
- Modify: `frontend/src/wiring/filter.ts` (`baseMatches`)
- Test: `frontend/src/wiring/filter.test.ts`, `frontend/src/flat.test.ts` (append)

**Interfaces:**
- Produces:
  - `BuildingRecord`: `owner_type: string | null`, `owner_parts: string[]`, `owner_legal_forms: string[]`, `owner_inferred: boolean`, `market: string | null`, `market_inferred: boolean`, `portfolio_units: number | null`, `portfolio_value: number | null`
  - `FilterFields`: `ownerTypes: string[]` (the value, or its parts when mixed), `legalForms: string[]`, `ownerInferred: boolean`, `market: string`, `marketInferred: boolean`; `metrics['portfolio-units']`, `metrics['portfolio-value']`
  - `FilterState`: `ownerTypes: string[]`, `legalForms: string[]`, `market: string[]`, `includeInferred: boolean` (default `true`)
  - `FilterSection` gains `'portfolio'`; `MetricSection` (metric-controls.ts) gains `'portfolio'` (Task 9 renders it)

- [ ] **Step 1: Write the failing tests**

In `frontend/src/wiring/filter.test.ts`, following the file's existing helpers for building `FilterFields` and `FilterState` (read its top; reuse its field factory and add defaults `ownerTypes: [], legalForms: [], ownerInferred: false, market: 'unknown', marketInferred: false`):

```ts
describe('classification filters', () => {
  const pass = (f: Partial<FilterFields>, s: Partial<FilterState>) =>
    filterBuildings([fields(f)], { ...defaultFilterState(), ...s }, []).visible.size === 1;

  it('mixed matches any of its parts', () => {
    expect(pass({ ownerTypes: ['non_profit', 'private'] }, { ownerTypes: ['private'] })).toBe(true);
    expect(pass({ ownerTypes: ['non_profit', 'private'] }, { ownerTypes: ['government'] })).toBe(false);
  });

  it('unknown building passes only when no type is ticked', () => {
    expect(pass({ ownerTypes: [] }, {})).toBe(true);
    expect(pass({ ownerTypes: [] }, { ownerTypes: ['private'] })).toBe(false);
  });

  it('legal form narrows private owners', () => {
    expect(pass({ ownerTypes: ['private'], legalForms: ['numbered_company'] },
      { ownerTypes: ['private'], legalForms: ['numbered_company'] })).toBe(true);
    expect(pass({ ownerTypes: ['private'], legalForms: ['company'] },
      { ownerTypes: ['private'], legalForms: ['numbered_company'] })).toBe(false);
  });

  it('include inferred off drops inferred owner types and market values', () => {
    expect(pass({ ownerTypes: ['private'], ownerInferred: true }, { ownerTypes: ['private'], includeInferred: false })).toBe(false);
    expect(pass({ market: 'market', marketInferred: true }, { market: ['market'], includeInferred: false })).toBe(false);
    expect(pass({ market: 'non_market', marketInferred: false }, { market: ['non_market'], includeInferred: false })).toBe(true);
  });
});
```

In `frontend/src/flat.test.ts`, following its fixture pattern:

```ts
it('flattens classification and portfolio totals', () => {
  const b = { ...building, network_id: 'n1', classification: {
    owner: { value: 'mixed', legal_forms: ['numbered_company'], parts: ['non_profit', 'private'], reason: 'owners_differ', basis: ['registry'], inferred: false },
    market: { value: 'market', basis: ['registry'], inferred: true }, operator: null, scale: 'small_portfolio' } };
  const r = flatten(b, { n1: { ...network, totals: { ...network.totals, units: 40, assessed_value: 12_000_000 } } });
  expect([r.owner_type, r.owner_parts, r.owner_legal_forms, r.market, r.market_inferred]).toEqual(
    ['mixed', ['non_profit', 'private'], ['numbered_company'], 'market', true]);
  expect([r.portfolio_units, r.portfolio_value]).toEqual([40, 12_000_000]);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/wiring/filter.test.ts src/flat.test.ts`
Expected: FAIL (type errors / undefined fields)

- [ ] **Step 3: Implement**

`flat.ts`: add `'owner_type', 'owner_legal_forms', 'market', 'portfolio_units', 'portfolio_value'` to `FLAT_COLUMNS` (after `land_share_pctl`). In `flatten`:

```ts
    owner_type: b.classification.owner.value === 'unknown' ? null : b.classification.owner.value,
    owner_parts: b.classification.owner.parts,
    owner_legal_forms: b.classification.owner.legal_forms,
    owner_inferred: b.classification.owner.inferred,
    market: b.classification.market.value === 'unknown' ? null : b.classification.market.value,
    market_inferred: b.classification.market.inferred,
    portfolio_units: net?.totals.units ?? null,
    portfolio_value: net?.totals.assessed_value ?? null,
```

`types.ts` `BuildingRecord`: add the eight fields with the types listed under Interfaces.

`tables.ts` `FilterFields` and `filterFields(r)`:

```ts
    ownerTypes: r.owner_type === 'mixed' ? [...(r.owner_parts ?? [])] : r.owner_type ? [r.owner_type] : [],
    legalForms: [...(r.owner_legal_forms ?? [])],
    ownerInferred: !!r.owner_inferred,
    market: r.market ?? 'unknown',
    marketInferred: !!r.market_inferred,
```

and in `metrics`:

```ts
      'portfolio-units': truncOrNull(r.portfolio_units),
      'portfolio-value': roundOrNull(r.portfolio_value),
```

`filter-state.ts`: extend `FilterState` with `ownerTypes`, `legalForms`, `market`, `includeInferred`; `defaultFilterState()` adds `ownerTypes: [], legalForms: [], market: [], includeInferred: true`; `FilterSection` adds `'portfolio'`; in `clearSection`, `'ownership'` also resets `ownerTypes: [], legalForms: [], market: [], includeInferred: true`, and `case 'portfolio': return { ...state, thresholds: withoutSection(state.thresholds, 'portfolio', metricSection) };`; `sectionCounts` adds `ownerTypes.length + legalForms.length + market.length + (includeInferred ? 0 : 1)` to ownership and a `portfolio` count from `active.portfolio` (extend the `active` record).

`filter.ts` `baseMatches`, before `return true`:

```ts
  if (s.ownerTypes.length > 0) {
    if (!s.includeInferred && f.ownerInferred) return false;
    if (!s.ownerTypes.some((t) => f.ownerTypes.includes(t))) return false;
  }
  if (s.legalForms.length > 0 && !s.legalForms.some((t) => f.legalForms.includes(t))) return false;
  if (s.market.length > 0) {
    if (!s.includeInferred && f.marketInferred) return false;
    if (!s.market.includes(f.market)) return false;
  }
```

- [ ] **Step 4: Run tests and typecheck**

Run: `cd frontend && npm run typecheck && npm test`
Expected: all PASS. Fix any existing test that constructs a full `FilterState` or `FilterFields` literal by adding the new defaults.

- [ ] **Step 5: Commit (ask first)**

```bash
git add frontend/src
git commit -m "Frontend: classification and portfolio fields in the filter pass"
```

---

### Task 9: Frontend: sidebar controls

**Files:**
- Modify: `frontend/index.html` (Ownership section around lines 1631–1643; new "Landlord portfolio" `<details>` section after it, modelled on `#filter-value-details` at line 1657)
- Modify: `frontend/src/wiring/filter-state.ts` (`FilterControls`, `findFilterControls`, `readFilterState`, `writeFilterState`)
- Modify: `frontend/src/wiring/metric-controls.ts` (portfolio section, lines 274–295)
- Modify: wherever housing chips get their click handlers and section-clear buttons are wired (`grep -rn "housingChips\|filter-clear-value" frontend/src/wiring`)
- Test: `frontend/src/wiring/filter-state.dom.test.ts` (append)

**Interfaces:**
- Consumes: `FilterState` fields from Task 8
- Produces: DOM: `.owner-type-chip[data-owner-type]` (government / non_profit / coop / private), `.legal-form-chip[data-legal-form]` (individual / company / numbered_company / trust / partnership), `.market-chip[data-market]` (non_market / market), `#filter-include-inferred` (checkbox, checked), `#filter-portfolio-section`, `#filter-count-portfolio`, `#filter-clear-portfolio`

- [ ] **Step 1: Write the failing DOM test**

Following the existing pattern in `filter-state.dom.test.ts` (it builds the sidebar HTML, calls `findFilterControls`, then `readFilterState` / `writeFilterState`):

```ts
it('round-trips the classification filters', () => {
  const c = findFilterControls(document, undefined, metrics);
  const state = { ...defaultFilterState(), ownerTypes: ['private'], legalForms: ['numbered_company'], market: ['market'], includeInferred: false };
  writeFilterState(c, state);
  expect(readFilterState(c)).toMatchObject({ ownerTypes: ['private'], legalForms: ['numbered_company'], market: ['market'], includeInferred: false });
});

it('legal form chips are disabled until Private is chosen', () => {
  const c = findFilterControls(document, undefined, metrics);
  writeFilterState(c, defaultFilterState());
  expect(c.legalFormChips.every((chip) => chip.hasAttribute('disabled'))).toBe(true);
  writeFilterState(c, { ...defaultFilterState(), ownerTypes: ['private'] });
  expect(c.legalFormChips.some((chip) => chip.hasAttribute('disabled'))).toBe(false);
});
```

Make sure the test's sidebar HTML is read from `index.html` (as the existing DOM tests do) so the new markup is exercised.

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/wiring/filter-state.dom.test.ts`
Expected: FAIL

- [ ] **Step 3: Markup**

In the Ownership section of `index.html`, after the "Landlord on record" checkbox, using the housing chips' classes:

```html
<div class="filter-subheading">Owner type <span class="provenance-hint" title="From the provincial registry, City records and VTU research; inferred types come from the rental licence holder or City housing lists.">ⓘ</span></div>
<div class="filter-chips">
  <button type="button" class="filter-chip owner-type-chip" data-owner-type="private" aria-pressed="false">Private</button>
  <button type="button" class="filter-chip owner-type-chip" data-owner-type="non_profit" aria-pressed="false">Non-profit</button>
  <button type="button" class="filter-chip owner-type-chip" data-owner-type="coop" aria-pressed="false">Co-op</button>
  <button type="button" class="filter-chip owner-type-chip" data-owner-type="government" aria-pressed="false">Public</button>
</div>
<div class="filter-chips">
  <button type="button" class="filter-chip legal-form-chip" data-legal-form="individual" aria-pressed="false" disabled>Individual</button>
  <button type="button" class="filter-chip legal-form-chip" data-legal-form="company" aria-pressed="false" disabled>Company</button>
  <button type="button" class="filter-chip legal-form-chip" data-legal-form="numbered_company" aria-pressed="false" disabled>Numbered company</button>
  <button type="button" class="filter-chip legal-form-chip" data-legal-form="trust" aria-pressed="false" disabled>Trust</button>
  <button type="button" class="filter-chip legal-form-chip" data-legal-form="partnership" aria-pressed="false" disabled>Partnership</button>
</div>
<div class="filter-subheading">Rents</div>
<div class="filter-chips">
  <button type="button" class="filter-chip market-chip" data-market="market" aria-pressed="false">Market</button>
  <button type="button" class="filter-chip market-chip" data-market="non_market" aria-pressed="false">Non-market</button>
</div>
<label><input type="checkbox" id="filter-include-inferred" checked> Include inferred</label>
```

Use whatever subheading class the sidebar already uses. If there's none, add `.filter-subheading` to the stylesheet next to `.filter-section h4` (smaller and muted). After the Assessed value `<details>`, copy that block with ids `filter-portfolio-details`, `filter-count-portfolio`, `filter-clear-portfolio`, heading "Landlord portfolio", an ⓘ reading "Their rental buildings on this map only — a lower bound", and an inner container `<div id="filter-portfolio-section"></div>`.

- [ ] **Step 4: Controls**

`filter-state.ts` `FilterControls` adds `ownerTypeChips`, `legalFormChips`, `marketChips: HTMLElement[]` and `includeInferred: HTMLInputElement | null`. `findFilterControls` queries them. `readFilterState` reads pressed chips the same way as `housing` (via `data-owner-type`, `data-legal-form`, `data-market`) and `includeInferred: c.includeInferred ? c.includeInferred.checked : true`. `writeFilterState` sets `aria-pressed` for each chip group and the checkbox, and toggles `disabled` on legal-form chips: disabled unless `state.ownerTypes.includes('private')`. When disabling, also set `aria-pressed="false"`.

Wire the click handlers: find where `housingChips` get their click listener (toggle `aria-pressed`, then the filter callback) and attach the same handler to the three new chip groups, plus `change` on `#filter-include-inferred`. After an owner-type chip click, re-run `writeFilterState(c, readFilterState(c))` so legal-form chips enable or disable and drop their selection. Wire `#filter-clear-portfolio` the way `#filter-clear-value` is wired, with section `'portfolio'`.

`metric-controls.ts`: `MetricSection = 'building' | 'value' | 'portfolio'`. Add

```ts
// Under the Landlord portfolio heading.
const PORTFOLIO_METRIC_LABELS: Record<string, string> = { portfolio_units: 'Units', portfolio_value: 'Assessed value' };
```

and, in the render loop, pick the section:

```ts
      const section: MetricSection = PORTFOLIO_METRIC_LABELS[metric] && portfolioContainer ? 'portfolio'
        : VALUE_METRIC_LABELS[metric] && valueContainer ? 'value' : 'building';
      const label = section === 'portfolio' ? PORTFOLIO_METRIC_LABELS[metric] : section === 'value' ? VALUE_METRIC_LABELS[metric] : undefined;
      const shown = label ? { ...summary, label } : summary;
      const container = section === 'portfolio' ? portfolioContainer : section === 'value' ? valueContainer : buildingContainer;
```

with `const portfolioContainer = doc.getElementById('filter-portfolio-section');` cleared alongside `valueContainer`.

- [ ] **Step 5: Run tests and typecheck**

Run: `cd frontend && npm run typecheck && npm test`
Expected: all PASS, including `wiring.characterization.test.ts`. If its snapshot covers the sidebar markup, update it only for the added controls.

- [ ] **Step 6: Look at it**

Run: `uv run dev`, open the map, and check that the chips toggle, legal form enables only with Private, "Include inferred" off shrinks the counts, the two portfolio sliders show histograms, "Reset filters" clears everything and re-checks "Include inferred", and it works at phone width.

- [ ] **Step 7: Commit (ask first)**

```bash
git add frontend/index.html frontend/src
git commit -m "Sidebar: owner type, legal form, rents and landlord portfolio filters"
```

---

### Task 10: Popup: headline, party kinds, network grouping

**Files:**
- Create: `frontend/src/popup/classification.ts`
- Modify: `frontend/src/popup/labels.ts` (`LABELS.ownerType`, `.kind`, `.scale`, `.market`, `.basis`)
- Modify: `frontend/src/popup/summary.ts` (`renderSummary`)
- Modify: `frontend/src/popup/ownership.ts` (`entityItem`, `entityLists`, owner/manager lines)
- Test: `frontend/src/popup/classification.test.ts` (create), `frontend/src/popup/ownership.test.ts` (append)

**Interfaces:**
- Consumes: `Building.classification`, `Party.kind`, `Party.institutional`, `NetworkEntity.kind`
- Produces: `classificationHeadline(b: Building): string` (HTML, `''` when nothing is known); `kindChip(p: Party): string`

- [ ] **Step 1: Write the failing tests**

`frontend/src/popup/classification.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { classificationHeadline } from './classification';
import { building } from './fixtures';

const withClass = (classification: any) => ({ ...building, classification });
const unknown = { value: 'unknown', basis: [], inferred: false };

describe('classificationHeadline', () => {
  it('headline is empty when nothing is known', () => {
    expect(classificationHeadline(withClass({ owner: { ...unknown, legal_forms: [], parts: [], reason: null }, market: unknown, operator: null, scale: null }))).toBe('');
  });

  it('names type, legal form, scale and market, marking inferred parts', () => {
    const html = classificationHeadline(withClass({
      owner: { value: 'private', legal_forms: ['numbered_company'], parts: [], reason: null, basis: ['registry', 'name_rule'], inferred: false },
      market: { value: 'market', basis: ['registry'], inferred: true }, operator: null, scale: 'large_portfolio' }));
    expect(html).toContain('Private');
    expect(html).toContain('numbered company');
    expect(html).toContain('large portfolio');
    expect(html).toMatch(/class="[^"]*inferred[^"]*"[^>]*>market/);
  });

  it('says an owner from the licence holder is not confirmed on title', () => {
    const html = classificationHeadline(withClass({
      owner: { value: 'private', legal_forms: ['company'], parts: [], reason: null, basis: ['licence', 'name_rule'], inferred: true },
      market: unknown, operator: null, scale: null }));
    expect(html).toContain('not confirmed on title');
  });

  it('spells out a public-land leasehold', () => {
    const html = classificationHeadline(withClass({
      owner: { value: 'mixed', legal_forms: ['company'], parts: ['government', 'private'], reason: 'public_land_private_leasehold', basis: ['registry', 'city_owned'], inferred: false },
      market: unknown, operator: null, scale: null }));
    expect(html).toContain('City land, private leasehold');
  });
});
```

In `ownership.test.ts`, following its existing render setup:

```ts
it('groups network members by kind', () => {
  const net = { ...network, entities: [
    { name: 'Kim, Phil', also_named: [], kind: 'individual', buildings: 0 },
    { name: '0733603 BC Ltd', also_named: [], kind: 'numbered_company', buildings: 3 },
    { name: '0733604 BC Ltd', also_named: [], kind: 'numbered_company', buildings: 1 },
    { name: 'Kim Holdings Ltd', also_named: [], kind: 'company', buildings: 2 },
  ] };
  const html = renderOwnership({ ...building, network_id: net.id }, { ...ctx, networks: { [net.id]: net } });
  expect(html).toContain('1 person');
  expect(html).toContain('2 numbered companies');
  expect(html).toContain('1 company');
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx vitest run src/popup`
Expected: FAIL (`classification` module missing; grouping text absent)

- [ ] **Step 3: Labels**

`labels.ts`, inside `LABELS`:

```ts
  ownerType: { government: 'Public', non_profit: 'Non-profit', coop: 'Co-op', private: 'Private', mixed: 'Mixed', unknown: '' },
  kind: {
    government: 'public body', non_profit: 'non-profit', coop: 'co-op', individual: 'individual', company: 'company',
    numbered_company: 'numbered company', trust: 'trust', partnership: 'partnership', unknown: '',
  },
  kindPlural: {
    government: ['public body', 'public bodies'], non_profit: ['non-profit', 'non-profits'], coop: ['co-op', 'co-ops'],
    individual: ['person', 'people'], company: ['company', 'companies'], numbered_company: ['numbered company', 'numbered companies'],
    trust: ['trust', 'trusts'], partnership: ['partnership', 'partnerships'], unknown: ['other', 'others'],
  },
  institutional: { reit: 'REIT', pension_fund: 'pension fund', insurer: 'insurer', asset_manager: 'asset manager', other: 'institutional investor' },
  scale: { single: 'single building', small_portfolio: 'small portfolio', large_portfolio: 'large portfolio' },
  market: { non_market: 'non-market', market: 'market', unknown: '' },
  basis: {
    name_rule: 'the name', registry: 'the provincial registry', licence: 'the rental licence holder', listing: "the manager's listing",
    city_owned: "the City's list of City-owned land", non_market_list: "the City's non-market housing list", chf_bc: "CHF BC's co-op list",
    sro_inventory: "the City's SRO inventory", claim_registry: 'provincial registry (research)', claim_city_records: 'City records',
    vtu_research: 'VTU research',
  },
```

Adjust the object's type annotation if `LABELS` is declared `as const` or typed. Keep the existing pattern.

- [ ] **Step 4: Headline**

`frontend/src/popup/classification.ts`:

```ts
/** The classification headline on the Summary tab (spec 2026-10-20). */
import type { Building, Party } from '../contract.gen';
import { escapeHtml } from '../html';
import { provenanceIcon } from '../provenance';
import { LABELS } from './labels';

const basisText = (basis: string[]): string =>
  basis.map((b) => (LABELS.basis as Record<string, string>)[b] ?? b).join(', ');

const part = (text: string, inferred: boolean, why: string): string =>
  `<span class="popup-class${inferred ? ' inferred' : ''}">${escapeHtml(text)}</span>${why ? provenanceIcon(why) : ''}`;

function ownerWhy(b: Building): string {
  const o = b.classification.owner;
  if (o.basis.includes('licence')) return `From ${basisText(['licence'])}; not confirmed on title.`;
  return o.basis.length ? `From ${basisText(o.basis)}.` : '';
}

export function classificationHeadline(b: Building): string {
  const { owner, market, scale } = b.classification;
  const parts: string[] = [];
  if (owner.value === 'mixed') {
    const text = owner.reason === 'public_land_private_leasehold' ? 'City land, private leasehold'
      : `Mixed: ${owner.parts.map((p) => LABELS.ownerType[p]).join(' and ')}`;
    parts.push(part(text, owner.inferred, ownerWhy(b)));
  } else if (owner.value !== 'unknown') {
    parts.push(part(LABELS.ownerType[owner.value], owner.inferred, ownerWhy(b)));
  }
  if (owner.legal_forms.length) parts.push(escapeHtml(owner.legal_forms.map((k) => LABELS.kind[k]).join(', ')));
  if (scale) parts.push(escapeHtml(LABELS.scale[scale]));
  if (market.value !== 'unknown') {
    const why = market.inferred && market.value === 'market'
      ? `Inferred: privately owned and not on ${basisText(['non_market_list'])}.`
      : `From ${basisText(market.basis)}.`;
    parts.push(part(LABELS.market[market.value] + (market.inferred ? ' (inferred)' : ''), market.inferred, why));
  }
  return parts.length ? `<div class="popup-classification">${parts.join(' · ')}</div>` : '';
}

/** A party's kind (and institutional flag), as a small chip after its name. */
export function kindChip(p: Party): string {
  const labels = [p.kind ? LABELS.kind[p.kind] : '', p.institutional ? LABELS.institutional[p.institutional] : '']
    .filter(Boolean);
  return labels.length ? ` <span class="popup-kind">${escapeHtml(labels.join(' · '))}</span>` : '';
}
```

`summary.ts` `renderSummary`: prepend `classificationHeadline(b)` right after `badges(b)`.

CSS (in `frontend/src/popup.css`): `.popup-classification` (one line, slightly smaller than body text), `.popup-class.inferred` (muted colour, dotted underline), `.popup-kind` (small muted pill like `.popup-tier`). Use existing colour tokens and check both light and dark themes.

- [ ] **Step 5: Ownership tab**

`ownership.ts`:
- `entityItem`: `const held = e.kind === 'individual' ? '' : ...` (people show no building count, as now).
- Replace `entityLists`:

```ts
const KIND_ORDER = ['individual', 'company', 'numbered_company', 'trust', 'partnership', 'non_profit', 'coop', 'government', 'unknown'] as const;

/** The network's members grouped by kind, people first (most buildings on the map first, as exported). */
function entityLists(entities: NetworkEntity[]): string {
  const lists = KIND_ORDER.map((kind) => {
    const group = entities.filter((e) => e.kind === kind);
    const [one, many] = LABELS.kindPlural[kind];
    return collapsed(plural(group.length, one, many), group.map(entityItem));
  }).join('');
  return lists && `<div class="popup-muted net-entities-intro">Linked in this network:</div>${lists}`;
}
```

- Where the tab renders owner, interest-holder, manager and licensee names (`ownersBody`, `registryLine`, `managedBy`, `licensedTo`), append `kindChip(p)` after the escaped name. On the manager line, also show the operator type when `b.classification.operator` is set and differs from the manager's own kind label: `<span class="popup-muted">operator: ${LABELS.ownerType[op.value]}</span>`.

- [ ] **Step 6: Run tests and typecheck**

Run: `cd frontend && npm run typecheck && npm test`
Expected: all PASS. Update existing ownership snapshot/text tests that expected the old "N people / N companies" lists only where the wording legitimately changed.

- [ ] **Step 7: Look at it**

Run: `uv run python scripts/rebuild_data.py --skip-ingest && uv run dev`. Open popups for a numbered-company building, a City-land building (e.g. one of the VAHEF sites), a non-profit co-op, an SRO with a non-profit operator, and a licence-only building. Each headline should read correctly, inferred parts should look softer with an ⓘ explaining why, and the popup should work at phone width.

- [ ] **Step 8: Commit (ask first)**

```bash
git add frontend/src
git commit -m "Popup: classification headline, party kinds, network members by kind"
```

---

### Task 11: Docs, spec amendments, full rebuild check

**Files:**
- Modify: `docs/superpowers/specs/2026-10-20-building-classification-design.md` (apply "Spec refinements" 1–6; replace the "Derived tables" section and the SQL examples with the CSV outputs and a `sqlite3 :memory:` `.import --csv` example)
- Modify: `CLAUDE.md` (Section 3: a short "Building classification" paragraph and the two attribute claim relationships under "Claims ingestion"; Section 9: tick a new Phase 1 item; Open questions: replace the paused sector-classification sentence with a pointer to the spec)
- Modify: `docs/DATA_SOURCES.md` only if Task 4 missed anything

- [ ] **Step 1: Amend the spec and CLAUDE.md** as listed above. Keep CLAUDE.md edits short, matching its density.

- [ ] **Step 2: Full rebuild and snapshot comparison**

Run:

```bash
uv run python scripts/compare_snapshots.py --help   # read its usage first
```

Snapshot `data/derived` before the change (from `main`, if not already taken), then:

```bash
uv run python scripts/prepare_data.py
uv run python scripts/rebuild_data.py
uv run python scripts/compare_snapshots.py <before> <after>
```

Expected differences only: the new `raw_city_owned_properties` table, `ingest_runs` rows, `schema_version` 5, `Party.kind`/`institutional`, `Building.classification`, `NetworkEntity.kind` values, `NetworkTotals.assessed_value`, and the two new `filter_config` metrics. Anything else is a regression; stop and investigate.

- [ ] **Step 3: Public-gate check**

Run: `uv run pytest tests/test_export_ownership.py tests/test_export_artifacts.py -v`, then `grep -c "source_note\|reported_by\|tenant_report" data/derived/artifacts/*.json`. Expected: all tests PASS and every count is 0.

- [ ] **Step 4: Run the report** (`uv run python scripts/classification_report.py`) and paste its summary counts into the hand-off message for the author.

- [ ] **Step 5: Commit (ask first)**

```bash
git add CLAUDE.md docs
git commit -m "Docs: building classification in CLAUDE.md and the spec's planning refinements"
```

Deploy is **not** part of this plan. `uv run deploy` happens only when the author asks, after they've looked at the map locally.
