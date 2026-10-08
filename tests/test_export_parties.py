"""Parties in roles (spec 2026-10-08, section 3)."""

from tc_core.export_parties import build_parties, match_key


def row(**kw):
    base = dict(
        owner_name="(Unknown)", owner_key="unknown", owner_source=None,
        registry_owner_pids=[], registry_retrieved=None, interest_holders=[],
        licence_holder="(Unknown)", managed_by=None, managed_by_source=None, listings=[],
        sro_owner=None, sro_operator=None,
    )
    base.update(kw)
    return base


def roles(parties):
    return [(p.role, p.name, p.same_as) for p in parties]


def test_match_key_ignores_punctuation_suffixes_and_plurals():
    assert match_key("0888189 B.C. Ltd.") == match_key("0888189 BC Ltd")
    assert match_key("Yorkshire Place Apts. Ltd.") == match_key("Yorkshire Place Apt Ltd")
    assert match_key("The Pacific Investment Corporation Limited") == match_key("Pacific Investment Corporation Ltd")
    assert match_key("GLR Properties") != match_key("Concert Properties")


def test_registry_owner_with_licence_spelled_differently():  # 2145 York Ave
    parties = build_parties(row(
        owner_name="Yorkshire Place Apts. Ltd.", owner_source="registry",
        registry_owner_pids=[{"name": "Yorkshire Place Apts. Ltd.", "pids": ["007-273-924"]}],
        registry_retrieved="2024-05-03",
        licence_holder="Yorkshire Place Apt Ltd",
        managed_by="Cascadia Apartment Rentals", managed_by_source="listing",
        listings=[{"by": "Cascadia Apartment Rentals", "url": "https://cascadia.example/l/1", "seen": "2026-09-30"}],
    ), {})
    assert roles(parties) == [
        ("owner", "Yorkshire Place Apts. Ltd.", None),
        ("manager", "Cascadia Apartment Rentals", None),
        ("licensee", "Yorkshire Place Apt Ltd", "owner"),
    ]
    owner = parties[0]
    assert owner.pids == ["007-273-924"]
    assert [s.type for s in owner.sources] == ["registry", "licence"]
    assert owner.sources[0].as_of == "2024-05-03"
    assert parties[1].sources[0].url == "https://cascadia.example/l/1"


def test_sro_owner_operator_and_unmatched_licensee():  # 518 Richards St
    parties = build_parties(row(
        owner_name="BC Housing", owner_source="sro_list", sro_owner="BC Housing",
        sro_operator="Atira Property Management",
        licence_holder="PHS Community Services Society",
    ), {})
    assert roles(parties) == [
        ("owner", "BC Housing", None),
        ("manager", "Atira Property Management", None),
        ("licensee", "PHS Community Services Society", None),
    ]
    assert parties[0].sources[0].type == "sro_inventory"


def test_manager_holding_the_licence():  # Dorset
    parties = build_parties(row(
        licence_holder="Dorset Realty Group Canada Ltd",
        managed_by="Dorset Realty Group Canada Ltd", managed_by_source="licence",
    ), {})
    assert roles(parties) == [
        ("manager", "Dorset Realty Group Canada Ltd", None),
        ("licensee", "Dorset Realty Group Canada Ltd", "manager"),
    ]


def test_registry_owner_wins_over_sro_owner():
    parties = build_parties(row(
        owner_name="REAL OWNER LTD.", owner_source="registry",
        registry_owner_pids=[{"name": "REAL OWNER LTD.", "pids": ["011-111-111"]}],
        sro_owner="BC Housing",
    ), {})
    assert [p.name for p in parties if p.role == "owner"] == ["REAL OWNER LTD."]


def test_joint_and_separate_owners_keep_their_pids():
    parties = build_parties(row(
        owner_name="B HOLDINGS LTD.", owner_source="registry",
        registry_owner_pids=[
            {"name": "B HOLDINGS LTD.", "pids": ["011-111-111", "022-222-222"]},
            {"name": "A HOLDINGS LTD.", "pids": ["011-111-111"]},
        ],
    ), {})
    assert [(p.name, p.pids) for p in parties] == [
        ("B HOLDINGS LTD.", ["011-111-111", "022-222-222"]),
        ("A HOLDINGS LTD.", ["011-111-111"]),
    ]


def test_interest_holders_are_typed():
    parties = build_parties(row(
        owner_name="EZELIYA HOLDINGS INC.", owner_source="registry",
        registry_owner_pids=[{"name": "EZELIYA HOLDINGS INC.", "pids": ["011-111-111"]}],
        interest_holders=[{"name": "KARA, JAMIL", "interest": "trustee", "pids": ["011-111-111"]}],
    ), {})
    holder = [p for p in parties if p.role == "interest_holder"][0]
    assert (holder.name, holder.interest, holder.pids) == ("KARA, JAMIL", "trustee", ["011-111-111"])


def test_same_entity_cluster_links_licensee_to_owner():
    clusters = {"0733603 BC Ltd": "0733603 BC Ltd / Phil Kim", "Phil Kim": "0733603 BC Ltd / Phil Kim"}
    parties = build_parties(row(
        owner_name="0733603 BC Ltd", owner_source="registry",
        registry_owner_pids=[{"name": "0733603 BC Ltd", "pids": ["011-111-111"]}],
        licence_holder="Phil Kim",
    ), clusters)
    assert parties[-1].same_as == "owner"


def test_listing_url_must_be_http_and_seen_must_be_a_date():
    parties = build_parties(row(
        listings=[{"by": "Evil Co", "url": "javascript:alert(1)", "seen": "last week"}],
    ), {})
    assert parties[0].sources[0].url is None
    assert parties[0].sources[0].as_of is None


def test_overlay_row_has_no_parties():
    assert build_parties(row(), {}) == []
