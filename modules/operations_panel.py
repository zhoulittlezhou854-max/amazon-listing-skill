from __future__ import annotations

from typing import Any, Dict, List

from modules.compute_tiering import summarize_compute_tier_map
from modules.evidence_engine import summarize_evidence_bundle
from modules.intent_weights import summarize_intent_weight_snapshot


EU_LOCALES = {"DE", "FR", "IT", "ES", "UK"}


def build_prelaunch_checklist(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_summary = summarize_evidence_bundle(generated_copy.get("evidence_bundle", {}) or {})
    compute_summary = summarize_compute_tier_map(generated_copy.get("compute_tier_map", {}) or {})
    intent_summary = writing_policy.get("intent_weight_summary") or summarize_intent_weight_snapshot(
        writing_policy.get("intent_weight_snapshot") or {}
    )
    market_pack = writing_policy.get("market_pack", {}) or {}
    listing_status = (risk_report.get("listing_status") or {}).get("status") or scoring_results.get("listing_status") or ""
    blocking_reasons = (risk_report.get("listing_status") or {}).get("blocking_reasons") or scoring_results.get("blocking_reasons") or []
    production = scoring_results.get("production_readiness", {}) or {}
    search_trace = (generated_copy.get("decision_trace") or {}).get("search_terms_trace") or {}
    target_country = str(getattr(preprocessed_data, "target_country", "") or "").upper()
    is_eu = target_country in EU_LOCALES

    items: List[Dict[str, Any]] = []

    def add_item(key: str, label: str, status: str, note: str, blocking: bool) -> None:
        items.append(
            {
                "key": key,
                "label": label,
                "status": status,
                "note": note,
                "blocking": blocking,
            }
        )

    generation_status = production.get("generation_status") or (generated_copy.get("metadata") or {}).get("generation_status") or "offline"
    add_item(
        "generation_status",
        "Live generation status",
        "pass" if generation_status in {"live_success", "live_with_fallback"} else "fail",
        generation_status,
        True,
    )
    add_item(
        "listing_status",
        "Listing blockers cleared",
        "pass" if listing_status != "NOT_READY_FOR_LISTING" and not blocking_reasons else "fail",
        "; ".join(str(item) for item in blocking_reasons) or "no blocking reasons",
        True,
    )
    add_item(
        "unsupported_claims",
        "Unsupported claims resolved",
        "pass" if evidence_summary.get("unsupported_claim_count", 0) == 0 else "fail",
        f"unsupported={evidence_summary.get('unsupported_claim_count', 0)}",
        True,
    )
    add_item(
        "market_pack",
        "Market pack loaded",
        "pass" if market_pack.get("locale") else "warn",
        market_pack.get("locale") or "missing",
        False,
    )
    add_item(
        "after_sales_pack",
        "EU after-sales / SOP pack ready",
        "pass" if (not is_eu) or ((market_pack.get("after_sales_promises") or []) and (market_pack.get("support_sop") or [])) else "warn",
        f"promises={len(market_pack.get('after_sales_promises') or [])} sop={len(market_pack.get('support_sop') or [])}",
        False,
    )
    add_item(
        "compute_fallbacks",
        "Fallback fields under control",
        "pass" if compute_summary.get("fallback_field_count", 0) == 0 else "warn",
        f"fallback_fields={compute_summary.get('fallback_field_count', 0)}",
        False,
    )
    add_item(
        "search_terms_depth",
        "Search terms sufficiently populated",
        "pass" if int(search_trace.get("byte_length") or 0) >= 120 else "warn",
        f"{int(search_trace.get('byte_length') or 0)}/{int(search_trace.get('max_bytes') or 249)} bytes",
        False,
    )
    add_item(
        "aplus_minimum",
        "A+ minimum content ready",
        "pass" if (scoring_results.get("aplus_word_count_check") or {}).get("meets_minimum") else "warn",
        f"meets_minimum={(scoring_results.get('aplus_word_count_check') or {}).get('meets_minimum', False)}",
        False,
    )
    add_item(
        "intent_learning",
        "Intent-learning signal attached",
        "pass" if intent_summary.get("updated_keyword_count", 0) > 0 else "warn",
        f"keywords={intent_summary.get('updated_keyword_count', 0)} themes={intent_summary.get('external_theme_count', 0)}",
        False,
    )

    blocking_count = sum(1 for item in items if item["blocking"] and item["status"] == "fail")
    pass_count = sum(1 for item in items if item["status"] == "pass")
    warn_count = sum(1 for item in items if item["status"] == "warn")

    return {
        "items": items,
        "blocking_count": blocking_count,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "total_count": len(items),
    }


def build_thirty_day_iteration_panel(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> Dict[str, Any]:
    checklist = build_prelaunch_checklist(
        preprocessed_data=preprocessed_data,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report=risk_report,
        scoring_results=scoring_results,
    )
    evidence_summary = summarize_evidence_bundle(generated_copy.get("evidence_bundle", {}) or {})
    intent_summary = writing_policy.get("intent_weight_summary") or summarize_intent_weight_snapshot(
        writing_policy.get("intent_weight_snapshot") or {}
    )
    market_pack = writing_policy.get("market_pack", {}) or {}

    stages = [
        {
            "day": 0,
            "focus": "Launch gate and claim cleanup",
            "primary_metric": "listing_status / unsupported_claims",
            "actions": [
                "Clear any blocking listing-status reason before export.",
                f"Resolve unsupported claims count={evidence_summary.get('unsupported_claim_count', 0)} and rerun if needed.",
            ],
        },
        {
            "day": 7,
            "focus": "Traffic training and external signal capture",
            "primary_metric": "CTR / external themes / promoted keywords",
            "actions": [
                "Upload PPC / Search Term / external review-source snapshot from the first live week.",
                f"Current intent-weight signals: keywords={intent_summary.get('updated_keyword_count', 0)}, themes={intent_summary.get('external_theme_count', 0)}.",
            ],
        },
        {
            "day": 14,
            "focus": "EU localization and after-sales reassurance",
            "primary_metric": "market pack coverage / support SOP readiness",
            "actions": [
                f"Validate locale pack `{market_pack.get('locale') or 'n/a'}` against buyer questions and support tickets.",
                "Tighten B5 / FAQ support reassurance using after-sales SOP and compatibility guidance.",
            ],
        },
        {
            "day": 30,
            "focus": "Scale winners and lock next operating baseline",
            "primary_metric": "AI OS readiness / total score / retained winners",
            "actions": [
                f"Promote surviving themes: {', '.join(intent_summary.get('top_external_themes', [])[:3]) or 'n/a'}.",
                f"Freeze next baseline from total_score={scoring_results.get('total_score', 0)} and ai_os_score={scoring_results.get('ai_os_score', 0)}.",
            ],
        },
    ]

    return {
        "stages": stages,
        "blocking_count": checklist["blocking_count"],
    }

