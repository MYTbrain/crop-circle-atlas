"""Local MCP adapter for deterministic crop-circle field-resolution operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .adapters import compact_result, provider_from_spec
from .config import Settings
from .models import Citation, Clue
from .service import FieldResolutionService


mcp = FastMCP("Crop Circle Geolocator", json_response=True)


def _service() -> FieldResolutionService:
    return FieldResolutionService(Settings.from_env())


def _clues(values: list[dict[str, Any]]) -> list[Clue]:
    return [Clue(
        kind=item["kind"], value=item["value"], confidence=float(item["confidence"]),
        citations=tuple(Citation(**citation) for citation in item.get("citations", [])),
        qualifiers=dict(item.get("qualifiers", {})),
    ) for item in values]


@mcp.tool()
def get_formation_context(formation_id: str) -> dict[str, Any]:
    """Return report metadata, source assertions, and locality warnings for one formation."""
    return _service().get_formation_context(formation_id)


@mcp.tool()
def create_field_resolution_job(formation_id: str, previous_job_ids: list[str] | None = None) -> dict[str, Any]:
    """Create an append-only field-resolution job without changing atlas coordinates."""
    service = _service(); job = service.create_job(formation_id, previous_job_ids or [])
    return service.get_job_status(job.job_id)


@mcp.tool()
def set_location_clues(job_id: str, clues: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist cited structured location clues for a queued job."""
    service = _service(); job = service.set_clues(job_id, _clues(clues))
    return service.get_job_status(job.job_id)


@mcp.tool()
def resolve_search_area(job_id: str, geometry: dict[str, Any], exclusions: list[dict[str, Any]] | None = None, provider: str = "manual", query: str = "", admin_context: dict[str, str] | None = None) -> dict[str, Any]:
    """Persist a bounded locality_search_area polygon; it is never a formation site."""
    service = _service(); job = service.set_search_area(job_id, geometry, exclusions or [], provider, query, admin_context)
    return service.get_job_status(job.job_id)


@mcp.tool()
def search_imagery(job_id: str, provider: str, provider_options: dict[str, Any], collections: list[str] | None = None, date_start: str | None = None, date_end: str | None = None, limit: int | None = None) -> dict[str, Any]:
    """Search a configured local, STAC, Planetary Computer, or USGS provider."""
    return compact_result(_service().search_imagery(job_id, provider_from_spec(provider, provider_options), collections, date_start, date_end, limit))


@mcp.tool()
def generate_candidate_tiles(job_id: str, imagery_item: dict[str, Any], tile_size_m: float = 512, overlap: float = 0.25, scales: list[float] | None = None, rotations: list[float] | None = None, representations: list[str] | None = None) -> dict[str, Any]:
    """Generate cached metre-based raster tiles with explicit physical footprints."""
    return compact_result(_service().generate_tiles(job_id, imagery_item, tile_size_m, overlap, scales or [1.0], rotations or [0.0], representations or ["color", "edge", "gradient"]))


@mcp.tool()
def rank_candidate_tiles(job_id: str, source_image_path: str, tile_manifest: dict[str, Any], top_k: int = 20, mask_path: str | None = None) -> dict[str, Any]:
    """Rank candidate tiles with the deterministic CPU edge-gradient baseline."""
    return compact_result(_service().rank_tiles(job_id, Path(source_image_path), tile_manifest, top_k, Path(mask_path) if mask_path else None))


@mcp.tool()
def match_candidate(job_id: str, source_image_path: str, tile: dict[str, Any], retrieval_score: float = 0) -> dict[str, Any]:
    """Attempt SIFT/RANSAC registration; output remains review_required at best."""
    return compact_result(_service().match_candidate(job_id, Path(source_image_path), tile, retrieval_score))


@mcp.tool()
def validate_registration(job_id: str, registration_candidate_id: str, controls: list[dict[str, Any]], held_out_checkpoints: list[dict[str, Any]], reviewer: str, uncertainty_components: dict[str, float] | None = None) -> dict[str, Any]:
    """Validate controls and independent checkpoints in physical ground metres."""
    return compact_result(_service().validate_registration(job_id, registration_candidate_id, controls, held_out_checkpoints, reviewer, uncertainty_components))


@mcp.tool()
def get_job_status(job_id: str) -> dict[str, Any]:
    """Return the latest immutable job version, warnings, history count, and next states."""
    return _service().get_job_status(job_id)


@mcp.tool()
def save_review_decision(job_id: str, review: dict[str, Any], checkpoint_validation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist an explicit human decision; machine candidates are never silently promoted."""
    return compact_result(_service().save_review(job_id, review, checkpoint_validation))


@mcp.tool()
def measure_registered_component(job_id: str, registration_candidate: dict[str, Any], tile: dict[str, Any], endpoint_a_px: list[float], endpoint_b_px: list[float], endpoint_uncertainty_m: float, directionality: str = "bidirectional") -> dict[str, Any]:
    """Measure a reviewed straight component as true-north azimuth with uncertainty."""
    return compact_result(_service().measure_component(job_id, registration_candidate, tile, endpoint_a_px, endpoint_b_px, endpoint_uncertainty_m, directionality))


@mcp.tool()
def generate_local_overlay(job_id: str, review: dict[str, Any], registration_candidate: dict[str, Any], tile: dict[str, Any], source_image_path: str, public_export: bool = False) -> dict[str, Any]:
    """Generate local KML/KMZ; public derivatives fail closed on insufficient rights."""
    return compact_result(_service().generate_local_overlay(job_id, review, registration_candidate, tile, Path(source_image_path), public_export))


@mcp.tool()
def promote_reviewed_resolution(job_id: str, review: dict[str, Any], longitude: float, latitude: float, coordinate_method: str, confirm: bool = False) -> dict[str, Any]:
    """Create a separately confirmed canonical-registry patch proposal without applying it."""
    return compact_result(_service().promote_reviewed_resolution(job_id, review, longitude, latitude, coordinate_method, confirm))


if __name__ == "__main__":
    mcp.run()
