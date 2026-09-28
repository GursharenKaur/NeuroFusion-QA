from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import random
from typing import Any


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

    The clean input is never modified in place.
    """

    clean_records = list(records)

    if corruption == "C1_namespace_stripping":
        return _inject_c1_namespace_stripping(
            clean_records,
            affected_count=affected_count,
            seed=seed,
        )

    raise ValueError(
        f"Unsupported corruption type: {corruption!r}"
    )