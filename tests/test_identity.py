from neurofusion_qa.identity import (
    AuthoritativeCrosswalk,
    Finding,
    canonicalize_participant_id,
    check_i1_acquisition_key_injectivity,
    check_i1_canonicalization_collision,
    check_i1_namespace_completeness,
    check_i2_join_cardinality,
    check_i3_cross_modal_pairing,
    check_i5_split_independence,
    check_i6_metric_denominator_traceability,
)
import pytest

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
    assert finding.observed == (
        "2 distinct source paths; "
        "0 paths with conflicting retrieved hashes"
    )
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

def test_canonicalize_participant_id_normalizes_numeric_variants():
    assert canonicalize_participant_id("sub-01") == "sub-1"
    assert canonicalize_participant_id("sub-1") == "sub-1"
    assert canonicalize_participant_id("SUB-01") == "sub-1"
    assert canonicalize_participant_id("sub_01") == "sub-1"


def test_i1_canonicalization_collision_detects_distinct_raw_ids():
    records = [
        ManifestRecord(
            dataset_namespace="openneuro:synthetic",
            dataset_version="0.1.0",
            participant_id="sub-01",
        ),
        ManifestRecord(
            dataset_namespace="openneuro:synthetic",
            dataset_version="0.1.0",
            participant_id="sub-1",
        ),
    ]

    findings = check_i1_canonicalization_collision(records)

    assert len(findings) == 1

    finding = findings[0]

    assert isinstance(finding, Finding)
    assert finding.rule_id == "I1.canonicalization_collision"
    assert finding.severity == "ERROR"
    assert finding.key_type == "person_key"

    assert set(finding.affected_keys) == {
        (
            "openneuro:synthetic",
            "0.1.0",
            "sub-01",
        ),
        (
            "openneuro:synthetic",
            "0.1.0",
            "sub-1",
        ),
    }

    assert finding.observed == {
        "canonical_participant_id": "sub-1",
        "raw_participant_ids": ("sub-01", "sub-1"),
    }


def test_i1_canonicalization_collision_accepts_same_raw_id():
    records = [
        ManifestRecord(
            dataset_namespace="openneuro:synthetic",
            dataset_version="0.1.0",
            participant_id="sub-01",
        ),
        ManifestRecord(
            dataset_namespace="openneuro:synthetic",
            dataset_version="0.1.0",
            participant_id="sub-01",
        ),
    ]

    findings = check_i1_canonicalization_collision(records)

    assert findings == []


def test_i1_canonicalization_collision_is_namespace_qualified():
    records = [
        ManifestRecord(
            dataset_namespace="dataset-A",
            dataset_version="1.0",
            participant_id="sub-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset-B",
            dataset_version="1.0",
            participant_id="sub-1",
        ),
    ]

    findings = check_i1_canonicalization_collision(records)

    assert findings == []


def test_i1_acquisition_key_injectivity_retains_paths_without_retrieved_hashes():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/func/source_a.nii.gz",
        source_sha256="not_retrieved",
    )
    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/func/source_b.nii.gz",
        source_sha256="not_retrieved",
    )

    findings = check_i1_acquisition_key_injectivity(
        [record_1, record_2]
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "I1.acquisition_key_injectivity"

    evidence_paths = {
        row["source_path"] for row in findings[0].evidence_rows
    }
    assert evidence_paths == {
        "sub-01/func/source_a.nii.gz",
        "sub-01/func/source_b.nii.gz",
    }
    assert all(
        row["source_sha256"] == "not_retrieved"
        for row in findings[0].evidence_rows
    )

def test_i2_one_to_one_clean():
    findings = check_i2_join_cardinality(
        {"sub-01": 1, "sub-02": 1},
        {"sub-01": 1, "sub-02": 1},
        relation="one_to_one",
    )

    assert findings == []

def test_i2_one_to_one_detects_multiple_matches():
    findings = check_i2_join_cardinality(
        {"sub-01": 1},
        {"sub-01": 2},
        relation="one_to_one",
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "I2.cardinality_mismatch"
    assert findings[0].severity == "ERROR"
    assert findings[0].affected_keys == ("sub-01",)


def test_i2_one_to_many_is_valid():
    findings = check_i2_join_cardinality(
        {"sub-01": 1},
        {"sub-01": 3},
        relation="one_to_many",
    )

    assert findings == []


def test_i2_many_to_one_is_valid():
    findings = check_i2_join_cardinality(
        {"sub-01": 3},
        {"sub-01": 1},
        relation="many_to_one",
    )

    assert findings == []


def test_i2_many_to_many_fails_closed():
    findings = check_i2_join_cardinality(
        {"sub-01": 2},
        {"sub-01": 3},
        relation="one_to_one",
    )

    rule_ids = {finding.rule_id for finding in findings}

    assert "I2.many_to_many" in rule_ids
    assert "I2.cardinality_mismatch" in rule_ids


def test_i2_reports_unmatched_left_and_right_keys():
    findings = check_i2_join_cardinality(
        {"sub-01": 1, "sub-02": 1},
        {"sub-01": 1, "sub-03": 1},
        relation="one_to_one",
    )

    unmatched = next(
        finding
        for finding in findings
        if finding.rule_id == "I2.unmatched_keys"
    )

    assert unmatched.severity == "ERROR"
    assert set(unmatched.affected_keys) == {
        "sub-02",
        "sub-03",
    }


def test_i2_rejects_undeclared_relation():
    try:
        check_i2_join_cardinality(
            {"sub-01": 1},
            {"sub-01": 1},
            relation="many_to_many",
        )
    except ValueError as exc:
        assert "Unsupported join relation" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

@pytest.mark.parametrize("invalid_count", [0, -1])
def test_i2_rejects_non_positive_counts(invalid_count):
    with pytest.raises(ValueError, match="must be positive"):
        check_i2_join_cardinality(
            {"sub-01": invalid_count},
            {"sub-01": 1},
            relation="one_to_one",
        )


@pytest.mark.parametrize("invalid_count", [True, False, 1.5, "2"])
def test_i2_rejects_non_integer_counts(invalid_count):
    with pytest.raises(ValueError, match="must be an integer"):
        check_i2_join_cardinality(
            {"sub-01": invalid_count},
            {"sub-01": 1},
            relation="one_to_one",
        )

def test_i3_same_person_cross_modal_pair_is_clean():
    left = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert findings == []

def test_i3_detects_cross_modal_person_mismatch():
    left = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-02",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "I3.person_pairing"
    assert findings[0].severity == "ERROR"

def test_i3_does_not_accept_identical_participant_strings_across_namespaces():
    left = ManifestRecord(
        dataset_namespace="dataset-A",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="dataset-B",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "I3.person_pairing"

def test_i3_rejects_cross_dataset_pair_not_present_in_crosswalk():
    left = ManifestRecord(
        dataset_namespace="dataset-A",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="dataset-B",
        dataset_version="1.0",
        participant_id="sub-42",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    crosswalk = AuthoritativeCrosswalk(
        source="approved_crosswalk.csv",
        version="1.0",
        sha256="abc123",
        approved_by="PI",
        approved_date="2026-09-22",
        mapping={
            left.person_key: (
                "dataset-B",
                "1.0",
                "sub-99",
            ),
        },
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)],
        crosswalk=crosswalk,
    )

    assert any(
        finding.rule_id == "I3.person_pairing"
        for finding in findings
    )



def test_i3_detects_session_mismatch():
    left = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-02",
        modality="eeg",
        task="task-rest",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "I3.session_compatibility"

def test_i3_detects_task_mismatch():
    left = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="eeg",
        task="task-memory",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "I3.task_compatibility"

def test_i3_missing_session_on_one_side_is_not_assumed_compatible():
    left = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id=None,
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert any(
        finding.rule_id == "I3.session_compatibility"
        for finding in findings
    )

def test_i3_rejects_same_modality_pair():
    left = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)]
    )

    assert any(
        finding.rule_id == "I3.modality_pairing"
        for finding in findings
    )

def test_i3_authoritative_crosswalk_allows_valid_cross_dataset_pair():
    left = ManifestRecord(
        dataset_namespace="dataset-A",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="dataset-B",
        dataset_version="1.0",
        participant_id="sub-42",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    crosswalk = AuthoritativeCrosswalk(
        source="approved_crosswalk.csv",
        version="1.0",
        sha256="a" * 64,
        approved_by="PI",
        approved_date="2026-09-22",
        mapping={
            left.person_key: right.person_key,
        },
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)],
        crosswalk=crosswalk,
    )

    assert findings == []


def test_i3_invalid_crosswalk_metadata_cannot_authorize_pairing():
    left = ManifestRecord(
        dataset_namespace="dataset-A",
        dataset_version="1.0",
        participant_id="sub-01",
        session_id="ses-01",
        modality="bold",
        task="task-rest",
    )

    right = ManifestRecord(
        dataset_namespace="dataset-B",
        dataset_version="1.0",
        participant_id="sub-42",
        session_id="ses-01",
        modality="eeg",
        task="task-rest",
    )

    crosswalk = AuthoritativeCrosswalk(
        source="approved_crosswalk.csv",
        version="1.0",
        sha256="abc123",
        approved_by="PI",
        approved_date="2026-09-22",
        mapping={
            left.person_key: right.person_key,
        },
    )

    findings = check_i3_cross_modal_pairing(
        [(left, right)],
        crosswalk=crosswalk,
    )

    rule_ids = {finding.rule_id for finding in findings}

    assert "I3.crosswalk_provenance" in rule_ids
    assert "I3.person_pairing" in rule_ids
    assert all(finding.severity == "ERROR" for finding in findings)

def test_i5_person_split_is_clean():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="test",
        ),
    ]

    findings = check_i5_split_independence(records)

    assert findings == []


def test_i5_detects_person_in_multiple_splits():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
    ]

    findings = check_i5_split_independence(records)

    assert any(
        finding.rule_id == "I5.person_split_leakage"
        for finding in findings
    )


def test_i5_detects_source_hash_across_splits():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
            source_path="sub-01/a.nii.gz",
            source_sha256="same-source-hash",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="test",
            source_path="sub-02/b.nii.gz",
            source_sha256="same-source-hash",
        ),
    ]

    findings = check_i5_split_independence(records)

    assert any(
        finding.rule_id == "I5.source_split_leakage"
        for finding in findings
    )


def test_i5_detects_derivative_hash_across_splits():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
            derivative_path="derivatives/a.nii.gz",
            derivative_sha256="same-derivative-hash",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="test",
            derivative_path="derivatives/b.nii.gz",
            derivative_sha256="same-derivative-hash",
        ),
    ]

    findings = check_i5_split_independence(records)

    assert any(
        finding.rule_id == "I5.derivative_split_leakage"
        for finding in findings
    )


def test_i5_grouping_variable_is_clean_when_confined_to_one_split():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-03",
            split="test",
        ),
    ]

    grouping_variables = {
        "family_id": {
            "family-01": [
                ("test", "1.0", "sub-01"),
                ("test", "1.0", "sub-02"),
            ],
        }
    }

    findings = check_i5_split_independence(
        records,
        grouping_variables=grouping_variables,
    )

    assert findings == []

def test_i5_detects_grouping_variable_across_splits():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="test",
        ),
    ]

    grouping_variables = {
        "family_id": {
            "family-01": [
                ("test", "1.0", "sub-01"),
                ("test", "1.0", "sub-02"),
            ],
        }
    }

    findings = check_i5_split_independence(
        records,
        grouping_variables=grouping_variables,
    )

    assert any(
        finding.rule_id == "I5.grouping_variable_split_leakage"
        for finding in findings
    )

def test_i5_missing_split_is_reported():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split=None,
        ),
    ]

    findings = check_i5_split_independence(records)

    assert any(
        finding.rule_id == "I5.missing_split"
        for finding in findings
    )

def test_i6_metric_denominator_is_traceable():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="test",
        ),
    ]

    populations = {
        "test_population_v1": [
            ("test", "1.0", "sub-01"),
            ("test", "1.0", "sub-02"),
        ]
    }

    metrics = [
        {
            "metric_name": "accuracy",
            "split": "test",
            "numerator": 2,
            "denominator": 2,
            "population_key": "test_population_v1",
        }
    ]

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics,
        populations,
    )

    assert findings == []


def test_i6_detects_denominator_mismatch():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-02",
            split="test",
        ),
    ]

    populations = {
        "test_population_v1": [
            ("test", "1.0", "sub-01"),
            ("test", "1.0", "sub-02"),
        ]
    }

    metrics = [
        {
            "metric_name": "accuracy",
            "split": "test",
            "numerator": 1,
            "denominator": 5,
            "population_key": "test_population_v1",
        }
    ]

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics,
        populations,
    )

    assert any(
        finding.rule_id == "I6.denominator_mismatch"
        for finding in findings
    )


def test_i6_detects_unknown_population():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
    ]

    populations = {}

    metrics = [
        {
            "metric_name": "accuracy",
            "split": "test",
            "numerator": 1,
            "denominator": 1,
            "population_key": "unknown_population",
        }
    ]

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics,
        populations,
    )

    assert any(
        finding.rule_id == "I6.untraceable_population"
        for finding in findings
    )


def test_i6_detects_missing_population_key():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
    ]

    populations = {
        "test_population_v1": [
            ("test", "1.0", "sub-01"),
        ]
    }

    metrics = [
        {
            "metric_name": "accuracy",
            "split": "test",
            "numerator": 1,
            "denominator": 1,
        }
    ]

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics,
        populations,
    )

    assert any(
        finding.rule_id == "I6.missing_population_key"
        for finding in findings
    )


def test_i6_detects_invalid_numerator_denominator_relationship():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
    ]

    populations = {
        "test_population_v1": [
            ("test", "1.0", "sub-01"),
        ]
    }

    metrics = [
        {
            "metric_name": "accuracy",
            "split": "test",
            "numerator": 2,
            "denominator": 1,
            "population_key": "test_population_v1",
        }
    ]

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics,
        populations,
    )

    assert any(
        finding.rule_id == "I6.invalid_numerator"
        for finding in findings
    )


def test_i6_detects_nonpositive_denominator():
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
            split="test",
        ),
    ]

    populations = {
        "test_population_v1": [
            ("test", "1.0", "sub-01"),
        ]
    }

    metrics = [
        {
            "metric_name": "accuracy",
            "split": "test",
            "numerator": 0,
            "denominator": 0,
            "population_key": "test_population_v1",
        }
    ]

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics,
        populations,
    )

    assert any(
        finding.rule_id == "I6.invalid_denominator"
        for finding in findings
    )


import pytest


@pytest.mark.parametrize("denominator", ["2", 2.5, True, False, None])
def test_i6_rejects_invalid_denominator_types(denominator):
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
        )
    ]
    populations = {
        "test_population_v1": [("test", "1.0", "sub-01")]
    }
    metrics = [{
        "metric_name": "accuracy",
        "numerator": 0,
        "denominator": denominator,
        "population_key": "test_population_v1",
    }]

    findings = check_i6_metric_denominator_traceability(
        records, metrics, populations
    )

    assert any(
        finding.rule_id == "I6.invalid_denominator"
        for finding in findings
    )


@pytest.mark.parametrize("numerator", ["0", 0.5, True, False, None])
def test_i6_rejects_invalid_numerator_types(numerator):
    records = [
        ManifestRecord(
            dataset_namespace="test",
            dataset_version="1.0",
            participant_id="sub-01",
        )
    ]
    populations = {
        "test_population_v1": [("test", "1.0", "sub-01")]
    }
    metrics = [{
        "metric_name": "accuracy",
        "numerator": numerator,
        "denominator": 1,
        "population_key": "test_population_v1",
    }]

    findings = check_i6_metric_denominator_traceability(
        records, metrics, populations
    )

    assert any(
        finding.rule_id == "I6.invalid_numerator"
        for finding in findings
    )

@pytest.mark.parametrize(
    "participant_id",
    ["", "  ", "sub", "sub-", "sub_"],
)
def test_canonicalize_participant_id_rejects_empty_canonical_labels(
    participant_id,
):
    with pytest.raises(ValueError, match="nonempty label"):
        canonicalize_participant_id(participant_id)


def test_canonicalize_participant_id_preserves_existing_separator_convention():
    assert canonicalize_participant_id("sub--01") == "sub-1"
    assert canonicalize_participant_id("sub 01") == "sub-1"
    assert canonicalize_participant_id("sub-A01") == "sub-a01"


def test_i1_acquisition_key_injectivity_ignores_missing_source_paths():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path=None,
        source_sha256=None,
    )
    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path=None,
        source_sha256=None,
    )

    assert check_i1_acquisition_key_injectivity([record_1, record_2]) == []


def test_i1_acquisition_key_injectivity_accepts_missing_hash_for_same_path():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/func/sub-01_bold.nii.gz",
        source_sha256="not_retrieved",
    )
    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/func/sub-01_bold.nii.gz",
        source_sha256="abc123",
    )

    assert check_i1_acquisition_key_injectivity([record_1, record_2]) == []

def test_i1_acquisition_key_injectivity_detects_conflicting_retrieved_hashes():
    record_1 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/func/sub-01_bold.nii.gz",
        source_sha256="abc123",
    )
    record_2 = ManifestRecord(
        dataset_namespace="ds000117",
        dataset_version="1.1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01/func/sub-01_bold.nii.gz",
        source_sha256="def456",
    )

    findings = check_i1_acquisition_key_injectivity([record_1, record_2])

    assert len(findings) == 1
    assert findings[0].rule_id == "I1.acquisition_key_injectivity"
    assert "conflicting retrieved hashes" in findings[0].message
