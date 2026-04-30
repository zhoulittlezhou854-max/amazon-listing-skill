from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from main import run_generator_workflow

WORKER_STATUS_FILE = "worker_status.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _output_paths(output_dir: Path) -> Dict[str, str]:
    output_dir = Path(output_dir)
    mapping = {
        "generated_copy_path": output_dir / "generated_copy.json",
        "scoring_results_path": output_dir / "scoring_results.json",
        "risk_report_path": output_dir / "risk_report.json",
        "execution_summary_path": output_dir / "execution_summary.json",
    }
    return {key: str(path.resolve()) for key, path in mapping.items() if path.exists()}


def _write_status(output_dir: Path, status: Dict[str, Any]) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / WORKER_STATUS_FILE).write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status


def _default_reference_status(worker_name: str, role: str, state: str) -> tuple[str, str, bool]:
    worker_name = str(worker_name or "")
    role = str(role or "")
    state = str(state or "")
    if role == "primary" or worker_name == "version_a":
        if state == "success":
            return "primary_result", "version_a completed successfully", True
        if state in {"failed", "timed_out", "terminated"}:
            return "failed" if state == "failed" else "not_available", f"{worker_name} {state}", False
        return "primary_pending", "version_a is not terminal yet", False
    if state == "success":
        return "usable_candidate", "version_b completed successfully", False
    if state == "failed":
        return "failed", "version_b failed", False
    if state == "timed_out":
        return "not_available", "version_b timed out", False
    return "not_available", "version_b is not terminal yet", False


def create_worker_status_manifest(
    output_dir: str | Path,
    worker_name: str,
    role: str,
    deadline_seconds: int,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    started = _now()
    deadline = started + timedelta(seconds=int(deadline_seconds or 0))
    reference_status, reference_reason, used_for_final = _default_reference_status(worker_name, role, "pending")
    status: Dict[str, Any] = {
        "worker_name": worker_name,
        "role": role,
        "state": "pending",
        "reference_status": reference_status,
        "reference_reason": reference_reason,
        "used_for_final_verdict": used_for_final,
        "started_at": _iso(started),
        "deadline_at": _iso(deadline),
        "finished_at": None,
        "deadline_seconds": int(deadline_seconds or 0),
        "heartbeat_at": _iso(started),
        "current_step": None,
        "current_stage": "pending",
        "current_field": "",
        "output_dir": str(output_path.resolve()),
        "error": "",
        "termination": {},
    }
    status.update(_output_paths(output_path))
    return _write_status(output_path, status)


def read_worker_status(output_dir: str | Path) -> Dict[str, Any]:
    path = Path(output_dir) / WORKER_STATUS_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def update_worker_status(output_dir: str | Path, **updates: Any) -> Dict[str, Any]:
    output_path = Path(output_dir)
    status = read_worker_status(output_path)
    if not status:
        status = {"output_dir": str(output_path.resolve())}
    status.update({key: value for key, value in updates.items() if value is not None})
    status["heartbeat_at"] = _iso(_now())
    status.update(_output_paths(output_path))
    return _write_status(output_path, status)


def mark_worker_terminal_state(
    output_dir: str | Path,
    *,
    state: str,
    error: str = "",
    termination: Optional[Dict[str, Any]] = None,
    reference_status: Optional[str] = None,
    reference_reason: Optional[str] = None,
    used_for_final_verdict: Optional[bool] = None,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    status = read_worker_status(output_path)
    worker_name = str(status.get("worker_name") or "")
    role = str(status.get("role") or "")
    inferred_status, inferred_reason, inferred_used = _default_reference_status(worker_name, role, state)
    if state == "timed_out":
        inferred_reason = f"{worker_name} timed out after {status.get('deadline_seconds') or 0} seconds"
    status.update(
        {
            "state": state,
            "finished_at": _iso(_now()),
            "heartbeat_at": _iso(_now()),
            "error": str(error or ""),
            "reference_status": reference_status or inferred_status,
            "reference_reason": reference_reason or inferred_reason,
            "used_for_final_verdict": inferred_used if used_for_final_verdict is None else bool(used_for_final_verdict),
        }
    )
    if termination is not None:
        status["termination"] = dict(termination)
    status.update(_output_paths(output_path))
    return _write_status(output_path, status)


def _parse_steps(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(chunk.strip()) for chunk in value.split(",") if chunk.strip()]


def _callback_for(output_dir: Path):
    def _callback(event: Dict[str, Any]) -> None:
        current_step = event.get("step")
        update_worker_status(
            output_dir,
            state="running",
            current_step=current_step,
            current_stage=event.get("stage_label") or event.get("stage") or "",
            current_field=event.get("field") or event.get("field_name") or "",
        )
    return _callback


def run_worker_job(
    *,
    worker_name: str,
    role: str,
    config_path: str,
    output_dir: str | Path,
    steps: Iterable[int] | None,
    deadline_seconds: int,
    blueprint_model_override: str | None = None,
    title_model_override: str | None = None,
    bullet_model_override: str | None = None,
) -> Dict[str, Any]:
    output_path = Path(output_dir)
    create_worker_status_manifest(output_path, worker_name, role, deadline_seconds)
    update_worker_status(output_path, state="running", current_stage="workflow_start")
    try:
        result = run_generator_workflow(
            config_path,
            str(output_path),
            steps=list(steps) if steps is not None else None,
            blueprint_model_override=blueprint_model_override,
            title_model_override=title_model_override,
            bullet_model_override=bullet_model_override,
            status_callback=_callback_for(output_path),
        )
        summary = result.get("summary") or {}
        workflow_status = summary.get("workflow_status") or "success"
        if workflow_status == "success" and (output_path / "generated_copy.json").exists():
            return mark_worker_terminal_state(output_path, state="success")
        return mark_worker_terminal_state(output_path, state="failed", error=str(summary.get("error") or workflow_status))
    except Exception as exc:
        return mark_worker_terminal_state(output_path, state="failed", error=str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one Amazon listing version worker")
    parser.add_argument("--worker-name", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--deadline-seconds", type=int, required=True)
    parser.add_argument("--steps", default="")
    parser.add_argument("--blueprint-model-override")
    parser.add_argument("--title-model-override")
    parser.add_argument("--bullet-model-override")
    args = parser.parse_args(argv)
    result = run_worker_job(
        worker_name=args.worker_name,
        role=args.role,
        config_path=args.config_path,
        output_dir=args.output_dir,
        steps=_parse_steps(args.steps),
        deadline_seconds=args.deadline_seconds,
        blueprint_model_override=args.blueprint_model_override,
        title_model_override=args.title_model_override,
        bullet_model_override=args.bullet_model_override,
    )
    return 0 if result.get("state") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
