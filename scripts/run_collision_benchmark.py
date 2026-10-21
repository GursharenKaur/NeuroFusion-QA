from __future__ import annotations

import argparse
import hashlib
import json
import os
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


def write_checkpoint_atomic(
    output_root: Path,
    checkpoint: dict,
) -> Path:
    """Atomically persist benchmark progress."""
    checkpoint_path = output_root / "run_checkpoint.json"
    temporary_path = output_root / ".run_checkpoint.json.tmp"

    payload = json.dumps(
        checkpoint,
        indent=2,
        sort_keys=True,
    ) + "\n"

    try:
        with temporary_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temporary_path, checkpoint_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return checkpoint_path


def validate_checkpoint_identity(
    checkpoint: dict,
    config_sha256: str,
    selected_experiment_ids: list[str],
) -> None:
    """Reject checkpoints belonging to another configuration or job selection."""
    if checkpoint.get("schema_version") != 1:
        raise RuntimeError("Unsupported benchmark checkpoint schema.")

    if checkpoint.get("config_sha256") != config_sha256:
        raise RuntimeError(
            "Checkpoint configuration hash differs from the current config."
        )

    if checkpoint.get("selected_experiment_ids") != selected_experiment_ids:
        raise RuntimeError(
            "Checkpoint job selection differs from the current selection."
        )


def _validate_checkpoint_progress(
    checkpoint: dict,
    selected_experiment_ids: list[str],
) -> None:
    """Validate progress records before allowing a checkpoint to be resumed."""
    completed = checkpoint.get("completed_results")
    failures = checkpoint.get("failures")
    if not isinstance(completed, list) or not isinstance(failures, list):
        raise RuntimeError(
            "Checkpoint progress must contain completed_results and failures lists."
        )

    selected = set(selected_experiment_ids)
    completed_ids: list[str] = []
    failure_ids: list[str] = []

    for item in completed:
        if not isinstance(item, dict):
            raise RuntimeError("Checkpoint completed result must be a JSON object.")
        experiment_id = item.get("experiment_id")
        if not isinstance(experiment_id, str) or experiment_id not in selected:
            raise RuntimeError(
                "Checkpoint contains a completed result outside the selected job list."
            )
        if not isinstance(item.get("output_hashes"), dict):
            raise RuntimeError(
                f"Checkpoint result for {experiment_id} has no output hash mapping."
            )
        completed_ids.append(experiment_id)

    for item in failures:
        if not isinstance(item, dict):
            raise RuntimeError("Checkpoint failure record must be a JSON object.")
        experiment_id = item.get("experiment_id")
        if not isinstance(experiment_id, str) or experiment_id not in selected:
            raise RuntimeError(
                "Checkpoint contains a failure outside the selected job list."
            )
        failure_ids.append(experiment_id)

    if len(completed_ids) != len(set(completed_ids)):
        raise RuntimeError("Checkpoint contains duplicate completed job records.")
    if len(failure_ids) != len(set(failure_ids)):
        raise RuntimeError("Checkpoint contains duplicate failure records.")
    if set(completed_ids) & set(failure_ids):
        raise RuntimeError("Checkpoint marks the same job both completed and failed.")


def initialize_checkpoint(
    output_root: Path,
    config_sha256: str,
    selected_experiment_ids: list[str],
    mode: str,
) -> dict:
    """Create a checkpoint or safely load matching progress for recovery."""
    checkpoint_path = output_root / "run_checkpoint.json"

    if checkpoint_path.exists():
        try:
            checkpoint = json.loads(
                checkpoint_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Cannot read existing checkpoint {checkpoint_path}: {exc}"
            ) from exc

        if not isinstance(checkpoint, dict):
            raise RuntimeError("Existing benchmark checkpoint must be a JSON object.")

        validate_checkpoint_identity(
            checkpoint,
            config_sha256,
            selected_experiment_ids,
        )
        if checkpoint.get("mode") != mode:
            raise RuntimeError("Checkpoint run mode differs from the current mode.")
        _validate_checkpoint_progress(checkpoint, selected_experiment_ids)
        return checkpoint

    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "run_id": now,
        "run_started_utc": now,
        "updated_utc": now,
        "mode": mode,
        "config_sha256": config_sha256,
        "selected_experiment_ids": selected_experiment_ids,
        "completed_results": [],
        "failures": [],
    }

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
        "--stratified-core",
        action="store_true",
        help="Run a deterministic core subset across sizes, corruptions, severities, and seeds.",
    )
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
    parser.add_argument(
        "--compress-manifests",
        action="store_true",
        help="Use Windows NTFS compression for generated manifests.",
    )
    args = parser.parse_args()

    selected_modes = sum(
        (args.smoke, args.full_grid)
    )

    if selected_modes > 1:
        parser.error("--smoke and --full-grid cannot be combined.")

    if not (
        args.dry_run
        or args.smoke
        or args.full_grid
        or args.stratified_core
        or args.start_index > 0
        or args.limit is not None
    ):
        parser.error(
            "Choose --dry-run, --smoke, --full-grid, "
            "--stratified-core, or specify a bounded subset "
            "with --start-index or --limit."
        )

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
            corruptions=("C0_clean", *CORRUPTIONS),
            severities=(0.01,),
            seeds=(7,),
        )
        jobs = smoke_jobs
        if args.limit is not None:
            jobs = jobs[:args.limit]
    elif args.stratified_core:
        jobs = [
            job for job in all_jobs
            if job.modalities == 2
            and job.sessions == 1
            and job.runs_per_modality == 1
            and job.seed in (17, 67)
        ]
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

    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()
    selected_experiment_ids = [job.experiment_id for job in jobs]
    base_mode = (
        "smoke" if args.smoke
        else "stratified-core" if args.stratified_core
        else "full-grid" if args.full_grid
        else "subset"
    )
    mode = (
        f"{base_mode}|manifest_storage="
        f"{'ntfs_compressed' if args.compress_manifests else 'uncompressed'}"
    )

    try:
        checkpoint = initialize_checkpoint(
            output_root,
            config_sha256,
            selected_experiment_ids,
            mode,
        )
    except RuntimeError as exc:
        print(f"Checkpoint error: {exc}", file=sys.stderr)
        return 2

    run_started = checkpoint["run_started_utc"]
    started = time.perf_counter()
    results = checkpoint["completed_results"]
    failures = checkpoint["failures"]


    def persist_progress() -> None:
        checkpoint["updated_utc"] = datetime.now(timezone.utc).isoformat()
        checkpoint["completed_results"] = results
        checkpoint["failures"] = failures
        write_checkpoint_atomic(output_root, checkpoint)


    # Persist initial state before starting the first job.
    try:
        persist_progress()
    except OSError as exc:
        print(
            f"Checkpoint persistence failed before job execution: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    for index, job in enumerate(jobs, start=1):
        print(
            f"[{index}/{len(jobs)}] {job.experiment_id}",
            flush=True,
        )
        # Retry prior failures. run_benchmark_job validates any existing per-job
        # completion marker and all artifact hashes before reusing its outputs.
        failures[:] = [
            item for item in failures
            if item.get("experiment_id") != job.experiment_id
        ]
        try:
            result = run_benchmark_job(
                job,
                output_root=output_root,
                config_path=config_path,
                resume=not args.no_resume,
                compress_manifest=args.compress_manifests,
            )
            result_record = {
                "experiment_id": result.experiment_id,
                "job_directory": result.job_directory,
                "runtime_seconds": result.runtime_seconds,
                "peak_memory_bytes": result.peak_memory_bytes,
                "detection": result.detection,
                "output_hashes": result.output_hashes,
            }
            # Replace rather than append so interrupted/retried runs cannot
            # duplicate completed-result entries in the checkpoint or summary.
            results[:] = [
                item for item in results
                if item.get("experiment_id") != result.experiment_id
            ]
            results.append(result_record)
        except Exception as exc:
            results[:] = [
                item for item in results
                if item.get("experiment_id") != job.experiment_id
            ]
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
        finally:
            try:
                persist_progress()
            except OSError as exc:
                print(
                    "Checkpoint persistence failed after processing "
                    f"{job.experiment_id}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                return 2

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
