"""Benchmark manifest runner; real-world scoring requires evaluator mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .manifest import load_evaluator_ground_truth, load_input_manifest


def describe_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = load_input_manifest(manifest_path)
    cases = manifest.get("cases", [])
    return {
        "case_count": len(cases),
        "open_license_pixel_cases": sum(case.get("source_image", {}).get("rights_status") == "cc_by_sa" for case in cases),
        "metadata_only_cases": sum(not case.get("source_image", {}).get("benchmark_pixels_permitted", False) for case in cases),
        "warning": "Manifest description is not a performance result; evaluator coordinates remain isolated.",
    }


def load_for_evaluation(manifest_path: Path, ground_truth_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return load_input_manifest(manifest_path), load_evaluator_ground_truth(ground_truth_path, evaluator=True)

