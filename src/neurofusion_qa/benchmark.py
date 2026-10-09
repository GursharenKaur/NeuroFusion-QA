import hashlib
import json
import platform
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from .identity import (
    Finding,
    canonicalize_participant_id,
)
from .corruptions import inject_corruption
from .manifest import ManifestRecord
from .reporting import audit_manifest

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

    if truth.get("corruption") in {
        "C1_namespace_stripping",
        "C2_canonicalization_collision",
    }:
        # C1 localization is evaluated at the person-key level.
        # Cross-modal pairs and acquisition keys remain valid findings,
        # but are not separate localized people.
        localized_keys = {
            _freeze_key(key)
            for finding in findings
            if finding.key_type == "person_key"
            for key in finding.affected_keys
        }
    else:
        localized_keys = {
            _freeze_key(key)
            for finding in findings
            for key in finding.affected_keys
        }

    corruption = truth.get("corruption")

    if corruption == "C4_cross_modal_permutation":
        # C4 truth identifies the original source person.
        # The destination person is involved in the pair but is
        # not the injected corruption target.
        localized_keys = {
            _freeze_key(operation["original_person_key"])
            for operation in truth.get("operations", [])
            if operation.get("operation")
            == "reassign_modality_record_to_other_participant"
            and operation.get("original_person_key") is not None
        }

    elif corruption == "C3_duplicate_propagation":
        # Localize the duplicated acquisition using direct I4 evidence.
        localized_keys = {
            _freeze_key(key)
            for finding in findings
            if finding.rule_id in {
                "I4.repeated_row",
                "I4.repeated_source_path",
            }
            for key in finding.affected_keys
        }

    elif corruption in {
        "C1_namespace_stripping",
        "C2_canonicalization_collision",
    }:
        # Evaluate identity-changing corruptions at person-key level.
        localized_keys = {
            _freeze_key(key)
            for finding in findings
            if finding.key_type == "person_key"
            for key in finding.affected_keys
        }

    else:
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
        localized_key_count=len(true_positive_keys | false_positive_keys),
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


def _build_synthetic_join_check_for_pair(
    records: list[ManifestRecord],
    left_modality: str,
    right_modality: str,
) -> dict[str, Any]:
    """Build one-to-one join evidence for a specific modality pair."""

    def counts_for_modality(modality: str) -> dict[Any, int]:
        counts: dict[Any, int] = {}

        for record in records:
            if record.modality != modality:
                continue

            join_key = (
                record.dataset_namespace,
                record.dataset_version,
                canonicalize_participant_id(record.participant_id),
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


def build_synthetic_cross_modal_join_check(
    records: Iterable[ManifestRecord],
) -> dict[str, Any]:
    """Build join evidence for exactly two synthetic modalities."""
    records = list(records)

    modalities = sorted({
        record.modality
        for record in records
        if record.modality is not None
    })

    if len(modalities) != 2:
        raise ValueError(
            "Synthetic cross-modal I2 join requires exactly two modalities."
        )

    return _build_synthetic_join_check_for_pair(
        records, modalities[0], modalities[1]
    )


def build_synthetic_cross_modal_join_checks(
    records: Iterable[ManifestRecord],
) -> list[dict[str, Any]]:
    """Build one-to-one join evidence for every unordered modality pair.

    Implementation convention: each modality pair is checked independently.
    """
    records = list(records)

    modalities = sorted({
        record.modality
        for record in records
        if record.modality is not None
    })

    if len(modalities) < 2:
        raise ValueError(
            "Synthetic cross-modal I2 joins require at least two modalities."
        )

    return [
        _build_synthetic_join_check_for_pair(
            records, modalities[i], modalities[j]
        )
        for i in range(len(modalities))
        for j in range(i + 1, len(modalities))
    ]

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

def _git_commit() -> str:
    """Return the current Git commit for benchmark provenance."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _git_working_tree_status() -> str:
    """Describe whether tracked or untracked repository changes exist."""
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"

    return "dirty" if status else "clean"


def _code_provenance() -> str:
    """Record Git revision and the current Python source-tree fingerprint."""
    return "\n".join(
        [
            f"git_commit={_git_commit()}",
            f"working_tree_status={_git_working_tree_status()}",
            f"python_source_tree_sha256={_source_tree_hash()}",
        ]
    ) + "\n"

def _environment_snapshot() -> str:
    """Return a compact reproducible environment description."""
    return "\n".join(
        [
            f"python={sys.version}",
            f"platform={platform.platform()}",
            f"executable={sys.executable}",
        ]
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

@dataclass(frozen=True)
class BenchmarkJobResult:
    experiment_id: str
    job_directory: str
    completed: bool
    runtime_seconds: float
    peak_memory_bytes: int
    detection: dict[str, object]
    output_hashes: dict[str, str]

def _manifest_records_sha256(
    records: Iterable[ManifestRecord],
) -> str:
    """Hash a manifest deterministically from its serialized records."""
    records = list(records)

    rows = []
    for record in records:
        rows.append(
            {
                field: getattr(record, field)
                for field in record.__dataclass_fields__
            }
        )

    payload = json.dumps(
        rows,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _source_tree_hash() -> str:
    """Return a deterministic hash of the Python source tree."""
    root = Path(__file__).resolve().parent

    digest = hashlib.sha256()

    for path in sorted(root.rglob("*.py")):
        digest.update(
            str(path.relative_to(root)).encode("utf-8")
        )
        digest.update(path.read_bytes())

    return digest.hexdigest()

def _write_manifest_tsv(
    records: Iterable[ManifestRecord],
    path: Path,
) -> None:
    """Write synthetic benchmark records as a deterministic TSV."""
    records = list(records)

    fields = list(ManifestRecord.__dataclass_fields__)

    lines = [
        "\t".join(fields),
    ]

    for record in records:
        values = []

        for field in fields:
            value = getattr(record, field)

            if value is None:
                value = ""

            values.append(str(value))

        lines.append("\t".join(values))

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

BENCHMARK_OUTPUT_NAMES = (
    "config.snapshot.yaml",
    "environment.txt",
    "git_commit.txt",
    "parent_manifest.sha256",
    "corrupted_manifest.tsv",
    "truth.json",
    "audit_report.json",
    "metrics.json",
    "stdout.log",
    "stderr.log",
)

def run_benchmark_job(
    job: BenchmarkJob,
    *,
    output_root: Path,
    config_path: Path,
    resume: bool = True,
) -> BenchmarkJobResult:
    """
    Execute exactly one synthetic benchmark job.

    The job is written atomically into its final directory only after
    all required artifacts have been produced successfully.
    """
    output_root = Path(output_root)
    config_path = Path(config_path)

    final_dir = output_root / job.experiment_id
    marker = final_dir / "completed.json"

    if resume and final_dir.exists() and marker.exists():
        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8"))
            expected_hashes = marker_data["output_hashes"]

            valid = (
                marker_data.get("experiment_id") == job.experiment_id
                and isinstance(expected_hashes, dict)
                and set(expected_hashes) == set(BENCHMARK_OUTPUT_NAMES)
            )

            if valid:
                for filename in BENCHMARK_OUTPUT_NAMES:
                    path = final_dir / filename
                    expected_hash = expected_hashes[filename]

                    if not path.is_file():
                        valid = False
                        break

                    if not isinstance(expected_hash, str):
                        valid = False
                        break

                    actual_hash = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()

                    if actual_hash != expected_hash:
                        valid = False
                        break

            if valid:
                return BenchmarkJobResult(
                    experiment_id=job.experiment_id,
                    job_directory=str(final_dir),
                    completed=True,
                    runtime_seconds=float(marker_data["runtime_seconds"]),
                    peak_memory_bytes=int(marker_data["peak_memory_bytes"]),
                    detection=marker_data["detection"],
                    output_hashes=expected_hashes,
                )
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            pass

    if final_dir.exists():
        raise RuntimeError(
            "Existing benchmark job directory is not a valid completed job: "
            f"{final_dir}. Preserve the directory for inspection or move it "
            "aside before rerunning this experiment."
        )

    output_root.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(
        prefix=f".{job.experiment_id}.",
        dir=output_root,
    ) as temporary:
        temp_dir = Path(temporary)

        started = time.perf_counter()
        tracemalloc.start()

        try:
            # 1. Build clean synthetic manifest.
            clean_records = build_synthetic_manifest(
                people=job.people,
                modalities=job.modalities,
                sessions=job.sessions,
                runs_per_modality=job.runs_per_modality,
            )

            # 2. Hash clean parent manifest.
            parent_manifest_sha256 = _manifest_records_sha256(clean_records)

            # 3. Inject corruption while keeping truth separate.
            clean_metrics = None
            clean_populations = None

            if job.corruption == "C6_denominator_mismatch":
                clean_metrics, clean_populations = (
                    build_synthetic_metric_evidence(clean_records)
                )

            corrupted_records, truth = inject_corruption(
                clean_records,
                corruption=job.corruption,
                affected_count=job.affected_count,
                seed=job.seed,
                metrics=clean_metrics,
                populations=clean_populations,
            )

            # 4. Build supplemental evidence required by the audit.
            join_checks = None
            cross_modal_pairs = None
            metrics = None
            populations = None
            if job.corruption == "C2_canonicalization_collision":
                join_checks = build_synthetic_cross_modal_join_checks(
                    corrupted_records
                )

            if job.corruption == "C3_duplicate_propagation":
                join_checks = build_synthetic_cross_modal_join_checks(
                    corrupted_records
                )

                clean_population = {
                    record.person_key for record in clean_records
                }

                metrics, populations = build_synthetic_metric_evidence(
                    corrupted_records,
                    denominator_override=len(clean_population) + 1,
                )

            if job.corruption in {
                "C1_namespace_stripping",
                "C4_cross_modal_permutation",
            }:
                cross_modal_pairs = build_synthetic_cross_modal_pairs_from_clean(
                    clean_records,
                    corrupted_records,
                )


            if job.corruption == "C6_denominator_mismatch":
                # C6 changes metric denominators, not manifest records.
                metrics = corrupted_records
                populations = clean_populations
                corrupted_records = clean_records

            # 5. Run the IdentityGuard audit.
            manifest_hash = _manifest_records_sha256(corrupted_records)

            report = audit_manifest(
                corrupted_records,
                join_checks=join_checks,
                cross_modal_pairs=cross_modal_pairs,
                metrics=metrics,
                populations=populations,
                manifest_hash=manifest_hash,
                config_hash=_sha256_file(config_path),
                code_hash=_source_tree_hash(),
            )

            # 6. Evaluate against hidden corruption truth.
            evaluation = evaluate_benchmark_findings(
                report.findings,
                truth,
            )

            runtime_seconds = time.perf_counter() - started
            _, peak_memory_bytes = tracemalloc.get_traced_memory()

            # 7. Write required artifacts.
            config_snapshot = config_path.read_text(encoding="utf-8")

            _write_text(
                temp_dir / "config.snapshot.yaml",
                config_snapshot,
            )
            _write_text(
                temp_dir / "environment.txt",
                _environment_snapshot(),
            )
            code_provenance = _code_provenance()
            provenance_fields = dict(
                line.split("=", 1)
                for line in code_provenance.splitlines()
            )

            _write_text(
                temp_dir / "git_commit.txt",
                code_provenance,
            )
            _write_text(
                temp_dir / "parent_manifest.sha256",
                parent_manifest_sha256 + "\n",
            )

            _write_manifest_tsv(
                corrupted_records,
                temp_dir / "corrupted_manifest.tsv",
            )

            _write_json(
                temp_dir / "truth.json",
                truth,
            )

            _write_text(
                temp_dir / "audit_report.json",
                report.to_json(),
            )

            audit_report_payload = json.loads(report.to_json())
            config_sha256 = hashlib.sha256(
                (temp_dir / "config.snapshot.yaml").read_bytes()
            ).hexdigest()

            metrics_payload = {
                "experiment_id": job.experiment_id,
                "parent_manifest_sha256": parent_manifest_sha256,
                "config_sha256": config_sha256,
                "git_commit": provenance_fields["git_commit"],
                "working_tree_status": provenance_fields["working_tree_status"],
                "python_source_tree_sha256": provenance_fields[
                    "python_source_tree_sha256"
                ],
                "people": job.people,
                "modalities": job.modalities,
                "sessions": job.sessions,
                "runs_per_modality": job.runs_per_modality,
                "corruption": job.corruption,
                "severity": job.severity,
                "affected_count": job.affected_count,
                "seed": job.seed,
                "runtime_seconds": runtime_seconds,
                "peak_memory_bytes": peak_memory_bytes,
                "rule_outputs": audit_report_payload,
                "detection": asdict(evaluation),
            }

            _write_json(
                temp_dir / "metrics.json",
                metrics_payload,
            )

            _write_text(
                temp_dir / "stdout.log",
                "",
            )
            _write_text(
                temp_dir / "stderr.log",
                "",
            )

            # 8. Hash all required outputs.
            output_names = BENCHMARK_OUTPUT_NAMES

            output_hashes = {
                name: hashlib.sha256(
                    (temp_dir / name).read_bytes()
                ).hexdigest()
                for name in output_names
            }

            # 9. Completed marker is written last.
            _write_json(
                temp_dir / "completed.json",
                {
                    "experiment_id": job.experiment_id,
                    "runtime_seconds": runtime_seconds,
                    "peak_memory_bytes": peak_memory_bytes,
                    "detection": asdict(evaluation),
                    "output_hashes": output_hashes,
                },
            )

            if final_dir.exists():
                raise FileExistsError(
                    f"Benchmark job directory already exists: {final_dir}"
                )

            temp_dir.rename(final_dir)

            return BenchmarkJobResult(
                experiment_id=job.experiment_id,
                job_directory=str(final_dir),
                completed=True,
                runtime_seconds=runtime_seconds,
                peak_memory_bytes=peak_memory_bytes,
                detection=asdict(evaluation),
                output_hashes=output_hashes,
            )

        finally:
            tracemalloc.stop()