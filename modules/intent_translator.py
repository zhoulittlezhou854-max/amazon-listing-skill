#!/usr/bin/env python3
"""
Node 3.5 - 意图转译引擎 (PRD v8.2)
强制使用 ENGLISH 输出 Intent Graph / STAG 结构

输入: reserve_keywords, 数据诊断信息
输出: 纯英文 Intent Graph / STAG，供后续 Node 0 / Node 4 使用
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# 场景标签映射 (多语言 -> 英文标准化)
SCENE_LABEL_MAP = {
    # 中文场景
    "骑行记录": "cycling_recording",
    "水下探索": "underwater_exploration",
    "旅行记录": "travel_documentation",
    "家庭使用": "family_use",
    "户外运动": "outdoor_sports",
    "滑雪运动": "skiing",
    "登山徒步": "hiking_trekking",
    "自驾游": "road_trip",
    "宠物拍摄": "pet_photography",
    "vlog制作": "vlog_content_creation",
    "运动训练": "sports_training",
    "赛事记录": "sports_event_recording",
    "野外探险": "wilderness_exploration",
    "极限运动": "extreme_sports",
    "日常记录": "daily_lifelogging",
    # 英文场景 (保持原样)
    "cycling_recording": "cycling_recording",
    "underwater_exploration": "underwater_exploration",
    "travel_documentation": "travel_documentation",
    "family_use": "family_use",
    "outdoor_sports": "outdoor_sports",
}


def _normalize_scene_label(scene: str) -> str:
    """将任意语言场景名归一化为英文标签"""
    return SCENE_LABEL_MAP.get(scene, scene.lower().replace(" ", "_"))


def _select_keywords_for_intent(arsenal: Optional[Dict[str, Any]], preprocessed_data: Any) -> List[Dict[str, Any]]:
    """从军火库或预处理数据中提取关键词"""
    if arsenal and arsenal.get("reserve_keywords"):
        return arsenal["reserve_keywords"][:20]  # 取前20个

    keywords = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    return sorted(keywords, key=lambda x: x.get("search_volume", 0), reverse=True)[:20]


def _infer_capabilities_from_keywords(keywords: List[Dict[str, Any]]) -> List[str]:
    """从关键词推断能力标签"""
    capability_keywords = {
        "waterproof": "waterproof",
        "4k": "4K_video",
        "stabilization": "stabilization",
        "wifi": "wifi_connectivity",
        "battery": "long_battery_life",
        "screen": "dual_screen",
        "mount": "versatile_mounting",
        "hd": "hd_video",
        "sport": "sports_compatible",
    }
    found = set()
    for kw in keywords:
        text = kw.get("keyword", "").lower()
        for pattern, cap in capability_keywords.items():
            if pattern in text:
                found.add(cap)
    return list(found) if found else ["general_recording"]


def _build_stag_groups(keywords: List[Dict[str, Any]], data_mode: str) -> List[Dict[str, Any]]:
    """
    根据关键词构建 STAG (Single Theme Ad Group) 结构
    PRD v8.2: 每个 STAG 代表一个单主题广告组场景
    """
    stag_groups = []

    # 按搜索量排序取前10个关键词
    sorted_kw = sorted(keywords, key=lambda x: x.get("search_volume", 0), reverse=True)[:10]

    # 定义场景分组策略 (英文标签)
    scene_templates = [
        {
            "id": "stag_1",
            "english_label": "action_camera_capture",
            "primary_scenarios": ["outdoor_sports", "cycling_recording"],
            "keywords": [],
            "capabilities": ["4K_video", "stabilization"],
            "target_persona": "Outdoor Enthusiast",
            "campaign_advice": "Use SP + SB, emphasize 4K and EIS"
        },
        {
            "id": "stag_2",
            "english_label": "underwater_recording",
            "primary_scenarios": ["underwater_exploration"],
            "keywords": [],
            "capabilities": ["waterproof"],
            "target_persona": "Diving Hobbyist",
            "campaign_advice": "Show waterproof depth and accessories"
        },
        {
            "id": "stag_3",
            "english_label": "travel_documentation",
            "primary_scenarios": ["travel_documentation", "road_trip"],
            "keywords": [],
            "capabilities": ["wifi_connectivity", "long_battery_life"],
            "target_persona": "Travel Blogger",
            "campaign_advice": "Highlight portability and sharing features"
        },
        {
            "id": "stag_4",
            "english_label": "daily_lifelogging",
            "primary_scenarios": ["family_use", "daily_lifelogging"],
            "keywords": [],
            "capabilities": ["dual_screen", "versatile_mounting"],
            "target_persona": "Family User",
            "campaign_advice": "Emphasize ease of use and family-friendly features"
        },
        {
            "id": "stag_5",
            "english_label": "content_creation",
            "primary_scenarios": ["vlog_content_creation"],
            "keywords": [],
            "capabilities": ["4K_video", "wifi_connectivity"],
            "target_persona": "Content Creator",
            "campaign_advice": "Promote video quality and app connectivity"
        },
    ]

    # 分配关键词到 STAG
    for i, kw in enumerate(sorted_kw):
        kw_text = kw.get("keyword", "")
        kw_lower = kw_text.lower()

        # 根据关键词内容分配 STAG
        if any(w in kw_lower for w in ["water", "diving", "underwater", "swim", "surf"]):
            target_stag = stag_groups[1] if len(stag_groups) > 1 else stag_groups[0]
        elif any(w in kw_lower for w in ["travel", "trip", "road", "vacation"]):
            target_stag = stag_groups[2] if len(stag_groups) > 2 else stag_groups[0]
        elif any(w in kw_lower for w in ["family", "daily", "home", "kid", "pet"]):
            target_stag = stag_groups[3] if len(stag_groups) > 3 else stag_groups[0]
        elif any(w in kw_lower for w in ["vlog", "content", "youtube", "creator"]):
            target_stag = stag_groups[4] if len(stag_groups) > 4 else stag_groups[0]
        else:
            target_stag = stag_groups[0]

        target_stag["keywords"].append(kw_text)

    # 如果是 SYNTHETIC_COLD_START，标记合成关键词
    if data_mode == "SYNTHETIC_COLD_START":
        for stag in scene_templates:
            if not stag["keywords"]:
                stag["keywords"] = ["[SYNTH]_" + stag["english_label"]]

    # 只返回有数据的 STAG
    return [s for s in scene_templates if s["keywords"]][:5]


def _build_intent_graph(keywords: List[Dict[str, Any]], preprocessed_data: Any, data_mode: str) -> List[Dict[str, Any]]:
    """
    构建英文 Intent Graph
    PRD v8.2: 输出结构包含 id, english_label, source_keywords, usage_scenarios, capabilities
    """
    intents = []
    sorted_kw = sorted(keywords, key=lambda x: x.get("search_volume", 0), reverse=True)[:10]
    capabilities = _infer_capabilities_from_keywords(keywords)

    purchase_stages = ["Awareness", "Consideration", "Decision"]
    personas = ["Outdoor Enthusiast", "Travel Blogger", "Diving Hobbyist", "Family User", "Content Creator"]

    for idx, kw in enumerate(sorted_kw):
        kw_text = kw.get("keyword", "")
        volume = kw.get("search_volume", 0)

        # 推断场景
        kw_lower = kw_text.lower()
        if "water" in kw_lower or "diving" in kw_lower or "underwater" in kw_lower:
            scenes = ["underwater_exploration"]
        elif "travel" in kw_lower or "trip" in kw_lower:
            scenes = ["travel_documentation", "road_trip"]
        elif "family" in kw_lower or "home" in kw_lower:
            scenes = ["family_use"]
        elif "vlog" in kw_lower or "content" in kw_lower:
            scenes = ["vlog_content_creation"]
        else:
            scenes = ["outdoor_sports", "cycling_recording"]

        intent = {
            "id": f"intent_{idx + 1}",
            "english_label": kw_text.lower().replace(" ", "_"),
            "source_keywords": [kw_text],
            "search_volume": volume,
            "usage_scenarios": scenes,
            "capabilities": capabilities[:3],
            "user_identity": personas[idx % len(personas)],
            "purchase_intent": purchase_stages[idx % len(purchase_stages)],
            "pain_point": "needs stable footage and reliable waterproof performance",
            # PRD v8.2 SYNTH 标记
            "is_synthetic": data_mode == "SYNTHETIC_COLD_START" and idx >= 5
        }
        intents.append(intent)

    return intents


def generate_intent_graph(arsenal_output: Optional[Dict[str, Any]], preprocessed_data: Any) -> Dict[str, Any]:
    """
    生成纯英文 Intent Graph / STAG (Node 3.5)

    PRD v8.2 约束:
    - 强制使用 ENGLISH 输出
    - 输入任意语言关键词，归一化为英文意图标签
    - 添加 [SYNTH] 标记表明合成意图（当 data_mode=SYNTHETIC_COLD_START）
    - 输出结构保留足够字段供后续 Node 4 做「英文意图 → 目标语文案」映射

    Args:
        arsenal_output: 关键词军火库输出
        preprocessed_data: 预处理数据 (含 data_mode, language 等)

    Returns:
        纯英文 Intent Graph / STAG 结构
    """
    # 获取数据诊断信息
    data_mode = getattr(preprocessed_data, "data_mode", "SYNTHETIC_COLD_START")
    target_language = getattr(preprocessed_data, "language", "English")
    target_country = getattr(preprocessed_data, "target_country", "US")

    # 选择关键词
    keywords = _select_keywords_for_intent(arsenal_output, preprocessed_data)

    # 构建 Intent Graph (纯英文)
    intent_graph = _build_intent_graph(keywords, preprocessed_data, data_mode)

    # 构建 STAG Groups (纯英文)
    stag_groups = _build_stag_groups(keywords, data_mode)

    # 组装输出
    result = {
        "version": "v8.2",
        "reasoning_language": "EN",  # PRD v8.2: 固定为EN
        "target_language": target_language,
        "target_country": target_country,
        "data_mode": data_mode,
        "intent_graph": intent_graph,
        "stag_groups": stag_groups,
        # 供 Node 4 使用的元信息
        "metadata": {
            "total_intents": len(intent_graph),
            "total_stag_groups": len(stag_groups),
            "keywords_source": "arsenal" if arsenal_output else "preprocessed_data",
            "has_synthetic": any(i.get("is_synthetic", False) for i in intent_graph)
        }
    }

    return result


__all__ = ["generate_intent_graph"]
