"""Rights decisions kept separate from spatial confidence."""

from __future__ import annotations

from typing import Any


PUBLICATION_STATUSES = {
    "public_domain",
    "cc0",
    "cc_by",
    "cc_by_sa",
    "licensed",
    "permission_granted",
    "owner_supplied_publication_authorized",
}
LICENSE_REQUIRED = {"cc0", "cc_by", "cc_by_sa", "licensed"}
HOLDER_REQUIRED = {"cc_by", "cc_by_sa", "licensed", "permission_granted", "owner_supplied_publication_authorized"}


def publication_qualification(rights: dict[str, Any] | None) -> tuple[bool, list[str]]:
    rights = rights or {}
    status = str(rights.get("status", "local_analysis_only")).strip().lower()
    reasons: list[str] = []
    if status not in PUBLICATION_STATUSES:
        reasons.append("rights_status_not_publication_authorized")
    if rights.get("public_derivative_export_allowed") is not True:
        reasons.append("public_derivative_export_not_explicitly_allowed")
    if not str(rights.get("proof", "")).strip():
        reasons.append("missing_license_or_permission_proof")
    if status in LICENSE_REQUIRED and not str(rights.get("license", "")).strip():
        reasons.append("missing_license_identifier")
    if status in HOLDER_REQUIRED and not str(rights.get("holder", "")).strip():
        reasons.append("missing_rights_holder")
    return not reasons, reasons


def require_publication_rights(rights: dict[str, Any] | None) -> None:
    allowed, reasons = publication_qualification(rights)
    if not allowed:
        raise PermissionError("publication export denied: " + ", ".join(reasons))

