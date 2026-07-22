from __future__ import annotations

import pytest

from crop_circle_geo.spatial import (
    geodesic_distance_m,
    points_spatial_distribution,
    polygon_area_sq_km,
    transform_xy,
    true_bearing_deg,
    validate_search_polygon,
)


def test_crs_round_trip_and_physical_ground_distance():
    lon, lat = -122.726, 45.171
    x, y = transform_xy(lon, lat, "EPSG:4326", "EPSG:3857")
    round_lon, round_lat = transform_xy(x, y, "EPSG:3857", "EPSG:4326")
    assert round_lon == pytest.approx(lon, abs=1e-8)
    assert round_lat == pytest.approx(lat, abs=1e-8)
    assert 78 < geodesic_distance_m((lon, lat), (lon + 0.001, lat)) < 80


def test_search_polygon_is_bounded_and_never_reclassified_as_a_site():
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-122.73, 45.17], [-122.72, 45.17], [-122.72, 45.18], [-122.73, 45.18], [-122.73, 45.17]]],
    }
    geometry, area = validate_search_polygon(polygon, 10)
    assert geometry["type"] == "Polygon"
    assert 0.8 < area < 0.9
    assert polygon_area_sq_km(geometry) == pytest.approx(area)
    with pytest.raises(ValueError, match="exceeds configured limit"):
        validate_search_polygon(polygon, 0.1)


def test_true_bearing_and_distribution_score():
    assert true_bearing_deg((0, 0), (0, 1)) == pytest.approx(0, abs=0.01)
    assert true_bearing_deg((0, 0), (1, 0)) == pytest.approx(90, abs=0.01)
    distributed = points_spatial_distribution([(5, 5), (95, 5), (95, 95), (5, 95)], 100, 100)
    clustered = points_spatial_distribution([(5, 5), (6, 5), (6, 6), (5, 6)], 100, 100)
    assert distributed > 0.8
    assert clustered < 0.1

