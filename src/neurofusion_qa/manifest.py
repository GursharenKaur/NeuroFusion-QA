from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bids import BIDSLayout
import hashlib
from datetime import datetime, timezone

import csv

@dataclass(frozen=True)
class ManifestMetadata:
    """
    Metadata describing one generated IdentityGuard-BIDS manifest.

    The field meanings are required by the research protocol. Exact
    implementation values are provisional conventions and may be revised
    if the project protocol is amended.
    """

    schema_version: str
    tool_version: str
    dataset_metadata_hash: str
    row_count: int
    generation_time: str

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
    metadata_only: bool = False,
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
                source_sha256=(
                    "not_retrieved"
                    if metadata_only
                    else sha256_file(bids_file.path)
                ),
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

def build_manifest_metadata(
    dataset_root: str | Path,
    *,
    row_count: int,
    schema_version: str = "1.0",
    tool_version: str = "0.1.0",
) -> ManifestMetadata:
    """
    Build metadata for a generated IdentityGuard-BIDS manifest.

    Provisional implementation conventions:
    - schema_version: "1.0"
    - tool_version: "0.1.0"
    - dataset metadata: dataset_description.json
    - generation_time: UTC ISO-8601
    """
    root = Path(dataset_root).resolve()
    metadata_path = root / "dataset_description.json"

    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"Missing BIDS dataset metadata file: {metadata_path}"
        )

    return ManifestMetadata(
        schema_version=schema_version,
        tool_version=tool_version,
        dataset_metadata_hash=sha256_file(metadata_path),
        row_count=row_count,
        generation_time=datetime.now(timezone.utc).isoformat(),
    )

def load_manifest_tsv(path: str | Path) -> list[ManifestRecord]:
    """
    Load an IdentityGuard-BIDS tabular manifest from TSV.

    This TSV representation is an implementation convention for the
    project. It uses the same fields as ManifestRecord and preserves
    empty optional values as None.
    """
    path = Path(path)

    required_columns = {
        "dataset_namespace",
        "dataset_version",
        "participant_id",
    }

    optional_columns = {
        "session_id",
        "modality",
        "task",
        "acquisition",
        "run",
        "source_path",
        "source_sha256",
        "derivative_recipe_sha256",
        "derivative_path",
        "derivative_sha256",
        "split",
        "analysis_role",
    }

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")

        if reader.fieldnames is None:
            raise ValueError("Manifest TSV has no header.")

        columns = set(reader.fieldnames)

        missing = required_columns - columns
        if missing:
            raise ValueError(
                "Manifest TSV is missing required columns: "
                + ", ".join(sorted(missing))
            )

        unknown = columns - required_columns - optional_columns
        if unknown:
            raise ValueError(
                "Manifest TSV contains unsupported columns: "
                + ", ".join(sorted(unknown))
            )

        records: list[ManifestRecord] = []

        for row_number, row in enumerate(reader, start=2):
            def value(column: str) -> str | None:
                raw = row.get(column)
                if raw is None or raw == "":
                    return None
                return raw

            namespace = value("dataset_namespace")
            version = value("dataset_version")
            participant = value("participant_id")

            if namespace is None:
                raise ValueError(
                    f"Manifest row {row_number} has an empty "
                    "dataset_namespace."
                )

            if version is None:
                raise ValueError(
                    f"Manifest row {row_number} has an empty "
                    "dataset_version."
                )

            if participant is None:
                raise ValueError(
                    f"Manifest row {row_number} has an empty "
                    "participant_id."
                )

            records.append(
                ManifestRecord(
                    dataset_namespace=namespace,
                    dataset_version=version,
                    participant_id=participant,
                    session_id=value("session_id"),
                    modality=value("modality"),
                    task=value("task"),
                    acquisition=value("acquisition"),
                    run=value("run"),
                    source_path=value("source_path"),
                    source_sha256=value("source_sha256"),
                    derivative_recipe_sha256=value(
                        "derivative_recipe_sha256"
                    ),
                    derivative_path=value("derivative_path"),
                    derivative_sha256=value("derivative_sha256"),
                    split=value("split"),
                    analysis_role=value("analysis_role"),
                )
            )

    return records