from __future__ import annotations

from pathlib import Path

from crop_circle_geo.benchmark.synthetic import create_synthetic_case


def create_synthetic_raster(root: Path):
    return create_synthetic_case(root)
