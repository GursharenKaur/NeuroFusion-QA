import hashlib
import json
from pathlib import Path

import pytest

from scripts.report_repository_coverage import (
    build_coverage_rows,
    load_repository_tree,
    main,
)


def test_coverage_hashes_present_content_and_marks_missing_files(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    content = b"metadata content"
    (root / "present.json").write_bytes(content)

    entries = [
        {"path": "present.json", "type": "blob", "sha": "repo-sha", "size": len(content)},
        {"path": "missing.nii.gz", "type": "blob", "sha": "missing-sha", "size": 100},
        {"path": "sub-01", "type": "tree", "sha": "tree-sha"},
    ]

    rows = build_coverage_rows(root, entries)
    by_path = {row["path"]: row for row in rows}

    assert by_path["present.json"]["local_status"] == "present_locally"
    assert by_path["present.json"]["content_status"] == "local_content_hashed"
    assert by_path["present.json"]["content_sha256"] == hashlib.sha256(content).hexdigest()

    assert by_path["missing.nii.gz"]["local_status"] == "not_retrieved"
    assert by_path["missing.nii.gz"]["content_status"] == "no_local_file"
    assert by_path["missing.nii.gz"]["content_sha256"] == ""

    assert by_path["sub-01"]["local_status"] == "directory_entry"
    assert by_path["sub-01"]["content_status"] == "not_applicable"


def test_coverage_detects_git_annex_pointer(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    pointer = (
        "../../../../../.git/annex/objects/Mw/m8/"
        "MD5E-s879788831--example.fif/MD5E-s879788831--example.fif"
    )
    (root / "recording.fif").write_text(pointer, encoding="utf-8")

    rows = build_coverage_rows(
        root,
        [{"path": "recording.fif", "type": "blob", "sha": "abc", "size": 879788831}],
    )

    assert rows[0]["content_status"] == "git_annex_pointer"
    assert rows[0]["content_sha256"] == ""


def test_repository_tree_loader_accepts_utf8_bom(tmp_path):
    path = tmp_path / "tree.json"
    path.write_text(
        json.dumps({
            "truncated": False,
            "tree": [{"path": "b", "type": "blob"}, {"path": "a", "type": "blob"}],
        }),
        encoding="utf-8-sig",
    )

    entries = load_repository_tree(path)

    assert [entry["path"] for entry in entries] == ["a", "b"]


def test_repository_tree_loader_rejects_truncated_tree(tmp_path):
    path = tmp_path / "tree.json"
    path.write_text(
        json.dumps({"truncated": True, "tree": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="truncated=false"):
        load_repository_tree(path)


def test_coverage_cli_writes_report(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}", encoding="utf-8")

    tree_path = tmp_path / "tree.json"
    tree_path.write_text(
        json.dumps({
            "truncated": False,
            "tree": [{
                "path": "dataset_description.json",
                "type": "blob",
                "sha": "repository-sha",
                "size": 2,
            }],
        }),
        encoding="utf-8",
    )

    output = tmp_path / "reports" / "coverage.tsv"
    result = main([
        "--dataset-root", str(root),
        "--repository-tree", str(tree_path),
        "--output", str(output),
    ])

    assert result == 0
    assert output.is_file()
    text = output.read_text(encoding="utf-8")
    assert text.startswith("path\tentry_type\t")
    assert "local_content_hashed" in text

def test_coverage_reports_size_mismatch(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    (root / "recording.nii.gz").write_bytes(b"short")

    rows = build_coverage_rows(
        root,
        [{
            "path": "recording.nii.gz",
            "type": "blob",
            "sha": "repository-sha",
            "size": 100,
        }],
    )

    assert rows[0]["local_status"] == "present_locally"
    assert rows[0]["local_size_bytes"] == 5
    assert rows[0]["size_status"] == "size_mismatch"
    assert rows[0]["content_status"] == "local_content_hashed"
