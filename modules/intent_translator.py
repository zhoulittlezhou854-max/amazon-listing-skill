#!/usr/bin/env python3
"""
Node 4 - COSMO 意图图谱基础实现
"""

from __future__ import annotations

from typing import Any, Dict, List


def _select_high_conv_keywords(arsenal: Dict[str, Any], preprocessed_data: Any) -> List[str]:
    if arsenal and arsenal.get("reserve_keywords"):
        return [kw["keyword"] for kw in arsenal["reserve_keywords"] if kw.get("high_conv")] or \
               [kw["keyword"] for kw in arsenal["reserve_keywords"][:5]]
    keywords = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    sorted_keywords = sorted(keywords, key=lambda x: x.get("search_volume", 0), reverse=True)
    return [row.get("keyword") for row in sorted_keywords[:5] if row.get("keyword")]


def generate_intent_graph(arsenal_output: Dict[str, Any], preprocessed_data: Any) -> Dict[str, Any]:
    high_conv_keywords = _select_high_conv_keywords(arsenal_output, preprocessed_data)
    if not high_conv_keywords:
        high_conv_keywords = ["action camera", "sports camera"]

    personas = ["骑行者", "旅行博主", "潜水玩家", "通勤族"]
    purchase_stages = ["Awareness", "Consideration", "Decision"]

    intent_graph = []
    for idx, keyword in enumerate(high_conv_keywords):
        intent_graph.append({
            "keyword": keyword,
            "user_identity": personas[idx % len(personas)],
            "purchase_intent": purchase_stages[idx % len(purchase_stages)],
            "pain_point": "需要稳定画面与可靠防水",
            "stag_groups": [
                {"group_name": "骑行记录", "keywords": [keyword], "persona": "骑行者"},
                {"group_name": "户外冒险", "keywords": high_conv_keywords[:3], "persona": "户外玩家"}
            ]
        })

    stag_groups = [
        {
            "group_name": "户外运动",
            "keywords": high_conv_keywords[:3],
            "persona": "Outdoor Explorer",
            "advice": "投放SP + SB，突出4K与EIS"
        },
        {
            "group_name": "水下探索",
            "keywords": high_conv_keywords[3:5] or high_conv_keywords[:2],
            "persona": "Diving Hobbyist",
            "advice": "展示防水深度与配件"
        }
    ]

    return {
        "intent_graph": intent_graph,
        "stag_groups": stag_groups
    }


__all__ = ["generate_intent_graph"]
