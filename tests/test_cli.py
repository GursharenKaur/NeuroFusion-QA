import json
from pathlib import Path

from neurofusion_qa.cli import main


def write_manifest(path: Path, rows: list[list[str]]) -> None:
    header = [
        "dataset_namespace",
        "dataset_version",
        "participant_id",
        "session_id",
        "modality",
        "source_path",
        "source_sha256",
        "split",
    ]

    lines = [
        "\t".join(header),
        *("\t".join(row) for row in rows),
    ]

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def write_config(path: Path) -> None:
    path.write_text(
        "protocol:\n  name: test\n",
        encoding="utf-8",
    )


def test_cli_clean_manifest_returns_zero(tmp_path: Path):
    manifest = tmp_path / "manifest.tsv"

    write_manifest(
        manifest,
        [
            [
                "test",
                "1.0",
                "sub-01",
                "ses-01",
                "T1w",
                "sub-01_T1w.nii.gz",
                "hash-01",
                "train",
            ]
        ],
    )

    config = tmp_path / "config.yaml"
    write_config(config)

    json_output = tmp_path / "audit.json"
    tsv_output = tmp_path / "audit.tsv"
    markdown_output = tmp_path / "audit.md"

    exit_code = main(
        [
            "audit",
            str(manifest),
            "--config",
            str(config),
            "--json",
            str(json_output),
            "--tsv",
            str(tsv_output),
            "--markdown",
            str(markdown_output),
        ]
    )

    assert exit_code == 0
    assert json_output.exists()
    assert tsv_output.exists()
    assert markdown_output.exists()

    payload = json.loads(
        json_output.read_text(encoding="utf-8")
    )

    assert payload["provenance"]["manifest_sha256"]
    assert payload["provenance"]["config_sha256"]
    assert payload["provenance"]["code_hash"]


def test_cli_audit_error_returns_one(tmp_path: Path):
    manifest = tmp_path / "manifest.tsv"

    write_manifest(
        manifest,
        [
            [
                "test",
                "1.0",
                "sub-01",
                "ses-01",
                "T1w",
                "sub-01_T1w.nii.gz",
                "hash-01",
                "train",
            ],
            [
                "test",
                "1.0",
                "sub-01",
                "ses-01",
                "T1w",
                "sub-01_T1w_copy.nii.gz",
                "hash-02",
                "train",
            ],
        ],
    )

    config = tmp_path / "config.yaml"
    write_config(config)

    exit_code = main(
        [
            "audit",
            str(manifest),
            "--config",
            str(config),
            "--json",
            str(tmp_path / "audit.json"),
            "--tsv",
            str(tmp_path / "audit.tsv"),
            "--markdown",
            str(tmp_path / "audit.md"),
        ]
    )

    assert exit_code == 1


def test_cli_missing_manifest_returns_two(tmp_path: Path):
    config = tmp_path / "config.yaml"
    write_config(config)

    exit_code = main(
        [
            "audit",
            str(tmp_path / "does_not_exist.tsv"),
            "--config",
            str(config),
        ]
    )

    assert exit_code == 2