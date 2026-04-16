#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from main import run_generator_workflow
from modules import report_generator


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
) -> dict:
    started = time.time()
    result = run_generator_workflow(
        str(config_path),
        str(output_dir),
        steps=steps,
        blueprint_model_override=blueprint_model_override,
    )
    elapsed_seconds = round(time.time() - started, 2)
    return {
        "result": result,
        "elapsed_seconds": elapsed_seconds,
        "generated_copy": _load_json(output_dir / "generated_copy.json"),
        "scoring_results": _load_json(output_dir / "scoring_results.json"),
        "bullet_blueprint": _load_json(output_dir / "bullet_blueprint.json"),
    }


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
    )
    dual_report = report_generator.generate_dual_version_report(
        sku=args.product,
        market=args.market.upper(),
        run_id=args.run_id,
        version_a={
            "generated_copy": version_a["generated_copy"],
            "scoring_results": version_a["scoring_results"],
            "blueprint_model": (version_a["bullet_blueprint"] or {}).get("llm_model") or "deepseek-chat",
            "elapsed_seconds": version_a["elapsed_seconds"],
        },
        version_b={
            "generated_copy": version_b["generated_copy"],
            "scoring_results": version_b["scoring_results"],
            "blueprint_model": (version_b["bullet_blueprint"] or {}).get("llm_model") or "deepseek-reasoner",
            "elapsed_seconds": version_b["elapsed_seconds"],
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
    print(f"Dual report: {dual_report_path}")


if __name__ == "__main__":
    main()
