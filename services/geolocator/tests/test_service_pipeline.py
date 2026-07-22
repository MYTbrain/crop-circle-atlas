from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from shapely.geometry import box, mapping

from conftest import create_synthetic_raster
from crop_circle_geo.config import Settings
from crop_circle_geo.imagery.local_raster import LocalRasterProvider
from crop_circle_geo.models import Citation, Clue, JobState
from crop_circle_geo.service import FieldResolutionService


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_persisted_service_pipeline_requires_review_before_overlay(tmp_path):
    raster_root = tmp_path / "rasters"; raster_root.mkdir()
    _, source_image, _ = create_synthetic_raster(raster_root)
    settings = replace(Settings.from_env(REPO_ROOT), cache_root=tmp_path / "cache", max_tiles=20)
    service = FieldResolutionService(settings)
    context = service.get_formation_context("cc_e5724a3476de")
    job = service.create_job("cc_e5724a3476de")
    job = service.set_clues(job.job_id, [Clue("road", "synthetic road", .9, (Citation(context["formation"]["source_urls"]),))])
    job = service.set_search_area(job.job_id, mapping(box(-123.1, 45.0, -122.8, 45.3)))
    imagery = service.search_imagery(job.job_id, LocalRasterProvider(raster_root), date_start="1997-01-01", date_end="1997-12-31")
    assert imagery["item_count"] == 1
    generated = service.generate_tiles(job.job_id, imagery["items"][0], tile_size_m=512, overlap=0, representations=("color",))
    tile_manifest = service.artifacts.load(generated["path"])
    ranked = service.rank_tiles(job.job_id, source_image, tile_manifest, top_k=4)
    matched = service.match_candidate(job.job_id, source_image, ranked["rankings"][0]["tile"], ranked["rankings"][0]["score"])
    assert matched["candidate"]["machine_status"] == "review_required"
    assert service.get_job(job.job_id).state is JobState.REVIEW_REQUIRED
    review = service.save_review(job.job_id, {
        "reviewer": "test reviewer", "decision": "accepted",
        "selected_candidate_id": matched["candidate"]["registration_candidate_id"],
        "spatial_classification": "candidate_field", "coordinate_uncertainty_m": 75,
        "rights_decision": {"status": "local_analysis_only", "public_derivative_export_allowed": False},
        "publication_eligible": False, "notes": "synthetic service path", "evidence_sha256s": [],
    })
    assert review["state"] == "candidate_field"
    overlay = service.generate_local_overlay(job.job_id, review["review"], matched["candidate"], ranked["rankings"][0]["tile"], source_image)
    assert Path(overlay["overlay"]["kmz_path"]).exists()
    assert len(service.store.event_history(job.job_id)) >= 10

