
import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_derivative_inventory import (
    build_inventory,
    main,
    sha256_file,
)


NAMESPACE = "openneuro:ds000117"
VERSION = "1.1.0"


def write_json(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def git_blob_sha1(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def make_fixture(tmp_path: Path, count: int = 2):
    root = tmp_path / "dataset"
    derivative_root = root / "derivatives" / "meg_derivatives"
    report_path = tmp_path / "verification.csv"

    paths = []

    for index in range(1, count + 1):
        participant = f"sub-{index:02d}"
        relative = (
            Path("derivatives")
            / "meg_derivatives"
            / participant
            / "ses-meg"
            / "meg"
            / f"{participant}_ses-meg_task-rest_proc-sss_meg.json"
        )
        path = root / relative
        content = json.dumps(
            {"participant": participant, "fixture": True},
            sort_keys=True,
        ) + "\n"
        write_json(path, content)
        paths.append((relative.as_posix(), path))

    with report_path.open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "Path",
                "ExpectedBytes",
                "ActualBytes",
                "GitTreeBlobSHA",
                "LocalGitBlobSHA",
                "GitBlobMatch",
                "SHA256",
            ],
        )
        writer.writeheader()

        for relative, path in paths:
            content = path.read_bytes()
            blob_sha = git_blob_sha1(content)
            writer.writerow(
                {
                    "Path": relative,
                    "ExpectedBytes": len(content),
                    "ActualBytes": len(content),
                    "GitTreeBlobSHA": blob_sha,
                    "LocalGitBlobSHA": blob_sha,
                    "GitBlobMatch": "True",
                    "SHA256": hashlib.sha256(content).hexdigest(),
                }
            )

    return root, report_path, paths


def test_inventory_contains_every_verified_sidecar_once(tmp_path):
    root, report, paths = make_fixture(tmp_path, count=3)

    records = build_inventory(root, NAMESPACE, VERSION, report)

    inventory_paths = [record["derivative_path"] for record in records]

    assert len(records) == 3
    assert len(set(inventory_paths)) == 3
    assert set(inventory_paths) == {relative for relative, _ in paths}
    assert all(record["record_type"] == "metadata_sidecar" for record in records)
    assert all(record["git_blob_match"] == "true" for record in records)


def test_inventory_paths_are_relative_posix_paths(tmp_path):
    root, report, _ = make_fixture(tmp_path)

    records = build_inventory(root, NAMESPACE, VERSION, report)

    for record in records:
        path = str(record["derivative_path"])
        assert path.startswith("derivatives/meg_derivatives/")
        assert "\\" not in path
        assert not Path(path).is_absolute()


def test_inventory_hashes_match_local_files(tmp_path):
    root, report, paths = make_fixture(tmp_path)

    records = build_inventory(root, NAMESPACE, VERSION, report)
    expected = {
        relative: hashlib.sha256(path.read_bytes()).hexdigest()
        for relative, path in paths
    }

    for record in records:
        assert record["derivative_sha256"] == expected[record["derivative_path"]]


def test_inventory_is_sorted_deterministically(tmp_path):
    root, report, _ = make_fixture(tmp_path, count=4)

    first = build_inventory(root, NAMESPACE, VERSION, report)
    second = build_inventory(root, NAMESPACE, VERSION, report)

    first_paths = [record["derivative_path"] for record in first]
    second_paths = [record["derivative_path"] for record in second]

    assert first_paths == sorted(first_paths)
    assert first_paths == second_paths


def test_inventory_rejects_modified_file(tmp_path):
    root, report, paths = make_fixture(tmp_path)
    _, file_path = paths[0]
    file_path.write_text('{"modified": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Expected-size mismatch|Reported-size mismatch|SHA-256 verification failed"):
        build_inventory(root, NAMESPACE, VERSION, report)


def test_inventory_rejects_failed_git_blob_verification(tmp_path):
    root, report, _ = make_fixture(tmp_path)

    rows = list(csv.DictReader(report.open(encoding="utf-8", newline="")))
    rows[0]["GitBlobMatch"] = "False"

    with report.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="Git blob verification failed"):
        build_inventory(root, NAMESPACE, VERSION, report)


def test_inventory_rejects_missing_report_entry(tmp_path):
    root, report, _ = make_fixture(tmp_path)

    rows = list(csv.DictReader(report.open(encoding="utf-8", newline="")))
    rows.pop()

    with report.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="absent from the verification report"):
        build_inventory(root, NAMESPACE, VERSION, report)


def test_inventory_rejects_non_json_file(tmp_path):
    root, report, _ = make_fixture(tmp_path)
    extra = root / "derivatives" / "meg_derivatives" / "extra.txt"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("not a sidecar", encoding="utf-8")

    with pytest.raises(ValueError, match="Unexpected non-JSON file"):
        build_inventory(root, NAMESPACE, VERSION, report)


def test_cli_writes_inventory_and_metadata(tmp_path):
    root, report, _ = make_fixture(tmp_path)
    inventory_path = tmp_path / "out" / "inventory.tsv"
    metadata_path = tmp_path / "out" / "metadata.json"

    result = main(
        [
            "--dataset-root", str(root),
            "--namespace", NAMESPACE,
            "--version", VERSION,
            "--verification-report", str(report),
            "--inventory", str(inventory_path),
            "--metadata", str(metadata_path),
        ]
    )

    assert result == 0
    assert inventory_path.is_file()
    assert metadata_path.is_file()

    with inventory_path.open(encoding="utf-8", newline="") as file:
        records = list(csv.DictReader(file, delimiter="\t"))

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert len(records) == 2
    assert metadata["row_count"] == 2
    assert metadata["lineage_verified"] is False
    assert metadata["processed_data_presence_assessed"] is False
    assert metadata["inventory_sha256"] == sha256_file(inventory_path)
