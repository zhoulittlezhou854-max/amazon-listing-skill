#!/usr/bin/env python3
"""Keyword utilities shared between writing_policy and copy_generation."""

from __future__ import annotations

import re
import math
from typing import Any, Dict, List, Optional, Sequence

from modules.language_utils import get_scene_display


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


def _tier_from_volume(volume: float) -> str:
    if volume >= 10000:
        return "l1"
    if volume >= 1000:
        return "l2"
    return "l3"


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
    """Return tiered keyword lists prioritizing real vocab > keyword table > fallback."""
    limits = limits or {"l1": 8, "l2": 12, "l3": 12}
    tiers: Dict[str, List[str]] = {"l1": [], "l2": [], "l3": []}
    seen = {tier: set() for tier in tiers}

    metadata_map: Dict[str, Dict[str, Any]] = {}
    preferred_locale = locale_code_for_language(language)
    category_type = _infer_category_type(preprocessed_data)
    volume_samples: List[float] = []

    def add_keyword(token: str, tier: str, meta: Optional[Dict[str, Any]] = None):
        if not token:
            return
        normalized = token.strip()
        if not normalized:
            return
        tier_key = (tier or "l3").lower()
        if tier_key not in tiers:
            tier_key = _tier_from_volume(float((meta or {}).get("search_volume") or 0))
        bucket = tiers[tier_key]
        key = normalized.lower()
        blocked_brand = bool(is_blocklisted_brand(token))
        relevance_issue = keyword_relevance_issue(token, category_type)
        if not blocked_brand and not relevance_issue:
            _append_unique(bucket, token, seen[tier_key], limits.get(tier_key))
        detected_locale = detect_token_locale(normalized)
        try:
            numeric_volume = float((meta or {}).get("search_volume", 0))
        except (TypeError, ValueError):
            numeric_volume = 0.0
        volume_samples.append(numeric_volume)
        long_tail_flag = len(re.split(r"[\s\-_\/]+", normalized)) >= 4
        explicit_tier = bool(meta and meta.get("explicit_tier"))

        payload = {
            "keyword": normalized,
            "tier": tier_key.upper(),
            "source_type": (meta or {}).get("source_type", source),
            "search_volume": numeric_volume,
            "source_country": (meta or {}).get("country"),
            "detected_locale": detected_locale,
            "conversion_rank": None,
            "long_tail_flag": long_tail_flag,
            "high_vol_flag": False,
            "explicit_tier": explicit_tier,
            "blocked_brand": blocked_brand,
            "backend_only": blocked_brand,
            "category_type": category_type,
            "relevance_filtered": bool(relevance_issue),
            "relevance_reason": relevance_issue,
        }
        existing = metadata_map.get(key)
        if not existing or explicit_tier or not existing.get("explicit_tier"):
            metadata_map[key] = payload
        if blocked_brand or relevance_issue:
            return

    source = "real_vocab"
    rv = real_vocab or getattr(preprocessed_data, "real_vocab", None)
    rv_rows: Sequence[Dict[str, Any]] = getattr(rv, "top_keywords", []) if rv else []
    if rv_rows:
        sorted_rows = sorted(
            rv_rows,
            key=lambda row: float(row.get("search_volume") or 0),
            reverse=True,
        )
        for row in sorted_rows:
            keyword = row.get("keyword") or row.get("search_term")
            if not keyword:
                continue
            try:
                volume = float(row.get("search_volume") or 0)
            except (TypeError, ValueError):
                volume = 0
            tier_hint = str(row.get("tier") or "").strip().lower()
            tier_override = tier_hint if tier_hint in {"l1", "l2", "l3"} else ""
            tier = tier_override or _tier_from_volume(volume)
            add_keyword(
                keyword,
                tier,
                {
                    "source_type": row.get("source_type") or "real_vocab",
                    "search_volume": volume,
                    "country": row.get("country"),
                    "explicit_tier": bool(tier_override),
                },
            )
    else:
        source = "keyword_table"
        keyword_rows = getattr(getattr(preprocessed_data, "keyword_data", None), "keywords", []) or []
        for row in sorted(keyword_rows, key=lambda r: float(r.get("search_volume") or 0), reverse=True):
            keyword = row.get("keyword") or row.get("search_term")
            if not keyword:
                continue
            try:
                volume = float(row.get("search_volume") or 0)
            except (TypeError, ValueError):
                volume = 0
            tier_hint = str(row.get("tier") or "").strip().lower()
            tier_override = tier_hint if tier_hint in {"l1", "l2", "l3"} else ""
            tier = tier_override or _tier_from_volume(volume)
            add_keyword(
                keyword,
                tier,
                {
                    "source_type": row.get("source_type") or source,
                    "search_volume": volume,
                    "country": row.get("country"),
                    "explicit_tier": bool(tier_override),
                },
            )

    def _apply_locale_filter(words: List[str]) -> List[str]:
        filtered: List[str] = []
        for token in words:
            meta = metadata_map.get(token.lower())
            if preferred_locale and preferred_locale != "en":
                if not token_matches_locale(token, meta, preferred_locale):
                    continue
            filtered.append(token)
        return filtered

    tiers["l1"] = _apply_locale_filter(tiers["l1"])
    tiers["l2"] = _apply_locale_filter(tiers["l2"])
    tiers["l3"] = _apply_locale_filter(tiers["l3"])

    if volume_samples:
        sorted_volumes = sorted(volume_samples)
        idx = max(0, math.ceil(0.75 * len(sorted_volumes)) - 1)
        threshold = sorted_volumes[idx]
    else:
        threshold = float("inf")
    if math.isfinite(threshold) and threshold > 0:
        for meta_entry in metadata_map.values():
            if meta_entry.get("search_volume", 0) >= threshold:
                meta_entry["high_vol_flag"] = True

    if not tiers["l1"] and not tiers["l2"] and not tiers["l3"]:
        source = "fallback"
        fallback = DEFAULT_KEYWORDS_BY_LANGUAGE.get(language, DEFAULT_KEYWORDS_BY_LANGUAGE["English"])
        for tier, words in fallback.items():
            for word in words:
                add_keyword(
                    word,
                    tier,
                    {"source_type": "locale_fallback", "search_volume": 0, "country": preferred_locale.upper()},
                )

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
