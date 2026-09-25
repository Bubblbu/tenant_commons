"""A rental licence held by a known property manager names the manager, not
the landlord (Tribe Rental Management holds licences for buildings owned by
Greenbrier Holdings, Shapiro Holdings and others)."""

import pandas as pd

from tc_core.export import apply_property_managers, load_property_managers

TRIBE = "Tribe Rental Management"


def _row(**over):
    row = {
        "owner_name": TRIBE,
        "owner_key": "tribe-rental-management",
        "owner_source": "licence",
        "licence_holder": TRIBE,
        "network_key": "tribe-rental-management",
        "network_name": TRIBE,
        "network_source": "licence",
    }
    row.update(over)
    return row


def _apply(*rows):
    df = pd.DataFrame(list(rows))
    apply_property_managers(df, {"tribe-rental-management"})
    return df


def test_manager_named_only_by_its_licence_is_not_shown_as_landlord():
    row = _apply(_row()).iloc[0]
    assert (row.owner_name, row.owner_key, row.owner_source) == ("(Unknown)", "unknown", None)
    assert (row.network_name, row.network_key, row.network_source) == ("(Unknown)", "unknown", None)
    assert row.managed_by == TRIBE


def test_registry_owner_stays_landlord_and_the_manager_is_recorded():
    row = _apply(_row(
        owner_name="GREENBRIER HOLDINGS LTD.", owner_key="greenbrier-holdings-ltd", owner_source="registry",
        network_name="Greenbrier Holdings Ltd", network_key="net:greenbrier-holdings-ltd", network_source="claims",
    )).iloc[0]
    assert (row.owner_name, row.owner_source) == ("GREENBRIER HOLDINGS LTD.", "registry")
    assert (row.network_key, row.network_source) == ("net:greenbrier-holdings-ltd", "claims")
    assert row.managed_by == TRIBE


def test_licence_holders_not_listed_as_managers_are_untouched():
    row = _apply(_row(owner_name="Solo Ltd", owner_key="solo-ltd", licence_holder="Solo Ltd",
                      network_name="Solo Ltd", network_key="solo-ltd")).iloc[0]
    assert (row.owner_name, row.owner_source, row.network_key) == ("Solo Ltd", "licence", "solo-ltd")
    assert row.managed_by is None


def test_load_property_managers_reads_names_as_keys(tmp_path):
    path = tmp_path / "property_managers.toml"
    path.write_text('[[manager]]\nname = "Tribe Rental Management"\n\n[[manager]]\nname = "Example Mgmt Ltd."\n')
    assert load_property_managers(str(path)) == {"tribe-rental-management", "example-mgmt-ltd"}


def test_no_managers_file_means_no_managers(tmp_path):
    assert load_property_managers(None) == set()
    assert load_property_managers(str(tmp_path / "missing.toml")) == set()


def test_registry_owner_without_a_claims_group_becomes_its_own_group():
    # 1220 Cardero: Broadway Properties on title, Tribe's licence was the only group.
    row = _apply(_row(owner_name="Broadway Properties Ltd.", owner_key="broadway-properties-ltd", owner_source="registry")).iloc[0]
    assert (row.network_name, row.network_key, row.network_source) == (
        "Broadway Properties Ltd.", "broadway-properties-ltd", "registry",
    )


def test_any_landlord_without_a_group_is_its_own_group():
    # Registry owner, no rental licence, no claims group (e.g. 2061 Beach Ave).
    from tc_core.export import fallback_group_to_owner

    df = pd.DataFrame([
        _row(owner_name="Solo Owner Ltd.", owner_key="solo-owner-ltd", owner_source="registry",
             licence_holder="(Unknown)", network_name="(Unknown)", network_key="unknown", network_source=None),
        _row(owner_name="(Unknown)", owner_key="unknown", owner_source=None,
             licence_holder="(Unknown)", network_name="(Unknown)", network_key="unknown", network_source=None),
    ])
    fallback_group_to_owner(df)
    assert tuple(df.iloc[0][["network_name", "network_key", "network_source"]]) == (
        "Solo Owner Ltd.", "solo-owner-ltd", "registry",
    )
    assert df.iloc[1].network_key == "unknown"


def test_managers_include_the_managing_side_of_confirmed_managed_by_claims():
    from tc_core.claims import record_claim
    from tc_core.db import get_connection, init_db
    from tc_core.export import managers_from_claims

    conn = get_connection(":memory:")
    init_db(conn)
    record_claim(conn, entity_a="Tribe Rental Management", entity_b="Greenbrier Holdings Ltd",
                 relationship="managed_by", source_type="manual_research", confidence="confirmed")
    record_claim(conn, entity_a="Maybe Mgmt Ltd", entity_b="Some Owner Ltd",
                 relationship="managed_by", source_type="manual_research", confidence="unconfirmed")
    assert managers_from_claims(conn) == {"tribe-rental-management"}
