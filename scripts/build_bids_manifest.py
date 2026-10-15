from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

from neurofusion_qa.manifest import (
    ManifestRecord,
    build_manifest_metadata,
    build_manifest_records,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a manifest from locally available BIDS files."
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help=(
            "Mark source hashes as not_retrieved. Use only when source "
            "contents genuinely have not been retrieved."
        ),
    )
    return parser


def write_manifest_tsv(path: Path, records: list[ManifestRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [field.name for field in fields(ManifestRecord)]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file, fieldnames=columns, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        root = args.dataset_root.resolve()
        if not root.is_dir():
            raise ValueError(f"Dataset root is not a directory: {root}")

        records = build_manifest_records(
            root,
            dataset_namespace=args.namespace,
            dataset_version=args.version,
            metadata_only=args.metadata_only,
        )
        metadata = build_manifest_metadata(root, row_count=len(records))

        write_manifest_tsv(args.manifest, records)
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        args.metadata.write_text(
            json.dumps(asdict(metadata), indent=2) + "\n",
            encoding="utf-8",
        )

        print(
            f"Manifest written: {args.manifest} "
            f"({len(records)} participant-associated records)"
        )
        print(f"Metadata written: {args.metadata}")
        print(
            "Hash mode: "
            + ("not_retrieved" if args.metadata_only else "SHA-256 of local files")
        )
        return 0

    except (OSError, ValueError) as exc:
        print(f"Manifest builder error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
