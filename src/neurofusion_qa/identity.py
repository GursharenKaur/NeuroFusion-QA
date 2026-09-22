from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re
import unicodedata


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

    The original participant_id is never modified.
    """
    normalized = unicodedata.normalize("NFKC", participant_id)
    normalized = normalized.casefold().strip()

    # Remove the BIDS subject prefix and one or more separators.
    label = re.sub(r"^sub[-_.\s]*", "", normalized)

    # Treat punctuation/separators as equivalent.
    label = re.sub(r"[-_.\s]+", "", label)

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


def _crosswalk_maps_persons(
    left_key: tuple[str, str, str],
    right_key: tuple[str, str, str],
    crosswalk: AuthoritativeCrosswalk,
) -> bool:
    """
    Check whether an authoritative crosswalk explicitly establishes
    the supplied left/right person relationship.
    """
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