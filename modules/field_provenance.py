"""Field-level provenance and launch eligibility helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_PROVENANCE_ORDER = {
    "native_live": 0,
    "repaired_live": 1,
    "safe_fallback": 2,
    "unsafe_fallback": 3,
    "unavailable": 4,
}

_FIELD_ALIASES = {
    "desc": "description",
    "description": "description",
    "description_llm": "description",
    "product_description": "description",
    "body_copy": "description",
    "search term": "search_terms",
    "search terms": "search_terms",
    "search_term": "search_terms",
    "search_terms": "search_terms",
}


def _clean_field(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    raw = "_".join(raw.split())
    return _FIELD_ALIASES.get(raw, raw)


def _field_names(values: Any) -> set[str]:
    return {_clean_field(item) for item in (values or []) if _clean_field(item)}


def _explicit_provenance(field: str, metadata: dict[str, Any]) -> str | None:
    provenance = metadata.get("field_provenance") or {}
    if not isinstance(provenance, dict):
        return None
    value = None
    for candidate_field, candidate_value in provenance.items():
        if _clean_field(candidate_field) == field:
            value = candidate_value
            break
    if isinstance(value, dict):
        value = value.get("provenance_tier") or value.get("tier")
    if value is None:
        return None
    tier = _clean_field(value)
    return tier if tier in _PROVENANCE_ORDER else None


def _risk_blocking_reasons(field: str, risk_summary: dict[str, Any]) -> list[str]:
    blocking_fields = _field_names(risk_summary.get("blocking_fields"))
    reasons: list[str] = []
    if field in blocking_fields:
        reasons.append(f"risk_blocked:{field}")

    for section_value in risk_summary.values():
        if not isinstance(section_value, dict):
            continue
        nested_fields = _field_names(section_value.get("blocking_fields"))
        if field in nested_fields:
            reason = f"risk_blocked:{field}"
            if reason not in reasons:
                reasons.append(reason)
        for issue in section_value.get("issues") or []:
            if isinstance(issue, dict) and _clean_field(issue.get("field")) == field:
                reason = f"risk_blocked:{field}"
                if reason not in reasons:
                    reasons.append(reason)
    return reasons


def build_field_candidate(
    field: str,
    text: str | None,
    source_version: str | None,
    metadata: dict | None = None,
    risk_summary: dict | None = None,
) -> dict:
    """Build a field candidate with provenance and launch eligibility."""
    field = _clean_field(field)
    metadata = dict(metadata or {})
    risk_summary = dict(risk_summary or {})
    text_present = bool(str(text or "").strip())

    tier = _explicit_provenance(field, metadata)
    if tier is None:
        if not text_present:
            tier = "unavailable"
        elif field in _field_names(metadata.get("visible_llm_fallback_fields")):
            tier = "safe_fallback"
        else:
            tier = "native_live"

    blocking_reasons: list[str] = []
    if not text_present:
        tier = "unavailable"
        blocking_reasons.append("field_unavailable")

    blocking_reasons.extend(reason for reason in _risk_blocking_reasons(field, risk_summary) if reason not in blocking_reasons)

    if tier == "safe_fallback":
        eligibility = "review_only"
        if "fallback_not_launch_eligible" not in blocking_reasons:
            blocking_reasons.append("fallback_not_launch_eligible")
    elif tier == "unsafe_fallback":
        eligibility = "blocked"
        if "unsafe_fallback" not in blocking_reasons:
            blocking_reasons.append("unsafe_fallback")
    elif tier == "unavailable":
        eligibility = "blocked"
        if "field_unavailable" not in blocking_reasons:
            blocking_reasons.append("field_unavailable")
    elif blocking_reasons:
        eligibility = "blocked"
    else:
        eligibility = "launch_eligible"

    return {
        "field": field,
        "text_present": text_present,
        "source_version": source_version,
        "provenance_tier": tier,
        "eligibility": eligibility,
        "launch_eligible": eligibility == "launch_eligible",
        "blocking_reasons": blocking_reasons,
    }


def select_launch_eligible_field(field: str, candidates: list[dict]) -> dict:
    """Select the best launch-eligible field candidate, or best non-launch fallback."""
    normalized_field = _clean_field(field)
    normalized_candidates = [dict(candidate or {}) for candidate in candidates if isinstance(candidate, dict)]
    ordered = sorted(
        normalized_candidates,
        key=lambda candidate: _PROVENANCE_ORDER.get(str(candidate.get("provenance_tier") or "unavailable"), 99),
    )
    for candidate in ordered:
        if candidate.get("eligibility") == "launch_eligible":
            selected = deepcopy(candidate)
            selected["launch_eligible"] = True
            return selected
    if ordered:
        selected = deepcopy(ordered[0])
        selected["launch_eligible"] = False
        return selected
    return {
        "field": normalized_field,
        "text_present": False,
        "source_version": None,
        "provenance_tier": "unavailable",
        "eligibility": "blocked",
        "launch_eligible": False,
        "blocking_reasons": ["field_unavailable"],
    }
