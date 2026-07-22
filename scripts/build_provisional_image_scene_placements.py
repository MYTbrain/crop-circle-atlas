"""Build reproducible, explicitly provisional source-photo scene placements.

The input records a source-image anchor, local display scale, and orientation
basis.  The generated footprints are useful map displays, not accepted survey
georegistrations, and are kept out of the alignment-analysis population.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "provisional_image_scene_placements.json"
CATALOG_PATH = ROOT / "web" / "data" / "formation_images.json"
OVERLAYS_PATH = ROOT / "web" / "data" / "registered_overlays.json"
OBSERVATIONS_PATH = ROOT / "data" / "registered_overlay_observations.json"


def local_pixel_to_wgs84(transform: dict, point: list[float]) -> list[float]:
    """Apply the documented local square-pixel display transform."""
    x, y = map(float, point)
    anchor_x, anchor_y = map(float, transform["anchor_pixel_xy"])
    anchor_latitude, anchor_longitude = map(
        float, transform["anchor_wgs84_lat_lon"]
    )
    scale = float(transform["meters_per_pixel"])
    x_bearing = math.radians(float(transform["source_x_axis_true_bearing_deg"]))
    y_bearing = math.radians(
        float(transform["source_x_axis_true_bearing_deg"])
        + float(transform.get("source_y_axis_rotation_deg", 90.0))
    )
    x_metres = (x - anchor_x) * scale
    y_metres = (y - anchor_y) * scale
    east_metres = math.sin(x_bearing) * x_metres + math.sin(y_bearing) * y_metres
    north_metres = math.cos(x_bearing) * x_metres + math.cos(y_bearing) * y_metres
    latitude = anchor_latitude + north_metres / 111_320.0
    longitude = anchor_longitude + east_metres / (
        111_320.0 * math.cos(math.radians(anchor_latitude))
    )
    return [round(latitude, 12), round(longitude, 12)]


def _catalog_images() -> dict[tuple[str, str], dict]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    result = {}
    for formation_id, images in payload["images_by_formation"].items():
        for image in images:
            result[(formation_id, image["image_url"])] = image
    return result


def _replace_managed(existing: list[dict], generated: list[dict], key: str) -> list[dict]:
    managed_ids = {item[key] for item in generated}
    retained = [item for item in existing if item.get(key) not in managed_ids]
    return retained + generated


def build(root: Path = ROOT) -> tuple[int, int]:
    if Path(root).resolve() != ROOT.resolve():
        raise ValueError("custom roots are not supported by this builder")
    specs_payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    specs = specs_payload["placements"]
    catalog = _catalog_images()
    overlays_payload = json.loads(OVERLAYS_PATH.read_text(encoding="utf-8"))
    observations_payload = json.loads(OBSERVATIONS_PATH.read_text(encoding="utf-8"))

    generated_overlays = []
    generated_observations = []
    seen_overlay_ids = set()
    seen_observation_ids = set()
    for spec in specs:
        overlay_id = spec["overlay_id"]
        observation_id = spec["observation_id"]
        if overlay_id in seen_overlay_ids or observation_id in seen_observation_ids:
            raise ValueError(f"duplicate placement identifier in input: {overlay_id}")
        seen_overlay_ids.add(overlay_id)
        seen_observation_ids.add(observation_id)

        image = catalog.get((spec["formation_id"], spec["source_image_url"]))
        if not image:
            raise ValueError(
                f"source image is not linked to {spec['formation_id']}: "
                f"{spec['source_image_url']}"
            )
        width = int(image["width"])
        height = int(image["height"])
        anchor_x, anchor_y = map(float, spec["anchor_pixel_xy"])
        if not (0 <= anchor_x <= width and 0 <= anchor_y <= height):
            raise ValueError(f"anchor pixel is outside source frame: {overlay_id}")
        latitude, longitude = map(float, spec["anchor_wgs84_lat_lon"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError(f"invalid WGS84 anchor: {overlay_id}")
        if float(spec["meters_per_pixel"]) <= 0:
            raise ValueError(f"meters_per_pixel must be positive: {overlay_id}")

        transform = {
            "model": "local_square_pixel_provisional_scene_placement",
            "anchor_pixel_xy": [anchor_x, anchor_y],
            "anchor_wgs84_lat_lon": [latitude, longitude],
            "meters_per_pixel": float(spec["meters_per_pixel"]),
            "source_x_axis_true_bearing_deg": float(
                spec["source_x_axis_true_bearing_deg"]
            ),
            "source_y_axis_rotation_deg": float(
                spec.get("source_y_axis_rotation_deg", 90.0)
            ),
            "scale_basis": spec["scale_basis"],
            "orientation_basis": spec["orientation_basis"],
            "orientation_status": spec["orientation_status"],
            "independent_ground_checkpoint_count": int(
                spec.get("independent_ground_checkpoint_count", 0)
            ),
        }
        pixel_corners = [[0, 0], [width, 0], [width, height], [0, height]]
        if spec.get("corners_wgs84"):
            corners = [list(map(float, point)) for point in spec["corners_wgs84"]]
            if len(corners) != 4 or any(
                len(point) != 2
                or not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180)
                for point in corners
            ):
                raise ValueError(f"invalid projective corner set: {overlay_id}")
            display_transform = {
                "projective_display_transform": {
                    "model": "four_corner_projective_scene_placement",
                    "source_frame_corners_xy": pixel_corners,
                    "corners_wgs84_lat_lon": corners,
                    "basis": spec["corner_basis"],
                    "independent_ground_checkpoint_count": int(
                        spec.get("independent_ground_checkpoint_count", 0)
                    ),
                }
            }
        else:
            corners = [local_pixel_to_wgs84(transform, point) for point in pixel_corners]
            display_transform = {"local_display_transform": transform}

        formal_status = spec.get(
            "formal_alignment_status", "excluded_pending_independent_ground_control"
        )
        source_page_url = image["source_page_url"]
        source_sha256 = image["sha256"]
        generated_observations.append(
            {
                "observation_id": observation_id,
                "overlay_id": overlay_id,
                "classification": spec["registration_status"],
                "formal_alignment_status": formal_status,
                "source_evidence": {
                    "url": spec["source_image_url"],
                    "page_url": source_page_url,
                    "sha256": source_sha256,
                    "width_px": width,
                    "height_px": height,
                    "pixel_boundary_extent_xy": [0, 0, width, height],
                    "distribution": "remote_source_link_only_not_packaged",
                },
                "source_report_controls": {
                    "coordinate_wgs84_lat_lon": [latitude, longitude],
                    "coordinate_uncertainty_m": int(spec["coordinate_uncertainty_m"]),
                    "site_text": spec["site_text"],
                    **spec.get("source_report_controls", {}),
                },
                **(
                    {"landmark_controls": spec["landmark_controls"]}
                    if spec.get("landmark_controls")
                    else {}
                ),
                **display_transform,
                "computed_corners_wgs84_lat_lon": corners,
                "quality": {
                    "status": spec["quality_status"],
                    "limitations": spec["quality_limitations"],
                },
            }
        )
        generated_overlays.append(
            {
                "overlay_id": overlay_id,
                "registration_observation_id": observation_id,
                "formation_id": spec["formation_id"],
                "assertion_id": spec["assertion_id"],
                "title": spec["title"],
                "source_image_url": spec["source_image_url"],
                "source_page_url": source_page_url,
                "source_image_sha256": source_sha256,
                "corners": corners,
                "center": [latitude, longitude],
                "coordinate_uncertainty_m": int(spec["coordinate_uncertainty_m"]),
                "registration_status": spec["registration_status"],
                "display_geometry_status": spec["display_geometry_status"],
                "reference_imagery": spec["reference_imagery"],
                "reference_imagery_date": spec.get("reference_imagery_date", "2026-07-21"),
                "reviewed_at": spec.get("reviewed_at", "2026-07-21"),
                "review_basis": spec["review_basis"],
                "source_photo_pixels": "remote_source_link_only",
                "rights_status": "not_cleared_for_redistribution",
                "default_opacity": float(spec.get("default_opacity", 0.68)),
                "show_by_default": False,
                "formal_alignment_status": formal_status,
                "quality_disclosure": spec["quality_disclosure"],
                "notes": spec["notes"],
            }
        )

    overlays_payload["overlays"] = _replace_managed(
        overlays_payload["overlays"], generated_overlays, "overlay_id"
    )
    observations_payload["observations"] = _replace_managed(
        observations_payload["observations"], generated_observations, "observation_id"
    )
    OVERLAYS_PATH.write_text(
        json.dumps(overlays_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    OBSERVATIONS_PATH.write_text(
        json.dumps(observations_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return len(generated_overlays), len(overlays_payload["overlays"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    generated, total = build()
    print(f"Built {generated} provisional image-scene placements; {total} total overlays")


if __name__ == "__main__":
    main()
