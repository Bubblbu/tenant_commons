"""A licence-name group must not stand in for a registry owner's network when
the licence holder is someone else (final review, 2026-10-08)."""

from types import SimpleNamespace

import polars as pl

from tc_core.export import regroup_registry_owners


def _frame(**cols):
    base = {
        "owner_name": ["X HOLDINGS LTD."], "owner_key": ["x-holdings-ltd"], "owner_source": ["registry"],
        "licence_holder": ["Y Properties Ltd"],
        "network_key": ["y-properties-ltd"], "network_name": ["Y Properties Ltd"], "network_source": ["licence"],
    }
    base.update({k: [v] for k, v in cols.items()})
    return pl.DataFrame(base)


def _first(df):
    return SimpleNamespace(**df.row(0, named=True))


def test_registry_owner_leaves_a_different_licence_holders_group():
    row = _first(regroup_registry_owners(_frame()))
    assert (row.network_key, row.network_name, row.network_source) == (
        "x-holdings-ltd", "X HOLDINGS LTD.", "registry")


def test_licence_group_kept_when_the_licence_names_the_owner():
    row = _first(regroup_registry_owners(_frame(
        licence_holder="X Holdings Ltd", network_key="x-holdings-ltd-2", network_name="X Holdings Ltd")))
    assert (row.network_key, row.network_source) == ("x-holdings-ltd-2", "licence")


def test_claims_networks_and_licence_owners_untouched():
    claims = _first(regroup_registry_owners(_frame(network_key="net:z", network_source="claims")))
    assert claims.network_key == "net:z"
    licence = _first(regroup_registry_owners(_frame(owner_source="licence")))
    assert licence.network_key == "y-properties-ltd"
