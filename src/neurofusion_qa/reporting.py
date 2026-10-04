from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .identity import Finding


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