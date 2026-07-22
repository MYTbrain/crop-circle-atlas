from __future__ import annotations

import pytest

from crop_circle_geo.models import JobState
from crop_circle_geo.validation.decision_gate import publication_decision, reviewed_spatial_state


def test_machine_score_is_insufficient_for_corroboration():
    review = {
        "decision": "accepted", "spatial_classification": "corroborated_field",
        "compatible_evidence_types": ["image_match"], "coordinate_uncertainty_m": 20,
    }
    with pytest.raises(ValueError, match="two compatible evidence types"):
        reviewed_spatial_state(review, {"result": "pass"})


def test_reviewed_candidate_and_corroborated_paths():
    assert reviewed_spatial_state({"decision": "downgraded", "spatial_classification": "candidate_field"}, None) is JobState.CANDIDATE_FIELD
    review = {
        "decision": "accepted", "spatial_classification": "corroborated_field",
        "compatible_evidence_types": ["source_aerial", "historical_orthophoto"],
        "coordinate_uncertainty_m": 20, "contradictory_evidence_unresolved": False,
    }
    assert reviewed_spatial_state(review, {"result": "pass"}) is JobState.CORROBORATED_FIELD


def test_publication_is_separate_and_rights_gated():
    result = publication_decision({"publication_eligible": True, "rights_decision": {"status": "permission_pending"}})
    assert result["publication_eligible"] is False

