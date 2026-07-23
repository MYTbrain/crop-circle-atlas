"""Deterministic local GeoTIFF/COG discovery and cutouts."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import rasterio
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping, shape

from ..provenance import canonical_json, sha256_bytes, sha256_file, stable_id, utc_now
from .base import ImageryProvider


def _date_overlaps(start: str | None, end: str | None, item_start: str | None, item_end: str | None) -> bool:
    if not start and not end:
        return True
    query_start = date.fromisoformat((start or "0001-01-01")[:10])
    query_end = date.fromisoformat((end or "9999-12-31")[:10])
    candidate_start = date.fromisoformat((item_start or "0001-01-01")[:10])
    candidate_end = date.fromisoformat((item_end or item_start or "9999-12-31")[:10])
    return candidate_start <= query_end and query_start <= candidate_end


class LocalRasterProvider(ImageryProvider):
    name = "local_raster"

    def __init__(self, raster_root: Path):
        self.raster_root = raster_root.resolve()

    @staticmethod
    def metadata_path(raster_path: Path) -> Path:
        return raster_path.with_suffix(raster_path.suffix + ".metadata.json")

    def _normalize(self, path: Path) -> dict[str, Any]:
        metadata_path = self.metadata_path(path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
        with rasterio.open(path) as dataset:
            if not dataset.crs:
                raise ValueError(f"local raster has no CRS: {path}")
            bounds_wgs84 = transform_bounds(dataset.crs, "EPSG:4326", *dataset.bounds, densify_pts=21)
            geometry = mapping(box(*bounds_wgs84))
            gsd = metadata.get("ground_sample_distance_m")
            if gsd is None and dataset.crs.is_projected:
                gsd = float((abs(dataset.transform.a) + abs(dataset.transform.e)) / 2)
            source_metadata = {
                "path_name": path.name,
                "dataset_crs": dataset.crs.to_string(),
                "dataset_bounds": list(dataset.bounds),
                "width": dataset.width,
                "height": dataset.height,
                "metadata": metadata,
            }
        identity = {
            "provider": self.name,
            "collection": metadata.get("collection", "local"),
            "item_id": metadata.get("item_id", path.stem),
            "local_file_sha256": sha256_file(path),
        }
        return {
            "schema_version": "crop-circle-atlas/imagery-item/v1",
            "imagery_item_id": stable_id("img", identity),
            "provider": self.name,
            "collection": str(metadata.get("collection", "local")),
            "item_id": str(metadata.get("item_id", path.stem)),
            "acquisition": {"start": metadata.get("acquisition_start"), "end": metadata.get("acquisition_end") or metadata.get("acquisition_start")},
            "geometry": geometry,
            "bbox": list(bounds_wgs84),
            "crs": source_metadata["dataset_crs"],
            "ground_sample_distance_m": float(gsd) if gsd is not None else None,
            "source_scale": metadata.get("source_scale"),
            "asset": {"href": None, "local_reference": str(path), "media_type": "image/tiff; application=geotiff"},
            "rights": metadata.get("rights", {
                "status": "local_analysis_only", "holder": None, "license": None, "proof": None,
                "public_derivative_export_allowed": False,
            }),
            "retrieved_at": utc_now(),
            "source_metadata_sha256": sha256_bytes(canonical_json(source_metadata)),
            "local_file_sha256": identity["local_file_sha256"],
            "orthorectified": bool(metadata.get("orthorectified", False)),
            "provider_metadata": source_metadata,
        }

    def search(self, polygon_wgs84, date_start, date_end, collections=None, limit=100):
        if limit <= 0:
            raise ValueError("imagery search limit must be positive")
        query = shape(polygon_wgs84)
        if query.is_empty or not query.is_valid:
            raise ValueError("imagery query polygon is invalid")
        results = []
        candidates = sorted({*self.raster_root.glob("*.tif"), *self.raster_root.glob("*.tiff")})
        for path in candidates:
            item = self._normalize(path)
            if collections and item["collection"] not in collections:
                continue
            acquisition = item["acquisition"]
            if not _date_overlaps(date_start, date_end, acquisition["start"], acquisition["end"]):
                continue
            if not query.intersects(shape(item["geometry"])):
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def cutout(self, item, bounds, destination):
        source = Path(item["asset"]["local_reference"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(source) as dataset:
            window = from_bounds(*bounds, transform=dataset.transform).round_offsets().round_lengths()
            full = Window(0, 0, dataset.width, dataset.height)
            window = window.intersection(full)
            data = dataset.read(window=window)
            profile = dataset.profile.copy()
            profile.update(width=int(window.width), height=int(window.height), transform=dataset.window_transform(window))
            with rasterio.open(destination, "w", **profile) as output:
                output.write(data)
        return destination

