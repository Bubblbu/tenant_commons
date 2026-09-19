"""GeoJSON -> polars loader shared by the prepare steps (ported from vhd)."""

from __future__ import annotations

from pathlib import Path

import polars as pl


def load_polars(file: Path) -> pl.DataFrame:
    return (
        pl.read_json(file)
        .select("features")
        .explode("features")
        .unnest("features")
        .select("properties")
        .unnest("properties")
    )
