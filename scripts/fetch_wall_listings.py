"""Snapshot Wall Financial's rental portfolio for raw_manager_listings.

Wall Financial owns and runs its own buildings, so this is an owner's
listing feed rather than a third-party manager's: it names buildings and
gives their addresses, it doesn't change who the map says owns them.

Source: https://www.wallfinancialcorporation.com/rental (Webflow, 18 cards
as of 2026-09-30) lists every property, rented or not:

    <div data-city="Vancouver" data-status="Now Renting" role="listitem"
         class="rentals-item w-dyn-item"> ... <a href="/properties/amber-lodge">

The street address is only on each property's page, in its schema.org
ApartmentComplex block ("1045 W 14th Ave, Vancouver, BC"), so every card
costs one more request. Properties still in development may have none.

Writes data/raw/property_managers/wall/<YYYY-MM-DD>.json in the
theliftsystem.com feed shape (id, name, permalink, address, client) that
tc_core/ingest/manager_listings.py reads. Manual pull, like
fetch_dorset_listings.py: re-run by hand, then rebuild.
"""

from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

BASE_URL = "https://www.wallfinancialcorporation.com"
LIST_URL = f"{BASE_URL}/rental"
MANAGER = "Wall Financial Corporation"
DEFAULT_DIR = "data/raw/property_managers/wall"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_CARD_RE = re.compile(
    r'<div data-city="([^"]*)" data-status="([^"]*)" role="listitem" class="rentals-item\b'
)
_LINK_RE = re.compile(r'href="(/properties/[^"#?]+)"')
_TITLE_RE = re.compile(r'<h2 class="card_primary_title[^"]*">(.*?)</h2>', re.DOTALL)
_UNITS_AVAILABLE_RE = re.compile(r'<div class="units-available">\s*(\d+)\s*</div>')
_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
_COUNT_RE = re.compile(r'"@id": "[^"]*/rental#rentals".*?"numberOfItems": (\d+)', re.DOTALL)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_cards(page: str) -> list[dict]:
    starts = list(_CARD_RE.finditer(page))
    if not starts:
        raise RuntimeError(
            "No rentals-item cards found: Wall's page markup may have changed; "
            "re-check the source before assuming an empty result."
        )
    cards = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(page)
        chunk = page[start.start():end]
        link = _LINK_RE.search(chunk)
        title = _TITLE_RE.search(chunk)
        if not link or not title:
            raise RuntimeError(f"Card {i + 1} has no property link or title.")
        available = _UNITS_AVAILABLE_RE.search(chunk)
        cards.append({
            "slug": link.group(1).rsplit("/", 1)[-1],
            "name": htmllib.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip(),
            "permalink": BASE_URL + link.group(1),
            "city": htmllib.unescape(start.group(1)).strip() or None,
            "status": htmllib.unescape(start.group(2)).strip() or None,
            "units_available": int(available.group(1)) if available else None,
        })
    count = _COUNT_RE.search(page)
    if count and int(count.group(1)) != len(cards):
        raise RuntimeError(
            f"Page lists {count.group(1)} properties but {len(cards)} cards were "
            "parsed: the page may now paginate or lazy-load."
        )
    return cards


def parse_property(page: str) -> dict:
    """Street address, coordinates and unit count from a property page's schema.org blocks."""
    out: dict = {}
    for block in _LD_JSON_RE.findall(page):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        entity = data.get("mainEntity") if data.get("@type") == "WebPage" else data
        if not isinstance(entity, dict) or entity.get("@type") not in ("ApartmentComplex", "Residence"):
            continue
        street = ((entity.get("address") or {}).get("streetAddress") or "").strip()
        if street and "street" not in out:
            # "1045 W 14th Ave, Vancouver, BC": the city and province have their own fields.
            out["street"] = street.split(",")[0].strip()
            out["postal_code"] = (entity.get("address") or {}).get("postalCode")
        geo = entity.get("geo") or {}
        if geo.get("latitude") and "lat" not in out:
            out["lat"], out["lon"] = float(geo["latitude"]), float(geo["longitude"])
        if entity.get("numberOfRooms") and "units" not in out:
            out["units"] = int(entity["numberOfRooms"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=DEFAULT_DIR, help="Snapshot directory")
    parser.add_argument("--date", default=date.today().isoformat(), help="Snapshot date (file name)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between property-page requests")
    args = parser.parse_args()

    cards = parse_cards(fetch(LIST_URL))
    listings = []
    for card in cards:
        time.sleep(args.delay)
        detail = parse_property(fetch(card["permalink"]))
        listings.append({
            "id": card["slug"],
            "name": card["name"],
            "permalink": card["permalink"],
            "address": {
                "address": detail.get("street"),
                "city": card["city"],
                "postal_code": detail.get("postal_code"),
                "lat": detail.get("lat"),
                "lon": detail.get("lon"),
            },
            "units": detail.get("units"),
            "status": card["status"],
            "units_available": card["units_available"],
            "client": {"name": MANAGER},
        })
    missing = [x["name"] for x in listings if not x["address"]["address"]]
    print(f"{len(listings)} properties; no street address for: {', '.join(missing) or 'none'}.", file=sys.stderr)

    out = Path(args.out_dir) / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(listings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
