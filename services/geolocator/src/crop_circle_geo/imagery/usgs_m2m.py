"""Narrow USGS M2M adapter; live credentials are environment-only."""

from __future__ import annotations

import os
from typing import Any, Protocol

from ..provenance import canonical_json, sha256_bytes, stable_id, utc_now
from .base import ImageryProvider


class JsonTransport(Protocol):
    def post(self, path: str, payload: dict[str, Any], api_key: str | None = None) -> dict[str, Any]: ...


class UsgsM2MProvider(ImageryProvider):
    name = "usgs_m2m"

    def __init__(self, transport: JsonTransport, dataset_name: str, username: str | None = None, token: str | None = None):
        self.transport = transport
        self.dataset_name = dataset_name
        self.username = username or os.getenv("USGS_M2M_USERNAME")
        self.token = token or os.getenv("USGS_M2M_TOKEN")

    def _api_key(self) -> str:
        if self.token:
            return self.token
        if not self.username:
            raise RuntimeError("USGS_M2M_USERNAME and USGS_M2M_TOKEN are not configured")
        response = self.transport.post("login-token", {"username": self.username, "token": os.getenv("USGS_M2M_APP_TOKEN", "")})
        if response.get("errorCode") or not response.get("data"):
            raise RuntimeError(f"USGS M2M authentication failed: {response.get('errorMessage', 'unknown error')}")
        return str(response["data"])

    def search(self, polygon_wgs84, date_start, date_end, collections=None, limit=100):
        if limit <= 0:
            raise ValueError("imagery search limit must be positive")
        api_key = self._api_key()
        payload = {
            "datasetName": self.dataset_name,
            "maxResults": limit,
            "sceneFilter": {
                "spatialFilter": {"filterType": "geojson", "geoJson": polygon_wgs84},
                "acquisitionFilter": {"start": date_start, "end": date_end},
            },
        }
        response = self.transport.post("scene-search", payload, api_key=api_key)
        if response.get("errorCode"):
            raise RuntimeError(f"USGS M2M search failed: {response.get('errorMessage', response['errorCode'])}")
        output = []
        for scene in response.get("data", {}).get("results", [])[:limit]:
            source_metadata = dict(scene)
            scene_id = str(scene.get("entityId") or scene.get("displayId"))
            geometry = scene.get("spatialCoverage") or scene.get("geometry")
            bbox = scene.get("boundingBox") or []
            identity = {"dataset": self.dataset_name, "scene_id": scene_id}
            output.append({
                "schema_version": "crop-circle-atlas/imagery-item/v1", "imagery_item_id": stable_id("img", identity),
                "provider": self.name, "collection": self.dataset_name, "item_id": scene_id,
                "acquisition": {"start": scene.get("acquisitionDate"), "end": scene.get("acquisitionDate")},
                "geometry": geometry, "bbox": bbox, "crs": str(scene.get("spatialReference") or "unknown"),
                "ground_sample_distance_m": scene.get("spatialResolution"), "source_scale": scene.get("scale"),
                "asset": {"href": None, "local_reference": None, "media_type": None},
                "rights": {"status": "item_rights_review_required", "holder": "USGS", "license": None, "proof": None, "public_derivative_export_allowed": False},
                "retrieved_at": utc_now(), "source_metadata_sha256": sha256_bytes(canonical_json(source_metadata)),
                "local_file_sha256": None, "orthorectified": bool(scene.get("orthorectified", False)),
                "provider_metadata": source_metadata,
            })
        return output

    def request_download(self, entity_ids: list[str]) -> dict[str, Any]:
        response = self.transport.post(
            "download-options", {"datasetName": self.dataset_name, "entityIds": entity_ids}, api_key=self._api_key(),
        )
        if response.get("errorCode"):
            raise RuntimeError(f"USGS M2M download-options failed: {response.get('errorMessage')}")
        return response.get("data", {})
