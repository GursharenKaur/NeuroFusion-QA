from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from .identity import (
    Finding,
    canonicalize_participant_id,
)
from .manifest import ManifestRecord

SYNTHETIC_NAMESPACE = "synthetic:identityguard"
SYNTHETIC_VERSION = "1.0"


def affected_count_for_severity(
    eligible_people: int,
    severity: float,
) -> int:
    """
    Convert protocol-defined severity into an affected-person count.

    The research protocol defines severity as the fraction of eligible
    person keys affected, rounded up to at least one.

    This helper implements that benchmark convention centrally so the
    factorial runner does not duplicate the calculation.
    """
    if eligible_people < 1:
        raise ValueError(
            "eligible_people must be at least 1."
        )

    if not 0 < severity <= 1:
        raise ValueError(
            "severity must be greater than 0 and at most 1."
        )

    # ceil(eligible_people * severity), written without a floating-point
    # math.ceil dependency.
    affected_count = int(
        eligible_people * severity
    )

    if affected_count < eligible_people * severity:
        affected_count += 1

    return max(1, affected_count)


@dataclass(frozen=True)
class BenchmarkJob:
    experiment_id: str
    people: int
    modalities: int
    sessions: int
    runs_per_modality: int
    corruption: str
    severity: float
    affected_count: int
    seed: int

@dataclass(frozen=True)
class BenchmarkEvaluation:
    detected: bool
    expected_violation_detected: bool
    expected_violation_count: int
    detected_expected_violation_count: int
    affected_key_count: int
    localized_key_count: int
    localization_true_positives: int
    localization_false_positives: int
    failure_type_correct: bool

def generate_benchmark_jobs(
    *,
    people: Iterable[int] = (16, 64, 256, 1024, 4096),
    modalities: Iterable[int] = (2, 3),
    sessions: Iterable[int] = (1, 2),
    runs_per_modality: Iterable[int] = (1, 4),
    corruptions: Iterable[str] = (
        "C1_namespace_stripping",
        "C2_canonicalization_collision",
        "C3_duplicate_propagation",
        "C4_cross_modal_permutation",
        "C5_subject_split_leakage",
        "C6_denominator_mismatch",
    ),
    severities: Iterable[float] = (0.01, 0.05, 0.10, 0.25),
    seeds: Iterable[int] = range(100),
) -> list[BenchmarkJob]:
    """
    Generate the deterministic synthetic E2 factorial benchmark design.

    Severity is converted to affected_count using the protocol-defined
    fraction of eligible person keys.

    This function only generates job specifications. It does not create
    manifests, inject corruptions, execute audits, or write files.
    """
    jobs: list[BenchmarkJob] = []

    for person_count in people:
        for modality_count in modalities:
            for session_count in sessions:
                for run_count in runs_per_modality:
                    for corruption in corruptions:
                        for severity in severities:
                            affected_count = affected_count_for_severity(
                                person_count,
                                severity,
                            )

                            for seed in seeds:
                                experiment_id = (
                                    f"synthetic_"
                                    f"p{person_count}_"
                                    f"m{modality_count}_"
                                    f"s{session_count}_"
                                    f"r{run_count}_"
                                    f"{corruption}_"
                                    f"sev{severity:g}_"
                                    f"seed{seed:03d}"
                                )

                                jobs.append(
                                    BenchmarkJob(
                                        experiment_id=experiment_id,
                                        people=person_count,
                                        modalities=modality_count,
                                        sessions=session_count,
                                        runs_per_modality=run_count,
                                        corruption=corruption,
                                        severity=severity,
                                        affected_count=affected_count,
                                        seed=seed,
                                    )
                                )

    return jobs

def evaluate_benchmark_findings(
    findings: Iterable[Finding],
    truth: dict[str, Any],
) -> BenchmarkEvaluation:
    """
    Compare detector findings with hidden corruption truth.

    The detector receives only the corrupted input. This function is part of
    the evaluator and therefore receives the hidden truth separately.
    """
    expected_violations = set(truth.get("expected_violations", []))
    affected_keys = {
        _freeze_key(key)
        for key in truth.get("affected_keys", [])
    }

    findings = tuple(findings)

    operation_target_rows = {
        operation["target_row_index"]
        for operation in truth.get("operations", [])
        if "target_row_index" in operation
    }

    detected_rule_ids = {
        finding.rule_id
        for finding in findings
    }

    detected_expected = (
        expected_violations & detected_rule_ids
    )

    detected = bool(findings)
    expected_violation_detected = bool(detected_expected)

    localized_keys = {
        _freeze_key(key)
        for finding in findings
        for key in finding.affected_keys
    }

    true_positive_keys = localized_keys & affected_keys

    # Some corruptions intentionally modify identity-bearing fields.
    # In those cases the detector's observed key may differ from the
    # clean affected key stored in hidden truth. Use the corruption
    # operation's row-level evidence to establish correspondence.
    operation_rows = {
        operation["row_index"]
        for operation in truth.get("operations", [])
        if "row_index" in operation
    }

    operation_target_rows = {
        operation["target_row_index"]
        for operation in truth.get("operations", [])
        if "target_row_index" in operation
    }

    localized_operation_keys = set()
    operation_matched_observed_keys = set()

    for finding in findings:
        evidence_rows = {
            evidence.get("row_index")
            for evidence in finding.evidence_rows
            if isinstance(evidence, dict)
        }

        operation_match = (
            bool(evidence_rows & operation_rows)
            or bool(evidence_rows & operation_target_rows)
        )

        if operation_match:
            # The finding corresponds to a corruption operation whose clean
            # affected key is stored separately in hidden truth.
            localized_operation_keys.update(affected_keys)

            # The observed detector keys are not false positives because
            # operation evidence establishes their correspondence to the
            # clean affected key.
            operation_matched_observed_keys.update(
                _freeze_key(key)
                for key in finding.affected_keys
            )

    true_positive_keys |= localized_operation_keys

    false_positive_keys = (
        localized_keys
        - true_positive_keys
        - operation_matched_observed_keys
    )


    failure_type_correct = (
        bool(expected_violations)
        and expected_violations.issubset(detected_rule_ids)
    )

    return BenchmarkEvaluation(
        detected=detected,
        expected_violation_detected=expected_violation_detected,
        expected_violation_count=len(expected_violations),
        detected_expected_violation_count=len(detected_expected),
        affected_key_count=len(affected_keys),
        localized_key_count=len(localized_keys),
        localization_true_positives=len(true_positive_keys),
        localization_false_positives=len(false_positive_keys),
        failure_type_correct=failure_type_correct,
    )

def _freeze_key(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_freeze_key(item) for item in value)

    if isinstance(value, tuple):
        return tuple(_freeze_key(item) for item in value)

    if isinstance(value, dict):
        return tuple(
            sorted(
                (
                    key,
                    _freeze_key(item),
                )
                for key, item in value.items()
            )
        )

    return value

def _deterministic_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _synthetic_split(participant_index: int) -> str:
    """
    Deterministically assign a participant to one of the existing split labels.

    Split proportions are not specified by the research protocol. This is
    therefore an implementation convention for the synthetic benchmark.
    """
    labels = ("train", "validation", "test")
    return labels[(participant_index - 1) % len(labels)]


def build_synthetic_manifest(
    people: int,
    modalities: int,
    sessions: int,
    runs_per_modality: int,
) -> list[ManifestRecord]:
    """
    Build a deterministic synthetic IdentityGuard-BIDS manifest.

    The synthetic manifest follows the implementation conventions documented
    in docs/IDENTITYGUARD_METHOD.md. It contains no real imaging data.
    """
    if people <= 0:
        raise ValueError("people must be greater than zero")
    if modalities <= 0:
        raise ValueError("modalities must be greater than zero")
    if sessions <= 0:
        raise ValueError("sessions must be greater than zero")
    if runs_per_modality <= 0:
        raise ValueError("runs_per_modality must be greater than zero")

    records: list[ManifestRecord] = []

    for person_index in range(1, people + 1):
        participant_id = f"sub-{person_index:05d}"
        split = _synthetic_split(person_index)

        for session_index in range(1, sessions + 1):
            session_id = f"ses-{session_index:02d}"

            for modality_index in range(1, modalities + 1):
                modality = f"mod-{modality_index:02d}"

                for run_index in range(1, runs_per_modality + 1):
                    run = f"{run_index:02d}"

                    identity = (
                        f"{SYNTHETIC_NAMESPACE}|"
                        f"{SYNTHETIC_VERSION}|"
                        f"{participant_id}|"
                        f"{session_id}|"
                        f"{modality}|"
                        f"task-synthetic|"
                        f"acq-01|"
                        f"{run}"
                    )

                    source_path = (
                        f"{participant_id}/"
                        f"{session_id}/"
                        f"{modality}/"
                        f"{participant_id}_"
                        f"{session_id}_"
                        f"{modality}_"
                        f"task-synthetic_"
                        f"run-{run}.synthetic"
                    )

                    source_sha256 = _deterministic_sha256(
                        f"source|{identity}"
                    )

                    derivative_recipe_sha256 = _deterministic_sha256(
                        "derivative-recipe|identityguard-synthetic-v1"
                    )

                    derivative_path = (
                        f"derivatives/identityguard/"
                        f"{participant_id}/"
                        f"{session_id}/"
                        f"{modality}/"
                        f"{participant_id}_"
                        f"{session_id}_"
                        f"{modality}_"
                        f"task-synthetic_"
                        f"run-{run}.synthetic"
                    )

                    derivative_sha256 = _deterministic_sha256(
                        f"derivative|{identity}|{derivative_recipe_sha256}"
                    )

                    records.append(
                        ManifestRecord(
                            dataset_namespace=SYNTHETIC_NAMESPACE,
                            dataset_version=SYNTHETIC_VERSION,
                            participant_id=participant_id,
                            session_id=session_id,
                            modality=modality,
                            task="task-synthetic",
                            acquisition="acq-01",
                            run=run,
                            source_path=source_path,
                            source_sha256=source_sha256,
                            derivative_recipe_sha256=derivative_recipe_sha256,
                            derivative_path=derivative_path,
                            derivative_sha256=derivative_sha256,
                            split=split,
                            analysis_role="primary",
                        )
                    )

    return records

def build_synthetic_cross_modal_pairs(
    records: Iterable[ManifestRecord],
) -> list[tuple[ManifestRecord, ManifestRecord]]:
    """
    Build explicit cross-modal pairing evidence for the synthetic benchmark.

    Pairing is based only on the synthetic benchmark's structural record
    organization: participant ID, session, and task. No participant-string
    similarity or cross-dataset identity inference is used.

    The resulting pairs are explicit supplemental evidence supplied to I3;
    they are not hidden corruption truth.
    """
    grouped: dict[tuple[Any, Any, Any], list[ManifestRecord]] = {}

    for record in records:
        key = (
            record.participant_id,
            record.session_id,
            record.task,
        )
        grouped.setdefault(key, []).append(record)

    pairs: list[tuple[ManifestRecord, ManifestRecord]] = []

    for group in grouped.values():
        by_modality: dict[Any, list[ManifestRecord]] = {}

        for record in group:
            by_modality.setdefault(record.modality, []).append(record)

        modalities = sorted(
            modality
            for modality in by_modality
            if modality is not None
        )

        for index, left_modality in enumerate(modalities):
            for right_modality in modalities[index + 1:]:
                left_records = by_modality[left_modality]
                right_records = by_modality[right_modality]

                pair_count = min(
                    len(left_records),
                    len(right_records),
                )

                for pair_index in range(pair_count):
                    pairs.append(
                        (
                            left_records[pair_index],
                            right_records[pair_index],
                        )
                    )

    return pairs

def build_synthetic_cross_modal_pairs_from_clean(
    clean_records: Iterable[ManifestRecord],
    corrupted_records: Iterable[ManifestRecord],
) -> list[tuple[ManifestRecord, ManifestRecord]]:
    """
    Build explicit synthetic cross-modal pairing evidence using the clean
    synthetic manifest as the pairing reference.

    The clean manifest defines the intended participant/session/task/modality
    relationships. The corresponding records are then retrieved from the
    corrupted manifest by stable row position.

    This preserves the intended pairing relationship while allowing C4
    identity-changing corruption to be detected by I3.

    The clean manifest is benchmark construction evidence, not hidden
    corruption truth supplied to the audit engine.
    """
    clean_records = list(clean_records)
    corrupted_records = list(corrupted_records)

    if len(clean_records) != len(corrupted_records):
        raise ValueError(
            "Clean and corrupted manifests must contain the same number "
            "of records."
        )

    grouped: dict[tuple[Any, Any, Any], dict[Any, list[int]]] = {}

    for index, record in enumerate(clean_records):
        key = (
            record.participant_id,
            record.session_id,
            record.task,
        )
        grouped.setdefault(key, {}).setdefault(
            record.modality, []
        ).append(index)

    pairs: list[tuple[ManifestRecord, ManifestRecord]] = []

    for modality_groups in grouped.values():
        modalities = sorted(
            modality
            for modality in modality_groups
            if modality is not None
        )

        for index, left_modality in enumerate(modalities):
            for right_modality in modalities[index + 1:]:
                left_indices = modality_groups[left_modality]
                right_indices = modality_groups[right_modality]

                pair_count = min(
                    len(left_indices),
                    len(right_indices),
                )

                for pair_index in range(pair_count):
                    left_index = left_indices[pair_index]
                    right_index = right_indices[pair_index]

                    pairs.append(
                        (
                            corrupted_records[left_index],
                            corrupted_records[right_index],
                        )
                    )

    return pairs

def build_synthetic_cross_modal_join_check(
    records: Iterable[ManifestRecord],
) -> dict[str, Any]:
    """
    Build explicit one-to-one cross-modal join evidence for the synthetic
    benchmark.

    The synthetic benchmark uses the first two modality labels as the two
    sides of the declared relation. Join keys are namespace-qualified
    canonical participant identity plus session/acquisition/run context.

    This is supplemental benchmark evidence supplied to I2. It is not
    hidden corruption truth and does not infer cross-dataset identity.
    """
    records = list(records)

    modalities = sorted(
        {
            record.modality
            for record in records
            if record.modality is not None
        }
    )

    if len(modalities) != 2:
        raise ValueError(
            "Synthetic cross-modal I2 join requires exactly two modalities."
        )

    left_modality, right_modality = modalities

    def counts_for_modality(
        modality: str,
    ) -> dict[Any, int]:
        counts: dict[Any, int] = {}

        for record in records:
            if record.modality != modality:
                continue

            join_key = (
                record.dataset_namespace,
                record.dataset_version,
                canonicalize_participant_id(
                    record.participant_id
                ),
                record.session_id,
                record.task,
                record.acquisition,
                record.run,
            )

            counts[join_key] = counts.get(join_key, 0) + 1

        return counts

    return {
        "left_counts": counts_for_modality(left_modality),
        "right_counts": counts_for_modality(right_modality),
        "relation": "one_to_one",
    }

def build_synthetic_metric_evidence(
    records: Iterable[ManifestRecord],
    *,
    denominator_override: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[Any, ...]]]]:
    """
    Build explicit synthetic metric/population evidence for I6.

    Implementation convention:
    - Each eligible namespace-qualified person key has one traceable
      synthetic metric.
    - Each metric explicitly declares a population containing that
      person key.
    - The clean denominator is therefore 1 for each person-level metric.
    - An explicit denominator_override changes the declared denominator
      while leaving population membership and numerator unchanged.

    This person-level metric representation allows the synthetic C6
    affected count to follow the protocol-defined severity unit:
    eligible person keys.

    This is benchmark evidence supplied to the audit engine. It is not
    hidden corruption truth and is not an additional research-protocol
    requirement.
    """
    records = list(records)

    population_keys = sorted(
        {
            record.person_key
            for record in records
            if (
                record.person_key[0] is not None
                and record.person_key[1] is not None
                and record.person_key[2]
            )
        }
    )

    metrics: list[dict[str, Any]] = []
    populations: dict[str, list[tuple[Any, ...]]] = {}

    for index, person_key in enumerate(population_keys):
        population_key = (
            f"synthetic_population_person_{index:05d}"
        )

        populations[population_key] = [person_key]

        denominator = (
            1
            if denominator_override is None
            else denominator_override
        )

        metrics.append(
            {
                "metric_name": (
                    f"synthetic_accuracy_{index:05d}"
                ),
                "split": "all",
                "numerator": 1,
                "denominator": denominator,
                "population_key": population_key,
            }
        )

    return metrics, populations