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
    Remove dataset namespaces from one selected record for each affected
    person key.

    `affected_count` is the number of affected person keys, matching the
    protocol-defined synthetic severity unit.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    person_to_indices: dict[tuple[Any, ...], list[int]] = {}

    for index, record in enumerate(records):
        if (
            record.dataset_namespace is None
            or record.dataset_version is None
            or not record.participant_id
        ):
            continue

        person_to_indices.setdefault(record.person_key, []).append(index)

    eligible_people = sorted(person_to_indices)

    if affected_count > len(eligible_people):
        raise ValueError(
            "affected_count cannot exceed the number of eligible person keys."
        )

    rng = random.Random(seed)
    selected_people = rng.sample(eligible_people, affected_count)

    corrupted = list(records)
    affected_keys = []
    operations = []

    for person_key in selected_people:
        index = rng.choice(person_to_indices[person_key])
        original = corrupted[index]

        affected_keys.append(person_key)

        corrupted[index] = replace(
            original,
            dataset_namespace=None,
        )

        operations.append(
            {
                "operation": "remove_dataset_namespace",
                "row_index": index,
                "affected_person_key": person_key,
            }
        )

    truth = {
        "corruption": "C1_namespace_stripping",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": [
            "I1.namespace_completeness",
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

    person_to_indices: dict[tuple[Any, ...], list[int]] = {}

    for index, record in enumerate(records):
        if (
            record.dataset_namespace is None
            or record.dataset_version is None
            or not record.participant_id
        ):
            continue

        person_to_indices.setdefault(record.person_key, []).append(index)

    # A collision is only valid within the same namespace and version.
    # Group people first so random selection cannot create incompatible pairs.
    people_by_dataset: dict[tuple[Any, Any], list[tuple[Any, ...]]] = {}

    for person_key in sorted(person_to_indices):
        dataset_key = (person_key[0], person_key[1])
        people_by_dataset.setdefault(dataset_key, []).append(person_key)

    # Build candidate pairs without reusing a person across collision instances.
    candidate_pairs = []

    for dataset_key in sorted(people_by_dataset):
        people = people_by_dataset[dataset_key]
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                candidate_pairs.append((people[i], people[j]))

    rng.shuffle(candidate_pairs)

    selected_pairs = []
    used_people = set()

    for donor_person, target_person in candidate_pairs:
        if donor_person in used_people or target_person in used_people:
            continue

        selected_pairs.append((donor_person, target_person))
        used_people.add(donor_person)
        used_people.add(target_person)

        if len(selected_pairs) == affected_count:
            break

    if len(selected_pairs) < affected_count:
        raise ValueError(
            "C2 requires enough distinct eligible people to form "
            "the requested number of collision instances within "
            "matching dataset namespaces and versions."
        )

    corrupted = list(records)
    affected_keys = []
    operations = []

    for donor_person, target_person in selected_pairs:
        donor_index = rng.choice(person_to_indices[donor_person])
        target_index = rng.choice(person_to_indices[target_person])

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

def _inject_c5_subject_split_leakage(
    records: list[Any],
    *,
    affected_count: int,
    seed: int,
):
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    available_splits = sorted(
        {
            record.split
            for record in records
            if record.split is not None
        }
    )

    if len(available_splits) < 2:
        raise ValueError(
            "C5 requires at least two distinct split assignments."
        )

    # Group records by person, but only consider people who have
    # at least two records currently assigned to the same split.
    person_split_groups = {}
    for index, record in enumerate(records):
        if record.split is None:
            continue

        identity_fields = (
            record.dataset_namespace,
            record.dataset_version,
            record.participant_id,
        )
        if any(
            not isinstance(value, str) or not value.strip()
            for value in identity_fields
        ):
            continue

        person_groups = person_split_groups.setdefault(
            record.person_key, {}
        )
        person_groups.setdefault(record.split, []).append(index)

    eligible_groups = []

    for person_key, split_groups in person_split_groups.items():
        for split, indices in split_groups.items():
            if len(indices) >= 2:
                eligible_groups.append(
                    (person_key, split, indices)
                )

    if affected_count > len(eligible_groups):
        raise ValueError(
            "affected_count cannot exceed the number of eligible "
            "person/split groups."
        )

    rng = random.Random(seed)

    selected_groups = rng.sample(
        eligible_groups,
        affected_count,
    )

    corrupted = list(records)
    operations = []
    affected_keys = []

    for person_key, original_split, indices in selected_groups:
        source_index = rng.choice(indices)

        alternative_splits = [
            split
            for split in available_splits
            if split != original_split
        ]

        new_split = rng.choice(alternative_splits)

        original = corrupted[source_index]

        corrupted[source_index] = replace(
            original,
            split=new_split,
        )

        affected_keys.append(person_key)

        operations.append(
            {
                "operation": "move_record_to_different_split",
                "source_row_index": source_index,
                "affected_person_key": person_key,
                "original_split": original_split,
                "new_split": new_split,
            }
        )

    truth = {
        "corruption": "C5_subject_split_leakage",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": [
            "I5.person_split_leakage",
        ],
    }

    return corrupted, truth



def _inject_c6_denominator_mismatch(
    records: list[Any],
    *,
    metrics: list[dict[str, Any]],
    populations: dict[str, list[tuple[Any, ...]]],
    affected_count: int,
    seed: int,
):
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    if not metrics:
        raise ValueError("C6 requires at least one metric record.")

    if populations is None:
        raise ValueError("C6 requires population definitions.")

    eligible_indices = []

    for index, metric in enumerate(metrics):
        population_key = metric.get("population_key")
        if not population_key:
            continue

        person_keys = populations.get(population_key)
        if not person_keys:
            continue

        actual_denominator = len(set(person_keys))
        if actual_denominator <= 0:
            continue

        eligible_indices.append(index)

    if affected_count > len(eligible_indices):
        raise ValueError(
            "affected_count cannot exceed the number of eligible metrics."
        )

    rng = random.Random(seed)
    selected_indices = sorted(
        rng.sample(eligible_indices, affected_count)
    )

    # Validate every selected metric before creating the corrupted copy.
    for index in selected_indices:
        denominator = metrics[index].get("denominator")

        if isinstance(denominator, bool) or not isinstance(
            denominator, int
        ):
            raise ValueError(
                "C6 requires metric denominators to be integers; "
                "booleans are not valid denominators."
            )

        if denominator <= 0:
            raise ValueError(
                "C6 requires metric denominators to be positive."
            )

    corrupted_metrics = [dict(metric) for metric in metrics]
    operations = []
    affected_keys = []

    for index in selected_indices:
        original = metrics[index]
        population_key = original["population_key"]
        person_keys = populations[population_key]
        actual_denominator = len(set(person_keys))
        original_denominator = original["denominator"]

        # Always create a denominator that differs from the actual
        # unique-person count.
        new_denominator = actual_denominator + 1

        corrupted_metrics[index]["denominator"] = new_denominator
        affected_keys.append(population_key)

        operations.append(
            {
                "operation": "change_metric_denominator",
                "metric_index": index,
                "metric_name": original.get("metric_name"),
                "population_key": population_key,
                "original_denominator": original_denominator,
                "actual_population_denominator": actual_denominator,
                "new_denominator": new_denominator,
            }
        )

    truth = {
        "corruption": "C6_denominator_mismatch",
        "seed": seed,
        "parent_manifest_sha256": _manifest_hash(records),
        "operations": operations,
        "affected_keys": affected_keys,
        "expected_violations": ["I6.denominator_mismatch"],
    }

    return corrupted_metrics, truth

def inject_corruption(
    records: list[Any],
    *,
    corruption: str,
    affected_count: int,
    seed: int,
    metrics: list[dict[str, Any]] | None = None,
    populations: dict[str, list[tuple[Any, ...]]] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """
    Inject one documented corruption into a clean manifest.

    Currently implemented:
        C0_clean
        C1_namespace_stripping
        C2_canonicalization_collision
        C3_duplicate_propagation
        C4_cross_modal_permutation
        C5_subject_split_leakage
        C6_denominator_mismatch

    The clean input is never modified in place.
    """

    clean_records = list(records)

    if corruption == "C0_clean":
        return clean_records, {
            "corruption": "C0_clean",
            "operations": [],
            "expected_violations": [],
            "affected_keys": [],
        }

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

    if corruption == "C5_subject_split_leakage":
        return _inject_c5_subject_split_leakage(
            clean_records,
            affected_count=affected_count,
            seed=seed,
        )

    if corruption == "C6_denominator_mismatch":
        if metrics is None:
            raise ValueError(
                "C6_denominator_mismatch requires metrics."
            )

        if populations is None:
            raise ValueError(
                "C6_denominator_mismatch requires populations."
            )

        return _inject_c6_denominator_mismatch(
            clean_records,
            metrics=metrics,
            populations=populations,
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
    Duplicate one manifest/acquisition row for each affected person key.

    `affected_count` is the number of affected person keys. Exactly one
    eligible row is duplicated for each selected person.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    person_to_indices: dict[tuple[Any, ...], list[int]] = {}

    for index, record in enumerate(records):
        if (
            record.dataset_namespace is None
            or record.dataset_version is None
            or not record.participant_id
        ):
            continue

        person_to_indices.setdefault(record.person_key, []).append(index)

    eligible_people = sorted(person_to_indices)

    if affected_count > len(eligible_people):
        raise ValueError(
            "affected_count cannot exceed the number of eligible person keys."
        )

    rng = random.Random(seed)
    selected_people = rng.sample(eligible_people, affected_count)

    corrupted = list(records)
    operations = []
    affected_keys = []

    for person_key in selected_people:
        source_index = rng.choice(person_to_indices[person_key])
        original = records[source_index]

        corrupted.append(original)

        affected_keys.append(original.acquisition_key)

        operations.append(
            {
                "operation": "duplicate_manifest_row",
                "source_row_index": source_index,
                "duplicated_row_index": len(corrupted) - 1,
                "affected_person_key": person_key,
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
    Reassign one modality-bearing record for each affected source person
    to another person's participant ID.

    `affected_count` is the number of affected source person keys.
    """
    if affected_count < 1:
        raise ValueError("affected_count must be at least 1.")

    eligible_by_person: dict[tuple[Any, ...], list[int]] = {}

    for index, record in enumerate(records):
        if (
            record.dataset_namespace is None
            or record.dataset_version is None
            or not record.participant_id
            or not record.modality
        ):
            continue

        eligible_by_person.setdefault(record.person_key, []).append(index)

    eligible_people = sorted(eligible_by_person)

    people_by_namespace_version: dict[tuple[Any, Any], list[tuple[Any, ...]]] = {}

    for person_key in eligible_people:
        namespace_version = (person_key[0], person_key[1])
        people_by_namespace_version.setdefault(
            namespace_version, []
        ).append(person_key)

    eligible_source_people = [
        person_key
        for person_key in eligible_people
        if len(
            people_by_namespace_version[
                (person_key[0], person_key[1])
            ]
        ) >= 2
    ]

    if len(eligible_source_people) < 1:
        raise ValueError(
            "C4 requires at least two distinct participant identities "
            "in the same dataset namespace/version."
        )

    if affected_count > len(eligible_source_people):
        raise ValueError(
            "affected_count cannot exceed the number of eligible source "
            "person keys with same-namespace/version alternatives."
        )

    rng = random.Random(seed)

    selected_source_people = rng.sample(
        eligible_source_people,
        affected_count,
    )

    corrupted = list(records)
    operations = []
    affected_keys = []

    for source_person_key in selected_source_people:
        source_index = rng.choice(
            eligible_by_person[source_person_key]
        )
        source = records[source_index]

        possible_targets = [
            person_key
            for person_key in eligible_people
            if person_key != source_person_key
            and person_key[0] == source_person_key[0]
            and person_key[1] == source_person_key[1]
        ]

        if not possible_targets:
            raise ValueError(
                "C4 requires another participant in the same "
                "dataset namespace/version."
            )

        target_person_key = rng.choice(possible_targets)

        target_indices = eligible_by_person[target_person_key]
        target_index = rng.choice(target_indices)
        target = records[target_index]

        original_source_key = source.person_key
        new_participant_id = target.participant_id

        corrupted[source_index] = replace(
            source,
            participant_id=new_participant_id,
        )

        affected_keys.append(original_source_key)

        operations.append(
            {
                "operation": (
                    "reassign_modality_record_to_other_participant"
                ),
                "source_row_index": source_index,
                "target_row_index": target_index,
                "original_person_key": original_source_key,
                "new_person_key": corrupted[source_index].person_key,
                "modality": source.modality,
            }
        )

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