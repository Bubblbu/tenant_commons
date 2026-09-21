import pandas as pd

from overlay_fingerprint import fingerprint_overlays


def _frame():
    return pd.DataFrame(
        {
            "addr_key": ["100 main st", "200 oak st", "300 elm st"],
            "local_area": ["Downtown", "Kitsilano", "Downtown"],
            "is_coop": [True, False, False],
            "is_sro": [False, True, False],
        }
    )


def test_counts_by_type():
    fp = fingerprint_overlays(_frame())
    assert fp["counts"] == {"coop": 1, "sro": 1, "none": 1, "total": 3}


def test_keys_are_sorted_and_keyed_on_addr_key():
    fp = fingerprint_overlays(_frame())
    assert fp["keys"] == [
        ["100 main st", "coop", "Downtown"],
        ["200 oak st", "sro", "Kitsilano"],
        ["300 elm st", "none", "Downtown"],
    ]


def test_is_deterministic_regardless_of_row_order():
    a = fingerprint_overlays(_frame())
    b = fingerprint_overlays(_frame().iloc[::-1].reset_index(drop=True))
    assert a == b
