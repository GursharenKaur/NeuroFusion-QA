from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from .identity import Finding
from .manifest import ManifestRecord

SYNTHETIC_NAMESPACE = "synthetic:identityguard"
SYNTHETIC_VERSION = "1.0"

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

    localized_operation_keys = {
        _freeze_key(key)
        for finding in findings
        if any(
            isinstance(evidence, dict)
            and evidence.get("row_index") in operation_rows
            for evidence in finding.evidence_rows
        )
        for key in finding.affected_keys
    }

    true_positive_keys |= localized_operation_keys

    false_positive_keys = localized_keys - true_positive_keys

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