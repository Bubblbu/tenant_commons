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


def test_address_key_variants_collapses_a_civic_number_range():
    # "7401 - 7469 Talon Square" matches both the unit-prefix shape (\w+ "-"
    # \d+...) and the range shape (\d+ "-" \d+...), so all three candidates
    # come back, most-literal-first; _match_key in overlays.py tries each in
    # turn and returns the first that hits a known building key.
    assert address_key_variants("7401 - 7469 Talon Square") == [
        "7401 - 7469 talon square",
        "7469 talon square",
        "7401 talon square",
    ]
