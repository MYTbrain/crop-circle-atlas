"""Transform registered endpoints into true-north bearings."""

from __future__ import annotations

import math
from typing import Any, Sequence

from ..spatial import geodesic_distance_m, transform_xy, true_bearing_deg
from ..validation.homography import apply_homography


def _tile_pixel_to_lonlat(tile: dict[str, Any], point: Sequence[float]) -> tuple[float, float]:
    west, south, east, north = map(float, tile["bounds"])
    width, height = map(float, tile["dimensions_px"])
    x = west + float(point[0]) / width * (east - west)
    y = north - float(point[1]) / height * (north - south)
    return transform_xy(x, y, tile["crs"], "EPSG:4326")


def measure_registered_component(
    homography_source_to_tile: Sequence[Sequence[float]],
    tile: dict[str, Any],
    endpoint_a_px: Sequence[float],
    endpoint_b_px: Sequence[float],
    endpoint_uncertainty_m: float,
    directionality: str = "bidirectional",
) -> dict[str, Any]:
    if directionality not in {"forward", "reverse", "bidirectional"}:
        raise ValueError("directionality must be forward, reverse, or bidirectional")
    transformed = apply_homography(homography_source_to_tile, [endpoint_a_px, endpoint_b_px])
    a = _tile_pixel_to_lonlat(tile, transformed[0])
    b = _tile_pixel_to_lonlat(tile, transformed[1])
    length_m = geodesic_distance_m(a, b)
    if length_m <= 0:
        raise ValueError("straight-component endpoints must be distinct")
    forward = true_bearing_deg(a, b)
    reverse = true_bearing_deg(b, a)
    selected = reverse if directionality == "reverse" else forward
    angular_uncertainty = math.degrees(math.atan2(2 * max(0, endpoint_uncertainty_m), length_m))
    midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    return {
        "endpoint_a": {"longitude": a[0], "latitude": a[1]},
        "endpoint_b": {"longitude": b[0], "latitude": b[1]},
        "forward_azimuth_true_deg": forward, "reverse_azimuth_true_deg": reverse,
        "selected_azimuth_true_deg": selected, "azimuth_uncertainty_deg": angular_uncertainty,
        "directionality": directionality, "length_m": length_m,
        "ray_origin": {"longitude": midpoint[0], "latitude": midpoint[1], "uncertainty_m": endpoint_uncertainty_m},
        "status": "provisional_pending_explicit_promotion",
        "formal_alignment_eligible": False,
    }

