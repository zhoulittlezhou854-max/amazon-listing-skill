#!/usr/bin/env python3
"""Live GPT smoke runner for healthcheck + optional workflow execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import AmazonListingGenerator, load_dotenv  # noqa: E402
from modules.llm_client import (  # noqa: E402
    configure_llm_runtime,
    get_llm_client,
    LLMClientUnavailable,
)


DEFAULT_STEPS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def _load_config(config_path: Path) -> Dict[str, Any]:
    return json.loads(config_path.read_text(encoding="utf-8"))


def _healthcheck_summary(health: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": bool(health.get("ok")),
        "provider": health.get("provider"),
        "configured_model": health.get("configured_model"),
        "returned_model": health.get("returned_model"),
        "wire_api": health.get("wire_api"),
        "base_url": health.get("base_url"),
        "request_id_present": bool(health.get("request_id")),
        "latency_ms": health.get("latency_ms"),
        "error": health.get("error"),
        "response_preview": health.get("response_preview"),
    }


def _probe_summary(client: Any) -> Dict[str, Any]:
    result = {
        "provider": getattr(client, "provider_label", "unknown"),
        "mode": getattr(client, "mode_label", "unknown"),
        "active_model": getattr(client, "active_model", None),
        "wire_api": getattr(client, "wire_api", None),
        "base_url": getattr(client, "base_url", None),
        "success": False,
        "text_preview": "",
        "error": "",
        "response_meta": {},
    }
    try:
        text = client.generate_text(
            "Reply with exactly READY.",
            {"probe": "smoke", "purpose": "verify_text_output"},
            temperature=0.0,
        )
        result["success"] = bool(text and text.strip())
        result["text_preview"] = (text or "").strip()[:80]
    except Exception as exc:  # pragma: no cover - runtime path
        result["error"] = str(exc)
    result["response_meta"] = getattr(client, "response_metadata", {}) or {}
    if not result["success"] and not result["error"]:
        result["error"] = result["response_meta"].get("error") or "empty_text_output"
    return result


def run_smoke(
    config_path: Path,
    output_dir: Path,
    steps: List[int],
    run_workflow: bool,
) -> Dict[str, Any]:
    load_dotenv()
    config = _load_config(config_path)
    configure_llm_runtime(config.get("llm"))

    result: Dict[str, Any] = {
        "config_path": str(config_path),
        "output_dir": str(output_dir),
        "steps": steps,
        "run_workflow": run_workflow,
        "llm": {},
        "workflow": None,
    }

    try:
        client = get_llm_client()
    except LLMClientUnavailable as exc:
        result["llm"] = {
            "init_ok": False,
            "error": str(exc),
        }
        return result

    health = client.healthcheck()
    probe = _probe_summary(client)
    result["llm"] = {
        "init_ok": not getattr(client, "is_offline", True),
        "healthcheck": _healthcheck_summary(health),
        "probe": probe,
    }

    live_ready = bool(health.get("ok")) and bool(probe.get("success"))
    result["llm"]["live_ready"] = live_ready

    if run_workflow and live_ready:
        generator = AmazonListingGenerator(str(config_path), str(output_dir))
        result["workflow"] = generator.run_workflow(steps)
    elif run_workflow:
        result["workflow"] = {
            "status": "skipped",
            "reason": "live_llm_not_ready",
        }

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Live GPT smoke runner")
    parser.add_argument("--config", required=True, help="run_config path")
    parser.add_argument("--output-dir", required=True, help="output directory")
    parser.add_argument("--steps", default=",".join(str(step) for step in DEFAULT_STEPS), help="workflow steps, e.g. 0,3,5,6,7,8,9")
    parser.add_argument("--run-workflow", action="store_true", help="run workflow if live probe succeeds")
    args = parser.parse_args()

    config_path = Path(args.config)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    steps = [int(item.strip()) for item in args.steps.split(",") if item.strip()]

    result = run_smoke(config_path, output_dir, steps, args.run_workflow)
    smoke_path = output_dir / "live_smoke_result.json"
    smoke_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"live_smoke_result: {smoke_path}")

    if result.get("llm", {}).get("live_ready"):
        print("live_ready=true")
        return 0

    print("live_ready=false")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
