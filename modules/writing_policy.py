#!/usr/bin/env python3
"""
writing_policy 生成模块 (Step 5)
版本: v1.0
功能: 生成文案写作策略，包括场景优先级、能力场景绑定等
"""

import csv
import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

from modules.keyword_utils import extract_tiered_keywords, build_keyword_slots, infer_category_type
from modules.language_utils import (
    canonicalize_capability,
    english_capability_label,
    get_capability_display,
    get_scene_display,
)
from modules.intent_translator import enrich_policy_with_intent_graph
from modules.retention_guard import build_retention_strategy
from modules.intent_weights import apply_intent_weight_overrides
from modules.market_packs import apply_market_pack, load_market_pack
from modules.question_bank import build_question_bank_context


@dataclass
class PreprocessedData:
    """预处理数据类（简化版）"""
    run_config: Any
    attribute_data: Any
    keyword_data: Any
    review_data: Any
    aba_data: Any
    core_selling_points: List[str]
    accessory_descriptions: List[Dict[str, Any]]
    quality_score: int
    language: str
    processed_at: str
    canonical_core_selling_points: List[str] = field(default_factory=list)
    canonical_accessory_descriptions: List[Dict[str, Any]] = field(default_factory=list)
    canonical_capability_notes: Dict[str, Any] = field(default_factory=dict)
    real_vocab: Any = None
    target_country: str = ""
    capability_constraints: Dict[str, Any] = field(default_factory=dict)
    keyword_metadata: List[Dict[str, Any]] = field(default_factory=list)
    raw_human_insights: str = ""


# 运动相机常见场景 (English internal labels)
ACTION_CAMERA_SCENES = [
    "outdoor_sports", "cycling_recording", "underwater_exploration", "travel_documentation", "family_use",
    "skiing", "hiking_trekking", "road_trip", "pet_photography", "vlog_content_creation",
    "sports_training", "sports_event_recording", "wilderness_exploration", "extreme_sports", "daily_lifelogging"
]

WEARABLE_BODY_CAMERA_SCENES = [
    "commuting_capture", "vlog_content_creation", "travel_documentation", "daily_lifelogging", "service_interaction"
]

# 能力与场景的默认绑定关系 (English scene labels internally)
DEFAULT_CAPABILITY_SCENE_BINDINGS = {
    "4k recording": ["outdoor_sports", "underwater_exploration", "travel_documentation", "sports_event_recording"],
    "stabilization": ["cycling_recording", "skiing", "hiking_trekking", "sports_training"],
    "waterproof": ["underwater_exploration", "rainy_use", "swimming", "surfing"],
    "wifi connection": ["family_use", "vlog_content_creation", "daily_lifelogging", "pet_photography"],
    "dual screen": ["selfie_vlog", "family_use", "travel_documentation", "pet_photography"],
    "long battery life": ["outdoor_sports", "hiking_trekking", "road_trip", "wilderness_exploration"],
    "voice control": ["sports_training", "cycling_recording", "skiing", "extreme_sports"],
    "live streaming": ["sports_event_recording", "vlog_content_creation", "outdoor_sports", "travel_documentation"]
}

SCENE_ALIAS_PATTERNS = [
    (re.compile(r"(?:骑行|bik(?:e|ing)|velo|v[ée]lo|fahrrad|cycling|helmet|helm|motorrad|moto)", re.IGNORECASE), "cycling_recording"),
    (re.compile(r"(?:水下|潜水|plong|underwater|snork|tauch|unterwasser|swim|surf)", re.IGNORECASE), "underwater_exploration"),
    (re.compile(r"(?:旅行|旅游|travel|trip|voyage|reise|urlaub|vacation|road trip)", re.IGNORECASE), "travel_documentation"),
    (re.compile(r"(?:家庭|family|famille|familie|kids?|child|parent)", re.IGNORECASE), "family_use"),
    (re.compile(r"(?:vlog|creator|content|youtube|selfie)", re.IGNORECASE), "vlog_content_creation"),
    (re.compile(r"(?:sport|训练|entraînement|training|workout|outdoor)", re.IGNORECASE), "sports_training"),
    (re.compile(r"(?:body\s?cam|bodycam|body camera|wearable|thumb camera|clip(?:-|\s)?on|hands[\s-]?free|neck strap|back clip|commut(?:e|ing)|travel camera)", re.IGNORECASE), "commuting_capture"),
    (re.compile(r"(?:service|patrol|security|interaction|shift|delivery rider)", re.IGNORECASE), "service_interaction"),
]

_BENCHMARK_MIN_LENGTH = 80
_BENCHMARK_MAX_LENGTH = 280
_BENCHMARK_NUMERIC_PATTERN = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*"
    r"(?:gb|mb|tb|oz|g|kg|lbs?|hours?|hrs?|mins?|minutes?|seconds?|secs?|"
    r"fps|mm|cm|m|ft|[kmg]?hz|mah|mw|x|°)\b"
    r"|"
    r"\b\d+(?:\.\d+)?[kK]\b"
    r"|"
    r"\b\d+(?:\.\d+)?[pP]\b"
    r"|"
    r"\b\d+\s*-\s*\d+\b"
    r"|"
    r"\b\d+(?:\.\d+)?°)",
    re.IGNORECASE,
)
_BENCHMARK_HARD_BLOCK_WORDS = {
    "best",
    "#1",
    "guaranteed",
    "unbeatable",
    "number one",
}
_BENCHMARK_SOFT_PENALTY_WORDS = {
    "perfect",
    "ultimate",
    "revolutionary",
}
_BENCHMARK_VERB_PATTERN = re.compile(
    r"\b(?:capture|captures|record|records|film|films|shoot|shoots|stream|streams|document|documents|mount|mounts|wear|wears|clip|clips|track|tracks|share|shares|create|creates|"
    r"stabilize|deliver|feature|features|include|includes|offer|offers|provide|provides|"
    r"support|supports|enable|enables|allow|allows|let|lets|keep|keeps|lock|locks|"
    r"\w+ing|\w+ed)\b",
    re.IGNORECASE,
)


def _get_category_default_benchmarks() -> List[str]:
    return [
        (
            "Capture Every Detail — 4K UHD at 30fps records crisp footage even in fast-motion scenes, "
            "so your highlight reel looks ready to share straight from the camera."
        ),
        (
            "All-Day Power, Featherlight Build — At just 35g with a 150-minute battery, clip it to your "
            "chest or helmet and forget it's there until the ride is done."
        ),
        (
            "Instant Stabilization — Electronic image stabilization smooths out road vibration and sudden "
            "movements, delivering steady POV shots without a separate gimbal."
        ),
    ]


def _normalize_benchmark_prefix(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "").strip().lower())
    compact = compact.replace("—", "-")
    return compact[:50]


def _benchmark_candidate_paths(preprocessed_data: Any) -> List[Path]:
    candidates: List[Path] = []
    run_config = getattr(preprocessed_data, "run_config", None)
    input_files = getattr(run_config, "input_files", {}) or {}
    review_table = (
        getattr(run_config, "review_table", None)
        or input_files.get("review_table")
        or input_files.get("multi_dimension_table")
    ) if run_config else None
    if review_table:
        candidates.append(Path(review_table))
    multi_dimension_table = input_files.get("multi_dimension_table") if run_config else None
    if multi_dimension_table:
        candidates.append(Path(multi_dimension_table))
    product_id = getattr(run_config, "product_id", None) if run_config else None
    market = getattr(run_config, "market", None) or getattr(run_config, "target_country", None) or "US"
    if product_id:
        candidates.append(Path(f"config/products/{product_id}_{market}/{product_id}产品全维度表.csv"))
    ingestion_audit = getattr(preprocessed_data, "ingestion_audit", {}) or {}
    table_meta = ingestion_audit.get("multi_dimension_table") or {}
    if isinstance(table_meta, dict) and table_meta.get("path"):
        candidates.append(Path(str(table_meta.get("path"))))
    deduped: List[Path] = []
    seen = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(candidate)
    return deduped


def _benchmark_source_rank(row: Dict[str, Any]) -> tuple:
    role = str(row.get("ASIN_Role", "") or "").lower()
    if "exact" in role:
        role_rank = 0
    elif "similar" in role:
        role_rank = 1
    else:
        role_rank = 2
    bsr_raw = row.get("bsr_rank", row.get("BSR_Rank", "999999")) or "999999"
    try:
        bsr_rank = int(float(str(bsr_raw).strip()))
    except Exception:
        bsr_rank = 999999
    review_raw = row.get("review_count", row.get("Review_Count", "0")) or "0"
    try:
        review_count = int(float(str(review_raw).strip()))
    except Exception:
        review_count = 0
    return (role_rank, bsr_rank, -review_count)


def _bullet_has_action_opener(text: str) -> bool:
    raw_text = " ".join(str(text or "").split())
    if not raw_text:
        return False
    header, separator, body = raw_text.partition("—")
    if not separator:
        header, separator, body = raw_text.partition(":")
    segments = []
    if header:
        segments.append(" ".join(header.split()[:10]))
    if body:
        segments.append(" ".join(body.split()[:10]))
    if not segments:
        segments = [" ".join(raw_text.split()[:10])]
    return any(_BENCHMARK_VERB_PATTERN.search(segment) for segment in segments)


def _is_high_quality_bullet(text: str, bsr_rank: int = 999999) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return False
    if not _BENCHMARK_MIN_LENGTH <= len(normalized) <= _BENCHMARK_MAX_LENGTH:
        return False
    lowered = normalized.lower()
    if any(word in lowered for word in _BENCHMARK_HARD_BLOCK_WORDS):
        return False
    has_soft_penalty = any(word in lowered for word in _BENCHMARK_SOFT_PENALTY_WORDS)
    if has_soft_penalty and bsr_rank > 500:
        return False
    if not _BENCHMARK_NUMERIC_PATTERN.search(lowered):
        return False
    if not _bullet_has_action_opener(normalized):
        return False
    return True


def _extract_benchmark_bullets(preprocessed_data: Any) -> List[str]:
    candidates: List[Dict[str, Any]] = []
    for path in _benchmark_candidate_paths(preprocessed_data):
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    data_type = str(row.get("Data_Type", "") or "").lower()
                    field_name = str(row.get("Field_Name", "") or "").lower()
                    content = " ".join(str(row.get("Content_Text", "") or "").split())
                    source_rank = _benchmark_source_rank(row)
                    if "listing" not in data_type:
                        continue
                    if not field_name.startswith("bullet"):
                        continue
                    if not _is_high_quality_bullet(content, bsr_rank=source_rank[1]):
                        continue
                    candidates.append(
                        {
                            "text": content,
                            "source_rank": source_rank,
                        }
                    )
        except Exception:
            continue
    candidates.sort(key=lambda item: item["source_rank"])
    seen = set()
    result: List[str] = []
    for item in candidates:
        text = item["text"]
        key = _normalize_benchmark_prefix(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= 5:
            break
    return result or _get_category_default_benchmarks()


def _default_scenes_for_category(category_type: str) -> List[str]:
    if category_type == "wearable_body_camera":
        return WEARABLE_BODY_CAMERA_SCENES[:]
    return ACTION_CAMERA_SCENES[:]


def _infer_policy_category_type(preprocessed_data: Any) -> str:
    category_type = infer_category_type(preprocessed_data)
    return category_type or "action_camera"


def _build_product_profile(
    preprocessed_data: Any,
    language: str,
    prioritized_scenes: List[str],
    core_selling_points: List[str],
) -> Dict[str, Any]:
    category_type = _infer_policy_category_type(preprocessed_data)
    hero_spec = core_selling_points[0] if core_selling_points else (
        "hands_free_recording" if category_type == "wearable_body_camera" else "4K_recording"
    )
    if category_type == "wearable_body_camera":
        return {
            "profile_version": "v8.2",
            "reasoning_language": "EN",
            "target_language": language,
            "category_type": "wearable_body_camera",
            "physical_form": "clip_on_thumb_camera",
            "hero_spec": hero_spec,
            "value_proposition": "Lightweight clip-on POV camera for hands-free daily capture and travel moments",
            "primary_use_cases": prioritized_scenes[:4] or WEARABLE_BODY_CAMERA_SCENES[:4],
            "target_audience_role": "Commuter / Daily Vlogger / Traveler / Service Worker",
            "pain_points": [
                "bulky cameras interrupt movement",
                "awkward mounts slow down recording",
                "short battery life cuts clips early",
            ],
            "competitive_edge": "Clip-on portability with honest everyday-fit guidance and quick POV switching",
            "taboo_concepts": ["spy_use", "surveillance_claim", "tactical_equipment", "weapon_context"],
            "tone_hint": _get_tone_hint(language),
        }

    return {
        "profile_version": "v8.2",
        "reasoning_language": "EN",
        "target_language": language,
        "category_type": "action_camera",
        "physical_form": "compact_wearable_camera",
        "hero_spec": hero_spec,
        "value_proposition": f"High-performance {hero_spec} designed for outdoor and sports use",
        "primary_use_cases": prioritized_scenes[:4] or ACTION_CAMERA_SCENES[:4],
        "target_audience_role": "Outdoor Enthusiast / Sports User / Content Creator",
        "pain_points": ["unstable footage", "limited waterproofing", "short battery life"],
        "competitive_edge": "Multi-scenario coverage with key capabilities",
        "taboo_concepts": ["military_use", "tactical_equipment", "weapon_context"],
        "tone_hint": _get_tone_hint(language),
    }

# 需要限制的能力（只能在FAQ中提及）
FAQ_ONLY_CAPABILITIES = [
    "Digital stabilization limitation",
    "Waterproof depth limitation",
    "Battery replacement guidance",
    "Compatibility limitation",
    "Warranty terms detail",
]

LENGTH_RULES = {
    "title": {
        "target_min": 160,
        "target_max": 190,
        "hard_ceiling": 200,
        "soft_warning": 150,
    },
    "bullet": {
        "target_min": 200,
        "target_max": 250,
        "hard_ceiling": 500,
        "seo_byte_limit": 1000,
    },
}


def get_length_rule(field: str) -> Dict[str, int]:
    return dict(LENGTH_RULES.get(field, {}))


# 4场景默认策略模板 (English internal labels)
DEFAULT_4SCENE_POLICY = {
    "scene_priority": ["cycling_recording", "underwater_exploration", "travel_documentation", "family_use"],
    "keyword_allocation_strategy": "balanced",
    "title_keyword_slots": {
        "slot_1_brand": True,
        "slot_2_l1": True,
        "slot_3_scene_1": True,
        "slot_4_capability": True,
        "slot_5_scene_2": True,
        "max_title_length": LENGTH_RULES["title"]["hard_ceiling"]
    },
    "bullet_keyword_plan": {
        "B1": {"primary": "L1", "secondary": "scene_1", "focus": "primary_scene"},
        "B2": {"primary": "L1/L2", "secondary": "scene_2", "focus": "core_capability"},
        "B3": {"primary": "L2", "secondary": "scene_3", "focus": "differentiation"},
        "B4": {"primary": "L3", "secondary": "scene_4", "focus": "boundary_statement"},
        "B5": {"primary": "none", "secondary": "warranty", "focus": "after_sales"}
    },
    "search_terms_plan": {
        "priority_tiers": ["L3"],
        "max_terms": 10,
        "avoid_duplication_with_title": True
    }
}

# 禁止的能力组合 (English)
DEFAULT_FORBIDDEN_PAIRS = [
    ["5K recording", "stabilization"],
    ["8K recording", "live streaming"],
    ["waterproof", "charging"],
    ["extreme temperature", "extended use"],
]

TITLE_SLOT_BLUEPRINT = [
    {
        "slot": "brand",
        "required": True,
        "responsibility": "Official seller brand or line",
        "source_priority": ["run_config.brand", "attribute.brand_name"],
        "notes": "No promo adjectives or ™ symbols."
    },
    {
        "slot": "l1_keyword",
        "required": True,
        "responsibility": "Primary L1 keyword (High-Conv or High-Traffic)",
        "source_priority": ["keyword_arsenal.l1", "order_winning.top_conversion"],
        "notes": "Appear within front 70 chars."
    },
    {
        "slot": "scene",
        "scene_index": 0,
        "required": True,
        "responsibility": "Primary scene/persona label",
        "source_priority": ["intent_graph.scenes", "review.persona"],
        "notes": "Localized noun (e.g., commuting security, vlog)."
    },
    {
        "slot": "hero_capability",
        "required": True,
        "responsibility": "Quantified capability (runtime/resolution/mount)",
        "source_priority": ["attribute.hero_spec", "supplement.numeric_proof"],
        "notes": "Only facts supported by verified specs."
    },
    {
        "slot": "scene",
        "scene_index": 1,
        "required": False,
        "responsibility": "Secondary scene or persona",
        "source_priority": ["intent_graph.scenes", "aba.scene_terms"],
        "notes": "Optional; only populate when scene coverage available."
    },
    {
        "slot": "spec_pack",
        "required": False,
        "responsibility": "Spec roll-up (runtime, waterproof depth, stabilization modes)",
        "source_priority": ["compliance_directives", "attribute.verified_specs"],
        "notes": "Comma-separated; avoid duplicate metrics already surfaced earlier."
    }
]

FIELD_ROLE_SUMMARY = {
    "title": {
        "requirements": [
            "Target 160-190 characters, hard ceiling 200 characters, brand + L1 + hero scene within front 70 chars",
            "Include one quantified spec (minutes, 4K, depth) only if verified",
            "No promo words, competitor names, or duplicate nouns"
        ],
        "keyword_routing": {
            "L1": "brand + l1 slot",
            "L2": "only if extends persona (scene slot)",
            "L3": "never visible; route to Search Terms"
        }
    },
    "bullets": {
        "format": "Each bullet uses HEADER — body, target 200-250 chars, hard ceiling 500 chars, EM DASH separator",
        "responsibilities": {
            "B1": "Mount + hero scene (P0)",
            "B2": "Runtime / numeric proof (P0)",
            "B3": "Capability + persona tie (P1)",
            "B4": "Boundary statement + accessory gating (P1)",
            "B5": "After-sales / warranty / compatibility (P2)"
        },
        "compliance_hooks": ["B4 must carry qualifiers for risky claims", "B2/B3 include numeric proof when available"]
    },
    "search_terms": {
        "requirements": [
            "Residual keywords only (L2/L3), ≤site byte cap",
            "Strip duplicates, taboo words, and visible-field repeats",
            "Mark backend-only risky claims for compliance logging"
        ]
    }
}


def _build_copy_contracts(
    language: str,
    keyword_slots: Dict[str, Any],
    bullet_slot_rules: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    title_slot_keywords = keyword_slots.get("title") or []
    bullet_keyword_slots = {
        slot_name: list((keyword_slots.get(f"bullet_{idx}") or {}).get("keywords") or [])
        for idx, slot_name in enumerate(["B1", "B2", "B3", "B4", "B5"], start=1)
    }
    return {
        "bullet_opening": {
            "header_required": True,
            "header_word_range": [3, 5],
            "body_opening_style": "capability_or_action",
            "forbidden_weak_openers": [
                "with", "avec", "mit", "con", "using", "through", "via", "by",
                "avec", "pour", "mit", "mit dem", "con il", "con la",
            ],
            "frontload_window_tokens": 16,
        },
        "scene_capability_numeric_binding": {
            "enabled": True,
            "require_scene_and_capability": True,
            "require_numeric_or_condition_slots": ["B2", "B4", "B5"],
            "condition_markers": ["1080P", "4K", "5K", "EIS", "housing", "case", "WiFi", "30m", "30 m"],
        },
        "keyword_slot_occupancy": {
            "enabled": True,
            "title_anchor_keywords": list(title_slot_keywords[:3]),
            "bullet_keyword_slots": bullet_keyword_slots,
            "top_conversion_slots": ["B1", "B2", "B3"],
            "max_keywords_per_bullet": 2,
        },
        "title_dewater": {
            "enabled": True,
            "weak_connectors": ["with", "avec", "mit", "con"],
            "preserve_exact_phrases": True,
            "frontload_window_chars": 60,
        },
        "description_action_style": {
            "enabled": True,
            "prefer_action_verbs": True,
            "avoid_manual_tone": True,
            "preferred_verb_frames": ["capture", "explore", "film", "share", "ride", "frame"],
        },
        "slot_contracts": bullet_slot_rules,
        "language": language,
    }


def _build_bullet_slot_rules(
    prioritized_scenes: List[str],
    keyword_routing: Dict[str, List[str]],
    retention_strategy: Dict[str, Any],
    preprocessed_data: Any,
) -> Dict[str, Dict[str, Any]]:
    feedback_context = getattr(preprocessed_data, "feedback_context", {}) or {}
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    mode_guidance = constraints.get("recording_mode_guidance", {}) or {}
    preferred_stabilization_mode = mode_guidance.get("preferred_stabilization_mode") or constraints.get("stabilization_best_mode") or ""
    guidance_by_mode = mode_guidance.get("guidance_by_mode", {}) or {}
    motion_mode_contract = {}
    if preferred_stabilization_mode:
        motion_mode_contract = {
            "preferred_mode": preferred_stabilization_mode,
            "best_scenes": (guidance_by_mode.get(preferred_stabilization_mode) or {}).get("scene_focus", []),
            "copy_rule": (guidance_by_mode.get(preferred_stabilization_mode) or {}).get("copy_rule", ""),
        }
    detail_mode_contract = {}
    for detail_mode in ["5K", "4K"]:
        if detail_mode in guidance_by_mode:
            detail_mode_contract = {
                "preferred_mode": detail_mode,
                "best_scenes": (guidance_by_mode.get(detail_mode) or {}).get("scene_focus", []),
                "copy_rule": (guidance_by_mode.get(detail_mode) or {}).get("copy_rule", ""),
                "stabilization_visibility": (guidance_by_mode.get(detail_mode) or {}).get("stabilization_visibility", ""),
            }
            break
    sp_keywords = [
        str((row or {}).get("keyword") or "").strip()
        for row in feedback_context.get("sp_intent", []) or []
        if str((row or {}).get("keyword") or "").strip()
    ]
    return {
        "B1": {
            "role": "hero_conversion_anchor",
            "scene_index": 0,
            "tier": "P0",
            "required_elements": ["hero_scene", "traffic_anchor", "proof_of_clarity"],
            "preferred_keywords": (retention_strategy.get("title_anchor_keywords") or keyword_routing.get("title_traffic_keywords", []))[:2],
            "goal": "Protect the main organic traffic asset and first-click conversion theme.",
        },
        "B2": {
            "role": "numeric_outcome_proof",
            "scene_index": 1,
            "tier": "P0",
            "required_elements": ["runtime_or_resolution", "outcome_translation", "buyer_confidence"],
            "preferred_keywords": keyword_routing.get("bullet_conversion_keywords", [])[:2],
            "goal": "Turn hard specs into concrete usage outcome and believable proof.",
            "mode_contract": motion_mode_contract,
        },
        "B3": {
            "role": "intent_expansion_scene",
            "scene_index": 2,
            "tier": "P1",
            "required_elements": ["new_intent_scene", "persona_fit", "accessory_match"],
            "preferred_keywords": (sp_keywords + keyword_routing.get("bullet_conversion_keywords", []))[:3],
            "goal": "Absorb the freshest SP intent without displacing the core title asset.",
        },
        "B4": {
            "role": "best_use_guidance",
            "scene_index": 3,
            "tier": "P1",
            "required_elements": ["limitation_framing", "mode_or_accessory_condition", "positive_guidance"],
            "preferred_keywords": keyword_routing.get("bullet_conversion_keywords", [])[2:4],
            "goal": "Express limits as warm best-use advice, never as seller-side risk language.",
            "mode_contract": detail_mode_contract,
        },
        "B5": {
            "role": "package_trust_close",
            "scene_index": 0,
            "tier": "P2",
            "required_elements": ["package_contents", "compatibility_or_capacity", "trust_close"],
            "preferred_keywords": keyword_routing.get("backend_longtail_keywords", [])[:2],
            "goal": "Close with what's included, capacity/compatibility, and practical purchase reassurance.",
        },
    }


def _derive_keyword_routing(tiered_keywords: Dict[str, List[str]]) -> Dict[str, List[str]]:
    metadata = tiered_keywords.get("_metadata", {}) or {}
    visible_candidates = [
        meta for meta in metadata.values()
        if not meta.get("blocked_brand") and not meta.get("relevance_filtered")
    ]
    traffic = sorted(
        visible_candidates,
        key=lambda item: (
            1 if (item.get("source_type") or "") == "feedback_organic_core" else 0,
            float(item.get("search_volume") or 0),
        ),
        reverse=True,
    )
    conversion = sorted(
        visible_candidates,
        key=lambda item: (
            1 if (item.get("source_type") or "") == "feedback_organic_core" else 0,
            1 if item.get("high_vol_flag") else 0,
            float(item.get("search_volume") or 0),
        ),
        reverse=True,
    )
    long_tail = [
        item for item in visible_candidates
        if (item.get("long_tail_flag") or (item.get("tier") or "").upper() == "L3")
    ]
    return {
        "title_traffic_keywords": [item.get("keyword") for item in traffic[:3] if item.get("keyword")],
        "bullet_conversion_keywords": [item.get("keyword") for item in conversion[:5] if item.get("keyword")],
        "backend_longtail_keywords": [item.get("keyword") for item in long_tail[:8] if item.get("keyword")],
    }


def _feedback_keywords(preprocessed_data: Any, bucket: str) -> List[str]:
    context = getattr(preprocessed_data, "feedback_context", {}) or {}
    rows = context.get(bucket) or []
    keywords: List[str] = []
    for row in rows:
        keyword = (row or {}).get("keyword") if isinstance(row, dict) else row
        if keyword:
            keywords.append(str(keyword).strip())
    return [keyword for keyword in keywords if keyword]


def _is_waterproof_term(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["waterproof", "ip", "防水", "潜水", "unterwasser", "wasserdicht"])


def _is_stabilization_term(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["stabilization", "防抖", "eis", "bildstabilisierung", "稳定"])


def _build_compliance_directives(preprocessed_data: PreprocessedData) -> Dict[str, Any]:
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    target_country = (preprocessed_data.target_country or "US").upper()
    byte_limit = 500 if target_country == "JP" else 200 if target_country == "IN" else 249

    waterproof_supported = constraints.get("waterproof_supported", False)
    waterproof_note = constraints.get("waterproof_note", "")
    if constraints.get("waterproof_requires_case"):
        waterproof_note = waterproof_note or "Only waterproof when using included housing"

    stabilization_supported = constraints.get("stabilization_supported", False)
    stabilization_note = constraints.get("stabilization_note", "")

    backend_only_terms: List[str] = []
    if not waterproof_supported:
        backend_only_terms.extend(["waterproof", "underwater", "ip68", "潜水", "wasserdicht"])
    if not stabilization_supported:
        backend_only_terms.extend(["stabilization", "防抖", "eis", "bildstabilisierung"])

    directives = {
        "waterproof": {
            "allow_visible": waterproof_supported,
            "requires_case": constraints.get("waterproof_requires_case", False),
            "depth_m": constraints.get("waterproof_depth_m"),
            "note": waterproof_note,
        },
        "stabilization": {
            "allow_visible": stabilization_supported,
            "modes": constraints.get("stabilization_modes", []),
            "note": stabilization_note,
        },
        "max_resolution": constraints.get("max_resolution", ""),
        "runtime_minutes": constraints.get("runtime_minutes"),
        "search_term_byte_limit": byte_limit,
        "backend_only_terms": sorted(set(filter(None, backend_only_terms))),
    }
    return directives


def _build_title_slots(prioritized_scenes: List[str]) -> List[Dict[str, Any]]:
    """
    Build ordered title slots using blueprint + prioritized scenes.
    """
    slots: List[Dict[str, Any]] = []
    for blueprint in TITLE_SLOT_BLUEPRINT:
        slot_entry = dict(blueprint)
        if slot_entry.get("slot") == "scene":
            scene_index = slot_entry.get("scene_index", 0)
            if prioritized_scenes:
                if scene_index < len(prioritized_scenes):
                    slot_entry["scene"] = prioritized_scenes[scene_index]
                else:
                    slot_entry["scene"] = prioritized_scenes[-1]
            else:
                slot_entry["scene"] = None
        slots.append(slot_entry)
    return slots


def extract_scenes_from_keywords(
    keyword_data: Any,
    language: str = "English",
    category_type: Optional[str] = None,
) -> List[str]:
    """
    从关键词数据中提取场景 (English labels internally)
    """
    scenes = set()

    if not keyword_data or not hasattr(keyword_data, 'keywords'):
        return list(scenes)
    keyword_blob = " ".join(
        str(item.get("keyword") or item.get("search_term") or "")
        for item in keyword_data.keywords
    ).lower()
    category_type = category_type or (
        "wearable_body_camera" if any(
            token in keyword_blob
            for token in ["body camera", "body cam", "bodycam", "wearable", "thumb camera", "clip-on", "clip on"]
        ) else "action_camera"
    )

    for keyword_item in keyword_data.keywords:
        keyword = keyword_item.get('keyword', '') or keyword_item.get("search_term", "")
        if not keyword:
            continue
        keyword_lower = keyword.lower()
        for pattern, scene_code in SCENE_ALIAS_PATTERNS:
            if scene_code in {"commuting_capture", "service_interaction"} and category_type != "wearable_body_camera":
                continue
            if pattern.search(keyword_lower):
                scenes.add(scene_code)

    default_scenes = _default_scenes_for_category(category_type)
    if len(scenes) < 3:
        scenes.update(default_scenes[:5])

    if category_type == "wearable_body_camera":
        scenes.update(["commuting_capture", "travel_documentation", "vlog_content_creation"])
    else:
        scenes.update(["cycling_recording", "underwater_exploration", "travel_documentation"])

    ordered = [scene for scene in default_scenes if scene in scenes]
    tail = [scene for scene in scenes if scene not in ordered]
    return (ordered + tail)[:8]


def prioritize_scenes(scenes: List[str], review_data: Any, aba_data: Any) -> List[str]:
    """
    根据评论和ABA数据对场景进行优先级排序 (English labels)
    """
    if not scenes:
        return ACTION_CAMERA_SCENES[:5]

    # 简单的优先级排序（可根据实际数据增强）
    scene_scores = {}

    # 基础分数
    for i, scene in enumerate(scenes):
        scene_scores[scene] = len(scenes) - i  # 原始顺序的权重

    # 根据评论数据调整分数
    if review_data and hasattr(review_data, 'insights'):
        for insight in review_data.insights:
            content = insight.get('content_text', '').lower()
            for scene in scenes:
                # 简单关键词匹配
                scene_keywords = {
                    'outdoor_sports': ['户外', '运动', 'outside', 'sport'],
                    'cycling_recording': ['骑行', '自行车', 'biking', 'bicycle'],
                    'underwater_exploration': ['水下', '游泳', '潜水', 'underwater', 'swim'],
                    'travel_documentation': ['旅行', '旅游', 'travel', 'trip'],
                    'family_use': ['家庭', '孩子', 'family', 'kid'],
                    'commuting_capture': ['commute', 'commuting', 'daily', 'walking', 'travel', 'hands-free'],
                    'service_interaction': ['service', 'patrol', 'interaction', 'delivery', 'work shift'],
                    'daily_lifelogging': ['daily', 'everyday', 'routine', 'life'],
                    'vlog_content_creation': ['vlog', 'creator', 'selfie', 'content'],
                }

                if scene in scene_keywords:
                    for keyword in scene_keywords[scene]:
                        if keyword in content:
                            scene_scores[scene] = scene_scores.get(scene, 0) + 2

    # 根据ABA数据调整分数（搜索量）
    if aba_data and hasattr(aba_data, 'trends'):
        for trend in aba_data.trends:
            keyword = trend.get('keyword', '').lower()
            search_volume = trend.get('search_volume', 0)

            for scene in scenes:
                scene_keywords = {
                    'outdoor_sports': ['outdoor', 'sports'],
                    'cycling_recording': ['biking', 'bicycle'],
                    'underwater_exploration': ['underwater', 'waterproof'],
                    'travel_documentation': ['travel', 'trip'],
                    'family_use': ['family', 'home'],
                    'commuting_capture': ['body camera', 'wearable camera', 'thumb camera', 'mini camera'],
                    'service_interaction': ['body cam', 'bodycam', 'wearable camera'],
                    'daily_lifelogging': ['daily', 'mini camera', 'small camera'],
                    'vlog_content_creation': ['vlog', 'creator', 'pov camera'],
                }

                if scene in scene_keywords:
                    for kw in scene_keywords[scene]:
                        if kw in keyword and search_volume > 0:
                            scene_scores[scene] = scene_scores.get(scene, 0) + min(search_volume / 1000, 5)

    # 按分数排序
    sorted_scenes = sorted(scene_scores.items(), key=lambda x: x[1], reverse=True)
    return [scene for scene, score in sorted_scenes]


def create_capability_scene_bindings(
    capabilities: List[str],
    prioritized_scenes: List[str],
    attribute_data: Any = None,
    language: str = "English",
) -> List[Dict[str, Any]]:
    """
    创建能力与场景的绑定关系（使用规范化英文标签 + 本地化展示名）
    """
    bindings: List[Dict[str, Any]] = []

    for capability in capabilities:
        slug = canonicalize_capability(capability)
        english_label = english_capability_label(slug)
        localized_label = get_capability_display(slug, language)

        allowed_scenes = DEFAULT_CAPABILITY_SCENE_BINDINGS.get(english_label, [])
        allowed_scenes = [scene for scene in allowed_scenes if scene in prioritized_scenes]
        if not allowed_scenes and prioritized_scenes:
            allowed_scenes = prioritized_scenes[:3]

        binding_type = "used_for_func"
        if "stabilization" in slug:
            binding_type = "performance_feature"
        elif "waterproof" in slug:
            binding_type = "environmental_feature"
        elif "wifi" in slug or "connect" in slug:
            binding_type = "connectivity_feature"

        bindings.append({
            "capability": english_label,
            "capability_slug": slug,
            "capability_localized": localized_label,
            "binding_type": binding_type,
            "allowed_scenes": allowed_scenes,
            "allowed_scenes_localized": [get_scene_display(scene, language) for scene in allowed_scenes],
            "forbidden_scenes": [],
            "usage_notes": f"Used in {', '.join(allowed_scenes[:2])} scenarios" if allowed_scenes else "No specific scene restrictions"
        })

    if any(scene in prioritized_scenes for scene in WEARABLE_BODY_CAMERA_SCENES):
        target_scenes = ["commuting_capture", "vlog_content_creation", "travel_documentation"]
    else:
        target_scenes = ["cycling_recording", "underwater_exploration", "travel_documentation"]
    bound_scenes = set()
    for binding in bindings:
        bound_scenes.update(binding.get("allowed_scenes", []))

    missing_scenes = [scene for scene in target_scenes if scene not in bound_scenes]
    if missing_scenes and attribute_data and hasattr(attribute_data, 'data'):
        attr_data = attribute_data.data

        for scene in missing_scenes:
            slug = None
            binding_type = "used_for_func"

            if scene == "underwater_exploration":
                if attr_data.get('waterproof_depth'):
                    slug = "waterproof"
                    binding_type = "environmental_feature"
                elif attr_data.get('video_resolution'):
                    slug = "4k_recording"
                    binding_type = "performance_feature"
            elif scene == "cycling_recording":
                if any("stabilization" in canonicalize_capability(cap) for cap in capabilities):
                    continue
                if attr_data.get('image_stabilization'):
                    slug = "stabilization"
                    binding_type = "performance_feature"
            elif scene == "travel_documentation":
                if attr_data.get('video_resolution'):
                    slug = "4k_recording"
                    binding_type = "performance_feature"
                elif attr_data.get('weight'):
                    slug = "versatile_mounting"
                    binding_type = "design_feature"
            elif scene == "commuting_capture":
                if attr_data.get('weight') or attr_data.get('item weight'):
                    slug = "versatile_mounting"
                    binding_type = "design_feature"
                elif attr_data.get('battery_average_life'):
                    slug = "long_battery_life"
                    binding_type = "performance_feature"
            elif scene == "vlog_content_creation":
                if attr_data.get('connectivity') or attr_data.get('connectivity technolog'):
                    slug = "wifi_connection"
                    binding_type = "connectivity_feature"

            if slug:
                english_label = english_capability_label(slug)
                localized_label = get_capability_display(slug, language)
                bindings.append({
                    "capability": english_label,
                    "capability_slug": slug,
                    "capability_localized": localized_label,
                    "binding_type": binding_type,
                    "allowed_scenes": [scene],
                    "allowed_scenes_localized": [get_scene_display(scene, language)],
                    "forbidden_scenes": [],
                    "usage_notes": f"Used in {scene} scenarios"
                })

    return bindings


def identify_faq_only_capabilities(capabilities: List[str], attribute_data: Any) -> List[str]:
    """
    识别只能在FAQ中提及的能力
    """
    faq_capabilities = []

    # 添加默认的FAQ only能力
    faq_capabilities.extend(FAQ_ONLY_CAPABILITIES)

    # 基于属性数据识别需要限制的能力
    if attribute_data and hasattr(attribute_data, 'data'):
        attr_data = attribute_data.data

        # 检查数字防抖
        stabilization = str(attr_data.get('image_stabilization', '')).lower()
        if 'digital' in stabilization or '数字' in stabilization:
            faq_capabilities.append("Digital stabilization limitation")

        # 检查防水限制
        waterproof_depth = str(attr_data.get('waterproof_depth', '')).lower()
        if 'case' in waterproof_depth or '壳' in waterproof_depth:
            faq_capabilities.append("Waterproof depth limitation")

        # 检查电池限制
        battery_life = str(attr_data.get('battery_life', '')).lower()
        if 'non-removable' in battery_life or '不可拆卸' in battery_life:
            faq_capabilities.append("Battery replacement guidance")

    # 添加能力列表中需要限制的项
    for capability in capabilities:
        capability_lower = capability.lower()
        if any(restricted in capability_lower for restricted in ['limit', 'notice', 'warning']):
            faq_capabilities.append(capability)

    return list(set(faq_capabilities))[:5]  # 最多5个


def identify_forbidden_pairs(capabilities: List[str], attribute_data: Any) -> List[List[str]]:
    """
    识别禁止的能力组合
    """
    forbidden_pairs = []

    # 添加默认禁止组合
    forbidden_pairs.extend(DEFAULT_FORBIDDEN_PAIRS)

    if attribute_data and hasattr(attribute_data, 'data'):
        attr_data = attribute_data.data

        # 基于属性数据识别禁止组合
        # 示例：如果分辨率是5K但防抖是数字防抖，则禁止组合
        resolution = str(attr_data.get('video_resolution', '')).lower()
        stabilization = str(attr_data.get('image_stabilization', '')).lower()

        if ('5k' in resolution or '5120' in resolution) and ('digital' in stabilization or '数字' in stabilization):
            forbidden_pairs.append(["5K recording", "digital stabilization"])

        # 如果防水深度有限制
        waterproof = str(attr_data.get('waterproof_depth', '')).lower()
        if '30' in waterproof and ('充电' in waterproof or 'charge' in waterproof):
            forbidden_pairs.append(["30m waterproof", "charging underwater"])

    # 基于能力列表识别可能冲突的组合
    capability_keywords = {
        'high_resolution': ['5k', '8k', '4k60fps'],
        'stabilization': ['stabilization', '防抖'],
        'live_streaming': ['streaming', '直播'],
        'waterproof': ['waterproof', '防水'],
        'low_temperature': ['cold', '低温'],
    }

    for i, cap1 in enumerate(capabilities):
        for j, cap2 in enumerate(capabilities):
            if i >= j:
                continue

            cap1_lower = cap1.lower()
            cap2_lower = cap2.lower()

            # 检查是否可能冲突
            if ('5k' in cap1_lower or '8k' in cap1_lower) and ('stabilization' in cap2_lower):
                forbidden_pairs.append([cap1, cap2])

            if ('streaming' in cap1_lower or '直播' in cap1_lower) and ('8k' in cap2_lower):
                forbidden_pairs.append([cap1, cap2])

    return forbidden_pairs[:10]  # 最多10个禁止组合


def generate_policy(preprocessed_data: PreprocessedData,
                    core_selling_points: List[str],
                    language: str = "English") -> Dict[str, Any]:
    """
    生成writing_policy

    Args:
        preprocessed_data: 预处理数据
        core_selling_points: 核心卖点列表
        language: 目标语言

    Returns:
        writing_policy字典
    """
    compliance_directives = _build_compliance_directives(preprocessed_data)
    canonical_caps = getattr(preprocessed_data, "canonical_core_selling_points", None)
    if canonical_caps:
        core_selling_points = canonical_caps[:]

    # 过滤不可见的能力
    visible_selling_points: List[str] = []
    backend_only_caps: List[str] = []
    for cap in core_selling_points:
        if _is_waterproof_term(cap) and not compliance_directives["waterproof"]["allow_visible"]:
            backend_only_caps.append(cap)
            continue
        if _is_stabilization_term(cap) and not compliance_directives["stabilization"]["allow_visible"]:
            backend_only_caps.append(cap)
            continue
        visible_selling_points.append(cap)
    if not visible_selling_points:
        visible_selling_points = core_selling_points[:]
    core_selling_points = visible_selling_points
    compliance_directives["backend_only_terms"] = sorted(
        set(compliance_directives.get("backend_only_terms", []) + backend_only_caps)
    )

    # 1. 提取场景并排序
    category_type = _infer_policy_category_type(preprocessed_data)
    scenes = extract_scenes_from_keywords(preprocessed_data.keyword_data, language, category_type=category_type)
    feedback_scene_seed = " ".join(_feedback_keywords(preprocessed_data, "sp_intent"))
    if feedback_scene_seed:
        class _FeedbackKeywordData:
            keywords = [{"keyword": feedback_scene_seed}]
        scenes.extend(extract_scenes_from_keywords(_FeedbackKeywordData(), language, category_type=category_type))
    prioritized_scenes = prioritize_scenes(scenes, preprocessed_data.review_data, preprocessed_data.aba_data)
    if not compliance_directives.get("waterproof", {}).get("allow_visible", True):
        prioritized_scenes = [scene for scene in prioritized_scenes if scene != "underwater_exploration"]
    if len(prioritized_scenes) < 4:
        for scene in _default_scenes_for_category(category_type):
            if scene not in prioritized_scenes:
                prioritized_scenes.append(scene)
            if len(prioritized_scenes) >= 4:
                break

    # 2. 创建能力场景绑定
    tiered_keywords = extract_tiered_keywords(
        preprocessed_data,
        language,
        getattr(preprocessed_data, "real_vocab", None),
    )
    keyword_routing = _derive_keyword_routing(tiered_keywords)
    retention_strategy = build_retention_strategy(preprocessed_data)
    keyword_routing["title_traffic_keywords"] = [
        keyword for keyword in (
            retention_strategy.get("title_anchor_keywords", [])
            + keyword_routing.get("title_traffic_keywords", [])
        )
        if keyword
    ][:5]
    keyword_routing["bullet_conversion_keywords"] = [
        keyword for keyword in (
            retention_strategy.get("bullet_anchor_keywords", [])
            + keyword_routing.get("bullet_conversion_keywords", [])
        )
        if keyword
    ][:6]
    preferred_locale = tiered_keywords.get("_preferred_locale")
    keyword_slots = build_keyword_slots(tiered_keywords, prioritized_scenes, language)

    canonical_caps = [
        english_capability_label(canonicalize_capability(cap))
        for cap in core_selling_points
    ]
    capability_scene_bindings = create_capability_scene_bindings(
        canonical_caps, prioritized_scenes, preprocessed_data.attribute_data, language
    )

    # 3. 识别FAQ only能力
    faq_only_capabilities = identify_faq_only_capabilities(core_selling_points, preprocessed_data.attribute_data)

    # 4. 识别禁止组合
    forbidden_pairs = identify_forbidden_pairs(core_selling_points, preprocessed_data.attribute_data)

    title_slots = _build_title_slots(prioritized_scenes)
    search_term_plan = {
        "priority_tiers": ["l3"],
        "max_bytes": compliance_directives.get("search_term_byte_limit", 249),
        "backend_only_terms": sorted(
            set(
                compliance_directives.get("backend_only_terms", [])
                + _feedback_keywords(preprocessed_data, "backend_only")
            )
        ),
        "approved_feedback_backend_terms": _feedback_keywords(preprocessed_data, "backend_only"),
        "routing_notes": "Title routes traffic head terms, bullets route conversion intent, L3 long-tail stays backend",
        "traffic_priority_keywords": keyword_routing["title_traffic_keywords"],
        "conversion_priority_keywords": keyword_routing["bullet_conversion_keywords"],
        "backend_longtail_keywords": keyword_routing["backend_longtail_keywords"],
    }
    bullet_slot_rules = _build_bullet_slot_rules(
        prioritized_scenes,
        keyword_routing,
        retention_strategy,
        preprocessed_data,
    )
    benchmark_bullets = _extract_benchmark_bullets(preprocessed_data)

    # 6. 构建完整policy (含 PRD v8.2 Node 0 英文Profile)
    product_profile = _build_product_profile(
        preprocessed_data,
        language,
        prioritized_scenes,
        core_selling_points,
    )

    policy = {
        "scene_priority": prioritized_scenes,
        "keyword_allocation_strategy": "balanced",  # 默认使用balanced策略
        "keyword_slots": keyword_slots,
        "capability_scene_bindings": capability_scene_bindings,
        "faq_only_capabilities": faq_only_capabilities,
        "forbidden_pairs": forbidden_pairs,
        "title_slots": title_slots,
        "search_term_plan": search_term_plan,
        "bullet_slot_rules": bullet_slot_rules,
        "benchmark_bullets": benchmark_bullets,
        "compliance_directives": compliance_directives,
        "field_role_summary": FIELD_ROLE_SUMMARY,
        "language": language,
        "target_language": language,
        "reasoning_language": "EN",
        "recording_mode_guidance": getattr(preprocessed_data, "capability_constraints", {}).get("recording_mode_guidance", {}),
        "product_profile": product_profile,  # PRD v8.2 Node 0 英文侧写
        "preferred_locale": preferred_locale,
        "keyword_routing": keyword_routing,
        "retention_strategy": retention_strategy,
        "metadata": {
            "core_selling_points_count": len(core_selling_points),
            "scenes_count": len(prioritized_scenes),
            "bindings_count": len(capability_scene_bindings),
            "generated_at": preprocessed_data.processed_at,
            "preferred_locale": preferred_locale,
            "feedback_organic_core_count": len(_feedback_keywords(preprocessed_data, "organic_core")),
            "feedback_sp_intent_count": len(_feedback_keywords(preprocessed_data, "sp_intent")),
            "retention_baseline_keywords": len(retention_strategy.get("baseline_keywords", [])),
        },
        "keyword_metadata": (getattr(preprocessed_data, "keyword_metadata", []) or [])[:50],
    }
    policy["copy_contracts"] = _build_copy_contracts(language, keyword_slots, bullet_slot_rules)
    market_pack = load_market_pack(getattr(preprocessed_data, "target_country", ""))
    policy["question_bank_context"] = build_question_bank_context(
        getattr(preprocessed_data, "asin_entity_profile", {}) or {},
        getattr(preprocessed_data, "target_country", ""),
    )
    policy = apply_market_pack(policy, market_pack)
    policy = apply_intent_weight_overrides(
        policy,
        retention_strategy,
        getattr(preprocessed_data, "intent_weight_snapshot", {}) or {},
    )
    policy = enrich_policy_with_intent_graph(policy, getattr(preprocessed_data, "capability_constraints", {}) or {})
    return policy


def generate_default_4scene_policy(preprocessed_data: Any) -> Dict[str, Any]:
    """
    生成默认的4场景策略模板 (推荐默认配置)

    Args:
        preprocessed_data: 预处理数据对象（需包含核心卖点/语言/关键词信息）

    Returns:
        4场景默认writing_policy字典
    """
    language = getattr(preprocessed_data, "language", "English")
    canonical_caps = getattr(preprocessed_data, "canonical_core_selling_points", [])
    core_selling_points = canonical_caps or getattr(preprocessed_data, "core_selling_points", [])
    tiered_keywords = extract_tiered_keywords(
        preprocessed_data,
        language,
        getattr(preprocessed_data, "real_vocab", None),
    )
    keyword_routing = _derive_keyword_routing(tiered_keywords)
    retention_strategy = build_retention_strategy(preprocessed_data)
    keyword_routing["title_traffic_keywords"] = [
        keyword for keyword in (
            retention_strategy.get("title_anchor_keywords", [])
            + keyword_routing.get("title_traffic_keywords", [])
        )
        if keyword
    ][:5]
    keyword_routing["bullet_conversion_keywords"] = [
        keyword for keyword in (
            retention_strategy.get("bullet_anchor_keywords", [])
            + keyword_routing.get("bullet_conversion_keywords", [])
        )
        if keyword
    ][:6]
    preferred_locale = tiered_keywords.get("_preferred_locale")
    compliance_directives = _build_compliance_directives(preprocessed_data)
    benchmark_bullets = _extract_benchmark_bullets(preprocessed_data)

    # 4个固定场景 (English)
    category_type = _infer_policy_category_type(preprocessed_data)
    four_scenes = _default_scenes_for_category(category_type)[:4]
    if not compliance_directives.get("waterproof", {}).get("allow_visible", True):
        four_scenes = [scene for scene in four_scenes if scene != "underwater_exploration"]
        for scene in _default_scenes_for_category(category_type):
            if scene not in four_scenes:
                four_scenes.append(scene)
            if len(four_scenes) >= 4:
                break
    keyword_slots = build_keyword_slots(tiered_keywords, four_scenes, language)

    # 为每个核心卖点创建场景绑定
    canonical_caps = [
        english_capability_label(canonicalize_capability(cap))
        for cap in core_selling_points
    ]
    capability_scene_bindings = create_capability_scene_bindings(
        canonical_caps or ["4k recording", "stabilization", "waterproof"],
        four_scenes,
        preprocessed_data.attribute_data,
        language
    )

    # PRD v8.2 Node 0: 产品战略侧写 (强制英文)
    # 这些字段用于内部推理，不直接生成目标语文案
    product_profile = _build_product_profile(
        preprocessed_data,
        language,
        four_scenes,
        core_selling_points,
    )
    if product_profile.get("category_type") == "action_camera":
        product_profile["actioncam_specific"] = {
            "mount_system": "multi_mount_compatible",
            "battery_strategy": "180min_continuous_recording",
            "evidence_priority": "video_quality",
            "stealth_priority": "low",
        }

    policy = {
        "scene_priority": four_scenes,
        "keyword_allocation_strategy": "balanced",
        "keyword_slots": keyword_slots,
        "capability_scene_bindings": capability_scene_bindings,
        "faq_only_capabilities": FAQ_ONLY_CAPABILITIES[:3],  # 限制为3个
        "forbidden_pairs": DEFAULT_FORBIDDEN_PAIRS[:2],  # 限制为2个
        "title_slots": _build_title_slots(four_scenes),
        "search_term_plan": {
            "priority_tiers": ["l3"],
            "max_bytes": compliance_directives.get("search_term_byte_limit", 249),
            "backend_only_terms": compliance_directives.get("backend_only_terms", []),
            "routing_notes": "Debug fallback routing: traffic -> title, conversion -> bullets, long-tail -> backend",
            "traffic_priority_keywords": keyword_routing["title_traffic_keywords"],
            "conversion_priority_keywords": keyword_routing["bullet_conversion_keywords"],
            "backend_longtail_keywords": keyword_routing["backend_longtail_keywords"],
        },
        "bullet_slot_rules": _build_bullet_slot_rules(
            four_scenes,
            keyword_routing,
            retention_strategy,
            preprocessed_data,
        ),
        "benchmark_bullets": benchmark_bullets,
        "compliance_directives": compliance_directives,
        "field_role_summary": FIELD_ROLE_SUMMARY,
        "language": language,
        "target_language": language,
        "reasoning_language": "EN",
        "recording_mode_guidance": getattr(preprocessed_data, "capability_constraints", {}).get("recording_mode_guidance", {}),
        "product_profile": product_profile,  # PRD v8.2 Node 0 英文侧写
        "preferred_locale": preferred_locale,
        "keyword_routing": keyword_routing,
        "retention_strategy": retention_strategy,
        "metadata": {
            "core_selling_points_count": len(core_selling_points),
            "scenes_count": len(four_scenes),
            "bindings_count": len(capability_scene_bindings),
            "is_default_4scene_template": True,
            "generated_at": "",
            "preferred_locale": preferred_locale,
            "retention_baseline_keywords": len(retention_strategy.get("baseline_keywords", [])),
        },
        "keyword_metadata": (getattr(preprocessed_data, "keyword_metadata", []) or [])[:50],
    }
    policy["copy_contracts"] = _build_copy_contracts(language, keyword_slots, policy["bullet_slot_rules"])
    market_pack = load_market_pack(getattr(preprocessed_data, "target_country", ""))
    policy["question_bank_context"] = build_question_bank_context(
        getattr(preprocessed_data, "asin_entity_profile", {}) or {},
        getattr(preprocessed_data, "target_country", ""),
    )
    policy = apply_market_pack(policy, market_pack)
    policy = apply_intent_weight_overrides(
        policy,
        retention_strategy,
        getattr(preprocessed_data, "intent_weight_snapshot", {}) or {},
    )
    policy = enrich_policy_with_intent_graph(policy, getattr(preprocessed_data, "capability_constraints", {}) or {})
    return policy


def _get_tone_hint(language: str) -> str:
    """根据目标语言返回语气风格提示"""
    tone_hints = {
        "Chinese": "direct_professional",
        "English": "casual_informative",
        "German": "technical_direct",
        "French": "elegant_descriptive",
        "Italian": "passionate_creative",
        "Spanish": "vibrant_engaging",
        "Japanese": "polite_detailed"
    }
    return tone_hints.get(language, "casual_informative")


def save_policy_to_file(policy: Dict[str, Any], filepath: str):
    """保存policy到文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(policy, f, ensure_ascii=False, indent=2)


def load_policy_from_file(filepath: str) -> Dict[str, Any]:
    """从文件加载policy"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    # 测试代码
    from dataclasses import dataclass

    @dataclass
    class MockKeywordData:
        keywords: List[Dict[str, Any]]

    @dataclass
    class MockReviewData:
        insights: List[Dict[str, Any]]

    @dataclass
    class MockABAData:
        trends: List[Dict[str, Any]]

    @dataclass
    class MockAttributeData:
        data: Dict[str, Any]

    # 创建模拟数据
    mock_preprocessed = PreprocessedData(
        run_config=None,
        attribute_data=MockAttributeData(data={
            "video_resolution": "4K",
            "image_stabilization": "Digital",
            "waterproof_depth": "30米（带防水壳）"
        }),
        keyword_data=MockKeywordData(keywords=[
            {"keyword": "outdoor sports camera"},
            {"keyword": "biking camera"},
            {"keyword": "underwater camera"}
        ]),
        review_data=MockReviewData(insights=[
            {"content_text": "户外运动拍摄效果很好", "field_name": "Feature_Praise"},
            {"content_text": "骑行时防抖效果不错", "field_name": "Feature_Praise"}
        ]),
        aba_data=MockABAData(trends=[
            {"keyword": "action camera outdoor", "search_volume": 5000},
            {"keyword": "bike camera", "search_volume": 3000}
        ]),
        core_selling_points=["4K录像", "防抖", "防水", "WiFi连接"],
        accessory_descriptions=[],
        quality_score=85,
        language="Chinese",
        processed_at="2024-01-01T00:00:00"
    )

    policy = generate_policy(mock_preprocessed, mock_preprocessed.core_selling_points, "Chinese")
    print("生成的writing_policy:")
    print(json.dumps(policy, ensure_ascii=False, indent=2))
