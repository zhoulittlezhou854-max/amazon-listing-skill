#!/usr/bin/env python3
"""Node 0 - Dynamic Bullet Blueprint generator."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from modules.llm_client import get_llm_client, LLMClientUnavailable
from modules.keyword_utils import extract_tiered_keywords
from modules.language_utils import english_capability_label, canonicalize_capability

MAX_INSIGHT_CHARS = 4000


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


def generate_bullet_blueprint(preprocessed_data: Any,
                              writing_policy: Dict[str, Any],
                              intent_graph: Optional[Dict[str, Any]] = None,
                              output_path: Optional[str] = None) -> Dict[str, Any]:
    tiered_keywords = extract_tiered_keywords(
        preprocessed_data,
        getattr(preprocessed_data, "language", "English"),
        getattr(preprocessed_data, "real_vocab", None),
    )
    l2_keywords = tiered_keywords.get("l2", []) or []
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

    payload = {
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
    }

    system_prompt = (
        "You are Node 0, the Dynamic Blueprint Strategist for Amazon listings. "
        "You receive exhaustive Canonical English data and must plan exactly five bullet slots. "
        "Rules:\n"
        "1. You have many insights but ONLY 5 bullets. Bundle related specs + accessories into cohesive themes.\n"
        "2. Every high-importance trade-off or warning from raw_human_insights MUST be explicitly assigned to a bullet.\n"
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
        "7. Output strict JSON: {\"bullets\": [{\"bullet_index\": 1-5, \"theme\": str, "
        "\"assigned_l2_keywords\": [..], \"mandatory_elements\": [..], \"scenes\": [..], "
        "\"capabilities\": [..], \"accessories\": [..], \"persona\": str, \"pain_point\": str, "
        "\"buying_trigger\": str, \"proof_angle\": str, \"priority\": \"P0|P1|P2\", \"slot_directive\": str}]}."
    )

    llm = get_llm_client()
    try:
        response = llm.generate_text(system_prompt, payload, temperature=0.15)
        blueprint = _parse_llm_blueprint(response or "")
    except (LLMClientUnavailable, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Bullet blueprint generation failed: {exc}") from exc

    blueprint["created_at"] = datetime.utcnow().isoformat()
    blueprint["llm_model"] = getattr(llm, "active_model", "offline")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(blueprint, fp, ensure_ascii=False, indent=2)
    return blueprint
