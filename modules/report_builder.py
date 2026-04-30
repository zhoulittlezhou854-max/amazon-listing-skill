#!/usr/bin/env python3
"""Compact readiness summary for operators."""

from __future__ import annotations

from typing import Any, Dict, List

from modules.listing_status import derive_listing_status
from modules.report_generator import _listing_readiness


def _status_icon(status: str) -> str:
    return "✅" if str(status or "").lower() == "pass" else "⚠️"


def _dimension_rows(dimensions: Dict[str, Dict[str, Any]]) -> List[str]:
    ordered = [
        ("traffic", "A10 流量"),
        ("content", "COSMO 内容"),
        ("conversion", "Rufus 转化"),
        ("readability", "Fluency 可读性"),
    ]
    lines = ["| 维度 | 得分 | 状态 |", "|------|------|------|"]
    for key, label in ordered:
        item = dimensions.get(key) or {}
        lines.append(
            f"| {label} | {item.get('score', 0)}/{item.get('max', 0)} | {_status_icon(item.get('status'))} |"
        )
    return lines


def build_readiness_summary(
    *,
    sku: str,
    run_id: str,
    generated_copy: Dict[str, Any],
    scoring_results: Dict[str, Any],
    risk_report: Dict[str, Any],
    generated_at: str,
) -> str:
    bullets = list(generated_copy.get("bullets") or [])
    bullets += [""] * max(0, 5 - len(bullets))
    search_terms = generated_copy.get("search_terms") or []
    if isinstance(search_terms, list):
        search_terms_text = ", ".join(str(item) for item in search_terms if str(item).strip())
    else:
        search_terms_text = str(search_terms or "")
    review_queue = risk_report.get("review_queue") or []
    review_lines = [
        f"- {item.get('field')}: {item.get('issue')} ({item.get('priority')})"
        for item in review_queue
    ] or ["无"]
    action_required = scoring_results.get("action_required") or "可直接上架"
    metadata = (generated_copy.get("metadata") or {}) if isinstance(generated_copy, dict) else {}
    final_quality = metadata.get("final_visible_quality") or generated_copy.get("final_visible_quality") or {}
    if not isinstance(final_quality, dict):
        final_quality = {}
    final_quality_status = str(final_quality.get("operational_status") or "").strip()
    final_quality_blockers = [
        str(item).strip()
        for item in (final_quality.get("paste_ready_blockers") or [])
        if str(item).strip()
    ]
    final_quality_warnings = [
        str(item).strip()
        for item in (final_quality.get("review_only_warnings") or [])
        if str(item).strip()
    ]
    canonical_risk_report = dict(risk_report or {})
    if not canonical_risk_report.get("listing_status"):
        canonical_risk_report["listing_status"] = derive_listing_status(
            metadata.get("generation_status") or scoring_results.get("generation_status") or "",
            canonical_risk_report,
            llm_response_state=metadata.get("llm_response_state") or "",
            visible_fallback_fields=metadata.get("visible_llm_fallback_fields") or [],
        )
    readiness = _listing_readiness(metadata, canonical_risk_report)
    listing_status = readiness.get("status") or "UNKNOWN"
    candidate_operational_status = final_quality_status or listing_status
    if final_quality_blockers:
        listing_status = "NOT_READY_FOR_LISTING"
        action_required = "需先处理 final visible quality 阻断；最终是否可导出以上层 final_readiness_verdict.json 为准"
    final_blocker_lines = [f"- {item}" for item in final_quality_blockers] or ["无"]
    final_warning_lines = [f"- {item}" for item in final_quality_warnings] or ["无"]
    lines = [
        "# Listing Readiness Summary",
        f"**SKU:** {sku}  **Run:** {run_id}  **Date:** {generated_at}",
        "",
        "## 验收结论",
        f"{'✅' if listing_status == 'READY_FOR_LISTING' else '⚠️'} {listing_status}",
        "",
        "## 四维评分",
        *_dimension_rows(scoring_results.get("dimensions") or {}),
        "",
        "## 候选文案状态",
        f"Candidate visible quality: {candidate_operational_status or 'UNKNOWN'}",
        "Operational authority: final_readiness_verdict.json",
        "",
        "### Final Visible Blockers",
        *final_blocker_lines,
        "",
        "### Review Warnings",
        *final_warning_lines,
        "",
        "## 可见文案",
        f"**Title:** {generated_copy.get('title', '')}",
        "",
        "**Bullets:**",
        f"- B1: {bullets[0]}",
        f"- B2: {bullets[1]}",
        f"- B3: {bullets[2]}",
        f"- B4: {bullets[3]}",
        f"- B5: {bullets[4]}",
        "",
        f"**Search Terms:** {search_terms_text}",
        "",
        "## 风险 / 复核项",
        *review_lines,
        "",
        "## 操作建议",
        action_required,
    ]
    return "\n".join(lines) + "\n"
