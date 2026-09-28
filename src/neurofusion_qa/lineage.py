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

def check_i4_derivative_lineage(
    records: list[Any],
) -> list[Finding]:
    """
    Validate derivative lineage completeness and derivative-key uniqueness.

    Implementation convention:
    derivative_key =
        (acquisition_key, derivative_recipe_sha256, derivative_path)

    The acquisition_key represents the declared parent acquisition.
    """

    findings: list[Finding] = []

    derivative_records = [
        record
        for record in records
        if record.derivative_path is not None
        or record.derivative_sha256 is not None
        or record.derivative_recipe_sha256 is not None
    ]

    # ---------------------------------------------------------
    # 1. Validate derivative lineage completeness.
    # ---------------------------------------------------------
    for record in derivative_records:
        missing_fields = []

        if not record.derivative_recipe_sha256:
            missing_fields.append("derivative_recipe_sha256")

        if not record.derivative_path:
            missing_fields.append("derivative_path")

        if missing_fields:
            findings.append(
                Finding(
                    rule_id="I4.derivative_lineage_incomplete",
                    severity="ERROR",
                    message=(
                        "Derivative record is missing required lineage fields."
                    ),
                    key_type="derivative_key",
                    affected_keys=(record.acquisition_key,),
                    expected=(
                        "every derivative has a recipe hash and "
                        "derivative output path"
                    ),
                    observed={
                        "missing_fields": tuple(missing_fields),
                        "derivative_path": record.derivative_path,
                        "derivative_recipe_sha256": (
                            record.derivative_recipe_sha256
                        ),
                    },
                    evidence_rows=(record,),
                    remediation=(
                        "Provide the derivative recipe/configuration hash "
                        "and derivative output path before treating the "
                        "derivative as a traceable analysis artifact."
                    ),
                )
            )

    # ---------------------------------------------------------
    # 2. Validate that the parent acquisition is identifiable.
    #
    # BIDS acquisition entities may legitimately be absent.
    # Therefore None in session/task/acquisition/run does not by
    # itself mean that parent lineage is missing.
    # ---------------------------------------------------------
    for record in derivative_records:
        required_parent_fields = {
            "dataset_namespace": record.dataset_namespace,
            "dataset_version": record.dataset_version,
            "participant_id": record.participant_id,
        }

        missing_parent_fields = tuple(
            field
            for field, value in required_parent_fields.items()
            if value is None or value == ""
        )

        if missing_parent_fields:
            findings.append(
                Finding(
                    rule_id="I4.missing_parent_acquisition",
                    severity="ERROR",
                    message=(
                        "Derivative record does not contain sufficient "
                        "information to identify its parent acquisition."
                    ),
                    key_type="acquisition_key",
                    affected_keys=(record.acquisition_key,),
                    expected=(
                        "a derivative has sufficient identity information "
                        "to identify its parent acquisition"
                    ),
                    observed={
                        "missing_parent_fields": missing_parent_fields,
                    },
                    evidence_rows=(record,),
                    remediation=(
                        "Restore the required parent identity identifiers "
                        "before treating the derivative as traceable."
                    ),
                )
            )

    # ---------------------------------------------------------
    # 3. Detect conflicting output hashes for the same
    #    declared derivative key.
    # ---------------------------------------------------------
    derivative_key_groups: dict[tuple[Any, ...], list[Any]] = {}

    for record in derivative_records:
        if not record.derivative_recipe_sha256:
            continue

        if not record.derivative_path:
            continue

        derivative_key = (
            record.acquisition_key,
            record.derivative_recipe_sha256,
            record.derivative_path,
        )

        derivative_key_groups.setdefault(
            derivative_key,
            [],
        ).append(record)

    for derivative_key, matching_records in derivative_key_groups.items():
        hashes = {
            record.derivative_sha256
            for record in matching_records
            if record.derivative_sha256
            and record.derivative_sha256 != "not_retrieved"
        }

        if len(hashes) <= 1:
            continue

        findings.append(
            Finding(
                rule_id="I4.derivative_key_collision",
                severity="ERROR",
                message=(
                    "One declared derivative key corresponds to multiple "
                    "different derivative file hashes."
                ),
                key_type="derivative_key",
                affected_keys=(derivative_key,),
                expected=(
                    "one derivative key resolves to at most one retrieved "
                    "derivative content hash"
                ),
                observed={
                    "distinct_derivative_hashes": tuple(sorted(hashes)),
                },
                evidence_rows=tuple(
                    {
                        "derivative_key": derivative_key,
                        "derivative_path": record.derivative_path,
                        "derivative_recipe_sha256": (
                            record.derivative_recipe_sha256
                        ),
                        "derivative_sha256": record.derivative_sha256,
                    }
                    for record in matching_records
                ),
                remediation=(
                    "Inspect the derivative recipe, output path, and "
                    "generated file hashes for an inconsistent or "
                    "overwritten derivative."
                ),
            )
        )

    return findings