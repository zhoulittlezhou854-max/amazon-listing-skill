from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, List, Optional


_REPAIRABLE_ISSUES = {
    "missing_keywords",
    "missing_header_or_em_dash",
    "header_body_rupture",
    "dash_tail_without_predicate",
    "repeated_word_root",
    "unsupported_capability_negative_literal",
    "scrub_induced_awkwardness",
}

_R1_BATCH_DEFAULT_REPAIR_POLICY = {
    "on_contract_fail": "rerender_slot",
    "on_fluency_fail": "rerender_slot",
    "on_keyword_coverage_fail": "rerender_slot",
}


def _normalize_slot(slot: Any) -> str:
    value = str(slot or "").strip().lower()
    if value.startswith("bullet_b") and value.removeprefix("bullet_b").isdigit():
        return f"B{value.removeprefix('bullet_b')}"
    if value.startswith("bullet_") and value.removeprefix("bullet_").isdigit():
        return f"B{value.removeprefix('bullet_')}"
    if re.fullmatch(r"b\d+", value):
        return value.upper()
    return str(slot or "").strip().upper()


def _slot_index(slot: str) -> Optional[int]:
    normalized = _normalize_slot(slot)
    if normalized.startswith("B") and normalized[1:].isdigit():
        return int(normalized[1:]) - 1
    return None


def _get_slot_row(rows: Any, slot: str) -> Optional[Dict[str, Any]]:
    normalized_slot = _normalize_slot(slot)
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if _normalize_slot(row.get("slot")) == normalized_slot:
            return deepcopy(row)
    return None


def _get_slot_bullet(bullets: Any, slot: str) -> Optional[str]:
    idx = _slot_index(slot)
    if idx is None:
        return None
    if isinstance(bullets, list) and 0 <= idx < len(bullets):
        return deepcopy(bullets[idx])
    return None


def _is_r1_batch_surface(generated_copy: Dict[str, Any]) -> bool:
    metadata = generated_copy.get("metadata") or {}
    return str(metadata.get("visible_copy_mode") or "").strip() == "r1_batch"


def _resolve_repair_policy(slot_rule: Dict[str, Any], generated_copy: Dict[str, Any]) -> Dict[str, Any]:
    explicit = deepcopy(slot_rule.get("repair_policy") or {})
    if explicit:
        return explicit
    if _is_r1_batch_surface(generated_copy):
        return deepcopy(_R1_BATCH_DEFAULT_REPAIR_POLICY)
    return {}


def _build_rerender_reasons(slot_quality: Dict[str, Any], repair_policy: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    contract_action = str(repair_policy.get("on_contract_fail") or "").strip()
    fluency_action = str(repair_policy.get("on_fluency_fail") or "").strip()
    keyword_action = str(repair_policy.get("on_keyword_coverage_fail") or "").strip()

    if slot_quality.get("contract_pass") is False and contract_action == "rerender_slot":
        reasons.append("contract_fail")
    if slot_quality.get("fluency_pass") is False and fluency_action == "rerender_slot":
        reasons.append("fluency_fail")
    if slot_quality.get("keyword_coverage_pass") is False and keyword_action == "rerender_slot":
        reasons.append("keyword_coverage_fail")
    if slot_quality.get("unsupported_policy_pass") is False and "contract_fail" not in reasons and contract_action == "rerender_slot":
        reasons.append("unsupported_policy_fail")

    if not reasons:
        return []

    for issue in slot_quality.get("issues") or []:
        normalized = str(issue or "").strip()
        if normalized.startswith("slot_contract_failed:") and "slot_contract_failed" not in reasons:
            reasons.append("slot_contract_failed")
        if normalized in _REPAIRABLE_ISSUES and normalized not in reasons:
            reasons.append(normalized)
    return reasons


def build_slot_rerender_plan(generated_copy: Dict[str, Any], writing_policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    bullet_packets = list(generated_copy.get("bullet_packets") or [])
    slot_quality_packets = list(generated_copy.get("slot_quality_packets") or [])
    if not bullet_packets or not slot_quality_packets:
        return []

    slot_rules = writing_policy.get("bullet_slot_rules") or {}
    plan: List[Dict[str, Any]] = []
    for packet in bullet_packets:
        slot = _normalize_slot(packet.get("slot"))
        if not slot:
            continue
        slot_quality = _get_slot_row(slot_quality_packets, slot) or {}
        slot_rule = slot_rules.get(slot) or {}
        repair_policy = _resolve_repair_policy(slot_rule, generated_copy)
        rerender_reasons = _build_rerender_reasons(slot_quality, repair_policy)
        if not rerender_reasons:
            continue
        priority = "high" if any(reason in {"contract_fail", "unsupported_policy_fail"} for reason in rerender_reasons) else "medium"
        plan.append(
            {
                "slot": slot,
                "current_bullet": _get_slot_bullet(generated_copy.get("bullets") or [], slot),
                "source_packet": deepcopy(packet),
                "slot_quality": deepcopy(slot_quality),
                "repair_policy": repair_policy,
                "rerender_reasons": rerender_reasons,
                "priority": priority,
                "strategy": "slot_packet_rerender",
            }
        )
    return plan


def apply_slot_rerender_result(generated_copy: Dict[str, Any], rerender_result: Dict[str, Any]) -> Dict[str, Any]:
    updated = deepcopy(generated_copy)
    slot = _normalize_slot(rerender_result.get("slot"))
    idx = _slot_index(slot)
    if idx is None:
        return updated

    if idx < len(updated.get("bullets") or []) and "bullet" in rerender_result:
        updated["bullets"][idx] = rerender_result.get("bullet")

    for key, field_name in (("packet", "bullet_packets"), ("quality", "slot_quality_packets")):
        rows = list(updated.get(field_name) or [])
        replaced = False
        for row_idx, row in enumerate(rows):
            if isinstance(row, dict) and _normalize_slot(row.get("slot")) == slot:
                rows[row_idx] = deepcopy(rerender_result.get(key) or row)
                replaced = True
                break
        if not replaced and rerender_result.get(key):
            rows.append(deepcopy(rerender_result[key]))
        updated[field_name] = rows
    return updated


def execute_slot_rerender_plan(
    generated_copy: Dict[str, Any],
    rerender_plan: List[Dict[str, Any]],
    rerender_slot_fn,
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    updated = deepcopy(generated_copy)
    results: List[Dict[str, Any]] = []

    for plan_entry in rerender_plan or []:
        slot = _normalize_slot((plan_entry or {}).get("slot"))
        try:
            rerender_result = rerender_slot_fn(deepcopy(plan_entry), deepcopy(updated))
        except Exception as exc:
            results.append({"slot": slot, "status": "error", "error": str(exc)})
            continue
        if not rerender_result:
            results.append({"slot": slot, "status": "skipped"})
            continue
        updated = apply_slot_rerender_result(updated, rerender_result)
        results.append({"slot": slot, "status": str(rerender_result.get("status") or "applied")})

    return updated, results
