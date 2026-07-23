from __future__ import annotations

import json
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_all_geolocator_schemas_are_valid_draft_2020_12():
    names = [
        "field-resolution-job-v1.schema.json", "imagery-item-v1.schema.json", "candidate-tile-v1.schema.json",
        "registration-candidate-v1.schema.json", "checkpoint-validation-v1.schema.json",
        "field-resolution-review-v1.schema.json",
    ]
    for name in names:
        schema = json.loads((REPO_ROOT / "schemas" / name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
