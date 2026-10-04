from pathlib import Path

import pytest

from neurofusion_qa.identity import Finding
from neurofusion_qa.reporting import AuditReport


def make_finding(
    *,
    rule_id: str = "I1.test_rule",
    severity: str = "ERROR",
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message="Test finding",
        key_type="person_key",
        affected_keys=(("dataset", "1.0", "sub-01"),),
        expected="clean",
        observed="violation",
        evidence_rows=(1, 2),
        remediation="Review the implicated records.",
    )


def test_empty_report_summary():
    report = AuditReport(findings=())

    assert report.total_findings == 0
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.info_count == 0
    assert report.has_errors is False


def test_summary_counts_findings_by_severity():
    report = AuditReport(
        findings=(
            make_finding(severity="ERROR"),
            make_finding(
                rule_id="I2.test_rule",
                severity="WARNING",
            ),
            make_finding(
                rule_id="I3.test_rule",
                severity="INFO",
            ),
        )
    )

    assert report.summary() == {
        "total_findings": 3,
        "errors": 1,
        "warnings": 1,
        "infos": 1,
    }


def test_to_dict_preserves_finding_fields():
    finding = make_finding()

    report = AuditReport(
        findings=(finding,),
        manifest_hash="manifest-hash",
        config_hash="config-hash",
        code_hash="code-hash",
        generated_at="2026-10-04T00:00:00+00:00",
    )

    payload = report.to_dict()

    assert payload["report_version"] == "1.0"
    assert payload["generated_at"] == "2026-10-04T00:00:00+00:00"

    assert payload["provenance"] == {
        "manifest_sha256": "manifest-hash",
        "config_sha256": "config-hash",
        "code_hash": "code-hash",
    }

    assert payload["summary"]["errors"] == 1

    serialized_finding = payload["findings"][0]

    assert serialized_finding["rule_id"] == "I1.test_rule"
    assert serialized_finding["severity"] == "ERROR"
    assert serialized_finding["affected_keys"] == [
        ["dataset", "1.0", "sub-01"]
    ]
    assert serialized_finding["evidence_rows"] == [1, 2]


def test_json_is_valid_and_deterministic():
    report = AuditReport(
        findings=(make_finding(),),
        generated_at="2026-10-04T00:00:00+00:00",
    )

    first = report.to_json()
    second = report.to_json()

    assert first == second

    import json

    parsed = json.loads(first)

    assert parsed["summary"]["total_findings"] == 1
    assert parsed["findings"][0]["rule_id"] == "I1.test_rule"


def test_write_json_creates_report(tmp_path: Path):
    report = AuditReport(
        findings=(make_finding(),),
        generated_at="2026-10-04T00:00:00+00:00",
    )

    output = tmp_path / "reports" / "audit.json"

    report.write_json(output)

    assert output.exists()

    import json

    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["findings"][0]["rule_id"] == "I1.test_rule"


def test_tsv_contains_one_row_per_finding():
    report = AuditReport(
        findings=(
            make_finding(),
            make_finding(
                rule_id="I2.test_rule",
                severity="WARNING",
            ),
        )
    )

    tsv = report.to_tsv()
    lines = tsv.strip().splitlines()

    assert len(lines) == 3

    assert lines[0].split("\t") == [
        "rule_id",
        "severity",
        "message",
        "key_type",
        "affected_keys",
        "expected",
        "observed",
        "evidence_rows",
        "remediation",
    ]

    assert "I1.test_rule" in lines[1]
    assert "I2.test_rule" in lines[2]


def test_markdown_contains_summary_and_findings():
    report = AuditReport(
        findings=(make_finding(),),
        generated_at="2026-10-04T00:00:00+00:00",
    )

    markdown = report.to_markdown()

    assert "# IdentityGuard-BIDS Audit Report" in markdown
    assert "## Summary" in markdown
    assert "## Findings" in markdown
    assert "I1.test_rule" in markdown
    assert "Test finding" in markdown


def test_raise_for_errors_does_nothing_for_clean_report():
    report = AuditReport(findings=())

    report.raise_for_errors()


def test_raise_for_errors_raises_for_error():
    report = AuditReport(
        findings=(make_finding(severity="ERROR"),)
    )

    with pytest.raises(RuntimeError, match="I1.test_rule"):
        report.raise_for_errors()


def test_warnings_do_not_raise():
    report = AuditReport(
        findings=(
            make_finding(
                rule_id="I2.warning",
                severity="WARNING",
            ),
        )
    )

    report.raise_for_errors()

def test_json_normalizes_nested_structured_values():
    finding = Finding(
        rule_id="I4.test_rule",
        severity="ERROR",
        message="Nested structured evidence",
        key_type="acquisition_key",
        affected_keys=(
            ("dataset", "1.0", "sub-01"),
            ("dataset", "1.0", "sub-02"),
        ),
        expected={"paths": {Path("a/b.nii.gz")}},
        observed={
            "details": {
                "source": Path("c/d.nii.gz"),
                "values": (1, 2, 3),
            }
        },
        evidence_rows=({"row": 1}, {"row": 2}),
        remediation="Inspect the duplicated source.",
    )

    report = AuditReport(findings=(finding,))

    payload = report.to_dict()
    serialized = payload["findings"][0]

    assert serialized["affected_keys"] == [
        ["dataset", "1.0", "sub-01"],
        ["dataset", "1.0", "sub-02"],
    ]

    assert serialized["observed"]["details"]["source"] == "c/d.nii.gz"
    assert serialized["observed"]["details"]["values"] == [1, 2, 3]
    assert serialized["evidence_rows"] == [
        {"row": 1},
        {"row": 2},
    ]

    assert serialized["expected"]["paths"] == ["a/b.nii.gz"]


def test_tsv_escapes_tabs_and_newlines():
    finding = Finding(
        rule_id="I1.special_chars",
        severity="ERROR",
        message="Message with\ttab and\nnewline",
        key_type="person_key",
        affected_keys=(("sub-01",),),
        expected="expected",
        observed="observed",
        evidence_rows=(),
        remediation="Fix\tthis\nrecord.",
    )

    report = AuditReport(findings=(finding,))

    tsv = report.to_tsv()

    lines = tsv.strip().splitlines()

    assert len(lines) == 2
    assert "\\t" in lines[1]
    assert "\\n" in lines[1]


def test_markdown_escapes_table_pipes():
    finding = Finding(
        rule_id="I1.pipe_rule",
        severity="WARNING",
        message="A | B",
        key_type="person_key",
        affected_keys=(("sub-01",),),
        expected="A",
        observed="B",
        evidence_rows=(),
        remediation="Check A | B.",
    )

    report = AuditReport(findings=(finding,))

    markdown = report.to_markdown()

    assert "A \\| B" in markdown

from neurofusion_qa.manifest import ManifestRecord
from neurofusion_qa.reporting import audit_manifest

def make_clean_record(
    participant_id: str = "sub-01",
    *,
    modality: str = "T1w",
    split: str | None = "train",
) -> ManifestRecord:
    return ManifestRecord(
        dataset_namespace="test",
        dataset_version="1.0",
        participant_id=participant_id,
        session_id="ses-01",
        modality=modality,
        source_path=f"{participant_id}_{modality}.nii.gz",
        source_sha256=f"hash-{participant_id}-{modality}",
        split=split,
    )


def test_audit_manifest_runs_manifest_based_invariants():
    records = [
        make_clean_record("sub-01", modality="T1w"),
        make_clean_record("sub-01", modality="bold"),
    ]

    report = audit_manifest(records)

    assert isinstance(report, AuditReport)
    assert report.total_findings == 0


def test_audit_manifest_reports_i1_failure():
    records = [
        ManifestRecord(
            dataset_namespace="",
            dataset_version="1.0",
            participant_id="sub-01",
            source_path="sub-01_T1w.nii.gz",
        )
    ]

    report = audit_manifest(records)

    assert report.has_errors
    assert any(
        finding.rule_id == "I1.namespace_completeness"
        for finding in report.findings
    )


def test_audit_manifest_requires_both_i6_inputs():
    records = [
        make_clean_record()
    ]

    with pytest.raises(
        ValueError,
        match="I6 requires both metrics and populations",
    ):
        audit_manifest(
            records,
            metrics=[],
        )


def test_audit_manifest_does_not_infer_i2_i3_or_i6():
    records = [
        make_clean_record("sub-01", modality="T1w"),
        make_clean_record("sub-02", modality="bold"),
    ]

    report = audit_manifest(records)

    rule_ids = {
        finding.rule_id
        for finding in report.findings
    }

    assert not any(rule_id.startswith("I2.") for rule_id in rule_ids)
    assert not any(rule_id.startswith("I3.") for rule_id in rule_ids)
    assert not any(rule_id.startswith("I6.") for rule_id in rule_ids)

def test_audit_manifest_runs_i2_when_join_check_is_supplied():
    records = [
        make_clean_record("sub-01"),
    ]

    report = audit_manifest(
        records,
        join_checks=[
            {
                "left_counts": {
                    ("test", "1.0", "sub-01"): 2,
                },
                "right_counts": {
                    ("test", "1.0", "sub-01"): 1,
                },
                "relation": "one_to_one",
            }
        ],
    )

    assert any(
        finding.rule_id == "I2.cardinality_mismatch"
        for finding in report.findings
    )

def test_audit_manifest_runs_i3_when_pairs_are_supplied():
    left = make_clean_record(
        "sub-01",
        modality="T1w",
    )

    right = make_clean_record(
        "sub-02",
        modality="bold",
    )

    report = audit_manifest(
        [left, right],
        cross_modal_pairs=[
            (left, right),
        ],
    )

    assert any(
        finding.rule_id == "I3.person_pairing"
        for finding in report.findings
    )

def test_audit_manifest_runs_i6_when_metrics_and_populations_are_supplied():
    record = make_clean_record("sub-01")

    population_key = "test_population"

    population = {
        population_key: {
            record.person_key,
        }
    }

    metrics = [
        {
            "metric_id": "accuracy",
            "population_key": population_key,
            "numerator": 1,
            "denominator": 1,
        }
    ]

    report = audit_manifest(
        [record],
        metrics=metrics,
        populations=population,
    )

    assert not any(
        finding.rule_id.startswith("I6.")
        for finding in report.findings
    )