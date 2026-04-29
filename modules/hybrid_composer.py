from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from modules import image_handoff, report_builder, report_generator, risk_check, scoring
from modules.copy_generation import _build_bullet_packet, _build_slot_quality_packet
from modules.field_provenance import build_field_candidate, select_launch_eligible_field
from modules.hybrid_optimizer import (
    LISTING_L2_COVERAGE_THRESHOLD,
    analyze_listing_l2_coverage,
    repair_hybrid_bullets_for_l2,
)
from modules.keyword_reconciliation import reconcile_keyword_assignments


DEFAULT_HYBRID_SELECTION_POLICY: Dict[str, str] = {
    "title": "version_a",
    "bullets": "version_b",
    "description": "version_a",
    "faq": "version_a",
    "search_terms": "version_a",
    "aplus_content": "version_a",
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_text(value: Any) -> str:
    return _NON_ALNUM_RE.sub(" ", str(value or "").lower()).strip()


def _output_text(value: Any) -> str:
    return str(value or "").strip()


def _metadata_key(keyword: Any) -> str:
    return " ".join(str(keyword or "").strip().lower().split())


def _merge_keyword_metadata(target: Dict[str, Dict[str, Any]], row: Dict[str, Any]) -> None:
    keyword = str((row or {}).get("keyword") or (row or {}).get("normalized_keyword") or "").strip()
    key = _metadata_key(keyword)
    if not key:
        return
    merged = dict(row or {})
    merged["keyword"] = keyword
    existing = target.get(key) or {}
    combined = dict(existing)
    for field, value in merged.items():
        if value in (None, "", [], {}):
            continue
        combined.setdefault(field, value)
    target[key] = combined


def _group_keyword_assignments(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        keyword = str((row or {}).get("keyword") or "").strip()
        key = _metadata_key((row or {}).get("normalized_keyword") or keyword)
        if not key:
            continue
        record = grouped.setdefault(key, {**row, "keyword": keyword, "assigned_fields": []})
        for field in (row or {}).get("assigned_fields") or []:
            if field not in record["assigned_fields"]:
                record["assigned_fields"].append(field)
    return list(grouped.values())


def _reconcile_hybrid_keywords(
    hybrid_copy: Dict[str, Any],
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
    writing_policy: Dict[str, Any],
) -> Dict[str, Any]:
    metadata: Dict[str, Dict[str, Any]] = {}
    for source in (version_a, version_b):
        reconciliation = source.get("keyword_reconciliation") or {}
        for row in reconciliation.get("assignments") or []:
            _merge_keyword_metadata(metadata, row)
        for row in (source.get("decision_trace") or {}).get("keyword_assignments") or []:
            _merge_keyword_metadata(metadata, row)
    for row in (writing_policy or {}).get("keyword_metadata") or []:
        _merge_keyword_metadata(metadata, row)

    reconciliation = reconcile_keyword_assignments(hybrid_copy, metadata)
    assignments = _group_keyword_assignments(reconciliation.get("assignments") or [])
    return {**reconciliation, "assignments": assignments}


def _slot_aliases(slot: str) -> set[str]:
    slot = str(slot or "").strip().upper()
    normalized = slot.lower()
    if slot.startswith("BULLET_"):
        matches = re.fullmatch(r"bullet_(\d+)", normalized)
        if matches:
            index = matches.group(1)
            return {normalized, f"b{index}", f"bullet_b{index}"}
    if not slot.startswith("B"):
        return {normalized} if slot else set()
    try:
        index = int(slot[1:])
    except ValueError:
        return {slot.lower()}
    return {slot.lower(), f"bullet_b{index}"}


def _extract_blocked_bullet_slots(version_risk: Dict[str, Any]) -> set[str]:
    blocked: set[str] = set()
    for field in version_risk.get("blocking_fields") or []:
        normalized = str(field or "").strip().lower()
        if normalized.startswith("bullet_b"):
            blocked.add(f"B{normalized.removeprefix('bullet_b')}")
        elif normalized.startswith("bullet_") and normalized.removeprefix("bullet_").isdigit():
            blocked.add(f"B{normalized.removeprefix('bullet_')}")
        elif normalized.startswith("b") and normalized[1:].isdigit():
            blocked.add(normalized.upper())

    truth = version_risk.get("truth_consistency") or {}
    for issue in truth.get("issues") or []:
        field = str(issue.get("field") or "").strip().lower()
        if field.startswith("bullet_b"):
            blocked.add(f"B{field.removeprefix('bullet_b')}")
        elif field.startswith("b") and field[1:].isdigit():
            blocked.add(field.upper())
    return blocked


def _extract_fallback_bullet_slots(version_metadata: Dict[str, Any]) -> set[str]:
    slots: set[str] = set()
    for field in version_metadata.get("visible_llm_fallback_fields") or []:
        normalized = str(field or "").strip().lower()
        if normalized.startswith("bullet_b"):
            slots.add(f"B{normalized.removeprefix('bullet_b')}")
        elif normalized.startswith("bullet_") and normalized.removeprefix("bullet_").isdigit():
            slots.add(f"B{normalized.removeprefix('bullet_')}")
        elif normalized.startswith("b") and normalized[1:].isdigit():
            slots.add(normalized.upper())
    return slots


def _extract_scrub_integrity_bullet_slots(audit_trail: Any) -> set[str]:
    slots: set[str] = set()
    for entry in audit_trail or []:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field") or "").strip().lower()
        if not field.startswith("bullet_b"):
            continue
        reason = str(entry.get("reason") or "").strip().lower()
        action = str(entry.get("action") or "").strip().lower()
        if not field.removeprefix("bullet_b").isdigit():
            continue
        if reason.startswith("forbidden_visible_terms") or (
            action == "delete" and reason == "forbidden_visible_terms_scrub"
        ):
            slots.add(f"B{field.removeprefix('bullet_b')}")
    return slots


def _build_slot_l2_targets(*payloads: Dict[str, Any]) -> Dict[str, list[str]]:
    slot_targets: Dict[str, list[str]] = {}
    for payload in payloads:
        rows = ((payload.get("decision_trace") or {}).get("keyword_assignments") or [])
        for row in rows:
            if str(row.get("tier") or "").upper() != "L2":
                continue
            keyword = str(row.get("keyword") or "").strip()
            if not keyword:
                continue
            for field in row.get("assigned_fields") or []:
                aliases = _slot_aliases(field)
                for alias in aliases:
                    if alias.startswith("b") and alias[1:].isdigit():
                        slot = alias.upper()
                        bucket = slot_targets.setdefault(slot, [])
                        if keyword not in bucket:
                            bucket.append(keyword)


    return slot_targets


def _bullet_has_slot_targets(bullet: Any, slot_targets: list[str]) -> bool:
    if not slot_targets:
        return True
    normalized_bullet = _normalize_text(bullet)
    return any(_normalize_text(keyword) in normalized_bullet for keyword in slot_targets)


def _normalize_assigned_field(field: Any) -> str:
    value = str(field or "").strip().lower()
    if value.startswith("bullet_b") and value.removeprefix("bullet_b").isdigit():
        return f"B{value.removeprefix('bullet_b')}"
    if value.startswith("bullet_") and value.removeprefix("bullet_").isdigit():
        return f"B{value.removeprefix('bullet_')}"
    if value.startswith("b") and value[1:].isdigit():
        return value.upper()
    return value


def _slot_quality_is_unhealthy(slot_quality: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(slot_quality, dict) or not slot_quality:
        return False
    if slot_quality.get("fluency_pass") is False:
        return True
    if slot_quality.get("unsupported_policy_pass") is False:
        return True
    unhealthy_issues = {
        "missing_header_or_em_dash",
        "header_body_rupture",
        "dash_tail_without_predicate",
        "repeated_word_root",
        "unsupported_capability_negative_literal",
    }
    for issue in slot_quality.get("issues") or []:
        normalized = str(issue or "").strip()
        if normalized in unhealthy_issues or normalized.startswith("slot_contract_failed:"):
            return True
    return False


def _find_slot_payload_row(rows: Any, slot: str, idx: Optional[int] = None) -> Optional[Dict[str, Any]]:
    slot_aliases = _slot_aliases(slot)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        row_aliases = _slot_aliases(row.get("slot"))
        if slot_aliases & row_aliases:
            return deepcopy(row)
    if isinstance(rows, list) and idx is not None and 0 <= idx < len(rows) and isinstance(rows[idx], dict):
        return deepcopy(rows[idx])
    return None


def select_source_for_bullet_slot(
    *,
    slot: str,
    bullet_a: Any,
    bullet_b: Any,
    meta_a: Dict[str, Any],
    risk_a: Dict[str, Any],
    meta_b: Dict[str, Any],
    risk_b: Dict[str, Any],
    slot_l2_targets: list[str],
    audit_a: Optional[Any] = None,
    audit_b: Optional[Any] = None,
    quality_a: Optional[Dict[str, Any]] = None,
    quality_b: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    slot = str(slot).upper()
    blocked_a = _extract_blocked_bullet_slots(risk_a)
    blocked_b = _extract_blocked_bullet_slots(risk_b)
    fallback_a = _extract_fallback_bullet_slots(meta_a)
    fallback_b = _extract_fallback_bullet_slots(meta_b)
    scrubbed_a = _extract_scrub_integrity_bullet_slots(audit_a)
    scrubbed_b = _extract_scrub_integrity_bullet_slots(audit_b)

    disqualified = []
    soft_signals: list[str] = []
    eligible = {}
    for version, bullet, blocked, fallback in (
        ("version_a", bullet_a, blocked_a, fallback_a),
        ("version_b", bullet_b, blocked_b, fallback_b),
    ):
        if slot in fallback:
            disqualified.append({"version": version, "reason": f"fallback_marked:{slot.lower()}"})
            eligible[version] = False
            continue
        if slot in blocked:
            disqualified.append({"version": version, "reason": f"risk_blocked:{slot.lower()}"})
            eligible[version] = False
            continue
        eligible[version] = True

    if not eligible.get("version_a") and not eligible.get("version_b"):
        return {
            "source_version": None,
            "selection_reason": "no_eligible_source",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }
    if eligible.get("version_a") and not eligible.get("version_b"):
        reason = next((row["reason"] for row in disqualified if row["version"] == "version_b"), "single_eligible_source")
        return {
            "source_version": "version_a",
            "selection_reason": "version_b_fallback_marked" if reason.startswith("fallback_marked:") else "version_b_risk_blocked",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }
    if eligible.get("version_b") and not eligible.get("version_a"):
        reason = next((row["reason"] for row in disqualified if row["version"] == "version_a"), "single_eligible_source")
        return {
            "source_version": "version_b",
            "selection_reason": "version_a_fallback_marked" if reason.startswith("fallback_marked:") else "version_a_risk_blocked",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }

    if slot in scrubbed_b and slot not in scrubbed_a:
        soft_signals.append("version_b_scrub_integrity_flag")
        return {
            "source_version": "version_a",
            "selection_reason": "version_b_scrub_integrity_flag",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }
    if slot in scrubbed_a and slot not in scrubbed_b:
        soft_signals.append("version_a_scrub_integrity_flag")
        return {
            "source_version": "version_b",
            "selection_reason": "version_a_scrub_integrity_flag",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }

    b_quality_failed = _slot_quality_is_unhealthy(quality_b)
    a_quality_failed = _slot_quality_is_unhealthy(quality_a)
    if b_quality_failed and not a_quality_failed:
        soft_signals.append("version_b_quality_failed")
        return {
            "source_version": "version_a",
            "selection_reason": "version_b_quality_failed",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }
    if a_quality_failed and not b_quality_failed:
        soft_signals.append("version_a_quality_failed")
        return {
            "source_version": "version_b",
            "selection_reason": "version_a_quality_failed",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }

    a_has_l2 = _bullet_has_slot_targets(bullet_a, slot_l2_targets)
    b_has_l2 = _bullet_has_slot_targets(bullet_b, slot_l2_targets)
    if a_has_l2 and not b_has_l2:
        soft_signals.append("version_b_missing_l2")
    if b_has_l2 and not a_has_l2:
        return {
            "source_version": "version_b",
            "selection_reason": "slot_default_preference",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }
    return {
        "source_version": "version_b",
        "selection_reason": "slot_default_preference",
        "disqualified": disqualified,
        "soft_signals": soft_signals,
    }


def assess_field_eligibility(
    field: str,
    version_metadata: Dict[str, Any],
    version_risk: Dict[str, Any],
) -> tuple[bool, str]:
    fallback_fields = {str(item).strip() for item in (version_metadata.get("visible_llm_fallback_fields") or []) if str(item).strip()}
    if field in fallback_fields:
        return False, f"fallback_marked:{field}"

    blocking_fields = {str(item).strip() for item in (version_risk.get("blocking_fields") or []) if str(item).strip()}
    if field in blocking_fields:
        return False, f"risk_blocked:{field}"

    return True, ""


def select_source_for_field(
    field: str,
    meta_a: Dict[str, Any],
    risk_a: Dict[str, Any],
    meta_b: Dict[str, Any],
    risk_b: Dict[str, Any],
) -> Dict[str, Any]:
    default_source = DEFAULT_HYBRID_SELECTION_POLICY.get(field, "version_a")
    evaluations = []
    for version, meta, risk in (
        ("version_a", meta_a, risk_a),
        ("version_b", meta_b, risk_b),
    ):
        eligible, reason = assess_field_eligibility(field, meta, risk)
        evaluations.append(
            {
                "version": version,
                "eligible": eligible,
                "reason": reason,
            }
        )

    eligible_versions = [entry["version"] for entry in evaluations if entry["eligible"]]
    disqualified = [
        {"version": entry["version"], "reason": entry["reason"]}
        for entry in evaluations
        if not entry["eligible"] and entry["reason"]
    ]
    if not eligible_versions:
        return {
            "source_version": None,
            "selection_reason": "no_eligible_source",
            "disqualified": disqualified,
        }
    if len(eligible_versions) == 1:
        chosen = eligible_versions[0]
        other = next((entry for entry in disqualified if entry["version"] != chosen), None)
        reason_map = {
            "fallback_marked": f"{other['version']}_fallback_marked" if other else "single_eligible_source",
            "risk_blocked": f"{other['version']}_risk_blocked" if other else "single_eligible_source",
        }
        selection_reason = "single_eligible_source"
        if other:
            if other["reason"].startswith("fallback_marked:"):
                selection_reason = reason_map["fallback_marked"]
            elif other["reason"].startswith("risk_blocked:"):
                selection_reason = reason_map["risk_blocked"]
        return {
            "source_version": chosen,
            "selection_reason": selection_reason,
            "disqualified": disqualified,
        }
    return {
        "source_version": default_source,
        "selection_reason": "default_preference",
        "disqualified": disqualified,
    }


def _build_source_trace(
    field_decisions: Dict[str, Dict[str, Any]],
    bullet_decisions: list[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "title": field_decisions["title"],
        "bullets": bullet_decisions,
        "description": field_decisions["description"],
        "faq": field_decisions["faq"],
        "search_terms": field_decisions["search_terms"],
        "aplus_content": field_decisions["aplus_content"],
    }


def _build_hybrid_shadow_slot_payload(
    *,
    slot: str,
    idx: int,
    source_version: str,
    chosen_bullet: Any,
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not chosen_bullet or not source_version:
        return None, None

    source_payload = version_a if source_version == "version_a" else version_b
    packet = _find_slot_payload_row(source_payload.get("bullet_packets"), slot, idx)
    if packet is None:
        trace_entry = _find_slot_payload_row(
            (source_payload.get("decision_trace") or {}).get("bullet_trace"),
            slot,
            idx,
        ) or {}
        packet = _build_bullet_packet(slot, str(chosen_bullet), trace_entry=trace_entry)
    packet["slot"] = slot

    slot_quality = _find_slot_payload_row(source_payload.get("slot_quality_packets"), slot, idx)
    if slot_quality is None:
        slot_quality = _build_slot_quality_packet(packet)
    slot_quality["slot"] = slot
    return packet, slot_quality


def _recompute_visible_fallback_fields(
    field_sources: Dict[str, Any],
    meta_a: Dict[str, Any],
    meta_b: Dict[str, Any],
) -> list[str]:
    fallback_a = {str(item).strip() for item in (meta_a.get("visible_llm_fallback_fields") or []) if str(item).strip()}
    fallback_b = {str(item).strip() for item in (meta_b.get("visible_llm_fallback_fields") or []) if str(item).strip()}
    selected: list[str] = []
    for field, source in field_sources.items():
        if field == "bullets":
            continue
        fallback_pool = fallback_a if source == "version_a" else fallback_b
        if field in fallback_pool and field not in selected:
            selected.append(field)
    return selected


def compose_hybrid_listing(
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
    output_dir: Path,
    selection_policy: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    policy = {**DEFAULT_HYBRID_SELECTION_POLICY, **(selection_policy or {})}
    output_dir = Path(output_dir)
    risk_a = version_a.get("risk_report") or {}
    risk_b = version_b.get("risk_report") or {}
    meta_a = version_a.get("metadata") or {}
    meta_b = version_b.get("metadata") or {}
    slot_l2_targets = _build_slot_l2_targets(version_a, version_b)

    field_decisions: Dict[str, Dict[str, Any]] = {}
    field_values: Dict[str, Any] = {}
    field_provenance: Dict[str, Dict[str, Any]] = {}
    no_eligible_source: list[str] = []
    degraded_reasons: list[str] = []
    for field_name in DEFAULT_HYBRID_SELECTION_POLICY:
        if field_name == "description":
            candidates = [
                build_field_candidate(field_name, version_a.get(field_name), "version_a", meta_a, risk_a),
                build_field_candidate(field_name, version_b.get(field_name), "version_b", meta_b, risk_b),
            ]
            selected_candidate = select_launch_eligible_field(field_name, candidates)
            field_provenance[field_name] = {**deepcopy(selected_candidate), "candidates": candidates}
            if selected_candidate.get("eligibility") == "launch_eligible":
                decision = {
                    "source_version": selected_candidate.get("source_version"),
                    "selection_reason": f"{selected_candidate.get('provenance_tier')}_selected",
                    "disqualified": [
                        {
                            "version": candidate.get("source_version"),
                            "reason": ",".join(candidate.get("blocking_reasons") or []) or candidate.get("eligibility"),
                        }
                        for candidate in candidates
                        if candidate.get("eligibility") != "launch_eligible"
                    ],
                }
            else:
                decision = {
                    "source_version": None,
                    "selection_reason": "no_eligible_source",
                    "disqualified": [
                        {
                            "version": candidate.get("source_version"),
                            "reason": ",".join(candidate.get("blocking_reasons") or []) or candidate.get("eligibility"),
                        }
                        for candidate in candidates
                    ],
                }
        else:
            decision = select_source_for_field(field_name, meta_a, risk_a, meta_b, risk_b)
        field_decisions[field_name] = decision
        source_version = decision["source_version"]
        if source_version is None:
            field_values[field_name] = None
            no_eligible_source.append(field_name)
            continue
        source_payload = version_a if source_version == "version_a" else version_b
        field_values[field_name] = deepcopy(source_payload.get(field_name))

    title_source = field_decisions["title"]["source_version"] or policy.get("title", "version_a")
    search_terms_source = field_decisions["search_terms"]["source_version"] or policy.get("search_terms", "version_a")

    bullet_decisions: list[Dict[str, Any]] = []
    selected_bullets: list[Any] = []
    selected_bullet_packets: list[Dict[str, Any]] = []
    selected_slot_quality_packets: list[Dict[str, Any]] = []
    bullets_a = list(version_a.get("bullets") or [])
    bullets_b = list(version_b.get("bullets") or [])
    for idx in range(max(len(bullets_a), len(bullets_b))):
        slot = f"B{idx + 1}"
        decision = select_source_for_bullet_slot(
            slot=slot,
            bullet_a=bullets_a[idx] if idx < len(bullets_a) else None,
            bullet_b=bullets_b[idx] if idx < len(bullets_b) else None,
            meta_a=meta_a,
            risk_a=risk_a,
            meta_b=meta_b,
            risk_b=risk_b,
            slot_l2_targets=slot_l2_targets.get(slot, []),
            audit_a=version_a.get("audit_trail"),
            audit_b=version_b.get("audit_trail"),
            quality_a=_find_slot_payload_row(version_a.get("slot_quality_packets"), slot, idx),
            quality_b=_find_slot_payload_row(version_b.get("slot_quality_packets"), slot, idx),
        )
        bullet_source = decision["source_version"] or policy.get("bullets", "version_b")
        chosen_bullet = None
        if bullet_source == "version_a":
            if idx < len(bullets_a):
                chosen_bullet = bullets_a[idx]
            elif idx < len(bullets_b):
                chosen_bullet = bullets_b[idx]
                bullet_source = "version_b"
                decision = {**decision, "selection_reason": "degraded_fallback_to_b", "degraded_mode": True}
                degraded_reasons.append(f"B{idx + 1}:degraded_fallback_to_b")
        else:
            if idx < len(bullets_b):
                chosen_bullet = bullets_b[idx]
            elif idx < len(bullets_a):
                chosen_bullet = bullets_a[idx]
                bullet_source = "version_a"
                decision = {**decision, "selection_reason": "degraded_fallback_to_a", "degraded_mode": True}
                degraded_reasons.append(f"B{idx + 1}:degraded_fallback_to_a")
        if chosen_bullet is not None:
            selected_bullets.append(deepcopy(chosen_bullet))
            packet, slot_quality = _build_hybrid_shadow_slot_payload(
                slot=slot,
                idx=idx,
                source_version=bullet_source,
                chosen_bullet=chosen_bullet,
                version_a=version_a,
                version_b=version_b,
            )
            if packet is not None:
                selected_bullet_packets.append(packet)
            if slot_quality is not None:
                selected_slot_quality_packets.append(slot_quality)
        bullet_decisions.append(
            {
                "slot": slot,
                "source_version": bullet_source,
                "selection_reason": decision["selection_reason"],
                "disqualified": deepcopy(decision["disqualified"]),
                "soft_signals": deepcopy(decision.get("soft_signals") or []),
                "degraded_mode": bool(decision.get("degraded_mode")),
            }
        )

    unique_bullet_sources = {row["source_version"] for row in bullet_decisions if row.get("source_version")}
    bullet_source = next(iter(unique_bullet_sources)) if len(unique_bullet_sources) == 1 else "mixed"
    field_values["bullets"] = selected_bullets if selected_bullets else field_values.get("bullets")

    field_sources = {field: (decision["source_version"] or None) for field, decision in field_decisions.items()}
    field_sources["bullets"] = bullet_source

    base_metadata = deepcopy((version_a if title_source == "version_a" else version_b).get("metadata") or {})
    recomputed_visible_fallbacks = _recompute_visible_fallback_fields(field_sources, meta_a, meta_b)
    hybrid_copy: Dict[str, Any] = {
        "title": _output_text(field_values.get("title")),
        "bullets": list(field_values.get("bullets") or []) if field_values.get("bullets") is not None else None,
        "bullet_packets": selected_bullet_packets,
        "slot_quality_packets": selected_slot_quality_packets,
        "description": _output_text(field_values.get("description")),
        "faq": list(field_values.get("faq") or []) if field_values.get("faq") is not None else None,
        "search_terms": list(field_values.get("search_terms") or []) if field_values.get("search_terms") is not None else None,
        "aplus_content": _output_text(field_values.get("aplus_content")),
        "metadata": {
            **base_metadata,
            "visible_copy_mode": "hybrid_postselect",
            "visible_copy_status": "hybrid_mixed",
            "hybrid_sources": field_sources,
            "visible_llm_fallback_fields": recomputed_visible_fallbacks,
            "field_provenance": field_provenance,
            "degraded_mode": bool(degraded_reasons),
            "degraded_reasons": degraded_reasons,
        },
    }
    if no_eligible_source:
        hybrid_copy["_no_eligible_source"] = no_eligible_source

    hybrid_copy["source_trace"] = _build_source_trace(field_decisions, bullet_decisions)
    hybrid_copy["decision_trace"] = {
        "bullet_trace": [
            deepcopy(trace_row)
            for decision in bullet_decisions
            for trace_row in ((version_a if decision["source_version"] == "version_a" else version_b).get("decision_trace", {}).get("bullet_trace", []) or [])
            if str(trace_row.get("slot") or "").upper() == decision["slot"]
        ],
        "search_terms_trace": deepcopy((version_b if search_terms_source == "version_b" else version_a).get("decision_trace", {}).get("search_terms_trace", {})),
        "keyword_assignments": [],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "generated_copy.json").write_text(json.dumps(hybrid_copy, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "source_trace.json").write_text(json.dumps(hybrid_copy["source_trace"], ensure_ascii=False, indent=2), encoding="utf-8")
    return hybrid_copy


def rebuild_hybrid_decision_trace(
    hybrid_copy: Dict[str, Any],
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
) -> Dict[str, Any]:
    source_trace = hybrid_copy.get("source_trace") or {}
    field_sources = ((hybrid_copy.get("metadata") or {}).get("hybrid_sources") or {})
    merged: list[Dict[str, Any]] = []
    seen: dict[tuple[str, str], Dict[str, Any]] = {}

    def _source_payload(name: str) -> Dict[str, Any]:
        return version_a if name == "version_a" else version_b

    def _ingest(source_version: str, allowed_fields: set[str]) -> None:
        payload = _source_payload(source_version)
        rows = ((payload.get("decision_trace") or {}).get("keyword_assignments") or [])
        normalized_allowed = {_normalize_assigned_field(field) for field in allowed_fields}
        for row in rows:
            assigned = []
            for field in row.get("assigned_fields") or []:
                normalized_field = _normalize_assigned_field(field)
                if normalized_field in normalized_allowed:
                    assigned.append(normalized_field)
                    if normalized_field.startswith("B") and normalized_field[1:].isdigit():
                        legacy_alias = f"bullet_{normalized_field[1:]}"
                        if legacy_alias not in assigned:
                            assigned.append(legacy_alias)
            if not assigned:
                continue
            keyword = str(row.get("keyword") or "").strip()
            if not keyword:
                continue
            key = (keyword.lower(), source_version)
            existing = seen.get(key)
            if existing:
                for field in assigned:
                    if field not in existing["assigned_fields"]:
                        existing["assigned_fields"].append(field)
                continue
            record = {
                "keyword": keyword,
                "tier": row.get("tier"),
                "source_type": row.get("source_type"),
                "search_volume": row.get("search_volume"),
                "assigned_fields": assigned,
                "source_version": source_version,
            }
            seen[key] = record
            merged.append(record)

    title_source = field_sources.get("title", "version_a")
    search_terms_source = field_sources.get("search_terms", "version_a")
    _ingest(title_source, {"title"})
    for bullet_row in source_trace.get("bullets") or []:
        source_version = bullet_row.get("source_version")
        slot = str(bullet_row.get("slot") or "").upper()
        if not source_version or not slot:
            continue
        index = slot[1:] if slot.startswith("B") else ""
        allowed = {slot}
        if index.isdigit():
            allowed.add(f"bullet_b{index}")
        _ingest(source_version, allowed)
    _ingest(search_terms_source, {"search_terms"})

    rebuilt = {
        "bullet_trace": deepcopy(hybrid_copy.get("decision_trace", {}).get("bullet_trace", [])),
        "search_terms_trace": deepcopy(hybrid_copy.get("decision_trace", {}).get("search_terms_trace", {})),
        "keyword_assignments": merged,
    }
    hybrid_copy["decision_trace"] = rebuilt
    return rebuilt


def _collect_hybrid_l2_keywords(hybrid_copy: Dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    rows = ((hybrid_copy.get("decision_trace") or {}).get("keyword_assignments") or [])
    for row in rows:
        if str(row.get("tier") or "").upper() != "L2":
            continue
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        assigned_fields = {str(field).strip().lower() for field in (row.get("assigned_fields") or []) if str(field).strip()}
        if not any(field.startswith("b") or field.startswith("bullet_b") for field in assigned_fields):
            continue
        if keyword not in keywords:
            keywords.append(keyword)
    return keywords


def _build_hybrid_l2_slot_targets(hybrid_copy: Dict[str, Any]) -> dict[str, list[str]]:
    slot_targets: dict[str, list[str]] = {}
    rows = ((hybrid_copy.get("decision_trace") or {}).get("keyword_assignments") or [])
    for row in rows:
        if str(row.get("tier") or "").upper() != "L2":
            continue
        keyword = str(row.get("keyword") or "").strip()
        if not keyword:
            continue
        for field in row.get("assigned_fields") or []:
            normalized = _normalize_assigned_field(field)
            if normalized.startswith("B") and normalized[1:].isdigit():
                bucket = slot_targets.setdefault(normalized, [])
                if keyword not in bucket:
                    bucket.append(keyword)
    return slot_targets


def _record_hybrid_repair_keyword_assignments(
    hybrid_copy: Dict[str, Any],
    repair_actions: list[Dict[str, Any]],
) -> None:
    decision_trace = hybrid_copy.setdefault("decision_trace", {})
    rows = decision_trace.setdefault("keyword_assignments", [])
    for action in repair_actions or []:
        keyword = str(action.get("keyword") or "").strip()
        slot = str(action.get("slot") or "").upper().strip()
        if not keyword or not slot.startswith("B") or not slot[1:].isdigit():
            continue
        alias = f"bullet_b{slot[1:]}"
        existing = next(
            (
                row for row in rows
                if str(row.get("keyword") or "").strip().lower() == keyword.lower()
                and str(row.get("source_version") or "").strip() == "hybrid_repair"
            ),
            None,
        )
        if existing is None:
            existing = {
                "keyword": keyword,
                "tier": "L2",
                "source_type": "hybrid_repair",
                "search_volume": None,
                "assigned_fields": [],
                "source_version": "hybrid_repair",
            }
            rows.append(existing)
        for field in (slot, alias):
            if field not in existing["assigned_fields"]:
                existing["assigned_fields"].append(field)


def build_hybrid_launch_decision(
    *,
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
    hybrid_copy: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: list[str] = []
    listing_status = ((risk_report.get("listing_status") or {}).get("status")) or ""
    if listing_status != "READY_FOR_LISTING":
        reasons.append("listing_not_ready")

    dimensions = scoring_results.get("dimensions") or {}
    a10 = ((dimensions.get("traffic") or {}).get("score")) or 0
    cosmo = ((dimensions.get("content") or {}).get("score")) or 0
    rufus = ((dimensions.get("conversion") or {}).get("score")) or 0
    fluency = ((dimensions.get("readability") or {}).get("score")) or 0
    scores = {
        "A10": a10,
        "COSMO": cosmo,
        "Rufus": rufus,
        "Fluency": fluency,
    }
    thresholds = {
        "A10": 80,
        "COSMO": 90,
        "Rufus": 90,
        "Fluency": 24,
    }
    if a10 < 80:
        reasons.append("a10_below_threshold")
    if cosmo < 90:
        reasons.append("cosmo_below_threshold")
    if rufus < 90:
        reasons.append("rufus_below_threshold")
    if fluency < 24:
        reasons.append("fluency_below_threshold")

    metadata = hybrid_copy.get("metadata") or {}
    if metadata.get("visible_llm_fallback_fields"):
        reasons.append("visible_fallback_present")
    if hybrid_copy.get("_no_eligible_source"):
        reasons.append("no_eligible_source_present")
    field_provenance = metadata.get("field_provenance") or {}
    if isinstance(field_provenance, dict):
        for field_name, record in field_provenance.items():
            if not isinstance(record, dict):
                continue
            tier = str(record.get("provenance_tier") or "").strip()
            reason_set = {str(reason) for reason in (record.get("blocking_reasons") or [])}
            if tier == "safe_fallback" or "fallback_not_launch_eligible" in reason_set:
                reasons.append(f"field_safe_fallback_not_launch_eligible:{field_name}")
            if tier == "unsafe_fallback" or "unsafe_fallback" in reason_set:
                reasons.append(f"field_unsafe_fallback:{field_name}")
            if tier == "unavailable" or "field_unavailable" in reason_set:
                reasons.append(f"field_unavailable:{field_name}")

    score_gate_passed = (
        a10 >= thresholds["A10"]
        and cosmo >= thresholds["COSMO"]
        and rufus >= thresholds["Rufus"]
        and fluency >= thresholds["Fluency"]
    )
    passed = not reasons
    return {
        "passed": passed,
        "recommended_output": "hybrid" if passed and score_gate_passed else "version_a",
        "scores": scores,
        "thresholds": thresholds,
        "reasons": reasons,
    }


def finalize_hybrid_outputs(
    *,
    hybrid_copy: Dict[str, Any],
    version_a: Dict[str, Any],
    version_b: Dict[str, Any],
    writing_policy: Dict[str, Any],
    preprocessed_data: Any,
    output_dir: Path,
    language: str,
    intent_graph: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    rebuilt_trace = rebuild_hybrid_decision_trace(hybrid_copy, version_a, version_b)
    hybrid_copy["decision_trace"] = rebuilt_trace

    metadata = hybrid_copy.setdefault("metadata", {})
    metadata["visible_copy_status"] = "hybrid_mixed_reaudited"
    metadata["hybrid_generation_status"] = "reaudited"
    selected_versions = {field.get("source_version") for field in (hybrid_copy.get("source_trace") or {}).get("bullets") or [] if field.get("source_version")}
    selected_versions.add(((hybrid_copy.get("source_trace") or {}).get("title") or {}).get("source_version"))
    selected_versions.add(((hybrid_copy.get("source_trace") or {}).get("description") or {}).get("source_version"))
    selected_versions.discard(None)
    hybrid_copy["audit_trail"] = []
    for source_version in ["version_a", "version_b"]:
        if source_version not in selected_versions:
            continue
        payload = version_a if source_version == "version_a" else version_b
        hybrid_copy["audit_trail"].extend(deepcopy(payload.get("audit_trail") or []))

    slot_targets = _build_slot_l2_targets(version_a, version_b)
    coverage = analyze_listing_l2_coverage(
        hybrid_copy.get("bullets") or [],
        slot_targets,
        threshold=LISTING_L2_COVERAGE_THRESHOLD,
    )
    metadata["hybrid_l2_coverage"] = {
        "covered_slots": coverage["covered_slots"],
        "coverage_count": coverage["coverage_count"],
        "threshold": coverage["threshold"],
    }
    metadata["hybrid_repairs"] = []
    if not coverage["meets_threshold"]:
        l2_diagnostics = repair_hybrid_bullets_for_l2(
            hybrid_copy.get("bullets") or [],
            missing_keywords=coverage["missing_keywords"],
            max_repairs=2,
        )
        metadata["hybrid_l2_diagnostics"] = l2_diagnostics
    else:
        metadata["hybrid_l2_diagnostics"] = {}

    keyword_reconciliation = _reconcile_hybrid_keywords(
        hybrid_copy=hybrid_copy,
        version_a=version_a,
        version_b=version_b,
        writing_policy=writing_policy,
    )
    hybrid_copy["keyword_reconciliation"] = keyword_reconciliation
    hybrid_copy.setdefault("decision_trace", {})["keyword_assignments"] = list(keyword_reconciliation.get("assignments") or [])
    hybrid_copy["decision_trace"]["keyword_reconciliation_status"] = keyword_reconciliation.get("status")
    hybrid_copy["decision_trace"]["keyword_reconciliation_coverage"] = keyword_reconciliation.get("coverage") or {}

    risk_report = risk_check.perform_risk_check(
        hybrid_copy,
        writing_policy,
        getattr(getattr(preprocessed_data, "attribute_data", None), "data", {}) or {},
        capability_constraints=getattr(preprocessed_data, "capability_constraints", {}) or {},
        preprocessed_data=preprocessed_data,
    )
    if hybrid_copy.get("_no_eligible_source"):
        issues = [
            {
                "rule": "no_eligible_source",
                "description": f"无可用字段来源: {field}",
                "severity": "high",
                "field": field,
            }
            for field in hybrid_copy.get("_no_eligible_source") or []
        ]
        truth = risk_report.get("truth_consistency") or {"passed": 1, "total": 1, "issues": [], "all_passed": True}
        truth["issues"] = list(truth.get("issues") or []) + issues
        truth["passed"] = 0
        truth["all_passed"] = False
        risk_report["truth_consistency"] = truth
        listing_status = risk_report.get("listing_status") or {"status": "READY_FOR_LISTING", "blocking_reasons": []}
        listing_status["status"] = "NOT_READY_FOR_LISTING"
        reasons = list(listing_status.get("blocking_reasons") or [])
        for field in hybrid_copy.get("_no_eligible_source") or []:
            reason = f"无可用字段来源: {field}"
            if reason not in reasons:
                reasons.append(reason)
        listing_status["blocking_reasons"] = reasons
        risk_report["listing_status"] = listing_status
    scoring_results = scoring.calculate_scores(
        hybrid_copy,
        writing_policy,
        preprocessed_data,
        intent_graph=intent_graph,
        risk_report=risk_report,
    )
    metadata["launch_decision"] = build_hybrid_launch_decision(
        risk_report=risk_report,
        scoring_results=scoring_results,
        hybrid_copy=hybrid_copy,
    )
    listing_report = report_generator.generate_report(
        preprocessed_data=preprocessed_data,
        generated_copy=hybrid_copy,
        writing_policy=writing_policy,
        risk_report=risk_report,
        scoring_results=scoring_results,
        language=language,
        intent_graph=intent_graph,
    )
    readiness_summary = report_builder.build_readiness_summary(
        sku=f"{getattr(getattr(preprocessed_data, 'run_config', None), 'brand_name', '')}_{getattr(preprocessed_data, 'target_country', '')}",
        run_id=output_dir.name,
        generated_copy=hybrid_copy,
        scoring_results=scoring_results,
        risk_report=risk_report,
        generated_at=getattr(preprocessed_data, "processed_at", ""),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "generated_copy.json").write_text(json.dumps(hybrid_copy, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "risk_report.json").write_text(json.dumps(risk_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "scoring_results.json").write_text(json.dumps(scoring_results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "listing_report.md").write_text(listing_report, encoding="utf-8")
    (output_dir / "readiness_summary.md").write_text(readiness_summary, encoding="utf-8")
    (output_dir / "source_trace.json").write_text(json.dumps(hybrid_copy.get("source_trace") or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    image_handoff_path = image_handoff.write_image_handoff(
        output_dir=output_dir,
        preprocessed_data=preprocessed_data,
        generated_copy=hybrid_copy,
        writing_policy=writing_policy,
        intent_graph=intent_graph or {},
        risk_report=risk_report,
    )
    return {
        "generated_copy": hybrid_copy,
        "risk_report": risk_report,
        "scoring_results": scoring_results,
        "listing_report_path": str(output_dir / "listing_report.md"),
        "readiness_summary_path": str(output_dir / "readiness_summary.md"),
        "image_handoff_path": str(image_handoff_path),
    }
