#!/usr/bin/env python3
"""Workflow execution service for Streamlit UI."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from main import DEFAULT_REPORT_FILE, run_generator_workflow
from modules.compute_tiering import summarize_compute_tier_map
from modules.evidence_engine import summarize_evidence_bundle
from modules.intent_weights import summarize_intent_weight_snapshot
from modules.listing_status import RUN_FAILED
from modules.operations_panel import build_prelaunch_checklist, build_thirty_day_iteration_panel

from app.services.workspace_service import snapshot_run_outputs


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_workspace_workflow(
    run_config_path: str,
    workspace_dir: str,
    steps: Optional[List[int]] = None,
) -> Dict[str, Any]:
    workspace = Path(workspace_dir)
    run_dir = workspace / "runs" / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)

    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer), redirect_stderr(buffer):
            result = run_generator_workflow(run_config_path, str(run_dir), steps=steps)
    except Exception as exc:
        return {
            "status": RUN_FAILED,
            "error": str(exc),
            "run_dir": str(run_dir.resolve()),
            "logs": buffer.getvalue(),
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
    }
