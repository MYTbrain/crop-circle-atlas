from __future__ import annotations

from dataclasses import replace

import pytest

from crop_circle_geo.models import FieldResolutionJob, JobState
from crop_circle_geo.workflow import transition


@pytest.fixture
def job():
    return FieldResolutionJob(
        schema_version="crop-circle-atlas/field-resolution-job/v1", job_id="frj_0123456789abcdef0123",
        formation_id="cc_test", source_assertion_ids=("a_test",), reported_date={"start": "2000-01-01", "end": "2000-01-01"},
        locality_text="Example", clues=(), search_polygons=(), created_at="2026-07-22T00:00:00Z",
        updated_at="2026-07-22T00:00:00Z", software={"component": "test", "version": "1"}, state=JobState.QUEUED,
    )


def test_machine_cannot_promote_to_corroborated_or_publication_state(job):
    review_job = replace(job, state=JobState.REVIEW_REQUIRED)
    with pytest.raises(PermissionError):
        transition(review_job, JobState.CORROBORATED_FIELD, "machine")
    with pytest.raises(ValueError):
        transition(job, JobState.PUBLICATION_ELIGIBLE, "reviewer")


def test_only_valid_reviewed_transitions_are_allowed(job):
    clues = transition(job, JobState.CLUES_EXTRACTED, "machine")
    area = transition(clues, JobState.SEARCH_AREA_READY, "machine")
    assert area.state is JobState.SEARCH_AREA_READY
    review_job = replace(job, state=JobState.REVIEW_REQUIRED)
    accepted = transition(review_job, JobState.CORROBORATED_FIELD, "reviewer")
    published = transition(accepted, JobState.PUBLICATION_ELIGIBLE, "reviewer")
    assert published.state is JobState.PUBLICATION_ELIGIBLE

