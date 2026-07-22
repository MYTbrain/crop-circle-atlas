"""Windowed, cacheable candidate-tile generation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import rasterio
from PIL import Image
from rasterio.windows import Window
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping

from .provenance import canonical_json, sha256_bytes, sha256_file, stable_id


REPRESENTATIONS = {"color", "grayscale", "edge", "gradient"}


def tile_cache_key(item: dict[str, Any], parameters: dict[str, Any], window: dict[str, int]) -> str:
    return sha256_bytes(canonical_json({
        "imagery_item_id": item["imagery_item_id"],
        "local_file_sha256": item.get("local_file_sha256"),
        "parameters": parameters,
        "window": window,
        "generator": "crop-circle-geolocator/tile-generator/v1",
    }))


def _uint8_color(data: np.ndarray) -> np.ndarray:
    bands = data[: min(3, data.shape[0])]
    if bands.shape[0] == 1:
        bands = np.repeat(bands, 3, axis=0)
    if bands.shape[0] == 2:
        bands = np.concatenate([bands, bands[:1]], axis=0)
    image = np.moveaxis(bands, 0, -1).astype(np.float32)
    result = np.zeros_like(image, dtype=np.uint8)
    for channel in range(image.shape[2]):
        plane = image[..., channel]
        valid = plane[np.isfinite(plane)]
        if not valid.size:
            continue
        low, high = np.percentile(valid, [2, 98])
        if high <= low:
            high = low + 1
        result[..., channel] = np.clip((plane - low) * (255 / (high - low)), 0, 255).astype(np.uint8)
    return result


def _representation(color: np.ndarray, kind: str) -> np.ndarray:
    if kind == "color":
        return color
    gray = cv2.cvtColor(color, cv2.COLOR_RGB2GRAY)
    if kind == "grayscale":
        return gray
    if kind == "edge":
        return cv2.Canny(gray, 60, 140, L2gradient=True)
    if kind == "gradient":
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        return cv2.normalize(cv2.magnitude(gx, gy), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    raise ValueError(f"unsupported representation: {kind}")


def generate_candidate_tiles(
    item: dict[str, Any],
    cache_root: Path,
    tile_size_m: float = 512,
    overlap: float = 0.25,
    scales: Iterable[float] = (1.0,),
    rotations: Iterable[float] = (0.0,),
    representations: Iterable[str] = ("color", "edge", "gradient"),
    max_tiles: int = 10_000,
) -> dict[str, Any]:
    if not 0 <= overlap < 1:
        raise ValueError("tile overlap must be in [0, 1)")
    if tile_size_m <= 0 or max_tiles <= 0:
        raise ValueError("tile size and max tiles must be positive")
    representation_list = tuple(dict.fromkeys(representations))
    if not representation_list or not set(representation_list) <= REPRESENTATIONS:
        raise ValueError("one or more tile representations are invalid")
    source = Path(item["asset"]["local_reference"])
    output_root = cache_root.resolve() / "tiles" / item["imagery_item_id"]
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    cache_hits = 0
    cache_misses = 0
    parameters = {
        "tile_size_m": tile_size_m, "overlap": overlap,
        "scales": [float(value) for value in scales], "rotations": [float(value) for value in rotations],
        "representations": list(representation_list),
    }
    with rasterio.open(source) as dataset:
        if not dataset.crs or not dataset.crs.is_projected:
            raise ValueError("candidate tiling requires a projected raster CRS with linear units")
        unit_name = (dataset.crs.linear_units or "").lower()
        if unit_name not in {"metre", "meter", "metres", "meters", "m"}:
            raise ValueError(f"candidate tiling requires metre-based projected CRS, got {unit_name or 'unknown units'}")
        resolution = (abs(dataset.transform.a) + abs(dataset.transform.e)) / 2
        for scale in parameters["scales"]:
            if scale <= 0:
                raise ValueError("tile scales must be positive")
            size_px = max(64, int(round(tile_size_m * scale / resolution)))
            step_px = max(1, int(round(size_px * (1 - overlap))))
            row_offsets = list(range(0, max(1, dataset.height - size_px + 1), step_px)) or [0]
            col_offsets = list(range(0, max(1, dataset.width - size_px + 1), step_px)) or [0]
            if row_offsets[-1] != max(0, dataset.height - size_px):
                row_offsets.append(max(0, dataset.height - size_px))
            if col_offsets[-1] != max(0, dataset.width - size_px):
                col_offsets.append(max(0, dataset.width - size_px))
            for row_off in row_offsets:
                for col_off in col_offsets:
                    window = Window(col_off, row_off, min(size_px, dataset.width), min(size_px, dataset.height))
                    window_dict = {"col_off": int(window.col_off), "row_off": int(window.row_off), "width": int(window.width), "height": int(window.height)}
                    data = None
                    raster_bounds = dataset.window_bounds(window)
                    wgs_bounds = transform_bounds(dataset.crs, "EPSG:4326", *raster_bounds, densify_pts=21)
                    for rotation in parameters["rotations"]:
                        for representation in representation_list:
                            variant = {**parameters, "scale": scale, "rotation": rotation, "representation": representation}
                            key = tile_cache_key(item, variant, window_dict)
                            tile_id = stable_id("tile", {"cache_key": key})
                            destination = output_root / f"{tile_id}.png"
                            metadata_path = destination.with_suffix(".json")
                            if destination.exists() and metadata_path.exists():
                                record = json.loads(metadata_path.read_text(encoding="utf-8"))
                                if record.get("raster_sha256") == sha256_file(destination):
                                    records.append(record)
                                    cache_hits += 1
                                    if len(records) > max_tiles:
                                        raise ValueError(f"tile count exceeds configured limit {max_tiles}")
                                    continue
                            if data is None:
                                data = dataset.read(window=window, boundless=False)
                            rendered = _representation(_uint8_color(data), representation)
                            image = Image.fromarray(rendered)
                            if rotation % 360:
                                image = image.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=0)
                            image.save(destination, format="PNG", optimize=False, compress_level=9)
                            record = {
                                "schema_version": "crop-circle-atlas/candidate-tile/v1",
                                "candidate_tile_id": tile_id, "imagery_item_id": item["imagery_item_id"],
                                "bounds": [float(value) for value in raster_bounds], "dimensions_px": [image.width, image.height],
                                "crs": dataset.crs.to_string(), "physical_footprint": mapping(box(*wgs_bounds)),
                                "overlap": overlap, "scale": scale, "rotation_deg": rotation, "representation": representation,
                                "raster_sha256": sha256_file(destination),
                                "embedding": {"model": "not_computed", "version": "0"},
                                "cache_key": key, "local_path": str(destination),
                            }
                            metadata_path.write_bytes(canonical_json(record) + b"\n")
                            records.append(record)
                            cache_misses += 1
                            if len(records) > max_tiles:
                                raise ValueError(f"tile count exceeds configured limit {max_tiles}")
    manifest = {
        "schema_version": "crop-circle-atlas/candidate-tile-manifest/v1",
        "imagery_item_id": item["imagery_item_id"], "parameters": parameters,
        "tile_count": len(records), "cache_hits": cache_hits, "cache_misses": cache_misses,
        "tiles": records,
    }
    manifest_path = output_root / f"manifest-{sha256_bytes(canonical_json(parameters))[:16]}.json"
    manifest_path.write_bytes(canonical_json(manifest) + b"\n")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
