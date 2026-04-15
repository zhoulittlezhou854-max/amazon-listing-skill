#!/usr/bin/env python3
"""Human-in-the-loop feedback snapshot helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence


def build_feedback_context(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    organic_core: List[Dict[str, Any]] = []
    sp_intent: List[Dict[str, Any]] = []
    backend_only: List[Dict[str, Any]] = []
    blocked_terms: List[Dict[str, Any]] = []

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        item = {
            "keyword": keyword,
            "source": row.get("source") or "unknown",
            "search_volume": row.get("search_volume") or 0,
            "conversion": row.get("conversion") or 0,
            "orders": row.get("orders") or 0,
            "suggested_slot": row.get("suggested_slot") or "backend",
            "risk_flag": row.get("risk_flag") or "ok",
            "reason": row.get("reason") or "",
        }
        keep = bool(row.get("keep", True))
        if not keep or item["risk_flag"] in {"blocked_brand", "garbled"}:
            blocked_terms.append(item)
            continue
        if item["suggested_slot"] == "backend":
            backend_only.append(item)
        elif item["source"] == "organic":
            organic_core.append(item)
        else:
            sp_intent.append(item)

    return {
        "organic_core": organic_core,
        "sp_intent": sp_intent,
        "backend_only": backend_only,
        "blocked_terms": blocked_terms,
    }


def save_feedback_snapshot(
    workspace_dir: str,
    source_file: str,
    rows: Sequence[Dict[str, Any]],
    product_code: str,
    site: str,
    operator_notes: str = "",
) -> str:
    workspace = Path(workspace_dir)
    feedback_dir = workspace / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    approved_keywords = build_feedback_context(rows)
    saved_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "product_code": product_code,
        "site": site,
        "source_file": source_file,
        "approved_keywords": approved_keywords,
        "operator_notes": operator_notes,
        "saved_at": saved_at,
        # flattened aliases for downstream modules
        "organic_core": approved_keywords["organic_core"],
        "sp_intent": approved_keywords["sp_intent"],
        "backend_only": approved_keywords["backend_only"],
        "blocked_terms": approved_keywords["blocked_terms"],
    }
    stamp = saved_at.replace(":", "-")[:19]
    target = feedback_dir / f"feedback_{stamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def load_feedback_snapshot(snapshot_path: str) -> Dict[str, Any]:
    path = Path(snapshot_path)
    if not path.exists():
        raise FileNotFoundError(snapshot_path)
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "build_feedback_context",
    "save_feedback_snapshot",
    "load_feedback_snapshot",
]
