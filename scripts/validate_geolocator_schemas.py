#!/usr/bin/env python3
"""Validate every geolocator schema and the committed benchmark documents."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = [
    "field-resolution-job-v1.schema.json", "imagery-item-v1.schema.json", "candidate-tile-v1.schema.json",
    "registration-candidate-v1.schema.json", "checkpoint-validation-v1.schema.json",
    "field-resolution-review-v1.schema.json",
]


def main() -> int:
    for name in SCHEMAS:
        Draft202012Validator.check_schema(json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8")))
    for name in ("reviewed-cases-input.json", "evaluator-only-ground-truth.json", "mvp-results.json"):
        json.loads((ROOT / "services" / "geolocator" / "benchmarks" / name).read_text(encoding="utf-8"))
    print(f"PASS schemas={len(SCHEMAS)} benchmark_json=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
