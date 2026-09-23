"""Download the Vancouver Open Data exports tc_core needs.

Replaces `scripts/sync_from_vhd.py` and vhd's download_data.py. Each dataset
is fetched in the formats its consumers read: CSV for the ingest
(raw_addresses, blocks, block numbers, local-area boundary) and GeoJSON for
the prepare steps (properties/buildings). Files land as
`<dataset-id>.<format>` so `DataPaths.cov()` can find them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import requests

BASE_URL = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets"
DEFAULT_TAX_REPORT_YEAR = 2026


@dataclass(frozen=True)
class Dataset:
    id: str
    formats: tuple[str, ...]
    refine: str | None = None  # may contain "{year}"


DATASETS = (
    Dataset("local-area-boundary", ("csv", "geojson")),
    Dataset("property-addresses", ("csv", "geojson")),
    Dataset("property-tax-report", ("geojson",), refine="report_year:{year}"),
    Dataset("business-licences", ("geojson",)),
    Dataset("non-market-housing", ("geojson",)),
    Dataset("rental-standards-current-issues", ("geojson",)),
    Dataset("block-outlines", ("csv",)),
    Dataset("block-numbers", ("csv",)),
)


@dataclass(frozen=True)
class Download:
    dataset: str
    fmt: str
    refine: str | None
    url: str
    out_path: Path


def plan_downloads(
    out_dir: str | Path,
    tax_report_year: int = DEFAULT_TAX_REPORT_YEAR,
    only: Sequence[str] | None = None,
) -> list[Download]:
    known = {d.id for d in DATASETS}
    unknown = sorted(set(only or ()) - known)
    if unknown:
        raise ValueError(f"unknown dataset(s): {', '.join(unknown)}")
    out_dir = Path(out_dir)
    plan: list[Download] = []
    for ds in DATASETS:
        if only and ds.id not in only:
            continue
        refine = ds.refine.format(year=tax_report_year) if ds.refine else None
        for fmt in ds.formats:
            plan.append(
                Download(
                    ds.id, fmt, refine,
                    f"{BASE_URL}/{ds.id}/exports/{fmt}",
                    out_dir / f"{ds.id}.{fmt}",
                )
            )
    return plan


def download(dl: Download, get: Callable = requests.get, chunk_size: int = 1 << 20) -> int:
    """Stream one export to disk. Writes to a .part file and renames on
    success, so a dropped connection never clobbers an existing good file."""
    dl.out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dl.out_path.with_name(dl.out_path.name + ".part")
    params = {"refine": dl.refine} if dl.refine else None
    total = 0
    try:
        r = get(dl.url, stream=True, params=params, timeout=120)
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size):
                f.write(chunk)
                total += len(chunk)
        os.replace(tmp, dl.out_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return total


def fetch_all(
    out_dir: str | Path,
    tax_report_year: int = DEFAULT_TAX_REPORT_YEAR,
    only: Sequence[str] | None = None,
    get: Callable = requests.get,
    log: Callable[[str], None] = print,
) -> list[Download]:
    plan = plan_downloads(out_dir, tax_report_year, only)
    for dl in plan:
        log(f"fetching {dl.out_path.name} ...")
        size = download(dl, get=get)
        log(f"  {dl.out_path.name}: {size / 1e6:.1f} MB")
    return plan
