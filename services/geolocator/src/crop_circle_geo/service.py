"""Formation-context and field-resolution job service."""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .config import Settings
from .models import Clue, FieldResolutionJob, JobState, SearchPolygon, job_from_dict
from .provenance import software_fingerprint, stable_id, utc_now
from .spatial import validate_search_polygon
from .workflow import VersionedJobStore, transition


class FieldResolutionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = VersionedJobStore(settings.ensure_cache())

    def _csv_rows(self, relative_path: str) -> list[dict[str, str]]:
        path = self.settings.repository_root / relative_path
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def get_formation_context(self, formation_id: str) -> dict[str, Any]:
        formations = self._csv_rows("data/formations.csv")
        formation = next((row for row in formations if row.get("formation_id") == formation_id), None)
        if not formation:
            raise KeyError(f"unknown formation: {formation_id}")
        assertion_ids = [item.strip() for item in formation.get("assertion_ids", "").split(";") if item.strip()]
        assertion_set = set(assertion_ids)
        assertions = [row for row in self._csv_rows("data/source_assertions.csv") if row.get("assertion_id") in assertion_set]
        locality = {
            "text": ", ".join(filter(None, [formation.get("place"), formation.get("county"), formation.get("region"), formation.get("country")])),
            "latitude": formation.get("locality_reference_latitude") or None,
            "longitude": formation.get("locality_reference_longitude") or None,
            "method": formation.get("locality_coordinate_method") or None,
            "role": formation.get("location_role") or formation.get("location_status"),
            "warning": "Locality coordinates are search anchors only and never an exact formation site.",
        }
        return {
            "formation": formation,
            "source_assertions": assertions,
            "source_assertion_ids": assertion_ids,
            "locality": locality,
            "warnings": [
                "No canonical coordinate will be changed by this service.",
                "Alias reconciliation must precede spatial promotion.",
            ],
        }

    def create_job(self, formation_id: str, previous_job_ids: Iterable[str] = ()) -> FieldResolutionJob:
        context = self.get_formation_context(formation_id)
        formation = context["formation"]
        now = utc_now()
        identity = {
            "formation_id": formation_id,
            "source_assertion_ids": context["source_assertion_ids"],
            "created_at": now,
        }
        job = FieldResolutionJob(
            schema_version="crop-circle-atlas/field-resolution-job/v1",
            job_id=stable_id("frj", identity), formation_id=formation_id,
            source_assertion_ids=tuple(context["source_assertion_ids"]),
            reported_date={"start": formation.get("date_iso") or None, "end": formation.get("date_iso") or None},
            locality_text=context["locality"]["text"], clues=(), search_polygons=(),
            created_at=now, updated_at=now, software=software_fingerprint(__version__),
            state=JobState.QUEUED, previous_job_ids=tuple(previous_job_ids),
            warnings=("Locality reference retained only as bounded-search context.",),
        )
        self.store.save(job, "job_created", "machine", {"canonical_catalog_mutated": False})
        return job

    def get_job(self, job_id: str) -> FieldResolutionJob:
        return job_from_dict(self.store.latest_payload(job_id))

    def set_clues(self, job_id: str, clues: Iterable[Clue], actor: str = "reviewer") -> FieldResolutionJob:
        job = self.get_job(job_id)
        new_job = replace(job, clues=tuple(clues), updated_at=utc_now())
        if new_job.state is JobState.QUEUED:
            new_job = transition(new_job, JobState.CLUES_EXTRACTED, "machine" if actor == "machine" else "reviewer")
        self.store.save(new_job, "clues_set", actor, {"clue_count": len(new_job.clues)})
        return new_job

    def set_search_area(
        self,
        job_id: str,
        geometry: dict[str, Any],
        exclusions: Iterable[dict[str, Any]] = (),
        provider: str = "manual",
        query: str = "",
        admin_context: dict[str, str] | None = None,
    ) -> FieldResolutionJob:
        job = self.get_job(job_id)
        if job.state is JobState.QUEUED:
            raise ValueError("location clues must be recorded before a search area")
        exclusions_tuple = tuple(exclusions)
        resolved, area_sq_km = validate_search_polygon(
            geometry, self.settings.max_search_area_sq_km, exclusions_tuple,
        )
        polygon_identity = {"geometry": resolved, "provider": provider, "query": query, "exclusions": exclusions_tuple}
        search = SearchPolygon(
            polygon_id=stable_id("search", polygon_identity), geometry=resolved,
            provider=provider, query=query, exclusions=exclusions_tuple, area_sq_km=area_sq_km,
            admin_context=admin_context or {},
        )
        updated = replace(job, search_polygons=job.search_polygons + (search,), updated_at=utc_now())
        if updated.state is JobState.CLUES_EXTRACTED:
            updated = transition(updated, JobState.SEARCH_AREA_READY, "machine")
        self.store.save(updated, "search_area_added", "reviewer", {
            "polygon_id": search.polygon_id, "area_sq_km": area_sq_km,
            "spatial_role": "locality_search_area", "canonical_catalog_mutated": False,
        })
        return updated

    def transition_job(self, job_id: str, target: JobState, actor: str) -> FieldResolutionJob:
        updated = transition(self.get_job(job_id), target, actor)
        self.store.save(updated, "state_transition", actor, {"target": target.value})
        return updated
