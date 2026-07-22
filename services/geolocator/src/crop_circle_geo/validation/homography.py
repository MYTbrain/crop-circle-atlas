"""Homography solving and stability diagnostics."""

from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from ..spatial import points_spatial_distribution


def _points(values: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError("point coordinates must be an N x 2 array")
    if not np.isfinite(array).all():
        raise ValueError("point coordinates must be finite")
    return array


def apply_homography(matrix: Sequence[Sequence[float]], points: Sequence[Sequence[float]]) -> np.ndarray:
    matrix_array = np.asarray(matrix, dtype=np.float64)
    if matrix_array.shape != (3, 3) or not np.isfinite(matrix_array).all():
        raise ValueError("homography must be one finite 3 x 3 matrix")
    point_array = _points(points).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(point_array, matrix_array).reshape(-1, 2)


def _hartley_normalization(points: np.ndarray) -> np.ndarray:
    centroid = points.mean(axis=0)
    mean_distance = float(np.linalg.norm(points - centroid, axis=1).mean())
    if mean_distance <= np.finfo(float).eps:
        raise ValueError("control points have no spatial extent")
    scale = np.sqrt(2.0) / mean_distance
    return np.array(
        [
            [scale, 0.0, -scale * centroid[0]],
            [0.0, scale, -scale * centroid[1]],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def homography_condition(
    matrix: Sequence[Sequence[float]],
    source_points: Sequence[Sequence[float]] | None = None,
    destination_points: Sequence[Sequence[float]] | None = None,
) -> float:
    """Measure transform stability without penalizing valid CRS translations."""
    value = np.asarray(matrix, dtype=np.float64)
    if value.shape != (3, 3) or not np.isfinite(value).all() or abs(value[2, 2]) < 1e-12:
        return float("inf")
    if source_points is not None and destination_points is not None:
        source_transform = _hartley_normalization(_points(source_points))
        destination_transform = _hartley_normalization(_points(destination_points))
        value = destination_transform @ value @ np.linalg.inv(source_transform)
    value = value / value[2, 2]
    return float(np.linalg.cond(value))


def solve_homography(source, destination, ransac_threshold_px=None):
    src = _points(source)
    dst = _points(destination)
    if len(src) != len(dst) or len(src) < 4:
        raise ValueError("homography requires at least four paired points")
    source_span = np.ptp(src, axis=0)
    destination_span = np.ptp(dst, axis=0)
    source_distribution = points_spatial_distribution(src, max(1.0, source_span[0]), max(1.0, source_span[1]))
    destination_distribution = points_spatial_distribution(dst, max(1.0, destination_span[0]), max(1.0, destination_span[1]))
    if min(source_distribution, destination_distribution) < 0.02:
        raise ValueError("degenerate homography point distribution")
    method = cv2.RANSAC if ransac_threshold_px is not None else 0
    matrix, mask = cv2.findHomography(src, dst, method, float(ransac_threshold_px or 0))
    if matrix is None:
        raise ValueError("homography solve failed")
    condition = homography_condition(matrix, src, dst)
    determinant = float(np.linalg.det(matrix / matrix[2, 2])) if abs(matrix[2, 2]) > 1e-12 else 0
    degenerate = not np.isfinite(condition) or condition > 1e10 or abs(determinant) < 1e-10
    projected = apply_homography(matrix, src)
    errors = np.linalg.norm(projected - dst, axis=1)
    inliers = (mask.ravel() > 0) if mask is not None else np.ones(len(src), dtype=bool)
    return {
        "matrix": matrix,
        "inlier_mask": inliers,
        "errors": errors,
        "condition": condition,
        "determinant": determinant,
        "degenerate": degenerate,
        "source_distribution": source_distribution,
        "destination_distribution": destination_distribution,
    }
