import csv
import json
from pathlib import Path

from scripts.build_bids_manifest import main


FIXTURE = Path(__file__).parent / "fixtures" / "bids_minimal"


def test_builder_writes_valid_tsv_and_metadata(tmp_path):
    manifest_path = tmp_path / "nested" / "manifest.tsv"
    metadata_path = tmp_path / "nested" / "metadata.json"

    result = main([
        "--dataset-root", str(FIXTURE),
        "--namespace", "smoke-test",
        "--version", "0.1",
        "--manifest", str(manifest_path),
        "--metadata", str(metadata_path),
    ])

    assert result == 0
    assert manifest_path.is_file()
    assert metadata_path.is_file()

    with manifest_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        rows = list(reader)

    assert reader.fieldnames is not None
    assert "participant_id" in reader.fieldnames
    assert len(rows) == 1
    assert rows[0]["participant_id"] == "sub-01"
    assert rows[0]["source_path"] == (
        "sub-01/func/sub-01_task-rest_run-01_bold.nii.gz"
    )
    assert rows[0]["source_sha256"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )

    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)
    assert metadata["row_count"] == 1
    assert metadata_text.endswith("\n")
    assert not metadata_text.endswith("\\n")


def test_builder_metadata_only_marks_records_not_retrieved(tmp_path):
    manifest_path = tmp_path / "manifest.tsv"
    metadata_path = tmp_path / "metadata.json"

    result = main([
        "--dataset-root", str(FIXTURE),
        "--namespace", "smoke-test",
        "--version", "0.1",
        "--manifest", str(manifest_path),
        "--metadata", str(metadata_path),
        "--metadata-only",
    ])

    assert result == 0

    with manifest_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file, delimiter="\t"))

    assert len(rows) == 1
    assert rows[0]["source_sha256"] == "not_retrieved"


def test_builder_rejects_nonexistent_dataset_root(tmp_path, capsys):
    result = main([
        "--dataset-root", str(tmp_path / "missing"),
        "--namespace", "smoke-test",
        "--version", "0.1",
        "--manifest", str(tmp_path / "manifest.tsv"),
        "--metadata", str(tmp_path / "metadata.json"),
    ])

    assert result == 2
    assert "Dataset root is not a directory" in capsys.readouterr().err
    assert not (tmp_path / "manifest.tsv").exists()
    assert not (tmp_path / "metadata.json").exists()
