"""Active-member rule (internal only, never exported): a member-tagged record
counts unless its latest membership year is old, and a recent NationBuilder
update keeps an older member active."""

from datetime import datetime, timezone

import polars as pl

from tc_core.metrics.membership_metrics import _parse_updated_at, prepare_membership_metrics

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


def test_nationbuilder_export_times_are_read_as_vancouver_time():
    # NationBuilder's export format, in the nation's (Vancouver) time zone.
    assert _parse_updated_at("10/15/2024 9:22 AM") == datetime(2024, 10, 15, 16, 22, tzinfo=timezone.utc)
    assert _parse_updated_at("01/05/2026  9:05 PM") == datetime(2026, 1, 6, 5, 5, tzinfo=timezone.utc)
    assert _parse_updated_at("07/01/2026 12:30 PM") == datetime(2026, 7, 1, 19, 30, tzinfo=timezone.utc)


def test_iso_times_still_parse_and_anything_else_is_none():
    assert _parse_updated_at("2026-09-01T12:00:00+00:00") == datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    assert _parse_updated_at("last tuesday") is None
    assert _parse_updated_at(None) is None


def test_a_recent_update_keeps_an_older_member_active():
    members = pl.DataFrame({
        "building_id": [1, 1, 2],
        "tag_list": ["member, membership-2022", "member, membership-2022", "member"],
        "updated_at": ["09/01/2026 10:00 AM", "09/01/2024 10:00 AM", None],
    })
    active = prepare_membership_metrics(members, NOW)["is_active_default"].to_list()
    assert active == [True, False, True]
