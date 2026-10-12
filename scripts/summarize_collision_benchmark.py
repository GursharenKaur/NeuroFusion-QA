
from __future__ import annotations

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
    for row in rows:
        if row["artifact_hashes_valid"]:
            groups[row["corruption"]].append(row)

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
        "statistical_methods": {
            "binomial_confidence_interval": "two-sided Clopper-Pearson exact, 95%",
            "runtime_quantiles": "inclusive linear interpolation; median and IQR",
            "paired_bootstrap": "not calculated; comparison unit not yet specified",
            "runtime_scaling": "not calculated; scaling model and aggregation unit not yet specified",
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
