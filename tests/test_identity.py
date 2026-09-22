from neurofusion_qa.identity import (
    Finding,
    check_i1_namespace_completeness,
)
from neurofusion_qa.manifest import ManifestRecord

def test_i1_namespace_completeness_clean():
    records = [
        ManifestRecord(
            dataset_namespace="openneuro:synthetic",
            dataset_version="0.1.0",
            participant_id="sub-01",
        )
    ]

    findings = check_i1_namespace_completeness(records)

    assert findings == []

def test_i1_namespace_completeness_detects_missing_namespace():
    records = [
        ManifestRecord(
            dataset_namespace="",
            dataset_version="0.1.0",
            participant_id="sub-01",
        )
    ]

    findings = check_i1_namespace_completeness(records)

    assert len(findings) == 1

    finding = findings[0]

    assert isinstance(finding, Finding)
    assert finding.rule_id == "I1.namespace_completeness"
    assert finding.severity == "ERROR"
    assert finding.key_type == "person_key"
    assert finding.affected_keys == (
        ("", "0.1.0", "sub-01"),
    )

def test_i1_namespace_completeness_detects_missing_participant():
    records = [
        ManifestRecord(
            dataset_namespace="openneuro:synthetic",
            dataset_version="0.1.0",
            participant_id="",
        )
    ]

    findings = check_i1_namespace_completeness(records)

    assert len(findings) == 1
    assert findings[0].rule_id == "I1.namespace_completeness"
    assert findings[0].severity == "ERROR"

from neurofusion_qa.identity import (
    Finding,
    check_i1_acquisition_key_injectivity,
    check_i1_namespace_completeness,
)
from neurofusion_qa.manifest import ManifestRecord


def test_i1_acquisition_key_injectivity_accepts_identical_source_identity():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/sub-01_task-rest_run-01_bold.nii.gz",
        source_sha256="abc123",
    )

    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/sub-01_task-rest_run-01_bold.nii.gz",
        source_sha256="abc123",
    )

    findings = check_i1_acquisition_key_injectivity(
        [record_1, record_2]
    )

    assert findings == []


def test_i1_acquisition_key_injectivity_detects_different_source_paths():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/source_a.nii.gz",
        source_sha256="abc123",
    )

    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/source_b.nii.gz",
        source_sha256="def456",
    )

    findings = check_i1_acquisition_key_injectivity(
        [record_1, record_2]
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.rule_id == "I1.acquisition_key_injectivity"
    assert finding.severity == "ERROR"
    assert finding.key_type == "acquisition_key"
    assert finding.affected_keys == (record_1.acquisition_key,)
    assert finding.observed == "2 distinct source file/hash identities"
    assert len(finding.evidence_rows) == 2


def test_i1_acquisition_key_injectivity_detects_same_path_with_different_hash():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/sub-01_task-rest_run-01_bold.nii.gz",
        source_sha256="abc123",
    )

    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
        run="01",
        source_path="sub-01/func/sub-01_task-rest_run-01_bold.nii.gz",
        source_sha256="different_hash",
    )

    findings = check_i1_acquisition_key_injectivity(
        [record_1, record_2]
    )

    assert len(findings) == 1

    finding = findings[0]

    assert finding.rule_id == "I1.acquisition_key_injectivity"
    assert finding.severity == "ERROR"
    assert finding.key_type == "acquisition_key"
    assert finding.affected_keys == (record_1.acquisition_key,)
    assert len(finding.evidence_rows) == 2