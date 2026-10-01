"""Snapshot Dorset Realty's residential portfolio for raw_manager_listings.

Source: https://dorsetrealty.com/properties/residential/ renders every
property as a server-side card on one page (50 as of 2026-09-30), vacant
or fully rented alike:

    <div class="drl-property-card" data-property-id="3332">
      ... <span class="drl-card__badge-text">3 units available</span>
      <a href="https://dorsetrealty.com/properties/residential/ocean-crest/">
        <h2 class="drl-card__title">Ocean Crest</h2>
        <span class="drl-card__city">Vancouver</span>
        <div class="drl-card__street">1333 Jervis Street</div>

Writes data/raw/property_managers/dorset/<YYYY-MM-DD>.json in the same
shape as the theliftsystem.com feed (id, name, permalink, address,
client), so tc_core/ingest/manager_listings.py reads it unchanged. Cards
carry no staff contact details. Manual pull, like fetch_coops.py: re-run by
hand, then rebuild.
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

SOURCE_URL = "https://dorsetrealty.com/properties/residential/"
MANAGER = "Dorset Realty Group"
DEFAULT_DIR = "data/raw/property_managers/dorset"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_CARD_START_RE = re.compile(r'<div class="drl-property-card" data-property-id="(\d+)">')
_COUNT_RE = re.compile(r'<span id="drl-results-count">(\d+)</span>')
_FIELDS = {
    "permalink": re.compile(r'<a href="([^"]+)" class="drl-card__link">'),
    "name": re.compile(r'<h2 class="drl-card__title">(.*?)</h2>', re.DOTALL),
    "city": re.compile(r'<span class="drl-card__city">(.*?)</span>', re.DOTALL),
    "street": re.compile(r'<div class="drl-card__street">(.*?)</div>', re.DOTALL),
    "status": re.compile(r'<span class="drl-card__badge-text">(.*?)</span>', re.DOTALL),
}


def fetch_html(url: str = SOURCE_URL) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def _text(match: re.Match | None) -> str | None:
    if not match:
        return None
    return htmllib.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip() or None


def parse_cards(page: str) -> list[dict]:
    starts = list(_CARD_START_RE.finditer(page))
    if not starts:
        raise RuntimeError(
            "No drl-property-card elements found: Dorset's page markup may "
            "have changed; re-check the source before assuming an empty result."
        )
    listings = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(page)
        card = page[start.start():end]
        f = {k: _text(rx.search(card)) for k, rx in _FIELDS.items()}
        listings.append({
            "id": int(start.group(1)),
            "name": f["name"],
            "permalink": f["permalink"],
            "address": {"address": f["street"], "city": f["city"]},
            "status": f["status"],
            "client": {"name": MANAGER},
        })
    count = _COUNT_RE.search(page)
    if count and int(count.group(1)) != len(listings):
        raise RuntimeError(
            f"Page reports {count.group(1)} properties but {len(listings)} cards "
            "were parsed: the page may now paginate or lazy-load."
        )
    return listings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=DEFAULT_DIR, help="Snapshot directory")
    parser.add_argument("--date", default=date.today().isoformat(), help="Snapshot date (file name)")
    parser.add_argument("--html-file", help="Parse this saved page instead of fetching")
    args = parser.parse_args()

    page = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else fetch_html()
    listings = parse_cards(page)
    available = sum(1 for x in listings if x["status"] and "available" in x["status"])
    print(f"{len(listings)} properties ({available} with vacancies).", file=sys.stderr)

    out = Path(args.out_dir) / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(listings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
