"""Benchmark input loading with evaluator-coordinate isolation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


FORBIDDEN_INPUT_KEYS = {
    "ground_truth", "exact_coordinate", "exact_coordinates", "accepted_footprint",
    "site_latitude", "site_longitude", "accepted_site_latitude", "accepted_site_longitude",
    "evaluator_only", "final_coordinate", "final_coordinates",
}


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    violations = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.lower() in FORBIDDEN_INPUT_KEYS:
                violations.append(child_path)
            violations.extend(_walk_forbidden(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return violations


def load_input_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    violations = _walk_forbidden(payload)
    if violations:
        raise ValueError("benchmark input leaks evaluator-only data at: " + ", ".join(violations))
    if payload.get("schema_version") != "crop-circle-atlas/geolocator-benchmark-input/v1":
        raise ValueError("unsupported benchmark input manifest")
    return payload


def load_evaluator_ground_truth(path: Path, evaluator: bool = False) -> dict[str, Any]:
    if not evaluator:
        raise PermissionError("evaluator-only ground truth is unavailable to search and matching modules")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "crop-circle-atlas/geolocator-benchmark-ground-truth/v1":
        raise ValueError("unsupported evaluator ground-truth manifest")
    return payload

