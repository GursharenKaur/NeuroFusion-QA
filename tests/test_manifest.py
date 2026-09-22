from neurofusion_qa.manifest import (
    ManifestRecord,
    build_manifest_records,
    record_from_bids_file,
)
from bids import BIDSLayout


def test_person_key_preserves_dataset_namespace_version_and_raw_participant_id():
    record = ManifestRecord(
        dataset_namespace="openneuro:ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
    )

    assert record.person_key == (
        "openneuro:ds000117",
        "1.1.0",
        "sub-01",
    )


def test_acquisition_key_extends_person_key():
    record = ManifestRecord(
        dataset_namespace="openneuro:ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="rest",
        acquisition="highres",
        run="01",
    )

    assert record.acquisition_key == (
        "openneuro:ds000117",
        "1.1.0",
        "sub-01",
        "ses-01",
        "bold",
        "rest",
        "highres",
        "01",
    )


def test_missing_bids_entities_are_explicit_nulls():
    record = ManifestRecord(
        dataset_namespace="openneuro:ds000117",
        dataset_version="1.1.0",
        participant_id="sub-emptyroom",
    )

    assert record.session_id is None
    assert record.modality is None
    assert record.task is None
    assert record.acquisition is None
    assert record.run is None


def test_raw_participant_label_is_not_normalized():
    record = ManifestRecord(
        dataset_namespace="openneuro:ds000117",
        dataset_version="1.1.0",
        participant_id="sub-001",
    )

    assert record.participant_id == "sub-001"
    assert record.person_key[-1] == "sub-001"

def test_record_from_bids_file_preserves_bids_entities():
    layout = BIDSLayout(
        "tests/fixtures/bids_minimal",
        validate=True,
    )

    bids_files = layout.get(
        suffix="bold",
        return_type="object",
    )

    record = record_from_bids_file(
        bids_files[0],
        dataset_namespace="openneuro:synthetic",
        dataset_version="0.1.0",
    )

    assert record.dataset_namespace == "openneuro:synthetic"
    assert record.dataset_version == "0.1.0"

    assert record.participant_id == "sub-01"
    assert record.session_id is None
    assert record.modality == "bold"
    assert record.task == "task-rest"
    assert record.acquisition is None
    assert record.run == "01"

def test_build_manifest_records_is_deterministic():
    records = build_manifest_records(
        "tests/fixtures/bids_minimal",
        dataset_namespace="openneuro:synthetic",
        dataset_version="0.1.0",
    )

    assert len(records) == 1

    record = records[0]

    assert record.participant_id == "sub-01"
    assert record.source_path == (
        "sub-01/func/sub-01_task-rest_run-01_bold.nii.gz"
    )


def test_build_manifest_records_normalizes_path_to_posix():
    records = build_manifest_records(
        "tests/fixtures/bids_minimal",
        dataset_namespace="openneuro:synthetic",
        dataset_version="0.1.0",
    )

    assert records[0].source_path is not None
    assert "\\" not in records[0].source_path
    assert not records[0].source_path.startswith("/")