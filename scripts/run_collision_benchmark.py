from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from neurofusion_qa.benchmark import (  # noqa: E402
    generate_benchmark_jobs,
    run_benchmark_job,
)

CORRUPTIONS = (
    "C1_namespace_stripping",
    "C2_canonicalization_collision",
    "C3_duplicate_propagation",
    "C4_cross_modal_permutation",
    "C5_subject_split_leakage",
    "C6_denominator_mismatch",
)


def protocol_is_approved(config_path: Path) -> bool:
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml
        config = yaml.safe_load(text)
    except Exception as exc:
        raise RuntimeError(f"Cannot parse protocol YAML: {exc}") from exc

    protocol = config.get("protocol", {}) if isinstance(config, dict) else {}
    status = protocol.get("status")
    approver = protocol.get("approved_by")
    approved_date = protocol.get("approved_date")

    return (
        status == "approved"
        and isinstance(approver, str)
        and approver.strip()
        and approver.strip() not in {"[PI]", "[STUDENT]"}
        and approved_date is not None
        and str(approved_date).strip().lower() not in {"", "null", "none"}
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the IdentityGuard-BIDS synthetic benchmark."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "identityguard_protocol.yaml",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs" / "collision_benchmark",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--full-grid", action="store_true")
    parser.add_argument(
        "--start-index", type=int, default=0,
        help="Zero-based starting position in the deterministic job list.",
    )
    parser.add_argument(
        "--limit", type=int,
        help="Maximum jobs to run; intended for controlled smoke runs.",
    )
    parser.add_argument(
        "--no-resume", action="store_true",
        help="Do not reuse validated completed jobs.",
    )
    args = parser.parse_args()

    selected_modes = sum(
        (args.smoke, args.full_grid)
    )

    if selected_modes > 1:
        parser.error("--smoke and --full-grid cannot be combined.")

    if not (args.dry_run or args.smoke or args.full_grid):
        parser.error("Choose --dry-run, --smoke, or --full-grid.")

    if args.dry_run and args.full_grid:
        parser.error("--dry-run and --full-grid cannot be combined.")

    config_path = args.config.resolve()
    output_root = args.output_root.resolve()

    if not config_path.is_file():
        parser.error(f"Config file does not exist: {config_path}")
    if args.start_index < 0:
        parser.error("--start-index must be >= 0")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")

    if args.full_grid:
        if args.limit is not None or args.start_index != 0:
            parser.error(
                "--full-grid runs the complete design; do not combine it "
                "with --limit or --start-index."
            )
        if not protocol_is_approved(config_path):
            parser.error(
                "Full grid blocked: protocol must have status 'approved', "
                "a named approver, and an approval date. Do not bypass this "
                "gate before PI/G1 approval."
            )

    all_jobs = generate_benchmark_jobs()

    if args.smoke:
        smoke_jobs = generate_benchmark_jobs(
            people=(16,),
            modalities=(2,),
            sessions=(1,),
            runs_per_modality=(1,),
            corruptions=CORRUPTIONS,
            severities=(0.01,),
            seeds=(7,),
        )
        jobs = smoke_jobs
        if args.limit is not None:
            jobs = jobs[:args.limit]
    elif args.full_grid:
        jobs = all_jobs
    else:
        jobs = all_jobs[
            args.start_index:
            args.start_index + args.limit
            if args.limit is not None
            else None
        ]

    print(f"Config:      {config_path}")
    print(f"Output root: {output_root}")
    print(f"Protocol approved: {protocol_is_approved(config_path)}")
    print(f"Total design jobs: {len(all_jobs)}")
    print(f"Selected jobs:     {len(jobs)}")

    if args.dry_run:
        print("Dry run only; no benchmark jobs executed.")
        for job in jobs[:10]:
            print(
                f"{job.experiment_id} | people={job.people} "
                f"corruption={job.corruption} severity={job.severity} "
                f"affected={job.affected_count} seed={job.seed}"
            )
        if len(jobs) > 10:
            print(f"... and {len(jobs) - 10} more")
        return 0

    if not jobs:
        print("No jobs selected.", file=sys.stderr)
        return 2

    output_root.mkdir(parents=True, exist_ok=True)
    run_started = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    results = []
    failures = []

    for index, job in enumerate(jobs, start=1):
        print(
            f"[{index}/{len(jobs)}] {job.experiment_id}",
            flush=True,
        )
        try:
            result = run_benchmark_job(
                job,
                output_root=output_root,
                config_path=config_path,
                resume=not args.no_resume,
            )
            results.append({
                "experiment_id": result.experiment_id,
                "job_directory": result.job_directory,
                "runtime_seconds": result.runtime_seconds,
                "peak_memory_bytes": result.peak_memory_bytes,
                "detection": result.detection,
                "output_hashes": result.output_hashes,
            })
        except Exception as exc:
            failures.append({
                "experiment_id": job.experiment_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            print(
                f"FAILED: {job.experiment_id}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )

    summary = {
        "run_started_utc": run_started,
        "run_finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "config_path": str(config_path),
        "output_root": str(output_root),
        "mode": "smoke" if args.smoke else "full-grid" if args.full_grid else "subset",
        "selected_jobs": len(jobs),
        "completed_jobs": len(results),
        "failed_jobs": len(failures),
        "results": results,
        "failures": failures,
    }

    summary_path = output_root / (
        f"run_summary_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"\nCompleted: {len(results)} / {len(jobs)}")
    print(f"Failed:    {len(failures)}")
    print(f"Summary:   {summary_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
