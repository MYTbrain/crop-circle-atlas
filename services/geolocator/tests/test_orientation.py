from __future__ import annotations

import pytest

from crop_circle_geo.orientation.bearing import measure_registered_component


def test_registered_component_produces_true_bearing_and_remains_provisional():
    tile = {
        "bounds": [500000, 5000000, 501000, 5001000], "dimensions_px": [1000, 1000], "crs": "EPSG:32610",
    }
    result = measure_registered_component(
        [[1, 0, 0], [0, 1, 0], [0, 0, 1]], tile, [500, 800], [500, 200], 2, "forward",
    )
    assert result["forward_azimuth_true_deg"] == pytest.approx(0, abs=1)
    assert result["azimuth_uncertainty_deg"] > 0
    assert result["formal_alignment_eligible"] is False

