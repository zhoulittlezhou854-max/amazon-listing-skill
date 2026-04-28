#!/usr/bin/env python3
"""算法评分模块 (hybrid metadata + visible-text driven)

依据 PRD 规则对 A10 / COSMO / Rufus / 价格竞争力四维度打分。
新版评分以 pipeline 元数据为主，并在 COSMO 维度补充扫描最终可见字段，
避免因为 LLM 的 capability_mapping/scene_mapping 略保守而低估真实可见覆盖。
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.compute_tiering import summarize_compute_tier_map
from modules.evidence_engine import summarize_evidence_bundle
from modules.generation_status import is_live_success_status
from modules.intent_weights import summarize_intent_weight_snapshot
from modules.listing_status import (
    NOT_READY_FOR_LISTING,
    DIMENSION_THRESHOLDS,
    build_action_required,
    build_review_queue,
    determine_listing_status,
)
from modules.risk_check import collect_fluency_issues

MAX_A10 = 100
MAX_COSMO = 100
MAX_RUFUS = 100
MAX_PRICE = 10
MAX_AI_OS = 100
MAX_READABILITY = 30
FLUENCY_FIELD_WEIGHTS = {
    "title": 10,
    "bullet_b1": 4,
    "bullet_b2": 3,
    "bullet_b3": 3,
    "bullet_b4": 2,
    "bullet_b5": 2,
    "aplus": 6,
}


def _normalize_tier(value: Optional[str]) -> str:
    if not value:
        return ""
    tier = str(value).upper()
    return tier if tier in {"L1", "L2", "L3"} else tier


def _extract_keyword_assignments(
    decision_trace: Dict[str, Any],
    preprocessed_data: Any,
) -> List[Dict[str, Any]]:
    """Return keyword assignment records while preserving protocol metadata."""
    assignments = decision_trace.get("keyword_assignments")
    normalized: List[Dict[str, Any]] = []
    if isinstance(assignments, list):
        for row in assignments:
            fields = row.get("assigned_fields") or []
            if not fields:
                continue
            record = dict(row)
            traffic_tier = row.get("traffic_tier") or row.get("tier")
            record["tier"] = _normalize_tier(traffic_tier)
            record["traffic_tier"] = _normalize_tier(traffic_tier)
            record["assigned_fields"] = list(fields)
            normalized.append(record)
    if normalized:
        return normalized

    # fallback to preprocessed_data.keyword_metadata (may include assigned_fields after copy_generation)
    meta_list = getattr(preprocessed_data, "keyword_metadata", []) or []
    for entry in meta_list:
        fields = entry.get("assigned_fields")
        if not fields:
            continue
        record = dict(entry)
        traffic_tier = entry.get("traffic_tier") or entry.get("tier") or entry.get("level")
        record["tier"] = _normalize_tier(traffic_tier)
        record["traffic_tier"] = _normalize_tier(traffic_tier)
        record["assigned_fields"] = list(fields)
        normalized.append(record)
    return normalized


def _score_a10(assignments: List[Dict[str, Any]], audit_trail: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    def _fields(entry: Dict[str, Any]) -> List[str]:
        return [str(field or "") for field in (entry.get("assigned_fields") or [])]

    def _has_title(entry: Dict[str, Any]) -> bool:
        return any(field.startswith("title") for field in _fields(entry))

    def _bullet_fields(entry: Dict[str, Any]) -> List[str]:
        return [field for field in _fields(entry) if field.startswith("bullet_")]

    def _has_search_terms(entry: Dict[str, Any]) -> bool:
        return "search_terms" in _fields(entry)

    def _quality_status(entry: Dict[str, Any]) -> str:
        return str(entry.get("quality_status") or "qualified").strip().lower()

    def _routing_role(entry: Dict[str, Any]) -> str:
        return str(entry.get("routing_role") or "").strip().lower()

    def _traffic_tier(entry: Dict[str, Any]) -> str:
        return _normalize_tier(entry.get("traffic_tier") or entry.get("tier"))

    def _is_qualified(entry: Dict[str, Any]) -> bool:
        return _quality_status(entry) in {"", "qualified"}

    def _is_bad_quality(entry: Dict[str, Any]) -> bool:
        return _quality_status(entry) in {"rejected", "blocked"}

    def _intended_role(entry: Dict[str, Any], *, has_role_metadata: bool) -> str:
        role = _routing_role(entry)
        if role:
            return role
        tier = _traffic_tier(entry)
        if not has_role_metadata:
            if tier == "L1":
                return "title"
            if tier == "L2":
                return "bullet"
            if tier == "L3":
                return "backend"
        return ""

    tier_map: Dict[str, List[Dict[str, Any]]] = {"L1": [], "L2": [], "L3": []}
    for entry in assignments:
        tier = _traffic_tier(entry)
        if tier not in tier_map:
            tier_map[tier] = []
        tier_map[tier].append(entry)

    has_role_metadata = any(_routing_role(entry) for entry in assignments)
    qualified = [entry for entry in assignments if _is_qualified(entry)]
    bad_visible = [
        entry
        for entry in assignments
        if _is_bad_quality(entry) and (_has_title(entry) or _bullet_fields(entry))
    ]

    head_candidates = [
        entry
        for entry in qualified
        if _routing_role(entry) == "title" or _traffic_tier(entry) == "L1"
    ]
    head_hits = sum(1 for entry in head_candidates if _has_title(entry))
    head_target = max(1, min(3, len(head_candidates))) if head_candidates else 1
    head_score = int(min(1.0, head_hits / head_target) * 30) if head_candidates else 0
    head_note = f"Head traffic anchors {head_hits}/{len(head_candidates) or '0'} placed in title"

    placement_candidates = [
        entry
        for entry in qualified
        if _intended_role(entry, has_role_metadata=has_role_metadata) in {"title", "bullet", "backend", "residual"}
    ]
    placement_hits = 0
    for entry in placement_candidates:
        role = _intended_role(entry, has_role_metadata=has_role_metadata)
        if role == "title" and _has_title(entry):
            placement_hits += 1
        elif role == "bullet" and _bullet_fields(entry):
            placement_hits += 1
        elif role in {"backend", "residual"} and _has_search_terms(entry):
            placement_hits += 1
    placement_target = max(1, len(placement_candidates)) if placement_candidates else 1
    placement_score = int(min(1.0, placement_hits / placement_target) * 25) if placement_candidates else 0
    placement_note = f"Qualified keyword placement {placement_hits}/{len(placement_candidates) or '0'} matched intended role"

    bullet_entries = [
        entry
        for entry in qualified
        if _routing_role(entry) == "bullet" or (not has_role_metadata and _traffic_tier(entry) == "L2")
    ]
    bullet_fields = set()
    for entry in bullet_entries:
        bullet_fields.update(_bullet_fields(entry))
    unique_slots = len(bullet_fields)
    if unique_slots >= 3:
        bullet_score = 25
    elif unique_slots == 2:
        bullet_score = 17
    elif unique_slots == 1:
        bullet_score = 8
    else:
        bullet_score = 0
    bullet_note = f"Bullet conversion keywords cover {unique_slots} bullet slots"

    if has_role_metadata:
        backend_entries = [
            entry for entry in qualified if _routing_role(entry) in {"backend", "residual"}
        ]
    else:
        backend_entries = tier_map.get("L3", [])
    backend_hits = sum(
        1
        for entry in backend_entries
        if _has_search_terms(entry)
    )
    backend_target = max(1, min(5, len(backend_entries))) if backend_entries else 1
    backend_score = int(min(1.0, backend_hits / backend_target) * 10) if backend_entries else 0
    backend_note = f"Backend residual keywords {backend_hits}/{len(backend_entries) or '0'} placed in Search Terms"

    quality_score = 0 if bad_visible else 10
    quality_note = (
        f"Blocked/rejected visible keywords: {len(bad_visible)}"
        if bad_visible
        else "No blocked or rejected visible keywords"
    )

    brand_violation = any(
        (entry or {}).get("action") == "brand_visible_violation"
        for entry in (audit_trail or [])
    )
    if brand_violation:
        head_score = placement_score = bullet_score = backend_score = quality_score = 0
        head_note += "（检测到竞争品牌，A10 清零）"
        placement_note += "（检测到竞争品牌，A10 清零）"
        bullet_note += "（检测到竞争品牌，A10 清零）"
        backend_note += "（检测到竞争品牌，A10 清零）"
        quality_note += "（检测到竞争品牌，A10 清零）"

    if bad_visible:
        placement_score = 0
        placement_note += "；visible rejected/blocked keyword invalidates placement"

    l1_score = min(40, head_score + 10) if head_score else 0
    l2_score = min(30, bullet_score)
    l3_score = min(30, backend_score)
    subtotal = head_score + placement_score + bullet_score + backend_score + quality_score
    return {
        "head_traffic_anchor": {"max": 30, "score": head_score, "note": head_note},
        "qualified_keyword_placement": {"max": 25, "score": placement_score, "note": placement_note},
        "bullet_conversion_coverage": {"max": 25, "score": bullet_score, "note": bullet_note},
        "backend_residual_coverage": {"max": 10, "score": backend_score, "note": backend_note},
        "keyword_quality_penalty": {"max": 10, "score": quality_score, "note": quality_note},
        "l1_title_alignment": {"max": 40, "score": l1_score, "note": head_note},
        "l2_bullet_distribution": {"max": 30, "score": l2_score, "note": bullet_note},
        "l3_search_terms": {"max": 30, "score": l3_score, "note": backend_note},
        "subtotal": subtotal,
    }


def _count_compliance_actions(audit_trail: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "downgrade": 0,
        "backend_only": 0,
        "taboo_skip": 0,
        "locale_skip": 0,
        "brand_skip": 0,
        "constraint_skip": 0,
        "word_swap": 0,
    }
    for entry in audit_trail or []:
        action = entry.get("action")
        if action == "backend_only_deferred":
            counts["backend_only"] += 1
            continue
        if action == "compliance_word_swap":
            counts["word_swap"] += 1
            continue
        if action in counts:
            counts[action] += 1
    return counts


def _capability_token_roots(text: str) -> set[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    roots: set[str] = set()
    synonyms = {
        "video": "recording",
        "capture": "recording",
        "filming": "recording",
        "filme": "recording",
        "wi": "wifi",
        "fi": "wifi",
        "wireless": "wifi",
        "connectivity": "wifi",
        "connection": "wifi",
        "connected": "wifi",
        "screen": "display",
        "screens": "display",
        "dual": "display",
        "display": "display",
        "travels": "travel",
        "traveling": "travel",
        "travelling": "travel",
        "commute": "commuting",
        "commuter": "commuting",
        "rides": "cycling",
        "ride": "cycling",
        "bike": "cycling",
        "helmet": "cycling",
        "sport": "sports",
        "training": "sports",
    }
    stopwords = {"for", "and", "with", "the", "a", "an", "to", "of", "camera", "action", "use", "using", "included", "compatible"}
    for token in raw_tokens:
        if token in stopwords:
            continue
        roots.add(synonyms.get(token, token))
    return roots


def _capability_matches(supported: str, mapped: str) -> bool:
    supported_norm = (supported or "").lower()
    mapped_norm = (mapped or "").lower()
    if not supported_norm or not mapped_norm:
        return False
    if supported_norm in mapped_norm or mapped_norm in supported_norm:
        return True
    supported_roots = _capability_token_roots(supported_norm)
    mapped_roots = _capability_token_roots(mapped_norm)
    if not supported_roots or not mapped_roots:
        return False
    return supported_roots.issubset(mapped_roots) or mapped_roots.issubset(supported_roots)


def _visible_text(generated_copy: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(generated_copy.get("title") or ""),
            " ".join(generated_copy.get("bullets") or []),
            str(generated_copy.get("description") or ""),
        ]
    ).strip()


SCENE_TEXT_ALIASES: Dict[str, List[str]] = {
    "outdoor_sports": ["outdoor sports", "outdoor", "adventure", "trail"],
    "cycling_recording": ["cycling", "bike", "ride", "helmet", "commute", "pov"],
    "underwater_exploration": ["underwater", "snorkeling", "diving", "water"],
    "travel_documentation": ["travel", "trip", "vacation", "route review", "journey"],
    "road_trip": ["road trip", "route review", "scenic drive", "trip"],
    "family_use": ["family", "kids", "weekend", "parents"],
    "daily_lifelogging": ["everyday", "daily", "commute", "on the go", "moments"],
    "vlog_content_creation": ["vlog", "creator", "selfie", "content"],
    "sports_training": ["training", "workout", "sports", "practice"],
}


def _visible_capability_hits(
    supported_caps: Sequence[str],
    bullet_trace: Sequence[Dict[str, Any]],
    visible_text: str,
) -> set[str]:
    visible_caps: set[str] = set()
    visible_roots = _capability_token_roots(visible_text)
    mapped_candidates: List[str] = []
    for entry in bullet_trace or []:
        mapped_candidates.extend(entry.get("capability_mapping") or [])
        mapped_candidates.extend(entry.get("capability_bundle") or [])
        if entry.get("capability"):
            mapped_candidates.append(entry.get("capability"))

    for supported in supported_caps:
        if not supported:
            continue
        supported_roots = _capability_token_roots(supported)
        if supported_roots and supported_roots.issubset(visible_roots):
            visible_caps.add(supported)
            continue
        for mapped in mapped_candidates:
            if _capability_matches(supported, str(mapped or "")):
                visible_caps.add(supported)
                break
    return visible_caps


def _visible_scene_hits(
    expected_scenes: Sequence[str],
    bullet_trace: Sequence[Dict[str, Any]],
    visible_text: str,
) -> set[str]:
    visible_scenes: set[str] = set()
    lowered_text = (visible_text or "").lower()

    for entry in bullet_trace or []:
        scene_code = (entry.get("scene_code") or "").lower()
        if scene_code:
            visible_scenes.add(scene_code)
        for mapped_scene in entry.get("scene_mapping") or entry.get("scenes") or []:
            normalized_scene = (mapped_scene or "").lower()
            if normalized_scene:
                visible_scenes.add(normalized_scene)

    for scene in expected_scenes or []:
        aliases = SCENE_TEXT_ALIASES.get(scene, []) + [scene.replace("_", " ")]
        if any(alias and alias.lower() in lowered_text for alias in aliases):
            visible_scenes.add(scene)
    return visible_scenes


def _score_cosmo(
    generated_copy: Dict[str, Any],
    bullet_trace: Sequence[Dict[str, Any]],
    intent_graph: Optional[Dict[str, Any]],
    writing_policy: Dict[str, Any],
    audit_trail: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    capability_meta = (intent_graph or {}).get("capability_metadata", []) or []
    supported_caps = [
        (entry.get("capability") or "").lower()
        for entry in capability_meta
        if entry.get("is_supported", True)
    ]
    scene_meta = (intent_graph or {}).get("scene_metadata", []) or []
    expected_scenes = [
        (entry.get("scene") or "").lower()
        for entry in scene_meta
        if entry.get("visibility", "visible") != "removed"
    ]
    if not expected_scenes:
        expected_scenes = [
            (code or "").lower()
            for code in writing_policy.get("scene_priority", [])[:4]
        ]

    visible_text = _visible_text(generated_copy)
    if supported_caps:
        visible_caps = _visible_capability_hits(supported_caps, bullet_trace, visible_text)
    else:
        visible_caps = set()
    visible_scenes = _visible_scene_hits(expected_scenes, bullet_trace, visible_text)

    cap_total = len(supported_caps) or 1
    capability_score = int(min(1.0, len(visible_caps) / cap_total) * 40)
    capability_note = (
        f"可宣称能力 {len(visible_caps)}/{len(supported_caps) or '0'} 呈现在可见字段"
        if supported_caps
        else "缺少 capability_metadata，跳过覆盖率要求"
    )

    expected_scene_count = len(expected_scenes) or 1
    scene_score = int(min(1.0, len(visible_scenes) / expected_scene_count) * 40)
    scene_note = f"场景覆盖 {len(visible_scenes)}/{len(expected_scenes) or '0'}"

    compliance_counts = _count_compliance_actions(audit_trail)
    bonus_points = min(
        20,
        compliance_counts.get("downgrade", 0) * 4
        + compliance_counts.get("backend_only", 0) * 4
        + compliance_counts.get("taboo_skip", 0) * 5,
    )
    compliance_note = (
        f"downgrade:{compliance_counts.get('downgrade',0)} "
        f"backend_only:{compliance_counts.get('backend_only',0)} "
        f"taboo_skip:{compliance_counts.get('taboo_skip',0)} "
        f"brand_skip:{compliance_counts.get('brand_skip',0)} "
        f"constraint_skip:{compliance_counts.get('constraint_skip',0)} "
        f"word_swap:{compliance_counts.get('word_swap',0)}"
    )

    subtotal = capability_score + scene_score + bonus_points
    return {
        "capability_coverage": {
            "max": 40,
            "score": capability_score,
            "note": capability_note,
        },
        "scene_distribution": {"max": 40, "score": scene_score, "note": scene_note},
        "compliance_actions": {
            "max": 20,
            "score": bonus_points,
            "note": compliance_note,
        },
        "subtotal": subtotal,
    }


def _extract_visible_spec_signals(
    generated_copy: Dict[str, Any],
    capability_constraints: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    def _dedupe(items: Sequence[str]) -> List[str]:
        return list(dict.fromkeys([item for item in items if item]))

    visible_text = " ".join(
        [
            str(generated_copy.get("title") or ""),
            " ".join(generated_copy.get("bullets") or []),
            str(generated_copy.get("description") or ""),
            str(generated_copy.get("aplus_content") or ""),
        ]
    ).lower()
    attribute_evidence = ((generated_copy.get("evidence_bundle") or {}).get("attribute_evidence") or {})

    def _attr_text(*keys: str) -> str:
        values = [str(attribute_evidence.get(key) or "") for key in keys]
        return " ".join(values).strip().lower()

    available_specs: List[str] = []
    visible_specs: List[str] = []

    runtime_value = capability_constraints.get("runtime_minutes") or _attr_text("battery average life", "battery_life")
    if runtime_value:
        available_specs.append("runtime")
        if re.search(r"\b(?:150|90)\s*minutes?\b", visible_text) or "runtime" in visible_text:
            visible_specs.append("runtime")

    resolution_text = _attr_text("video capture resolution", "video_resolution", "effective video reso")
    if resolution_text:
        available_specs.append("resolution")
        if any(token in visible_text for token in ["1080p", "4k", "1920"]):
            visible_specs.append("resolution")

    weight_text = _attr_text("item weight", "weight")
    if weight_text:
        available_specs.append("weight")
        if any(token in visible_text for token in ["0.1 kilograms", "0.1 kilogram", "0.1 kg", "100g", "100 g"]):
            visible_specs.append("weight")

    view_text = _attr_text("lens type", "maximum focal length", "minimum focal length")
    if view_text:
        available_specs.append("view_angle")
        if any(token in visible_text for token in ["wide angle", "180", "30 millimeters", "28 millimeters"]):
            visible_specs.append("view_angle")

    waterproof_depth = capability_constraints.get("waterproof_depth_m")
    waterproof_text = _attr_text("water resistance leve", "water_resistance_level")
    waterproof_supported = bool(waterproof_depth) or (
        waterproof_text and "not water resistant" not in waterproof_text and "not waterproof" not in waterproof_text
    )
    if waterproof_supported:
        available_specs.append("waterproof")
        if any(token in visible_text for token in ["waterproof", "water resistant", "underwater", "30 m"]):
            visible_specs.append("waterproof")

    return _dedupe(available_specs), _dedupe(visible_specs)


def _score_rufus(
    generated_copy: Dict[str, Any],
    bullet_trace: Sequence[Dict[str, Any]],
    capability_constraints: Dict[str, Any],
    search_terms_trace: Dict[str, Any],
) -> Dict[str, Any]:
    expected_numeric = [
        entry
        for entry in bullet_trace or []
        if entry.get("numeric_expectation")
    ]
    met_numeric = [
        entry
        for entry in expected_numeric
        if entry.get("numeric_met")
    ]
    if expected_numeric:
        numeric_score = int(len(met_numeric) / len(expected_numeric) * 40)
    else:
        numeric_score = 40
    numeric_note = (
        f"满足 {len(met_numeric)}/{len(expected_numeric)} 个 numeric expectation"
        if expected_numeric
        else "无 numeric expectation，视为达标"
    )

    available_specs, visible_specs = _extract_visible_spec_signals(generated_copy, capability_constraints)
    if not available_specs:
        spec_score = 20
        spec_note = "结构化规格：无（缺失不扣分）"
    else:
        target_specs = max(1, min(4, len(available_specs)))
        covered = len([spec for spec in available_specs if spec in visible_specs][:target_specs])
        spec_score = int(min(1.0, covered / target_specs) * 40)
        spec_note = (
            f"结构化规格：{', '.join(available_specs)} "
            f"visible_specs={covered}/{target_specs}"
        )

    byte_len = search_terms_trace.get("byte_length", 0)
    target_bytes = max(1, search_terms_trace.get("max_bytes", 249))
    search_score = int(min(1.0, byte_len / 150) * 20)
    search_note = f"Search Terms 使用 {byte_len}/{target_bytes} bytes"

    subtotal = numeric_score + spec_score + search_score
    return {
        "numeric_expectations": {
            "max": 40,
            "score": numeric_score,
            "note": numeric_note,
        },
        "spec_signal_coverage": {
            "max": 40,
            "score": spec_score,
            "note": spec_note,
        },
        "search_term_bytes": {
            "max": 20,
            "score": search_score,
            "note": search_note,
        },
        "subtotal": subtotal,
    }


def _search_trace_fallback(generated_copy: Dict[str, Any]) -> Dict[str, Any]:
    terms = generated_copy.get("search_terms") or []
    term_text = " ".join(terms)
    return {
        "byte_length": len(term_text.encode("utf-8")),
        "max_bytes": 249,
        "backend_only_used": 0,
    }


def _price_stats(
    preprocessed_data: Any, attribute_data: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    keyword_rows = getattr(
        getattr(preprocessed_data, "keyword_data", None), "keywords", []
    ) if preprocessed_data else []
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


def _score_price(
    price_median: Optional[float], current_price: Optional[float]
) -> Tuple[int, bool, str]:
    if price_median and current_price:
        ratio = current_price / price_median
        if 0.85 <= ratio <= 1.10:
            score = 10
        elif 0.70 <= ratio < 0.85:
            score = 7
        elif 1.10 < ratio <= 1.15:
            score = 6
        elif ratio > 1.15:
            score = 0
        elif ratio < 0.70:
            score = 3
        else:
            score = 0
        return score, True, f"品类中位 {price_median:.2f} vs 当前 {current_price:.2f}"
    return 0, False, "价格数据缺失，跳过评分"


def _boundary_check_from_trace(bullet_trace: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    boundary_slot = next(
        (entry for entry in bullet_trace or [] if entry.get("slot") == "B4"),
        None,
    )
    exists = boundary_slot is not None
    return {
        "exists": exists,
        "sentence": boundary_slot.get("capability") if exists else None,
        "score_impact": "+10" if exists else "0",
    }


def _aplus_check(aplus_content: str) -> Dict[str, Any]:
    word_count = len(re.findall(r"\w+", aplus_content or ""))
    meets = word_count >= 500
    return {
        "word_count": word_count,
        "meets_minimum": meets,
        "score_impact": "+15" if meets else "0",
    }


def _score_production_readiness(metadata: Dict[str, Any]) -> Dict[str, Any]:
    generation_status = metadata.get("generation_status") or "offline"
    fallback_count = int(metadata.get("llm_fallback_count") or 0)
    unsupported_claim_count = int(metadata.get("unsupported_claim_count") or 0)
    fallback_density = int(metadata.get("fallback_density") or 0)
    if is_live_success_status(generation_status):
        penalty = 0
        authenticity_score = 10
        advisory = "Live GPT generation confirmed."
    elif generation_status == "live_with_fallback":
        penalty = min(8, 3 + fallback_count)
        authenticity_score = 6
        advisory = f"Live generation completed with {fallback_count} fallback field(s)."
    else:
        penalty = 15
        authenticity_score = 0
        advisory = "Offline or unverifiable generation; production score must be downgraded."
    return {
        "generation_status": generation_status,
        "configured_model": metadata.get("configured_model") or metadata.get("llm_model"),
        "returned_model": metadata.get("returned_model"),
        "fallback_count": fallback_count,
        "fallback_density": fallback_density,
        "unsupported_claim_count": unsupported_claim_count,
        "authenticity_score": authenticity_score,
        "penalty": penalty,
        "advisory": advisory,
        "llm_response_state": metadata.get("llm_response_state", ""),
    }


def _score_ai_os_readiness(
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
) -> Dict[str, Any]:
    evidence_summary = summarize_evidence_bundle(generated_copy.get("evidence_bundle", {}) or {})
    compute_summary = summarize_compute_tier_map(generated_copy.get("compute_tier_map", {}) or {})
    intent_weight_snapshot = (
        writing_policy.get("intent_weight_snapshot")
        or generated_copy.get("intent_weight_snapshot")
        or {}
    )
    intent_summary = writing_policy.get("intent_weight_summary") or summarize_intent_weight_snapshot(
        intent_weight_snapshot
    )
    market_pack = writing_policy.get("market_pack", {}) or {}

    claim_count = int(evidence_summary.get("claim_count") or 0)
    supported_claim_count = int(evidence_summary.get("supported_claim_count") or 0)
    unsupported_claim_count = int(evidence_summary.get("unsupported_claim_count") or 0)
    if claim_count <= 0:
        evidence_score = 0
        evidence_note = "缺少结构化 evidence bundle，无法判断 claim 支撑度"
    else:
        support_ratio = min(1.0, supported_claim_count / claim_count)
        unsupported_ratio = min(1.0, unsupported_claim_count / claim_count)
        rufus_score = min(1.0, float(evidence_summary.get("rufus_score") or 0.0))
        evidence_blend = max(
            0.0,
            min(
                1.0,
                support_ratio * 0.5
                + rufus_score * 0.3
                + (1.0 - unsupported_ratio) * 0.2,
            ),
        )
        evidence_score = int(round(25 * evidence_blend))
        evidence_note = (
            f"supported={supported_claim_count}/{claim_count} "
            f"unsupported={unsupported_claim_count} "
            f"rufus={rufus_score:.2f}"
        )

    lexical_preferences = list(market_pack.get("lexical_preferences") or [])
    faq_templates = list(market_pack.get("faq_templates") or [])
    compliance_reminders = list(market_pack.get("compliance_reminders") or [])
    after_sales_promises = list(market_pack.get("after_sales_promises") or [])
    support_sop = list(market_pack.get("support_sop") or [])
    regulatory_watchouts = list(market_pack.get("regulatory_watchouts") or [])
    market_score = (
        (8 if market_pack.get("locale") else 0)
        + (4 if lexical_preferences else 0)
        + (4 if faq_templates else 0)
        + (3 if compliance_reminders else 0)
        + (3 if after_sales_promises else 0)
        + (2 if support_sop else 0)
        + (1 if regulatory_watchouts else 0)
    )
    market_note = (
        f"locale={market_pack.get('locale') or 'n/a'} "
        f"lexical={len(lexical_preferences)} "
        f"faq_templates={len(faq_templates)} "
        f"reminders={len(compliance_reminders)} "
        f"after_sales={len(after_sales_promises)} "
        f"sop={len(support_sop)}"
    )

    field_count = int(compute_summary.get("field_count") or 0)
    fallback_field_count = int(compute_summary.get("fallback_field_count") or 0)
    rerun_recommended_count = int(compute_summary.get("rerun_recommended_count") or 0)
    if field_count <= 0:
        compute_score = 0
        compute_note = "缺少 compute tier map，无法判断字段级 provenance"
    else:
        provenance_score = min(10, field_count)
        stability_score = max(0, 10 - fallback_field_count * 2)
        rerun_score = 5 if fallback_field_count == 0 else min(5, rerun_recommended_count)
        compute_score = provenance_score + stability_score + rerun_score
        compute_note = f"fields={field_count} fallback={fallback_field_count} rerun={rerun_recommended_count}"

    updated_keyword_count = int(intent_summary.get("updated_keyword_count") or 0)
    scene_count = int(intent_summary.get("scene_count") or 0)
    capability_count = int(intent_summary.get("capability_count") or 0)
    channel_count = int(intent_summary.get("channel_count") or 0)
    external_theme_count = int(intent_summary.get("external_theme_count") or 0)
    if updated_keyword_count == 0 and scene_count == 0 and capability_count == 0 and channel_count == 0 and external_theme_count == 0:
        intent_score = 0
        intent_note = "未加载 intent weight snapshot"
    else:
        intent_score = min(
            25,
            min(10, updated_keyword_count * 2)
            + min(6, scene_count * 3)
            + min(5, capability_count * 2)
            + min(2, channel_count)
            + min(2, external_theme_count),
        )
        intent_note = (
            f"keywords={updated_keyword_count} scenes={scene_count} "
            f"capabilities={capability_count} channels={channel_count} "
            f"themes={external_theme_count}"
        )

    subtotal = evidence_score + market_score + compute_score + intent_score
    percent = (subtotal / MAX_AI_OS) * 100 if MAX_AI_OS else 0
    if percent >= 85:
        grade = "优秀"
    elif percent >= 60:
        grade = "良好"
    else:
        grade = "待补强"

    return {
        "evidence_alignment": {"max": 25, "score": evidence_score, "note": evidence_note},
        "market_localization": {"max": 25, "score": market_score, "note": market_note},
        "compute_observability": {"max": 25, "score": compute_score, "note": compute_note},
        "intent_learning": {"max": 25, "score": intent_score, "note": intent_note},
        "subtotal": subtotal,
        "grade": grade,
    }


def _score_readability(generated_copy: Dict[str, Any]) -> Dict[str, Any]:
    issues = collect_fluency_issues(generated_copy)
    issues_by_field: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        field = str(issue.get("field") or "").strip()
        if not field:
            continue
        issues_by_field.setdefault(field, []).append(issue)

    bullets = generated_copy.get("bullets") or []
    field_texts = {
        "title": str(generated_copy.get("title") or "").strip(),
        "bullet_b1": str(bullets[0] if len(bullets) > 0 else "").strip(),
        "bullet_b2": str(bullets[1] if len(bullets) > 1 else "").strip(),
        "bullet_b3": str(bullets[2] if len(bullets) > 2 else "").strip(),
        "bullet_b4": str(bullets[3] if len(bullets) > 3 else "").strip(),
        "bullet_b5": str(bullets[4] if len(bullets) > 4 else "").strip(),
        "aplus": str(generated_copy.get("aplus_content") or "").strip(),
    }

    breakdown: Dict[str, int] = {}
    blocking_fields: List[str] = []
    detail: Dict[str, Any] = {}
    for field, max_score in FLUENCY_FIELD_WEIGHTS.items():
        text = field_texts.get(field, "")
        field_issues = issues_by_field.get("aplus_content" if field == "aplus" else field, [])
        if not text:
            score = max_score
            status = "missing_skip"
        else:
            severities = {str(issue.get("severity") or "").lower() for issue in field_issues}
            if "high" in severities:
                score = 0
                blocking_fields.append(field)
                status = "high_issue"
            elif "medium" in severities:
                score = max_score // 2
                status = "medium_issue"
            else:
                score = max_score
                status = "clean"
        breakdown[field] = score
        detail[field] = {
            "max": max_score,
            "score": score,
            "status": status,
            "issues": [f"{item.get('rule')}:{item.get('severity')}" for item in field_issues],
        }

    subtotal = sum(breakdown.values())
    return {
        "label": "Fluency",
        "score": subtotal,
        "max": MAX_READABILITY,
        "threshold": DIMENSION_THRESHOLDS["readability"],
        "status": "pass" if subtotal >= DIMENSION_THRESHOLDS["readability"] else "fail",
        "breakdown": breakdown,
        "field_details": detail,
        "blocking_fields": blocking_fields,
        "issue_count": len(issues),
        "issue_sample": [f"{item.get('field')}:{item.get('rule')}" for item in issues[:8]],
        "subtotal": subtotal,
        "issue_summary": (
            f"readability 维度未达标（{subtotal}/{MAX_READABILITY}，阈值 {DIMENSION_THRESHOLDS['readability']}），"
            f"问题字段：{'、'.join(blocking_fields)}"
            if subtotal < DIMENSION_THRESHOLDS["readability"] and blocking_fields
            else ""
        ),
    }


def calculate_scores(
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    preprocessed_data: Any,
    intent_graph: Optional[Dict[str, Any]] = None,
    risk_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """主入口，返回完整 scoring_detail 结构。"""
    decision_trace = generated_copy.get("decision_trace") or {}
    keyword_assignments = _extract_keyword_assignments(decision_trace, preprocessed_data)
    audit_trail = generated_copy.get("audit_trail", [])
    a10 = _score_a10(keyword_assignments, audit_trail)

    bullet_trace = decision_trace.get("bullet_trace") or []
    search_trace = decision_trace.get("search_terms_trace") or _search_trace_fallback(generated_copy)
    cosmo = _score_cosmo(generated_copy, bullet_trace, intent_graph, writing_policy, audit_trail)

    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    rufus = _score_rufus(generated_copy, bullet_trace, capability_constraints, search_trace)
    readability = _score_readability(generated_copy)
    metadata = generated_copy.get("metadata", {}) or {}
    production_readiness = _score_production_readiness(metadata)
    ai_os_readiness = _score_ai_os_readiness(generated_copy, writing_policy or {})
    risk_report = risk_report or {}
    legacy_listing_status = (risk_report.get("listing_status") or {}).get("status", "")
    blocking_reasons = (risk_report.get("listing_status") or {}).get("blocking_reasons", [])

    attribute_data = getattr(
        getattr(preprocessed_data, "attribute_data", None), "data", {}
    ) if preprocessed_data else {}
    price_median, current_price, price_note = _price_stats(preprocessed_data, attribute_data)
    price_score, price_available, price_detail_note = _score_price(price_median, current_price)

    max_total = MAX_A10 + MAX_COSMO + MAX_RUFUS + MAX_READABILITY
    raw_total_score = a10["subtotal"] + cosmo["subtotal"] + rufus["subtotal"] + readability["subtotal"]
    if price_available:
        max_total += MAX_PRICE
        raw_total_score += price_score

    total_score = max(0, raw_total_score - production_readiness["penalty"])
    if legacy_listing_status == NOT_READY_FOR_LISTING:
        total_score = max(0, total_score - 20)

    percent = (total_score / max_total) * 100 if max_total else 0
    if percent >= 90:
        rating = "优秀"
    elif percent >= 70:
        rating = "良好"
    else:
        rating = "待优化"

    rating_gate_reason = ""
    if production_readiness["generation_status"] == "offline":
        rating = "待优化"
        rating_gate_reason = "generation_status=offline，正式上架评分不可判为优秀/良好"
    elif legacy_listing_status == NOT_READY_FOR_LISTING:
        rating = "待优化"
        rating_gate_reason = "listing_status=NOT_READY_FOR_LISTING，存在阻断问题"
    elif production_readiness["generation_status"] == "live_with_fallback" and rating == "优秀":
        rating = "良好"
        rating_gate_reason = "存在 live fallback，优秀评级自动降为良好"

    boundary_check = _boundary_check_from_trace(bullet_trace)
    aplus_check = _aplus_check(generated_copy.get("aplus_content", ""))

    dimensions = {
        "traffic": {
            "label": "A10",
            "score": a10["subtotal"],
            "max": MAX_A10,
            "threshold": DIMENSION_THRESHOLDS["traffic"],
            "status": "pass" if a10["subtotal"] >= DIMENSION_THRESHOLDS["traffic"] else "fail",
            "breakdown": {k: v for k, v in a10.items() if k != "subtotal"},
        },
        "content": {
            "label": "COSMO",
            "score": cosmo["subtotal"],
            "max": MAX_COSMO,
            "threshold": DIMENSION_THRESHOLDS["content"],
            "status": "pass" if cosmo["subtotal"] >= DIMENSION_THRESHOLDS["content"] else "fail",
            "breakdown": {k: v for k, v in cosmo.items() if k not in {"subtotal"}},
        },
        "conversion": {
            "label": "Rufus",
            "score": rufus["subtotal"],
            "max": MAX_RUFUS,
            "threshold": DIMENSION_THRESHOLDS["conversion"],
            "status": "pass" if rufus["subtotal"] >= DIMENSION_THRESHOLDS["conversion"] else "fail",
            "breakdown": {k: v for k, v in rufus.items() if k not in {"subtotal"}},
        },
        "readability": readability,
    }
    listing_status, blocking_dimensions = determine_listing_status(dimensions)
    action_required = build_action_required(blocking_dimensions)
    review_queue = build_review_queue(blocking_dimensions)

    result = {
        "a10": a10,
        "cosmo": cosmo,
        "rufus": rufus,
        "readability": readability,
        "dimensions": dimensions,
        "price_competitiveness": {
            "price_median": price_median,
            "current_price": current_price,
            "max": MAX_PRICE if price_available else 0,
            "score": price_score if price_available else None,
            "range": price_note,
            "data_available": price_available,
            "note": price_detail_note,
        },
        "production_readiness": production_readiness,
        "ai_os_readiness": ai_os_readiness,
        "listing_status": listing_status or ("READY_FOR_LISTING" if is_live_success_status(production_readiness["generation_status"]) else ""),
        "blocking_dimensions": blocking_dimensions,
        "action_required": action_required,
        "review_queue": review_queue,
        "blocking_reasons": blocking_reasons,
        "raw_total_score": raw_total_score,
        "total_score": total_score,
        "total_max": max_total,
        "max_total": max_total,
        "grade_percent": round(percent, 1),
        "rating": rating,
        "rating_gate_reason": rating_gate_reason,
        "boundary_declaration_check": boundary_check,
        "aplus_word_count_check": aplus_check,
        "scoring_detail_version": "v10.0.0-dimensions",
        "_deprecated": "total_score 将在下一版本移除，请使用 dimensions",
        "keyword_assignment_sample": keyword_assignments[:12],
    }
    result.update(
        {
            "a10_score": a10["subtotal"],
            "cosmo_score": cosmo["subtotal"],
            "rufus_score": rufus["subtotal"],
            "readability_score": readability["subtotal"],
            "price_competitiveness_score": price_score if price_available else None,
            "ai_os_score": ai_os_readiness["subtotal"],
            "ai_os_grade": ai_os_readiness["grade"],
            "grade": rating,
        }
    )
    return result


__all__ = ["calculate_scores"]
