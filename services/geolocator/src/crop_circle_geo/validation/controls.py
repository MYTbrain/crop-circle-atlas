"""Control/checkpoint role validation."""

from __future__ import annotations

from typing import Any


TRANSIENT_CONTROL_TERMS = {"crop formation", "vehicle", "shadow", "crop row", "temporary track"}


def validate_landmarks(controls: list[dict[str, Any]], checkpoints: list[dict[str, Any]]) -> dict[str, Any]:
    control_ids = {item.get("landmark_id") for item in controls}
    checkpoint_ids = {item.get("landmark_id") for item in checkpoints}
    if None in control_ids or None in checkpoint_ids:
        raise ValueError("every landmark needs an ID")
    if control_ids & checkpoint_ids:
        raise ValueError("held-out checkpoints must never be used as controls")
    if len(control_ids) != len(controls) or len(checkpoint_ids) != len(checkpoints):
        raise ValueError("landmark IDs must be unique")
    for expected_role, items in (("control", controls), ("checkpoint", checkpoints)):
        for item in items:
            if item.get("role") != expected_role:
                raise ValueError(f"{expected_role} landmark has the wrong role")
            description = str(item.get("description", "")).lower()
            if any(term in description for term in TRANSIENT_CONTROL_TERMS):
                raise ValueError(f"transient feature cannot be a {expected_role}: {description}")
    return {"control_count": len(controls), "checkpoint_count": len(checkpoints), "independent": True}

