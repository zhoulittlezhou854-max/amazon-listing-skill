"""Canonical product fact registry for visible-claim decisions."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


ALIASES = {
    "video_resolution": ["video_resolution", "Video capture resolution", "video capture resolution", "Resolution"],
    "battery_life": ["battery_life", "Battery Average Life", "Battery Life", "runtime"],
    "weight": ["weight", "Item Weight", "item weight", "Product Weight"],
    "included_components": ["included_components", "Included components", "Components Included"],
    "water_resistance": ["water_resistance", "Water Resistance Leve", "Water Resistance Level", "waterproof_depth"],
}

VISIBLE_ALLOWED = "visible_allowed"
BOUNDARY_ONLY = "boundary_only"
BLOCKED = "blocked"
UNKNOWN = "unknown"

_REQUIRED_FACTS = {
    "generic": ["video_resolution", "battery_life", "weight"],
    "wearable_body_camera": ["video_resolution", "battery_life", "weight", "waterproof_supported"],
}


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _iter_sources(
    attribute_data: Dict[str, Any],
    supplemental_data: Optional[Dict[str, Any]],
    capability_constraints: Optional[Dict[str, Any]],
) -> Iterable[Tuple[str, Dict[str, Any], float]]:
    yield "attribute_data", attribute_data or {}, 0.95
    if supplemental_data:
        yield "supplemental_data", supplemental_data, 0.85
    if capability_constraints:
        yield "capability_constraints", capability_constraints, 0.9


def _find_value(
    fact_id: str,
    attribute_data: Dict[str, Any],
    supplemental_data: Optional[Dict[str, Any]],
    capability_constraints: Optional[Dict[str, Any]],
) -> Tuple[Any, str, str, float]:
    alias_keys = {_normalized_key(alias) for alias in ALIASES.get(fact_id, [fact_id])}
    for source_name, source_data, confidence in _iter_sources(attribute_data, supplemental_data, capability_constraints):
        for key, value in source_data.items():
            if _normalized_key(key) in alias_keys and value not in {None, ""}:
                return value, str(key), source_name, confidence
    return None, "", "", 0.0


def _parse_number_and_unit(value: Any) -> Tuple[Any, str]:
    text = str(value or "").strip()
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)?", text)
    if not match:
        return value, ""
    number = float(match.group(1))
    if number.is_integer():
        number = int(number)
    return number, (match.group(2) or "").lower()


def _parse_battery_life(value: Any) -> Tuple[Any, str]:
    number, unit = _parse_number_and_unit(value)
    if unit in {"min", "mins", "minute", "minutes"}:
        return number, "minutes"
    if unit in {"hr", "hrs", "hour", "hours"} and isinstance(number, (int, float)):
        minutes = number * 60
        return int(minutes) if float(minutes).is_integer() else minutes, "minutes"
    return number, unit or "minutes"


def _parse_weight(value: Any) -> Tuple[Any, str]:
    number, unit = _parse_number_and_unit(value)
    if unit in {"kilogram", "kilograms"}:
        unit = "kg"
    if unit in {"gram", "grams"}:
        unit = "g"
    return number, unit


def _extract_storage_component(value: Any) -> Optional[str]:
    text = str(value or "")
    parts = [part.strip() for part in re.split(r"[,;/|]", text) if part.strip()]
    for part in parts:
        if re.search(r"\b\d+\s*(?:gb|g)\b", part, re.IGNORECASE) and re.search(
            r"card|memory|storage", part, re.IGNORECASE
        ):
            return re.sub(r"\s+", " ", part)
    match = re.search(r"\b\d+\s*(?:gb|g)\b[^,;/|]*(?:card|memory|storage)[^,;/|]*", text, re.IGNORECASE)
    if match:
        return re.sub(r"\s+", " ", match.group(0).strip())
    return None


def _waterproof_fact(value: Any, source_key: str, source: str, confidence: float) -> Dict[str, Any]:
    text = str(value or "").strip()
    normalized = text.lower()
    negative = any(token in normalized for token in ["not water", "non-water", "not waterproof", "no waterproof", "不防水"])
    unknown = any(token in normalized for token in ["unknown", "not mentioned", "no ip rating", "unrated", "未说明", "未知"])
    positive = bool(
        re.search(r"\bwater[\s-]?resistant\b|\bwaterproof\b|\bipx\d+\b|\b\d+(?:\.\d+)?\s*(?:m|meter|meters)\b", normalized)
    )
    if negative:
        fact_value: Any = False
        permission = BLOCKED
    elif unknown:
        fact_value = text
        permission = UNKNOWN
    elif positive:
        fact_value = True
        permission = VISIBLE_ALLOWED if re.search(r"ipx\d|\d+\s*m", normalized) else BOUNDARY_ONLY
    else:
        fact_value = text
        permission = UNKNOWN
    return {
        "fact_id": "waterproof_supported",
        "value": fact_value,
        "raw_value": value,
        "unit": "",
        "source": source,
        "source_key": source_key,
        "confidence": confidence,
        "claim_permission": permission,
    }


def _make_fact(
    fact_id: str,
    value: Any,
    source_key: str,
    source: str,
    confidence: float,
    claim_permission: str = VISIBLE_ALLOWED,
    unit: str = "",
) -> Dict[str, Any]:
    fact: Dict[str, Any] = {
        "fact_id": fact_id,
        "value": value,
        "raw_value": value,
        "unit": unit,
        "source": source,
        "source_key": source_key,
        "confidence": confidence,
        "claim_permission": claim_permission,
    }
    return fact


def build_canonical_facts(
    attribute_data: dict,
    supplemental_data: dict | None = None,
    capability_constraints: dict | None = None,
) -> dict:
    """Build normalized facts with evidence strength and visible-claim permission."""
    warnings: List[Dict[str, Any]] = []
    facts: List[Dict[str, Any]] = []

    value, source_key, source, confidence = _find_value(
        "video_resolution", attribute_data, supplemental_data, capability_constraints
    )
    if value not in {None, ""}:
        facts.append(_make_fact("video_resolution", str(value).strip(), source_key, source, confidence))

    value, source_key, source, confidence = _find_value(
        "battery_life", attribute_data, supplemental_data, capability_constraints
    )
    if value not in {None, ""}:
        parsed, unit = _parse_battery_life(value)
        facts.append(_make_fact("battery_life", parsed, source_key, source, confidence, unit=unit))

    value, source_key, source, confidence = _find_value("weight", attribute_data, supplemental_data, capability_constraints)
    if value not in {None, ""}:
        parsed, unit = _parse_weight(value)
        facts.append(_make_fact("weight", parsed, source_key, source, confidence, unit=unit))

    value, source_key, source, confidence = _find_value(
        "included_components", attribute_data, supplemental_data, capability_constraints
    )
    if value not in {None, ""}:
        facts.append(_make_fact("included_components", str(value).strip(), source_key, source, confidence))
        storage = _extract_storage_component(value)
        if storage:
            facts.append(_make_fact("storage_included", storage, source_key, source, confidence))

    value, source_key, source, confidence = _find_value(
        "water_resistance", attribute_data, supplemental_data, capability_constraints
    )
    if value not in {None, ""}:
        facts.append(_waterproof_fact(value, source_key, source, confidence))

    fact_map = {fact["fact_id"]: fact for fact in facts}
    for required in _REQUIRED_FACTS["generic"]:
        if required not in fact_map:
            warnings.append({"fact_id": required, "severity": "medium", "message": f"Missing canonical fact: {required}"})

    return {"facts": facts, "fact_map": fact_map, "warnings": warnings}


def summarize_fact_readiness(canonical_facts: dict, category_type: str = "generic") -> dict:
    """Summarize whether required facts are known enough for generation."""
    facts = canonical_facts.get("facts") or []
    fact_map = canonical_facts.get("fact_map") or {fact.get("fact_id"): fact for fact in facts if fact.get("fact_id")}
    required = _REQUIRED_FACTS.get(category_type, _REQUIRED_FACTS["generic"])

    required_fact_status: Dict[str, str] = {}
    blocking_missing_facts: List[str] = []
    known_count = 0

    for fact_id in required:
        fact = fact_map.get(fact_id)
        if not fact or fact.get("value") in {None, ""} or fact.get("claim_permission") == UNKNOWN:
            required_fact_status[fact_id] = "missing"
            blocking_missing_facts.append(fact_id)
            continue
        permission = fact.get("claim_permission")
        if permission == BLOCKED:
            required_fact_status[fact_id] = "known_blocked"
        elif permission == BOUNDARY_ONLY:
            required_fact_status[fact_id] = "known_boundary"
        else:
            required_fact_status[fact_id] = "known_visible"
        known_count += 1

    total_required = len(required)
    readiness_score = int(round((known_count / total_required) * 100)) if total_required else 100
    coverage = {
        "known": known_count,
        "required": total_required,
        "ratio": round(known_count / total_required, 4) if total_required else 1.0,
    }
    warnings = list(canonical_facts.get("warnings") or [])
    for fact_id in blocking_missing_facts:
        warnings.append({"fact_id": fact_id, "severity": "high", "message": f"Required fact is missing: {fact_id}"})

    return {
        "category_type": category_type,
        "required_facts": required,
        "required_fact_status": required_fact_status,
        "coverage": coverage,
        "blocking_missing": blocking_missing_facts,
        "blocking_missing_facts": blocking_missing_facts,
        "readiness_score": readiness_score,
        "warnings": warnings,
    }
