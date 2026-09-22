from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    message: str
    key_type: str
    affected_keys: tuple[Any, ...]
    expected: Any
    observed: Any
    evidence_rows: tuple[Any, ...]
    remediation: str

def check_i1_namespace_completeness(
    records: list[Any],
) -> list[Finding]:
    """
    Check I1 namespace completeness.

    Namespace, version, and participant must be present.
    """
    findings: list[Finding] = []

    affected_keys: list[Any] = []
    evidence_rows: list[Any] = []

    for index, record in enumerate(records):
        missing_fields = []

        if not record.dataset_namespace:
            missing_fields.append("dataset_namespace")

        if not record.dataset_version:
            missing_fields.append("dataset_version")

        if not record.participant_id:
            missing_fields.append("participant_id")

        if missing_fields:
            affected_keys.append(record.person_key)
            evidence_rows.append(
                {
                    "row_index": index,
                    "missing_fields": tuple(missing_fields),
                }
            )

    if affected_keys:
        findings.append(
            Finding(
                rule_id="I1.namespace_completeness",
                severity="ERROR",
                message="Namespace, version, and participant must be present.",
                key_type="person_key",
                affected_keys=tuple(affected_keys),
                expected="dataset_namespace, dataset_version, and participant_id present",
                observed=f"{len(affected_keys)} affected records",
                evidence_rows=tuple(evidence_rows),
                remediation="Populate the required identity fields from authoritative BIDS metadata; do not infer missing namespace values.",
            )
        )

    return findings