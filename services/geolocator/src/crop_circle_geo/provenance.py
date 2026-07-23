"""Canonical serialization, hashing, and run-stage provenance."""

from __future__ import annotations

import hashlib
import json
import platform
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, value: Any, length: int = 20) -> str:
    return f"{prefix}_{sha256_bytes(canonical_json(value))[:length]}"


def software_fingerprint(version: str) -> dict[str, str]:
    return {
        "component": "crop-circle-geolocator",
        "version": version,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


@contextmanager
def measured_stage(manifest: dict[str, Any], name: str, **inputs: Any) -> Iterator[dict[str, Any]]:
    stage = {
        "name": name,
        "started_at": utc_now(),
        "finished_at": None,
        "duration_seconds": None,
        "inputs": inputs,
        "outputs": {},
        "bytes_read": 0,
        "bytes_downloaded": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "errors": [],
        "retries": 0,
    }
    manifest.setdefault("stages", []).append(stage)
    started = time.perf_counter()
    try:
        yield stage
    except Exception as exc:
        stage["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        stage["duration_seconds"] = round(time.perf_counter() - started, 6)
        stage["finished_at"] = utc_now()

