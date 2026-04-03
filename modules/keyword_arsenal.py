#!/usr/bin/env python3
"""
Node 3 - 关键词军火库基础实现
"""

from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Tuple


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


def build_arsenal(preprocessed_data: Any) -> Dict[str, Any]:
    keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    review_insights = getattr(getattr(preprocessed_data, "review_data", None), "insights", []) or []

    reserve_keywords = []
    prices = []
    for row in keyword_rows:
        keyword = row.get("keyword") or row.get("search_term")
        if not keyword:
            continue
        level, volume = _tier_keyword(row)
        conversion_rate = row.get("conversion_rate") or 0
        try:
            conversion_rate = float(conversion_rate)
        except (TypeError, ValueError):
            conversion_rate = 0
        if row.get("avg_price"):
            try:
                prices.append(float(row["avg_price"]))
            except (TypeError, ValueError):
                pass
        reserve_keywords.append({
            "keyword": keyword,
            "level": level,
            "search_volume": volume,
            "conversion_rate": conversion_rate,
            "high_conv": _is_high_conv(row)
        })

    reserve_keywords = sorted(reserve_keywords, key=lambda x: x["search_volume"], reverse=True)

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

    arsenal = {
        "site": getattr(preprocessed_data.run_config, "target_country", "US"),
        "language": preprocessed_data.language,
        "circuit_breaker_applied": True,
        "parameter_constraints": [
            {"constraint": "5K 模式不支持防抖", "action": "faq_only"},
            {"constraint": "30 米防水需使用防水壳", "action": "boundary_declaration"}
        ],
        "reserve_keywords": reserve_keywords[:50],
        "competitor_brands": ["GoPro", "Insta360", "DJI"],
        "price_context": {
            "price_median": price_median,
            "currency": "EUR" if getattr(preprocessed_data.run_config, "target_country", "US") == "DE" else "USD",
            "sample_size": len(prices)
        },
        "review_pain_points": review_pain_points,
        "rufus_high_freq_questions": rufus_questions
    }

    return arsenal


__all__ = ["build_arsenal"]
