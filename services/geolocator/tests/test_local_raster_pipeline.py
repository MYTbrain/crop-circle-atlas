from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from shapely.geometry import mapping, box

from conftest import create_synthetic_raster
from crop_circle_geo.imagery.local_raster import LocalRasterProvider
from crop_circle_geo.matching.opencv_sift import OpenCvSiftMatcher
from crop_circle_geo.retrieval.cpu_baseline import CpuBaselineRetriever
from crop_circle_geo.tiles import generate_candidate_tiles
from crop_circle_geo.validation.homography import apply_homography


def test_local_geotiff_search_tiling_cache_retrieval_and_sift(tmp_path):
    _, source_path, expected_matrix = create_synthetic_raster(tmp_path)
    provider = LocalRasterProvider(tmp_path)
    query = mapping(box(-123.1, 45.0, -122.8, 45.3))
    items = provider.search(query, "1997-01-01", "1997-12-31", limit=5)
    assert len(items) == 1
    assert items[0]["orthorectified"] is True
    manifest = generate_candidate_tiles(
        items[0], tmp_path / "cache", tile_size_m=512, overlap=0, scales=(1,), rotations=(0,),
        representations=("color",), max_tiles=10,
    )
    assert manifest["tile_count"] == 4
    repeated = generate_candidate_tiles(
        items[0], tmp_path / "cache", tile_size_m=512, overlap=0, scales=(1,), rotations=(0,),
        representations=("color",), max_tiles=10,
    )
    assert repeated["cache_hits"] == 4
    retriever = CpuBaselineRetriever(tmp_path / "cache")
    ranked = retriever.rank(source_path, manifest["tiles"], top_k=4)
    assert ranked[0]["tile"]["bounds"][0] == pytest.approx(500000)
    assert ranked[0]["tile"]["bounds"][3] == pytest.approx(5001000)
    matcher = OpenCvSiftMatcher(ratio_threshold=0.82)
    result = matcher.match(source_path, ranked[0]["tile"], ranked[0]["score"])
    assert result["machine_status"] == "review_required"
    assert result["metrics"]["inlier_count"] >= 20
    center = apply_homography(result["homography"], [[200, 200]])[0]
    expected = apply_homography(expected_matrix, [[200, 200]])[0]
    assert np.linalg.norm(center - expected) < 4


def test_cutout_uses_raster_window(tmp_path):
    raster_path, _, _ = create_synthetic_raster(tmp_path)
    provider = LocalRasterProvider(tmp_path)
    item = provider._normalize(raster_path)
    destination = tmp_path / "cutout.tif"
    provider.cutout(item, (500000, 5000488, 500512, 5001000), destination)
    with __import__("rasterio").open(destination) as dataset:
        assert (dataset.width, dataset.height) == (512, 512)

