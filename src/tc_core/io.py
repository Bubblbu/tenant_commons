"""CSV loading helpers.

Forked from `src/sica_mapping/core/io.py` (see normalize.py's provenance
note; `sica_mapping` is retired) minus `setup_logging`, which was a
sica_mapping-specific logging concern this package never needed. Ported
from pandas to polars 2026-10.
"""

from __future__ import annotations

import csv

import polars as pl

# Text pandas.read_csv treats as missing by default. Raw tables store such
# text verbatim; pass this as `null_values` where a hand-typed field should
# read "N/A" and the like as empty instead.
PLACEHOLDER_NULLS = [
    "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan", "1.#IND", "1.#QNAN",
    "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a", "nan", "null",
]


def read_any_csv(path: str) -> pl.DataFrame:
    """Read a CSV whose delimiter varies by source (";" for City Open Data
    exports, "," elsewhere), sniffed from the header line.

    Types are inferred from the whole file, not the first rows, and a quoted
    empty string ("") is read as missing, like an empty cell. Text such as
    "NA" or "n/a" is kept as written.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        header = f.readline()
    try:
        separator = csv.Sniffer().sniff(header, delimiters=",;\t").delimiter
    except csv.Error:  # a single-column file has nothing to sniff
        separator = ","
    df = pl.read_csv(path, separator=separator, infer_schema_length=None)
    return df.with_columns(pl.col(pl.String).replace("", None))


def normalize_cols(df: pl.DataFrame) -> pl.DataFrame:
    """Return a copy with normalised column names."""

    def _clean(col: object) -> str:
        s = str(col).replace("﻿", "")
        return s.strip().lower().replace(" ", "_")

    return df.rename(_clean)


def require_columns(df: pl.DataFrame, cols: set[str], label: str) -> None:
    """Ensure the expected columns are available."""
    missing = set(cols) - set(df.columns)
    if missing:
        raise RuntimeError(f"{label} missing columns: {sorted(missing)}")
