from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from conftest import create_synthetic_raster
from crop_circle_geo.imagery.local_raster import LocalRasterProvider
from crop_circle_geo.matching.opencv_sift import OpenCvSiftMatcher
from crop_circle_geo.tiles import generate_candidate_tiles


REPO_ROOT = Path(__file__).resolve().parents[3]


def validate(name, payload):
    schema = json.loads((REPO_ROOT / "schemas" / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(payload)


def test_imagery_tile_and_registration_artifacts_match_schemas(tmp_path):
    raster_path, source_path, _ = create_synthetic_raster(tmp_path)
    item = LocalRasterProvider(tmp_path)._normalize(raster_path)
    validate("imagery-item-v1.schema.json", item)
    tile = generate_candidate_tiles(item, tmp_path / "cache", 512, 0, (1,), (0,), ("color",), 10)["tiles"][0]
    validate("candidate-tile-v1.schema.json", tile)
    candidate = OpenCvSiftMatcher(ratio_threshold=0.82).match(source_path, tile, 1)
    validate("registration-candidate-v1.schema.json", candidate)
