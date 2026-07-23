"""Independent checkpoint errors measured in physical ground metres."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

import numpy as np

from ..provenance import stable_id, utc_now
from ..spatial import geodesic_distance_m, transform_xy
from .controls import validate_landmarks
from .homography import apply_homography, solve_homography


def validate_checkpoints(
    registration_candidate_id: str,
    controls: list[dict[str, Any]],
    checkpoints: list[dict[str, Any]],
    reviewer: str,
    target_crs: str = "EPSG:3857",
    pass_threshold_m: float = 25,
    downgrade_threshold_m: float = 100,
) -> dict[str, Any]:
    role_summary = validate_landmarks(controls, checkpoints)
    if len(controls) < 4:
        raise ValueError("at least four controls are required")
    if len(checkpoints) < 3:
        raise ValueError("at least three held-out checkpoints are required for independent validation")
    source = [item["source_pixel"] for item in controls]
    destination = [transform_xy(*item["map_coordinate"], "EPSG:4326", target_crs) for item in controls]
    solved = solve_homography(source, destination)
    if solved["degenerate"]:
        raise ValueError("control homography is degenerate")
    predicted_projected = apply_homography(solved["matrix"], [item["source_pixel"] for item in checkpoints])
    errors = []
    resolved_checkpoints = []
    for item, projected in zip(checkpoints, predicted_projected, strict=True):
        predicted_lonlat = transform_xy(*projected, target_crs, "EPSG:4326")
        error = geodesic_distance_m(predicted_lonlat, item["map_coordinate"])
        errors.append(error)
        resolved_checkpoints.append({**item, "predicted_map_coordinate": list(predicted_lonlat), "error_m": error})
    errors_array = np.asarray(errors, dtype=float)
    metrics = {
        "errors_m": [round(value, 6) for value in errors],
        "median_m": round(float(median(errors)), 6),
        "rmse_m": round(float(math.sqrt(np.mean(errors_array ** 2))), 6),
        "maximum_m": round(float(np.max(errors_array)), 6),
        "p95_m": round(float(np.percentile(errors_array, 95)), 6),
    }
    result = "pass" if metrics["p95_m"] <= pass_threshold_m else (
        "downgrade" if metrics["p95_m"] <= downgrade_threshold_m else "reject"
    )
    identity = {"registration_candidate_id": registration_candidate_id, "controls": controls, "checkpoints": checkpoints}
    return {
        "schema_version": "crop-circle-atlas/checkpoint-validation/v1",
        "validation_id": stable_id("val", identity), "registration_candidate_id": registration_candidate_id,
        "controls": controls, "checkpoints": resolved_checkpoints, "metrics": metrics,
        "spatial_distribution": {
            "controls": solved["source_distribution"], "independent_checkpoints": role_summary["independent"],
            "homography_condition": solved["condition"],
        },
        "reviewer": reviewer, "validated_at": utc_now(), "result": result,
        "homography": solved["matrix"].tolist(), "target_crs": target_crs,
    }

