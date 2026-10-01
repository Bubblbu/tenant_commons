"""Snapshot MetCap Living's Vancouver portfolio for raw_manager_listings.

MetCap Living manages rental buildings for their owners, so its listings
name the building's manager, not its owner.

Source: https://www.metcap.com/province-search-results?lang=en&province=117&city=Vancouver
renders every Vancouver property as a server-side card on one page (23 as of
2026-09-30):

    <div class="province-results__item" ... onclick="centerMap($(this), {lat: 49.28, lon: -123.13})">
      <h2><a href="/property/1005-jervis-street-vancouver-bc-v6e-3t1">1005 Jervis Street, Vancouver, BC V6E 3T1</a></h2>
      <p><span class="d-block">The Summit</span> ...

Writes data/raw/property_managers/metcap/<YYYY-MM-DD>.json in the same
shape as the theliftsystem.com feed (id, name, permalink, address, client),
so tc_core/ingest/manager_listings.py reads it unchanged. Cards carry no
staff contact details. Manual pull, like fetch_dorset_listings.py: re-run by
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

BASE_URL = "https://www.metcap.com"
SOURCE_URL = f"{BASE_URL}/province-search-results?lang=en&province=117&city=Vancouver"
MANAGER = "MetCap Living"
DEFAULT_DIR = "data/raw/property_managers/metcap"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

_CARD_RE = re.compile(
    r'<div class="province-results__item"[^>]*centerMap\(\$\(this\), \{lat: ([-\d.]+), lon: ([-\d.]+)\}\)'
)
_TITLE_RE = re.compile(r'<h2><a href="(/property/[^"]+)">(.*?)</a></h2>', re.DOTALL)
_NAME_RE = re.compile(r'<span class="d-block">([^<]*?)</span>', re.DOTALL)


def fetch_html(url: str = SOURCE_URL) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_cards(page: str) -> list[dict]:
    starts = list(_CARD_RE.finditer(page))
    if not starts:
        raise RuntimeError(
            "No province-results__item cards found: MetCap's page markup may "
            "have changed; re-check the source before assuming an empty result."
        )
    listings = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(page)
        card = page[start.start():end]
        title = _TITLE_RE.search(card)
        if not title:
            raise RuntimeError(f"Card {i + 1} has no property link.")
        full = htmllib.unescape(re.sub(r"<[^>]+>", "", title.group(2))).strip()
        # "1005 Jervis Street, Vancouver, BC V6E 3T1": the street, then the city.
        parts = [p.strip() for p in full.split(",")]
        # The name is a plain span in the card's own <p>; the last card's chunk
        # runs to the end of the page, so never search past that </p>.
        p_end = card.find("</p>", title.end())
        name = _NAME_RE.search(card, title.end(), p_end if p_end != -1 else len(card))
        listings.append({
            "id": title.group(1).rsplit("/", 1)[-1],
            "name": (htmllib.unescape(name.group(1)).strip() or None) if name else None,
            "permalink": BASE_URL + title.group(1),
            "address": {
                "address": parts[0],
                "city": parts[1] if len(parts) > 1 else None,
                "lat": float(start.group(1)),
                "lon": float(start.group(2)),
            },
            "client": {"name": MANAGER},
        })
    return listings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=DEFAULT_DIR, help="Snapshot directory")
    parser.add_argument("--date", default=date.today().isoformat(), help="Snapshot date (file name)")
    parser.add_argument("--html-file", help="Parse this saved page instead of fetching")
    args = parser.parse_args()

    page = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else fetch_html()
    listings = parse_cards(page)
    print(f"{len(listings)} properties.", file=sys.stderr)

    out = Path(args.out_dir) / f"{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(listings, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
