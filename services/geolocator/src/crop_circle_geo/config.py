"""Validated local-worker configuration with conservative resource limits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _unit_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not 0 <= value < 1:
        raise ValueError(f"{name} must be at least zero and less than one")
    return value


def default_cache_root() -> Path:
    configured = os.getenv("CROP_CIRCLE_GEO_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    local_app = os.getenv("LOCALAPPDATA")
    base = Path(local_app) if local_app else Path.home() / ".cache"
    return (base / "crop-circle-atlas" / "geolocator").resolve()


@dataclass(frozen=True)
class Settings:
    cache_root: Path
    repository_root: Path
    model_cache_root: Path | None = None
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    max_search_area_sq_km: float = 2_500.0
    max_imagery_items: int = 100
    max_tiles: int = 10_000
    max_top_k: int = 50
    max_download_bytes: int = 1_073_741_824
    processing_timeout_seconds: int = 3_600
    concurrent_workers: int = 2
    tile_overlap: float = 0.25

    @classmethod
    def from_env(cls, repository_root: Path | None = None) -> "Settings":
        root = repository_root or Path(os.getenv("CROP_CIRCLE_ATLAS_ROOT", Path.cwd()))
        return cls(
            cache_root=default_cache_root(),
            repository_root=root.resolve(),
            model_cache_root=Path(os.getenv("CROP_CIRCLE_GEO_MODEL_CACHE", default_cache_root() / "models")).expanduser().resolve(),
            api_host=os.getenv("CROP_CIRCLE_GEO_API_HOST", "127.0.0.1"),
            api_port=_positive_int("CROP_CIRCLE_GEO_API_PORT", 8765),
            max_search_area_sq_km=_positive_float("CROP_CIRCLE_GEO_MAX_SEARCH_AREA_SQ_KM", 2_500),
            max_imagery_items=_positive_int("CROP_CIRCLE_GEO_MAX_IMAGERY_ITEMS", 100),
            max_tiles=_positive_int("CROP_CIRCLE_GEO_MAX_TILES", 10_000),
            max_top_k=_positive_int("CROP_CIRCLE_GEO_MAX_TOP_K", 50),
            max_download_bytes=_positive_int("CROP_CIRCLE_GEO_MAX_DOWNLOAD_BYTES", 1_073_741_824),
            processing_timeout_seconds=_positive_int("CROP_CIRCLE_GEO_TIMEOUT_SECONDS", 3_600),
            concurrent_workers=_positive_int("CROP_CIRCLE_GEO_CONCURRENT_WORKERS", 2),
            tile_overlap=_unit_float("CROP_CIRCLE_GEO_TILE_OVERLAP", 0.25),
        )

    def ensure_cache(self) -> Path:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        return self.cache_root
