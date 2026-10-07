import json

import pytest

from tc_core.prepare.io import load_polars


def _feature_collection(tmp_path, features):
    path = tmp_path / "layer.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


@pytest.mark.filterwarnings("error::DeprecationWarning")
def test_each_feature_becomes_a_row_of_its_properties(tmp_path):
    features = [
        {"type": "Feature", "geometry": None, "properties": {"address": "179 main st", "units": 46}},
        {"type": "Feature", "geometry": None, "properties": {"address": "41 e hastings st", "units": 78}},
    ]
    df = load_polars(_feature_collection(tmp_path, features))
    assert df.to_dicts() == [p["properties"] for p in features]

