#!/usr/bin/env python3
"""Workspace bootstrap helpers for Streamlit UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_WORKSPACE_ROOT = Path("workspace")
DEFAULT_LLM_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key_env": "DEEPSEEK_API_KEY",
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


def _official_run_config_path(product_code: str, site: str) -> Path:
    return Path("config") / "run_configs" / f"{_slugify(product_code)}_{_slugify(site).upper()}.json"


def _load_official_llm_config(product_code: str, site: str) -> Dict[str, Any]:
    path = _official_run_config_path(product_code, site)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload.get("llm") or {})


def _llm_alignment_warning(active_llm: Dict[str, Any], official_llm: Dict[str, Any]) -> str:
    if not official_llm:
        return ""
    keys = ("provider", "model", "base_url", "api_key_env")
    mismatches = [
        key for key in keys
        if str(active_llm.get(key) or "").strip() != str(official_llm.get(key) or "").strip()
    ]
    if not mismatches:
        return ""
    return (
        "Workspace LLM config does not match the official run config for this SKU: "
        + ", ".join(mismatches)
    )


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

    resolved_llm_config = dict(llm_config or DEFAULT_LLM_CONFIG)
    official_llm_config = _load_official_llm_config(product_code, site)
    llm_alignment_warning = _llm_alignment_warning(resolved_llm_config, official_llm_config)

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
        "llm": resolved_llm_config,
        "llm_alignment_warning": llm_alignment_warning,
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
        "llm_alignment_warning": llm_alignment_warning,
    }

    (workspace_dir / "run_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace_dir / "product_config.json").write_text(json.dumps(product_config, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "workspace_name": workspace_name,
        "workspace_dir": str(workspace_dir.resolve()),
        "run_config_path": str((workspace_dir / "run_config.json").resolve()),
        "product_config_path": str((workspace_dir / "product_config.json").resolve()),
        "stored_files": stored_files,
        "llm_alignment_warning": llm_alignment_warning,
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


def list_product_code_options(site: str, workspace_root: str = "workspace") -> List[str]:
    target_site = (site or "").strip().upper()
    seen: set[str] = set()
    ordered: List[str] = []
    workspaces = sorted(
        list_workspaces(workspace_root),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )
    for workspace in workspaces:
        if target_site and str(workspace.get("site") or "").strip().upper() != target_site:
            continue
        product_code = str(workspace.get("product_code") or "").strip()
        if not product_code:
            continue
        dedupe_key = product_code.upper()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ordered.append(product_code)
    return ordered


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def infer_run_generation_status(run_dir: Path, generated_copy: Dict[str, Any] | None = None) -> str:
    generated_copy = generated_copy or _load_json(run_dir / "generated_copy.json")
    status = ((generated_copy.get("metadata") or {}).get("generation_status") or "").strip()
    if status:
        return status
    execution_summary = _load_json(run_dir / "execution_summary.json")
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
    return ""


def _run_created_at(run_dir: Path) -> str:
    try:
        return datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def _dimension_scores(scoring_results: Dict[str, Any]) -> Dict[str, Any]:
    dims = scoring_results.get("dimensions") or {}
    return {
        "A10": (dims.get("traffic") or {}).get("score", 0),
        "COSMO": (dims.get("content") or {}).get("score", 0),
        "Rufus": (dims.get("conversion") or {}).get("score", 0),
        "Fluency": (dims.get("readability") or {}).get("score", 0),
    }


def _load_run_version(run_dir: Path) -> Dict[str, Any]:
    generated_copy = _load_json(run_dir / "generated_copy.json")
    risk_report = _load_json(run_dir / "risk_report.json")
    scoring_results = _load_json(run_dir / "scoring_results.json")
    return {
        "run_dir": str(run_dir.resolve()),
        "generated_copy": generated_copy,
        "risk_report": risk_report,
        "scoring_results": scoring_results,
        "report_path": str((run_dir / "listing_report.md").resolve()) if (run_dir / "listing_report.md").exists() else "",
        "report_text": _load_text(run_dir / "listing_report.md"),
        "readiness_summary_path": str((run_dir / "readiness_summary.md").resolve()) if (run_dir / "readiness_summary.md").exists() else "",
        "readiness_summary_text": _load_text(run_dir / "readiness_summary.md"),
        "listing_status": ((risk_report.get("listing_status") or {}).get("status") or scoring_results.get("listing_status") or ""),
        "generation_status": infer_run_generation_status(run_dir, generated_copy),
        "scores": _dimension_scores(scoring_results),
    }


def _recommended_generation_status(recommended_output: str, version_a: Dict[str, Any], version_b: Dict[str, Any], hybrid: Dict[str, Any]) -> str:
    source_map = {
        "version_a": version_a,
        "version_b": version_b,
        "hybrid": hybrid,
    }
    payload = source_map.get(recommended_output) or {}
    return str(payload.get("generation_status") or version_a.get("generation_status") or "")


def _resolve_compare_report(run_dir: Path) -> Path | None:
    for name in ["all_report_compare.md", "dual_version_report.md"]:
        candidate = run_dir / name
        if candidate.exists():
            return candidate
    return None


def list_workspace_runs(workspace_dir: str) -> List[Dict[str, Any]]:
    root = Path(workspace_dir) / "runs"
    if not root.exists():
        return []

    records: List[Dict[str, Any]] = []
    for run_dir in sorted([path for path in root.iterdir() if path.is_dir()], key=lambda path: path.name, reverse=True):
        dual_report = _resolve_compare_report(run_dir)
        if dual_report is not None:
            version_a = _load_run_version(run_dir / "version_a")
            version_b = _load_run_version(run_dir / "version_b")
            hybrid = _load_run_version(run_dir / "hybrid") if (run_dir / "hybrid").exists() else {}
            final_readiness_verdict = _load_json(run_dir / "final_readiness_verdict.json")
            launch_gate = final_readiness_verdict.get("launch_gate") or {}
            recommended_output = str(final_readiness_verdict.get("recommended_output") or "version_a")
            records.append(
                {
                    "run_id": run_dir.name,
                    "created_at": _run_created_at(run_dir),
                    "run_dir": str(run_dir.resolve()),
                    "is_dual_version": True,
                    "generation_status": _recommended_generation_status(recommended_output, version_a, version_b, hybrid),
                    "listing_status": str(final_readiness_verdict.get("listing_status") or version_a.get("listing_status") or ""),
                    "scores": dict(launch_gate.get("scores") or version_a.get("scores") or {}),
                    "recommended_output": recommended_output,
                    "version_a": version_a,
                    "version_b": version_b,
                    "hybrid": hybrid,
                    "dual_report_path": str(dual_report.resolve()),
                    "dual_report_text": _load_text(dual_report),
                    "final_readiness_verdict": final_readiness_verdict,
                    "listing_ready_path": str((run_dir / "LISTING_READY.md").resolve()) if (run_dir / "LISTING_READY.md").exists() else "",
                    "listing_ready_text": _load_text(run_dir / "LISTING_READY.md"),
                }
            )
            continue

        version = _load_run_version(run_dir)
        records.append(
            {
                "run_id": run_dir.name,
                "created_at": _run_created_at(run_dir),
                "run_dir": str(run_dir.resolve()),
                "is_dual_version": False,
                "generation_status": version.get("generation_status", ""),
                "listing_status": version.get("listing_status", ""),
                "scores": version.get("scores", {}),
                **version,
            }
        )
    return records


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
    compare_report = _resolve_compare_report(run_path)
    if compare_report is not None:
        for name in [compare_report.name, "final_readiness_verdict.json", "LISTING_READY.md"]:
            source = run_path / name
            if not source.exists():
                continue
            target = snapshots / f"latest_{name}"
            target.write_bytes(source.read_bytes())
            captured[name] = str(target.resolve())
        for version_name in ["version_a", "version_b", "hybrid"]:
            version_dir = run_path / version_name
            if not version_dir.exists():
                continue
            for artifact_name in ["generated_copy.json", "risk_report.json", "scoring_results.json", "listing_report.md"]:
                source = version_dir / artifact_name
                if not source.exists():
                    continue
                target = snapshots / f"latest_{version_name}_{artifact_name}"
                target.write_bytes(source.read_bytes())
                captured[f"{version_name}_{artifact_name}"] = str(target.resolve())
        return captured
    for name in ["generated_copy.json", "risk_report.json", "scoring_results.json", "listing_report.md"]:
        source = run_path / name
        if not source.exists():
            continue
        target = snapshots / f"latest_{name}"
        target.write_bytes(source.read_bytes())
        captured[name] = str(target.resolve())
    return captured
