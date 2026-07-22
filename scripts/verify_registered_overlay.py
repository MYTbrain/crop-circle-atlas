"""Recalculate persisted public source-photo display footprints.

This proves that published display geometry follows from recorded measurements.
It does not promote a provisional visual or source-coordinate placement to an
accepted georegistration; each observation records its missing controls and
other limitations.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def solve_three_by_three(matrix, values):
    augmented = [list(map(float, row)) + [float(value)] for row, value in zip(matrix, values)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-15:
            raise ValueError("degenerate three-point affine controls")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                left - factor * right
                for left, right in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][3] for row in range(3)]


def fit_affine(control_pairs):
    design = [[*pair["source_xy"], 1.0] for pair in control_pairs]
    x_coefficients = solve_three_by_three(
        design, [pair["reference_xy"][0] for pair in control_pairs]
    )
    y_coefficients = solve_three_by_three(
        design, [pair["reference_xy"][1] for pair in control_pairs]
    )
    return [x_coefficients, y_coefficients, [0.0, 0.0, 1.0]]


def apply_affine(matrix, point):
    x, y = map(float, point)
    return [
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
    ]


def reference_pixel_to_wgs84(mapping, point):
    x, y = map(float, point)
    longitude = (
        mapping["longitude_formula"]["origin_longitude"]
        + (x - mapping["longitude_formula"]["origin_x_px"])
        * mapping["longitude_formula"]["degrees_per_px"]
    )
    latitude = (
        mapping["latitude_formula"]["origin_latitude"]
        - (y - mapping["latitude_formula"]["origin_y_px"])
        * mapping["latitude_formula"]["degrees_per_px_south"]
    )
    return [latitude, longitude]


def local_pixel_to_wgs84(transform, point):
    """Apply the recorded local square-pixel display transform."""
    x, y = map(float, point)
    anchor_x, anchor_y = map(float, transform["anchor_pixel_xy"])
    anchor_latitude, anchor_longitude = map(
        float, transform["anchor_wgs84_lat_lon"]
    )
    scale = float(transform["meters_per_pixel"])
    x_bearing = math.radians(float(transform["source_x_axis_true_bearing_deg"]))
    y_bearing = math.radians(
        float(transform["source_x_axis_true_bearing_deg"])
        + float(transform["source_y_axis_rotation_deg"])
    )
    x_metres = (x - anchor_x) * scale
    y_metres = (y - anchor_y) * scale
    east_metres = math.sin(x_bearing) * x_metres + math.sin(y_bearing) * y_metres
    north_metres = math.cos(x_bearing) * x_metres + math.cos(y_bearing) * y_metres
    latitude = anchor_latitude + north_metres / 111320.0
    longitude = anchor_longitude + east_metres / (
        111320.0 * math.cos(math.radians(anchor_latitude))
    )
    return [latitude, longitude]


def assert_points_close(actual, expected, tolerance, label):
    if len(actual) != len(expected):
        raise AssertionError(f"{label}: point-count mismatch")
    for index, (left, right) in enumerate(zip(actual, expected)):
        if len(left) != len(right) or any(
            not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tolerance)
            for a, b in zip(left, right)
        ):
            raise AssertionError(f"{label}[{index}] mismatch: {left!r} != {right!r}")


def validate_registered_overlay(root=ROOT):
    root = Path(root)
    payload = json.loads(
        (root / "data" / "registered_overlay_observations.json").read_text(encoding="utf-8")
    )
    overlay_payload = json.loads(
        (root / "web" / "data" / "registered_overlays.json").read_text(encoding="utf-8")
    )
    observations = {item["observation_id"]: item for item in payload["observations"]}
    overlays = {item["overlay_id"]: item for item in overlay_payload["overlays"]}
    observation = observations["regobs_hubbard_2000_three_lobe_v1"]
    overlay = overlays[observation["overlay_id"]]

    assert overlay["registration_observation_id"] == observation["observation_id"]
    assert overlay["registration_status"] == observation["classification"]
    assert overlay["formal_alignment_status"] == observation["formal_alignment_status"]
    assert overlay["source_image_sha256"] == observation["source_evidence"]["sha256"]
    assert overlay["source_image_url"] == observation["source_evidence"]["url"]

    fitted = fit_affine(observation["control_pairs"])
    assert_points_close(
        fitted, observation["source_to_reference_affine"], 2e-12, "source affine"
    )
    fitted_controls = [
        apply_affine(fitted, pair["source_xy"]) for pair in observation["control_pairs"]
    ]
    assert_points_close(
        fitted_controls,
        [pair["reference_xy"] for pair in observation["control_pairs"]],
        1e-9,
        "training controls",
    )

    left, top, right, bottom = observation["source_evidence"]["pixel_boundary_extent_xy"]
    source_corners = [[left, top], [right, top], [right, bottom], [left, bottom]]
    reference_corners = [apply_affine(fitted, point) for point in source_corners]
    assert_points_close(
        reference_corners,
        observation["source_frame_corners_in_reference_xy"],
        2e-9,
        "reference corners",
    )
    geographic_corners = [
        reference_pixel_to_wgs84(observation["reference_to_wgs84"], point)
        for point in reference_corners
    ]
    assert_points_close(
        geographic_corners,
        observation["computed_corners_wgs84_lat_lon"],
        5e-13,
        "computed WGS84 corners",
    )
    assert_points_close(geographic_corners, overlay["corners"], 5e-13, "published corners")

    reference_lobes = observation["reference_lobe_detection"]["fit_points_xy"]
    centroid = [sum(point[axis] for point in reference_lobes) / 3 for axis in (0, 1)]
    geographic_centroid = reference_pixel_to_wgs84(observation["reference_to_wgs84"], centroid)
    assert_points_close(
        [geographic_centroid],
        [observation["computed_lobe_centroid_wgs84_lat_lon"]],
        5e-13,
        "computed center",
    )
    assert_points_close([geographic_centroid], [overlay["center"]], 5e-13, "published center")

    envelope = observation["detector_sensitivity_envelope"]
    calculated_envelope_m = envelope["max_corner_displacement_px"] * envelope["scale_m_per_px"]
    assert math.isclose(
        calculated_envelope_m, envelope["max_corner_displacement_m"], abs_tol=0.01
    )
    assert "coordinate_uncertainty_m" not in overlay
    assert overlay["coordinate_uncertainty_status"] == "not_independently_quantified"
    assert overlay["display_corner_sensitivity_envelope_m"] == envelope["published_rounded_envelope_m"]
    assert overlay["display_corner_sensitivity_envelope_m"] >= calculated_envelope_m
    assert "not_confidence_interval" in overlay["display_corner_sensitivity_kind"]
    assert observation["affine_fit"]["independent_checkpoint_count"] == 0

    local_observation_ids = sorted(
        observation_id
        for observation_id, candidate in observations.items()
        if "local_display_transform" in candidate
    )
    for observation_id in local_observation_ids:
        local_observation = observations[observation_id]
        local_overlay = overlays[local_observation["overlay_id"]]
        source = local_observation["source_evidence"]
        transform = local_observation["local_display_transform"]
        assert local_overlay["registration_observation_id"] == observation_id
        assert local_overlay["registration_status"] == local_observation["classification"]
        assert local_overlay["formal_alignment_status"] == local_observation["formal_alignment_status"]
        assert local_overlay["source_image_url"] == source["url"]
        assert local_overlay["source_image_sha256"] == source["sha256"]
        assert local_overlay["source_photo_pixels"] == "remote_source_link_only"
        assert local_overlay["rights_status"] == "not_cleared_for_redistribution"
        assert local_overlay["show_by_default"] is False
        assert transform["independent_ground_checkpoint_count"] >= 0

        left, top, right, bottom = source["pixel_boundary_extent_xy"]
        source_corners = [[left, top], [right, top], [right, bottom], [left, bottom]]
        local_corners = [local_pixel_to_wgs84(transform, point) for point in source_corners]
        assert_points_close(
            local_corners,
            local_observation["computed_corners_wgs84_lat_lon"],
            8e-12,
            f"{observation_id} computed corners",
        )
        assert_points_close(
            local_corners,
            local_overlay["corners"],
            8e-12,
            f"{observation_id} published corners",
        )
        anchor = local_pixel_to_wgs84(transform, transform["anchor_pixel_xy"])
        assert_points_close(
            [anchor], [local_overlay["center"]], 2e-12, f"{observation_id} center"
        )
        assert local_overlay["coordinate_uncertainty_m"] == local_observation[
            "source_report_controls"
        ]["coordinate_uncertainty_m"]

    projective_observation_ids = sorted(
        observation_id
        for observation_id, candidate in observations.items()
        if "projective_display_transform" in candidate
    )
    for observation_id in projective_observation_ids:
        projective_observation = observations[observation_id]
        projective_overlay = overlays[projective_observation["overlay_id"]]
        source = projective_observation["source_evidence"]
        transform = projective_observation["projective_display_transform"]
        assert projective_overlay["registration_observation_id"] == observation_id
        assert projective_overlay["registration_status"] == projective_observation["classification"]
        assert projective_overlay["formal_alignment_status"] == projective_observation["formal_alignment_status"]
        assert projective_overlay["source_image_url"] == source["url"]
        assert projective_overlay["source_image_sha256"] == source["sha256"]
        if "wikimedia.org" in projective_overlay["source_image_url"]:
            assert projective_overlay["source_photo_pixels"] == "remote_open_license_source_link_only"
            assert projective_overlay["rights_status"] in {"CC BY-SA 3.0", "CC BY 2.0"}
            assert projective_overlay["embedding_allowed"] is True
            assert projective_overlay["license_url"].startswith(
                "https://creativecommons.org/licenses/by"
            )
            assert projective_overlay["rights_attribution"]
        else:
            assert projective_overlay["source_photo_pixels"] in {
                "remote_source_link_only",
                "remote_source_on_explicit_user_action",
            }
            assert projective_overlay["rights_status"] == "not_cleared_for_redistribution"
            assert projective_overlay["embedding_allowed"] is True
        assert projective_overlay["show_by_default"] is False
        left, top, right, bottom = source["pixel_boundary_extent_xy"]
        assert transform["source_frame_corners_xy"] == [
            [left, top], [right, top], [right, bottom], [left, bottom]
        ]
        assert_points_close(
            transform["corners_wgs84_lat_lon"],
            projective_observation["computed_corners_wgs84_lat_lon"],
            1e-12,
            f"{observation_id} projective corners",
        )
        assert_points_close(
            transform["corners_wgs84_lat_lon"],
            projective_overlay["corners"],
            1e-12,
            f"{observation_id} published projective corners",
        )
        assert projective_overlay["coordinate_uncertainty_m"] == projective_observation[
            "source_report_controls"
        ]["coordinate_uncertainty_m"]

    assert observations["regobs_jupiter_2005_source_gps_v1"][
        "local_display_transform"
    ]["orientation_status"] == "unresolved_display_assumption"
    assert observations["regobs_wausau_1997_usgs_followup_v1"]["quality"][
        "status"
    ] == "useful_provisional_landmark_registration"
    return observation


if __name__ == "__main__":
    result = validate_registered_overlay()
    print(
        "PASS registered overlay observation: "
        f"{result['observation_id']} remains {result['classification']}"
    )
