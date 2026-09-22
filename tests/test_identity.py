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