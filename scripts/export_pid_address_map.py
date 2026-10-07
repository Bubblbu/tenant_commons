#!/usr/bin/env python3
"""Builds a PID <-> address lookup table from the ingested raw_addresses.

`buildings` (see merge.py) is keyed on `addr_key` (a normalized street
string) and never carries the BC land title parcel ID (PID) at all. This
script exports a standalone bridge table — one row per address point, with
its civic address and the same `addr_key` the merge pipeline already uses —
so PID-keyed sources (BC Assessment, other Open Data layers, etc.) can be
joined onto `buildings`/`raw_addresses` without re-deriving the key.

The real 9-digit numeric PID lives in raw_addresses.site_id, not
p_parcel_id (Vancouver's own internal alphanumeric address-point ID, e.g.
"__GLL1JZ" — unique per row but meaningless outside this dataset) and not
pcoord (an 8-digit legacy tax coordinate, not a land title PID). ~7.5% of
rows have a BC land title plan number in site_id instead (prefixes like
EPS/VAS/LMS/BCS — bare-land-strata/subdivision plans that haven't been
assigned individual PIDs at the address-point level) or are blank; for
those, `pid` is left null rather than emitting a non-PID value under that
name. `address_point_id` (p_parcel_id) is always present so every row
still has a stable join key even when no real PID exists.

Reads from data/derived/tc_core.db's `raw_addresses` table (already ingested from
config's `addresses` path) rather than re-parsing the source CSV, so this
stays consistent with whatever's actually loaded.

Usage: uv run python scripts/export_pid_address_map.py [--config config.toml]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PID_RE = re.compile(r"\d{9}")

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only for <3.11
    tomllib = None

import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.db import get_connection, query_frame  # noqa: E402
from tc_core.normalize import addr_key_from_freeform  # noqa: E402


def _load_paths(config_path: Path) -> tuple[Path, Path]:
    if tomllib is None:
        raise RuntimeError("tomllib not available; upgrade to Python 3.11+.")
    raw = tomllib.loads(config_path.read_text())
    paths = raw.get("paths", {})
    try:
        db_path = paths["tc_core_db"]
        out_path = paths["pid_address_map"]
    except KeyError as exc:
        raise ValueError(f"{config_path} is missing paths.{exc.args[0]}") from exc
    return REPO_ROOT / db_path, REPO_ROOT / out_path


def _civic_str(civic) -> str:
    civic_int = float(civic)
    return str(int(civic_int)) if civic_int.is_integer() else str(civic_int)


def _addr_key(civic, street) -> str:
    if street is None:
        return addr_key_from_freeform("")
    if civic is None:
        return addr_key_from_freeform(str(street))
    return addr_key_from_freeform(f"{_civic_str(civic)} {street}")


def _full_address(civic, street) -> str | None:
    street = None if street is None else str(street)
    if civic is None:
        return street
    return f"{_civic_str(civic)} {street}" if street else _civic_str(civic)


def build_pid_address_map(conn) -> pl.DataFrame:
    df = query_frame(
        conn,
        "SELECT p_parcel_id AS address_point_id, site_id, civic_number, std_street, "
        "geo_local_area, geo_point_2d FROM raw_addresses",
    ).with_columns(pl.all().cast(pl.String))
    dupes = df.height - df["address_point_id"].n_unique()
    if dupes:
        raise RuntimeError(
            f"raw_addresses.p_parcel_id has {dupes} duplicate value(s); "
            "this table was assumed to be one row per address point."
        )

    points = list(zip(df["civic_number"], df["std_street"]))
    out = df.select(
        pid=pl.when(pl.col("site_id").str.contains(f"^{PID_RE.pattern}$"))
        .then(pl.col("site_id")),
        address_point_id="address_point_id",
        address=pl.Series([_full_address(c, s) for c, s in points], dtype=pl.String),
        addr_key=pl.Series([_addr_key(c, s) for c, s in points], dtype=pl.String),
        local_area="geo_local_area",
        lat_lon="geo_point_2d",
    )
    # An address point with no street has an empty key; write it as an
    # empty cell, not "".
    return out.sort("addr_key", maintain_order=True).with_columns(
        pl.col("addr_key").replace("", None)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO_ROOT / "config.toml"))
    args = parser.parse_args()

    db_path, out_path = _load_paths(Path(args.config))

    if not db_path.exists():
        print(
            f"{db_path} not found. Run the tc_core ingest first "
            "(python -m tc_core.ingest) to populate raw_addresses.",
            file=sys.stderr,
        )
        return 1

    conn = get_connection(db_path)
    try:
        out = build_pid_address_map(conn)
    finally:
        conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.write_csv(out_path)
    print(f"Wrote {out.height} PID->address rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
