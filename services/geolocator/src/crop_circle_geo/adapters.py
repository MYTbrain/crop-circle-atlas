"""Small adapter helpers shared by the CLI, MCP server, and local API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .imagery.local_raster import LocalRasterProvider
from .imagery.planetary_computer import PlanetaryComputerProvider
from .imagery.stac import StacProvider
from .imagery.usgs_m2m import UsgsHttpTransport, UsgsM2MProvider


def read_json(value: str | Path | dict[str, Any] | list[Any]) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = str(value)
    path = Path(text)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(text)


def provider_from_spec(name: str, options: dict[str, Any]):
    normalized = name.strip().lower()
    if normalized in {"local", "local_raster"}:
        root = options.get("raster_root")
        if not root:
            raise ValueError("local_raster requires raster_root")
        return LocalRasterProvider(Path(root))
    if normalized == "stac":
        endpoint = options.get("endpoint")
        if not endpoint:
            raise ValueError("stac requires endpoint")
        return StacProvider(endpoint, asset_key=options.get("asset_key", "image"))
    if normalized in {"planetary", "planetary_computer"}:
        return PlanetaryComputerProvider(
            endpoint=options.get("endpoint", "https://planetarycomputer.microsoft.com/api/stac/v1"),
            asset_key=options.get("asset_key", "image"),
        )
    if normalized in {"usgs", "usgs_m2m"}:
        dataset = options.get("dataset_name")
        if not dataset:
            raise ValueError("usgs_m2m requires dataset_name")
        return UsgsM2MProvider(UsgsHttpTransport(), dataset)
    raise ValueError(f"unsupported imagery provider: {name}")


def compact_result(value: dict[str, Any]) -> dict[str, Any]:
    """Keep orchestration results textual and bounded; paths retain full evidence."""
    result = dict(value)
    candidate = result.get("candidate")
    if isinstance(candidate, dict) and len(candidate.get("matches", [])) > 25:
        candidate = dict(candidate)
        candidate["matches_returned"] = 25
        candidate["matches_total"] = len(candidate["matches"])
        candidate["matches"] = candidate["matches"][:25]
        result["candidate"] = candidate
    rankings = result.get("rankings")
    if isinstance(rankings, list) and len(rankings) > 50:
        result["rankings"] = rankings[:50]
        result["rankings_total"] = len(rankings)
    return result

