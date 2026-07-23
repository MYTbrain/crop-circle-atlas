"""CPU SIFT, ratio filtering, RANSAC, and fail-closed diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from ..provenance import sha256_file, stable_id
from ..spatial import points_spatial_distribution, transform_xy
from ..validation.homography import apply_homography, homography_condition
from .base import RegistrationMatcher


def _tile_pixel_to_lonlat(tile: dict[str, Any], point: Sequence[float]) -> list[float]:
    west, south, east, north = map(float, tile["bounds"])
    width, height = map(float, tile["dimensions_px"])
    x = west + float(point[0]) / width * (east - west)
    y = north - float(point[1]) / height * (north - south)
    lon, lat = transform_xy(x, y, tile["crs"], "EPSG:4326")
    return [lon, lat]


class OpenCvSiftMatcher(RegistrationMatcher):
    name = "opencv_sift_ransac"
    version = "1.0.0"

    def __init__(self, ratio_threshold: float = 0.75, ransac_threshold_px: float = 4.0, max_features: int = 8_000):
        if not 0 < ratio_threshold < 1:
            raise ValueError("ratio threshold must be between zero and one")
        self.ratio_threshold = ratio_threshold
        self.ransac_threshold_px = ransac_threshold_px
        self.max_features = max_features

    @staticmethod
    def _read(path: Path) -> np.ndarray:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"unable to read image: {path}")
        return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(image)

    def _insufficient(self, source_image: Path, tile: dict[str, Any], match_count: int, limitation: str) -> dict[str, Any]:
        identity = {"source": sha256_file(source_image), "tile": tile["candidate_tile_id"], "matcher": self.version}
        return {
            "schema_version": "crop-circle-atlas/registration-candidate/v1",
            "registration_candidate_id": stable_id("reg", identity), "source_image_sha256": identity["source"],
            "candidate_tile_id": tile["candidate_tile_id"], "matcher": {"name": self.name, "version": self.version},
            "transform_type": "projective_homography", "homography": np.eye(3).tolist(), "matches": [],
            "inlier_mask": [], "metrics": {"inlier_count": 0, "inlier_ratio": 0, "spatial_distribution": 0, "reprojection_rmse_px": 0, "homography_condition": 1, "degenerate": True, "filtered_match_count": match_count},
            "proposed_image_corners": [[0, 0]] * 4, "proposed_formation_center": [0, 0],
            "preliminary_uncertainty_m": None, "machine_score": 0, "machine_status": "insufficient_matches",
            "rights_status": "local_analysis_only", "limitations": [limitation, "Machine output is not a field-resolution decision."],
        }

    def match(self, source_image, tile, retrieval_score=0):
        source_path = Path(source_image)
        destination_path = Path(tile["local_path"])
        source = self._read(source_path)
        destination = self._read(destination_path)
        sift = cv2.SIFT_create(nfeatures=self.max_features)
        source_keypoints, source_descriptors = sift.detectAndCompute(source, None)
        destination_keypoints, destination_descriptors = sift.detectAndCompute(destination, None)
        if source_descriptors is None or destination_descriptors is None:
            return self._insufficient(source_path, tile, 0, "SIFT found no usable descriptors.")
        pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(source_descriptors, destination_descriptors, k=2)
        good = [first for first, second in pairs if first.distance < self.ratio_threshold * second.distance]
        if len(good) < 8:
            return self._insufficient(source_path, tile, len(good), "Fewer than eight ratio-filtered matches.")
        source_points = np.float64([source_keypoints[item.queryIdx].pt for item in good])
        destination_points = np.float64([destination_keypoints[item.trainIdx].pt for item in good])
        matrix, mask = cv2.findHomography(source_points, destination_points, cv2.RANSAC, self.ransac_threshold_px)
        if matrix is None or mask is None:
            return self._insufficient(source_path, tile, len(good), "RANSAC did not produce a homography.")
        inlier_mask = mask.ravel().astype(bool)
        inlier_count = int(np.count_nonzero(inlier_mask))
        projected = apply_homography(matrix, source_points)
        residuals = np.linalg.norm(projected - destination_points, axis=1)
        inlier_residuals = residuals[inlier_mask]
        source_distribution = points_spatial_distribution(source_points[inlier_mask], source.shape[1], source.shape[0]) if inlier_count else 0
        destination_distribution = points_spatial_distribution(destination_points[inlier_mask], destination.shape[1], destination.shape[0]) if inlier_count else 0
        spatial_distribution = round((source_distribution * destination_distribution) ** 0.5, 6)
        condition = homography_condition(matrix)
        determinant = float(np.linalg.det(matrix / matrix[2, 2])) if abs(matrix[2, 2]) > 1e-12 else 0
        corners_source = np.float64([[0, 0], [source.shape[1], 0], [source.shape[1], source.shape[0]], [0, source.shape[0]]])
        corners_tile = apply_homography(matrix, corners_source)
        center_tile = apply_homography(matrix, [[source.shape[1] / 2, source.shape[0] / 2]])[0]
        folded = False
        signed = []
        for index in range(4):
            a, b, c = corners_tile[index], corners_tile[(index + 1) % 4], corners_tile[(index + 2) % 4]
            ab = b - a
            bc = c - b
            signed.append(float((ab[0] * bc[1]) - (ab[1] * bc[0])))
        folded = not (all(value > 0 for value in signed) or all(value < 0 for value in signed))
        inlier_ratio = inlier_count / len(good)
        degenerate = (
            inlier_count < 8 or inlier_ratio < 0.2 or spatial_distribution < 0.08 or
            not np.isfinite(condition) or condition > 1e10 or abs(determinant) < 1e-10 or folded
        )
        stability_score = 0 if not np.isfinite(condition) else max(0, min(1, 1 - np.log10(max(1, condition)) / 10))
        residual_score = max(0, min(1, 1 - float(np.mean(inlier_residuals)) / max(1, self.ransac_threshold_px * 2))) if inlier_count else 0
        machine_score = (
            0.2 * max(0, min(1, float(retrieval_score))) + 0.25 * min(1, inlier_count / 80) +
            0.2 * inlier_ratio + 0.2 * spatial_distribution + 0.1 * stability_score + 0.05 * residual_score
        )
        source_hash = sha256_file(source_path)
        identity = {"source": source_hash, "tile": tile["candidate_tile_id"], "matcher": self.version, "matrix": matrix.tolist()}
        limitations = [
            "No independent held-out checkpoint has validated this machine transform.",
            "Agricultural repetition can produce persuasive false matches.",
            "Machine output is not a field-resolution decision.",
        ]
        if float(tile.get("rotation_deg", 0)) % 360:
            degenerate = True
            limitations.append("Rotated tile geodetic inversion is not enabled in the CPU MVP matcher.")
        matches = [
            {"source": source_points[index].tolist(), "destination": destination_points[index].tolist(), "distance": float(item.distance)}
            for index, item in enumerate(good)
        ]
        return {
            "schema_version": "crop-circle-atlas/registration-candidate/v1",
            "registration_candidate_id": stable_id("reg", identity), "source_image_sha256": source_hash,
            "candidate_tile_id": tile["candidate_tile_id"], "matcher": {"name": self.name, "version": self.version},
            "transform_type": "projective_homography", "homography": matrix.tolist(), "matches": matches,
            "inlier_mask": inlier_mask.tolist(),
            "metrics": {
                "inlier_count": inlier_count, "inlier_ratio": round(inlier_ratio, 8),
                "spatial_distribution": spatial_distribution,
                "source_distribution": source_distribution, "destination_distribution": destination_distribution,
                "reprojection_rmse_px": round(float(np.sqrt(np.mean(inlier_residuals ** 2))) if inlier_count else 0, 8),
                "homography_condition": condition, "homography_determinant": determinant,
                "degenerate": degenerate, "folded_footprint": folded, "filtered_match_count": len(good),
                "retrieval_score": retrieval_score,
            },
            "proposed_image_corners": [_tile_pixel_to_lonlat(tile, point) for point in corners_tile],
            "proposed_formation_center": _tile_pixel_to_lonlat(tile, center_tile),
            "preliminary_uncertainty_m": None, "machine_score": round(machine_score, 8),
            "machine_status": "rejected_degenerate" if degenerate else "review_required",
            "rights_status": tile.get("rights_status", "local_analysis_only"), "limitations": limitations,
        }
