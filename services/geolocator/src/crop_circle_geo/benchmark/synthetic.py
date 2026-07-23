"""Deterministic positive synthetic benchmark for pipeline mathematics only."""

from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from ..imagery.local_raster import LocalRasterProvider
from ..matching.opencv_sift import OpenCvSiftMatcher
from ..provenance import utc_now
from ..retrieval.cpu_baseline import CpuBaselineRetriever
from ..tiles import generate_candidate_tiles
from ..validation.homography import apply_homography
from .metrics import retrieval_recall


def create_synthetic_case(root: Path) -> tuple[Path, Path, np.ndarray]:
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    reference = np.full((1024, 1024, 3), 205, dtype=np.uint8)
    reference = np.clip(reference.astype(np.int16) + rng.normal(0, 7, reference.shape), 0, 255).astype(np.uint8)
    for index in range(24):
        x, y = int(rng.integers(15, 490)), int(rng.integers(15, 490))
        color = tuple(int(value) for value in rng.integers(20, 190, 3))
        if index % 3 == 0:
            cv2.circle(reference, (x, y), int(rng.integers(8, 28)), color, -1)
        elif index % 3 == 1:
            cv2.rectangle(reference, (x, y), (min(510, x + 35), min(510, y + 24)), color, -1)
        else:
            cv2.line(reference, (x, y), (min(510, x + 90), min(510, y + 45)), color, 5)
    cv2.putText(reference, "NORTH FARM 97", (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (15, 35, 15), 3, cv2.LINE_AA)
    cv2.line(reference, (0, 510), (1023, 510), (40, 40, 40), 10)
    cv2.line(reference, (510, 0), (510, 1023), (60, 60, 60), 8)
    for x in range(540, 1000, 45):
        cv2.line(reference, (x, 550), (x + 15, 990), (100, 120, 80), 2)
    raster_path = root / "synthetic.tif"
    with rasterio.open(raster_path, "w", driver="GTiff", height=1024, width=1024, count=3, dtype="uint8", crs="EPSG:32610", transform=from_origin(500000, 5001000, 1, 1), compress="deflate") as dataset:
        dataset.write(np.moveaxis(reference, -1, 0))
    metadata = {
        "collection": "synthetic-open", "item_id": "synthetic-001", "acquisition_start": "1997-06-28",
        "acquisition_end": "1997-06-28", "orthorectified": True, "ground_sample_distance_m": 1,
        "rights": {"status": "cc0", "holder": None, "license": "CC0-1.0", "proof": "generated synthetic fixture", "public_derivative_export_allowed": True},
    }
    raster_path.with_suffix(".tif.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    reference_quad = np.float32([[35, 40], [470, 25], [485, 475], [20, 485]])
    source_corners = np.float32([[0, 0], [399, 0], [399, 399], [0, 399]])
    reference_to_source = cv2.getPerspectiveTransform(reference_quad, source_corners)
    source = cv2.warpPerspective(reference, reference_to_source, (400, 400), flags=cv2.INTER_CUBIC)
    source = cv2.convertScaleAbs(cv2.GaussianBlur(source, (3, 3), .6), alpha=.92, beta=8)
    source_path = root / "source.png"; cv2.imwrite(str(source_path), source)
    return raster_path, source_path, np.linalg.inv(reference_to_source)


def run_synthetic_benchmark(work_root: Path | None = None) -> dict[str, Any]:
    temporary = None
    if work_root is None:
        temporary = tempfile.TemporaryDirectory(prefix="crop-circle-geo-benchmark-")
        work_root = Path(temporary.name)
    work_root.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    started = time.perf_counter(); _, source, expected = create_synthetic_case(work_root / "raster"); timings["fixture_generation"] = time.perf_counter() - started
    provider = LocalRasterProvider(work_root / "raster")
    started = time.perf_counter(); items = provider.search(mapping(box(-123.1, 45, -122.8, 45.3)), "1997-01-01", "1997-12-31", limit=5); timings["imagery_search"] = time.perf_counter() - started
    started = time.perf_counter(); manifest = generate_candidate_tiles(items[0], work_root / "cache", tile_size_m=512, overlap=0, scales=(1,), rotations=(0,), representations=("color",), max_tiles=10); timings["tile_generation"] = time.perf_counter() - started
    repeated_tiles = generate_candidate_tiles(items[0], work_root / "cache", tile_size_m=512, overlap=0, scales=(1,), rotations=(0,), representations=("color",), max_tiles=10)
    retriever = CpuBaselineRetriever(work_root / "cache")
    started = time.perf_counter(); ranked = retriever.rank(source, manifest["tiles"], top_k=4); timings["retrieval"] = time.perf_counter() - started
    repeated_ranked = retriever.rank(source, manifest["tiles"], top_k=4)
    expected_rank = next(row["rank"] for row in ranked if row["tile"]["bounds"][0] == 500000 and row["tile"]["bounds"][3] == 5001000)
    selected = ranked[0]
    started = time.perf_counter(); candidate = OpenCvSiftMatcher(ratio_threshold=.82).match(source, selected["tile"], selected["score"]); timings["matching"] = time.perf_counter() - started
    sample = np.float64([[0,0],[399,0],[399,399],[0,399],[100,100],[200,100],[300,100],[100,300],[200,300],[300,300]])
    expected_points = apply_homography(expected, sample)
    recovered_points = apply_homography(candidate["homography"], sample)
    errors = np.linalg.norm(expected_points - recovered_points, axis=1)
    center_expected = apply_homography(expected, [[200,200]])[0]
    center_recovered = apply_homography(candidate["homography"], [[200,200]])[0]
    cache_hits = repeated_tiles["cache_hits"] + sum(row["embedding_cache_hit"] for row in repeated_ranked) + int(repeated_ranked[0]["source_embedding_cache_hit"])
    cache_misses = manifest["cache_misses"] + len(ranked) + 1
    result = {
        "schema_version": "crop-circle-atlas/geolocator-benchmark-result/v1",
        "result_kind": "synthetic_positive_mathematics_only", "generated_at": utc_now(),
        "performance_claim_eligible": False,
        "transformations": ["projective", "crop", "blur", "contrast_and_brightness_change"],
        "retrieval": {**retrieval_recall([expected_rank]), "correct_tile_rank": expected_rank},
        "registration": {
            "machine_status": candidate["machine_status"], "center_error_m_at_1m_gsd": round(float(np.linalg.norm(center_expected-center_recovered)), 6),
            "footprint_corner_mean_error_m_at_1m_gsd": round(float(errors[:4].mean()), 6),
            "footprint_corner_max_error_m_at_1m_gsd": round(float(errors[:4].max()), 6),
            "checkpoint_median_m_at_1m_gsd": round(float(np.median(errors[4:])), 6),
            "checkpoint_rmse_m_at_1m_gsd": round(float(math.sqrt(np.mean(errors[4:]**2))), 6),
            "checkpoint_maximum_m_at_1m_gsd": round(float(errors[4:].max()), 6),
            "inlier_count": candidate["metrics"]["inlier_count"], "inlier_ratio": candidate["metrics"]["inlier_ratio"],
            "matcher": candidate["matcher"],
        },
        "false_acceptance_rate": "not_measured_no_negative_synthetic_cases",
        "unresolved_or_defer_rate": 0.0 if candidate["machine_status"] == "review_required" else 1.0,
        "processing_time_seconds": {key: round(value,6) for key,value in timings.items()},
        "imagery_items_searched": len(items), "tiles_searched": len(manifest["tiles"]), "device": "cpu",
        "retriever": {"name": retriever.name, "version": retriever.version},
        "cache": {"hits": cache_hits, "misses": cache_misses, "hit_rate": round(cache_hits/max(1,cache_hits+cache_misses),6)},
        "warning": "Synthetic performance validates implementation mathematics only and is not evidence of real-world geolocation effectiveness.",
    }
    if temporary is not None:
        temporary.cleanup()
    return result


if __name__ == "__main__":
    print(json.dumps(run_synthetic_benchmark(), indent=2, sort_keys=True))
