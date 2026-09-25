import pytest
import requests

from tc_core.fetch.cov_open_data import download, fetch_all, plan_downloads


class FakeResponse:
    def __init__(self, chunks=(b"a;b\n", b"1;2\n"), fail_at=None, ok=True):
        self.chunks, self.fail_at, self.ok = chunks, fail_at, ok

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError("500")

    def iter_content(self, size):
        for i, chunk in enumerate(self.chunks):
            if i == self.fail_at:
                raise ConnectionError("dropped")
            yield chunk


def test_plan_covers_every_consumer_format(tmp_path):
    names = {d.out_path.name for d in plan_downloads(tmp_path)}
    assert names == {
        "local-area-boundary.csv", "local-area-boundary.geojson",
        "property-addresses.csv", "property-addresses.geojson",
        "property-tax-report.geojson",
        "business-licences.geojson",
        "non-market-housing.geojson",
        "rental-standards-current-issues.geojson",
        "city-owned-properties.csv",
        "block-outlines.csv",
        "block-numbers.csv",
    }


def test_only_the_tax_report_is_refined(tmp_path):
    plan = {d.dataset: d for d in plan_downloads(tmp_path, tax_report_year=2027)}
    assert plan["property-tax-report"].refine == "report_year:2027"
    assert all(d.refine is None for n, d in plan.items() if n != "property-tax-report")


def test_url_shape(tmp_path):
    (dl,) = plan_downloads(tmp_path, only=["block-numbers"])
    assert dl.url == (
        "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/"
        "block-numbers/exports/csv"
    )


def test_unknown_dataset_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="nope"):
        plan_downloads(tmp_path, only=["nope"])


def test_download_writes_file_and_passes_refine(tmp_path):
    (dl,) = plan_downloads(tmp_path, only=["property-tax-report"])
    seen = {}

    def get(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse()

    assert download(dl, get=get) == 8
    assert dl.out_path.read_bytes() == b"a;b\n1;2\n"
    assert seen["params"] == {"refine": "report_year:2026"}


def test_failed_download_keeps_the_existing_file(tmp_path):
    (dl,) = plan_downloads(tmp_path, only=["block-numbers"])
    dl.out_path.write_bytes(b"old data")

    with pytest.raises(ConnectionError):
        download(dl, get=lambda url, **kw: FakeResponse(fail_at=1))

    assert dl.out_path.read_bytes() == b"old data"
    assert not list(tmp_path.glob("*.part"))


def test_fetch_all_logs_each_file(tmp_path):
    lines = []
    done = fetch_all(
        tmp_path, only=["block-numbers"], get=lambda url, **kw: FakeResponse(), log=lines.append
    )
    assert [d.out_path.name for d in done] == ["block-numbers.csv"]
    assert any("block-numbers.csv" in line for line in lines)
