from neurofusion_qa.lineage import (
    check_i4_identical_source_hashes_under_different_keys,
    check_i4_identical_derivative_hashes_under_different_keys,
    check_i4_repeated_paths_or_rows,
)

from neurofusion_qa.manifest import ManifestRecord

def test_i4_same_hash_same_key_is_clean():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
        ),
    ]

    findings = check_i4_identical_source_hashes_under_different_keys(records)

    assert findings == []


def test_i4_identical_hash_under_different_keys_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            source_path="sub-02/b.nii.gz",
            source_sha256="abc",
        ),
    ]

    findings = check_i4_identical_source_hashes_under_different_keys(records)

    assert len(findings) == 1
    assert findings[0].rule_id == "I4.identical_source_hash_different_keys"
    assert findings[0].severity == "ERROR"
    assert len(findings[0].affected_keys) == 2


def test_i4_repeated_source_path_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            source_path="sub-01/a.nii.gz",
            source_sha256="abc",
        ),
    ]

    findings = check_i4_repeated_paths_or_rows(records)

    rule_ids = {finding.rule_id for finding in findings}

    assert "I4.repeated_source_path" in rule_ids


def test_i4_exact_repeated_row_is_reported():
    record = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/a.nii.gz",
        source_sha256="abc",
    )

    findings = check_i4_repeated_paths_or_rows([record, record])

    rule_ids = {finding.rule_id for finding in findings}

    assert "I4.repeated_row" in rule_ids

def test_i4_identical_derivative_hash_under_different_keys_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            derivative_path="derivatives/a.nii.gz",
            derivative_sha256="xyz",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            derivative_path="derivatives/b.nii.gz",
            derivative_sha256="xyz",
        ),
    ]

    findings = check_i4_identical_derivative_hashes_under_different_keys(
        records
    )

    assert len(findings) == 1
    assert findings[0].rule_id == (
        "I4.identical_derivative_hash_different_keys"
    )
    assert findings[0].severity == "ERROR"
    assert len(findings[0].affected_keys) == 2