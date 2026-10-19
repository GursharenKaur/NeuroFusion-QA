from __future__ import annotations

from collections import defaultdict
from typing import Any

from .identity import Finding

def _normalized_split(value: Any) -> str | None:
    """Return a trimmed split label, or None if it is missing/blank."""
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def _usable_hash(value: Any) -> str | None:
    """Return a usable hash value, excluding missing and unavailable values."""
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized or normalized == "not_retrieved":
        return None

    return normalized

def check_i5_person_split_independence(
    records: list[Any],
) -> list[Finding]:
    """
    Check that every person key belongs to exactly one outer split.
    """
    grouped: dict[Any, set[str]] = defaultdict(set)

    for record in records:
        split = _normalized_split(record.split)
        if split is None:
            continue

        grouped[record.person_key].add(split)

    findings: list[Finding] = []

    for person_key, splits in grouped.items():
        if len(splits) <= 1:
            continue

        findings.append(
            Finding(
                rule_id="I5.person_split_independence",
                severity="ERROR",
                message="One person key appears in multiple outer splits.",
                key_type="person_key",
                affected_keys=(person_key,),
                expected="each person key belongs to exactly one outer split",
                observed=tuple(sorted(splits)),
                evidence_rows=tuple(
                    {
                        "person_key": record.person_key,
                        "split": record.split,
                        "source_path": record.source_path,
                    }
                    for record in records
                    if record.person_key == person_key
                    and record.split is not None
                ),
                remediation=(
                    "Assign all records belonging to the person key to one "
                    "outer split and verify the split assignment."
                ),
            )
        )

    return findings


def check_i5_source_hash_split_independence(
    records: list[Any],
) -> list[Finding]:
    """
    Check that a source hash does not occur across outer splits.
    """
    grouped: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for record in records:
        split = _normalized_split(record.split)
        source_hash = _usable_hash(record.source_sha256)

        if split is None or source_hash is None:
            continue

        grouped[source_hash][split].append(record)

    findings: list[Finding] = []

    for source_hash, split_records in grouped.items():
        if len(split_records) <= 1:
            continue

        affected_keys = tuple(
            sorted(
                {
                    record.acquisition_key
                    for records_for_split in split_records.values()
                    for record in records_for_split
                },
                key=str,
            )
        )

        evidence_rows = tuple(
            {
                "source_sha256": source_hash,
                "split": split,
                "acquisition_key": record.acquisition_key,
                "source_path": record.source_path,
            }
            for split, records_for_split in split_records.items()
            for record in records_for_split
        )

        findings.append(
            Finding(
                rule_id="I5.source_hash_split_independence",
                severity="ERROR",
                message="A source file hash appears across multiple outer splits.",
                key_type="acquisition_key",
                affected_keys=affected_keys,
                expected="a source hash occurs in at most one outer split",
                observed=tuple(sorted(split_records)),
                evidence_rows=evidence_rows,
                remediation=(
                    "Inspect the records sharing the source hash and ensure "
                    "the same source observation cannot cross outer splits."
                ),
            )
        )

    return findings


def check_i5_derivative_hash_split_independence(
    records: list[Any],
) -> list[Finding]:
    """
    Check that a derivative hash does not occur across outer splits.
    """
    grouped: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for record in records:
        split = _normalized_split(record.split)
        derivative_hash = _usable_hash(record.derivative_sha256)

        if split is None or derivative_hash is None:
            continue

        grouped[derivative_hash][split].append(record)

    findings: list[Finding] = []

    for derivative_hash, split_records in grouped.items():
        if len(split_records) <= 1:
            continue

        affected_keys = tuple(
            sorted(
                {
                    record.acquisition_key
                    for records_for_split in split_records.values()
                    for record in records_for_split
                },
                key=str,
            )
        )

        evidence_rows = tuple(
            {
                "derivative_sha256": derivative_hash,
                "split": split,
                "acquisition_key": record.acquisition_key,
                "derivative_path": record.derivative_path,
            }
            for split, records_for_split in split_records.items()
            for record in records_for_split
        )

        findings.append(
            Finding(
                rule_id="I5.derivative_hash_split_independence",
                severity="ERROR",
                message="A derivative file hash appears across multiple outer splits.",
                key_type="acquisition_key",
                affected_keys=affected_keys,
                expected="a derivative hash occurs in at most one outer split",
                observed=tuple(sorted(split_records)),
                evidence_rows=evidence_rows,
                remediation=(
                    "Inspect the derivative records sharing the hash and "
                    "ensure the same derived observation cannot cross outer splits."
                ),
            )
        )

    return findings