import pytest

from scripts.summarize_collision_benchmark import (
    exact_binomial_ci,
    runtime_summary,
    safe_rate,
)


def test_safe_rate_handles_zero_denominator():
    assert safe_rate(0, 0) is None


def test_safe_rate_calculates_proportion():
    assert safe_rate(3, 4) == 0.75


def test_exact_binomial_ci_all_successes():
    lower, upper = exact_binomial_ci(1, 1)
    assert lower == pytest.approx(0.025)
    assert upper == 1.0


def test_exact_binomial_ci_no_successes():
    lower, upper = exact_binomial_ci(0, 1)
    assert lower == 0.0
    assert upper == pytest.approx(0.975)


def test_exact_binomial_ci_zero_trials():
    assert exact_binomial_ci(0, 0) is None


def test_runtime_summary_single_observation():
    result = runtime_summary([{"runtime_seconds": 2.5}])
    assert result["runtime_n"] == 1
    assert result["median_runtime_seconds"] == 2.5
    assert result["runtime_iqr_seconds"] == 0.0


def test_runtime_summary_even_number_uses_true_median():
    result = runtime_summary([
        {"runtime_seconds": 1.0},
        {"runtime_seconds": 3.0},
    ])
    assert result["median_runtime_seconds"] == 2.0
    assert result["runtime_q1_seconds"] == 1.5
    assert result["runtime_q3_seconds"] == 2.5
    assert result["runtime_iqr_seconds"] == 1.0


def test_runtime_summary_ignores_missing_runtime():
    result = runtime_summary([
        {"runtime_seconds": 1.0},
        {"runtime_seconds": None},
        {"runtime_seconds": 3.0},
    ])
    assert result["runtime_n"] == 2
    assert result["median_runtime_seconds"] == 2.0
