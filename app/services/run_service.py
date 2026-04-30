#!/usr/bin/env python3
"""Workflow execution service for Streamlit UI."""

from __future__ import annotations

import io
import json
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from main import DEFAULT_REPORT_FILE, load_preprocessed_snapshot, run_generator_workflow
from modules.compute_tiering import summarize_compute_tier_map
from modules.evidence_engine import summarize_evidence_bundle
from modules.intent_weights import summarize_intent_weight_snapshot
from modules.listing_status import RUN_FAILED
from modules.operations_panel import build_prelaunch_checklist, build_thirty_day_iteration_panel
from modules import hybrid_composer, report_generator, run_supervisor
from run_pipeline import (
    _build_final_readiness_verdict,
    _load_version_bundle,
    _write_hybrid_unavailable,
    _write_listing_ready,
)

from app.services.workspace_service import infer_run_generation_status, snapshot_run_outputs

ALL_REPORT_COMPARE_FILE = "all_report_compare.md"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _persist_failure_summary(
    run_dir: Path,
    *,
    run_config_path: str,
    steps: Optional[List[int]],
    error: str,
    logs: str,
) -> None:
    summary = {
        "output_dir": str(run_dir.resolve()),
        "steps_requested": steps or [],
        "workflow_status": "failed",
        "error": error,
        "results": {
            "service_wrapper": {
                "status": "error",
                "error": error,
            }
        },
        "run_config_path": str(Path(run_config_path).resolve()) if run_config_path else "",
    }
    (run_dir / "execution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if logs.strip():
        (run_dir / "run_failure.log").write_text(logs, encoding="utf-8")


def _run_single_workflow(
    run_config_path: str,
    run_dir: Path,
    steps: Optional[List[int]] = None,
    *,
    blueprint_model_override: Optional[str] = None,
    title_model_override: Optional[str] = None,
    bullet_model_override: Optional[str] = None,
) -> Dict[str, Any]:
    result = run_generator_workflow(
        run_config_path,
        str(run_dir),
        steps=steps,
        blueprint_model_override=blueprint_model_override,
        title_model_override=title_model_override,
        bullet_model_override=bullet_model_override,
    )
    return {
        "result": result,
        "generated_copy": _load_json(run_dir / "generated_copy.json"),
        "risk_report": _load_json(run_dir / "risk_report.json"),
        "scoring_results": _load_json(run_dir / "scoring_results.json"),
        "bullet_blueprint": _load_json(run_dir / "bullet_blueprint.json"),
        "execution_summary": _load_json(run_dir / "execution_summary.json"),
    }


def _finalize_dual_version_outputs(
    *,
    run_dir: Path,
    run_config: Dict[str, Any],
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
    supervisor_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    version_a_dir = run_dir / "version_a"
    version_b_dir = run_dir / "version_b"
    hybrid_dir = run_dir / "hybrid"
    version_a_for_hybrid = {**(version_a.get("generated_copy") or {}), "risk_report": version_a.get("risk_report") or {}}
    version_b_for_hybrid = {**(version_b.get("generated_copy") or {}), "risk_report": version_b.get("risk_report") or {}}
    supervisor_summary = supervisor_summary or {}
    hybrid_copy: Dict[str, Any] = {}
    if version_a.get("generated_copy") and version_b.get("generated_copy"):
        hybrid_copy = hybrid_composer.compose_hybrid_listing(
            version_a=version_a_for_hybrid,
            version_b=version_b_for_hybrid,
            output_dir=hybrid_dir,
        )
    elif version_a.get("generated_copy"):
        _write_hybrid_unavailable(
            hybrid_dir,
            reason=str(supervisor_summary.get("hybrid_unavailable_reason") or "version_b_unavailable"),
            supervisor_summary=supervisor_summary,
        )
    else:
        _write_hybrid_unavailable(
            hybrid_dir,
            reason="version_a_unavailable",
            supervisor_summary=supervisor_summary,
        )

    hybrid_bundle: Dict[str, Any] = {}
    preprocessed_path = version_a_dir / "preprocessed_data.json"
    writing_policy_path = version_a_dir / "writing_policy.json"
    if hybrid_copy and preprocessed_path.exists() and writing_policy_path.exists():
        hybrid_bundle = hybrid_composer.finalize_hybrid_outputs(
            hybrid_copy=hybrid_copy,
            version_a=version_a_for_hybrid,
            version_b=version_b_for_hybrid,
            writing_policy=_load_json(writing_policy_path),
            preprocessed_data=load_preprocessed_snapshot(str(preprocessed_path)),
            output_dir=hybrid_dir,
            language=((version_a.get("generated_copy") or {}).get("metadata") or {}).get("target_language") or "English",
            intent_graph=_load_json(version_a_dir / "intent_graph.json"),
        )

    final_readiness_verdict = _build_final_readiness_verdict(
        run_id=run_dir.name,
        output_dir=run_dir,
        version_a=version_a,
        version_b=version_b,
        hybrid_bundle=hybrid_bundle,
        hybrid_copy=hybrid_copy,
        supervisor_summary=supervisor_summary,
    )
    final_readiness_verdict_path = run_dir / "final_readiness_verdict.json"
    final_readiness_verdict_path.write_text(
        json.dumps(final_readiness_verdict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    listing_ready_path = _write_listing_ready(run_dir, final_readiness_verdict)
    dual_report = report_generator.generate_dual_version_report(
        sku=run_config.get("product_code") or Path(run_dir).name,
        market=(run_config.get("target_country") or "").upper(),
        run_id=run_dir.name,
        version_a={
            "generated_copy": version_a.get("generated_copy") or {},
            "scoring_results": version_a.get("scoring_results") or {},
            "generation_status": infer_run_generation_status(version_a_dir, version_a.get("generated_copy") or {}),
            "execution_summary": version_a.get("execution_summary") or {},
            "blueprint_model": ((version_a.get("bullet_blueprint") or {}).get("llm_model")) or "deepseek-chat",
            "visible_copy_model": "deepseek-chat",
            "elapsed_seconds": 0,
        },
        version_b={
            "generated_copy": version_b.get("generated_copy") or {},
            "scoring_results": version_b.get("scoring_results") or {},
            "generation_status": infer_run_generation_status(version_b_dir, version_b.get("generated_copy") or {}),
            "execution_summary": version_b.get("execution_summary") or {},
            "blueprint_model": ((version_b.get("bullet_blueprint") or {}).get("llm_model")) or "deepseek-reasoner",
            "visible_copy_model": "deepseek-reasoner (title+bullets)",
            "elapsed_seconds": 0,
        },
        hybrid={
            "generated_copy": hybrid_bundle.get("generated_copy") or hybrid_copy,
            "scoring_results": hybrid_bundle.get("scoring_results") or {},
            "generation_status": (((hybrid_bundle.get("generated_copy") or hybrid_copy).get("metadata") or {}).get("hybrid_generation_status")) or "composed",
            "final_readiness_verdict": final_readiness_verdict,
        },
    )
    dual_report_path = run_dir / ALL_REPORT_COMPARE_FILE
    dual_report_path.write_text(dual_report, encoding="utf-8")
    return {
        "hybrid_copy": hybrid_copy,
        "hybrid_bundle": hybrid_bundle,
        "final_readiness_verdict": final_readiness_verdict,
        "final_readiness_verdict_path": str(final_readiness_verdict_path.resolve()),
        "listing_ready_path": str(listing_ready_path.resolve()),
        "dual_report_path": str(dual_report_path.resolve()),
        "dual_report_text": dual_report,
        "supervisor_summary": supervisor_summary,
    }


def run_workspace_workflow(
    run_config_path: str,
    workspace_dir: str,
    steps: Optional[List[int]] = None,
    *,
    dual_version: bool = False,
) -> Dict[str, Any]:
    workspace = Path(workspace_dir)
    run_dir = workspace / "runs" / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    run_config = _load_json(Path(run_config_path))

    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            if dual_version:
                version_a_dir = run_dir / "version_a"
                version_b_dir = run_dir / "version_b"
                worker_specs = [
                    run_supervisor.build_worker_spec(
                        worker_name="version_a",
                        run_config_path=run_config_path,
                        output_dir=version_a_dir,
                        steps=steps,
                    ),
                    run_supervisor.build_worker_spec(
                        worker_name="version_b",
                        run_config_path=run_config_path,
                        output_dir=version_b_dir,
                        steps=steps,
                        blueprint_model_override="deepseek-reasoner",
                        title_model_override="deepseek-reasoner",
                        bullet_model_override="deepseek-reasoner",
                    ),
                ]
                for spec in worker_specs:
                    run_supervisor.launch_worker(spec)
                supervisor_summary = run_supervisor.supervise_workers(worker_specs=worker_specs)
                run_supervisor.write_supervisor_summary(run_dir, supervisor_summary)
                version_a = _load_version_bundle(version_a_dir)
                version_b = _load_version_bundle(version_b_dir)
                dual_outputs = _finalize_dual_version_outputs(
                    run_dir=run_dir,
                    run_config=run_config,
                    version_a=version_a,
                    version_b=version_b,
                    supervisor_summary=supervisor_summary,
                )
                result = {
                    "summary": {
                        "workflow_status": supervisor_summary.get("state") or "unknown",
                        "version_a_summary": version_a.get("execution_summary") or {},
                        "version_b_summary": version_b.get("execution_summary") or {},
                    },
                    "generated_copy": version_a["generated_copy"],
                    "risk_report": version_a.get("risk_report") or {},
                    "scoring_results": version_a["scoring_results"],
                    "writing_policy": version_a["result"].get("writing_policy") or {},
                    "preprocessed_data": version_a["result"].get("preprocessed_data"),
                    "dual_version": {
                        "version_a_dir": str(version_a_dir.resolve()),
                        "version_b_dir": str(version_b_dir.resolve()),
                        "dual_report_path": dual_outputs["dual_report_path"],
                        "version_a": {
                            "generated_copy": version_a["generated_copy"],
                            "scoring_results": version_a["scoring_results"],
                            "generation_status": infer_run_generation_status(version_a_dir, version_a["generated_copy"]),
                            "reference_status": ((supervisor_summary.get("workers") or {}).get("version_a") or {}).get("reference_status"),
                            "worker_status": (supervisor_summary.get("workers") or {}).get("version_a") or {},
                        },
                        "version_b": {
                            "generated_copy": version_b["generated_copy"],
                            "scoring_results": version_b["scoring_results"],
                            "generation_status": infer_run_generation_status(version_b_dir, version_b["generated_copy"]),
                            "reference_status": ((supervisor_summary.get("workers") or {}).get("version_b") or {}).get("reference_status"),
                            "worker_status": (supervisor_summary.get("workers") or {}).get("version_b") or {},
                        },
                    },
                    "hybrid": {
                        "generated_copy": dual_outputs["hybrid_bundle"].get("generated_copy") or dual_outputs["hybrid_copy"],
                        "risk_report": dual_outputs["hybrid_bundle"].get("risk_report") or {},
                        "scoring_results": dual_outputs["hybrid_bundle"].get("scoring_results") or {},
                    },
                    "final_readiness_verdict": dual_outputs["final_readiness_verdict"],
                    "final_readiness_verdict_path": dual_outputs["final_readiness_verdict_path"],
                    "listing_ready_path": dual_outputs["listing_ready_path"],
                    "supervisor_summary": supervisor_summary,
                }
            else:
                result = run_generator_workflow(run_config_path, str(run_dir), steps=steps)
    except Exception as exc:
        failure_logs = buffer.getvalue()
        trace_output = traceback.format_exc()
        if trace_output:
            failure_logs = f"{failure_logs}\n{trace_output}".strip()
        _persist_failure_summary(
            run_dir,
            run_config_path=run_config_path,
            steps=steps,
            error=str(exc),
            logs=failure_logs,
        )
        return {
            "status": RUN_FAILED,
            "error": str(exc),
            "run_dir": str(run_dir.resolve()),
            "logs": failure_logs,
            "report_path": "",
            "metadata": {},
        }

    summary = result.get("summary") or {}
    generated_copy = result.get("generated_copy") or {}
    risk_report = result.get("risk_report") or {}
    scoring_results = result.get("scoring_results") or {}
    writing_policy = result.get("writing_policy") or {}
    metadata = generated_copy.get("metadata") or {}
    evidence_summary = summarize_evidence_bundle(generated_copy.get("evidence_bundle") or {})
    compute_tier_summary = summarize_compute_tier_map(generated_copy.get("compute_tier_map") or {})
    intent_weight_summary = writing_policy.get("intent_weight_summary") or summarize_intent_weight_snapshot(
        writing_policy.get("intent_weight_snapshot") or {}
    )
    prelaunch_checklist = build_prelaunch_checklist(
        preprocessed_data=result.get("preprocessed_data") or None,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report=risk_report,
        scoring_results=scoring_results,
    )
    thirty_day_iteration_panel = build_thirty_day_iteration_panel(
        preprocessed_data=result.get("preprocessed_data") or None,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report=risk_report,
        scoring_results=scoring_results,
    )
    report_path = str((run_dir / DEFAULT_REPORT_FILE).resolve()) if (run_dir / DEFAULT_REPORT_FILE).exists() else ""
    report_text = Path(report_path).read_text(encoding="utf-8") if report_path else ""
    snapshots = snapshot_run_outputs(str(workspace.resolve()), str(run_dir.resolve()))
    dual_payload = result.get("dual_version") or {}
    dual_report_path = dual_payload.get("dual_report_path") or ""
    dual_report_text = result.get("dual_report_text") or (Path(dual_report_path).read_text(encoding="utf-8") if dual_report_path else "")

    return {
        "status": summary.get("workflow_status") or "unknown",
        "listing_status": (risk_report.get("listing_status") or {}).get("status") or "",
        "run_dir": str(run_dir.resolve()),
        "report_path": report_path,
        "report_text": report_text,
        "metadata": metadata,
        "risk_report": risk_report,
        "scoring_results": scoring_results,
        "evidence_summary": evidence_summary,
        "compute_tier_summary": compute_tier_summary,
        "intent_weight_summary": intent_weight_summary,
        "prelaunch_checklist": prelaunch_checklist,
        "thirty_day_iteration_panel": thirty_day_iteration_panel,
        "execution_summary": summary,
        "snapshots": snapshots,
        "logs": buffer.getvalue(),
        "dual_version": dual_payload,
        "supervisor_summary": result.get("supervisor_summary") or {},
        "dual_report_path": dual_report_path,
        "dual_report_text": dual_report_text,
        "hybrid": result.get("hybrid") or {},
        "final_readiness_verdict": result.get("final_readiness_verdict") or {},
        "final_readiness_verdict_path": result.get("final_readiness_verdict_path") or "",
        "listing_ready_path": result.get("listing_ready_path") or "",
    }
