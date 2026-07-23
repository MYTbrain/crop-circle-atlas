from crop_circle_geo.benchmark.synthetic import run_synthetic_benchmark


def test_complete_synthetic_benchmark_recovers_known_transform(tmp_path):
    result = run_synthetic_benchmark(tmp_path)
    assert result["result_kind"] == "synthetic_positive_mathematics_only"
    assert result["performance_claim_eligible"] is False
    assert result["retrieval"]["top_1_recall"] == 1
    assert result["registration"]["machine_status"] == "review_required"
    assert result["registration"]["center_error_m_at_1m_gsd"] < 4
    assert result["registration"]["footprint_corner_max_error_m_at_1m_gsd"] < 10
    assert result["registration"]["checkpoint_maximum_m_at_1m_gsd"] < 5
