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
        reserve.append({
            "keyword": kw,
            "level": level,
            "search_volume": vol,
            "conversion_rate": rate,
            "high_conv": rate >= 1.5,
            "_source_type": row.get("source_type", "unknown"),
            "_source_file": row.get("source_file", ""),
        })

    reserve.sort(key=lambda x: x["search_volume"], reverse=True)
    return reserve, "real_vocab"


def build_arsenal(preprocessed_data: Any) -> Dict[str, Any]:
    # ─── Priority 1: 真实国家词表 ───
    real_vocab = getattr(preprocessed_data, "real_vocab", None)
    reserve_keywords, kw_source = _build_from_real_vocab(real_vocab)

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

    if not reserve_keywords:
        # ─── Priority 2: 预处理数据中的关键词表 ───
        keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []

        # 计算百分位阈值
        volumes = []
        for row in keyword_rows:
            volume = row.get("search_volume") or row.get("月搜索量") or 0
            try:
                volume = float(volume)
            except (TypeError, ValueError):
                volume = 0
            if volume > 0:
                volumes.append(volume)

        # 按搜索量降序排序
        volumes.sort(reverse=True)

        # 计算阈值：L1 = 前20%，L2 = 20-60%，L3 = 60%以下
        l1_threshold = 0
        l2_threshold = 0
        if volumes:
            n = len(volumes)
            l1_idx = int(0.2 * n)
            l2_idx = int(0.6 * n)
            l1_idx = min(l1_idx, n-1) if n > 0 else 0
            l2_idx = min(l2_idx, n-1) if n > 0 else 0
            l1_threshold = volumes[l1_idx] if l1_idx < n else volumes[-1]
            l2_threshold = volumes[l2_idx] if l2_idx < n else volumes[-1]
        else:
            l1_threshold = 10000
            l2_threshold = 1000

        reserve_keywords = []
        prices = []
        for row in keyword_rows:
            keyword = row.get("keyword") or row.get("search_term")
            if not keyword:
                continue
            level, volume = _tier_keyword(row, l1_threshold, l2_threshold)
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
        kw_source = "keyword_table"

    review_insights = getattr(getattr(preprocessed_data, "review_data", None), "insights", []) or []
    prices = []  # Initialize to avoid UnboundLocalError when Priority 1 succeeds

    if not reserve_keywords and prices is not None:
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
            "currency": "EUR" if getattr(preprocessed_data.run_config, "target_country", "US") in ("DE", "FR") else "USD",
            "sample_size": len(prices)
        },
        "review_pain_points": review_pain_points,
        "rufus_high_freq_questions": rufus_questions,
        # 关键词来源追踪（用于判断是否使用真实本地词）
        "_keyword_source": kw_source,
        "_real_vocab_available": getattr(real_vocab, "is_available", False) if real_vocab else False,
    }

    return arsenal


__all__ = ["build_arsenal"]
