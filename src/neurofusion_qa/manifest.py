from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bids import BIDSLayout


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