from neurofusion_qa.manifest import ManifestRecord
from neurofusion_qa.split import (
    check_i5_person_split_independence,
    check_i5_source_hash_split_independence,
    check_i5_derivative_hash_split_independence,
)


def test_i5_person_in_multiple_splits_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01/a.nii.gz",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01/b.nii.gz",
            split="test",
        ),
    ]

    findings = check_i5_person_split_independence(records)

    assert len(findings) == 1
    assert findings[0].rule_id == "I5.person_split_independence"
    assert findings[0].severity == "ERROR"


def test_i5_person_with_one_split_is_clean():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01/a.nii.gz",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01/b.nii.gz",
            split="train",
        ),
    ]

    assert check_i5_person_split_independence(records) == []


def test_i5_source_hash_across_splits_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            source_path="sub-02/b.nii.gz",
            source_sha256="abc",
            split="test",
        ),
    ]

    findings = check_i5_source_hash_split_independence(records)

    assert len(findings) == 1
    assert findings[0].rule_id == "I5.source_hash_split_independence"


def test_i5_derivative_hash_across_splits_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            derivative_path="derivatives/a.nii.gz",
            derivative_sha256="xyz",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            derivative_path="derivatives/b.nii.gz",
            derivative_sha256="xyz",
            split="test",
        ),
    ]

    findings = check_i5_derivative_hash_split_independence(records)

    assert len(findings) == 1
    assert findings[0].rule_id == "I5.derivative_hash_split_independence"


def test_i5_same_hash_within_same_split_is_clean():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            source_path="sub-02/b.nii.gz",
            source_sha256="abc",
            split="train",
        ),
    ]

    assert check_i5_source_hash_split_independence(records) == []