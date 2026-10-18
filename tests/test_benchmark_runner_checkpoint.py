
import json

import pytest

from scripts.run_collision_benchmark import (
    initialize_checkpoint,
    validate_checkpoint_identity,
    write_checkpoint_atomic,
)


def test_initialize_checkpoint_records_run_identity(tmp_path):
    checkpoint = initialize_checkpoint(
        output_root=tmp_path,
        config_sha256="config-hash",
        selected_experiment_ids=["job-1", "job-2"],
        mode="subset",
    )

    assert checkpoint["schema_version"] == 1
    assert checkpoint["config_sha256"] == "config-hash"
    assert checkpoint["selected_experiment_ids"] == ["job-1", "job-2"]
    assert checkpoint["mode"] == "subset"
    assert checkpoint["completed_results"] == []
    assert checkpoint["failures"] == []


def test_checkpoint_identity_accepts_exact_match():
    validate_checkpoint_identity(
        {
            "schema_version": 1,
            "config_sha256": "config-hash",
            "selected_experiment_ids": ["job-1", "job-2"],
        },
        "config-hash",
        ["job-1", "job-2"],
    )


@pytest.mark.parametrize(
    ("checkpoint", "config_hash", "job_ids", "message"),
    [
        (
            {
                "schema_version": 1,
                "config_sha256": "old-hash",
                "selected_experiment_ids": ["job-1"],
            },
            "new-hash",
            ["job-1"],
            "configuration hash",
        ),
        (
            {
                "schema_version": 1,
                "config_sha256": "config-hash",
                "selected_experiment_ids": ["job-1"],
            },
            "config-hash",
            ["job-1", "job-2"],
            "job selection",
        ),
        (
            {
                "schema_version": 99,
                "config_sha256": "config-hash",
                "selected_experiment_ids": ["job-1"],
            },
            "config-hash",
            ["job-1"],
            "schema",
        ),
    ],
)
def test_checkpoint_identity_rejects_mismatch(
    checkpoint, config_hash, job_ids, message
):
    with pytest.raises(RuntimeError, match=message):
        validate_checkpoint_identity(checkpoint, config_hash, job_ids)


def test_checkpoint_is_written_as_valid_json(tmp_path):
    checkpoint = {
        "schema_version": 1,
        "config_sha256": "config-hash",
        "selected_experiment_ids": ["job-1"],
        "completed_results": [],
        "failures": [],
    }

    path = write_checkpoint_atomic(tmp_path, checkpoint)

    assert path.name == "run_checkpoint.json"
    assert json.loads(path.read_text(encoding="utf-8")) == checkpoint
    assert not (tmp_path / ".run_checkpoint.json.tmp").exists()


def test_existing_checkpoint_is_not_silently_overwritten(tmp_path):
    original = {
        "schema_version": 1,
        "config_sha256": "config-hash",
        "selected_experiment_ids": ["job-1"],
        "completed_results": [],
        "failures": [],
    }
    path = write_checkpoint_atomic(tmp_path, original)

    with pytest.raises(RuntimeError, match="already exists"):
        initialize_checkpoint(
            output_root=tmp_path,
            config_sha256="config-hash",
            selected_experiment_ids=["job-1"],
            mode="subset",
        )

    assert json.loads(path.read_text(encoding="utf-8")) == original


from types import SimpleNamespace

import scripts.run_collision_benchmark as runner


def _fake_job(experiment_id):
    return SimpleNamespace(
        experiment_id=experiment_id,
        people=16,
        corruption="C1_namespace_stripping",
        severity=0.01,
        affected_count=1,
        seed=7,
    )


def _fake_result(experiment_id):
    return SimpleNamespace(
        experiment_id=experiment_id,
        job_directory=f"jobs/{experiment_id}",
        runtime_seconds=0.1,
        peak_memory_bytes=1024,
        detection={"detected": True},
        output_hashes={"result.json": "fake-hash"},
    )


def _write_test_config(path):
    path.write_text(
        "protocol:\n"
        "  status: draft_until_G1\n"
        "  approved_by: '[PI]'\n"
        "  approved_date: null\n",
        encoding="utf-8",
    )


def test_main_persists_successful_job_and_preserves_summary_schema(
    tmp_path, monkeypatch
):
    config = tmp_path / "protocol.yaml"
    _write_test_config(config)
    output_root = tmp_path / "output"

    jobs = [_fake_job("job-1"), _fake_job("job-2")]
    monkeypatch.setattr(runner, "generate_benchmark_jobs", lambda **kwargs: jobs)
    monkeypatch.setattr(
        runner, "run_benchmark_job",
        lambda job, **kwargs: _fake_result(job.experiment_id),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_collision_benchmark.py",
            "--config", str(config),
            "--output-root", str(output_root),
            "--smoke",
            "--limit", "2",
        ],
    )

    assert runner.main() == 0

    checkpoint = json.loads(
        (output_root / "run_checkpoint.json").read_text(encoding="utf-8")
    )
    assert [item["experiment_id"] for item in checkpoint["completed_results"]] == [
        "job-1", "job-2"
    ]
    assert checkpoint["failures"] == []

    summaries = list(output_root.glob("run_summary_*.json"))
    assert len(summaries) == 1
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert set(summary) == {
        "run_started_utc",
        "run_finished_utc",
        "elapsed_seconds",
        "config_path",
        "output_root",
        "mode",
        "selected_jobs",
        "completed_jobs",
        "failed_jobs",
        "results",
        "failures",
    }
    assert summary["completed_jobs"] == 2
    assert summary["failed_jobs"] == 0


def test_main_records_failed_job_and_continues(
    tmp_path, monkeypatch
):
    config = tmp_path / "protocol.yaml"
    _write_test_config(config)
    output_root = tmp_path / "output"

    jobs = [_fake_job("job-1"), _fake_job("job-2")]
    monkeypatch.setattr(runner, "generate_benchmark_jobs", lambda **kwargs: jobs)

    def fake_run(job, **kwargs):
        if job.experiment_id == "job-1":
            raise ValueError("simulated failure")
        return _fake_result(job.experiment_id)

    monkeypatch.setattr(runner, "run_benchmark_job", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_collision_benchmark.py",
            "--config", str(config),
            "--output-root", str(output_root),
            "--smoke",
            "--limit", "2",
        ],
    )

    assert runner.main() == 1

    checkpoint = json.loads(
        (output_root / "run_checkpoint.json").read_text(encoding="utf-8")
    )
    assert [item["experiment_id"] for item in checkpoint["completed_results"]] == [
        "job-2"
    ]
    assert len(checkpoint["failures"]) == 1
    assert checkpoint["failures"][0]["experiment_id"] == "job-1"
    assert checkpoint["failures"][0]["error_type"] == "ValueError"


def test_main_stops_if_checkpoint_persistence_fails(
    tmp_path, monkeypatch
):
    config = tmp_path / "protocol.yaml"
    _write_test_config(config)
    output_root = tmp_path / "output"

    jobs = [_fake_job("job-1")]
    monkeypatch.setattr(runner, "generate_benchmark_jobs", lambda **kwargs: jobs)

    executed = []
    monkeypatch.setattr(
        runner,
        "run_benchmark_job",
        lambda job, **kwargs: executed.append(job.experiment_id)
        or _fake_result(job.experiment_id),
    )
    monkeypatch.setattr(
        runner,
        "write_checkpoint_atomic",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_collision_benchmark.py",
            "--config", str(config),
            "--output-root", str(output_root),
            "--smoke",
            "--limit", "1",
        ],
    )

    assert runner.main() == 2

    # Initial checkpoint persistence fails before any benchmark job starts.
    assert executed == []


def test_main_stops_after_post_job_checkpoint_failure(
    tmp_path, monkeypatch, capsys
):
    config = tmp_path / "protocol.yaml"
    _write_test_config(config)
    output_root = tmp_path / "output"

    jobs = [_fake_job("job-1"), _fake_job("job-2")]
    monkeypatch.setattr(
        runner, "generate_benchmark_jobs", lambda **kwargs: jobs
    )

    executed = []

    def fake_run(job, **kwargs):
        executed.append(job.experiment_id)
        return _fake_result(job.experiment_id)

    monkeypatch.setattr(runner, "run_benchmark_job", fake_run)

    checkpoint_writes = 0

    def fake_write_checkpoint(*args, **kwargs):
        nonlocal checkpoint_writes
        checkpoint_writes += 1

        # Initial checkpoint succeeds; first post-job write fails.
        if checkpoint_writes == 2:
            raise OSError("simulated disk failure")

        return output_root / "run_checkpoint.json"

    monkeypatch.setattr(
        runner, "write_checkpoint_atomic", fake_write_checkpoint
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_collision_benchmark.py",
            "--config", str(config),
            "--output-root", str(output_root),
            "--smoke",
            "--limit", "2",
        ],
    )

    assert runner.main() == 2
    assert executed == ["job-1"]

    captured = capsys.readouterr()
    assert "Checkpoint persistence failed" in captured.err
    assert "simulated disk failure" in captured.err
