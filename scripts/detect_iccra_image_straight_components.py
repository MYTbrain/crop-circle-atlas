#!/usr/bin/env python3
"""Create a rights-safe straight-component review queue for ICCRA images.

The source pixels are read only from the ignored private cache.  This program
emits public *metadata only*: URLs, hashes, coverage status, detector
diagnostics, and axes measured in image coordinates.  It never copies or
renders an ICCRA image and never interprets an image-space axis as true north.

The thresholds are intentionally conservative for photographs and maps.  A
candidate tier means "worth human review", not "a crop formation has a straight
component".  Geographic rays still require the independently reviewed
``orientation_observations.csv`` qualification path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as exc:  # pragma: no cover - environment-dependent message
    raise SystemExit(
        "OpenCV is required: python -m pip install opencv-python-headless==4.13.0.92"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "data" / "iccra_image_links.csv"
OUTPUT_CSV = ROOT / "data" / "iccra_image_straight_candidates.csv"
METRICS_JSON = ROOT / "outputs" / "straight-components" / "iccra_image_metrics.json"
DETECTOR_VERSION = "iccra-source-image-straight-v1.0.0"
AXIS_REFERENCE = "image x-axis; 0=right; clockwise; modulo 180"
CAVEAT = (
    "automated ICCRA source-image review candidate only; image-space axis; "
    "not human-validated; not a true-north azimuth; source rights not cleared"
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_ANALYSIS_DIMENSION = 1600
ANGLE_CLUSTER_TOLERANCE_DEG = 5.0


@dataclass(frozen=True)
class Segment:
    length: float
    angle: float
    border_rejected: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def angle_distance(a: float, b: float) -> float:
    """Smallest distance between two unoriented axes, in degrees."""
    return abs((a - b + 90.0) % 180.0 - 90.0)


def axis_mean(weighted_angles: list[tuple[float, float]]) -> float:
    x = sum(weight * math.cos(math.radians(2.0 * angle)) for weight, angle in weighted_angles)
    y = sum(weight * math.sin(math.radians(2.0 * angle)) for weight, angle in weighted_angles)
    return (math.degrees(math.atan2(y, x)) / 2.0) % 180.0


def axis_uncertainty(weighted_angles: list[tuple[float, float]], mean: float) -> float:
    total = sum(weight for weight, _ in weighted_angles)
    if not total:
        return 90.0
    variance = sum(weight * angle_distance(angle, mean) ** 2 for weight, angle in weighted_angles) / total
    return math.sqrt(variance)


def cluster_segments(segments: list[Segment]) -> list[dict[str, float | int]]:
    """Cluster unoriented line segments without manufacturing a compass bearing."""
    candidates: list[dict[str, float | int]] = []
    for seed in segments:
        members = [item for item in segments if angle_distance(item.angle, seed.angle) <= ANGLE_CLUSTER_TOLERANCE_DEG]
        weighted = [(item.length, item.angle) for item in members]
        mean = axis_mean(weighted)
        candidates.append(
            {
                "axis": mean,
                "support": sum(item.length for item in members),
                "count": len(members),
                "uncertainty": axis_uncertainty(weighted, mean),
                "max_length": max(item.length for item in members),
            }
        )
    candidates.sort(key=lambda item: (-float(item["support"]), float(item["axis"])))
    clusters: list[dict[str, float | int]] = []
    for candidate in candidates:
        if all(angle_distance(float(candidate["axis"]), float(kept["axis"])) > 11.0 for kept in clusters):
            clusters.append(candidate)
    return clusters


def is_border_segment(x1: float, y1: float, x2: float, y2: float, width: int, height: int, angle: float) -> bool:
    """Suppress scan borders and page/photo frames, not interior cardinal lines."""
    margin_x = max(3.0, width * 0.025)
    margin_y = max(3.0, height * 0.025)
    near_horizontal_edge = (
        angle_distance(angle, 0.0) <= 4.0
        and ((y1 <= margin_y and y2 <= margin_y) or (y1 >= height - margin_y and y2 >= height - margin_y))
    )
    near_vertical_edge = (
        angle_distance(angle, 90.0) <= 4.0
        and ((x1 <= margin_x and x2 <= margin_x) or (x1 >= width - margin_x and x2 >= width - margin_x))
    )
    return near_horizontal_edge or near_vertical_edge


def candidate_score(
    image_kind: str,
    max_length_norm: float,
    dominant_support_norm: float,
    dominant_fraction: float,
    dominant_count: int,
    line_density: float,
) -> tuple[float, str]:
    """Return an unvalidated review score and conservative tier.

    Maps, aerials, and ordinary photographs contain many unrelated straight
    edges.  They therefore use stricter coherence and score gates than images
    explicitly catalogued as diagrams.  Dense edge fields are mildly penalized
    because roads, buildings, text, and crop rows otherwise dominate the queue.
    """
    length_strength = min(max_length_norm / 0.48, 1.0)
    support_strength = min(dominant_support_norm / 1.45, 1.0)
    coherence_strength = min(dominant_fraction / 0.40, 1.0)
    repeat_strength = min(dominant_count / 7.0, 1.0)
    density_penalty = min(max(line_density - 24.0, 0.0) / 100.0, 0.16)
    score = (
        0.36 * length_strength
        + 0.27 * support_strength
        + 0.27 * coherence_strength
        + 0.10 * repeat_strength
        - density_penalty
    )
    score = max(0.0, min(score, 1.0))

    diagram = image_kind == "diagram"
    if diagram:
        high = score >= 0.74 and max_length_norm >= 0.30 and dominant_count >= 2
        medium = score >= 0.60 and max_length_norm >= 0.22 and dominant_count >= 2
        low = score >= 0.45 and max_length_norm >= 0.13
    else:
        high = (
            score >= 0.84
            and max_length_norm >= 0.38
            and dominant_fraction >= 0.20
            and dominant_count >= 3
        )
        medium = (
            score >= 0.73
            and max_length_norm >= 0.29
            and dominant_fraction >= 0.16
            and dominant_count >= 3
        )
        low = (
            score >= 0.60
            and max_length_norm >= 0.20
            and dominant_fraction >= 0.12
            and dominant_count >= 2
        )
    return score, "high" if high else "medium" if medium else "low" if low else "none"


def analyze_image(gray: "np.ndarray", image_kind: str) -> dict[str, object]:
    if gray.ndim != 2 or not gray.size:
        raise ValueError("analysis expects a nonempty grayscale image")
    original_height, original_width = gray.shape
    scale_factor = min(1.0, MAX_ANALYSIS_DIMENSION / max(original_height, original_width))
    if scale_factor < 1.0:
        gray = cv2.resize(
            gray,
            (max(1, round(original_width * scale_factor)), max(1, round(original_height * scale_factor))),
            interpolation=cv2.INTER_AREA,
        )
    height, width = gray.shape
    blurred = cv2.GaussianBlur(gray, (3, 3), 0.8)
    # LSD on grayscale retains faint formation edges better than a fixed binary
    # threshold while remaining deterministic under a pinned OpenCV release.
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    detected = detector.detect(blurred)[0]
    raw_count = 0
    border_count = 0
    segments: list[Segment] = []
    minimum_length = max(10.0, min(width, height) * 0.075)
    if detected is not None:
        for raw in detected[:, 0]:
            raw_count += 1
            x1, y1, x2, y2 = (float(value) for value in raw)
            length = math.hypot(x2 - x1, y2 - y1)
            if length < minimum_length:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
            border = is_border_segment(x1, y1, x2, y2, width, height, angle)
            if border:
                border_count += 1
                continue
            segments.append(Segment(length=length, angle=angle, border_rejected=False))

    clusters = cluster_segments(segments)
    total_support = sum(item.length for item in segments)
    dominant = clusters[0] if clusters else None
    max_length = max((item.length for item in segments), default=0.0)
    dominant_support = float(dominant["support"]) if dominant else 0.0
    dominant_fraction = dominant_support / total_support if total_support else 0.0
    normalization = float(max(1, min(width, height)))
    max_length_norm = max_length / normalization
    dominant_support_norm = dominant_support / normalization
    megapixels = max(width * height / 1_000_000.0, 0.01)
    line_density = len(segments) / megapixels
    dominant_count = int(dominant["count"]) if dominant else 0
    score, tier = candidate_score(
        image_kind,
        max_length_norm,
        dominant_support_norm,
        dominant_fraction,
        dominant_count,
        line_density,
    )
    useful_clusters = [item for item in clusters if float(item["support"]) >= minimum_length * 1.5][:4]
    return {
        "analysis_status": "analyzed_private_cache",
        "analysis_width_px": width,
        "analysis_height_px": height,
        "analysis_scale_factor": f"{scale_factor:.6f}",
        "detector_score": f"{score:.3f}",
        "straight_component_tier": tier,
        "straight_component_candidate": "yes_review_candidate" if tier in {"high", "medium", "low"} else "no_review_candidate",
        "dominant_axis_image_deg": f"{float(dominant['axis']):.1f}" if dominant else "",
        "axis_uncertainty_deg": f"{float(dominant['uncertainty']):.1f}" if dominant else "",
        "axis_candidates_image_deg": ";".join(f"{float(item['axis']):.1f}" for item in useful_clusters),
        "raw_line_segment_count": raw_count,
        "qualifying_line_segment_count": len(segments),
        "border_segment_rejection_count": border_count,
        "dominant_cluster_segment_count": dominant_count,
        "max_segment_length_px": f"{max_length:.1f}",
        "max_segment_length_normalized": f"{max_length_norm:.3f}",
        "dominant_support_length_px": f"{dominant_support:.1f}",
        "dominant_support_normalized": f"{dominant_support_norm:.3f}",
        "dominant_support_fraction": f"{dominant_fraction:.3f}",
        "qualifying_lines_per_megapixel": f"{line_density:.3f}",
    }


def empty_analysis(status: str) -> dict[str, object]:
    return {
        "analysis_status": status,
        "analysis_width_px": "",
        "analysis_height_px": "",
        "analysis_scale_factor": "",
        "detector_score": "",
        "straight_component_tier": "not_analyzed",
        "straight_component_candidate": "not_analyzed",
        "dominant_axis_image_deg": "",
        "axis_uncertainty_deg": "",
        "axis_candidates_image_deg": "",
        "raw_line_segment_count": "",
        "qualifying_line_segment_count": "",
        "border_segment_rejection_count": "",
        "dominant_cluster_segment_count": "",
        "max_segment_length_px": "",
        "max_segment_length_normalized": "",
        "dominant_support_length_px": "",
        "dominant_support_normalized": "",
        "dominant_support_fraction": "",
        "qualifying_lines_per_megapixel": "",
    }


def split_assertion_ids(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "image_link_id", "assertion_ids", "source_page_url", "image_url", "image_kind",
        "is_iccra_hosted", "fetch_policy", "http_status", "sha256", "cache_path",
        "public_redistribution_status",
    }
    missing = required - set(rows[0] if rows else [])
    if missing:
        raise SystemExit(f"ICCRA image inventory is missing fields: {sorted(missing)}")
    ids = [row["image_link_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate image_link_id values in ICCRA image inventory")
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze_inventory(rows: list[dict[str, str]], root: Path = ROOT) -> tuple[list[dict[str, object]], dict[str, object]]:
    pixel_features_by_sha: dict[str, dict[str, object] | str] = {}
    classification_by_sha_kind: dict[tuple[str, str], dict[str, object]] = {}
    actual_hash_by_path: dict[Path, str] = {}
    output_rows: list[dict[str, object]] = []
    pixel_decode_count = 0

    for source in rows:
        hosted = source.get("is_iccra_hosted", "").strip().lower() == "true"
        http_status = source.get("http_status", "").strip()
        declared_sha = source.get("sha256", "").strip().lower()
        cache_text = source.get("cache_path", "").strip()
        cache_path = (root / cache_text).resolve() if cache_text else None
        image_kind = source.get("image_kind", "") or "photograph_or_unspecified"

        if not hosted:
            analysis = empty_analysis("external_not_fetched")
        elif http_status != "200":
            analysis = empty_analysis(f"hosted_fetch_failed_http_{http_status or 'unknown'}")
        elif not cache_path or not cache_path.is_file():
            analysis = empty_analysis("private_cache_missing")
        elif not HEX64.fullmatch(declared_sha):
            analysis = empty_analysis("invalid_inventory_sha256")
        else:
            if cache_path not in actual_hash_by_path:
                actual_hash_by_path[cache_path] = sha256_file(cache_path)
            actual_hash = actual_hash_by_path[cache_path]
            if actual_hash != declared_sha:
                analysis = empty_analysis("private_cache_hash_mismatch")
            else:
                feature_state = pixel_features_by_sha.get(declared_sha)
                if feature_state is None:
                    image = cv2.imread(str(cache_path), cv2.IMREAD_GRAYSCALE)
                    if image is None or not image.size:
                        feature_state = "private_cache_decode_failed"
                    else:
                        # Pixel features are kind-independent.  The image kind
                        # only changes conservative tier thresholds below.
                        feature_state = analyze_image(image, image_kind)
                        pixel_decode_count += 1
                    pixel_features_by_sha[declared_sha] = feature_state
                if isinstance(feature_state, str):
                    analysis = empty_analysis(feature_state)
                else:
                    key = (declared_sha, image_kind)
                    if key not in classification_by_sha_kind:
                        # Recompute from pixels only when a byte-identical image
                        # is catalogued under a different kind.  This is rare and
                        # keeps the stricter photograph/map gates explicit.
                        if any(existing_sha == declared_sha for existing_sha, _ in classification_by_sha_kind):
                            image = cv2.imread(str(cache_path), cv2.IMREAD_GRAYSCALE)
                            if image is None or not image.size:
                                classification_by_sha_kind[key] = empty_analysis("private_cache_decode_failed")
                            else:
                                classification_by_sha_kind[key] = analyze_image(image, image_kind)
                        else:
                            classification_by_sha_kind[key] = feature_state
                    analysis = classification_by_sha_kind[key]

        candidate_key = f"{source['image_link_id']}|{declared_sha}|{DETECTOR_VERSION}"
        output_rows.append(
            {
                "candidate_id": "isc_" + hashlib.sha1(candidate_key.encode("utf-8")).hexdigest()[:16],
                "image_link_id": source["image_link_id"],
                "assertion_ids": source.get("assertion_ids", ""),
                "source_page_url": source.get("source_page_url", ""),
                "image_url": source.get("image_url", ""),
                "image_sha256": declared_sha,
                "image_kind": image_kind,
                "inventory_http_status": http_status,
                "public_redistribution_status": source.get("public_redistribution_status", ""),
                **analysis,
                "axis_reference": AXIS_REFERENCE,
                "geographic_azimuth_qualified": "false",
                "detector_version": DETECTOR_VERSION,
                "rights_safe_output": "metadata_only_no_source_or_derived_pixels",
                "caveat": CAVEAT,
            }
        )

    analyzed = [row for row in output_rows if row["analysis_status"] == "analyzed_private_cache"]
    cached_input = [
        row for row in rows
        if row.get("is_iccra_hosted", "").strip().lower() == "true" and row.get("http_status", "").strip() == "200"
    ]
    unique_analyzed: dict[str, dict[str, object]] = {}
    for row in analyzed:
        unique_analyzed.setdefault(str(row["image_sha256"]), row)
    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    for row in analyzed:
        by_kind[str(row["image_kind"])][str(row["straight_component_tier"])] += 1
    linked_analyzed = [row for row in analyzed if row["assertion_ids"]]
    linked_candidate = [row for row in linked_analyzed if row["straight_component_tier"] in {"high", "medium", "low"}]
    metrics: dict[str, object] = {
        "generated_at": utc_now(),
        "detector_version": DETECTOR_VERSION,
        "opencv_version": cv2.__version__,
        "input_inventory": str(INPUT_CSV.relative_to(ROOT)).replace("\\", "/"),
        "input_inventory_rows": len(rows),
        "successfully_cached_hosted_rows": len(cached_input),
        "analyzed_rows": len(analyzed),
        "cached_row_coverage": round(len(analyzed) / len(cached_input), 6) if cached_input else None,
        "unique_successfully_cached_sha256": len({row.get("sha256", "") for row in cached_input if row.get("sha256")}),
        "unique_pixel_sha256_analyzed": len(unique_analyzed),
        "private_pixel_decodes": pixel_decode_count,
        "duplicate_rows_reusing_sha_analysis": len(analyzed) - len(unique_analyzed),
        "analysis_status_counts": dict(sorted(Counter(str(row["analysis_status"]) for row in output_rows).items())),
        "tier_counts_by_inventory_row": dict(sorted(Counter(str(row["straight_component_tier"]) for row in analyzed).items())),
        "tier_counts_by_unique_pixel_sha256": dict(sorted(Counter(str(row["straight_component_tier"]) for row in unique_analyzed.values()).items())),
        "tier_counts_by_image_kind": {kind: dict(sorted(counts.items())) for kind, counts in sorted(by_kind.items())},
        "linked_assertion_coverage": {
            "analyzed_image_rows_with_assertion_ids": len(linked_analyzed),
            "candidate_image_rows_with_assertion_ids": len(linked_candidate),
            "unique_assertion_ids_with_analyzed_images": len({item for row in linked_analyzed for item in split_assertion_ids(str(row["assertion_ids"]))}),
            "unique_assertion_ids_with_candidate_images": len({item for row in linked_candidate for item in split_assertion_ids(str(row["assertion_ids"]))}),
        },
        "angle_semantics": {
            "reference": "image x-axis",
            "zero": "right",
            "direction": "clockwise in image coordinates",
            "period_degrees": 180,
            "geographic_interpretation": "none",
        },
        "qualification_boundary": {
            "candidate_meaning": "automated review priority only; no manual validation",
            "true_north_bearing_created": False,
            "geographic_ray_eligible": False,
            "source_pixel_output": False,
            "derived_pixel_output": False,
            "public_output": "metadata only",
        },
    }
    return output_rows, metrics


FIELDNAMES = [
    "candidate_id", "image_link_id", "assertion_ids", "source_page_url", "image_url",
    "image_sha256", "image_kind", "inventory_http_status", "public_redistribution_status",
    "analysis_status", "analysis_width_px", "analysis_height_px", "analysis_scale_factor",
    "detector_score", "straight_component_tier", "straight_component_candidate",
    "dominant_axis_image_deg", "axis_uncertainty_deg", "axis_candidates_image_deg",
    "raw_line_segment_count", "qualifying_line_segment_count", "border_segment_rejection_count",
    "dominant_cluster_segment_count", "max_segment_length_px", "max_segment_length_normalized",
    "dominant_support_length_px", "dominant_support_normalized", "dominant_support_fraction",
    "qualifying_lines_per_megapixel", "axis_reference", "geographic_azimuth_qualified",
    "detector_version", "rights_safe_output", "caveat",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INPUT_CSV)
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--metrics", type=Path, default=METRICS_JSON)
    args = parser.parse_args()

    rows = read_inventory(args.inventory)
    output_rows, metrics = analyze_inventory(rows)
    write_csv(args.output, output_rows, FIELDNAMES)
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    if metrics["analyzed_rows"] != metrics["successfully_cached_hosted_rows"]:
        print("ERROR: not every successfully cached hosted image row was analyzed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
