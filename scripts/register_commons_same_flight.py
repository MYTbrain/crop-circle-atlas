"""Transfer a reviewed aerial registration across a same-flight photo sequence.

This is an authoring tool, not a survey adjustment.  It uses SIFT matches to
estimate a similarity transform between adjacent frames, then constrains each
frame to the manually reviewed formation center.  The generated placements are
display-only, explicitly provisional, and excluded from alignment analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "web" / "data" / "formation_images.json"
DRAFT_PATH = ROOT / "data" / "commons_scene_placements_draft.json"
OUTPUT_PATH = ROOT / "data" / "commons_same_flight_scene_placements.json"
FORMATION_ID = "cc_2deeb6879ebf"
REFERENCE_ID = "commons_img_acedd0a59403fee4"
REVIEWED_AT = "2026-07-22"

# Coordinates are in the Wikimedia matching derivative described by
# ``expected_match_dimensions``.  Centers are in original-source pixels and
# were visually checked against the central flattened circle in each frame.
FRAMES = {
    REFERENCE_ID: {
        "roi": [430, 610, 1050, 1050],
        "center": [700, 830],
        "expected_match_dimensions": [1920, 1440],
    },
    "commons_img_1dfd99f84c449652": {
        "parent": REFERENCE_ID,
        "roi": [100, 250, 1700, 1250],
        "center": [800, 800],
        "expected_match_dimensions": [1920, 1440],
        "time_slug": "164420",
        "captured_at": "2008-07-15T16:44:20",
    },
    "commons_img_fbcc84da2be5d83d": {
        "parent": "commons_img_1dfd99f84c449652",
        "roi": [250, 1050, 1400, 2048],
        "center": [800, 1550],
        "expected_match_dimensions": [1536, 2048],
        "time_slug": "164623",
        "captured_at": "2008-07-15T16:46:23",
    },
    "commons_img_c50349097c37912c": {
        "parent": "commons_img_1dfd99f84c449652",
        "roi": [150, 350, 1650, 1300],
        "center": [800, 900],
        "expected_match_dimensions": [1920, 1440],
        "time_slug": "164415",
        "captured_at": "2008-07-15T16:44:15",
    },
    "commons_img_c92c8820e1e86db3": {
        "parent": "commons_img_fbcc84da2be5d83d",
        "roi": [50, 500, 1500, 1900],
        "center": [735, 1200],
        "expected_match_dimensions": [1536, 2048],
        "time_slug": "164633",
        "captured_at": "2008-07-15T16:46:33",
    },
    "commons_img_ef8b5a93a8a0be9f": {
        "parent": "commons_img_c92c8820e1e86db3",
        "roi": [0, 100, 1536, 1600],
        "center": [700, 750],
        "expected_match_dimensions": [1536, 2048],
        "time_slug": "164435",
        "captured_at": "2008-07-15T16:44:35",
    },
    "commons_img_f77e3ebef9abf039": {
        "parent": "commons_img_c92c8820e1e86db3",
        "roi": [20, 20, 1210, 940],
        "center": [610, 450],
        "expected_match_dimensions": [1236, 954],
        "time_slug": "164441",
        "captured_at": "2008-07-15T16:44:41",
    },
    "commons_img_59ad520d1c270f8e": {
        "parent": "commons_img_c92c8820e1e86db3",
        "roi": [450, 600, 1250, 1250],
        "center": [820, 900],
        "expected_match_dimensions": [1920, 1440],
        "time_slug": "164650",
        "captured_at": "2008-07-15T16:46:50",
    },
    "commons_img_5f41071b079087fa": {
        "parent": REFERENCE_ID,
        "roi": [500, 650, 1100, 1100],
        "center": [800, 800],
        "expected_match_dimensions": [1920, 1440],
        "time_slug": "164346",
        "captured_at": "2008-07-15T16:43:46",
        "manual_centered_identity": True,
    },
}


def _matrix_list(matrix: np.ndarray) -> list[list[float]]:
    return [[round(float(value), 12) for value in row] for row in matrix]


def _catalog() -> dict[str, dict]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {
        image["image_link_id"]: image
        for image in payload["images_by_formation"][FORMATION_ID]
    }


def _special_redirect(image: dict, width: int | None = None) -> str:
    title = str(image["title_text"]).removeprefix("File:")
    suffix = f"?width={width}" if width else ""
    return f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{quote(title)}{suffix}"


def _download(url: str, target: Path) -> None:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "CropCircleAtlasResearch/1.0 "
                "(https://github.com/MYTbrain/crop-circle-atlas)"
            )
        },
    )
    target.write_bytes(urlopen(request, timeout=60).read())


def _ensure_cache(cache_dir: Path, catalog: dict[str, dict], download: bool) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for image_id, spec in FRAMES.items():
        image = catalog[image_id]
        match_path = cache_dir / f"{image_id}_1600.jpg"
        original_path = cache_dir / f"{image_id}_original.jpg"
        if download and not match_path.exists():
            _download(_special_redirect(image, 1600), match_path)
        if download and not original_path.exists():
            _download(_special_redirect(image), original_path)
        if not match_path.exists() or not original_path.exists():
            raise FileNotFoundError(
                f"missing {image_id} cache; rerun with --download or provide both files"
            )
        match_image = cv2.imread(str(match_path), cv2.IMREAD_GRAYSCALE)
        original_image = cv2.imread(str(original_path), cv2.IMREAD_GRAYSCALE)
        if match_image is None or original_image is None:
            raise ValueError(f"unreadable cached image: {image_id}")
        match_dimensions = [match_image.shape[1], match_image.shape[0]]
        if match_dimensions != spec["expected_match_dimensions"]:
            raise ValueError(
                f"unexpected matching derivative dimensions for {image_id}: "
                f"{match_dimensions}"
            )
        original_dimensions = [original_image.shape[1], original_image.shape[0]]
        expected_original = [int(image["width"]), int(image["height"])]
        if original_dimensions != expected_original:
            raise ValueError(
                f"unexpected original dimensions for {image_id}: {original_dimensions}"
            )
        expected_sha1 = str(image.get("source_hash", ""))
        actual_sha1 = hashlib.sha1(original_path.read_bytes()).hexdigest()
        if expected_sha1 and actual_sha1 != expected_sha1:
            raise ValueError(f"Commons original SHA-1 mismatch: {image_id}")


def _features(cache_dir: Path) -> dict[str, tuple[np.ndarray, list, np.ndarray]]:
    detector = cv2.SIFT_create(
        nfeatures=30_000, contrastThreshold=0.006, edgeThreshold=20
    )
    result = {}
    for image_id, spec in FRAMES.items():
        image = cv2.imread(
            str(cache_dir / f"{image_id}_1600.jpg"), cv2.IMREAD_GRAYSCALE
        )
        mask = np.zeros(image.shape, dtype=np.uint8)
        x1, y1, x2, y2 = spec["roi"]
        mask[y1:y2, x1:x2] = 255
        keypoints, descriptors = detector.detectAndCompute(image, mask)
        result[image_id] = (image, keypoints, descriptors)
    return result


def _similarity_edge(
    image_id: str,
    parent_id: str,
    features: dict[str, tuple[np.ndarray, list, np.ndarray]],
    catalog: dict[str, dict],
) -> tuple[np.ndarray, dict]:
    image, keypoints, descriptors = features[image_id]
    parent, parent_keypoints, parent_descriptors = features[parent_id]
    pairs = cv2.BFMatcher().knnMatch(descriptors, parent_descriptors, k=2)
    matches = [left for left, right in pairs if left.distance < 0.78 * right.distance]
    source = np.float32([keypoints[item.queryIdx].pt for item in matches])
    target = np.float32([parent_keypoints[item.trainIdx].pt for item in matches])
    affine, inlier_mask = cv2.estimateAffinePartial2D(
        source,
        target,
        method=cv2.RANSAC,
        ransacReprojThreshold=4,
        maxIters=20_000,
        confidence=0.999,
        refineIters=20,
    )
    if affine is None or inlier_mask is None:
        raise ValueError(f"similarity transfer failed: {image_id}")
    inliers = int(inlier_mask.sum())
    if inliers < 5:
        raise ValueError(f"insufficient transfer inliers for {image_id}: {inliers}")
    match_matrix = np.vstack([affine, [0.0, 0.0, 1.0]])
    width, height = int(catalog[image_id]["width"]), int(catalog[image_id]["height"])
    parent_width = int(catalog[parent_id]["width"])
    parent_height = int(catalog[parent_id]["height"])
    source_scale = np.diag([image.shape[1] / width, image.shape[0] / height, 1.0])
    parent_scale = np.diag(
        [parent.shape[1] / parent_width, parent.shape[0] / parent_height, 1.0]
    )
    original_matrix = np.linalg.inv(parent_scale) @ match_matrix @ source_scale
    return original_matrix, {
        "candidate_match_count": len(matches),
        "ransac_inlier_count": inliers,
        "ransac_inlier_fraction": round(inliers / len(matches), 6),
        "source_roi_match_pixels": FRAMES[image_id]["roi"],
        "parent_roi_match_pixels": FRAMES[parent_id]["roi"],
        "source_to_parent_original_pixel_matrix": _matrix_list(original_matrix),
    }


def _point(matrix: np.ndarray, xy: list[float]) -> np.ndarray:
    value = matrix @ np.array([float(xy[0]), float(xy[1]), 1.0])
    return value[:2] / value[2]


def _wgs84_corners(
    support_to_reference: np.ndarray,
    reference_to_export: np.ndarray,
    width: int,
    height: int,
) -> list[list[float]]:
    source_corners = np.float64(
        [[[0.0, 0.0], [float(width), 0.0], [float(width), float(height)], [0.0, float(height)]]]
    )
    export_corners = cv2.perspectiveTransform(
        source_corners, reference_to_export @ support_to_reference
    )[0]
    return [
        [
            round(47.695 - float(y) / 1067.0 * 0.020, 12),
            round(8.710 + float(x) / 1600.0 * 0.030, 12),
        ]
        for x, y in export_corners
    ]


def build(cache_dir: Path, download: bool = False) -> int:
    cv2.setRNGSeed(20_080_715)
    catalog = _catalog()
    _ensure_cache(cache_dir, catalog, download)
    features = _features(cache_dir)
    draft = json.loads(DRAFT_PATH.read_text(encoding="utf-8"))["placements"][0]
    reference_to_export = np.array(
        draft["transform"]["homography_matrix"], dtype=np.float64
    )
    reference_center = np.array(draft["anchor_pixel_xy"], dtype=np.float64)
    transforms = {REFERENCE_ID: np.eye(3)}
    transfer_metrics = {}

    for image_id, spec in FRAMES.items():
        if image_id == REFERENCE_ID:
            continue
        parent_id = spec["parent"]
        if spec.get("manual_centered_identity"):
            source_to_parent = np.eye(3)
            metrics = {
                "candidate_match_count": 0,
                "ransac_inlier_count": 0,
                "ransac_inlier_fraction": 0.0,
                "method": "manual_same_scale_center_constraint",
            }
        else:
            source_to_parent, metrics = _similarity_edge(
                image_id, parent_id, features, catalog
            )
            metrics["method"] = "sift_ransac_similarity_then_center_constraint"
        cumulative = transforms[parent_id] @ source_to_parent
        mapped_center = _point(cumulative, spec["center"])
        correction = np.eye(3)
        correction[0, 2] = reference_center[0] - mapped_center[0]
        correction[1, 2] = reference_center[1] - mapped_center[1]
        cumulative = correction @ cumulative
        determinant = float(np.linalg.det(cumulative[:2, :2]))
        if not np.isfinite(cumulative).all() or abs(determinant) < 1e-5:
            raise ValueError(f"degenerate constrained transfer: {image_id}")
        transforms[image_id] = cumulative
        transfer_metrics[image_id] = {
            **metrics,
            "parent_image_id": parent_id,
            "manual_center_original_pixels": spec["center"],
            "center_constraint_reference_pixels": draft["anchor_pixel_xy"],
            "support_to_reference_original_pixel_matrix": _matrix_list(cumulative),
        }

    placements = []
    rights = draft["rights"]
    for image_id, spec in FRAMES.items():
        if image_id == REFERENCE_ID:
            continue
        image = catalog[image_id]
        original_path = cache_dir / f"{image_id}_original.jpg"
        sha256 = hashlib.sha256(original_path.read_bytes()).hexdigest()
        width, height = int(image["width"]), int(image["height"])
        metrics = transfer_metrics[image_id]
        inliers = metrics["ransac_inlier_count"]
        manual_only = bool(spec.get("manual_centered_identity"))
        method_summary = (
            "a manually centered, same-scale scene transfer"
            if manual_only
            else f"a constrained SIFT similarity transfer ({inliers} RANSAC inliers on its final edge)"
        )
        quality_disclosure = (
            f"This same-flight frame uses {method_summary} from the reviewed "
            "Diessenhofen reference frame. The formation center was visually "
            "checked, but oblique parallax, extrapolated frame corners, and the "
            "absence of independent ground checkpoints make the display warp "
            "provisional and exclude it from alignment calculations."
        )
        placements.append(
            {
                "overlay_id": f"commons-diessenhofen-20080715-{spec['time_slug']}",
                "observation_id": f"regobs_commons_diessenhofen_{spec['time_slug']}_transfer_v1",
                "formation_id": FORMATION_ID,
                "assertion_id": image["assertion_id"],
                "title": (
                    f"Diessenhofen 2008-07-15 {spec['captured_at'][-8:]} "
                    "same-flight aerial placement"
                ),
                "source_image_url": image["image_url"],
                "source_image_sha256": sha256,
                "anchor_pixel_xy": spec["center"],
                "anchor_wgs84_lat_lon": draft["anchor_wgs84_lat_lon"],
                "corners_wgs84": _wgs84_corners(
                    transforms[image_id], reference_to_export, width, height
                ),
                "corner_basis": (
                    "Same-flight similarity transfer to the manually controlled "
                    "Diessenhofen reference frame, constrained at the reviewed "
                    "formation center; full-frame corners are extrapolated."
                ),
                "coordinate_uncertainty_m": 90 if not manual_only else 120,
                "registration_status": "provisional_same_flight_similarity_transfer",
                "display_geometry_status": "four_corner_projective_scene_placement",
                "reference_imagery": draft["reference_imagery"]["provider"],
                "reference_imagery_date": draft["reference_imagery"][
                    "imagery_date_status"
                ],
                "reviewed_at": REVIEWED_AT,
                "site_text": (
                    "The frame depicts the same Diessenhofen formation and field "
                    "during the same documented 2008-07-15 aerial sequence."
                ),
                "source_report_controls": {
                    "reported_place": draft["reported_place"],
                    "captured_at": spec["captured_at"],
                    "reference_overlay_id": draft["overlay_id"].removesuffix("-draft"),
                },
                "independent_ground_checkpoint_count": 0,
                "review_basis": (
                    "Same-flight transfer to the accepted reference scene plus a "
                    "manual formation-center constraint."
                ),
                "quality_status": "same_event_center_checked_display_warp_provisional",
                "quality_limitations": quality_disclosure,
                "quality_disclosure": quality_disclosure,
                "notes": (
                    "Openly licensed source pixels load only after explicit user "
                    "action. This placement is display-only."
                ),
                "rights_status": rights["license"],
                "rights_attribution": rights["attribution"],
                "license_url": rights["license_url"],
                "embedding_allowed": True,
                "source_photo_pixels": "remote_open_license_source_link_only",
                "source_distribution": "remote_open_license_link_not_packaged",
                "source_registration": {
                    "kind": "same_flight_similarity_transfer_with_center_constraint",
                    "source_image_sha1": image["source_hash"],
                    "source_image_sha1_algorithm": image["source_hash_algorithm"],
                    "source_image_sha256": sha256,
                    "corner_uncertainty_m": 180 if not manual_only else 240,
                    "reference_overlay_id": draft["overlay_id"].removesuffix("-draft"),
                    "transfer": metrics,
                    "quality_gate": {
                        "formal_alignment_status": "excluded_pending_independent_ground_control",
                        "independent_ground_checkpoint_count": 0,
                    },
                    "rights": rights,
                },
            }
        )

    output = {
        "metadata": {
            "schema_version": "crop-circle-atlas/commons-same-flight-placements/v1",
            "reviewed_at": REVIEWED_AT,
            "reference_overlay_id": draft["overlay_id"].removesuffix("-draft"),
            "method": "same_flight_similarity_transfer_with_center_constraint",
            "notice": (
                "All placements are provisional display geometry, retain zero "
                "independent ground checkpoints, and are excluded from alignment analysis."
            ),
        },
        "placements": placements,
    }
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return len(placements)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "tmp" / "commons_diessenhofen",
    )
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    count = build(args.cache_dir.resolve(), args.download)
    print(f"Built {count} provisional same-flight image placements")


if __name__ == "__main__":
    main()
