"""Common imagery provider contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ImageryProvider(ABC):
    name: str

    @abstractmethod
    def search(
        self,
        polygon_wgs84: dict[str, Any],
        date_start: str | None,
        date_end: str | None,
        collections: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return normalized imagery-item dictionaries."""

    def cutout(self, item: dict[str, Any], bounds: tuple[float, float, float, float], destination: Path) -> Path:
        raise NotImplementedError(f"{self.name} does not implement local cutouts")

