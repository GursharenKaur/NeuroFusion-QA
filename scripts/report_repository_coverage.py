from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_git_annex_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            text = file.read(4096).decode("utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return False

    return (
        text.startswith("../../")
        and "/.git/annex/objects/" in text
        and "MD5E-" in text
    )


def load_repository_tree(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
        raise ValueError("Repository tree JSON must contain a 'tree' array.")

    if data.get("truncated") is not False:
        raise ValueError("Repository tree must explicitly report truncated=false.")

    entries = data["tree"]
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("Repository tree contains an entry without a path.")

    return sorted(entries, key=lambda entry: entry["path"])


def build_coverage_rows(
    dataset_root: Path,
    repository_entries: list[dict[str, Any]],
) -> list[dict[str, str | int]]:
    root = dataset_root.resolve()
    rows: list[dict[str, str | int]] = []

    for entry in repository_entries:
        relative = entry["path"]
        entry_type = str(entry.get("type", "unknown"))
        expected_size = entry.get("size", "")
        has_expected_size = (
            isinstance(expected_size, int) and expected_size >= 0
        )

        row: dict[str, str | int] = {
            "path": relative,
            "entry_type": entry_type,
            "expected_size_bytes": expected_size if has_expected_size else "",
            "local_status": "not_retrieved",
            "local_size_bytes": "",
            "size_status": (
                "expected_size_unavailable"
                if entry_type == "blob" and not has_expected_size
                else "not_applicable"
            ),
            "content_sha256": "",
            "content_status": "no_local_file",
            "repository_blob_sha": str(entry.get("sha", "")),
        }

        if entry_type != "blob":
            row["local_status"] = "directory_entry"
            row["content_status"] = "not_applicable"
            rows.append(row)
            continue

        local_path = (root / Path(relative)).resolve()
        if not local_path.is_relative_to(root):
            raise ValueError(f"Repository path escapes dataset root: {relative}")

        if not local_path.is_file():
            rows.append(row)
            continue

        local_size = local_path.stat().st_size
        row["local_size_bytes"] = local_size
        row["local_status"] = "present_locally"

        if not has_expected_size:
            row["size_status"] = "expected_size_unavailable"
        elif local_size == expected_size:
            row["size_status"] = "matches_expected_size"
        else:
            row["size_status"] = "size_mismatch"

        if is_git_annex_pointer(local_path):
            row["content_status"] = "git_annex_pointer"
        else:
            row["content_sha256"] = sha256_file(local_path)
            row["content_status"] = "local_content_hashed"

        rows.append(row)

    return rows


def write_coverage_tsv(
    path: Path,
    rows: list[dict[str, str | int]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "path",
        "entry_type",
        "expected_size_bytes",
        "local_status",
        "local_size_bytes",
        "size_status",
        "content_sha256",
        "content_status",
        "repository_blob_sha",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a pinned repository tree with local files without "
            "treating absent content as retrieved."
        )
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--repository-tree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        root = args.dataset_root.resolve()
        if not root.is_dir():
            raise ValueError(f"Dataset root is not a directory: {root}")

        entries = load_repository_tree(args.repository_tree)
        rows = build_coverage_rows(root, entries)
        write_coverage_tsv(args.output, rows)

        blob_rows = [row for row in rows if row["entry_type"] == "blob"]
        counts: dict[str, int] = {}
        for row in blob_rows:
            status = str(row["content_status"])
            counts[status] = counts.get(status, 0) + 1

        print(f"Coverage report written: {args.output}")
        print(f"Repository entries: {len(rows)}")
        print(f"Repository file entries: {len(blob_rows)}")
        for status, count in sorted(counts.items()):
            print(f"{status}: {count}")

        return 0

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Coverage report error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
