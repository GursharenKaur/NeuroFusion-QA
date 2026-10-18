from dataclasses import dataclass
from datetime import date
import re
import unicodedata
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

    Implementation convention:
    - Records without a usable source path are excluded.
    - Distinct paths under one acquisition key are a conflict.
    - Distinct retrieved hashes for the same path are a conflict.
    - Missing hashes and "not_retrieved" are not content identities.
    - Evidence retains observed paths even when hashes are unavailable.
    """
    grouped: dict[
        Any, dict[str, dict[str, set[str]]]
    ] = {}
    observed_hashes: dict[Any, dict[str, set[str | None]]] = {}

    for record in records:
        source_path = record.source_path

        if (
            not isinstance(source_path, str)
            or not source_path.strip()
        ):
            continue

        acquisition_key = record.acquisition_key
        source_hash = record.source_sha256

        path_hashes = grouped.setdefault(
            acquisition_key, {}
        ).setdefault(source_path, set())

        observed_hashes.setdefault(
            acquisition_key, {}
        ).setdefault(source_path, set()).add(source_hash)

        if (
            isinstance(source_hash, str)
            and source_hash.strip()
            and source_hash != "not_retrieved"
        ):
            path_hashes.add(source_hash)

    findings: list[Finding] = []

    for acquisition_key, paths in grouped.items():
        conflicting_hash_paths = {
            source_path
            for source_path, hashes in paths.items()
            if len(hashes) > 1
        }

        if len(paths) <= 1 and not conflicting_hash_paths:
            continue

        evidence_rows = tuple(
            {
                "acquisition_key": acquisition_key,
                "source_path": source_path,
                "source_sha256": source_hash,
            }
            for source_path in sorted(paths)
            for source_hash in sorted(
                observed_hashes[acquisition_key][source_path],
                key=lambda value: (value is not None, value or ""),
            )
        )

        findings.append(
            Finding(
                rule_id="I1.acquisition_key_injectivity",
                severity="ERROR",
                message=(
                    "One acquisition key maps to multiple source paths "
                    "or conflicting retrieved hashes."
                ),
                key_type="acquisition_key",
                affected_keys=(acquisition_key,),
                expected=(
                    "each acquisition key maps to one source path "
                    "and at most one retrieved source hash"
                ),
                observed=(
                    f"{len(paths)} distinct source paths; "
                    f"{len(conflicting_hash_paths)} paths with "
                    "conflicting retrieved hashes"
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

def canonicalize_participant_id(participant_id: str) -> str:
    """
    Return the canonical audit representation of a participant ID.

    Implementation convention:
    - Unicode NFKC normalization
    - case folding
    - removal of the leading BIDS 'sub' prefix
    - common punctuation/separators treated equivalently
    - numeric labels have leading zeroes removed
    - canonical form is reconstructed as 'sub-<label>'

    Raises:
        ValueError: If the participant ID is empty or contains only
            the BIDS subject prefix and separators.

    The original participant_id is never modified.
    """
    normalized = unicodedata.normalize("NFKC", participant_id)
    normalized = normalized.casefold().strip()

    # Remove the BIDS subject prefix and one or more separators.
    label = re.sub(r"^sub[-_.\s]*", "", normalized)

    # Treat punctuation/separators as equivalent.
    label = re.sub(r"[-_.\s]+", "", label)

    if not label:
        raise ValueError(
            "Participant ID must contain a nonempty label after normalization."
        )

    # Numeric participant labels are canonicalized by numeric value.
    if label.isdigit():
        label = str(int(label))

    return f"sub-{label}"

def check_i1_canonicalization_collision(
    records: list[Any],
) -> list[Finding]:
    """
    Detect distinct raw participant IDs that collapse to the same
    canonical participant representation within one dataset namespace
    and dataset version.

    The raw participant IDs are preserved and reported as evidence.
    """
    grouped: dict[
        tuple[str, str, str],
        dict[str, list[tuple[int, Any]]],
    ] = {}

    for index, record in enumerate(records):
        if not record.dataset_namespace:
            continue

        if not record.dataset_version:
            continue

        if not record.participant_id:
            continue

        canonical_id = canonicalize_participant_id(
            record.participant_id
        )

        namespace_key = (
            record.dataset_namespace,
            record.dataset_version,
            canonical_id,
        )

        grouped.setdefault(namespace_key, {}).setdefault(
            record.participant_id,
            [],
        ).append((index, record))

    findings: list[Finding] = []

    for canonical_key, raw_groups in grouped.items():
        if len(raw_groups) <= 1:
            continue

        evidence_rows = []

        for raw_id in sorted(raw_groups):
            for row_index, record in raw_groups[raw_id]:
                evidence_rows.append(
                    {
                        "row_index": row_index,
                        "dataset_namespace": record.dataset_namespace,
                        "dataset_version": record.dataset_version,
                        "raw_participant_id": raw_id,
                        "canonical_participant_id": canonical_key[2],
                    }
                )

        person_keys = tuple(
            (
                canonical_key[0],
                canonical_key[1],
                raw_id,
            )
            for raw_id in sorted(raw_groups)
        )

        findings.append(
            Finding(
                rule_id="I1.canonicalization_collision",
                severity="ERROR",
                message=(
                    "Distinct raw participant IDs collapse to the same "
                    "canonical participant representation."
                ),
                key_type="person_key",
                affected_keys=person_keys,
                expected=(
                    "distinct raw participant IDs must remain distinct "
                    "after canonicalization"
                ),
                observed={
                    "canonical_participant_id": canonical_key[2],
                    "raw_participant_ids": tuple(sorted(raw_groups)),
                },
                evidence_rows=tuple(evidence_rows),
                remediation=(
                    "Inspect the raw participant labels and preserve them "
                    "as distinct identities unless an authoritative "
                    "crosswalk explicitly establishes equivalence."
                ),
            )
        )

    return findings

@dataclass(frozen=True)
class AuthoritativeCrosswalk:
    """
    Explicit cross-dataset identity crosswalk.

    Implementation convention:
    A crosswalk must carry provenance metadata and an explicit mapping
    between namespace-qualified person keys. IdentityGuard-BIDS never
    derives this mapping from participant-string similarity.
    """

    source: str
    version: str
    sha256: str
    approved_by: str
    approved_date: str
    mapping: dict[
        tuple[str, str, str],
        tuple[str, str, str],
    ]


def _session_task_compatible(
    left_value: Any,
    right_value: Any,
) -> bool:
    """
    Apply the IdentityGuard-BIDS session/task compatibility convention.

    Equal values are compatible.
    Two explicit nulls are compatible.
    A null paired with a value is incompatible.
    Different explicit values are incompatible.
    """
    if left_value is None and right_value is None:
        return True

    if left_value is None or right_value is None:
        return False

    return left_value == right_value

def _crosswalk_metadata_errors(
    crosswalk: AuthoritativeCrosswalk,
) -> list[str]:
    """Validate crosswalk provenance metadata and mapping structure."""
    errors: list[str] = []

    for field_name in (
        "source",
        "version",
        "approved_by",
    ):
        value = getattr(crosswalk, field_name, None)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field_name} must be a non-empty string")

    digest = getattr(crosswalk, "sha256", None)
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
    ):
        errors.append(
            "sha256 must contain exactly 64 hexadecimal characters"
        )

    approved_date = getattr(crosswalk, "approved_date", None)
    if (
        not isinstance(approved_date, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", approved_date) is None
    ):
        errors.append("approved_date must use YYYY-MM-DD format")
    else:
        try:
            date.fromisoformat(approved_date)
        except ValueError:
            errors.append("approved_date must be a valid calendar date")

    mapping = getattr(crosswalk, "mapping", None)
    if not isinstance(mapping, dict) or not mapping:
        errors.append("mapping must be a non-empty dictionary")
    else:
        for source_key, target_key in mapping.items():
            for label, person_key in (
                ("source", source_key),
                ("target", target_key),
            ):
                if (
                    not isinstance(person_key, tuple)
                    or len(person_key) != 3
                    or any(
                        not isinstance(part, str) or not part.strip()
                        for part in person_key
                    )
                ):
                    errors.append(
                        f"mapping {label} keys must be tuples of three "
                        "non-empty strings"
                    )
                    break

    return errors

def _crosswalk_maps_persons(
    left_key: tuple[str, str, str],
    right_key: tuple[str, str, str],
    crosswalk: AuthoritativeCrosswalk,
) -> bool:
    """Check a mapping only when crosswalk metadata is valid."""
    if _crosswalk_metadata_errors(crosswalk):
        return False

    mapped_right = crosswalk.mapping.get(left_key)
    return mapped_right == right_key

def check_i3_cross_modal_pairing(
    pairs: list[tuple[Any, Any]],
    *,
    crosswalk: AuthoritativeCrosswalk | None = None,
) -> list[Finding]:
    """
    Check explicit cross-modal record pairs.

    Rules:
    1. Records from the same dataset must have the same namespace-qualified
       person key.
    2. Cross-dataset identity requires an authoritative crosswalk.
    3. Session and task values must satisfy the explicit compatibility rule.
    4. A pair must contain two distinct modalities.

    The function does not infer pairings and does not use participant-string
    similarity to establish identity.
    """
    findings: list[Finding] = []
    crosswalk_errors = (
        _crosswalk_metadata_errors(crosswalk)
        if crosswalk is not None
        else []
    )

    if crosswalk_errors:
        findings.append(
            Finding(
                rule_id="I3.crosswalk_provenance",
                severity="ERROR",
                message="Authoritative crosswalk metadata is invalid.",
                key_type="crosswalk",
                affected_keys=(),
                expected=(
                    "non-empty provenance fields, a valid SHA-256 "
                    "digest format, an ISO approval date, and a valid mapping"
                ),
                observed={
                    "errors": crosswalk_errors,
                    "source": crosswalk.source,
                    "version": crosswalk.version,
                    "sha256": crosswalk.sha256,
                    "approved_by": crosswalk.approved_by,
                    "approved_date": crosswalk.approved_date,
                },
                evidence_rows=(),
                remediation=(
                    "Correct the crosswalk metadata and verify its digest "
                    "against the authoritative crosswalk artifact before "
                    "using it to establish cross-dataset identity."
                ),
            )
        )

    for pair_index, (left, right) in enumerate(pairs):
        left_key = left.person_key
        right_key = right.person_key

        evidence = {
            "pair_index": pair_index,
            "left_person_key": left_key,
            "right_person_key": right_key,
            "left_session_id": left.session_id,
            "right_session_id": right.session_id,
            "left_task": left.task,
            "right_task": right.task,
            "left_modality": left.modality,
            "right_modality": right.modality,
        }

        # --------------------------------------------------------------
        # Person identity / provenance
        # --------------------------------------------------------------
        same_person = left_key == right_key

        if not same_person:
            crosswalk_valid = (
                crosswalk is not None
                and _crosswalk_maps_persons(
                    left_key,
                    right_key,
                    crosswalk,
                )
            )

            if not crosswalk_valid:
                findings.append(
                    Finding(
                        rule_id="I3.person_pairing",
                        severity="ERROR",
                        message=(
                            "Cross-modal pair does not have compatible "
                            "namespace-qualified person identity."
                        ),
                        key_type="cross_modal_pair",
                        affected_keys=((left_key, right_key),),
                        expected=(
                            "same namespace-qualified person key or "
                            "explicit authoritative crosswalk mapping"
                        ),
                        observed={
                            "left_person_key": left_key,
                            "right_person_key": right_key,
                            "crosswalk_supplied": crosswalk is not None,
                        },
                        evidence_rows=(evidence,),
                        remediation=(
                            "Verify the participant identities and namespaces. "
                            "For cross-dataset pairing, supply an approved "
                            "authoritative crosswalk with provenance metadata."
                        ),
                    )
                )

        # --------------------------------------------------------------
        # Modality
        # --------------------------------------------------------------
        if (
            left.modality is None
            or right.modality is None
            or left.modality == right.modality
        ):
            findings.append(
                Finding(
                    rule_id="I3.modality_pairing",
                    severity="ERROR",
                    message=(
                        "Cross-modal pairing requires two explicit, "
                        "different modality values."
                    ),
                    key_type="cross_modal_pair",
                    affected_keys=((left_key, right_key),),
                    expected="two explicit and different modality values",
                    observed={
                        "left_modality": left.modality,
                        "right_modality": right.modality,
                    },
                    evidence_rows=(evidence,),
                    remediation=(
                        "Verify that the pair contains one record from each "
                        "intended modality."
                    ),
                )
            )

        # --------------------------------------------------------------
        # Session compatibility
        # --------------------------------------------------------------
        if not _session_task_compatible(
            left.session_id,
            right.session_id,
        ):
            findings.append(
                Finding(
                    rule_id="I3.session_compatibility",
                    severity="ERROR",
                    message=(
                        "Cross-modal pair contains incompatible session "
                        "identifiers."
                    ),
                    key_type="cross_modal_pair",
                    affected_keys=((left_key, right_key),),
                    expected=(
                        "equal session identifiers or both session "
                        "identifiers absent"
                    ),
                    observed={
                        "left_session_id": left.session_id,
                        "right_session_id": right.session_id,
                    },
                    evidence_rows=(evidence,),
                    remediation=(
                        "Verify that the records belong to compatible "
                        "sessions before pairing them."
                    ),
                )
            )

        # --------------------------------------------------------------
        # Task compatibility
        # --------------------------------------------------------------
        if not _session_task_compatible(
            left.task,
            right.task,
        ):
            findings.append(
                Finding(
                    rule_id="I3.task_compatibility",
                    severity="ERROR",
                    message=(
                        "Cross-modal pair contains incompatible task "
                        "identifiers."
                    ),
                    key_type="cross_modal_pair",
                    affected_keys=((left_key, right_key),),
                    expected=(
                        "equal task identifiers or both task identifiers "
                        "absent"
                    ),
                    observed={
                        "left_task": left.task,
                        "right_task": right.task,
                    },
                    evidence_rows=(evidence,),
                    remediation=(
                        "Verify that the records correspond to the same "
                        "task before pairing them."
                    ),
                )
            )

    return findings

def check_i2_join_cardinality(
    left_counts: dict[Any, int],
    right_counts: dict[Any, int],
    *,
    relation: str,
) -> list[Finding]:
    """
    Check observed join cardinality against a declared relation.

    Supported declared relations:
    - one_to_one
    - one_to_many
    - many_to_one

    Unmatched keys and many-to-many relationships are reported explicitly.
    """
    allowed_relations = {
        "one_to_one",
        "one_to_many",
        "many_to_one",
    }

    if relation not in allowed_relations:
        raise ValueError(
            f"Unsupported join relation: {relation!r}"
        )
    for side, counts in (
        ("left", left_counts),
        ("right", right_counts),
    ):
        for key, count in counts.items():
            if isinstance(count, bool) or not isinstance(count, int):
                raise ValueError(
                    f"{side} count for key {key!r} must be an integer."
                )

            if count < 1:
                raise ValueError(
                    f"{side} count for key {key!r} must be positive."
                )

    findings: list[Finding] = []

    left_keys = set(left_counts)
    right_keys = set(right_counts)

    unmatched_left = sorted(left_keys - right_keys, key=str)
    unmatched_right = sorted(right_keys - left_keys, key=str)

    if unmatched_left or unmatched_right:
        findings.append(
            Finding(
                rule_id="I2.unmatched_keys",
                severity="ERROR",
                message="Join contains unmatched keys.",
                key_type="join_key",
                affected_keys=tuple(
                    unmatched_left + unmatched_right
                ),
                expected="all declared join keys are matched",
                observed={
                    "unmatched_left": len(unmatched_left),
                    "unmatched_right": len(unmatched_right),
                },
                evidence_rows=tuple(
                    [
                        {
                            "side": "left",
                            "key": key,
                            "count": left_counts[key],
                        }
                        for key in unmatched_left
                    ]
                    + [
                        {
                            "side": "right",
                            "key": key,
                            "count": right_counts[key],
                        }
                        for key in unmatched_right
                    ]
                ),
                remediation=(
                    "Review the unmatched keys and verify that the "
                    "declared join relation and source manifests are correct."
                ),
            )
        )

    common_keys = left_keys & right_keys

    violating_keys: list[Any] = []
    evidence_rows: list[Any] = []

    for key in sorted(common_keys, key=str):
        left_count = left_counts[key]
        right_count = right_counts[key]

        is_valid = False

        if relation == "one_to_one":
            is_valid = left_count == 1 and right_count == 1

        elif relation == "one_to_many":
            is_valid = left_count == 1 and right_count >= 1

        elif relation == "many_to_one":
            is_valid = left_count >= 1 and right_count == 1

        if not is_valid:
            violating_keys.append(key)
            evidence_rows.append(
                {
                    "key": key,
                    "left_count": left_count,
                    "right_count": right_count,
                }
            )

    if violating_keys:
        findings.append(
            Finding(
                rule_id="I2.cardinality_mismatch",
                severity="ERROR",
                message=(
                    "Observed join cardinality does not match "
                    "the declared relation."
                ),
                key_type="join_key",
                affected_keys=tuple(violating_keys),
                expected=relation,
                observed=tuple(evidence_rows),
                evidence_rows=tuple(evidence_rows),
                remediation=(
                    "Verify the declared relation and inspect the "
                    "multiplicity of the affected join keys."
                ),
            )
        )

    many_to_many_keys = tuple(
        key
        for key in sorted(common_keys, key=str)
        if left_counts[key] > 1 and right_counts[key] > 1
    )

    if many_to_many_keys:
        findings.append(
            Finding(
                rule_id="I2.many_to_many",
                severity="ERROR",
                message=(
                    "Many-to-many join detected; such joins fail closed "
                    "unless separately approved and justified."
                ),
                key_type="join_key",
                affected_keys=many_to_many_keys,
                expected="no many-to-many join",
                observed=tuple(
                    {
                        "key": key,
                        "left_count": left_counts[key],
                        "right_count": right_counts[key],
                    }
                    for key in many_to_many_keys
                ),
                evidence_rows=tuple(
                    {
                        "key": key,
                        "left_count": left_counts[key],
                        "right_count": right_counts[key],
                    }
                    for key in many_to_many_keys
                ),
                remediation=(
                    "Do not perform the many-to-many join unless it has "
                    "been separately approved and justified."
                ),
            )
        )

    return findings

def check_i5_split_independence(
    records,
    *,
    grouping_variables=None,
):
    """
    Check split independence for person identities, source hashes,
    derivative hashes, and explicitly declared grouping variables.

    Implementation conventions:
    - A person_key must occur in exactly one non-null split.
    - A retrieved source hash must not occur across multiple splits.
    - A retrieved derivative hash must not occur across multiple splits.
    - Grouping variables are supplied explicitly as:
        {
            "variable_name": {
                "group_value": [
                    person_key,
                    person_key,
                    ...
                ]
            }
        }
    - A missing split is reported because split independence cannot be
      established for an unassigned record.
    - The values "not_retrieved" are excluded from hash leakage checks.
    """

    findings = []

    # ---------------------------------------------------------
    # I5.1 Split completeness
    # ---------------------------------------------------------
    missing_split_rows = []

    for index, record in enumerate(records):
        split = getattr(record, "split", None)

        if split is None or str(split).strip() == "":
            missing_split_rows.append(index)

    if missing_split_rows:
        findings.append(
            Finding(
                rule_id="I5.missing_split",
                severity="ERROR",
                message=(
                    "One or more records have no split assignment; "
                    "split independence cannot be established."
                ),
                key_type="record",
                affected_keys=[],
                expected="Every audited record has a split assignment.",
                observed={
                    "missing_split_rows": missing_split_rows,
                },
                evidence_rows=missing_split_rows,
                remediation=(
                    "Assign each record to an explicit analysis split "
                    "before performing split-independence auditing."
                ),
            )
        )

    # ---------------------------------------------------------
    # I5.2 Person split leakage
    # ---------------------------------------------------------
    person_splits = {}

    for index, record in enumerate(records):
        split = getattr(record, "split", None)

        if split is None or str(split).strip() == "":
            continue

        person_key = record.person_key

        person_splits.setdefault(person_key, []).append(
            (str(split), index)
        )

    for person_key, entries in person_splits.items():
        splits = sorted({split for split, _ in entries})

        if len(splits) > 1:
            evidence_rows = [
                index
                for _, index in entries
            ]

            findings.append(
                Finding(
                    rule_id="I5.person_split_leakage",
                    severity="ERROR",
                    message=(
                        "A single person identity occurs in multiple "
                        "analysis splits."
                    ),
                    key_type="person",
                    affected_keys=[person_key],
                    expected="Each person_key belongs to exactly one split.",
                    observed={
                        "splits": splits,
                    },
                    evidence_rows=evidence_rows,
                    remediation=(
                        "Keep all records belonging to the same person_key "
                        "within one outer analysis split."
                    ),
                )
            )

    # ---------------------------------------------------------
    # I5.3 Source-hash split leakage
    # ---------------------------------------------------------
    source_hash_splits = {}

    for index, record in enumerate(records):
        split = getattr(record, "split", None)
        source_hash = getattr(record, "source_sha256", None)

        if (
            split is None
            or str(split).strip() == ""
            or source_hash is None
            or source_hash == ""
            or source_hash == "not_retrieved"
        ):
            continue

        source_hash_splits.setdefault(source_hash, []).append(
            (str(split), index)
        )

    for source_hash, entries in source_hash_splits.items():
        splits = sorted({split for split, _ in entries})

        if len(splits) > 1:
            evidence_rows = [
                index
                for _, index in entries
            ]

            findings.append(
                Finding(
                    rule_id="I5.source_split_leakage",
                    severity="ERROR",
                    message=(
                        "The same retrieved source content hash occurs "
                        "across multiple analysis splits."
                    ),
                    key_type="source_hash",
                    affected_keys=[source_hash],
                    expected=(
                        "A retrieved source_sha256 occurs in only one split."
                    ),
                    observed={
                        "splits": splits,
                    },
                    evidence_rows=evidence_rows,
                    remediation=(
                        "Remove cross-split duplication of the same source "
                        "content or correct the split assignments."
                    ),
                )
            )

    # ---------------------------------------------------------
    # I5.4 Derivative-hash split leakage
    # ---------------------------------------------------------
    derivative_hash_splits = {}

    for index, record in enumerate(records):
        split = getattr(record, "split", None)
        derivative_hash = getattr(record, "derivative_sha256", None)

        if (
            split is None
            or str(split).strip() == ""
            or derivative_hash is None
            or derivative_hash == ""
            or derivative_hash == "not_retrieved"
        ):
            continue

        derivative_hash_splits.setdefault(
            derivative_hash, []
        ).append(
            (str(split), index)
        )

    for derivative_hash, entries in derivative_hash_splits.items():
        splits = sorted({split for split, _ in entries})

        if len(splits) > 1:
            evidence_rows = [
                index
                for _, index in entries
            ]

            findings.append(
                Finding(
                    rule_id="I5.derivative_split_leakage",
                    severity="ERROR",
                    message=(
                        "The same retrieved derivative content hash occurs "
                        "across multiple analysis splits."
                    ),
                    key_type="derivative_hash",
                    affected_keys=[derivative_hash],
                    expected=(
                        "A retrieved derivative_sha256 occurs in only one split."
                    ),
                    observed={
                        "splits": splits,
                    },
                    evidence_rows=evidence_rows,
                    remediation=(
                        "Remove cross-split duplication of the same "
                        "derivative content or correct the split assignments."
                    ),
                )
            )

    # ---------------------------------------------------------
    # I5.5 Explicit grouping-variable split leakage
    # ---------------------------------------------------------
    if grouping_variables:
        record_splits_by_person = {}

        for record in records:
            split = getattr(record, "split", None)

            if split is None or str(split).strip() == "":
                continue

            record_splits_by_person.setdefault(
                record.person_key,
                set(),
            ).add(str(split))

        for variable_name, groups in grouping_variables.items():
            for group_value, person_keys in groups.items():
                group_splits = set()
                evidence_rows = []

                for person_key in person_keys:
                    splits = record_splits_by_person.get(
                        person_key,
                        set(),
                    )

                    group_splits.update(splits)

                    for index, record in enumerate(records):
                        if (
                            record.person_key == person_key
                            and getattr(record, "split", None)
                        ):
                            evidence_rows.append(index)

                if len(group_splits) > 1:
                    findings.append(
                        Finding(
                            rule_id="I5.grouping_variable_split_leakage",
                            severity="ERROR",
                            message=(
                                "A declared grouping variable contains "
                                "members assigned to multiple analysis splits."
                            ),
                            key_type="grouping_variable",
                            affected_keys=[
                                (variable_name, group_value)
                            ],
                            expected=(
                                "Each grouping-variable value belongs "
                                "to one analysis split."
                            ),
                            observed={
                                "variable": variable_name,
                                "value": group_value,
                                "splits": sorted(group_splits),
                            },
                            evidence_rows=sorted(set(evidence_rows)),
                            remediation=(
                                "Keep all members of the same declared "
                                "grouping variable within one outer split."
                            ),
                        )
                    )

    return findings

def check_i6_metric_denominator_traceability(
    records,
    metrics,
    populations,
):
    """
    Check that analysis-metric denominators are traceable to an
    explicitly declared audited population.

    Implementation convention:
    - Each metric declares a population_key.
    - populations maps population keys to namespace-qualified person_keys.
    - The expected denominator is the number of unique person_keys
      in the declared population.
    - numerator must satisfy 0 <= numerator <= denominator.
    - denominator must be positive.
    - The metric population must be explicitly declared.
    """

    findings = []

    # ---------------------------------------------------------
    # Build the set of audited person keys.
    # ---------------------------------------------------------
    audited_person_keys = {
        record.person_key
        for record in records
    }

    # ---------------------------------------------------------
    # Validate each metric.
    # ---------------------------------------------------------
    for metric_index, metric in enumerate(metrics):

        metric_name = metric.get("metric_name")
        population_key = metric.get("population_key")

        numerator = metric.get("numerator")
        denominator = metric.get("denominator")

        # -----------------------------------------------------
        # I6.1 Population declaration
        # -----------------------------------------------------
        if not population_key:
            findings.append(
                Finding(
                    rule_id="I6.missing_population_key",
                    severity="ERROR",
                    message=(
                        "The metric does not declare the population "
                        "from which its denominator was calculated."
                    ),
                    key_type="metric",
                    affected_keys=[metric_name],
                    expected=(
                        "Every metric declares an explicit population_key."
                    ),
                    observed={
                        "metric_index": metric_index,
                        "population_key": population_key,
                    },
                    evidence_rows=[metric_index],
                    remediation=(
                        "Associate the metric with an explicitly "
                        "declared audited population."
                    ),
                )
            )

            continue

        if population_key not in populations:
            findings.append(
                Finding(
                    rule_id="I6.untraceable_population",
                    severity="ERROR",
                    message=(
                        "The metric references a population that is "
                        "not present in the population registry."
                    ),
                    key_type="metric_population",
                    affected_keys=[population_key],
                    expected=(
                        "Every metric population_key resolves to a "
                        "declared population."
                    ),
                    observed={
                        "metric": metric_name,
                        "population_key": population_key,
                    },
                    evidence_rows=[metric_index],
                    remediation=(
                        "Declare the metric population and provide "
                        "its namespace-qualified person keys."
                    ),
                )
            )

            continue

        # -----------------------------------------------------
        # I6.2 Denominator validity
        # -----------------------------------------------------
        denominator_valid = (
            isinstance(denominator, int)
            and not isinstance(denominator, bool)
            and denominator > 0
        )

        if not denominator_valid:
            findings.append(
                Finding(
                    rule_id="I6.invalid_denominator",
                    severity="ERROR",
                    message=(
                        "The metric denominator must be a positive integer."
                    ),
                    key_type="metric",
                    affected_keys=[metric_name],
                    expected="Metric denominator is a positive integer.",
                    observed={"denominator": denominator},
                    evidence_rows=[metric_index],
                    remediation=(
                        "Provide the actual positive integer denominator "
                        "used to calculate the metric."
                    ),
                )
            )

        # -----------------------------------------------------
        # I6.3 Numerator validity
        # -----------------------------------------------------
        numerator_valid = (
            isinstance(numerator, int)
            and not isinstance(numerator, bool)
            and numerator >= 0
        )

        if not numerator_valid:
            findings.append(
                Finding(
                    rule_id="I6.invalid_numerator",
                    severity="ERROR",
                    message=(
                        "The metric numerator must be a non-negative integer."
                    ),
                    key_type="metric",
                    affected_keys=[metric_name],
                    expected="Metric numerator is a non-negative integer.",
                    observed={"numerator": numerator},
                    evidence_rows=[metric_index],
                    remediation=(
                        "Record the non-negative integer numerator "
                        "used to calculate the metric."
                    ),
                )
            )
        elif denominator_valid and numerator > denominator:
            findings.append(
                Finding(
                    rule_id="I6.invalid_numerator",
                    severity="ERROR",
                    message=(
                        "The metric numerator is outside the "
                        "valid range defined by its denominator."
                    ),
                    key_type="metric",
                    affected_keys=[metric_name],
                    expected="0 <= numerator <= denominator.",
                    observed={
                        "numerator": numerator,
                        "denominator": denominator,
                    },
                    evidence_rows=[metric_index],
                    remediation=(
                        "Correct the numerator or denominator "
                        "to match the recorded metric population."
                    ),
                )
            )

        # -----------------------------------------------------
        # I6.4 Denominator traceability
        # -----------------------------------------------------
        declared_population = populations[population_key]

        population_person_keys = set(declared_population)

        # The population itself must be represented in the audited
        # records.
        missing_person_keys = (
            population_person_keys - audited_person_keys
        )

        if missing_person_keys:
            findings.append(
                Finding(
                    rule_id="I6.untraceable_population",
                    severity="ERROR",
                    message=(
                        "The declared metric population contains "
                        "person keys that are absent from the audited records."
                    ),
                    key_type="metric_population",
                    affected_keys=[population_key],
                    expected=(
                        "Every population member is represented "
                        "in the audited manifest."
                    ),
                    observed={
                        "missing_person_keys": sorted(
                            missing_person_keys
                        ),
                    },
                    evidence_rows=[metric_index],
                    remediation=(
                        "Ensure the metric population is constructed "
                        "from the same audited manifest or explain "
                        "the missing population members."
                    ),
                )
            )

        expected_denominator = len(population_person_keys)

        if denominator != expected_denominator:
            findings.append(
                Finding(
                    rule_id="I6.denominator_mismatch",
                    severity="ERROR",
                    message=(
                        "The metric denominator does not match the "
                        "size of its declared audited population."
                    ),
                    key_type="metric_population",
                    affected_keys=[population_key],
                    expected={
                        "denominator": expected_denominator,
                    },
                    observed={
                        "denominator": denominator,
                        "population_size": expected_denominator,
                    },
                    evidence_rows=[metric_index],
                    remediation=(
                        "Reconcile the reported metric denominator "
                        "with the explicitly declared population."
                    ),
                )
            )

    return findings