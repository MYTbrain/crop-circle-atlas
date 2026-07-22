"""Conservative registration uncertainty propagation."""

from __future__ import annotations

import math
from typing import Any


def conservative_uncertainty_m(
    checkpoint_metrics: dict[str, Any],
    reference_accuracy_m: float,
    landmark_selection_m: float,
    source_resolution_m: float,
    source_distortion_m: float,
    center_interpretation_m: float,
    control_selection_instability_m: float,
) -> dict[str, Any]:
    named = {
        "reference_accuracy_m": reference_accuracy_m,
        "landmark_selection_m": landmark_selection_m,
        "source_resolution_m": source_resolution_m,
        "source_distortion_m": source_distortion_m,
        "center_interpretation_m": center_interpretation_m,
        "control_selection_instability_m": control_selection_instability_m,
    }
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in named.values()):
        raise ValueError("uncertainty components must be finite and non-negative")
    checkpoint_floor = max(float(checkpoint_metrics.get("p95_m", 0)), float(checkpoint_metrics.get("maximum_m", 0)))
    component_rss = math.sqrt(sum(float(value) ** 2 for value in named.values()))
    total = checkpoint_floor + component_rss
    return {
        "coordinate_uncertainty_m": round(total, 3),
        "method": "held_out_checkpoint_floor_plus_component_rss",
        "checkpoint_floor_m": round(checkpoint_floor, 3),
        "components": {key: round(float(value), 3) for key, value in named.items()},
        "limitations": ["This conservative bound is not a probabilistic confidence interval."],
    }

