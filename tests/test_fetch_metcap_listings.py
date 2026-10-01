"""MetCap Living's Vancouver search page parses into the shared feed shape."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "fetch_metcap_listings",
    Path(__file__).resolve().parent.parent / "scripts" / "fetch_metcap_listings.py",
)
metcap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metcap)

CARD = """
<div class="province-results__item" style="cursor: pointer;" onclick="centerMap($(this), {lat: 49.2849601, lon: -123.1322621})">
  <div class="province-results__content">
    <h2><a href="/property/1005-jervis-street-vancouver-bc-v6e-3t1">1005 Jervis Street, Vancouver, BC V6E 3T1</a></h2>
    <p>
      <span class="d-block">The Summit</span>
      <span class="d-block"><a href="/apartment/1-bedroom-22">Vancouver 1 Bedroom from $2,275.00</a></span>
    </p>
  </div>
</div>
<div class="province-results__item" style="cursor: pointer;" onclick="centerMap($(this), {lat: 49.29, lon: -123.14})">
  <div class="province-results__content">
    <h2><a href="/property/1265-cardero-street-vancouver-bc-v6g-2j2">1265 Cardero Street, Vancouver, BC V6G 2J2</a></h2>
    <p>
      <span class="d-block"><a href="/apartment/x">Vancouver Bachelor from $1,999.00</a></span>
    </p>
  </div>
</div>
<footer><span class="d-block">Not a building name</span></footer>
"""


def test_cards_parse_into_the_feed_shape():
    listings = metcap.parse_cards(CARD)
    assert listings[0] == {
        "id": "1005-jervis-street-vancouver-bc-v6e-3t1",
        "name": "The Summit",
        "permalink": "https://www.metcap.com/property/1005-jervis-street-vancouver-bc-v6e-3t1",
        "address": {"address": "1005 Jervis Street", "city": "Vancouver", "lat": 49.2849601, "lon": -123.1322621},
        "client": {"name": "MetCap Living"},
    }
    assert listings[1]["name"] is None
    assert listings[1]["address"]["address"] == "1265 Cardero Street"


def test_a_page_without_cards_fails_loudly():
    with pytest.raises(RuntimeError):
        metcap.parse_cards("<html></html>")
