import json
from pathlib import Path

import pytest

from scripts import summarize_collision_benchmark as summarizer
from scripts.summarize_collision_benchmark import (
    exact_binomial_ci,
    inspect_job,
    paired_bootstrap_comparisons,
    runtime_scaling_summary,
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


from scripts.summarize_collision_benchmark import paired_bootstrap_comparisons


def _paired_row(corruption, seed, detected, *, valid=True):
    return {
        "corruption": corruption,
        "people": 16,
        "modalities": 2,
        "sessions": 1,
        "runs_per_modality": 1,
        "severity": 0.05,
        "seed": seed,
        "expected_violation_detected": detected,
        "failure_type_correct": detected,
        "artifact_hashes_valid": valid,
    }


def test_paired_bootstrap_is_reproducible():
    rows = [
        _paired_row("C1", 0, True),
        _paired_row("C2", 0, False),
        _paired_row("C1", 1, True),
        _paired_row("C2", 1, True),
        _paired_row("C1", 2, False),
        _paired_row("C2", 2, True),
    ]

    first = paired_bootstrap_comparisons(rows, n_resamples=200)
    second = paired_bootstrap_comparisons(rows, n_resamples=200)

    assert first == second

    comparison = next(
        item for item in first["comparisons"]
        if item["corruption_a"] == "C1"
        and item["corruption_b"] == "C2"
        and item["metric"] == "expected_violation_detection_rate"
    )

    assert comparison["matched_design_blocks"] == 3
    assert comparison["mean_paired_difference"] == pytest.approx(0.0)
    assert comparison["status"] == "calculated"
    assert len(comparison["confidence_interval"]) == 2


def test_paired_bootstrap_does_not_pair_different_seeds():
    rows = [
        _paired_row("C1", 0, True),
        _paired_row("C2", 1, False),
    ]

    result = paired_bootstrap_comparisons(rows, n_resamples=100)

    assert all(
        item["matched_design_blocks"] == 0
        and item["confidence_interval"] is None
        for item in result["comparisons"]
    )


def test_paired_bootstrap_excludes_invalid_artifacts():
    rows = [
        _paired_row("C1", 0, True),
        _paired_row("C2", 0, False, valid=False),
    ]

    result = paired_bootstrap_comparisons(rows, n_resamples=100)

    assert all(
        item["matched_design_blocks"] == 0
        for item in result["comparisons"]
    )


def test_paired_bootstrap_rejects_ambiguous_duplicate_keys():
    rows = [
        _paired_row("C1", 0, True),
        _paired_row("C1", 0, False),
        _paired_row("C2", 0, False),
    ]

    result = paired_bootstrap_comparisons(rows, n_resamples=100)

    assert all(
        item["matched_design_blocks"] == 0
        and item["duplicate_design_keys_excluded"] == 1
        for item in result["comparisons"]
    )


def test_paired_bootstrap_single_pair_has_no_interval():
    rows = [
        _paired_row("C1", 0, True),
        _paired_row("C2", 0, False),
    ]

    result = paired_bootstrap_comparisons(rows, n_resamples=100)

    assert all(
        item["matched_design_blocks"] == 1
        and item["status"] == "insufficient_pairs"
        and item["confidence_interval"] is None
        for item in result["comparisons"]
    )

def _scaling_row(people, runtime, memory, *, seed=1, valid=True):
    return {
        "people": people,
        "corruption": "I1",
        "modalities": 2,
        "sessions": 1,
        "runs_per_modality": 1,
        "severity": 0.05,
        "seed": seed,
        "runtime_seconds": runtime,
        "peak_memory_bytes": memory,
        "artifact_hashes_valid": valid,
    }


def test_runtime_scaling_summarizes_by_people_count():
    result = runtime_scaling_summary([
        _scaling_row(10, 2.0, 1000),
        _scaling_row(10, 4.0, 2000, seed=2),
    ])

    assert result["participant_count_levels"] == [10]
    group = result["by_people_count"][0]
    assert group["valid_jobs"] == 2
    assert group["runtime_seconds_n"] == 2
    assert group["median_runtime_seconds"] == 3.0
    assert group["peak_traced_python_bytes_n"] == 2
    assert group["median_peak_traced_python_bytes"] == 1500.0
    assert result["adjacent_size_comparisons"] == []


def test_runtime_scaling_calculates_matched_adjacent_size_ratios():
    result = runtime_scaling_summary([
        _scaling_row(10, 2.0, 1000),
        _scaling_row(20, 5.0, 2500),
    ])

    comparison = result["adjacent_size_comparisons"][0]
    assert comparison["matched_configurations"] == 1
    assert comparison["runtime_ratio_n"] == 1
    assert comparison["median_runtime_ratio"] == 2.5
    assert comparison["peak_traced_python_memory_ratio_n"] == 1
    assert comparison["median_peak_traced_python_memory_ratio"] == 2.5
    assert comparison["status"] == "calculated"


def test_runtime_scaling_excludes_invalid_and_zero_denominator_ratios():
    result = runtime_scaling_summary([
        _scaling_row(10, 0.0, 0),
        _scaling_row(20, 3.0, 2000),
        _scaling_row(10, 100.0, 100000, valid=False),
    ])

    comparison = result["adjacent_size_comparisons"][0]
    assert result["eligible_jobs"] == 2
    assert comparison["runtime_ratio_n"] == 0
    assert comparison["median_runtime_ratio"] is None
    assert comparison["peak_traced_python_memory_ratio_n"] == 0
    assert comparison["median_peak_traced_python_memory_ratio"] is None
    assert comparison["status"] == "insufficient_valid_matched_measurements"


def test_runtime_scaling_does_not_match_different_seeds():
    result = runtime_scaling_summary([
        _scaling_row(10, 2.0, 1000, seed=1),
        _scaling_row(20, 5.0, 2500, seed=2),
    ])

    comparison = result["adjacent_size_comparisons"][0]
    assert comparison["matched_configurations"] == 0
    assert comparison["runtime_ratio_n"] == 0
    assert comparison["median_runtime_ratio"] is None


from scripts.summarize_collision_benchmark import inspect_job


def test_inspect_job_extracts_baseline_evaluation_fields(tmp_path, monkeypatch):
    """Baseline-evaluation fields must be available in summarized rows."""
    from scripts import summarize_collision_benchmark as summarizer

    payloads = {
        "completed.json": {"output_hashes": {}},
        "metrics.json": {
            "corruption": "C0_clean",
            "detection": {},
        },
        "truth.json": {"corruption": "C0_clean"},
        "baseline_evaluation.json": {
            "status": "complete",
            "scored_baseline_count": 1,
            "clean_control": True,
            "clean_false_alarm_count": 0,
            "clean_false_alarm_denominator": 1,
        },
    }

    def fake_load_json(path):
        return payloads[Path(path).name]

    monkeypatch.setattr(summarizer, "load_json", fake_load_json)
    monkeypatch.setattr(
        summarizer,
        "REQUIRED_ARTIFACTS",
        (),
        raising=False,
    )

    result = inspect_job(tmp_path)

    assert result["baseline_evaluation_status"] == "complete"
    assert result["baseline_scored_count"] == 1
    assert result["clean_control"] is True
    assert result["clean_false_alarm_count"] == 0
    assert result["clean_false_alarm_denominator"] == 1


def test_clean_control_counts_reject_boolean_and_negative_values():
    """Counts must not silently accept booleans or negative integers."""
    rows = [
        {
            "artifact_hashes_valid": True,
            "corruption": "C0_clean",
            "clean_false_alarm_count": 0,
            "clean_false_alarm_denominator": 1,
        },
        {
            "artifact_hashes_valid": True,
            "corruption": "C0_clean",
            "clean_false_alarm_count": True,
            "clean_false_alarm_denominator": False,
        },
        {
            "artifact_hashes_valid": True,
            "corruption": "C0_clean",
            "clean_false_alarm_count": -1,
            "clean_false_alarm_denominator": -2,
        },
        {
            "artifact_hashes_valid": False,
            "corruption": "C0_clean",
            "clean_false_alarm_count": 100,
            "clean_false_alarm_denominator": 100,
        },
    ]

    count = sum(
        row["clean_false_alarm_count"]
        for row in rows
        if row["artifact_hashes_valid"]
        and isinstance(row.get("clean_false_alarm_count"), int)
        and not isinstance(row.get("clean_false_alarm_count"), bool)
        and row["clean_false_alarm_count"] >= 0
    )
    denominator = sum(
        row["clean_false_alarm_denominator"]
        for row in rows
        if row["artifact_hashes_valid"]
        and isinstance(row.get("clean_false_alarm_denominator"), int)
        and not isinstance(row.get("clean_false_alarm_denominator"), bool)
        and row["clean_false_alarm_denominator"] >= 0
    )

    assert count == 0
    assert denominator == 1


def test_main_generates_clean_control_summary_without_dropping_analyses(
    tmp_path, monkeypatch
):
    """The CLI must aggregate valid C0 controls separately from corruptions."""
    input_root = tmp_path / "jobs"
    output_dir = tmp_path / "summary"
    input_root.mkdir()

    # main() discovers directories containing completed.json.
    for job_name in ("clean_valid", "corruption_valid", "clean_invalid"):
        job_dir = input_root / job_name
        job_dir.mkdir()
        (job_dir / "completed.json").write_text("{}", encoding="utf-8")

    rows_by_name = {
        "clean_valid": {
            "experiment_id": "clean_valid",
            "corruption": "C0_clean",
            "artifact_hashes_valid": True,
            "artifact_errors": "",
            "clean_false_alarm_count": 1,
            "clean_false_alarm_denominator": 10,
        },
        "corruption_valid": {
            "experiment_id": "corruption_valid",
            "corruption": "C1_namespace_stripping",
            "artifact_hashes_valid": True,
            "artifact_errors": "",
            "clean_false_alarm_count": None,
            "clean_false_alarm_denominator": None,
        },
        "clean_invalid": {
            "experiment_id": "clean_invalid",
            "corruption": "C0_clean",
            "artifact_hashes_valid": False,
            "artifact_errors": "synthetic invalid job",
            "clean_false_alarm_count": 100,
            "clean_false_alarm_denominator": 100,
        },
    }

    monkeypatch.setattr(
        summarizer,
        "inspect_job",
        lambda job_dir: rows_by_name[job_dir.name],
    )
    monkeypatch.setattr(
        summarizer,
        "summarize_group",
        lambda group: {
            "valid_jobs": len(group),
            "expected_violation_detection_successes": 1,
            "expected_violation_detection_trials": 1,
            "failure_type_correct_jobs": 1,
            "failure_type_accuracy_trials": 1,
            "localization_true_positives": 1,
            "localization_precision_denominator": 1,
        },
    )
    monkeypatch.setattr(
        summarizer,
        "paired_bootstrap_comparisons",
        lambda rows: {"method": "paired percentile bootstrap"},
    )
    monkeypatch.setattr(
        summarizer,
        "runtime_scaling_summary",
        lambda rows: {"method": "descriptive runtime scaling"},
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "summarize_collision_benchmark.py",
            "--input-root",
            str(input_root),
            "--output-dir",
            str(output_dir),
        ],
    )

    result = summarizer.main()

    # The CLI returns 1 when any job is invalid.
    assert result == 1

    summary = json.loads(
        (output_dir / "benchmark_summary.json").read_text(encoding="utf-8")
    )

    clean = summary["clean_control_summary"]
    assert clean["valid_clean_control_jobs"] == 1
    assert clean["scored_false_alarm_count"] == 1
    assert clean["scored_prediction_denominator"] == 10
    assert clean["scored_false_alarm_rate"] == pytest.approx(0.1)

    # C0 controls are summarized separately, not as a corruption group.
    assert "C0_clean" not in summary["aggregate_by_corruption"]
    assert summary["aggregate_by_corruption"]["C1_namespace_stripping"][
        "valid_jobs"
    ] == 1

    # The invalid clean-control job is excluded from the clean totals.
    assert summary["invalid_jobs"] == 1
    assert clean["scored_false_alarm_count"] != 101
    assert clean["scored_prediction_denominator"] != 110

    # Existing statistical analyses must remain in the output.
    assert summary["paired_bootstrap"]["method"] == (
        "paired percentile bootstrap"
    )
    assert summary["runtime_scaling"]["method"] == (
        "descriptive runtime scaling"
    )
