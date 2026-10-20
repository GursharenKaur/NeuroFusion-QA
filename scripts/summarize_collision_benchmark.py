
from __future__ import annotations
import math
from collections import Counter, defaultdict
import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median, quantiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from neurofusion_qa.benchmark import BENCHMARK_OUTPUT_NAMES  # noqa: E402


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def inspect_job(job_dir: Path) -> dict:
    marker = load_json(job_dir / "completed.json")
    metrics = load_json(job_dir / "metrics.json")
    truth = load_json(job_dir / "truth.json")
    baseline_evaluation = load_json(job_dir / "baseline_evaluation.json")

    hashes = marker.get("output_hashes", {})
    hash_errors = []

    if not isinstance(hashes, dict):
        hashes = {}
        hash_errors.append("output_hashes is not an object")

    if set(hashes) != set(BENCHMARK_OUTPUT_NAMES):
        hash_errors.append("required artifact hash set does not match")

    for filename in BENCHMARK_OUTPUT_NAMES:
        path = job_dir / filename
        expected = hashes.get(filename)

        if not path.is_file():
            hash_errors.append(f"missing artifact: {filename}")
            continue

        if not isinstance(expected, str):
            hash_errors.append(f"missing hash: {filename}")
            continue

        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            hash_errors.append(f"hash mismatch: {filename}")

    detection = metrics.get("detection", {})
    if not isinstance(detection, dict):
        detection = {}

    if marker.get("experiment_id") != job_dir.name:
        hash_errors.append("completion marker experiment_id mismatch")

    if metrics.get("experiment_id") != job_dir.name:
        hash_errors.append("metrics experiment_id mismatch")

    expected_keys = truth.get("affected_keys", [])
    if not isinstance(expected_keys, list):
        expected_keys = []

    return {
        "experiment_id": job_dir.name,
        "corruption": metrics.get("corruption", truth.get("corruption", "")),
        "people": metrics.get("people"),
        "modalities": metrics.get("modalities"),
        "sessions": metrics.get("sessions"),
        "runs_per_modality": metrics.get("runs_per_modality"),
        "severity": metrics.get("severity"),
        "affected_count": metrics.get("affected_count"),
        "seed": metrics.get("seed"),
        "expected_violation_count": len(truth.get("expected_violations", [])),
        "truth_affected_key_count": len(expected_keys),
        "detected": detection.get("detected"),
        "expected_violation_detected": detection.get(
            "expected_violation_detected"
        ),
        "failure_type_correct": detection.get("failure_type_correct"),
        "detected_expected_violation_count": detection.get(
            "detected_expected_violation_count"
        ),
        "localization_true_positives": detection.get(
            "localization_true_positives"
        ),
        "localization_false_positives": detection.get(
            "localization_false_positives"
        ),
        "runtime_seconds": metrics.get("runtime_seconds"),
        "peak_memory_bytes": metrics.get("peak_memory_bytes"),
        "artifact_hashes_valid": not hash_errors,
        "artifact_errors": "; ".join(hash_errors),
        "job_directory": str(job_dir.resolve()),
        "baseline_evaluation_status": baseline_evaluation.get("status"),
        "baseline_scored_count": baseline_evaluation.get("scored_baseline_count"),
        "clean_control": baseline_evaluation.get("clean_control", False),
        "clean_false_alarm_count": baseline_evaluation.get("clean_false_alarm_count"),
        "clean_false_alarm_denominator": baseline_evaluation.get(
            "clean_false_alarm_denominator"
        ),
    }


def safe_rate(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def exact_binomial_ci(successes: int, trials: int, confidence: float = 0.95):
    """Two-sided Clopper-Pearson exact binomial confidence interval."""
    if trials == 0:
        return None

    from scipy.stats import beta

    alpha = 1.0 - confidence
    lower = 0.0 if successes == 0 else float(
        beta.ppf(alpha / 2, successes, trials - successes + 1)
    )
    upper = 1.0 if successes == trials else float(
        beta.ppf(1 - alpha / 2, successes + 1, trials - successes)
    )
    return [lower, upper]


def runtime_summary(group: list[dict]) -> dict:
    values = sorted(
        r["runtime_seconds"]
        for r in group
        if isinstance(r["runtime_seconds"], (int, float))
        and not isinstance(r["runtime_seconds"], bool)
    )
    if not values:
        return {
            "runtime_n": 0,
            "median_runtime_seconds": None,
            "runtime_q1_seconds": None,
            "runtime_q3_seconds": None,
            "runtime_iqr_seconds": None,
        }

    # statistics.quantiles uses linear interpolation for the inclusive method.
    if len(values) == 1:
        q1 = q3 = values[0]
    else:
        q1, _, q3 = quantiles(values, n=4, method="inclusive")

    med = median(values)
    return {
        "runtime_n": len(values),
        "median_runtime_seconds": med,
        "runtime_q1_seconds": q1,
        "runtime_q3_seconds": q3,
        "runtime_iqr_seconds": q3 - q1,
    }


PAIRING_FIELDS = (
    "people",
    "modalities",
    "sessions",
    "runs_per_modality",
    "severity",
    "seed",
)

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_CONFIDENCE = 0.95
BOOTSTRAP_BASE_SEED = 20261019

SCALING_MATCH_FIELDS = (
    "corruption",
    "modalities",
    "sessions",
    "runs_per_modality",
    "severity",
    "seed",
)


def _valid_measurement(value) -> bool:
    """Accept finite, non-negative numeric measurements, excluding booleans."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _measurement_summary(rows: list[dict], field: str, prefix: str) -> dict:
    """Summarize one measurement using the inclusive quartile convention."""
    values = sorted(
        row[field]
        for row in rows
        if _valid_measurement(row.get(field))
    )

    if not values:
        return {
            f"{prefix}_n": 0,
            f"median_{prefix}": None,
            f"{prefix}_q1": None,
            f"{prefix}_q3": None,
            f"{prefix}_iqr": None,
        }

    if len(values) == 1:
        q1 = q3 = values[0]
    else:
        q1, _, q3 = quantiles(values, n=4, method="inclusive")

    return {
        f"{prefix}_n": len(values),
        f"median_{prefix}": median(values),
        f"{prefix}_q1": q1,
        f"{prefix}_q3": q3,
        f"{prefix}_iqr": q3 - q1,
    }


def runtime_scaling_summary(rows: list[dict]) -> dict:
    """
    Describe measured scaling across participant counts.

    Only artifact-valid rows are eligible. Adjacent participant-count levels
    are compared using matching corruption, modalities, sessions,
    runs_per_modality, severity, and seed.

    Ratios are larger-workload measurement / smaller-workload measurement.
    Duplicate design keys are excluded from matched comparisons.
    """
    valid_rows = [
        row for row in rows
        if row.get("artifact_hashes_valid") is True
        and isinstance(row.get("people"), int)
        and not isinstance(row.get("people"), bool)
        and row["people"] > 0
    ]

    by_people = defaultdict(list)
    for row in valid_rows:
        by_people[row["people"]].append(row)

    descriptive = []
    for people in sorted(by_people):
        group = by_people[people]
        item = {
            "people": people,
            "valid_jobs": len(group),
        }
        item.update(
            _measurement_summary(group, "runtime_seconds", "runtime_seconds")
        )
        item.update(
            _measurement_summary(group, "peak_memory_bytes", "peak_traced_python_bytes")
        )
        descriptive.append(item)

    # Index each design configuration at each participant count.
    indexed = defaultdict(list)
    for row in valid_rows:
        if not all(field in row and row[field] is not None
                   for field in SCALING_MATCH_FIELDS):
            continue

        signature = tuple(row[field] for field in SCALING_MATCH_FIELDS)
        indexed[(signature, row["people"])].append(row)

    people_levels = sorted(by_people)
    comparisons = []

    for smaller, larger in zip(people_levels, people_levels[1:]):
        runtime_ratios = []
        memory_ratios = []
        matched_configurations = 0
        duplicate_configurations_excluded = 0

        signatures = {
            signature
            for signature, people in indexed
            if people in (smaller, larger)
        }

        for signature in signatures:
            low_rows = indexed.get((signature, smaller), [])
            high_rows = indexed.get((signature, larger), [])

            if not low_rows or not high_rows:
                continue

            # A configuration must have exactly one job at each size.
            if len(low_rows) != 1 or len(high_rows) != 1:
                duplicate_configurations_excluded += 1
                continue

            low, high = low_rows[0], high_rows[0]
            matched_configurations += 1

            low_runtime = low.get("runtime_seconds")
            high_runtime = high.get("runtime_seconds")
            if (
                _valid_measurement(low_runtime)
                and _valid_measurement(high_runtime)
                and low_runtime > 0
            ):
                runtime_ratios.append(high_runtime / low_runtime)

            low_memory = low.get("peak_memory_bytes")
            high_memory = high.get("peak_memory_bytes")
            if (
                _valid_measurement(low_memory)
                and _valid_measurement(high_memory)
                and low_memory > 0
            ):
                memory_ratios.append(high_memory / low_memory)

        comparisons.append({
            "smaller_people": smaller,
            "larger_people": larger,
            "matched_configurations": matched_configurations,
            "duplicate_configurations_excluded": (
                duplicate_configurations_excluded
            ),
            "runtime_ratio_n": len(runtime_ratios),
            "median_runtime_ratio": (
                median(runtime_ratios) if runtime_ratios else None
            ),
            "peak_traced_python_memory_ratio_n": len(memory_ratios),
            "median_peak_traced_python_memory_ratio": (
                median(memory_ratios) if memory_ratios else None
            ),
            "ratio_definition": (
                "measurement at larger_people divided by measurement "
                "at smaller_people"
            ),
            "status": (
                "calculated"
                if runtime_ratios or memory_ratios
                else "insufficient_valid_matched_measurements"
            ),
        })

    return {
        "method": (
            "Descriptive measurements by participant count and matched "
            "ratios between adjacent observed participant-count levels"
        ),
        "eligible_jobs": len(valid_rows),
        "participant_count_levels": people_levels,
        "by_people_count": descriptive,
        "adjacent_size_comparisons": comparisons,
        "matching_fields": list(SCALING_MATCH_FIELDS),
        "memory_measurement": (
            "peak traced Python allocations reported by tracemalloc; "
            "not total process RSS or system memory"
        ),
        "limitations": (
            "Empirical descriptive scaling only; no computational "
            "complexity model is fitted. Missing or invalid measurements, "
            "zero denominators, unmatched configurations, and ambiguous "
            "duplicate configurations are not used to calculate ratios."
        ),
    }

def _percentile(sorted_values: list[float], probability: float) -> float:
    """Linear-interpolated percentile of an already sorted sequence."""
    if not sorted_values:
        raise ValueError("Cannot calculate a percentile from empty data.")

    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower

    return (
        sorted_values[lower] * (1.0 - fraction)
        + sorted_values[upper] * fraction
    )


def paired_bootstrap_comparisons(
    rows: list[dict],
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    base_seed: int = BOOTSTRAP_BASE_SEED,
) -> dict:
    """
    Compare corruption types using matched synthetic benchmark conditions.

    Pairing unit: a matched design block identified by
    people count, modalities, sessions, runs_per_modality, severity, and seed.
    The same affected subjects or records are not necessarily paired.
    Difference is corruption_a's rate minus corruption_b's rate.
    Confidence intervals are percentile bootstrap intervals over matched
    blocks, with replacement.
    """
    import random
    from itertools import combinations

    if n_resamples < 1:
        raise ValueError("n_resamples must be at least 1.")

    valid_rows = [
        row for row in rows
        if row.get("artifact_hashes_valid") is True
    ]

    corruption_names = sorted({
        row.get("corruption")
        for row in valid_rows
        if isinstance(row.get("corruption"), str)
        and row["corruption"]
    })

    metrics = {
        "expected_violation_detected": "expected_violation_detection_rate",
        "failure_type_correct": "failure_type_accuracy",
    }

    comparisons = []

    for comparison_index, (corruption_a, corruption_b) in enumerate(
        combinations(corruption_names, 2)
    ):
        # Build a list per key so duplicate records cannot silently
        # become arbitrary matches.
        indexed = {}
        for corruption in (corruption_a, corruption_b):
            indexed[corruption] = {}

            for row in valid_rows:
                if row.get("corruption") != corruption:
                    continue

                values = tuple(row.get(field) for field in PAIRING_FIELDS)

                # Missing design fields cannot establish a valid pair.
                if any(value is None for value in values):
                    continue

                indexed[corruption].setdefault(values, []).append(row)

        keys_a = indexed[corruption_a]
        keys_b = indexed[corruption_b]

        duplicate_keys = {
            key
            for key in set(keys_a) | set(keys_b)
            if len(keys_a.get(key, [])) > 1
            or len(keys_b.get(key, [])) > 1
        }

        matched_keys = sorted(
            (
                set(keys_a) & set(keys_b)
            ) - duplicate_keys,
            key=repr,
        )

        for metric_index, (metric_field, metric_name) in enumerate(
            metrics.items()
        ):
            differences = []

            for key in matched_keys:
                value_a = keys_a[key][0].get(metric_field)
                value_b = keys_b[key][0].get(metric_field)

                # Do not coerce missing or non-boolean outcomes.
                if type(value_a) is not bool or type(value_b) is not bool:
                    continue

                differences.append(
                    float(value_a) - float(value_b)
                )

            pair_count = len(differences)
            estimate = (
                sum(differences) / pair_count
                if pair_count
                else None
            )

            interval = None
            status = "insufficient_pairs"

            # A single pair can give a point estimate, but not a useful
            # empirical bootstrap interval.
            if pair_count >= 2:
                rng = random.Random(
                    base_seed + comparison_index * len(metrics)
                    + metric_index
                )
                bootstrap_estimates = []

                for _ in range(n_resamples):
                    sample_sum = sum(
                        differences[rng.randrange(pair_count)]
                        for _ in range(pair_count)
                    )
                    bootstrap_estimates.append(sample_sum / pair_count)

                bootstrap_estimates.sort()
                alpha = 1.0 - BOOTSTRAP_CONFIDENCE

                interval = [
                    _percentile(bootstrap_estimates, alpha / 2),
                    _percentile(bootstrap_estimates, 1 - alpha / 2),
                ]
                status = "calculated"

            comparisons.append({
                "corruption_a": corruption_a,
                "corruption_b": corruption_b,
                "metric": metric_name,
                "difference_definition": (
                    f"{corruption_a} rate minus {corruption_b} rate"
                ),
                "matched_design_blocks": pair_count,
                "duplicate_design_keys_excluded": len(duplicate_keys),
                "mean_paired_difference": estimate,
                "confidence_level": BOOTSTRAP_CONFIDENCE,
                "confidence_interval": interval,
                "status": status,
                "resamples": n_resamples if pair_count >= 2 else 0,
                "random_seed": (
                    base_seed + comparison_index * len(metrics)
                    + metric_index
                    if pair_count >= 2 else None
                ),
            })

    return {
        "method": "paired percentile bootstrap",
        "pairing_unit": (
            "matched design block: same people count, modalities, sessions, "
            "runs_per_modality, severity, and seed across corruption types; "
            "the same affected subjects or records are not guaranteed"
        ),
        "pairing_fields": list(PAIRING_FIELDS),
        "confidence_level": BOOTSTRAP_CONFIDENCE,
        "resamples": n_resamples,
        "base_random_seed": base_seed,
        "interval_method": "two-sided percentile interval with linear interpolation",
        "difference_scale": "absolute rate difference, from -1 to 1",
        "missing_or_duplicate_pairs": (
            "Missing design fields, missing/non-boolean outcomes, unmatched "
            "keys, and ambiguous duplicate keys are not used as pairs."
        ),
        "comparisons": comparisons,
    }

def summarize_group(group: list[dict]) -> dict:
    jobs = len(group)
    detected = sum(r["expected_violation_detected"] is True for r in group)
    correctly_typed = sum(r["failure_type_correct"] is True for r in group)
    tp = sum(r["localization_true_positives"] or 0 for r in group)
    fp = sum(r["localization_false_positives"] or 0 for r in group)
    affected = sum(r["truth_affected_key_count"] for r in group)

    result = {
        "valid_jobs": jobs,
        "expected_violation_detection_successes": detected,
        "expected_violation_detection_trials": jobs,
        "expected_violation_detection_rate": safe_rate(detected, jobs),
        "expected_violation_detection_ci95": exact_binomial_ci(detected, jobs),
        "failure_type_correct_jobs": correctly_typed,
        "failure_type_accuracy_trials": jobs,
        "failure_type_accuracy": safe_rate(correctly_typed, jobs),
        "failure_type_accuracy_ci95": exact_binomial_ci(correctly_typed, jobs),
        "localization_true_positives": tp,
        "localization_false_positives": fp,
        "affected_key_denominator": affected,
        "affected_key_recall": safe_rate(tp, affected),
        "localization_precision_denominator": tp + fp,
        "localization_precision": safe_rate(tp, tp + fp),
    }
    result.update(runtime_summary(group))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize and validate IdentityGuard-BIDS benchmark jobs."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=ROOT / "outputs" / "collision_benchmark",
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else input_root

    if not input_root.is_dir():
        parser.error(f"Input directory does not exist: {input_root}")

    job_dirs = sorted(
        p for p in input_root.iterdir()
        if p.is_dir() and (p / "completed.json").is_file()
    )

    rows = []
    invalid_jobs = []

    for job_dir in job_dirs:
        try:
            row = inspect_job(job_dir)
            rows.append(row)
            if not row["artifact_hashes_valid"]:
                invalid_jobs.append({
                    "experiment_id": row["experiment_id"],
                    "errors": row["artifact_errors"],
                })
        except Exception as exc:
            invalid_jobs.append({
                "experiment_id": job_dir.name,
                "errors": f"{type(exc).__name__}: {exc}",
            })

    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "benchmark_summary.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8")

    groups = defaultdict(list)
    clean_controls = []

    for row in rows:
        if not row["artifact_hashes_valid"]:
            continue

        if row["corruption"] == "C0_clean":
            clean_controls.append(row)
        else:
            groups[row["corruption"]].append(row)

    clean_false_alarm_count = sum(
        row["clean_false_alarm_count"]
        for row in clean_controls
        if isinstance(row.get("clean_false_alarm_count"), int)
        and not isinstance(row.get("clean_false_alarm_count"), bool)
        and row["clean_false_alarm_count"] >= 0
    )

    clean_false_alarm_denominator = sum(
        row["clean_false_alarm_denominator"]
        for row in clean_controls
        if isinstance(row.get("clean_false_alarm_denominator"), int)
        and not isinstance(row.get("clean_false_alarm_denominator"), bool)
        and row["clean_false_alarm_denominator"] >= 0
    )

    paired_bootstrap = paired_bootstrap_comparisons(rows)
    runtime_scaling = runtime_scaling_summary(rows)

    summary = {
        "input_root": str(input_root),
        "completed_directories_found": len(job_dirs),
        "jobs_summarized": len(rows),
        "valid_jobs": sum(r["artifact_hashes_valid"] for r in rows),
        "invalid_jobs": len(invalid_jobs),
        "aggregate_by_corruption": {
            corruption: summarize_group(group)
            for corruption, group in sorted(groups.items())
        },
        "invalid_job_details": invalid_jobs,
        "clean_control_summary": {
            "valid_clean_control_jobs": len(clean_controls),
            "scored_false_alarm_count": clean_false_alarm_count,
            "scored_prediction_denominator": clean_false_alarm_denominator,
            "scored_false_alarm_rate": safe_rate(
                clean_false_alarm_count,
                clean_false_alarm_denominator,
            ),
            "scope": (
                "Baseline-specific scored predictions on C0_clean only; "
                "not a protocol-wide false-alarm rate."
            ),
        },
        "paired_bootstrap": paired_bootstrap,
        "runtime_scaling": runtime_scaling,
        "statistical_methods": {
            "binomial_confidence_interval": (
                "two-sided Clopper-Pearson exact, 95%"
            ),
            "runtime_quantiles": (
                "inclusive linear interpolation; median and IQR"
            ),
            "paired_bootstrap": (
                "10,000 paired percentile bootstrap resamples; "
                "matched design conditions and seed; fixed random seed; "
                "absolute difference in rates"
            ),
            "runtime_scaling": (
                "Descriptive median and inclusive IQR by participant count; "
                "adjacent observed sizes compared by matched configuration "
                "ratios. Memory refers to peak traced Python allocations, "
                "not process RSS."
            ),
        },
        "note": (
            "Aggregates include only jobs whose required artifacts passed "
            "hash validation. Job-level proportions use valid jobs as their "
            "denominator. Localization metrics use pooled key-level counts. "
            "Review invalid_job_details before interpreting results."
        ),
    }

    json_path = output_dir / "benchmark_summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Completed directories found: {len(job_dirs)}")
    print(f"Jobs summarized:             {len(rows)}")
    print(f"Valid jobs:                  {summary['valid_jobs']}")
    print(f"Invalid jobs:                {len(invalid_jobs)}")
    print(f"CSV:                         {csv_path}")
    print(f"JSON:                        {json_path}")

    for corruption, values in sorted(summary["aggregate_by_corruption"].items()):
        print(
            f"{corruption}: jobs={values['valid_jobs']}, "
            f"detection={values['expected_violation_detection_successes']}/"
            f"{values['expected_violation_detection_trials']}, "
            f"type_accuracy={values['failure_type_correct_jobs']}/"
            f"{values['failure_type_accuracy_trials']}, "
            f"localization_precision="
            f"{values['localization_true_positives']}/"
            f"{values['localization_precision_denominator']}"
        )

    return 1 if invalid_jobs else 0


if __name__ == "__main__":
    raise SystemExit(main())
