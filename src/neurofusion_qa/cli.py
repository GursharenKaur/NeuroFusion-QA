from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .manifest import load_manifest_tsv
from .reporting import audit_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="identityguard",
        description="IdentityGuard-BIDS audit CLI.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    audit_parser = subparsers.add_parser(
        "audit",
        help="Run an IdentityGuard-BIDS manifest audit.",
    )

    audit_parser.add_argument(
        "manifest",
        type=Path,
        help="Path to the tabular manifest TSV.",
    )

    audit_parser.add_argument(
        "--json",
        dest="json_output",
        type=Path,
        default=Path("audit_report.json"),
        help="JSON report path.",
    )

    audit_parser.add_argument(
        "--tsv",
        dest="tsv_output",
        type=Path,
        default=Path("audit_report.tsv"),
        help="TSV report path.",
    )

    audit_parser.add_argument(
        "--markdown",
        dest="markdown_output",
        type=Path,
        default=Path("audit_report.md"),
        help="Markdown report path.",
    )

    return parser


def run_audit(args: argparse.Namespace) -> int:
    records = load_manifest_tsv(args.manifest)

    report = audit_manifest(records)

    report.write_json(args.json_output)
    report.write_tsv(args.tsv_output)
    report.write_markdown(args.markdown_output)

    print(
        "IdentityGuard-BIDS audit complete: "
        f"{report.total_findings} finding(s), "
        f"{report.error_count} error(s), "
        f"{report.warning_count} warning(s), "
        f"{report.info_count} info(s)."
    )

    if report.has_errors:
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "audit":
            return run_audit(args)

        parser.error(f"Unknown command: {args.command}")

    except (OSError, ValueError) as exc:
        print(
            f"IdentityGuard-BIDS error: {exc}",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())