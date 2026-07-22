#!/usr/bin/env python3
"""Fail when selected geolocator dependencies disappear from the license audit."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKERS = {
    "affine": "Affine", "jsonschema": "jsonschema", "numpy": "NumPy",
    "opencv-python-headless": "opencv-python-headless", "pillow": "Pillow", "pyproj": "pyproj",
    "rasterio": "Rasterio", "shapely": "Shapely", "fastapi": "FastAPI", "mcp": "MCP Python SDK",
    "uvicorn": "Uvicorn", "planetary-computer": "Planetary Computer SDK", "pystac-client": "PySTAC Client",
    "pytest": "pytest", "pytest-cov": "pytest-cov",
}


def package_name(requirement: str) -> str:
    return re.split(r"[<>=!~\[]", requirement, maxsplit=1)[0].strip().lower()


def main() -> int:
    project = tomllib.loads((ROOT / "services" / "geolocator" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = list(project["dependencies"])
    for group in project["optional-dependencies"].values():
        requirements.extend(group)
    selected = {package_name(item) for item in requirements}
    audit = (ROOT / "docs" / "GEOLOCATOR_LICENSES.md").read_text(encoding="utf-8")
    missing = sorted(name for name in selected if name in MARKERS and MARKERS[name] not in audit)
    if missing:
        raise SystemExit("license audit missing selected packages: " + ", ".join(missing))
    for required in ("GDAL", "GEOS", "PROJ", "EarthMatch", "EarthLoc", "VisMatch", "LightGlue", "AnyLoc", "MegaLoc", "Leaflet.DistortableImage", "Allmaps", "TiTiler", "rio-cogeo"):
        if required not in audit:
            raise SystemExit(f"license audit missing evaluated component: {required}")
    print(f"PASS selected_packages={len(selected)} evaluated_components=13")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
