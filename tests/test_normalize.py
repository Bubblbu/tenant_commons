from tc_core.normalize import (
    addr_key_from_freeform,
    address_key_variants,
    move_trailing_direction,
    normalize_street,
)


def test_normalize_street_does_not_match_inside_a_longer_word():
    # normalize_street must not turn "Streetcar" into "Stcar" the way a bare
    # substring .replace(" street", " st") would.
    assert normalize_street("Main Streetcar") == "main streetcar"


def test_normalize_street_abbreviates_known_types():
    assert normalize_street("Burrard Street") == "burrard st"
    assert normalize_street("Pine Road") == "pine rd"
    assert normalize_street("Cambie Boulevard") == "cambie blvd"


def test_addr_key_from_freeform_extracts_civic_number():
    assert addr_key_from_freeform("1234 Burrard Street") == "1234 burrard st"


def test_addr_key_from_freeform_strips_a_trailing_footnote_marker():
    # The City's FOI rental list marks some addresses with a trailing "*"
    # footnote (e.g. "1155 Thurlow St*"). clean_address used to strip all
    # non-alphanumeric characters, so this always keyed cleanly; unifying on
    # addr_key_from_freeform (which only stripped periods) silently dropped
    # this row from the props join, losing a real 162-unit building.
    assert addr_key_from_freeform("1155 Thurlow St*") == "1155 thurlow st"


def test_move_trailing_direction_moves_direction_to_front():
    assert move_trailing_direction("Georgia W") == "w georgia"


def test_move_trailing_direction_passes_through_when_no_trailing_direction():
    assert move_trailing_direction("Main St") == "Main St"


def test_move_trailing_direction_passes_none_through():
    assert move_trailing_direction(None) is None


def test_address_key_variants_folds_spelled_out_direction():
    assert address_key_variants("1865 East 10th Avenue") == ["1865 e 10th ave"]


def test_address_key_variants_strips_unit_prefix_as_a_second_candidate():
    assert address_key_variants("#800 - 1047 Barclay St") == [
        "#800 - 1047 barclay st",
        "1047 barclay st",
    ]


# ---------------------------------------------------------------------------
# Canonical spelling rules (normalize_street / addr_key_from_freeform).
# Applied to every key on both sides of every join, so they only make
# spellings agree; see docs/ADDRESS_MATCHING.md. Examples are real source rows.
# ---------------------------------------------------------------------------

import pytest

from tc_core.normalize import AddressMatcher, loose_key


@pytest.mark.parametrize("raw, key", [
    # C1 ordinal suffix added to a bare street number
    ("1771 E 18 AVENUE", "1771 e 18th ave"),
    ("2535 W 8 Av", "2535 w 8th ave"),
    ("100 W 1 Ave", "100 w 1st ave"),
    ("100 W 2 Ave", "100 w 2nd ave"),
    ("100 E 3 Ave", "100 e 3rd ave"),
    ("100 E 11 Ave", "100 e 11th ave"),
    ("100 E 12 Ave", "100 e 12th ave"),
    ("100 E 13 Ave", "100 e 13th ave"),
    ("100 E 21 Ave", "100 e 21st ave"),
    ("100 E 22 Ave", "100 e 22nd ave"),
    ("100 E 23 Ave", "100 e 23rd ave"),
    # C2 direction glued to the street number
    ("131 W49th Avenue", "131 w 49th ave"),
    ("2005 E40th Ave", "2005 e 40th ave"),
    ("2005 E40 Ave", "2005 e 40th ave"),
    # C3 trailing direction moved to the front (FOI style)
    ("962 16TH AVE E", "962 e 16th ave"),
    ("33 PENDER ST E", "33 e pender st"),
    ("3443 7TH AVE W", "3443 w 7th ave"),
    # ...but a trailing N/S after a leading direction stays put
    ("2777 E KENT AVE N", "2777 e kent ave n"),
    ("2777 E KENT AV NORTH", "2777 e kent ave n"),
    ("2922 East Kent Avenue South", "2922 east kent ave s"),  # spelled-out leading direction counts
    # C4 trailing compass words abbreviated
    ("2610 GRANDVIEW HIGHWAY S", "2610 s grandview hwy"),
    ("2610 Grandview Hwy South", "2610 s grandview hwy"),
    # C5 compound leading directions abbreviated
    ("575 Southwest Marine Drive", "575 sw marine dr"),
    ("3608 SE Marine Dr", "3608 se marine dr"),
    # C6 more street-type abbreviations
    ("1267 Marinaside Crescent", "1267 marinaside cres"),
    ("3381 Marquette Cr", "3381 marquette cres"),
    ("7601 Bywell Crt", "7601 bywell ct"),
    # C7 doubled street type (FOI 2024 extract artifact)
    ("309 E CORDOVA ST St", "309 e cordova st"),
    ("1535 W 16TH AVE St", "1535 w 16th ave"),
    # C8 en dash / mis-decoded en dash read as a hyphen
    ("3120–3184 Knight St", "3120-3184 knight st"),
    ("3120â€“3184 Knight St", "3120-3184 knight st"),
])
def test_canonical_rules(raw, key):
    assert addr_key_from_freeform(raw) == key


def test_canonical_rules_leave_ordinary_keys_alone():
    for key in ["1155 thurlow st", "1201 w georgia st", "3212 east blvd", "1415 st georges ave",
                "8 w cordova st", "2898 kingsway", "742 e broadway"]:
        assert addr_key_from_freeform(key) == key


# ---------------------------------------------------------------------------
# Range vs unit (address_key_variants)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, variants", [
    # V1 range: B > A, same side of the street (same parity), B - A <= 200 -> A first, then B
    ("429 - 433 W Pender St", ["429 - 433 w pender st", "429 w pender st", "433 w pender st"]),
    ("7401 - 7469 Talon Square", ["7401 - 7469 talon square", "7401 talon square", "7469 talon square"]),
    # V1 abbreviated range end ("3335-45" = 3335 to 3345)
    ("3335-45 Sophia St", ["3335-45 sophia st", "3335 sophia st", "3345 sophia st"]),
    # V1 "&" / "and" always list civic numbers
    ("7430 & 7460 Heather St", ["7430 & 7460 heather st", "7430 heather st", "7460 heather st"]),
    ("5077 and 5095 Heather St", ["5077 and 5095 heather st", "5077 heather st", "5095 heather st"]),
    # V2 unit prefix: "#", letters, B < A, odd/even mix, or a gap > 200 -> B only, never A
    ("#800 - 1047 Barclay St", ["#800 - 1047 barclay st", "1047 barclay st"]),
    ("303-1210 Jervis St", ["303-1210 jervis st", "1210 jervis st"]),
    ("100-2950 Heather Street", ["100-2950 heather st", "2950 heather st"]),
    ("PH1-1500 Hornby St", ["ph1-1500 hornby st", "1500 hornby st"]),
    ("1205-1210 Jervis St", ["1205-1210 jervis st", "1210 jervis st"]),
    # V3 several addresses: the first one is tried as well
    ("3306 E 5th Ave / 3350 E 5th Ave", ["3306 e 5th ave / 3350 e 5th ave", "3306 e 5th ave"]),
    ("407 & 417 Heatley Ave. ; 684 E Hastings St.",
     ["407 & 417 heatley ave ; 684 e hastings st", "407 & 417 heatley ave", "407 heatley ave", "417 heatley ave"]),
    # V4 spelled-out direction (existing rule)
    ("1865 East 10th Avenue", ["1865 e 10th ave"]),
    ("2922 East Kent Avenue South", ["2922 e kent ave s"]),
])
def test_address_key_variants(raw, variants):
    assert address_key_variants(raw) == variants


def test_a_unit_number_never_matches_the_civic_number_it_looks_like():
    # 303 Jervis St exists too; reading "303-1210" as a range would put the
    # tenant in the wrong building.
    m = AddressMatcher({"303 jervis st", "1210 jervis st"})
    assert m.match("303-1210 Jervis St") == "1210 jervis st"
    assert AddressMatcher({"303 jervis st"}).match("303-1210 Jervis St") is None


# ---------------------------------------------------------------------------
# AddressMatcher: tiers that need the set of known keys
# ---------------------------------------------------------------------------

KNOWN = {
    "1255 kingsway",
    "1266 w 12th ave", "1095 bute st", "1209 e broadway", "2215 e hastings st",
    "1425 w 10th ave", "404 hawks ave", "2290 wall st", "1120 e georgia st",
    "100 main st", "200 main st", "200 main ave",
}


@pytest.mark.parametrize("raw, key", [
    # M1 exact (after canonical rules and variants)
    ("1266 W 12TH AVE", "1266 w 12th ave"),
    # M2 building name after the street type is dropped
    ("1266 W 12TH AVE Appolloni Court", "1266 w 12th ave"),
    ("1095 BUTE ST St James Court", "1095 bute st"),
    ("2290 WALL ST Wave Court", "2290 wall st"),
    ("1209 E BROADWAY Plaza", "1209 e broadway"),
    ("1265 Kingsway Ave", "1255 kingsway"),  # stray type after Kingsway cut, then a secondary address
    # M3 street type missing or wrong, when only one known address fits
    ("2215 E HASTINGS", "2215 e hastings st"),
    ("1425 W 10th", "1425 w 10th ave"),
    ("404 Hawks St.", "404 hawks ave"),
    # M4 range whose ends aren't known but exactly one number inside it is
    ("1102 - 1138 E Georgia St", "1120 e georgia st"),
])
def test_matcher_tiers(raw, key):
    assert AddressMatcher(KNOWN, aliases={"1265 kingsway": "1255 kingsway"}).match(raw) == key


@pytest.mark.parametrize("raw", [
    "200 Main",            # M3 ambiguous: 200 main st and 200 main ave both exist
    "100 Main Mall",       # no street type to cut at: not truncated to "100 main"
    "1415 St Georges Ave", # leading "St" (Saint) is not a street type
    "",
    None,
])
def test_matcher_refuses_to_guess(raw):
    assert AddressMatcher(KNOWN).match(raw) is None


def test_matcher_aliases_resolve_secondary_addresses():
    m = AddressMatcher({"1000 beach ave"}, aliases={"1010 beach ave": "1000 beach ave"})
    assert m.match("1010 Beach Avenue") == "1000 beach ave"


def test_loose_key_drops_only_the_final_street_type():
    assert loose_key("404 hawks ave") == "404 hawks"
    assert loose_key("1415 st georges ave") == "1415 st georges"
    assert loose_key("2898 kingsway") == "2898 kingsway"

