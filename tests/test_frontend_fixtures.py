"""frontend/fixtures/ is generated, never hand-edited: regenerating it must
reproduce the committed files byte for byte, and it must hold no membership."""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "frontend" / "fixtures"
FILES = [
    "filter_config.json", "marker_metadata.json", "building_records.json",
    "networks.json", "blocks.geojson", "local-area-boundary.geojson", "overlay_areas.geojson",
]


def test_committed_fixtures_match_the_generator(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/make_frontend_fixtures.py", "--out", str(tmp_path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in FILES:
        assert (tmp_path / name).read_bytes() == (FIXTURES / name).read_bytes(), (
            f"{name} drifted — regenerate: uv run python scripts/make_frontend_fixtures.py"
        )


def test_fixtures_hold_no_membership():
    markers = json.loads((FIXTURES / "marker_metadata.json").read_text())["markers"]
    assert markers and all("member_count" not in m and "is_vtu" not in m for m in markers)
    totals = json.loads((FIXTURES / "filter_config.json").read_text())["dataset_totals"]
    assert "members" not in totals and "vtu_buildings" not in totals


def test_fixtures_cover_every_source_and_carry_the_contract_version():
    markers = json.loads((FIXTURES / "marker_metadata.json").read_text())["markers"]
    assert {m["source"] for m in markers} == {"building", "overlay_sro", "overlay_coop"}
    for name in FILES[:5]:
        assert json.loads((FIXTURES / name).read_text())["schema_version"] == 3, name


def test_fixtures_exercise_every_popup_case():
    """The popup's cases (spec 2026-10-08): registry owner with an interest
    holder and a differently spelled licence, an SRO with an unmatched
    licensee, a rezoning, a co-op, a claims network."""
    records = list(json.loads((FIXTURES / "building_records.json").read_text())["records"].values())
    networks = json.loads((FIXTURES / "networks.json").read_text())["networks"]
    parties = [p for r in records for p in r["parties"]]
    assert any(p["role"] == "owner" and p["sources"][0]["type"] == "registry" for p in parties)
    assert any(p["role"] == "interest_holder" for p in parties)
    assert any(p["role"] == "licensee" and p["same_as"] == "owner" for p in parties)
    assert any(p["role"] == "licensee" and p["same_as"] is None for p in parties)
    assert any(r["sro"] for r in records) and any(r["coop"] for r in records)
    assert any(r["rezoning"] for r in records)
    assert any(n["tier"] == "confirmed" for n in networks.values())
    assert json.loads((FIXTURES / "filter_config.json").read_text())["licence_year"] == 2026
