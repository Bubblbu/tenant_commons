"""The City's SRO inventory fills the landlord of buildings no other source
names, and its abbreviated names are expanded for display."""

from types import SimpleNamespace

import polars as pl

from tc_core.export import clean_sro_name, fill_owner_from_sro


def _frame(**cols):
    base = {
        "owner_name": ["(Unknown)"],
        "owner_key": ["unknown"],
        "owner_source": [None],
        "network_key": ["unknown"],
        "network_name": ["(Unknown)"],
        "network_source": [None],
        "sro_owner": ["BCH"],
        "sro_operator": ["Atira Property Managem"],
    }
    base.update({k: [v] for k, v in cols.items()})
    return pl.DataFrame(base)


def _first(df):
    return SimpleNamespace(**df.row(0, named=True))


def test_sro_owner_fills_a_building_no_other_source_names():
    df = _frame()
    row = _first(fill_owner_from_sro(df))
    assert (row.owner_name, row.owner_key, row.owner_source) == ("BC Housing", "bc-housing", "sro_list")
    assert (row.network_key, row.network_name, row.network_source) == ("bc-housing", "BC Housing", "sro_list")


def test_sro_owner_never_replaces_a_registry_or_licence_owner():
    df = _frame(
        owner_name="PHS Community Services Society",
        owner_key="phs-community-services-society",
        owner_source="licence",
        network_key="phs-community-services-society",
        network_name="PHS Community Services Society",
        network_source="licence",
    )
    row = _first(fill_owner_from_sro(df))
    assert row.owner_name == "PHS Community Services Society"
    assert row.owner_source == "licence"


def test_building_without_an_sro_owner_stays_not_on_record():
    df = _frame(sro_owner=None)
    row = _first(fill_owner_from_sro(df))
    assert (row.owner_key, row.owner_source) == ("unknown", None)


def test_sro_names_are_expanded_and_category_words_dropped():
    df = _frame(sro_operator="Private")
    row = _first(fill_owner_from_sro(df))
    assert row.sro_owner == "BC Housing"
    assert row.sro_operator is None
    assert clean_sro_name("Atira Property Managem") == "Atira Property Management"
    assert clean_sro_name("COV") == "City of Vancouver"
    assert clean_sro_name("Phl Kim - 0733603 BC Ltd") == "Phl Kim - 0733603 BC Ltd"
    assert clean_sro_name(None) is None
    assert clean_sro_name("  ") is None


def test_missing_sro_values_stay_null_for_non_sro_buildings():
    df = _frame(sro_owner=None, sro_operator=None)
    row = _first(fill_owner_from_sro(df))
    assert row.sro_owner is None and row.sro_operator is None
