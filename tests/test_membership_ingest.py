"""ingest_membership() reads only the allow-listed NationBuilder columns and
treats placeholder text in hand-typed fields as missing."""

from tc_core.ingest.membership import ALLOWED_MEMBERSHIP_COLUMNS, load_membership_frame

HEADER = "nationbuilder_id,email,primary_address1,phone,tag_list,updated_at\n"


def _export(tmp_path, *rows):
    path = tmp_path / "membership_full.csv"
    path.write_text(HEADER + "".join(rows))
    return str(path)


def test_only_allow_listed_columns_are_read(tmp_path):
    df = load_membership_frame(_export(tmp_path, "7,a@b.c,100 Main St,555,member,2026-01-01\n"))
    assert set(df.columns) == {*ALLOWED_MEMBERSHIP_COLUMNS, "addr_key"}


def test_placeholder_addresses_are_missing(tmp_path):
    df = load_membership_frame(_export(tmp_path, "7,a@b.c,N/A,555,member,2026-01-01\n"))
    row = df.row(0, named=True)
    assert row["primary_address1"] is None
    assert row["addr_key"] in (None, "")
