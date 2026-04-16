#!/usr/bin/env python3
"""Traffic retention guard for historical organic keywords."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

VISIBLE_FIELDS = ("title", "bullets", "description")
READY_STATUSES = {"READY_FOR_LISTING", "READY_FOR_HUMAN_REVIEW"}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _visible_text(generated_copy: Dict[str, Any]) -> str:
    parts: List[str] = []
    for field in VISIBLE_FIELDS:
        value = generated_copy.get(field)
        if isinstance(value, list):
            parts.extend(str(item) for item in value if item)
        elif value:
            parts.append(str(value))
    return " ".join(parts)


def _dedupe_keywords(keywords: Iterable[str], limit: int = 5) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for keyword in keywords:
        normalized = _normalize(keyword)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(keyword).strip())
        if len(deduped) >= limit:
            break
    return deduped


def _workspace_dir(preprocessed_data: Any) -> Path | None:
    run_config = getattr(preprocessed_data, "run_config", None)
    workspace_dir = getattr(run_config, "workspace_dir", "") if run_config else ""
    if not workspace_dir:
        return None
    path = Path(str(workspace_dir))
    return path if path.exists() else None


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _extract_feedback_keywords(preprocessed_data: Any) -> List[str]:
    feedback_context = getattr(preprocessed_data, "feedback_context", {}) or {}
    keywords: List[str] = []
    for bucket in ("organic_core",):
        for row in feedback_context.get(bucket, []) or []:
            keyword = (row or {}).get("keyword") if isinstance(row, dict) else row
            if keyword:
                keywords.append(str(keyword).strip())
    approved = feedback_context.get("approved_keywords", {}) or {}
    for row in approved.get("organic_core", []) or []:
        keyword = (row or {}).get("keyword") if isinstance(row, dict) else row
        if keyword:
            keywords.append(str(keyword).strip())
    return _dedupe_keywords(keywords, limit=5)


def _extract_keywords_from_assignment_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
    title_anchors: List[str] = []
    bullet_anchors: List[str] = []
    all_keywords: List[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        fields = set(row.get("assigned_fields") or [])
        tier = str(row.get("tier") or "").upper()
        source_type = str(row.get("source_type") or "").lower()
        if "title" in fields and (tier == "L1" or "feedback_organic_core" in source_type):
            title_anchors.append(keyword)
        if any(field in {"bullet_1", "bullet_2"} for field in fields):
            bullet_anchors.append(keyword)
        all_keywords.append(keyword)
    return {
        "title_anchors": _dedupe_keywords(title_anchors, limit=3),
        "bullet_anchors": _dedupe_keywords(bullet_anchors, limit=4),
        "all_keywords": _dedupe_keywords(all_keywords, limit=8),
    }


def _extract_history_keywords_from_run(run_dir: Path) -> Dict[str, Any]:
    generated = _load_json(run_dir / "generated_copy.json")
    scoring = _load_json(run_dir / "scoring_results.json")
    risk = _load_json(run_dir / "risk_report.json")
    assignments = ((generated.get("decision_trace") or {}).get("keyword_assignments") or [])
    extracted = _extract_keywords_from_assignment_rows(assignments)
    listing_status = (
        scoring.get("listing_status")
        or ((risk.get("listing_status") or {}).get("status"))
        or ""
    )
    return {
        "run_dir": str(run_dir.resolve()),
        "listing_status": listing_status,
        "total_score": float(scoring.get("total_score") or 0),
        "grade": scoring.get("grade") or "",
        "title_anchors": extracted["title_anchors"],
        "bullet_anchors": extracted["bullet_anchors"],
        "all_keywords": extracted["all_keywords"],
    }


def _select_historical_baseline(preprocessed_data: Any) -> Dict[str, Any]:
    workspace_dir = _workspace_dir(preprocessed_data)
    if not workspace_dir:
        return {}
    run_root = workspace_dir / "runs"
    if not run_root.exists():
        return {}

    candidates: List[Dict[str, Any]] = []
    for run_dir in sorted(run_root.iterdir()):
        if not run_dir.is_dir():
            continue
        if not (run_dir / "generated_copy.json").exists() or not (run_dir / "scoring_results.json").exists():
            continue
        candidate = _extract_history_keywords_from_run(run_dir)
        if candidate["all_keywords"]:
            candidates.append(candidate)

    if not candidates:
        return {}

    ready = [item for item in candidates if item.get("listing_status") in READY_STATUSES]
    pool = ready or candidates
    pool.sort(
        key=lambda item: (
            1 if item.get("listing_status") in READY_STATUSES else 0,
            float(item.get("total_score") or 0),
            len(item.get("title_anchors") or []),
        ),
        reverse=True,
    )
    return pool[0]


def build_retention_strategy(preprocessed_data: Any) -> Dict[str, Any]:
    feedback_keywords = _extract_feedback_keywords(preprocessed_data)
    historical = _select_historical_baseline(preprocessed_data)
    title_anchors = _dedupe_keywords(
        feedback_keywords + (historical.get("title_anchors") or []),
        limit=4,
    )
    bullet_anchors = _dedupe_keywords(
        (historical.get("bullet_anchors") or []) + feedback_keywords,
        limit=5,
    )
    baseline_keywords = _dedupe_keywords(
        title_anchors + bullet_anchors + (historical.get("all_keywords") or []),
        limit=8,
    )
    return {
        "enabled": bool(title_anchors or bullet_anchors or baseline_keywords),
        "workspace_dir": str(_workspace_dir(preprocessed_data).resolve()) if _workspace_dir(preprocessed_data) else "",
        "title_anchor_keywords": title_anchors,
        "bullet_anchor_keywords": bullet_anchors,
        "baseline_keywords": baseline_keywords,
        "historical_run": historical.get("run_dir", ""),
        "historical_listing_status": historical.get("listing_status", ""),
        "historical_total_score": historical.get("total_score", 0),
        "feedback_keywords": feedback_keywords,
    }


def calculate_retention_report(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> Dict[str, Any]:
    strategy = build_retention_strategy(preprocessed_data)
    reference_keywords = strategy.get("baseline_keywords") or []
    if not reference_keywords:
        return {
            "enabled": False,
            "reference_keywords": [],
            "retained_keywords": [],
            "missing_keywords": [],
            "retention_rate": 1.0,
            "threshold": 0.6,
            "is_blocking": False,
            "blocking_reason": "",
            "title_anchor_keywords": [],
            "title_anchor_missing": [],
            "historical_run": "",
        }

    visible = _normalize(_visible_text(generated_copy))
    retained: List[str] = []
    missing: List[str] = []
    for keyword in reference_keywords:
        if _normalize(keyword) in visible:
            retained.append(keyword)
        else:
            missing.append(keyword)

    title_anchor_keywords = strategy.get("title_anchor_keywords") or []
    title_anchor_missing = [
        keyword for keyword in title_anchor_keywords
        if _normalize(keyword) not in visible
    ]
    retention_rate = len(retained) / max(1, len(reference_keywords))
    threshold = 0.6
    is_blocking = retention_rate < threshold or len(title_anchor_missing) >= max(2, len(title_anchor_keywords))
    blocking_reason = ""
    if len(title_anchor_missing) >= max(2, len(title_anchor_keywords)) and title_anchor_keywords:
        blocking_reason = f"title_anchor_loss ({len(title_anchor_missing)}/{len(title_anchor_keywords)})"
    elif is_blocking:
        blocking_reason = f"traffic_retention_below_threshold ({len(retained)}/{len(reference_keywords)})"

    return {
        "enabled": True,
        "reference_keywords": reference_keywords,
        "retained_keywords": retained,
        "missing_keywords": missing,
        "retention_rate": retention_rate,
        "threshold": threshold,
        "is_blocking": is_blocking,
        "blocking_reason": blocking_reason,
        "title_anchor_keywords": title_anchor_keywords,
        "title_anchor_missing": title_anchor_missing,
        "bullet_anchor_keywords": strategy.get("bullet_anchor_keywords") or [],
        "historical_run": strategy.get("historical_run", ""),
        "historical_listing_status": strategy.get("historical_listing_status", ""),
    }


__all__ = ["build_retention_strategy", "calculate_retention_report"]
