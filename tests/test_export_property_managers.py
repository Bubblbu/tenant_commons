"""A rental licence held by a known property manager names the manager, not
the landlord (Tribe Rental Management holds licences for buildings owned by
Greenbrier Holdings, Shapiro Holdings and others)."""

from types import SimpleNamespace

import polars as pl

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
    df = pl.DataFrame(list(rows))
    return apply_property_managers(df, {"tribe-rental-management"})


def _first(df):
    return SimpleNamespace(**df.row(0, named=True))


def test_manager_named_only_by_its_licence_is_not_shown_as_landlord():
    row = _first(_apply(_row()))
    assert (row.owner_name, row.owner_key, row.owner_source) == ("(Unknown)", "unknown", None)
    assert (row.network_name, row.network_key, row.network_source) == ("(Unknown)", "unknown", None)
    assert row.managed_by == TRIBE


def test_registry_owner_stays_landlord_and_the_manager_is_recorded():
    row = _first(_apply(_row(
        owner_name="GREENBRIER HOLDINGS LTD.", owner_key="greenbrier-holdings-ltd", owner_source="registry",
        network_name="Greenbrier Holdings Ltd", network_key="net:greenbrier-holdings-ltd", network_source="claims",
    )))
    assert (row.owner_name, row.owner_source) == ("GREENBRIER HOLDINGS LTD.", "registry")
    assert (row.network_key, row.network_source) == ("net:greenbrier-holdings-ltd", "claims")
    assert row.managed_by == TRIBE


def test_licence_holders_not_listed_as_managers_are_untouched():
    row = _first(_apply(_row(owner_name="Solo Ltd", owner_key="solo-ltd", licence_holder="Solo Ltd",
                      network_name="Solo Ltd", network_key="solo-ltd")))
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
    row = _first(_apply(_row(owner_name="Broadway Properties Ltd.", owner_key="broadway-properties-ltd", owner_source="registry")))
    assert (row.network_name, row.network_key, row.network_source) == (
        "Broadway Properties Ltd.", "broadway-properties-ltd", "registry",
    )


def test_any_landlord_without_a_group_is_its_own_group():
    # Registry owner, no rental licence, no claims group (e.g. 2061 Beach Ave).
    from tc_core.export import fallback_group_to_owner

    df = pl.DataFrame([
        _row(owner_name="Solo Owner Ltd.", owner_key="solo-owner-ltd", owner_source="registry",
             licence_holder="(Unknown)", network_name="(Unknown)", network_key="unknown", network_source=None),
        _row(owner_name="(Unknown)", owner_key="unknown", owner_source=None,
             licence_holder="(Unknown)", network_name="(Unknown)", network_key="unknown", network_source=None),
    ])
    df = fallback_group_to_owner(df)
    assert tuple(df.row(0, named=True)[c] for c in ("network_name", "network_key", "network_source")) == (
        "Solo Owner Ltd.", "solo-owner-ltd", "registry",
    )
    assert df["network_key"][1] == "unknown"


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


LISTED = [{"by": TRIBE, "url": "https://example.org/1", "seen": "2026-09-30"}]


def test_a_licence_named_manager_is_marked_as_coming_from_the_licence():
    row = _first(_apply(_row(listings=LISTED)))
    assert (row.managed_by, row.managed_by_source) == (TRIBE, "licence")


def test_a_managers_current_listing_names_it_without_touching_the_owner():
    row = _first(_apply(_row(
        owner_name="Broadway Properties Ltd.", owner_key="broadway-properties-ltd", owner_source="registry",
        licence_holder="Broadway Properties Ltd.",
        network_name="Broadway Properties Ltd.", network_key="broadway-properties-ltd", network_source="registry",
        listings=LISTED,
    )))
    assert (row.managed_by, row.managed_by_source) == (TRIBE, "listing")
    assert (row.owner_name, row.owner_source) == ("Broadway Properties Ltd.", "registry")
    assert (row.network_key, row.network_source) == ("broadway-properties-ltd", "registry")


def test_a_listing_by_a_company_not_in_the_managers_list_sets_no_manager():
    row = _first(_apply(_row(
        owner_name="0888189 B.C. Ltd.", owner_key="0888189-b-c-ltd", owner_source="registry",
        licence_holder="0888189 BC Ltd", network_key="0888189-b-c-ltd", network_source="registry",
        listings=[{"by": "Wall Financial Corporation", "url": "https://example.org/w", "seen": "2026-09-30"}],
    )))
    assert row.managed_by is None and row.managed_by_source is None
    assert row.owner_name == "0888189 B.C. Ltd."


def test_load_listing_aliases_maps_feed_names_to_the_managers_name(tmp_path):
    from tc_core.export import load_listing_aliases

    path = tmp_path / "property_managers.toml"
    path.write_text(
        '[[manager]]\nname = "Tribe Rental Management"\nlisting_names = ["Tribe Rentals"]\n\n'
        '[[manager]]\nname = "Dorset Realty Group"\n'
    )
    assert load_listing_aliases(str(path)) == {
        "tribe-rentals": "Tribe Rental Management",
        "tribe-rental-management": "Tribe Rental Management",
        "dorset-realty-group": "Dorset Realty Group",
    }
    assert load_listing_aliases(None) == {}
