from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from summarize_collision_benchmark import inspect_job  # noqa: E402

ORIGINAL_ROOTS = [
    ROOT / "outputs" / "stratified_core_20261021",
    ROOT / "outputs" / "stratified_core_seeds17_67_20261021",
    ROOT / "outputs" / "stratified_core_seeds27_77_20261021",
]

CORRECTED_C3_ROOTS = [
    ROOT / "outputs" / "c3_corrected_20261021_run1",
    ROOT / "outputs" / "c3_corrected_20261021_run2",
    ROOT / "outputs" / "c3_corrected_20261021_run3",
]

OUTPUT_ROOT = ROOT / "outputs" / "canonical_benchmark_20261021"
MANIFEST_PATH = OUTPUT_ROOT / "provenance_manifest.csv"
README_PATH = OUTPUT_ROOT / "CANONICAL_DATASET_PROVENANCE.json"

EXPECTED_PER_CORRUPTION = 100
EXPECTED_TOTAL = 600


def load_job_dirs(roots: list[Path]) -> list[Path]:
    found = []
    for root in roots:
        if not root.is_dir():
            raise FileNotFoundError(f"Input root not found: {root}")
        found.extend(
            path for path in sorted(root.iterdir())
            if path.is_dir() and (path / "completed.json").is_file()
        )
    return found


def read_marker(job_dir: Path) -> dict:
    with (job_dir / "completed.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_job(job_dir: Path) -> dict:
    row = inspect_job(job_dir)
    if not row.get("artifact_hashes_valid"):
        raise ValueError(
            f"Invalid artifacts in {job_dir}: {row.get('artifact_errors')}"
        )
    return row


def create_junction(destination: Path, source: Path) -> None:
    # Windows directory junction: no job files are copied.
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(destination), str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not destination.is_dir():
        raise RuntimeError(
            f"Could not create junction:\n"
            f"Destination: {destination}\nSource: {source}\n"
            f"{result.stdout}\n{result.stderr}"
        )


def main() -> int:
    # Refuse to overwrite an earlier dataset or partial build.
    if OUTPUT_ROOT.exists():
        raise FileExistsError(
            f"{OUTPUT_ROOT} already exists. Inspect it first; "
            "this script will not overwrite or mix datasets."
        )

    original_dirs = load_job_dirs(ORIGINAL_ROOTS)
    corrected_dirs = load_job_dirs(CORRECTED_C3_ROOTS)

    original_by_id: dict[str, list[Path]] = {}
    for path in original_dirs:
        marker = read_marker(path)
        experiment_id = marker.get("experiment_id")
        if not experiment_id:
            raise ValueError(f"Missing experiment_id in {path}")
        original_by_id.setdefault(experiment_id, []).append(path)

    corrected_c3_by_id: dict[str, list[Path]] = {}
    for path in corrected_dirs:
        marker = read_marker(path)
        experiment_id = marker.get("experiment_id")
        corruption = marker.get("job", {}).get("corruption")
        if not experiment_id or corruption != "C3_duplicate_propagation":
            raise ValueError(
                f"Unexpected job in corrected C3 roots: {path}"
            )
        corrected_c3_by_id.setdefault(experiment_id, []).append(path)

    # The original roots must contain 600 distinct experiment IDs.
    if len(original_by_id) != 600:
        raise ValueError(
            f"Expected 600 unique original IDs, found {len(original_by_id)}"
        )

    # Corrected C3 must cover exactly the original C3 experiment-ID set.
    original_c3_ids = {
        experiment_id
        for experiment_id, paths in original_by_id.items()
        if read_marker(paths[0]).get("job", {}).get("corruption")
        == "C3_duplicate_propagation"
    }
    corrected_c3_ids = set(corrected_c3_by_id)

    if len(corrected_dirs) != 120 or len(corrected_c3_ids) != 100:
        raise ValueError(
            "Corrected C3 expectations failed: "
            f"{len(corrected_dirs)} directories, "
            f"{len(corrected_c3_ids)} unique IDs"
        )
    if corrected_c3_ids != original_c3_ids:
        raise ValueError(
            "Corrected C3 IDs do not exactly match original C3 IDs. "
            f"Missing corrected IDs: {sorted(original_c3_ids - corrected_c3_ids)[:5]}; "
            f"unexpected corrected IDs: {sorted(corrected_c3_ids - original_c3_ids)[:5]}"
        )

    selected: dict[str, tuple[Path, str]] = {}

    for experiment_id, paths in original_by_id.items():
        marker = read_marker(paths[0])
        corruption = marker.get("job", {}).get("corruption")

        if corruption == "C3_duplicate_propagation":
            # Prefer corrected outputs, with deterministic root order.
            candidates = corrected_c3_by_id[experiment_id]
            source = candidates[0]
            source_kind = "corrected_C3"
        else:
            # ORIGINAL_ROOTS were loaded in deterministic priority order.
            source = paths[0]
            source_kind = "original"

        selected[experiment_id] = (source, source_kind)

    if len(selected) != EXPECTED_TOTAL:
        raise ValueError(f"Expected {EXPECTED_TOTAL} jobs, got {len(selected)}")

    # Validate every chosen job before creating the canonical output.
    validated = []
    for experiment_id, (source, source_kind) in sorted(selected.items()):
        row = validate_job(source)
        marker = read_marker(source)
        job = marker.get("job", {})
        validated.append({
            "experiment_id": experiment_id,
            "corruption": job.get("corruption"),
            "seed": job.get("seed"),
            "people": job.get("people"),
            "severity": job.get("severity"),
            "source_kind": source_kind,
            "source_directory": str(source.resolve()),
            "config_sha256": marker.get("config_sha256"),
            "git_commit_file_sha256": marker.get("output_hashes", {}).get(
                "git_commit.txt", ""
            ),
            "completed_json_sha256": sha256_file(source / "completed.json"),
            "artifact_hashes_valid": row.get("artifact_hashes_valid"),
        })

    counts = Counter(row["corruption"] for row in validated)
    expected_corruptions = {
        "C1_namespace_stripping",
        "C2_canonicalization_collision",
        "C3_duplicate_propagation",
        "C4_cross_modal_permutation",
        "C5_subject_split_leakage",
        "C6_denominator_mismatch",
    }
    if set(counts) != expected_corruptions:
        raise ValueError(f"Unexpected corruption types: {dict(counts)}")
    if any(counts[name] != EXPECTED_PER_CORRUPTION for name in expected_corruptions):
        raise ValueError(f"Expected 100 jobs per corruption: {dict(counts)}")
    if not all(row["artifact_hashes_valid"] for row in validated):
        raise ValueError("At least one selected job failed artifact validation.")

    # Only now create the new dataset.
    OUTPUT_ROOT.mkdir(parents=True)
    try:
        for row in validated:
            destination = OUTPUT_ROOT / row["experiment_id"]
            source = Path(row["source_directory"])
            create_junction(destination, source)

        with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(validated[0]))
            writer.writeheader()
            writer.writerows(validated)

        provenance = {
            "dataset": "IdentityGuard-BIDS canonical stratified-core benchmark",
            "created_by": "scripts/build_canonical_benchmark.py",
            "selection_rule": (
                "One job per experiment_id; original jobs retained for C1/C2/C4/C5/C6; "
                "corrected C3 jobs replace all original C3 jobs."
            ),
            "unique_job_count": len(validated),
            "execution_history": {
                "original_directories": len(original_dirs),
                "original_unique_experiment_ids": len(original_by_id),
                "corrected_c3_directories": len(corrected_dirs),
                "corrected_c3_unique_experiment_ids": len(corrected_c3_by_id),
            },
            "jobs_per_corruption": dict(sorted(counts.items())),
            "config_sha256_values": sorted({
                row["config_sha256"] for row in validated
            }),
            "storage_note": (
                "Source job directories are exposed through Windows junctions; "
                "original directories are not modified. Storage mode can differ "
                "between original and corrected C3 executions."
            ),
            "provenance_manifest": MANIFEST_PATH.name,
        }
        README_PATH.write_text(
            json.dumps(provenance, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        # Leave the partial build visible for inspection; do not silently
        # remove potentially useful junctions or provenance files.
        raise

    print(f"Canonical root: {OUTPUT_ROOT}")
    print(f"Selected unique jobs: {len(validated)}")
    print(f"Jobs per corruption: {dict(sorted(counts.items()))}")
    print(f"All selected artifact hashes valid: True")
    print(f"Provenance manifest: {MANIFEST_PATH}")
    print(f"Dataset metadata: {README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
