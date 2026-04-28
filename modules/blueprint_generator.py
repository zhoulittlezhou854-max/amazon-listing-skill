#!/usr/bin/env python3
"""Node 0 - Dynamic Bullet Blueprint generator."""

from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from modules.llm_client import get_llm_client, LLMClientUnavailable
from modules.keyword_utils import extract_tiered_keywords
from modules.language_utils import english_capability_label, canonicalize_capability
try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore

MAX_INSIGHT_CHARS = 4000
BLUEPRINT_PRIMARY_MODEL = "deepseek-chat"
BLUEPRINT_FALLBACK_MODEL = "deepseek-reasoner"

AUDIENCE_GROUPS = {
    "hero": "Primary use case / main buyer persona",
    "professional": "Professional / work use (security, service staff, evidence-capture)",
    "daily": "Daily personal use (commuting, travel, family, lifestyle)",
    "guidance": "Usage boundary / what this product is NOT for",
    "kit": "Kit value / what's included / package contents",
}

AUDIENCE_FALLBACK_PLAN = [
    {"slot": "B1", "group": "hero", "focus": "primary differentiating feature"},
    {"slot": "B2", "group": "professional", "focus": "work/evidence use case"},
    {"slot": "B3", "group": "daily", "focus": "daily personal use scenario"},
    {"slot": "B4", "group": "guidance", "focus": "usage boundary or compatibility note"},
    {"slot": "B5", "group": "kit", "focus": "included items and package value"},
]

SUPPRESSED_CAPABILITY_TERMS = {
    "live_streaming_supported": ["live stream", "live streaming", "livestream"],
    "waterproof_supported": ["waterproof", "underwater"],
    "stabilization_supported": ["stabilization", "stabilized", "eis"],
}

_NEGATIVE_PREFIX_RE = re.compile(
    r"(?i)^(?:(?:explicit\s+)?note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?(?:has\s+no|no|without)\s+\w+(?:\s+\w+){0,2}\s*[,;:\.-]?\s*"
)
_NEGATIVE_SUFFIX_RE = re.compile(
    r"(?i)\s*[,;:-]?\s*(?:as\s+it\s+)?(?:lacks|has\s+no|without)\s+\w+(?:\s+\w+){0,2}\s*\.?\s*$"
)
_NEGATIVE_ONLY_RE = re.compile(
    r"(?i)^(?:(?:explicit\s+)?note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?(?:lacks|has\s+no|no|without)\s+\w+(?:\s+\w+){0,2}\s*\.?$"
)
_GUIDANCE_HINT_RE = re.compile(r"(?i)\b(guidance|warning|boundary|best[- ]use|first-time|informed buyer|not suitable)\b")
_MID_SENTENCE_NEGATIVE_REPAIRS = [
    (
        re.compile(r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?lacks image\s+and\s+"),
        ", ",
    ),
    (
        re.compile(r"(?i)(?:,\s*)?(?:note:\s*)?(?:(?:it|this camera|the camera|machine)\s+)?(?:has\s+no|no)\s+image\s+and\s+"),
        ", ",
    ),
]


def _summarize_attributes(attr_data: Any) -> Dict[str, Any]:
    raw = getattr(attr_data, "data", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(attr_data, dict):
        return attr_data
    return {}


def _canonical_capabilities(preprocessed_data: Any) -> List[str]:
    canonical_caps = getattr(preprocessed_data, "canonical_core_selling_points", None)
    if canonical_caps:
        return canonical_caps
    caps = getattr(preprocessed_data, "core_selling_points", []) or []
    return [english_capability_label(canonicalize_capability(cap)) for cap in caps]


def _blueprint_metadata_rows(tiered_keywords: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = tiered_keywords.get("_metadata", {}) or {}
    if isinstance(metadata, dict):
        return [row for row in metadata.values() if isinstance(row, dict)]
    if isinstance(metadata, list):
        return [row for row in metadata if isinstance(row, dict)]
    return []


def _blueprint_numeric(row: Dict[str, Any], field: str) -> float:
    try:
        return float(row.get(field) or 0)
    except (TypeError, ValueError):
        return 0.0


def _derive_blueprint_l2_keywords(tiered_keywords: Dict[str, Any]) -> List[str]:
    bullet_rows = [
        row for row in _blueprint_metadata_rows(tiered_keywords)
        if str(row.get("quality_status") or "").lower() == "qualified"
        and str(row.get("routing_role") or "").lower() == "bullet"
    ]
    if not bullet_rows:
        return list(tiered_keywords.get("l2", []) or [])

    sorted_rows = sorted(
        bullet_rows,
        key=lambda row: (
            _blueprint_numeric(row, "opportunity_score"),
            _blueprint_numeric(row, "blue_ocean_score"),
            _blueprint_numeric(row, "conversion_score"),
            _blueprint_numeric(row, "search_volume"),
        ),
        reverse=True,
    )
    keywords: List[str] = []
    seen = set()
    for row in sorted_rows:
        keyword = str(row.get("keyword") or "").strip()
        key = keyword.lower()
        if keyword and key not in seen:
            seen.add(key)
            keywords.append(keyword)
    return keywords


def _truncate_insights(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.strip()
    if len(text) <= MAX_INSIGHT_CHARS:
        return text
    return text[:MAX_INSIGHT_CHARS]


def _strip_markdown_fences(text: str) -> str:
    """
    Allow the LLM to wrap JSON inside ```json``` fences or prepend explanations.
    Extract the first JSON object substring when wrapping is detected.
    """
    if not text:
        return ""
    cleaned = text.strip()
    fence_match = re.match(r"```(?:json)?\s*(.*?)\s*```$", cleaned, re.IGNORECASE | re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    # find first JSON object if extra commentary exists
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if 0 <= start < end:
        return cleaned[start:end + 1].strip()
    return cleaned


def _parse_llm_blueprint(response: str) -> Dict[str, Any]:
    payload = _strip_markdown_fences(response or "")
    if not payload:
        raise ValueError("LLM blueprint returned empty response")
    data = json.loads(payload)
    bullets = data.get("bullets") or data.get("slots") or data.get("entries")
    if not isinstance(bullets, list):
        raise ValueError("LLM blueprint missing bullets list")
    normalized: List[Dict[str, Any]] = []
    for item in bullets:
        if not isinstance(item, dict):
            continue
        normalized.append(item)
    if not normalized:
        raise ValueError("LLM blueprint returned empty bullets")
    data["bullets"] = normalized[:5]
    return data


def _clean_suppressed_text(text: str, blocked_terms: Sequence[str]) -> str:
    cleaned = str(text or "")
    for term in blocked_terms:
        cleaned = re.sub(re.escape(term), "", cleaned, flags=re.IGNORECASE)
    for pattern, replacement in _MID_SENTENCE_NEGATIVE_REPAIRS:
        cleaned = pattern.sub(replacement, cleaned)
    changed = False
    repaired_segments: List[str] = []
    for segment in re.split(r"(?<=[.!?])\s+", cleaned.strip()):
        segment = segment.strip()
        if not segment:
            continue
        original = segment
        segment = _NEGATIVE_PREFIX_RE.sub("", segment)
        segment = _NEGATIVE_SUFFIX_RE.sub("", segment)
        segment = re.sub(r"\s+", " ", segment).strip(" ,;:-")
        if not segment or _NEGATIVE_ONLY_RE.fullmatch(segment):
            changed = True
            continue
        if segment != original:
            changed = True
        if repaired_segments and segment[:1].islower():
            segment = segment[:1].upper() + segment[1:]
        repaired_segments.append(segment)
    cleaned = " ".join(repaired_segments) if (changed or repaired_segments) else cleaned
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,;:])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:]){2,}", r"\1", cleaned)
    cleaned = re.sub(r"\b(and|or)\b\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[,;:\-\s]+|[,;:\-\s]+$", "", cleaned)
    return cleaned.strip()


def _entry_mentions_blocked_terms(entry: Dict[str, Any], blocked_terms: Sequence[str]) -> bool:
    values: List[str] = []
    for field in ("theme", "proof_angle", "slot_directive"):
        values.append(str(entry.get(field) or ""))
    for list_field in ("mandatory_elements", "capabilities"):
        values.extend(str(item or "") for item in (entry.get(list_field) or []))
    lowered = " || ".join(values).lower()
    return any(str(term or "").strip().lower() in lowered for term in blocked_terms if str(term or "").strip())


def _negative_constraint_slot_score(entry: Dict[str, Any]) -> tuple[int, int]:
    index = int(entry.get("bullet_index") or 0)
    text = " ".join(
        [
            str(entry.get("theme") or ""),
            str(entry.get("persona") or ""),
            str(entry.get("pain_point") or ""),
            str(entry.get("buying_trigger") or ""),
            str(entry.get("proof_angle") or ""),
            str(entry.get("slot_directive") or ""),
        ]
    )
    score = 0
    if index == 4:
        score += 5
    if _GUIDANCE_HINT_RE.search(text):
        score += 3
    return score, -index


def _prune_duplicate_negative_constraint(
    entry: Dict[str, Any],
    blocked_terms: Sequence[str],
) -> Dict[str, Any]:
    pruned = deepcopy(entry)
    for field in ("theme", "proof_angle", "slot_directive"):
        pruned[field] = _clean_suppressed_text(pruned.get(field, ""), blocked_terms)
    mandatory_values: List[str] = []
    for item in pruned.get("mandatory_elements") or []:
        original = str(item or "").strip()
        if not original:
            continue
        lowered = original.lower()
        if any(term.lower() in lowered for term in blocked_terms):
            continue
        mandatory_values.append(original)
    pruned["mandatory_elements"] = mandatory_values
    capabilities = []
    for item in pruned.get("capabilities") or []:
        original = str(item or "").strip()
        if not original:
            continue
        lowered = original.lower()
        if any(term.lower() in lowered for term in blocked_terms):
            continue
        capabilities.append(original)
    pruned["capabilities"] = capabilities
    return pruned


def _dedupe_negative_constraint_blueprint_content(
    blueprint: Dict[str, Any],
    suppressed_capabilities: Sequence[str],
) -> Dict[str, Any]:
    suppressed = {str(item or "").strip().lower() for item in (suppressed_capabilities or []) if str(item or "").strip()}
    if not suppressed:
        return blueprint

    deduped = deepcopy(blueprint)
    bullets = deduped.get("bullets") or []
    if not isinstance(bullets, list):
        return deduped

    for capability_key in suppressed:
        blocked_terms = SUPPRESSED_CAPABILITY_TERMS.get(capability_key, [])
        if not blocked_terms:
            continue
        matching_indexes = [
            idx
            for idx, entry in enumerate(bullets)
            if isinstance(entry, dict) and _entry_mentions_blocked_terms(entry, blocked_terms)
        ]
        if len(matching_indexes) <= 1:
            continue
        keep_index = max(matching_indexes, key=lambda idx: _negative_constraint_slot_score(bullets[idx]))
        for idx in matching_indexes:
            if idx == keep_index:
                continue
            bullets[idx] = _prune_duplicate_negative_constraint(bullets[idx], blocked_terms)
    deduped["bullets"] = bullets
    return deduped


def _scrub_suppressed_blueprint_content(
    blueprint: Dict[str, Any],
    suppressed_capabilities: Sequence[str],
) -> Dict[str, Any]:
    suppressed = {str(item or "").strip().lower() for item in (suppressed_capabilities or []) if str(item or "").strip()}
    blocked_terms: List[str] = []
    for key in suppressed:
        blocked_terms.extend(SUPPRESSED_CAPABILITY_TERMS.get(key, []))
    if not blocked_terms:
        return blueprint

    scrubbed = deepcopy(blueprint)
    for entry in scrubbed.get("bullets") or []:
        if not isinstance(entry, dict):
            continue
        for field in ("theme", "proof_angle", "slot_directive"):
            entry[field] = _clean_suppressed_text(entry.get(field, ""), blocked_terms)
        for list_field in ("mandatory_elements", "capabilities"):
            values = []
            for item in entry.get(list_field) or []:
                cleaned = _clean_suppressed_text(str(item or ""), blocked_terms)
                if cleaned:
                    values.append(cleaned)
            entry[list_field] = values
    return scrubbed


def _build_audience_allocation_plan(preprocessed_data: Any, writing_policy: Dict[str, Any]) -> List[Dict[str, str]]:
    scenes = writing_policy.get("scene_priority", []) or []
    canonical_caps = _canonical_capabilities(preprocessed_data)
    primary_feature = canonical_caps[0] if canonical_caps else "primary differentiating feature"
    secondary_feature = canonical_caps[1] if len(canonical_caps) > 1 else primary_feature
    scene_focus = scenes[0].replace("_", " ") if scenes else "daily personal use scenario"
    fallback_entries = []
    for entry in AUDIENCE_FALLBACK_PLAN:
        focus = entry["focus"]
        if entry["group"] == "hero":
            focus = primary_feature
        elif entry["group"] == "professional":
            focus = f"evidence-ready {secondary_feature}"
        elif entry["group"] == "daily":
            focus = scene_focus
        elif entry["group"] == "guidance":
            focus = "best-use guidance and product boundary"
        elif entry["group"] == "kit":
            focus = "what is included in the package"
        fallback_entries.append({
            "slot": entry["slot"],
            "group": entry["group"],
            "label": AUDIENCE_GROUPS[entry["group"]],
            "focus": focus,
        })
    return fallback_entries


def _build_audience_allocation_prompt(plan: Sequence[Dict[str, str]]) -> str:
    lines = [
        "Audience Allocation Plan - MUST follow this structure:",
        "You are planning 5 bullet points. Each bullet must serve a DIFFERENT audience group. Do not write 3+ bullets for the same audience.",
        "",
        "Allocation:",
    ]
    for entry in plan:
        lines.append(
            f"- {entry['slot']} [{entry['group']} | {entry['label']}]: Focus on {entry['focus']}"
        )
    lines.extend([
        "",
        "Constraint: At least 2 different audience groups must be represented across B1-B5.",
        "If all 5 bullets address the same scenario, this blueprint is INVALID and must be regenerated.",
        'CRITICAL: If you write 3 or more bullet plans that all target "commuting / cycling / on-the-go" use cases, this blueprint is AUTOMATICALLY REJECTED. You must redistribute to different audience groups before finalizing.',
    ])
    return "\n".join(lines)


def _stream_llm_response(client: Any, messages: List[Dict[str, str]], model: str, timeout: int) -> str:
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        timeout=timeout,
    )
    chunks: List[str] = []
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        content = getattr(delta, "content", None)
        if content:
            chunks.append(content)
    return "".join(chunks)


def _call_blueprint_llm(
    client: Any,
    messages: List[Dict[str, str]],
    timeout: int,
    artifact_dir: Optional[str],
    audit_log: Optional[List[Dict[str, Any]]],
) -> str:
    del artifact_dir  # Reserved for future artifact logging, kept in signature by design.
    attempts = [
        (BLUEPRINT_PRIMARY_MODEL, 30),
        (BLUEPRINT_FALLBACK_MODEL, 120),
    ]
    last_exc: Optional[Exception] = None
    for index, (model, model_timeout) in enumerate(attempts, start=1):
        started = time.time()
        try:
            response = _stream_llm_response(client, messages, model=model, timeout=model_timeout)
            try:
                setattr(client, "_last_blueprint_model", model)
            except Exception:
                pass
            if hasattr(client, "_record_response_meta"):
                try:
                    client._record_response_meta(  # type: ignore[attr-defined]
                        endpoint="chat.completions",
                        wire_api="chat/completions",
                        response_data={"model": model},
                        latency_ms=int((time.time() - started) * 1000),
                        success=bool(response),
                        error="" if response else "empty_content",
                        configured_model=model,
                    )
                except Exception:
                    pass
            return response
        except Exception as exc:
            last_exc = exc
            if hasattr(client, "_record_response_meta"):
                try:
                    client._record_response_meta(  # type: ignore[attr-defined]
                        endpoint="chat.completions",
                        wire_api="chat/completions",
                        response_data={"model": model},
                        latency_ms=int((time.time() - started) * 1000),
                        success=False,
                        error=str(exc),
                        configured_model=model,
                    )
                except Exception:
                    pass
            if index == 1 and audit_log is not None:
                audit_log.append(
                    {
                        "action": "llm_retry",
                        "model": model,
                        "error": str(exc),
                    }
                )
    if last_exc is None:
        raise RuntimeError("Blueprint LLM call failed without an exception")
    raise last_exc


def _resolve_blueprint_stream_client(llm: Any) -> Any:
    stream_client = getattr(llm, "_client", None)
    if stream_client is not None:
        return stream_client
    deepseek_key = getattr(llm, "_deepseek_key", None)
    deepseek_base = getattr(llm, "_deepseek_base", None)
    if OpenAI is not None and deepseek_key and deepseek_base:
        return OpenAI(api_key=deepseek_key, base_url=deepseek_base)
    raise RuntimeError("Blueprint streaming client is unavailable")


def _generate_bullet_blueprint_impl(
    preprocessed_data: Any,
    writing_policy: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
    *,
    override_model: Optional[str] = None,
) -> Dict[str, Any]:
    tiered_keywords = extract_tiered_keywords(
        preprocessed_data,
        getattr(preprocessed_data, "language", "English"),
        getattr(preprocessed_data, "real_vocab", None),
    )
    l2_keywords = _derive_blueprint_l2_keywords(tiered_keywords)
    canonical_caps = _canonical_capabilities(preprocessed_data)
    attr_summary = _summarize_attributes(getattr(preprocessed_data, "attribute_data", {}))
    compliance = writing_policy.get("compliance_directives", {})
    human_insights = _truncate_insights(getattr(preprocessed_data, "raw_human_insights", ""))
    scenes = writing_policy.get("scene_priority", []) or []
    intent_nodes = (intent_graph or {}).get("intent_graph") if isinstance(intent_graph, dict) else intent_graph
    persona_notes = []
    if isinstance(intent_nodes, list):
        for node in intent_nodes[:5]:
            if not isinstance(node, dict):
                continue
            description = node.get("mini_brief") or node.get("scene")
            if description:
                persona_notes.append(description)
    audience_allocation = _build_audience_allocation_plan(preprocessed_data, writing_policy)
    suppressed_capabilities = sorted(
        {
            str(item).strip()
            for item in (
                list(writing_policy.get("suppressed_capabilities") or [])
                + [
                    spec_name
                    for spec_name, spec_value in (getattr(preprocessed_data, "capability_constraints", {}) or {}).items()
                    if spec_name in SUPPRESSED_CAPABILITY_TERMS
                    and (
                        (isinstance(spec_value, bool) and spec_value is False)
                        or str(spec_value).strip().lower() in {"false", "0", "no", "none", "not supported", "unsupported"}
                    )
                ]
            )
            if str(item).strip()
        }
    )

    request_payload = {
        "target_language": getattr(preprocessed_data, "language", "English"),
        "l2_keywords": l2_keywords[:20],
        "canonical_capabilities": canonical_caps[:8],
        "scenes": scenes[:6],
        "compliance_rules": compliance,
        "attributes": {k: attr_summary[k] for k in list(attr_summary.keys())[:20]},
        "raw_human_insights": human_insights,
        "persona_briefs": persona_notes,
        "keyword_routing": writing_policy.get("keyword_routing", {}),
        "bullet_slot_rules": writing_policy.get("bullet_slot_rules", {}),
        "retention_strategy": writing_policy.get("retention_strategy", {}),
        "recording_mode_guidance": writing_policy.get("recording_mode_guidance", {}),
        "copy_contracts": writing_policy.get("copy_contracts", {}),
        "feedback_context": getattr(preprocessed_data, "feedback_context", {}) or {},
        "audience_allocation": audience_allocation,
        "suppressed_capabilities": suppressed_capabilities,
        "_request_timeout_seconds": 45 if override_model == "deepseek-reasoner" else 90,
        "_disable_fallback": bool(override_model == "deepseek-reasoner"),
    }

    system_prompt = (
        "You are Node 0, the Dynamic Blueprint Strategist for Amazon listings. "
        "You receive exhaustive Canonical English data and must plan exactly five bullet slots. "
        "Rules:\n"
        "1. You have many insights but ONLY 5 bullets. Bundle related specs + accessories into cohesive themes.\n"
        "2. Every high-importance trade-off or warning from raw_human_insights MUST be explicitly assigned to a bullet.\n"
        "2b. Unsupported or negative capability facts (for example no stabilization / not waterproof) may appear in ONLY ONE bullet slot. "
        "Choose the single best-fit slot for each such limitation, usually B4 guidance, and do not repeat the same limitation elsewhere.\n"
        "3. Reserve traffic head terms for the Title. Bullets should prioritize conversion-intent L2 terms and buying triggers.\n"
        "4. Map each bullet to concrete mandatory elements (facts, trade-offs, accessories, personas, proof angles) so downstream writers cannot ignore them.\n"
        "5. Every bullet must name a persona, pain point, buying_trigger, and proof_angle.\n"
        "6. If feedback_context provides organic_core or sp_intent keywords, preserve organic_core traffic anchors and translate sp_intent into scene-specific bullet themes.\n"
        "6b. Treat bullet_slot_rules as hard slot contracts. B1 protects hero conversion assets, B2 translates numeric proof into outcome, "
        "B3 expands new intent scenes, B4 handles best-use guidance, and B5 closes with package trust.\n"
        "6c. Do not leave any slot ending in an unfinished clause, hanging connector, or vague warning. Every slot must feel publishable.\n"
        "6d. Treat recording_mode_guidance as a hard truth contract. If 1080P is the preferred stabilization mode, route bike/helmet/motion scenes there. "
        "If 4K or 5K are marked detail-first or stabilization-discouraged, reserve them for travel/detail/static framing instead of smooth-motion promises.\n"
        "6e. Treat copy_contracts as hard production rules: B1-B3 must protect top conversion slots, every slot needs a clear primary keyword or capability anchor, "
        "and the bullet plan should avoid repetitive weak openers or generic sentence templates across languages.\n"
        f"6f. {_build_audience_allocation_prompt(audience_allocation)}\n"
        "7. Output strict JSON: {\"bullets\": [{\"bullet_index\": 1-5, \"theme\": str, "
        "\"assigned_l2_keywords\": [..], \"mandatory_elements\": [..], \"scenes\": [..], "
        "\"capabilities\": [..], \"accessories\": [..], \"persona\": str, \"pain_point\": str, "
        "\"buying_trigger\": str, \"proof_angle\": str, \"priority\": \"P0|P1|P2\", \"slot_directive\": str}]}."
    )

    llm = get_llm_client()
    stream_client = _resolve_blueprint_stream_client(llm)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False)},
    ]
    try:
        response = _call_blueprint_llm(
            stream_client,
            messages,
            int(request_payload.get("_request_timeout_seconds") or 30),
            None,
            [],
        )
        configured_model = (
            getattr(stream_client, "_last_blueprint_model", "")
            or (getattr(llm, "response_metadata", {}) or {}).get("configured_model")
            or BLUEPRINT_PRIMARY_MODEL
        )
        if hasattr(llm, "_record_response_meta"):
            llm._record_response_meta(  # type: ignore[attr-defined]
                endpoint="chat.completions",
                wire_api="chat/completions",
                response_data={"model": configured_model},
                latency_ms=None,
                success=bool(response),
                error="" if response else "empty_content",
                configured_model=configured_model,
            )
        blueprint = _scrub_suppressed_blueprint_content(
            _dedupe_negative_constraint_blueprint_content(
                _parse_llm_blueprint(response or ""),
                suppressed_capabilities,
            ),
            suppressed_capabilities,
        )
    except (LLMClientUnavailable, ValueError, json.JSONDecodeError) as exc:
        error = RuntimeError(f"Bullet blueprint generation failed: {exc}")
        setattr(
            error,
            "debug_context",
            {
                "stage": "bullet_blueprint",
                "field": "bullet_blueprint",
                "system_prompt": system_prompt,
                "request_payload": {
                    "field": "bullet_blueprint",
                    "override_model": override_model or "",
                    "payload": request_payload,
                },
                "llm_response_meta": (getattr(llm, "response_metadata", {}) or {}),
                "error": str(exc),
            },
        )
        raise error from exc
    except Exception as exc:
        error = RuntimeError(f"Bullet blueprint generation failed: {exc}")
        setattr(
            error,
            "debug_context",
            {
                "stage": "bullet_blueprint",
                "field": "bullet_blueprint",
                "system_prompt": system_prompt,
                "request_payload": {
                    "field": "bullet_blueprint",
                    "override_model": override_model or "",
                    "payload": request_payload,
                },
                "llm_response_meta": (getattr(llm, "response_metadata", {}) or {}),
                "error": str(exc),
            },
        )
        raise error from exc

    blueprint["created_at"] = datetime.now(timezone.utc).isoformat()
    blueprint["llm_model"] = (
        (getattr(llm, "response_metadata", {}) or {}).get("configured_model")
        or getattr(llm, "active_model", "offline")
    )
    blueprint["audience_allocation"] = {
        entry["slot"]: {
            "group": entry["group"],
            "label": entry["label"],
            "focus": entry["focus"],
        }
        for entry in audience_allocation
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(blueprint, fp, ensure_ascii=False, indent=2)
    return blueprint


def generate_bullet_blueprint(
    preprocessed_data: Any,
    writing_policy: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    return _generate_bullet_blueprint_impl(
        preprocessed_data=preprocessed_data,
        writing_policy=writing_policy,
        intent_graph=intent_graph,
        output_path=output_path,
    )


def generate_bullet_blueprint_r1(
    preprocessed_data: Any,
    writing_policy: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Experimental R1 blueprint path; main production workflow should keep using V3."""
    return _generate_bullet_blueprint_impl(
        preprocessed_data=preprocessed_data,
        writing_policy=writing_policy,
        intent_graph=intent_graph,
        output_path=output_path,
        override_model="deepseek-reasoner",
    )


def generate_blueprint_r1(
    preprocessed_data: Any,
    writing_policy: Dict[str, Any],
    intent_graph: Optional[Dict[str, Any]] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Backward-compatible alias for the experimental R1 blueprint path."""
    return generate_bullet_blueprint_r1(
        preprocessed_data=preprocessed_data,
        writing_policy=writing_policy,
        intent_graph=intent_graph,
        output_path=output_path,
    )
