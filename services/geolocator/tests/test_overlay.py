from __future__ import annotations

import zipfile

import pytest

from conftest import create_synthetic_raster
from crop_circle_geo.imagery.local_raster import LocalRasterProvider
from crop_circle_geo.matching.opencv_sift import OpenCvSiftMatcher
from crop_circle_geo.overlay import generate_overlay
from crop_circle_geo.tiles import generate_candidate_tiles


def test_reviewed_local_overlay_and_publication_gate(tmp_path):
    raster_path, source_path, _ = create_synthetic_raster(tmp_path)
    item = LocalRasterProvider(tmp_path)._normalize(raster_path)
    tile = generate_candidate_tiles(item, tmp_path / "cache", 512, 0, (1,), (0,), ("color",), 10)["tiles"][0]
    candidate = OpenCvSiftMatcher(ratio_threshold=0.82).match(source_path, tile, 1)
    assert candidate["machine_status"] == "review_required"
    review = {
        "review_id": "review-1", "job_id": "job-1", "formation_id": "cc_test", "reviewer": "Test reviewer",
        "reviewed_at": "2026-07-22", "decision": "downgraded", "spatial_classification": "candidate_field",
        "coordinate_uncertainty_m": 50, "publication_eligible": False,
        "rights_decision": {"status": "local_analysis_only", "public_derivative_export_allowed": False},
    }
    output = generate_overlay(review, candidate, tile, source_path, tmp_path / "output")
    with zipfile.ZipFile(output["kmz_path"]) as archive:
        assert {"doc.kml", "metadata.json"}.issubset(archive.namelist())
        assert b"LOCAL ANALYSIS ONLY" in archive.read("doc.kml")
    with pytest.raises(PermissionError, match="did not explicitly authorize"):
        generate_overlay(review, candidate, tile, source_path, tmp_path / "public", public_export=True)


def test_public_overlay_requires_complete_rights(tmp_path):
    raster_path, source_path, _ = create_synthetic_raster(tmp_path)
    item = LocalRasterProvider(tmp_path)._normalize(raster_path)
    tile = generate_candidate_tiles(item, tmp_path / "cache", 512, 0, (1,), (0,), ("color",), 10)["tiles"][0]
    candidate = OpenCvSiftMatcher(ratio_threshold=0.82).match(source_path, tile, 1)
    review = {
        "review_id": "review-2", "job_id": "job-1", "formation_id": "cc_test", "reviewer": "Test reviewer",
        "reviewed_at": "2026-07-22", "decision": "accepted", "spatial_classification": "corroborated_field",
        "coordinate_uncertainty_m": 10, "publication_eligible": True,
        "rights_decision": {"status": "cc0", "license": "CC0-1.0", "proof": "synthetic-test-fixture", "public_derivative_export_allowed": True},
    }
    output = generate_overlay(review, candidate, tile, source_path, tmp_path / "public", public_export=True)
    assert output["public_export"] is True
