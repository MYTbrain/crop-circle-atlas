"""Localhost-only FastAPI control plane for the reviewer workbench."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .adapters import provider_from_spec
from .config import Settings
from .mcp_server import _clues
from .service import FieldResolutionService


app = FastAPI(title="Crop Circle Geolocator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost", "http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"], allow_credentials=False,
)


def _service() -> FieldResolutionService:
    return FieldResolutionService(Settings.from_env())


def _guard(call: Callable[[], Any]) -> Any:
    try:
        return call()
    except (ValueError, KeyError, PermissionError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    settings = Settings.from_env()
    return {"status": "ok", "mode": "local", "cache_root": str(settings.cache_root), "credentials_exposed": False}


@app.get("/formations")
def formations(q: str = "", limit: int = 100) -> dict[str, Any]:
    path = Settings.from_env().repository_root / "data" / "formations.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    needle = q.casefold().strip()
    if needle:
        rows = [row for row in rows if needle in " ".join(row.values()).casefold()]
    return {"items": rows[: min(max(limit, 1), 500)], "total_matches": len(rows)}


@app.get("/formations/{formation_id}")
def formation_context(formation_id: str):
    return _guard(lambda: _service().get_formation_context(formation_id))


@app.post("/jobs")
def create_job(body: dict[str, Any]):
    service = _service()
    return _guard(lambda: service.get_job_status(service.create_job(body["formation_id"], body.get("previous_job_ids", [])).job_id))


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    return _guard(lambda: _service().get_job_status(job_id))


@app.post("/jobs/{job_id}/clues")
def set_clues(job_id: str, body: dict[str, Any]):
    service = _service()
    return _guard(lambda: service.get_job_status(service.set_clues(job_id, _clues(body["clues"])).job_id))


@app.post("/jobs/{job_id}/search-area")
def set_search_area(job_id: str, body: dict[str, Any]):
    service = _service()
    return _guard(lambda: service.get_job_status(service.set_search_area(
        job_id, body["geometry"], body.get("exclusions", []), body.get("provider", "manual"),
        body.get("query", ""), body.get("admin_context"),
    ).job_id))


@app.post("/jobs/{job_id}/imagery/search")
def search_imagery(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().search_imagery(
        job_id, provider_from_spec(body["provider"], body.get("provider_options", {})),
        body.get("collections"), body.get("date_start"), body.get("date_end"), body.get("limit"),
    ))


@app.post("/jobs/{job_id}/tiles")
def tiles(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().generate_tiles(
        job_id, body["imagery_item"], body.get("tile_size_m", 512), body.get("overlap", .25),
        body.get("scales", [1.0]), body.get("rotations", [0.0]),
        body.get("representations", ["color", "edge", "gradient"]),
    ))


@app.post("/jobs/{job_id}/rank")
def rank(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().rank_tiles(
        job_id, Path(body["source_image_path"]), body["tile_manifest"], body.get("top_k", 20),
        Path(body["mask_path"]) if body.get("mask_path") else None,
    ))


@app.post("/jobs/{job_id}/match")
def match(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().match_candidate(job_id, Path(body["source_image_path"]), body["tile"], body.get("retrieval_score", 0)))


@app.post("/jobs/{job_id}/validate")
def validate(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().validate_registration(
        job_id, body["registration_candidate_id"], body["controls"], body["held_out_checkpoints"],
        body["reviewer"], body.get("uncertainty_components"),
    ))


@app.post("/jobs/{job_id}/review")
def review(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().save_review(job_id, body["review"], body.get("checkpoint_validation")))


@app.post("/jobs/{job_id}/orientation")
def orientation(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().measure_component(
        job_id, body["registration_candidate"], body["tile"], body["endpoint_a_px"], body["endpoint_b_px"],
        body["endpoint_uncertainty_m"], body.get("directionality", "bidirectional"),
    ))


@app.post("/jobs/{job_id}/overlay")
def overlay(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().generate_local_overlay(
        job_id, body["review"], body["registration_candidate"], body["tile"], Path(body["source_image_path"]),
        body.get("public_export", False),
    ))


@app.post("/jobs/{job_id}/promote")
def promote(job_id: str, body: dict[str, Any]):
    return _guard(lambda: _service().promote_reviewed_resolution(
        job_id, body["review"], body["longitude"], body["latitude"], body["coordinate_method"], body.get("confirm", False),
    ))


@app.get("/artifact")
def artifact(path: str = Query(...)):
    return _guard(lambda: _service().artifacts.load(path))


@app.get("/file")
def local_file(path: str = Query(...)):
    settings = Settings.from_env()
    requested = Path(path).resolve()
    cache = settings.cache_root.resolve()
    if cache not in requested.parents or requested.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".kml", ".kmz", ".json"}:
        raise HTTPException(status_code=403, detail="only safe geolocator-cache artifacts may be served")
    if not requested.is_file() or requested.stat().st_size > settings.max_download_bytes:
        raise HTTPException(status_code=404, detail="artifact file not found or exceeds the configured limit")
    return FileResponse(requested)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    container_bind = host == "0.0.0.0" and os.getenv("CROP_CIRCLE_GEO_ALLOW_CONTAINER_BIND") == "true"
    if host not in {"127.0.0.1", "localhost", "::1"} and not container_bind:
        raise ValueError("the MVP API is localhost-only")
    import uvicorn
    uvicorn.run(app, host=host, port=port)
