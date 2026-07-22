from __future__ import annotations

import pytest

from crop_circle_geo.spatial import transform_xy
from crop_circle_geo.validation.checkpoints import validate_checkpoints
from crop_circle_geo.validation.controls import validate_landmarks


def landmark(identifier, role, pixel):
    x = 1_000_000 + pixel[0] * 2
    y = 5_000_000 - pixel[1] * 2
    lonlat = transform_xy(x, y, "EPSG:3857", "EPSG:4326")
    return {
        "landmark_id": identifier, "role": role, "description": "persistent building corner",
        "source_pixel": list(pixel), "map_coordinate": list(lonlat), "reference_imagery_id": "reference-ortho",
        "landmark_uncertainty_m": 1,
    }


def test_checkpoints_are_independent_and_use_physical_ground_metres():
    controls = [landmark(f"c{index}", "control", pixel) for index, pixel in enumerate(
        [(0, 0), (500, 0), (500, 400), (0, 400), (250, 40), (460, 200), (250, 360), (40, 200)]
    )]
    checkpoints = [landmark(f"p{index}", "checkpoint", pixel) for index, pixel in enumerate([(150, 120), (350, 150), (220, 300)])]
    result = validate_checkpoints("reg_test", controls, checkpoints, "Reviewer")
    assert result["result"] == "pass"
    assert result["metrics"]["maximum_m"] < 0.01
    assert result["spatial_distribution"]["independent_checkpoints"] is True


def test_checkpoint_reuse_and_transient_controls_fail_closed():
    control = landmark("same", "control", (0, 0))
    checkpoint = {**landmark("same", "checkpoint", (10, 10))}
    with pytest.raises(ValueError, match="never be used as controls"):
        validate_landmarks([control], [checkpoint])
    with pytest.raises(ValueError, match="transient"):
        validate_landmarks([{**control, "description": "crop formation center"}], [])

