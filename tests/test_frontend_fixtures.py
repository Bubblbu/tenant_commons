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
    "blocks.geojson", "local-area-boundary.geojson",
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
    for name in FILES[:4]:
        assert json.loads((FIXTURES / name).read_text())["schema_version"] == 1, name


def test_fixtures_exercise_registry_owners_and_a_claims_network():
    records = json.loads((FIXTURES / "building_records.json").read_text())["records"].values()
    assert any(r["owner_source"] == "registry" for r in records)
    assert any(r["network_source"] == "claims" for r in records)
    assert json.loads((FIXTURES / "filter_config.json").read_text())["licence_year"] == 2026
