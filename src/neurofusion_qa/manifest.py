from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bids import BIDSLayout
import hashlib

@dataclass(frozen=True)
class ManifestRecord:
    """
    One row of the IdentityGuard-BIDS manifest.

    Raw BIDS identifiers are preserved exactly. Missing BIDS entities
    are represented as None rather than fabricated values.
    """

    dataset_namespace: str
    dataset_version: str
    participant_id: str

    session_id: Optional[str] = None
    modality: Optional[str] = None
    task: Optional[str] = None
    acquisition: Optional[str] = None
    run: Optional[str] = None

    source_path: Optional[str] = None
    source_sha256: Optional[str] = None

    derivative_recipe_sha256: Optional[str] = None
    derivative_path: Optional[str] = None
    derivative_sha256: Optional[str] = None

    split: Optional[str] = None
    analysis_role: Optional[str] = None

    @property
    def person_key(self) -> tuple[str, str, str]:
        """
        Canonical person key defined by the research protocol.
        """
        return (
            self.dataset_namespace,
            self.dataset_version,
            self.participant_id,
        )

    @property
    def acquisition_key(
        self,
    ) -> tuple[
        str,
        str,
        str,
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
    ]:
        """
        Canonical acquisition key defined by the research protocol.
        """
        return (
            self.dataset_namespace,
            self.dataset_version,
            self.participant_id,
            self.session_id,
            self.modality,
            self.task,
            self.acquisition,
            self.run,
        )


def record_from_bids_file(
    bids_file: Any,
    *,
    dataset_namespace: str,
    dataset_version: str,
) -> ManifestRecord:
    """
    Convert one PyBIDS BIDSFile into an IdentityGuard ManifestRecord.

    Raw BIDS participant labels are reconstructed with the ``sub-`` prefix
    because PyBIDS exposes the participant entity as its value only.
    """

    entities = bids_file.entities

    subject = entities.get("subject")
    if subject is None:
        raise ValueError(
            f"BIDS file does not contain a participant entity: {bids_file.path}"
        )

    return ManifestRecord(
        dataset_namespace=dataset_namespace,
        dataset_version=dataset_version,
        participant_id=f"sub-{subject}",
        session_id=_prefixed_entity(entities.get("session"), "ses-"),
        modality=entities.get("suffix"),
        task=_prefixed_entity(entities.get("task"), "task-"),
        acquisition=_prefixed_entity(
            entities.get("acquisition"),
            "acq-",
        ),
        run=_string_entity(entities.get("run")),
        source_path=_relative_posix_path(bids_file.path),
    )

def build_manifest_records(
    dataset_root: str | Path,
    *,
    dataset_namespace: str,
    dataset_version: str,
) -> list[ManifestRecord]:
    """
    Build deterministic manifest records from a BIDS dataset.

    The dataset is parsed with PyBIDS. Output records are sorted by
    normalized dataset-relative source path.
    """
    root = Path(dataset_root).resolve()

    layout = BIDSLayout(
        str(root),
        validate=True,
    )

    records: list[ManifestRecord] = []

    for bids_file in layout.get(return_type="object"):
        if bids_file.path is None:
            continue

        entities = bids_file.entities

        # Metadata files such as dataset_description.json do not carry
        # a participant entity and therefore are not manifest records.
        if entities.get("subject") is None:
            continue

        record = record_from_bids_file(
            bids_file,
            dataset_namespace=dataset_namespace,
            dataset_version=dataset_version,
        )

        relative_path = Path(bids_file.path).resolve().relative_to(root)

        records.append(
            ManifestRecord(
                dataset_namespace=record.dataset_namespace,
                dataset_version=record.dataset_version,
                participant_id=record.participant_id,
                session_id=record.session_id,
                modality=record.modality,
                task=record.task,
                acquisition=record.acquisition,
                run=record.run,
                source_path=relative_path.as_posix(),
                source_sha256=sha256_file(bids_file.path),
                derivative_recipe_sha256=record.derivative_recipe_sha256,
                derivative_path=record.derivative_path,
                derivative_sha256=record.derivative_sha256,
                split=record.split,
                analysis_role=record.analysis_role,
            )
        )

    records.sort(key=lambda record: record.source_path or "")

    return records

def sha256_file(
    path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> str:
    """
    Compute a file's SHA-256 digest using streaming chunks.
    """
    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        while chunk := file.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()

def _string_entity(value: Any) -> str | None:
    """Convert a PyBIDS entity value to a string without inventing values."""
    if value is None:
        return None

    return str(value)


def _prefixed_entity(value: Any, prefix: str) -> str | None:
    """Restore the BIDS entity label when PyBIDS exposes only its value."""
    if value is None:
        return None

    return f"{prefix}{value}"


def _relative_posix_path(path: str | Path) -> str:
    """
    Return a normalized POSIX path.

    Dataset-root-relative path handling will be added in the later
    manifest-builder increment.
    """
    return Path(path).as_posix()