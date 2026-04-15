#!/usr/bin/env python3
"""Workspace bootstrap helpers for Streamlit UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_WORKSPACE_ROOT = Path("workspace")
DEFAULT_LLM_CONFIG = {
    "provider": "openai_compatible",
    "model": "gpt-5.4",
    "base_url": "https://api.gptclubapi.xyz/openai",
    "wire_api": "responses",
    "api_key_env": "CRS_OAI_KEY",
    "force_live_llm": True,
}


def _slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (value or "").strip())


def _write_uploaded_file(target: Path, uploaded: Any) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(uploaded, "getvalue"):
        target.write_bytes(uploaded.getvalue())
    elif isinstance(uploaded, (str, Path)):
        source = Path(uploaded)
        target.write_bytes(source.read_bytes())
    else:
        raise TypeError(f"Unsupported upload type for {target.name}")
    return target


def build_workspace_name(product_code: str, site: str) -> str:
    return f"{_slugify(product_code).upper()}_{_slugify(site).upper()}"


def initialize_workspace(
    product_code: str,
    site: str,
    brand_name: str,
    files: Mapping[str, Any],
    manual_notes: str = "",
    workspace_root: str = "workspace",
    llm_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    workspace_name = build_workspace_name(product_code, site)
    workspace_dir = Path(workspace_root) / workspace_name
    inputs_dir = workspace_dir / "inputs"
    runs_dir = workspace_dir / "runs"
    feedback_dir = workspace_dir / "feedback"
    snapshots_dir = workspace_dir / "snapshots"
    for folder in [inputs_dir, runs_dir, feedback_dir, snapshots_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    stored_files: Dict[str, str] = {}
    for key, uploaded in files.items():
        if not uploaded:
            continue
        filename = getattr(uploaded, "name", None) or Path(str(uploaded)).name
        stored_files[key] = str(_write_uploaded_file(inputs_dir / filename, uploaded).resolve())

    config = {
        "product_code": product_code,
        "target_country": site.upper(),
        "brand_name": brand_name.strip() or "TOSBARRFT",
        "workspace_dir": str(workspace_dir.resolve()),
        "manual_notes": manual_notes,
        "core_selling_points_raw": manual_notes,
        "accessory_params_raw": "",
        "feedback_snapshot_path": "",
        "intent_weight_snapshot_path": "",
        "input_files": {
            "attribute_table": stored_files.get("attribute_table", ""),
            "keyword_table": stored_files.get("keyword_table", ""),
            "aba_merged": stored_files.get("aba_merged", ""),
            "review_table": stored_files.get("review_table", ""),
        },
        "llm": dict(llm_config or DEFAULT_LLM_CONFIG),
    }

    product_config = {
        "product_code": product_code,
        "site": site.upper(),
        "brand_name": brand_name.strip() or "TOSBARRFT",
        "workspace_dir": str(workspace_dir.resolve()),
        "input_files": config["input_files"],
        "manual_notes": manual_notes,
        "run_config_path": str((workspace_dir / "run_config.json").resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    (workspace_dir / "run_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace_dir / "product_config.json").write_text(json.dumps(product_config, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "workspace_name": workspace_name,
        "workspace_dir": str(workspace_dir.resolve()),
        "run_config_path": str((workspace_dir / "run_config.json").resolve()),
        "product_config_path": str((workspace_dir / "product_config.json").resolve()),
        "stored_files": stored_files,
    }


def list_workspaces(workspace_root: str = "workspace") -> List[Dict[str, Any]]:
    root = Path(workspace_root)
    if not root.exists():
        return []
    workspaces: List[Dict[str, Any]] = []
    for product_config in sorted(root.glob("*/product_config.json")):
        try:
            payload = json.loads(product_config.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["run_config_path"] = payload.get("run_config_path") or str((product_config.parent / "run_config.json").resolve())
        payload["workspace_dir"] = payload.get("workspace_dir") or str(product_config.parent.resolve())
        workspaces.append(payload)
    return workspaces


def attach_feedback_snapshot(run_config_path: str, feedback_snapshot_path: str) -> str:
    path = Path(run_config_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    config["feedback_snapshot_path"] = str(Path(feedback_snapshot_path).resolve())
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.resolve())


def attach_intent_weight_snapshot(run_config_path: str, intent_weight_snapshot_path: str) -> str:
    path = Path(run_config_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    config["intent_weight_snapshot_path"] = str(Path(intent_weight_snapshot_path).resolve())
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.resolve())


def snapshot_run_outputs(workspace_dir: str, run_dir: str) -> Dict[str, str]:
    workspace = Path(workspace_dir)
    snapshots = workspace / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    run_path = Path(run_dir)
    captured: Dict[str, str] = {}
    for name in ["generated_copy.json", "risk_report.json", "scoring_results.json", "listing_report.md"]:
        source = run_path / name
        if not source.exists():
            continue
        target = snapshots / f"latest_{name}"
        target.write_bytes(source.read_bytes())
        captured[name] = str(target.resolve())
    return captured
