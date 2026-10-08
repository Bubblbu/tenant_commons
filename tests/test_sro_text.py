"""SRO inventory PDF-extraction damage (spec 2026-10-08, section 5)."""

import pytest

from tc_core.export import clean_sro_name
from tc_core.sro_text import is_leaked_label, sector


@pytest.mark.parametrize("raw, expected", [
    ("Private", "private"), ("P rivate", "private"), ("Pri vate", "private"),
    ("Non-Profit", "non_profit"), ("N on-Profit", "non_profit"),
    ("Government", "government"), ("Chinese Society", "chinese_society"),
    (None, None), ("", None), ("Atira Property Management", None),
])
def test_sector(raw, expected):
    assert sector(raw) == expected


@pytest.mark.parametrize("raw", ["Private", "vP rivate", "SPrivate", "nPrivate", "P rivate"])
def test_leaked_sector_labels_are_detected(raw):
    assert is_leaked_label(raw)


@pytest.mark.parametrize("raw", ["Private Holdings Ltd", "Atira Property Management", "Government Street Hotel Ltd"])
def test_real_names_are_not_labels(raw):
    assert not is_leaked_label(raw)


def test_clean_sro_name_drops_leaked_labels_and_expands_aliases():
    assert clean_sro_name("vP rivate") is None
    assert clean_sro_name("BCH") == "BC Housing"
    assert clean_sro_name("  Kenstone Properties Ltd ") == "Kenstone Properties Ltd"
