"""Normalize generated listing artifacts into candidate contracts."""

from collections.abc import Mapping
from typing import Any

from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

_FAILED_STATUSES = {"failed", "timed_out", "timeout", "error"}
_REQUIRED_BULLET_COUNT = 5
_TRACE_KEYS = (
    "source_trace",
    "keyword_reconciliation",
    "risk_summary",
    "score_summary",
    "metadata",
)


def _clean_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_search_terms(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(cleaned for item in value if (cleaned := _clean_string(item)))
    return _clean_string(value)


def _clean_bullets(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [cleaned for item in value if (cleaned := _clean_string(item))]


def _clean_trace(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _is_failed_status(status_key: str) -> bool:
    return status_key in _FAILED_STATUSES or status_key.startswith("failed_at_")


def _field_provenance_blockers(metadata: Mapping[str, Any]) -> list[str]:
    field_provenance = metadata.get("field_provenance") or {}
    if not isinstance(field_provenance, Mapping):
        return []
    blockers: list[str] = []
    for field, record in field_provenance.items():
        if not isinstance(record, Mapping):
            continue
        field_name = _clean_string(field)
        tier = _clean_string(record.get("provenance_tier"))
        eligibility = _clean_string(record.get("eligibility"))
        reasons = {_clean_string(reason) for reason in (record.get("blocking_reasons") or []) if _clean_string(reason)}
        if tier == "safe_fallback" or eligibility == "review_only" or "fallback_not_launch_eligible" in reasons:
            blockers.append(f"field_safe_fallback_not_launch_eligible:{field_name}")
        if tier == "unsafe_fallback" or "unsafe_fallback" in reasons:
            blockers.append(f"field_unsafe_fallback:{field_name}")
        if tier == "unavailable" or "field_unavailable" in reasons:
            blockers.append(f"field_unavailable:{field_name}")
    return blockers


def _slot_contract_blockers(artifact: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    quality_slots: set[str] = set()
    for row in artifact.get("slot_quality_packets") or []:
        if not isinstance(row, Mapping):
            continue
        slot = _clean_string(row.get("slot")) or "unknown"
        quality_slots.add(slot.upper())
        for issue in row.get("issues") or []:
            clean = _clean_string(issue)
            if not clean.startswith("slot_contract_failed:"):
                continue
            reason = clean.split(":", 1)[1] or "unknown"
            blockers.append(f"slot_contract_failed:{slot}:{reason}")
    bullets = _clean_bullets(artifact.get("bullets"))
    if len(bullets) >= 5 and "B5" not in quality_slots:
        result = validate_bullet_against_contract(bullets[4], build_slot_contract("B5"))
        for reason in result.get("reasons") or []:
            blockers.append(f"slot_contract_failed:B5:{reason}")
    return blockers


def _canonical_fact_blockers(metadata: Mapping[str, Any]) -> list[str]:
    readiness = metadata.get("canonical_fact_readiness") or metadata.get("fact_readiness") or {}
    if not isinstance(readiness, Mapping):
        return []
    blockers: list[str] = []
    for fact_id in readiness.get("blocking_missing") or []:
        clean = _clean_string(fact_id)
        if clean:
            blockers.append(f"canonical_fact_missing:{clean}")
    for fact_id in readiness.get("blocking_missing_facts") or []:
        clean = _clean_string(fact_id)
        if clean:
            blockers.append(f"canonical_fact_missing:{clean}")
    for fact_id in readiness.get("blocked_claim_facts") or readiness.get("canonical_fact_blocked_claims") or []:
        clean = _clean_string(fact_id)
        if clean:
            blockers.append(f"canonical_fact_blocked_claim:{clean}")
    return blockers


def _final_visible_quality(artifact: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    top_level = artifact.get("final_visible_quality")
    if isinstance(top_level, Mapping):
        return dict(top_level)
    nested = metadata.get("final_visible_quality")
    if isinstance(nested, Mapping):
        return dict(nested)
    return {}


def _final_visible_blockers(final_quality: Mapping[str, Any]) -> list[str]:
    return [
        clean
        for item in (final_quality.get("paste_ready_blockers") or [])
        if (clean := _clean_string(item))
    ]


def build_listing_candidate(
    candidate_id: str,
    artifact: Mapping[str, Any],
    *,
    source_type: str,
) -> dict[str, Any]:
    """Build a reviewable/paste-ready candidate contract from an artifact."""
    title = _clean_string(artifact.get("title"))
    bullets = _clean_bullets(artifact.get("bullets"))
    description = _clean_string(artifact.get("description"))
    search_terms = _clean_search_terms(artifact.get("search_terms"))
    generation_status = _clean_string(artifact.get("generation_status"))
    status_key = generation_status.lower()
    failed_status = _is_failed_status(status_key)

    blockers: list[str] = []
    if not title:
        blockers.append("title_missing")
    if len(bullets) < _REQUIRED_BULLET_COUNT:
        blockers.append("insufficient_bullets")
    if not description:
        blockers.append("description_missing")
    if not search_terms:
        blockers.append("search_terms_missing")
    if failed_status:
        blockers.append(f"generation_{status_key}")
    metadata = _clean_trace(artifact.get("metadata"))
    blockers.extend(_field_provenance_blockers(metadata))
    blockers.extend(_slot_contract_blockers(artifact))
    blockers.extend(_canonical_fact_blockers(metadata))
    final_quality = _final_visible_quality(artifact, metadata)
    blockers.extend(_final_visible_blockers(final_quality))
    keyword_reconciliation = _clean_trace(artifact.get("keyword_reconciliation"))
    if keyword_reconciliation.get("status") != "complete":
        blockers.append("keyword_reconciliation_incomplete")
    risk_summary = _clean_trace(artifact.get("risk_summary"))
    risk_listing_status = _clean_trace(risk_summary.get("listing_status"))
    if str(risk_listing_status.get("status") or "").strip().upper() == "NOT_READY_FOR_LISTING":
        blockers.append("risk_listing_not_ready")
        blockers.extend(str(item) for item in (risk_listing_status.get("blocking_reasons") or []) if str(item).strip())
    experimental_source = source_type == "experimental" or candidate_id == "version_b"
    if experimental_source:
        blockers.append("experimental_version_not_paste_ready")

    reviewable = bool(title and len(bullets) >= _REQUIRED_BULLET_COUNT and not failed_status)
    paste_ready = reviewable and not blockers

    candidate: dict[str, Any] = {
        "candidate_id": candidate_id,
        "source_type": source_type,
        "generation_status": generation_status,
        "reviewable_status": "reviewable" if reviewable else "not_reviewable",
        "paste_ready_status": "paste_ready" if paste_ready else "blocked",
        "paste_ready_blockers": blockers,
        "debug_only": (not reviewable) or experimental_source,
        "title": title,
        "bullets": bullets,
        "description": description,
        "search_terms": search_terms,
        "final_visible_quality": final_quality,
    }
    for key in _TRACE_KEYS:
        if key == "keyword_reconciliation":
            candidate[key] = keyword_reconciliation
        elif key == "risk_summary":
            candidate[key] = risk_summary
        elif key == "metadata":
            candidate[key] = metadata
        else:
            candidate[key] = _clean_trace(artifact.get(key))
    return candidate
