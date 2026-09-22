from __future__ import annotations

from typing import Any

from .identity import Finding

def check_i4_identical_source_hashes_under_different_keys(
    records: list[Any],
) -> list[Finding]:
    """Report identical source hashes occurring under different keys."""
    grouped: dict[str, list[Any]] = {}

    for record in records:
        file_hash = record.source_sha256

        if not file_hash or file_hash == "not_retrieved":
            continue

        grouped.setdefault(file_hash, []).append(record)

    findings: list[Finding] = []

    for file_hash, matching_records in grouped.items():
        keys = {record.acquisition_key for record in matching_records}

        if len(keys) <= 1:
            continue

        affected_keys = tuple(sorted(keys, key=str))

        evidence_rows = tuple(
            {
                "acquisition_key": record.acquisition_key,
                "source_path": record.source_path,
                "source_sha256": record.source_sha256,
            }
            for record in matching_records
        )

        findings.append(
            Finding(
                rule_id="I4.identical_source_hash_different_keys",
                severity="ERROR",
                message="Identical source file hash occurs under different acquisition keys.",
                key_type="acquisition_key",
                affected_keys=affected_keys,
                expected="identical source hashes are not silently associated with different acquisition keys",
                observed=f"{len(affected_keys)} distinct acquisition keys share source hash {file_hash}",
                evidence_rows=evidence_rows,
                remediation=(
                    "Inspect the records sharing the source hash and determine "
                    "whether the repeated source file is intentional or indicates "
                    "an identity/key error."
                ),
            )
        )

    return findings

def check_i4_identical_derivative_hashes_under_different_keys(
    records: list[Any],
) -> list[Finding]:
    """Report identical derivative hashes occurring under different keys."""
    grouped: dict[str, list[Any]] = {}

    for record in records:
        file_hash = record.derivative_sha256

        if not file_hash or file_hash == "not_retrieved":
            continue

        grouped.setdefault(file_hash, []).append(record)

    findings: list[Finding] = []

    for file_hash, matching_records in grouped.items():
        keys = {record.acquisition_key for record in matching_records}

        if len(keys) <= 1:
            continue

        affected_keys = tuple(sorted(keys, key=str))

        evidence_rows = tuple(
            {
                "acquisition_key": record.acquisition_key,
                "derivative_path": record.derivative_path,
                "derivative_sha256": record.derivative_sha256,
            }
            for record in matching_records
        )

        findings.append(
            Finding(
                rule_id="I4.identical_derivative_hash_different_keys",
                severity="ERROR",
                message="Identical derivative file hash occurs under different acquisition keys.",
                key_type="acquisition_key",
                affected_keys=affected_keys,
                expected="identical derivative hashes are not silently associated with different acquisition keys",
                observed=f"{len(affected_keys)} distinct acquisition keys share derivative hash {file_hash}",
                evidence_rows=evidence_rows,
                remediation=(
                    "Inspect the derivative records sharing the hash and verify "
                    "their declared provenance and output identity."
                ),
            )
        )

    return findings


def check_i4_repeated_paths_or_rows(
    records: list[Any],
) -> list[Finding]:
    """
    Report repeated source paths and exact repeated rows.

    Repeated paths/rows must not silently be counted as independent
    observations.
    """
    path_groups: dict[str, list[int]] = {}
    row_groups: dict[Any, list[int]] = {}

    for index, record in enumerate(records):
        if record.source_path:
            path_groups.setdefault(record.source_path, []).append(index)

        row_groups.setdefault(record, []).append(index)

    findings: list[Finding] = []

    repeated_paths = {
        path: indices
        for path, indices in path_groups.items()
        if len(indices) > 1
    }

    if repeated_paths:
        affected_keys = tuple(
            sorted(
                {
                    records[index].acquisition_key
                    for indices in repeated_paths.values()
                    for index in indices
                },
                key=str,
            )
        )

        evidence_rows = tuple(
            {
                "source_path": path,
                "row_indices": tuple(indices),
            }
            for path, indices in sorted(repeated_paths.items())
        )

        findings.append(
            Finding(
                rule_id="I4.repeated_source_path",
                severity="ERROR",
                message="A source path occurs in multiple manifest rows.",
                key_type="acquisition_key",
                affected_keys=affected_keys,
                expected="each source path occurs once unless explicitly represented by a declared relation",
                observed=f"{len(repeated_paths)} repeated source paths",
                evidence_rows=evidence_rows,
                remediation=(
                    "Inspect repeated source paths and verify whether the rows "
                    "represent an intentional declared relation or duplicated observations."
                ),
            )
        )

    repeated_rows = {
        record: indices
        for record, indices in row_groups.items()
        if len(indices) > 1
    }

    if repeated_rows:
        affected_keys = tuple(
            sorted(
                {
                    record.acquisition_key
                    for record in repeated_rows
                },
                key=str,
            )
        )

        evidence_rows = tuple(
            {
                "row_indices": tuple(indices),
                "acquisition_key": record.acquisition_key,
                "source_path": record.source_path,
            }
            for record, indices in repeated_rows.items()
        )

        findings.append(
            Finding(
                rule_id="I4.repeated_row",
                severity="ERROR",
                message="An identical manifest row occurs multiple times.",
                key_type="acquisition_key",
                affected_keys=affected_keys,
                expected="identical manifest rows are not silently counted as independent observations",
                observed=f"{len(repeated_rows)} repeated rows",
                evidence_rows=evidence_rows,
                remediation=(
                    "Remove unintended duplicate rows or explicitly document "
                    "the declared relation that makes the repetition valid."
                ),
            )
        )

    return findings