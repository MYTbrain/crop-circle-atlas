from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import rasterio
from rasterio.transform import from_origin


def create_synthetic_raster(root: Path):
    rng = np.random.default_rng(42)
    reference = np.full((1024, 1024, 3), 205, dtype=np.uint8)
    reference = np.clip(reference.astype(np.int16) + rng.normal(0, 7, reference.shape), 0, 255).astype(np.uint8)
    for index in range(24):
        x = int(rng.integers(15, 490))
        y = int(rng.integers(15, 490))
        color = tuple(int(value) for value in rng.integers(20, 190, 3))
        if index % 3 == 0:
            cv2.circle(reference, (x, y), int(rng.integers(8, 28)), color, -1)
        elif index % 3 == 1:
            cv2.rectangle(reference, (x, y), (min(510, x + 35), min(510, y + 24)), color, -1)
        else:
            cv2.line(reference, (x, y), (min(510, x + 90), min(510, y + 45)), color, 5)
    cv2.putText(reference, "NORTH FARM 97", (60, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (15, 35, 15), 3, cv2.LINE_AA)
    cv2.line(reference, (0, 510), (1023, 510), (40, 40, 40), 10)
    cv2.line(reference, (510, 0), (510, 1023), (60, 60, 60), 8)
    for x in range(540, 1000, 45):
        cv2.line(reference, (x, 550), (x + 15, 990), (100, 120, 80), 2)
    raster_path = root / "synthetic.tif"
    profile = {
        "driver": "GTiff", "height": 1024, "width": 1024, "count": 3, "dtype": "uint8",
        "crs": "EPSG:32610", "transform": from_origin(500000, 5001000, 1, 1), "compress": "deflate",
    }
    with rasterio.open(raster_path, "w", **profile) as dataset:
        dataset.write(np.moveaxis(reference, -1, 0))
    metadata = {
        "collection": "synthetic-open", "item_id": "synthetic-001",
        "acquisition_start": "1997-06-28", "acquisition_end": "1997-06-28",
        "orthorectified": True, "ground_sample_distance_m": 1,
        "rights": {"status": "cc0", "holder": None, "license": "CC0-1.0", "proof": "synthetic-test-fixture", "public_derivative_export_allowed": True},
    }
    raster_path.with_suffix(".tif.metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    source_quad = np.float32([[35, 40], [470, 25], [485, 475], [20, 485]])
    source_corners = np.float32([[0, 0], [399, 0], [399, 399], [0, 399]])
    reference_to_source = cv2.getPerspectiveTransform(source_quad, source_corners)
    source = cv2.warpPerspective(reference, reference_to_source, (400, 400), flags=cv2.INTER_CUBIC)
    source = cv2.GaussianBlur(source, (3, 3), 0.6)
    source = cv2.convertScaleAbs(source, alpha=0.92, beta=8)
    source_path = root / "source.png"
    cv2.imwrite(str(source_path), source)
    source_to_reference = np.linalg.inv(reference_to_source)
    return raster_path, source_path, source_to_reference

