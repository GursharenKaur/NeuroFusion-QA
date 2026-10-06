from __future__ import annotations

import hashlib

from .manifest import ManifestRecord


SYNTHETIC_NAMESPACE = "synthetic:identityguard"
SYNTHETIC_VERSION = "1.0"


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