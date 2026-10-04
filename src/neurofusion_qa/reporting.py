from __future__ import annotations
import hashlib

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .identity import (
    Finding,
    check_i1_acquisition_key_injectivity,
    check_i1_canonicalization_collision,
    check_i1_namespace_completeness,
    check_i2_join_cardinality,
    check_i3_cross_modal_pairing,
    check_i5_split_independence,
    check_i6_metric_denominator_traceability,
)
from .lineage import (
    check_i4_derivative_lineage,
    check_i4_identical_derivative_hashes_under_different_keys,
    check_i4_identical_source_hashes_under_different_keys,
    check_i4_repeated_paths_or_rows,
)

@dataclass(frozen=True)
class AuditReport:
    """
    Machine-readable and human-readable representation of one audit.

    The report contains the findings produced by the IdentityGuard-BIDS
    invariant checks together with provenance metadata.

    The JSON/TSV/Markdown representations are implementation conventions
    for this project. The research specification requires JSON plus a
    human-readable TSV/Markdown summary and requires input/config/code
    provenance to be included.
    """

    findings: tuple[Finding, ...]
    manifest_hash: str | None = None
    config_hash: str | None = None
    code_hash: str | None = None
    generated_at: str | None = None

    def __post_init__(self) -> None:
        if self.generated_at is None:
            object.__setattr__(
                self,
                "generated_at",
                datetime.now(timezone.utc).isoformat(),
            )

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def error_count(self) -> int:
        return sum(
            1 for finding in self.findings
            if finding.severity == "ERROR"
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1 for finding in self.findings
            if finding.severity == "WARNING"
        )

    @property
    def info_count(self) -> int:
        return sum(
            1 for finding in self.findings
            if finding.severity == "INFO"
        )

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def raise_for_errors(self) -> None:
        """
        Raise RuntimeError when the audit contains an ERROR finding.

        This mirrors the research protocol's required non-zero failure
        behavior at the API level. CLI exit-code handling will be added
        separately.
        """
        if not self.has_errors:
            return

        rules = sorted(
            {finding.rule_id for finding in self.findings
             if finding.severity == "ERROR"}
        )

        raise RuntimeError(
            f"IdentityGuard-BIDS audit failed with "
            f"{self.error_count} ERROR finding(s): "
            f"{', '.join(rules)}"
        )

    def summary(self) -> dict[str, int]:
        """Return deterministic severity counts."""
        return {
            "total_findings": self.total_findings,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "infos": self.info_count,
        }

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the report to a JSON-compatible dictionary.

        Finding values are normalized recursively so tuples and other
        structured values remain deterministic and JSON serializable.
        """
        return {
            "report_version": "1.0",
            "generated_at": self.generated_at,
            "provenance": {
                "manifest_sha256": self.manifest_hash,
                "config_sha256": self.config_hash,
                "code_hash": self.code_hash,
            },
            "summary": self.summary(),
            "findings": [
                _normalize(finding)
                for finding in self.findings
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Return the complete report as deterministic JSON text."""
        return json.dumps(
            self.to_dict(),
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
        )

    def write_json(self, path: Path) -> None:
        """Write the machine-readable JSON report."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.to_json() + "\n",
            encoding="utf-8",
        )

    def to_tsv(self) -> str:
        """
        Return one TSV row per finding.

        Structured finding fields are represented as compact JSON so the
        TSV retains the exact evidence without introducing a second
        ad-hoc serialization format.
        """
        headers = [
            "rule_id",
            "severity",
            "message",
            "key_type",
            "affected_keys",
            "expected",
            "observed",
            "evidence_rows",
            "remediation",
        ]

        rows = ["\t".join(headers)]

        for finding in self.findings:
            values = [
                finding.rule_id,
                finding.severity,
                finding.message,
                finding.key_type,
                _compact_json(finding.affected_keys),
                _compact_json(finding.expected),
                _compact_json(finding.observed),
                _compact_json(finding.evidence_rows),
                finding.remediation,
            ]

            rows.append(
                "\t".join(_tsv_escape(value) for value in values)
            )

        return "\n".join(rows) + "\n"

    def write_tsv(self, path: Path) -> None:
        """Write the human/analysis-friendly TSV report."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.to_tsv(),
            encoding="utf-8",
        )

    def to_markdown(self) -> str:
        """Return a concise human-readable Markdown report."""
        lines = [
            "# IdentityGuard-BIDS Audit Report",
            "",
            "## Summary",
            "",
            f"- Total findings: {self.total_findings}",
            f"- Errors: {self.error_count}",
            f"- Warnings: {self.warning_count}",
            f"- Infos: {self.info_count}",
            "",
            "## Provenance",
            "",
            f"- Generated at: `{self.generated_at}`",
            f"- Manifest SHA-256: `{self.manifest_hash}`",
            f"- Config SHA-256: `{self.config_hash}`",
            f"- Code hash: `{self.code_hash}`",
            "",
            "## Findings",
            "",
        ]

        if not self.findings:
            lines.append("No findings.")
            lines.append("")
            return "\n".join(lines)

        lines.extend(
            [
                "| Rule | Severity | Key type | Message |",
                "|---|---|---|---|",
            ]
        )

        for finding in self.findings:
            lines.append(
                "| "
                f"{_markdown_escape(finding.rule_id)} | "
                f"{_markdown_escape(finding.severity)} | "
                f"{_markdown_escape(finding.key_type)} | "
                f"{_markdown_escape(finding.message)} |"
            )

        lines.append("")

        for index, finding in enumerate(self.findings, start=1):
            lines.extend(
                [
                    f"### Finding {index}: `{finding.rule_id}`",
                    "",
                    f"**Severity:** `{finding.severity}`",
                    "",
                    f"**Message:** {finding.message}",
                    "",
                    f"**Affected keys:** `{_compact_json(finding.affected_keys)}`",
                    "",
                    f"**Expected:** `{_compact_json(finding.expected)}`",
                    "",
                    f"**Observed:** `{_compact_json(finding.observed)}`",
                    "",
                    f"**Evidence rows:** `{_compact_json(finding.evidence_rows)}`",
                    "",
                    f"**Remediation:** {finding.remediation}",
                    "",
                ]
            )

        return "\n".join(lines)

    def write_markdown(self, path: Path) -> None:
        """Write the human-readable Markdown report."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.to_markdown(),
            encoding="utf-8",
        )


def _normalize(value: Any) -> Any:
    """
    Recursively convert project values into JSON-compatible primitives.
    """
    if value is None:
        return None

    if isinstance(value, Path):
        return value.as_posix()

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(
                value.items(),
                key=lambda item: str(item[0]),
            )
        }

    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]

    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                ensure_ascii=False,
            ),
        )

    if hasattr(value, "__dataclass_fields__"):
        return _normalize(asdict(value))

    return str(value)


def _compact_json(value: Any) -> str:
    """Serialize a structured value deterministically for TSV/Markdown."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _tsv_escape(value: Any) -> str:
    """
    Make a value safe for a single TSV cell.

    Tabs/newlines are escaped rather than allowed to corrupt the row
    structure.
    """
    text = str(value)
    return (
        text
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _markdown_escape(value: Any) -> str:
    """Escape characters that would break the Markdown table."""
    return str(value).replace("|", "\\|").replace("\n", " ")

def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest of one file."""
    digest = hashlib.sha256()

    with Path(path).open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def sha256_source_tree(source_root: str | Path) -> str:
    """
    Return a deterministic SHA-256 digest of a Python source tree.

    Files are ordered by relative POSIX path. Each file contributes its
    relative path followed by its raw bytes.
    """
    root = Path(source_root).resolve()

    if not root.is_dir():
        raise ValueError(f"Source root does not exist: {root}")

    files = sorted(
        path
        for path in root.rglob("*.py")
        if path.is_file()
    )

    digest = hashlib.sha256()

    for path in files:
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative_path)
        digest.update(b"\0")

        with path.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)

        digest.update(b"\0")

    return digest.hexdigest()

def audit_manifest(
    records: list[Any],
    *,
    join_checks: Iterable[dict[str, Any]] | None = None,
    cross_modal_pairs: Iterable[Any] | None = None,
    crosswalk: Any | None = None,
    metrics: Iterable[dict[str, Any]] | None = None,
    populations: dict[Any, Any] | None = None,
    grouping_variables: dict[str, Any] | None = None,
    manifest_hash: str | None = None,
    config_hash: str | None = None,
    code_hash: str | None = None,
) -> AuditReport:
    """
    Run the IdentityGuard-BIDS invariant checks over a manifest.

    The manifest itself is sufficient for the checks whose evidence is
    represented directly by ManifestRecord fields:

        I1, I4, I5

    Supplemental inputs are required for invariants whose evidence is
    represented outside the base manifest:

        I2 -> join_checks
        I3 -> cross_modal_pairs
        I6 -> metrics + populations

    This explicit-input convention is intentional. The current research
    protocol does not define a concrete serialized schema for these
    supplemental relation/analysis tables, so the audit engine does not
    invent one or infer missing evidence from ordinary manifest rows.

    Parameters
    ----------
    records:
        Manifest records to audit.

    join_checks:
        Explicit join-cardinality specifications for I2.

    cross_modal_pairs:
        Explicit cross-modal pair records for I3.

    crosswalk:
        Optional authoritative crosswalk passed directly to I3.

    metrics:
        Explicit analysis metrics for I6.

    populations:
        Explicit metric populations for I6.

    grouping_variables:
        Optional grouping-variable mapping used by the existing I5
        implementation.
    """
    findings: list[Finding] = []

    # ---------------------------------------------------------
    # I1 — Identity completeness / injectivity
    # ---------------------------------------------------------

    findings.extend(
        check_i1_namespace_completeness(records)
    )

    findings.extend(
        check_i1_acquisition_key_injectivity(records)
    )

    findings.extend(
        check_i1_canonicalization_collision(records)
    )

    # ---------------------------------------------------------
    # I2 — Join cardinality
    #
    # Only evaluate when an explicit relation specification has
    # been supplied. Do not infer a join relationship from rows.
    # ---------------------------------------------------------

    if join_checks is not None:
        for join_check in join_checks:
            findings.extend(
                check_i2_join_cardinality(**join_check)
            )

    # ---------------------------------------------------------
    # I3 — Cross-modal pairing
    #
    # Pairing evidence must be explicit. No string-similarity
    # or row-order inference is performed here.
    # ---------------------------------------------------------

    if cross_modal_pairs is not None:
        findings.extend(
            check_i3_cross_modal_pairing(
                cross_modal_pairs,
                crosswalk=crosswalk,
            )
        )

    # ---------------------------------------------------------
    # I4 — Derivative lineage / duplication
    # ---------------------------------------------------------

    findings.extend(
        check_i4_identical_source_hashes_under_different_keys(
            records
        )
    )

    findings.extend(
        check_i4_identical_derivative_hashes_under_different_keys(
            records
        )
    )

    findings.extend(
        check_i4_repeated_paths_or_rows(records)
    )

    findings.extend(
        check_i4_derivative_lineage(records)
    )

    # ---------------------------------------------------------
    # I5 — Split independence
    # ---------------------------------------------------------

    findings.extend(
        check_i5_split_independence(
            records,
            grouping_variables=grouping_variables,
        )
    )

    # ---------------------------------------------------------
    # I6 — Metric denominator traceability
    #
    # Both metrics and populations are required because neither
    # alone provides enough evidence to audit denominator
    # traceability.
    # ---------------------------------------------------------

    if metrics is not None or populations is not None:
        if metrics is None or populations is None:
            raise ValueError(
                "I6 requires both metrics and populations."
            )

        findings.extend(
            check_i6_metric_denominator_traceability(
                records,
                metrics,
                populations,
            )
        )

    return AuditReport(
        findings=tuple(findings),
        manifest_hash=manifest_hash,
        config_hash=config_hash,
        code_hash=code_hash,
    )