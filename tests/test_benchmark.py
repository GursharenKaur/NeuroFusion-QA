from neurofusion_qa.benchmark import (
    build_synthetic_manifest,
    build_synthetic_cross_modal_pairs,
    evaluate_benchmark_findings,
)

def test_synthetic_manifest_record_count():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    assert len(records) == 16 * 2 * 1 * 1


def test_synthetic_manifest_has_expected_people():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    person_keys = {record.person_key for record in records}

    assert len(person_keys) == 16


def test_synthetic_manifest_is_deterministic():
    first = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=2,
    )

    second = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=2,
    )

    assert first == second


def test_synthetic_manifest_keeps_person_records_in_one_split():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=2,
    )

    splits_by_person = {}

    for record in records:
        splits_by_person.setdefault(record.person_key, set()).add(record.split)

    assert all(len(splits) == 1 for splits in splits_by_person.values())


def test_synthetic_manifest_acquisition_keys_are_unique():
    records = build_synthetic_manifest(
        people=16,
        modalities=3,
        sessions=2,
        runs_per_modality=4,
    )

    acquisition_keys = [record.acquisition_key for record in records]

    assert len(acquisition_keys) == len(set(acquisition_keys))


def test_synthetic_manifest_has_deterministic_provenance():
    records = build_synthetic_manifest(
        people=4,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    assert all(record.source_sha256 is not None for record in records)
    assert all(len(record.source_sha256) == 64 for record in records)

    assert all(record.derivative_sha256 is not None for record in records)
    assert all(len(record.derivative_sha256) == 64 for record in records)

    assert len({record.source_sha256 for record in records}) == len(records)

from neurofusion_qa.identity import Finding
from neurofusion_qa.benchmark import evaluate_benchmark_findings


def test_benchmark_evaluation_detects_expected_rule_and_key():
    affected_key = (
        "synthetic:identityguard",
        "1.0",
        "sub-00001",
    )

    findings = [
        Finding(
            rule_id="I1.namespace_completeness",
            severity="ERROR",
            message="Missing namespace.",
            key_type="person_key",
            affected_keys=(affected_key,),
            expected="present",
            observed=None,
            evidence_rows=(0,),
            remediation="Restore dataset namespace.",
        )
    ]

    truth = {
        "expected_violations": [
            "I1.namespace_completeness",
        ],
        "affected_keys": [
            affected_key,
        ],
    }

    evaluation = evaluate_benchmark_findings(
        findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.expected_violation_count == 1
    assert evaluation.detected_expected_violation_count == 1
    assert evaluation.affected_key_count == 1
    assert evaluation.localized_key_count == 1
    assert evaluation.localization_true_positives == 1
    assert evaluation.localization_false_positives == 0
    assert evaluation.failure_type_correct is True


def test_benchmark_evaluation_detects_localization_false_positive():
    affected_key = (
        "synthetic:identityguard",
        "1.0",
        "sub-00001",
    )

    unrelated_key = (
        "synthetic:identityguard",
        "1.0",
        "sub-00002",
    )

    findings = [
        Finding(
            rule_id="I1.namespace_completeness",
            severity="ERROR",
            message="Missing namespace.",
            key_type="person_key",
            affected_keys=(unrelated_key,),
            expected="present",
            observed=None,
            evidence_rows=(1,),
            remediation="Restore dataset namespace.",
        )
    ]

    truth = {
        "expected_violations": [
            "I1.namespace_completeness",
        ],
        "affected_keys": [
            affected_key,
        ],
    }

    evaluation = evaluate_benchmark_findings(
        findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.localization_true_positives == 0
    assert evaluation.localization_false_positives == 1
    assert evaluation.failure_type_correct is True


def test_benchmark_evaluation_handles_clean_control():
    findings = []

    truth = {
        "corruption": "C0_clean",
        "expected_violations": [],
        "affected_keys": [],
    }

    evaluation = evaluate_benchmark_findings(
        findings,
        truth,
    )

    assert evaluation.detected is False
    assert evaluation.expected_violation_detected is False
    assert evaluation.expected_violation_count == 0
    assert evaluation.detected_expected_violation_count == 0
    assert evaluation.affected_key_count == 0
    assert evaluation.localized_key_count == 0
    assert evaluation.localization_true_positives == 0
    assert evaluation.localization_false_positives == 0
    assert evaluation.failure_type_correct is False

from neurofusion_qa.corruptions import inject_corruption
from neurofusion_qa.reporting import audit_manifest


def test_single_c1_benchmark_integration():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted_records, truth = inject_corruption(
        clean_records,
        corruption="C1_namespace_stripping",
        affected_count=1,
        seed=20270915,
    )

    cross_modal_pairs = build_synthetic_cross_modal_pairs(
        corrupted_records
    )

    report = audit_manifest(
        corrupted_records,
        cross_modal_pairs=cross_modal_pairs,
    )

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert truth["corruption"] == "C1_namespace_stripping"
    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.failure_type_correct is True

def test_benchmark_evaluation_localizes_identity_changing_corruption():
    affected_key = (
        "synthetic:identityguard",
        "1.0",
        "sub-00010",
    )

    corrupted_key = (
        None,
        "1.0",
        "sub-00010",
    )

    findings = [
        Finding(
            rule_id="I1.namespace_completeness",
            severity="ERROR",
            message="Missing namespace.",
            key_type="person_key",
            affected_keys=(corrupted_key,),
            expected="present",
            observed=None,
            evidence_rows=(
                {
                    "row_index": 18,
                    "missing_fields": ("dataset_namespace",),
                },
            ),
            remediation="Restore dataset namespace.",
        )
    ]

    truth = {
        "corruption": "C1_namespace_stripping",
        "operations": [
            {
                "operation": "remove_dataset_namespace",
                "row_index": 18,
            }
        ],
        "expected_violations": [
            "I1.namespace_completeness",
        ],
        "affected_keys": [
            affected_key,
        ],
    }

    evaluation = evaluate_benchmark_findings(
        findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.localization_true_positives == 1
    assert evaluation.localization_false_positives == 0
    assert evaluation.failure_type_correct is True