from neurofusion_qa.lineage import (
    check_i4_derivative_lineage,
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

def test_i4_complete_derivative_lineage_is_clean():
    record = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/source.nii.gz",
        source_sha256="source123",
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/preproc/sub-01_bold.nii.gz",
        derivative_sha256="derivative123",
    )

    findings = check_i4_derivative_lineage(records=[record])

    assert findings == []


def test_i4_missing_derivative_recipe_is_reported():
    record = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/source.nii.gz",
        source_sha256="source123",
        derivative_recipe_sha256=None,
        derivative_path="derivatives/preproc/sub-01_bold.nii.gz",
        derivative_sha256="derivative123",
    )

    findings = check_i4_derivative_lineage(records=[record])

    assert len(findings) == 1
    assert findings[0].rule_id == "I4.derivative_lineage_incomplete"
    assert findings[0].severity == "ERROR"


def test_i4_missing_parent_acquisition_is_reported():
    record = ManifestRecord(
        dataset_namespace="",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id=None,
        modality=None,
        task=None,
        acquisition=None,
        run=None,
        source_path=None,
        source_sha256=None,
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/preproc/sub-01_output.nii.gz",
        derivative_sha256="derivative123",
    )

    findings = check_i4_derivative_lineage(records=[record])

    assert any(
        finding.rule_id == "I4.missing_parent_acquisition"
        for finding in findings
    )


def test_i4_same_derivative_key_with_conflicting_hashes_is_reported():
    record_1 = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/source.nii.gz",
        source_sha256="source123",
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/preproc/sub-01_bold.nii.gz",
        derivative_sha256="hash_a",
    )

    record_2 = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/source.nii.gz",
        source_sha256="source123",
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/preproc/sub-01_bold.nii.gz",
        derivative_sha256="hash_b",
    )

    findings = check_i4_derivative_lineage(
        records=[record_1, record_2]
    )

    assert any(
        finding.rule_id == "I4.derivative_key_collision"
        for finding in findings
    )

def test_i4_whitespace_recipe_hash_is_incomplete():
    record = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        derivative_recipe_sha256="   ",
        derivative_path="derivatives/sub-01_bold.nii.gz",
    )

    findings = check_i4_derivative_lineage([record])

    assert any(
        finding.rule_id == "I4.derivative_lineage_incomplete"
        and "derivative_recipe_sha256"
        in finding.observed["missing_fields"]
        for finding in findings
    )


def test_i4_whitespace_derivative_path_is_incomplete():
    record = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        derivative_recipe_sha256="recipe123",
        derivative_path="   ",
    )

    findings = check_i4_derivative_lineage([record])

    assert any(
        finding.rule_id == "I4.derivative_lineage_incomplete"
        and "derivative_path" in finding.observed["missing_fields"]
        for finding in findings
    )


def test_i4_whitespace_parent_namespace_is_missing():
    record = ManifestRecord(
        dataset_namespace="   ",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/sub-01_bold.nii.gz",
    )

    findings = check_i4_derivative_lineage([record])

    assert any(
        finding.rule_id == "I4.missing_parent_acquisition"
        and "dataset_namespace"
        in finding.observed["missing_parent_fields"]
        for finding in findings
    )


def test_i4_unavailable_hash_does_not_create_hash_collision():
    record_with_hash = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/sub-01_bold.nii.gz",
        derivative_sha256="hash_a",
    )
    record_without_hash = ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        derivative_recipe_sha256="recipe123",
        derivative_path="derivatives/sub-01_bold.nii.gz",
        derivative_sha256="not_retrieved",
    )

    findings = check_i4_derivative_lineage(
        [record_with_hash, record_without_hash]
    )

    assert not any(
        finding.rule_id == "I4.derivative_key_collision"
        for finding in findings
    )
