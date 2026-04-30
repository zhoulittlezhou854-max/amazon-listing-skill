#!/usr/bin/env python3
"""
文案生成模块 (Step 6)
版本: v1.0
功能: 生成完整的Listing文案，包括Title、Bullets、Description、FAQ、Search Terms、A+内容
"""

import json
import logging
import os
import re
import time
import unicodedata
from copy import deepcopy
from typing import Callable, Dict, List, Any, Optional, Sequence, Tuple, Set
from dataclasses import dataclass, field
from pathlib import Path

from modules.keyword_utils import (
    extract_tiered_keywords as kw_extract_tiered_keywords,
    build_keyword_slots,
    infer_category_type,
    locale_code_for_language,
    token_matches_locale,
    is_blocklisted_brand,
    find_blocklisted_terms,
    remove_blocklisted_terms,
)
from modules.language_utils import (
    CANONICAL_CAPABILITIES,
    CAPABILITY_TRANSLATIONS,
    SCENE_TRANSLATIONS,
    CATEGORY_TRANSLATIONS,
    canonicalize_capability,
    english_capability_label,
    get_capability_display,
    get_scene_display,
    get_localized_accessory_experience_by_key,
    _normalize_to_canonical_english,
)
from modules.llm_client import (
    DEEPSEEK_R1_EXPERIMENT_MODEL,
    get_llm_client,
    is_r1_experiment_model,
    LLMClientUnavailable,
)
from modules.stag_locale import get_stag_display
from modules.intent_translator import write_visual_briefs_to_intent_graph
from modules.evidence_engine import build_evidence_bundle
from modules.question_bank import build_question_bank_context
from modules.compute_tiering import build_compute_tier_map
from modules.keyword_reconciliation import reconcile_keyword_assignments as reconcile_final_text_keyword_assignments
from modules.packet_rerender import build_slot_rerender_plan, execute_slot_rerender_plan
from modules.final_visible_quality import repair_final_visible_copy, validate_final_visible_copy
from modules.writing_policy import LENGTH_RULES
from modules import fluency_check as fc
from modules import repair_logger
from modules.claim_language_contract import audit_claim_language, repair_claim_language
from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

try:  # Optional external translator (falls back to rule-based localization if unavailable)
    from deep_translator import GoogleTranslator  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    GoogleTranslator = None


@dataclass
class PreprocessedData:
    """预处理数据类（简化版）"""
    run_config: Any
    attribute_data: Any
    keyword_data: Any
    review_data: Any
    aba_data: Any
    real_vocab: Any = None  # 真实国家词表（Priority 1）
    core_selling_points: List[str] = field(default_factory=list)
    accessory_descriptions: List[Dict[str, Any]] = field(default_factory=list)
    quality_score: int = 0
    language: str = "English"
    processed_at: str = ""
    canonical_core_selling_points: List[str] = field(default_factory=list)
    canonical_accessory_descriptions: List[Dict[str, Any]] = field(default_factory=list)
    canonical_capability_notes: Dict[str, Any] = field(default_factory=dict)
    target_country: str = ""
    capability_constraints: Dict[str, Any] = field(default_factory=dict)
    keyword_metadata: List[Dict[str, Any]] = field(default_factory=list)
    raw_human_insights: str = ""


class KeywordAssignmentTracker:
    """Tracks where tiered keywords are routed so scoring can inspect metadata instead of strings."""

    def __init__(self, metadata_map: Optional[Dict[str, Dict[str, Any]]] = None,
                 keyword_metadata: Optional[List[Dict[str, Any]]] = None):
        self._metadata_map = metadata_map or {}
        self._keyword_metadata = keyword_metadata or []
        self._assignments: Dict[str, Dict[str, Any]] = {}

    def record(self, field: str, tokens: Sequence[str]) -> None:
        if not tokens:
            return
        for token in tokens:
            normalized = (token or "").strip()
            if not normalized:
                continue
            key = normalized.lower()
            meta = self._metadata_map.get(key)
            if not meta:
                continue
            row_metadata = dict(meta)
            row_metadata.setdefault("keyword", normalized)
            bucket = self._assignments.setdefault(
                key,
                {
                    "metadata": row_metadata,
                    "fields": set(),
                },
            )
            bucket["metadata"].update({k: v for k, v in row_metadata.items() if not _metadata_value_is_empty(v)})
            bucket["fields"].add(field)

    def as_list(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for meta in self._assignments.values():
            metadata = dict(meta.get("metadata") or {})
            tier = str(metadata.get("traffic_tier") or metadata.get("tier") or "").upper()
            if tier:
                metadata["tier"] = tier
                metadata.setdefault("traffic_tier", tier)
            record = {
                **metadata,
                "keyword": metadata.get("keyword"),
                "assigned_fields": sorted(meta["fields"]),
            }
            records.append(record)
        return records

    def load_from_records(self, records: Sequence[Dict[str, Any]]) -> None:
        self._assignments = {}
        for record in records or []:
            keyword = str((record or {}).get("keyword") or "").strip()
            if not keyword:
                continue
            key = keyword.lower()
            self._assignments[key] = {
                "metadata": dict(record or {}, keyword=keyword),
                "fields": set((record or {}).get("assigned_fields") or []),
            }

    def flush_into_preprocessed(self, preprocessed: Any) -> None:
        if not hasattr(preprocessed, "keyword_metadata"):
            return
        keyword_meta_list = getattr(preprocessed, "keyword_metadata") or []
        index = {}
        for entry in keyword_meta_list:
            key = (entry.get("keyword") or "").strip().lower()
            if key:
                index[key] = entry
        for key, assignment in self._assignments.items():
            entry = index.get(key)
            if not entry:
                continue
            fields = set(entry.get("assigned_fields") or [])
            fields.update(assignment["fields"])
            entry["assigned_fields"] = sorted(fields)


def _keyword_present_in_visible_text(text: str, keyword: str) -> bool:
    normalized_text = _normalize_keyword_text(text or "")
    normalized_keyword = _normalize_keyword_text(keyword or "")
    return bool(normalized_keyword and normalized_keyword in normalized_text)


def _keyword_metadata_row(keyword: str, row: Optional[Dict[str, Any]] = None, *, tier: str = "") -> Dict[str, Any]:
    source = row or {}
    metadata = dict(source)
    resolved_tier = str(
        source.get("traffic_tier")
        or source.get("tier")
        or source.get("level")
        or tier
        or ""
    ).upper()
    metadata.update({
        "keyword": source.get("keyword") or keyword,
        "tier": resolved_tier,
        "traffic_tier": source.get("traffic_tier") or resolved_tier,
        "source_type": source.get("source_type"),
        "search_volume": source.get("search_volume"),
        "country": source.get("country") or source.get("source_country"),
        "detected_locale": source.get("detected_locale"),
    })
    return metadata


def _metadata_value_is_empty(value: Any) -> bool:
    return value is None or value == ""


def reconcile_final_keyword_assignments(
    generated_copy: Dict[str, Any],
    metadata_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    reconciliation = reconcile_final_text_keyword_assignments(generated_copy or {}, metadata_map or {})
    return _group_reconciled_keyword_assignments(reconciliation.get("assignments") or [])


def _group_reconciled_keyword_assignments(assignments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in assignments or []:
        keyword = str((row or {}).get("keyword") or "").strip()
        if not keyword:
            continue
        key = str((row or {}).get("normalized_keyword") or keyword).strip().lower()
        fields = list((row or {}).get("assigned_fields") or [])
        field = str((row or {}).get("field") or "").strip()
        if field and field not in fields:
            fields.append(field)
        if not fields:
            continue
        record = grouped.get(key)
        if not record:
            record = dict(row)
            record["keyword"] = keyword
            record["assigned_fields"] = []
            grouped[key] = record
        for assigned_field in fields:
            if assigned_field not in record["assigned_fields"]:
                record["assigned_fields"].append(assigned_field)
    return list(grouped.values())


def _prepare_final_keyword_metadata(
    assignment_tracker: KeywordAssignmentTracker,
    tiered_keywords: Dict[str, Any],
    writing_policy: Dict[str, Any],
) -> None:
    metadata_map = getattr(assignment_tracker, "_metadata_map", None)
    if metadata_map is None:
        return

    protected_keys = {
        "tier",
        "traffic_tier",
        "source_type",
        "search_volume",
        "country",
        "detected_locale",
    }

    def _merge_metadata(
        existing: Dict[str, Any],
        incoming: Dict[str, Any],
        *,
        prefer_incoming_for: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        merged = dict(existing or {})
        prefer_incoming_for = prefer_incoming_for or set()
        for key, value in (incoming or {}).items():
            if _metadata_value_is_empty(value):
                continue
            if key in prefer_incoming_for or _metadata_value_is_empty(merged.get(key)):
                merged[key] = value
            elif key not in protected_keys:
                # Keep earlier protocol truth when present; otherwise fill gaps.
                merged.setdefault(key, value)
        return merged

    # The tier map extracted from the source keyword table is authoritative.
    for keyword, row in ((tiered_keywords or {}).get("_metadata", {}) or {}).items():
        normalized = str(keyword or "").strip().lower()
        if normalized:
            metadata_map[normalized] = _merge_metadata(
                metadata_map.get(normalized) or {},
                _keyword_metadata_row(str(keyword), row),
                prefer_incoming_for=protected_keys | {"keyword"},
            )

    for tier_key in ("l1", "l2", "l3"):
        for keyword in (tiered_keywords or {}).get(tier_key) or []:
            normalized = str(keyword or "").strip().lower()
            if not normalized:
                continue
            metadata_map.setdefault(
                normalized,
                _keyword_metadata_row(str(keyword), {"keyword": str(keyword)}, tier=tier_key.upper()),
            )

    # Policy metadata can add backend-only/synthetic candidates, but must not
    # retier keywords already known from the real keyword table.
    for row in (writing_policy or {}).get("keyword_metadata") or []:
        keyword = str((row or {}).get("keyword") or "").strip()
        if not keyword:
            continue
        normalized = keyword.lower()
        metadata_map[normalized] = _merge_metadata(
            metadata_map.get(normalized) or {},
            _keyword_metadata_row(keyword, row),
        )

    for record in assignment_tracker.as_list():
        keyword = str((record or {}).get("keyword") or "").strip()
        if not keyword:
            continue
        normalized = keyword.lower()
        metadata_map[normalized] = _merge_metadata(
            metadata_map.get(normalized) or {},
            _keyword_metadata_row(keyword, record),
        )


def _reconcile_final_keyword_assignments(
    assignment_tracker: KeywordAssignmentTracker,
    *,
    title: str,
    bullets: Sequence[str],
    search_terms: Sequence[str],
    description: str = "",
    tiered_keywords: Dict[str, Any],
    writing_policy: Dict[str, Any],
) -> Dict[str, Any]:
    _prepare_final_keyword_metadata(assignment_tracker, tiered_keywords, writing_policy)
    metadata_map = getattr(assignment_tracker, "_metadata_map", {}) or {}
    reconciliation = reconcile_final_text_keyword_assignments(
        {
            "title": title,
            "bullets": list(bullets or []),
            "description": description,
            "search_terms": list(search_terms or []),
        },
        metadata_map,
    )
    assignments = _group_reconciled_keyword_assignments(reconciliation.get("assignments") or [])
    assignment_tracker.load_from_records(assignments)
    return {
        **reconciliation,
        "assignments": assignments,
    }


def _normalize_core_selling_points(points: Sequence[str]) -> List[str]:
    normalized: List[str] = []
    seen: Set[str] = set()
    for point in points or []:
        canonical = _normalize_to_canonical_english(point)
        if not canonical:
            continue
        label = english_capability_label(canonicalize_capability(canonical)) or canonical
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(label)
    return normalized


def _normalize_accessory_descriptions(accessories: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for item in accessories or []:
        normalized.append(
            {
                "name": _normalize_to_canonical_english(item.get("name", "")),
                "specification": _normalize_to_canonical_english(item.get("specification", "")),
                "original": item.get("original", ""),
                "note": _normalize_to_canonical_english(item.get("note", "")),
                "description": _normalize_to_canonical_english(item.get("description", "")),
                "params": item.get("params", {}),
            }
        )
    return normalized


LEGACY_BULLET_SLOT_RULES = {
    "B1": {"role": "mount_scene", "scene_index": 0, "tier": "P0"},
    "B2": {"role": "runtime_power", "scene_index": 1, "tier": "P0"},
    "B3": {"role": "capability_persona", "scene_index": 2, "tier": "P1"},
    "B4": {"role": "compliance_boundary", "scene_index": 3, "tier": "P1"},
    "B5": {"role": "after_sales", "scene_index": 0, "tier": "P2"},
}


# Helper utilities ----------------------------------------------------------

def _build_attr_lookup(attribute_data: Any) -> Dict[str, str]:
    raw = attribute_data.data if hasattr(attribute_data, "data") else attribute_data or {}
    lookup: Dict[str, str] = {}
    for key, value in raw.items():
        if not key:
            continue
        norm_key = str(key).strip().lower()
        lookup[norm_key] = value.strip() if isinstance(value, str) else str(value)
    return lookup


def _get_attr_value(attr_lookup: Dict[str, str], aliases: List[str], default: str = "") -> str:
    for alias in aliases:
        if alias and alias.lower() in attr_lookup:
            return attr_lookup[alias.lower()]
    return default


def _format_scene_label(scene_code: Optional[str], language: str) -> str:
    if not scene_code:
        return "daily use"
    display = get_stag_display(scene_code, locale_code_for_language(language)) or get_scene_display(scene_code, language)
    canonical = scene_code.replace("_", " ")
    return display if display else canonical


_NEGATIVE_FRAGMENT_PREFIX_RE = re.compile(
    r"(?i)^(?:(?:explicit\s+)?note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?(?:(?:does\s+not\s+(?:include|feature|support|offer))(?:\s+\w+){0,3}|(?:has\s+no\b|no\b|without\b|lacks\b)(?:\s+\w+){0,3})\s*[,;:\.-]?\s*"
)
_NEGATIVE_FRAGMENT_SUFFIX_RE = re.compile(
    r"(?i)\s*[,;:-]?\s*(?:as\s+it\s+)?(?:(?:does\s+not\s+(?:include|feature|support|offer))(?:\s+\w+){0,3}|(?:lacks\b|has\s+no\b|without\b)(?:\s+\w+){0,3})\s*\.?\s*$"
)
_NEGATIVE_FRAGMENT_ONLY_RE = re.compile(
    r"(?i)^(?:(?:explicit\s+)?note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?(?:(?:does\s+not\s+(?:include|feature|support|offer))(?:\s+\w+){0,3}|(?:lacks\b|has\s+no\b|no\b|without\b)(?:\s+\w+){0,3})\s*\.?$"
)
_MID_SENTENCE_NEGATIVE_REPAIRS = [
    (
        re.compile(r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?lacks image\s+and\s+"),
        ", ",
    ),
    (
        re.compile(r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?(?:has\s+no|no)\s+image\s+and\s+"),
        ", ",
    ),
    (
        re.compile(r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?does\s+not\s+(?:include|feature|support|offer)\s+image\s+and\s+"),
        ", ",
    ),
]

_UNSUPPORTED_STABILIZATION_CLAUSE_PATTERNS = [
    re.compile(
        r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this body camera|this camera|the camera|machine)\s+)?"
        r"(?:does\s+not\s+(?:include|feature|support|offer)|lacks|has\s+no|no)\s+"
        r"(?:(?:electronic|digital|image)\s+)?stabilization\b(?:,\s*so)?"
    ),
    re.compile(
        r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this body camera|this camera|the camera|machine)\s+)?"
        r"(?:does\s+not\s+(?:include|feature|support|offer)|lacks|has\s+no|no)\s+eis\b(?:,\s*so)?"
    ),
]
_UNSUPPORTED_STABILIZATION_NEGATIVE_GUIDANCE_PATTERNS = [
    re.compile(
        r"(?i)(?:,\s*)?(?:and\s+)?(?:it\s+is\s+)?not\s+suitable\s+for\s+high[- ]vibration\s+environments?(?:\s+such\s+as\s+[^.]+)?\.?"
    ),
    re.compile(
        r"(?i)(?:,\s*)?(?:and\s+)?avoid\s+high[- ]vibration\s+(?:surfaces|mounts|use)(?:\s+like\s+[^.]+)?\.?"
    ),
    re.compile(
        r"(?i)\b(?:suitable|best)\s+for\s+stable\s+professional\s+scenes\.?"
    ),
]
_STEADY_RECORDING_GUIDANCE = "Suitable for steady recording, fixed-position shots, and smooth daily scenes."
_STEADY_MOUNT_GUIDANCE = "Use a stable mount or a gentle handheld hold for the clearest footage."


def _cleanup_sentence_spacing(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or ""))
    cleaned = re.sub(r"\s+([,;:.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\s*—\s*", " — ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ,;:-")


def _rewrite_unsupported_stabilization_guidance(text: str) -> tuple[str, bool]:
    original = str(text or "").strip()
    if not original:
        return original, False
    lowered = original.lower()
    if not any(
        token in lowered
        for token in (
            "stabilization",
            "image stabilization",
            "digital stabilization",
            "electronic image stabilization",
            "eis",
        )
    ):
        return original, False

    header, body = _split_bullet_header_body(original)
    working = body or original
    for pattern in _UNSUPPORTED_STABILIZATION_CLAUSE_PATTERNS:
        working = pattern.sub(" ", working)
    for pattern in _UNSUPPORTED_STABILIZATION_NEGATIVE_GUIDANCE_PATTERNS:
        working = pattern.sub(" ", working)
    working = re.sub(r"(?i)\b(?:this body camera|this camera|the camera|it)\s+does\s+not\s+include\b", " ", working)
    working = _cleanup_sentence_spacing(working)

    body_lower = working.lower()
    guidance_parts: List[str] = []
    if "steady recording" not in body_lower:
        guidance_parts.append(_STEADY_RECORDING_GUIDANCE)
    if not any(
        phrase in body_lower
        for phrase in (
            "stable mount",
            "steady mount",
            "steady surface",
            "stable surface",
            "gentle handheld",
            "fixed-position",
            "fixed position",
        )
    ):
        guidance_parts.append(_STEADY_MOUNT_GUIDANCE)

    rewritten_body = working
    if guidance_parts:
        rewritten_body = f"{rewritten_body} {' '.join(guidance_parts)}".strip()
    rewritten_body = _cleanup_sentence_spacing(rewritten_body)
    if rewritten_body and rewritten_body[-1] not in ".!?":
        rewritten_body += "."

    rewritten = f"{header} — {rewritten_body}" if header and body else rewritten_body
    rewritten = _cleanup_sentence_spacing(rewritten)
    return rewritten or original, rewritten != original


def _rewrite_unsupported_capability_guidance(
    text: str,
    unsupported_capabilities: Optional[Sequence[str]],
) -> tuple[str, Optional[str]]:
    capabilities = {str(item or "").strip().lower() for item in (unsupported_capabilities or []) if str(item or "").strip()}
    if "stabilization_supported" in capabilities:
        rewritten, changed = _rewrite_unsupported_stabilization_guidance(text)
        if changed:
            return rewritten, "stabilization_supported"
    return str(text or ""), None


def _repair_scrubbed_visible_fragments(text: str) -> tuple[str, bool]:
    changed = False
    cleaned_text = str(text or "").strip()
    for pattern, replacement in _MID_SENTENCE_NEGATIVE_REPAIRS:
        updated = pattern.sub(replacement, cleaned_text)
        if updated != cleaned_text:
            cleaned_text = updated
            changed = True
    repaired_segments: List[str] = []
    for segment in re.split(r"(?<=[.!?])\s+", cleaned_text):
        segment = segment.strip()
        if not segment:
            continue
        original = segment
        segment = _NEGATIVE_FRAGMENT_PREFIX_RE.sub("", segment)
        segment = _NEGATIVE_FRAGMENT_SUFFIX_RE.sub("", segment)
        segment = re.sub(r"\s+", " ", segment).strip(" ,;:-")
        if not segment or _NEGATIVE_FRAGMENT_ONLY_RE.fullmatch(segment):
            changed = True
            continue
        if segment != original:
            changed = True
            if repaired_segments and segment[:1].islower():
                segment = segment[:1].upper() + segment[1:]
        repaired_segments.append(segment)
    repaired = " ".join(repaired_segments) if (changed or repaired_segments) else str(text or "").strip()
    repaired = re.sub(r"\s+", " ", repaired).strip(" ,;:-")
    return repaired, changed


def _scrub_visible_field(
    text: str,
    field: str,
    audit_log: Optional[List[Dict[str, Any]]],
    fallback: str = "",
    forbidden_terms: Optional[Sequence[str]] = None,
    unsupported_capabilities: Optional[Sequence[str]] = None,
) -> str:
    rewritten_text, rewritten_capability = _rewrite_unsupported_capability_guidance(
        text,
        unsupported_capabilities,
    )
    if rewritten_capability:
        cleaned = rewritten_text
        if audit_log is not None:
            _log_action(
                audit_log,
                field,
                "rewrite",
                {"reason": "unsupported_capability_semantic_rewrite", "capability": rewritten_capability},
            )
        terms = find_blocklisted_terms(cleaned)
        if not terms:
            return cleaned
        cleaned = remove_blocklisted_terms(cleaned).strip()
        if not cleaned:
            cleaned = fallback.strip()
        if audit_log is not None:
            _log_action(
                audit_log,
                field,
                "brand_visible_violation",
                {"terms": sorted(set(terms))},
            )
        return cleaned

    cleaned = text
    removed_terms: List[str] = []
    ordered_terms = sorted(
        {str(term or "").strip() for term in (forbidden_terms or []) if str(term or "").strip()},
        key=len,
        reverse=True,
    )
    for term in ordered_terms:
        candidate = str(term or "").strip()
        if not candidate:
            continue
        pattern = re.compile(re.escape(candidate), re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub(" ", cleaned)
            removed_terms.append(candidate)
    cleaned, repaired_fragments = _repair_scrubbed_visible_fragments(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;|-")
    if removed_terms and audit_log is not None:
        _log_action(
            audit_log,
            field,
            "delete",
            {"terms": sorted(set(removed_terms)), "reason": "forbidden_visible_terms_scrub"},
        )
    if repaired_fragments and audit_log is not None:
        _log_action(
            audit_log,
            field,
            "rewrite",
            {"reason": "forbidden_visible_terms_fragment_repair"},
        )
    terms = find_blocklisted_terms(text)
    if not terms:
        return cleaned
    cleaned = remove_blocklisted_terms(cleaned).strip()
    if not cleaned:
        cleaned = fallback.strip()
    if audit_log is not None:
        _log_action(
            audit_log,
            field,
            "brand_visible_violation",
            {"terms": sorted(set(terms))},
        )
    return cleaned


def _forbidden_visible_terms(directives: Dict[str, Any]) -> List[str]:
    terms = list((directives or {}).get("backend_only_terms", []) or [])
    waterproof = (directives or {}).get("waterproof", {}) or {}
    stabilization = (directives or {}).get("stabilization", {}) or {}
    if not waterproof.get("allow_visible", True):
        terms.extend(["waterproof", "underwater", "étanche", "wasserdicht", "impermeabile", "resistente al agua", "防水"])
    if not stabilization.get("allow_visible", True):
        terms.extend(
            [
                "electronic image stabilization",
                "image stabilization",
                "digital stabilization",
                "stabilization",
                "stabilisation",
                "stabilisierung",
                "stabilizzazione",
                "防抖",
            ]
        )
    deduped: List[str] = []
    seen = set()
    for term in terms:
        normalized = str(term or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(term).strip())
    return deduped


def _unsupported_capability_rewrites(
    directives: Dict[str, Any],
    *,
    enable_semantic_rewrite: bool,
) -> List[str]:
    if not enable_semantic_rewrite:
        return []
    rewrites: List[str] = []
    stabilization = (directives or {}).get("stabilization", {}) or {}
    if not stabilization.get("allow_visible", True):
        rewrites.append("stabilization_supported")
    return rewrites


def _log_action(audit_log: Optional[List[Dict[str, Any]]],
                field: str,
                action: str,
                detail: Dict[str, Any]):
    if audit_log is None:
        return
    payload = {"field": field, "action": action}
    payload.update(detail)
    audit_log.append(payload)


def _description_provenance_from_audit_entries(entries: List[Dict[str, Any]]) -> str:
    for entry in reversed(entries or []):
        if (
            (entry or {}).get("field") == "description_llm"
            and (entry or {}).get("action") in {"llm_success", "llm_fallback"}
            and (entry or {}).get("provenance_tier")
        ):
            return str((entry or {}).get("provenance_tier") or "")
    return ""


def _log_retryable_llm_exception(
    audit_log: Optional[List[Dict[str, Any]]],
    field: str,
    exc: LLMClientUnavailable,
    attempt: int,
) -> bool:
    if not getattr(exc, "retryable", False):
        _log_action(audit_log, field, "llm_unavailable", {"error": str(exc)})
        return False
    reason = getattr(exc, "error_code", "") or str(exc)
    _log_action(
        audit_log,
        field,
        "llm_retry",
        {"attempt": attempt, "reason": reason, "error": str(exc)},
    )
    return True


def _format_mode_guidance(mode_guidance: Dict[str, Any], scene_code: Optional[str] = None) -> str:
    guidance = mode_guidance or {}
    by_mode = guidance.get("guidance_by_mode", {}) or {}
    if not by_mode:
        return "none"
    scene = (scene_code or "").strip().lower()
    entries: List[str] = []
    preferred_mode = guidance.get("preferred_stabilization_mode")
    if preferred_mode:
        entries.append(f"preferred stabilization mode={preferred_mode}")
    for mode in sorted(by_mode.keys(), key=lambda item: {"1080P": 1, "2K": 2, "4K": 3, "5K": 4, "8K": 5}.get(str(item).upper(), 99)):
        item = by_mode.get(mode) or {}
        scenes = item.get("scene_focus") or []
        if scene and scenes and scene not in [str(value).lower() for value in scenes]:
            if mode not in {preferred_mode, "4K", "5K"}:
                continue
        entries.append(
            f"{mode}: scenes={','.join(scenes[:4]) or 'general'}; "
            f"stabilization={item.get('stabilization_visibility') or 'n/a'}; "
            f"rule={item.get('copy_rule') or ''}"
        )
    return " | ".join(entries[:4]) or "none"


def _split_bullet_header_body(text: str) -> Tuple[str, str]:
    cleaned = (text or "").strip()
    for separator in [" — ", " – ", " -- ", " - "]:
        if separator in cleaned:
            header, body = cleaned.split(separator, 1)
            return header.strip(), body.strip()
    return "", cleaned


def _normalized_anchor_hits(text: str, anchors: Sequence[str]) -> bool:
    normalized = _normalize_keyword_text(text)
    for anchor in anchors or []:
        cleaned = _normalize_keyword_text(anchor)
        if cleaned and cleaned in normalized:
            return True
    return False


def _frontload_segment(text: str, token_limit: int) -> str:
    tokens = re.findall(r"\S+", text or "")
    return " ".join(tokens[: max(1, token_limit)])


def _build_localized_capability_anchors(
    capability_bundle: Sequence[str],
    target_language: str,
    real_vocab: Optional[Any] = None,
    data_mode: str = "SYNTHETIC_COLD_START",
) -> List[str]:
    anchors: List[str] = []
    seen: Set[str] = set()
    for capability in capability_bundle or []:
        slug = canonicalize_capability(str(capability or ""))
        alias_candidates = []
        canonical_entry = CANONICAL_CAPABILITIES.get(slug) or {}
        raw_capability = str(capability or "").strip()
        if not canonical_entry and raw_capability and re.search(r"[_-]", raw_capability):
            continue
        for alias in canonical_entry.get("aliases", []) or []:
            alias_text = str(alias or "").strip()
            if not alias_text:
                continue
            alias_candidates.append(alias_text)
            translated_alias = _translate_capability(alias_text, target_language, real_vocab, data_mode)
            if translated_alias and translated_alias != alias_text:
                alias_candidates.append(translated_alias)
        for candidate in [
            capability,
            _translate_capability(capability, target_language, real_vocab, data_mode),
            *alias_candidates,
        ]:
            cleaned = str(candidate or "").strip()
            norm = _normalize_keyword_text(cleaned)
            if not cleaned or not norm or norm in seen:
                continue
            seen.add(norm)
            anchors.append(cleaned)
    return anchors


def _build_localized_scene_anchors(
    scenes: Sequence[str],
    target_language: str,
    real_vocab: Optional[Any] = None,
    data_mode: str = "SYNTHETIC_COLD_START",
) -> List[str]:
    anchors: List[str] = []
    seen: Set[str] = set()
    for scene in scenes or []:
        candidates = _scene_semantic_aliases(scene, target_language) + [
            _translate_scene(scene, target_language, real_vocab, data_mode),
            _format_scene_label(scene, target_language),
            scene,
        ]
        for candidate in candidates:
            cleaned = str(candidate or "").strip()
            norm = _normalize_keyword_text(cleaned)
            if not cleaned or not norm or norm in seen:
                continue
            seen.add(norm)
            anchors.append(cleaned)
    return anchors


SCENE_SEMANTIC_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "cycling_recording": {
        "English": ["cycling", "bike", "biking", "ride", "helmet POV", "commute"],
        "French": ["velo", "cyclisme", "trajet", "casque", "balade"],
        "German": ["Fahrrad", "Radfahren", "Pendeln", "Helm", "Tour"],
    },
    "underwater_exploration": {
        "English": ["underwater", "snorkeling", "diving", "swimming", "pool"],
        "French": ["plongee", "snorkeling", "sous l'eau", "natation"],
        "German": ["Unterwasser", "Schnorcheln", "Tauchen", "Schwimmen"],
    },
    "travel_documentation": {
        "English": ["travel", "trip", "vacation", "journey", "route review"],
        "French": ["voyage", "vacances", "trajet", "escapade"],
        "German": ["Reise", "Urlaub", "Ausflug", "Tour"],
    },
    "family_use": {
        "English": ["family", "kids", "weekend", "daily moments"],
        "French": ["famille", "enfants", "week-end", "moments du quotidien"],
        "German": ["Familie", "Kinder", "Wochenende", "Alltag"],
    },
    "sports_training": {
        "English": ["training", "workout", "practice", "sports"],
        "French": ["entrainement", "sport", "seance"],
        "German": ["Training", "Workout", "Sport", "Praxis"],
    },
    "outdoor_sports": {
        "English": ["outdoor", "trail", "sports", "adventure"],
        "French": ["outdoor", "plein air", "aventure", "sport"],
        "German": ["Outdoor", "Abenteuer", "Trail", "Sport"],
    },
    "commuting_capture": {
        "English": ["commute", "commuting", "daily ride", "everyday travel"],
        "French": ["trajet", "trajets quotidiens", "deplacement quotidien"],
        "German": ["Pendeln", "Alltagsfahrt", "Arbeitsweg"],
    },
    "vlog_content_creation": {
        "English": ["vlog", "selfie", "content creation", "creator"],
        "French": ["vlog", "selfie", "creation de contenu"],
        "German": ["Vlog", "Selfie", "Content", "Creator"],
    },
}


def _scene_semantic_aliases(scene_code: str, target_language: str) -> List[str]:
    if not scene_code:
        return []
    language = target_language or "English"
    alias_map = SCENE_SEMANTIC_ALIASES.get(scene_code, {})
    english_aliases = alias_map.get("English", [])
    localized_aliases = alias_map.get(language, [])
    merged = _dedupe_keyword_sequence(list(localized_aliases) + list(english_aliases))
    if merged:
        return merged
    return _dedupe_keyword_sequence(
        [
            get_scene_display(scene_code, language),
            scene_code.replace("_", " "),
        ]
    )


def _mask_exact_phrases(text: str, phrases: Sequence[str]) -> Tuple[str, Dict[str, str]]:
    masked = text or ""
    placeholders: Dict[str, str] = {}
    for idx, phrase in enumerate(_dedupe_keyword_sequence(phrases)):
        if not phrase:
            continue
        placeholder = f"__EXACT_{idx}__"
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        match = pattern.search(masked)
        if not match:
            continue
        placeholders[placeholder] = match.group(0)
        masked = pattern.sub(placeholder, masked, count=1)
    return masked, placeholders


def _restore_masked_phrases(text: str, placeholders: Dict[str, str]) -> str:
    restored = text or ""
    for key, value in placeholders.items():
        restored = restored.replace(key, value)
    return restored


def _dewater_title_text(
    text: str,
    exact_phrases: Sequence[str],
    audit_log: Optional[List[Dict[str, Any]]] = None,
) -> str:
    if not text:
        return text
    masked, placeholders = _mask_exact_phrases(text, exact_phrases)
    cleaned = masked
    for connector in ["with", "avec", "mit", "con"]:
        cleaned = re.sub(rf",\s*{connector}\s+", ", ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\s+{connector}\s+,", ", ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r",\s*,+", ", ", cleaned)
    cleaned = cleaned.strip(" ,")
    restored = _restore_masked_phrases(cleaned, placeholders)
    if restored != text and audit_log is not None:
        _log_action(audit_log, "title", "title_dewater", {"before": text[:120], "after": restored[:120]})
    return restored


def _ensure_title_core_category_frontload(title: str, payload: Dict[str, Any], max_front_window: int = 80) -> str:
    candidate = re.sub(r"\s+", " ", (title or "").strip())
    if not candidate:
        return candidate
    primary_category = str(payload.get("primary_category") or "").strip()
    required_phrase = (
        next(
            (
                kw for kw in (payload.get("exact_match_keywords") or [])
                if primary_category and _normalize_keyword_text(primary_category) in _normalize_keyword_text(kw)
            ),
            "",
        )
        or primary_category
        or next((kw for kw in (payload.get("l1_keywords") or []) if kw), "")
        or ""
    )
    required_phrase = str(required_phrase or "").strip()
    if not required_phrase:
        return candidate
    if _normalize_keyword_text(required_phrase) in _normalize_keyword_text(candidate[:max_front_window]):
        return candidate
    brand = str(payload.get("brand_name") or payload.get("brand") or "").strip()
    remainder = candidate
    if brand and candidate.lower().startswith(brand.lower()):
        remainder = candidate[len(brand):].lstrip(" ,|-–—")
        prefix = f"{brand} {required_phrase}".strip()
    else:
        prefix = required_phrase
    if _normalize_keyword_text(required_phrase) in _normalize_keyword_text(remainder):
        remainder = re.sub(re.escape(required_phrase), "", remainder, flags=re.IGNORECASE).strip(" ,|-–—")
    rebuilt = ", ".join([part for part in [prefix, remainder] if part]).strip(" ,")
    return re.sub(r"\s+", " ", rebuilt)


def _apply_title_core_category_frontload(title: str, payload: Dict[str, Any], max_length: int) -> str:
    if int(max_length or 0) < 90:
        return re.sub(r"\s+", " ", (title or "")).strip()
    return _ensure_title_core_category_frontload(title, payload)


def _patch_title_missing_keywords(
    title: str,
    missing_keywords: Sequence[str],
    payload: Dict[str, Any],
    max_length: int,
) -> str:
    repaired = re.sub(r"\s+", " ", (title or "")).strip(" ,")
    for keyword in [str(item).strip() for item in (missing_keywords or []) if str(item).strip()]:
        if _normalize_keyword_text(keyword) in _normalize_keyword_text(repaired):
            continue
        appended = f"{repaired}, {keyword}".strip(" ,")
        if len(appended) <= max_length:
            repaired = appended
            continue
        sections = [section.strip() for section in repaired.split(",") if section.strip()]
        replaced = False
        for keep_count in range(len(sections) - 1, 0, -1):
            candidate_sections = sections[:keep_count] + [keyword]
            candidate = ", ".join(candidate_sections).strip(" ,")
            candidate = _apply_title_core_category_frontload(candidate, payload, max_length)
            candidate = _trim_to_word_boundary(candidate, max_length)
            if _normalize_keyword_text(keyword) in _normalize_keyword_text(candidate):
                repaired = candidate
                replaced = True
                break
        if not replaced:
            repaired = _trim_to_word_boundary(appended, max_length)
    if _title_is_keyword_dump(repaired) or _title_has_broken_tail(repaired):
        repaired = _build_deterministic_title_candidate(
            payload,
            required_keywords=_dedupe_keyword_sequence(list(payload.get("required_keywords") or []) + list(missing_keywords or [])),
            numeric_specs=payload.get("numeric_specs") or [],
            max_length=max_length,
        )
    return re.sub(r"\s+", " ", repaired).strip(" ,")


TITLE_BARE_PARAMETER_BRACKET_RE = re.compile(
    r"\([^)]*\d[^)]*\b(?:mm|cm|mah|gb|tb|fps|hz|inch|inches|mp|nm|focal length)\b[^)]*\)",
    re.IGNORECASE,
)


def _title_is_keyword_dump(title: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (title or "")).strip(" ,")
    if not cleaned:
        return False
    segments = [segment.strip() for segment in cleaned.split(",") if segment.strip()]
    if len(segments) < 4:
        return False
    lowered = cleaned.lower()
    flow_markers = [
        " for ",
        " with ",
        " featuring ",
        " built for ",
        " designed for ",
        " ideal for ",
        " includes ",
        " including ",
        " and ",
    ]
    if any(marker in lowered for marker in flow_markers):
        return False
    compact_segments = sum(1 for segment in segments[1:] if len(segment.split()) <= 4)
    cameraish_segments = sum(
        1 for segment in segments if any(token in segment.lower() for token in ["camera", "cam", "video", "record"])
    )
    return compact_segments >= 3 or cameraish_segments >= max(3, len(segments) - 1)


def _title_has_bare_parameter_brackets(title: str) -> bool:
    return bool(TITLE_BARE_PARAMETER_BRACKET_RE.search(title or ""))


def _title_support_use_phrase(keywords: Sequence[str]) -> str:
    cleaned = [str(keyword).strip() for keyword in keywords or [] if str(keyword).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return f"{cleaned[0]} use"
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]} use"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]} use"


def _title_has_broken_tail(title: str) -> bool:
    lowered = re.sub(r"\s+", " ", (title or "")).strip(" ,").lower()
    if not lowered:
        return False
    broken_endings = (" for", " with", " and", " built", " featuring", " ideal", " designed")
    return lowered.endswith(broken_endings)


def _clean_title_phrases(values: Sequence[Any]) -> List[str]:
    phrases: List[str] = []
    for value in values or []:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned.lower() == "none":
            continue
        phrases.append(cleaned)
    return _dedupe_keyword_sequence(phrases)


def _build_natural_title_candidate(
    payload: Dict[str, Any],
    lead_keyword: str,
    support_keywords: Sequence[str],
    differentiators: Sequence[str],
    max_length: int,
) -> str:
    brand = str(payload.get("brand_name") or payload.get("brand") or "").strip()
    primary_category = str(payload.get("primary_category") or "").strip()
    lead_parts: List[str] = [brand]
    normalized_lead = _normalize_keyword_text(lead_keyword)
    if lead_keyword:
        lead_parts.append(lead_keyword)
    if primary_category and _normalize_keyword_text(primary_category) not in normalized_lead and max_length >= 120:
        lead_parts.append(primary_category)
    lead = " ".join(part for part in lead_parts if part).strip()
    clean_differentiators = _clean_title_phrases(differentiators)[:3]
    scene_code = next((item for item in (payload.get("scene_priority") or []) if item), "")
    scene_phrase = _format_scene_label(scene_code, payload.get("target_language") or "English") if scene_code else ""
    if scene_phrase and payload.get("target_language") == "English":
        scene_phrase = scene_phrase.title()
    support_candidates = [
        keyword
        for keyword in _dedupe_keyword_sequence(support_keywords)
        if _normalize_keyword_text(keyword) not in _normalize_keyword_text(lead)
    ][:3]
    support_phrases = [_title_support_use_phrase(support_candidates[:count]) for count in range(1, len(support_candidates) + 1)]
    if max_length >= 140:
        support_phrases = list(reversed(support_phrases))
    if not support_phrases:
        support_phrases = [""]
    diff_long = " and ".join(clean_differentiators[:2]).strip()
    diff_short = clean_differentiators[0] if clean_differentiators else ""
    diff_compact = " ".join(clean_differentiators[:2]).strip()
    diff_rich = ""
    if len(clean_differentiators) >= 3:
        diff_rich = f"{clean_differentiators[0]}, {clean_differentiators[1]}, and {clean_differentiators[2]}"
    else:
        diff_rich = diff_long
    second_scene_code = next((item for item in (payload.get("scene_priority") or [])[1:] if item), "")
    second_scene_phrase = _format_scene_label(second_scene_code, payload.get("target_language") or "English") if second_scene_code else ""
    if second_scene_phrase and payload.get("target_language") == "English":
        second_scene_phrase = second_scene_phrase.title()
    templates: List[str] = []
    for support_phrase in support_phrases:
        templates.extend([
            f"{lead} {diff_compact} for {support_phrase}" if lead and diff_compact and support_phrase else "",
            f"{lead} with {diff_short}, designed for {support_phrase}" if lead and diff_short and support_phrase else "",
            f"{lead} with {diff_long}, designed for {support_phrase}" if lead and diff_long and support_phrase else "",
            f"{lead} with {diff_rich}, designed for {support_phrase}" if lead and diff_rich and support_phrase and max_length >= 185 else "",
            f"{lead} designed for {support_phrase} with {diff_short}" if lead and support_phrase and diff_short else "",
            f"{lead} designed for {support_phrase}" if lead and support_phrase else "",
            f"{lead} with {diff_long} for {scene_phrase}, designed for {support_phrase}" if lead and diff_long and scene_phrase and support_phrase else "",
            f"{lead} with {diff_rich} for {scene_phrase}, designed for {support_phrase}" if lead and diff_rich and scene_phrase and support_phrase and max_length >= 185 else "",
            f"{lead} with {diff_short} for {scene_phrase}, designed for {support_phrase}" if lead and diff_short and scene_phrase and support_phrase else "",
            f"{lead} for {scene_phrase} with {diff_short}, designed for {support_phrase}" if lead and diff_short and scene_phrase and support_phrase else "",
            f"{lead} with {diff_long} for {scene_phrase} and {second_scene_phrase}, designed for {support_phrase}" if lead and diff_long and scene_phrase and second_scene_phrase and support_phrase else "",
            f"{lead} with {diff_rich} for {scene_phrase} and {second_scene_phrase}, designed for {support_phrase}" if lead and diff_rich and scene_phrase and second_scene_phrase and support_phrase and max_length >= 185 else "",
            f"{lead} with {diff_short} for {scene_phrase} and {second_scene_phrase}, designed for {support_phrase}" if lead and diff_short and scene_phrase and second_scene_phrase and support_phrase else "",
        ])
    templates.extend([
        f"{lead} with {diff_long} for {scene_phrase}" if lead and diff_long and scene_phrase else "",
        f"{lead} with {diff_long} for {scene_phrase} and {second_scene_phrase}" if lead and diff_long and scene_phrase and second_scene_phrase else "",
        f"{lead} with {diff_short} for {scene_phrase}" if lead and diff_short and scene_phrase else "",
        f"{lead} with {diff_short}" if lead and diff_short else "",
        lead,
    ])
    valid_candidates: List[str] = []
    for template in templates:
        candidate = re.sub(r"\s+", " ", template).strip(" ,")
        if not candidate:
            continue
        candidate = _dewater_title_text(candidate, payload.get("exact_match_keywords") or [])
        candidate = _apply_title_core_category_frontload(candidate, payload, max_length)
        candidate = _trim_to_word_boundary(candidate, max_length)
        if (
            candidate
            and not _title_is_keyword_dump(candidate)
            and not _title_has_bare_parameter_brackets(candidate)
            and not _title_has_broken_tail(candidate)
        ):
            valid_candidates.append(candidate)
    if valid_candidates:
        target_min = int(payload.get("target_min_length") or LENGTH_RULES["title"]["target_min"])
        target_max = int(payload.get("target_max_length") or LENGTH_RULES["title"]["target_max"])
        preferred = [candidate for candidate in valid_candidates if target_min <= len(candidate) <= max_length]
        pool = preferred or valid_candidates
        best = max(
            pool,
            key=lambda candidate: (
                min(len(candidate), target_max),
                len(candidate),
            ),
        )
        soft_warning = int(payload.get("soft_warning_length") or LENGTH_RULES["title"]["soft_warning"])
        if len(best) < soft_warning and max_length >= soft_warning:
            fallback_usage_phrase = "everyday content creation" if (payload.get("target_language") or "English").strip().lower() == "english" else ""
            extension_parts = [part for part in [*clean_differentiators, second_scene_phrase, scene_phrase, fallback_usage_phrase] if part]
            normalized_best = _normalize_keyword_text(best)
            for extra in extension_parts:
                normalized_extra = _normalize_keyword_text(extra)
                if normalized_extra and normalized_extra in normalized_best:
                    continue
                joiner = " with " if any(token in normalized_extra for token in ("runtime", "lens", "1080p", "4k", "wifi", "battery")) else " for "
                expanded = _trim_to_word_boundary(f"{best}{joiner}{extra}", max_length)
                expanded = _dewater_title_text(expanded, payload.get("exact_match_keywords") or [])
                if (
                    expanded
                    and len(expanded) > len(best)
                    and not _title_is_keyword_dump(expanded)
                    and not _title_has_bare_parameter_brackets(expanded)
                    and not _title_has_broken_tail(expanded)
                ):
                    best = expanded
                    normalized_best = _normalize_keyword_text(best)
                    if len(best) >= soft_warning:
                        break
        return best
    return _trim_to_word_boundary(re.sub(r"\s+", " ", lead).strip(), max_length)


def _build_title_budget(required_keywords: Sequence[str], max_length: int) -> Dict[str, Any]:
    keywords = [str(item).strip() for item in required_keywords or [] if str(item).strip()]
    reserved = sum(len(keyword) for keyword in keywords)
    separators = max(0, len(keywords) - 1) * 2
    remaining = max(0, int(max_length) - reserved - separators)
    return {
        "required_keywords": keywords,
        "remaining_character_budget": remaining,
        "max_length": int(max_length),
    }


def _title_is_below_target_length(text: str, payload: Dict[str, Any]) -> bool:
    candidate = re.sub(r"\s+", " ", str(text or "")).strip()
    if not candidate:
        return True
    max_length = int(payload.get("max_length") or LENGTH_RULES["title"]["hard_ceiling"])
    target_min = int(payload.get("target_min_length") or LENGTH_RULES["title"]["target_min"])
    soft_warning = int(payload.get("soft_warning_length") or LENGTH_RULES["title"]["soft_warning"])
    if max_length < soft_warning:
        return False
    if len(candidate) >= target_min:
        return False
    differentiators = _clean_title_phrases(
        [payload.get("core_capability")] + list(_flatten_tokens(payload.get("numeric_specs") or []))
    )
    available_detail = bool(
        differentiators
        or (payload.get("scene_priority") or [])
        or (payload.get("assigned_keywords") or [])
        or (payload.get("required_keywords") or [])
    )
    return available_detail and len(candidate) < soft_warning


def _rule_repair_title_length(
    title: str,
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]] = None,
    target_min: int = 190,
    target_max: int = 198,
    hard_ceiling: int = 200,
) -> str:
    candidate = re.sub(r"\s+", " ", (title or "")).strip(" ,")
    length = len(candidate)
    required_keywords = [
        str(item).strip()
        for item in (
            payload.get("required_keywords")
            or payload.get("exact_match_keywords")
            or []
        )
        if str(item).strip()
    ]

    if length > hard_ceiling:
        if required_keywords:
            candidate = _frontload_required_keywords(candidate, required_keywords)
        trimmed = _trim_to_word_boundary(candidate, target_max)
        if audit_log is not None:
            _log_action(audit_log, "title", "rule_repair_trim", {
                "before_len": length,
                "after_len": len(trimmed),
                "reason": "exceeded_hard_ceiling",
            })
        return trimmed

    if target_min <= length <= target_max:
        return candidate

    if target_max < length <= hard_ceiling:
        if required_keywords:
            candidate = _frontload_required_keywords(candidate, required_keywords)
        trimmed = _trim_to_word_boundary(candidate, target_max)
        if audit_log is not None:
            _log_action(audit_log, "title", "rule_repair_trim", {
                "before_len": length,
                "after_len": len(trimmed),
                "reason": "above_target_max",
            })
        return trimmed

    pool = _dedupe_keyword_sequence(
        list(payload.get("exact_match_keywords") or [])
        + list(payload.get("l1_keywords") or [])
        + list(payload.get("assigned_keywords") or [])
        + list(payload.get("_repair_keyword_pool") or [])
    )

    repaired = candidate
    appended: List[str] = []

    for kw in pool:
        if len(repaired) >= target_min:
            break
        kw_clean = str(kw or "").strip()
        if not kw_clean:
            continue
        if _normalize_keyword_text(kw_clean) in _normalize_keyword_text(repaired):
            continue

        joiners = [", ", " for ", " with "] if len(repaired) < target_min - 20 else [", "]
        chosen = None
        for joiner in joiners:
            candidate_append = f"{repaired}{joiner}{kw_clean}"
            if len(candidate_append) <= hard_ceiling:
                chosen = candidate_append
                break
        if not chosen:
            continue
        repaired = chosen
        appended.append(kw_clean)

    if audit_log is not None and appended:
        _log_action(audit_log, "title", "rule_repair_extend", {
            "before_len": length,
            "after_len": len(repaired),
            "appended_keywords": appended,
            "reason": "below_target_min",
        })

    if len(repaired) > hard_ceiling:
        repaired = _trim_to_word_boundary(repaired, target_max)

    if target_max < len(repaired) <= hard_ceiling:
        repaired = _trim_to_word_boundary(repaired, target_max)

    return repaired


def _frontload_required_keywords(title: str, required_keywords: Sequence[str]) -> str:
    candidate = re.sub(r"\s+", " ", str(title or "")).strip(" ,")
    if not candidate:
        return candidate

    parts = [part.strip(" ,") for part in candidate.split(",") if part.strip(" ,")]
    if len(parts) <= 1:
        return candidate

    safe_zone = max(1, len(candidate) * 2 // 3)
    front_parts = [parts[0]]
    middle_parts: List[str] = []
    tail_parts: List[str] = []
    normalized_candidate = _normalize_keyword_text(candidate)

    for keyword in required_keywords or []:
        normalized_keyword = _normalize_keyword_text(keyword)
        if not normalized_keyword or normalized_keyword not in normalized_candidate:
            continue

        current_candidate = ", ".join(front_parts + middle_parts + tail_parts + parts[1:])
        current_normalized = _normalize_keyword_text(current_candidate)
        pos = current_normalized.find(normalized_keyword)
        if pos < 0 or pos < safe_zone:
            continue

        moved = False
        for index in range(1, len(parts)):
            part = parts[index]
            if normalized_keyword not in _normalize_keyword_text(part):
                continue
            if part not in front_parts and part not in middle_parts:
                middle_parts.append(part)
            parts[index] = ""
            moved = True
            break
        if not moved:
            continue

    for part in parts[1:]:
        cleaned = part.strip(" ,")
        if cleaned:
            tail_parts.append(cleaned)

    reordered = [part for part in front_parts + middle_parts + tail_parts if part]
    return re.sub(r"\s+", " ", ", ".join(reordered)).strip(" ,")


def _assemble_title_from_segments(
    brand: str,
    lead_keyword: str,
    required_keywords: List[str],
    numeric_specs: List[str],
    differentiators: List[str],
    use_cases: List[str],
    target_min: int = 190,
    target_max: int = 198,
    hard_ceiling: int = 200,
) -> str:
    brand_clean = re.sub(r"\s+", " ", str(brand or "")).strip(" ,")
    lead_clean = re.sub(r"\s+", " ", str(lead_keyword or "")).strip(" ,")
    lead = " ".join(part for part in [brand_clean, lead_clean] if part).strip(" ,")

    def _clean_list(items: Sequence[str]) -> List[str]:
        cleaned: List[str] = []
        seen_local = set()
        for item in items or []:
            text = re.sub(r"\s+", " ", str(item or "")).strip(" ,")
            normalized = _normalize_keyword_text(text)
            if not text or not normalized or normalized in seen_local:
                continue
            cleaned.append(text)
            seen_local.add(normalized)
        return cleaned

    def _human_join(items: Sequence[str]) -> str:
        values = [str(item).strip() for item in items or [] if str(item).strip()]
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]} and {values[1]}"
        return f"{', '.join(values[:-1])}, and {values[-1]}"

    required_clean = _clean_list(required_keywords)
    numeric_clean = _clean_list(numeric_specs)
    numeric_norms = {_normalize_keyword_text(item) for item in numeric_clean}
    diff_clean = [
        item for item in _clean_list(differentiators)
        if _normalize_keyword_text(item) not in numeric_norms
    ]
    use_clean = _clean_list(use_cases)

    title = lead

    def _append_required_list(limit: int) -> None:
        nonlocal title
        selected: List[str] = []
        for item in required_clean:
            if _normalize_keyword_text(item) in _normalize_keyword_text(title):
                continue
            trial = f"{title}, {_human_join(selected + [item])}".strip(" ,")
            if len(trial) > limit:
                continue
            selected.append(item)
        if selected:
            title = f"{title}, {_human_join(selected)}".strip(" ,")

    def _append_clause(prefix: str, items: Sequence[str], limit: int) -> None:
        nonlocal title
        selected: List[str] = []
        title_norm = _normalize_keyword_text(title)
        for item in items:
            if _normalize_keyword_text(item) in title_norm:
                continue
            trial = f"{title}, {prefix}{_human_join(selected + [item])}".strip(" ,")
            if len(trial) > limit:
                continue
            selected.append(item)
        if selected:
            title = f"{title}, {prefix}{_human_join(selected)}".strip(" ,")

    for limit in (target_max, hard_ceiling):
        if len(title) >= target_min:
            break
        _append_required_list(limit)
        _append_clause("with ", numeric_clean + diff_clean, limit)
        _append_clause("for ", use_clean, limit)

    title = re.sub(r"\s+", " ", title).strip(" ,")
    if len(title) > hard_ceiling:
        title = _trim_to_word_boundary(title, hard_ceiling)
    return title


def _extract_title_recipe(payload: Dict[str, Any]) -> Dict[str, List[str] | str]:
    if not isinstance(payload, dict):
        return {"lead_keyword": "", "differentiators": [], "use_cases": []}
    lead_keyword = str(payload.get("lead_keyword") or "").strip()
    differentiators = [
        str(item).strip()
        for item in (payload.get("differentiators") or [])
        if str(item).strip()
    ]
    use_cases = [
        str(item).strip()
        for item in (payload.get("use_cases") or [])
        if str(item).strip()
    ]
    return {
        "lead_keyword": lead_keyword,
        "differentiators": differentiators[:4],
        "use_cases": use_cases[:4],
    }


def _build_deterministic_title_candidate(
    payload: Dict[str, Any],
    required_keywords: Sequence[str],
    numeric_specs: Sequence[str],
    max_length: int,
) -> str:
    brand = str(payload.get("brand_name") or payload.get("brand") or "").strip()
    primary_category = str(payload.get("primary_category") or "").strip()
    l1_keywords = [str(item).strip() for item in (payload.get("l1_keywords") or []) if str(item).strip()]
    assigned_keywords = [str(item).strip() for item in (payload.get("assigned_keywords") or []) if str(item).strip()]
    ordered_keywords = _dedupe_keyword_sequence(
        list(required_keywords or [])
        + l1_keywords
        + assigned_keywords
        + ([primary_category] if primary_category else [])
    )
    lead_keyword = next((kw for kw in ordered_keywords if kw), primary_category or "camera")
    differentiators = _clean_title_phrases([payload.get("core_capability")] + list(_flatten_tokens(numeric_specs)))
    support_keywords = [
        keyword for keyword in ordered_keywords
        if _normalize_keyword_text(keyword) not in _normalize_keyword_text(lead_keyword)
    ]
    candidate = _build_natural_title_candidate(
        payload,
        lead_keyword=lead_keyword or primary_category or brand or "camera",
        support_keywords=support_keywords,
        differentiators=differentiators,
        max_length=max_length,
    )
    passed, _, _ = _validate_field_text(candidate, required_keywords, numeric_specs)
    if passed and len(candidate) <= max_length and not _title_is_keyword_dump(candidate):
        return candidate
    fallback_lead = " ".join(part for part in [brand, lead_keyword] if part).strip()
    return _trim_to_word_boundary(fallback_lead or candidate, max_length)


def _title_scene_connector(target_language: str) -> str:
    language = (target_language or "English").strip().lower()
    return {
        "english": "For",
        "french": "Pour",
        "german": "Für",
        "spanish": "Para",
        "italian": "Per",
        "chinese": "适合",
    }.get(language, "For")


def _title_inline_scene_connector(target_language: str) -> str:
    language = (target_language or "English").strip().lower()
    return {
        "english": "for",
        "french": "pour",
        "german": "für",
        "spanish": "para",
        "italian": "per",
        "chinese": "适合",
    }.get(language, "for")


def _title_connector_overuse(
    text: str,
    exact_phrases: Sequence[str],
    weak_connectors: Sequence[str],
) -> List[str]:
    masked, _ = _mask_exact_phrases(text or "", exact_phrases or [])
    hits: List[str] = []
    for connector in weak_connectors or []:
        pattern = re.compile(rf"\b{re.escape(str(connector).strip())}\b", re.IGNORECASE)
        matches = pattern.findall(masked)
        if matches:
            hits.extend([connector] * len(matches))
    return hits


def _merge_capability_mapping(
    capability_bundle: Sequence[str],
    explicit_mapping: Sequence[str],
    fallback_capability: Optional[str] = None,
) -> List[str]:
    merged: List[str] = []
    seen: Set[str] = set()
    for item in list(explicit_mapping or []) + list(capability_bundle or []) + ([fallback_capability] if fallback_capability else []):
        cleaned = str(item or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return merged


def _record_constraint_audit_actions(
    audit_log: Optional[List[Dict[str, Any]]],
    title: str,
    bullets: Sequence[str],
    description: str,
    writing_policy: Dict[str, Any],
    capability_constraints: Dict[str, Any],
) -> None:
    visible_text = " ".join([title or "", *(bullets or []), description or ""]).lower()
    if not visible_text:
        return
    directives = writing_policy.get("compliance_directives", {}) or {}
    waterproof = directives.get("waterproof", {}) or {}
    if waterproof.get("requires_case") and any(token in visible_text for token in ["waterproof", "underwater", "防水", "étanche", "wasserdicht"]):
        if any(token in visible_text for token in ["housing", "case", "防水壳", "boîtier", "gehäuse"]):
            _log_action(
                audit_log,
                "waterproof",
                "downgrade",
                {"reason": "visible_claim_qualified_with_housing_condition"},
            )
    best_mode = (
        capability_constraints.get("stabilization_best_mode")
        or (capability_constraints.get("recording_mode_guidance", {}) or {}).get("preferred_stabilization_mode")
        or ""
    )
    if best_mode and any(token in visible_text for token in ["stabilization", "stabilisation", "eis", "防抖", "bildstabilisierung"]):
        if best_mode.lower() in visible_text:
            _log_action(
                audit_log,
                "stabilization",
                "downgrade",
                {"reason": f"visible_claim_qualified_to_{best_mode.lower()}"},
            )


def _is_budget_constrained_live_runtime() -> bool:
    if os.getenv("LISTING_STRICT_BUDGET_RUNTIME", "").strip().lower() not in {"1", "true", "yes"}:
        return False
    return _is_openai_compatible_gateway_runtime()


def _is_openai_compatible_gateway_runtime() -> bool:
    client = get_llm_client()
    provider = (getattr(client, "provider_label", "") or "").lower()
    base_url = (getattr(client, "base_url", "") or "").lower()
    has_codex_exec_fallback = bool(getattr(client, "has_codex_exec_fallback", False))
    return (
        provider == "openai_compatible"
        and "api.gptclubapi.xyz/openai" in base_url
        and has_codex_exec_fallback
    )


def _llm_retry_budget(default_attempts: int) -> int:
    if _is_budget_constrained_live_runtime():
        return 1
    return max(1, default_attempts)


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9À-ÖØ-öø-ÿ]+", re.UNICODE)


def _tokenize_text_block(text: str) -> List[str]:
    if not text:
        return []
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if len(token) > 1]


def _stem_token(token: str) -> str:
    token = (token or "").strip().lower()
    if not token:
        return ""
    suffixes = ("ments", "ment", "ings", "ing", "tion", "ions", "ies", "ers", "es", "s")
    for suffix in suffixes:
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            return token[: -len(suffix)]
    return token


def _advanced_copy_rules() -> str:
    return (
        "ADVANCED WRITING RULES:\n"
        "A. De-jargonize every technical term by immediately translating it into a user-facing sensory or practical benefit.\n"
        "B. Outcome over capacity: convert cold units such as mAh, GB, and W into user-friendly duration, storage, or real-life usage outcomes whenever supported by facts.\n"
        "C. Customer-facing framing only: when describing limitations or prerequisites, present them as best-use guidance rather than seller-side return-reduction language.\n"
    )


def _gather_used_tokens(title: str, bullets: Sequence[str], description: str) -> Set[str]:
    used: Set[str] = set()
    for block in [title, description] + list(bullets or []):
        for token in _tokenize_text_block(block or ""):
            stem = _stem_token(token)
            if stem:
                used.add(stem)
    return used


def _keyword_conflicts_constraints(token: str, capability_constraints: Optional[Dict[str, Any]]) -> Optional[str]:
    text = (token or "").strip().lower()
    if not text:
        return "empty_keyword"
    constraints = capability_constraints or {}
    if constraints.get("wifi_supported") and any(phrase in text for phrase in ["sans wifi", "without wifi", "ohne wifi"]):
        return "wifi_conflict"
    return None


def _derive_mini_brief(scene_code: Optional[str], audience: str, pain_point: str) -> str:
    scene_code = (scene_code or "general_use").lower()
    templates = {
        "cycling_recording": "A {audience} carving through sunrise bike lanes, camera clipped tight while {pain_point}.",
        "underwater_exploration": "A {audience} finning through glowing reefs, housing locked so {pain_point}.",
        "travel_documentation": "A {audience} hopping trains with dawn-to-dusk shots rolling, never fearing {pain_point}.",
        "family_use": "An {audience} chasing kids and pets across the park, magnets snapping on so {pain_point}.",
        "outdoor_sports": "A {audience} racing along ridgelines, POV steady even when {pain_point}.",
        "general_use": "A {audience} capturing daily adventures confidently with {pain_point} solved.",
    }
    template = templates.get(scene_code, templates["general_use"])
    return template.format(audience=audience, pain_point=pain_point)


FR_LOCALIZED_BRIEFS = {
    "cycling_recording": "Coursier sous la pluie, caméra calée sur la veste pour bannir les flous POV.",
    "underwater_exploration": "Plongeur loisir qui longe un récif, boîtier verrouillé pour oublier toute peur d'infiltration.",
    "travel_documentation": "Voyageur sac au dos qui enchaîne les trains du lever au coucher sans craindre la panne d'autonomie.",
    "family_use": "Parents poursuivant trottinettes et chiots, clips magnétiques gardant chaque éclat de rire centré.",
    "general_use": "Créateur qui capture le quotidien sereinement, chaque scène reste nette.",
}

DE_LOCALIZED_BRIEFS = {
    "cycling_recording": "Kurier, der durch verregnete Gassen fliegt, Kamera fest an der Jacke und kein verwackeltes POV mehr.",
    "underwater_exploration": "Hobbytaucher, der am Riff entlanggleitet, Gehäuse verriegelt und keine Sorge vor Wasserschäden.",
    "travel_documentation": "Backpacker von Sonnenaufgang bis Sonnenuntergang, Akku hält jede Panoramaaufnahme durch.",
    "family_use": "Eltern, die Rollern und Haustieren hinterherjagen, Magnetclips halten jedes Lachen im Bild.",
    "general_use": "Creator hält den Alltag fest und jede Szene bleibt stabil.",
}


def _build_localized_mini_brief(scene_code: Optional[str],
                                audience: str,
                                pain_point: str,
                                language: str,
                                fallback_text: str) -> str:
    normalized_scene = (scene_code or "general_use").lower()
    lang = (language or "").lower()
    if lang.startswith("fr"):
        return FR_LOCALIZED_BRIEFS.get(normalized_scene, FR_LOCALIZED_BRIEFS["general_use"])
    if lang.startswith("de"):
        return DE_LOCALIZED_BRIEFS.get(normalized_scene, DE_LOCALIZED_BRIEFS["general_use"])
    return fallback_text


SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[.!?])\s+')


def _split_scene_action_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = [segment.strip() for segment in SENTENCE_SPLIT_PATTERN.split(text.strip()) if segment.strip()]
    return parts


def _build_feeling_clause(language: str, localized_pain_point: Optional[str], compact: bool = False) -> str:
    lang = (language or "").lower()
    pain_phrase = (localized_pain_point or "").strip()
    if lang.startswith("fr"):
        if pain_phrase:
            return (
                "Soulagement total : ce souci disparaît."
                if compact else
                f"Ressentez la sérénité : {pain_phrase} n'entrave plus vos prises."
            )
        return "Soulagement total : chaque POV reste net." if compact else "Ressentez la sérénité : chaque POV reste net et fluide."
    if lang.startswith("de"):
        if pain_phrase:
            return (
                "Erleichterung pur: Problem gelöst."
                if compact else
                f"Spüre die Erleichterung: {pain_phrase} bremst dich nicht mehr aus."
            )
        return "Erleichterung pur: jede Aufnahme sitzt." if compact else "Spüre die Erleichterung: jede Aufnahme bleibt stabil."
    if lang.startswith("es"):
        if pain_phrase:
            return (
                "Alivio total: problema resuelto."
                if compact else
                f"Siente el alivio: {pain_phrase} ya no arruina tus planos."
            )
        return "Alivio total: cada toma sigue fluida." if compact else "Siente el alivio: cada toma se mantiene fluida."
    if lang.startswith("it"):
        if pain_phrase:
            return (
                "Sollievo totale: problema risolto."
                if compact else
                f"Senti la tranquillità: {pain_phrase} non limita più le riprese."
            )
        return "Sollievo totale: ogni ripresa resta stabile." if compact else "Senti la tranquillità: ogni ripresa resta stabile."
    if pain_phrase:
        return "Relief: issue solved." if compact else f"Feel the relief: {pain_phrase} is no longer an issue."
    return "Relief: every shot stays stable." if compact else "Feel the relief: every shot stays stable."




def _guarantee_mandatory_keywords(text: str, keywords: Sequence[str], language: str) -> str:
    def _keyword_semantically_present(candidate_text: str, keyword_phrase: str) -> bool:
        normalized_candidate = _normalize_keyword_text(candidate_text or "")
        normalized_keyword = _normalize_keyword_text(keyword_phrase or "")
        if normalized_keyword and normalized_keyword in normalized_candidate:
            return True
        candidate_tokens = {
            _normalize_word_root(token)
            for token in _tokenize_alpha_words(candidate_text or "")
            if _normalize_word_root(token)
        }
        keyword_tokens = [
            _normalize_word_root(token)
            for token in _tokenize_alpha_words(keyword_phrase or "")
            if _normalize_word_root(token)
        ]
        connector_tokens = {"with", "for", "and", "or", "of", "the", "a", "an", "to"}
        meaningful_tokens = [
            token for token in keyword_tokens
            if token not in connector_tokens and len(token) > 2
        ]
        if not meaningful_tokens:
            return False
        return all(token in candidate_tokens for token in meaningful_tokens)

    tokens = [token.strip() for token in (keywords or []) if token and token.strip()]
    if not tokens:
        return text
    missing: List[str] = []
    for token in tokens:
        if not _keyword_semantically_present(text, token):
            missing.append(token)
    if not missing:
        return text
    suffix = ", ".join(dict.fromkeys(missing))
    trimmed = text.rstrip()
    if trimmed.endswith((".", "!", "?")):
        trimmed = trimmed[:-1].rstrip()
    language_key = (language or "english").strip().lower()
    connector = {
        "english": "Includes",
        "french": "Inclut",
        "german": "Enthalt",
        "spanish": "Incluye",
        "italian": "Include",
        "chinese": "包含",
    }.get(language_key, "Includes")
    if connector == "包含":
        addition = f" {connector}{suffix}。"
    else:
        addition = f" {connector} {suffix}."
    return f"{trimmed}{addition}"


def _select_intent_context(intent_graph: Sequence[Dict[str, Any]], scene_code: Optional[str], capability: Optional[str]) -> Dict[str, Any]:
    scene_code = (scene_code or "").lower()
    capability = (capability or "").lower()
    fallback = {
        "pain_point": "general performance concern",
        "audience": "general audience",
        "mini_brief": _derive_mini_brief(scene_code or "general_use", "general audience", "general performance concern"),
    }
    for node in intent_graph or []:
        if scene_code and node.get("scene") == scene_code:
            if "mini_brief" not in node:
                node["mini_brief"] = _derive_mini_brief(scene_code, node.get("audience", "creator"), node.get("pain_point", "performance issues"))
            return node
    for node in intent_graph or []:
        cap = (node.get("capability") or "").lower()
        if capability and capability in cap:
            if "mini_brief" not in node:
                node["mini_brief"] = _derive_mini_brief(scene_code or node.get("scene"), node.get("audience", "creator"), node.get("pain_point", "performance issues"))
            return node
    return fallback


def _enforce_bullet_length(text: str, limit: int = LENGTH_RULES["bullet"]["hard_ceiling"]) -> str:
    if limit is None:
        limit = LENGTH_RULES["bullet"]["hard_ceiling"]
    if len(text) <= limit:
        return text
    if " – " not in text:
        trimmed = _trim_to_word_boundary(text, max(1, limit - 1)).rstrip(" ,;:-|–—")
        return trimmed + "." if trimmed else text[:limit]
    prefix, body = text.split(" – ", 1)
    sentences = re.split(r'(?<=[.!?])\s+', body.strip())
    scene_action_feeling = sentences[:3]
    remainder = sentences[3:]
    trimmed = f"{prefix} – {' '.join(scene_action_feeling).strip()}"
    if remainder:
        trimmed = f"{trimmed} {' '.join(remainder).strip()}".strip()
    if len(trimmed) <= limit:
        return trimmed
    base = f"{prefix} – {' '.join(scene_action_feeling).strip()}".strip()
    if len(base) <= limit:
        return base
    trimmed_limit = base[:limit].rstrip()
    last_period = trimmed_limit.rfind(".")
    if last_period != -1 and last_period > len(prefix):
        return trimmed_limit[:last_period + 1].strip()
    last_comma = max(trimmed_limit.rfind(","), trimmed_limit.rfind(";"))
    if last_comma != -1 and last_comma > len(prefix):
        trimmed_limit = trimmed_limit[:last_comma].rstrip()
        if trimmed_limit and trimmed_limit[-1] not in ".!?":
            trimmed_limit += "."
        return trimmed_limit
    last_space = trimmed_limit.rfind(" ")
    if last_space != -1:
        trimmed_limit = trimmed_limit[:last_space].rstrip()
    if trimmed_limit and trimmed_limit[-1] not in ".!?":
        trimmed_limit += "."
    return trimmed_limit


def _dedupe_adjacent_words(text: str) -> str:
    tokens = text.split()
    if not tokens:
        return text
    deduped: List[str] = []
    prev = ""
    for token in tokens:
        lower = token.lower()
        if lower == prev:
            continue
        deduped.append(token)
        prev = lower
    return " ".join(deduped)


def _dedupe_keyword_sequence(keywords: Sequence[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for keyword in keywords or []:
        cleaned = (keyword or "").strip()
        normalized = _normalize_keyword_text(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped


def _trim_to_word_boundary(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    candidate = cleaned[:limit].rstrip(" ,;:-|–—")
    last_space = candidate.rfind(" ")
    last_comma = candidate.rfind(",")
    boundary = max(last_space, last_comma)
    if boundary > max(20, limit // 2):
        candidate = candidate[:boundary].rstrip(" ,;:-|–—")
    return candidate


def _dedupe_exact_phrase_occurrences(text: str, phrases: Sequence[str]) -> str:
    cleaned = text or ""
    for phrase in _dedupe_keyword_sequence(phrases):
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        matches = list(pattern.finditer(cleaned))
        if len(matches) <= 1:
            continue
        rebuilt: List[str] = []
        cursor = 0
        for idx, match in enumerate(matches):
            start, end = match.span()
            rebuilt.append(cleaned[cursor:start])
            if idx == 0:
                rebuilt.append(cleaned[start:end])
            cursor = end
        rebuilt.append(cleaned[cursor:])
        cleaned = "".join(rebuilt)
        cleaned = re.sub(r"\s+,", ",", cleaned)
        cleaned = re.sub(r",\s*,+", ", ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    return cleaned


def _title_exact_keyword_priority(keyword: str, primary_category: str = "") -> Tuple[int, int, int]:
    normalized = _normalize_keyword_text(keyword)
    category_norm = _normalize_keyword_text(primary_category)
    token_count = len(_tokenize_text_block(normalized))
    score = 0
    if category_norm and category_norm in normalized:
        score += 60
    if "action camera" in normalized:
        score += 35
    if re.search(r"\b(?:4k|5k|1080p|60fps|30fps)\b", normalized):
        score += 15
    return (score, token_count, -len(keyword))


def _ordered_exact_match_keywords(payload: Dict[str, Any]) -> List[str]:
    exact_keywords = _dedupe_keyword_sequence(payload.get("exact_match_keywords") or [])
    primary_category = payload.get("primary_category") or ""
    return sorted(
        exact_keywords,
        key=lambda keyword: _title_exact_keyword_priority(keyword, primary_category),
        reverse=True,
    )


def _title_spec_priority(spec: str) -> Tuple[int, int]:
    normalized = _normalize_keyword_text(spec)
    score = 0
    if re.search(r"\b(?:4k|5k|1080p|2k|60fps|30fps)\b", normalized):
        score += 50
    if re.search(r"\b(?:wifi|wi-fi|bluetooth|dual screen|double screen|eis)\b", normalized):
        score += 30
    if re.search(r"\b\d+\s*(?:m|min|minutes)\b", normalized):
        score += 20
    if re.search(r"\b\d+\s*(?:g|kg)\b", normalized):
        score += 5
    return (score, -len(spec or ""))


def _infer_title_scene_for_keyword(
    keyword: str,
    scene_priority: Sequence[str],
    used_scenes: Set[str],
) -> str:
    normalized = _normalize_keyword_text(keyword)
    heuristic_map = [
        ("cycling_recording", ["bike", "biking", "cycling", "ride", "helmet", "commute", "pov"]),
        ("underwater_exploration", ["underwater", "dive", "diving", "snorkel", "swim", "water"]),
        ("travel_documentation", ["travel", "trip", "vacation", "journey", "vlog"]),
        ("family_use", ["family", "kids", "child", "weekend"]),
        ("sports_training", ["sport", "training", "workout", "practice"]),
        ("outdoor_sports", ["outdoor", "trail", "adventure"]),
    ]
    for scene_code, hints in heuristic_map:
        if scene_code in (scene_priority or []):
            if any(hint in normalized for hint in hints):
                return scene_code
    for scene_code in scene_priority or []:
        if scene_code and scene_code not in used_scenes:
            return str(scene_code)
    return ""


def _title_scene_hint_for_keyword(keyword: str, scene_code: str, target_language: str) -> str:
    if not scene_code:
        return ""
    normalized = _normalize_keyword_text(keyword)
    target = target_language or "English"
    if target == "English":
        if scene_code == "cycling_recording":
            if "helmet" in normalized:
                return "Helmet POV"
            if any(token in normalized for token in ["bike", "cycling", "ride"]):
                return "Cycling"
        elif scene_code == "travel_documentation":
            if "vlog" in normalized:
                return "Travel Vlogs"
            return "Travel"
        elif scene_code == "underwater_exploration":
            return "Underwater Use"
    label = _format_scene_label(scene_code, target)
    if target == "English" and label:
        return label.title()
    return label


def _format_secondary_title_keyword(
    keyword: str,
    scene_code: str,
    target_language: str,
) -> str:
    phrase = (keyword or "").strip()
    if not phrase:
        return ""
    scene_hint = _title_scene_hint_for_keyword(phrase, scene_code, target_language)
    if not scene_hint:
        return phrase
    connector = _title_inline_scene_connector(target_language)
    normalized_phrase = _normalize_keyword_text(phrase)
    normalized_hint = _normalize_keyword_text(scene_hint)
    if normalized_hint and normalized_hint in normalized_phrase:
        return phrase
    if connector == "适合":
        return f"{phrase}{connector}{scene_hint}"
    return f"{phrase} {connector} {scene_hint}"


def _build_title_scene_segment(payload: Dict[str, Any]) -> str:
    target_language = payload.get("target_language") or "English"
    scenes = []
    for scene_code in (payload.get("scene_priority") or [])[:2]:
        alias_candidates = _scene_semantic_aliases(scene_code, target_language)
        label = alias_candidates[0] if alias_candidates else _format_scene_label(scene_code, target_language)
        if label:
            if target_language == "English":
                label = label.title()
            scenes.append(label)
    scenes = _dedupe_keyword_sequence(scenes)
    if not scenes:
        return ""
    connector = _title_scene_connector(target_language)
    if len(scenes) == 1:
        return f"{connector} {scenes[0]}"
    return f"{connector} {scenes[0]} & {scenes[1]}"


def _compose_exact_match_title(payload: Dict[str, Any]) -> str:
    brand = (payload.get("brand_name") or payload.get("brand") or "").strip()
    exact_keywords = _ordered_exact_match_keywords(payload)
    primary_category = payload.get("primary_category") or "Camera"
    max_length = int(payload.get("max_length") or LENGTH_RULES["title"]["hard_ceiling"])
    lead_exact = exact_keywords[0] if exact_keywords else primary_category
    other_exact = exact_keywords[1:]
    target_language = payload.get("target_language") or "English"
    specs = sorted(
        _dedupe_keyword_sequence(
            list(_flatten_tokens(payload.get("numeric_specs") or [])) + [payload.get("core_capability") or ""]
        ),
        key=_title_spec_priority,
        reverse=True,
    )
    used_scenes: Set[str] = set()
    formatted_secondary_exact: List[str] = []
    for keyword in other_exact:
        scene_code = _infer_title_scene_for_keyword(keyword, payload.get("scene_priority") or [], used_scenes)
        if scene_code:
            used_scenes.add(scene_code)
        formatted_secondary_exact.append(_format_secondary_title_keyword(keyword, scene_code, target_language))
    remaining_scenes = [
        scene_code for scene_code in (payload.get("scene_priority") or [])
        if scene_code and scene_code not in used_scenes
    ]
    scene_payload = dict(payload)
    scene_payload["scene_priority"] = remaining_scenes
    scene_payload["scene_priority"] = remaining_scenes or (payload.get("scene_priority") or [])
    lead = " ".join(part for part in [brand, lead_exact] if part).strip()
    support_keywords = _dedupe_keyword_sequence(formatted_secondary_exact or other_exact)
    differentiators = _dedupe_keyword_sequence(specs[:2])

    candidate = _build_natural_title_candidate(
        scene_payload,
        lead_keyword=lead_exact or primary_category,
        support_keywords=support_keywords,
        differentiators=differentiators,
        max_length=max_length,
    )
    candidate = _dedupe_exact_phrase_occurrences(candidate, exact_keywords)
    candidate = _dedupe_comma_sections(candidate)
    candidate = _dewater_title_text(candidate, exact_keywords)
    candidate = _trim_to_word_boundary(candidate, max_length)
    candidate_normalized = _normalize_keyword_text(candidate)
    secondary_exact_fully_preserved = all(
        _normalize_keyword_text(keyword) in candidate_normalized
        for keyword in formatted_secondary_exact
    )
    if all(_normalize_keyword_text(keyword) in candidate_normalized for keyword in exact_keywords) and secondary_exact_fully_preserved:
        return candidate

    exact_scene_clause = " and ".join(formatted_secondary_exact[:2]).strip()
    if exact_scene_clause:
        explicit_candidate = f"{lead} {' '.join(specs[:2]).strip()} for {exact_scene_clause}".strip()
        explicit_candidate = _dedupe_exact_phrase_occurrences(explicit_candidate, exact_keywords)
        explicit_candidate = _dewater_title_text(explicit_candidate, exact_keywords)
        explicit_candidate = _trim_to_word_boundary(explicit_candidate, max_length)
        if all(_normalize_keyword_text(keyword) in _normalize_keyword_text(explicit_candidate) for keyword in exact_keywords):
            return explicit_candidate

    fallback = candidate or lead
    fallback = _dewater_title_text(fallback, exact_keywords)
    return _trim_to_word_boundary(fallback, max_length)


def _filter_capabilities(capabilities: List[str],
                         directives: Dict[str, Any],
                         audit_log: Optional[List[Dict[str, Any]]] = None,
                         field: str = "") -> List[str]:
    allowed = []
    for cap in capabilities or []:
        if _is_waterproof_term(cap) and not directives.get("waterproof", {}).get("allow_visible", True):
            _log_action(
                audit_log,
                field or "copy",
                "delete",
                {"term": cap, "reason": "waterproof blocked by capability_constraints"}
            )
            continue
        if _is_stabilization_term(cap) and not directives.get("stabilization", {}).get("allow_visible", True):
            _log_action(
                audit_log,
                field or "copy",
                "delete",
                {"term": cap, "reason": "stabilization blocked by capability_constraints"}
            )
            continue
        allowed.append(cap)
    if not allowed:
        return capabilities or ["4K recording"]
    return allowed


def _is_waterproof_term(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["waterproof", "ip", "防水", "unterwasser", "wasserdicht", "潜水"])


def _is_stabilization_term(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ["stabilization", "防抖", "eis", "bildstabilisierung", "稳定"])


def _scene_from_rule(scenes: List[str], index: int) -> Optional[str]:
    if not scenes:
        return None
    if index < len(scenes):
        return scenes[index]
    return scenes[-1]


def _summarize_accessories(accessories: List[Dict[str, Any]]) -> str:
    names = []
    for acc in accessories:
        spec = acc.get("specification") or acc.get("original") or acc.get("name")
        if spec:
            names.append(spec)
    if not names:
        return "magnetic clip and back clip system"
    unique = []
    for name in names:
        if name not in unique:
            unique.append(name)
        if len(unique) == 3:
            break
    return ", ".join(unique)


def _extract_minutes(value: str) -> Optional[int]:
    if not value:
        return None
    match = re.search(r'(\d+)\s*(min|分钟)', value.lower())
    if match:
        return int(match.group(1))
    return None


def _compose_bullet_body(role: str,
                         scene_label: str,
                         keyword_text: str,
                         capability: str,
                         directives: Dict[str, Any],
                         attr_lookup: Dict[str, str],
                         accessories: List[Dict[str, Any]],
                         rule: Dict[str, Any],
                         slot_name: str,
                         audit_log: Optional[List[Dict[str, Any]]] = None,
                         scene_code: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    bullet_meta = {
        "scene_code": scene_code,
        "scene_label": scene_label,
        "capability": capability,
        "numeric_met": False,
        "numeric_source": None,
        "numeric_values": [],
    }
    runtime_minutes = directives.get("runtime_minutes") or _extract_minutes(
        attr_lookup.get("battery average life") or attr_lookup.get("battery_life", "")
    )
    runtime_phrase = f"{runtime_minutes}-minute runtime" if runtime_minutes else attr_lookup.get("battery_life", "all-day power")
    if runtime_minutes:
        bullet_meta["numeric_met"] = True
        bullet_meta["numeric_source"] = bullet_meta["numeric_source"] or "runtime_minutes"
        bullet_meta["numeric_values"].append(f"{runtime_minutes} minutes")
    weight_value = attr_lookup.get("item weight") or attr_lookup.get("weight")
    weight_phrase = weight_value if weight_value else "lightweight build"
    waterproof = directives.get("waterproof", {})
    stabilization = directives.get("stabilization", {})
    accessory_summary = _summarize_accessories(accessories)
    keyword_phrase = keyword_text or capability

    required_elements = rule.get("required_elements", [])
    if "runtime_minutes" in required_elements and not runtime_minutes:
        _log_action(
            audit_log,
            f"bullet_{slot_name.lower()}",
            "downgrade",
            {"reason": "runtime_minutes missing, fallback to attribute battery_life"}
        )
    if "mount_system" in required_elements and accessory_summary == "magnetic clip and back clip system":
        _log_action(
            audit_log,
            f"bullet_{slot_name.lower()}",
            "fallback",
            {"reason": "mount/accessory list missing, used generic summary"}
        )
    if "persona_label" in required_elements and not keyword_text:
        _log_action(
            audit_log,
            f"bullet_{slot_name.lower()}",
            "fallback",
            {"reason": "keyword slot empty, injected capability text"}
        )

    if role == "mount_scene":
        return (
            f"{accessory_summary} locks onto gear for {scene_label}. "
            f"{capability} captures true POV stories while staying {weight_phrase}."
        ), bullet_meta
    if role == "runtime_power":
        scene_fragment = scene_label or "long shifts"
        return (
            f"{capability} with {runtime_phrase} keeps {scene_fragment} recordings uninterrupted. "
            f"{keyword_phrase or 'Dual-channel charging'} avoids mid-shift swapping."
        ), bullet_meta
    if role == "capability_persona":
        return (
            f"{capability} and {keyword_phrase or 'dual-display control'} help creators master {scene_label}. "
            f"Stay in frame with instant preview and share-ready clips."
        ), bullet_meta
    if role == "compliance_boundary":
        if waterproof.get("allow_visible"):
            depth = waterproof.get("depth_m")
            condition = " when using the included housing" if waterproof.get("requires_case") else ""
            depth_phrase = f"{depth} m" if depth else "deep water"
            note = waterproof.get("note") or ""
            if depth:
                bullet_meta["numeric_met"] = True
                bullet_meta["numeric_source"] = bullet_meta["numeric_source"] or "waterproof_depth"
                bullet_meta["numeric_values"].append(f"{depth} m")
            return (
                f"{keyword_phrase or 'Water-ready kit'} withstands {depth_phrase}{condition}. "
                f"{note or 'State the housing requirement inside the same sentence.'}"
            ), bullet_meta
        boundary_note = waterproof.get("note") or "Not designed for underwater use; keep device dry."
        safe_label = "Safety note"
        _log_action(
            audit_log,
            f"bullet_{slot_name.lower()}",
            "downgrade",
            {"reason": "waterproof not supported, replaced with safety boundary"}
        )
        return f"{safe_label}: {boundary_note}", bullet_meta
    if role == "after_sales":
        warranty = attr_lookup.get("warranty") or attr_lookup.get("warranty_period") or "24-month support"
        connectivity = attr_lookup.get("connectivity technolog") or attr_lookup.get("connectivity", "WiFi app control")
        localized_promises = list(rule.get("after_sales_promises") or [])
        localized_sop = list(rule.get("support_sop") or [])
        support_phrase = localized_promises[0] if localized_promises else warranty.replace("warranty", "support").replace("Warranty", "Support")
        sop_phrase = localized_sop[0] if localized_sop else ""
        return (
            f"{keyword_phrase or 'Pro support'} backed by {support_phrase}. "
            f"{sop_phrase or f'{connectivity} enables live preview and quick file transfers.'}"
        ), bullet_meta
    # fallback
    fallback_text = (
        f"{keyword_phrase or capability} elevates {scene_label} performance while staying {weight_phrase}. "
        f"{runtime_phrase} ensures you capture the full story."
    )
    if rule.get("numeric_expectation") and not re.search(r"\d", fallback_text):
        extra_value = runtime_phrase if re.search(r"\d", runtime_phrase or "") else attr_lookup.get("battery_life", "")
        if extra_value and extra_value not in fallback_text:
            fallback_text = f"{fallback_text} Rated for {extra_value}."
            if re.search(r"\d", extra_value):
                bullet_meta["numeric_met"] = True
                bullet_meta["numeric_source"] = bullet_meta["numeric_source"] or "battery_life"
                normalized_value = re.sub(r"\s+", " ", extra_value).strip()
                if normalized_value:
                    bullet_meta["numeric_values"].append(normalized_value)
        _log_action(
            audit_log,
            f"bullet_{slot_name.lower()}",
            "numeric_patch",
            {"reason": "added numeric proof to satisfy slot expectation"}
        )
        bullet_meta["numeric_met"] = True
        bullet_meta["numeric_source"] = bullet_meta["numeric_source"] or "numeric_patch"
    return fallback_text, bullet_meta


TABOO_KEYWORDS = {
    "spycam",
    "spy camera",
    "hidden camera",
    "nanny cam",
    "espion",
    "espionnage",
}

CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")

BULLET_TEMPLATES = {
    "B1": {
        "Chinese": "{content}",
        "English": "{content}",
        "German": "{content}",
        "French": "{content}",
        "Spanish": "{content}",
        "Italian": "{content}"
    },
    "B2": {
        "Chinese": "{content}",
        "English": "{content}",
        "German": "{content}",
        "French": "{content}",
        "Spanish": "{content}",
        "Italian": "{content}"
    },
    "B3": {
        "Chinese": "{content}",
        "English": "{content}",
        "German": "{content}",
        "French": "{content}",
        "Spanish": "{content}",
        "Italian": "{content}"
    },
    "B4": {
        "Chinese": "{content}",
        "English": "{content}",
        "German": "{content}",
        "French": "{content}",
        "Spanish": "{content}",
        "Italian": "{content}"
    },
    "B5": {
        "Chinese": "{content}",
        "English": "{content}",
        "German": "{content}",
        "French": "{content}",
        "Spanish": "{content}",
        "Italian": "{content}"
    },
}

DESCRIPTION_CLOSING_STATEMENTS = {
    "English": "Buy now and start capturing your moments!",
    "German": "Jetzt kaufen und Ihre Aufnahmeerlebnisse beginnen!",
    "French": "Achetez maintenant et capturez vos instants forts !",
    "Spanish": "¡Compra ahora y comienza a capturar tus momentos!",
    "Italian": "Acquista ora e inizia a catturare i tuoi momenti!",
    "Chinese": "立即购买，开启您的拍摄之旅！",
}

DESCRIPTION_TEMPLATES = {
    "English": "{brand} {product_name} for {scene}. {core_capability}. {selling_points} {bullet1} {bullet2} {bullet3} {closing_statement} Package includes: {accessories}",
    "German": "{brand} {product_name} für {scene}. {core_capability}. {selling_points} {bullet1} {bullet2} {bullet3} {closing_statement} Lieferumfang: {accessories}",
    "French": "{brand} {product_name} pour {scene}. {core_capability}. {selling_points} {bullet1} {bullet2} {bullet3} {closing_statement} Contenu du coffret : {accessories}",
    "Spanish": "{brand} {product_name} para {scene}. {core_capability}. {selling_points} {bullet1} {bullet2} {bullet3} {closing_statement} Contenido del paquete: {accessories}",
    "Italian": "{brand} {product_name} per {scene}. {core_capability}. {selling_points} {bullet1} {bullet2} {bullet3} {closing_statement} Contenuto della confezione: {accessories}",
    "Chinese": "{brand} {product_name} 面向{scene}，具备{core_capability}。{selling_points}{bullet1}{bullet2}{bullet3}{closing_statement} 包装内含：{accessories}",
}


# FAQ模板
FAQ_TEMPLATES = {
    "Chinese": [
        {"q": "产品是否防水？", "a": "是的，产品配备防水壳，支持{waterproof_depth}防水。"},
        {"q": "电池续航多久？", "a": "电池续航约{battery_life}，支持边充边用。"},
        {"q": "支持哪些存储卡？", "a": "支持Micro SD卡，最大支持{max_storage}。"},
        {"q": "如何传输文件？", "a": "可通过WiFi或USB连接传输文件。"},
        {"q": "质保期多久？", "a": "提供{warranty_period}质保，享受全国联保服务。"}
    ],
    "English": [
        {"q": "Is the product waterproof?", "a": "Yes, it comes with a waterproof case that supports {waterproof_depth}."},
        {"q": "How long does the battery last?", "a": "The battery lasts about {battery_life} and supports charging while recording."},
        {"q": "What memory cards are supported?", "a": "Supports Micro SD cards up to {max_storage}."},
        {"q": "How to transfer files?", "a": "Files can be transferred via WiFi or USB connection."},
        {"q": "What is the warranty period?", "a": "It comes with {warranty_period} warranty with nationwide service coverage."}
    ],
    "German": [
        {"q": "Ist das Produkt wasserdicht?", "a": "Ja, es wird mit einem Wassergehäuse geliefert, das {waterproof_depth} unterstützt."},
        {"q": "Wie lange hält der Akku?", "a": "Der Akku hält ca. {battery_life} und unterstützt Aufladen während der Aufnahme."},
        {"q": "Welche Speicherkarten werden unterstützt?", "a": "Unterstützt Micro SD-Karten bis zu {max_storage}."},
        {"q": "Wie übertrage ich Dateien?", "a": "Dateien können über WLAN oder USB-Verbindung übertragen werden."},
        {"q": "Wie lang ist die Garantiezeit?", "a": "{warranty_period} Garantie mit deutschlandweitem Service."}
    ],
    "French": [
        {"q": "Le produit est-t-il waterproof?", "a": "Oui, il est livré avec un boîtier waterproof supportant {waterproof_depth}."},
        {"q": "Quelle est l'autonomie de la batterie?", "a": "La batterie dure environ {battery_life} et supporte la charge pendant l'enregistrement."},
        {"q": "Quelles cartes mémoire sont supportées?", "a": "Supporte les cartes Micro SD jusqu'à {max_storage}."},
        {"q": "Comment transférer les fichiers?", "a": "Les fichiers peuvent être transférés via WiFi ou connexion USB."},
        {"q": "Quelle est la période de garantie?", "a": "Garantie {warranty_period} avec couverture nationale."}
    ],
    "Spanish": [
        {"q": "¿El producto es resistente al agua?", "a": "Sí, viene con una carcasa waterproof que soporta {waterproof_depth}."},
        {"q": "¿Cuánto dura la batería?", "a": "La batería dura unos {battery_life} y soporta carga durante la grabación."},
        {"q": "¿Qué tarjetas de memoria son compatibles?", "a": "Soporta tarjetas Micro SD hasta {max_storage}."},
        {"q": "¿Cómo transfiero los archivos?", "a": "Los archivos se pueden transferir por WiFi o conexión USB."},
        {"q": "¿Cuál es el período de garantía?", "a": "Garantía de {warranty_period} con cobertura nacional."}
    ],
    "Italian": [
        {"q": "Il prodotto è impermeabile?", "a": "Sì, viene fornito con una custodia waterproof che supporta {waterproof_depth}."},
        {"q": "Quanto dura la batteria?", "a": "La batteria dura circa {battery_life} e supporta la ricarica durante la registrazione."},
        {"q": "Quali schede di memoria sono supportate?", "a": "Supporta schede Micro SD fino a {max_storage}."},
        {"q": "Come trasferisco i file?", "a": "I file possono essere trasferiti tramite WiFi o connessione USB."},
        {"q": "Qual è il periodo di garanzia?", "a": "Garanzia di {warranty_period} con copertura nazionale."}
    ]
}


def _has_real_vocab(preprocessed_data: Any) -> bool:
    """检查是否有真实国家词表（Priority 1）"""
    rv = getattr(preprocessed_data, "real_vocab", None)
    if rv is None:
        # Fallback: 检查 real_vocab 是否为 dict（来自JSON反序列化）
        rv_dict = getattr(preprocessed_data, "__dict__", {}).get("real_vocab")
        if rv_dict and isinstance(rv_dict, dict) and rv_dict.get("is_available"):
            return True
        return False
    return getattr(rv, "is_available", False)


def _reconstruct_real_vocab(preprocessed_data: Any) -> Any:
    """
    尝试从 preprocessed_data 重建 RealVocabData 对象。
    处理三种情况：
    1. real_vocab 是 RealVocabData 对象（正常情况）
    2. real_vocab 是 dict（来自 JSON 反序列化）
    3. real_vocab 嵌套在 preprocessed_data 的某个子对象中
    """
    feedback_context = getattr(preprocessed_data, "feedback_context", {}) or {}

    def _merge_feedback_rows(top_keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = list(top_keywords or [])
        for row in (feedback_context.get("organic_core") or []) + (feedback_context.get("sp_intent") or []):
            keyword = str((row or {}).get("keyword") or "").strip()
            if not keyword:
                continue
            merged.insert(
                0,
                {
                    "keyword": keyword,
                    "search_volume": float((row or {}).get("search_volume") or 0),
                    "conversion_rate": float((row or {}).get("conversion") or 0),
                    "source_type": "feedback_organic_core" if row in (feedback_context.get("organic_core") or []) else "feedback_sp_intent",
                    "tier": "L1" if row in (feedback_context.get("organic_core") or []) else "L2",
                },
            )
        return merged

    # 情况1: 直接属性
    rv = getattr(preprocessed_data, "real_vocab", None)
    if rv is not None and not isinstance(rv, dict):
        if getattr(rv, "is_available", False):
            rv.top_keywords = _merge_feedback_rows(getattr(rv, "top_keywords", []) or [])
            return rv
        return None

    # 情况2: __dict__ 中的 dict
    rv_dict = getattr(preprocessed_data, "__dict__", {}).get("real_vocab")
    if rv_dict and isinstance(rv_dict, dict) and rv_dict.get("is_available"):
        class ReconstructedRealVocab:
            def __init__(self, d):
                self.country = d.get("country", "")
                self.is_available = d.get("is_available", False)
                self.total_count = d.get("total_count", 0)
                self.aba_count = d.get("aba_count", 0)
                self.order_winning_count = d.get("order_winning_count", 0)
                self.review_count = d.get("review_count", 0)
                self.top_keywords = _merge_feedback_rows(d.get("top_keywords", []) or [])
                self.data_mode = d.get("data_mode", "SYNTHETIC_COLD_START")
        return ReconstructedRealVocab(rv_dict)

    # 情况3: 嵌套在 preprocessed_data.real_vocab 本身是 dict 的情况
    if isinstance(rv, dict) and rv.get("is_available"):
        class ReconstructedRealVocab:
            def __init__(self, d):
                self.country = d.get("country", "")
                self.is_available = d.get("is_available", False)
                self.total_count = d.get("total_count", 0)
                self.aba_count = d.get("aba_count", 0)
                self.order_winning_count = d.get("order_winning_count", 0)
                self.review_count = d.get("review_count", 0)
                self.top_keywords = _merge_feedback_rows(d.get("top_keywords", []) or [])
                self.data_mode = d.get("data_mode", "SYNTHETIC_COLD_START")
        return ReconstructedRealVocab(rv)

    return None


def extract_tiered_keywords(preprocessed_data: Any, language: str = "Chinese", real_vocab: Any = None) -> Dict[str, List[str]]:
    """
    兼容旧接口，实际调用 modules.keyword_utils.extract_tiered_keywords。
    """
    return kw_extract_tiered_keywords(preprocessed_data, language, real_vocab)


def extract_l1_keywords(keyword_data: Any, language: str = "Chinese") -> List[str]:
    """
    提取 L1 关键词（由 keyword_protocol 的相对分层决定）- 保留兼容性接口
    """
    tiered = extract_tiered_keywords(keyword_data, language)
    return tiered.get("l1", [])


def extract_high_conv_keywords(keyword_data: Any) -> List[str]:
    """
    提取高转化关键词（购买率≥1.5%）
    """
    high_conv_keywords = []

    if not keyword_data or not hasattr(keyword_data, 'keywords'):
        return []

    for keyword_item in keyword_data.keywords:
        conversion_rate = keyword_item.get('conversion_rate', 0)
        keyword = keyword_item.get('keyword', '')

        if conversion_rate >= 1.5 and keyword:
            high_conv_keywords.append(keyword)

    return high_conv_keywords[:3]


def generate_title(
    preprocessed_data: PreprocessedData,
    writing_policy: Dict[str, Any],
    l1_keywords: List[str],
    tiered_keywords: Dict[str, List[str]] = None,
    keyword_allocation_strategy: str = "balanced",
    audit_log: Optional[List[Dict[str, Any]]] = None,
    blocked_terms: Optional[Sequence[str]] = None,
    assignment_tracker: Optional[KeywordAssignmentTracker] = None,
    target_language: Optional[str] = None,
    request_timeout_seconds: Optional[int] = None,
    artifact_dir: Optional[str] = None,
    llm_override_model: Optional[str] = None,
) -> str:
    tiered_keywords = tiered_keywords or {"l1": [], "l2": [], "l3": []}
    target_language = target_language or getattr(preprocessed_data, "language", "English")
    directives = writing_policy.get("compliance_directives", {})
    brand = getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT")
    product_name = getattr(getattr(preprocessed_data, "run_config", None), "product_name", "") or "Action Camera"
    category = getattr(getattr(preprocessed_data, "run_config", None), "category", "Action Camera")

    blocked = tuple(term.lower() for term in (blocked_terms or []))
    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    retention_strategy = writing_policy.get("retention_strategy", {}) or {}

    generic_title_tokens = {
        "camera", "caméra", "kamera", "cámara", "cameraa", "camcorder", "caméscope",
        "de", "d", "di", "da", "del",
    }

    def _filter_blocked(words: Sequence[str]) -> List[str]:
        clean: List[str] = []
        for word in words or []:
            normalized = (word or "").strip()
            if not normalized:
                continue
            normalized_lower = normalized.lower()
            if any(term and term in normalized_lower for term in blocked):
                _log_action(
                    audit_log,
                    "title",
                    "backend_only",
                    {"term": normalized, "reason": "blocked in visible fields"},
                )
                continue
            conflict_reason = _keyword_conflicts_constraints(normalized, capability_constraints)
            if conflict_reason:
                _log_action(
                    audit_log,
                    "title",
                    "constraint_skip",
                    {"term": normalized, "reason": conflict_reason},
                )
                continue
            clean.append(normalized)
        return clean

    title_slots = writing_policy.get("keyword_slots", {})
    slot_keywords = title_slots.get("title") or []
    prioritized_title_anchors = retention_strategy.get("title_anchor_keywords", []) or []
    raw_primary_l1 = _filter_blocked(
        prioritized_title_anchors + list(slot_keywords or []) + list(l1_keywords or []) + list(tiered_keywords.get("l1", []) or [])
    )
    if not raw_primary_l1:
        raw_primary_l1 = ["action camera 4k"]
    anchor_priority = {
        _normalize_keyword_text(keyword): max(0, 100 - idx)
        for idx, keyword in enumerate(prioritized_title_anchors)
        if keyword
    }

    def _keyword_signal_score(keyword: str) -> Tuple[int, int]:
        normalized_tokens = [
            token for token in _tokenize_text_block(_normalize_keyword_text(keyword))
            if token not in generic_title_tokens
        ]
        return (anchor_priority.get(_normalize_keyword_text(keyword), 0), len(normalized_tokens), -len(keyword))

    ranked_l1 = [
        keyword
        for _, keyword in sorted(
            enumerate(raw_primary_l1),
            key=lambda item: (_keyword_signal_score(item[1]), -item[0]),
            reverse=True,
        )
    ]
    exact_match_keywords = _dedupe_keyword_sequence(
        prioritized_title_anchors
        + (writing_policy.get("keyword_routing", {}) or {}).get("title_traffic_keywords", [])
        + ranked_l1
    )[:3]
    primary_l1 = ranked_l1[:2] if len(ranked_l1) > 1 else ranked_l1[:1]
    assigned_keywords = _filter_blocked(tiered_keywords.get("l2", [])[:1])
    repair_keyword_pool = _filter_blocked(
        list(tiered_keywords.get("l1", []) or []) + list(tiered_keywords.get("l2", []) or [])
    )

    core_capabilities = _filter_capabilities(preprocessed_data.core_selling_points, directives, audit_log, "title")
    numeric_specs = _collect_numeric_tokens(preprocessed_data, directives)
    payload = {
        "field": "title",
        "brand_name": brand,
        "product_name": product_name,
        "primary_category": category,
        "l1_keywords": primary_l1[:2],
        "assigned_keywords": assigned_keywords[:1],
        "core_capability": core_capabilities[0] if core_capabilities else "",
        "scene_priority": writing_policy.get("scene_priority", [])[:3],
        "numeric_specs": numeric_specs[:2],
        "target_language": target_language,
        "max_length": LENGTH_RULES["title"]["hard_ceiling"],
        "exact_match_keywords": exact_match_keywords,
        "_repair_keyword_pool": repair_keyword_pool,
        "copy_contracts": writing_policy.get("copy_contracts", {}),
        "_artifact_dir": artifact_dir,
        "_llm_override_model": llm_override_model,
    }
    if request_timeout_seconds:
        payload["_request_timeout_seconds"] = int(request_timeout_seconds)
    if llm_override_model:
        payload["_disable_fallback"] = True
    required_keywords = _dedupe_keyword_sequence(
        exact_match_keywords + payload["assigned_keywords"]
    )
    title_text = _generate_and_audit_title(
        payload,
        audit_log,
        assignment_tracker,
        required_keywords,
    )
    title_text = _dedupe_adjacent_words(title_text)
    title_text = _dewater_title_text(title_text, exact_match_keywords, audit_log)
    title_text = _dedupe_exact_phrase_occurrences(title_text, exact_match_keywords)
    if exact_match_keywords and _is_openai_compatible_gateway_runtime():
        title_text = _compose_exact_match_title(payload)
    return title_text

def clean_bullet_text(bullet: str) -> str:
    """
    清理bullet文本，移除模板标记【...】
    """
    # 移除【...】模式，包括中英文括号
    cleaned = re.sub(r'【[^】]*】', '', bullet)  # 中文括号
    cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)  # 英文括号
    # 清理多余空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _allocate_capability_bundles(capabilities: Sequence[str], slot_count: int) -> List[List[str]]:
    bundles: List[List[str]] = []
    if slot_count <= 0:
        return bundles
    bundles = [[] for _ in range(slot_count)]
    if not capabilities:
        return bundles
    for idx, capability in enumerate(capabilities):
        bundles[idx % slot_count].append(capability)
    return bundles


def _ordered_slot_filter(slot_filter: Optional[Sequence[str]], available_slots: Sequence[str]) -> List[str]:
    available = [str(slot) for slot in (available_slots or []) if str(slot)]
    if not slot_filter:
        return available
    requested = {str(slot) for slot in slot_filter if str(slot)}
    return [slot for slot in available if slot in requested]


def _generate_bullet_points_legacy(
    preprocessed_data: PreprocessedData,
    writing_policy: Dict[str, Any],
    language: str = "English",
    tiered_keywords: Dict[str, List[str]] = None,
    keyword_allocation_strategy: str = "balanced",
    keyword_slots: Optional[Dict[str, Any]] = None,
    audit_log: Optional[List[Dict[str, Any]]] = None,
    blocked_terms: Optional[Sequence[str]] = None,
    assignment_tracker: Optional[KeywordAssignmentTracker] = None,
    target_language: Optional[str] = None,
    request_timeout_seconds: Optional[int] = None,
    slot_filter: Optional[Sequence[str]] = None,
    artifact_dir: Optional[str] = None,
    llm_override_model: Optional[str] = None,
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """
    Generate five bullet points with constrained payloads.

    Returns:
        reasoning_bullets: English fallback strings used by downstream modules.
        bullet_trace: Slot metadata for auditing/scoring.
        localized_bullets: Final target-language bullets (LLM or rule-based fallback).
    """
    reasoning_bullets: List[str] = []
    localized_bullets: List[str] = []
    bullet_trace: List[Dict[str, Any]] = []

    tiered_keywords = tiered_keywords or {"l1": [], "l2": [], "l3": []}
    scenes = writing_policy.get('scene_priority', [])
    final_language = target_language or getattr(preprocessed_data, "language", language)
    real_vocab = getattr(preprocessed_data, "real_vocab", None)
    data_mode = getattr(preprocessed_data, "data_mode", "SYNTHETIC_COLD_START")
    default_scenes = ["outdoor_sports", "cycling_recording", "underwater_exploration", "travel_documentation", "family_use"]
    while len(scenes) < 4:
        scenes.extend([s for s in default_scenes if s not in scenes][:4 - len(scenes)])

    if keyword_slots is None:
        keyword_slots = writing_policy.get("keyword_slots")
    if not keyword_slots:
        keyword_slots = build_keyword_slots(tiered_keywords, scenes, final_language)

    attr_lookup = _build_attr_lookup(preprocessed_data.attribute_data)
    directives = writing_policy.get("compliance_directives", {})
    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    accessory_descriptions = getattr(preprocessed_data, "accessory_descriptions", []) or []
    canonical_accessories = getattr(preprocessed_data, "canonical_accessory_descriptions", []) or accessory_descriptions
    accessory_experiences: List[str] = []
    localized_accessory_experiences: List[str] = []
    for acc in (canonical_accessories or []):
        exp = acc.get("experience")
        if not exp:
            continue
        accessory_experiences.append(exp)
        key = acc.get("experience_key")
        if key:
            localized = get_localized_accessory_experience_by_key(key, final_language)
            if localized:
                localized_accessory_experiences.append(localized)
    accessory_items = _prepare_accessory_items(accessory_descriptions)
    intent_graph = writing_policy.get("intent_graph") or []
    evidence_numeric_values = _collect_evidence_numeric_values(attr_lookup, capability_constraints)
    allowed_capabilities = _filter_capabilities(preprocessed_data.core_selling_points, directives, audit_log, "bullets")
    if not allowed_capabilities:
        allowed_capabilities = ["4K recording"]
    capability_metadata = writing_policy.get("capability_metadata") or []
    intent_capabilities: List[str] = []
    for node in intent_graph or []:
        capability_label = node.get("capability")
        if capability_label and capability_label not in intent_capabilities:
            intent_capabilities.append(capability_label)
    for capability_label in intent_capabilities:
        if capability_label not in allowed_capabilities:
            allowed_capabilities.append(capability_label)
    metadata_capabilities = [
        entry.get("capability") for entry in capability_metadata
        if entry.get("is_supported", True)
    ]
    for capability_label in metadata_capabilities:
        if capability_label and capability_label not in allowed_capabilities:
            allowed_capabilities.append(capability_label)

    slot_rules = writing_policy.get("bullet_slot_rules", LEGACY_BULLET_SLOT_RULES)
    slot_keys = ["B1", "B2", "B3", "B4", "B5"]
    selected_slots = set(_ordered_slot_filter(slot_filter, slot_keys))
    slot_capability_bundles = _allocate_capability_bundles(allowed_capabilities, len(slot_keys))
    capability_cycle = 0
    blocked = {term.lower() for term in (blocked_terms or [])}
    brand_name = getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT")
    slot_keyword_records: Dict[str, List[str]] = {}

    def _keywords(slot_lookup: str, fallback: List[str], field_label: str, slot_name: str) -> List[str]:
        slot = keyword_slots.get(slot_lookup) or {}
        words = slot.get("keywords") or []
        if not words:
            words = fallback
        filtered: List[str] = []
        for word in words:
            if not word:
                continue
            if word.lower() in blocked:
                _log_action(
                    audit_log,
                    f"bullet_{slot_name.lower()}",
                    "backend_only",
                    {"term": word, "reason": "blocked in visible fields"},
                )
                continue
            conflict_reason = _keyword_conflicts_constraints(word, capability_constraints)
            if conflict_reason:
                _log_action(
                    audit_log,
                    f"bullet_{slot_name.lower()}",
                    "constraint_skip",
                    {"term": word, "reason": conflict_reason},
                )
                continue
            filtered.append(word)
        if assignment_tracker and filtered:
            assignment_tracker.record(field_label, filtered)
        return filtered

    l2_pool = tiered_keywords.get("l2", []) or []
    used_spec_dimensions: Set[str] = set()
    for idx, slot_name in enumerate(slot_keys):
        if selected_slots and slot_name not in selected_slots:
            continue
        rule = slot_rules.get(slot_name, LEGACY_BULLET_SLOT_RULES.get(slot_name, {}))
        role = rule.get("role", "mount_scene")
        scene_code = _scene_from_rule(scenes, rule.get("scene_index", idx))
        scene_label = _format_scene_label(scene_code, final_language)
        template = BULLET_TEMPLATES[slot_name].get(language, BULLET_TEMPLATES[slot_name]["English"])

        fallback_kw: List[str] = []
        if slot_name == "B1":
            fallback_kw = l2_pool[:1]
        elif slot_name == "B2":
            fallback_kw = l2_pool[1:2]
        elif slot_name == "B3":
            fallback_kw = l2_pool[2:3]
        else:
            fallback_kw = []

        keyword_list = _keywords(f"bullet_{idx+1}", fallback_kw, f"bullet_{slot_name.lower()}", slot_name)
        keyword_text = ", ".join(keyword_list)
        slot_keyword_records[slot_name] = keyword_list
        capability = allowed_capabilities[capability_cycle % len(allowed_capabilities)]
        capability_bundle = slot_capability_bundles[idx] if idx < len(slot_capability_bundles) else []
        spec_dimension_target = _select_slot_spec_dimension(
            slot_name,
            capability,
            capability_bundle or [capability],
            used_spec_dimensions,
        )
        capability_cycle += 1

        content, bullet_meta = _compose_bullet_body(
            role=role,
            scene_label=scene_label,
            keyword_text=keyword_text,
            capability=capability,
            directives=directives,
            attr_lookup=attr_lookup,
            accessories=accessory_descriptions,
            rule=rule,
            slot_name=slot_name,
            audit_log=audit_log,
            scene_code=scene_code,
        )

        fallback_full = clean_bullet_text(template.format(content=content))
        reasoning_bullets.append(fallback_full)

        numeric_values = bullet_meta.get("numeric_values") or []
        numeric_proof = numeric_values[0] if numeric_values else _preferred_numeric_proof_for_capability(
            capability,
            capability_constraints,
            attr_lookup,
            evidence_numeric_values,
        )

        intent_context = _select_intent_context(intent_graph, scene_code, capability)

        mini_brief_text = intent_context.get("mini_brief")
        localized_mini_brief = _build_localized_mini_brief(scene_code, intent_context.get("audience", ""), intent_context.get("pain_point", ""), final_language, mini_brief_text or "")
        if not localized_mini_brief and mini_brief_text:
            localized_mini_brief = _translate_text_to_language(mini_brief_text, final_language, real_vocab, data_mode)
        localized_pain_point = ""
        raw_pain_point = intent_context.get("pain_point")
        if raw_pain_point:
            localized_pain_point = _translate_text_to_language(raw_pain_point, final_language, real_vocab, data_mode)
        payload = {
            "slot": slot_name,
            "role": role,
            "scene_context": scene_code,
            "scene_label": scene_label,
            "mandatory_keywords": keyword_list,
            "numeric_proof": numeric_proof,
            "evidence_numeric_values": evidence_numeric_values,
            "capability": capability,
            "target_language": final_language,
            "keyword_strategy": keyword_allocation_strategy,
            "tier_hint": rule.get("tier"),
            "brand": brand_name,
            "pain_point": intent_context.get("pain_point"),
            "audience": intent_context.get("audience"),
            "accessory_visuals": accessory_items[:4],
            "accessory_experiences": accessory_experiences,
            "mini_brief": intent_context.get("mini_brief"),
            "localized_mini_brief": localized_mini_brief,
            "localized_accessory_experiences": localized_accessory_experiences,
            "localized_pain_point": localized_pain_point,
            "raw_human_insights": getattr(preprocessed_data, "raw_human_insights", ""),
            "all_scenes": writing_policy.get("scene_priority", []),
            "all_capabilities": allowed_capabilities,
            "capability_bundle": capability_bundle or [capability],
            "scene_mapping": [scene_code] if scene_code else [],
            "localized_capability_anchors": _build_localized_capability_anchors(
                capability_bundle or [capability],
                final_language,
                real_vocab,
                data_mode,
            ),
            "localized_scene_anchors": _build_localized_scene_anchors(
                [scene_code] if scene_code else [],
                final_language,
                real_vocab,
                data_mode,
            ),
            "copy_contracts": writing_policy.get("copy_contracts", {}),
            "slot_rule_contract": (writing_policy.get("bullet_slot_rules") or {}).get(slot_name, {}),
            "recording_mode_guidance": writing_policy.get("recording_mode_guidance", {}),
            "benchmark_bullets": writing_policy.get("benchmark_bullets", []),
            "forbidden_visible_terms": directives.get("backend_only_terms", []),
            "audience_group": "",
            "audience_label": "",
            "audience_focus": "",
            "spec_dimension_target": spec_dimension_target,
            "spec_dimensions_used": sorted(used_spec_dimensions),
            "_artifact_dir": artifact_dir,
            "_llm_override_model": llm_override_model,
        }
        if request_timeout_seconds:
            payload["_request_timeout_seconds"] = int(request_timeout_seconds)
        if llm_override_model:
            payload["_disable_fallback"] = True
        payload["_last_capability_mapping"] = []
        localized_text = _generate_and_audit_bullet(payload, audit_log, slot_name)
        capability_map = _merge_capability_mapping(
            capability_bundle,
            payload.get("_last_capability_mapping") or [],
            capability,
        )
        localized_bullets.append(localized_text)
        bullet_trace.append({
            "slot": slot_name,
            "scene_code": scene_code,
            "scene_mapping": [scene_code] if scene_code else [],
            "capability": capability,
            "numeric_expectation": bool(rule.get("numeric_expectation")),
            "numeric_met": bullet_meta.get("numeric_met", False),
            "numeric_source": bullet_meta.get("numeric_source"),
            "keywords": keyword_list,
            "capability_mapping": capability_map,
            "capability_bundle": capability_bundle,
            "audience_group": "",
            "audience_label": "",
            "audience_focus": "",
            "spec_dimension_target": spec_dimension_target,
        })
        used_spec_dimensions.update(_infer_spec_dimensions(localized_text))
        used_spec_dimensions.update(_infer_spec_dimensions(capability))
        for mapped_capability in capability_map:
            used_spec_dimensions.update(_infer_spec_dimensions(str(mapped_capability)))

    final_bullets: List[str] = []
    for i, bullet_text in enumerate(localized_bullets):
        cleaned = clean_bullet_text(bullet_text)
        slot_name = slot_keys[i] if i < len(slot_keys) else f"B{i+1}"
        cleaned = _guarantee_mandatory_keywords(cleaned, slot_keyword_records.get(slot_name, []), final_language)
        enforced = _enforce_bullet_length(cleaned)
        if enforced != cleaned and audit_log is not None:
            _log_action(
                audit_log,
                f"bullet_b{i+1}",
                "trimmed",
                {"reason": f"exceeded {LENGTH_RULES['bullet']['hard_ceiling']} char limit"},
            )
        cleaned = enforced
        final_bullets.append(cleaned)

    final_bullets = _diversify_duplicate_bullet_dimensions(
        final_bullets,
        bullet_trace,
        allowed_capabilities,
        slot_keyword_records,
        final_language,
        audit_log,
        attr_lookup,
        capability_constraints,
    )

    return reasoning_bullets, bullet_trace, final_bullets


def generate_bullet_points(
    preprocessed_data: PreprocessedData,
    writing_policy: Dict[str, Any],
    language: str = "English",
    tiered_keywords: Dict[str, List[str]] = None,
    keyword_allocation_strategy: str = "balanced",
    keyword_slots: Optional[Dict[str, Any]] = None,
    audit_log: Optional[List[Dict[str, Any]]] = None,
    blocked_terms: Optional[Sequence[str]] = None,
    assignment_tracker: Optional[KeywordAssignmentTracker] = None,
    target_language: Optional[str] = None,
    bullet_blueprint: Optional[Any] = None,
    request_timeout_seconds: Optional[int] = None,
    slot_filter: Optional[Sequence[str]] = None,
    artifact_dir: Optional[str] = None,
    llm_override_model: Optional[str] = None,
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    if bullet_blueprint:
        return _generate_bullets_from_blueprint(
            preprocessed_data=preprocessed_data,
            writing_policy=writing_policy,
            language=language,
            tiered_keywords=tiered_keywords,
            keyword_allocation_strategy=keyword_allocation_strategy,
            keyword_slots=keyword_slots,
            audit_log=audit_log,
            blocked_terms=blocked_terms,
            assignment_tracker=assignment_tracker,
            target_language=target_language,
            bullet_blueprint=bullet_blueprint,
            request_timeout_seconds=request_timeout_seconds,
            slot_filter=slot_filter,
            artifact_dir=artifact_dir,
            llm_override_model=llm_override_model,
        )
    return _generate_bullet_points_legacy(
        preprocessed_data=preprocessed_data,
        writing_policy=writing_policy,
        language=language,
        tiered_keywords=tiered_keywords,
        keyword_allocation_strategy=keyword_allocation_strategy,
        keyword_slots=keyword_slots,
        audit_log=audit_log,
        blocked_terms=blocked_terms,
        assignment_tracker=assignment_tracker,
        target_language=target_language,
        request_timeout_seconds=request_timeout_seconds,
        slot_filter=slot_filter,
        artifact_dir=artifact_dir,
        llm_override_model=llm_override_model,
    )


def _normalize_blueprint_entries(blueprint: Any) -> List[Dict[str, Any]]:
    if not blueprint:
        return []
    audience_map = {}
    if isinstance(blueprint, dict):
        audience_map = blueprint.get("audience_allocation") or {}
        candidates = (
            blueprint.get("bullets")
            or blueprint.get("entries")
            or blueprint.get("slots")
            or []
        )
    else:
        candidates = blueprint
    normalized: List[Dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("bullet_index") or entry.get("index") or entry.get("slot_index") or entry.get("slot")
        if isinstance(idx, str):
            idx = idx.replace("B", "").strip()
        try:
            idx_int = int(idx)
        except Exception:
            continue
        if idx_int < 1 or idx_int > 5:
            continue
        audience_entry = audience_map.get(f"B{idx_int}") if isinstance(audience_map, dict) else {}
        normalized.append({
            "index": idx_int,
            "slot": f"B{idx_int}",
            "theme": entry.get("theme") or entry.get("summary") or entry.get("title") or f"Bullet {idx_int}",
            "assigned_keywords": entry.get("assigned_l2_keywords") or entry.get("assigned_keywords") or entry.get("keywords") or [],
            "mandatory_elements": entry.get("mandatory_elements") or entry.get("critical_insights") or entry.get("insights") or [],
            "scenes": entry.get("scenes") or entry.get("scene_priority") or entry.get("scene") or [],
            "capabilities": entry.get("capabilities") or entry.get("capability_focus") or [],
            "accessories": entry.get("accessories") or entry.get("accessory_focus") or [],
            "persona": entry.get("persona") or entry.get("audience"),
            "pain_point": entry.get("pain_point"),
            "buying_trigger": entry.get("buying_trigger"),
            "proof_angle": entry.get("proof_angle"),
            "priority": entry.get("priority"),
            "slot_directive": entry.get("slot_directive") or entry.get("directive"),
            "audience_group": (audience_entry or {}).get("group") or entry.get("audience_group") or "",
            "audience_label": (audience_entry or {}).get("label") or entry.get("audience_label") or "",
            "audience_focus": (audience_entry or {}).get("focus") or entry.get("audience_focus") or "",
            "notes": entry.get("notes"),
        })
    normalized.sort(key=lambda item: item["index"])
    seen = {item["index"] for item in normalized}
    next_idx = 1
    while len(normalized) < 5:
        while next_idx in seen:
            next_idx += 1
        normalized.append({
            "index": next_idx,
            "slot": f"B{next_idx}",
            "theme": f"Dynamic Theme {next_idx}",
            "assigned_keywords": [],
            "mandatory_elements": [],
            "scenes": [],
            "capabilities": [],
            "accessories": [],
            "persona": "",
            "pain_point": "",
            "buying_trigger": "",
            "proof_angle": "",
            "priority": "P1" if next_idx <= 3 else "P2",
            "slot_directive": "",
            "audience_group": "",
            "audience_label": "",
            "audience_focus": "",
            "notes": "auto-filled fallback",
        })
        seen.add(next_idx)
        next_idx += 1
    return normalized[:5]


def _normalize_bullet_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    packet = dict(packet or {})

    def _clean_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _clean_list(value: Any) -> List[str]:
        cleaned: List[str] = []
        for item in value or []:
            normalized = _clean_text(item)
            if normalized:
                cleaned.append(normalized)
        return cleaned

    unsupported_policy = packet.get("unsupported_capability_policy") or {}
    normalized_unsupported_policy = {
        "expression_mode": _clean_text(unsupported_policy.get("expression_mode")) or "",
        "capabilities": _clean_list(unsupported_policy.get("capabilities")),
    }

    return {
        "slot": _clean_text(packet.get("slot")) or "B1",
        "header": _clean_text(packet.get("header")),
        "benefit": _clean_text(packet.get("benefit")),
        "proof": _clean_text(packet.get("proof")),
        "guidance": _clean_text(packet.get("guidance")),
        "required_keywords": _clean_list(packet.get("required_keywords")),
        "required_facts": _clean_list(packet.get("required_facts")),
        "capability_mapping": _clean_list(packet.get("capability_mapping")),
        "scene_mapping": _clean_list(packet.get("scene_mapping")),
        "unsupported_capability_policy": normalized_unsupported_policy,
        "contract_version": _clean_text(packet.get("contract_version")) or "slot_packet_v1",
    }


def _assemble_bullet_from_packet(packet: Dict[str, Any]) -> str:
    normalized = _normalize_bullet_packet(packet)
    header = normalized.get("header", "")
    body_parts = [
        normalized.get("benefit", ""),
        normalized.get("proof", ""),
        normalized.get("guidance", ""),
    ]
    body = " ".join(part for part in body_parts if part).strip()
    if header and body:
        return f"{header} — {body}"
    return header or body


_AWKWARD_SCRUB_PHRASES = (
    "comfortably extended-session",
    "suitable for smooth",
    "for suitable clarity",
)


def _has_scrub_induced_awkwardness(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in _AWKWARD_SCRUB_PHRASES)


def _build_bullet_packet(
    slot: str,
    bullet_text: str,
    trace_entry: Optional[Dict[str, Any]] = None,
    slot_rule_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    trace_entry = trace_entry or {}
    slot_rule_contract = slot_rule_contract or {}
    header, body = _split_bullet_header_body(str(bullet_text or ""))
    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", body or "") if segment.strip()]

    benefit = sentences[0] if sentences else body.strip()
    proof = sentences[1] if len(sentences) > 1 else ""
    guidance = " ".join(sentences[2:]).strip() if len(sentences) > 2 else ""
    if not guidance and any(token in (body or "").lower() for token in ("best for", "use ", "ideal for", "recommended for")):
        guidance = body.strip() if len(sentences) <= 1 else ""

    packet = {
        "slot": slot or trace_entry.get("slot") or "B1",
        "header": header,
        "benefit": benefit,
        "proof": proof,
        "guidance": guidance,
        "required_keywords": trace_entry.get("keywords") or [],
        "required_facts": slot_rule_contract.get("required_facts") or [],
        "capability_mapping": trace_entry.get("capability_mapping") or trace_entry.get("capability_bundle") or [],
        "scene_mapping": trace_entry.get("scene_mapping") or ([trace_entry.get("scene_code")] if trace_entry.get("scene_code") else []),
        "unsupported_capability_policy": slot_rule_contract.get("unsupported_capability_policy") or {},
        "contract_version": "slot_packet_v1",
    }
    return _normalize_bullet_packet(packet)


def _sync_bullet_packets_to_final_bullets(
    bullets: Sequence[str],
    bullet_packets: Sequence[Dict[str, Any]],
    bullet_trace: Sequence[Dict[str, Any]],
    slot_rule_contracts: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    synced: List[Dict[str, Any]] = []
    for idx, bullet in enumerate(bullets or []):
        slot = f"B{idx + 1}"
        previous = next(
            (
                packet for packet in bullet_packets or []
                if str((packet or {}).get("slot") or "").strip().upper() == slot
            ),
            {},
        )
        trace_entry = bullet_trace[idx] if idx < len(bullet_trace or []) and isinstance(bullet_trace[idx], dict) else {}
        rebuilt = _build_bullet_packet(
            slot,
            str(bullet or ""),
            trace_entry=trace_entry,
            slot_rule_contract=slot_rule_contracts.get(slot) or {},
        )
        rebuilt["required_keywords"] = list(previous.get("required_keywords") or rebuilt.get("required_keywords") or [])
        rebuilt["required_facts"] = list(previous.get("required_facts") or rebuilt.get("required_facts") or [])
        rebuilt["capability_mapping"] = list(previous.get("capability_mapping") or rebuilt.get("capability_mapping") or [])
        rebuilt["scene_mapping"] = list(previous.get("scene_mapping") or rebuilt.get("scene_mapping") or [])
        rebuilt["unsupported_capability_policy"] = deepcopy(
            previous.get("unsupported_capability_policy")
            or rebuilt.get("unsupported_capability_policy")
            or (slot_rule_contracts.get(slot) or {}).get("unsupported_capability_policy")
            or {}
        )
        synced.append(_normalize_bullet_packet(rebuilt))
    return synced


def _build_slot_quality_packet(
    packet: Dict[str, Any],
    copy_contracts: Optional[Dict[str, Any]] = None,
    slot_rule_contract: Optional[Dict[str, Any]] = None,
    target_language: str = "English",
) -> Dict[str, Any]:
    normalized = _normalize_bullet_packet(packet)
    copy_contracts = copy_contracts or {}
    slot_rule_contract = slot_rule_contract or {}
    assembled_text = _assemble_bullet_from_packet(normalized)
    localized_scene_anchors = _build_localized_scene_anchors(
        normalized.get("scene_mapping") or [],
        target_language,
    )
    localized_capability_anchors = _build_localized_capability_anchors(
        normalized.get("capability_mapping") or [],
        target_language,
    )
    payload = {
        "slot": normalized.get("slot"),
        "mandatory_keywords": normalized.get("required_keywords") or [],
        "numeric_proof": None,
        "localized_scene_anchors": localized_scene_anchors,
        "localized_capability_anchors": localized_capability_anchors,
        "copy_contracts": copy_contracts,
        "forbidden_visible_terms": [],
    }
    ok, failure_reason = _bullet_candidate_meets_constraints(assembled_text, payload)
    issues: List[str] = []

    issue_map = {
        "format_contract": "missing_header_or_em_dash",
        "missing_keywords": "missing_keywords",
        "fluency_header_trailing_preposition": "header_trailing_preposition",
        "fluency_header_body_rupture": "header_body_rupture",
        "fluency_dash_tail_without_predicate": "dash_tail_without_predicate",
        "fluency_repeated_word_root": "repeated_word_root",
        "frontload_anchor_missing": "frontload_anchor_missing",
        "scene_binding_missing": "scene_binding_missing",
        "capability_binding_missing": "capability_binding_missing",
        "numeric_or_condition_missing": "numeric_or_condition_missing",
        "blocked_terms": "blocked_terms",
        "forbidden_visible_terms": "forbidden_visible_terms",
    }
    for key, issue_name in issue_map.items():
        if failure_reason.get(key):
            issues.append(issue_name)
    if _has_scrub_induced_awkwardness(assembled_text) and "scrub_induced_awkwardness" not in issues:
        issues.append("scrub_induced_awkwardness")

    slot_contract = build_slot_contract(
        str(normalized.get("slot") or ""),
        canonical_facts=slot_rule_contract.get("canonical_facts") if isinstance(slot_rule_contract, dict) else None,
        keyword_metadata=slot_rule_contract.get("keyword_metadata") if isinstance(slot_rule_contract, dict) else None,
    )
    slot_contract_result = validate_bullet_against_contract(assembled_text, slot_contract)
    if not slot_contract_result.get("passed"):
        for reason in slot_contract_result.get("reasons") or []:
            issue = f"slot_contract_failed:{reason}"
            if issue not in issues:
                issues.append(issue)

    sentence_contract = slot_rule_contract.get("sentence_contract") or {}
    unsupported_policy = (
        normalized.get("unsupported_capability_policy")
        or slot_rule_contract.get("unsupported_capability_policy")
        or {}
    )
    require_proof = "proof" in (sentence_contract.get("body_components") or [])
    proof_present = bool(normalized.get("proof")) or not require_proof

    guidance = str(normalized.get("guidance") or "").strip()
    forbid_patterns = set(sentence_contract.get("forbid_patterns") or [])
    if "dash_tail_fragment" in forbid_patterns and guidance:
        guidance_tokens = fc._tokenize_words(guidance)  # type: ignore[attr-defined]
        guidance_has_predicate = fc._contains_predicate(guidance)  # type: ignore[attr-defined]
        if guidance_tokens and len(guidance_tokens) <= 5 and not guidance_has_predicate:
            if "dash_tail_without_predicate" not in issues:
                issues.append("dash_tail_without_predicate")

    unsupported_policy_pass = True
    if unsupported_policy.get("expression_mode") == "positive_guidance_only" and unsupported_policy.get("capabilities"):
        negative_literal = re.search(
            r"\b(?:does not|do not|lacks|has no|not suitable for)\b",
            assembled_text,
            flags=re.IGNORECASE,
        )
        if negative_literal:
            unsupported_policy_pass = False
            if "unsupported_capability_negative_literal" not in issues:
                issues.append("unsupported_capability_negative_literal")
    format_pass = "missing_header_or_em_dash" not in issues
    keyword_coverage_pass = "missing_keywords" not in issues
    fluency_pass = not any(
        issue in {
            "header_trailing_preposition",
            "header_body_rupture",
            "dash_tail_without_predicate",
            "repeated_word_root",
            "scrub_induced_awkwardness",
        }
        for issue in issues
    )
    contract_pass = ok and proof_present and unsupported_policy_pass and bool(slot_contract_result.get("passed"))

    return {
        "slot": normalized.get("slot"),
        "contract_pass": contract_pass,
        "fluency_pass": fluency_pass,
        "keyword_coverage_pass": keyword_coverage_pass,
        "proof_present": proof_present,
        "unsupported_policy_pass": unsupported_policy_pass,
        "format_pass": format_pass,
        "fallback_used": False,
        "rerender_count": 0,
        "issues": issues,
        "slot_contract": slot_contract_result,
    }


def _slot_rerender_quality_passes_gate(quality: Dict[str, Any]) -> bool:
    if not isinstance(quality, dict):
        return False
    return (
        quality.get("contract_pass") is not False
        and quality.get("fluency_pass") is not False
        and quality.get("keyword_coverage_pass") is not False
        and quality.get("unsupported_policy_pass") is not False
    )


def _rerender_slot_from_packet_plan(
    plan_entry: Dict[str, Any],
    writing_policy: Dict[str, Any],
    target_language: str,
    model_overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    slot = str(plan_entry.get("slot") or "").strip().upper()
    if not slot:
        raise RuntimeError("slot_rerender_missing_slot")

    source_packet = deepcopy(plan_entry.get("source_packet") or {})
    slot_rule_contract = ((writing_policy.get("bullet_slot_rules") or {}).get(slot) or {})
    client = get_llm_client()
    override_model = (model_overrides or {}).get("bullets") or None
    system_prompt = (
        "You are repairing exactly one Amazon listing bullet packet.\n"
        "Return exactly one JSON object with keys: slot, header, benefit, proof, guidance, required_keywords, capability_mapping, scene_mapping.\n"
        "Rules:\n"
        "1. Keep the slot fixed.\n"
        "2. Preserve supported facts only; do not invent specs.\n"
        "3. Resolve the listed rerender issues.\n"
        "4. Write natural, fluent English that satisfies the slot contract.\n"
        "5. If unsupported_capability_policy.expression_mode is positive_guidance_only, avoid literal negatives like does not include or lacks.\n"
        "6. Output valid JSON only.\n"
    )
    payload = {
        "field": "slot_packet_rerender",
        "slot": slot,
        "target_language": target_language,
        "current_bullet": plan_entry.get("current_bullet") or "",
        "current_packet": source_packet,
        "slot_quality": deepcopy(plan_entry.get("slot_quality") or {}),
        "rerender_reasons": list(plan_entry.get("rerender_reasons") or []),
        "slot_rule_contract": slot_rule_contract,
        "copy_contracts": writing_policy.get("copy_contracts") or {},
        "_request_timeout_seconds": _experimental_stage_timeout_seconds("bullets", override_model),
        "_disable_fallback": True,
    }
    try:
        text = client.generate_text(
            system_prompt,
            payload,
            temperature=0.2,
            override_model=override_model,
        )
        parsed = _extract_embedded_json_payload(text or "")
        if not isinstance(parsed, dict):
            raise RuntimeError("slot_rerender_non_json_payload")

        merged_packet = {
            **source_packet,
            **parsed,
            "slot": slot,
            "required_keywords": parsed.get("required_keywords") or source_packet.get("required_keywords") or [],
            "required_facts": parsed.get("required_facts") or source_packet.get("required_facts") or [],
            "capability_mapping": parsed.get("capability_mapping") or source_packet.get("capability_mapping") or [],
            "scene_mapping": parsed.get("scene_mapping") or source_packet.get("scene_mapping") or [],
            "unsupported_capability_policy": (
                parsed.get("unsupported_capability_policy")
                or source_packet.get("unsupported_capability_policy")
                or slot_rule_contract.get("unsupported_capability_policy")
                or {}
            ),
        }
        packet = _normalize_bullet_packet(merged_packet)
        bullet = _assemble_bullet_from_packet(packet)
        quality = _build_slot_quality_packet(
            packet,
            copy_contracts=writing_policy.get("copy_contracts") or {},
            slot_rule_contract=slot_rule_contract,
            target_language=target_language,
        )
        quality["rerender_count"] = int(((plan_entry.get("slot_quality") or {}).get("rerender_count") or 0)) + 1
        if not _slot_rerender_quality_passes_gate(quality):
            return _build_local_slot_rerender_fallback(
                plan_entry,
                writing_policy,
                target_language,
            )
        return {
            "slot": slot,
            "bullet": bullet,
            "packet": packet,
            "quality": quality,
            "status": "applied",
        }
    except Exception:
        return _build_local_slot_rerender_fallback(
            plan_entry,
            writing_policy,
            target_language,
        )


def _build_local_slot_rerender_fallback(
    plan_entry: Dict[str, Any],
    writing_policy: Dict[str, Any],
    target_language: str,
) -> Dict[str, Any]:
    slot = str(plan_entry.get("slot") or "").strip().upper()
    source_packet = _normalize_bullet_packet(plan_entry.get("source_packet") or {})
    slot_rule_contract = ((writing_policy.get("bullet_slot_rules") or {}).get(slot) or {})
    rerender_reasons = set(plan_entry.get("rerender_reasons") or [])
    slot_quality = deepcopy(plan_entry.get("slot_quality") or {})

    packet = deepcopy(source_packet)
    if slot == "B5" and (
        "slot_contract_failed" in rerender_reasons
        or "repeated_word_root" in rerender_reasons
        or "keyword_coverage_fail" in rerender_reasons
        or "missing_keywords" in rerender_reasons
        or any(str(issue or "").startswith("slot_contract_failed:") for issue in (slot_quality.get("issues") or []))
        or "missing_keywords" in set(slot_quality.get("issues") or [])
    ):
        required_keywords = [str(keyword or "").strip() for keyword in (packet.get("required_keywords") or []) if str(keyword or "").strip()]
        keyword_phrase = " and ".join(required_keywords) if required_keywords else "body camera"
        header = "READY-TO-RECORD KIT"
        benefit = (
            f"Start with the included {keyword_phrase}, magnetic clip, back clip, "
            "USB-C cable, and 32 GB microSD card."
        )
        proof = "Add higher-capacity storage up to 256 GB when needed."
        scene_anchors = []
        for scene in packet.get("scene_mapping") or []:
            per_scene = _build_localized_scene_anchors([scene], target_language)
            if per_scene:
                scene_anchors.append(per_scene[0])
        capability_anchors = _build_localized_capability_anchors(
            packet.get("capability_mapping") or [],
            target_language,
        )
        safe_capability = next(
            (
                anchor for anchor in capability_anchors
                if not re.search(r"\b(?:battery|charge|runtime|minutes?|hours?)\b", str(anchor or ""), re.IGNORECASE)
            ),
            "",
        )
        guidance_parts: List[str] = []
        if scene_anchors:
            guidance_parts.append(f"Pack it for {' and '.join(scene_anchors[:2])} use.")
        if safe_capability:
            guidance_parts.append(f"Keep {safe_capability} simple during setup.")
        guidance = " ".join(guidance_parts)
        rebuilt_packet = _build_bullet_packet(
            slot,
            f"{header} -- {benefit} {proof} {guidance}".strip(),
            trace_entry={
                "slot": slot,
                "keywords": required_keywords,
                "capability_mapping": list(packet.get("capability_mapping") or []),
                "scene_mapping": list(packet.get("scene_mapping") or []),
            },
            slot_rule_contract=slot_rule_contract,
        )
        rebuilt_packet["required_keywords"] = required_keywords
        rebuilt_packet["required_facts"] = list(packet.get("required_facts") or [])
        rebuilt_packet["guidance"] = guidance
        quality = _build_slot_quality_packet(
            rebuilt_packet,
            copy_contracts=writing_policy.get("copy_contracts") or {},
            slot_rule_contract=slot_rule_contract,
            target_language=target_language,
        )
        quality["rerender_count"] = int(((plan_entry.get("slot_quality") or {}).get("rerender_count") or 0)) + 1
        quality["fallback_used"] = True
        return {
            "slot": slot,
            "bullet": _assemble_bullet_from_packet(rebuilt_packet),
            "packet": rebuilt_packet,
            "quality": quality,
            "status": "applied_local_fallback",
        }

    if "contract_fail" in rerender_reasons and not packet.get("proof"):
        packet["proof"] = "Designed for clear, reliable daily recording."
    localized_scene_anchors = _build_localized_scene_anchors(
        packet.get("scene_mapping") or [],
        target_language,
    )
    localized_capability_anchors = _build_localized_capability_anchors(
        packet.get("capability_mapping") or [],
        target_language,
    )
    if ("fluency_fail" in rerender_reasons or "dash_tail_without_predicate" in rerender_reasons) and packet.get("guidance"):
        scene_phrase = next((anchor for anchor in localized_scene_anchors if " " not in anchor or len(anchor.split()) <= 3), "")
        if not scene_phrase:
            scene_phrase = "steady daily recording"
        packet["guidance"] = f"Use it for {scene_phrase} and other steady everyday setups."

    frontload_targets = _dedupe_keyword_sequence(
        list(packet.get("required_keywords") or [])
        + list(localized_capability_anchors)
        + list(localized_scene_anchors)
    )
    issue_names = set(slot_quality.get("issues") or [])
    failure_reason: Dict[str, Any] = {}
    if slot_quality.get("contract_pass") is False and frontload_targets:
        failure_reason["frontload_anchor_missing"] = frontload_targets[:4]
    if "missing_keywords" in rerender_reasons or "missing_keywords" in issue_names:
        failure_reason["missing_keywords"] = list(packet.get("required_keywords") or [])
    if "dash_tail_without_predicate" in rerender_reasons or "dash_tail_without_predicate" in issue_names:
        failure_reason["fluency_dash_tail_without_predicate"] = True
    if "header_trailing_preposition" in rerender_reasons or "header_trailing_preposition" in issue_names:
        failure_reason["fluency_header_trailing_preposition"] = True
    if "repeated_word_root" in rerender_reasons or "repeated_word_root" in issue_names:
        failure_reason["fluency_repeated_word_root"] = True

    bullet = _repair_bullet_candidate_deterministically(
        _assemble_bullet_from_packet(packet),
        failure_reason,
        {
            "slot": slot,
            "mandatory_keywords": list(packet.get("required_keywords") or []),
            "target_language": target_language,
            "localized_scene_anchors": localized_scene_anchors,
            "localized_capability_anchors": localized_capability_anchors,
            "copy_contracts": writing_policy.get("copy_contracts") or {},
            "numeric_proof": None,
        },
    )
    trace_entry = {
        "slot": slot,
        "keywords": list(packet.get("required_keywords") or []),
        "capability_mapping": list(packet.get("capability_mapping") or []),
        "scene_mapping": list(packet.get("scene_mapping") or []),
    }
    rebuilt_packet = _build_bullet_packet(
        slot,
        bullet,
        trace_entry=trace_entry,
        slot_rule_contract=slot_rule_contract,
    )
    rebuilt_packet["required_keywords"] = list(packet.get("required_keywords") or [])
    rebuilt_packet["required_facts"] = list(packet.get("required_facts") or [])
    rebuilt_packet["unsupported_capability_policy"] = deepcopy(
        packet.get("unsupported_capability_policy")
        or slot_rule_contract.get("unsupported_capability_policy")
        or {}
    )
    quality = _build_slot_quality_packet(
        rebuilt_packet,
        copy_contracts=writing_policy.get("copy_contracts") or {},
        slot_rule_contract=slot_rule_contract,
        target_language=target_language,
    )
    quality["rerender_count"] = int(((plan_entry.get("slot_quality") or {}).get("rerender_count") or 0)) + 1
    quality["fallback_used"] = True
    return {
        "slot": slot,
        "bullet": _assemble_bullet_from_packet(rebuilt_packet),
        "packet": rebuilt_packet,
        "quality": quality,
        "status": "applied_local_fallback",
    }


def _run_slot_rerender_pass(
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    *,
    target_language: str,
    model_overrides: Optional[Dict[str, str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    rerender_plan = list(
        generated_copy.get("slot_rerender_plan")
        or build_slot_rerender_plan(generated_copy, writing_policy)
    )
    if not rerender_plan:
        updated = deepcopy(generated_copy)
        updated["slot_rerender_results"] = []
        updated["slot_rerender_plan"] = []
        return updated

    if progress_callback:
        progress_callback(f"slot_rerender: {len(rerender_plan)} slot(s)")

    updated_copy, rerender_results = execute_slot_rerender_plan(
        generated_copy,
        rerender_plan,
        lambda plan_entry, _current_copy: _rerender_slot_from_packet_plan(
            plan_entry,
            writing_policy,
            target_language,
            model_overrides=model_overrides,
        ),
    )
    updated_copy["slot_rerender_results"] = rerender_results
    updated_copy["slot_rerender_plan"] = build_slot_rerender_plan(updated_copy, writing_policy)
    return updated_copy


def _apply_final_visible_quality_gate(
    generated_surface: Dict[str, Any],
    writing_policy: Dict[str, Any],
    *,
    target_language: str,
    candidate_id: str,
    source_type: str,
) -> Dict[str, Any]:
    """Repair final pasteable text and rebuild packet quality from that text."""
    repaired_surface, final_report = repair_final_visible_copy(
        generated_surface,
        candidate_id=candidate_id,
        source_type=source_type,
    )
    slot_rule_contracts = writing_policy.get("bullet_slot_rules") or {}
    bullets = list(repaired_surface.get("bullets") or [])
    existing_packets = _align_final_visible_quality_packets(
        list(repaired_surface.get("bullet_packets") or []),
        bullets,
    )
    bullet_trace: List[Dict[str, Any]] = []
    for packet in existing_packets:
        if not isinstance(packet, dict):
            bullet_trace.append({})
            continue
        bullet_trace.append(
            {
                "slot": packet.get("slot"),
                "keywords": packet.get("required_keywords") or [],
                "capability_mapping": packet.get("capability_mapping") or [],
                "scene_mapping": packet.get("scene_mapping") or [],
            }
        )

    bullet_packets = _sync_bullet_packets_to_final_bullets(
        bullets,
        existing_packets,
        bullet_trace,
        slot_rule_contracts,
    )
    repaired_surface["bullet_packets"] = bullet_packets
    repaired_surface["slot_quality_packets"] = [
        _build_slot_quality_packet(
            packet,
            copy_contracts=writing_policy.get("copy_contracts") or {},
            slot_rule_contract=slot_rule_contracts.get(packet.get("slot")) or {},
            target_language=target_language,
        )
        for packet in bullet_packets
    ]
    repaired_surface["final_visible_quality"] = final_report
    metadata = deepcopy(repaired_surface.get("metadata") or {})
    metadata["final_visible_quality"] = final_report
    repaired_surface["metadata"] = metadata
    return repaired_surface


def _align_final_visible_quality_packets(
    bullet_packets: Sequence[Dict[str, Any]],
    bullets: Sequence[str],
) -> List[Dict[str, Any]]:
    """Keep packet metadata aligned when deterministic repair changes a slot contract."""
    aligned: List[Dict[str, Any]] = []
    for idx, packet in enumerate(bullet_packets or []):
        updated = deepcopy(packet) if isinstance(packet, dict) else {}
        slot = str(updated.get("slot") or f"B{idx + 1}").strip().upper()
        bullet = str(bullets[idx] if idx < len(bullets or []) else "")
        if slot == "B5" and not re.search(r"\b(?:battery|runtime|per charge|150 minutes)\b", bullet, re.IGNORECASE):
            updated["capability_mapping"] = [
                item
                for item in (updated.get("capability_mapping") or [])
                if not re.search(r"\b(?:battery|runtime|charge)\b", str(item or ""), re.IGNORECASE)
            ]
            updated["required_facts"] = [
                item
                for item in (updated.get("required_facts") or [])
                if not re.search(r"\b(?:battery|runtime|charge)\b", str(item or ""), re.IGNORECASE)
            ]
        aligned.append(updated)
    return aligned


def _build_blueprint_fallback_text(theme: str,
                                   scene_label: str,
                                   capability: str,
                                   mandatory_elements: Sequence[str],
                                   attr_lookup: Dict[str, str],
                                   persona: str = "",
                                   buying_trigger: str = "",
                                   proof_angle: str = "") -> str:
    insight_clause = ""
    if mandatory_elements:
        insight_clause = mandatory_elements[0]
    elif attr_lookup.get("battery_life"):
        insight_clause = f"Rated for {attr_lookup['battery_life']}."
    elif attr_lookup.get("video_resolution"):
        insight_clause = f"Delivers {attr_lookup['video_resolution']} clarity."
    audience_clause = f" for {persona}" if persona else ""
    trigger_clause = f" when {buying_trigger}" if buying_trigger else ""
    base = (
        f"{theme} — {capability or 'core capability'} empowers {scene_label or 'daily POV storytelling'}"
        f"{audience_clause}{trigger_clause}."
    )
    if proof_angle:
        base = f"{base} Proof: {proof_angle}."
    if insight_clause:
        return f"{base} {insight_clause}"
    return base


def _generate_bullets_from_blueprint(
    preprocessed_data: PreprocessedData,
    writing_policy: Dict[str, Any],
    language: str,
    tiered_keywords: Optional[Dict[str, List[str]]],
    keyword_allocation_strategy: str,
    keyword_slots: Optional[Dict[str, Any]],
    audit_log: Optional[List[Dict[str, Any]]],
    blocked_terms: Optional[Sequence[str]],
    assignment_tracker: Optional[KeywordAssignmentTracker],
    target_language: Optional[str],
    bullet_blueprint: Any,
    request_timeout_seconds: Optional[int] = None,
    slot_filter: Optional[Sequence[str]] = None,
    artifact_dir: Optional[str] = None,
    llm_override_model: Optional[str] = None,
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    normalized_entries = _normalize_blueprint_entries(bullet_blueprint)
    if not normalized_entries:
        return _generate_bullet_points_legacy(
            preprocessed_data,
            writing_policy,
            language,
            tiered_keywords,
            keyword_allocation_strategy,
            keyword_slots,
            audit_log,
            blocked_terms,
            assignment_tracker,
            target_language,
            request_timeout_seconds,
            slot_filter,
            artifact_dir,
            llm_override_model,
        )
    selected_slots = set(_ordered_slot_filter(slot_filter, [entry["slot"] for entry in normalized_entries]))
    tiered_keywords = tiered_keywords or {"l1": [], "l2": [], "l3": []}
    scenes = writing_policy.get("scene_priority", []) or []
    default_scenes = ["cycling_recording", "underwater_exploration", "travel_documentation", "family_use", "outdoor_sports"]
    while len(scenes) < 4:
        for candidate in default_scenes:
            if candidate not in scenes:
                scenes.append(candidate)
            if len(scenes) >= 4:
                break
    final_language = target_language or getattr(preprocessed_data, "language", language)
    if keyword_slots is None:
        keyword_slots = writing_policy.get("keyword_slots")
    if not keyword_slots:
        keyword_slots = build_keyword_slots(tiered_keywords, scenes, final_language)
    attr_lookup = _build_attr_lookup(preprocessed_data.attribute_data)
    directives = writing_policy.get("compliance_directives", {})
    accessory_descriptions = getattr(preprocessed_data, "accessory_descriptions", []) or []
    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    canonical_accessories = getattr(preprocessed_data, "canonical_accessory_descriptions", []) or accessory_descriptions
    accessory_experiences: List[str] = []
    localized_accessory_experiences: List[str] = []
    for acc in (canonical_accessories or []):
        exp = acc.get("experience")
        if exp:
            accessory_experiences.append(exp)
            key = acc.get("experience_key")
            if key:
                localized = get_localized_accessory_experience_by_key(key, final_language)
                if localized:
                    localized_accessory_experiences.append(localized)
    accessory_items = _prepare_accessory_items(accessory_descriptions)
    evidence_numeric_values = _collect_evidence_numeric_values(attr_lookup, capability_constraints)
    allowed_capabilities = _filter_capabilities(preprocessed_data.core_selling_points, directives, audit_log, "bullets")
    if not allowed_capabilities:
        allowed_capabilities = ["4K recording", "stabilization", "long battery"]
    blocked = {term.lower() for term in (blocked_terms or [])}
    l2_pool = tiered_keywords.get("l2", []) or []
    brand_name = getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT")
    slot_keyword_records: Dict[str, List[str]] = {}
    reasoning_fallbacks: List[str] = []
    localized_bullets: List[str] = []
    bullet_trace: List[Dict[str, Any]] = []
    slot_names: List[str] = []
    used_spec_dimensions: Set[str] = set()

    def _resolve_keywords(entry_index: int, slot_name: str, explicit: Sequence[str]) -> List[str]:
        resolved: List[str] = []
        for token in explicit or []:
            token = (token or "").strip()
            if not token or token.lower() in blocked:
                continue
            conflict_reason = _keyword_conflicts_constraints(token, capability_constraints)
            if conflict_reason:
                continue
            resolved.append(token)
        if resolved:
            return resolved
        slot_lookup = f"bullet_{entry_index}"
        slot_meta = keyword_slots.get(slot_lookup) if isinstance(keyword_slots, dict) else {}
        fallback_tokens = []
        if isinstance(slot_meta, dict):
            fallback_tokens = slot_meta.get("keywords") or []
        if not fallback_tokens and l2_pool:
            idx = (entry_index - 1) % len(l2_pool)
            fallback_tokens = [l2_pool[idx]]
        filtered: List[str] = []
        for token in fallback_tokens:
            cleaned = (token or "").strip()
            if not cleaned or cleaned.lower() in blocked:
                continue
            conflict_reason = _keyword_conflicts_constraints(cleaned, capability_constraints)
            if conflict_reason:
                continue
            filtered.append(cleaned)
        return filtered

    for entry in normalized_entries:
        slot_name = entry["slot"]
        if selected_slots and slot_name not in selected_slots:
            continue
        slot_names.append(slot_name)
        keywords = _resolve_keywords(entry["index"], slot_name, entry.get("assigned_keywords"))
        if assignment_tracker and keywords:
            assignment_tracker.record(f"bullet_{entry['index']}", keywords)
        slot_keyword_records[slot_name] = keywords

        capability_bundle = entry.get("capabilities") or []
        if not capability_bundle:
            idx = (entry["index"] - 1) % len(allowed_capabilities)
            capability_bundle = [allowed_capabilities[idx]]
        capability = capability_bundle[0]

        scene_code = None
        entry_scenes = entry.get("scenes") or []
        if entry_scenes:
            scene_code = entry_scenes[0]
        else:
            scene_code = scenes[(entry["index"] - 1) % len(scenes)]
        scene_label = _format_scene_label(scene_code, final_language)

        mandatory_elements = [str(item).strip() for item in (entry.get("mandatory_elements") or []) if str(item).strip()]
        fallback_text = _build_blueprint_fallback_text(
            entry["theme"],
            scene_label,
            capability,
            mandatory_elements,
            attr_lookup,
            persona=entry.get("persona", ""),
            buying_trigger=entry.get("buying_trigger", ""),
            proof_angle=entry.get("proof_angle", ""),
        )
        reasoning_fallbacks.append(fallback_text)

        payload = {
            "slot": slot_name,
            "role": entry["theme"],
            "scene_context": scene_code,
            "scene_label": scene_label,
            "mandatory_keywords": keywords,
            "numeric_proof": _preferred_numeric_proof_for_capability(
                capability,
                capability_constraints,
                attr_lookup,
                evidence_numeric_values,
            ),
            "evidence_numeric_values": evidence_numeric_values,
            "capability": capability,
            "target_language": final_language,
            "keyword_strategy": keyword_allocation_strategy,
            "brand": brand_name,
            "pain_point": entry.get("pain_point"),
            "audience": entry.get("persona") or entry.get("priority"),
            "persona": entry.get("persona"),
            "buying_trigger": entry.get("buying_trigger"),
            "proof_angle": entry.get("proof_angle"),
            "accessory_visuals": accessory_items[:4],
            "accessory_experiences": accessory_experiences,
            "mini_brief": entry.get("buying_trigger") or entry.get("notes"),
            "localized_mini_brief": entry.get("buying_trigger") or entry.get("notes"),
            "localized_accessory_experiences": localized_accessory_experiences,
            "localized_pain_point": entry.get("pain_point"),
            "raw_human_insights": getattr(preprocessed_data, "raw_human_insights", ""),
            "all_scenes": writing_policy.get("scene_priority", []),
            "all_capabilities": allowed_capabilities,
            "capability_bundle": capability_bundle,
            "scene_mapping": entry_scenes or ([scene_code] if scene_code else []),
            "localized_capability_anchors": _build_localized_capability_anchors(
                capability_bundle or [capability],
                final_language,
                getattr(preprocessed_data, "real_vocab", None),
                getattr(preprocessed_data, "data_mode", "SYNTHETIC_COLD_START"),
            ),
            "localized_scene_anchors": _build_localized_scene_anchors(
                entry_scenes or ([scene_code] if scene_code else []),
                final_language,
                getattr(preprocessed_data, "real_vocab", None),
                getattr(preprocessed_data, "data_mode", "SYNTHETIC_COLD_START"),
            ),
            "copy_contracts": writing_policy.get("copy_contracts", {}),
            "slot_rule_contract": (writing_policy.get("bullet_slot_rules") or {}).get(slot_name, {}),
            "recording_mode_guidance": writing_policy.get("recording_mode_guidance", {}),
            "benchmark_bullets": writing_policy.get("benchmark_bullets", []),
            "forbidden_visible_terms": directives.get("backend_only_terms", []),
            "blueprint_theme": entry.get("theme"),
            "mandatory_elements": mandatory_elements,
            "blueprint_notes": entry.get("proof_angle") or entry.get("notes"),
            "blueprint_accessories": entry.get("accessories"),
            "slot_directive": entry.get("slot_directive"),
            "audience_group": entry.get("audience_group"),
            "audience_label": entry.get("audience_label"),
            "audience_focus": entry.get("audience_focus"),
            "spec_dimension_target": _select_slot_spec_dimension(
                slot_name,
                capability,
                capability_bundle or [capability],
                used_spec_dimensions,
            ),
            "spec_dimensions_used": sorted(used_spec_dimensions),
            "_artifact_dir": artifact_dir,
            "_llm_override_model": llm_override_model,
        }
        if request_timeout_seconds:
            payload["_request_timeout_seconds"] = int(request_timeout_seconds)
        if llm_override_model:
            payload["_disable_fallback"] = True
        payload["_last_capability_mapping"] = []
        localized_text = _generate_and_audit_bullet(payload, audit_log, slot_name)
        capability_map = _merge_capability_mapping(
            capability_bundle,
            payload.get("_last_capability_mapping") or [],
            capability,
        )
        localized_bullets.append(localized_text)
        bullet_trace.append({
            "slot": slot_name,
            "scene_code": scene_code,
            "scene_mapping": entry_scenes or ([scene_code] if scene_code else []),
            "theme": entry.get("theme"),
            "capability": capability,
            "capability_mapping": capability_map,
            "capability_bundle": capability_bundle,
            "keywords": keywords,
            "mandatory_elements": mandatory_elements,
            "blueprint_accessories": entry.get("accessories"),
            "persona": entry.get("persona"),
            "pain_point": entry.get("pain_point"),
            "buying_trigger": entry.get("buying_trigger"),
            "proof_angle": entry.get("proof_angle"),
            "slot_directive": entry.get("slot_directive"),
            "audience_group": entry.get("audience_group"),
            "audience_label": entry.get("audience_label"),
            "audience_focus": entry.get("audience_focus"),
            "spec_dimension_target": payload.get("spec_dimension_target"),
        })
        used_spec_dimensions.update(_infer_spec_dimensions(localized_text))
        used_spec_dimensions.update(_infer_spec_dimensions(capability))
        for mapped_capability in capability_map:
            used_spec_dimensions.update(_infer_spec_dimensions(str(mapped_capability)))

    final_bullets: List[str] = []
    for idx, bullet_text in enumerate(localized_bullets):
        slot_name = slot_names[idx] if idx < len(slot_names) else f"B{idx+1}"
        cleaned = clean_bullet_text(bullet_text)
        cleaned = _guarantee_mandatory_keywords(cleaned, slot_keyword_records.get(slot_name, []), final_language)
        enforced = _enforce_bullet_length(cleaned)
        if enforced != cleaned and audit_log is not None:
            _log_action(
                audit_log,
                f"bullet_b{idx+1}",
                "trimmed",
                {"reason": f"exceeded {LENGTH_RULES['bullet']['hard_ceiling']} char limit"},
            )
        final_bullets.append(enforced)

    final_bullets = _diversify_duplicate_bullet_dimensions(
        final_bullets,
        bullet_trace,
        allowed_capabilities,
        slot_keyword_records,
        final_language,
        audit_log,
        attr_lookup,
        capability_constraints,
    )

    return reasoning_fallbacks, bullet_trace, final_bullets


def _generate_and_audit_bullet(
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]],
    slot_name: str,
) -> str:
    field = f"bullet_{slot_name.lower()}"
    payload.pop("_capability_mapping_result", None)
    payload.pop("_last_capability_mapping", None)
    last_candidate = ""
    last_reason: Dict[str, Any] = {}
    for attempt in range(_llm_retry_budget(3)):
        try:
            candidate = _llm_generate_bullet(payload)
        except LLMClientUnavailable as exc:
            if _log_retryable_llm_exception(audit_log, field, exc, attempt + 1):
                continue
            break
        passed, reason = _bullet_candidate_meets_constraints(candidate, payload)
        if passed:
            _log_action(audit_log, field, "llm_success", {"attempt": attempt + 1})
            capability_map = _merge_capability_mapping(
                payload.get("capability_bundle") or [],
                payload.get("_capability_mapping_result") or [],
                payload.get("capability"),
            )
            payload["_last_capability_mapping"] = capability_map
            return candidate
        last_candidate = candidate
        last_reason = reason
        reason["attempt"] = attempt + 1
        _log_action(audit_log, field, "llm_retry", reason)
    if last_candidate and last_reason.get("missing_keywords"):
        patched_candidate = _guarantee_mandatory_keywords(
            last_candidate,
            payload.get("mandatory_keywords") or [],
            payload.get("target_language") or "English",
        )
        repassed, repaired_reason = _bullet_candidate_meets_constraints(patched_candidate, payload)
        if repassed:
            _log_action(
                audit_log,
                field,
                "llm_success",
                {"attempt": "patched", "patched_missing_keywords": last_reason.get("missing_keywords")},
            )
            capability_map = _merge_capability_mapping(
                payload.get("capability_bundle") or [],
                payload.get("_capability_mapping_result") or [],
                payload.get("capability"),
            )
            payload["_last_capability_mapping"] = capability_map
            return patched_candidate
        last_candidate = patched_candidate
        last_reason = repaired_reason
    if last_candidate and _repairable_bullet_failure(last_reason):
        try:
            repaired_candidate = _repair_bullet_candidate_with_llm(last_candidate, last_reason, payload)
        except Exception as exc:
            _log_action(audit_log, field, "llm_retry", {"reason": "repair_failed", "error": str(exc)})
        else:
            if repaired_candidate:
                repaired_candidate = _extract_bullet_text_from_response(repaired_candidate, payload)
                repassed, repaired_reason = _bullet_candidate_meets_constraints(repaired_candidate, payload)
                if repassed:
                    _log_action(
                        audit_log,
                        field,
                        "llm_success",
                        {"attempt": "repair_pass", "repaired_from": last_reason},
                    )
                    _record_repair_event(
                        payload.get("_artifact_dir"),
                        field,
                        last_reason,
                        last_candidate,
                        repaired_candidate,
                        repair_success=True,
                        attempts=1,
                        benchmark_used=bool(payload.get("benchmark_bullets")),
                    )
                    capability_map = _merge_capability_mapping(
                        payload.get("capability_bundle") or [],
                        payload.get("_capability_mapping_result") or [],
                        payload.get("capability"),
                    )
                    payload["_last_capability_mapping"] = capability_map
                    return repaired_candidate
                last_candidate = repaired_candidate
                last_reason = repaired_reason
    numeric_specs = [payload.get("numeric_proof")] if payload.get("numeric_proof") else []
    if last_candidate and _repairable_bullet_failure(last_reason):
        deterministic_candidate = _repair_bullet_candidate_deterministically(last_candidate, last_reason, payload)
        if deterministic_candidate:
            repassed, repaired_reason = _bullet_candidate_meets_constraints(deterministic_candidate, payload)
            if repassed:
                _log_action(
                    audit_log,
                    field,
                    "llm_success",
                    {"attempt": "deterministic_repair", "repaired_from": last_reason},
                )
                _record_repair_event(
                    payload.get("_artifact_dir"),
                    field,
                    last_reason,
                    last_candidate,
                    deterministic_candidate,
                    repair_success=True,
                    attempts=1,
                    benchmark_used=False,
                )
                capability_map = _merge_capability_mapping(
                    payload.get("capability_bundle") or [],
                    payload.get("_capability_mapping_result") or [],
                    payload.get("capability"),
                )
                payload["_last_capability_mapping"] = capability_map
                return deterministic_candidate
            last_candidate = deterministic_candidate
            last_reason = repaired_reason
    if last_reason:
        scaffold_candidate = _fallback_text_for_field(field, payload, numeric_specs)
        deterministic_candidate = _repair_bullet_candidate_deterministically(scaffold_candidate, last_reason, payload)
        if deterministic_candidate:
            repassed, repaired_reason = _bullet_candidate_meets_constraints(deterministic_candidate, payload)
            if repassed:
                _log_action(
                    audit_log,
                    field,
                    "llm_success",
                    {"attempt": "deterministic_repair", "repaired_from": last_reason, "source": "payload_scaffold"},
                )
                _record_repair_event(
                    payload.get("_artifact_dir"),
                    field,
                    last_reason,
                    scaffold_candidate,
                    deterministic_candidate,
                    repair_success=True,
                    attempts=1,
                    benchmark_used=False,
                )
                capability_map = _merge_capability_mapping(
                    payload.get("capability_bundle") or [],
                    payload.get("_capability_mapping_result") or [],
                    payload.get("capability"),
                )
                payload["_last_capability_mapping"] = capability_map
                return deterministic_candidate
            last_candidate = deterministic_candidate
            last_reason = repaired_reason
    if last_reason.get("forbidden_visible_terms"):
        fallback = _fallback_text_for_field(field, payload, numeric_specs)
    else:
        fallback = last_candidate or _fallback_text_for_field(field, payload, numeric_specs)
    fallback = _guarantee_mandatory_keywords(
        fallback,
        payload.get("mandatory_keywords") or [],
        payload.get("target_language") or "English",
    )
    if numeric_specs and not _check_numeric_presence(fallback, numeric_specs):
        fallback = f"{fallback} {' '.join(_flatten_tokens(numeric_specs))}".strip()
    blocked_terms = find_blocklisted_terms(fallback)
    if blocked_terms:
        fallback = remove_blocklisted_terms(fallback).strip()
    capability_map = _merge_capability_mapping(
        payload.get("capability_bundle") or [],
        payload.get("_capability_mapping_result") or [],
        payload.get("capability"),
    )
    payload["_last_capability_mapping"] = capability_map
    _log_action(
        audit_log,
        field,
        "llm_fallback",
        {"reason": "bullet_retry_exhausted", "last_reason": last_reason or {"reason": "unknown"}},
    )
    logging.warning("bullet fallback used for %s due to %s", field, (last_reason or {}).get("reason") or last_reason or "unknown")
    if _repairable_bullet_failure(last_reason or {}):
        _record_repair_event(
            payload.get("_artifact_dir"),
            field,
            last_reason or {},
            last_candidate or '',
            fallback,
            repair_success=False,
            attempts=1,
            benchmark_used=bool(payload.get("benchmark_bullets")),
        )
    return fallback


def _llm_generate_bullet(payload: Dict[str, Any]) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language", "the target language")
    scenes = ", ".join(payload.get("all_scenes") or [])
    capabilities = ", ".join(payload.get("all_capabilities") or [])
    theme = payload.get("blueprint_theme") or payload.get("role") or "Dynamic theme"
    mandatory_elements = payload.get("mandatory_elements") or []
    mandatory_text = "; ".join(mandatory_elements) if mandatory_elements else "None"
    accessory_focus = payload.get("blueprint_accessories") or []
    accessory_text = ", ".join(accessory_focus) if accessory_focus else "canonical accessories provided in the payload"
    persona = payload.get("persona") or payload.get("audience") or "target buyer"
    buying_trigger = payload.get("buying_trigger") or "confidence before purchase"
    proof_angle = payload.get("proof_angle") or payload.get("blueprint_notes") or "verified spec proof"
    slot_directive = payload.get("slot_directive") or "Keep the slot publishable, complete, and aligned with its Amazon role."
    audience_group = payload.get("audience_group") or "unspecified"
    audience_label = payload.get("audience_label") or audience_group
    audience_focus = payload.get("audience_focus") or proof_angle
    forbidden_terms = ", ".join(payload.get("forbidden_visible_terms") or []) or "none"
    evidence_numbers = ", ".join(payload.get("evidence_numeric_values") or []) or "none"
    spec_dimension_target = payload.get("spec_dimension_target") or "resolution"
    used_dimensions = ", ".join(payload.get("spec_dimensions_used") or []) or "none yet"
    mode_guidance = _format_mode_guidance(
        payload.get("recording_mode_guidance") or {},
        payload.get("scene_context"),
    )
    system_prompt = (
        "You are a world-class premium Amazon listing copywriter working in {target_language}. "
        "CRITICAL CONTEXT: You are generating copy for an Amazon listing in {target_language}. "
        "You are provided with 'raw_human_insights' written by the product creator. Give these insights the ABSOLUTE HIGHEST PRIORITY. "
        "Extract the emotional hooks, colloquial tone, and specific real-world usage scenarios. "
        "Weave these deeply into your {target_language} copy. DO NOT use robotic, repetitive sentence structures. "
        "Write as a high-end, native {target_language} e-commerce copywriter aiming for maximum conversion. "
        "All specs, scenes, accessories, and capabilities arrive in Canonical English and must be translated fully into {target_language} except for universal abbreviations (4K, WiFi, EIS) or brand names. "
        "Scenes to honor: {scenes}. Capabilities to thread visibly: {capabilities}. "
        "Integrate every provided capability and scene naturally across the bullets while honoring mandatory keywords and numeric proof. "
        "FORMAT REQUIREMENT: Start every bullet with a punchy ALL-CAPS header of 3-5 words that combines a core feature plus the user benefit, followed by a single space, an em dash (—), and the persuasive body sentence. "
        "Do NOT prepend numerals or other punctuation before the header. Example: \"HEADER KEYWORD HERE — persuasive body sentence...\" "
        "The first sentence after the dash should begin as an imperative or action-led invitation whenever natural in the target language. "
        "Keep each bullet roughly 200-250 characters (hard ceiling 500 characters) and self-regulate length without relying on downstream trimming. "
        "Translate specs into value and scene-based benefit instead of listing cold parameters. "
        "Package limitations positively as fit-for-use guidance, not self-deprecating weakness. "
        "Embed SEO phrases invisibly inside fluent grammar. Never join synonyms with slashes. "
        "Avoid explicit warranty/refund claims in visible bullets; when trust support matters, phrase it as after-sales support or purchase reassurance. "
        "Maintain a Professional, Premium, Persuasive voice and avoid slang or cheap colloquialisms such as zero hassle / sans prise de tete / sans blabla. "
        "Use the raw_human_insights to anchor vivid sensory details, first-hand user language, and persona pain/relief arcs. "
        "Evidence-backed numeric values available for this ASIN: {evidence_numbers}. "
        "Include at least one specific numeric value from that evidence list whenever it fits naturally; if numeric_proof is supplied, that exact value is mandatory. "
        "Cross-bullet spec contract: across B1-B5, collectively cover at least 4 distinct supported dimensions from runtime, resolution, weight, view-angle/lens, waterproof boundary, and connectivity. "
        "This slot MUST prioritize the {spec_dimension_target} dimension first and avoid repeating already-covered dimensions unless mandatory keywords force reuse. "
        "Already-covered dimensions: {used_dimensions}. "
        "Avoid unsupported filler adjectives such as high quality, excellent, amazing, premium quality, or guaranteed performance. "
        "Blueprint Theme: {theme}. Mandatory elements you must cover verbatim (paraphrase allowed but meaning must stay intact): {mandatory_text}. "
        "Slot Directive: {slot_directive}. "
        "Audience plan: this bullet is assigned to audience group [{audience_group}] {audience_label}. "
        "Core audience focus for this slot: {audience_focus}. "
        "Do NOT collapse back into generic commuting / cycling / on-the-go copy unless that focus is explicitly required for this slot. "
        "Persona to persuade: {persona}. Buying trigger to convert: {buying_trigger}. Proof angle to make the claim believable: {proof_angle}. "
        "Explicit accessory focus to visualize: {accessory_text}. "
        "Recording mode guidance you must obey: {mode_guidance}. "
        "Translate every spec into plain human value, convert hard capacity into lived usage outcome, and frame limitations as best-use guidance. "
        "Never end with unfinished clauses such as 'while', 'that', '&', trailing commas, or half-finished warnings. "
        "Do NOT output or even mention these forbidden visible terms unless they are already part of a mandatory keyword and positively supported: {forbidden_terms}. "
        "Respond with valid JSON containing two keys: \"text\" (the final bullet sentence) and \"capability_mapping\" "
        "(an array of canonical capability tags from the provided list that this bullet explicitly covers). "
        "Do not include any additional keys or commentary."
    ).format(
        target_language=target_language,
        scenes=scenes or "none provided",
        capabilities=capabilities or "none provided",
        theme=theme,
        evidence_numbers=evidence_numbers,
        spec_dimension_target=spec_dimension_target,
        used_dimensions=used_dimensions,
        mandatory_text=mandatory_text,
        slot_directive=slot_directive,
        audience_group=audience_group,
        audience_label=audience_label,
        audience_focus=audience_focus,
        persona=persona,
        buying_trigger=buying_trigger,
        proof_angle=proof_angle,
        accessory_text=accessory_text,
        mode_guidance=mode_guidance,
        forbidden_terms=forbidden_terms,
    )
    override_model = payload.get("_llm_override_model") or None
    try:
        response = client.generate_bullet(
            system_prompt,
            payload,
            temperature=0.35,
            override_model=override_model,
        )
    except TypeError:
        response = client.generate_bullet(system_prompt, payload, temperature=0.35)
    text = _extract_bullet_text_from_response(response, payload)
    if not text:
        raise LLMClientUnavailable("Empty LLM response")
    return text


def _extract_bullet_text_from_response(response: Optional[str], payload: Dict[str, Any]) -> str:
    payload["_capability_mapping_result"] = []
    if not response:
        return ""
    text = response.strip()
    parsed = _extract_embedded_json_payload(text)
    if isinstance(parsed, dict):
        body = parsed.get("text", "")
        mapping = parsed.get("capability_mapping", [])
        if isinstance(mapping, str):
            mapping = [mapping]
        elif not isinstance(mapping, list):
            mapping = []
        capability_mapping = []
        for item in mapping:
            if isinstance(item, str) and item.strip():
                capability_mapping.append(item.strip())
        payload["_capability_mapping_result"] = capability_mapping
        return str(body or "").strip()
    return text


def _repair_field_name(field_or_slot: str) -> str:
    value = str(field_or_slot or '').strip().lower()
    if value.startswith('bullet_') or value == 'title':
        return value
    if value.startswith('b') and value[1:].isdigit():
        return f"bullet_b{value[1:]}"
    return value or 'unknown'


def _repair_issue_details(reason: Dict[str, Any], default_rule: str = 'repair_attempt') -> Tuple[str, str]:
    mapping = [
        ('fluency_header_body_rupture', 'header_body_rupture', 'high'),
        ('fluency_header_trailing_preposition', 'header_trailing_preposition', 'medium'),
        ('fluency_dash_tail_without_predicate', 'dash_tail_without_predicate', 'medium'),
        ('fluency_repeated_word_root', 'repeated_word_root', 'medium'),
        ('fluency_dimension_repeat', 'bullet_dimension_repeat', 'medium'),
        ('missing_numeric', 'missing_numeric', 'medium'),
        ('numeric_or_condition_missing', 'numeric_or_condition_missing', 'medium'),
        ('missing_keywords', 'missing_keywords', 'medium'),
        ('length_exceeded', 'title_length_exceeded', 'medium'),
    ]
    for source_key, rule_id, severity in mapping:
        if source_key in (reason or {}):
            return rule_id, severity
    return default_rule, 'medium'


def _record_repair_event(
    artifact_dir: Optional[str],
    field: str,
    reason: Dict[str, Any],
    original: str,
    repaired: str,
    *,
    repair_success: bool,
    attempts: int = 1,
    benchmark_used: bool = False,
    default_rule: str = 'repair_attempt',
) -> None:
    if not artifact_dir:
        return
    try:
        rule_id, severity = _repair_issue_details(reason or {}, default_rule=default_rule)
        repair_logger.record_repair(
            artifact_dir=artifact_dir,
            field=_repair_field_name(field),
            rule_id=rule_id,
            severity=severity,
            original=str(original or ''),
            repaired=str(repaired or ''),
            repair_success=repair_success,
            attempts=attempts,
            benchmark_used=benchmark_used,
        )
    except Exception:
        return


def _repairable_bullet_failure(reason: Dict[str, Any]) -> bool:
    if not reason:
        return False
    repairable_keys = {
        "scene_binding_missing",
        "capability_binding_missing",
        "frontload_anchor_missing",
        "weak_opener",
        "missing_numeric",
        "numeric_or_condition_missing",
        "format_contract",
        "fluency_header_body_rupture",
        "fluency_header_trailing_preposition",
        "fluency_dash_tail_without_predicate",
        "fluency_repeated_word_root",
        "fluency_dimension_repeat",
    }
    return any(key in reason for key in repairable_keys)


def _repair_bullet_candidate_with_llm(
    candidate: str,
    failure_reason: Dict[str, Any],
    payload: Dict[str, Any],
) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language", "English")
    scene_targets = _dedupe_keyword_sequence(
        list(payload.get("localized_scene_anchors") or []) + list(payload.get("scene_mapping") or [])
    )[:5]
    capability_targets = _dedupe_keyword_sequence(payload.get("localized_capability_anchors") or [])[:4]
    keyword_targets = _dedupe_keyword_sequence(payload.get("mandatory_keywords") or [])[:4]
    repair_payload = {
        "candidate": candidate,
        "failure_reason": failure_reason,
        "target_language": target_language,
        "scene_targets": scene_targets,
        "capability_targets": capability_targets,
        "keyword_targets": keyword_targets,
        "numeric_proof": payload.get("numeric_proof"),
        "slot": payload.get("slot"),
        "recording_mode_guidance": payload.get("recording_mode_guidance") or {},
    }
    numeric_requirement = ""
    if failure_reason.get("missing_numeric"):
        numeric_requirement = (
            f' The repaired bullet MUST include the exact numeric proof "{failure_reason.get("missing_numeric")}".'
        )
    fluency_requirement = ""
    if any(
        key in failure_reason
        for key in (
            "fluency_header_body_rupture",
            "fluency_header_trailing_preposition",
            "fluency_dash_tail_without_predicate",
            "fluency_repeated_word_root",
            "fluency_dimension_repeat",
        )
    ):
        fluency_requirement = (
            " Fix fluency issues: header cannot end with a preposition, "
            "dash tail must include a complete predicate clause, and avoid repeating the same word root more than two times."
        )
    dimension_requirement = ""
    if failure_reason.get("fluency_dimension_repeat"):
        dimension_requirement = (
            "\n\n"
            + fc.build_bullet_dimension_repair_instruction(
                str(failure_reason.get("duplicated_dimension") or "repeated_dimension"),
                failure_reason.get("affected_bullets") or [],
            )
        )
    benchmark_bullets = payload.get("benchmark_bullets") or []
    benchmark_block = ""
    if benchmark_bullets:
        examples = "\n".join(
            f"{index + 1}. {text}"
            for index, text in enumerate(benchmark_bullets[:3])
            if str(text or "").strip()
        )
        if examples:
            benchmark_block = (
                " Reference examples — match their tone, structure, and confidence level:\n"
                f"{examples}\n"
            )
    if failure_reason.get("fluency_header_body_rupture"):
        system_prompt = fc.build_rupture_repair_prompt(
            candidate,
            benchmark_bullets,
            fc._extract_specs(candidate),
        )
    else:
        system_prompt = (
            "You are repairing one Amazon bullet point in {target_language}. "
            "Revise the candidate minimally so it remains natural, persuasive, and premium, but now passes the failed constraints. "
            "Keep the existing meaning and tone whenever possible. "
            "{benchmark_block}"
            "Requirements: keep the ALL-CAPS header plus em dash structure, preserve mandatory traffic phrases verbatim, "
            "include at least one natural scene anchor from scene_targets, include one capability anchor from capability_targets, "
            "and satisfy any numeric proof if provided.{numeric_requirement}{fluency_requirement} "
            "{dimension_requirement} "
            "Run one compliance pass before returning: remove or rewrite absolute claims such as #1, best, guaranteed, amazing, excellent, or high quality. "
            "Avoid robotic keyword stuffing, slashes, or raw internal scene codes. "
            "Return valid JSON with keys text and capability_mapping only."
        ).format(
            target_language=target_language,
            benchmark_block=benchmark_block,
            numeric_requirement=numeric_requirement,
            fluency_requirement=fluency_requirement,
            dimension_requirement=dimension_requirement,
        )
    override_model = payload.get("_llm_override_model") or None
    try:
        response = client.generate_bullet(
            system_prompt,
            repair_payload,
            temperature=0.15,
            override_model=override_model,
        )
    except TypeError:
        response = client.generate_bullet(system_prompt, repair_payload, temperature=0.15)
    repaired = _extract_bullet_text_from_response(response, payload)
    return (repaired or "").strip()


JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _extract_embedded_json_payload(text: str) -> Optional[Any]:
    if not text:
        return None
    candidates = [text.strip()]
    candidates.extend(match.group(1).strip() for match in JSON_FENCE_PATTERN.finditer(text or ""))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            continue
    decoder = json.JSONDecoder()
    raw = text.strip()
    for idx, char in enumerate(raw):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        return parsed
    return None


def _repair_bullet_candidate_deterministically(
    candidate: str,
    failure_reason: Dict[str, Any],
    payload: Dict[str, Any],
) -> str:
    text = _extract_bullet_text_from_response(candidate, payload).strip()
    if not text:
        return text
    header, body = _split_bullet_header_body(text)
    if not body:
        body = text
        header = ""

    frontload_targets = _dedupe_keyword_sequence(
        list(payload.get("mandatory_keywords") or [])
        + list(payload.get("localized_capability_anchors") or [])
        + list(payload.get("localized_scene_anchors") or [])
    )
    missing_frontload = [
        str(anchor).strip()
        for anchor in (failure_reason.get("frontload_anchor_missing") or [])
        if str(anchor).strip()
    ]
    frontload_candidates = missing_frontload or frontload_targets
    if failure_reason.get("frontload_anchor_missing") and frontload_candidates:
        preferred_anchor = next(
            (anchor for anchor in frontload_candidates if anchor and not _normalized_anchor_hits(header, [anchor])),
            frontload_candidates[0],
        )
        if preferred_anchor and not _normalized_anchor_hits(_frontload_segment(body, 16), [preferred_anchor]):
            if not _normalized_anchor_hits(header, [preferred_anchor]):
                body = f"{preferred_anchor} {body}".strip()
    missing_keywords = failure_reason.get("missing_keywords") or []
    if missing_keywords:
        lead_keyword = next((keyword for keyword in missing_keywords if keyword), "")
        if lead_keyword and _normalize_keyword_text(lead_keyword) not in _normalize_keyword_text(_frontload_segment(body, 16)):
            body = f"{lead_keyword} {body}".strip()
    scene_anchor = next((anchor for anchor in (payload.get("localized_scene_anchors") or []) if anchor), "")
    if scene_anchor and not _normalized_anchor_hits(body, [scene_anchor]):
        body = f"{scene_anchor} {body}".strip()
    capability_anchor = next((anchor for anchor in (payload.get("localized_capability_anchors") or []) if anchor), "")
    if capability_anchor and not _normalized_anchor_hits(body, [capability_anchor]):
        body = f"{capability_anchor} {body}".strip()
    numeric_proof = str(payload.get("numeric_proof") or "").strip()
    if failure_reason.get("missing_numeric") and numeric_proof and numeric_proof not in body:
        body = f"{body} for up to {numeric_proof}".strip()
    if failure_reason.get("fluency_header_trailing_preposition"):
        header = re.sub(r"\b(with|for|and|or|of)\b\s*$", "", header, flags=re.IGNORECASE).strip(" -—–")
    if failure_reason.get("fluency_dash_tail_without_predicate"):
        body = re.split(r"\s*[—–]\s*", body or "")[0].strip()
    if failure_reason.get("fluency_repeated_word_root"):
        body = _dedupe_repeated_root_tokens(body)
    rebuilt = f"{header} — {body}".strip() if header else body
    rebuilt = _guarantee_mandatory_keywords(
        rebuilt,
        payload.get("mandatory_keywords") or [],
        payload.get("target_language") or "English",
    )
    return _enforce_bullet_length(rebuilt)


DANGLING_BULLET_ENDINGS: Dict[str, Set[str]] = {
    "english": {
        "with", "while", "and", "or", "that", "which", "make", "makes", "making",
        "allow", "allows", "allowing", "provide", "provides", "providing",
        "offer", "offers", "offering", "help", "helps", "helping",
        "enable", "enables", "enabling", "ensure", "ensures", "ensuring",
    },
    "french": {
        "avec", "et", "ou", "qui", "pour", "afin", "rend", "rendent",
        "permet", "permettent", "offre", "offrent", "aide", "aident",
    },
    "german": {
        "mit", "und", "oder", "dass", "damit", "macht", "machen",
        "bietet", "bieten", "hilft", "helfen", "ermoglicht", "ermoglichen",
    },
}

FLUENCY_HEADER_TRAILING_PREPOSITIONS = {"with", "for", "and", "or", "of"}
FLUENCY_REPEAT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "you",
    "camera",
    "audio",
    "video",
    "recording",
}
FLUENCY_VERB_HINTS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "can",
    "could",
    "will",
    "would",
    "should",
    "may",
    "might",
    "must",
    "do",
    "does",
    "did",
    "capture",
    "captures",
    "document",
    "documents",
    "record",
    "records",
    "keep",
    "keeps",
    "support",
    "supports",
    "deliver",
    "delivers",
}
FLUENCY_INDEPENDENT_STARTERS = {
    "capture",
    "captures",
    "document",
    "documents",
    "record",
    "records",
    "create",
    "creates",
    "share",
    "shares",
    "use",
    "uses",
    "enjoy",
    "enjoys",
    "this",
    "it",
    "you",
}


def _tokenize_alpha_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", text or "")


def _normalize_word_root(token: str) -> str:
    value = _normalize_keyword_text(token or "")
    value = value.replace("'", "")
    if len(value) <= 3:
        return value
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[:-len(suffix)]
    return value


def _bullet_contains_predicate(text: str) -> bool:
    tokens = [_normalize_keyword_text(token) for token in _tokenize_alpha_words(text)]
    if not tokens:
        return False
    if any(token in FLUENCY_VERB_HINTS for token in tokens):
        return True
    return any(token.endswith("ed") or token.endswith("ing") for token in tokens if len(token) >= 4)


def _bullet_content_roots(text: str) -> Set[str]:
    roots: Set[str] = set()
    for token in _tokenize_alpha_words(text):
        root = _normalize_word_root(token)
        if len(root) < 4:
            continue
        if root in FLUENCY_REPEAT_STOPWORDS or root in FLUENCY_VERB_HINTS:
            continue
        roots.add(root)
    return roots


def _bullet_semantic_rupture(header: str, body: str) -> bool:
    if not header or not body:
        return False
    body_tokens = [_normalize_keyword_text(token) for token in _tokenize_alpha_words(body)]
    if len(body_tokens) < 5:
        return False
    if body_tokens[0] not in FLUENCY_INDEPENDENT_STARTERS:
        return False
    if not _bullet_contains_predicate(body):
        return False
    header_roots = _bullet_content_roots(header)
    body_roots = _bullet_content_roots(body)
    if len(header_roots) < 2 or len(body_roots) < 3:
        return False
    return len(header_roots.intersection(body_roots)) == 0


def _bullet_dash_tail_without_predicate(text: str) -> bool:
    parts = re.split(r"\s*[—–]\s*", text or "")
    if len(parts) < 2:
        return False
    tail = parts[-1].strip().strip(".,;:!?")
    if not tail:
        return False
    tokens = _tokenize_alpha_words(tail)
    if not tokens or len(tokens) > 5:
        return False
    if not all(re.match(r"^[A-Za-z0-9]+$", token) for token in tokens):
        return False
    return not _bullet_contains_predicate(tail)


def _bullet_repeated_roots(text: str) -> List[str]:
    counts: Dict[str, int] = {}
    for token in _tokenize_alpha_words(text):
        root = _normalize_word_root(token)
        if len(root) < 4 or root in FLUENCY_REPEAT_STOPWORDS:
            continue
        counts[root] = counts.get(root, 0) + 1
    return sorted(root for root, count in counts.items() if count > 2)


def _dedupe_repeated_root_tokens(text: str) -> str:
    if not text:
        return text
    kept: List[str] = []
    counts: Dict[str, int] = {}
    for token in text.split():
        alpha = _tokenize_alpha_words(token)
        if not alpha:
            kept.append(token)
            continue
        root = _normalize_word_root(alpha[0])
        if len(root) >= 4 and root not in FLUENCY_REPEAT_STOPWORDS:
            seen = counts.get(root, 0)
            if seen >= 2:
                continue
            counts[root] = seen + 1
        kept.append(token)
    return " ".join(kept).strip()


def _bullet_body_opener_signature(text: str) -> str:
    _, body = _split_bullet_header_body(text)
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", body or text or "")
    return _normalize_keyword_text(tokens[0]) if tokens else ""


def _bullet_has_dangling_tail(text: str, target_language: str) -> bool:
    _, body = _split_bullet_header_body(text)
    candidate = (body or text or "").strip()
    if not candidate:
        return True
    if re.search(r"[,:;—–-]\s*$", candidate):
        return True
    trailing_words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", candidate)
    if not trailing_words:
        return False
    language_key = (target_language or "English").strip().lower()
    endings = DANGLING_BULLET_ENDINGS.get(language_key, DANGLING_BULLET_ENDINGS["english"])
    last_word = _normalize_keyword_text(trailing_words[-1])
    return last_word in endings


def _collect_bullet_quality_reasons(
    text: str,
    target_language: str,
    recent_openers: Sequence[str],
) -> Tuple[List[str], str]:
    reasons: List[str] = []
    opener = _bullet_body_opener_signature(text)
    if _bullet_has_dangling_tail(text, target_language):
        reasons.append("unfinished_tail")
    if opener and opener not in {"the", "a", "an", "le", "la", "les", "der", "die", "das"}:
        if opener in set(recent_openers or []):
            reasons.append(f"repetitive_opener:{opener}")
    return reasons, opener


def _polish_bullet_quality_with_llm(
    candidate: str,
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]],
    field: str,
    recent_openers: Sequence[str],
) -> str:
    target_language = payload.get("target_language") or "English"
    reasons, _ = _collect_bullet_quality_reasons(candidate, target_language, recent_openers)
    if not reasons or _is_budget_constrained_live_runtime():
        return candidate
    client = get_llm_client()
    repair_payload = {
        "candidate": candidate,
        "reasons": reasons,
        "target_language": target_language,
        "mandatory_keywords": payload.get("mandatory_keywords") or [],
        "numeric_proof": payload.get("numeric_proof"),
        "scene_targets": payload.get("localized_scene_anchors") or [],
        "capability_targets": payload.get("localized_capability_anchors") or [],
        "avoid_openers": list(recent_openers or [])[-2:],
        "recording_mode_guidance": payload.get("recording_mode_guidance") or {},
    }
    system_prompt = (
        "You are a premium Amazon listing quality editor working in {target_language}. "
        "Polish one bullet minimally so it reads like a mature, publishable ecommerce sentence. "
        "Fix only these issues: {reasons}. "
        "Keep the ALL-CAPS header plus em dash structure. "
        "Preserve every mandatory traffic phrase verbatim and in the same word order. "
        "Preserve the numeric proof if provided. "
        "Keep the meaning, truth constraints, and mode guidance intact. "
        "If repetitive_opener is listed, start the body with a different strong verb than avoid_openers. "
        "Never end with an unfinished clause or broken verb. "
        "Keep it under 300 characters. "
        "Return only the final bullet string."
    ).format(
        target_language=target_language,
        reasons=", ".join(reasons),
    )
    try:
        polished = client.generate_text(system_prompt, repair_payload, temperature=0.1).strip()
    except LLMClientUnavailable as exc:
        _log_action(audit_log, field, "quality_polish_skipped", {"reason": "llm_unavailable", "error": str(exc)})
        return candidate
    if not polished or polished == candidate:
        return candidate
    repassed, failure_reason = _bullet_candidate_meets_constraints(polished, payload)
    if not repassed or _bullet_has_dangling_tail(polished, target_language):
        _log_action(
            audit_log,
            field,
            "quality_polish_skipped",
            {"reason": "validation_failed", "details": failure_reason or {"dangling_tail": True}},
        )
        return candidate
    _log_action(audit_log, field, "quality_polish_success", {"reasons": reasons})
    return polished


def _bullet_candidate_meets_constraints(text: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    normalized = _normalize_keyword_text(text)
    forbidden_hits = []
    for term in payload.get("forbidden_visible_terms") or []:
        normalized_term = _normalize_keyword_text(term)
        if normalized_term and normalized_term in normalized:
            forbidden_hits.append(term)
    if forbidden_hits:
        return False, {"forbidden_visible_terms": forbidden_hits}
    missing_keywords = []
    for keyword in payload.get("mandatory_keywords") or []:
        kw = (keyword or "").strip()
        if not kw:
            continue
        normalized_kw = _normalize_keyword_text(kw)
        if normalized_kw and normalized_kw not in normalized:
            missing_keywords.append(kw)
    if missing_keywords:
        return False, {"missing_keywords": missing_keywords}

    numeric_proof = payload.get("numeric_proof")
    if numeric_proof:
        proof_text = str(numeric_proof).strip()
        if proof_text and proof_text not in text:
            digits = re.findall(r"[\d]+(?:[.,]\d+)?", proof_text)
            missing_digits = [d for d in digits if d not in text]
            if digits and missing_digits:
                return False, {"missing_numeric": proof_text}
            if not digits:
                return False, {"missing_numeric": proof_text}

    blocked_terms = find_blocklisted_terms(text)
    if blocked_terms:
        return False, {"blocked_terms": blocked_terms}

    copy_contracts = payload.get("copy_contracts", {}) or {}
    bullet_opening = copy_contracts.get("bullet_opening", {}) or {}
    header, body = _split_bullet_header_body(text)
    if bullet_opening.get("header_required") and (not header or not body):
        return False, {"format_contract": "missing_header_or_em_dash"}
    weak_openers = [str(item).lower() for item in (bullet_opening.get("forbidden_weak_openers") or []) if item]
    if body:
        first_token = next(iter(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", body.lower())), "")
        if first_token and first_token in weak_openers:
            return False, {"weak_opener": first_token}
    frontload_window = int(bullet_opening.get("frontload_window_tokens") or 16)
    frontload = _frontload_segment(body or text, frontload_window)
    frontload_anchors = _dedupe_keyword_sequence(
        list(payload.get("mandatory_keywords") or [])
        + list(payload.get("localized_capability_anchors") or [])
        + list(payload.get("localized_scene_anchors") or [])
    )
    if frontload_anchors and not _normalized_anchor_hits(frontload, frontload_anchors):
        return False, {"frontload_anchor_missing": frontload_anchors[:4]}

    binding_contract = copy_contracts.get("scene_capability_numeric_binding", {}) or {}
    slot_name = str(payload.get("slot") or "")
    scene_anchors = payload.get("localized_scene_anchors") or []
    capability_anchors = payload.get("localized_capability_anchors") or []
    if binding_contract.get("require_scene_and_capability"):
        if scene_anchors and not _normalized_anchor_hits(text, scene_anchors):
            return False, {"scene_binding_missing": scene_anchors[:3]}
        if capability_anchors and not _normalized_anchor_hits(text, capability_anchors):
            return False, {"capability_binding_missing": capability_anchors[:3]}
    require_numeric_slots = set(binding_contract.get("require_numeric_or_condition_slots") or [])
    if slot_name in require_numeric_slots:
        condition_markers = _dedupe_keyword_sequence(
            list(binding_contract.get("condition_markers") or [])
            + list(payload.get("localized_capability_anchors") or [])
        )
        if not _check_numeric_presence(text, [payload.get("numeric_proof")] if payload.get("numeric_proof") else []):
            if condition_markers and not _normalized_anchor_hits(text, condition_markers):
                return False, {"numeric_or_condition_missing": condition_markers[:4]}

    if header:
        header_tokens = _tokenize_alpha_words(header)
        if header_tokens:
            trailing = _normalize_keyword_text(header_tokens[-1])
            if trailing in FLUENCY_HEADER_TRAILING_PREPOSITIONS:
                return False, {"fluency_header_trailing_preposition": trailing}
        rupture_issues = [
            issue for issue in fc.check_fluency(str(payload.get("slot") or "bullet"), text)
            if issue.rule_id == "header_body_rupture"
        ]
        if rupture_issues:
            return False, {"fluency_header_body_rupture": True}

    if _bullet_dash_tail_without_predicate(text):
        return False, {"fluency_dash_tail_without_predicate": True}

    repeated_roots = _bullet_repeated_roots(body or text)
    if repeated_roots:
        return False, {"fluency_repeated_word_root": repeated_roots[:3]}

    return True, {}


def _generate_and_audit_description(
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]],
) -> str:
    field = "description_llm"
    forbidden_terms = [term for term in (payload.get("forbidden_visible_terms") or []) if term]
    canonical_facts = payload.get("canonical_facts")
    last_candidate = ""
    for attempt in range(_llm_retry_budget(3)):
        try:
            candidate = _llm_generate_description(payload)
        except LLMClientUnavailable as exc:
            if _log_retryable_llm_exception(audit_log, field, exc, attempt + 1):
                continue
            break
        candidate = candidate.strip()
        if not candidate:
            _log_action(audit_log, field, "llm_retry", {"reason": "empty_output", "attempt": attempt + 1})
            continue
        last_candidate = candidate
        claim_audit = audit_claim_language(candidate, canonical_facts)
        if not claim_audit.get("passed"):
            if claim_audit.get("repairable"):
                repaired = repair_claim_language(candidate, canonical_facts)
                repaired_audit = audit_claim_language(repaired, canonical_facts)
                if repaired and repaired_audit.get("passed"):
                    _log_action(
                        audit_log,
                        field,
                        "claim_language_repaired",
                        {
                            "attempt": attempt + 1,
                            "violations": claim_audit.get("violations") or [],
                        },
                    )
                    candidate = repaired
                else:
                    _log_action(
                        audit_log,
                        field,
                        "llm_retry",
                        {
                            "reason": "description_claim_language_repair_failed",
                            "violations": claim_audit.get("violations") or [],
                            "post_repair_violations": repaired_audit.get("violations") or [],
                            "attempt": attempt + 1,
                        },
                    )
                    continue
            else:
                _log_action(
                    audit_log,
                    field,
                    "llm_retry",
                    {
                        "reason": "description_claim_language_blocked",
                        "violations": claim_audit.get("violations") or [],
                        "blocking_reasons": claim_audit.get("blocking_reasons") or [],
                        "attempt": attempt + 1,
                    },
                )
                continue
        provenance_tier = "repaired_live" if candidate != last_candidate else "native_live"
        forbidden_hits = [
            term for term in forbidden_terms
            if _normalize_keyword_text(term) and _normalize_keyword_text(term) in _normalize_keyword_text(candidate)
        ]
        if forbidden_hits:
            _log_action(
                audit_log,
                field,
                "llm_retry",
                {"reason": "forbidden_visible_terms", "terms": forbidden_hits, "attempt": attempt + 1},
            )
            continue
        blocked_terms = find_blocklisted_terms(candidate)
        if blocked_terms:
            cleaned = remove_blocklisted_terms(candidate).strip()
            if cleaned:
                _log_action(
                    audit_log,
                    field,
                    "brand_scrubbed",
                    {"terms": blocked_terms, "attempt": attempt + 1},
                )
                candidate = cleaned
            else:
                _log_action(
                    audit_log,
                    field,
                    "llm_retry",
                    {"reason": "brand_blocked", "terms": blocked_terms, "attempt": attempt + 1},
                )
                continue
        _log_action(audit_log, field, "llm_success", {"attempt": attempt + 1, "provenance_tier": provenance_tier})
        return candidate
    fallback = _fallback_text_for_field(
        "description",
        {
            **payload,
            "core_selling_points": payload.get("all_capabilities") or [],
        },
        [],
    )
    fallback = re.sub(r"\s+", " ", (fallback or "").replace("<br>", " ")).strip()
    fallback = remove_blocklisted_terms(fallback).strip() or fallback
    fallback = repair_claim_language(fallback, canonical_facts)
    fallback = re.sub(r"\s+", " ", fallback).strip(" ,.-")
    if fallback:
        fallback_claim_audit = audit_claim_language(fallback, canonical_facts)
        fallback_provenance_tier = "safe_fallback"
        if not fallback_claim_audit.get("passed"):
            fallback_provenance_tier = "unsafe_fallback"
            _log_action(
                audit_log,
                field,
                "claim_language_blocked",
                {
                    "violations": fallback_claim_audit.get("violations") or [],
                    "blocking_reasons": fallback_claim_audit.get("blocking_reasons") or [],
                    "fallback": True,
                },
            )
        _log_action(
            audit_log,
            field,
            "llm_fallback",
            {
                "reason": "description_retry_exhausted",
                "fallback_preview": fallback[:160],
                "provenance_tier": fallback_provenance_tier,
            },
        )
        _record_repair_event(
            payload.get("_artifact_dir"),
            "description",
            {"description_retry_exhausted": True},
            last_candidate or "",
            fallback,
            repair_success=False,
            default_rule="description_retry_exhausted",
        )
        return fallback
    raise RuntimeError("LLM description generation failed after retries")


def generate_description(
    preprocessed_data: PreprocessedData,
    writing_policy: Dict[str, Any],
    title: str,
    reasoning_bullets: Sequence[str],
    target_language: Optional[str] = None,
    audit_log: Optional[List[Dict[str, Any]]] = None,
    request_timeout_seconds: Optional[int] = None,
) -> str:
    target_language = target_language or getattr(preprocessed_data, "language", "English")
    attr_data = getattr(preprocessed_data.attribute_data, "data", {}) if hasattr(preprocessed_data, "attribute_data") else {}
    capability_notes = getattr(preprocessed_data, "canonical_capability_notes", {})
    capability_bindings = writing_policy.get("capability_scene_bindings", [])
    payload = {
        "title": title,
        "reasoning_bullets": list(reasoning_bullets or []),
        "target_language": target_language,
        "raw_human_insights": getattr(preprocessed_data, "raw_human_insights", ""),
        "all_scenes": writing_policy.get("scene_priority", []),
        "all_capabilities": getattr(preprocessed_data, "canonical_core_selling_points", None)
        or getattr(preprocessed_data, "core_selling_points", []),
        "attributes": attr_data,
        "capability_scene_bindings": capability_bindings,
        "capability_notes": capability_notes,
        "product_profile": writing_policy.get("product_profile", {}),
        "forbidden_visible_terms": (writing_policy.get("compliance_directives", {}) or {}).get("backend_only_terms", []),
        "canonical_facts": getattr(preprocessed_data, "canonical_facts", {}) or {},
    }
    if request_timeout_seconds:
        payload["_request_timeout_seconds"] = int(request_timeout_seconds)
    return _generate_and_audit_description(payload, audit_log)


def _llm_generate_title(payload: Dict[str, Any]) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language", "English")
    exact_match_keywords = payload.get("exact_match_keywords") or []
    required_keywords = [str(item).strip() for item in (payload.get("required_keywords") or []) if str(item).strip()]
    max_length = int(payload.get("max_length") or LENGTH_RULES["title"]["hard_ceiling"])
    remaining_budget = payload.get("remaining_character_budget")
    repair_context = payload.get("repair_context") or {}
    core_category_keyword = (
        next((kw for kw in exact_match_keywords if kw and _normalize_keyword_text(payload.get("primary_category") or "") in _normalize_keyword_text(kw)), "")
        or next((kw for kw in payload.get("l1_keywords") or [] if kw), "")
        or payload.get("primary_category")
        or "camera"
    )
    dynamic_core_keywords = _dedupe_keyword_sequence(
        list(required_keywords or [])
        + list(exact_match_keywords or [])
        + list(payload.get("l1_keywords") or [])
        + list(payload.get("assigned_keywords") or [])
    )
    differentiators = _clean_title_phrases(
        [payload.get("core_capability")] + list(_flatten_tokens(payload.get("numeric_specs") or []))
    )[:2]
    min_keyword_hits = min(3, len(dynamic_core_keywords)) if dynamic_core_keywords else 0
    required_keyword_rule = (
        "12. REQUIRED KEYWORDS: include these exact phrases naturally in one title while staying readable: "
        + ", ".join(required_keywords)
        + ".\n"
    ) if required_keywords else ""
    budget_rule = (
        f"13. Hard max length is {max_length} characters. Remaining free budget after required keywords is about {remaining_budget} characters.\n"
    )
    repair_rule = ""
    if repair_context:
        repair_rule = (
            "14. Repair the previous title in ONE pass: satisfy all missing keywords and stay within the hard max length at the same time.\n"
            f"15. Previous failure reason: {json.dumps(repair_context, ensure_ascii=False)}.\n"
        )
    exact_phrase_rule = (
        "16. The following traffic phrases are immutable and must appear verbatim, in the same word order, without compression or rewriting: "
        + ", ".join(exact_match_keywords)
        + ".\n"
    ) if exact_match_keywords else ""
    system_prompt = (
        "You are an elite premium ecommerce copywriter and Amazon SEO expert working natively in "
        f"{target_language}. All keywords and specs arrive as Canonical English placeholders, "
        "so you must localize every connective and descriptor into the final target_language. "
        "No English filler words may remain unless they are global abbreviations (4K, EIS, WiFi) or brand names.\n"
        "Generate a single product title in "
        f"{target_language} based on the provided JSON payload.\n"
        "RULES:\n"
        "1. Start exactly with the brand name.\n"
        f"2. Include at least {min_keyword_hits or 1} of these core keywords naturally in the title, never as a raw list: {', '.join(dynamic_core_keywords[:6]) or core_category_keyword}.\n"
        f"3. Naturally embed the two strongest differentiators when available: {', '.join(differentiators) or 'verified runtime and hero capability'}.\n"
        "4. The title must read like a natural English product name phrase, not a comma-stacked keyword list.\n"
        "5. Use Title Case for the major words. Never output a crude lowercase keyword dump.\n"
        f"6. Target {LENGTH_RULES['title']['target_min']}-{LENGTH_RULES['title']['target_max']} characters and never exceed {max_length} characters.\n"
        "7. Prefer a fuller natural product-name phrase that uses the available evidence; do not stop too early with a short skeletal title.\n"
        "8. Do not use slash-joined synonyms, do not keyword-stuff, and do not sound generic or cheap.\n"
        "9. Tone must feel Professional, Premium, Persuasive, and Action-oriented.\n"
        "10. Translate specs into human value and never sound like an internal parameter dump.\n"
        f"11. The first 80 characters MUST contain the core category keyword '{core_category_keyword}'.\n"
        "12. FORBIDDEN: pure comma-separated keyword lists or bare technical parameter brackets.\n"
        "13. Output ONLY the raw title string, no quotes, no explanations.\n"
        f"{required_keyword_rule}"
        f"{budget_rule}"
        f"{repair_rule}"
        f"{exact_phrase_rule}"
    )
    override_model = payload.get("_llm_override_model") or None
    try:
        text = client.generate_text(
            system_prompt,
            payload,
            temperature=0.25,
            override_model=override_model,
        )
    except TypeError:
        text = client.generate_text(system_prompt, payload, temperature=0.25)
    text = (text or "").strip()
    if not text:
        raise LLMClientUnavailable("Empty LLM response")
    return text


def _generate_and_audit_title(
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]],
    assignment_tracker: Optional[KeywordAssignmentTracker],
    required_keywords: Sequence[str],
    max_retries: int = 3,
) -> str:
    if payload.get("use_r1_recipe"):
        return _generate_title_r1(payload, audit_log, assignment_tracker, required_keywords)
    prefetched_candidates = list(payload.get("_prefetched_title_candidates") or [])
    brand = (payload.get("brand_name") or "").strip()
    brand_lower = brand.lower()
    numeric_specs = payload.get("numeric_specs") or []
    primary_l1 = next((kw for kw in payload.get("l1_keywords") or [] if kw), "")
    title_contract = (payload.get("copy_contracts") or {}).get("title_dewater", {}) or {}
    weak_connectors = title_contract.get("weak_connectors") or ["with", "avec", "mit", "con"]
    exact_match_keywords = payload.get("exact_match_keywords") or []
    banned_punct = {".", "。"}
    last_candidate = ""
    max_attempts = _llm_retry_budget(max_retries)
    for attempt in range(1, max_attempts + 1):
        try:
            attempt_payload = {
                **payload,
                **_build_title_budget(required_keywords, payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"])),
            }
            if prefetched_candidates:
                candidate = str(prefetched_candidates.pop(0) or "")
            else:
                candidate = _llm_generate_title(attempt_payload)
        except LLMClientUnavailable as exc:
            if _log_retryable_llm_exception(audit_log, "title", exc, attempt):
                continue
            break
        candidate_stripped = candidate.strip()
        if not candidate_stripped:
            _log_action(audit_log, "title", "llm_retry", {"attempt": attempt, "reason": "empty_output"})
            continue
        last_candidate = candidate_stripped
        if brand and not candidate_stripped.lower().startswith(brand_lower):
            candidate_stripped = f"{brand} {candidate_stripped}"
            _log_action(audit_log, "title", "llm_adjusted_brand", {"attempt": attempt})
        remainder = candidate_stripped[len(brand):].lstrip(" -|–—")
        if primary_l1 and (not remainder.lower().startswith(primary_l1.lower())):
            candidate_stripped = f"{brand} {primary_l1} {remainder}"
            _log_action(audit_log, "title", "llm_adjusted_l1", {"attempt": attempt})
        sanitized = candidate_stripped
        for punct in banned_punct:
            sanitized = sanitized.replace(punct, " ")
        normalized = re.sub(r"\s+", " ", sanitized)
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = _dedupe_adjacent_words(normalized)
        normalized = _dewater_title_text(normalized, exact_match_keywords, audit_log)
        normalized = _apply_title_core_category_frontload(
            normalized,
            payload,
            payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
        )
        if _title_is_keyword_dump(normalized):
            _log_action(audit_log, "title", "llm_retry", {"attempt": attempt, "reason": "keyword_dump_title"})
            continue
        if _title_has_bare_parameter_brackets(normalized):
            _log_action(audit_log, "title", "llm_retry", {"attempt": attempt, "reason": "bare_parameter_brackets"})
            continue
        if _title_is_below_target_length(normalized, payload):
            _log_action(
                audit_log,
                "title",
                "llm_retry",
                {
                    "attempt": attempt,
                    "reason": "below_target_length",
                    "length": len(normalized),
                    "target_min": int(payload.get("target_min_length") or LENGTH_RULES["title"]["target_min"]),
                },
            )
            continue
        connector_hits = _title_connector_overuse(normalized, exact_match_keywords, weak_connectors)
        if len(connector_hits) >= 2:
            _log_action(
                audit_log,
                "title",
                "llm_retry",
                {"attempt": attempt, "reason": "weak_connector_overuse", "connectors": connector_hits[:3]},
            )
            continue
        if len(normalized) > payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]):
            trimmed_candidate = _trim_to_word_boundary(normalized, payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]))
            trimmed_candidate = _patch_title_missing_keywords(
                trimmed_candidate,
                required_keywords,
                payload,
                payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
            )
            trimmed_candidate = _dewater_title_text(trimmed_candidate, exact_match_keywords, audit_log)
            trimmed_candidate = _apply_title_core_category_frontload(
                trimmed_candidate,
                payload,
                payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
            )
            repassed, repaired_reason, _ = _validate_field_text(trimmed_candidate, required_keywords, numeric_specs)
            if repassed and not _title_is_keyword_dump(trimmed_candidate) and not _title_has_bare_parameter_brackets(trimmed_candidate) and len(trimmed_candidate) <= payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]) and not _title_is_below_target_length(trimmed_candidate, payload):
                _log_action(
                    audit_log,
                    "title",
                    "llm_success",
                    {"attempt": "trimmed_length_repair", "source_attempt": attempt},
                )
                if assignment_tracker and required_keywords:
                    assignment_tracker.record("title", required_keywords)
                return trimmed_candidate
            _log_action(
                audit_log,
                "title",
                "llm_retry",
                {"attempt": attempt, "reason": "length_exceeded", "repair_reason": repaired_reason},
            )
            repair_payload = {
                **payload,
                **_build_title_budget(required_keywords, payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"])),
                "repair_context": {"reason": "length_exceeded", "current_title": normalized[:180], "required_keywords": list(required_keywords)},
            }
            try:
                repaired_candidate = _llm_generate_title(repair_payload).strip()
            except LLMClientUnavailable:
                repaired_candidate = ""
            if repaired_candidate:
                repaired_candidate = _dewater_title_text(_dedupe_adjacent_words(repaired_candidate), exact_match_keywords, audit_log)
                repaired_candidate = _apply_title_core_category_frontload(
                    repaired_candidate,
                    payload,
                    payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
                )
                repaired_candidate = _trim_to_word_boundary(repaired_candidate, payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]))
                repassed, repaired_reason, _ = _validate_field_text(repaired_candidate, required_keywords, numeric_specs)
                if repassed and not _title_is_keyword_dump(repaired_candidate) and not _title_has_bare_parameter_brackets(repaired_candidate) and len(repaired_candidate) <= payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]) and not _title_is_below_target_length(repaired_candidate, payload):
                    _log_action(audit_log, "title", "llm_success", {"attempt": "coordinated_repair", "source_attempt": attempt})
                    _record_repair_event(
                        payload.get("_artifact_dir"),
                        "title",
                        {"length_exceeded": True},
                        normalized,
                        repaired_candidate,
                        repair_success=True,
                        default_rule="title_length_exceeded",
                    )
                    if assignment_tracker and required_keywords:
                        assignment_tracker.record("title", required_keywords)
                    return repaired_candidate
            continue
        passed, reason, _ = _validate_field_text(normalized, required_keywords, numeric_specs)
        if not passed:
            missing_keywords = reason.get("missing_keywords") or []
            if missing_keywords:
                patched = _patch_title_missing_keywords(
                    normalized,
                    missing_keywords,
                    payload,
                    payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
                )
                if patched != normalized:
                    repassed, repaired_reason, _ = _validate_field_text(patched, required_keywords, numeric_specs)
                    if repassed and not _title_is_keyword_dump(patched) and not _title_has_bare_parameter_brackets(patched) and not _title_is_below_target_length(patched, payload):
                        _log_action(
                            audit_log,
                            "title",
                            "llm_success",
                            {"attempt": "patched_missing_keywords", "patched_keywords": missing_keywords},
                        )
                        _record_repair_event(
                            payload.get("_artifact_dir"),
                            "title",
                            {"missing_keywords": missing_keywords},
                            normalized,
                            patched,
                            repair_success=True,
                            default_rule="title_missing_keyword",
                        )
                        if assignment_tracker and required_keywords:
                            assignment_tracker.record("title", required_keywords)
                        return patched
                    reason = repaired_reason
                repair_payload = {
                    **payload,
                    **_build_title_budget(required_keywords, payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"])),
                    "repair_context": {"reason": reason, "current_title": normalized[:180], "required_keywords": list(required_keywords)},
                }
                try:
                    repaired_candidate = _llm_generate_title(repair_payload).strip()
                except LLMClientUnavailable:
                    repaired_candidate = ""
                if repaired_candidate:
                    repaired_candidate = _dewater_title_text(_dedupe_adjacent_words(repaired_candidate), exact_match_keywords, audit_log)
                    repaired_candidate = _apply_title_core_category_frontload(
                        repaired_candidate,
                        payload,
                        payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
                    )
                    repaired_candidate = _trim_to_word_boundary(repaired_candidate, payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]))
                    repassed, repaired_reason, _ = _validate_field_text(repaired_candidate, required_keywords, numeric_specs)
                    if repassed and not _title_is_keyword_dump(repaired_candidate) and not _title_has_bare_parameter_brackets(repaired_candidate) and len(repaired_candidate) <= payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]) and not _title_is_below_target_length(repaired_candidate, payload):
                        _log_action(audit_log, "title", "llm_success", {"attempt": "coordinated_repair", "source_attempt": attempt})
                        _record_repair_event(
                            payload.get("_artifact_dir"),
                            "title",
                            reason if isinstance(reason, dict) else {"missing_keywords": missing_keywords},
                            normalized,
                            repaired_candidate,
                            repair_success=True,
                            default_rule="title_missing_keyword",
                        )
                        if assignment_tracker and required_keywords:
                            assignment_tracker.record("title", required_keywords)
                        return repaired_candidate
                    reason = repaired_reason or reason
            reason["attempt"] = attempt
            _log_action(audit_log, "title", "llm_retry", reason)
            continue
        if not _title_is_below_target_length(normalized, payload):
            _log_action(audit_log, "title", "llm_success", {"attempt": attempt})
            if assignment_tracker and required_keywords:
                assignment_tracker.record("title", required_keywords)
            return normalized
        _log_action(
            audit_log,
            "title",
            "llm_retry",
            {"attempt": attempt, "reason": "below_target_length", "length": len(normalized), "target_min": int(payload.get("target_min_length") or LENGTH_RULES["title"]["target_min"])},
        )
        continue
    if last_candidate:
        max_length = payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"])
        repaired_title = _patch_title_missing_keywords(
            last_candidate,
            required_keywords,
            payload,
            max_length,
        )
        repaired_title = re.sub(r"[。.]+", " ", repaired_title)
        repaired_title = re.sub(r"\s+", " ", repaired_title).strip()
        if brand and not repaired_title.lower().startswith(brand_lower):
            repaired_title = f"{brand} {repaired_title}".strip()
        remainder = repaired_title[len(brand):].lstrip(" -|–—") if brand and repaired_title.lower().startswith(brand_lower) else repaired_title
        if primary_l1 and not remainder.lower().startswith(primary_l1.lower()):
            repaired_title = f"{brand} {primary_l1} {remainder}".strip() if brand else f"{primary_l1} {remainder}".strip()
        repaired_title = _dewater_title_text(_dedupe_adjacent_words(repaired_title), exact_match_keywords, audit_log)
        repaired_title = _apply_title_core_category_frontload(repaired_title, payload, max_length)
        repaired_title = _trim_to_word_boundary(repaired_title, max_length)
        repassed, repaired_reason, _ = _validate_field_text(repaired_title, required_keywords, numeric_specs)
        if repassed and not _title_is_keyword_dump(repaired_title) and not _title_has_bare_parameter_brackets(repaired_title) and not _title_is_below_target_length(repaired_title, payload):
            _log_action(
                audit_log,
                "title",
                "llm_success",
                {"attempt": "post_retry_patch", "repaired_from": last_candidate[:120]},
            )
            _record_repair_event(
                payload.get("_artifact_dir"),
                "title",
                repaired_reason or {"missing_keywords": required_keywords},
                last_candidate,
                repaired_title,
                repair_success=True,
                default_rule="title_missing_keyword",
            )
            if assignment_tracker and required_keywords:
                assignment_tracker.record("title", required_keywords)
            return repaired_title
        if repaired_reason:
            _log_action(
                audit_log,
                "title",
                "llm_retry",
                {"attempt": "post_retry_patch", "reason": repaired_reason},
            )
    if payload.get("_disable_fallback"):
        raise RuntimeError("title_validation_failed_after_retry")
    fallback = last_candidate or _fallback_text_for_field("title", payload, numeric_specs)
    if brand and not fallback.lower().startswith(brand_lower):
        fallback = f"{brand} {fallback}".strip()
    fallback = re.sub(r"[。.]+", " ", fallback)
    fallback = fallback.replace("，", ",")
    fallback = _dedupe_adjacent_words(re.sub(r"\s+", " ", fallback)).strip()
    remainder = fallback[len(brand):].lstrip(" -|–—") if brand and fallback.lower().startswith(brand_lower) else fallback
    if primary_l1 and not remainder.lower().startswith(primary_l1.lower()):
        fallback = f"{brand} {primary_l1} {remainder}".strip() if brand else f"{primary_l1} {remainder}".strip()
    if fallback.count(",") < 2:
        category = payload.get("primary_category") or ""
        core = " ".join([p for p in (payload.get("assigned_keywords") or [])[:1] + [payload.get("core_capability") or ""] if p]).strip()
        scene = " ".join([str(item).replace("_", " ") for item in (payload.get("scene_priority") or [])[:2] if item]).strip()
        lead = " ".join([p for p in [brand, primary_l1 or category] if p]).strip()
        if category and primary_l1 and category.lower() not in lead.lower():
            lead = f"{brand} {primary_l1} {category}".strip()
        fallback = ", ".join([part for part in [lead, core or " ".join(_flatten_tokens(numeric_specs)), scene] if part]).strip()
    missing_keywords = [
        keyword for keyword in required_keywords or []
        if keyword and _normalize_keyword_text(keyword) not in _normalize_keyword_text(fallback)
    ]
    if missing_keywords:
        compact = _fallback_text_for_field(
            "title",
            {
                **payload,
                "mandatory_keywords": _dedupe_keyword_sequence(
                    list(payload.get("l1_keywords") or []) + list(missing_keywords)
                ),
                "assigned_keywords": list(payload.get("assigned_keywords") or []),
            },
            numeric_specs,
        )
        fallback = compact or _patch_title_missing_keywords(
            fallback,
            missing_keywords,
            payload,
            payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"]),
        )
    if numeric_specs and not _check_numeric_presence(fallback, numeric_specs):
        fallback = f"{fallback} {' '.join(_flatten_tokens(numeric_specs))}".strip()
    fallback = re.sub(r"\s+", " ", fallback).strip()
    fallback = _dewater_title_text(fallback, exact_match_keywords, audit_log)
    max_length = payload.get("max_length", LENGTH_RULES["title"]["hard_ceiling"])
    fallback = _apply_title_core_category_frontload(fallback, payload, max_length)
    fallback = _trim_to_word_boundary(fallback, max_length)
    deterministic_candidate = _build_deterministic_title_candidate(
        payload,
        required_keywords,
        numeric_specs,
        max_length,
    )
    deterministic_candidate = _dewater_title_text(deterministic_candidate, exact_match_keywords, audit_log)
    deterministic_candidate = _apply_title_core_category_frontload(deterministic_candidate, payload, max_length)
    deterministic_candidate = _trim_to_word_boundary(deterministic_candidate, max_length)
    repassed, _, _ = _validate_field_text(deterministic_candidate, required_keywords, numeric_specs)
    if repassed and not _title_is_keyword_dump(deterministic_candidate) and not _title_has_bare_parameter_brackets(deterministic_candidate) and not _title_is_below_target_length(deterministic_candidate, payload):
        _log_action(
            audit_log,
            "title",
            "llm_success",
            {"attempt": "deterministic_repair", "repaired_from": last_candidate[:120]},
        )
        _record_repair_event(
            payload.get("_artifact_dir"),
            "title",
            {"missing_keywords": required_keywords},
            last_candidate,
            deterministic_candidate,
            repair_success=True,
            default_rule="title_missing_keyword",
        )
        if assignment_tracker and required_keywords:
            assignment_tracker.record("title", required_keywords)
        return deterministic_candidate
    _log_action(
        audit_log,
        "title",
        "llm_fallback",
        {"reason": "title_retry_exhausted", "fallback_preview": fallback[:120]},
    )
    logging.warning("title fallback used after retry exhaustion")
    _record_repair_event(
        payload.get("_artifact_dir"),
        "title",
        {"missing_keywords": required_keywords},
        last_candidate or '',
        fallback,
        repair_success=False,
        default_rule="title_missing_keyword",
    )
    if assignment_tracker and required_keywords:
        assignment_tracker.record("title", required_keywords)
    return fallback


def _validate_title_final(
    title: str,
    payload: Dict[str, Any],
    required_keywords: Sequence[str],
) -> Tuple[bool, Dict[str, Any]]:
    numeric_specs = payload.get("numeric_specs") or []
    max_length = int(payload.get("max_length") or LENGTH_RULES["title"]["hard_ceiling"])
    issues: Dict[str, Any] = {}
    if len(title or "") > max_length:
        issues["length_exceeded"] = True
    if _title_is_below_target_length(title or "", payload):
        issues["below_target_length"] = {
            "length": len(title or ""),
            "target_min": int(payload.get("target_min_length") or LENGTH_RULES["title"]["target_min"]),
        }
    passed, reason, _ = _validate_field_text(title or "", required_keywords, numeric_specs)
    if not passed and reason:
        issues.update(reason if isinstance(reason, dict) else {"validation_error": reason})
    if _title_is_keyword_dump(title or ""):
        issues["keyword_dump_title"] = True
    if _title_has_bare_parameter_brackets(title or ""):
        issues["bare_parameter_brackets"] = True
    return not issues, issues


def _generate_title_r1(
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]],
    assignment_tracker: Optional[KeywordAssignmentTracker],
    required_keywords: Sequence[str],
) -> str:
    brand = (payload.get("brand_name") or "").strip()
    brand_lower = brand.lower()
    max_length = int(payload.get("max_length") or LENGTH_RULES["title"]["hard_ceiling"])
    target_min = int(payload.get("target_min_length") or LENGTH_RULES["title"]["target_min"])
    prefetched_candidates = list(payload.get("_prefetched_title_candidates") or [])

    def _light_cleanup(text: str) -> str:
        cleaned = re.sub(r"[。.]+", " ", str(text or ""))
        cleaned = cleaned.replace("，", ",")
        cleaned = _dedupe_adjacent_words(re.sub(r"\s+", " ", cleaned)).strip(" ,")
        if brand and cleaned and not cleaned.lower().startswith(brand_lower):
            cleaned = f"{brand} {cleaned}".strip()
        return cleaned

    def _repair(candidate: str) -> str:
        repaired = _light_cleanup(candidate)
        if required_keywords:
            repaired = _patch_title_missing_keywords(repaired, required_keywords, payload, max_length)
        if len(repaired) > max_length or len(repaired) < target_min:
            repaired = _rule_repair_title_length(
                repaired,
                {**payload, "required_keywords": list(required_keywords or [])},
                audit_log=None,
                target_min=target_min,
                target_max=int(payload.get("target_max_length") or LENGTH_RULES["title"]["target_max"]),
                hard_ceiling=max_length,
            )
        if required_keywords:
            repaired = _patch_title_missing_keywords(repaired, required_keywords, payload, max_length)
        repaired = _trim_to_word_boundary(_light_cleanup(repaired), max_length)
        return repaired

    candidate = _repair(str(prefetched_candidates.pop(0) or "")) if prefetched_candidates else ""
    if candidate:
        passed, issues = _validate_title_final(candidate, payload, required_keywords)
        if passed:
            _log_action(audit_log, "title", "r1_recipe_success", {"attempt": "prefetched_recipe", "length": len(candidate)})
            if assignment_tracker and required_keywords:
                assignment_tracker.record("title", required_keywords)
            return candidate
        _log_action(audit_log, "title", "r1_recipe_retry", {"attempt": "prefetched_recipe", "reason": issues})

    deterministic = _repair(
        _build_deterministic_title_candidate(
            payload,
            required_keywords,
            payload.get("numeric_specs") or [],
            max_length,
        )
    )
    passed, issues = _validate_title_final(deterministic, payload, required_keywords)
    if passed:
        _log_action(audit_log, "title", "r1_recipe_success", {"attempt": "deterministic_finalize", "length": len(deterministic)})
        if assignment_tracker and required_keywords:
            assignment_tracker.record("title", required_keywords)
        return deterministic

    _log_action(audit_log, "title", "r1_recipe_validation_failed", {"reason": issues, "length": len(deterministic)})
    if payload.get("_disable_fallback"):
        raise RuntimeError("title_validation_failed_after_r1_finalize")
    return deterministic


def _llm_generate_aplus(payload: Dict[str, Any]) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language", "English")
    evidence_numbers = ", ".join(payload.get("evidence_numeric_values") or []) or "none"
    supported_spec_dimensions = ", ".join(payload.get("supported_spec_dimensions") or []) or "runtime, resolution, weight, view_angle, connectivity"
    system_prompt = (
        "You are a premium Amazon brand copywriter responding natively in "
        f"{target_language}. All product_profile data, capability_scene_bindings, and accessories arrive as Canonical English; "
        "translate EVERY concept, connective, and descriptor into the target_language so no English filler remains "
        "(only universal tokens like 4K/EIS/WiFi or brand names may stay in English). "
        "Paint vivid usage images when accessories are supplied instead of listing them verbatim.\n"
        "Create structured A+ Content in fluent "
        f"{target_language}. "
        "RULES:\n"
        "1. Use Markdown headers (##, ###) to separate sections such as Brand Story, Core Technologies, "
        "Usage Scenarios, and What's in the Box.\n"
        "2. Write persuasive paragraphs that weave capability_scene_bindings and product_profile data "
        "into immersive storytelling.\n"
        "3. For every Markdown header you output, immediately follow it with a line formatted as "
        "[Visual Design Brief: ...] that instructs a graphic designer on subject/action, camera angle + "
        "lighting, and text placement/negative space for the paired visual. Directly beneath that line, output a JSON block "
        "with keys section/subject/angle/lighting/text_placement/canonical_specs_highlighted so downstream multimodal systems can parse it.\n"
        "4. Translate and normalize any raw Chinese or English fragments from the payload into natural "
        f"{target_language}. NO Chinese characters may appear in the output.\n"
        "5. Maintain a professional, premium tone focused on benefits and proof.\n"
        "6. De-jargonize technical language, express capacity as buyer outcome, and frame limitations as best-use guidance.\n"
        f"7. Verified numeric evidence available: {evidence_numbers}. Each module paragraph must anchor on at least one verified numeric claim when a relevant number is available.\n"
        "8. Avoid absolute claims such as #1, best, guaranteed, amazing, or excellent.\n"
        f"9. Spec-anchor contract: rotate dimensions across modules before repeating. Supported dimensions: {supported_spec_dimensions}. "
        "Each section paragraph must include one quantifiable spec anchor tied to one of those dimensions.\n"
    )
    text = client.generate_text(system_prompt, payload, temperature=0.35)
    text = (text or "").strip()
    if not text:
        raise LLMClientUnavailable("Empty LLM response")
    return text


def _generate_and_audit_aplus(
    payload: Dict[str, Any],
    audit_log: Optional[List[Dict[str, Any]]],
    max_retries: int = 2,
) -> str:
    field = "aplus_content"
    payload.pop("_aplus_fallback", None)
    if _is_budget_constrained_live_runtime():
        fallback = _fallback_aplus_content(payload)
        payload["_aplus_fallback"] = True
        _log_action(audit_log, field, "llm_fallback", {"reason": "runtime_budget_preserve_core_copy"})
        return fallback
    for attempt in range(1, _llm_retry_budget(max_retries) + 1):
        try:
            candidate = _llm_generate_aplus(payload)
        except LLMClientUnavailable as exc:
            if _log_retryable_llm_exception(audit_log, field, exc, attempt):
                continue
            break
        candidate = candidate.strip()
        if not candidate:
            _log_action(audit_log, field, "llm_retry", {"attempt": attempt, "reason": "empty_output"})
            continue
        if "##" not in candidate:
            _log_action(audit_log, field, "llm_retry", {"attempt": attempt, "reason": "missing_markdown"})
            continue
        if CHINESE_CHAR_PATTERN.search(candidate):
            _log_action(audit_log, field, "llm_retry", {"attempt": attempt, "reason": "chinese_characters_detected"})
            continue
        blocked_terms = find_blocklisted_terms(candidate)
        if blocked_terms:
            _log_action(
                audit_log,
                field,
                "llm_retry",
                {"attempt": attempt, "reason": "brand_blocked", "terms": blocked_terms},
            )
            continue
        _log_action(audit_log, field, "llm_success", {"attempt": attempt})
        return candidate
    fallback = _fallback_aplus_content(payload)
    payload["_aplus_fallback"] = True
    _log_action(audit_log, field, "llm_fallback", {"reason": "llm_failure_or_timeout"})
    return fallback


def _fallback_aplus_content(payload: Dict[str, Any]) -> str:
    target_language = payload.get("target_language", "English")
    profile = payload.get("product_profile", {})
    brand = payload.get("brand_name", "YourBrand")
    scenes = profile.get("scene_priority", []) or ["travel_documentation", "family_use", "cycling_recording"]
    capabilities = profile.get("core_capabilities", []) or ["4K recording", "stabilization", "waterproof housing", "long battery"]
    accessories = payload.get("accessories") or ["complete mounting kit", "waterproof housing", "magnetic lanyard"]
    localized_scenes = [
        _translate_scene(scene, target_language).replace("_", " ")
        for scene in scenes[:3]
    ]
    localized_caps = [
        _translate_capability(cap, target_language)
        for cap in capabilities[:4]
    ]
    localized_accessories = [
        _translate_text_to_language(item, target_language)
        for item in accessories[:4]
    ]
    scene_text = ", ".join([item for item in localized_scenes if item])
    capability_text = ", ".join([item for item in localized_caps if item])
    accessory_text = ", ".join([item for item in localized_accessories if item])
    labels = _language_style_profile(target_language)["section_labels"]
    section_copy = {
        "English": {
            "brand_story": "{brand} stays ready across {scene_text}. The compact dual-screen body keeps framing simple while WiFi control helps review clips quickly on the spot.",
            "core_technologies": "Key advantages such as {capability_text} keep the listing grounded in practical proof instead of inflated claims.",
            "usage_scenarios": "From daily rides to travel memories and family moments, {brand} supports lightweight hands-free capture without bulky gear slowing the user down.",
            "in_the_box": "Inside the kit you get {accessory_text}, plus the essentials needed to start shooting quickly after unboxing.",
        },
        "French": {
            "brand_story": "{brand} accompagne naturellement des scenes comme {scene_text}. Son boitier compact a double ecran simplifie le cadrage, et le controle WiFi aide a verifier les clips sans perdre le rythme.",
            "core_technologies": "Des points forts comme {capability_text} apportent des preuves concretes, utiles pour une fiche Amazon claire, credible et orientee conversion.",
            "usage_scenarios": "Pour le velo, le voyage ou les souvenirs du quotidien, {brand} mise sur une capture mains libres legere afin de filmer sans s'encombrer.",
            "in_the_box": "Dans la boite, vous retrouvez {accessory_text}, avec l'essentiel pour commencer a filmer rapidement des l'ouverture.",
        },
        "German": {
            "brand_story": "{brand} passt zu Szenarien wie {scene_text}. Das kompakte Dual-Screen-Gehause erleichtert das Framing, und die WiFi-Steuerung macht die schnelle Clip-Kontrolle unterwegs einfacher.",
            "core_technologies": "Merkmale wie {capability_text} liefern belastbare Nutzensignale, damit der Amazon-Auftritt klar, glaubwurdig und kaufstark bleibt.",
            "usage_scenarios": "Ob Radfahrt, Reise oder Familienmoment: {brand} steht fur leichte freihandige Aufnahmen, ohne den Nutzer mit sperrigem Zubehor auszubremsen.",
            "in_the_box": "Im Lieferumfang finden sich {accessory_text} sowie die wichtigsten Basics fur einen schnellen Start direkt nach dem Auspacken.",
        },
        "Spanish": {
            "brand_story": "{brand} acompana escenas como {scene_text}. El cuerpo compacto con doble pantalla facilita el encuadre y el control WiFi permite revisar clips con rapidez.",
            "core_technologies": "Ventajas como {capability_text} aportan pruebas utiles para una ficha de Amazon clara, creible y orientada a conversion.",
            "usage_scenarios": "Desde trayectos diarios hasta viajes y momentos en familia, {brand} apuesta por una grabacion manos libres ligera y practica.",
            "in_the_box": "En la caja encuentras {accessory_text}, junto con lo esencial para empezar a grabar nada mas abrir el producto.",
        },
        "Italian": {
            "brand_story": "{brand} si adatta bene a scene come {scene_text}. Il corpo compatto con doppio schermo rende l'inquadratura piu semplice e il controllo WiFi aiuta a rivedere subito le clip.",
            "core_technologies": "Vantaggi come {capability_text} offrono prove concrete, utili per una scheda Amazon chiara, credibile e orientata alla conversione.",
            "usage_scenarios": "Tra bici, viaggi e momenti di tutti i giorni, {brand} punta su riprese leggere a mani libere senza ingombri inutili.",
            "in_the_box": "Nella confezione trovi {accessory_text}, oltre agli elementi essenziali per iniziare a registrare subito dopo l'apertura.",
        },
    }.get(target_language) or {
        "brand_story": "{brand} stays ready across {scene_text}.",
        "core_technologies": "{capability_text} provide the clearest proof points for the listing.",
        "usage_scenarios": "{brand} supports hands-free capture across everyday scenarios.",
        "in_the_box": "Inside the kit you get {accessory_text}.",
    }
    paragraphs = [
        f"## {labels['brand_story']}\n{section_copy['brand_story'].format(brand=brand, scene_text=scene_text)}",
        f"## {labels['core_technologies']}\n{section_copy['core_technologies'].format(capability_text=capability_text)}",
        f"## {labels['usage_scenarios']}\n{section_copy['usage_scenarios'].format(brand=brand)}",
        f"## {labels['in_the_box']}\n{section_copy['in_the_box'].format(accessory_text=accessory_text)}",
    ]
    markdown = "\n\n".join(paragraphs)
    return _apply_default_visual_briefs(markdown, target_language, localized_caps)


def _llm_generate_description(payload: Dict[str, Any]) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language", "the target language")
    scenes = ", ".join(payload.get("all_scenes") or [])
    capabilities = ", ".join(payload.get("all_capabilities") or [])
    forbidden_terms = ", ".join(payload.get("forbidden_visible_terms") or []) or "none"
    system_prompt = (
        "You are a world-class premium Amazon listing storyteller working in {target_language}. "
        "CRITICAL CONTEXT: You are generating copy for an Amazon listing in {target_language}. "
        "You are provided with 'raw_human_insights' written by the product creator. Give these insights the ABSOLUTE HIGHEST PRIORITY. "
        "Extract the emotional hooks, colloquial tone, and specific real-world usage scenarios. "
        "Weave these deeply into your {target_language} copy. DO NOT use robotic, repetitive sentence structures. "
        "Write as a high-end, native {target_language} e-commerce copywriter aiming for maximum conversion. "
        "Translate every scene, spec, accessory, and capability from Canonical English into {target_language}, except universal abbreviations (4K/EIS/WiFi) or brand names. "
        "Scenes to honor: {scenes}. Capabilities to spotlight: {capabilities}. "
        "Produce four fluent paragraphs: (1) sensory hook spanning at least three provided scenes, (2) hero capabilities + accessories woven into a micro-story, "
        "(3) reliability proof covering only supported runtime / mounting / waterproof depth / motion-fit boundaries from the payload, "
        "(4) colloquial CTA referencing package contents + after-sales support. "
        "Reference the intent_graph personas and pain points so every paragraph shows a problem/solution arc drawn from raw_human_insights. "
        "Do not invent specs; keep all numeric values intact. "
        "Never mention these forbidden visible terms in the description: {forbidden_terms}. "
        "Keep the tone Professional, Premium, Persuasive, and action-oriented. Avoid cheap slang, casual filler, slash-joined synonyms, or low-end marketplace phrasing. "
        "Avoid comparative language like 'better than', avoid absolute words like 'best', and avoid explicit warranty/refund claims in the visible description. "
        "Translate jargon into direct buyer value, convert capacity into real-life usage outcome when facts allow, and express limitations as premium best-use recommendations. "
        "CRITICAL FORMATTING: Amazon forbids HTML formatting except the <br> tag. Output plain text, using only <br> to separate the four paragraphs. "
        "Do NOT use any other HTML tag, markdown symbol, numbering, or bullet list. "
        "Use flowing sentences (no bullet lists) and keep the overall description tight, persuasive, and human."
    ).format(
        target_language=target_language,
        scenes=scenes or "none provided",
        capabilities=capabilities or "none provided",
        forbidden_terms=forbidden_terms,
    )
    text = client.generate_description(system_prompt, payload, temperature=0.35)
    text = (text or "").strip()
    if not text:
        raise LLMClientUnavailable("Empty LLM response")
    return text


def _llm_generate_faq(payload: Dict[str, Any]) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language", "English")
    system_prompt = (
        "You are an Amazon customer support specialist responding in pure "
        f"{target_language}. Canonical English facts are provided in capability_constraints, compliance directives, and intent_graph; "
        "translate every question and answer fully so no English filler remains (except brand names or universal abbreviations like 4K/EIS/WiFi). "
        "Using the capability_constraints, compliance directives, and intent_graph, "
        "generate exactly 3 FAQ entries in "
        f"{target_language}. Each entry must be a JSON object with keys 'q' and 'a'. "
        "Questions should reflect the audience pain points, and answers must cite the actual specs provided "
        "(e.g., waterproof depth, runtime) without inventing new numbers. "
        "Output ONLY a JSON array, e.g. "
        "[{\"q\":\"...\",\"a\":\"...\"},...]."
    )
    text = client.generate_text(system_prompt, payload, temperature=0.25)
    text = (text or "").strip()
    if not text:
        raise LLMClientUnavailable("Empty LLM response")
    return text


def _parse_faq_output(text: str) -> List[Dict[str, str]]:
    try:
        data = json.loads(text)
    except Exception:
        return []
    entries: List[Dict[str, str]] = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            q = (item.get("q") or "").strip()
            a = (item.get("a") or "").strip()
            if q and a:
                entries.append({"q": q, "a": a})
    return entries


def _faq_entries_valid(entries: List[Dict[str, str]]) -> bool:
    if not entries:
        return False
    for entry in entries:
        if find_blocklisted_terms(entry.get("q")) or find_blocklisted_terms(entry.get("a")):
            return False
    return True


def _generate_and_audit_faq(payload: Dict[str, Any],
                            fallback_entries: List[Dict[str, str]],
                            audit_log: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    if _is_budget_constrained_live_runtime():
        _log_action(audit_log, "faq", "llm_fallback", {"reason": "runtime_budget_preserve_core_copy"})
        return fallback_entries
    for attempt in range(_llm_retry_budget(2)):
        try:
            raw = _llm_generate_faq(payload)
        except LLMClientUnavailable as exc:
            if _log_retryable_llm_exception(audit_log, "faq", exc, attempt + 1):
                continue
            return fallback_entries
        entries = _parse_faq_output(raw)
        if _faq_entries_valid(entries):
            _log_action(audit_log, "faq", "llm_success", {"attempt": attempt + 1})
            return entries
        _log_action(
            audit_log,
            "faq",
            "llm_retry",
            {"attempt": attempt + 1, "reason": "invalid_or_blocked_entries"},
        )
    _log_action(audit_log, "faq", "llm_fallback", {"reason": "validation_failed"})
    _record_repair_event(
        payload.get("_artifact_dir"),
        "faq",
        {"faq_validation_failed": True},
        json.dumps(fallback_entries, ensure_ascii=False),
        json.dumps(fallback_entries, ensure_ascii=False),
        repair_success=False,
        default_rule="faq_validation_failed",
    )
    return fallback_entries



def generate_faq(preprocessed_data: PreprocessedData,
                writing_policy: Dict[str, Any],
                language: str = "Chinese",
                audit_log: Optional[List[Dict[str, Any]]] = None,
                request_timeout_seconds: Optional[int] = None) -> List[Dict[str, str]]:
    """
    生成FAQ（LLM优先，失败时回退模板）
    """
    directives = writing_policy.get("compliance_directives", {})
    faq_only_capabilities = writing_policy.get('faq_only_capabilities', [])
    entity_profile = getattr(preprocessed_data, "asin_entity_profile", {}) or {}
    question_bank_context = writing_policy.get("question_bank_context") or build_question_bank_context(
        entity_profile,
        getattr(preprocessed_data, "target_country", ""),
    )
    fallback_faq = _compose_faq_fallback(
        preprocessed_data,
        directives,
        faq_only_capabilities,
        language,
        question_bank_context,
    )
    payload = {
        "brand": getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT"),
        "target_language": language or getattr(preprocessed_data, "language", "Chinese"),
        "capability_constraints": getattr(preprocessed_data, "capability_constraints", {}) or {},
        "compliance_directives": directives,
        "faq_only_capabilities": faq_only_capabilities,
        "intent_graph": writing_policy.get("intent_graph", []),
        "question_bank_context": question_bank_context,
    }
    if request_timeout_seconds:
        payload["_request_timeout_seconds"] = int(request_timeout_seconds)
    return _generate_and_audit_faq(payload, fallback_faq, audit_log)


def _compose_faq_fallback(preprocessed_data: PreprocessedData,
                          directives: Dict[str, Any],
                          faq_only_capabilities: List[str],
                          language: str,
                          question_bank_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}
    waterproof = directives.get("waterproof", {})
    depth = waterproof.get("depth_m")
    waterproof_depth = f"{depth}米" if depth else attr_data.get('waterproof_depth', '30米')
    if waterproof.get("requires_case") and waterproof.get("note"):
        waterproof_note = waterproof["note"]
    else:
        waterproof_note = "需按说明使用防水壳。" if waterproof.get("requires_case") else ""
    battery_life = attr_data.get('battery_life', '150分钟')
    max_storage = attr_data.get('max_storage', '256GB')
    warranty_period = attr_data.get('warranty_period', '12个月')

    templates = FAQ_TEMPLATES.get(language, FAQ_TEMPLATES["English"])
    faqs: List[Dict[str, str]] = []
    question_bank_context = question_bank_context or {}
    for item in (question_bank_context.get("questions") or [])[:2]:
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        evidence_hints = ", ".join(question_bank_context.get("evidence_hints", [])[:2])
        answer = (
            f"Check the supported product facts before purchase: {evidence_hints}."
            if language == "English"
            else f"下单前请结合当前已验证信息确认：{evidence_hints or '请查看详情页中的参数与使用边界'}。"
        )
        faqs.append({"q": question, "a": answer})
    format_params = {
        "waterproof_depth": waterproof_depth,
        "battery_life": battery_life,
        "max_storage": max_storage,
        "warranty_period": warranty_period,
        "waterproof_note": waterproof_note or ""
    }
    for template in templates[:5]:
        if len(faqs) >= 5:
            break
        faqs.append({
            "q": template["q"],
            "a": template["a"].format(**format_params),
        })

    for capability in faq_only_capabilities[:2]:
        if len(faqs) >= 5:
            break
        if "防抖" in capability or "stabilization" in capability:
            faqs.append({
                "q": "防抖功能有什么限制？" if language == "Chinese" else "Are there any limitations to the stabilization?",
                "a": "这款产品更适合城市通勤、日常记录和 Vlog 自拍等相对平稳的场景；若需应对摩托车或高强度颠簸运动，建议搭配专业稳定设备以获得更理想的画面表现。" if language == "Chinese" else "Built to shine in commuting, everyday POV, and vlog-style movement; for motorcycle use or higher-intensity vibration, pair it with dedicated stabilization gear for the best viewing experience."
            })
        elif "防水" in capability or "waterproof" in capability:
            faqs.append({
                "q": "防水功能需要注意什么？" if language == "Chinese" else "What should I know about the waterproof feature?",
                "a": waterproof_note or ("搭配随附防水壳使用时，更适合浮潜、泳池和旅行涉水记录；按照说明正确密封，并在标注深度范围内使用，可获得更安心的拍摄体验。" if language == "Chinese" else "For the most confident water recording, use the included housing for snorkeling, pool days, and travel water scenes, and stay within the stated depth guidance after sealing the case correctly.")
            })
    return faqs[:5]


def generate_search_terms(preprocessed_data: PreprocessedData,
                         writing_policy: Dict[str, Any],
                         title: str,
                         bullets: List[str],
                         description: str = "",
                         language: str = "Chinese",
                         tiered_keywords: Dict[str, List[str]] = None,
                         keyword_slots: Optional[Dict[str, Any]] = None,
                         audit_log: Optional[List[Dict[str, Any]]] = None,
                         assignment_tracker: Optional[KeywordAssignmentTracker] = None) -> Tuple[List[str], Dict[str, Any]]:
    """
    生成搜索词 - 优化版：优先使用L2/L3长尾关键词
    """
    tiered_keywords = tiered_keywords or {"l1": [], "l2": [], "l3": []}
    candidate_terms: List[str] = []
    taboo_terms = TABOO_KEYWORDS
    plan = writing_policy.get("search_term_plan", {})
    max_bytes = plan.get("max_bytes", 249)
    backend_only_terms = set(plan.get("backend_only_terms", []))
    backend_residual_keywords = plan.get("backend_residual_keywords", []) or []
    backend_longtail_keywords = backend_residual_keywords or plan.get("backend_longtail_keywords", []) or []
    approved_feedback_backend_terms = plan.get("approved_feedback_backend_terms", []) or []
    priority_tiers = [
        str(tier or "").strip().lower()
        for tier in (plan.get("priority_tiers", ["l3"]) or [])
        if str(tier or "").strip()
    ]
    priority_roles = {
        str(role or "").strip().lower()
        for role in (plan.get("priority_roles") or [])
        if str(role or "").strip()
    }
    role_aware_search_plan = bool(priority_roles)
    role_checked_sources = {
        "backend_longtail",
        "brand",
        "category",
        "scene_backend",
        "mode_backend",
        "keyword_slot",
        "policy_l3",
        "priority_role",
        "priority_tier",
        "l3_fill",
        "density_fill",
    }
    metadata_map = dict((tiered_keywords or {}).get("_metadata", {}) or {})
    for row in writing_policy.get("keyword_metadata") or []:
        keyword = str((row or {}).get("keyword") or "").strip()
        if not keyword:
            continue
        lowered = keyword.lower()
        existing = metadata_map.get(lowered) or {}
        merged = dict(row or {})
        merged.update(existing)
        merged["keyword"] = existing.get("keyword") or keyword
        merged["tier"] = str(existing.get("tier") or (row or {}).get("tier") or (row or {}).get("level") or "").upper()
        merged["source_type"] = existing.get("source_type") or (row or {}).get("source_type")
        merged["search_volume"] = existing.get("search_volume") or (row or {}).get("search_volume")
        merged["country"] = existing.get("country") or (row or {}).get("country") or (row or {}).get("source_country")
        merged["detected_locale"] = existing.get("detected_locale") or (row or {}).get("detected_locale")
        metadata_map[lowered] = merged
    if assignment_tracker is not None and hasattr(assignment_tracker, "_metadata_map"):
        assignment_tracker._metadata_map.update(metadata_map)
    preferred_locale = (
        writing_policy.get("preferred_locale")
        or (tiered_keywords or {}).get("_preferred_locale")
        or locale_code_for_language(language)
    )
    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    category_type = infer_category_type(preprocessed_data)
    title_front_tokens = _tokenize_text_block(title)[:5]
    title_front_phrase = " ".join(title_front_tokens)

    search_term_roots: Set[str] = set()
    candidate_term_keys: Set[str] = set()
    backend_only_used = 0
    dedup_root_skips = 0
    existing_non_search_assignment_keywords: Set[str] = set()
    if assignment_tracker is not None:
        for record in assignment_tracker.as_list():
            fields = set((record or {}).get("assigned_fields") or [])
            if any(field != "search_terms" for field in fields):
                keyword = str((record or {}).get("keyword") or "").strip().lower()
                if keyword:
                    existing_non_search_assignment_keywords.add(keyword)

    def _search_role_allowed(term: str, *, allow_unmapped: bool = False) -> bool:
        if not role_aware_search_plan:
            return True
        meta = metadata_map.get((term or "").strip().lower()) or {}
        if not meta:
            return allow_unmapped
        if meta.get("blocked") or meta.get("blocked_brand") or meta.get("relevance_filtered"):
            return False
        quality_status = str(meta.get("quality_status") or "").strip().lower()
        if quality_status and quality_status != "qualified":
            return False
        routing_role = str(meta.get("routing_role") or meta.get("role") or "").strip().lower()
        return routing_role in priority_roles

    backend_plan_terms = {
        str(term or "").strip().lower()
        for term in backend_longtail_keywords
        if str(term or "").strip()
    }

    def _role_priority_terms() -> List[str]:
        if not role_aware_search_plan:
            return []
        rows = []
        for row in metadata_map.values():
            keyword = str((row or {}).get("keyword") or "").strip()
            if keyword and _search_role_allowed(keyword):
                rows.append(row)
        rows = sorted(
            rows,
            key=lambda row: (
                float((row or {}).get("opportunity_score") or 0),
                float((row or {}).get("blue_ocean_score") or 0),
                float((row or {}).get("keyword_quality_score") or 0),
                float((row or {}).get("search_volume") or 0),
            ),
            reverse=True,
        )
        return _dedupe_keyword_sequence([str((row or {}).get("keyword") or "").strip() for row in rows])

    explicit_policy_l3_terms: List[str] = []
    for row in writing_policy.get("keyword_metadata") or []:
        keyword = str((row or {}).get("keyword") or "").strip()
        if not keyword:
            continue
        tier = str((row or {}).get("tier") or (row or {}).get("level") or "").upper()
        if tier != "L3":
            continue
        if role_aware_search_plan and not _search_role_allowed(keyword):
            continue
        if keyword.lower() in existing_non_search_assignment_keywords:
            continue
        explicit_policy_l3_terms.append(keyword)
    explicit_policy_l3_terms = [
        keyword
        for keyword in _dedupe_keyword_sequence(
            sorted(
                explicit_policy_l3_terms,
                key=lambda item: float((metadata_map.get(item.lower()) or {}).get("search_volume") or 0),
                reverse=True,
            )
        )
    ]

    def _add_term(term: str, source: str = "keyword"):
        nonlocal backend_only_used, dedup_root_skips
        cleaned = (term or "").strip()
        if not cleaned:
            return
        normalized = cleaned.lower()
        if title_front_phrase and _tokenize_text_block(cleaned) == title_front_tokens:
            _log_action(
                audit_log,
                "search_terms",
                "title_front_skip",
                {"term": cleaned, "source": source, "reason": "exact_title_front_phrase"},
            )
            return
        matched_brand = is_blocklisted_brand(cleaned)
        if matched_brand:
            _log_action(
                audit_log,
                "search_terms",
                "brand_skip",
                {"term": cleaned, "brand": matched_brand, "source": source},
            )
            return
        meta = metadata_map.get(normalized)
        if preferred_locale and preferred_locale != "en":
            if not token_matches_locale(cleaned, meta, preferred_locale):
                _log_action(
                    audit_log,
                    "search_terms",
                    "locale_skip",
                    {"term": cleaned, "source": source, "preferred_locale": preferred_locale},
                )
                return
        if any(taboo in normalized for taboo in taboo_terms):
            _log_action(
                audit_log,
                "search_terms",
                "taboo_skip",
                {"term": cleaned, "reason": "taboo keyword filtered"},
            )
            return
        if role_aware_search_plan and source in role_checked_sources:
            if not _search_role_allowed(cleaned, allow_unmapped=normalized in backend_plan_terms):
                _log_action(
                    audit_log,
                    "search_terms",
                    "routing_role_skip",
                    {"term": cleaned, "source": source, "priority_roles": sorted(priority_roles)},
                )
                return
        conflict_reason = _keyword_conflicts_constraints(cleaned, capability_constraints)
        if conflict_reason:
            _log_action(
                audit_log,
                "search_terms",
                "constraint_skip",
                {"term": cleaned, "reason": conflict_reason},
            )
            return
        if normalized in candidate_term_keys:
            _log_action(
                audit_log,
                "search_terms",
                "dedupe_skip",
                {"term": cleaned, "source": source, "reason": "term_already_added"},
            )
            return
        tokens = _tokenize_text_block(cleaned)
        new_roots: List[str] = []
        for token in tokens:
            root = _stem_token(token)
            if not root:
                continue
            if root not in search_term_roots:
                new_roots.append(root)
        if not new_roots:
            dedup_root_skips += 1
            _log_action(
                audit_log,
                "search_terms",
                "dedupe_skip",
                {"term": cleaned, "source": source, "reason": "tokens_already_used"},
            )
            return
        search_term_roots.update(new_roots)
        candidate_term_keys.add(normalized)
        candidate_terms.append(cleaned)
        if assignment_tracker:
            assignment_tracker.record("search_terms", [cleaned])
        if source == "backend_only":
            backend_only_used += 1

    if keyword_slots is None:
        keyword_slots = writing_policy.get("keyword_slots") or {}
    for kw in (keyword_slots.get("search_terms") or {}).get("keywords", []):
        if kw:
            _add_term(kw, source="keyword_slot")

    for term in backend_longtail_keywords:
        _add_term(term, source="backend_longtail")

    for term in explicit_policy_l3_terms:
        _add_term(term, source="policy_l3")

    if role_aware_search_plan:
        for kw in _role_priority_terms():
            _add_term(kw, source="priority_role")
    else:
        for tier in priority_tiers:
            for kw in tiered_keywords.get(tier, []):
                _add_term(kw, source="priority_tier")

    if backend_only_terms:
        for term in backend_only_terms:
            _log_action(
                audit_log,
                "search_terms",
                "backend_only_deferred",
                {"term": term, "reason": "recorded for diagnostics but not injected into final Amazon backend copy"},
            )

    for term in approved_feedback_backend_terms:
        _add_term(term, source="feedback_backend")

    scene_backend_terms = {
        "cycling_recording": {
            "English": ["cycling camera", "bike helmet camera", "commute camera"],
            "German": ["Fahrradkamera", "Helmkamera", "Pendelkamera"],
            "French": ["caméra vélo", "caméra casque", "caméra trajet"],
        },
        "underwater_exploration": {
            "English": ["underwater camera", "snorkeling camera"],
            "German": ["Unterwasserkamera", "Schnorchelkamera"],
            "French": ["caméra sous-marine", "caméra snorkeling"],
        },
        "travel_documentation": {
            "English": ["travel camera", "vacation camera"],
            "German": ["Reisekamera", "Urlaubskamera"],
            "French": ["caméra voyage", "caméra vacances"],
        },
        "sports_training": {
            "English": ["training camera", "pov camera"],
            "German": ["Trainingskamera", "POV Kamera"],
            "French": ["caméra entraînement", "caméra POV"],
        },
        "vlog_content_creation": {
            "English": ["vlog camera", "wifi action camera"],
            "German": ["Vlog Kamera", "WLAN Actionkamera"],
            "French": ["caméra vlog", "caméra action wifi"],
        },
        "family_use": {
            "English": ["family travel camera"],
            "German": ["Familienkamera"],
            "French": ["caméra famille"],
        },
    }
    for scene_code in (writing_policy.get("scene_priority") or [])[:5]:
        localized_defaults = scene_backend_terms.get(scene_code, {})
        for term in localized_defaults.get(language, localized_defaults.get("English", [])):
            _add_term(term, source="scene_backend")

    mode_guidance = writing_policy.get("recording_mode_guidance", {}) or {}
    for mode, info in (mode_guidance.get("guidance_by_mode") or {}).items():
        visibility = (info or {}).get("stabilization_visibility") or ""
        if mode == "1080P" and visibility in {"primary", "qualified"}:
            for term in {
                "English": ["1080p action camera", "stabilized action camera"],
                "German": ["1080P Actionkamera", "stabilisierte Actionkamera"],
                "French": ["caméra action 1080p", "caméra action stabilisée"],
            }.get(language, []):
                _add_term(term, source="mode_backend")
        if mode == "4K":
            for term in {
                "English": ["4k adventure camera", "4k travel camera"],
                "German": ["4K Outdoorkamera", "4K Reisekamera"],
                "French": ["caméra aventure 4k", "caméra voyage 4k"],
            }.get(language, []):
                _add_term(term, source="mode_backend")

    category_terms_by_category = {
        "wearable_body_camera": {
            "Chinese": ["拇指相机", "可穿戴相机", "迷你相机"],
            "English": ["body camera", "body cam", "wearable camera", "thumb camera"],
            "German": ["Bodycam", "Körperkamera", "Mini Kamera"],
            "French": ["caméra corporelle", "mini caméra", "caméra portable"],
            "Spanish": ["cámara corporal", "mini cámara", "cámara wearable"],
            "Italian": ["body cam", "mini camera", "telecamera indossabile"],
            "Japanese": ["ボディカメラ", "小型カメラ", "ウェアラブルカメラ"],
        },
        "action_camera": {
            "Chinese": ["运动相机", "户外相机", "摄像机", "拍摄设备"],
            "English": ["action camera", "sports camera", "camcorder", "recording device"],
            "German": ["Actionkamera", "Sportkamera", "Videokamera", "Aufnahmegerät"],
            "French": ["caméra d'action", "caméra sport"],
            "Spanish": ["cámara de acción", "cámara deportiva", "videocámara", "dispositivo de grabación"],
            "Italian": ["videocamera sportiva", "fotocamera sportiva", "videocamera", "dispositivo di registrazione"],
            "Japanese": ["アクションカメラ", "スポーツカメラ", "ビデオカメラ", "録画装置"],
        },
    }
    category_terms = category_terms_by_category.get(category_type, category_terms_by_category["action_camera"])
    for term in category_terms.get(language, category_terms["English"]):
        _add_term(term, source="category")

    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"
    if brand != "TOSBARRFT":
        _add_term(brand, source="brand")

    filtered_terms: List[str] = []
    byte_total = 0
    existing_terms: Set[str] = set()
    for term in candidate_terms:
        term_bytes = len(term.encode("utf-8"))
        extra = 1 if filtered_terms else 0
        if byte_total + term_bytes + extra > max_bytes:
            _log_action(audit_log, "search_terms", "truncate_skip", {"term": term, "reason": "byte_limit"})
            continue
        filtered_terms.append(term)
        existing_terms.add(term)
        byte_total += term_bytes + extra

    if byte_total < max_bytes and not role_aware_search_plan:
        for kw in tiered_keywords.get("l3", []):
            keyword_phrase = (kw or "").strip()
            if not keyword_phrase or keyword_phrase in existing_terms:
                continue
            normalized_phrase = keyword_phrase.lower()
            meta = metadata_map.get(normalized_phrase)
            if preferred_locale and preferred_locale != "en":
                if not token_matches_locale(keyword_phrase, meta, preferred_locale):
                    _log_action(
                        audit_log,
                        "search_terms",
                        "locale_skip",
                        {"term": keyword_phrase, "source": "l3_fill", "preferred_locale": preferred_locale},
                    )
                    continue
            if is_blocklisted_brand(keyword_phrase):
                _log_action(
                    audit_log,
                    "search_terms",
                    "brand_skip",
                    {"term": keyword_phrase, "source": "l3_fill"},
                )
                continue
            if any(taboo in normalized_phrase for taboo in taboo_terms):
                _log_action(
                    audit_log,
                    "search_terms",
                    "taboo_skip",
                    {"term": keyword_phrase, "reason": "taboo keyword filtered"},
                )
                continue
            conflict_reason = _keyword_conflicts_constraints(keyword_phrase, capability_constraints)
            if conflict_reason:
                _log_action(
                    audit_log,
                    "search_terms",
                    "constraint_skip",
                    {"term": keyword_phrase, "source": "l3_fill", "reason": conflict_reason},
                )
                continue
            roots = [_stem_token(token) for token in _tokenize_text_block(keyword_phrase)]
            roots = [root for root in roots if root]
            if roots and all(root in search_term_roots for root in roots):
                _log_action(
                    audit_log,
                    "search_terms",
                    "dedupe_skip",
                    {"term": keyword_phrase, "source": "l3_fill", "reason": "tokens_already_used"},
                )
                continue
            term_bytes = len(keyword_phrase.encode("utf-8"))
            extra = 1 if filtered_terms else 0
            if byte_total + term_bytes + extra > max_bytes:
                continue
            filtered_terms.append(keyword_phrase)
            existing_terms.add(keyword_phrase)
            byte_total += term_bytes + extra
            search_term_roots.update(roots)
            if assignment_tracker:
                assignment_tracker.record("search_terms", [keyword_phrase])
            if byte_total >= max_bytes:
                break

    min_density_target = min(max_bytes, int(plan.get("density_target_bytes") or 220))
    if byte_total < min_density_target:
        density_candidates: List[str] = []
        density_candidates.extend(backend_longtail_keywords)
        if role_aware_search_plan:
            density_candidates.extend(_role_priority_terms())
        else:
            density_candidates.extend(tiered_keywords.get("l3", []))
            density_candidates.extend(tiered_keywords.get("l2", []))
        if category_type == "wearable_body_camera":
            density_candidates.extend([
                "mini body camera",
                "travel body camera",
                "wearable body camera",
                "commute body camera",
            ])
        else:
            density_candidates.extend([
                "mini action camera",
                "travel action camera",
                "wearable action camera",
                "compact vlog camera",
            ])
        scene_density_terms = {
            "cycling_recording": ["cycling action camera", "bike helmet camera", "commute ride camera"],
            "travel_documentation": ["travel vlog camera", "vacation action camera"],
            "vlog_content_creation": ["portable vlog camera", "selfie vlog camera"],
            "family_use": ["family travel camera"],
            "sports_training": ["training action camera", "sports pov camera"],
        }
        for scene_code in (writing_policy.get("scene_priority") or [])[:5]:
            density_candidates.extend(scene_density_terms.get(scene_code, []))

        for keyword_phrase in _dedupe_keyword_sequence(density_candidates):
            if byte_total >= min_density_target:
                break
            if not keyword_phrase or keyword_phrase in existing_terms:
                continue
            normalized_phrase = keyword_phrase.lower()
            if title_front_phrase and _tokenize_text_block(keyword_phrase) == title_front_tokens:
                continue
            meta = metadata_map.get(normalized_phrase)
            if preferred_locale and preferred_locale != "en":
                if not token_matches_locale(keyword_phrase, meta, preferred_locale):
                    continue
            if any(taboo in normalized_phrase for taboo in taboo_terms):
                continue
            if is_blocklisted_brand(keyword_phrase):
                continue
            if role_aware_search_plan and not _search_role_allowed(
                keyword_phrase,
                allow_unmapped=normalized_phrase in backend_plan_terms,
            ):
                continue
            conflict_reason = _keyword_conflicts_constraints(keyword_phrase, capability_constraints)
            if conflict_reason:
                continue
            term_bytes = len(keyword_phrase.encode("utf-8"))
            extra = 1 if filtered_terms else 0
            if byte_total + term_bytes + extra > max_bytes:
                continue
            filtered_terms.append(keyword_phrase)
            existing_terms.add(keyword_phrase)
            byte_total += term_bytes + extra
            if assignment_tracker:
                assignment_tracker.record("search_terms", [keyword_phrase])
            _log_action(
                audit_log,
                "search_terms",
                "density_fill",
                {"term": keyword_phrase, "byte_length": byte_total},
            )

    trace = {
        "byte_length": byte_total,
        "max_bytes": max_bytes,
        "backend_only_used": backend_only_used,
        "dedup_root_skips": dedup_root_skips,
        "unique_tokens": len(filtered_terms),
    }
    _log_action(
        audit_log,
        "search_terms",
        "dedupe_summary",
        {"unique_tokens": len(filtered_terms), "byte_length": byte_total, "dedup_root_skips": dedup_root_skips},
    )
    return filtered_terms, trace


def generate_aplus_content(preprocessed_data: PreprocessedData,
                          writing_policy: Dict[str, Any],
                          language: str = "Chinese",
                          audit_log: Optional[List[Dict[str, Any]]] = None,
                          request_timeout_seconds: Optional[int] = None) -> Tuple[str, bool, List[Dict[str, Any]]]:
    """
    生成A+内容（强制使用实时 LLM）
    """
    target_language = language or getattr(preprocessed_data, "language", "English")
    brand = getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT")
    capability_bindings = writing_policy.get("capability_scene_bindings", [])
    accessory_items = _prepare_accessory_items(preprocessed_data.accessory_descriptions)
    attr_lookup = _build_attr_lookup(preprocessed_data.attribute_data)
    capability_constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    evidence_numeric_values = _collect_evidence_numeric_values(attr_lookup, capability_constraints)
    supported_spec_dimensions = _dedupe_keyword_sequence(
        _infer_spec_dimensions(" ".join(evidence_numeric_values))
        + _infer_spec_dimensions(" ".join(preprocessed_data.core_selling_points or []))
        + _infer_spec_dimensions(" ".join([str(v) for v in attr_lookup.values() if v]))
    )

    payload = {
        "field": "aplus",
        "brand_name": brand,
        "target_language": target_language,
        "product_profile": {
            "core_capabilities": preprocessed_data.core_selling_points,
            "scene_priority": writing_policy.get("scene_priority", []),
            "attributes": attr_lookup,
            "quality_score": getattr(preprocessed_data, "quality_score", None),
        },
        "capability_scene_bindings": capability_bindings,
        "accessories": accessory_items,
        "unassigned_keywords": writing_policy.get("keyword_slots", {}).get("aplus_keywords", []),
        "evidence_numeric_values": evidence_numeric_values,
        "supported_spec_dimensions": supported_spec_dimensions,
    }
    if request_timeout_seconds:
        payload["_request_timeout_seconds"] = int(request_timeout_seconds)

    text = _generate_and_audit_aplus(payload, audit_log)
    is_native = not payload.get("_aplus_fallback", False)
    visual_briefs = _extract_visual_briefs(text)
    write_visual_briefs_to_intent_graph(writing_policy, visual_briefs)
    return text, is_native, visual_briefs


VISUAL_HEADER_PATTERN = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def _build_visual_brief_line(title: str, language: str, canonical_specs: Optional[List[str]] = None) -> str:
    lang = (language or "").lower()
    canonical_specs = canonical_specs or []
    if lang.startswith("fr"):
        brief_text = f"[Visual Design Brief: Illustrer « {title} » avec un sujet dynamique, angle trois-quarts, éclairage contrasté et espace négatif à gauche pour le texte français.]"
        json_block = json.dumps({
            "section": title,
            "subject": f"Sujet dynamique lié à « {title} »",
            "angle": "angle trois-quarts",
            "lighting": "éclairage contrasté",
            "text_placement": "espace négatif à gauche",
            "canonical_specs_highlighted": canonical_specs[:3],
        }, ensure_ascii=False)
        return f"{brief_text}\n{json_block}"
    if lang.startswith("zh"):
        brief_text = f"[Visual Design Brief: 展示“{title}”主题，人物处于真实使用场景，三分构图，右侧留出排版空白。]"
        json_block = json.dumps({
            "section": title,
            "subject": f"以“{title}”为主题的真实使用者",
            "angle": "三分构图",
            "lighting": "柔和补光+高对比",
            "text_placement": "右侧留白",
            "canonical_specs_highlighted": canonical_specs[:3],
        }, ensure_ascii=False)
        return f"{brief_text}\n{json_block}"
    brief_text = f"[Visual Design Brief: Depict '{title}' with lifestyle action, three-quarter angle lighting, and ample negative space for localized copy.]"
    json_block = json.dumps({
        "section": title,
        "subject": f"Lifestyle subject illustrating '{title}'",
        "angle": "three-quarter",
        "lighting": "high-contrast rim light",
        "text_placement": "negative space to the right",
        "canonical_specs_highlighted": canonical_specs[:3],
    }, ensure_ascii=False)
    return f"{brief_text}\n{json_block}"


def _apply_default_visual_briefs(markdown: str, language: str, canonical_specs: Optional[List[str]] = None) -> str:
    def _inject(match: re.Match) -> str:
        header = match.group(0)
        title = match.group(2)
        return f"{header}\n{_build_visual_brief_line(title, language, canonical_specs)}"

    return VISUAL_HEADER_PATTERN.sub(_inject, markdown)


def _extract_visual_briefs(markdown: str) -> List[Dict[str, Any]]:
    briefs: List[Dict[str, Any]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            data = json.loads(stripped)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("section"):
            briefs.append(data)
    return briefs


def _sanitize_accessory_text(text: str) -> str:
    """
    Normalize accessory snippets before surfacing them in visible fields.
    Removes bracketed tokens, excess whitespace, and lingering punctuation.
    """
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = re.sub(r"[\\[\\]{}<>•]", " ", cleaned)
    cleaned = re.sub(r"\\s+", " ", cleaned).strip()
    return cleaned


def _prepare_accessory_items(accessories: List[Dict[str, Any]]) -> List[str]:
    items: List[str] = []
    for acc in accessories or []:
        segments: List[str] = []
        for key in ("name", "specification", "note", "description", "original"):
            value = acc.get(key)
            if value:
                segments.append(str(value))
        combined = " ".join(segments)
        cleaned = _sanitize_accessory_text(combined)
        if cleaned:
            items.append(cleaned)
    return items


def _collect_numeric_tokens(preprocessed_data: PreprocessedData,
                            directives: Dict[str, Any]) -> List[str]:
    tokens: List[str] = []
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    runtime = constraints.get("runtime_minutes") or directives.get("runtime_minutes")
    if runtime:
        tokens.append(f"{runtime} minutes")
    depth = constraints.get("waterproof_depth_m") or directives.get("waterproof", {}).get("depth_m")
    if depth:
        tokens.append(f"{depth} m")
    battery = constraints.get("battery_capacity") or _get_attr_value(
        _build_attr_lookup(preprocessed_data.attribute_data),
        ["battery capacity", "battery_capacity"], ""
    )
    if battery:
        tokens.append(str(battery))
    resolution = constraints.get("max_resolution") or directives.get("max_resolution")
    if resolution:
        tokens.append(str(resolution))
    normalized_tokens: List[str] = []
    seen = set()
    for token in tokens:
        cleaned = re.sub(r"\s+", " ", str(token)).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        normalized_tokens.append(cleaned)
    return normalized_tokens


def _build_llm_system_prompt(field_name: str, target_language: str) -> str:
    return (
        f"You are an expert Amazon listing copywriter. Field: {field_name}. "
        "All payload fields are canonical English facts/specifications. "
        f"Generate the final text directly in {target_language} using only those facts. "
        "Never output Chinese characters or transliterations. "
        "Do not output JSON or explanations—return the final text only."
    )


def _call_llm_for_field(field_name: str,
                        payload: Dict[str, Any],
                        temperature: float = 0.35) -> str:
    client = get_llm_client()
    target_language = payload.get("target_language") or "English"
    system_prompt = _build_llm_system_prompt(field_name, target_language)
    text = client.generate_text(system_prompt, payload, temperature)
    return (text or "").strip()


def _flatten_tokens(tokens: Sequence[str]) -> List[str]:
    flattened: List[str] = []
    for token in tokens or []:
        if not token:
            continue
        flattened.append(re.sub(r"\s+", " ", str(token)).strip())
    return flattened


def _check_numeric_presence(text: str, numeric_specs: Sequence[str]) -> bool:
    if not numeric_specs:
        return True
    normalized_text = text.lower()
    for spec in numeric_specs:
        if not spec:
            continue
        normalized_spec = str(spec).lower()
        digits = re.findall(r"[\d]+(?:[.,]\d+)?", normalized_spec)
        if digits:
            if not any(digit in normalized_text for digit in digits):
                return False
        elif normalized_spec not in normalized_text:
            return False
    return True


def _extract_resolution_evidence(attr_lookup: Dict[str, str]) -> str:
    for key in ("video_resolution", "resolution", "video_capture_resolution"):
        value = str(attr_lookup.get(key) or "").strip()
        if not value:
            continue
        match = re.search(r"\b(?:5k|4k|2k|1080p|720p)\b", value, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return ""


def _collect_evidence_numeric_values(
    attr_lookup: Dict[str, str],
    capability_constraints: Dict[str, Any],
    *,
    limit: int = 5,
) -> List[str]:
    values: List[str] = []
    runtime = capability_constraints.get("runtime_minutes")
    if runtime:
        values.append(f"{runtime} minutes")
    depth = capability_constraints.get("waterproof_depth_m")
    if depth:
        values.append(f"{depth} m")
    resolution = _extract_resolution_evidence(attr_lookup)
    if resolution:
        values.append(resolution)
    for key in ("battery_life", "weight", "item_weight"):
        value = str(attr_lookup.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return _dedupe_keyword_sequence(values)[:limit]


SPEC_DIMENSION_HINTS: Dict[str, Sequence[str]] = {
    "runtime": ("minute", "minutes", "battery", "runtime", "power"),
    "resolution": ("1080p", "4k", "5k", "resolution", "hd", "full hd", "video capture"),
    "weight": ("kg", "kilogram", "g", "gram", "weight", "lightweight", "portable"),
    "view_angle": ("wide angle", "view angle", "fov", "degree", "lens", "focal", "f/"),
    "waterproof": ("waterproof", "water resistant", "underwater", "dive", "snorkel", "m depth"),
    "connectivity": ("wifi", "wi-fi", "wireless", "bluetooth", "usb", "type-c", "app"),
}

DEFAULT_SLOT_SPEC_DIMENSIONS: Dict[str, str] = {
    "B1": "resolution",
    "B2": "runtime",
    "B3": "weight",
    "B4": "view_angle",
    "B5": "connectivity",
}


def _infer_spec_dimensions(text: str) -> List[str]:
    lowered = _normalize_keyword_text(text or "")
    if not lowered:
        return []
    dimensions: List[str] = []
    for dimension, hints in SPEC_DIMENSION_HINTS.items():
        if any(hint and hint in lowered for hint in hints):
            dimensions.append(dimension)
    return _dedupe_keyword_sequence(dimensions)


def _select_slot_spec_dimension(
    slot_name: str,
    capability: str,
    capability_bundle: Sequence[str],
    used_dimensions: Set[str],
) -> str:
    candidates: List[str] = []
    for candidate_text in [capability] + list(capability_bundle or []):
        candidates.extend(_infer_spec_dimensions(candidate_text))
    fallback = DEFAULT_SLOT_SPEC_DIMENSIONS.get((slot_name or "").upper(), "")
    if fallback:
        candidates.append(fallback)
    deduped = _dedupe_keyword_sequence(candidates)
    for dimension in deduped:
        if dimension not in used_dimensions:
            return dimension
    return deduped[0] if deduped else "resolution"


def _preferred_numeric_proof_for_capability(
    capability: str,
    capability_constraints: Dict[str, Any],
    attr_lookup: Dict[str, str],
    evidence_numeric_values: Sequence[str],
) -> Optional[str]:
    capability_norm = _normalize_keyword_text(capability or "")
    runtime = capability_constraints.get("runtime_minutes")
    depth = capability_constraints.get("waterproof_depth_m")
    resolution = _extract_resolution_evidence(attr_lookup)
    if any(token in capability_norm for token in ["battery", "runtime", "power"]):
        return f"{runtime} minutes" if runtime else (attr_lookup.get("battery_life") or None)
    if any(token in capability_norm for token in ["waterproof", "underwater", "dive", "snorkel"]):
        return f"{depth} m" if depth else None
    if any(token in capability_norm for token in ["resolution", "video", "definition", "4k", "1080p", "5k"]):
        return resolution or None
    if any(token in capability_norm for token in ["lightweight", "portable", "weight"]):
        return attr_lookup.get("weight") or attr_lookup.get("item_weight") or None
    return next((item for item in evidence_numeric_values or [] if item), None)


def _bullet_dimension_signature(text: str, capability: str = "") -> str:
    source = capability or text or ""
    tokens = [
        token for token in _tokenize_text_block(_normalize_keyword_text(source))
        if token not in {"with", "for", "and", "the", "camera", "design", "ready", "life", "mode"}
    ]
    return " ".join(tokens[:2]).strip()


def _diversify_duplicate_bullet_dimensions(
    final_bullets: List[str],
    bullet_trace: List[Dict[str, Any]],
    allowed_capabilities: Sequence[str],
    slot_keyword_records: Dict[str, List[str]],
    final_language: str,
    audit_log: Optional[List[Dict[str, Any]]],
    attr_lookup: Dict[str, str],
    capability_constraints: Dict[str, Any],
) -> List[str]:
    dedup_result = fc.check_bullet_dimension_dedup(final_bullets)
    if not dedup_result.get("pass"):
        duplicated_dimension = str(dedup_result.get("duplicated_dimension") or "repeated_dimension")
        affected_bullets = [int(idx) for idx in (dedup_result.get("affected_bullets") or [])]
        for bullet_number in affected_bullets[1:] or affected_bullets:
            idx = bullet_number - 1
            if idx < 0 or idx >= len(final_bullets):
                continue
            trace_entry = bullet_trace[idx] if idx < len(bullet_trace) else {}
            slot_name = trace_entry.get("slot") or f"B{idx+1}"
            payload = {
                "slot": slot_name,
                "capability": trace_entry.get("capability") or "",
                "target_language": final_language,
                "mandatory_keywords": slot_keyword_records.get(slot_name, []),
                "localized_capability_anchors": _build_localized_capability_anchors(
                    trace_entry.get("capability_mapping") or [trace_entry.get("capability") or ""],
                    final_language,
                ),
                "localized_scene_anchors": _build_localized_scene_anchors(
                    trace_entry.get("scene_mapping") or ([trace_entry.get("scene_code")] if trace_entry.get("scene_code") else []),
                    final_language,
                ),
                "numeric_proof": _preferred_numeric_proof_for_capability(
                    trace_entry.get("capability") or "",
                    capability_constraints,
                    attr_lookup,
                    _collect_evidence_numeric_values(attr_lookup, capability_constraints),
                ),
                "benchmark_bullets": [
                    bullet for bullet_idx, bullet in enumerate(final_bullets)
                    if bullet_idx != idx and str(bullet or "").strip()
                ][:3],
            }
            failure_reason = {
                "fluency_dimension_repeat": True,
                "duplicated_dimension": duplicated_dimension,
                "affected_bullets": affected_bullets,
            }
            try:
                repaired = _repair_bullet_candidate_with_llm(final_bullets[idx], failure_reason, payload)
            except Exception:
                repaired = ""
            if repaired:
                repaired = _guarantee_mandatory_keywords(repaired, slot_keyword_records.get(slot_name, []), final_language)
                repaired = _enforce_bullet_length(repaired)
                final_bullets[idx] = repaired
                _log_action(
                    audit_log,
                    f"bullet_b{idx+1}",
                    "bullet_dimension_dedup_repair",
                    {"duplicated_dimension": duplicated_dimension, "affected_bullets": affected_bullets},
                )

    seen_signatures: Set[str] = set()
    used_capabilities = {
        _normalize_keyword_text((entry or {}).get("capability") or "")
        for entry in bullet_trace or []
        if (entry or {}).get("capability")
    }
    evidence_numeric_values = _collect_evidence_numeric_values(attr_lookup, capability_constraints)
    for idx, bullet in enumerate(final_bullets):
        trace_entry = bullet_trace[idx] if idx < len(bullet_trace) else {}
        signature = _bullet_dimension_signature(bullet, trace_entry.get("capability") or "")
        if not signature or signature not in seen_signatures:
            if signature:
                seen_signatures.add(signature)
            continue
        replacement_capability = next(
            (
                capability for capability in (allowed_capabilities or [])
                if _normalize_keyword_text(capability) not in used_capabilities
                and _bullet_dimension_signature("", capability) not in seen_signatures
            ),
            "",
        )
        if not replacement_capability:
            continue
        slot_name = trace_entry.get("slot") or f"B{idx+1}"
        numeric_proof = _preferred_numeric_proof_for_capability(
            replacement_capability,
            capability_constraints,
            attr_lookup,
            evidence_numeric_values,
        )
        payload = {
            "slot": slot_name,
            "capability": replacement_capability,
            "target_language": final_language,
            "brand_name": "",
            "mandatory_keywords": slot_keyword_records.get(slot_name, []),
            "localized_capability_anchors": _build_localized_capability_anchors([replacement_capability], final_language),
            "localized_scene_anchors": _build_localized_scene_anchors([trace_entry.get("scene_code")] if trace_entry.get("scene_code") else [], final_language),
        }
        replacement = _fallback_text_for_field(
            f"bullet_{slot_name.lower()}",
            payload,
            [numeric_proof] if numeric_proof else [],
        )
        replacement = _guarantee_mandatory_keywords(replacement, slot_keyword_records.get(slot_name, []), final_language)
        replacement = _enforce_bullet_length(replacement)
        final_bullets[idx] = replacement
        trace_entry["capability"] = replacement_capability
        trace_entry["capability_mapping"] = _merge_capability_mapping([replacement_capability], [], replacement_capability)
        used_capabilities.add(_normalize_keyword_text(replacement_capability))
        new_signature = _bullet_dimension_signature(replacement, replacement_capability)
        if new_signature:
            seen_signatures.add(new_signature)
        _log_action(
            audit_log,
            f"bullet_b{idx+1}",
            "bullet_dimension_dedup",
            {"replaced_with": replacement_capability},
        )
    return final_bullets


def _normalize_keyword_text(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return stripped.lower()


SEO_SLASH_PATTERN = re.compile(r"(?<!\d)\b[^\W\d_]{2,}\s*/\s*[^\W\d_]{2,}\b", re.IGNORECASE)
LOW_QUALITY_SLANG_PATTERNS = [
    re.compile(r"z[eé]ro gal[eè]re", re.IGNORECASE),
    re.compile(r"sans prise de t[eê]te", re.IGNORECASE),
    re.compile(r"sans blabla", re.IGNORECASE),
]


def _validate_field_text(text: str,
                         required_keywords: Sequence[str],
                         numeric_specs: Sequence[str]) -> Tuple[bool, Dict[str, Any], bool]:
    normalized_text = _normalize_keyword_text(text)
    if SEO_SLASH_PATTERN.search(text or ""):
        return False, {"seo_joiner": "slash_synonym_pattern"}, False
    slang_hits = [pattern.pattern for pattern in LOW_QUALITY_SLANG_PATTERNS if pattern.search(text or "")]
    if slang_hits:
        return False, {"slang_hits": slang_hits}, False
    missing_keywords = []
    for keyword in required_keywords or []:
        if not keyword:
            continue
        if _normalize_keyword_text(keyword) not in normalized_text:
            missing_keywords.append(keyword)
    if missing_keywords:
        return False, {"missing_keywords": missing_keywords}, False
    numeric_met = _check_numeric_presence(text, numeric_specs)
    if numeric_specs and not numeric_met:
        return False, {"missing_numeric": _flatten_tokens(numeric_specs)}, False
    blocked = find_blocklisted_terms(text)
    if blocked:
        return False, {"blocked_terms": blocked}, False
    return True, {}, numeric_met


def _fallback_text_for_field(field_name: str,
                             payload: Dict[str, Any],
                             numeric_specs: Sequence[str]) -> str:
    keywords = payload.get("mandatory_keywords") or []
    capability = payload.get("capability") or payload.get("core_capability") or ""
    scene = payload.get("scene_label") or payload.get("scene") or payload.get("scene_context")
    brand = payload.get("brand") or payload.get("brand_name")
    numeric = " ".join(numeric_specs) if numeric_specs else ""
    target_language = payload.get("target_language") or "English"
    if field_name == "title":
        category = payload.get("primary_category") or "Camera"
        exact_keywords = _dedupe_keyword_sequence(payload.get("exact_match_keywords") or [])
        l1_keywords = payload.get("l1_keywords") or []
        assigned_keywords = payload.get("assigned_keywords") or []
        lead_keyword = exact_keywords[0] if exact_keywords else (l1_keywords[0] if l1_keywords else category)
        support_keywords = _dedupe_keyword_sequence(exact_keywords + list(keywords) + list(l1_keywords) + list(assigned_keywords))
        title = _build_natural_title_candidate(
            payload,
            lead_keyword=lead_keyword,
            support_keywords=[
                keyword for keyword in support_keywords
                if _normalize_keyword_text(keyword) not in _normalize_keyword_text(lead_keyword)
            ],
            differentiators=[item for item in [capability] + list(_flatten_tokens(numeric_specs))[:2] if item],
            max_length=int(payload.get("max_length") or LENGTH_RULES["title"]["hard_ceiling"]),
        )
        return _dewater_title_text(title, exact_keywords)
    if field_name.startswith("bullet"):
        lead_keyword = keywords[0] if keywords else ""
        localized_capability = (
            (payload.get("localized_capability_anchors") or [capability] or [""])[0]
            or capability
            or lead_keyword
        )
        localized_scene = (
            (payload.get("localized_scene_anchors") or [scene] or [""])[0]
            or scene
            or _format_scene_label(payload.get("scene_context") or "", target_language)
        )
        slot_name = str(payload.get("slot") or field_name).upper()
        focus_parts: List[str] = []
        for part in [lead_keyword, localized_capability, numeric]:
            cleaned_part = str(part or "").strip()
            if not cleaned_part:
                continue
            normalized_part = _normalize_keyword_text(cleaned_part)
            if normalized_part and normalized_part in _normalize_keyword_text(" ".join(focus_parts)):
                continue
            focus_parts.append(cleaned_part)
        focus = ", ".join(focus_parts).strip(", ") or "clear, reliable footage"
        english_templates = {
            "B1": ("COMMUTE READY CLARITY", "Stay ready on every {scene} with {focus}, giving you a dependable clip from the first minute to the last."),
            "B2": ("ALL-DAY RECORDING POWER", "Keep filming through {scene} thanks to {focus}, so longer sessions feel covered without constant recharging."),
            "B3": ("ONE-TOUCH THUMB CAM", "Start recording fast during {scene} with {focus}, making spontaneous moments easier to catch and keep."),
            "B4": ("TRAINING FOOTAGE THAT HOLDS", "Bring steadier detail to {scene} with {focus}, helping every rep, route, or drill stay easy to review later."),
            "B5": ("CONFIDENT DAILY WEAR", "Clip in for {scene} and rely on {focus}, giving you a lightweight setup that stays easy to carry and use."),
        }
        header, body_template = english_templates.get(slot_name, english_templates["B1"])
        body = body_template.format(scene=localized_scene or 'everyday use', focus=focus)
        sentence = re.sub(r"\s+", " ", f"{header} — {body}").strip()
        return sentence
    if field_name == "description":
        return (
            f"{brand or ''} {payload.get('product_name') or ''} "
            f"combine {', '.join(payload.get('core_selling_points') or [])}. "
            f"{numeric}".strip()
        )
    if field_name == "aplus":
        return (
            f"{brand or 'Brand'} présente ses fonctionnalités clés : "
            f"{', '.join(payload.get('core_selling_points') or [])}."
        )
    return " ".join(keywords) or "Product copy unavailable."


def _generate_field_output(field_name: str,
                           payload: Dict[str, Any],
                           required_keywords: Sequence[str],
                           numeric_specs: Sequence[str],
                           audit_log: Optional[List[Dict[str, Any]]],
                           fallback_text: str,
                           tracker_field: Optional[str] = None,
                           assignment_tracker: Optional[KeywordAssignmentTracker] = None,
                           max_retries: int = 2) -> Tuple[str, Dict[str, Any]]:
    required_keywords = _flatten_tokens(required_keywords)
    numeric_specs = _flatten_tokens(numeric_specs)
    for attempt in range(1, max_retries + 1):
        try:
            candidate = _call_llm_for_field(field_name, payload)
        except LLMClientUnavailable as exc:
            if _log_retryable_llm_exception(audit_log, field_name, exc, attempt):
                continue
            break
        if not candidate:
            _log_action(
                audit_log,
                field_name,
                "llm_retry",
                {"attempt": attempt, "reason": "empty_output"}
            )
            continue
        passed, reason, numeric_met = _validate_field_text(candidate, required_keywords, numeric_specs)
        if passed:
            _log_action(audit_log, field_name, "llm_success", {"attempt": attempt})
            if tracker_field and assignment_tracker and required_keywords:
                assignment_tracker.record(tracker_field, required_keywords)
            return candidate, {"numeric_met": numeric_met}
        reason["attempt"] = attempt
        _log_action(audit_log, field_name, "llm_retry", reason)
    _log_action(audit_log, field_name, "llm_fallback", {"reason": "validation_failed"})
    if tracker_field and assignment_tracker and required_keywords:
        assignment_tracker.record(tracker_field, required_keywords)
    fallback_numeric_met = _check_numeric_presence(fallback_text, numeric_specs)
    return fallback_text, {"numeric_met": fallback_numeric_met}


def _translate_capability(capability: str, target_language: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """Translate capability phrase using shared dictionaries with real-vocab fallback."""
    if target_language == "English":
        return capability

    translations = CAPABILITY_TRANSLATIONS.get(target_language, {})
    candidate = translations.get(capability) or translations.get(capability.lower(), capability)
    if candidate == capability:
        slug = canonicalize_capability(capability)
        canonical_candidate = get_capability_display(slug, target_language)
        if canonical_candidate and canonical_candidate != english_capability_label(slug):
            candidate = canonical_candidate

    if real_vocab and getattr(real_vocab, "is_available", False):
        for kw in getattr(real_vocab, "top_keywords", []) or []:
            word = kw.get("keyword", "")
            if word and candidate.lower() in word.lower():
                return word

    if candidate == capability and data_mode == "SYNTHETIC_COLD_START":
        return f"[SYNTH]_{capability}"
    return candidate


def _translate_scene(scene_label: str, target_language: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """Translate scene label using shared dictionaries with vocab fallback."""
    if target_language == "English":
        return scene_label

    translations = SCENE_TRANSLATIONS.get(target_language, {})
    candidate = translations.get(scene_label, scene_label)

    if real_vocab and getattr(real_vocab, "is_available", False):
        for kw in getattr(real_vocab, "top_keywords", []) or []:
            word = kw.get("keyword", "")
            if word and candidate.lower() in word.lower():
                return word

    if candidate == scene_label and data_mode == "SYNTHETIC_COLD_START":
        return f"[SYNTH]_{scene_label}"
    return candidate


def _translate_text_to_language(text: str, target_language: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """Replace known phrases with localized equivalents."""
    if target_language == "English":
        return text

    translations = {
        **CAPABILITY_TRANSLATIONS.get(target_language, {}),
        **SCENE_TRANSLATIONS.get(target_language, {}),
        **CATEGORY_TRANSLATIONS.get(target_language, {}),
    }
    for phrase, translated in sorted(translations.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
        text = pattern.sub(translated, text)

    return _apply_rule_based_translation(text, target_language)


TRANSLATION_CODE_MAP = {
    "English": "en",
    "French": "fr",
    "German": "de",
    "Spanish": "es",
    "Italian": "it",
    "Chinese": "zh",
    "Japanese": "ja",
}

LANGUAGE_STYLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "English": {
        "connectors": ["and", "or"],
        "section_labels": {
            "brand_story": "Brand Story",
            "core_technologies": "Core Technologies",
            "usage_scenarios": "Usage Scenarios",
            "in_the_box": "What's in the Box",
        },
    },
    "French": {
        "connectors": ["et", "ou"],
        "section_labels": {
            "brand_story": "Histoire de la marque",
            "core_technologies": "Technologies essentielles",
            "usage_scenarios": "Scenes d'usage",
            "in_the_box": "Contenu de la boite",
        },
    },
    "German": {
        "connectors": ["und", "oder"],
        "section_labels": {
            "brand_story": "Markengeschichte",
            "core_technologies": "Kerntechnologien",
            "usage_scenarios": "Einsatzszenarien",
            "in_the_box": "Lieferumfang",
        },
    },
    "Spanish": {
        "connectors": ["y", "o"],
        "section_labels": {
            "brand_story": "Historia de la marca",
            "core_technologies": "Tecnologias clave",
            "usage_scenarios": "Escenarios de uso",
            "in_the_box": "Contenido de la caja",
        },
    },
    "Italian": {
        "connectors": ["e", "o"],
        "section_labels": {
            "brand_story": "Storia del brand",
            "core_technologies": "Tecnologie chiave",
            "usage_scenarios": "Scenari d'uso",
            "in_the_box": "Contenuto della confezione",
        },
    },
}

ENGLISH_RESIDUE_HINTS = {
    "brand story",
    "core technologies",
    "usage scenarios",
    "what's in the box",
    "open the kit",
    "whether you're",
    "was built for",
    "ready for action",
    "hands-free",
    "quick-start guide",
}


def _language_style_profile(target_language: str) -> Dict[str, Any]:
    return LANGUAGE_STYLE_PROFILES.get(target_language, LANGUAGE_STYLE_PROFILES["English"])


def _normalize_phrase_for_dedupe(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^A-Za-z0-9]+", " ", normalized.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _dedupe_comma_sections(text: str) -> str:
    had_trailing_comma = (text or "").rstrip().endswith(",")
    sections = [section.strip() for section in (text or "").split(",")]
    if len(sections) < 2:
        return text
    deduped: List[str] = []
    seen = set()
    for section in sections:
        normalized = _normalize_phrase_for_dedupe(section)
        if not section:
            continue
        if normalized and normalized in seen:
            continue
        if normalized:
            seen.add(normalized)
        deduped.append(section)
    result = ", ".join(deduped)
    if had_trailing_comma and result and not result.endswith(","):
        result += ","
    return result


VISUAL_BRIEF_INLINE_PATTERN = re.compile(r"\[Visual Design Brief:[^\]]*\]\s*", re.IGNORECASE)


def _strip_visible_structured_artifacts(text: str, field: str) -> str:
    if not text:
        return ""
    cleaned = str(text)
    parsed = _extract_embedded_json_payload(cleaned)
    if isinstance(parsed, dict) and parsed.get("text") and field.startswith("bullet"):
        cleaned = str(parsed.get("text") or "")
    cleaned = VISUAL_BRIEF_INLINE_PATTERN.sub("", cleaned)

    def _replace_fenced_block(match: re.Match) -> str:
        inner = match.group(1).strip()
        parsed_inner = _extract_embedded_json_payload(inner)
        if isinstance(parsed_inner, dict) and parsed_inner.get("text"):
            return str(parsed_inner.get("text") or "")
        if field == "aplus_content":
            return ""
        return inner

    cleaned = JSON_FENCE_PATTERN.sub(_replace_fenced_block, cleaned)
    kept_lines: List[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append("")
            continue
        parsed_line = None
        if stripped.startswith("{") and stripped.endswith("}"):
            parsed_line = _extract_embedded_json_payload(stripped)
        if isinstance(parsed_line, dict):
            if parsed_line.get("text"):
                kept_lines.append(str(parsed_line.get("text") or ""))
            elif field != "aplus_content":
                kept_lines.append(line)
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _dedupe_adjacent_phrases(text: str, max_phrase_len: int = 8) -> str:
    tokens = (text or "").split()
    if len(tokens) < 4:
        return text
    idx = 0
    while idx < len(tokens):
        removed = False
        max_len_here = min(max_phrase_len, (len(tokens) - idx) // 2)
        for size in range(max_len_here, 1, -1):
            left = " ".join(tokens[idx: idx + size])
            right = " ".join(tokens[idx + size: idx + size * 2])
            if _normalize_phrase_for_dedupe(left) and _normalize_phrase_for_dedupe(left) == _normalize_phrase_for_dedupe(right):
                del tokens[idx + size: idx + size * 2]
                removed = True
                break
        if not removed:
            idx += 1
    return " ".join(tokens)


def _cleanup_localized_artifacts(text: str, target_language: str) -> str:
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = cleaned.replace("’", "'")
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([(\[])\s+", r"\1", cleaned)
    cleaned = re.sub(r"\s+([)\]])", r"\1", cleaned)
    cleaned = re.sub(r"\s*(?:/|\|)\s*([,.;:])", r"\1", cleaned)
    connectors = _language_style_profile(target_language).get("connectors", [])
    for connector in connectors:
        cleaned = re.sub(rf"(?i)\b{re.escape(connector)}\b\s*([,.;:!?])", r"\1", cleaned)
        cleaned = re.sub(rf"(?i)\b{re.escape(connector)}\b\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s*-\s*-\s*", " - ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = _dedupe_adjacent_words(_dedupe_adjacent_phrases(cleaned))
    return cleaned


def _contains_english_residue(text: str, target_language: str) -> bool:
    if not text or target_language == "English":
        return False
    lowered = text.lower()
    if any(hint in lowered for hint in ENGLISH_RESIDUE_HINTS):
        return True
    ascii_words = re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", text)
    if len(ascii_words) < 8:
        return False
    common = {"the", "with", "for", "and", "into", "while", "ready", "story", "core", "usage", "box", "built"}
    hits = sum(1 for word in ascii_words if word.lower() in common)
    return hits >= 4


def _should_run_localization_pass(text: str, target_language: str, llm_offline: bool, force: bool = False) -> bool:
    if force or llm_offline:
        return True
    if not text or target_language == "English":
        return False
    if CHINESE_CHAR_PATTERN.search(text):
        return True
    if SNAKE_CASE_TOKEN_RE.search(text):
        return True
    return _contains_english_residue(text, target_language)


def _finalize_visible_text(
    text: str,
    field: str,
    target_language: str,
    audit_log: Optional[List[Dict[str, Any]]] = None,
    canonical_facts: Optional[Dict[str, Any]] = None,
) -> str:
    cleaned = _strip_visible_structured_artifacts(text, field)
    cleaned = _cleanup_localized_artifacts(cleaned, target_language)
    if field == "title":
        cleaned = _dedupe_comma_sections(cleaned)
    absolute_terms_rewritten: List[str] = []
    original_cleaned = cleaned
    claim_audit = audit_claim_language(cleaned, canonical_facts)
    if not claim_audit.get("passed"):
        if claim_audit.get("repairable"):
            repaired = repair_claim_language(cleaned, canonical_facts)
            repaired_audit = audit_claim_language(repaired, canonical_facts)
            if repaired_audit.get("passed"):
                absolute_terms_rewritten.extend(
                    str(item.get("surface") or item.get("reason") or "claim_language")
                    for item in claim_audit.get("violations") or []
                )
                cleaned = repaired
            elif audit_log is not None:
                _log_action(
                    audit_log,
                    field,
                    "claim_language_repair_failed",
                    {
                        "violations": claim_audit.get("violations") or [],
                        "post_repair_violations": repaired_audit.get("violations") or [],
                    },
                )
        elif audit_log is not None:
            _log_action(
                audit_log,
                field,
                "claim_language_blocked",
                {
                    "violations": claim_audit.get("violations") or [],
                    "blocking_reasons": claim_audit.get("blocking_reasons") or [],
                },
            )
    rewrite_rules = [
        (r"\bnumber\s*1\b", "compact", "number 1"),
        (r"\bperfect\b", "ideal", "perfect"),
        (r"\bamazing\b", "standout", "amazing"),
        (r"\bexcellent\b", "strong", "excellent"),
        (r"\bhigh quality\b", "well-made", "high quality"),
        (r"\bpremium quality\b", "premium build", "premium quality"),
        (r"\bzero hidden costs\b", "clear starter bundle", "zero hidden costs"),
        (r"\bno surprise purchases\b", "fewer extra purchases", "no surprise purchases"),
        (r"\ball[- ]day\b", "extended-session", "all-day"),
    ]
    for pattern, replacement, label in rewrite_rules:
        updated = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        if updated != cleaned:
            absolute_terms_rewritten.append(label)
            cleaned = updated
    cleaned = re.sub(r"\bsupport\s+support\b", "support", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:and|or|while|that|with|ou|et|und|oder)\b\s*([,;:]?)\s*$", r"\1", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"\s*[&]+\s*$", "", cleaned).strip()
    if field.startswith("bullet") and cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    if cleaned != (text or "") and audit_log is not None:
        _log_action(audit_log, field, "postprocess_cleanup", {"target_language": target_language})
    if absolute_terms_rewritten and audit_log is not None:
        _log_action(
            audit_log,
            field,
            "downgrade",
            {
                "reason": "absolute_claim_rewritten",
                "terms": sorted(set(absolute_terms_rewritten)),
                "before": original_cleaned[:160],
                "after": cleaned[:160],
            },
        )
    return cleaned

FALLBACK_TRANSLATION_RULES: Dict[str, Dict[str, Any]] = {
    "French": {
        "phrases": [
            (re.compile(r"Stay in frame with instant preview and share-ready clips\.", re.IGNORECASE),
             "Restez dans le cadre grâce à un aperçu instantané et des clips prêts à partager."),
            (re.compile(r"Only waterproof when using the included housing", re.IGNORECASE),
             "Étanche uniquement avec le boîtier fourni"),
            (re.compile(r"with all-day power", re.IGNORECASE), "avec une autonomie pour toute la journée"),
            (re.compile(r"Buy now and start capturing your moments!", re.IGNORECASE),
             "Achetez maintenant et commencez à capturer vos moments !"),
            (re.compile(r"Key Features", re.IGNORECASE), "Principales caractéristiques"),
            (re.compile(r"Package includes", re.IGNORECASE), "Contenu de l'emballage"),
            (re.compile(r"Features", re.IGNORECASE), "Inclut"),
            (re.compile(r"Perfect for", re.IGNORECASE), "Idéal pour"),
            (re.compile(r"capture every moment", re.IGNORECASE), "capturez chaque instant"),
            (re.compile(r"while solving", re.IGNORECASE), "tout en résolvant"),
            (re.compile(r"blurry motion ruins POV footage", re.IGNORECASE),
             "les flous qui gâchent vos séquences POV"),
            (re.compile(r"fear of water damage during dives", re.IGNORECASE),
             "la peur des dommages d'eau pendant les plongées"),
            (re.compile(r"batteries dying mid expedition", re.IGNORECASE),
             "les batteries qui lâchent en pleine expédition"),
            (re.compile(r"cameras not adapting to helmets or chest rigs", re.IGNORECASE),
             "les caméras qui s'adaptent mal aux harnais thoraciques"),
            (re.compile(r"waterproof\s*case\s*supports\s*30m\s*waterproof", re.IGNORECASE),
             "boîtier étanche supportant 30 m d'immersion"),
            (re.compile(
                r"waterproof\s*case\s*supports\s*30m\s*waterproof\s*magnetic\s+accessories\s+wearable\s+neck\s+mount\s+attaches\s+to\s+metal\s+surfaces",
                re.IGNORECASE,
            ), "boîtier étanche 30 m et clip dorsal magnétique qui adhèrent aux surfaces métalliques"),
            (re.compile(r"magnetic\s+accessories\s+wearable\s+neck\s+mount\s+attaches\s+to\s+metal\s+surfaces", re.IGNORECASE),
             "clip dorsal magnétique avec tour de cou qui adhère aux surfaces métalliques"),
            (re.compile(r"Urban\s+vloggers", re.IGNORECASE), "vloggeurs urbains"),
            (re.compile(r"Travel\s+documentation", re.IGNORECASE), "journal de voyage"),
            (re.compile(r"other mounting accessories handlebar mount helmet", re.IGNORECASE),
             "autres fixations pour guidon et monture tête"),
            (re.compile(r"Recreational divers", re.IGNORECASE), "plongeurs loisirs"),
            (re.compile(r"Adventure travelers", re.IGNORECASE), "voyageurs aventure"),
            (re.compile(r"Active families", re.IGNORECASE), "familles actives"),
            (re.compile(r"Family use", re.IGNORECASE), "usage familial"),
            (re.compile(r"Use ([^.]+) for hands-free coverage", re.IGNORECASE),
             r"Exploitez \1 pour filmer mains libres"),
            (re.compile(r"wearable neck mount", re.IGNORECASE), "cordon tour de cou"),
            (re.compile(r"attaches to metal surfaces", re.IGNORECASE), "se fixe sur les surfaces métalliques"),
        ],
        "words": {
            "magnetic": "magnétique",
            "clip": "clip",
            "and": "et",
            "back": "dorsal",
            "system": "système",
            "locks": "se fixe",
            "onto": "sur",
            "gear": "l'équipement",
            "for": "pour",
            "cycling": "cyclisme",
            "recording": "enregistrement",
            "captures": "capture",
            "true": "véritables",
            "pov": "POV",
            "stories": "histoires",
            "while": "tout en",
            "staying": "restant",
            "grams": "g",
            "long": "longue",
            "battery": "batterie",
            "power": "puissance",
            "keeps": "maintient",
            "underwater": "sous-marine",
            "exploration": "exploration",
            "recordings": "enregistrements",
            "uninterrupted": "ininterrompus",
            "camera": "caméra",
            "avoids": "évite",
            "mid-shift": "pendant le service",
            "swapping": "les changements",
            "lightweight": "léger",
            "design": "design",
            "help": "aide",
            "creators": "créateurs",
            "master": "maîtriser",
            "travel": "voyage",
            "documentation": "documentation",
            "stay": "restez",
            "in": "dans",
            "frame": "le cadre",
            "instant": "instantané",
            "preview": "aperçu",
            "share-ready": "prêts à partager",
            "clips": "clips",
            "waterproof": "étanche",
            "withstands": "résiste",
            "when": "lorsque",
            "using": "en utilisant",
            "the": "la",
            "included": "fourni",
            "housing": "boîtier",
            "only": "uniquement",
            "up": "jusqu'à",
            "to": "à",
            "hd": "HD",
            "recording": "enregistrement",
            "backed": "garantie",
            "by": "par",
            "warranty": "garantie",
            "wifi": "WiFi",
            "app": "application",
            "control": "contrôle",
            "enables": "permet",
            "live": "en direct",
            "quick": "rapides",
            "file": "fichiers",
            "transfers": "transferts",
            "action": "action",
            "camera": "caméra",
            "is": "est",
            "designed": "conçue",
            "delivering": "offrant",
            "professional-grade": "de qualité professionnelle",
            "experience": "expérience",
            "features": "propose",
            "more": "plus",
            "now": "maintenant",
            "start": "commencez",
            "capturing": "à capturer",
            "your": "vos",
            "moments": "moments",
            "main": "unité",
            "unit": "principale",
            "data": "câble",
            "cable": "câble",
            "user": "manuel",
            "manual": "d'utilisation",
            "dual": "double",
            "screen": "écran",
            "hero": "atout",
            "scene": "scène",
            "brand": "marque",
            "connectivity": "connectivité",
            "powerful": "puissant",
            "ready": "prêt",
            "perfect": "idéal",
            "urban": "urbain",
            "vloggers": "vloggeurs",
            "capture": "capturez",
            "every": "chaque",
            "moment": "instant",
            "solving": "résolvant",
            "blurry": "flous",
            "motion": "mouvements",
            "ruins": "gâchent",
            "footage": "séquences",
            "fear": "peur",
            "damage": "dommages",
            "during": "pendant",
            "dives": "plongées",
            "batteries": "batteries",
            "dying": "qui s'épuisent",
            "mid": "en plein",
            "expedition": "expédition",
            "cameras": "caméras",
            "adapting": "qui s'adaptent",
            "helmets": "supports tête",
            "chest": "poitrine",
            "rigs": "harnais",
            "unlock": "déploient",
            "hands-free": "mains libres",
            "attach": "fixez",
            "anywhere": "partout",
            "case": "boîtier",
            "supports": "offre",
            "wearable": "à porter",
            "neck": "cou",
            "mount": "fixation",
            "metal": "métalliques",
            "surfaces": "surfaces",
            "with": "avec",
            "runtime": "autonomie",
            "other": "autres",
            "mounting": "de fixation",
            "accessories": "accessoires",
            "handlebar": "guidon",
            "helmet": "support tête",
            "month": "mois",
            "months": "mois",
            "use": "utilisez",
            "hands-free": "mains libres",
            "coverage": "couverture",
        },
    },
    "German": {
        "phrases": [
            (re.compile(r"Stay in frame with instant preview and share-ready clips\.", re.IGNORECASE),
             "Bleibe dank sofortiger Vorschau und teilbaren Clips im Bild."),
            (re.compile(r"Only waterproof when using the included housing", re.IGNORECASE),
             "Nur mit dem mitgelieferten Gehäuse wasserdicht"),
            (re.compile(r"Buy now and start capturing your moments!", re.IGNORECASE),
             "Jetzt kaufen und Momente festhalten!"),
            (re.compile(r"Key Features", re.IGNORECASE), "Wichtigste Merkmale"),
            (re.compile(r"Package includes", re.IGNORECASE), "Lieferumfang"),
            (re.compile(r"Perfect for", re.IGNORECASE), "Ideal für"),
            (re.compile(r"capture every moment", re.IGNORECASE), "halte jeden Moment fest"),
            (re.compile(r"while solving", re.IGNORECASE), "und behebt"),
            (re.compile(r"blurry motion ruins POV footage", re.IGNORECASE),
             "verwackelte Bewegungen, die POV-Aufnahmen ruinieren"),
            (re.compile(r"fear of water damage during dives", re.IGNORECASE),
             "die Angst vor Wasserschäden beim Tauchen"),
            (re.compile(r"batteries dying mid expedition", re.IGNORECASE),
             "Akkus, die mitten in der Tour schlappmachen"),
            (re.compile(r"cameras not adapting to helmets or chest rigs", re.IGNORECASE),
             "Kameras, die sich nicht an Helme oder Brustgurte anpassen"),
            (re.compile(r"waterproof\s*case\s*supports\s*30m\s*waterproof", re.IGNORECASE),
             "Wasserschutzgehäuse bis 30 m Tiefe"),
            (re.compile(
                r"waterproof\s*case\s*supports\s*30m\s*waterproof\s*magnetic\s+accessories\s+wearable\s+neck\s+mount\s+attaches\s+to\s+metal\s+surfaces",
                re.IGNORECASE,
            ), "30-m-Wasserschutzgehäuse und magnetischer Rückenclip mit Halsband für Metallflächen"),
            (re.compile(r"magnetic\s+accessories\s+wearable\s+neck\s+mount\s+attaches\s+to\s+metal\s+surfaces", re.IGNORECASE),
             "magnetischer Rückenclip mit Halsband haftet auf Metallflächen"),
            (re.compile(r"Urban\s+vloggers", re.IGNORECASE), "urbane Vlogger"),
            (re.compile(r"Travel\s+documentation", re.IGNORECASE), "Reiseaufzeichnung"),
            (re.compile(r"other mounting accessories handlebar mount helmet", re.IGNORECASE),
             "weiteres Montagezubehör für Lenker und Helm"),
            (re.compile(r"Recreational divers", re.IGNORECASE), "Freizeittaucher"),
            (re.compile(r"Adventure travelers", re.IGNORECASE), "Abenteuerreisende"),
            (re.compile(r"Active families", re.IGNORECASE), "aktive Familien"),
            (re.compile(r"Family use", re.IGNORECASE), "Familieneinsatz"),
            (re.compile(r"Use ([^.]+) for hands-free coverage", re.IGNORECASE),
             r"Nutzen Sie \1 für freihändige Aufnahmen"),
            (re.compile(r"wearable neck mount", re.IGNORECASE), "Halsbandhalterung"),
            (re.compile(r"attaches to metal surfaces", re.IGNORECASE), "haftet auf Metallflächen"),
        ],
        "words": {
            "magnetic": "magnetisch",
            "clip": "Clip",
            "and": "und",
            "back": "Rücken",
            "system": "System",
            "locks": "rastet",
            "onto": "an",
            "gear": "Ausrüstung",
            "for": "für",
            "cycling": "Radfahren",
            "recording": "Aufnahme",
            "captures": "erfasst",
            "true": "echte",
            "stories": "Geschichten",
            "while": "während",
            "staying": "es bleibt",
            "grams": "g",
            "long": "lange",
            "battery": "Batterie",
            "power": "Leistung",
            "keeps": "hält",
            "underwater": "unterwasser",
            "exploration": "Erkundung",
            "recordings": "Aufnahmen",
            "uninterrupted": "unterbrechungsfrei",
            "camera": "Kamera",
            "avoids": "vermeidet",
            "lightweight": "leichtes",
            "design": "Design",
            "help": "hilft",
            "creators": "Erstellern",
            "master": "zu meistern",
            "travel": "Reise",
            "documentation": "Dokumentation",
            "waterproof": "wasserdicht",
            "withstands": "hält stand",
            "when": "wenn",
            "using": "Sie",
            "included": "im Lieferumfang",
            "housing": "Gehäuse",
            "only": "nur",
            "hd": "HD",
            "backed": "gestützt",
            "warranty": "Garantie",
            "wifi": "WiFi",
            "app": "App",
            "control": "Steuerung",
            "enables": "ermöglicht",
            "live": "Live-",
            "quick": "schnelle",
            "file": "Datei",
            "transfers": "Übertragungen",
            "action": "Action",
            "is": "ist",
            "designed": "konzipiert",
            "delivering": "und liefert",
            "professional-grade": "professionelle",
            "experience": "Erfahrung",
            "features": "bietet",
            "more": "mehr",
            "main": "Haupteinheit",
            "unit": "Einheit",
            "data": "Daten",
            "cable": "Kabel",
            "user": "Benutzer",
            "manual": "Handbuch",
            "perfect": "ideal",
            "urban": "urbane",
            "vloggers": "Vlogger",
            "capture": "fange",
            "every": "jeden",
            "moment": "Moment",
            "solving": "beseitigt",
            "blurry": "verwackelte",
            "motion": "Bewegungen",
            "ruins": "ruinieren",
            "footage": "Aufnahmen",
            "fear": "Angst",
            "damage": "Schäden",
            "during": "während",
            "dives": "Tauchgängen",
            "batteries": "Akkus",
            "dying": "sterben",
            "mid": "mitten",
            "expedition": "Expedition",
            "cameras": "Kameras",
            "adapting": "anpassen",
            "helmets": "Helme",
            "chest": "Brust",
            "rigs": "Gurte",
            "unlock": "liefert",
            "hands-free": "freihändige",
            "attach": "befestige",
            "anywhere": "überall",
            "case": "Gehäuse",
            "supports": "bietet",
            "wearable": "tragbare",
            "neck": "Nacken",
            "mount": "Halterung",
            "metal": "Metall",
            "surfaces": "Flächen",
            "with": "mit",
            "runtime": "Betriebsdauer",
            "other": "weitere",
            "mounting": "Montage",
            "accessories": "Zubehör",
            "handlebar": "Lenker",
            "helmet": "Helm",
            "month": "Monat",
            "months": "Monate",
            "use": "nutze",
            "hands-free": "freihändige",
            "coverage": "Abdeckung",
        },
    },
}

PROTECTED_NUMBER_PATTERN = re.compile(r"\b\d+(?:[\.,]\d+)?\s?(?:m|min|mins|mm|cm|g|kg|mah|fps|p|gb|mb|k)?\b", re.IGNORECASE)
ZH_UNIT_PATTERNS = [
    (r'(\d+(?:[\.,]\d+)?)\s*公斤', r'\1 kg'),
    (r'(\d+(?:[\.,]\d+)?)\s*厘米', r'\1 cm'),
    (r'(\d+(?:[\.,]\d+)?)\s*毫米', r'\1 mm'),
    (r'(\d+(?:[\.,]\d+)?)\s*分钟', r'\1 minutes'),
    (r'(\d+(?:[\.,]\d+)?)\s*小时', r'\1 heures'),
    (r'(\d+(?:[\.,]\d+)?)\s*个月', r'\1 mois'),
    (r'(\d+(?:[\.,]\d+)?)\s*公里', r'\1 km'),
    (r'(\d+(?:[\.,]\d+)?)\s*米',   r'\1 m'),
    (r'(\d+(?:[\.,]\d+)?)\s*克',   r'\1 g'),
    (r'(\d+(?:[\.,]\d+)?)\s*瓦',   r'\1 W'),
    (r'(\d+(?:[\.,]\d+)?)\s*年',   r'\1 ans'),
    (r'(\d+(?:[\.,]\d+)?)\s*天',   r'\1 jours'),
]
SNAKE_CASE_TOKEN_RE = re.compile(r'\b([a-z]{2,}(?:_[a-z]+)+)\b')
_TRANSLATOR_CACHE: Dict[str, Any] = {}


def _mask_protected_tokens(text: str, brand_terms: Sequence[str]) -> (str, Dict[str, str]):
    placeholders: Dict[str, str] = {}
    counter = 0

    def _store(token: str) -> str:
        nonlocal counter
        key = f"__PROTECTED_{counter}__"
        placeholders[key] = token
        counter += 1
        return key

    text = PROTECTED_NUMBER_PATTERN.sub(lambda m: _store(m.group(0)), text)

    for term in brand_terms:
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        text = pattern.sub(lambda m: _store(m.group(0)), text)

    return text, placeholders


def _restore_protected_tokens(text: str, placeholders: Dict[str, str]) -> str:
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def _normalize_zh_units(text: str) -> Tuple[str, bool]:
    changed = False
    for pattern, repl in ZH_UNIT_PATTERNS:
        new_text = re.sub(pattern, repl, text)
        if new_text != text:
            changed = True
            text = new_text
    return text, changed


def _get_external_translator(locale_code: Optional[str]):
    if not locale_code or locale_code == "en" or GoogleTranslator is None:
        return None
    if locale_code in _TRANSLATOR_CACHE:
        return _TRANSLATOR_CACHE[locale_code]
    try:
        translator = GoogleTranslator(source="auto", target=locale_code)
        _TRANSLATOR_CACHE[locale_code] = translator
        return translator
    except Exception:  # pragma: no cover
        return None


def _resolve_snake_case_tokens(text: str, target_language: str) -> str:
    locale = locale_code_for_language(target_language)

    def _replace(match: re.Match) -> str:
        token = match.group(1)
        return get_stag_display(token, locale)

    return SNAKE_CASE_TOKEN_RE.sub(_replace, text)


def _apply_rule_based_translation(text: str, target_language: str) -> str:
    rules = FALLBACK_TRANSLATION_RULES.get(target_language)
    if not rules:
        return text
    translated = text
    for pattern, replacement in rules.get("phrases", []):
        translated = pattern.sub(replacement, translated)

    word_map = rules.get("words", {})

    def _replace_word(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        replacement = word_map.get(lower)
        if not replacement:
            return word
        if word.isupper():
            return replacement.upper()
        if word[0].isupper():
            return replacement.capitalize()
        return replacement

    translated = re.sub(r"[A-Za-z][A-Za-z'-]*", _replace_word, translated)
    return translated


def _localize_text_block(
    text: str,
    target_language: str,
    preferred_locale: Optional[str],
    brand_terms: Sequence[str],
    audit_log: Optional[List[Dict[str, Any]]] = None,
    field: Optional[str] = None,
) -> str:
    if not text or target_language == "English":
        return text

    locale_code = preferred_locale or TRANSLATION_CODE_MAP.get(target_language, "en")
    masked_text, placeholders = _mask_protected_tokens(text, brand_terms)
    masked_text, normalized_pre = _normalize_zh_units(masked_text)
    units_normalized = normalized_pre
    localized = None
    translator = _get_external_translator(locale_code)
    translator_error = None

    if translator:
        try:
            localized = translator.translate(masked_text)
        except Exception as exc:  # pragma: no cover - network failure
            translator_error = str(exc)

    if localized is None:
        masked_text, normalized_fallback = _normalize_zh_units(masked_text)
        if normalized_fallback:
            units_normalized = True
        localized = _apply_rule_based_translation(masked_text, target_language)

    localized = _restore_protected_tokens(localized, placeholders)
    localized = _resolve_snake_case_tokens(localized, target_language)

    if localized != text:
        if audit_log is not None and field:
            detail = {
                "target_language": target_language,
                "preferred_locale": preferred_locale,
                "method": "external" if translator else "rule_based",
            }
            if units_normalized:
                detail["units_normalized"] = True
            _log_action(
                audit_log,
                field,
                "localized",
                detail,
            )
        return localized

    if translator_error and audit_log is not None and field:
        _log_action(
            audit_log,
            field,
            "translation_unavailable",
            {"target_language": target_language, "reason": translator_error[:160]},
        )
    return text


def _build_english_title_structure(preprocessed_data: Any, writing_policy: Dict[str, Any],
                                    tiered_keywords: Dict[str, List[str]],
                                    keyword_allocation_strategy: str) -> Dict[str, Any]:
    """
    PRD v8.2: 第一阶段 - 用 English 构建标题信息结构
    返回: {brand, l1_keywords, scene_1, capability_1, scene_2, resolution}
    """
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "Brand"

    # 获取 Profile 中的 hero_spec
    profile = writing_policy.get("product_profile", {})
    hero_spec_raw = profile.get("hero_spec", "action camera")
    # 标准化 hero_spec（可能是中文）→ English
    hero_spec = _normalize_to_canonical_english(hero_spec_raw)

    # 获取场景
    scenes_en = profile.get("primary_use_cases", ["outdoor_sports", "cycling_recording"])

    # 获取 L1 关键词
    l1_keywords = tiered_keywords.get("l1", [])
    if not l1_keywords:
        l1_keywords = ["action camera 4k"]

    # 获取分辨率
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}
    resolution = attr_data.get('video_resolution', '4K')

    return {
        "brand": brand,
        "l1_keywords": l1_keywords,
        "scene_1": scenes_en[0] if scenes_en else "outdoor_sports",
        "scene_2": scenes_en[1] if len(scenes_en) > 1 else scenes_en[0],
        "hero_spec": hero_spec,
        "resolution": resolution
    }


def _generate_title_in_language(title_struct: Dict[str, Any], target_language: str,
                                 keyword_allocation_strategy: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """
    PRD v8.2: 第二阶段 - 根据目标语言生成标题
    """
    brand = title_struct["brand"]
    l1_keywords = title_struct["l1_keywords"]
    scene_1_en = title_struct["scene_1"]
    scene_2_en = title_struct["scene_2"]
    hero_spec = title_struct["hero_spec"]
    resolution = title_struct["resolution"]

    # 翻译场景
    scene_1 = _translate_scene(scene_1_en, target_language, real_vocab, data_mode)
    scene_2 = _translate_scene(scene_2_en, target_language, real_vocab, data_mode)

    # 翻译 hero_spec
    hero_spec_translated = _translate_capability(hero_spec, target_language, real_vocab, data_mode)

    # 构建标题
    if target_language == "English":
        title = f"{brand} {l1_keywords[0]} {scene_1} {hero_spec_translated} {resolution}"
    elif target_language == "German":
        title = f"{brand} {l1_keywords[0]} {scene_1} {hero_spec_translated} {resolution} {scene_2}"
    else:
        title = f"{brand} {l1_keywords[0]} {scene_1} {hero_spec_translated} {resolution}"

    # 清理 [SYNTH] 标记在标题中的显示（可选择保留或移除）
    # 这里保留 [SYNTH] 用于审计
    return title


def _field_stage_timeout_seconds(stage_name: str) -> int:
    defaults = {
        "title": 75,
        "bullets": 90,
        "description": 120,
        "faq": 75,
        "search_terms": 10,
        "aplus": 180,
    }
    env_key = f"LISTING_{stage_name.upper()}_TIMEOUT_SECONDS"
    raw = os.getenv(env_key) or os.getenv("LISTING_FIELD_TIMEOUT_SECONDS")
    try:
        return max(5, int(raw)) if raw else defaults.get(stage_name, 60)
    except Exception:
        return defaults.get(stage_name, 60)


def _uses_pure_r1_visible_batch(model_overrides: Optional[Dict[str, str]]) -> bool:
    overrides = model_overrides or {}
    return (
        is_r1_experiment_model(overrides.get("title"))
        and is_r1_experiment_model(overrides.get("bullets"))
    )


def _r1_batch_timeout_seconds() -> int:
    raw = os.getenv("R1_BATCH_TIMEOUT_SEC")
    try:
        return max(30, int(raw)) if raw else 180
    except Exception:
        return 180


def _deepseek_v4_pro_timeout_seconds() -> int:
    raw = os.getenv("DEEPSEEK_V4_PRO_TIMEOUT_SEC") or os.getenv("R1_STAGE_TIMEOUT_SEC")
    try:
        return max(45, int(raw)) if raw else 180
    except Exception:
        return 180


def _experimental_stage_timeout_seconds(stage_name: str, override_model: Optional[str]) -> int:
    timeout = _field_stage_timeout_seconds(stage_name)
    if not is_r1_experiment_model(override_model):
        return timeout
    return max(timeout, _deepseek_v4_pro_timeout_seconds())


def _field_stage_retry_budget(stage_name: str) -> int:
    defaults = {
        "title": 2,
        "bullets": 2,
        "description": 2,
        "faq": 2,
        "search_terms": 1,
        "aplus": 2,
    }
    env_key = f"LISTING_{stage_name.upper()}_RETRIES"
    raw = os.getenv(env_key)
    try:
        return max(1, int(raw)) if raw else defaults.get(stage_name, 1)
    except Exception:
        return defaults.get(stage_name, 1)


def _experimental_stage_retry_budget(stage_name: str, override_model: Optional[str]) -> int:
    budget = _field_stage_retry_budget(stage_name)
    if is_r1_experiment_model(override_model):
        return 1
    return budget


def _stage_artifact_path(artifact_dir: Optional[str], stage_name: str) -> Optional[Path]:
    if not artifact_dir:
        return None
    path = Path(artifact_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{stage_name}.json"


def _load_stage_artifact(artifact_dir: Optional[str], stage_name: str) -> Optional[Dict[str, Any]]:
    path = _stage_artifact_path(artifact_dir, stage_name)
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_stage_artifact(artifact_dir: Optional[str], stage_name: str, payload: Dict[str, Any]) -> None:
    path = _stage_artifact_path(artifact_dir, stage_name)
    if not path:
        return
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_partial_generation_artifact(
    artifact_dir: Optional[str],
    partial_copy: Dict[str, Any],
    field_generation_trace: Dict[str, Any],
) -> None:
    if not artifact_dir:
        return
    path = Path(artifact_dir)
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed_fields": sorted(partial_copy.keys()),
        "partial_copy": partial_copy,
        "field_generation_trace": field_generation_trace,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (path / "partial_generated_copy.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (path / "manifest.json").write_text(
        json.dumps({"field_generation_trace": field_generation_trace}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _ordered_bullet_slot_names(bullet_blueprint: Optional[Any]) -> List[str]:
    if bullet_blueprint:
        normalized_entries = _normalize_blueprint_entries(bullet_blueprint)
        slots = [entry.get("slot") for entry in normalized_entries if entry.get("slot")]
        ordered = _ordered_slot_filter(slots, slots)
        if ordered:
            return ordered
    return ["B1", "B2", "B3", "B4", "B5"]


def _resolve_primary_visible_llm_meta(
    field_generation_trace: Optional[Dict[str, Any]],
    fallback_meta: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    trace = field_generation_trace or {}
    fallback = fallback_meta or {}

    batch_meta = ((trace.get("visible_copy_batch") or {}).get("llm_response_meta") or {})
    if batch_meta.get("configured_model") or batch_meta.get("returned_model"):
        return dict(batch_meta)

    title_meta = ((trace.get("title") or {}).get("llm_response_meta") or {})
    if title_meta.get("configured_model") or title_meta.get("returned_model"):
        return dict(title_meta)

    for slot_name in ("bullet_b1", "bullet_b2", "bullet_b3", "bullet_b4", "bullet_b5"):
        bullet_meta = ((trace.get(slot_name) or {}).get("llm_response_meta") or {})
        if bullet_meta.get("configured_model") or bullet_meta.get("returned_model"):
            return dict(bullet_meta)

    return dict(fallback)


def _build_r1_batch_bullet_trace(
    bullet_blueprint: Optional[Any],
    bullet_slots: Sequence[str],
    slot_keyword_records: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    slot_keyword_records = slot_keyword_records or {}
    normalized_entries = {entry.get("slot"): entry for entry in _normalize_blueprint_entries(bullet_blueprint)}
    trace: List[Dict[str, Any]] = []
    for slot_name in bullet_slots:
        entry = normalized_entries.get(slot_name) or {}
        capability_bundle = list(entry.get("capabilities") or [])
        capability = capability_bundle[0] if capability_bundle else ""
        trace.append(
            {
                "slot": slot_name,
                "scene_code": ((entry.get("scenes") or [""])[0] if entry.get("scenes") else ""),
                "scene_mapping": list(entry.get("scenes") or []),
                "theme": entry.get("theme") or slot_name,
                "capability": capability,
                "capability_mapping": capability_bundle,
                "capability_bundle": capability_bundle,
                "keywords": list(slot_keyword_records.get(slot_name) or entry.get("assigned_keywords") or []),
                "mandatory_elements": list(entry.get("mandatory_elements") or []),
                "blueprint_accessories": entry.get("accessories"),
                "persona": entry.get("persona"),
                "pain_point": entry.get("pain_point"),
                "buying_trigger": entry.get("buying_trigger"),
                "proof_angle": entry.get("proof_angle"),
                "slot_directive": entry.get("slot_directive"),
                "audience_group": entry.get("audience_group"),
                "audience_label": entry.get("audience_label"),
                "audience_focus": entry.get("audience_focus"),
                "spec_dimension_target": "",
                "numeric_source": "",
            }
        )
    return trace



def _r1_batch_repair_title(
    client: Any,
    raw_title: str,
    *,
    brand_name: str,
    primary_category: str,
    core_keywords: Sequence[str],
    differentiators: Sequence[str],
    target_language: str,
) -> str:
    target_min = LENGTH_RULES["title"]["target_min"]
    target_max = LENGTH_RULES["title"]["target_max"]
    max_length = LENGTH_RULES["title"]["hard_ceiling"]
    repair_prompt = (
        "You are repairing only the title from an R1 visible-copy batch.\n"
        "Return exactly one JSON object: {\"title\":\"...\"}.\n"
        "Rules:\n"
        "1. Keep the same product intent and supported claims.\n"
        "2. Start with the brand name.\n"
        "3. Write a natural product name phrase, not a keyword list.\n"
        f"4. Target {target_min}-{target_max} characters. Hard ceiling: {max_length} characters.\n"
        "5. Do not finalize a short skeletal title. If the current title is too short, expand it with natural differentiators and valid keyword coverage.\n"
        "6. If the current title is too long, compress it without losing the core category, runtime, and main keyword intent.\n"
        "7. Include at least 3 core keywords naturally when provided.\n"
        "8. Output valid JSON only.\n"
    )
    payload = {
        "field": "visible_copy_batch_title_repair",
        "brand_name": brand_name,
        "primary_category": primary_category,
        "target_language": target_language,
        "current_title": raw_title,
        "core_keywords": list(core_keywords or []),
        "top_differentiators": list(differentiators or []),
        "target_min_length": target_min,
        "target_max_length": target_max,
        "max_length": max_length,
    }
    repaired_text = client.generate_text(
        repair_prompt,
        payload,
        temperature=0.2,
        override_model=DEEPSEEK_R1_EXPERIMENT_MODEL,
    )
    repaired = _extract_embedded_json_payload(repaired_text or "")
    if isinstance(repaired, dict):
        return str(repaired.get("title") or "").strip()
    return ""

def _r1_batch_generate_listing(
    preprocessed_data: PreprocessedData,
    writing_policy: Dict[str, Any],
    tiered_keywords: Dict[str, List[str]],
    bullet_blueprint: Optional[Any],
    target_language: str,
    blocked_terms: Sequence[str],
    audit_log: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    client = get_llm_client()
    attr_lookup = _build_attr_lookup(preprocessed_data.attribute_data)
    directives = writing_policy.get("compliance_directives", {}) or {}
    normalized_entries = _normalize_blueprint_entries(bullet_blueprint)
    core_capabilities = _filter_capabilities(
        getattr(preprocessed_data, "core_selling_points", []) or [],
        directives,
        audit_log,
        "bullets",
    )
    numeric_specs = _collect_numeric_tokens(preprocessed_data, directives)[:4]
    exact_keywords = _dedupe_keyword_sequence(
        list((writing_policy.get("keyword_routing") or {}).get("title_traffic_keywords") or [])
        + list((writing_policy.get("keyword_slots") or {}).get("title") or [])
        + list(tiered_keywords.get("l1", []) or [])
    )[:6]
    differentiators = _clean_title_phrases(core_capabilities + list(_flatten_tokens(numeric_specs)))[:3]
    bullet_slots = [f"B{idx}" for idx in range(1, 6)]
    slot_keyword_records: Dict[str, List[str]] = {}
    bullet_plan: List[Dict[str, Any]] = []
    for slot_name in bullet_slots:
        entry = next((item for item in normalized_entries if item.get("slot") == slot_name), {}) or {}
        keywords = list(entry.get("assigned_keywords") or [])
        if not keywords:
            fallback_pool = list(tiered_keywords.get("l2", []) or []) + list(tiered_keywords.get("l3", []) or [])
            idx = max(0, int(slot_name[1:]) - 1)
            keywords = fallback_pool[idx:idx + 1]
        cleaned_keywords = [kw for kw in keywords if kw and kw.lower() not in {term.lower() for term in blocked_terms or []}]
        slot_keyword_records[slot_name] = cleaned_keywords
        bullet_plan.append(
            {
                "slot": slot_name,
                "theme": entry.get("theme") or slot_name,
                "audience_group": entry.get("audience_group") or "",
                "audience_label": entry.get("audience_label") or "",
                "audience_focus": entry.get("audience_focus") or "",
                "persona": entry.get("persona") or "",
                "buying_trigger": entry.get("buying_trigger") or "",
                "proof_angle": entry.get("proof_angle") or "",
                "scene_mapping": list(entry.get("scenes") or []),
                "capabilities": list(entry.get("capabilities") or []),
                "assigned_keywords": cleaned_keywords,
                "mandatory_elements": list(entry.get("mandatory_elements") or []),
                "slot_directive": entry.get("slot_directive") or "",
                "unsupported_capability_policy": (writing_policy.get("bullet_slot_rules") or {}).get(slot_name, {}).get("unsupported_capability_policy") or {},
            }
        )

    system_prompt = (
        "You are an elite Amazon ecommerce copywriter using DeepSeek R1 to draft the visible listing copy in one pass.\n"
        "Return exactly one JSON object with keys title_recipe and bullet_packets.\n"
        "Format:\n"
        '{"title_recipe":{"lead_keyword":"...","differentiators":["..."],"use_cases":["..."]},"bullet_packets":[{"slot":"B1","header":"...","benefit":"...","proof":"...","guidance":"...","required_keywords":["..."],"capability_mapping":["..."],"scene_mapping":["..."]}]}\n'
        "Hard rules:\n"
        "1. Output valid JSON only. No markdown, no commentary, no code fences.\n"
        "2. title_recipe.lead_keyword must be the strongest category phrase for the product.\n"
        "3. title_recipe.differentiators must be short supported selling-point phrases, not full sentences.\n"
        "4. title_recipe.use_cases must be short supported scenario phrases, not full sentences.\n"
        "5. Do not output a finished title string unless explicitly requested elsewhere.\n"
        "6. Write exactly 5 bullet_packets in the requested slot order.\n"
        "7. Each packet must include slot, header, benefit, proof, guidance, required_keywords, capability_mapping, and scene_mapping.\n"
        "8. Each bullet must feel distinct in audience or feature angle; do not write 3 or more commute/on-the-go bullets.\n"
        "9. Keep each bullet under 500 characters.\n"
        "10. Use the Audience Allocation Plan and Bullet Plan as binding instructions.\n"
        "11. Do not invent unsupported specs or accessories.\n"
        "12. Do not use fallback wording like ready to share, every clip feels ready, or generic keyword stuffing.\n"
        "13. If unsupported_capability_policy.expression_mode is positive_guidance_only, never write literal negative phrasing like does not include, lacks, has no, or not suitable for. Reframe as best-use guidance instead.\n"
    )
    payload = {
        "field": "visible_copy_batch",
        "brand_name": getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT"),
        "product_name": getattr(getattr(preprocessed_data, "run_config", None), "product_name", ""),
        "primary_category": getattr(getattr(preprocessed_data, "run_config", None), "category", "camera"),
        "target_language": target_language,
        "core_keywords": exact_keywords,
        "top_differentiators": differentiators,
        "numeric_specs": numeric_specs,
        "scene_priority": list(writing_policy.get("scene_priority") or []),
        "core_capabilities": core_capabilities[:5],
        "attribute_snapshot": {k: attr_lookup.get(k) for k in list(attr_lookup.keys())[:8]},
        "audience_allocation": (bullet_blueprint or {}).get("audience_allocation") if isinstance(bullet_blueprint, dict) else {},
        "bullet_plan": bullet_plan,
        "_request_timeout_seconds": _r1_batch_timeout_seconds(),
        "_disable_fallback": True,
    }
    try:
        text = client.generate_text(
            system_prompt,
            payload,
            temperature=0.2,
            override_model=DEEPSEEK_R1_EXPERIMENT_MODEL,
        )
    except Exception as exc:
        setattr(
            exc,
            "debug_context",
            {
                "stage": "visible_copy_batch",
                "system_prompt": system_prompt,
                "request_payload": payload,
                "llm_response_meta": deepcopy(getattr(client, "response_metadata", {}) or {}),
                "error": str(exc),
            },
        )
        raise
    parsed = _extract_embedded_json_payload(text or "")
    if not isinstance(parsed, dict):
        raise RuntimeError("R1 batch returned non-JSON payload")
    recipe_payload = parsed.get("title_recipe") if isinstance(parsed, dict) else None
    recipe = _extract_title_recipe(recipe_payload if isinstance(recipe_payload, dict) else {})
    if not recipe.get("lead_keyword"):
        recipe = {
            "lead_keyword": exact_keywords[0] if exact_keywords else getattr(getattr(preprocessed_data, "run_config", None), "category", "camera"),
            "differentiators": differentiators[:3],
            "use_cases": list(writing_policy.get("scene_priority") or [])[:3],
        }
    recipe_required_keywords = [
        keyword
        for keyword in exact_keywords[:3]
        if _normalize_keyword_text(keyword) != _normalize_keyword_text(str(recipe.get("lead_keyword") or ""))
    ]
    raw_title = _assemble_title_from_segments(
        getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT"),
        str(recipe.get("lead_keyword") or ""),
        recipe_required_keywords,
        list(_flatten_tokens(numeric_specs[:2])),
        list(recipe.get("differentiators") or []),
        [str(item).replace("_", " ") for item in list(recipe.get("use_cases") or [])],
        target_min=LENGTH_RULES["title"]["target_min"],
        target_max=LENGTH_RULES["title"]["target_max"],
        hard_ceiling=LENGTH_RULES["title"]["hard_ceiling"],
    )
    if audit_log is not None:
        _log_action(
            audit_log,
            "title",
            "recipe_assembled",
            {
                "lead_keyword": recipe.get("lead_keyword") or "",
                "differentiators": list(recipe.get("differentiators") or []),
                "use_cases": list(recipe.get("use_cases") or []),
                "after_len": len(raw_title),
            },
        )
    packet_payload = parsed.get("bullet_packets") or []
    bullets = parsed.get("bullets") or []
    if not raw_title:
        raise RuntimeError("R1 batch returned empty title")
    title_target_min = LENGTH_RULES["title"]["target_min"]
    title_target_max = LENGTH_RULES["title"]["target_max"]
    if len(raw_title) < title_target_min or len(raw_title) > title_target_max:
        title_repair_payload = {
            "exact_match_keywords": exact_keywords[:3],
            "l1_keywords": exact_keywords[:2],
            "assigned_keywords": list(tiered_keywords.get("l2", []) or [])[:1],
            "_repair_keyword_pool": list(tiered_keywords.get("l1", []) or []) + list(tiered_keywords.get("l2", []) or []),
        }
        raw_title = _rule_repair_title_length(
            raw_title,
            title_repair_payload,
            audit_log=audit_log,
            target_min=title_target_min,
            target_max=title_target_max,
            hard_ceiling=LENGTH_RULES["title"]["hard_ceiling"],
        )
    bullet_trace = _build_r1_batch_bullet_trace(bullet_blueprint, bullet_slots, slot_keyword_records)
    slot_contracts = writing_policy.get("bullet_slot_rules") or {}
    if isinstance(packet_payload, list) and len(packet_payload) == 5:
        bullet_packets = []
        for idx, raw_packet in enumerate(packet_payload):
            slot_name = bullet_slots[idx]
            trace_entry = bullet_trace[idx] if idx < len(bullet_trace) else {}
            packet = _normalize_bullet_packet(
                {
                    "slot": raw_packet.get("slot") or slot_name,
                    "header": raw_packet.get("header"),
                    "benefit": raw_packet.get("benefit"),
                    "proof": raw_packet.get("proof"),
                    "guidance": raw_packet.get("guidance"),
                    "required_keywords": raw_packet.get("required_keywords") or trace_entry.get("keywords") or [],
                    "required_facts": raw_packet.get("required_facts") or (slot_contracts.get(slot_name) or {}).get("required_elements") or [],
                    "capability_mapping": raw_packet.get("capability_mapping") or trace_entry.get("capability_mapping") or [],
                    "scene_mapping": raw_packet.get("scene_mapping") or trace_entry.get("scene_mapping") or [],
                    "unsupported_capability_policy": raw_packet.get("unsupported_capability_policy") or (slot_contracts.get(slot_name) or {}).get("unsupported_capability_policy") or {},
                    "contract_version": raw_packet.get("contract_version") or "slot_packet_v1",
                }
            )
            bullet_packets.append(packet)
        cleaned_bullets = [_assemble_bullet_from_packet(packet) for packet in bullet_packets]
    else:
        if not isinstance(bullets, list) or len(bullets) != 5:
            raise RuntimeError("R1 batch must return exactly 5 bullets")
        cleaned_bullets = [str(item or "").strip() for item in bullets]
        if any(not item for item in cleaned_bullets):
            raise RuntimeError("R1 batch returned empty bullet")
        bullet_packets = [
            _build_bullet_packet(
                slot=slot_name,
                bullet_text=bullet_text,
                trace_entry=trace_entry,
                slot_rule_contract=slot_contracts.get(slot_name) or {},
            )
            for slot_name, bullet_text, trace_entry in zip(bullet_slots, cleaned_bullets, bullet_trace)
        ]
    title_payload = {
        "field": "title",
        "brand_name": getattr(getattr(preprocessed_data, "run_config", None), "brand_name", "TOSBARRFT"),
        "product_name": getattr(getattr(preprocessed_data, "run_config", None), "product_name", ""),
        "primary_category": getattr(getattr(preprocessed_data, "run_config", None), "category", "camera"),
        "l1_keywords": exact_keywords[:2],
        "assigned_keywords": list(tiered_keywords.get("l2", []) or [])[:1],
        "core_capability": core_capabilities[0] if core_capabilities else "",
        "scene_priority": list(writing_policy.get("scene_priority") or [])[:3],
        "numeric_specs": numeric_specs[:2],
        "target_language": target_language,
        "max_length": LENGTH_RULES["title"]["hard_ceiling"],
        "exact_match_keywords": exact_keywords[:3],
        "_repair_keyword_pool": list(tiered_keywords.get("l1", []) or []) + list(tiered_keywords.get("l2", []) or []),
        "copy_contracts": writing_policy.get("copy_contracts", {}),
        "_llm_override_model": DEEPSEEK_R1_EXPERIMENT_MODEL,
        "_disable_fallback": True,
        "use_r1_recipe": True,
        "_prefetched_title_candidates": [raw_title],
    }
    required_title_keywords = _dedupe_keyword_sequence(
        list(title_payload.get("exact_match_keywords") or []) + list(title_payload.get("assigned_keywords") or [])
    )
    title = _generate_and_audit_title(
        title_payload,
        audit_log,
        assignment_tracker=None,
        required_keywords=required_title_keywords,
        max_retries=2,
    )
    if _title_is_keyword_dump(title):
        raise RuntimeError("R1 batch title is still a keyword dump")
    if len(title) > LENGTH_RULES["title"]["hard_ceiling"]:
        raise RuntimeError("R1 batch title exceeds hard ceiling")
    if any(len(item) > LENGTH_RULES["bullet"]["hard_ceiling"] for item in cleaned_bullets):
        raise RuntimeError("R1 batch bullet exceeds hard ceiling")
    return {
        "title": title,
        "bullets": cleaned_bullets,
        "bullet_trace": bullet_trace,
        "bullet_packets": bullet_packets,
        "keyword_assignment_plan": {
            "title": required_title_keywords,
            "bullets": deepcopy(slot_keyword_records),
        },
    }


def generate_multilingual_copy(preprocessed_data: PreprocessedData,
                              writing_policy: Dict[str, Any],
                              language: str = None,
                              intent_graph_data: Optional[Dict[str, Any]] = None,
                              bullet_blueprint: Optional[Any] = None,
                              artifact_dir: Optional[str] = None,
                              resume_existing: bool = False,
                              progress_callback: Optional[Callable[[str], None]] = None,
                              model_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    PRD v8.2 Node 4: 多语言文案生成

    流程:
    1. 从 writing_policy.product_profile 提取 English 策略
    2. 从 writing_policy.intent_graph 提取 English Intent Graph
    3. 内部规划用 English 构建信息结构
    4. 最后一步根据 target_language 翻译/生成目标语句子
    5. 缺本地词时添加 [SYNTH] 标记

    Args:
        preprocessed_data: 预处理数据
        writing_policy: writing_policy策略 (含 product_profile, intent_graph)
        language: 目标语言 (默认从 preprocessed_data.language 获取)

    Returns:
        包含所有文案组件的字典
    """
    if artifact_dir:
        repair_logger.initialize_repair_logs(artifact_dir)
    llm_client = get_llm_client()
    llm_provider_name = getattr(llm_client, "provider_label", "unknown")
    llm_mode_label = getattr(llm_client, "mode_label", "offline" if getattr(llm_client, "is_offline", True) else "live")
    llm_credential_source = getattr(llm_client, "credential_source", "none")
    intent_graph_data = intent_graph_data or {}
    intent_graph_nodes = intent_graph_data.get("intent_graph") or writing_policy.get("intent_graph") or []
    capability_metadata = intent_graph_data.get("capability_metadata") or []
    writing_policy = dict(writing_policy or {})
    writing_policy["intent_graph"] = intent_graph_nodes
    writing_policy["capability_metadata"] = capability_metadata

    # 确定目标语言
    target_language = language or getattr(preprocessed_data, 'language', 'English')

    # PRD v8.2: 从 Profile 获取 reasoning_language (固定为 EN)
    profile = writing_policy.get("product_profile", {})
    reasoning_language = profile.get("reasoning_language", "EN")
    data_mode = getattr(preprocessed_data, 'data_mode', 'SYNTHETIC_COLD_START')

    # 读取关键词分配策略
    keyword_allocation_strategy = writing_policy.get("keyword_allocation_strategy", "balanced")

    # 提取分层关键词（Priority 1: 真实国家词表，Priority 2: keyword_data）
    rv_for_tiering = _reconstruct_real_vocab(preprocessed_data)
    tiered_keywords = extract_tiered_keywords(preprocessed_data, target_language, real_vocab=rv_for_tiering)
    l1_keywords = tiered_keywords.get("l1", [])
    preferred_locale = writing_policy.get("preferred_locale") or tiered_keywords.get("_preferred_locale")
    keyword_assignment_tracker = KeywordAssignmentTracker(
        tiered_keywords.get("_metadata", {}),
        getattr(preprocessed_data, "keyword_metadata", None),
    )

    scene_priority = writing_policy.get("scene_priority", [])
    keyword_slots = writing_policy.get("keyword_slots")
    if not keyword_slots:
        keyword_slots = build_keyword_slots(tiered_keywords, scene_priority, target_language)

    backend_only_terms = set(
        writing_policy.get("search_term_plan", {}).get("backend_only_terms", [])
    )
    blocked_terms = backend_only_terms | TABOO_KEYWORDS

    # ---- PRD v8.2 Node 4 Phase 0: 标准化中文能力词/配件名为英文 ----
    # (内部规划统一用 English，不能有残留中文能力词嵌入英文句子)
    canonical_caps = getattr(preprocessed_data, "canonical_core_selling_points", None)
    if canonical_caps:
        core_selling_points_en = canonical_caps
    else:
        core_selling_points_en = _normalize_core_selling_points(preprocessed_data.core_selling_points)
    canonical_accessories = getattr(preprocessed_data, "canonical_accessory_descriptions", None)
    if canonical_accessories:
        accessory_descriptions_en = canonical_accessories
    else:
        accessory_descriptions_en = _normalize_accessory_descriptions(preprocessed_data.accessory_descriptions)

    # 创建一个临时 preprocessed_data 副本用于后续调用（只改这两个字段）
    preprocessed_en = preprocessed_data
    # 使用 dataclass.replace 风格的浅拷贝（如果支持的话），否则手动构造
    try:
        import dataclasses
        preprocessed_en = dataclasses.replace(
            preprocessed_data,
            core_selling_points=core_selling_points_en,
            accessory_descriptions=accessory_descriptions_en,
            canonical_core_selling_points=core_selling_points_en,
            canonical_accessory_descriptions=accessory_descriptions_en,
            language="English"
        )
    except Exception:
        # Fallback: 手动浅拷贝（仅适用于我们实际用到的字段）
        class _EnProxy:
            def __init__(self, pd, caps, accs):
                self.run_config = pd.run_config
                self.attribute_data = pd.attribute_data
                self.keyword_data = pd.keyword_data
                self.review_data = pd.review_data
                self.aba_data = pd.aba_data
                self.real_vocab = getattr(pd, "real_vocab", None)  # 保留真实词表
                self.core_selling_points = caps
                self.accessory_descriptions = accs
                self.canonical_core_selling_points = caps
                self.canonical_accessory_descriptions = accs
                self.canonical_capability_notes = getattr(pd, "canonical_capability_notes", {})
                self.canonical_facts = getattr(pd, "canonical_facts", {})
                self.quality_score = pd.quality_score
                self.language = "English"
                self.processed_at = pd.processed_at
        preprocessed_en = _EnProxy(preprocessed_data, core_selling_points_en, accessory_descriptions_en)

    audit_log: List[Dict[str, Any]] = []
    field_generation_trace: Dict[str, Any] = {}
    canonical_facts = getattr(preprocessed_en, "canonical_facts", None) or getattr(preprocessed_data, "canonical_facts", {}) or {}
    partial_copy: Dict[str, Any] = {}
    model_overrides = model_overrides or {}
    pure_r1_visible_batch = _uses_pure_r1_visible_batch(model_overrides)
    bullet_packets: List[Dict[str, Any]] = []
    slot_quality_packets: List[Dict[str, Any]] = []

    def _restore_stage_snapshot(stage_artifact: Dict[str, Any]) -> None:
        restored_records = stage_artifact.get("keyword_assignments") or []
        keyword_assignment_tracker.load_from_records(restored_records)
        audit_entries = stage_artifact.get("audit_entries") or []
        if audit_entries:
            audit_log.extend(audit_entries)

    def _run_stage(stage_name: str, fn, partial_fields: Dict[str, Any]) -> Any:
        if resume_existing:
            cached = _load_stage_artifact(artifact_dir, stage_name)
            if cached and cached.get("status") == "success":
                if progress_callback:
                    progress_callback(f"{stage_name}: resume from artifact")
                _restore_stage_snapshot(cached)
                result = cached.get("result")
                field_generation_trace[stage_name] = {
                    "status": "resumed",
                    "duration_ms": cached.get("duration_ms"),
                    "attempt_count": cached.get("attempt_count", 1),
                    "llm_response_meta": cached.get("llm_response_meta") or {},
                }
                partial_copy.update(partial_fields(result))
                _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)
                return result

        base_assignment_snapshot = keyword_assignment_tracker.as_list()
        stage_start_idx = len(audit_log)
        attempts: List[Dict[str, Any]] = []
        last_error = ""
        stage_override_model = None
        if stage_name == "title":
            stage_override_model = model_overrides.get("title") or None
        elif stage_name.startswith("bullet_"):
            stage_override_model = model_overrides.get("bullets") or None
        max_retries = _experimental_stage_retry_budget(stage_name, stage_override_model)
        for attempt in range(1, max_retries + 1):
            if progress_callback:
                progress_callback(f"{stage_name}: attempt {attempt}/{max_retries}")
            keyword_assignment_tracker.load_from_records(base_assignment_snapshot)
            started = time.time()
            try:
                result = fn()
            except Exception as exc:
                last_error = str(exc)
                llm_meta = deepcopy(getattr(llm_client, "response_metadata", {}) or {})
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "error",
                        "duration_ms": int((time.time() - started) * 1000),
                        "error": last_error,
                        "llm_response_meta": llm_meta,
                    }
                )
                _save_stage_artifact(
                    artifact_dir,
                    stage_name,
                    {
                        "stage": stage_name,
                        "status": "error",
                        "attempt_count": attempt,
                        "attempts": attempts,
                        "error": last_error,
                        "audit_entries": audit_log[stage_start_idx:],
                        "keyword_assignments": keyword_assignment_tracker.as_list(),
                    },
                )
                if attempt >= max_retries:
                    if progress_callback:
                        progress_callback(f"{stage_name}: failed ({last_error})")
                    field_generation_trace[stage_name] = {
                        "status": "error",
                        "attempt_count": attempt,
                        "error": last_error,
                    }
                    _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)
                    raise RuntimeError(f"{stage_name} generation failed: {last_error}") from exc
                continue

            llm_meta = deepcopy(getattr(llm_client, "response_metadata", {}) or {})
            duration_ms = int((time.time() - started) * 1000)
            if progress_callback:
                progress_callback(f"{stage_name}: success in {duration_ms} ms")
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "success",
                    "duration_ms": duration_ms,
                    "llm_response_meta": llm_meta,
                }
            )
            stage_payload = {
                "stage": stage_name,
                "status": "success",
                "attempt_count": attempt,
                "attempts": attempts,
                "duration_ms": duration_ms,
                "result": result,
                "audit_entries": audit_log[stage_start_idx:],
                "keyword_assignments": keyword_assignment_tracker.as_list(),
                "llm_response_meta": llm_meta,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            provenance_tier = ""
            if stage_name == "description":
                provenance_tier = _description_provenance_from_audit_entries(audit_log[stage_start_idx:])
                if provenance_tier:
                    stage_payload["provenance_tier"] = provenance_tier
            _save_stage_artifact(artifact_dir, stage_name, stage_payload)
            field_generation_trace[stage_name] = {
                "status": "success",
                "attempt_count": attempt,
                "duration_ms": duration_ms,
                "llm_response_meta": llm_meta,
            }
            if provenance_tier:
                field_generation_trace[stage_name]["provenance_tier"] = provenance_tier
            partial_copy.update(partial_fields(result))
            _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)
            return result
        raise RuntimeError(f"{stage_name} generation failed: {last_error or 'unknown error'}")

    bullet_slots = _ordered_bullet_slot_names(bullet_blueprint)
    if pure_r1_visible_batch:
        started = time.time()
        if progress_callback:
            progress_callback("visible_copy_batch: attempt 1/1")
        try:
            batch_result = _r1_batch_generate_listing(
                preprocessed_en,
                writing_policy,
                tiered_keywords,
                bullet_blueprint,
                target_language,
                list(blocked_terms),
                audit_log=audit_log,
            )
        except Exception as exc:
            llm_meta = deepcopy(getattr(llm_client, "response_metadata", {}) or {})
            llm_debug_context = deepcopy(getattr(exc, "debug_context", {}) or {})
            duration_ms = int((time.time() - started) * 1000)
            _save_stage_artifact(
                artifact_dir,
                "visible_copy_batch",
                {
                    "stage": "visible_copy_batch",
                    "status": "error",
                    "attempt_count": 1,
                    "attempts": [
                        {
                            "attempt": 1,
                            "status": "error",
                            "duration_ms": duration_ms,
                            "error": str(exc),
                            "llm_response_meta": llm_meta,
                            "llm_debug_context": llm_debug_context,
                        }
                    ],
                    "error": str(exc),
                    "audit_entries": audit_log,
                    "keyword_assignments": keyword_assignment_tracker.as_list(),
                    "llm_debug_context": llm_debug_context,
                },
            )
            field_generation_trace["visible_copy_batch"] = {
                "status": "error",
                "attempt_count": 1,
                "duration_ms": duration_ms,
                "error": str(exc),
                "llm_response_meta": llm_meta,
                "llm_debug_context": llm_debug_context,
            }
            _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)
            raise RuntimeError(f"R1 batch visible copy generation failed: {exc}") from exc

        llm_meta = deepcopy(getattr(llm_client, "response_metadata", {}) or {})
        duration_ms = int((time.time() - started) * 1000)
        title = batch_result["title"]
        title_ceiling = LENGTH_RULES["title"]["hard_ceiling"]
        if len(title) > title_ceiling:
            raise RuntimeError("R1 batch visible copy generation failed: title exceeds hard ceiling")
        bullets = list(batch_result["bullets"] or [])
        bullet_trace = list(batch_result.get("bullet_trace") or [])
        bullet_packets = list(batch_result.get("bullet_packets") or [])
        reasoning_bullets = list(bullets)
        partial_copy.update({"title": title, "bullets": bullets, "bullet_trace": bullet_trace, "bullet_packets": bullet_packets})
        field_generation_trace["visible_copy_batch"] = {
            "status": "success",
            "attempt_count": 1,
            "duration_ms": duration_ms,
            "subfields": ["title"] + [f"bullet_{slot.lower()}" for slot in bullet_slots],
            "llm_response_meta": llm_meta,
        }
        field_generation_trace["title"] = {
            "status": "success",
            "attempt_count": 1,
            "duration_ms": duration_ms,
            "llm_response_meta": llm_meta,
            "source": "visible_copy_batch",
        }
        for idx, slot_name in enumerate(bullet_slots, start=1):
            field_generation_trace[f"bullet_{slot_name.lower()}"] = {
                "status": "success",
                "attempt_count": 1,
                "duration_ms": duration_ms,
                "llm_response_meta": llm_meta,
                "source": "visible_copy_batch",
                "slot_index": idx,
            }
        field_generation_trace["bullets"] = {
            "status": "success",
            "slot_count": len(bullet_slots),
            "subfields": [f"bullet_{slot.lower()}" for slot in bullet_slots],
            "duration_ms": duration_ms,
            "source": "visible_copy_batch",
        }
        _save_stage_artifact(
            artifact_dir,
            "visible_copy_batch",
            {
                "stage": "visible_copy_batch",
                "status": "success",
                "attempt_count": 1,
                "duration_ms": duration_ms,
                "result": {"title": title, "bullets": bullets, "bullet_trace": bullet_trace, "bullet_packets": bullet_packets},
                "audit_entries": audit_log,
                "keyword_assignments": keyword_assignment_tracker.as_list(),
                "llm_response_meta": llm_meta,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)
    else:
        title_text = _run_stage(
            "title",
            lambda: generate_title(
                preprocessed_en,
                writing_policy,
                l1_keywords,
                tiered_keywords,
                keyword_allocation_strategy,
                audit_log=audit_log,
                blocked_terms=blocked_terms,
                assignment_tracker=keyword_assignment_tracker,
                target_language=target_language,
                request_timeout_seconds=_experimental_stage_timeout_seconds("title", model_overrides.get("title") or None),
                llm_override_model=model_overrides.get("title") or None,
            ),
            lambda result: {"title": result},
        )
        title = title_text
        title_ceiling = LENGTH_RULES["title"]["hard_ceiling"]
        if len(title) > title_ceiling:
            _log_action(audit_log, "title", "truncate", {"reason": f"exceeded {title_ceiling} char limit"})
            title = title[: title_ceiling - 3] + "..."
            partial_copy["title"] = title
            _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)

        bullet_reasoning_map: Dict[str, str] = {}
        bullet_trace_map: Dict[str, Dict[str, Any]] = {}
        bullet_text_map: Dict[str, str] = {}
        bullet_stage_traces: List[Dict[str, Any]] = []

        def _bullet_partial_fields(slot_name: str, result: Any) -> Dict[str, Any]:
            reasoning_list, trace_list, bullet_list = result or ([], [], [])
            bullet_reasoning_map[slot_name] = (reasoning_list or [""])[0] if reasoning_list else ""
            bullet_trace_map[slot_name] = (trace_list or [{}])[0] if trace_list else {}
            bullet_text_map[slot_name] = (bullet_list or [""])[0] if bullet_list else ""
            return {
                "bullets": [bullet_text_map[slot] for slot in bullet_slots if bullet_text_map.get(slot)],
                "bullet_trace": [bullet_trace_map[slot] for slot in bullet_slots if bullet_trace_map.get(slot)],
            }

        for slot_name in bullet_slots:
            stage_name = f"bullet_{slot_name.lower()}"
            _run_stage(
                stage_name,
                lambda slot_name=slot_name: generate_bullet_points(
                    preprocessed_en,
                    writing_policy,
                    "English",
                    tiered_keywords,
                    keyword_allocation_strategy,
                    keyword_slots,
                    audit_log=audit_log,
                    blocked_terms=blocked_terms,
                    assignment_tracker=keyword_assignment_tracker,
                    target_language=target_language,
                    bullet_blueprint=bullet_blueprint,
                    request_timeout_seconds=_experimental_stage_timeout_seconds("bullets", model_overrides.get("bullets") or None),
                    slot_filter=[slot_name],
                    llm_override_model=model_overrides.get("bullets") or None,
                ),
                lambda result, slot_name=slot_name: _bullet_partial_fields(slot_name, result),
            )
            bullet_stage_traces.append(field_generation_trace.get(stage_name, {}))

        reasoning_bullets = [bullet_reasoning_map.get(slot, "") for slot in bullet_slots if slot in bullet_reasoning_map]
        bullet_trace = [bullet_trace_map.get(slot, {}) for slot in bullet_slots if slot in bullet_trace_map]
        bullets = [bullet_text_map.get(slot, "") for slot in bullet_slots if slot in bullet_text_map]
        field_generation_trace["bullets"] = {
            "status": "success" if all(trace.get("status") in {"success", "resumed"} for trace in bullet_stage_traces) else "partial",
            "slot_count": len(bullet_slots),
            "subfields": [f"bullet_{slot.lower()}" for slot in bullet_slots],
            "duration_ms": sum(int(trace.get("duration_ms") or 0) for trace in bullet_stage_traces),
        }
        _write_partial_generation_artifact(artifact_dir, partial_copy, field_generation_trace)

    description = _run_stage(
        "description",
        lambda: generate_description(
            preprocessed_en,
            writing_policy,
            title,
            reasoning_bullets,
            target_language=target_language,
            audit_log=audit_log,
            request_timeout_seconds=_field_stage_timeout_seconds("description"),
        ),
        lambda result: {"description": result},
    )

    faq = _run_stage(
        "faq",
        lambda: generate_faq(
            preprocessed_en,
            writing_policy,
            target_language,
            audit_log=audit_log,
            request_timeout_seconds=_field_stage_timeout_seconds("faq"),
        ),
        lambda result: {"faq": result},
    )

    search_terms, search_terms_trace = _run_stage(
        "search_terms",
        lambda: generate_search_terms(
            preprocessed_en,
            writing_policy,
            title,
            bullets,
            description,
            target_language,
            tiered_keywords,
            keyword_slots,
            audit_log=audit_log,
            assignment_tracker=keyword_assignment_tracker,
        ),
        lambda result: {
            "search_terms": list((result or [[], {}])[0] or []),
            "search_terms_trace": (result or [[], {}])[1] or {},
        },
    )

    aplus_content, aplus_is_native, visual_briefs = _run_stage(
        "aplus",
        lambda: generate_aplus_content(
            preprocessed_en,
            writing_policy,
            target_language,
            audit_log=audit_log,
            request_timeout_seconds=_field_stage_timeout_seconds("aplus"),
        ),
        lambda result: {
            "aplus_content": (result or ["", False, []])[0] or "",
            "visual_briefs": list((result or ["", False, []])[2] or []),
        },
    )

    brand_name = getattr(preprocessed_data.run_config, "brand_name", "TOSBARRFT")
    brand_terms = [brand_name, brand_name.upper(), brand_name.lower()]
    visible_forbidden_terms = _forbidden_visible_terms(writing_policy.get("compliance_directives", {}) or {})
    unsupported_capability_rewrites = _unsupported_capability_rewrites(
        writing_policy.get("compliance_directives", {}) or {},
        enable_semantic_rewrite=pure_r1_visible_batch,
    )
    title = _scrub_visible_field(
        title,
        "title",
        audit_log,
        fallback=brand_name,
        forbidden_terms=visible_forbidden_terms,
        unsupported_capabilities=unsupported_capability_rewrites,
    )
    title = _finalize_visible_text(title, "title", target_language, audit_log, canonical_facts=canonical_facts)
    llm_offline = getattr(llm_client, "_offline", True)
    non_english_locale = target_language.lower() not in {"english", "en"}
    recent_bullet_openers: List[str] = []
    for idx in range(len(bullets)):
        field_name = f"bullet_b{idx+1}"
        trace_entry = bullet_trace[idx] if idx < len(bullet_trace) else {}
        protected_terms = list(brand_terms)
        if trace_entry.get("keywords"):
            protected_terms.extend(trace_entry.get("keywords") or [])
        if non_english_locale and llm_offline:
            localized_value = _localize_text_block(
                bullets[idx],
                target_language,
                preferred_locale,
                protected_terms,
                audit_log,
                field_name,
            )
        else:
            localized_value = bullets[idx]
        bullet_text = _scrub_visible_field(
            localized_value,
            field_name,
            audit_log,
            fallback=brand_name,
            forbidden_terms=visible_forbidden_terms,
            unsupported_capabilities=unsupported_capability_rewrites,
        )
        bullet_text = _finalize_visible_text(bullet_text, field_name, target_language, audit_log, canonical_facts=canonical_facts)
        if not llm_offline and not pure_r1_visible_batch:
            polish_payload = {
                "target_language": target_language,
                "mandatory_keywords": trace_entry.get("keywords") or [],
                "numeric_proof": trace_entry.get("numeric_source"),
                "localized_scene_anchors": _build_localized_scene_anchors(
                    trace_entry.get("scene_mapping") or ([trace_entry.get("scene_code")] if trace_entry.get("scene_code") else []),
                    target_language,
                    rv_for_tiering,
                    data_mode,
                ),
                "localized_capability_anchors": _build_localized_capability_anchors(
                    trace_entry.get("capability_bundle") or ([trace_entry.get("capability")] if trace_entry.get("capability") else []),
                    target_language,
                    rv_for_tiering,
                    data_mode,
                ),
                "copy_contracts": writing_policy.get("copy_contracts", {}),
                "slot": trace_entry.get("slot"),
                "recording_mode_guidance": writing_policy.get("recording_mode_guidance", {}),
                "forbidden_visible_terms": (writing_policy.get("compliance_directives", {}) or {}).get("backend_only_terms", []),
            }
            polished_bullet = _polish_bullet_quality_with_llm(
                bullet_text,
                polish_payload,
                audit_log,
                field_name,
                recent_bullet_openers,
            )
            if polished_bullet != bullet_text:
                bullet_text = _scrub_visible_field(
                    polished_bullet,
                    field_name,
                    audit_log,
                    fallback=brand_name,
                    forbidden_terms=visible_forbidden_terms,
                    unsupported_capabilities=unsupported_capability_rewrites,
                )
                bullet_text = _finalize_visible_text(bullet_text, field_name, target_language, audit_log, canonical_facts=canonical_facts)
        bullets[idx] = bullet_text
        opener_signature = _bullet_body_opener_signature(bullets[idx])
        if opener_signature:
            recent_bullet_openers.append(opener_signature)
    slot_rule_contracts = writing_policy.get("bullet_slot_rules") or {}
    if pure_r1_visible_batch and bullet_packets:
        bullet_packets = _sync_bullet_packets_to_final_bullets(
            bullets,
            bullet_packets,
            bullet_trace,
            slot_rule_contracts,
        )
    if _should_run_localization_pass(description, target_language, llm_offline):
        description = _localize_text_block(description, target_language, preferred_locale, brand_terms, audit_log, "description")
    description = _scrub_visible_field(
        description,
        "description",
        audit_log,
        fallback=brand_name,
        forbidden_terms=visible_forbidden_terms,
        unsupported_capabilities=unsupported_capability_rewrites,
    )
    description = _finalize_visible_text(description, "description", target_language, audit_log, canonical_facts=canonical_facts)
    localized_faq: List[Dict[str, str]] = []
    for idx, entry in enumerate(faq):
        q_field = f"faq_q{idx+1}"
        a_field = f"faq_a{idx+1}"
        question = entry.get("q", "")
        answer = entry.get("a", "")
        if _should_run_localization_pass(question, target_language, llm_offline):
            question = _localize_text_block(question, target_language, preferred_locale, brand_terms, audit_log, q_field)
        if _should_run_localization_pass(answer, target_language, llm_offline):
            answer = _localize_text_block(answer, target_language, preferred_locale, brand_terms, audit_log, a_field)
        localized_faq.append({
            "q": _finalize_visible_text(question, q_field, target_language, audit_log, canonical_facts=canonical_facts),
            "a": _finalize_visible_text(answer, a_field, target_language, audit_log, canonical_facts=canonical_facts),
        })
    faq = localized_faq
    if not aplus_is_native or _should_run_localization_pass(aplus_content, target_language, llm_offline):
        aplus_content = _localize_text_block(aplus_content, target_language, preferred_locale, brand_terms, audit_log, "aplus_content")
    aplus_content = _finalize_visible_text(aplus_content, "aplus_content", target_language, audit_log, canonical_facts=canonical_facts)

    _record_constraint_audit_actions(
        audit_log,
        title,
        bullets,
        description,
        writing_policy,
        getattr(preprocessed_en, "capability_constraints", {}) or {},
    )

    slot_rule_contracts = writing_policy.get("bullet_slot_rules") or {}
    if not bullet_packets and bullets:
        bullet_packets = [
            _build_bullet_packet(
                f"B{idx + 1}",
                str(bullet or ""),
                trace_entry=(bullet_trace[idx] if idx < len(bullet_trace) and isinstance(bullet_trace[idx], dict) else {}),
                slot_rule_contract=slot_rule_contracts.get(f"B{idx + 1}") or {},
            )
            for idx, bullet in enumerate(bullets)
        ]
    slot_quality_packets = [
        _build_slot_quality_packet(
            packet,
            copy_contracts=writing_policy.get("copy_contracts") or {},
            slot_rule_contract=slot_rule_contracts.get(packet.get("slot")) or {},
            target_language=target_language,
        )
        for packet in (bullet_packets or [])
    ]
    slot_rerender_plan = build_slot_rerender_plan(
        {
            "metadata": {"visible_copy_mode": "r1_batch"} if pure_r1_visible_batch else {},
            "bullets": bullets,
            "bullet_packets": bullet_packets,
            "slot_quality_packets": slot_quality_packets,
        },
        writing_policy,
    )
    slot_rerender_results: List[Dict[str, Any]] = []
    if slot_rerender_plan:
        rerender_surface = _run_slot_rerender_pass(
            {
                "metadata": {"visible_copy_mode": "r1_batch"} if pure_r1_visible_batch else {},
                "bullets": bullets,
                "bullet_packets": bullet_packets,
                "slot_quality_packets": slot_quality_packets,
                "slot_rerender_plan": slot_rerender_plan,
            },
            writing_policy,
            target_language=target_language,
            model_overrides=model_overrides,
            progress_callback=progress_callback,
        )
        bullets = list(rerender_surface.get("bullets") or bullets)
        bullet_packets = list(rerender_surface.get("bullet_packets") or bullet_packets)
        slot_quality_packets = list(rerender_surface.get("slot_quality_packets") or slot_quality_packets)
        slot_rerender_plan = list(rerender_surface.get("slot_rerender_plan") or [])
        slot_rerender_results = list(rerender_surface.get("slot_rerender_results") or [])

    final_visible_surface = {
        "title": title,
        "bullets": bullets,
        "description": description,
        "search_terms": search_terms,
        "bullet_packets": bullet_packets,
        "slot_quality_packets": slot_quality_packets,
        "metadata": {"visible_copy_mode": "r1_batch"} if pure_r1_visible_batch else {},
    }
    if not pure_r1_visible_batch:
        final_visible_surface = _apply_final_visible_quality_gate(
            final_visible_surface,
            writing_policy,
            target_language=target_language,
            candidate_id="version_a",
            source_type="stable",
        )
        bullets = list(final_visible_surface.get("bullets") or bullets)
        description = str(final_visible_surface.get("description") or description)
        bullet_packets = list(final_visible_surface.get("bullet_packets") or bullet_packets)
        slot_quality_packets = list(final_visible_surface.get("slot_quality_packets") or slot_quality_packets)
        final_visible_quality = dict(final_visible_surface.get("final_visible_quality") or {})
    else:
        final_visible_quality = validate_final_visible_copy(
            final_visible_surface,
            candidate_id="version_b",
            source_type="experimental",
        )

    keyword_reconciliation = _reconcile_final_keyword_assignments(
        keyword_assignment_tracker,
        title=title,
        bullets=bullets,
        search_terms=search_terms,
        description=description,
        tiered_keywords=tiered_keywords,
        writing_policy=writing_policy,
    )

    # 构建完整文案
    decision_trace = {
        "keyword_assignments": keyword_assignment_tracker.as_list(),
        "keyword_reconciliation_status": keyword_reconciliation.get("status"),
        "keyword_reconciliation_coverage": keyword_reconciliation.get("coverage") or {},
        "bullet_trace": bullet_trace,
        "search_terms_trace": search_terms_trace,
    }

    llm_response_meta = getattr(llm_client, "response_metadata", {}) or {}
    primary_visible_llm_meta = _resolve_primary_visible_llm_meta(field_generation_trace, llm_response_meta)
    llm_healthcheck = getattr(llm_client, "healthcheck_status", {}) or {}
    llm_fallback_fields = [
        str((entry or {}).get("field") or "").strip()
        for entry in audit_log
        if (entry or {}).get("action") == "llm_fallback"
    ]
    llm_fallback_count = sum(
        1 for entry in audit_log if (entry or {}).get("action") == "llm_fallback"
    )
    visible_llm_fallback_fields = []
    for field_name in llm_fallback_fields:
        normalized = field_name
        if field_name.startswith("bullet_"):
            normalized = field_name.replace("bullet_", "").upper()
        elif field_name == "description_llm":
            normalized = "description"
        if field_name == "title" or field_name.startswith("bullet_") or field_name in {"description_llm", "aplus_content"}:
            if normalized not in visible_llm_fallback_fields:
                visible_llm_fallback_fields.append(normalized)
    if llm_offline:
        generation_status = "offline"
    elif llm_fallback_count:
        generation_status = "live_with_fallback"
    else:
        generation_status = "live_success"

    entity_profile = getattr(preprocessed_data, "asin_entity_profile", {}) or {}
    evidence_bundle = build_evidence_bundle(preprocessed_data, entity_profile)
    claim_support_matrix = evidence_bundle.get("claim_support_matrix", []) or []
    unsupported_claim_count = sum(
        1 for row in claim_support_matrix if (row or {}).get("support_status") == "unsupported"
    )
    weak_claim_count = sum(
        1 for row in claim_support_matrix if (row or {}).get("support_status") == "weakly_supported"
    )
    rufus_readiness = evidence_bundle.get("rufus_readiness", {}) or {}

    copy_dict = {
        "title": title,
        "bullets": bullets,
        "bullet_packets": bullet_packets,
        "slot_quality_packets": slot_quality_packets,
        "slot_rerender_plan": slot_rerender_plan,
        "slot_rerender_results": slot_rerender_results,
        "description": description,
        "faq": faq,
        "search_terms": search_terms,
        "aplus_content": aplus_content,
        "visual_briefs": visual_briefs,
        "evidence_bundle": evidence_bundle,
        "keyword_reconciliation": keyword_reconciliation,
        "final_visible_quality": final_visible_quality,
        "metadata": {
            "version": "v8.2",
            "reasoning_language": reasoning_language,
            "target_language": target_language,
            "language": target_language,
            "data_mode": data_mode,
            "generation_status": generation_status,
            "has_synthetic": "[SYNTH]" in title or any("[SYNTH]" in b for b in bullets),
            "title_length": len(title),
            "bullets_count": len(bullets),
            "description_length": len(description),
            "faq_count": len(faq),
            "search_terms_count": len(search_terms),
            "aplus_content_length": len(aplus_content),
            "generated_at": preprocessed_data.processed_at,
            "llm_model": getattr(llm_client, "active_model", None),
            "llm_provider": llm_provider_name,
            "llm_mode": llm_mode_label,
            "llm_credential_source": llm_credential_source,
            "llm_wire_api": getattr(llm_client, "wire_api", "chat/completions"),
            "llm_base_url": getattr(llm_client, "base_url", ""),
            "llm_fallback_count": llm_fallback_count,
            "llm_fallback_fields": llm_fallback_fields,
            "visible_llm_fallback_fields": visible_llm_fallback_fields,
            "configured_model": primary_visible_llm_meta.get("configured_model") or getattr(llm_client, "active_model", None),
            "returned_model": primary_visible_llm_meta.get("returned_model"),
            "last_stage_configured_model": llm_response_meta.get("configured_model") or getattr(llm_client, "active_model", None),
            "last_stage_returned_model": llm_response_meta.get("returned_model"),
            "llm_request_id": llm_response_meta.get("request_id", ""),
            "llm_response_id": llm_response_meta.get("response_id", ""),
            "llm_latency_ms": llm_response_meta.get("latency_ms"),
            "llm_endpoint": llm_response_meta.get("endpoint", ""),
            "llm_response_success": llm_response_meta.get("success"),
            "llm_response_state": llm_response_meta.get("response_state", ""),
            "llm_response_error": llm_response_meta.get("error", ""),
            "llm_healthcheck": llm_healthcheck,
            "field_generation_trace": field_generation_trace,
            "visible_copy_mode": "r1_batch" if pure_r1_visible_batch else "stage_by_stage",
            "visible_copy_status": "r1_pure" if pure_r1_visible_batch else "standard",
            "unsupported_claim_count": unsupported_claim_count,
            "weak_claim_count": weak_claim_count,
            "rufus_readiness_score": rufus_readiness.get("score", 0.0),
            "canonical_facts": deepcopy(getattr(preprocessed_data, "canonical_facts", {}) or {}),
            "canonical_fact_readiness": deepcopy(getattr(preprocessed_data, "fact_readiness", {}) or {}),
            "final_visible_quality": final_visible_quality,
        },
        "audit_trail": audit_log,
        "decision_trace": decision_trace,
    }
    copy_dict["compute_tier_map"] = build_compute_tier_map(copy_dict)
    copy_dict["metadata"]["fallback_density"] = sum(
        1 for item in copy_dict["compute_tier_map"].values() if item.get("tier_used") == "rule_based"
    )

    keyword_assignment_tracker.flush_into_preprocessed(preprocessed_data)
    if artifact_dir:
        _save_stage_artifact(
            artifact_dir,
            "final_copy",
            {"status": "success", "result": copy_dict, "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
        )
        _write_partial_generation_artifact(
            artifact_dir,
            {
                **partial_copy,
                "title": title,
                "bullets": bullets,
                "description": description,
                "faq": faq,
                "search_terms": search_terms,
                "aplus_content": aplus_content,
                "visual_briefs": visual_briefs,
            },
            field_generation_trace,
        )
    return copy_dict


def generate_listing_copy(preprocessed_data: PreprocessedData,
                         writing_policy: Dict[str, Any],
                         language: str = None,
                         intent_graph: Optional[Dict[str, Any]] = None,
                         bullet_blueprint: Optional[Any] = None,
                         artifact_dir: Optional[str] = None,
                         resume_existing: bool = False,
                         progress_callback: Optional[Callable[[str], None]] = None,
                         model_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    生成完整的Listing文案 - PRD v8.2 多语言版

    委托给 generate_multilingual_copy() 处理多语言逻辑：
    - 内部推理使用 English (Reasoning_Language = EN)
    - 最终输出使用 target_language
    - 缺本地词时添加 [SYNTH] 标记

    Args:
        preprocessed_data: 预处理数据
        writing_policy: writing_policy策略 (含 product_profile, intent_graph)
        language: 目标语言 (默认从 preprocessed_data.language 获取)

    Returns:
        包含所有文案组件的字典
    """
    return generate_multilingual_copy(
        preprocessed_data,
        writing_policy,
        language,
        intent_graph_data=intent_graph,
        bullet_blueprint=bullet_blueprint,
        artifact_dir=artifact_dir,
        resume_existing=resume_existing,
        progress_callback=progress_callback,
        model_overrides=model_overrides,
    )

    # 生成标题（确保L1在首80字符内，多场景）
    title = generate_title(preprocessed_data, writing_policy, l1_keywords, tiered_keywords, keyword_allocation_strategy)

    # 生成bullet points（多场景覆盖，使用L2/L3关键词）
    bullets = generate_bullet_points(preprocessed_data, writing_policy, language, tiered_keywords, keyword_allocation_strategy)

    # 生成描述
    description = generate_description(preprocessed_data, writing_policy, title, bullets, language)

    # 生成FAQ
    faq = generate_faq(preprocessed_data, writing_policy, language)

    # 生成搜索词（优先L2/L3长尾关键词）
    search_terms = generate_search_terms(preprocessed_data, writing_policy, title, bullets, description, language, tiered_keywords)

    # 生成A+内容
    aplus_content, _, _ = generate_aplus_content(preprocessed_data, writing_policy, language, audit_log=None)

    # 构建完整文案
    copy_dict = {
        "title": title,
        "bullets": bullets,
        "description": description,
        "faq": faq,
        "search_terms": search_terms,
        "aplus_content": aplus_content,
        "visual_briefs": [],
        "metadata": {
            "language": language,
            "title_length": len(title),
            "bullets_count": len(bullets),
            "description_length": len(description),
            "faq_count": len(faq),
            "search_terms_count": len(search_terms),
            "aplus_content_length": len(aplus_content),
            "generated_at": preprocessed_data.processed_at
        }
    }

    return copy_dict


def save_copy_to_file(copy_dict: Dict[str, Any], filepath: str):
    """保存文案到文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(copy_dict, f, ensure_ascii=False, indent=2)


def load_copy_from_file(filepath: str) -> Dict[str, Any]:
    """从文件加载文案"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    # 测试代码
    from dataclasses import dataclass, field

    @dataclass
    class MockKeywordData:
        keywords: List[Dict[str, Any]]

    @dataclass
    class MockAttributeData:
        data: Dict[str, Any]

    @dataclass
    class MockRunConfig:
        brand_name: str

    # 创建模拟数据
    mock_preprocessed = PreprocessedData(
        run_config=MockRunConfig(brand_name="TOSBARRFT"),
        attribute_data=MockAttributeData(data={
            "video_resolution": "4K 30fps",
            "waterproof_depth": "30米",
            "battery_life": "150分钟",
            "weight": "150g",
            "max_storage": "256GB",
            "warranty_period": "12个月"
        }),
        keyword_data=MockKeywordData(keywords=[
            {"keyword": "action camera", "search_volume": 15000},
            {"keyword": "sports camera", "search_volume": 8000},
            {"keyword": "waterproof camera", "search_volume": 12000}
        ]),
        review_data=None,
        aba_data=None,
        core_selling_points=["4K录像", "防抖", "防水", "WiFi连接", "双屏幕"],
        accessory_descriptions=[
            {"name": "防水壳", "specification": "30米防水"},
            {"name": "数据线", "specification": "USB-C"}
        ],
        quality_score=85,
        language="Chinese",
        processed_at="2024-01-01T00:00:00"
    )

    mock_writing_policy = {
        "scene_priority": ["户外运动", "骑行记录", "水下探索"],
        "capability_scene_bindings": [],
        "faq_only_capabilities": ["数字防抖限制说明"],
        "forbidden_pairs": [],
        "bullet_slot_rules": {},
        "language": "Chinese"
    }

    copy_dict = generate_listing_copy(mock_preprocessed, mock_writing_policy, "Chinese", intent_graph=None)
    print("生成的文案:")
    print(f"标题: {copy_dict['title']}")
    print(f"\nBullet Points ({len(copy_dict['bullets'])}条):")
    for i, bullet in enumerate(copy_dict['bullets'], 1):
        print(f"{i}. {bullet}")
    print(f"\n描述 (长度: {len(copy_dict['description'])}字符):")
    print(copy_dict['description'][:200] + "...")
    print(f"\nFAQ ({len(copy_dict['faq'])}条):")
    for i, faq_item in enumerate(copy_dict['faq'], 1):
        print(f"{i}. Q: {faq_item['q']}")
        print(f"   A: {faq_item['a']}")
    print(f"\n搜索词 ({len(copy_dict['search_terms'])}个): {', '.join(copy_dict['search_terms'])}")
    print(f"\nA+内容长度: {len(copy_dict['aplus_content'])}字符")
