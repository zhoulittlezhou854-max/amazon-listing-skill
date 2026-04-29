"""Visible claim-language audit and deterministic repair helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_ALLOWED_PERMISSIONS = {"visible_allowed", "allowed", "supported", "permitted"}


def _fact_map(canonical_facts: Optional[dict]) -> Dict[str, Dict[str, Any]]:
    if not isinstance(canonical_facts, dict):
        return {}
    facts = canonical_facts.get("fact_map") or {}
    if facts:
        return {str(key): value for key, value in facts.items() if isinstance(value, dict)}
    return {
        str(fact.get("fact_id")): fact
        for fact in canonical_facts.get("facts") or []
        if isinstance(fact, dict) and fact.get("fact_id")
    }


def _fact_allows(facts: Dict[str, Dict[str, Any]], fact_ids: List[str]) -> bool:
    for fact_id in fact_ids:
        fact = facts.get(fact_id) or {}
        permission = str(fact.get("claim_permission") or "").strip().lower()
        if permission in _ALLOWED_PERMISSIONS and fact.get("value") not in {None, "", False}:
            return True
    return False


def _violation(surface: str, reason: str, repairable: bool, start: int, end: int) -> Dict[str, Any]:
    return {
        "surface": surface,
        "reason": reason,
        "repairable": repairable,
        "span": [start, end],
    }


def audit_claim_language(text: str, canonical_facts: dict | None = None) -> dict:
    """Return claim-language status for visible listing copy."""
    source = str(text or "")
    facts = _fact_map(canonical_facts)
    violations: List[Dict[str, Any]] = []

    blocking_surface_patterns = [
        (re.compile(r"\bbest[-](?:in[-]class|selling)\b", re.IGNORECASE), "best", "unsupported_superlative"),
        (re.compile(r"#\s*1(?=-)", re.IGNORECASE), "#1", "unsupported_superlative"),
        (re.compile(r"\bbetter\s+than\s+ever\b", re.IGNORECASE), "better than", "unsupported_comparison"),
    ]
    for pattern, surface, reason in blocking_surface_patterns:
        for match in pattern.finditer(source):
            violations.append(_violation(surface, reason, False, match.start(), match.end()))

    repairable_patterns = [
        (re.compile(r"\bbest\b(?!-)", re.IGNORECASE), "best", "unsupported_superlative"),
        (re.compile(r"\bbetter\s+than\b(?!\s+ever\b)", re.IGNORECASE), "better than", "unsupported_comparison"),
        (re.compile(r"#\s*1\b(?!-)", re.IGNORECASE), "#1", "unsupported_superlative"),
    ]
    for pattern, surface, reason in repairable_patterns:
        for match in pattern.finditer(source):
            violations.append(_violation(surface, reason, True, match.start(), match.end()))

    guarded_patterns = [
        (re.compile(r"\bguaranteed\b", re.IGNORECASE), "guaranteed", "guarantee_claim", ["guarantee", "guaranteed_claim"]),
        (re.compile(r"\bwarranty\b", re.IGNORECASE), "warranty", "warranty_claim", ["warranty", "warranty_period"]),
        (re.compile(r"\bwaterproof\b", re.IGNORECASE), "waterproof", "truth_sensitive", ["waterproof_supported", "water_resistance"]),
    ]
    for pattern, surface, reason, fact_ids in guarded_patterns:
        if _fact_allows(facts, fact_ids):
            continue
        for match in pattern.finditer(source):
            violations.append(_violation(surface, reason, False, match.start(), match.end()))

    violations.sort(key=lambda row: (row["span"][0], row["span"][1]))
    blocking_reasons = [row["reason"] for row in violations if not row.get("repairable")]
    repairable = bool(violations) and not blocking_reasons and all(row.get("repairable") for row in violations)
    return {
        "passed": not violations,
        "repairable": repairable,
        "violations": violations,
        "blocking_reasons": blocking_reasons,
    }


def repair_claim_language(text: str, canonical_facts: dict | None = None) -> str:
    """Apply safe semantic rewrites for repairable claim surfaces."""
    repaired = str(text or "")
    replacements = [
        (re.compile(r"\bbest\s+for\b", re.IGNORECASE), "suitable for"),
        (re.compile(r"\bbetter\s+than\b(?!\s+ever\b)", re.IGNORECASE), "designed for"),
        (re.compile(r"#\s*1\b(?!-)", re.IGNORECASE), "compact"),
        (re.compile(r"\bbest\b(?!-)", re.IGNORECASE), "suitable"),
    ]
    for pattern, replacement in replacements:
        repaired = pattern.sub(replacement, repaired)
    return re.sub(r"\s+", " ", repaired).strip()
