#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from main import load_preprocessed_snapshot, run_generator_workflow
from modules import hybrid_composer, report_generator


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


def _run_single_version(
    *,
    config_path: Path,
    output_dir: Path,
    steps: list[int] | None,
    blueprint_model_override: str | None = None,
    title_model_override: str | None = None,
    bullet_model_override: str | None = None,
) -> dict:
    started = time.time()
    result = run_generator_workflow(
        str(config_path),
        str(output_dir),
        steps=steps,
        blueprint_model_override=blueprint_model_override,
        title_model_override=title_model_override,
        bullet_model_override=bullet_model_override,
    )
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
    return (
        ((risk_report.get("listing_status") or {}).get("status"))
        or scoring_results.get("listing_status")
        or "UNKNOWN"
    )


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


def _build_final_readiness_verdict(
    *,
    run_id: str,
    output_dir: Path,
    version_a: dict,
    hybrid_bundle: dict,
    hybrid_copy: dict,
) -> dict:
    hybrid_generated_copy = hybrid_bundle.get("generated_copy") or hybrid_copy or {}
    hybrid_risk_report = hybrid_bundle.get("risk_report") or {}
    hybrid_scoring_results = hybrid_bundle.get("scoring_results") or {}
    launch_decision = ((hybrid_generated_copy.get("metadata") or {}).get("launch_decision") or {})
    recommended_output = str(launch_decision.get("recommended_output") or "version_a")

    version_a_generated_copy_path = output_dir / "version_a" / "generated_copy.json"
    hybrid_generated_copy_path = output_dir / "hybrid" / "generated_copy.json"
    recommended_generated_copy_path = hybrid_generated_copy_path if recommended_output == "hybrid" else version_a_generated_copy_path

    if recommended_output == "hybrid":
        listing_status = _resolve_listing_status(hybrid_risk_report, hybrid_scoring_results)
    else:
        listing_status = _resolve_listing_status(version_a.get("risk_report") or {}, version_a.get("scoring_results") or {})

    verdict = {
        "run_id": run_id,
        "recommended_output": recommended_output,
        "listing_status": listing_status,
        "launch_gate": {
            "passed": bool(launch_decision.get("passed")),
            "scores": _launch_gate_scores(hybrid_scoring_results, launch_decision),
            "thresholds": dict(launch_decision.get("thresholds") or {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24}),
        },
        "reasons": list(launch_decision.get("reasons") or []),
        "artifact_paths": {
            "recommended_generated_copy": str(recommended_generated_copy_path),
            "version_a_generated_copy": str(version_a_generated_copy_path),
            "hybrid_generated_copy": str(hybrid_generated_copy_path),
        },
    }
    return verdict


def _write_listing_ready(output_dir: Path, final_verdict: dict) -> Path:
    recommended_path = Path((final_verdict.get("artifact_paths") or {}).get("recommended_generated_copy") or "")
    payload = _load_json(recommended_path) if recommended_path.exists() else {}
    bullets = list(payload.get("bullets") or [])
    description = str(payload.get("description") or "")
    search_terms = payload.get("search_terms") or []
    search_terms_text = ", ".join(search_terms) if isinstance(search_terms, list) else str(search_terms or "")
    lines = [
        "# Listing Ready",
        "",
        "## Recommended Source",
        f"- Output: `{final_verdict.get('recommended_output') or 'unknown'}`",
        f"- Status: `{final_verdict.get('listing_status') or 'UNKNOWN'}`",
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
    listing_ready_path = output_dir / "LISTING_READY.md"
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
    )
    version_b = _run_single_version(
        config_path=config_path,
        output_dir=version_b_dir,
        steps=steps,
        blueprint_model_override="deepseek-reasoner",
        title_model_override="deepseek-reasoner",
        bullet_model_override="deepseek-reasoner",
    )
    hybrid_dir = output_dir / "hybrid"
    version_a_for_hybrid = {**version_a["generated_copy"], "risk_report": version_a.get("risk_report") or {}}
    version_b_for_hybrid = {**version_b["generated_copy"], "risk_report": version_b.get("risk_report") or {}}
    hybrid_copy = hybrid_composer.compose_hybrid_listing(
        version_a=version_a_for_hybrid,
        version_b=version_b_for_hybrid,
        output_dir=hybrid_dir,
    )
    hybrid_bundle = {}
    preprocessed_path = version_a_dir / "preprocessed_data.json"
    writing_policy_path = version_a_dir / "writing_policy.json"
    if preprocessed_path.exists() and writing_policy_path.exists():
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
            "blueprint_model": (version_a["bullet_blueprint"] or {}).get("llm_model") or "deepseek-chat",
            "visible_copy_model": "deepseek-chat",
            "elapsed_seconds": version_a["elapsed_seconds"],
        },
        version_b={
            "generated_copy": version_b["generated_copy"],
            "scoring_results": version_b["scoring_results"],
            "generation_status": version_b["generation_status"],
            "execution_summary": version_b["execution_summary"],
            "blueprint_model": (version_b["bullet_blueprint"] or {}).get("llm_model") or "deepseek-reasoner",
            "visible_copy_model": "deepseek-reasoner (title+bullets)",
            "elapsed_seconds": version_b["elapsed_seconds"],
        },
        hybrid={
            "generated_copy": hybrid_bundle.get("generated_copy") or hybrid_copy,
            "scoring_results": hybrid_bundle.get("scoring_results") or {},
            "generation_status": ((hybrid_bundle.get("generated_copy") or hybrid_copy).get("metadata") or {}).get("hybrid_generation_status", "composed"),
            "final_readiness_verdict": final_readiness_verdict,
        },
    )
    dual_report_path = output_dir / "dual_version_report.md"
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
    print(f"Dual report: {dual_report_path}")
    print(f"Final verdict: {final_readiness_verdict_path}")
    print(f"Listing ready: {listing_ready_path}")


if __name__ == "__main__":
    main()
