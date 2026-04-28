#!/usr/bin/env python3
"""
Node 3 - 关键词军火库基础实现
"""

from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Tuple

from modules.keyword_protocol import build_keyword_protocol
from modules.keyword_utils import GLOBAL_BRAND_BLOCKLIST, infer_category_type, is_blocklisted_brand


def _build_keyword_entry(
    keyword: str,
    tier: str,
    search_volume: float,
    conversion_rate: float,
    source_type: str,
    source_file: str = "",
) -> Dict[str, Any]:
    """统一的关键词结构，方便写作策略消费元数据。"""
    return {
        "keyword": keyword,
        "level": tier,
        "tier": tier,
        "search_volume": search_volume,
        "conversion_rate": conversion_rate,
        "high_conv": conversion_rate >= 1.5,
        "source_type": source_type or "unknown",
        "source_file": source_file,
        "visibility": "visible",
        "downgrade_reason": "",
    }


def _tier_keyword(row: Dict[str, Any], l1_threshold: float, l2_threshold: float) -> Tuple[str, float]:
    volume = row.get("search_volume") or row.get("月搜索量") or 0
    try:
        volume = float(volume)
    except (TypeError, ValueError):
        volume = 0

    if volume >= l1_threshold:
        level = "L1"
    elif volume >= l2_threshold:
        level = "L2"
    else:
        level = "L3"
    return level, volume


def _is_high_conv(row: Dict[str, Any]) -> bool:
    rate = row.get("conversion_rate") or row.get("购买率") or 0
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = 0
    return rate >= 1.5


def _build_from_real_vocab(real_vocab: Any) -> Tuple[List[Dict[str, Any]], str]:
    """
    从真实国家词表构建 reserve_keywords（Priority 1）。

    Returns:
        (reserve_keywords_list, source_note)
    """
    if not real_vocab or not getattr(real_vocab, "is_available", False):
        return [], "synthetic"

    top_kw = getattr(real_vocab, "top_keywords", []) or []

    # 计算 tier 阈值
    volumes = []
    for row in top_kw:
        vol = row.get("search_volume") or 0
        try:
            vol = float(vol)
        except (TypeError, ValueError):
            vol = 0
        if vol > 0:
            volumes.append(vol)

    volumes.sort(reverse=True)
    n = len(volumes)
    l1_threshold = volumes[int(0.2 * n)] if n > 0 and int(0.2 * n) < n else 0
    l2_threshold = volumes[int(0.6 * n)] if n > 0 and int(0.6 * n) < n else 0

    reserve = []
    for row in top_kw:
        kw = row.get("keyword", "")
        if not kw:
            continue
        vol = float(row.get("search_volume") or 0)
        rate = float(row.get("conversion_rate") or 0)
        level, _ = _tier_keyword({"search_volume": vol}, l1_threshold, l2_threshold)
        reserve.append(
            _build_keyword_entry(
                keyword=kw,
                tier=level,
                search_volume=vol,
                conversion_rate=rate,
                source_type=row.get("source_type", "real_vocab"),
                source_file=row.get("source_file", ""),
            )
        )

    reserve.sort(key=lambda x: x["search_volume"], reverse=True)
    return reserve, "real_vocab"


def _decorate_protocol_entry(row: Dict[str, Any]) -> Dict[str, Any]:
    """Keep legacy keyword arsenal fields while preserving protocol metadata."""
    entry = dict(row)
    tier = entry.get("traffic_tier") or entry.get("tier") or ""
    entry["traffic_tier"] = tier
    entry["tier"] = tier
    entry["level"] = tier
    entry["high_conv"] = bool(
        _is_high_conv(entry)
        or float(entry.get("conversion_score") or 0) >= 0.75
        or float(entry.get("blue_ocean_score") or 0) >= 0.7
    )
    entry.setdefault("visibility", "visible")
    entry.setdefault("downgrade_reason", "")
    return entry


def _traffic_tier_priority(row: Dict[str, Any]) -> int:
    return {"L1": 0, "L2": 1, "L3": 2}.get(str(row.get("traffic_tier") or row.get("tier") or "").upper(), 3)


def _source_rows_and_note(preprocessed_data: Any) -> Tuple[List[Dict[str, Any]], str]:
    real_vocab = getattr(preprocessed_data, "real_vocab", None)
    if real_vocab and getattr(real_vocab, "is_available", False) and getattr(real_vocab, "top_keywords", None):
        return [dict(row) for row in (getattr(real_vocab, "top_keywords", []) or [])], "real_vocab"
    keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    return [dict(row) for row in keyword_rows], "keyword_table"


def build_arsenal(preprocessed_data: Any) -> Dict[str, Any]:
    # ─── Priority 1: 真实国家词表 ───
    real_vocab = getattr(preprocessed_data, "real_vocab", None)
    keyword_rows, kw_source = _source_rows_and_note(preprocessed_data)
    target_country = getattr(
        getattr(preprocessed_data, "run_config", None),
        "target_country",
        getattr(preprocessed_data, "target_country", "US"),
    )
    protocol = build_keyword_protocol(
        keyword_rows,
        country=str(target_country or "US").upper(),
        category_type=infer_category_type(preprocessed_data),
    )
    qualified_keywords = [_decorate_protocol_entry(row) for row in protocol.get("qualified_keywords", [])]
    watchlist_keywords = [_decorate_protocol_entry(row) for row in protocol.get("watchlist_keywords", [])]
    natural_only_keywords = [_decorate_protocol_entry(row) for row in protocol.get("natural_only_keywords", [])]
    rejected_keywords = [_decorate_protocol_entry(row) for row in protocol.get("rejected_keywords", [])]
    blocked_keywords = [_decorate_protocol_entry(row) for row in protocol.get("blocked_keywords", [])]

    reserve_keywords = sorted(
        qualified_keywords,
        key=lambda item: (
            _traffic_tier_priority(item),
            -float(item.get("opportunity_score") or 0),
            -float(item.get("search_volume") or 0),
        ),
    )[:50]

    # 如果有真实词表，将其关键词同步到 keyword_data.keywords（供 scoring._tier_keywords 使用）
    if reserve_keywords and getattr(real_vocab, "is_available", False):
        # 重建 keyword_data.keywords 以便 scoring 模块能够正确分层
        kw_list_for_scoring = []
        for kw_dict in reserve_keywords:
            kw_list_for_scoring.append({
                "keyword": kw_dict.get("keyword", ""),
                "search_term": kw_dict.get("keyword", ""),
                "search_volume": kw_dict.get("search_volume", 0),
                "conversion_rate": kw_dict.get("conversion_rate", 0),
            })
        # 同步到 preprocessed_data.keyword_data.keywords
        keyword_data_obj = getattr(preprocessed_data, "keyword_data", None)
        if keyword_data_obj is not None:
            try:
                keyword_data_obj.keywords = kw_list_for_scoring
            except AttributeError:
                # 如果 keyword_data 是 dict 类型，尝试直接赋值
                if isinstance(keyword_data_obj, dict):
                    keyword_data_obj["keywords"] = kw_list_for_scoring

    prices = []  # Always initialize prices before conditional block

    for row in keyword_rows:
        if row.get("avg_price"):
            try:
                prices.append(float(row["avg_price"]))
            except (TypeError, ValueError):
                pass

    review_insights = getattr(getattr(preprocessed_data, "review_data", None), "insights", []) or []
    feedback_context = getattr(preprocessed_data, "feedback_context", {}) or {}

    if prices:
        price_median = median(prices)
    else:
        price_median = None

    review_pain_points = [
        insight.get("content_text")
        for insight in review_insights
        if insight.get("field_name", "").lower() in {"negative_pain", "差评词", "pain_point"}
    ][:5]

    rufus_questions = [
        {
            "question": insight.get("content_text")[:80],
            "source": insight.get("field_name")
        }
        for insight in review_insights
        if insight.get("field_name", "").lower() in {"rufus_faq", "high_freq_question"}
    ][:5]

    traffic_priority_keywords = [
        entry for entry in qualified_keywords
        if entry.get("routing_role") == "title" and not is_blocklisted_brand(entry.get("keyword", ""))
    ]
    traffic_priority_keywords = sorted(
        traffic_priority_keywords,
        key=lambda item: (
            -float(item.get("opportunity_score") or 0),
            -float(item.get("search_volume") or 0),
        ),
    )[:12]
    conversion_priority_keywords = sorted(
        [
            entry for entry in qualified_keywords
            if entry.get("routing_role") == "bullet" and not is_blocklisted_brand(entry.get("keyword", ""))
        ],
        key=lambda item: (
            -float(item.get("blue_ocean_score") or 0),
            -float(item.get("conversion_score") or 0),
            -float(item.get("opportunity_score") or 0),
        ),
    )[:12]
    backend_only_terms = sorted(
        {
            entry.get("keyword", "")
            for entry in reserve_keywords
            if is_blocklisted_brand(entry.get("keyword", ""))
        }
    )
    backend_only_terms = sorted(
        set(
            backend_only_terms
            + [
                str((row or {}).get("keyword") or "").strip()
                for row in feedback_context.get("backend_only", []) or []
                if str((row or {}).get("keyword") or "").strip()
            ]
        )
    )
    taboo_terms = sorted(GLOBAL_BRAND_BLOCKLIST)[:30]
    keyword_metadata = [
        _decorate_protocol_entry(row)
        for row in (protocol.get("keyword_metadata", []) or [])
    ]
    if hasattr(preprocessed_data, "keyword_metadata"):
        preprocessed_data.keyword_metadata = keyword_metadata
    else:
        setattr(preprocessed_data, "keyword_metadata", keyword_metadata)

    arsenal = {
        "site": getattr(preprocessed_data.run_config, "target_country", "US"),
        "language": preprocessed_data.language,
        "circuit_breaker_applied": True,
        "parameter_constraints": [
            {"constraint": "5K 模式不支持防抖", "action": "faq_only"},
            {"constraint": "30 米防水需使用防水壳", "action": "boundary_declaration"}
        ],
        "reserve_keywords": reserve_keywords[:50],
        "traffic_priority_keywords": traffic_priority_keywords,
        "conversion_priority_keywords": conversion_priority_keywords,
        "qualified_keywords": qualified_keywords[:50],
        "watchlist_keywords": watchlist_keywords[:50],
        "natural_only_keywords": natural_only_keywords[:50],
        "rejected_keywords": rejected_keywords[:50],
        "blocked_keywords": blocked_keywords[:50],
        "keyword_protocol_summary": {
            "qualified_count": len(protocol.get("qualified_keywords", [])),
            "watchlist_count": len(protocol.get("watchlist_keywords", [])),
            "natural_only_count": len(protocol.get("natural_only_keywords", [])),
            "rejected_count": len(protocol.get("rejected_keywords", [])),
            "blocked_count": len(protocol.get("blocked_keywords", [])),
        },
        "backend_only_terms": backend_only_terms,
        "taboo_terms": taboo_terms,
        "competitor_brands": ["GoPro", "Insta360", "DJI"],
        "price_context": {
            "price_median": price_median,
            "currency": "EUR" if getattr(preprocessed_data.run_config, "target_country", "US") in ("DE", "FR") else "USD",
            "sample_size": len(prices)
        },
        "review_pain_points": review_pain_points,
        "rufus_high_freq_questions": rufus_questions,
        # 关键词来源追踪（用于判断是否使用真实本地词）
        "_keyword_source": kw_source,
        "_real_vocab_available": getattr(real_vocab, "is_available", False) if real_vocab else False,
        "keyword_metadata": keyword_metadata[:50],
    }

    return arsenal


__all__ = ["build_arsenal"]
