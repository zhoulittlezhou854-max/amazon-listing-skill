#!/usr/bin/env python3
"""
Node 3.5 - 意图转译引擎 (PRD v8.2)
强制使用 ENGLISH 输出 Intent Graph / STAG 结构

输入: reserve_keywords, 数据诊断信息
输出: 纯英文 Intent Graph / STAG，供后续 Node 0 / Node 4 使用
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from modules.language_utils import canonicalize_capability, english_capability_label
from modules.intent_weights import apply_intent_weight_to_intent_graph
from modules.keyword_utils import infer_category_type


@dataclass
class IntentNode:
    spec: str
    pain_point: str
    scene: str
    audience: str
    resolution: str = ""
    capability: str = ""
    buying_trigger: str = ""
    proof_angle: str = ""
    supporting_keywords: List[str] = field(default_factory=list)
    mini_brief: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec": self.spec,
            "pain_point": self.pain_point,
            "scene": self.scene,
            "audience": self.audience,
            "resolution": self.resolution,
            "capability": self.capability,
            "buying_trigger": self.buying_trigger,
            "proof_angle": self.proof_angle,
            "supporting_keywords": list(self.supporting_keywords),
            "mini_brief": self.mini_brief,
        }


# 场景标签映射 (多语言 -> 英文标准化)
SCENE_LABEL_MAP = {
    # 中文场景
    "骑行记录": "cycling_recording",
    "水下探索": "underwater_exploration",
    "旅行记录": "travel_documentation",
    "家庭使用": "family_use",
    "户外运动": "outdoor_sports",
    "通勤记录": "commuting_capture",
    "工作记录": "service_interaction",
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
    "commuting_capture": "commuting_capture",
    "service_interaction": "service_interaction",
}

SCENE_BRIEF_TEMPLATES = {
    "cycling_recording": "A {audience} weaving through wind-streaked city bike lanes, chest mount locked in as {pain_point} fades behind rock-solid footage.",
    "underwater_exploration": "A {audience} gliding past coral walls with the housing sealed tight, zero fear that {pain_point} will ruin the dive.",
    "travel_documentation": "A {audience} chasing sunrise-to-sunset landscapes, swapping spots without panic that {pain_point}.",
    "family_use": "An {audience} sprinting after kids and pets in the park, magnets snapping on so {pain_point} never interrupts playtime memories.",
    "outdoor_sports": "A {audience} carving mountain switchbacks, camera anchored while {pain_point} stays under control.",
    "commuting_capture": "A {audience} weaving through crowded commutes with a clip-on camera, staying hands-free while {pain_point} no longer breaks the moment.",
    "service_interaction": "A {audience} moving through real work shifts with discreet POV capture, relying on honest fit and battery proof instead of hype.",
    "general_use": "A {audience} documenting everyday adventures with confidence that {pain_point} is solved."
}


def _build_mini_brief(scene: str, audience: str, pain_point: str) -> str:
    template = SCENE_BRIEF_TEMPLATES.get(scene, SCENE_BRIEF_TEMPLATES["general_use"])
    return template.format(audience=audience, pain_point=pain_point)


INTENT_GRAPH_LIBRARY: Dict[str, List[Dict[str, str]]] = {
    "action_camera": [
        {
            "spec": "4k recording",
            "pain_point": "blurry motion ruins POV footage",
            "scene": "cycling_recording",
            "audience": "Urban vloggers",
            "resolution": "Capture 4K/60 clarity even on rough terrain",
            "capability": "4k recording",
            "supporting_keywords": ["4k", "hdr", "eis"],
            "mini_brief": "A food delivery rider weaving through rain-soaked streets, camera pinned to their jacket so every droplet stays steady in 4K.",
        },
        {
            "spec": "30m waterproof",
            "pain_point": "fear of water damage during dives",
            "scene": "underwater_exploration",
            "audience": "Recreational divers",
            "resolution": "IP68 housing keeps electronics safe down to 30 m",
            "capability": "waterproof",
            "supporting_keywords": ["waterproof", "ip68", "dive housing"],
            "mini_brief": "A recreational diver slipping beneath the surface, housing latched tight as schools of fish swirl without a single leak risk.",
        },
        {
            "spec": "150min runtime",
            "pain_point": "batteries dying mid expedition",
            "scene": "travel_documentation",
            "audience": "Adventure travelers",
            "resolution": "150-minute battery handles sunrise-to-sunset shoots",
            "capability": "long battery life",
            "supporting_keywords": ["150min", "dual battery", "usb-c"],
            "mini_brief": "A backpacker hopping trains from dawn to dusk, battery indicator hardly budging while every panorama stays live.",
        },
        {
            "spec": "multi-mount kit",
            "pain_point": "cameras not adapting to helmets or chest rigs",
            "scene": "family_use",
            "audience": "Active families",
            "resolution": "Magnetic and strap mounts keep POV steady anywhere",
            "capability": "versatile mounting",
            "supporting_keywords": ["magnetic clip", "helmet mount", "chest strap"],
            "mini_brief": "Parents chasing scooter races around the driveway, snapping on magnets and straps so every squeal stays centered.",
        },
    ],
    "wearable_body_camera": [
        {
            "spec": "long battery life",
            "pain_point": "short runtime cuts hands-free clips mid day",
            "scene": "commuting_capture",
            "audience": "Commuters and delivery riders",
            "resolution": "Up to 150 minutes of practical clip-on capture",
            "capability": "long battery life",
            "buying_trigger": "Wants one small camera that lasts through real errands and commutes",
            "proof_angle": "Battery minutes + lightweight body make the promise believable",
            "supporting_keywords": ["body camera", "thumb camera", "wearable camera"],
            "mini_brief": "A rider clips the camera on before a long shift, trusting it to keep rolling through crowded streets without bulky gear.",
        },
        {
            "spec": "versatile mounting",
            "pain_point": "bulky mounts slow down quick daily recording",
            "scene": "service_interaction",
            "audience": "Service staff and field workers",
            "resolution": "Magnetic and clip-on setup keeps capture quick and practical",
            "capability": "versatile mounting",
            "buying_trigger": "Needs hands-free POV without chest rigs or setup friction",
            "proof_angle": "Clip, magnetic mount, and rotating lens show real usability",
            "supporting_keywords": ["clip on camera", "magnetic back clip", "body cam"],
            "mini_brief": "A worker clips the camera on between customer stops, switching angles in seconds instead of wrestling with mounts.",
        },
        {
            "spec": "wifi connection",
            "pain_point": "slow file transfer kills the urge to share or review clips",
            "scene": "vlog_content_creation",
            "audience": "Daily vlog creators",
            "resolution": "Fast preview and transfer keep short clips moving",
            "capability": "wifi connection",
            "buying_trigger": "Wants fast review and easy posting after casual shoots",
            "proof_angle": "Phone preview and transfer explain why the camera fits daily content flow",
            "supporting_keywords": ["vlogging camera", "travel camera", "pov camera"],
            "mini_brief": "A creator flips from selfie to street shot, checks framing on the phone, and keeps moving before the moment fades.",
        },
    ],
}


def _normalize_scene_label(scene: str) -> str:
    """将任意语言场景名归一化为英文标签"""
    return SCENE_LABEL_MAP.get(scene, scene.lower().replace(" ", "_"))


def _select_keywords_for_intent(arsenal: Optional[Dict[str, Any]], preprocessed_data: Any) -> List[Dict[str, Any]]:
    """从军火库或预处理数据中提取关键词"""
    feedback_context = getattr(preprocessed_data, "feedback_context", {}) or {}
    feedback_sp = []
    for row in feedback_context.get("sp_intent", []) or []:
        keyword = str((row or {}).get("keyword") or "").strip()
        if not keyword:
            continue
        feedback_sp.append(
            {
                "keyword": keyword,
                "search_volume": float((row or {}).get("search_volume") or 0),
                "conversion_rate": float((row or {}).get("conversion") or 0),
                "source_type": "feedback_sp_intent",
            }
        )
    if arsenal and arsenal.get("reserve_keywords"):
        return (feedback_sp + arsenal["reserve_keywords"])[:20]  # 反馈场景词优先

    keywords = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    return (feedback_sp + sorted(keywords, key=lambda x: x.get("search_volume", 0), reverse=True))[:20]


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
    if not found:
        return ["general_recording"]

    canonical = []
    for label in found:
        slug = canonicalize_capability(label)
        canonical.append(english_capability_label(slug))
    return canonical


def _build_stag_groups(keywords: List[Dict[str, Any]], data_mode: str, category_type: str = "action_camera") -> List[Dict[str, Any]]:
    """
    根据关键词构建 STAG (Single Theme Ad Group) 结构
    PRD v8.2: 每个 STAG 代表一个单主题广告组场景
    """
    # 按搜索量排序取前10个关键词
    safe_keywords = keywords or []
    sorted_kw = sorted(safe_keywords, key=lambda x: x.get("search_volume", 0), reverse=True)[:10]

    # 定义场景分组策略 (英文标签)
    if category_type == "wearable_body_camera":
        scene_templates = [
            {
                "id": "stag_1",
                "english_label": "commute_pov_capture",
                "primary_scenarios": ["commuting_capture"],
                "keywords": [],
                "capabilities": ["long_battery_life", "versatile_mounting"],
                "target_persona": "Commuter",
                "campaign_advice": "Lead with hands-free daily capture and battery length"
            },
            {
                "id": "stag_2",
                "english_label": "service_shift_recording",
                "primary_scenarios": ["service_interaction"],
                "keywords": [],
                "capabilities": ["versatile_mounting"],
                "target_persona": "Service Worker",
                "campaign_advice": "Stress clip-on speed, honest fit, and practical POV"
            },
            {
                "id": "stag_3",
                "english_label": "travel_clip_camera",
                "primary_scenarios": ["travel_documentation"],
                "keywords": [],
                "capabilities": ["long_battery_life", "wifi_connectivity"],
                "target_persona": "Traveler",
                "campaign_advice": "Show portability, quick transfer, and everyday carry"
            },
            {
                "id": "stag_4",
                "english_label": "daily_vlog_clip",
                "primary_scenarios": ["vlog_content_creation", "daily_lifelogging"],
                "keywords": [],
                "capabilities": ["wifi_connectivity"],
                "target_persona": "Daily Creator",
                "campaign_advice": "Promote clip-on storytelling and fast phone review"
            },
        ]
    else:
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
    for kw in sorted_kw:
        kw_text = kw.get("keyword") or ""
        kw_lower = kw_text.lower()

        # 根据关键词内容分配 STAG
        target_stag = scene_templates[0]
        if category_type == "wearable_body_camera":
            if any(w in kw_lower for w in ["service", "body cam", "bodycam", "wearable"]):
                target_stag = scene_templates[1] if len(scene_templates) > 1 else scene_templates[0]
            elif any(w in kw_lower for w in ["travel", "trip", "vacation"]):
                target_stag = scene_templates[2] if len(scene_templates) > 2 else scene_templates[0]
            elif any(w in kw_lower for w in ["vlog", "content", "creator", "daily"]):
                target_stag = scene_templates[3] if len(scene_templates) > 3 else scene_templates[0]
        else:
            if any(w in kw_lower for w in ["water", "diving", "underwater", "swim", "surf"]):
                target_stag = scene_templates[1] if len(scene_templates) > 1 else scene_templates[0]
            elif any(w in kw_lower for w in ["travel", "trip", "road", "vacation"]):
                target_stag = scene_templates[2] if len(scene_templates) > 2 else scene_templates[0]
            elif any(w in kw_lower for w in ["family", "daily", "home", "kid", "pet"]):
                target_stag = scene_templates[3] if len(scene_templates) > 3 else scene_templates[0]
            elif any(w in kw_lower for w in ["vlog", "content", "youtube", "creator"]):
                target_stag = scene_templates[4] if len(scene_templates) > 4 else scene_templates[0]

        target_stag["keywords"].append(kw_text or "[SYNTH]_keyword")

    # 如果没有任何真实关键词，至少给默认 STAG 一个占位
    if not sorted_kw:
        scene_templates[0]["keywords"].append("[SYNTH]_action_camera")

    # 如果是 SYNTHETIC_COLD_START，标记合成关键词
    if data_mode == "SYNTHETIC_COLD_START":
        for stag in scene_templates:
            if not stag["keywords"]:
                stag["keywords"] = ["[SYNTH]_" + stag["english_label"]]

    # 只返回有数据的 STAG
    return [s for s in scene_templates if s["keywords"]][:5]


def _build_capability_metadata(
    capabilities: Sequence[str],
    constraints: Dict[str, Any],
    canonical_notes: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """为每个能力生成可见性元信息，供 downstream gating 使用。"""
    metadata: List[Dict[str, Any]] = []
    seen = set()
    canonical_notes = canonical_notes or {}
    for capability in capabilities:
        label = english_capability_label(canonicalize_capability(capability))
        if label in seen:
            continue
        entry = {
            "capability": label,
            "is_supported": True,
            "visibility": "visible",
            "downgrade_reason": "",
        }
        lowered = label.lower()
        if "waterproof" in lowered:
            supported = constraints.get("waterproof_supported", False)
            entry["is_supported"] = supported
            entry["visibility"] = "visible" if supported else "backend_only"
            if not supported:
                entry["downgrade_reason"] = constraints.get("waterproof_note", "Waterproof claim blocked")
        if "stabilization" in lowered:
            supported = constraints.get("stabilization_supported", False)
            entry["is_supported"] = entry["is_supported"] and supported
            if not supported:
                entry["visibility"] = "backend_only"
                entry["downgrade_reason"] = constraints.get("stabilization_note", "Stabilization claim blocked")
        supplemental_notes: List[str] = []
        if "waterproof" in lowered and canonical_notes.get("waterproof"):
            supplemental_notes.extend(canonical_notes["waterproof"])
        if any(token in lowered for token in ["battery", "runtime"]) and canonical_notes.get("runtime"):
            supplemental_notes.extend(canonical_notes["runtime"])
        if any(token in lowered for token in ["accessory", "mount"]) and canonical_notes.get("accessories"):
            supplemental_notes.extend(canonical_notes["accessories"])
        if supplemental_notes:
            entry["supplement_notes"] = supplemental_notes
        metadata.append(entry)
        seen.add(label)
    return metadata


def enrich_policy_with_intent_graph(policy: Dict[str, Any], specs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a concrete Spec -> Pain Point -> Scene -> Audience graph for downstream payloads.
    """
    specs = specs or {}
    nodes: List[IntentNode] = []
    default_scene = (policy.get("scene_priority") or ["general_use"])[0]
    default_audience = policy.get("product_profile", {}).get("target_audience_role", "general_audience")
    category = policy.get("product_profile", {}).get("category_type", "action_camera")
    templates = INTENT_GRAPH_LIBRARY.get(category, [])
    seen_specs = set()

    for preset in templates:
        spec_key = preset.get("spec", "").lower()
        if not spec_key:
            continue
        seen_specs.add(spec_key)
        resolved_value = (
            specs.get(spec_key)
            or specs.get(spec_key.replace(" ", "_"))
            or preset.get("resolution", "")
        )
        mini_brief = preset.get("mini_brief") or _build_mini_brief(
            _normalize_scene_label(preset.get("scene") or default_scene),
            preset.get("audience") or default_audience,
            preset.get("pain_point", "unmet need"),
        )
        node = IntentNode(
            spec=preset["spec"],
            pain_point=preset.get("pain_point", "unmet need"),
            scene=_normalize_scene_label(preset.get("scene") or default_scene),
            audience=preset.get("audience") or default_audience,
            resolution=str(resolved_value or preset.get("resolution", "")),
            capability=english_capability_label(
                canonicalize_capability(preset.get("capability") or preset["spec"])
            ),
            buying_trigger=preset.get("buying_trigger", "Wants reliable proof before checkout"),
            proof_angle=preset.get("proof_angle", "Verified spec + scene-fit benefit"),
            supporting_keywords=preset.get("supporting_keywords", []),
            mini_brief=mini_brief,
        )
        nodes.append(node)

    for spec_name, spec_value in specs.items():
        spec_key = str(spec_name).lower()
        if spec_key in seen_specs:
            continue
        normalized_scene = _normalize_scene_label(default_scene)
        node = IntentNode(
            spec=str(spec_name),
            pain_point="general performance concern",
            scene=normalized_scene,
            audience=str(default_audience),
            resolution=str(spec_value),
            capability=english_capability_label(canonicalize_capability(spec_name)),
            buying_trigger="Needs confidence that the product solves the key use case",
            proof_angle="Lead with the verified spec and concrete usage context",
            mini_brief=_build_mini_brief(normalized_scene, str(default_audience), "general performance concern"),
        )
        nodes.append(node)

    enriched_policy = dict(policy)
    enriched_policy["intent_graph"] = [node.to_dict() for node in nodes]
    return enriched_policy


def _build_scene_metadata(
    scenes: Sequence[str],
    capability_metadata: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """根据能力可见性推断场景是否允许在可视字段中呈现。"""
    metadata: List[Dict[str, Any]] = []
    seen = set()
    cap_lookup = {entry["capability"].lower(): entry for entry in capability_metadata}

    for scene in scenes:
        normalized = _normalize_scene_label(scene)
        if normalized in seen:
            continue
        entry = {
            "scene": normalized,
            "is_supported": True,
            "visibility": "visible",
            "downgrade_reason": "",
        }
        if normalized == "underwater_exploration":
            water_meta = next(
                (meta for key, meta in cap_lookup.items() if "waterproof" in key),
                None,
            )
            if water_meta and not water_meta["is_supported"]:
                entry["is_supported"] = False
                entry["visibility"] = "removed"
                entry["downgrade_reason"] = water_meta.get("downgrade_reason", "Waterproof disabled")
        metadata.append(entry)
        seen.add(normalized)
    return metadata


def _build_intent_graph(
    keywords: List[Dict[str, Any]], preprocessed_data: Any, data_mode: str
) -> Tuple[List[Dict[str, Any]], List[str]]:
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
            "buying_trigger": "needs confidence that footage stays stable and shareable",
            "proof_angle": "verified runtime, stabilization, and mounting proof",
            # PRD v8.2 SYNTH 标记
            "is_synthetic": data_mode == "SYNTHETIC_COLD_START" and idx >= 5
        }
        intents.append(intent)

    return intents, capabilities


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
    canonical_caps = getattr(preprocessed_data, "canonical_core_selling_points", []) or []
    canonical_notes = getattr(preprocessed_data, "canonical_capability_notes", {}) or {}

    category_type = infer_category_type(preprocessed_data)

    # 选择关键词
    keywords = _select_keywords_for_intent(arsenal_output, preprocessed_data)

    # 构建 Intent Graph (纯英文)
    intent_graph, inferred_capabilities = _build_intent_graph(keywords, preprocessed_data, data_mode)

    # 构建 STAG Groups (纯英文)
    stag_groups = _build_stag_groups(keywords, data_mode, category_type=category_type)

    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    if canonical_caps:
        inferred_capabilities.extend(canonical_caps)
    capability_meta = _build_capability_metadata(inferred_capabilities, constraints, canonical_notes)
    scene_candidates: List[str] = []
    for intent in intent_graph:
        scene_candidates.extend(intent.get("usage_scenarios", []))
    for stag in stag_groups:
        scene_candidates.extend(stag.get("primary_scenarios", []))
    scene_meta = _build_scene_metadata(scene_candidates, capability_meta)

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
            "category_type": category_type,
            "has_synthetic": any(i.get("is_synthetic", False) for i in intent_graph)
        },
        "capability_metadata": capability_meta,
        "scene_metadata": scene_meta,
    }

    result = apply_intent_weight_to_intent_graph(
        result,
        getattr(preprocessed_data, "intent_weight_snapshot", {}) or {},
    )

    return result


def write_visual_briefs_to_intent_graph(policy: Dict[str, Any], visual_briefs: Sequence[Dict[str, Any]]) -> None:
    """
    Persist structured visual briefs alongside the intent_graph for multimodal loops.
    """
    if not policy or not visual_briefs:
        return
    policy.setdefault("visual_briefs", [])
    policy["visual_briefs"].extend(visual_briefs)
    intent_graph = policy.get("intent_graph")
    if not intent_graph:
        return
    for node in intent_graph:
        bucket = node.setdefault("visual_briefs", [])
        bucket.extend(visual_briefs)


__all__ = ["generate_intent_graph", "write_visual_briefs_to_intent_graph"]
