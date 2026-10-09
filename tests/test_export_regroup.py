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


def test_overlay_point_joins_its_claims_network_without_a_registry_filing():
    from tc_core.export import apply_registry_to_overlays
    from tc_core.metrics.portfolios import Portfolio

    df = pl.DataFrame({
        "source": ["overlay_sro"], "addr_key": ["117 main st"],
        "owner_name": ["(Unknown)"], "owner_key": ["unknown"], "owner_source": [None],
        "registered_owners": [[]], "registry_pids": [[]], "registry_retrieved": [None],
        "registry_owner_pids": [[]], "interest_holders": [[]], "registry_no_filing": [None],
        "network_key": ["unknown"], "network_name": ["(Unknown)"], "network_source": [None],
        "network_name_source": [None], "network_entities": [None],
        "network_properties_on_title": [None], "network_evidence": [None],
    }, schema_overrides={c: pl.Object for c in (
        "registered_owners", "registry_pids", "registry_owner_pids", "interest_holders",
        "network_entities", "network_evidence")} | {
        "owner_source": pl.String, "registry_retrieved": pl.String, "registry_no_filing": pl.String,
        "network_source": pl.String, "network_name_source": pl.String,
        "network_properties_on_title": pl.Int64})
    port = Portfolio(portfolio_key="hansum", portfolio_name="Shun Chi Company Ltd.", name_source="default",
                     entities=["Shun Chi Company Ltd."], addr_keys={"117 main st"},
                     evidence={"registry": 0, "city_records": 1, "vtu_research": 0})
    row = _first(apply_registry_to_overlays(df, {}, {"117 main st": port}, {}, {}))
    assert (row.network_key, row.network_source) == ("net:hansum", "claims")
    assert row.owner_source is None  # no filing: the owner still comes from the SRO list
