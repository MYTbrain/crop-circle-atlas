from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from crop_circle_geo.api import app


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_local_api_health_context_and_job(monkeypatch, tmp_path):
    monkeypatch.setenv("CROP_CIRCLE_ATLAS_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("CROP_CIRCLE_GEO_CACHE", str(tmp_path))
    async def invoke():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["credentials_exposed"] is False
            context = await client.get("/formations/cc_e5724a3476de")
            assert context.status_code == 200
            assert context.json()["locality"]["role"] != "exact_site"
            created = await client.post("/jobs", json={"formation_id": "cc_e5724a3476de"})
            assert created.status_code == 200
            assert created.json()["job"]["state"] == "queued"
    asyncio.run(invoke())
