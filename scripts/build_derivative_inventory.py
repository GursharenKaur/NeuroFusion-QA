
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


SCHEMA_VERSION = "1.0"
TOOL_VERSION = "0.1.0"

COLUMNS = [
    "dataset_namespace",
    "dataset_version",
    "record_type",
    "participant_id",
    "session_id",
    "modality",
    "task",
    "derivative_path",
    "size_bytes",
    "derivative_sha256",
    "git_blob_match",
    "lineage_status",
    "processed_data_status",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_verification_report(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        required = {
            "Path",
            "ExpectedBytes",
            "ActualBytes",
            "GitBlobMatch",
            "SHA256",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "Verification report is missing columns: "
                + ", ".join(sorted(missing))
            )

        report = {}
        for row in reader:
            relative_path = PurePosixPath(row["Path"]).as_posix()

            if relative_path in report:
                raise ValueError(
                    f"Duplicate path in verification report: {relative_path}"
                )

            report[relative_path] = row

    return report


def build_inventory(
    dataset_root: Path,
    namespace: str,
    version: str,
    verification_report: Path,
) -> list[dict[str, str | int]]:
    derivative_root = dataset_root / "derivatives" / "meg_derivatives"

    if not dataset_root.is_dir():
        raise ValueError(f"Dataset root is not a directory: {dataset_root}")

    if not derivative_root.is_dir():
        raise ValueError(
            f"Derivative directory is missing: {derivative_root}"
        )

    report = load_verification_report(verification_report)

    files = sorted(
        (path for path in derivative_root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(dataset_root).as_posix(),
    )

    records = []

    for path in files:
        relative_path = path.relative_to(dataset_root).as_posix()

        if path.suffix.lower() != ".json":
            raise ValueError(
                f"Unexpected non-JSON file in this sidecar inventory: "
                f"{relative_path}"
            )

        evidence = report.get(relative_path)
        if evidence is None:
            raise ValueError(
                f"File is absent from the verification report: {relative_path}"
            )

        actual_size = path.stat().st_size
        actual_sha256 = sha256_file(path)

        if actual_size != int(evidence["ExpectedBytes"]):
            raise ValueError(f"Expected-size mismatch: {relative_path}")

        if actual_size != int(evidence["ActualBytes"]):
            raise ValueError(f"Reported-size mismatch: {relative_path}")

        if evidence["GitBlobMatch"].strip().lower() != "true":
            raise ValueError(f"Git blob verification failed: {relative_path}")

        if actual_sha256.lower() != evidence["SHA256"].strip().lower():
            raise ValueError(f"SHA-256 verification failed: {relative_path}")

        relative = PurePosixPath(relative_path)
        entities = relative.name.split("_")

        participant = relative.parts[2]
        if not participant.startswith("sub-"):
            raise ValueError(f"Unexpected participant path: {relative_path}")

        session = next(
            (part for part in relative.parts if part.startswith("ses-")),
            "",
        )

        task = next(
            (
                entity.removeprefix("task-")
                for entity in entities
                if entity.startswith("task-")
            ),
            "",
        )

        records.append(
            {
                "dataset_namespace": namespace,
                "dataset_version": version,
                "record_type": "metadata_sidecar",
                "participant_id": participant,
                "session_id": session,
                "modality": "meg",
                "task": task,
                "derivative_path": relative_path,
                "size_bytes": actual_size,
                "derivative_sha256": actual_sha256,
                "git_blob_match": "true",
                "lineage_status": "not_verified",
                "processed_data_status": "not_assessed",
            }
        )

    report_paths = {
        path
        for path in report
        if path.startswith("derivatives/meg_derivatives/")
    }

    inventory_paths = {
        str(record["derivative_path"]) for record in records
    }

    missing = report_paths - inventory_paths
    if missing:
        raise ValueError(
            "Verified sidecars are missing from inventory: "
            + ", ".join(sorted(missing))
        )

    if len(records) != len(inventory_paths):
        raise ValueError("Duplicate paths found in generated inventory")

    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a verified MEG derivative-sidecar inventory."
    )
    parser.add_argument("--dataset-root", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--verification-report", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        records = build_inventory(
            args.dataset_root.resolve(),
            args.namespace,
            args.version,
            args.verification_report.resolve(),
        )

        args.inventory.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.parent.mkdir(parents=True, exist_ok=True)

        with args.inventory.open(
            "w", encoding="utf-8", newline=""
        ) as file:
            writer = csv.DictWriter(
                file, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(records)

        metadata = {
            "schema_version": SCHEMA_VERSION,
            "tool_version": TOOL_VERSION,
            "dataset_namespace": args.namespace,
            "dataset_version": args.version,
            "record_type": "metadata_sidecar",
            "row_count": len(records),
            "verification_report_sha256": sha256_file(
                args.verification_report.resolve()
            ),
            "inventory_sha256": sha256_file(args.inventory),
            "generation_time": datetime.now(timezone.utc).isoformat(),
            "lineage_verified": False,
            "processed_data_presence_assessed": False,
        }

        args.metadata.write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )

        print(f"Derivative inventory written: {args.inventory}")
        print(f"Metadata written: {args.metadata}")
        print(f"Verified sidecar records: {len(records)}")
        return 0

    except (OSError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
