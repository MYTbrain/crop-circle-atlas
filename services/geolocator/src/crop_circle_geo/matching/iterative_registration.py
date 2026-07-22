"""Original iterative refinement coordinator inspired by published coarse-to-fine principles."""

from __future__ import annotations

from typing import Any, Callable


def quality_tuple(candidate: dict[str, Any]) -> tuple[float, float, float, float]:
    metrics = candidate.get("metrics", {})
    return (
        0 if metrics.get("degenerate") else 1,
        float(metrics.get("spatial_distribution", 0)),
        float(metrics.get("inlier_ratio", 0)),
        -float(metrics.get("reprojection_rmse_px", float("inf"))),
    )


class IterativeRegistration:
    """Refine only when independent quality dimensions improve."""

    def __init__(self, matcher, refinement_tile: Callable[[dict[str, Any]], dict[str, Any]], max_iterations: int = 3):
        self.matcher = matcher
        self.refinement_tile = refinement_tile
        self.max_iterations = max(1, min(5, max_iterations))

    def run(self, source_image, initial_tile, retrieval_score=0):
        history = []
        current_tile = initial_tile
        best = self.matcher.match(source_image, current_tile, retrieval_score)
        history.append(best["registration_candidate_id"])
        for _ in range(1, self.max_iterations):
            proposed_tile = self.refinement_tile(best)
            candidate = self.matcher.match(source_image, proposed_tile, retrieval_score)
            history.append(candidate["registration_candidate_id"])
            previous = quality_tuple(best)
            proposed = quality_tuple(candidate)
            improves_two = sum(new > old for old, new in zip(previous, proposed, strict=True)) >= 2
            if not improves_two or proposed[0] < previous[0]:
                break
            best = candidate
            current_tile = proposed_tile
        return {"best": best, "candidate_history": history, "iteration_count": len(history)}
