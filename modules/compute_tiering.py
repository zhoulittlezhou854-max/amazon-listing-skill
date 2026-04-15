from __future__ import annotations

from typing import Any, Dict


def _normalize_fallback_fields(fields: Any) -> set[str]:
    normalized: set[str] = set()
    for item in fields or []:
        value = str(item or "").strip().lower()
        if not value:
            continue
        if value in {"title", "description", "search_terms", "aplus_content"}:
            normalized.add(value)
            continue
        if value.startswith("bullet_"):
            normalized.add(value)
            continue
        if value.startswith("b") and value[1:].isdigit():
            normalized.add(f"bullet_{int(value[1:])}")
            continue
        if value.isdigit():
            normalized.add(f"bullet_{int(value)}")
    return normalized


def build_compute_tier_map(generated_copy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    metadata = generated_copy.get("metadata", {}) or {}
    fallback_fields = _normalize_fallback_fields(metadata.get("visible_llm_fallback_fields") or [])
    bullets = generated_copy.get("bullets", []) or []

    fields = ["title"]
    fields.extend(f"bullet_{idx}" for idx, _ in enumerate(bullets[:5], 1))
    fields.extend(["description", "search_terms", "aplus_content"])

    tier_map: Dict[str, Dict[str, Any]] = {}
    for field_name in fields:
        is_fallback = field_name in fallback_fields
        tier_map[field_name] = {
            "tier_used": "rule_based" if is_fallback else "native",
            "fallback_reason": "visible_llm_fallback" if is_fallback else "",
            "rerun_recommended": is_fallback,
            "rerun_priority": "high" if is_fallback and field_name in {"title", "bullet_1", "bullet_2"} else "normal",
        }
    return tier_map


def summarize_compute_tier_map(compute_tier_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    field_map = compute_tier_map or {}
    fallback_field_count = 0
    rerun_recommended_count = 0
    native_field_count = 0
    rule_based_field_count = 0
    high_priority_rerun_fields = []

    for field_name, info in field_map.items():
        tier_used = str((info or {}).get("tier_used") or "").strip().lower()
        rerun_recommended = bool((info or {}).get("rerun_recommended"))
        rerun_priority = str((info or {}).get("rerun_priority") or "").strip().lower()
        if tier_used == "native":
            native_field_count += 1
        if tier_used == "rule_based":
            rule_based_field_count += 1
            fallback_field_count += 1
        if rerun_recommended:
            rerun_recommended_count += 1
        if rerun_recommended and rerun_priority == "high":
            high_priority_rerun_fields.append(field_name)

    return {
        "field_count": len(field_map),
        "fallback_field_count": fallback_field_count,
        "rerun_recommended_count": rerun_recommended_count,
        "native_field_count": native_field_count,
        "rule_based_field_count": rule_based_field_count,
        "high_priority_rerun_fields": high_priority_rerun_fields,
    }
