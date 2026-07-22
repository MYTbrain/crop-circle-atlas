"""STAC search adapter with normalized evidence records."""

from __future__ import annotations

from typing import Any, Callable

from ..provenance import canonical_json, sha256_bytes, stable_id, utc_now
from .base import ImageryProvider


class StacProvider(ImageryProvider):
    name = "stac"

    def __init__(
        self,
        endpoint: str,
        asset_key: str = "image",
        client_factory: Callable[[str], Any] | None = None,
        asset_transform: Callable[[Any], Any] | None = None,
    ):
        self.endpoint = endpoint
        self.asset_key = asset_key
        self._client_factory = client_factory
        self._asset_transform = asset_transform or (lambda asset: asset)

    def _client(self):
        if self._client_factory:
            return self._client_factory(self.endpoint)
        try:
            from pystac_client import Client
        except ImportError as exc:
            raise RuntimeError("install the stac extra to use STAC providers") from exc
        return Client.open(self.endpoint)

    def search(self, polygon_wgs84, date_start, date_end, collections=None, limit=100):
        if limit <= 0:
            raise ValueError("imagery search limit must be positive")
        interval = None
        if date_start or date_end:
            interval = f"{date_start or '..'}/{date_end or '..'}"
        search = self._client().search(intersects=polygon_wgs84, datetime=interval, collections=collections, max_items=limit)
        results = []
        for item in search.items():
            assets = item.assets
            if self.asset_key not in assets:
                continue
            asset = self._asset_transform(assets[self.asset_key])
            properties = dict(item.properties)
            acquisition = properties.get("datetime") or properties.get("start_datetime")
            end = properties.get("end_datetime") or acquisition
            collection = item.collection_id or properties.get("collection", "")
            source_metadata = item.to_dict()
            identity = {"endpoint": self.endpoint, "collection": collection, "item_id": item.id, "asset": asset.href}
            results.append({
                "schema_version": "crop-circle-atlas/imagery-item/v1", "imagery_item_id": stable_id("img", identity),
                "provider": self.name, "collection": collection, "item_id": item.id,
                "acquisition": {"start": acquisition, "end": end}, "geometry": item.geometry,
                "bbox": list(item.bbox), "crs": str(properties.get("proj:code") or properties.get("proj:epsg") or "unknown"),
                "ground_sample_distance_m": properties.get("gsd"), "source_scale": None,
                "asset": {"href": asset.href, "local_reference": None, "media_type": getattr(asset, "media_type", None)},
                "rights": {"status": "provider_terms_review_required", "holder": None, "license": properties.get("license"), "proof": self.endpoint, "public_derivative_export_allowed": False},
                "retrieved_at": utc_now(), "source_metadata_sha256": sha256_bytes(canonical_json(source_metadata)),
                "local_file_sha256": None, "orthorectified": bool(properties.get("crop-circle:orthorectified", True)),
                "provider_metadata": source_metadata,
            })
            if len(results) >= limit:
                break
        return results
