"""Small helpers for angular uncertainty propagation."""

from __future__ import annotations

import math


def lateral_uncertainty_m(distance_m: float, azimuth_uncertainty_deg: float) -> float:
    return abs(float(distance_m) * math.sin(math.radians(float(azimuth_uncertainty_deg))))
