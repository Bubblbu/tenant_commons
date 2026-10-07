"""Read a Long Term Rental licence fee back into the units it pays for.

Fees follow the Licence By-law No. 4450 (consolidated to 2026-07-14,
data/raw/cov_bylaws/4450c.PDF): Schedule A charges Long Term Rental $98 per dwelling unit,
$71 per housekeeping unit and $47 per sleeping unit a year, or $277 flat for non-profit
housing, plus $1,108 for a swimming pool. A licence first taken out after January 1 pays the
$77 application fee (Schedule B) plus the annual fee x months remaining / 12 (s. 6(3)).

The rates are the 2026 ones; they change yearly ($94 per dwelling unit in 2025), so re-check
them against the by-law when the licence data moves to a new folderyear.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from functools import cache

DWELLING, HOUSEKEEPING, SLEEPING = 98, 71, 47
NON_PROFIT, POOL, APPLICATION = 277, 1108, 77
RATES_FOLDERYEAR = 2026
# $139 (a 2025 new one-unit licence left Pending) + $98 (2026 renewal): 553 licences in the
# 2026 data, nearly all issued Nov 2025-Jan 2026 to holders whose 2025 licence is still Pending.
ARREARS_ONE_UNIT = 237
NON_PROFIT_SUBTYPE = "Non-Profit Housing"


@cache
def _split(fee: float, months: int, application: int, rooms: bool, non_profit: bool) -> tuple | None:
    """(kind, dwellings, housekeeping, sleeping, pool) for the simplest reading, or None.

    With rooms=False only dwelling units (or the non-profit flat fee) are tried; the flat fee
    only when `non_profit` (a prorated $277 otherwise matches ordinary fees by chance)."""
    f = months / 12
    found = []
    for pool in (0, 1):
        base = fee - application - pool * POOL * f
        if non_profit and abs(base - NON_PROFIT * f) < 0.6:
            found.append(("non-profit", 0, 0, 0, pool))
        for s in range(int(base // (SLEEPING * f)) + 1 if rooms and base > 0 else 1):
            for h in range(int((base - SLEEPING * f * s) // (HOUSEKEEPING * f)) + 1 if rooms else 1):
                rest = base - (SLEEPING * s + HOUSEKEEPING * h) * f
                d = rest / (DWELLING * f)
                if d > -0.01 and abs(d - round(d)) * DWELLING * f < 0.6:
                    found.append(("rate", round(d), h, s, pool))
            if len(found) > 50:
                break
    found = [c for c in found if c[0] == "non-profit" or c[1] + c[2] + c[3] > 0]
    if not found:
        return None
    found.sort(key=lambda c: (c[0] != "non-profit", c[2] + c[3], c[4]))
    return found[0]


def parse_issued(value: str | None) -> datetime | None:
    """A licence's issueddate as a UTC datetime (a date alone is midnight UTC), or None."""
    try:
        issued = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if issued.tzinfo is None:
        return issued.replace(tzinfo=timezone.utc)
    return issued.astimezone(timezone.utc)


def decode_fee(fee: float, issued: datetime | None = None, status: str | None = None,
               subtype: str | None = None) -> dict:
    """Units behind one fee.

    Dwelling-only readings are tried before any reading with rooms: first the annual rate,
    then a new licence prorated from the issue month or the month before (the fee is set at
    application, the licence issued later). `fee_certain` is False for readings with rooms,
    which often have alternatives ($284 = 4 housekeeping units, or a late 2025 fee plus $98).
    """
    if fee is None or (isinstance(fee, float) and math.isnan(fee)):
        return {"fee_basis": "no fee"}
    if fee == APPLICATION:
        return {"fee_basis": "application fee only" + (" (pending)" if status == "Pending" else "")}
    if fee == ARREARS_ONE_UNIT:
        return {"fee_basis": "annual + 2025 arrears", "non_profit": False, "dwelling_units": 1,
                "housekeeping_units": 0, "sleeping_units": 0, "pool": 0, "fee_certain": True}
    tries = [("annual", 12, 0)]
    if issued is not None and issued.year == RATES_FOLDERYEAR:
        for month in (issued.month, issued.month - 1):
            if 1 < month <= 12:
                tries.append(("new, prorated", 13 - month, APPLICATION))
    tries.append(("new, full year", 12, APPLICATION))
    non_profit = subtype == NON_PROFIT_SUBTYPE or fee in (NON_PROFIT, NON_PROFIT + POOL)
    for rooms in (False, True):
        for basis, months, app in tries:
            hit = _split(float(fee), months, app, rooms, non_profit)
            if hit:
                kind, d, h, s, pool = hit
                return {"fee_basis": basis, "non_profit": kind == "non-profit", "dwelling_units": d,
                        "housekeeping_units": h, "sleeping_units": s, "pool": pool,
                        "fee_certain": not rooms}
    return {"fee_basis": "unexplained"}
