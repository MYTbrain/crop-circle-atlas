from __future__ import annotations

import asyncio
from pathlib import Path

from crop_circle_geo.mcp_server import mcp


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPECTED = {
    "get_formation_context", "create_field_resolution_job", "set_location_clues", "resolve_search_area",
    "search_imagery", "generate_candidate_tiles", "rank_candidate_tiles", "match_candidate",
    "validate_registration", "get_job_status", "save_review_decision", "measure_registered_component",
    "generate_local_overlay", "promote_reviewed_resolution",
}


def test_mcp_exposes_and_invokes_compact_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("CROP_CIRCLE_ATLAS_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("CROP_CIRCLE_GEO_CACHE", str(tmp_path))
    async def invoke():
        tools = await mcp.list_tools()
        assert {tool.name for tool in tools} == EXPECTED
        _, context = await mcp.call_tool("get_formation_context", {"formation_id": "cc_e5724a3476de"})
        assert context["formation"]["formation_id"] == "cc_e5724a3476de"
        _, created = await mcp.call_tool("create_field_resolution_job", {"formation_id": "cc_e5724a3476de"})
        assert created["job"]["state"] == "queued"
        assert created["job"]["artifacts"] == {}
    asyncio.run(invoke())
