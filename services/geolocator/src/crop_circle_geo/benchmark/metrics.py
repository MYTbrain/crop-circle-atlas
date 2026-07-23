"""Synthetic and real-world benchmark metrics kept explicitly separate."""

from __future__ import annotations

import math
from typing import Any, Iterable


def retrieval_recall(ranks: Iterable[int | None], cutoffs=(1, 5, 10, 50)) -> dict[str, float]:
    values = list(ranks)
    if not values:
        return {f"top_{cutoff}_recall": 0.0 for cutoff in cutoffs}
    return {
        f"top_{cutoff}_recall": sum(rank is not None and rank <= cutoff for rank in values) / len(values)
        for cutoff in cutoffs
    }


def stage_summary(stages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "processing_time_seconds": {stage["name"]: stage.get("duration_seconds", 0) for stage in stages},
        "bytes_read": sum(int(stage.get("bytes_read", 0)) for stage in stages),
        "bytes_downloaded": sum(int(stage.get("bytes_downloaded", 0)) for stage in stages),
        "cache_hits": sum(int(stage.get("cache_hits", 0)) for stage in stages),
        "cache_misses": sum(int(stage.get("cache_misses", 0)) for stage in stages),
    }

