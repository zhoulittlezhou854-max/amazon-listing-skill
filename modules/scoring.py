#!/usr/bin/env python3
"""算法评分模块 (Step 8)

按照 PRD v8.4.0 计算 A10 / COSMO / Rufus / 价格竞争力 四大评分维度，
并补充边界声明与 A+ 字数检查，输出 `scoring_detail` 结构。
"""

from __future__ import annotations

import math
import re
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple


MAX_A10 = 100
MAX_COSMO = 100
MAX_RUFUS = 100
MAX_PRICE = 10


def _lower_set(items: Sequence[str]) -> List[str]:
    return [item.lower() for item in items if isinstance(item, str) and item]


def _get_listing_text(generated_copy: Dict[str, Any]) -> str:
    parts = []
    if not generated_copy:
        return ""
    for key in ("title", "description", "aplus_content"):
        value = generated_copy.get(key)
        if isinstance(value, str):
            parts.append(value)
    if isinstance(generated_copy.get("bullets"), list):
        parts.extend(generated_copy["bullets"])
    if isinstance(generated_copy.get("faq"), list):
        for item in generated_copy["faq"]:
            parts.append(item.get("q", ""))
            parts.append(item.get("a", ""))
    return " \n".join(parts)


def _tier_keywords(preprocessed_data: Any) -> Tuple[List[str], List[str], List[str]]:
    l1, l2, l3 = [], [], []
    if not preprocessed_data:
        return l1, l2, l3

    keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    for row in keyword_rows:
        keyword = row.get("keyword") or row.get("search_term")
        if not keyword:
            continue
        volume = row.get("search_volume")
        try:
            volume = float(volume)
        except (TypeError, ValueError):
            volume = 0
        if volume >= 10000:
            l1.append(keyword)
        elif 1000 <= volume < 10000:
            l2.append(keyword)
        else:
            l3.append(keyword)
    return l1[:30], l2[:50], l3[:50]


def _count_occurrences(keywords: Sequence[str], text: str) -> int:
    if not keywords or not text:
        return 0
    text_lower = text.lower()
    return sum(1 for keyword in keywords if keyword and keyword.lower() in text_lower)


def _score_title_front_80(title: str, brand: str, scene_priority: List[str], l1_keywords: List[str]) -> Tuple[int, str]:
    max_score = 40
    if not title:
        return 0, "标题缺失"
    window = title[:80]
    score = 0
    notes = []
    if brand and brand.lower() in window.lower():
        score += 15
        notes.append("包含品牌")
    if l1_keywords and any(kw.lower() in window.lower() for kw in l1_keywords[:3]):
        score += 15
        notes.append("含L1词")
    if scene_priority and scene_priority[0] and scene_priority[0].lower() in window.lower():
        score += 10
        notes.append("含首要场景")
    return min(score, max_score), "，".join(notes) or "前80字符缺少关键要素"


def _score_keyword_tiering(generated_copy: Dict[str, Any], l1: List[str], l2: List[str], l3: List[str]) -> Tuple[int, str]:
    max_score = 30
    text = _get_listing_text(generated_copy)
    l1_hits = _count_occurrences(l1, generated_copy.get("title", "")) + _count_occurrences(l1, " ".join(generated_copy.get("bullets", [])))
    l2_hits = _count_occurrences(l2, text)
    st_terms = generated_copy.get("search_terms", []) or []
    search_term_text = " ".join(st_terms)
    l3_hits = _count_occurrences(l3, search_term_text)

    expected = 3  # Title/Bullets, 其他文案, Search Terms
    achieved = sum(hit > 0 for hit in (l1_hits, l2_hits, l3_hits))
    score = int((achieved / expected) * max_score)
    note = f"L1:{l1_hits} L2:{l2_hits} L3:{l3_hits}"
    return score, note


def _score_conversion_signals(bullets: List[str], attribute_data: Dict[str, Any]) -> Tuple[int, str]:
    max_score = 30
    if not bullets:
        return 0, "缺少 Bullets"

    score = 0
    notes = []

    # B1 应为 P0 tier（核心能力+主场景）
    if len(bullets) >= 1:
        # 简单检查：B1是否包含数字和关键描述
        bullet1 = bullets[0].lower()
        # 检查是否包含数字和场景/能力关键词
        has_number = bool(re.search(r"\d", bullet1))
        # 包含"防水"、"防抖"、"4K"等关键词
        has_keyword = any(kw in bullet1 for kw in ["防水", "防抖", "4k", "wifi", "双屏幕", "waterproof", "stabilization", "dual screen"])
        if has_number and has_keyword:
            score += 10
            notes.append("B1符合P0 tier")

    # B2-B3 应为 P1 tier（量化参数+场景词）
    p1_score = 0
    if len(bullets) >= 3:
        bullet2 = bullets[1].lower() if len(bullets) > 1 else ""
        bullet3 = bullets[2].lower() if len(bullets) > 2 else ""
        # 检查是否包含数字和量化参数
        has_number2 = bool(re.search(r"\d", bullet2))
        has_number3 = bool(re.search(r"\d", bullet3))
        # 检查是否包含参数关键词（如分钟、米、gb、g等）
        has_param2 = any(kw in bullet2 for kw in ["分钟", "米", "gb", "g", "min", "m", "克", "续航", "存储", "重量"])
        has_param3 = any(kw in bullet3 for kw in ["分钟", "米", "gb", "g", "min", "m", "克", "续航", "存储", "重量"])
        if has_number2 and has_param2:
            p1_score += 5
        if has_number3 and has_param3:
            p1_score += 5
    if p1_score > 0:
        score += p1_score
        notes.append(f"B2-B3 P1 tier得分{p1_score}")

    # B4-B5 应为 P2 tier（边界声明/质保售后）
    p2_score = 0
    if len(bullets) >= 5:
        bullet4 = bullets[3].lower() if len(bullets) > 3 else ""
        bullet5 = bullets[4].lower() if len(bullets) > 4 else ""
        # 检查边界声明关键词
        has_boundary4 = any(kw in bullet4 for kw in ["需", "需要", "not", "（", "(", "with ", "in "])
        has_warranty5 = any(kw in bullet5 for kw in ["质保", "保修", "warranty", "售后", "支持", "兼容"])
        # 检查是否包含数字
        has_number4 = bool(re.search(r"\d", bullet4))
        has_number5 = bool(re.search(r"\d", bullet5))
        if (has_boundary4 or has_number4):
            p2_score += 5
        if (has_warranty5 or has_number5):
            p2_score += 5
    if p2_score > 0:
        score += p2_score
        notes.append(f"B4-B5 P2 tier得分{p2_score}")

    # 确保不超过最高分
    score = min(score, max_score)
    note_str = "，".join(notes) if notes else "未达到tier要求"
    return score, note_str


def _score_scene_coverage(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> Tuple[int, str]:
    max_score = 40
    scenes = writing_policy.get("scene_priority", []) or []
    if not scenes:
        return 0, "无 scene_priority"
    text = _get_listing_text(generated_copy).lower()
    hits = sum(1 for scene in scenes if scene and scene.lower() in text)
    ratio = hits / len(scenes) if scenes else 0
    return int(ratio * max_score), f"覆盖 {hits}/{len(scenes)} 个场景"


def _score_capability_binding(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> Tuple[int, str]:
    max_score = 40
    bindings = writing_policy.get("capability_scene_bindings", []) or []
    if not bindings:
        return 0, "无能力绑定"
    text = _get_listing_text(generated_copy).lower()
    satisfied = 0
    for binding in bindings:
        capability = (binding.get("capability") or "").lower()
        allowed = _lower_set(binding.get("allowed_scenes", []))
        if capability and capability in text and any(scene in text for scene in allowed):
            satisfied += 1
    ratio = satisfied / len(bindings)
    score = min(max_score, int(ratio * max_score))
    return score, f"满足 {satisfied}/{len(bindings)} 条绑定"


def _score_audience_tags(generated_copy: Dict[str, Any]) -> Tuple[int, str]:
    max_score = 20
    personas = {
        "骑行": ["骑行", "biking", "cyclist"],
        "旅行": ["旅行", "travel", "commuter"],
        "家庭": ["家庭", "family", "kids"],
        "户外": ["户外", "outdoor", "hiker"],
    }
    text = _get_listing_text(generated_copy).lower()
    hits = 0
    hit_labels = []
    for label, keywords in personas.items():
        if any(keyword in text for keyword in keywords):
            hits += 1
            hit_labels.append(label)
    score = min(max_score, hits * 5)
    return score, f"触达人群: {', '.join(hit_labels) if hit_labels else '未提及受众'}"


def _score_fact_completeness(attribute_data: Dict[str, Any], generated_copy: Dict[str, Any]) -> Tuple[int, str]:
    max_score = 40
    if not attribute_data:
        return 0, "属性表缺失"
    text = _get_listing_text(generated_copy).lower()
    monitored_fields = [
        "video_resolution",
        "waterproof_depth",
        "battery_life",
        "weight",
        "max_storage",
        "connectivity",
    ]
    present = 0
    for field in monitored_fields:
        value = str(attribute_data.get(field, "")).lower()
        if value and value != "none" and value in text:
            present += 1
    ratio = present / len(monitored_fields)
    score = int(ratio * max_score)
    return score, f"事实覆盖 {present}/{len(monitored_fields)} 个参数"


def _score_faq_coverage(faq: List[Dict[str, str]]) -> Tuple[int, str]:
    max_score = 40
    if not faq:
        return 0, "FAQ缺失"
    count = len(faq)
    numeric_answers = sum(1 for item in faq if re.search(r"\d", item.get("a", "")))
    diversity = len({item.get("q") for item in faq})
    score = min(max_score, int((numeric_answers / max(1, count)) * 30) + (10 if count >= 5 and diversity >= 5 else 0))
    return score, f"FAQ 数量 {count}，含数字回答 {numeric_answers}"


def _score_conflict_check(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> Tuple[int, str]:
    max_score = 20
    forbidden_pairs = writing_policy.get("forbidden_pairs", []) or []
    if not forbidden_pairs:
        return max_score, "未定义禁止组合"
    text = _get_listing_text(generated_copy).lower()
    conflicts = 0
    for pair in forbidden_pairs:
        if len(pair) >= 2:
            a, b = pair[0].lower(), pair[1].lower()
            if a in text and b in text:
                conflicts += 1
    score = max(0, max_score - conflicts * 5)
    note = "无冲突" if conflicts == 0 else f"检测到 {conflicts} 处冲突"
    return score, note


def _price_stats(preprocessed_data: Any, attribute_data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) if preprocessed_data else []
    prices = []
    for row in keyword_rows or []:
        for key in ("avg_price", "price", "均价"):
            value = row.get(key)
            if value is None:
                continue
            try:
                prices.append(float(value))
            except (TypeError, ValueError):
                continue
    price_median = median(prices) if prices else None

    current_price = None
    price_note = None
    attr_candidates = [
        "price",
        "list_price",
        "msrp",
        "current_price",
        "offer_price",
        "售价",
    ]
    for key in attr_candidates:
        raw = attribute_data.get(key) if attribute_data else None
        if raw is None:
            continue
        try:
            current_price = float(str(raw).replace("€", "").replace("$", ""))
            break
        except ValueError:
            continue

    if price_median and current_price:
        ratio = current_price / price_median
        if ratio <= 0.9:
            price_note = "定价领先 (<90% 品类中位)"
        elif ratio <= 1.0:
            price_note = "定价贴近中位"
        elif ratio <= 1.1:
            price_note = "定价略高 (+10%)"
        elif ratio <= 1.2:
            price_note = "定价偏高 (+20%)"
        else:
            price_note = "定价远高于品类"
    elif not price_median or not current_price:
        price_note = "竞品或当前定价缺失"

    return price_median, current_price, price_note


def _score_price(price_median: Optional[float], current_price: Optional[float]) -> Tuple[int, bool, str]:
    if price_median and current_price:
        ratio = current_price / price_median
        if ratio <= 0.9:
            score = 10
        elif ratio <= 1.0:
            score = 9
        elif ratio <= 1.1:
            score = 7
        elif ratio <= 1.2:
            score = 5
        else:
            score = 2
        return score, True, f"品类中位 {price_median:.2f} vs 当前 {current_price:.2f}"
    return 0, False, "价格数据缺失，跳过评分"


def _boundary_check(bullets: List[str]) -> Dict[str, Any]:
    boundary_sentence = None
    for bullet in bullets or []:
        if any(marker in bullet for marker in ["需", "需要", "not", "（", "("]):
            boundary_sentence = bullet.strip()
            break
    return {
        "exists": boundary_sentence is not None,
        "sentence": boundary_sentence,
        "score_impact": "+10" if boundary_sentence else "0"
    }


def _aplus_check(aplus_content: str) -> Dict[str, Any]:
    word_count = len(re.findall(r"\w+", aplus_content or ""))
    meets = word_count >= 500
    return {
        "word_count": word_count,
        "meets_minimum": meets,
        "score_impact": "+15" if meets else "0"
    }


def calculate_scores(
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    preprocessed_data: Any
) -> Dict[str, Any]:
    """主入口，返回完整 scoring_detail 结构。"""

    title = generated_copy.get("title", "")
    bullets = generated_copy.get("bullets", []) or []
    attribute_data = getattr(getattr(preprocessed_data, "attribute_data", None), "data", {}) if preprocessed_data else {}
    brand = getattr(getattr(preprocessed_data, "run_config", None), "brand_name", None) or ""
    scene_priority = writing_policy.get("scene_priority", []) or []

    l1, l2, l3 = _tier_keywords(preprocessed_data)

    a10_title_score, a10_title_note = _score_title_front_80(title, brand, scene_priority, l1)
    a10_kw_score, a10_kw_note = _score_keyword_tiering(generated_copy, l1, l2, l3)
    a10_conv_score, a10_conv_note = _score_conversion_signals(bullets, attribute_data)
    a10_subtotal = a10_title_score + a10_kw_score + a10_conv_score

    scene_score, scene_note = _score_scene_coverage(writing_policy, generated_copy)
    binding_score, binding_note = _score_capability_binding(writing_policy, generated_copy)
    audience_score, audience_note = _score_audience_tags(generated_copy)
    cosmo_subtotal = scene_score + binding_score + audience_score

    fact_score, fact_note = _score_fact_completeness(attribute_data, generated_copy)
    faq_score, faq_note = _score_faq_coverage(generated_copy.get("faq", []))
    conflict_score, conflict_note = _score_conflict_check(writing_policy, generated_copy)
    rufus_subtotal = fact_score + faq_score + conflict_score

    price_median, current_price, price_note = _price_stats(preprocessed_data, attribute_data)
    price_score, price_available, price_detail_note = _score_price(price_median, current_price)

    boundary_check = _boundary_check(bullets)
    aplus_check = _aplus_check(generated_copy.get("aplus_content", ""))

    max_total = MAX_A10 + MAX_COSMO + MAX_RUFUS + (MAX_PRICE if price_available else 0)
    total_score = a10_subtotal + cosmo_subtotal + rufus_subtotal + (price_score if price_available else 0)
    percent = (total_score / max_total) * 100 if max_total else 0
    if percent >= 90:
        rating = "优秀"
    elif percent >= 70:
        rating = "良好"
    else:
        rating = "待优化"

    result = {
        "a10": {
            "title_front_80": {"max": 40, "score": a10_title_score, "note": a10_title_note},
            "keyword_tiering": {"max": 30, "score": a10_kw_score, "note": a10_kw_note},
            "conversion_signals": {"max": 30, "score": a10_conv_score, "note": a10_conv_note},
            "subtotal": a10_subtotal
        },
        "cosmo": {
            "scene_coverage": {"max": 40, "score": scene_score, "note": scene_note},
            "capability_scene_binding": {"max": 40, "score": binding_score, "note": binding_note},
            "audience_tags": {"max": 20, "score": audience_score, "note": audience_note},
            "subtotal": cosmo_subtotal
        },
        "rufus": {
            "fact_completeness": {"max": 40, "score": fact_score, "note": fact_note},
            "faq_coverage": {"max": 40, "score": faq_score, "note": faq_note},
            "conflict_check": {"max": 20, "score": conflict_score, "note": conflict_note},
            "subtotal": rufus_subtotal
        },
        "price_competitiveness": {
            "price_median": price_median,
            "current_price": current_price,
            "max": MAX_PRICE if price_available else 0,
            "score": price_score if price_available else None,
            "range": price_note,
            "data_available": price_available,
            "note": price_detail_note
        },
        "total_score": total_score,
        "max_total": max_total,
        "grade_percent": round(percent, 1),
        "rating": rating,
        "boundary_declaration_check": boundary_check,
        "aplus_word_count_check": aplus_check,
        "scoring_detail_version": "v8.4.0"
    }

    # 兼容 Step 8 旧字段
    result.update({
        "a10_score": a10_subtotal,
        "cosmo_score": cosmo_subtotal,
        "rufus_score": rufus_subtotal,
        "price_competitiveness_score": price_score if price_available else None,
        "grade": rating
    })

    return result


__all__ = ["calculate_scores"]
