"""Human-review policy gate; publication and spatial confidence stay separate."""

from __future__ import annotations

from typing import Any

from ..models import JobState
from ..rights import publication_qualification


def reviewed_spatial_state(review: dict[str, Any], checkpoint_validation: dict[str, Any] | None) -> JobState:
    decision = review.get("decision")
    classification = review.get("spatial_classification")
    if decision == "rejected":
        return JobState.REJECTED
    if decision == "deferred":
        return JobState.DEFERRED
    if decision == "unresolved" or classification == "unresolved":
        return JobState.UNRESOLVED
    if classification == "candidate_field":
        return JobState.CANDIDATE_FIELD
    if classification == "registered_site":
        if not review.get("source_coordinate_method"):
            raise ValueError("registered_site requires a recorded source coordinate method")
        return JobState.REGISTERED_SITE
    if classification != "corroborated_field":
        raise ValueError("review does not select a supported spatial classification")
    evidence_types = {str(value).strip() for value in review.get("compatible_evidence_types", []) if str(value).strip()}
    if decision != "accepted" or len(evidence_types) < 2:
        raise ValueError("corroborated_field requires explicit approval and two compatible evidence types")
    if not checkpoint_validation or checkpoint_validation.get("result") != "pass":
        raise ValueError("corroborated_field requires passing independent checkpoint validation")
    if review.get("contradictory_evidence_unresolved") is True:
        raise ValueError("corroborated_field cannot retain unresolved contradictory evidence")
    uncertainty = review.get("coordinate_uncertainty_m")
    if not isinstance(uncertainty, (int, float)) or uncertainty <= 0:
        raise ValueError("corroborated_field requires conservative coordinate uncertainty")
    return JobState.CORROBORATED_FIELD


def publication_decision(review: dict[str, Any]) -> dict[str, Any]:
    rights_allowed, reasons = publication_qualification(review.get("rights_decision"))
    explicitly_requested = review.get("publication_eligible") is True
    return {
        "publication_eligible": bool(explicitly_requested and rights_allowed),
        "rights_qualified": rights_allowed,
        "reasons": [] if explicitly_requested and rights_allowed else (["review_did_not_request_publication"] if not explicitly_requested else reasons),
    }
