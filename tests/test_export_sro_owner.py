"""The City's SRO inventory names the owner of buildings the registry doesn't
(over a licence holder too), and its abbreviated names are expanded for display."""

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


def test_sro_owner_outranks_a_licence_owner_and_its_licence_group():
    # Marble Arch: BC Housing owns it (SRO inventory); PHS only holds the licence.
    df = _frame(
        owner_name="PHS Community Services Society",
        owner_key="phs-community-services-society",
        owner_source="licence",
        network_key="phs-community-services-society",
        network_name="PHS Community Services Society",
        network_source="licence",
    )
    row = _first(fill_owner_from_sro(df))
    assert (row.owner_name, row.owner_key, row.owner_source) == ("BC Housing", "bc-housing", "sro_list")
    assert (row.network_key, row.network_name, row.network_source) == ("bc-housing", "BC Housing", "sro_list")


def test_sro_owner_never_replaces_a_registry_owner_or_claims_network():
    df = _frame(
        owner_name="REAL OWNER LTD.",
        owner_key="real-owner-ltd",
        owner_source="registry",
        network_key="net:real",
        network_name="Real Group",
        network_source="claims",
    )
    row = _first(fill_owner_from_sro(df))
    assert (row.owner_name, row.owner_source) == ("REAL OWNER LTD.", "registry")
    assert (row.network_key, row.network_source) == ("net:real", "claims")


def test_licence_owner_in_a_claims_network_keeps_the_network():
    df = _frame(
        owner_name="PHS Community Services Society",
        owner_key="phs-community-services-society",
        owner_source="licence",
        network_key="net:phs",
        network_name="PHS Group",
        network_source="claims",
    )
    row = _first(fill_owner_from_sro(df))
    assert row.owner_name == "BC Housing"
    assert (row.network_key, row.network_source) == ("net:phs", "claims")


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


from tc_core.sro_names import parse_sro_names

NAMES = parse_sro_names("""\
Chris Wall - 1030163 BC Ltd => 1030163 BC Ltd | behind: Chris Wall
Bob Leung and Richard Chang => owners: Bob Leung; Richard Chang
Ging, Huie S (15 year lease to Chris Wall) => Ging, Huie S | manager: Chris Wall
""")


def test_curated_names_correct_the_sro_owner():
    row = _first(fill_owner_from_sro(_frame(sro_owner="Chris Wall - 1030163 BC Ltd"), NAMES))
    assert (row.owner_name, row.owner_key) == ("1030163 BC Ltd", "1030163-bc-ltd")
    assert row.sro_owners == ["1030163 BC Ltd"]


def test_joint_sro_owners_are_kept_apart():
    row = _first(fill_owner_from_sro(_frame(sro_owner="Bob Leung and Richard Chang"), NAMES))
    assert row.owner_name == "Bob Leung"
    assert row.sro_owners == ["Bob Leung", "Richard Chang"]


def test_a_named_lessee_runs_the_building():
    row = _first(fill_owner_from_sro(
        _frame(sro_owner="Ging, Huie S (15 year lease to Chris Wall)", sro_operator="Private"), NAMES))
    assert (row.owner_name, row.sro_operator) == ("Ging, Huie S", "Chris Wall")


def test_buildings_without_an_sro_owner_have_no_sro_owners():
    row = _first(fill_owner_from_sro(_frame(sro_owner=None), NAMES))
    assert row.sro_owners == []
