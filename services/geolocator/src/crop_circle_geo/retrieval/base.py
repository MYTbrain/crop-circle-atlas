"""Retrieval interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Retriever(ABC):
    name: str
    version: str

    @abstractmethod
    def rank(self, source_image: Path, tiles: list[dict[str, Any]], top_k: int, mask: Path | None = None) -> list[dict[str, Any]]:
        """Return a bounded, score-sorted candidate list."""

