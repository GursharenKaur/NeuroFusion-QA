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

def check_i1_acquisition_key_injectivity(
    records: list[Any],
) -> list[Finding]:
    """
    Check I1 acquisition-key injectivity.

    One canonical acquisition key must not map to multiple distinct
    source file/hash identities.
    """
    grouped: dict[Any, set[tuple[Any, Any]]] = {}

    for record in records:
        acquisition_key = record.acquisition_key
        source_identity = (
            record.source_path,
            record.source_sha256,
        )

        grouped.setdefault(acquisition_key, set()).add(source_identity)

    findings: list[Finding] = []

    for acquisition_key, source_identities in grouped.items():
        if len(source_identities) <= 1:
            continue

        evidence_rows = tuple(
            {
                "acquisition_key": acquisition_key,
                "source_path": source_path,
                "source_sha256": source_sha256,
            }
            for source_path, source_sha256 in sorted(
                source_identities,
                key=lambda identity: (
                    identity[0] or "",
                    identity[1] or "",
                ),
            )
        )

        findings.append(
            Finding(
                rule_id="I1.acquisition_key_injectivity",
                severity="ERROR",
                message=(
                    "One acquisition key maps to multiple distinct "
                    "source file/hash identities."
                ),
                key_type="acquisition_key",
                affected_keys=(acquisition_key,),
                expected=(
                    "each acquisition_key maps to at most one "
                    "distinct source file/hash identity"
                ),
                observed=(
                    f"{len(source_identities)} distinct "
                    "source file/hash identities"
                ),
                evidence_rows=evidence_rows,
                remediation=(
                    "Inspect the conflicting source records and verify "
                    "the participant, session, modality, task, acquisition, "
                    "and run identifiers against authoritative source metadata."
                ),
            )
        )

    return findings