#!/usr/bin/env python3
"""Canonical listing status helpers for workflow, UI, and reports."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

READY_FOR_LISTING = "READY_FOR_LISTING"
READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
NOT_READY_FOR_LISTING = "NOT_READY_FOR_LISTING"
RUN_FAILED = "RUN_FAILED"

BLOCKING_SEVERITIES = {"high", "critical", "blocker"}
DIMENSION_THRESHOLDS = {
    "traffic": 80,
    "content": 80,
    "conversion": 80,
    "readability": 24,
}
REVIEW_PRIORITY = {
    "title": ("P0", "今天处理"),
    "bullet_b1": ("P0", "今天处理"),
    "bullet_b2": ("P1", "24h内"),
    "bullet_b3": ("P1", "24h内"),
    "bullet_b4": ("P2", "72h内"),
    "bullet_b5": ("P2", "72h内"),
    "aplus": ("P2", "72h内"),
    "search_terms": ("P3", "下次更新时"),
}
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# This module exposes two status layers on purpose:
# - `derive_listing_status()` is the runtime readiness gate used by risk/report
#   generation. It combines live generation state, fallback volume, and blocking
#   risk signals into the operational listing decision.
# - `determine_listing_status()` is the scoring-layer gate used by the four
#   dimension score report. It only evaluates whether dimension thresholds pass.
# Pipeline consumers should treat the runtime gate as the authoritative
# listing-status source for publish decisions, while the scoring gate explains
# which score dimensions still need work.


def _count_bullet_fallbacks(visible_fallback_fields: Sequence[Any]) -> int:
    count = 0
    for field in visible_fallback_fields or []:
        value = str(field or '').strip().lower()
        if not value:
            continue
        if value.startswith('bullet_b') or re.match(r'^b[1-5]$', value):
            count += 1
    return count


def _collect_issue_descriptions(section: Dict[str, Any], *, allow_medium: bool = False) -> List[str]:
    issues = section.get("issues") or []
    collected: List[str] = []
    blocking_levels = set(BLOCKING_SEVERITIES)
    if allow_medium:
        blocking_levels.add("medium")
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "").lower()
        if severity in blocking_levels:
            collected.append(issue.get("description") or issue.get("rule") or "blocking_issue")
    return collected


def derive_listing_status(
    generation_status: str,
    risk_report: Dict[str, Any] | None = None,
    retention_report: Dict[str, Any] | None = None,
    llm_response_state: str = "",
    visible_fallback_fields: Sequence[Any] | None = None,
) -> Dict[str, Any]:
    risk_report = risk_report or {}
    retention_report = retention_report or {}
    reasons: List[str] = []

    normalized_generation = (generation_status or "offline").lower()
    response_state = (llm_response_state or "").lower()

    if normalized_generation in {"offline", "live_failed"}:
        reasons.append("live_llm_not_verified")
    if _count_bullet_fallbacks(visible_fallback_fields or []) > 2:
        reasons.append("too_many_bullet_fallbacks")
    if response_state in {"missing_output_text", "empty_packet", "empty_content"}:
        reasons.append(response_state)

    for key in [
        "compliance",
        "policy_audit",
        "hallucination_risk",
        "truth_consistency",
        "language_consistency",
        "fluency",
    ]:
        reasons.extend(
            _collect_issue_descriptions(
                risk_report.get(key) or {},
                allow_medium=(key == "fluency"),
            )
        )

    if retention_report.get("is_blocking"):
        reasons.append(retention_report.get("blocking_reason") or "traffic_retention_failed")

    unique_reasons = []
    seen = set()
    for reason in reasons:
        normalized = str(reason).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_reasons.append(normalized)

    if unique_reasons:
        status = NOT_READY_FOR_LISTING
    elif normalized_generation == "live_success":
        status = READY_FOR_LISTING
    # `live_with_fallback` only reaches this branch if `too_many_bullet_fallbacks`
    # did not fire above, meaning fallback usage stayed inside the manual-review
    # tolerance window.
    elif normalized_generation == "live_with_fallback":
        status = READY_FOR_HUMAN_REVIEW
    else:
        status = NOT_READY_FOR_LISTING

    return {
        "status": status,
        "blocking_reasons": unique_reasons,
        "generation_status": generation_status or "offline",
        "llm_response_state": llm_response_state or "",
        "is_blocking": status == NOT_READY_FOR_LISTING,
    }


def determine_listing_status(dimensions: Dict[str, Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    blocking: List[Dict[str, Any]] = []
    for dimension, result in (dimensions or {}).items():
        threshold = int(result.get("threshold") or DIMENSION_THRESHOLDS.get(dimension, 0))
        if int(result.get("score") or 0) < threshold:
            blocking.append(
                {
                    "dimension": dimension,
                    "label": result.get("label") or dimension,
                    "score": int(result.get("score") or 0),
                    "max": int(result.get("max") or 0),
                    "threshold": threshold,
                    "blocking_fields": list(result.get("blocking_fields") or []),
                    "issue_summary": result.get("issue_summary") or "",
                }
            )
    if not blocking:
        return READY_FOR_LISTING, []
    return NOT_READY_FOR_LISTING, blocking


def build_action_required(blocking: Sequence[Dict[str, Any]]) -> str:
    if not blocking:
        return ""
    parts: List[str] = []
    for item in blocking:
        fields = list(item.get("blocking_fields") or [])
        field_suffix = f"，问题字段：{'、'.join(fields)}" if fields else ""
        parts.append(
            f"{item.get('label') or item.get('dimension')} 维度未达标"
            f"（{item.get('score', 0)}/{item.get('max', 0)}，阈值 {item.get('threshold', 0)}）"
            f"{field_suffix}"
        )
    return "；".join(parts)


def build_review_queue(blocking_dimensions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    seen = set()
    for dimension in blocking_dimensions or []:
        label = dimension.get("label") or dimension.get("dimension") or ""
        summary = dimension.get("issue_summary") or ""
        for field in dimension.get("blocking_fields") or []:
            if not field or field in seen:
                continue
            seen.add(field)
            priority, sla = REVIEW_PRIORITY.get(field, ("P3", "下次更新时"))
            queue.append(
                {
                    "field": field,
                    "dimension": label,
                    "issue": summary,
                    "priority": priority,
                    "sla": sla,
                }
            )
    return sorted(queue, key=lambda item: (_PRIORITY_ORDER.get(item["priority"], 99), item["field"]))


__all__ = [
    "READY_FOR_LISTING",
    "READY_FOR_HUMAN_REVIEW",
    "NOT_READY_FOR_LISTING",
    "RUN_FAILED",
    "derive_listing_status",
    "DIMENSION_THRESHOLDS",
    "determine_listing_status",
    "build_action_required",
    "build_review_queue",
]
