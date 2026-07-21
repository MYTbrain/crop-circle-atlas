from __future__ import annotations

import math
import re


VALID_ORIENTATION_METHODS = {
    "survey",
    "north_arrow",
    "georeferenced_photo",
    "landmark_registration",
    "other_documented",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_orientation(observation, formation):
    reasons = []
    assertion_fk = str(observation.get("assertion_id", "")).strip()
    formation_assertions = {
        value for value in str(formation.get("assertion_ids", "")).split("; ") if value
    }
    if not assertion_fk or assertion_fk not in formation_assertions:
        reasons.append("orientation_assertion_not_attached_to_formation")

    azimuth = as_float(observation.get("azimuth_true_deg"))
    uncertainty = as_float(observation.get("azimuth_uncertainty_deg"))
    method = str(observation.get("orientation_method", "")).strip()
    directionality = str(observation.get("directionality", "forward")).strip() or "forward"
    if azimuth is None or not math.isfinite(azimuth) or not 0 <= azimuth < 360:
        reasons.append("invalid_or_missing_true_azimuth")
    if uncertainty is None or not math.isfinite(uncertainty) or not 0 <= uncertainty <= 90:
        reasons.append("invalid_or_missing_azimuth_uncertainty")
    if method not in VALID_ORIENTATION_METHODS:
        reasons.append("unsupported_orientation_method")
    if directionality not in {"forward", "bidirectional"}:
        reasons.append("invalid_directionality")

    evidence_url = str(observation.get("evidence_url", "")).strip()
    evidence_sha256 = str(observation.get("evidence_sha256", "")).strip().lower()
    if not evidence_url and not evidence_sha256:
        reasons.append("missing_evidence")
    if evidence_sha256 and not HEX64.fullmatch(evidence_sha256):
        reasons.append("invalid_evidence_sha256")
    if not str(observation.get("reviewer", "")).strip():
        reasons.append("missing_reviewer")
    if not str(observation.get("reviewed_at", "")).strip():
        reasons.append("missing_review_date")

    max_range = as_float(observation.get("max_range_km"))
    corridor = as_float(observation.get("corridor_km"))
    origin_uncertainty_m = as_float(observation.get("origin_uncertainty_m"))
    if max_range is None or not math.isfinite(max_range) or max_range <= 0:
        reasons.append("invalid_max_range")
    if corridor is None or not math.isfinite(corridor) or corridor <= 0:
        reasons.append("invalid_corridor")
    if origin_uncertainty_m is None or not math.isfinite(origin_uncertainty_m) or origin_uncertainty_m < 0:
        reasons.append("invalid_origin_uncertainty")

    origin_lat = as_float(observation.get("origin_latitude"))
    origin_lon = as_float(observation.get("origin_longitude"))
    origin_method = str(observation.get("origin_coordinate_method", "")).strip()
    if origin_lat is None or origin_lon is None:
        origin_lat = as_float(formation.get("latitude"))
        origin_lon = as_float(formation.get("longitude"))
        origin_method = str(formation.get("geocode_method", "formation_coordinate")).strip()
        formation_uncertainty = as_float(formation.get("coordinate_uncertainty_km"), float("inf"))
        if origin_method == "geonames_locality_centroid" or formation_uncertainty > 1:
            reasons.append("coarse_origin_requires_registered_coordinate")
    elif not origin_method or origin_method == "geonames_locality_centroid":
        reasons.append("invalid_origin_coordinate_method")
    if (origin_lat is None or origin_lon is None or not math.isfinite(origin_lat) or
            not math.isfinite(origin_lon) or not -90 <= origin_lat <= 90 or not -180 <= origin_lon <= 180):
        reasons.append("missing_or_invalid_origin")

    return {
        "qualified": not reasons,
        "reasons": reasons,
        "azimuth": azimuth,
        "uncertainty": uncertainty,
        "directionality": directionality,
        "origin_latitude": origin_lat,
        "origin_longitude": origin_lon,
        "origin_method": origin_method,
        "max_range_km": max_range,
        "corridor_km": corridor,
        "origin_uncertainty_m": origin_uncertainty_m,
    }
