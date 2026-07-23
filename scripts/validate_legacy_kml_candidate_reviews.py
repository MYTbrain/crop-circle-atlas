#!/usr/bin/env python3
"""Validate manual outcomes for fail-closed legacy KML candidates."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEWS_PATH = ROOT / "data" / "legacy_kml_candidate_reviews.json"
CANDIDATES_PATH = ROOT / "data" / "legacy_kml_candidates.json"
ALLOWED_OUTCOMES = {
    "properly_registered",
    "provisional_registration",
    "candidate_field",
    "rejected",
    "unresolved",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def validate_reviews(reviews: dict, candidates: dict) -> dict[str, int]:
    if reviews.get("schema_version") != "legacy-kml-candidate-review/v1":
        raise ValueError("unexpected legacy KML review schema version")
    policy = reviews.get("policy", {})
    if set(policy.get("allowed_outcomes", [])) != ALLOWED_OUTCOMES:
        raise ValueError("legacy KML review outcomes do not match the closed vocabulary")
    for gate in (
        "automatic_site_promotion",
        "automatic_overlay_creation",
        "automatic_alignment_eligibility",
        "automatic_publication_eligibility",
    ):
        if policy.get(gate) is not False:
            raise ValueError(f"legacy KML review policy must fail closed: {gate}")
    if policy.get("candidate_field_is_not_a_registered_site") is not True:
        raise ValueError("candidate fields must remain distinct from registered sites")

    candidate_ids = {
        record.get("legacy_candidate_id") for record in candidates.get("candidates", [])
    }
    records = reviews.get("records")
    if not isinstance(records, list):
        raise ValueError("legacy KML review records must be a list")
    seen: set[str] = set()
    outcome_counts: dict[str, int] = {}
    for record in records:
        candidate_id = record.get("legacy_candidate_id")
        if not candidate_id or candidate_id in seen:
            raise ValueError(f"duplicate or missing legacy candidate review: {candidate_id!r}")
        seen.add(candidate_id)
        if candidate_id not in candidate_ids:
            raise ValueError(f"review references unknown legacy candidate: {candidate_id}")
        outcome = record.get("outcome")
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"invalid legacy candidate review outcome: {outcome!r}")
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        if not record.get("reviewed_at") or not record.get("reviewer") or not record.get("review_notes"):
            raise ValueError(f"legacy candidate review lacks review metadata: {candidate_id}")
        latitude = record.get("latitude")
        longitude = record.get("longitude")
        uncertainty = record.get("coordinate_uncertainty_m")
        if not isinstance(latitude, (int, float)) or not -90 <= latitude <= 90:
            raise ValueError(f"invalid review latitude: {candidate_id}")
        if not isinstance(longitude, (int, float)) or not -180 <= longitude <= 180:
            raise ValueError(f"invalid review longitude: {candidate_id}")
        if not isinstance(uncertainty, (int, float)) or not math.isfinite(uncertainty) or uncertainty <= 0:
            raise ValueError(f"invalid review coordinate uncertainty: {candidate_id}")
        evidence = record.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"legacy candidate review lacks evidence: {candidate_id}")
        evidence_ids = [item.get("evidence_id") for item in evidence]
        if any(not value for value in evidence_ids) or len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError(f"invalid legacy review evidence IDs: {candidate_id}")
        if any(not HEX64.fullmatch(str(item.get("sha256", ""))) for item in evidence):
            raise ValueError(f"invalid legacy review evidence hash: {candidate_id}")
        for gate in ("alignment_eligible", "overlay_eligible", "publication_eligible"):
            if record.get(gate) is not False:
                raise ValueError(f"legacy review bypassed {gate}: {candidate_id}")
    return dict(sorted(outcome_counts.items()))


def main() -> None:
    reviews = json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    counts = validate_reviews(reviews, candidates)
    print(json.dumps({"status": "PASS", "review_count": sum(counts.values()), "outcomes": counts}))


if __name__ == "__main__":
    main()
