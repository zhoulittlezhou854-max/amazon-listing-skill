#!/usr/bin/env python3
"""Keyword utilities shared between writing_policy and copy_generation."""

from __future__ import annotations

import re
import math
from typing import Any, Dict, List, Optional, Sequence

from modules.language_utils import get_scene_display
from modules.keyword_protocol import build_keyword_protocol


LANGUAGE_LOCALE_MAP = {
    "English": "en",
    "Chinese": "zh",
    "German": "de",
    "French": "fr",
    "Spanish": "es",
    "Italian": "it",
    "Japanese": "ja",
}

LOCALE_ACCENT_PATTERNS = {
    "fr": re.compile(r"[àâçéèêëîïôûùüÿœæ]", re.IGNORECASE),
    "de": re.compile(r"[äöüß]", re.IGNORECASE),
    "es": re.compile(r"[áéíóúñ]", re.IGNORECASE),
    "it": re.compile(r"[àèéìòù]", re.IGNORECASE),
}

# Keep this list focused on clear competitor brands / trademark-like product lines.
# Generic category nouns such as "casque", "pack", or "360" create false positives
# in FR/DE/EN listings and should be handled by relevance rules, not brand blocking.
GLOBAL_BRAND_BLOCKLIST = {
    "dji",
    "gopro",
    "go pro",
    "insta360",
    "osmo",
    "akaso",
    "sony",
    "insta",
    "sjcam",
    "markiii",
    "kodak",
    "canon",
    "moovora",
    "g7x",
    "action 6",
    "action 4",
    "action 5",
    "ps5",
    "shotkam",
    "viofo",
    "vantrue",
    "70mai",
    "garmin",
    "aiker",
    "jeto",
    "nuisk",
    "skypro",
    "sky pro",
    "swevix",
    "snaproll",
}


def _normalize_brand_token(token: str) -> str:
    return re.sub(r"[\s\-]", "", token.lower())


def is_blocklisted_brand(token: str) -> Optional[str]:
    compact = _normalize_brand_token(token)
    for brand in GLOBAL_BRAND_BLOCKLIST:
        if _normalize_brand_token(brand) in compact:
            return brand
    return None

def _compile_block_pattern(term: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", re.IGNORECASE)


_BLOCKLIST_PATTERNS = {
    term: _compile_block_pattern(term) for term in GLOBAL_BRAND_BLOCKLIST
}


def find_blocklisted_terms(text: Optional[str]) -> List[str]:
    if not text:
        return []
    hits = []
    for brand, pattern in _BLOCKLIST_PATTERNS.items():
        if pattern.search(text):
            hits.append(brand)
    return hits


def remove_blocklisted_terms(text: Optional[str]) -> str:
    cleaned = text or ""
    for pattern in _BLOCKLIST_PATTERNS.values():
        cleaned = pattern.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()

KANJI_PATTERN = re.compile(r"[\u4e00-\u9fff]")
KANA_PATTERN = re.compile(r"[\u3040-\u30ff]")

DEFAULT_KEYWORDS_BY_LANGUAGE = {
    "Chinese": {"l1": ["运动相机", "4K相机"], "l2": ["防水相机", "防抖相机"], "l3": ["户外相机"]},
    "English": {"l1": ["action camera 4k"], "l2": ["sports camera"], "l3": ["helmet camera"]},
    "German": {"l1": ["aktionskamera 4k"], "l2": ["sportkamera"], "l3": ["helmkamera"]},
    "French": {"l1": ["caméra d'action 4K"], "l2": ["caméra sport", "caméra étanche"], "l3": ["caméra casco"]},
    "Spanish": {"l1": ["cámara de acción 4K"], "l2": ["cámara deportiva", "cámara impermeable"], "l3": ["cámara casco"]},
    "Italian": {"l1": ["videocamera sportiva 4K"], "l2": ["fotocamera sportiva", "fotocamera impermeabile"], "l3": ["fotocamera casco"]},
    "Japanese": {"l1": ["アクションカメラ 4K"], "l2": ["スポーツカメラ", "防水カメラ"], "l3": ["ヘルメットカメラ"]},
}

ACTION_CAMERA_NEGATIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bespion",
        r"\bspy\b",
        r"\bhidden\b",
        r"\bnanny\b",
        r"\bsecurity\b",
        r"\bsurveillance\b",
        r"\bindoor\b",
        r"\bint[ée]rieure\b",
        r"\bversteckt",
        r"\bspion",
        r"\bpolice\b",
        r"\bpieton\b",
        r"\bbody\s?cam\b",
        r"\bbody camera\b",
        r"\bcorporelle\b",
        r"\bdash\s?cam\b",
        r"\bvoiture\b",
        r"\brearview\b",
        r"\br[ée]troviseur\b",
        r"\bpocket\b",
        r"\bmic\b",
        r"\bdrone\b",
        r"\bps5\b",
        r"\bprojector\b",
        r"\bvid[ée]o-projecteur\b",
        r"\bmultiprise\b",
        r"\bace pro\b",
        r"\bosmo pocket\b",
        r"\bnanovision\b",
        r"\b360 camera\b",
        r"\bcamera 360\b",
        r"\bcam[ée]ra 360\b",
        r"\bmini phone\b",
        r"\bcamera glasses\b",
        r"\bvideo glasses\b",
        r"\bbrille mit kamera\b",
        r"\bkinder\b",
    ]
]

ACTION_CAMERA_POSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bcamera\b",
        r"\bkamera\b",
        r"\bcam[ée]ra\b",
        r"\baction\b",
        r"\bsport\b",
        r"\bvlog\b",
        r"\b4k\b",
        r"\b5k\b",
        r"\bhelmet\b",
        r"\bcasque\b",
        r"\bhelm\b",
        r"\bhelmkamera\b",
        r"\bvelo\b",
        r"\bv[ée]lo\b",
        r"\bbike\b",
        r"\bfahrrad\b",
        r"\bmotorrad\b",
        r"\bcycling\b",
        r"\bwaterproof\b",
        r"\b[ée]tanche\b",
        r"\bunterwasser\b",
        r"\baktionskamera\b",
        r"\bactionkamera\b",
        r"\bunderwater\b",
        r"\bsnorkel",
        r"\bplong",
        r"\btravel\b",
        r"\bvoyage\b",
        r"\boutdoor\b",
        r"\bcam[ée]scope\b",
    ]
]

WEARABLE_BODY_CAMERA_NEGATIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bespion",
        r"\bspy\b",
        r"\bhidden\b",
        r"\bnanny\b",
        r"\bsurveillance\b",
        r"\bsecurity camera\b",
        r"\bindoor\b",
        r"\bdash\s?cam\b",
        r"\bdrone\b",
        r"\bcamera glasses\b",
        r"\bvideo glasses\b",
        r"\bsmart glasses\b",
        r"\bmini phone\b",
        r"\bprojector\b",
        r"\bps5\b",
    ]
]

WEARABLE_BODY_CAMERA_POSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bbody camera\b",
        r"\bbody cam\b",
        r"\bbodycam\b",
        r"\bwearable\b",
        r"\bthumb camera\b",
        r"\bclip(?:-|\s)?on\b",
        r"\bclip cam\b",
        r"\bmini camera\b",
        r"\bpov camera\b",
        r"\bvlogging camera\b",
        r"\btravel camera\b",
        r"\baction camera\b",
        r"\bsmall camera\b",
        r"\bmagnetic\b",
        r"\bneck(?:lace| strap| lanyard)?\b",
        r"\bhands[\s-]?free\b",
    ]
]


def _infer_category_type(preprocessed_data: Any) -> str:
    explicit = getattr(preprocessed_data, "category_type", None)
    if explicit:
        return str(explicit)
    core_points = " ".join(getattr(preprocessed_data, "core_selling_points", []) or []).lower()
    attr_data = getattr(getattr(preprocessed_data, "attribute_data", None), "data", {}) or {}
    attr_blob = " ".join(str(value) for value in attr_data.values()).lower()
    keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
    keyword_blob = " ".join(
        str(row.get("keyword") or row.get("search_term") or "")
        for row in keyword_rows[:60]
    ).lower()
    insight_blob = str(getattr(preprocessed_data, "raw_human_insights", "") or "").lower()
    combined = f"{core_points} {attr_blob} {keyword_blob} {insight_blob}"
    wearable_signals = [
        "body camera",
        "body cam",
        "bodycam",
        "wearable camera",
        "thumb camera",
        "clip on",
        "clip-on",
        "magnetic back clip",
        "neck strap",
        "back clip",
    ]
    action_signals = [
        "waterproof",
        "water resistance level | waterproof",
        "eis",
        "stabilization",
        "dual screen",
        "underwater",
        "helmet mount",
        "action camera",
        "aktionskamera",
        "action cam",
    ]
    wearable_score = sum(1 for token in wearable_signals if token in combined)
    action_score = sum(1 for token in action_signals if token in combined)
    if action_score >= wearable_score + 1 and action_score >= 2:
        return "action_camera"
    if wearable_score >= action_score and wearable_score >= 1:
        return "wearable_body_camera"
    if any(token in combined for token in ["waterproof", "stabilization", "4k", "action camera", "camcorder", "运动相机"]):
        return "action_camera"
    return "generic"


def infer_category_type(preprocessed_data: Any) -> str:
    return _infer_category_type(preprocessed_data)


def keyword_relevance_issue(token: str, category_type: str = "generic") -> Optional[str]:
    text = (token or "").strip()
    if not text:
        return "empty"
    lowered = text.lower()
    if category_type == "wearable_body_camera":
        for pattern in WEARABLE_BODY_CAMERA_NEGATIVE_PATTERNS:
            if pattern.search(lowered):
                return f"negative_pattern:{pattern.pattern}"
        if not any(pattern.search(lowered) for pattern in WEARABLE_BODY_CAMERA_POSITIVE_PATTERNS):
            return "missing_wearable_camera_signal"
        return None
    if category_type != "action_camera":
        return None
    for pattern in ACTION_CAMERA_NEGATIVE_PATTERNS:
        if pattern.search(lowered):
            return f"negative_pattern:{pattern.pattern}"
    if not any(pattern.search(lowered) for pattern in ACTION_CAMERA_POSITIVE_PATTERNS):
        return "missing_action_camera_signal"
    return None


def _append_unique(bucket: List[str], token: str, seen: set, limit: Optional[int]) -> None:
    if not token:
        return
    normalized = token.strip()
    if not normalized:
        return
    key = normalized.lower()
    if key in seen:
        return
    if limit is not None and len(bucket) >= limit:
        return
    seen.add(key)
    bucket.append(normalized)


def locale_code_for_language(language: str) -> str:
    return LANGUAGE_LOCALE_MAP.get(language, "en")


def detect_token_locale(token: str) -> str:
    if not token:
        return "unknown"
    stripped = token.strip()
    if not stripped:
        return "unknown"
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ\u3040-\u30FF\u4e00-\u9fff]", stripped):
        return "neutral"
    lowered = stripped.lower()
    for code, pattern in LOCALE_ACCENT_PATTERNS.items():
        if pattern.search(lowered):
            return code
    if KANJI_PATTERN.search(stripped):
        return "zh"
    if KANA_PATTERN.search(stripped):
        return "ja"
    return "en"


def token_matches_locale(token: str, metadata: Optional[Dict[str, Any]], preferred_locale: str) -> bool:
    if not preferred_locale or preferred_locale == "en":
        return True
    source_country = (metadata.get("source_country") or "").lower() if metadata else ""
    detected = metadata.get("detected_locale") if metadata else None
    detected = detected or detect_token_locale(token)
    if source_country and source_country.startswith(preferred_locale):
        return True
    if detected == "neutral" and source_country.startswith(preferred_locale):
        return True
    pattern = LOCALE_ACCENT_PATTERNS.get(preferred_locale)
    if not pattern and preferred_locale not in LOCALE_ACCENT_PATTERNS:
        pattern = re.compile(r"[\u00C0-\u024F]", re.IGNORECASE)
    if pattern and pattern.search(token):
        return True
    return detected == preferred_locale


def extract_tiered_keywords(
    preprocessed_data: Any,
    language: str = "English",
    real_vocab: Optional[Any] = None,
    limits: Optional[Dict[str, int]] = None,
) -> Dict[str, List[str]]:
    """Return legacy tier lists backed by the keyword protocol metadata."""
    limits = limits or {"l1": 8, "l2": 12, "l3": 12}
    preferred_locale = locale_code_for_language(language)
    category_type = _infer_category_type(preprocessed_data)

    source = "real_vocab"
    rv = real_vocab or getattr(preprocessed_data, "real_vocab", None)
    rv_rows: Sequence[Dict[str, Any]] = getattr(rv, "top_keywords", []) if rv else []
    if rv_rows:
        source_rows = [dict(row) for row in rv_rows]
    else:
        source = "keyword_table"
        source_rows = [
            dict(row)
            for row in (getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or [])
        ]

    for row in source_rows:
        row.setdefault("source_type", source)

    protocol = build_keyword_protocol(
        source_rows,
        country=preferred_locale.upper(),
        category_type=category_type,
    )

    metadata_map: Dict[str, Dict[str, Any]] = {}
    visible_rows: List[Dict[str, Any]] = []
    for row in protocol.get("keyword_metadata", []) or []:
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        meta_entry = dict(row)
        meta_entry.setdefault("source_type", source)
        meta_entry["source_country"] = meta_entry.get("country")
        meta_entry["detected_locale"] = meta_entry.get("detected_locale") or detect_token_locale(keyword)
        meta_entry["category_type"] = category_type
        meta_entry["blocked_brand"] = bool(is_blocklisted_brand(keyword))
        meta_entry["backend_only"] = bool(meta_entry["blocked_brand"])
        meta_entry["relevance_reason"] = keyword_relevance_issue(keyword, category_type)
        meta_entry["relevance_filtered"] = bool(meta_entry["relevance_reason"])
        meta_entry["high_vol_flag"] = False
        meta_entry["explicit_tier"] = str(row.get("tier") or "").upper() in {"L1", "L2", "L3"}
        if meta_entry.get("quality_status") != "qualified":
            pass
        elif meta_entry["blocked_brand"]:
            meta_entry["quality_status"] = "rejected"
            meta_entry["rejection_reason"] = "brand_blocked"
            meta_entry["traffic_tier"] = "REJECTED"
            meta_entry["tier"] = "REJECTED"
            meta_entry["routing_role"] = "blocked"
            meta_entry["opportunity_type"] = "blocked"
        elif meta_entry["relevance_filtered"]:
            meta_entry["quality_status"] = "rejected"
            meta_entry["rejection_reason"] = meta_entry["relevance_reason"]
            meta_entry["traffic_tier"] = "REJECTED"
            meta_entry["tier"] = "REJECTED"
            meta_entry["routing_role"] = "rejected"
            meta_entry["opportunity_type"] = "relevance_filtered"
        elif preferred_locale and preferred_locale != "en" and not token_matches_locale(keyword, meta_entry, preferred_locale):
            meta_entry["quality_status"] = "rejected"
            meta_entry["rejection_reason"] = "locale_mismatch"
            meta_entry["traffic_tier"] = "REJECTED"
            meta_entry["tier"] = "REJECTED"
            meta_entry["routing_role"] = "rejected"
            meta_entry["opportunity_type"] = "locale_filtered"

        metadata_map[keyword.lower()] = meta_entry
        if (
            meta_entry.get("quality_status") == "qualified"
            and str(meta_entry.get("traffic_tier") or "").lower() in {"l1", "l2", "l3"}
        ):
            visible_rows.append(meta_entry)

    volume_samples = [
        float(row.get("search_volume") or 0)
        for row in metadata_map.values()
        if isinstance(row.get("search_volume"), (int, float)) or str(row.get("search_volume") or "").replace(".", "", 1).isdigit()
    ]
    if volume_samples:
        sorted_volumes = sorted(volume_samples)
        idx = max(0, math.ceil(0.75 * len(sorted_volumes)) - 1)
        threshold = sorted_volumes[idx]
        if math.isfinite(threshold) and threshold > 0:
            for meta_entry in metadata_map.values():
                meta_entry["high_vol_flag"] = float(meta_entry.get("search_volume") or 0) >= threshold

    tiers: Dict[str, List[str]] = {"l1": [], "l2": [], "l3": []}
    seen = {tier: set() for tier in tiers}
    for row in sorted(
        visible_rows,
        key=lambda item: (
            {"L1": 0, "L2": 1, "L3": 2}.get(str(item.get("traffic_tier") or "").upper(), 3),
            -float(item.get("search_volume") or 0),
            -float(item.get("opportunity_score") or 0),
        ),
    ):
        tier_key = str(row.get("traffic_tier") or "L3").lower()
        _append_unique(tiers[tier_key], row["keyword"], seen[tier_key], limits.get(tier_key))

    if source == "real_vocab":
        # Sparse local vocab fixtures historically exposed order-winning rows as
        # L2/L3 candidates even when the new protocol has too few rows for a
        # full relative spread or marks a low-evidence row as watchlist.
        real_vocab_rows = [
            row for row in metadata_map.values()
            if row.get("source_type") in {"order_winning", "template", "review"}
        ]
        if real_vocab_rows and not tiers["l2"] and len(real_vocab_rows) <= 3:
            for keyword in list(tiers["l1"]):
                _append_unique(tiers["l2"], keyword, seen["l2"], limits.get("l2"))
                seen["l1"].discard(keyword.lower())
            tiers["l1"] = []
        for row in real_vocab_rows:
            if row.get("quality_status") == "watchlist":
                _append_unique(tiers["l3"], row["keyword"], seen["l3"], limits.get("l3"))

    if not tiers["l1"] and not tiers["l2"] and not tiers["l3"]:
        source = "fallback"
        fallback = DEFAULT_KEYWORDS_BY_LANGUAGE.get(language, DEFAULT_KEYWORDS_BY_LANGUAGE["English"])
        fallback_protocol_rows = []
        for tier, words in fallback.items():
            for word in words:
                tiers[tier].append(word)
                fallback_protocol_rows.append(
                    {
                        "keyword": word,
                        "search_volume": 0,
                        "source_type": "locale_fallback",
                        "country": preferred_locale.upper(),
                        "traffic_tier": tier.upper(),
                        "tier": tier.upper(),
                        "quality_status": "qualified",
                        "routing_role": {"l1": "title", "l2": "bullet", "l3": "backend"}[tier],
                        "rejection_reason": "",
                        "category_type": category_type,
                        "detected_locale": detect_token_locale(word),
                    }
                )
        for row in fallback_protocol_rows:
            metadata_map[row["keyword"].lower()] = row

    tiers["_source"] = source
    tiers["_metadata"] = metadata_map
    tiers["_preferred_locale"] = preferred_locale
    return tiers


def build_keyword_slots(
    tiered_keywords: Dict[str, List[str]],
    prioritized_scenes: List[str],
    language: str,
) -> Dict[str, Any]:
    """Derive keyword slots for title/bullets/search terms."""
    l1 = list(tiered_keywords.get("l1", []))
    l2 = list(tiered_keywords.get("l2", []))
    l3 = list(tiered_keywords.get("l3", []))

    def _merge_keywords(*groups: Sequence[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for group in groups:
            for token in group:
                if not token:
                    continue
                lowered = token.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                merged.append(token)
        return merged

    def _scene_phrase(index: int) -> str:
        if not prioritized_scenes:
            return ""
        code = prioritized_scenes[index % len(prioritized_scenes)]
        localized = get_scene_display(code, language)
        canonical = code.replace("_", " ")
        if localized.lower() == canonical.lower():
            return code
        return f"{localized} ({code})"

    slots = {
        "title": _merge_keywords(l1[:3]),
        "bullet_1": {
            "keywords": l2[:1],
            "scene": _scene_phrase(0),
        },
        "bullet_2": {
            "keywords": l2[1:2],
            "scene": _scene_phrase(1),
        },
        "bullet_3": {
            "keywords": l2[2:3],
            "scene": _scene_phrase(2),
        },
        "bullet_4": {
            "keywords": [],
        },
        "bullet_5": {
            "keywords": [],
        },
    }

    slots["search_terms"] = {"keywords": l3[:] if l3 else []}
    return slots
