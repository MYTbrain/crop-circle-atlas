from __future__ import annotations

import json
from pathlib import Path

import pytest

from crop_circle_geo.benchmark.manifest import load_evaluator_ground_truth, load_input_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_committed_input_manifest_contains_no_evaluator_coordinates():
    manifest = load_input_manifest(ROOT / "benchmarks" / "reviewed-cases-input.json")
    assert len(manifest["cases"]) == 9
    assert sum(case["source_image"]["benchmark_pixels_permitted"] for case in manifest["cases"]) == 1


def test_ground_truth_requires_explicit_evaluator_mode_and_leaks_are_rejected(tmp_path):
    ground_truth = ROOT / "benchmarks" / "evaluator-only-ground-truth.json"
    with pytest.raises(PermissionError):
        load_evaluator_ground_truth(ground_truth)
    assert len(load_evaluator_ground_truth(ground_truth, evaluator=True)["cases"]) == 9
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "crop-circle-atlas/geolocator-benchmark-input/v1", "exact_coordinates": [1, 2]}), encoding="utf-8")
    with pytest.raises(ValueError, match="leaks evaluator-only"):
        load_input_manifest(bad)
