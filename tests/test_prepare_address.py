from tc_core.prepare.address import clean_address, fix_street_names


def test_clean_address_abbreviates_and_strips():
    assert clean_address("1234 Burrard Street") == "1234 burrard st"
    assert clean_address("10 W. 5th Ave") == "10 w 5th av"
    assert clean_address("5 Main Way") == "5 main w"
    assert clean_address("77 Pine Road") == "77 pine rd"


def test_clean_address_passes_none_through():
    assert clean_address(None) is None


def test_fix_street_names_moves_trailing_direction_to_front():
    assert fix_street_names("Georgia W") == "w georgia"
    assert fix_street_names("Main St") == "Main St"
    assert fix_street_names(None) is None
