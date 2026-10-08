from neurofusion_qa.benchmark import (
    build_synthetic_cross_modal_join_check,
    build_synthetic_cross_modal_pairs,
    build_synthetic_manifest,
    evaluate_benchmark_findings,
    build_synthetic_metric_evidence,
    build_synthetic_cross_modal_pairs_from_clean,
    affected_count_for_severity,
    generate_benchmark_jobs,
)
import pytest

from neurofusion_qa.corruptions import inject_corruption
from neurofusion_qa.reporting import audit_manifest

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

def test_synthetic_cross_modal_join_check_is_one_to_one():
    records = build_synthetic_manifest(
        people=4,
        modalities=2,
        sessions=2,
        runs_per_modality=4,
    )

    join_check = build_synthetic_cross_modal_join_check(records)

    assert join_check["relation"] == "one_to_one"
    assert set(join_check["left_counts"]) == set(
        join_check["right_counts"]
    )
    assert set(join_check["left_counts"].values()) == {1}
    assert set(join_check["right_counts"].values()) == {1}

def test_c2_produces_declared_i2_cardinality_violation():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted, truth = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    join_check = build_synthetic_cross_modal_join_check(corrupted)

    report = audit_manifest(
        corrupted,
        join_checks=[join_check],
    )

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert "I1.canonicalization_collision" in rule_ids
    assert "I2.cardinality_mismatch" in rule_ids

    # Downstream unmatched-key evidence is allowed, but it is not
    # part of C2's declared expected violation set.
    assert set(truth["expected_violations"]) == {
        "I1.canonicalization_collision",
        "I2.cardinality_mismatch",
    }

    assert "I2.many_to_many" not in rule_ids

def test_synthetic_cross_modal_join_check_supports_full_grid():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=4,
    )

    join_check = build_synthetic_cross_modal_join_check(records)

    assert len(join_check["left_counts"]) == 128
    assert len(join_check["right_counts"]) == 128
    assert set(join_check["left_counts"].values()) == {1}
    assert set(join_check["right_counts"].values()) == {1}

def test_c2_benchmark_localization_uses_target_row():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted_records, truth = inject_corruption(
        clean_records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    join_check = build_synthetic_cross_modal_join_check(
        corrupted_records,
    )

    report = audit_manifest(
        corrupted_records,
        join_checks=[join_check],
    )

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert truth["corruption"] == "C2_canonicalization_collision"

    assert "I1.canonicalization_collision" in {
        finding.rule_id
        for finding in report.findings
    }

    assert "I2.cardinality_mismatch" in {
        finding.rule_id
        for finding in report.findings
    }

    assert evaluation.expected_violation_detected is True
    assert evaluation.failure_type_correct is True

    assert evaluation.localization_true_positives >= 1

def test_c3_produces_i2_i4_and_i6_benchmark_findings():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted_records, truth = inject_corruption(
        clean_records,
        corruption="C3_duplicate_propagation",
        affected_count=1,
        seed=20270915,
    )

    join_check = build_synthetic_cross_modal_join_check(
        corrupted_records
    )

    clean_population = {
        record.person_key
        for record in clean_records
    }

    metrics, populations = build_synthetic_metric_evidence(
        corrupted_records,
        denominator_override=len(clean_population) + 1,
    )

    report = audit_manifest(
        corrupted_records,
        join_checks=[join_check],
        metrics=metrics,
        populations=populations,
    )

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert "I2.cardinality_mismatch" in rule_ids
    assert "I4.repeated_row" in rule_ids
    assert "I4.repeated_source_path" in rule_ids
    assert "I6.denominator_mismatch" in rule_ids

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.failure_type_correct is True

def test_c4_produces_i3_person_pairing_finding():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted_records, truth = inject_corruption(
        clean_records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    cross_modal_pairs = build_synthetic_cross_modal_pairs_from_clean(
        clean_records,
        corrupted_records,
    )

    report = audit_manifest(
        corrupted_records,
        cross_modal_pairs=cross_modal_pairs,
    )

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert "I3.person_pairing" in rule_ids

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.failure_type_correct is True

def test_c5_produces_i5_person_split_leakage_finding():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted_records, truth = inject_corruption(
        clean_records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    report = audit_manifest(
        corrupted_records,
    )

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert "I5.person_split_leakage" in rule_ids

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.failure_type_correct is True

def test_c6_produces_i6_denominator_mismatch_finding():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    clean_metrics, populations = build_synthetic_metric_evidence(
        clean_records,
    )

    corrupted_metrics, truth = inject_corruption(
        clean_records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=clean_metrics,
        populations=populations,
    )

    report = audit_manifest(
        clean_records,
        metrics=corrupted_metrics,
        populations=populations,
    )

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert "I6.denominator_mismatch" in rule_ids

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.failure_type_correct is True

def test_c6_supports_multiple_affected_person_metrics():
    clean_records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    clean_metrics, populations = build_synthetic_metric_evidence(
        clean_records
    )

    corrupted_metrics, truth = inject_corruption(
        clean_records,
        corruption="C6_denominator_mismatch",
        affected_count=4,
        seed=20270915,
        metrics=clean_metrics,
        populations=populations,
    )

    report = audit_manifest(
        clean_records,
        metrics=corrupted_metrics,
        populations=populations,
    )

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert "I6.denominator_mismatch" in rule_ids

    evaluation = evaluate_benchmark_findings(
        report.findings,
        truth,
    )

    assert evaluation.detected is True
    assert evaluation.expected_violation_detected is True
    assert evaluation.expected_violation_count == 1
    assert evaluation.detected_expected_violation_count == 1
    assert evaluation.affected_key_count == 4
    assert evaluation.localized_key_count == 4
    assert evaluation.localization_true_positives == 4
    assert evaluation.localization_false_positives == 0
    assert evaluation.failure_type_correct is True

def test_affected_count_for_severity_16_people():
    assert affected_count_for_severity(16, 0.01) == 1
    assert affected_count_for_severity(16, 0.05) == 1
    assert affected_count_for_severity(16, 0.10) == 2
    assert affected_count_for_severity(16, 0.25) == 4


def test_affected_count_for_severity_64_people():
    assert affected_count_for_severity(64, 0.01) == 1
    assert affected_count_for_severity(64, 0.05) == 4
    assert affected_count_for_severity(64, 0.10) == 7
    assert affected_count_for_severity(64, 0.25) == 16


def test_affected_count_for_severity_rejects_invalid_input():
    with pytest.raises(ValueError):
        affected_count_for_severity(0, 0.10)

    with pytest.raises(ValueError):
        affected_count_for_severity(16, 0.0)

    with pytest.raises(ValueError):
        affected_count_for_severity(16, 1.01)

def test_generate_benchmark_jobs_has_expected_factorial_size():
    jobs = generate_benchmark_jobs()

    # 5 people × 2 modalities × 2 sessions × 2 runs
    # × 6 corruptions × 4 severities × 100 seeds
    # = 96,000 jobs.
    assert len(jobs) == 96000


def test_generate_benchmark_jobs_uses_protocol_severity_counts():
    jobs = generate_benchmark_jobs(
        people=(16,),
        modalities=(2,),
        sessions=(1,),
        runs_per_modality=(1,),
        corruptions=("C6_denominator_mismatch",),
        severities=(0.01, 0.05, 0.10, 0.25),
        seeds=(0,),
    )

    counts = {
        job.severity: job.affected_count
        for job in jobs
    }

    assert counts == {
        0.01: 1,
        0.05: 1,
        0.10: 2,
        0.25: 4,
    }


def test_generate_benchmark_jobs_is_deterministic():
    kwargs = {
        "people": (16, 64),
        "modalities": (2,),
        "sessions": (1,),
        "runs_per_modality": (1,),
        "corruptions": ("C1_namespace_stripping",),
        "severities": (0.01, 0.25),
        "seeds": (0, 1),
    }

    first = generate_benchmark_jobs(**kwargs)
    second = generate_benchmark_jobs(**kwargs)

    assert first == second