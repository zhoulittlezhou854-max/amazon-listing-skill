"""Final-text keyword reconciliation against authoritative metadata."""

from __future__ import annotations

import re
from typing import Any, Mapping

_PLURAL_SAFE_STOPWORDS = {
    "and",
    "by",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _normalize_keyword(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value)


def _coerce_search_term_texts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value)]


def _metadata_tier(metadata: Mapping[str, Any]) -> str:
    tier = str(
        metadata.get("tier")
        or metadata.get("traffic_tier")
        or metadata.get("level")
        or "UNCLASSIFIED"
    ).strip().upper()
    return tier or "UNCLASSIFIED"


def _token_pattern(token: str) -> str:
    escaped = re.escape(token)
    if len(token) > 1 and token.endswith("y") and token[-2] not in "aeiou":
        return f"{re.escape(token[:-1])}(?:y|ies)"
    if token.endswith(("s", "x", "z")) or token.endswith(("ch", "sh")):
        return f"{escaped}(?:es)?"
    return f"{escaped}s?"


def _phrase_pattern(normalized_keyword: str) -> re.Pattern[str]:
    tokens = normalized_keyword.split()
    if not tokens:
        return re.compile(r"a^")
    token_patterns = [
        re.escape(token) if token in _PLURAL_SAFE_STOPWORDS else _token_pattern(token)
        for token in tokens
    ]
    escaped = r"\s+".join(token_patterns)
    return re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)


def _candidate_fields(candidate: Mapping[str, Any]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {
        "title": [_coerce_text(candidate.get("title"))],
    }

    bullets = candidate.get("bullets")
    if isinstance(bullets, (list, tuple)):
        for index, bullet in enumerate(bullets[:5], start=1):
            fields[f"bullet_{index}"] = [_coerce_text(bullet)]

    for index in range(1, 6):
        field = f"bullet_{index}"
        if field not in fields:
            fields[field] = [_coerce_text(candidate.get(field))]

    fields["description"] = [_coerce_text(candidate.get("description"))]
    fields["search_terms"] = _coerce_search_term_texts(candidate.get("search_terms"))
    return fields


def reconcile_keyword_assignments(
    candidate: Mapping[str, Any], keyword_metadata: Mapping[str, Mapping[str, Any]]
) -> dict:
    """Scan final candidate text and return authoritative keyword assignments."""
    fields = _candidate_fields(candidate)
    assignments: list[dict[str, str]] = []
    l1_title_hits: set[str] = set()
    l2_bullet_slots: set[str] = set()
    l3_backend_terms: set[str] = set()

    for metadata_key, metadata in keyword_metadata.items():
        keyword = str(metadata.get("keyword") or metadata_key or "").strip()
        normalized_keyword = _normalize_keyword(keyword)
        if not normalized_keyword:
            continue

        tier = _metadata_tier(metadata)
        protocol_source = str(
            metadata.get("source") or metadata.get("protocol_source") or "unknown"
        ).strip() or "unknown"
        pattern = _phrase_pattern(normalized_keyword)

        for field, texts in fields.items():
            if not any(text and pattern.search(text) for text in texts):
                continue

            row = dict(metadata)
            row.update(
                {
                    "keyword": keyword,
                    "normalized_keyword": normalized_keyword,
                    "tier": tier,
                    "field": field,
                    "assigned_fields": [field],
                    "match_type": "exact_phrase",
                    "source": "final_text_reconciliation",
                    "protocol_source": protocol_source,
                    "traffic_tier": tier,
                }
            )
            assignments.append(row)

            if tier == "L1" and field == "title":
                l1_title_hits.add(normalized_keyword)
            elif tier == "L2" and field.startswith("bullet_"):
                l2_bullet_slots.add(field)
            elif tier == "L3" and field == "search_terms":
                l3_backend_terms.add(normalized_keyword)

    return {
        "status": "complete",
        "assignments": assignments,
        "coverage": {
            "l1_title_hits": len(l1_title_hits),
            "l2_bullet_slots": len(l2_bullet_slots),
            "l3_backend_terms": len(l3_backend_terms),
        },
        "warnings": [],
    }
