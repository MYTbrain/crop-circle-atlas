"""Typed project models and state-machine vocabulary."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class JobState(StrEnum):
    QUEUED = "queued"
    CLUES_EXTRACTED = "clues_extracted"
    SEARCH_AREA_READY = "search_area_ready"
    IMAGERY_CATALOGED = "imagery_cataloged"
    TILES_GENERATED = "tiles_generated"
    CANDIDATES_RANKED = "candidates_ranked"
    REGISTRATIONS_PROPOSED = "registrations_proposed"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    UNRESOLVED = "unresolved"
    CANDIDATE_FIELD = "candidate_field"
    CORROBORATED_FIELD = "corroborated_field"
    REGISTERED_SITE = "registered_site"
    PUBLICATION_ELIGIBLE = "publication_eligible"


class ReviewDecision(StrEnum):
    ACCEPTED = "accepted"
    DOWNGRADED = "downgraded"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Citation:
    source_url: str
    assertion_id: str | None = None
    quote_hash: str | None = None


@dataclass(frozen=True)
class Clue:
    kind: str
    value: str
    confidence: float
    citations: tuple[Citation, ...] = ()
    qualifiers: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.value.strip():
            raise ValueError("clue kind and value are required")
        if not 0 <= self.confidence <= 1:
            raise ValueError("clue confidence must be between 0 and 1")


@dataclass(frozen=True)
class SearchPolygon:
    polygon_id: str
    geometry: dict[str, Any]
    role: str = "locality_search_area"
    provider: str = "manual"
    query: str = ""
    exclusions: tuple[dict[str, Any], ...] = ()
    area_sq_km: float = 0.0
    admin_context: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role != "locality_search_area":
            raise ValueError("search polygons must remain locality_search_area")
        if self.area_sq_km < 0:
            raise ValueError("search polygon area cannot be negative")


@dataclass(frozen=True)
class FieldResolutionJob:
    schema_version: str
    job_id: str
    formation_id: str
    source_assertion_ids: tuple[str, ...]
    reported_date: dict[str, str | None]
    locality_text: str
    clues: tuple[Clue, ...]
    search_polygons: tuple[SearchPolygon, ...]
    created_at: str
    updated_at: str
    software: dict[str, str]
    state: JobState
    previous_job_ids: tuple[str, ...] = ()
    artifacts: dict[str, list[str]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = self.state.value
        return json.loads(json.dumps(value))


def as_json_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return asdict(value)


def job_from_dict(value: dict[str, Any]) -> FieldResolutionJob:
    clues = tuple(
        Clue(
            kind=item["kind"], value=item["value"], confidence=float(item["confidence"]),
            citations=tuple(Citation(**citation) for citation in item.get("citations", [])),
            qualifiers=dict(item.get("qualifiers", {})),
        ) for item in value.get("clues", [])
    )
    polygons = tuple(
        SearchPolygon(
            polygon_id=item["polygon_id"], geometry=item["geometry"], role=item.get("role", "locality_search_area"),
            provider=item.get("provider", "manual"), query=item.get("query", ""),
            exclusions=tuple(item.get("exclusions", [])), area_sq_km=float(item.get("area_sq_km", 0)),
            admin_context=dict(item.get("admin_context", {})),
        ) for item in value.get("search_polygons", [])
    )
    return FieldResolutionJob(
        schema_version=value["schema_version"], job_id=value["job_id"], formation_id=value["formation_id"],
        source_assertion_ids=tuple(value.get("source_assertion_ids", [])), reported_date=dict(value["reported_date"]),
        locality_text=value.get("locality_text", ""), clues=clues, search_polygons=polygons,
        created_at=value["created_at"], updated_at=value["updated_at"], software=dict(value["software"]),
        state=JobState(value["state"]), previous_job_ids=tuple(value.get("previous_job_ids", [])),
        artifacts={key: list(items) for key, items in value.get("artifacts", {}).items()},
        warnings=tuple(value.get("warnings", [])),
    )
