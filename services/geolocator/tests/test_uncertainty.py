from crop_circle_geo.validation.uncertainty import conservative_uncertainty_m


def test_uncertainty_includes_checkpoint_floor_and_all_components():
    value = conservative_uncertainty_m(
        {"p95_m": 12, "maximum_m": 15}, 2, 3, 1, 4, 5, 6,
    )
    assert value["coordinate_uncertainty_m"] > 24
    assert value["checkpoint_floor_m"] == 15
    assert "not a probabilistic confidence interval" in value["limitations"][0]

