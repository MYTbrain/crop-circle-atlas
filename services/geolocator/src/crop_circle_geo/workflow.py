"""Validated state transitions and append-only job persistence."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .models import FieldResolutionJob, JobState
from .provenance import canonical_json, sha256_bytes, utc_now


TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.CLUES_EXTRACTED, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.CLUES_EXTRACTED: {JobState.SEARCH_AREA_READY, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.SEARCH_AREA_READY: {JobState.IMAGERY_CATALOGED, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.IMAGERY_CATALOGED: {JobState.TILES_GENERATED, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.TILES_GENERATED: {JobState.CANDIDATES_RANKED, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.CANDIDATES_RANKED: {JobState.REGISTRATIONS_PROPOSED, JobState.REVIEW_REQUIRED, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.REGISTRATIONS_PROPOSED: {JobState.REVIEW_REQUIRED, JobState.DEFERRED, JobState.UNRESOLVED},
    JobState.REVIEW_REQUIRED: {
        JobState.REJECTED, JobState.DEFERRED, JobState.UNRESOLVED,
        JobState.CANDIDATE_FIELD, JobState.CORROBORATED_FIELD, JobState.REGISTERED_SITE,
    },
    JobState.CANDIDATE_FIELD: {JobState.REVIEW_REQUIRED, JobState.CORROBORATED_FIELD, JobState.DEFERRED},
    JobState.CORROBORATED_FIELD: {JobState.PUBLICATION_ELIGIBLE, JobState.REVIEW_REQUIRED},
    JobState.REGISTERED_SITE: {JobState.PUBLICATION_ELIGIBLE, JobState.REVIEW_REQUIRED},
    JobState.REJECTED: set(),
    JobState.DEFERRED: {JobState.QUEUED},
    JobState.UNRESOLVED: {JobState.QUEUED},
    JobState.PUBLICATION_ELIGIBLE: {JobState.REVIEW_REQUIRED},
}

MACHINE_FORBIDDEN = {JobState.CORROBORATED_FIELD, JobState.REGISTERED_SITE, JobState.PUBLICATION_ELIGIBLE}


def transition(job: FieldResolutionJob, target: JobState, actor: str) -> FieldResolutionJob:
    if target not in TRANSITIONS[job.state]:
        raise ValueError(f"invalid transition: {job.state.value} -> {target.value}")
    if actor == "machine" and target in MACHINE_FORBIDDEN:
        raise PermissionError(f"machine processing cannot transition to {target.value}")
    if target in {JobState.CORROBORATED_FIELD, JobState.REGISTERED_SITE, JobState.PUBLICATION_ELIGIBLE} and actor != "reviewer":
        raise PermissionError(f"{target.value} requires an explicit reviewer operation")
    return replace(job, state=target, updated_at=utc_now())


class VersionedJobStore:
    """Write immutable job versions and a compact append-only event stream."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.jobs_root = self.root / "jobs"
        self.events_path = self.root / "events.jsonl"

    def save(self, job: FieldResolutionJob, event: str, actor: str, details: dict[str, Any] | None = None) -> Path:
        payload = job.to_dict()
        digest = sha256_bytes(canonical_json(payload))
        directory = self.jobs_root / job.job_id
        directory.mkdir(parents=True, exist_ok=True)
        versions = sorted(directory.glob("*.json"))
        index = len(versions) + 1
        destination = directory / f"{index:05d}-{digest[:12]}.json"
        if not destination.exists():
            destination.write_bytes(canonical_json(payload) + b"\n")
        self.root.mkdir(parents=True, exist_ok=True)
        record = {
            "event_id": f"{job.job_id}:{index:05d}",
            "job_id": job.job_id,
            "formation_id": job.formation_id,
            "state": job.state.value,
            "event": event,
            "actor": actor,
            "timestamp": utc_now(),
            "artifact": str(destination),
            "sha256": digest,
            "details": details or {},
        }
        with self.events_path.open("ab") as handle:
            handle.write(canonical_json(record) + b"\n")
        return destination

    def latest_payload(self, job_id: str) -> dict[str, Any]:
        versions = sorted((self.jobs_root / job_id).glob("*.json"))
        if not versions:
            raise KeyError(f"unknown job: {job_id}")
        return json.loads(versions[-1].read_text(encoding="utf-8"))

    def event_history(self, job_id: str) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        return [
            json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines()
            if line and json.loads(line).get("job_id") == job_id
        ]
