#!/usr/bin/env python3
"""Node 8 - 最终仲裁报告生成器"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Optional

from modules.compute_tiering import summarize_compute_tier_map
from modules.evidence_engine import summarize_evidence_bundle
from modules.generation_status import is_live_generation_status, is_live_success_status
from modules.intent_weights import summarize_intent_weight_snapshot
from modules.language_utils import get_scene_display
from modules.operations_panel import build_prelaunch_checklist, build_thirty_day_iteration_panel
from modules.writing_policy import LENGTH_RULES


def _safe_get(obj: Any, *attrs, default=None):
    current = obj
    for attr in attrs:
        if current is None:
            return default
        current = getattr(current, attr, None)
    return current if current is not None else default


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _short_path_display(path: str) -> str:
    if not path:
        return "未提供"
    try:
        return Path(path).name or path
    except Exception:
        return path


def _format_header_usage(headers: Sequence[Dict[str, Any]], limit: int = 15) -> str:
    if not headers:
        return "[ ] 无有效列"
    chunks: List[str] = []
    display_entries = list(headers[:limit])
    remaining = max(0, len(headers) - len(display_entries))
    for entry in display_entries:
        label = entry.get("name") or "-"
        used = bool(entry.get("used"))
        mark = "x" if used else " "
        chunks.append(f"[{mark}] {label}")
    if remaining:
        chunks.append(f"... (+{remaining} 列)")
    return ", ".join(chunks)


def _generation_status(metadata: Dict[str, Any]) -> str:
    status = metadata.get("generation_status")
    if status:
        return status
    provider = metadata.get("llm_provider") or "offline"
    mode = metadata.get("llm_mode") or ("live" if provider != "offline" else "offline")
    if provider == "offline" or mode == "offline":
        return "offline"
    return "live_success"


def _listing_readiness(metadata: Dict[str, Any], risk_report: Dict[str, Any]) -> Dict[str, Any]:
    if (risk_report or {}).get("listing_status"):
        listing_status = risk_report["listing_status"]
        status = listing_status.get("status") or "NOT_READY_FOR_LISTING"
        reasons = listing_status.get("blocking_reasons") or []
        summary = "当前结果可进入人工终审。" if status == "READY_FOR_LISTING" else "当前结果不可直接作为正式上架版本。"
        return {
            "status": status,
            "summary": summary,
            "generation_status": _generation_status(metadata),
            "overall_passed": bool((risk_report or {}).get("overall_passed")),
            "reasons": reasons,
        }
    generation_status = _generation_status(metadata)
    overall_passed = bool((risk_report or {}).get("overall_passed"))
    fallback_count = int(metadata.get("llm_fallback_count") or 0)
    reasons: List[str] = []

    if generation_status == "offline":
        reasons.append("未完成 live LLM 生成")
    if generation_status == "live_with_fallback":
        reasons.append(f"存在 {fallback_count} 个字段 fallback")
    if not overall_passed:
        reasons.append("风险检查未完全通过")

    if is_live_success_status(generation_status) and overall_passed:
        status = "READY_FOR_LISTING"
        summary = "可作为上架前版本进入人工终审。"
    elif is_live_generation_status(generation_status):
        status = "READY_FOR_HUMAN_REVIEW"
        summary = "已完成真实 live 生成，但仍需人工确认风险或 fallback 字段。"
    else:
        status = "NOT_READY"
        summary = "当前结果不可作为正式上架版本使用。"

    return {
        "status": status,
        "summary": summary,
        "generation_status": generation_status,
        "overall_passed": overall_passed,
        "reasons": reasons,
    }


def _generation_authenticity_block(metadata: Dict[str, Any]) -> List[str]:
    configured_model = metadata.get("configured_model") or metadata.get("llm_model") or "unknown"
    returned_model = metadata.get("returned_model") or "unknown"
    lines = ["## Generation Authenticity"]
    lines.append(f"- Generation Status: {_generation_status(metadata)}")
    lines.append(f"- Provider: {metadata.get('llm_provider') or 'offline'}")
    lines.append(f"- Configured Model: {configured_model}")
    lines.append(f"- Returned Model: {returned_model}")
    lines.append(f"- Mode: {metadata.get('llm_mode') or 'offline'}")
    lines.append(f"- Wire API: {metadata.get('llm_wire_api') or 'chat/completions'}")
    lines.append(f"- Base URL: {metadata.get('llm_base_url') or 'n/a'}")
    lines.append(f"- Request ID: {metadata.get('llm_request_id') or 'n/a'}")
    latency = metadata.get("llm_latency_ms")
    lines.append(f"- Latency: {latency if latency is not None else 'n/a'} ms")
    lines.append(f"- Fallback Fields: {metadata.get('llm_fallback_count', 0)}")
    visible_fallbacks = metadata.get("visible_llm_fallback_fields") or []
    if visible_fallbacks:
        lines.append(f"- Visible Fallback Fields: {', '.join(visible_fallbacks)}")
    healthcheck = metadata.get("llm_healthcheck") or {}
    if healthcheck:
        lines.append(
            "- Healthcheck: "
            f"ok={healthcheck.get('ok')} "
            f"request_id={healthcheck.get('request_id') or 'n/a'} "
            f"model={healthcheck.get('returned_model') or healthcheck.get('configured_model') or 'n/a'}"
        )
    error = metadata.get("llm_response_error") or ""
    if error:
        lines.append(f"- Last Response Error: {error}")
    return lines


def _operations_payload_block(generated_copy: Dict[str, Any]) -> List[str]:
    bullets = generated_copy.get("bullets", []) or []
    faq = generated_copy.get("faq", []) or []
    search_terms = generated_copy.get("search_terms", []) or []
    lines = ["## Part 1：运营部分", "### 亚马逊后台可配置内容"]
    lines.append("**Title / item_name**")
    lines.append(generated_copy.get("title", "N/A"))
    lines.append("")
    lines.append("**Key Product Features / bullet_points**")
    for idx, bullet in enumerate(bullets[:5], 1):
        lines.append(f"{idx}. {bullet}")
    if not bullets:
        lines.append("- N/A")
    lines.append("")
    lines.append("**Product Description / product_description**")
    lines.append(generated_copy.get("description", "N/A"))
    lines.append("")
    lines.append("**Search Terms / generic_keywords**")
    lines.append(", ".join(search_terms) if search_terms else "N/A")
    lines.append("")
    lines.append("**FAQ / customer_qna_seed**")
    if faq:
        for item in faq:
            lines.append(f"- Q: {item.get('q', '')}")
            lines.append(f"  A: {item.get('a', '')}")
    else:
        lines.append("- N/A")
    lines.append("")
    lines.append("**A+ Content / brand_story_modules**")
    lines.append(generated_copy.get("aplus_content", "N/A"))
    return lines


def _operations_strategy_summary(
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> List[str]:
    metadata = generated_copy.get("metadata", {}) or {}
    production = scoring_results.get("production_readiness", {}) or {}
    keyword_routing = writing_policy.get("keyword_routing", {}) or {}
    lines = ["", "### 运营摘要"]
    lines.append(f"- 上架状态：{production.get('generation_status') or _generation_status(metadata)}")
    lines.append(
        f"- 标题长度：{metadata.get('title_length', len(generated_copy.get('title', '')))} / {LENGTH_RULES['title']['hard_ceiling']}"
    )
    lines.append(f"- Bullet 数量：{metadata.get('bullets_count', len(generated_copy.get('bullets', []) or []))} / 5")
    lines.append(f"- Search Terms 数量：{metadata.get('search_terms_count', len(generated_copy.get('search_terms', []) or []))}")
    lines.append(
        f"- 流量词路由：Title={', '.join(keyword_routing.get('title_traffic_keywords', [])[:3]) or '未配置'}"
    )
    lines.append(
        f"- 转化词路由：Bullets={', '.join(keyword_routing.get('bullet_conversion_keywords', [])[:5]) or '未配置'}"
    )
    lines.append(
        f"- 后台词路由：Search Terms={', '.join(keyword_routing.get('backend_longtail_keywords', [])[:8]) or '未配置'}"
    )
    return lines


def _system_process_block(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> List[str]:
    metadata = generated_copy.get("metadata", {}) or {}
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    lines = ["## Part 2：系统部分"]
    lines.extend(_generation_authenticity_block(metadata))
    lines.append("")
    lines.append("### 实际读取参数")
    lines.append(f"- Target language: {metadata.get('target_language') or getattr(preprocessed_data, 'language', 'unknown')}")
    lines.append(f"- Runtime minutes: {constraints.get('runtime_minutes', 'n/a')}")
    lines.append(f"- Waterproof depth: {constraints.get('waterproof_depth_m', 'n/a')}")
    lines.append(f"- Waterproof requires case: {constraints.get('waterproof_requires_case', 'n/a')}")
    lines.append(f"- Stabilization modes: {', '.join(constraints.get('stabilization_modes', []) or []) or 'n/a'}")
    lines.append(f"- Accessory catalog count: {constraints.get('accessory_catalog_count', 'n/a')}")
    lines.append("")
    lines.append("### 写入策略快照")
    lines.append(_policy_details_section(writing_policy))
    lines.append("")
    lines.extend(_data_ingestion_audit_block(preprocessed_data, generated_copy))
    lines.append("")
    lines.append("### 评分与过程指标")
    lines.append(_scoring_tables(scoring_results))
    return lines


def _evidence_alignment_block(generated_copy: Dict[str, Any]) -> List[str]:
    evidence_bundle = generated_copy.get("evidence_bundle", {}) or {}
    claim_support_matrix = evidence_bundle.get("claim_support_matrix", []) or []
    rufus_readiness = evidence_bundle.get("rufus_readiness", {}) or {}

    lines = ["### Evidence Alignment"]
    if not claim_support_matrix:
        lines.append("- No structured evidence bundle available.")
        return lines

    lines.append(
        "- Rufus readiness: "
        f"{rufus_readiness.get('score', 0.0)} "
        f"({rufus_readiness.get('supported_claim_count', 0)}/{rufus_readiness.get('total_claim_count', 0)} supported)"
    )
    for row in claim_support_matrix[:8]:
        claim = row.get("claim") or "unknown claim"
        support_status = row.get("support_status") or "unknown"
        lines.append(f"- {claim}: {support_status}")
    return lines


def _market_pack_block(writing_policy: Dict[str, Any]) -> List[str]:
    market_pack = writing_policy.get("market_pack", {}) or {}
    lines = ["### Market Pack"]
    if not market_pack:
        lines.append("- No market pack loaded.")
        return lines
    lines.append(f"- Locale: {market_pack.get('locale') or 'unknown'}")
    lexical_preferences = ", ".join(market_pack.get("lexical_preferences", [])[:4]) or "n/a"
    faq_templates = ", ".join(market_pack.get("faq_templates", [])[:4]) or "n/a"
    reminders = ", ".join(market_pack.get("compliance_reminders", [])[:4]) or "n/a"
    lines.append(f"- Lexical Preferences: {lexical_preferences}")
    lines.append(f"- FAQ Templates: {faq_templates}")
    lines.append(f"- Compliance Reminders: {reminders}")
    return lines


def _bundle_variant_block(preprocessed_data: Any) -> List[str]:
    entity_profile = getattr(preprocessed_data, "asin_entity_profile", {}) or {}
    supplement_signals = getattr(preprocessed_data, "supplement_signals", {}) or {}
    bundle_variant = (
        entity_profile.get("bundle_variant")
        or getattr(preprocessed_data, "bundle_variant", None)
        or supplement_signals.get("bundle_variant")
        or {}
    )

    lines = ["### Bundle Variant"]
    if not bundle_variant:
        lines.append("- No bundle-variant metadata detected.")
        return lines

    accessories = ", ".join(bundle_variant.get("included_accessories") or []) or "n/a"
    card_capacity = bundle_variant.get("card_capacity_gb")
    lines.append(f"- Included Accessories: {accessories}")
    lines.append(f"- Card Capacity: {card_capacity} GB" if card_capacity else "- Card Capacity: n/a")
    source = bundle_variant.get("source")
    if source:
        lines.append(f"- Source: {source}")
    return lines


def _after_sales_sop_block(writing_policy: Dict[str, Any]) -> List[str]:
    market_pack = writing_policy.get("market_pack", {}) or {}
    locale = str(market_pack.get("locale") or "").upper()
    title = "### EU After-Sales & SOP" if locale in {"DE", "FR", "IT", "ES", "UK"} else "### After-Sales & SOP"
    promises = list(market_pack.get("after_sales_promises") or [])
    sop = list(market_pack.get("support_sop") or [])
    watchouts = list(market_pack.get("regulatory_watchouts") or [])
    launch_checks = list(market_pack.get("launch_gate_checks") or [])

    lines = [title]
    if not any([promises, sop, watchouts, launch_checks]):
        lines.append("- No after-sales / SOP pack loaded.")
        return lines
    lines.append(f"- After-sales promises: {', '.join(promises[:4]) or 'n/a'}")
    lines.append(f"- Support SOP: {', '.join(sop[:4]) or 'n/a'}")
    if watchouts:
        lines.append(f"- Regulatory watchouts: {', '.join(watchouts[:4])}")
    if launch_checks:
        lines.append(f"- Launch gate checks: {', '.join(launch_checks[:4])}")
    return lines


def _compute_tier_block(generated_copy: Dict[str, Any]) -> List[str]:
    compute_tier_map = generated_copy.get("compute_tier_map", {}) or {}
    lines = ["### Compute Tier Map"]
    if not compute_tier_map:
        lines.append("- No compute tier map available.")
        return lines

    def _display_field(field_name: str) -> str:
        if field_name == "title":
            return "Title"
        if field_name == "description":
            return "Description"
        if field_name == "search_terms":
            return "Search Terms"
        if field_name == "aplus_content":
            return "A+ Content"
        if field_name.startswith("bullet_"):
            return f"Bullet {field_name.split('_', 1)[1]}"
        return field_name

    def _display_tier(tier_name: str) -> str:
        mapping = {
            "native": "Native",
            "polish": "Polish",
            "rule_based": "Rule-Based",
        }
        return mapping.get(tier_name, tier_name or "Unknown")

    for field_name, info in compute_tier_map.items():
        lines.append(
            f"- [{_display_field(field_name)}: {_display_tier(info.get('tier_used', 'unknown'))}] "
            f"rerun={info.get('rerun_recommended', False)}"
        )
    return lines


def _prelaunch_checklist_block(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> List[str]:
    checklist = build_prelaunch_checklist(preprocessed_data, generated_copy, writing_policy, risk_report, scoring_results)
    lines = ["### Pre-Launch Checklist"]
    for item in checklist.get("items", []):
        lines.append(f"- [{item.get('status')}] {item.get('label')}: {item.get('note')}")
    lines.append(
        f"- Summary: blocking={checklist.get('blocking_count', 0)} "
        f"warn={checklist.get('warn_count', 0)} pass={checklist.get('pass_count', 0)}"
    )
    return lines


def _thirty_day_iteration_block(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> List[str]:
    panel = build_thirty_day_iteration_panel(preprocessed_data, generated_copy, writing_policy, risk_report, scoring_results)
    lines = ["### 30-Day Iteration Panel"]
    for stage in panel.get("stages", []):
        lines.append(f"- Day {stage.get('day')}: {stage.get('focus')} ({stage.get('primary_metric')})")
        for action in stage.get("actions", [])[:2]:
            lines.append(f"  - {action}")
    return lines


def _operator_summary_block(generated_copy: Dict[str, Any], writing_policy: Dict[str, Any]) -> List[str]:
    evidence_summary = summarize_evidence_bundle(generated_copy.get("evidence_bundle", {}) or {})
    compute_tier_summary = summarize_compute_tier_map(generated_copy.get("compute_tier_map", {}) or {})
    intent_weight_summary = writing_policy.get("intent_weight_summary") or summarize_intent_weight_snapshot(
        writing_policy.get("intent_weight_snapshot") or {}
    )
    market_pack = writing_policy.get("market_pack", {}) or {}

    return [
        "### Operator Summary",
        f"- Unsupported claims: {evidence_summary.get('unsupported_claim_count', 0)}",
        f"- Rufus readiness: {evidence_summary.get('rufus_score', 0.0)}",
        f"- Market pack: {market_pack.get('locale') or 'n/a'}",
        f"- Fallback fields: {compute_tier_summary.get('fallback_field_count', 0)}",
        f"- Intent weight updates: {intent_weight_summary.get('updated_keyword_count', 0)}",
        f"- External themes: {', '.join(intent_weight_summary.get('top_external_themes', [])[:3]) or 'n/a'}",
        f"- Traffic channels: {', '.join(intent_weight_summary.get('channels', [])[:3]) or 'n/a'}",
    ]


def _diagnosis_and_optimization_block(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]],
) -> List[str]:
    decision_trace = generated_copy.get("decision_trace") or {}
    lines = ["## Part 3：诊断与优化部分"]
    lines.append("### 上架风险检查")
    lines.append(_compliance_section(risk_report))
    lines.append("")
    lines.append("### 真值一致性")
    lines.append(_truth_consistency_section(risk_report))
    lines.append("")
    lines.append("### 流量词留存率")
    lines.append(_traffic_retention_section(risk_report))
    lines.append("")
    lines.append("### 语言一致性")
    lines.append(_language_consistency_section(risk_report))
    lines.append("")
    lines.append("### 策略执行审计")
    lines.append(_policy_audit_section(risk_report))
    lines.append("")
    lines.append("### 自动删改审计")
    lines.append(_audit_trail_section(generated_copy.get("audit_trail")))
    lines.append("")
    lines.append("### 关键词分布检测")
    lines.extend(_keyword_distribution_section(writing_policy, generated_copy, decision_trace))
    lines.append("")
    lines.append("### Keyword Routing Delta")
    lines.append(_a10_routing_delta_section(writing_policy, decision_trace, generated_copy))
    lines.append("")
    lines.append("### 竞品差异化分析")
    lines.extend(_competitor_diff_points(preprocessed_data))
    lines.append("")
    lines.append("### STAG 广告投放建议")
    lines.append(_markdown_table(["STAG 场景", "优先关键词", "目标人群", "投放建议"], _stag_rows(writing_policy, generated_copy)))
    lines.append("")
    lines.append("### Rufus Q&A 种子")
    lines.append(_markdown_table(["序号", "问题种子", "答案要点"], _rufus_seed_rows(preprocessed_data, generated_copy)))
    lines.append("")
    lines.append("### 下一轮优化建议")
    lines.extend(_optimization_section(preprocessed_data, generated_copy, writing_policy, scoring_results, intent_graph))
    return lines


def _listing_readiness_block(metadata: Dict[str, Any], risk_report: Dict[str, Any]) -> List[str]:
    readiness = _listing_readiness(metadata, risk_report)
    lines = ["## Listing Readiness"]
    lines.append(f"- Status: {readiness['status']}")
    lines.append(f"- Summary: {readiness['summary']}")
    if readiness["reasons"]:
        lines.append("- Reasons:")
        for reason in readiness["reasons"]:
            lines.append(f"  - {reason}")
    else:
        lines.append("- Reasons: none")
    return lines


def _data_ingestion_audit_block(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> List[str]:
    audit = getattr(preprocessed_data, "ingestion_audit", {}) or {}
    metadata = generated_copy.get("metadata", {}) or {}
    lines: List[str] = ["[Data Ingestion Audit]"]

    model_name = metadata.get("configured_model") or metadata.get("llm_model") or "offline"
    returned_model = metadata.get("returned_model") or "unknown"
    provider = metadata.get("llm_provider") or "offline"
    mode = metadata.get("llm_mode") or ("live" if provider != "offline" else "offline")
    credential = metadata.get("llm_credential_source") or "none"
    lines.append(f"- Generated using LLM: {model_name}")
    lines.append(f"- Returned model: {returned_model}")
    lines.append(f"- Provider: {provider}")
    lines.append(f"- Mode: {mode}")
    lines.append(f"- Generation status: {_generation_status(metadata)}")
    lines.append(f"- Wire API: {metadata.get('llm_wire_api') or 'chat/completions'}")
    lines.append(f"- Request ID: {metadata.get('llm_request_id') or 'n/a'}")
    lines.append(f"- Credential source: {credential}")

    tables = audit.get("tables") or []
    if tables:
        for table in tables:
            label = table.get("label") or table.get("id") or "Data Table"
            short_path = _short_path_display(table.get("path", ""))
            row_count = table.get("row_count", 0)
            headers = table.get("headers") or []
            has_data = bool(row_count) or any(header.get("used") for header in headers)
            status = "[x]" if has_data else "[ ]"
            lines.append(f"- {status} {label} ({short_path}) → {row_count} rows")
            lines.append(f"  Headers: {_format_header_usage(headers)}")
    else:
        lines.append("- 未检测到结构化数据表。")

    insights_meta = audit.get("raw_human_insights") or {}
    if insights_meta:
        desc = f"{insights_meta.get('chars', 0)} chars"
        if insights_meta.get("truncated"):
            desc += " (truncated)"
        lines.append(f"- raw_human_insights buffer: {desc}")

    return lines


def _extract_keyword_tiers(preprocessed_data: Any) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    keywords = _safe_get(preprocessed_data, "keyword_data", "keywords", default=[]) or []
    for row in keywords:
        keyword = row.get("keyword") or row.get("search_term")
        if not keyword:
            continue
        try:
            volume = float(row.get("search_volume", 0))
        except (TypeError, ValueError):
            volume = 0
        if volume >= 10000:
            tier = "L1"
        elif volume >= 1000:
            tier = "L2"
        else:
            tier = "L3"
        mapping[keyword] = tier
    return mapping


def _keyword_locations(keyword: str, generated_copy: Dict[str, Any]) -> str:
    locations = []
    if not keyword:
        return "-"
    keyword_lower = keyword.lower()
    if keyword_lower in generated_copy.get("title", "").lower():
        locations.append("Title")
    for idx, bullet in enumerate(generated_copy.get("bullets", []) or [], 1):
        if keyword_lower in bullet.lower():
            locations.append(f"B{idx}")
    if keyword_lower in generated_copy.get("description", "").lower():
            locations.append("Description")
    st_text = " ".join(generated_copy.get("search_terms", []) or [])
    if keyword_lower in st_text.lower():
        locations.append("Search Terms")
    if not locations:
        locations.append("未覆盖")
    return "、".join(locations)


def _keyword_coverage_rows(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> List[List[str]]:
    mapping = _extract_keyword_tiers(preprocessed_data)
    rows: List[List[str]] = []
    for keyword, tier in list(mapping.items())[:12]:
        rows.append([keyword, tier, _keyword_locations(keyword, generated_copy)])
    if not rows:
        rows.append(["样例关键词", "L2", "Search Terms"])
    return rows


def _collect_keyword_arsenal(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> Dict[str, List[str]]:
    arsenal: Dict[str, List[str]] = {"L1": [], "L2": [], "L3": []}
    seen = {"L1": set(), "L2": set(), "L3": set()}

    def _add(keyword: str, tier: str) -> None:
        normalized_tier = (tier or "").upper()
        normalized_keyword = (keyword or "").strip()
        if normalized_tier not in arsenal or not normalized_keyword:
            return
        dedupe_key = normalized_keyword.lower()
        if dedupe_key in seen[normalized_tier]:
            return
        seen[normalized_tier].add(dedupe_key)
        arsenal[normalized_tier].append(normalized_keyword)

    decision_trace = generated_copy.get("decision_trace") or {}
    for entry in decision_trace.get("keyword_assignments") or []:
        _add(entry.get("keyword", ""), entry.get("tier", ""))

    for entry in getattr(preprocessed_data, "keyword_metadata", []) or []:
        _add(entry.get("keyword", ""), entry.get("tier", ""))

    if not any(arsenal.values()):
        for keyword, tier in _extract_keyword_tiers(preprocessed_data).items():
            _add(keyword, tier)

    return arsenal


def _keyword_arsenal_block(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> List[str]:
    arsenal = _collect_keyword_arsenal(preprocessed_data, generated_copy)

    def _render_keywords(keywords: Sequence[str]) -> List[str]:
        return [f"- {keyword}" for keyword in keywords] or ["- 无"]

    lines = [
        "## Keyword Arsenal",
        "",
        "### L1 — Title Keywords",
        "（直接用于 title 的核心词，最高权重）",
        *_render_keywords(arsenal["L1"]),
        "",
        "### L2 — Bullet Keywords",
        "（用于 bullets 的次级词，中等权重）",
        *_render_keywords(arsenal["L2"]),
        "",
        "### L3 — Search Terms Keywords",
        "（用于 search terms 的长尾词，低权重）",
        *_render_keywords(arsenal["L3"]),
        "",
        "### Routing Summary",
        "- L1 → Title: these keywords must appear in the product title",
        "- L2 → Bullets: these keywords should be naturally integrated into bullets",
        "- L3 → Search Terms: these keywords go into backend search terms field",
    ]
    return lines


def _collect_assignment_stats(assignments: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for tier in ("L1", "L2", "L3"):
        tier_entries = [
            entry for entry in assignments
            if (entry.get("tier") or "").upper() == tier
        ]
        stats[tier] = {
            "total": len(tier_entries),
            "title_hits": sum(
                any(str(field).startswith("title") for field in entry.get("assigned_fields") or [])
                for entry in tier_entries
            ),
            "visible_hits": sum(
                any(str(field).startswith("title") or str(field).startswith("bullet_")
                    for field in entry.get("assigned_fields") or [])
                for entry in tier_entries
            ),
            "search_hits": sum(
                "search_terms" in (entry.get("assigned_fields") or [])
                for entry in tier_entries
            ),
            "entries": tier_entries,
        }
    return stats


def _scene_distribution_notes(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> List[str]:
    scene_notes: List[str] = []
    scenes = writing_policy.get("scene_priority", []) or []
    language = writing_policy.get("language", "English")
    text_fields: Dict[str, str] = {
        "title": (generated_copy.get("title") or "").lower(),
        "search_terms": (" ".join(generated_copy.get("search_terms", []) or [])).lower()
    }
    for idx, bullet in enumerate(generated_copy.get("bullets", []) or [], 1):
        text_fields[f"bullet_b{idx}"] = bullet.lower()

    for scene_code in scenes[:5]:
        display = get_scene_display(scene_code, language) or scene_code.replace("_", " ")
        synonyms = {
            display.lower(),
            scene_code.replace("_", " ").lower()
        }
        coverage_fields = [
            field for field, text in text_fields.items()
            if any(term and term in text for term in synonyms)
        ]
        if len(coverage_fields) <= 1:
            field_str = coverage_fields[0] if coverage_fields else "任何字段"
            scene_notes.append(f"{display} 仅出现在 {field_str} → Scene 覆盖不足")
    return scene_notes


def _l2_overlap_notes(assignments: Sequence[Dict[str, Any]]) -> List[str]:
    notes: List[str] = []
    for entry in assignments:
        if (entry.get("tier") or "").upper() != "L2":
            continue
        fields = entry.get("assigned_fields") or []
        has_visible = any(str(field).startswith("title") or str(field).startswith("bullet_") for field in fields)
        if "search_terms" in fields and has_visible:
            keyword = entry.get("keyword") or "L2关键词"
            notes.append(f"{keyword} 同时位于可见字段与 Search Terms → 可替换为 L3 长尾词")
    return notes


def _slot_keywords(keyword_slots: Dict[str, Any], slot_key: str) -> List[str]:
    if not keyword_slots:
        return []
    if slot_key == "title":
        return keyword_slots.get("title") or []
    slot_meta = keyword_slots.get(slot_key) or {}
    if isinstance(slot_meta, dict):
        return list(slot_meta.get("keywords") or [])
    if isinstance(slot_meta, list):
        return slot_meta
    return []


def _assignment_lookup(assignments: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for entry in assignments or []:
        keyword = (entry.get("keyword") or "").strip().lower()
        if keyword:
            lookup[keyword] = entry
    return lookup


def _field_contains_keyword(keyword: str,
                            field_label: str,
                            assignment_index: Dict[str, Dict[str, Any]],
                            generated_copy: Dict[str, Any]) -> bool:
    normalized = (keyword or "").strip().lower()
    if not normalized:
        return False
    entry = assignment_index.get(normalized)
    if entry:
        assigned_fields = {
            (field or "").lower() for field in entry.get("assigned_fields") or []
        }
        if field_label in assigned_fields:
            return True
    target_text = ""
    field_label = field_label.lower()
    if field_label == "title":
        target_text = generated_copy.get("title", "")
    elif field_label.startswith("bullet_b"):
        try:
            idx = int(field_label.replace("bullet_b", "")) - 1
        except ValueError:
            idx = -1
        bullets = generated_copy.get("bullets") or []
        if 0 <= idx < len(bullets):
            target_text = bullets[idx]
    elif field_label == "search_terms":
        terms = generated_copy.get("search_terms") or []
        for term in terms:
            lowered = (term or "").strip().lower()
            if normalized == lowered or normalized in lowered:
                return True
        return False
    return normalized in (target_text or "").lower()


def _a10_routing_delta_section(
    writing_policy: Dict[str, Any],
    decision_trace: Dict[str, Any],
    generated_copy: Dict[str, Any],
) -> str:
    keyword_slots = writing_policy.get("keyword_slots") or {}
    assignments = decision_trace.get("keyword_assignments") or []
    assignment_index = _assignment_lookup(assignments)
    slot_specs = [
        ("title", "Title Slot", "L1", "title"),
        ("bullet_1", "Bullet 1", "L2", "bullet_b1"),
        ("bullet_2", "Bullet 2", "L2", "bullet_b2"),
        ("bullet_3", "Bullet 3", "L2", "bullet_b3"),
        ("search_terms", "Search Terms", "L3", "search_terms"),
    ]
    if not keyword_slots:
        return "- 未配置 keyword_slots，无法计算路由差值。"

    rows: List[List[str]] = []
    gap_alerts: List[str] = []
    for slot_key, slot_label, tier_label, field_label in slot_specs:
        expected_keywords = _slot_keywords(keyword_slots, slot_key)
        requested = len(expected_keywords)
        placed = sum(
            1
            for kw in expected_keywords
            if _field_contains_keyword(kw, field_label, assignment_index, generated_copy)
        )
        status = "OK" if requested == 0 else f"{placed}/{requested}"
        rows.append([slot_label, tier_label, str(requested), status])
        if requested == 0:
            if slot_key != "search_terms":
                gap_alerts.append(f"{slot_label}: 0 {tier_label} keywords available → 词库缺少该层级。")
            continue
        if placed < requested:
            missing = requested - placed
            gap_alerts.append(f"{slot_label}: Missing {missing}x {tier_label} keyword")

    def _collect_leaks(tier: str, allowed_fields: Sequence[str]) -> List[str]:
        leaks: List[str] = []
        allowed = {field.lower() for field in allowed_fields}
        for entry in assignments:
            if (entry.get("tier") or "").upper() != tier.upper():
                continue
            fields = {(field or "").lower() for field in entry.get("assigned_fields") or []}
            if not fields:
                continue
            disallowed = [field for field in fields if field not in allowed]
            if disallowed:
                leaks.append(entry.get("keyword") or tier)
        return leaks

    l1_leaks = _collect_leaks("L1", ["title"])
    if l1_leaks:
        sample = ", ".join(l1_leaks[:3])
        gap_alerts.append(f"L1 Leak: {len(l1_leaks)} keywords spilled outside Title ({sample})")

    l2_allowed = ["bullet_b1", "bullet_b2", "bullet_b3"]
    l2_leaks = _collect_leaks("L2", l2_allowed)
    if l2_leaks:
        sample = ", ".join(l2_leaks[:3])
        gap_alerts.append(f"L2 Leak: {len(l2_leaks)} keywords missed Bullets 1-3 ({sample})")

    l3_leaks = _collect_leaks("L3", ["search_terms"])
    if l3_leaks:
        sample = ", ".join(l3_leaks[:3])
        gap_alerts.append(f"L3 Leak: {len(l3_leaks)} keywords surfaced outside backend ({sample})")

    backend_terms = writing_policy.get("search_term_plan", {}).get("backend_only_terms") or []
    if backend_terms:
        preview = ", ".join(backend_terms[:3])
        gap_alerts.append(f"Backend-only: {len(backend_terms)} keywords quarantined ({preview})")

    table = _markdown_table(
        ["Slot", "Tier", "Requested", "Placed"],
        rows,
    )
    lines = [table]
    if gap_alerts:
        lines.append("")
        lines.append("**Gap Alerts**")
        lines.extend(f"- {alert}" for alert in gap_alerts)
    else:
        lines.append("")
        lines.append("- 所有槽位均满足硬路由要求。")
    return "\n".join(lines)


def _keyword_distribution_section(
    writing_policy: Dict[str, Any],
    generated_copy: Dict[str, Any],
    decision_trace: Dict[str, Any]
) -> List[str]:
    assignments = decision_trace.get("keyword_assignments") or []
    scene_notes = _scene_distribution_notes(writing_policy, generated_copy)
    overlap_notes = _l2_overlap_notes(assignments)
    lines: List[str] = []
    if not scene_notes and not overlap_notes:
        lines.append("- 关键词分布均衡，无需额外调整。")
        return lines
    if scene_notes:
        lines.append("**Scene 覆盖提示**")
        lines.extend([f"- {note}" for note in scene_notes])
    if overlap_notes:
        lines.append("**L2 重复覆盖**")
        lines.extend([f"- {note}" for note in overlap_notes])
    return lines


def _estimate_score_range(
    scoring_results: Dict[str, Any],
    decision_trace: Dict[str, Any],
    missing_keys: Sequence[str]
) -> Dict[str, Any]:
    total_score = scoring_results.get("total_score", 0) or 0
    max_total = scoring_results.get("max_total") or scoring_results.get("max_total_score") or 330
    metric_map = {
        "vocab": [
            ("a10", "l1_title_alignment"),
            ("a10", "l3_search_terms"),
            ("rufus", "search_term_bytes"),
        ],
        "runtime": [("rufus", "numeric_expectations")],
        "accessory": [("rufus", "spec_signal_coverage")],
    }
    added_keys = set()
    potential_gain = 0
    reason_lines: List[str] = []
    for key in missing_keys:
        for block, metric in metric_map.get(key, []):
            block_data = scoring_results.get(block, {}) or {}
            metric_data = block_data.get(metric, {}) or {}
            metric_max = metric_data.get("max")
            metric_score = metric_data.get("score")
            if metric_max is None or metric_score is None:
                continue
            gap = max(0, (metric_max or 0) - (metric_score or 0))
            metric_id = f"{block}.{metric}"
            if gap <= 0 or metric_id in added_keys:
                continue
            added_keys.add(metric_id)
            potential_gain += gap
            note = metric_data.get("note")
            reason_lines.append(f"{metric_id} 可释放 {gap} 分（{note or '无备注'}）")

    estimated_upper = min(max_total, total_score + potential_gain)
    if estimated_upper < total_score:
        estimated_upper = total_score

    stats = _collect_assignment_stats((decision_trace or {}).get("keyword_assignments") or [])
    search_trace = (decision_trace or {}).get("search_terms_trace") or {}
    trace_notes: List[str] = []
    if "vocab" in missing_keys and stats:
        l1_total = stats.get("L1", {}).get("total", 0)
        l1_title = stats.get("L1", {}).get("title_hits", 0)
        byte_len = search_trace.get("byte_length") or 0
        byte_max = search_trace.get("max_bytes") or 249
        trace_notes.append(
            f"decision_trace：L1 {l1_title}/{l1_total} 命中，Search Terms {byte_len}/{byte_max} bytes"
        )
    if "runtime" in missing_keys:
        trace_notes.append("decision_trace：存在 numeric_expectation 未满足的 bullet")
    if "accessory" in missing_keys:
        trace_notes.append("audit_trail：存在 accessories fallback 记录")

    return {
        "current": total_score,
        "max_total": max_total,
        "range": f"{total_score} ~ {estimated_upper}",
        "reasons": reason_lines,
        "trace_notes": trace_notes,
    }


def _confidence_summary_block(
    preprocessed_data: Any,
    scoring_results: Dict[str, Any],
    decision_trace: Dict[str, Any],
    generated_copy: Dict[str, Any],
) -> List[str]:
    target_country = (_safe_get(preprocessed_data, "run_config", "target_country", default="--") or "--").upper()
    real_vocab = getattr(preprocessed_data, "real_vocab", None)
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    metadata = generated_copy.get("metadata", {}) or {}

    checks: List[Dict[str, Any]] = []
    generation_status = _generation_status(metadata)
    checks.append({
        "key": "authenticity",
        "ok": is_live_success_status(generation_status),
        "ok_label": "✅ live GPT 生成完成",
        "missing_label": "❌ 生成真实性不足",
        "detail": (
            f"generation_status={generation_status}, "
            f"provider={metadata.get('llm_provider') or 'offline'}, "
            f"returned_model={metadata.get('returned_model') or 'unknown'}"
        ),
    })
    vocab_count = getattr(real_vocab, "total_count", 0) if real_vocab else 0
    if target_country in {"FR", "DE"}:
        vocab_ok = vocab_count >= 50
        detail = f"当前 {vocab_count} 条"
    else:
        vocab_ok = True
        detail = f"{target_country} 站点无需本地词库"
    checks.append({
        "key": "vocab",
        "ok": vocab_ok,
        "ok_label": f"✅ {target_country} 词库 ≥50 条",
        "missing_label": f"❌ {target_country} 词库稀疏",
        "detail": detail
    })

    runtime_minutes = constraints.get("runtime_minutes")
    checks.append({
        "key": "runtime",
        "ok": bool(runtime_minutes),
        "ok_label": "✅ runtime_minutes 已填写",
        "missing_label": "❌ runtime_minutes 缺失",
        "detail": f"runtime_minutes: {runtime_minutes if runtime_minutes else '缺失'}"
    })

    accessory_count = constraints.get("accessory_catalog_count") or 0
    checks.append({
        "key": "accessory",
        "ok": accessory_count > 0,
        "ok_label": "✅ accessory_catalog_count > 0",
        "missing_label": "❌ accessory_catalog 缺失",
        "detail": f"accessory_catalog_count: {accessory_count}"
    })

    passed = sum(1 for c in checks if c["ok"])
    total = len(checks)
    if not is_live_success_status(generation_status):
        descriptor = "🔴 评分仅供参考：当前结果未达到 live_success，不能视为正式可上架评分"
    elif passed == total:
        descriptor = "✅ 评分可信：数据充分，当前分数反映真实潜力"
    elif passed == total - 1:
        descriptor = "⚠️ 评分中等可信：存在 1 项数据缺口，分数可能偏低"
    else:
        descriptor = "🔴 评分仅供参考：存在多项数据缺口，当前分数低估真实潜力"

    missing_keys = [c["key"] for c in checks if not c["ok"]]
    summary = _estimate_score_range(scoring_results, decision_trace, missing_keys)

    lines = ["## 评分可信度摘要"]
    lines.append(f"- 可信度：{passed}/{total} → {descriptor}")
    if missing_keys:
        lines.append("- 数据缺口：")
        for check in checks:
            if check["ok"]:
                continue
            missing_label = check.get("missing_label") or check.get("ok_label") or check.get("key")
            lines.append(f"  - {missing_label}（{check['detail']}）")
    else:
        lines.append("- 数据缺口：无")

    lines.append(
        f"- 补齐后预计分数区间：{summary['range']}（当前 {summary['current']}/{summary['max_total']}）"
    )
    if summary.get("reasons"):
        lines.append("  - 依据：" + "；".join(summary["reasons"]))
    if summary.get("trace_notes"):
        lines.append("  - decision_trace：" + "；".join(summary["trace_notes"]))

    return lines


def _policy_details_section(writing_policy: Dict[str, Any]) -> str:
    lines: List[str] = []
    bullet_rules = writing_policy.get("bullet_slot_rules", {})
    rule_rows: List[List[str]] = []
    for slot in ["B1", "B2", "B3", "B4", "B5"]:
        rule = bullet_rules.get(slot)
        if isinstance(rule, dict):
            rule_rows.append([
                slot,
                rule.get("role", "-"),
                str(rule.get("scene_index", "-")),
                rule.get("tier", "-")
            ])
        elif rule:
            rule_rows.append([slot, str(rule), "-", "-"])
    if rule_rows:
        lines.append("### Bullet Slot Rules")
        lines.append(_markdown_table(["Slot", "Role", "Scene Idx", "Tier"], rule_rows))

    directives = writing_policy.get("compliance_directives", {})
    if directives:
        water = directives.get("waterproof", {})
        stab = directives.get("stabilization", {})
        lines.append("")
        lines.append("### Compliance Directives")
        lines.append(
            f"- Waterproof visible: {water.get('allow_visible', True)}"
            f"{' (requires housing)' if water.get('requires_case') else ''}, depth: {water.get('depth_m', 'n/a')}m"
        )
        if water.get("note"):
            lines.append(f"  - Note: {water['note']}")
        lines.append(f"- Stabilization visible: {stab.get('allow_visible', True)}, modes: {', '.join(stab.get('modes', [])) or 'n/a'}")
        if stab.get("note"):
            lines.append(f"  - Note: {stab['note']}")
        if directives.get("runtime_minutes"):
            lines.append(f"- Runtime proof: {directives['runtime_minutes']} min")

    search_plan = writing_policy.get("search_term_plan", {})
    if search_plan:
        lines.append("")
        lines.append("### Search Term Plan")
        lines.append(f"- Tier priority: {', '.join(search_plan.get('priority_tiers', [])) or '未定义'}")
        lines.append(f"- Byte limit: {search_plan.get('max_bytes', 249)}")
        backend_terms = search_plan.get("backend_only_terms", [])
        if backend_terms:
            lines.append(f"- Backend-only keywords: {', '.join(backend_terms)}")

    keyword_routing = writing_policy.get("keyword_routing", {}) or {}
    if keyword_routing:
        lines.append("")
        lines.append("### Keyword Routing")
        lines.append(
            f"- Title traffic keywords: {', '.join(keyword_routing.get('title_traffic_keywords', [])) or '未配置'}"
        )
        lines.append(
            f"- Bullet conversion keywords: {', '.join(keyword_routing.get('bullet_conversion_keywords', [])) or '未配置'}"
        )
        lines.append(
            f"- Backend long-tail keywords: {', '.join(keyword_routing.get('backend_longtail_keywords', [])) or '未配置'}"
        )

    return "\n".join(lines) if lines else "- 未配置结构化策略。"


def _audit_trail_section(audit_trail: Sequence[Dict[str, Any]]) -> str:
    if not audit_trail:
        return "暂无自动删改或降级记录。"
    action_map = {
        "delete": "删除",
        "downgrade": "降级",
        "backend_only": "转入后台",
        "truncate": "剪裁",
        "fallback": "结构兜底",
        "numeric_patch": "补充参数",
        "dedupe_skip": "去重",
        "visible_skip": "可见字段已包含",
    }
    rows: List[List[str]] = []
    for entry in list(audit_trail)[:25]:
        field = entry.get("field", "-")
        action_cn = action_map.get(entry.get("action"), entry.get("action", "-"))
        details = []
        for key, value in entry.items():
            if key in {"field", "action"}:
                continue
            if value in (None, "", []):
                continue
            details.append(f"{key}:{value}")
        rows.append([field, action_cn, "；".join(details) or "—"])
    return _markdown_table(["字段", "动作", "细节"], rows)


def _compliance_section(risk_report: Dict[str, Any]) -> str:
    compliance = (risk_report or {}).get("compliance", {})
    passed = compliance.get("passed", 0)
    total = compliance.get("total", 0)
    issues = compliance.get("issues", [])
    lines = [f"- 通过情况：{passed}/{total}", f"- 风险条目：{len(issues)}"]
    if issues:
        for issue in issues[:5]:
            lines.append(f"  - [{issue.get('severity', 'n/a')}] {issue.get('description', '未知')} ({issue.get('pattern', '-')})")
    else:
        lines.append("  - 未检测到违规词。")
    return "\n".join(lines)


def _policy_audit_section(risk_report: Dict[str, Any]) -> str:
    audit = (risk_report or {}).get("policy_audit", {})
    warnings = ((risk_report or {}).get("production_warnings") or {}).get("issues", [])
    passed = audit.get("passed", 0)
    total = audit.get("total", 0)
    issues = audit.get("issues", [])
    lines = [f"- 约束通过：{passed}/{total}", f"- 未通过条目：{len(issues)}", f"- 生产提醒：{len(warnings)}"]
    if issues:
        for issue in issues[:6]:
            lines.append(f"  - {issue.get('rule', '规则')}: {issue.get('description', '未提供描述')}")
    else:
        lines.append("  - 六条硬性约束均满足。")
    if warnings:
        for warning in warnings[:4]:
            lines.append(f"  - [提醒] {warning.get('rule', '规则')}: {warning.get('description', '未提供描述')}")
    return "\n".join(lines)


def _truth_consistency_section(risk_report: Dict[str, Any]) -> str:
    truth = (risk_report or {}).get("truth_consistency", {})
    passed = truth.get("passed", 0)
    total = truth.get("total", 0)
    issues = truth.get("issues", [])
    lines = [f"- 真值通过：{passed}/{total}", f"- 风险条目：{len(issues)}"]
    if issues:
        for issue in issues[:6]:
            lines.append(f"  - [{issue.get('severity', 'n/a')}] {issue.get('description', '未知问题')}")
    else:
        lines.append("  - 可见字段未发现真值冲突。")
    return "\n".join(lines)


def _hybrid_launch_report_block(generated_copy: Dict[str, Any], scoring_results: Dict[str, Any]) -> List[str]:
    metadata = generated_copy.get("metadata") or {}
    if str(metadata.get("visible_copy_mode") or "").strip() != "hybrid_postselect":
        return []

    launch_decision = metadata.get("launch_decision") or {}
    repairs = metadata.get("hybrid_repairs") or []
    source_trace = generated_copy.get("source_trace") or {}
    scores = launch_decision.get("scores") or {
        "A10": ((scoring_results.get("dimensions") or {}).get("traffic") or {}).get("score", 0),
        "COSMO": ((scoring_results.get("dimensions") or {}).get("content") or {}).get("score", 0),
        "Rufus": ((scoring_results.get("dimensions") or {}).get("conversion") or {}).get("score", 0),
        "Fluency": ((scoring_results.get("dimensions") or {}).get("readability") or {}).get("score", 0),
    }
    thresholds = launch_decision.get("thresholds") or {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24}

    lines = ["## Hybrid Launch Decision"]
    lines.append(f"- Recommended Output: `{launch_decision.get('recommended_output', 'unknown')}`")
    lines.append(f"- Hybrid Gate: {'passed' if launch_decision.get('passed') else 'failed'}")
    reason_list = launch_decision.get("reasons") or []
    lines.append(f"- Blocking Reasons: {', '.join(reason_list) if reason_list else 'none'}")
    lines.append(
        "- Scores: "
        f"A10 {scores.get('A10', 0)} / COSMO {scores.get('COSMO', 0)} / "
        f"Rufus {scores.get('Rufus', 0)} / Fluency {scores.get('Fluency', 0)}"
    )
    lines.append(
        "- Thresholds: "
        f"A10 {thresholds.get('A10', 80)} / COSMO {thresholds.get('COSMO', 90)} / "
        f"Rufus {thresholds.get('Rufus', 90)} / Fluency {thresholds.get('Fluency', 24)}"
    )
    lines.append(f"- Source Split: {metadata.get('hybrid_sources') or {}}")
    if source_trace.get("bullets"):
        bullet_summary = ", ".join(
            f"{row.get('slot')}->{row.get('source_version')} ({row.get('selection_reason')})"
            for row in source_trace.get("bullets") or []
        )
        lines.append(f"- Bullet Slots: {bullet_summary}")
    if repairs:
        repair_summary = ", ".join(
            f"{row.get('slot')}:{row.get('keyword')} [{row.get('action')}]" for row in repairs
        )
        lines.append(f"- Repair Actions: {repair_summary}")
    else:
        lines.append("- Repair Actions: none")
    lines.append("")
    return lines


def _traffic_retention_section(risk_report: Dict[str, Any]) -> str:
    retention = (risk_report or {}).get("traffic_retention", {}) or {}
    if not retention.get("enabled"):
        return "- 未启用历史自然流量词留存率检查。"
    lines = [
        f"- 留存率：{retention.get('retention_rate', 0):.0%}",
        f"- 阈值：{retention.get('threshold', 0):.0%}",
        f"- 阻断：{retention.get('is_blocking', False)}",
        f"- 已保留：{', '.join(retention.get('retained_keywords', []) or []) or '-'}",
        f"- 已丢失：{', '.join(retention.get('missing_keywords', []) or []) or '-'}",
    ]
    return "\n".join(lines)


def _language_consistency_section(risk_report: Dict[str, Any]) -> str:
    consistency = (risk_report or {}).get("language_consistency", {})
    passed = consistency.get("passed", 0)
    total = consistency.get("total", 0)
    issues = consistency.get("issues", [])
    lines = [f"- 语言一致性：{passed}/{total}", f"- 风险条目：{len(issues)}"]
    if issues:
        for issue in issues[:4]:
            lines.append(f"  - [{issue.get('severity', 'n/a')}] {issue.get('description', '未知问题')}")
    else:
        lines.append("  - 可见字段语言与目标站点一致。")
    return "\n".join(lines)


def _competitor_diff_points(preprocessed_data: Any) -> List[str]:
    attr_data = _safe_get(preprocessed_data, "attribute_data", "data", default={}) or {}
    selling_points = getattr(preprocessed_data, "core_selling_points", []) or []
    notes: List[str] = []
    if attr_data.get("waterproof_depth"):
        notes.append(f"- 水下场景：强调 {attr_data['waterproof_depth']} 防水，与竞品 10m 方案区分。")
    if attr_data.get("image_stabilization"):
        notes.append(f"- 防抖表现：突出 {attr_data['image_stabilization']} 在高速运动中的稳定性。")
    if attr_data.get("battery_life"):
        notes.append(f"- 续航里程：对比竞品 90 分钟，给出 {attr_data['battery_life']} 实测场景。")
    for point in selling_points[:3]:
        notes.append(f"- 核心卖点「{point}」结合参数输出差异化故事。")
    if not notes:
        notes.append("- 属性与卖点信息不足，需补充竞品差异化素材。")
    return notes[:5]


def _stag_rows(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    scenes = writing_policy.get("scene_priority", []) or []
    search_terms = generated_copy.get("search_terms", []) or []

    # 场景到目标人群的映射
    scene_to_audience = {
        "骑行记录": "骑行爱好者25-45岁，通勤族，户外运动达人",
        "户外运动": "户外运动爱好者20-40岁，登山、滑雪、徒步爱好者",
        "水下探索": "潜水爱好者25-50岁，水上运动爱好者，海洋摄影师",
        "旅行记录": "旅行爱好者22-55岁，背包客，旅游博主，家庭出游",
        "运动训练": "健身爱好者18-35岁，运动员，体育教练，训练记录者",
        "家庭使用": "家庭用户25-45岁，宠物主人，亲子家庭，生活记录者",
        "骑行": "骑行爱好者25-45岁，自行车通勤者，户外运动爱好者",
        "滑雪": "滑雪爱好者20-40岁，冬季运动爱好者，极限运动玩家",
        "登山": "登山爱好者25-50岁，徒步旅行者，户外探险家",
        "潜水": "潜水爱好者25-50岁，水下摄影师，海洋探索者",
        "旅行": "旅行爱好者22-55岁，背包客，旅游达人，度假家庭",
        "运动": "运动爱好者18-40岁，健身人群，运动员，体育爱好者",
        "家庭": "家庭用户25-45岁，父母，宠物主人，家庭活动记录者",
        "宠物": "宠物主人20-50岁，宠物爱好者，动物记录者",
        "儿童": "父母25-40岁，家庭用户，儿童成长记录者"
    }

    for scene in scenes[:5]:
        linked_terms = [kw for kw in search_terms if kw.lower().startswith(scene[:2].lower())][:2]
        if not linked_terms:
            linked_terms = search_terms[:2]

        # 获取目标人群描述，如果找不到则使用通用描述
        audience = scene_to_audience.get(scene)
        if not audience:
            # 尝试部分匹配
            for key, value in scene_to_audience.items():
                if key in scene:
                    audience = value
                    break
            if not audience:
                audience = f"目标人群：{scene or '泛用'}爱好者20-45岁"
        else:
            audience = f"目标人群：{audience}"

        rows.append([
            scene or "—",
            "、".join(linked_terms) if linked_terms else "—",
            audience,
            f"建议：围绕{scene or '该'}场景组合 SB/SP 广告，融入高转化词。"
        ])
    if not rows:
        rows.append(["未定义", "—", "—", "缺少 STAG 数据"])
    return rows


def _rufus_seed_rows(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    review_insights = _safe_get(preprocessed_data, "review_data", "insights", default=[]) or []
    faq = generated_copy.get("faq", []) or []
    source_pairs = []
    for insight in review_insights[:3]:
        question = f"用户担忧：{insight.get('field_name', 'Pain Point')}"
        answer = insight.get("content_text", "")[:80] or "需要补充洞察。"
        source_pairs.append((question, answer))
    for item in faq[:3]:
        source_pairs.append((item.get("q", "FAQ"), item.get("a", "")[:80]))
    for idx, (question, answer) in enumerate(source_pairs[:5], 1):
        rows.append([str(idx), question, answer])
    if not rows:
        rows.append(["1", "暂无历史问答", "需补充全维度表数据。"])
    return rows


def _input_file_path(preprocessed_data: Any, key: str, fallback_label: str) -> str:
    run_config = getattr(preprocessed_data, "run_config", None)
    files = getattr(run_config, "input_files", {}) or {}
    return files.get(key) or fallback_label


def _collect_assignment_stats(assignments: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for tier in ("L1", "L2", "L3"):
        tier_entries = [
            entry for entry in assignments
            if (entry.get("tier") or "").upper() == tier
        ]
        stats[tier] = {
            "total": len(tier_entries),
            "title_hits": sum(
                any(str(field).startswith("title") for field in entry.get("assigned_fields") or [])
                for entry in tier_entries
            ),
            "visible_hits": sum(
                any(str(field).startswith("title") or str(field).startswith("bullet_")
                    for field in entry.get("assigned_fields") or [])
                for entry in tier_entries
            ),
            "search_hits": sum(
                "search_terms" in (entry.get("assigned_fields") or [])
                for entry in tier_entries
            ),
            "entries": tier_entries,
        }
    return stats


def _scene_distribution_notes(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> List[str]:
    scene_notes: List[str] = []
    scenes = writing_policy.get("scene_priority", []) or []
    language = writing_policy.get("language", "English")
    text_fields: Dict[str, str] = {
        "title": (generated_copy.get("title") or "").lower(),
        "search_terms": (" ".join(generated_copy.get("search_terms", []) or [])).lower()
    }
    for idx, bullet in enumerate(generated_copy.get("bullets", []) or [], 1):
        text_fields[f"bullet_b{idx}"] = bullet.lower()

    for scene_code in scenes[:5]:
        display = get_scene_display(scene_code, language) or scene_code.replace("_", " ")
        synonyms = {
            display.lower(),
            scene_code.replace("_", " ").lower()
        }
        coverage_fields = [
            field for field, text in text_fields.items()
            if any(term and term in text for term in synonyms)
        ]
        if len(coverage_fields) <= 1:
            field_str = coverage_fields[0] if coverage_fields else "任何字段"
            scene_notes.append(f"{display} 仅出现在 {field_str} → Scene 覆盖不足")
    return scene_notes


def _l2_overlap_notes(assignments: Sequence[Dict[str, Any]]) -> List[str]:
    notes: List[str] = []
    for entry in assignments:
        if (entry.get("tier") or "").upper() != "L2":
            continue
        fields = entry.get("assigned_fields") or []
        has_visible = any(str(field).startswith("title") or str(field).startswith("bullet_") for field in fields)
        if "search_terms" in fields and has_visible:
            keyword = entry.get("keyword") or "L2关键词"
            notes.append(f"{keyword} 同时位于可见字段与 Search Terms → 可替换为 L3 长尾词")
    return notes


def _keyword_distribution_section(
    writing_policy: Dict[str, Any],
    generated_copy: Dict[str, Any],
    decision_trace: Dict[str, Any]
) -> List[str]:
    assignments = decision_trace.get("keyword_assignments") or []
    scene_notes = _scene_distribution_notes(writing_policy, generated_copy)
    overlap_notes = _l2_overlap_notes(assignments)
    lines: List[str] = []
    if not scene_notes and not overlap_notes:
        lines.append("- 关键词分布均衡，无需额外调整。")
        return lines
    if scene_notes:
        lines.append("**Scene 覆盖提示**")
        lines.extend([f"- {note}" for note in scene_notes])
    if overlap_notes:
        lines.append("**L2 重复覆盖**")
        lines.extend([f"- {note}" for note in overlap_notes])
    return lines


def _build_a10_suggestions(
    stats: Dict[str, Dict[str, Any]],
    search_trace: Dict[str, Any],
    audit_trail: Sequence[Dict[str, Any]],
    preprocessed_data: Any,
    country: str
) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    locale_skip = sum(1 for entry in audit_trail if entry.get("action") == "locale_skip")
    real_vocab = getattr(preprocessed_data, "real_vocab", None)
    rv_count = getattr(real_vocab, "total_count", 0) if real_vocab else 0
    country_lower = country.lower() if country else ""
    keyword_path = _input_file_path(preprocessed_data, "keyword_table", "关键词表/ABA 表")

    if stats["L1"]["total"] == 0:
        if rv_count and rv_count < 50:
            suggestions.append({
                "type": "data",
                "reason": f"{country} 词库缺少本地 L1 关键词",
                "action": f"补充 data/raw/{country_lower}/{country}/ 词库（≥50条 L1），预计提升 A10 约 25 分"
            })
        elif locale_skip:
            suggestions.append({
                "type": "data",
                "reason": "现有 L1 关键词为非目标语言，被 locale gating 自动过滤",
                "action": f"在 {keyword_path} 中补充本地化 L1 词，或清理英文词后重跑"
            })
        else:
            suggestions.append({
                "type": "strategy",
                "reason": "L1 未落入 title slot",
                "action": "检查 writing_policy.title_slots，固定一个高流量 L1（可通过 keyword_slots.title 填入）"
            })
    elif stats["L1"]["title_hits"] == 0:
        suggestions.append({
            "type": "strategy",
            "reason": "L1 未前置到标题前 80 字符",
            "action": "在 writing_policy.title_slots 中把 L1 slot 标记为 required，或在 copy_generation 中锁定品牌+L1组合"
        })

    byte_used = search_trace.get("byte_length") or 0
    byte_cap = search_trace.get("max_bytes") or 249
    if byte_cap and byte_used < 0.6 * byte_cap:
        suggestions.append({
            "type": "data",
            "reason": f"Search Terms 仅 {byte_used}/{byte_cap} bytes，L3 长尾词偏少",
            "action": f"补充 data/raw/{country_lower}/{country}/ 长尾词或在 ABA 表中追加低搜索量关键词，词库补齐后 Search Terms 会自动填满"
        })

    if stats["L3"]["total"] == 0:
        suggestions.append({
            "type": "data",
            "reason": "缺少 L3 长尾词",
            "action": f"在 {keyword_path} 或 data/raw/{country_lower}/{country}/ 中新增 ≥20 条本地长尾词，供 Search Terms 使用"
        })
    elif stats["L3"]["search_hits"] == 0:
        suggestions.append({
            "type": "strategy",
            "reason": "已有 L3 词未落入 Search Terms",
            "action": "检查 writing_policy.search_term_plan 优先级，确保 L3 排在 L2 之前或直接通过 keyword_slots.search_terms 指定"
        })
    return suggestions


def _build_cosmo_suggestions(
    preprocessed_data: Any,
    bullet_trace: Sequence[Dict[str, Any]],
    capability_constraints: Dict[str, Any],
    writing_policy: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]]
) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    cap_meta = (intent_graph or {}).get("capability_metadata") or []
    visible_caps = {
        (entry.get("capability") or "").lower()
        for entry in bullet_trace
        if entry.get("capability")
    }
    attribute_path = _input_file_path(preprocessed_data, "attribute_table", "属性表")
    supplement_source = getattr(preprocessed_data, "supplement_signals", {}) or {}
    supplement_path = supplement_source.get("source_path") or "产品卖点和配件补充.txt"

    for entry in cap_meta:
        capability = (entry.get("capability") or "").strip()
        normalized = capability.lower()
        if not capability or not entry.get("is_supported"):
            continue
        if normalized in visible_caps:
            continue
        if "water" in normalized and not capability_constraints.get("waterproof_depth_m"):
            suggestions.append({
                "type": "data",
                "reason": f"{capability} 缺少防水深度/条件支撑",
                "action": f"在 {supplement_path} 或 {attribute_path} 中填写防水深度与 housing 条件，再在 B4 引入该能力"
            })
        elif any(term in normalized for term in ["battery", "runtime", "long battery"]) and not capability_constraints.get("runtime_minutes"):
            suggestions.append({
                "type": "data",
                "reason": f"{capability} 需要运行时长数据",
                "action": f"在 {attribute_path} 中补充 Battery Life（分钟），或在补充文本写明续航以供 B2 使用"
            })
        else:
            suggestions.append({
                "type": "strategy",
                "reason": f"{capability} 未落入可见字段",
                "action": "调整 writing_policy.capability_scene_bindings，将该能力绑定到 B2/B3/B4 的核心句"
            })

    scene_priority = writing_policy.get("scene_priority", []) or []
    covered_scenes = {
        entry.get("scene_code") for entry in bullet_trace if entry.get("scene_code")
    }
    for scene_code in scene_priority[:4]:
        if scene_code in covered_scenes:
            continue
        scene_label = get_scene_display(scene_code, writing_policy.get("language", "English")) or scene_code
        suggestions.append({
            "type": "strategy",
            "reason": f"{scene_label} 未在可见字段中体现",
            "action": "在 keyword_slots.scene 或 bullets 中补充对应场景关键词，避免单场景曝光"
        })

    return suggestions


def _build_rufus_suggestions(
    preprocessed_data: Any,
    capability_constraints: Dict[str, Any],
    bullet_trace: Sequence[Dict[str, Any]]
) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    attribute_path = _input_file_path(preprocessed_data, "attribute_table", "属性表")
    supplement_source = getattr(preprocessed_data, "supplement_signals", {}) or {}
    supplement_path = supplement_source.get("source_path") or "产品卖点和配件补充.txt"

    if not capability_constraints.get("runtime_minutes"):
        suggestions.append({
            "type": "data",
            "reason": "B2 缺少运行时长 → numeric expectation 未满足",
            "action": f"在 {attribute_path} 或 {supplement_path} 中填入 Battery Life（分钟），再重跑即可自动注入"
        })

    if capability_constraints.get("accessory_catalog_count", 0) == 0:
        suggestions.append({
            "type": "data",
            "reason": "配件清单缺失 → B1 只能使用通用挂载描述",
            "action": f"在 {supplement_path} 中逐条列出配件（例：防水壳、胸带、磁吸夹），强化 B1 转化信号"
        })

    unmet_numeric = [
        entry for entry in bullet_trace
        if entry.get("numeric_expectation") and not entry.get("numeric_met")
    ]
    for entry in unmet_numeric:
        slot = entry.get("slot", "B?")
        if slot == "B4" and not capability_constraints.get("waterproof_depth_m"):
            suggestions.append({
                "type": "data",
                "reason": "B4 需要防水深度作为边界声明",
                "action": f"在 {attribute_path} 或 {supplement_path} 中新增防水深度（如 30m with housing）"
            })
        elif slot == "B2" and capability_constraints.get("runtime_minutes"):
            suggestions.append({
                "type": "strategy",
                "reason": "B2 有 runtime 数据但未写入",
                "action": "检查 writing_policy.bullet_slot_rules.B2 的 required_elements，确保 copy_generation 引用 runtime_minutes"
            })

    return suggestions


def _optimization_section(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    scoring_results: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]]
) -> List[str]:
    decision_trace = generated_copy.get("decision_trace") or {}
    assignments = decision_trace.get("keyword_assignments") or []
    search_trace = decision_trace.get("search_terms_trace") or {}
    bullet_trace = decision_trace.get("bullet_trace") or []
    audit_trail = generated_copy.get("audit_trail") or []
    stats = _collect_assignment_stats(assignments)
    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    country = _safe_get(preprocessed_data, "run_config", "target_country", default="--")

    a10_score = scoring_results.get("a10", {}).get("subtotal", scoring_results.get("a10_score"))
    cosmo_score = scoring_results.get("cosmo", {}).get("subtotal", scoring_results.get("cosmo_score"))
    rufus_score = scoring_results.get("rufus", {}).get("subtotal", scoring_results.get("rufus_score"))

    sections = [
        ("A10", a10_score or 0, 100, _build_a10_suggestions(stats, search_trace, audit_trail, preprocessed_data, country)),
        ("COSMO", cosmo_score or 0, 100, _build_cosmo_suggestions(preprocessed_data, bullet_trace, capability_constraints, writing_policy, intent_graph)),
        ("Rufus", rufus_score or 0, 100, _build_rufus_suggestions(preprocessed_data, capability_constraints, bullet_trace)),
    ]

    lines: List[str] = []
    for name, score, max_score, items in sections:
        lines.append(f"**{name}（{score}/{max_score}）**")
        if not items:
            lines.append("- 当前无明显扣分项，可保持现状。")
            continue
        for item in items:
            label = "数据缺口" if item["type"] == "data" else "策略可调"
            lines.append(f"- {label}：{item['reason']} → {item['action']}")
    return lines


def _build_action_items(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    scoring_results: Dict[str, Any],
    decision_trace: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen = set()
    priority_map = {"A10": 1, "Rufus": 2, "COSMO": 3}

    def add_item(dimension: str, category: str, file_ref: str, action: str, impact: str):
        key = (dimension, category, action)
        if key in seen:
            return
        seen.add(key)
        items.append({
            "priority": priority_map.get(dimension, 4),
            "category": category,
            "file": file_ref,
            "action": action,
            "expected_impact": impact,
            "scoring_dimension": dimension
        })

    target_country = (_safe_get(preprocessed_data, "run_config", "target_country", default="--") or "--").upper()
    country_lower = target_country.lower()
    keyword_path = _input_file_path(preprocessed_data, "keyword_table", "关键词表/ABA 表")
    attribute_path = _input_file_path(preprocessed_data, "attribute_table", "本品属性表.txt")
    attr_parent = Path(attribute_path).parent if "/" in attribute_path else None
    supplement_path = str(attr_parent / "产品卖点和配件等信息补充.txt") if attr_parent else "产品卖点和配件补充.txt"

    alerts = getattr(preprocessed_data, "data_alerts", None) or []
    for alert in alerts:
        if "词库稀疏" in alert:
            add_item(
                "A10",
                "数据缺口",
                f"data/raw/{country_lower}/{target_country}/",
                "补充本地 L1/L3 关键词 ≥50 条，并清理非目标语言词",
                "A10 预计提升（填满 Title 与 Search Terms）"
            )

    assignments = decision_trace.get("keyword_assignments") or []
    stats = _collect_assignment_stats(assignments)
    search_trace = decision_trace.get("search_terms_trace") or {}
    audit_trail = generated_copy.get("audit_trail") or []
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}

    if stats["L1"]["total"] == 0:
        add_item(
            "A10",
            "数据缺口",
            keyword_path,
            "在竞品出单词或 ABA 表中新增本地 L1 词并设定 tier=L1",
            "A10 预计提升（L1→Title）"
        )
    elif stats["L1"]["title_hits"] == 0:
        add_item(
            "A10",
            "策略可调",
            "writing_policy.json",
            "调整 writing_policy.title_slots，锁定品牌后第 1 个词为本地 L1",
            "A10 稳定（Title 含核心词）"
        )

    byte_used = search_trace.get("byte_length") or 0
    byte_cap = search_trace.get("max_bytes") or 249
    if byte_cap and byte_used < 0.6 * byte_cap:
        add_item(
            "A10",
            "数据缺口",
            f"data/raw/{country_lower}/{target_country}/",
            "补充 ≥20 条 L3 长尾词并在 search_term_plan 中开启 backend-only 槽位",
            "A10 预计提升（Search Terms bytes 提升）"
        )

    if any(entry.get("action") == "locale_skip" for entry in audit_trail):
        add_item(
            "A10",
            "数据缺口",
            f"data/raw/{country_lower}/{target_country}/",
            "为 locale gating 提供对应语言词表，或在关键词表中翻译现有 L1/L2",
            "A10 预计提升（Locale 解锁）"
        )

    runtime_minutes = constraints.get("runtime_minutes")
    if not runtime_minutes:
        add_item(
            "Rufus",
            "数据缺口",
            attribute_path,
            "在属性表或补充文件中写入 Battery Life（分钟）字段，供 B2 注入",
            "Rufus 预计提升（numeric expectation 满足）"
        )

    accessory_count = constraints.get("accessory_catalog_count") or 0
    if accessory_count == 0 or any("accessory" in (entry.get("reason", "").lower()) for entry in audit_trail):
        add_item(
            "Rufus",
            "数据缺口",
            supplement_path,
            "在补充文件中列出 ≥5 条配件（含中文/本地语言），供 B1 & 描述引用",
            "Rufus 预计提升（转化信号增强）"
        )

    bullet_trace = decision_trace.get("bullet_trace") or []
    if any(entry.get("numeric_expectation") and not entry.get("numeric_met") for entry in bullet_trace):
        add_item(
            "Rufus",
            "策略可调",
            "writing_policy.json",
            "为数值槽位配置 fallback 数字源（如 attribute.runtime_minutes）并在 copy_generation 启用 numeric_patch",
            "Rufus 稳定（避免空槽）"
        )

    scene_notes = _scene_distribution_notes(writing_policy or {}, generated_copy or {})
    if scene_notes:
        add_item(
            "COSMO",
            "策略可调",
            "writing_policy.json",
            f"重排 scene_priority 或 bullet_slot_rules，使 {scene_notes[0].split(' ')[0]} 进入 ≥2 个字段",
            "COSMO 预计提升（Scene 覆盖）"
        )

    overlap_notes = _l2_overlap_notes(assignments)
    if overlap_notes:
        add_item(
            "COSMO",
            "策略可调",
            "writing_policy.json",
            "检查 keyword_assignments，将重复覆盖的 L2 替换为 L3 backend-only",
            "COSMO 预计提升（Slot 稀释度下降）"
        )

    return sorted(items, key=lambda item: (item["priority"], item["category"], item["action"]))


def generate_action_items(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    scoring_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    decision_trace = generated_copy.get("decision_trace") or {}
    return _build_action_items(
        preprocessed_data=preprocessed_data,
        generated_copy=generated_copy,
        writing_policy=writing_policy or {},
        scoring_results=scoring_results or {},
        decision_trace=decision_trace or {},
    )


def _scoring_tables(scoring_results: Dict[str, Any]) -> str:
    if not scoring_results:
        return "评分数据缺失，模块 8 无法生成。"

    sections: List[str] = []
    for block_key, title in (("a10", "A10 维度"), ("cosmo", "COSMO 维度"), ("rufus", "Rufus 维度")):
        block = scoring_results.get(block_key, {})
        rows = []
        for metric_key, metric in block.items():
            if metric_key == "subtotal":
                continue
            rows.append([
                metric_key,
                str(metric.get("max", "-")),
                str(metric.get("score", "-")),
                metric.get("note", "-")
            ])
        sections.append(f"### {title}\n" + _markdown_table(["指标", "满分", "得分", "说明"], rows))
        sections.append(f"> 小计：{block.get('subtotal', 0)} 分")

    price = scoring_results.get("price_competitiveness", {})
    price_rows = [[
        str(price.get("price_median", "—")),
        str(price.get("current_price", "—")),
        price.get("range", "—"),
        str(price.get("score")) if price.get("score") is not None else "—"
    ]]
    sections.append("### 价格竞争力\n" + _markdown_table(["品类中位价", "当前定价", "区间判断", "得分"], price_rows))
    sections.append(f"- 数据可用: {'是' if price.get('data_available') else '否'}\n- 说明: {price.get('note', '—')}")

    ai_os = scoring_results.get("ai_os_readiness", {}) or {}
    if ai_os:
        rows = []
        for metric_key, metric in ai_os.items():
            if metric_key in {"subtotal", "grade"}:
                continue
            rows.append([
                metric_key,
                str(metric.get("max", "-")),
                str(metric.get("score", "-")),
                metric.get("note", "-"),
            ])
        sections.append("### AI OS Readiness\n" + _markdown_table(["指标", "满分", "得分", "说明"], rows))
        sections.append(
            f"> 小计：{ai_os.get('subtotal', 0)} 分\n"
            f"- Readiness grade: {ai_os.get('grade', 'N/A')}"
        )

    boundary = scoring_results.get("boundary_declaration_check", {})
    aplus = scoring_results.get("aplus_word_count_check", {})
    sections.append(
        "### 规则附加检查\n"
        f"- 边界声明: {'已检测' if boundary.get('exists') else '缺失'} → {boundary.get('sentence', '未找到句子')}\n"
        f"- A+ 字数: {aplus.get('word_count', 0)} 词，满足下限: {aplus.get('meets_minimum', False)}"
    )

    sections.append(
        "### 算法对齐摘要\n"
        f"- 总分: {scoring_results.get('total_score', 0)}/{scoring_results.get('max_total', 330)}\n"
        f"- 原始分: {scoring_results.get('raw_total_score', scoring_results.get('total_score', 0))}\n"
        f"- 综合评级: {scoring_results.get('rating', 'N/A')} ({scoring_results.get('grade_percent', 0)}%)"
    )
    production = scoring_results.get("production_readiness", {}) or {}
    if production:
        sections.append(
            "### Production Readiness\n"
            f"- Generation status: {production.get('generation_status', 'unknown')}\n"
            f"- Returned model: {production.get('returned_model', 'unknown')}\n"
            f"- Authenticity score: {production.get('authenticity_score', 0)}/10\n"
            f"- Penalty applied: -{production.get('penalty', 0)}\n"
            f"- Advisory: {production.get('advisory', '—')}"
        )
    if scoring_results.get("rating_gate_reason"):
        sections.append(f"- Rating Gate: {scoring_results.get('rating_gate_reason')}")

    return "\n\n".join(sections)


def generate_report(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
    language: str,
    intent_graph: Optional[Dict[str, Any]] = None
) -> str:
    brand = _safe_get(preprocessed_data, "run_config", "brand_name", default="TOSBARRFT")
    site = _safe_get(preprocessed_data, "run_config", "target_country", default="-")
    processed_at = getattr(preprocessed_data, "processed_at", datetime.now(timezone.utc).isoformat())
    listing_lang = language or getattr(preprocessed_data, "language", "English")
    data_alerts = getattr(preprocessed_data, "data_alerts", None) or []
    decision_trace = generated_copy.get("decision_trace") or {}
    metadata = generated_copy.get("metadata", {}) or {}

    lines: List[str] = []
    lines.append("# Amazon Listing 最终仲裁报告")
    lines.append(f"- 生成时间：{processed_at}")
    lines.append(f"- 站点：{site}")
    lines.append(f"- 品牌：{brand}")
    lines.append(f"- Listing 语言：{listing_lang}")
    lines.append("")
    lines.extend(_listing_readiness_block(metadata, risk_report or {}))
    lines.append("")
    if data_alerts:
        lines.append("**⚠️ 数据依赖提醒**")
        for alert in data_alerts:
            lines.append(f"- {alert}")
        lines.append("")

    confidence_lines = _confidence_summary_block(
        preprocessed_data=preprocessed_data,
        scoring_results=scoring_results or {},
        decision_trace=decision_trace or {},
        generated_copy=generated_copy,
    )
    lines.extend(confidence_lines)
    lines.append("")
    lines.extend(_hybrid_launch_report_block(generated_copy, scoring_results))
    lines.extend(_operations_payload_block(generated_copy))
    lines.extend(_operations_strategy_summary(generated_copy, writing_policy, scoring_results))
    lines.append("")
    lines.append("### 关键词覆盖审计表")
    lines.append(_markdown_table(["关键词", "层级", "出现位置"], _keyword_coverage_rows(preprocessed_data, generated_copy)))
    lines.append("")
    lines.extend(_keyword_arsenal_block(preprocessed_data, generated_copy))
    lines.append("")
    lines.extend(_operator_summary_block(generated_copy, writing_policy))
    lines.append("")
    lines.extend(_system_process_block(preprocessed_data, generated_copy, writing_policy, scoring_results))
    lines.append("")
    lines.extend(_evidence_alignment_block(generated_copy))
    lines.append("")
    lines.extend(_market_pack_block(writing_policy))
    lines.append("")
    lines.extend(_bundle_variant_block(preprocessed_data))
    lines.append("")
    lines.extend(_after_sales_sop_block(writing_policy))
    lines.append("")
    lines.extend(_prelaunch_checklist_block(preprocessed_data, generated_copy, writing_policy, risk_report, scoring_results))
    lines.append("")
    lines.extend(_thirty_day_iteration_block(preprocessed_data, generated_copy, writing_policy, risk_report, scoring_results))
    lines.append("")
    lines.extend(_compute_tier_block(generated_copy))
    lines.append("")
    lines.extend(
        _diagnosis_and_optimization_block(
            preprocessed_data=preprocessed_data,
            generated_copy=generated_copy,
            writing_policy=writing_policy,
            risk_report=risk_report,
            scoring_results=scoring_results,
            intent_graph=intent_graph,
        )
    )
    lines.append("")

    return "\n".join(lines)


def generate_dual_version_report(
    *,
    sku: str,
    market: str,
    run_id: str,
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
    hybrid: Optional[Dict[str, Any]] = None,
) -> str:
    def _failure_reason(version: Dict[str, Any]) -> str:
        return (
            str(version.get("failure_reason") or "").strip()
            or str(((version.get("execution_summary") or {}).get("results") or {}).get("step_5", {}).get("error") or "").strip()
            or str(((version.get("execution_summary") or {}).get("results") or {}).get("step_6", {}).get("error") or "").strip()
        )

    def _listing_block(version: Dict[str, Any]) -> list[str]:
        generated_copy = version.get("generated_copy") or {}
        generation_status = str(version.get("generation_status") or "").strip()
        if generation_status.startswith("FAILED_AT_") or generation_status == "FAILED":
            return [
                "### Listing",
                f"- Generation Status: {generation_status}",
                f"- Failure Reason: {_failure_reason(version) or 'unknown'}",
                "- Visible Copy: not generated",
                "",
            ]
        bullets = generated_copy.get("bullets") or []
        search_terms = generated_copy.get("search_terms") or []
        return [
            "### Listing",
            f"- Generation Status: {generation_status or ((generated_copy.get('metadata') or {}).get('generation_status') or '')}",
            f"- Title: {generated_copy.get('title') or ''}",
            "- Bullets:",
            *[f"  - B{idx}: {bullet}" for idx, bullet in enumerate(bullets, start=1)],
            f"- Description: {generated_copy.get('description') or ''}",
            f"- Search Terms: {', '.join(search_terms) if isinstance(search_terms, list) else str(search_terms or '')}",
            "",
        ]

    def _scoring_block(scoring_results: Dict[str, Any]) -> list[str]:
        dims = scoring_results.get("dimensions") or {}
        return [
            "### Scoring",
            f"- A10: {(dims.get('traffic') or {}).get('score', 0)}/100",
            f"- COSMO: {(dims.get('content') or {}).get('score', 0)}/100",
            f"- Rufus: {(dims.get('conversion') or {}).get('score', 0)}/100",
            f"- Fluency: {(dims.get('readability') or {}).get('score', 0)}/30",
            f"- listing_status: {scoring_results.get('listing_status') or 'UNKNOWN'}",
            "",
        ]

    def _summary_row(version: Dict[str, Any], dimension: str) -> str:
        return str(((version.get("scoring_results") or {}).get("dimensions") or {}).get(dimension, {}).get("score", ""))

    lines = [
        f"# Listing All Report Compare — {sku} {market} {run_id}",
        "",
        "## Version A：V3 全链路（主链路基线）",
        "",
        *_listing_block(version_a),
        *_scoring_block(version_a.get("scoring_results") or {}),
        "---",
        "",
        "## Version B：R1 Title + Bullets + V3 Remaining Fields（实验版）",
        "",
        *_listing_block(version_b),
        *_scoring_block(version_b.get("scoring_results") or {}),
        "---",
        "",
        "## 对比摘要",
        "",
        "| 维度 | Version A（V3） | Version B（R1 Title + Bullets） |",
        "|---|---|---|",
        f"| A10 | {_summary_row(version_a, 'traffic')} | {_summary_row(version_b, 'traffic')} |",
        f"| COSMO | {_summary_row(version_a, 'content')} | {_summary_row(version_b, 'content')} |",
        f"| Rufus | {_summary_row(version_a, 'conversion')} | {_summary_row(version_b, 'conversion')} |",
        f"| Fluency | {_summary_row(version_a, 'readability')} | {_summary_row(version_b, 'readability')} |",
        f"| generation_status | {version_a.get('generation_status', '')} | {version_b.get('generation_status', '')} |",
        f"| listing_status | {(version_a.get('scoring_results') or {}).get('listing_status', '')} | {(version_b.get('scoring_results') or {}).get('listing_status', '')} |",
        f"| Blueprint 来源 | {version_a.get('blueprint_model', 'deepseek-chat')} | {version_b.get('blueprint_model', 'deepseek-reasoner')} |",
        f"| 可见文案来源 | {version_a.get('visible_copy_model', 'deepseek-chat')} | {version_b.get('visible_copy_model', 'deepseek-reasoner (title+bullets)')} |",
        f"| 总耗时（秒） | {version_a.get('elapsed_seconds', 0)} | {version_b.get('elapsed_seconds', 0)} |",
        "",
    ]
    if hybrid:
        final_verdict = hybrid.get("final_readiness_verdict") or {}
        launch_gate = final_verdict.get("launch_gate") or {}
        scores = launch_gate.get("scores") or {}
        thresholds = launch_gate.get("thresholds") or {}
        lines.extend(
            [
                "## Hybrid Recommendation",
                "",
                *_listing_block(hybrid),
                *_scoring_block(hybrid.get("scoring_results") or {}),
                f"- Source Split: {((hybrid.get('generated_copy') or {}).get('metadata') or {}).get('hybrid_sources') or {}}",
                "",
                "## Hybrid Launch Decision",
                "",
                f"- Recommended Output: `{final_verdict.get('recommended_output') or (((hybrid.get('generated_copy') or {}).get('metadata') or {}).get('launch_decision', {}) or {}).get('recommended_output', 'unknown')}`",
                f"- Hybrid Gate: {'passed' if launch_gate.get('passed') else 'failed'}",
                f"- Blocking Reasons: {', '.join(final_verdict.get('reasons') or []) or 'none'}",
                "- Scores: "
                f"A10 {scores.get('A10', '')} / COSMO {scores.get('COSMO', '')} / "
                f"Rufus {scores.get('Rufus', '')} / Fluency {scores.get('Fluency', '')}",
                "- Thresholds: "
                f"A10 {thresholds.get('A10', '')} / COSMO {thresholds.get('COSMO', '')} / "
                f"Rufus {thresholds.get('Rufus', '')} / Fluency {thresholds.get('Fluency', '')}",
                f"- Launch Copy Source: `{((final_verdict.get('artifact_paths') or {}).get('recommended_generated_copy') or '')}`",
                "",
            ]
        )
    return "\n".join(lines)


__all__ = ["generate_report", "generate_action_items", "generate_dual_version_report"]
