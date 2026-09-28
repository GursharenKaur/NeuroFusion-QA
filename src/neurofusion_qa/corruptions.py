from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import random
from typing import Any
from .identity import canonicalize_participant_id


def _manifest_hash(records: list[Any]) -> str:
    """
    Create a deterministic hash of the clean manifest representation.

    The hash is used only to record the parent manifest associated with
    a corruption instance.
    """
    rows = [
        {
            "dataset_namespace": record.dataset_namespace,
            "dataset_version": record.dataset_version,
            "participant_id": record.participant_id,
            "session_id": record.session_id,
            "modality": record.modality,
            "task": record.task,
            "acquisition": record.acquisition,
            "run": record.run,
            "source_path": record.source_path,
            "source_sha256": record.source_sha256,
            "derivative_recipe_sha256": record.derivative_recipe_sha256,
            "derivative_path": record.derivative_path,
            "derivative_sha256": record.derivative_sha256,
            "split": record.split,
            "analysis_role": record.analysis_role,
        }
        for record in records
    ]

    payload = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def _inject_c1_namespace_stripping(
    records: list[Any],
    *,
    affected_count: int,
    seed: int,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Remove dataset namespaces from a deterministic seed-selected
    set of manifest records.

    This is the C1 implementation convention.

    Participant IDs and all other record fields are preserved.
    """

    if affected_count < 1:
        raise ValueError(
            "affected_count must be at least 1."
        )

    if affected_count > len(records):
        raise ValueError(
            "affected_count cannot exceed the number of records."
        )

    rng = random.Random(seed)

    affected_indices = sorted(
        rng.sample(
            range(len(records)),
            affected_count,
        )
    )

    corrupted = list(records)

    affected_keys = []

    for index in affected_indices:
        original = corrupted[index]

        affected_keys.append(
            original.person_key
        )

        corrupted[index] = replace(
            original,
            dataset_namespace=None,
        )

    truth = {
        "corruption": "C1_namespace_stripping",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": [
            {
                "operation": "remove_dataset_namespace",
                "row_index": index,
            }
            for index in affected_indices
        ],
        "affected_keys": affected_keys,
        "expected_violations": [
            "I1.namespace_completeness",
            "I3.person_pairing",
        ],
    }

    return corrupted, truth

def _collision_variant(participant_id: str) -> str:
    """
    Return a raw participant label that is different from the input
    but has the same canonical form under IdentityGuard's I1 policy.
    """
    canonical = canonicalize_participant_id(participant_id)

    if not canonical.startswith("sub-"):
        raise ValueError(
            f"Cannot construct canonicalization variant for participant ID: "
            f"{participant_id!r}"
        )

    label = canonical[4:]

    if label.isdigit():
        return f"sub-{int(label):03d}"

    return f"sub_{label}"


def _inject_c2_canonicalization_collision(
    records: list[Any],
    *,
    affected_count: int,
    seed: int,
):
    """
    Create canonicalization collisions by changing one participant label
    in each selected pair to a distinct raw label with the same canonical ID.

    `affected_count` denotes the number of collision instances. Each
    collision instance consumes two distinct manifest records.

    The original records are never modified in place.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    if affected_count * 2 > len(records):
        raise ValueError(
            "affected_count cannot exceed the number of available "
            "two-record collision instances."
        )

    rng = random.Random(seed)

    selected_indices = rng.sample(
        range(len(records)),
        affected_count * 2,
    )

    corrupted = list(records)
    affected_keys = []
    operations = []

    for pair_index in range(affected_count):
        donor_index = selected_indices[2 * pair_index]
        target_index = selected_indices[2 * pair_index + 1]

        donor = corrupted[donor_index]
        target = corrupted[target_index]

        # The collision must occur within the same namespace/version.
        if (
            donor.dataset_namespace != target.dataset_namespace
            or donor.dataset_version != target.dataset_version
        ):
            # This pair cannot produce an I1 collision because the
            # collision detector is namespace/version qualified.
            raise ValueError(
                "C2 requires each collision pair to share the same "
                "dataset namespace and version."
            )

        new_participant_id = _collision_variant(donor.participant_id)

        # Ensure the changed raw ID is actually different from the target.
        if new_participant_id == target.participant_id:
            new_participant_id = (
                f"{new_participant_id}_variant"
            )

            # Verify that our fallback still canonicalizes identically.
            if (
                canonicalize_participant_id(new_participant_id)
                != canonicalize_participant_id(donor.participant_id)
            ):
                raise ValueError(
                    "Unable to construct a canonicalization-equivalent "
                    "participant ID."
                )

        original_target_key = target.person_key

        corrupted[target_index] = replace(
            target,
            participant_id=new_participant_id,
        )

        affected_keys.append(original_target_key)

        operations.append(
            {
                "operation": "replace_participant_id_with_canonical_variant",
                "donor_row_index": donor_index,
                "target_row_index": target_index,
                "original_target_participant_id": target.participant_id,
                "new_target_participant_id": new_participant_id,
                "canonical_participant_id": canonicalize_participant_id(
                    donor.participant_id
                ),
            }
        )

    truth = {
        "corruption": "C2_canonicalization_collision",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": [
            "I1.canonicalization_collision",
            "I2.cardinality_mismatch",
        ],
    }

    return corrupted, truth

def _inject_c4_cross_modal_permutation(
    records: list[Any],
    *,
    affected_count: int,
    seed: int,
):
    """
    Create cross-modal identity permutations.

    Each corruption instance reassigns the participant ID of one
    modality-bearing record to a different participant in the same
    dataset namespace/version.

    The original records are never modified in place.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    eligible_indices = [
        index
        for index, record in enumerate(records)
        if (
            record.dataset_namespace is not None
            and record.dataset_version is not None
            and record.participant_id
            and record.modality
        )
    ]

    if len(eligible_indices) < 2:
        raise ValueError(
            "C4 requires at least two eligible modality records."
        )

    rng = random.Random(seed)
    corrupted = list(records)

    operations = []
    affected_keys = []

    available_sources = list(eligible_indices)

    for _ in range(affected_count):
        if not available_sources:
            raise ValueError(
                "Not enough eligible records for the requested "
                "affected_count."
            )

        rng.shuffle(available_sources)

        source_index = None
        target_index = None

        for candidate_source in available_sources:
            source = corrupted[candidate_source]

            for candidate_target in eligible_indices:
                if candidate_source == candidate_target:
                    continue

                target = records[candidate_target]

                # Keep the permutation within the same
                # namespace/version.
                if (
                    source.dataset_namespace
                    != target.dataset_namespace
                    or source.dataset_version
                    != target.dataset_version
                ):
                    continue

                # Must be a different participant.
                if source.person_key == target.person_key:
                    continue

                source_index = candidate_source
                target_index = candidate_target
                break

            if source_index is not None:
                break

        if source_index is None or target_index is None:
            raise ValueError(
                "Unable to construct a valid C4 cross-modal "
                "permutation from the supplied records."
            )

        source = corrupted[source_index]
        target = records[target_index]

        original_person_key = source.person_key

        corrupted[source_index] = replace(
            source,
            participant_id=target.participant_id,
        )

        affected_keys.append(original_person_key)

        operations.append(
            {
                "operation": (
                    "reassign_modality_record_to_other_participant"
                ),
                "source_row_index": source_index,
                "target_row_index": target_index,
                "original_person_key": original_person_key,
                "new_person_key": corrupted[source_index].person_key,
                "modality": source.modality,
            }
        )

        available_sources.remove(source_index)

    truth = {
        "corruption": "C4_cross_modal_permutation",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": [
            "I3.person_pairing",
        ],
    }

    return corrupted, truth

def inject_corruption(
    records: list[Any],
    *,
    corruption: str,
    affected_count: int,
    seed: int,
) -> tuple[list[Any], dict[str, Any]]:
    """
    Inject one documented corruption into a clean manifest.

    Currently implemented:
        C1_namespace_stripping
        C2_canonicalization_collision

    The clean input is never modified in place.
    """

    clean_records = list(records)

    if corruption == "C1_namespace_stripping":
        return _inject_c1_namespace_stripping(
            clean_records,
            affected_count=affected_count,
            seed=seed,
        )

    if corruption == "C2_canonicalization_collision":
        return _inject_c2_canonicalization_collision(
            clean_records,
            affected_count=affected_count,
            seed=seed,
        )
    
    if corruption == "C3_duplicate_propagation":
        return _inject_c3_duplicate_propagation(
            clean_records,
            affected_count=affected_count,
            seed=seed,
        )

    if corruption == "C4_cross_modal_permutation":
        return _inject_c4_cross_modal_permutation(
            clean_records,
            affected_count=affected_count,
            seed=seed,
        )

    raise ValueError(
        f"Unsupported corruption type: {corruption!r}"
    )

def _inject_c3_duplicate_propagation(
    records: list[Any],
    *,
    affected_count: int,
    seed: int,
):
    """
    Duplicate selected manifest/acquisition rows.

    `affected_count` is the number of source rows to duplicate.
    Each selected row is copied once.

    The clean input is never modified in place.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    if affected_count > len(records):
        raise ValueError(
            "affected_count cannot exceed the number of available records."
        )

    rng = random.Random(seed)

    selected_indices = sorted(
        rng.sample(range(len(records)), affected_count)
    )

    corrupted = list(records)
    operations = []
    affected_keys = []

    # Append duplicates rather than replacing the original rows.
    # This preserves the original evidence while introducing the
    # duplicate propagation corruption.
    for index in selected_indices:
        original = records[index]

        corrupted.append(original)

        affected_keys.append(original.acquisition_key)

        operations.append(
            {
                "operation": "duplicate_manifest_row",
                "source_row_index": index,
                "duplicated_row_index": len(corrupted) - 1,
                "affected_acquisition_key": original.acquisition_key,
            }
        )

    truth = {
        "corruption": "C3_duplicate_propagation",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": [
            "I2.cardinality_mismatch",
            "I4.repeated_row",
            "I4.repeated_source_path",
            "I6.denominator_mismatch",
        ],
    }

    return corrupted, truth

def _inject_c4_cross_modal_permutation(
    records: list[Any],
    *,
    affected_count: int,
    seed: int,
):
    """
    Permute cross-modal identity assignment.

    For each corruption instance, select two records from different
    participants and reassign the participant ID of one modality-B
    record to the other participant.

    The underlying acquisition/source evidence is preserved.

    `affected_count` denotes the number of corrupted modality-B records.

    The clean input is never modified in place.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    if affected_count > len(records):
        raise ValueError(
            "affected_count cannot exceed the number of available records."
        )

    # We need at least two distinct participant identities.
    participant_keys = {
        record.person_key
        for record in records
        if record.dataset_namespace is not None
        and record.dataset_version is not None
        and record.participant_id
    }

    if len(participant_keys) < 2:
        raise ValueError(
            "C4 requires at least two distinct participant identities."
        )

    rng = random.Random(seed)

    # Work with records that have an explicit modality and identity.
    eligible_indices = [
        index
        for index, record in enumerate(records)
        if record.dataset_namespace is not None
        and record.dataset_version is not None
        and record.participant_id
        and record.modality
    ]

    if len(eligible_indices) < 2:
        raise ValueError(
            "C4 requires at least two modality-bearing records."
        )

    corrupted = list(records)
    operations = []
    affected_keys = []

    available = list(eligible_indices)

    for _ in range(affected_count):
        if len(available) < 2:
            raise ValueError(
                "Not enough eligible records for the requested "
                "number of C4 corruption instances."
            )

        rng.shuffle(available)

        source_index = None
        target_index = None

        for candidate_source in available:
            source = corrupted[candidate_source]

            for candidate_target in available:
                if candidate_source == candidate_target:
                    continue

                target = corrupted[candidate_target]

                # Keep the corruption within the same namespace/version.
                if (
                    source.dataset_namespace != target.dataset_namespace
                    or source.dataset_version != target.dataset_version
                ):
                    continue

                # The two records must belong to different participants.
                if source.person_key == target.person_key:
                    continue

                source_index = candidate_source
                target_index = candidate_target
                break

            if source_index is not None:
                break

        if source_index is None or target_index is None:
            raise ValueError(
                "Unable to construct a valid C4 cross-modal permutation "
                "from the supplied records."
            )

        source = corrupted[source_index]
        target = corrupted[target_index]

        original_source_key = source.person_key
        new_participant_id = target.participant_id

        corrupted[source_index] = replace(
            source,
            participant_id=new_participant_id,
        )

        affected_keys.append(original_source_key)

        operations.append(
            {
                "operation": "reassign_modality_record_to_other_participant",
                "source_row_index": source_index,
                "target_row_index": target_index,
                "original_person_key": original_source_key,
                "new_person_key": corrupted[source_index].person_key,
                "modality": source.modality,
            }
        )

        # Prevent the same source record from being selected again.
        available.remove(source_index)

    truth = {
        "corruption": "C4_cross_modal_permutation",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": [
            "I3.person_pairing",
        ],
    }

    return corrupted, truth