from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import jsonschema
import pytest

from crop_circle_geo.config import Settings
from crop_circle_geo.models import Citation, Clue, JobState
from crop_circle_geo.service import FieldResolutionService


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_formation_context_and_versioned_job_leave_catalog_immutable(tmp_path):
    settings = replace(Settings.from_env(REPO_ROOT), cache_root=tmp_path)
    service = FieldResolutionService(settings)
    formation_id = "cc_e5724a3476de"
    formations_before = (REPO_ROOT / "data" / "formations.csv").read_bytes()
    context = service.get_formation_context(formation_id)
    assert context["locality"]["warning"].startswith("Locality coordinates are search anchors")
    job = service.create_job(formation_id)
    clue = Clue("road", "Whiskey Hill Road", 0.9, (Citation(context["formation"]["source_urls"]),))
    job = service.set_clues(job.job_id, [clue])
    polygon = {
        "type": "Polygon",
        "coordinates": [[[-122.74, 45.16], [-122.71, 45.16], [-122.71, 45.19], [-122.74, 45.19], [-122.74, 45.16]]],
    }
    job = service.set_search_area(job.job_id, polygon, provider="manual", query="reviewer-drawn")
    assert job.state is JobState.SEARCH_AREA_READY
    assert job.search_polygons[0].role == "locality_search_area"
    assert service.store.event_history(job.job_id)[-1]["details"]["canonical_catalog_mutated"] is False
    assert (REPO_ROOT / "data" / "formations.csv").read_bytes() == formations_before


def test_job_schema_validates_persisted_payload(tmp_path):
    settings = replace(Settings.from_env(REPO_ROOT), cache_root=tmp_path)
    service = FieldResolutionService(settings)
    job = service.create_job("cc_e5724a3476de")
    schema = jsonschema.validators.Draft202012Validator(
        __import__("json").loads((REPO_ROOT / "schemas" / "field-resolution-job-v1.schema.json").read_text(encoding="utf-8")),
        format_checker=jsonschema.FormatChecker(),
    )
    schema.validate(job.to_dict())

