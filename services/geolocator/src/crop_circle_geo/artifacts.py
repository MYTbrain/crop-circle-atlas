"""Content-addressed artifact persistence for local geolocation jobs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .provenance import canonical_json, sha256_bytes, stable_id


class ArtifactStore:
    def __init__(self, cache_root: Path):
        self.root = cache_root.resolve() / "artifacts"

    def save(
        self,
        category: str,
        payload: dict[str, Any],
        identifier: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", category):
            raise ValueError("artifact category must be a safe lowercase identifier")
        digest = sha256_bytes(canonical_json(payload))
        artifact_id = identifier or stable_id(category[:10], payload)
        directory = self.root / category
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{artifact_id}-{digest[:12]}.json"
        cache_hit = destination.exists()
        if not cache_hit:
            destination.write_bytes(canonical_json(payload) + b"\n")
        return {
            "artifact_id": artifact_id,
            "artifact_type": category,
            "path": str(destination),
            "sha256": digest,
            "cache_hit": cache_hit,
        }

    def load(self, reference: str | Path) -> dict[str, Any]:
        path = Path(reference)
        if not path.is_absolute():
            matches = sorted(self.root.glob(f"*/*{reference}*.json"))
            if len(matches) != 1:
                raise KeyError(f"artifact reference is unknown or ambiguous: {reference}")
            path = matches[0]
        resolved = path.resolve()
        if self.root not in resolved.parents:
            raise PermissionError("artifact reference must be within the configured geolocator cache")
        return json.loads(resolved.read_text(encoding="utf-8"))

