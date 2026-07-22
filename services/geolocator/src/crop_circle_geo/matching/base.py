"""Normalized registration matcher interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class RegistrationMatcher(ABC):
    name: str
    version: str

    @abstractmethod
    def match(self, source_image: Path, tile: dict[str, Any], retrieval_score: float = 0) -> dict[str, Any]:
        """Return a registration-candidate dictionary."""


class LineDominantMatcher(RegistrationMatcher):
    """Extension point for future road and field-boundary matching."""

