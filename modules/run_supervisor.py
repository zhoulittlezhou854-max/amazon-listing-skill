from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from modules import run_worker

DEFAULT_VERSION_A_DEADLINE_SECONDS = 1200
DEFAULT_VERSION_B_DEADLINE_SECONDS = 1800
SUPERVISOR_SUMMARY_FILE = "supervisor_summary.json"


def _now_ts() -> float:
    return time.time()


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _role_for(worker_name: str) -> str:
    return "experimental" if str(worker_name or "").lower() == "version_b" else "primary"


def _default_deadline(worker_name: str) -> int:
    return DEFAULT_VERSION_B_DEADLINE_SECONDS if str(worker_name or "").lower() == "version_b" else DEFAULT_VERSION_A_DEADLINE_SECONDS


def build_worker_spec(
    *,
    worker_name: str,
    run_config_path: str | Path,
    output_dir: str | Path,
    steps: Iterable[int] | None = None,
    deadline_seconds: int | None = None,
    blueprint_model_override: str | None = None,
    title_model_override: str | None = None,
    bullet_model_override: str | None = None,
) -> Dict[str, Any]:
    deadline = int(deadline_seconds or _default_deadline(worker_name))
    started_ts = _now_ts()
    command = [
        sys.executable,
        "-m",
        "modules.run_worker",
        "--worker-name",
        worker_name,
        "--role",
        _role_for(worker_name),
        "--config-path",
        str(run_config_path),
        "--output-dir",
        str(output_dir),
        "--deadline-seconds",
        str(deadline),
    ]
    if steps is not None:
        command.extend(["--steps", ",".join(str(step) for step in steps)])
    for flag, value in (
        ("--blueprint-model-override", blueprint_model_override),
        ("--title-model-override", title_model_override),
        ("--bullet-model-override", bullet_model_override),
    ):
        if value:
            command.extend([flag, value])
    return {
        "worker_name": worker_name,
        "role": _role_for(worker_name),
        "output_dir": str(Path(output_dir)),
        "deadline_seconds": deadline,
        "deadline_ts": started_ts + deadline,
        "deadline_at": _iso_from_ts(started_ts + deadline),
        "command": command,
    }


def launch_worker(spec: Dict[str, Any]) -> subprocess.Popen:
    output_dir = Path(spec["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        spec["command"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    spec["process"] = proc
    return proc


def _terminate_for_timeout(proc: Any, *, terminate_grace_seconds: int, kill_grace_seconds: int) -> Dict[str, Any]:
    termination = {
        "terminate_sent": False,
        "kill_sent": False,
        "terminated_after_timeout": False,
        "terminate_grace_seconds": terminate_grace_seconds,
        "kill_grace_seconds": kill_grace_seconds,
    }
    if proc is None:
        return termination
    try:
        if proc.poll() is None:
            proc.terminate()
            termination["terminate_sent"] = True
            try:
                proc.wait(timeout=terminate_grace_seconds)
            except Exception:
                if proc.poll() is None:
                    proc.kill()
                    termination["kill_sent"] = True
                    try:
                        proc.wait(timeout=kill_grace_seconds)
                    except Exception:
                        pass
    finally:
        termination["terminated_after_timeout"] = True
    return termination


def _status_for_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    status = run_worker.read_worker_status(spec.get("output_dir") or "")
    if status:
        return status
    return {
        "worker_name": spec.get("worker_name"),
        "role": spec.get("role"),
        "state": "pending",
        "reference_status": "not_available",
        "output_dir": spec.get("output_dir"),
    }


def _is_terminal(state: str) -> bool:
    return str(state or "") in {"success", "failed", "timed_out", "terminated"}


def _has_generated_copy(status: Dict[str, Any]) -> bool:
    return (Path(status.get("output_dir") or "") / "generated_copy.json").exists()


def _derive_summary_state(workers: Dict[str, Dict[str, Any]]) -> str:
    version_a = workers.get("version_a") or {}
    version_b = workers.get("version_b") or {}
    version_a_state = str(version_a.get("state") or "")
    version_b_state = str(version_b.get("state") or "")
    if version_a_state != "success" or not _has_generated_copy(version_a):
        return "failed"
    if version_b_state == "success" and _has_generated_copy(version_b):
        return "success"
    return "partial_success"


def _available_outputs(workers: Dict[str, Dict[str, Any]]) -> List[str]:
    outputs: List[str] = []
    for name, status in workers.items():
        if status.get("state") == "success" and (Path(status.get("output_dir") or "") / "generated_copy.json").exists():
            outputs.append(name)
    return outputs


def supervise_workers(
    *,
    worker_specs: List[Dict[str, Any]],
    poll_interval_seconds: float = 5,
    terminate_grace_seconds: int = 30,
    kill_grace_seconds: int = 10,
) -> Dict[str, Any]:
    specs_by_name = {str(spec.get("worker_name")): spec for spec in worker_specs}
    while True:
        all_terminal = True
        for spec in worker_specs:
            status = _status_for_spec(spec)
            state = str(status.get("state") or "")
            proc = spec.get("process")
            if not _is_terminal(state):
                all_terminal = False
                if _now_ts() >= float(spec.get("deadline_ts") or 0):
                    termination = _terminate_for_timeout(
                        proc,
                        terminate_grace_seconds=terminate_grace_seconds,
                        kill_grace_seconds=kill_grace_seconds,
                    )
                    status = run_worker.mark_worker_terminal_state(
                        spec["output_dir"],
                        state="timed_out",
                        error="deadline_exceeded",
                        termination=termination,
                    )
                    state = status.get("state")
                elif proc is not None and proc.poll() is not None:
                    status = run_worker.read_worker_status(spec["output_dir"])
                    if not _is_terminal(str(status.get("state") or "")):
                        generated_copy_exists = (Path(spec["output_dir"]) / "generated_copy.json").exists()
                        state = "success" if proc.returncode == 0 and generated_copy_exists else "failed"
                        error = ""
                        if proc.returncode == 0 and not generated_copy_exists:
                            error = "worker_exit_0_missing_generated_copy"
                        elif state == "failed":
                            error = f"worker_exit_{proc.returncode}"
                        status = run_worker.mark_worker_terminal_state(
                            spec["output_dir"],
                            state=state,
                            error=error,
                        )
                    state = status.get("state")
                all_terminal = all_terminal and _is_terminal(str(state or ""))
        if all_terminal:
            break
        if poll_interval_seconds:
            time.sleep(poll_interval_seconds)
        else:
            break

    workers = {name: _status_for_spec(spec) for name, spec in specs_by_name.items()}
    state = _derive_summary_state(workers)
    blocking = [] if state != "failed" else ["version_a"]
    summary = {
        "state": state,
        "workers": workers,
        "available_outputs": _available_outputs(workers),
        "blocking_components": blocking,
    }
    if (workers.get("version_b") or {}).get("state") in {"failed", "timed_out"}:
        summary["hybrid_status"] = "unavailable"
        summary["hybrid_unavailable_reason"] = f"version_b_{(workers.get('version_b') or {}).get('state')}"
    return summary


def write_supervisor_summary(run_dir: str | Path, summary: Dict[str, Any]) -> Path:
    path = Path(run_dir) / SUPERVISOR_SUMMARY_FILE
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
