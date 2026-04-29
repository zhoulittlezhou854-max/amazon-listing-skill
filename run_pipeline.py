#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import time
from pathlib import Path
from types import FrameType

from tools.runtime_bootstrap import ensure_project_venv

ensure_project_venv(Path(__file__).resolve().parent)

from main import load_preprocessed_snapshot, run_generator_workflow
from modules import hybrid_composer, report_generator
from modules.listing_candidate import build_listing_candidate
from modules.readiness_verdict import build_readiness_verdict

VERSION_A_DEADLINE_SECONDS = 1200
VERSION_B_DEADLINE_SECONDS = 1800


def _read_generation_status(output_dir: Path, summary: dict) -> str:
    generated_copy_path = output_dir / "generated_copy.json"
    if generated_copy_path.exists():
        try:
            payload = json.loads(generated_copy_path.read_text(encoding="utf-8"))
            status = ((payload.get("metadata") or {}).get("generation_status") or "").strip()
            if status:
                return status
        except Exception:
            pass
    execution_summary_path = output_dir / "execution_summary.json"
    if execution_summary_path.exists():
        try:
            execution_summary = json.loads(execution_summary_path.read_text(encoding="utf-8"))
            if execution_summary.get("workflow_status") == "failed":
                results = execution_summary.get("results") or {}
                step_5 = results.get("step_5") or {}
                step_6 = results.get("step_6") or {}
                if step_5.get("status") == "error":
                    error = str(step_5.get("error") or "")
                    if "experimental_version_b_blueprint_failed" in error:
                        return "FAILED_AT_BLUEPRINT"
                    return "FAILED"
                if step_6.get("status") == "error":
                    return "FAILED_AT_COPY"
                return "FAILED"
        except Exception:
            pass
    return (summary.get("results", {}).get("step_6") or {}).get("metadata", {}).get("generation_status", "unknown")


def resolve_run_paths(
    product: str,
    market: str,
    run_id: str,
    *,
    workspace_root: Path | None = None,
) -> tuple[Path, Path]:
    root = workspace_root or Path(__file__).resolve().parent
    config_name = f"{product}_{market.upper()}.json"
    config_path = root / "config" / "run_configs" / config_name
    output_dir = root / "output" / "runs" / f"{product}_{market.upper()}_{run_id}"
    return config_path, output_dir


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_failed_execution_summary(output_dir: Path, *, steps: list[int] | None, error: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "output_dir": str(output_dir.resolve()),
        "steps_requested": list(steps or []),
        "workflow_status": "failed",
        "error": str(error or "workflow_failed"),
        "results": {
            "workflow_wrapper": {
                "status": "error",
                "error": str(error or "workflow_failed"),
            }
        },
    }
    (output_dir / "execution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


class VersionRunTimeout(TimeoutError):
    """Raised when one version exceeds its supervised business deadline."""


def _version_deadline_seconds(worker_name: str) -> int:
    specific_key = f"AMAZON_LISTING_{str(worker_name or '').upper()}_DEADLINE_SECONDS"
    raw = os.environ.get(specific_key) or os.environ.get("AMAZON_LISTING_VERSION_DEADLINE_SECONDS")
    default_deadline = VERSION_B_DEADLINE_SECONDS if str(worker_name or "").lower() == "version_b" else VERSION_A_DEADLINE_SECONDS
    try:
        value = int(raw) if raw is not None else default_deadline
    except (TypeError, ValueError):
        value = default_deadline
    return max(1, value)


def _run_with_deadline(callable_obj, *, deadline_seconds: int | None):
    if not deadline_seconds or deadline_seconds <= 0 or not hasattr(signal, "SIGALRM"):
        return callable_obj()

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _handle_timeout(_signum: int, _frame: FrameType | None) -> None:
        raise VersionRunTimeout(f"version_deadline_exceeded:{int(deadline_seconds)}")

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, float(deadline_seconds))
    try:
        return callable_obj()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _run_single_version(
    *,
    config_path: Path,
    output_dir: Path,
    steps: list[int] | None,
    blueprint_model_override: str | None = None,
    title_model_override: str | None = None,
    bullet_model_override: str | None = None,
    deadline_seconds: int | None = None,
) -> dict:
    started = time.time()
    try:
        result = _run_with_deadline(
            lambda: run_generator_workflow(
                str(config_path),
                str(output_dir),
                steps=steps,
                blueprint_model_override=blueprint_model_override,
                title_model_override=title_model_override,
                bullet_model_override=bullet_model_override,
            ),
            deadline_seconds=deadline_seconds,
        )
    except Exception as exc:
        summary = _write_failed_execution_summary(output_dir, steps=steps, error=str(exc))
        result = {"summary": summary}
    elapsed_seconds = round(time.time() - started, 2)
    return {
        "result": result,
        "elapsed_seconds": elapsed_seconds,
        "generated_copy": _load_json(output_dir / "generated_copy.json"),
        "risk_report": _load_json(output_dir / "risk_report.json"),
        "scoring_results": _load_json(output_dir / "scoring_results.json"),
        "bullet_blueprint": _load_json(output_dir / "bullet_blueprint.json"),
        "execution_summary": _load_json(output_dir / "execution_summary.json"),
        "generation_status": _read_generation_status(output_dir, result.get("summary") or {}),
    }


def _resolve_listing_status(risk_report: dict, scoring_results: dict) -> str:
    return ((risk_report.get("listing_status") or {}).get("status")) or "UNKNOWN"


def _launch_gate_scores(scoring_results: dict, launch_decision: dict) -> dict:
    if launch_decision.get("scores"):
        return dict(launch_decision.get("scores") or {})
    dimensions = scoring_results.get("dimensions") or {}
    return {
        "A10": ((dimensions.get("traffic") or {}).get("score")) or 0,
        "COSMO": ((dimensions.get("content") or {}).get("score")) or 0,
        "Rufus": ((dimensions.get("conversion") or {}).get("score")) or 0,
        "Fluency": ((dimensions.get("readability") or {}).get("score")) or 0,
    }


def _candidate_artifact(version_name: str, version: dict, *, source_type: str) -> dict:
    generated_copy = dict(version.get("generated_copy") or {})
    if generated_copy and "keyword_reconciliation" not in generated_copy:
        generated_copy["keyword_reconciliation"] = {"status": "missing"}
    metadata = generated_copy.get("metadata") or {}
    if "generation_status" not in generated_copy:
        generated_copy["generation_status"] = (
            version.get("generation_status")
            or metadata.get("generation_status")
            or "unknown"
        )
    generated_copy.setdefault("risk_summary", version.get("risk_report") or {})
    generated_copy.setdefault("score_summary", version.get("scoring_results") or {})
    return build_listing_candidate(version_name, generated_copy, source_type=source_type)


def _build_final_readiness_verdict(
    *,
    run_id: str,
    output_dir: Path,
    version_a: dict,
    version_b: dict | None = None,
    hybrid_bundle: dict,
    hybrid_copy: dict,
    supervisor_summary: dict | None = None,
) -> dict:
    version_b = version_b or {}
    supervisor_summary = supervisor_summary or {}
    hybrid_generated_copy = hybrid_bundle.get("generated_copy") or hybrid_copy or {}
    hybrid_risk_report = hybrid_bundle.get("risk_report") or {}
    hybrid_scoring_results = hybrid_bundle.get("scoring_results") or {}
    launch_decision = ((hybrid_generated_copy.get("metadata") or {}).get("launch_decision") or {})
    recommended_output = str(launch_decision.get("recommended_output") or "version_a")
    launch_recommended_output = recommended_output
    launch_thresholds = dict(launch_decision.get("thresholds") or {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24})
    hybrid_scores_for_review = _launch_gate_scores(hybrid_scoring_results, launch_decision)

    version_a_generated_copy_path = output_dir / "version_a" / "generated_copy.json"
    version_b_generated_copy_path = output_dir / "version_b" / "generated_copy.json"
    hybrid_generated_copy_path = output_dir / "hybrid" / "generated_copy.json"
    version_a_available = bool(version_a.get("generated_copy"))
    version_b_available = bool(version_b.get("generated_copy"))
    hybrid_available = bool(hybrid_generated_copy)
    hybrid_score_gate_passed = (
        hybrid_scores_for_review.get("A10", 0) >= launch_thresholds.get("A10", 80)
        and hybrid_scores_for_review.get("COSMO", 0) >= launch_thresholds.get("COSMO", 90)
        and hybrid_scores_for_review.get("Rufus", 0) >= launch_thresholds.get("Rufus", 90)
        and hybrid_scores_for_review.get("Fluency", 0) >= launch_thresholds.get("Fluency", 24)
    )
    if recommended_output == "version_a" and hybrid_available and hybrid_score_gate_passed:
        recommended_output = "hybrid"

    if recommended_output == "hybrid" and not hybrid_available:
        recommended_output = "version_a" if version_a_available else ("version_b" if version_b_available else "version_a")
    elif recommended_output == "version_a" and not version_a_available and version_b_available:
        recommended_output = "version_b"
    elif recommended_output == "version_b" and not version_b_available and version_a_available:
        recommended_output = "version_a"

    if not version_a_available and version_b_available and recommended_output == "version_a":
        recommended_output = "version_b"

    if recommended_output == "hybrid":
        recommended_generated_copy_path = hybrid_generated_copy_path
    elif recommended_output == "version_b":
        recommended_generated_copy_path = version_b_generated_copy_path
    else:
        recommended_generated_copy_path = version_a_generated_copy_path

    if recommended_output == "hybrid":
        candidate_listing_status = _resolve_listing_status(hybrid_risk_report, hybrid_scoring_results)
        selected_scoring_results = hybrid_scoring_results
    elif recommended_output == "version_b":
        candidate_listing_status = _resolve_listing_status(version_b.get("risk_report") or {}, version_b.get("scoring_results") or {})
        selected_scoring_results = version_b.get("scoring_results") or {}
    else:
        candidate_listing_status = _resolve_listing_status(version_a.get("risk_report") or {}, version_a.get("scoring_results") or {})
        selected_scoring_results = version_a.get("scoring_results") or {}

    candidates = {}
    if version_a_available:
        candidates["version_a"] = _candidate_artifact("version_a", version_a, source_type="stable")
    if version_b_available:
        candidates["version_b"] = _candidate_artifact("version_b", version_b, source_type="experimental")
    if hybrid_available:
        hybrid_version = {
            "generated_copy": hybrid_generated_copy,
            "risk_report": hybrid_risk_report,
            "scoring_results": hybrid_scoring_results,
            "generation_status": ((hybrid_generated_copy.get("metadata") or {}).get("generation_status") or "composed"),
        }
        candidates["hybrid"] = _candidate_artifact("hybrid", hybrid_version, source_type="hybrid")
    candidate_verdict = build_readiness_verdict(
        candidates=candidates,
        run_state="partial_success" if version_a_available != version_b_available else "success",
    )
    if candidate_verdict.get("recommended_output"):
        recommended_output = str(candidate_verdict.get("recommended_output") or recommended_output)
        if recommended_output == "hybrid":
            recommended_generated_copy_path = hybrid_generated_copy_path
            candidate_listing_status = _resolve_listing_status(hybrid_risk_report, hybrid_scoring_results)
            selected_scoring_results = hybrid_scoring_results
        elif recommended_output == "version_b":
            recommended_generated_copy_path = version_b_generated_copy_path
            candidate_listing_status = _resolve_listing_status(version_b.get("risk_report") or {}, version_b.get("scoring_results") or {})
            selected_scoring_results = version_b.get("scoring_results") or {}
        else:
            recommended_generated_copy_path = version_a_generated_copy_path
            candidate_listing_status = _resolve_listing_status(version_a.get("risk_report") or {}, version_a.get("scoring_results") or {})
            selected_scoring_results = version_a.get("scoring_results") or {}

    thresholds = launch_thresholds
    selected_launch_decision = (
        launch_decision
        if recommended_output == "hybrid" and recommended_output == launch_recommended_output
        else {}
    )
    reasons = list(selected_launch_decision.get("reasons") or [])
    worker_states = (supervisor_summary.get("workers") or {}) if isinstance(supervisor_summary, dict) else {}
    if recommended_output == "version_b" and not reasons:
        if str((worker_states.get("version_a") or {}).get("state") or "") not in {"", "success"}:
            reasons.append("version_a_unavailable")
    if recommended_output == "version_a" and not version_a_available and version_b_available and "version_a_unavailable" not in reasons:
        reasons.append("version_a_unavailable")

    launch_scores = _launch_gate_scores(selected_scoring_results, selected_launch_decision)
    launch_passed = bool(selected_launch_decision.get("passed"))
    if not selected_launch_decision:
        launch_passed = (
            candidate_listing_status == "READY_FOR_LISTING"
            and launch_scores.get("A10", 0) >= thresholds.get("A10", 80)
            and launch_scores.get("COSMO", 0) >= thresholds.get("COSMO", 90)
            and launch_scores.get("Rufus", 0) >= thresholds.get("Rufus", 90)
            and launch_scores.get("Fluency", 0) >= thresholds.get("Fluency", 24)
        )
    if candidate_verdict.get("operational_listing_status") != "READY_FOR_LISTING":
        launch_passed = False
    operational_listing_status = (
        "READY_FOR_LISTING"
        if candidate_listing_status == "READY_FOR_LISTING"
        and launch_passed
        and candidate_verdict.get("operational_listing_status") == "READY_FOR_LISTING"
        else "NOT_READY_FOR_LISTING"
    )
    if candidate_listing_status != "READY_FOR_LISTING" and "listing_not_ready" not in reasons:
        reasons.append("listing_not_ready")
    if not launch_passed and not reasons:
        reasons.append("launch_gate_failed")
    for blocker in (candidate_verdict.get("launch_gate") or {}).get("blockers") or []:
        if blocker not in reasons:
            reasons.append(blocker)

    verdict = {
        "run_id": run_id,
        "recommended_output": recommended_output,
        "listing_status": operational_listing_status,
        "candidate_listing_status": candidate_listing_status,
        "operational_listing_status": operational_listing_status,
        "candidate_verdict": candidate_verdict,
        "candidate_rankings": candidate_verdict.get("candidate_rankings") or [],
        "launch_gate": {
            "passed": launch_passed,
            "scores": launch_scores,
            "thresholds": thresholds,
        },
        "reasons": reasons,
        "artifact_paths": {
            "recommended_generated_copy": str(recommended_generated_copy_path),
            "version_a_generated_copy": str(version_a_generated_copy_path),
            "version_b_generated_copy": str(version_b_generated_copy_path),
            "hybrid_generated_copy": str(hybrid_generated_copy_path),
        },
    }
    return verdict


def _format_candidate_block(candidate_id: str, payload: dict) -> list[str]:
    bullets = list(payload.get("bullets") or [])
    search_terms = payload.get("search_terms") or []
    search_terms_text = ", ".join(search_terms) if isinstance(search_terms, list) else str(search_terms or "")
    lines = [
        f"### {candidate_id}",
        "",
        "#### Title",
        "```text",
        str(payload.get("title") or ""),
        "```",
        "",
        "#### Bullets",
        "```text",
        "\n".join(str(item or "") for item in bullets),
        "```",
        "",
    ]
    if payload.get("description"):
        lines.extend(["#### Product Description", "```text", str(payload.get("description") or ""), "```", ""])
    if search_terms_text:
        lines.extend(["#### Search Terms", "```text", search_terms_text, "```", ""])
    return lines


def _format_field_provenance(payload: dict) -> list[str]:
    metadata = payload.get("metadata") or {}
    field_provenance = metadata.get("field_provenance") or {}
    if not isinstance(field_provenance, dict) or not field_provenance:
        return []
    lines = ["## Field Provenance", ""]
    for field, record in field_provenance.items():
        if not isinstance(record, dict):
            continue
        tier = record.get("provenance_tier") or "unknown"
        eligibility = record.get("eligibility") or "unknown"
        reasons = ", ".join(str(item) for item in (record.get("blocking_reasons") or []) if str(item).strip())
        suffix = f", reason: {reasons}" if reasons else ""
        lines.append(f"- {field}: {tier} -> {eligibility}{suffix}")
    lines.append("")
    return lines


def _format_canonical_fact_readiness(payload: dict) -> list[str]:
    metadata = payload.get("metadata") or {}
    readiness = metadata.get("canonical_fact_readiness") or metadata.get("fact_readiness") or {}
    if not isinstance(readiness, dict) or not readiness:
        return []
    lines = ["## Canonical Fact Readiness", ""]
    required_status = readiness.get("required_fact_status") or {}
    if isinstance(required_status, dict):
        for fact_id, status in required_status.items():
            lines.append(f"- {fact_id}: {status}")
    for fact_id in readiness.get("blocking_missing") or []:
        lines.append(f"- {fact_id}: missing")
    for fact_id in readiness.get("blocking_missing_facts") or []:
        lines.append(f"- {fact_id}: missing")
    lines.append("")
    return lines


def _write_listing_review_required(output_dir: Path, final_verdict: dict) -> Path:
    artifact_paths = final_verdict.get("artifact_paths") or {}
    recommended = final_verdict.get("recommended_output") or "unknown"
    candidate_ids = [recommended]
    if recommended == "hybrid":
        candidate_ids.append("version_a")
    seen: set[str] = set()
    recommended_path = Path(artifact_paths.get(f"{recommended}_generated_copy") or "")
    recommended_payload = _load_json(recommended_path) if recommended_path.exists() else {}
    lines = [
        "# Listing Review Required",
        "",
        "## Candidate Source",
        f"- Output: `{recommended}`",
        f"- Candidate Status: `{final_verdict.get('candidate_listing_status') or 'UNKNOWN'}`",
        f"- Operational Status: `{final_verdict.get('operational_listing_status') or 'UNKNOWN'}`",
        "",
        "## Launch Gate",
        f"- Passed: `{bool((final_verdict.get('launch_gate') or {}).get('passed'))}`",
        f"- Scores: `{json.dumps((final_verdict.get('launch_gate') or {}).get('scores') or {}, ensure_ascii=False)}`",
        f"- Reasons: `{', '.join(final_verdict.get('reasons') or []) or 'none'}`",
        "",
        "## Candidate Preview",
        "",
        "This is not a paste-ready export. Fix the blocking reasons before using these fields in Amazon Seller Central.",
        "",
    ]
    if recommended_payload:
        lines.extend(_format_field_provenance(recommended_payload))
        lines.extend(_format_canonical_fact_readiness(recommended_payload))
    for candidate_id in candidate_ids:
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        path_text = artifact_paths.get(f"{candidate_id}_generated_copy") or ""
        path = Path(path_text) if path_text else None
        payload = _load_json(path) if path and path.exists() else {}
        if payload:
            lines.extend(_format_candidate_block(candidate_id, payload))
    review_path = output_dir / "LISTING_REVIEW_REQUIRED.md"
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return review_path


def _write_listing_ready(output_dir: Path, final_verdict: dict) -> Path:
    recommended_path = Path((final_verdict.get("artifact_paths") or {}).get("recommended_generated_copy") or "")
    payload = _load_json(recommended_path) if recommended_path.exists() else {}
    bullets = list(payload.get("bullets") or [])
    description = str(payload.get("description") or "")
    search_terms = payload.get("search_terms") or []
    search_terms_text = ", ".join(search_terms) if isinstance(search_terms, list) else str(search_terms or "")
    is_ready = (
        str(final_verdict.get("listing_status") or "") == "READY_FOR_LISTING"
        and bool((final_verdict.get("launch_gate") or {}).get("passed"))
    )
    output_name = "LISTING_READY.md" if is_ready else "LISTING_REVIEW_REQUIRED.md"
    stale_name = "LISTING_REVIEW_REQUIRED.md" if is_ready else "LISTING_READY.md"
    stale_path = output_dir / stale_name
    if stale_path.exists():
        stale_path.unlink()
    if not is_ready:
        return _write_listing_review_required(output_dir, final_verdict)
    lines = [
        "# Listing Ready",
        "",
        "## Recommended Source",
        f"- Output: `{final_verdict.get('recommended_output') or 'unknown'}`",
        f"- Candidate Status: `{final_verdict.get('candidate_listing_status') or final_verdict.get('listing_status') or 'UNKNOWN'}`",
        f"- Operational Status: `{final_verdict.get('operational_listing_status') or final_verdict.get('listing_status') or 'UNKNOWN'}`",
        f"- Source File: `{recommended_path}`",
        "",
        "## Amazon Backend Paste Blocks",
        "",
        "按后台粘贴顺序提供，下面每个代码块都可单独复制。",
        "",
        "### Title",
        "```text",
        str(payload.get("title") or ""),
        "```",
        "",
        "### Bullet 1",
        "```text",
        bullets[0] if len(bullets) > 0 else "",
        "```",
        "",
        "### Bullet 2",
        "```text",
        bullets[1] if len(bullets) > 1 else "",
        "```",
        "",
        "### Bullet 3",
        "```text",
        bullets[2] if len(bullets) > 2 else "",
        "```",
        "",
        "### Bullet 4",
        "```text",
        bullets[3] if len(bullets) > 3 else "",
        "```",
        "",
        "### Bullet 5",
        "```text",
        bullets[4] if len(bullets) > 4 else "",
        "```",
        "",
        "### Product Description",
        "```text",
        description,
        "```",
        "",
        "### Search Terms",
        "```text",
        search_terms_text,
        "```",
        "",
        "## Quick Scan",
    ]
    lines.append(f"- Title length: {len(str(payload.get('title') or ''))}")
    lines.append(f"- Bullet count: {len(bullets)}")
    lines.append(f"- Description length: {len(description)}")
    lines.append(f"- Search terms count: {len(search_terms) if isinstance(search_terms, list) else (1 if search_terms_text else 0)}")
    provenance_lines = _format_field_provenance(payload)
    if provenance_lines:
        lines.extend(["", *provenance_lines])
    listing_ready_path = output_dir / output_name
    listing_ready_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return listing_ready_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convenience wrapper for real product pipeline runs.")
    parser.add_argument("--product", required=True, help="Product code, e.g. H91lite")
    parser.add_argument("--market", required=True, help="Marketplace code, e.g. US")
    parser.add_argument("--run-id", required=True, help="Run identifier, e.g. r6")
    parser.add_argument("--steps", help='Optional subset of steps, e.g. "0,5,6,7,8,9"')
    parser.add_argument("--fresh", action="store_true", help="Delete the target run directory before executing.")
    parser.add_argument("--dual-version", action="store_true", help="Generate both V3 baseline and R1-blueprint experimental outputs.")
    args = parser.parse_args()

    config_path, output_dir = resolve_run_paths(args.product, args.market, args.run_id)
    if not config_path.exists():
        raise SystemExit(f"Missing run config: {config_path}")

    if args.fresh and output_dir.exists():
        shutil.rmtree(output_dir)

    steps = None
    if args.steps:
        steps = [int(chunk.strip()) for chunk in args.steps.split(",") if chunk.strip()]

    if not args.dual_version:
        result = run_generator_workflow(str(config_path), str(output_dir), steps=steps)
        summary = result.get("summary") or {}
        print(f"Run complete: {output_dir}")
        print(f"Generation status: {_read_generation_status(output_dir, summary)}")
        return

    version_a_dir = output_dir / "version_a"
    version_b_dir = output_dir / "version_b"
    version_a = _run_single_version(
        config_path=config_path,
        output_dir=version_a_dir,
        steps=steps,
        deadline_seconds=_version_deadline_seconds("version_a"),
    )
    version_b = _run_single_version(
        config_path=config_path,
        output_dir=version_b_dir,
        steps=steps,
        blueprint_model_override="deepseek-v4-pro",
        title_model_override="deepseek-v4-pro",
        bullet_model_override="deepseek-v4-pro",
        deadline_seconds=_version_deadline_seconds("version_b"),
    )
    hybrid_dir = output_dir / "hybrid"
    version_a_for_hybrid = {**version_a["generated_copy"], "risk_report": version_a.get("risk_report") or {}}
    version_b_for_hybrid = {**version_b["generated_copy"], "risk_report": version_b.get("risk_report") or {}}
    hybrid_copy = {}
    hybrid_bundle = {}
    preprocessed_path = version_a_dir / "preprocessed_data.json"
    writing_policy_path = version_a_dir / "writing_policy.json"
    if version_a.get("generated_copy") and version_b.get("generated_copy"):
        hybrid_copy = hybrid_composer.compose_hybrid_listing(
            version_a=version_a_for_hybrid,
            version_b=version_b_for_hybrid,
            output_dir=hybrid_dir,
        )
    if hybrid_copy and preprocessed_path.exists() and writing_policy_path.exists():
        hybrid_bundle = hybrid_composer.finalize_hybrid_outputs(
            hybrid_copy=hybrid_copy,
            version_a=version_a_for_hybrid,
            version_b=version_b_for_hybrid,
            writing_policy=_load_json(writing_policy_path),
            preprocessed_data=load_preprocessed_snapshot(str(preprocessed_path)),
            output_dir=hybrid_dir,
            language=((version_a["generated_copy"].get("metadata") or {}).get("target_language") or "English"),
            intent_graph=_load_json(version_a_dir / "intent_graph.json"),
        )
    final_readiness_verdict = _build_final_readiness_verdict(
        run_id=args.run_id,
        output_dir=output_dir,
        version_a=version_a,
        version_b=version_b,
        hybrid_bundle=hybrid_bundle,
        hybrid_copy=hybrid_copy,
    )
    final_readiness_verdict_path = output_dir / "final_readiness_verdict.json"
    final_readiness_verdict_path.write_text(
        json.dumps(final_readiness_verdict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    listing_ready_path = _write_listing_ready(output_dir, final_readiness_verdict)
    dual_report = report_generator.generate_dual_version_report(
        sku=args.product,
        market=args.market.upper(),
        run_id=args.run_id,
        version_a={
            "generated_copy": version_a["generated_copy"],
            "scoring_results": version_a["scoring_results"],
            "generation_status": version_a["generation_status"],
            "execution_summary": version_a["execution_summary"],
            "blueprint_model": (version_a["bullet_blueprint"] or {}).get("llm_model") or "deepseek-v4-flash",
            "visible_copy_model": "deepseek-v4-flash",
            "elapsed_seconds": version_a["elapsed_seconds"],
        },
        version_b={
            "generated_copy": version_b["generated_copy"],
            "scoring_results": version_b["scoring_results"],
            "generation_status": version_b["generation_status"],
            "execution_summary": version_b["execution_summary"],
            "blueprint_model": (version_b["bullet_blueprint"] or {}).get("llm_model") or "deepseek-v4-pro",
            "visible_copy_model": "deepseek-v4-pro (title+bullets)",
            "elapsed_seconds": version_b["elapsed_seconds"],
        },
        hybrid={
            "generated_copy": hybrid_bundle.get("generated_copy") or hybrid_copy,
            "scoring_results": hybrid_bundle.get("scoring_results") or {},
            "generation_status": ((hybrid_bundle.get("generated_copy") or hybrid_copy).get("metadata") or {}).get("hybrid_generation_status", "composed"),
            "final_readiness_verdict": final_readiness_verdict,
        },
    )
    dual_report_path = output_dir / "all_report_compare.md"
    dual_report_path.write_text(dual_report, encoding="utf-8")
    print(f"Run complete: {output_dir}")
    print(
        "Version A generation status:",
        _read_generation_status(version_a_dir, (version_a["result"].get("summary") or {})),
    )
    print(
        "Version B generation status:",
        _read_generation_status(version_b_dir, (version_b["result"].get("summary") or {})),
    )
    print(f"Hybrid output: {hybrid_dir / 'generated_copy.json'}")
    print(f"Hybrid title source: {(hybrid_copy.get('metadata') or {}).get('hybrid_sources', {}).get('title', '')}")
    print(f"All report compare: {dual_report_path}")
    print(f"Final verdict: {final_readiness_verdict_path}")
    print(f"Listing export: {listing_ready_path}")


if __name__ == "__main__":
    main()
