from pathlib import Path

from modules import run_worker


def test_create_worker_status_manifest_records_deadline_and_reference_status(tmp_path: Path):
    status = run_worker.create_worker_status_manifest(
        output_dir=tmp_path,
        worker_name="version_b",
        role="experimental",
        deadline_seconds=1800,
    )

    assert status["worker_name"] == "version_b"
    assert status["role"] == "experimental"
    assert status["state"] == "pending"
    assert status["reference_status"] == "not_available"
    assert status["used_for_final_verdict"] is False
    assert status["deadline_seconds"] == 1800
    assert status["deadline_at"]
    assert status["output_dir"] == str(tmp_path.resolve())
    assert (tmp_path / run_worker.WORKER_STATUS_FILE).exists()


def test_update_worker_status_records_heartbeat_step_stage_and_field(tmp_path: Path):
    run_worker.create_worker_status_manifest(
        output_dir=tmp_path,
        worker_name="version_a",
        role="primary",
        deadline_seconds=1200,
    )

    updated = run_worker.update_worker_status(
        tmp_path,
        state="running",
        current_step=6,
        current_stage="copy_generation",
        current_field="description",
    )

    assert updated["state"] == "running"
    assert updated["heartbeat_at"]
    assert updated["current_step"] == 6
    assert updated["current_stage"] == "copy_generation"
    assert updated["current_field"] == "description"


def test_mark_worker_terminal_state_sets_reference_for_timeout(tmp_path: Path):
    run_worker.create_worker_status_manifest(
        output_dir=tmp_path,
        worker_name="version_b",
        role="experimental",
        deadline_seconds=1800,
    )

    final = run_worker.mark_worker_terminal_state(
        tmp_path,
        state="timed_out",
        error="deadline_exceeded",
        termination={"terminate_sent": True, "kill_sent": True},
    )

    assert final["state"] == "timed_out"
    assert final["reference_status"] == "not_available"
    assert final["reference_reason"] == "version_b timed out after 1800 seconds"
    assert final["termination"]["kill_sent"] is True


def test_run_worker_job_marks_success_and_writes_output_paths(tmp_path: Path, monkeypatch):
    def _fake_run_generator_workflow(*args, **kwargs):
        output_dir = Path(args[1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "generated_copy.json").write_text("{}", encoding="utf-8")
        (output_dir / "risk_report.json").write_text("{}", encoding="utf-8")
        (output_dir / "scoring_results.json").write_text("{}", encoding="utf-8")
        (output_dir / "execution_summary.json").write_text("{}", encoding="utf-8")
        callback = kwargs.get("status_callback")
        if callback:
            callback({"event": "step_started", "step": 6, "stage_label": "copy_generation", "field": "title"})
        return {"summary": {"workflow_status": "success"}}

    monkeypatch.setattr(run_worker, "run_generator_workflow", _fake_run_generator_workflow)

    result = run_worker.run_worker_job(
        worker_name="version_a",
        role="primary",
        config_path="config/run_configs/H91lite_US.json",
        output_dir=tmp_path,
        steps=[0, 6, 8],
        deadline_seconds=1200,
    )

    status = run_worker.read_worker_status(tmp_path)
    assert result["state"] == "success"
    assert status["state"] == "success"
    assert status["generated_copy_path"].endswith("generated_copy.json")
    assert status["reference_status"] == "primary_result"
    assert status["used_for_final_verdict"] is True
