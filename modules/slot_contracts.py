"""Bullet slot contract validation helpers.

The contract layer checks the final visible bullet shape. It does not replace
the LLM or scorer; it answers whether a slot kept one coherent selling promise.
"""

from __future__ import annotations

import re
from typing import Any


_FORBIDDEN_DEFAULTS = ("warranty", "guaranteed", "best")

_PROMISE_PATTERNS = {
    "ready_to_record_kit": (
        r"\bbox\b",
        r"\bincludes?\b",
        r"\bincluded\b",
        r"\bkit\b",
        r"\bsetup\b",
        r"\bstart recording\b",
        r"\bright out of the box\b",
        r"\bready[- ]to[- ]record\b",
    ),
    "storage_setup": (
        r"\bstorage\b",
        r"\bmemory card\b",
        r"\bsd card\b",
        r"\b32gb\b",
        r"\b64gb\b",
        r"\b128gb\b",
        r"\b256gb\b",
        r"\bexpand\b",
    ),
    "battery_runtime": (
        r"\bbattery\b",
        r"\bruntime\b",
        r"\bminute\b",
        r"\bhours?\b",
        r"\bcharge\b",
        r"\bpowers?\b",
    ),
    "support_service": (
        r"\bsupport team\b",
        r"\bcustomer support\b",
        r"\bhelp\b",
        r"\bservice\b",
    ),
}

_B5_ALLOWED_PRIMARY = ("ready_to_record_kit", "storage_setup", "compatibility_guidance")

_BATTERY_RUNTIME_CONTEXT_RE = re.compile(
    r"\b(?:battery\s+life|runtime|continuous\s+recording|per\s+charge|single\s+charge|"
    r"\d+\s*(?:minutes?|mins?|hours?|hrs?)\b)",
    re.IGNORECASE,
)

_PACKAGE_BATTERY_CONTEXT_RE = re.compile(
    r"\b(?:includes?|included|comes\s+with|inside(?:\s+you'?ll\s+find)?|package|box)\b"
    r".{0,120}\b(?:lithium\s+)?battery\b",
    re.IGNORECASE,
)


def _normalize_slot(slot: Any) -> str:
    value = str(slot or "").strip().upper()
    if value.startswith("B") and value[1:].isdigit():
        return value
    if value.startswith("BULLET_") and value.removeprefix("BULLET_").isdigit():
        return f"B{value.removeprefix('BULLET_')}"
    return value


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _allowed_facts_from(canonical_facts: dict | None) -> list[str]:
    fact_map = (canonical_facts or {}).get("fact_map") or {}
    allowed: list[str] = []
    if isinstance(fact_map, dict):
        for fact_id, fact in fact_map.items():
            if isinstance(fact, dict) and fact.get("claim_permission") == "visible_allowed":
                allowed.append(str(fact_id))
    return allowed


def _detect_promises(text: str) -> list[str]:
    hits: list[str] = []
    for promise, patterns in _PROMISE_PATTERNS.items():
        if promise == "battery_runtime":
            if _detect_battery_runtime(text):
                hits.append(promise)
            continue
        if any(re.search(pattern, text) for pattern in patterns):
            hits.append(promise)
    return hits


def _detect_battery_runtime(text: str) -> bool:
    if not re.search(r"\bbattery\b|\bcharge\b|\bruntime\b|\bminutes?\b|\bhours?\b", text, re.IGNORECASE):
        return False
    if _PACKAGE_BATTERY_CONTEXT_RE.search(text) and not _BATTERY_RUNTIME_CONTEXT_RE.search(text):
        return False
    return bool(_BATTERY_RUNTIME_CONTEXT_RE.search(text))


def build_slot_contract(
    slot: str,
    canonical_facts: dict | None = None,
    keyword_metadata: dict | None = None,
) -> dict:
    """Return slot role, allowed facts, forbidden surfaces, and bridge rules."""
    normalized_slot = _normalize_slot(slot)
    allowed_facts = _allowed_facts_from(canonical_facts)
    base = {
        "slot": normalized_slot,
        "slot_role": "single_semantic_promise",
        "allowed_facts": allowed_facts,
        "keyword_metadata": keyword_metadata or {},
        "forbidden_surfaces": [],
        "allowed_primary_promises": [],
        "allowed_secondary_bridges": [],
        "max_primary_promises": 1,
    }
    if normalized_slot == "B5":
        base.update(
            {
                "slot_role": "kit_readiness_or_support_boundary",
                "allowed_primary_promises": list(_B5_ALLOWED_PRIMARY),
                "allowed_secondary_bridges": ["storage_setup"],
                "forbidden_secondary_promises": ["battery_runtime", "support_service"],
                "forbidden_surfaces": list(_FORBIDDEN_DEFAULTS),
            }
        )
    return base


def validate_bullet_against_contract(bullet: str, contract: dict) -> dict:
    """Validate that a bullet keeps one coherent slot promise."""
    normalized = _normalize_text(bullet)
    reasons: list[str] = []
    detected_promises = _detect_promises(normalized)

    for forbidden in contract.get("forbidden_surfaces") or []:
        if re.search(rf"\b{re.escape(str(forbidden).lower())}\b", normalized):
            reasons.append(f"forbidden_surface:{forbidden}")

    allowed_primary = set(contract.get("allowed_primary_promises") or [])
    allowed_secondary = set(contract.get("allowed_secondary_bridges") or [])
    forbidden_secondary = set(contract.get("forbidden_secondary_promises") or [])
    observed_primary = [promise for promise in detected_promises if promise in allowed_primary]
    observed_forbidden = [promise for promise in detected_promises if promise in forbidden_secondary]

    if observed_forbidden:
        reasons.append("multiple_primary_promises")
    elif len(observed_primary) > int(contract.get("max_primary_promises") or 1):
        extra_primary = [promise for promise in observed_primary if promise not in allowed_secondary]
        if len(extra_primary) > int(contract.get("max_primary_promises") or 1):
            reasons.append("multiple_primary_promises")

    if contract.get("slot") == "B5" and "ready_to_record_kit" in detected_promises:
        non_bridge_topics = [
            promise
            for promise in detected_promises
            if promise not in {"ready_to_record_kit", *allowed_secondary}
        ]
        if non_bridge_topics and "multiple_primary_promises" not in reasons:
            reasons.append("multiple_primary_promises")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "detected_promises": detected_promises,
        "repair_payload": {
            "slot": contract.get("slot"),
            "slot_role": contract.get("slot_role"),
            "allowed_facts": list(contract.get("allowed_facts") or []),
            "allowed_primary_promises": list(contract.get("allowed_primary_promises") or []),
            "allowed_secondary_bridges": list(contract.get("allowed_secondary_bridges") or []),
            "forbidden_surfaces": list(contract.get("forbidden_surfaces") or []),
        },
    }
