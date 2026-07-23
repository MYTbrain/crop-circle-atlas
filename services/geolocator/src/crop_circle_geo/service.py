"""Formation-context and field-resolution job service."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from . import __version__
from .artifacts import ArtifactStore
from .config import Settings
from .imagery.base import ImageryProvider
from .matching.opencv_sift import OpenCvSiftMatcher
from .models import Clue, FieldResolutionJob, JobState, SearchPolygon, job_from_dict
from .orientation.bearing import measure_registered_component
from .overlay import generate_overlay
from .provenance import canonical_json, measured_stage, sha256_bytes, software_fingerprint, stable_id, utc_now
from .retrieval.cpu_baseline import CpuBaselineRetriever
from .spatial import validate_search_polygon
from .tiles import generate_candidate_tiles
from .validation.checkpoints import validate_checkpoints
from .validation.decision_gate import publication_decision, reviewed_spatial_state
from .validation.uncertainty import conservative_uncertainty_m
from .workflow import VersionedJobStore, transition


class FieldResolutionService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = VersionedJobStore(settings.ensure_cache())
        self.artifacts = ArtifactStore(settings.ensure_cache())

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

    def _schema(self, name: str) -> dict[str, Any]:
        return json.loads((self.settings.repository_root / "schemas" / name).read_text(encoding="utf-8"))

    def _validate(self, name: str, value: dict[str, Any]) -> None:
        Draft202012Validator(self._schema(name)).validate(value)

    @staticmethod
    def _next_states(job: FieldResolutionJob) -> list[str]:
        from .workflow import TRANSITIONS

        return sorted(item.value for item in TRANSITIONS[job.state])

    def _attach(
        self,
        job: FieldResolutionJob,
        category: str,
        artifact: dict[str, Any],
        event: str,
        target: JobState | None = None,
        actor: str = "machine",
        details: dict[str, Any] | None = None,
    ) -> FieldResolutionJob:
        artifacts = {key: list(values) for key, values in job.artifacts.items()}
        paths = artifacts.setdefault(category, [])
        if artifact["path"] not in paths:
            paths.append(artifact["path"])
        updated = replace(job, artifacts=artifacts, updated_at=utc_now())
        if target is not None and updated.state is not target:
            updated = transition(updated, target, actor)
        self.store.save(updated, event, actor, {
            "artifact_id": artifact["artifact_id"], "artifact_sha256": artifact["sha256"],
            "artifact_path": artifact["path"], "cache_hit": artifact["cache_hit"], **(details or {}),
        })
        return updated

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        return {
            "job": job.to_dict(),
            "event_count": len(self.store.event_history(job_id)),
            "next_valid_states": self._next_states(job),
            "warnings": list(job.warnings),
        }

    def search_imagery(
        self,
        job_id: str,
        provider: ImageryProvider,
        collections: list[str] | None = None,
        date_start: str | None = None,
        date_end: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state is not JobState.SEARCH_AREA_READY:
            raise ValueError("imagery search requires a search_area_ready job")
        if not job.search_polygons:
            raise ValueError("job has no search polygon")
        bounded_limit = min(limit or self.settings.max_imagery_items, self.settings.max_imagery_items)
        run = self._run_manifest(job, "search_imagery", {"provider": provider.name, "limit": bounded_limit})
        with measured_stage(run, "search_imagery", provider=provider.name, limit=bounded_limit) as stage:
            items = provider.search(
                job.search_polygons[-1].geometry,
                date_start or job.reported_date.get("start"),
                date_end or job.reported_date.get("end"),
                collections=collections,
                limit=bounded_limit,
            )
            for item in items:
                self._validate("imagery-item-v1.schema.json", item)
            stage["outputs"] = {"imagery_items": len(items)}
        manifest = {
            "schema_version": "crop-circle-atlas/imagery-search-manifest/v1",
            "job_id": job_id, "provider": provider.name, "items": items,
            "query_polygon_id": job.search_polygons[-1].polygon_id,
        }
        artifact = self.artifacts.save("imagery", manifest)
        updated = self._attach(job, "imagery", artifact, "imagery_cataloged", JobState.IMAGERY_CATALOGED)
        run_artifact = self._finish_run(run, updated.state.value)
        self._attach(updated, "runs", run_artifact, "run_manifest_saved")
        return {**artifact, "item_count": len(items), "items": items, "next_valid_states": self._next_states(updated)}

    def generate_tiles(
        self,
        job_id: str,
        imagery_item: dict[str, Any],
        tile_size_m: float = 512,
        overlap: float = 0.25,
        scales: Iterable[float] = (1.0,),
        rotations: Iterable[float] = (0.0,),
        representations: Iterable[str] = ("color", "edge", "gradient"),
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state is not JobState.IMAGERY_CATALOGED:
            raise ValueError("tile generation requires an imagery_cataloged job")
        manifest = generate_candidate_tiles(
            imagery_item, self.settings.ensure_cache(), tile_size_m=tile_size_m,
            overlap=overlap, scales=scales, rotations=rotations, representations=representations,
            max_tiles=self.settings.max_tiles,
        )
        for tile in manifest["tiles"]:
            self._validate("candidate-tile-v1.schema.json", tile)
        artifact = self.artifacts.save("tiles", manifest)
        updated = self._attach(job, "tiles", artifact, "tiles_generated", JobState.TILES_GENERATED,
                               details={"tile_count": manifest["tile_count"]})
        return {**artifact, "tile_count": manifest["tile_count"], "cache_hits": manifest["cache_hits"],
                "cache_misses": manifest["cache_misses"], "next_valid_states": self._next_states(updated)}

    def rank_tiles(
        self,
        job_id: str,
        source_image: Path,
        tile_manifest: dict[str, Any],
        top_k: int = 20,
        mask: Path | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state is not JobState.TILES_GENERATED:
            raise ValueError("ranking requires a tiles_generated job")
        bounded_top_k = min(top_k, self.settings.max_top_k)
        rankings = CpuBaselineRetriever(self.settings.ensure_cache()).rank(
            source_image, tile_manifest["tiles"], bounded_top_k, mask,
        )
        payload = {
            "schema_version": "crop-circle-atlas/candidate-ranking/v1", "job_id": job_id,
            "source_image": str(source_image.resolve()), "top_k": bounded_top_k,
            "rankings": rankings, "warning": "Retrieval score is not field-location evidence.",
        }
        artifact = self.artifacts.save("rankings", payload)
        updated = self._attach(job, "rankings", artifact, "candidates_ranked", JobState.CANDIDATES_RANKED,
                               details={"ranked_count": len(rankings)})
        return {**artifact, "rankings": rankings, "next_valid_states": self._next_states(updated)}

    def match_candidate(
        self,
        job_id: str,
        source_image: Path,
        tile: dict[str, Any],
        retrieval_score: float = 0,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state not in {JobState.CANDIDATES_RANKED, JobState.REGISTRATIONS_PROPOSED}:
            raise ValueError("matching requires a candidates_ranked or registrations_proposed job")
        candidate = OpenCvSiftMatcher().match(source_image, tile, retrieval_score)
        self._validate("registration-candidate-v1.schema.json", candidate)
        artifact = self.artifacts.save("registrations", candidate, candidate["registration_candidate_id"])
        target = JobState.REGISTRATIONS_PROPOSED if job.state is JobState.CANDIDATES_RANKED else None
        updated = self._attach(job, "registrations", artifact, "registration_proposed", target,
                               details={"machine_status": candidate["machine_status"]})
        if candidate["machine_status"] == "review_required" and updated.state is JobState.REGISTRATIONS_PROPOSED:
            updated = self.transition_job(job_id, JobState.REVIEW_REQUIRED, "machine")
        return {**artifact, "candidate": candidate, "next_valid_states": self._next_states(updated)}

    def validate_registration(
        self,
        job_id: str,
        registration_candidate_id: str,
        controls: list[dict[str, Any]],
        checkpoints: list[dict[str, Any]],
        reviewer: str,
        uncertainty_components: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state not in {JobState.REGISTRATIONS_PROPOSED, JobState.REVIEW_REQUIRED}:
            raise ValueError("validation requires a proposed registration")
        validation = validate_checkpoints(registration_candidate_id, controls, checkpoints, reviewer)
        components = uncertainty_components or {
            "reference_accuracy_m": 5, "landmark_selection_m": 2, "source_resolution_m": 2,
            "source_distortion_m": 5, "center_interpretation_m": 3, "control_selection_instability_m": 5,
        }
        validation["uncertainty"] = conservative_uncertainty_m(validation["metrics"], **components)
        self._validate("checkpoint-validation-v1.schema.json", validation)
        artifact = self.artifacts.save("validations", validation, validation["validation_id"])
        updated = self._attach(job, "validations", artifact, "registration_validated",
                               JobState.REVIEW_REQUIRED if job.state is JobState.REGISTRATIONS_PROPOSED else None,
                               actor="reviewer", details={"result": validation["result"]})
        return {**artifact, "validation": validation, "next_valid_states": self._next_states(updated)}

    def save_review(
        self,
        job_id: str,
        review_input: dict[str, Any],
        checkpoint_validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state is not JobState.REVIEW_REQUIRED:
            raise ValueError("review decisions require a review_required job")
        reviewed_at = utc_now()
        base = {**review_input, "job_id": job_id, "formation_id": job.formation_id, "reviewed_at": reviewed_at}
        base.setdefault("schema_version", "crop-circle-atlas/field-resolution-review/v1")
        base.setdefault("selected_candidate_id", None)
        base.setdefault("edited_controls", [])
        base.setdefault("held_out_checkpoints", [])
        base.setdefault("coordinate_uncertainty_m", None)
        base.setdefault("rights_decision", {"status": "local_analysis_only", "public_derivative_export_allowed": False})
        base.setdefault("publication_eligible", False)
        base.setdefault("notes", "")
        base.setdefault("evidence_sha256s", [])
        base["review_id"] = stable_id("review", {**base, "reviewed_at": reviewed_at})
        publication = publication_decision(base)
        if base["publication_eligible"] and not publication["publication_eligible"]:
            raise PermissionError("publication review fails rights gate: " + ", ".join(publication["reasons"]))
        target = reviewed_spatial_state(base, checkpoint_validation)
        self._validate("field-resolution-review-v1.schema.json", base)
        artifact = self.artifacts.save("reviews", base, base["review_id"])
        updated = self._attach(job, "reviews", artifact, "review_saved", target, actor="reviewer",
                               details={"decision": base["decision"], "spatial_classification": target.value})
        if publication["publication_eligible"] and updated.state in {JobState.CORROBORATED_FIELD, JobState.REGISTERED_SITE}:
            updated = self.transition_job(job_id, JobState.PUBLICATION_ELIGIBLE, "reviewer")
        return {**artifact, "review": base, "state": updated.state.value,
                "publication": publication, "next_valid_states": self._next_states(updated)}

    def measure_component(
        self,
        job_id: str,
        registration_candidate: dict[str, Any],
        tile: dict[str, Any],
        endpoint_a_px: list[float],
        endpoint_b_px: list[float],
        endpoint_uncertainty_m: float,
        directionality: str = "bidirectional",
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.state not in {JobState.CANDIDATE_FIELD, JobState.CORROBORATED_FIELD, JobState.REGISTERED_SITE, JobState.PUBLICATION_ELIGIBLE}:
            raise ValueError("orientation measurement requires a reviewed registration")
        measurement = measure_registered_component(
            registration_candidate["homography"], tile, endpoint_a_px, endpoint_b_px,
            endpoint_uncertainty_m, directionality,
        )
        measurement.update({"job_id": job_id, "formation_id": job.formation_id,
                            "registration_candidate_id": registration_candidate["registration_candidate_id"]})
        artifact = self.artifacts.save("orientations", measurement)
        self._attach(job, "orientations", artifact, "orientation_measured", actor="reviewer")
        return {**artifact, "measurement": measurement, "warnings": ["Provisional measurement is excluded from formal alignment analysis."]}

    def generate_local_overlay(
        self,
        job_id: str,
        review: dict[str, Any],
        registration_candidate: dict[str, Any],
        tile: dict[str, Any],
        source_image: Path,
        public_export: bool = False,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        output_dir = self.settings.ensure_cache() / "overlays" / job_id
        result = generate_overlay(review, registration_candidate, tile, source_image, output_dir, public_export)
        artifact = self.artifacts.save("overlay-records", result)
        self._attach(job, "overlays", artifact, "overlay_generated", actor="reviewer",
                     details={"public_export": public_export})
        return {**artifact, "overlay": result}

    def promote_reviewed_resolution(
        self,
        job_id: str,
        review: dict[str, Any],
        longitude: float,
        latitude: float,
        coordinate_method: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not confirm:
            raise PermissionError("promotion requires confirm=true on a separate explicit operation")
        if job.state not in {JobState.CORROBORATED_FIELD, JobState.REGISTERED_SITE, JobState.PUBLICATION_ELIGIBLE}:
            raise ValueError("only a reviewed corroborated field or registered site can be proposed for promotion")
        if review.get("job_id") != job_id or review.get("decision") != "accepted":
            raise ValueError("promotion requires the accepted review for this job")
        proposal = {
            "schema_version": "crop-circle-atlas/site-resolution-promotion/v1",
            "job_id": job_id, "formation_id": job.formation_id, "review_id": review["review_id"],
            "site_status": review["spatial_classification"], "longitude": float(longitude),
            "latitude": float(latitude), "coordinate_uncertainty_m": review["coordinate_uncertainty_m"],
            "coordinate_method": coordinate_method, "reviewer": review["reviewer"],
            "reviewed_at": review["reviewed_at"], "created_at": utc_now(),
            "canonical_catalog_mutated": False,
            "warning": "This is a reviewable patch proposal; the canonical registry was not mutated.",
        }
        artifact = self.artifacts.save("promotion-proposals", proposal)
        self._attach(job, "promotion_proposals", artifact, "promotion_proposal_created", actor="reviewer")
        return {**artifact, "proposal": proposal}

    def _run_manifest(self, job: FieldResolutionJob, operation: str, limits: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "crop-circle-atlas/run-manifest/v1", "job_id": job.job_id,
            "formation_id": job.formation_id, "operation": operation, "started_at": utc_now(),
            "finished_at": None, "device": "cpu", "models": {}, "limits": limits, "stages": [],
            "final_status": "running",
        }

    def _finish_run(self, run: dict[str, Any], status: str) -> dict[str, Any]:
        run["finished_at"] = utc_now()
        run["final_status"] = status
        return self.artifacts.save("runs", run)
