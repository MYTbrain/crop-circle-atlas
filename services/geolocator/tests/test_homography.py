from __future__ import annotations

import cv2
import numpy as np
import pytest

from crop_circle_geo.validation.homography import apply_homography, solve_homography


def test_known_projective_transform_is_recovered():
    source = np.float64([[0, 0], [500, 0], [500, 400], [0, 400], [250, 100], [100, 250], [400, 250], [250, 350]])
    expected = np.array([[1.2, 0.08, 130], [-0.04, 0.9, 75], [0.0003, -0.0002, 1]], dtype=float)
    destination = apply_homography(expected, source)
    result = solve_homography(source, destination)
    assert result["degenerate"] is False
    assert np.max(result["errors"]) < 5e-5
    assert np.max(np.abs(result["matrix"] / result["matrix"][2, 2] - expected)) < 5e-6


def test_collinear_homography_is_rejected():
    source = [[0, 0], [1, 0], [2, 0], [3, 0]]
    with pytest.raises(ValueError, match="degenerate"):
        solve_homography(source, source)
