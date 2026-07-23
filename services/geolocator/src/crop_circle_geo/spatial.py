"""CRS-safe geometry and geodesic calculations."""

from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from pyproj import Geod, Transformer
from shapely.geometry import Polygon, shape
from shapely.ops import transform

WGS84_GEOD = Geod(ellps="WGS84")


def transformer(source_crs: str, target_crs: str) -> Transformer:
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


def transform_xy(x: float, y: float, source_crs: str, target_crs: str) -> tuple[float, float]:
    output = transformer(source_crs, target_crs).transform(float(x), float(y))
    return float(output[0]), float(output[1])


def transform_geometry(geometry: dict[str, Any], source_crs: str, target_crs: str) -> dict[str, Any]:
    from shapely.geometry import mapping

    projected = transform(transformer(source_crs, target_crs).transform, shape(geometry))
    return mapping(projected)


def geodesic_distance_m(start_lonlat: Sequence[float], end_lonlat: Sequence[float]) -> float:
    _, _, distance = WGS84_GEOD.inv(
        float(start_lonlat[0]), float(start_lonlat[1]),
        float(end_lonlat[0]), float(end_lonlat[1]),
    )
    return float(abs(distance))


def true_bearing_deg(start_lonlat: Sequence[float], end_lonlat: Sequence[float]) -> float:
    azimuth, _, _ = WGS84_GEOD.inv(
        float(start_lonlat[0]), float(start_lonlat[1]),
        float(end_lonlat[0]), float(end_lonlat[1]),
    )
    return float(azimuth % 360)


def polygon_area_sq_km(geometry: dict[str, Any]) -> float:
    polygon = shape(geometry)
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("search polygon must be non-empty and valid")
    area, _ = WGS84_GEOD.geometry_area_perimeter(polygon)
    return abs(float(area)) / 1_000_000


def validate_search_polygon(
    geometry: dict[str, Any],
    max_area_sq_km: float,
    exclusions: Iterable[dict[str, Any]] = (),
) -> tuple[dict[str, Any], float]:
    from shapely.geometry import mapping

    candidate = shape(geometry)
    if candidate.geom_type != "Polygon" or candidate.is_empty or not candidate.is_valid:
        raise ValueError("search geometry must be one valid GeoJSON Polygon")
    for exclusion in exclusions:
        exclude = shape(exclusion)
        if not exclude.is_valid:
            raise ValueError("exclusion polygon is invalid")
        candidate = candidate.difference(exclude)
    if candidate.is_empty:
        raise ValueError("exclusion polygons remove the entire search area")
    if candidate.geom_type != "Polygon":
        raise ValueError("exclusions must leave one contiguous search polygon")
    area = polygon_area_sq_km(mapping(candidate))
    if area > max_area_sq_km:
        raise ValueError(f"search area {area:.3f} sq km exceeds configured limit {max_area_sq_km:.3f}")
    return mapping(candidate), area


def points_spatial_distribution(points: Sequence[Sequence[float]], width: float, height: float) -> float:
    if len(points) < 4 or width <= 0 or height <= 0:
        return 0.0
    normalized = [(float(x) / width, float(y) / height) for x, y in points]
    hull = Polygon(normalized).convex_hull
    if hull.geom_type != "Polygon":
        return 0.0
    coverage = min(1.0, float(hull.area))
    quadrants = {(min(1, int(x * 2)), min(1, int(y * 2))) for x, y in normalized}
    quadrant_score = len(quadrants) / 4
    return round(math.sqrt(max(0.0, coverage) * quadrant_score), 6)

