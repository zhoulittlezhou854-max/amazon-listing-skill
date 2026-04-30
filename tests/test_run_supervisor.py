from pathlib import Path

from modules import run_supervisor, run_worker


def test_build_worker_spec_sets_version_deadlines(tmp_path: Path):
    spec_a = run_supervisor.build_worker_spec(
        worker_name="version_a",
        run_config_path="config/run_configs/H91lite_US.json",
        output_dir=tmp_path / "version_a",
    )
    spec_b = run_supervisor.build_worker_spec(
        worker_name="version_b",
        run_config_path="config/run_configs/H91lite_US.json",
        output_dir=tmp_path / "version_b",
        blueprint_model_override="deepseek-v4-pro",
        title_model_override="deepseek-v4-pro",
        bullet_model_override="deepseek-v4-pro",
    )

    assert spec_a["deadline_seconds"] == 1200
    assert spec_a["role"] == "primary"
    assert spec_b["deadline_seconds"] == 1800
    assert spec_b["role"] == "experimental"
    assert "modules.run_worker" in " ".join(spec_b["command"])


def test_supervise_workers_marks_b_timeout_partial_success(tmp_path: Path):
    version_a = tmp_path / "version_a"
    version_b = tmp_path / "version_b"
    run_worker.create_worker_status_manifest(version_a, "version_a", "primary", 1200)
    (version_a / "generated_copy.json").write_text("{}", encoding="utf-8")
    run_worker.mark_worker_terminal_state(version_a, state="success")
    run_worker.create_worker_status_manifest(version_b, "version_b", "experimental", 1800)

    class _Proc:
        def __init__(self):
            self.returncode = None
        def poll(self):
            return self.returncode
        def terminate(self):
            self.terminated = True
        def kill(self):
            self.killed = True
            self.returncode = -9
        def wait(self, timeout=None):
            raise TimeoutError("still running")

    proc_a = _Proc()
    proc_a.returncode = 0
    proc_b = _Proc()

    specs = [
        {"worker_name": "version_a", "output_dir": str(version_a), "deadline_ts": 9999999999, "process": proc_a},
        {"worker_name": "version_b", "output_dir": str(version_b), "deadline_ts": 0, "process": proc_b},
    ]

    summary = run_supervisor.supervise_workers(
        worker_specs=specs,
        poll_interval_seconds=0,
        terminate_grace_seconds=0,
        kill_grace_seconds=0,
    )

    assert summary["state"] == "partial_success"
    assert summary["workers"]["version_a"]["state"] == "success"
    assert summary["workers"]["version_b"]["state"] == "timed_out"
    assert summary["workers"]["version_b"]["reference_status"] == "not_available"
    assert summary["workers"]["version_b"]["termination"]["kill_sent"] is True


def test_supervise_workers_marks_run_failed_when_version_a_fails(tmp_path: Path):
    version_a = tmp_path / "version_a"
    version_b = tmp_path / "version_b"
    run_worker.create_worker_status_manifest(version_a, "version_a", "primary", 1200)
    run_worker.mark_worker_terminal_state(version_a, state="failed", error="boom")
    run_worker.create_worker_status_manifest(version_b, "version_b", "experimental", 1800)
    (version_b / "generated_copy.json").write_text("{}", encoding="utf-8")
    run_worker.mark_worker_terminal_state(version_b, state="success")

    summary = run_supervisor.supervise_workers(
        worker_specs=[
            {"worker_name": "version_a", "output_dir": str(version_a), "deadline_ts": 9999999999, "process": None},
            {"worker_name": "version_b", "output_dir": str(version_b), "deadline_ts": 9999999999, "process": None},
        ],
        poll_interval_seconds=0,
    )

    assert summary["state"] == "failed"
    assert "version_a" in summary["blocking_components"]


def test_supervise_workers_marks_zero_exit_without_copy_as_failed(tmp_path: Path):
    version_a = tmp_path / "version_a"
    run_worker.create_worker_status_manifest(version_a, "version_a", "primary", 1200)

    class _Proc:
        returncode = 0

        def poll(self):
            return self.returncode

    summary = run_supervisor.supervise_workers(
        worker_specs=[
            {"worker_name": "version_a", "output_dir": str(version_a), "deadline_ts": 9999999999, "process": _Proc()},
        ],
        poll_interval_seconds=0,
    )

    assert summary["state"] == "failed"
    assert summary["workers"]["version_a"]["state"] == "failed"
    assert summary["workers"]["version_a"]["error"] == "worker_exit_0_missing_generated_copy"


def test_write_supervisor_summary_persists_json(tmp_path: Path):
    summary = {"state": "partial_success", "workers": {}, "available_outputs": ["version_a"]}
    path = run_supervisor.write_supervisor_summary(tmp_path, summary)
    assert path == tmp_path / run_supervisor.SUPERVISOR_SUMMARY_FILE
    assert path.exists()
