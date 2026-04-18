from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from modules import report_builder, report_generator, risk_check, scoring
from modules.hybrid_optimizer import collect_missing_l2_keywords, repair_hybrid_bullets_for_l2


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
) -> Dict[str, Any]:
    slot = str(slot).upper()
    blocked_a = _extract_blocked_bullet_slots(risk_a)
    blocked_b = _extract_blocked_bullet_slots(risk_b)
    fallback_a = _extract_fallback_bullet_slots(meta_a)
    fallback_b = _extract_fallback_bullet_slots(meta_b)

    disqualified = []
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
        }
    if eligible.get("version_a") and not eligible.get("version_b"):
        reason = next((row["reason"] for row in disqualified if row["version"] == "version_b"), "single_eligible_source")
        return {
            "source_version": "version_a",
            "selection_reason": "version_b_fallback_marked" if reason.startswith("fallback_marked:") else "version_b_risk_blocked",
            "disqualified": disqualified,
        }
    if eligible.get("version_b") and not eligible.get("version_a"):
        reason = next((row["reason"] for row in disqualified if row["version"] == "version_a"), "single_eligible_source")
        return {
            "source_version": "version_b",
            "selection_reason": "version_a_fallback_marked" if reason.startswith("fallback_marked:") else "version_a_risk_blocked",
            "disqualified": disqualified,
        }

    a_has_l2 = _bullet_has_slot_targets(bullet_a, slot_l2_targets)
    b_has_l2 = _bullet_has_slot_targets(bullet_b, slot_l2_targets)
    if a_has_l2 and not b_has_l2:
        return {
            "source_version": "version_a",
            "selection_reason": "version_b_missing_l2",
            "disqualified": disqualified,
        }
    if b_has_l2 and not a_has_l2:
        return {
            "source_version": "version_b",
            "selection_reason": "slot_default_preference",
            "disqualified": disqualified,
        }
    return {
        "source_version": "version_b",
        "selection_reason": "slot_default_preference",
        "disqualified": disqualified,
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
    no_eligible_source: list[str] = []
    for field_name in DEFAULT_HYBRID_SELECTION_POLICY:
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
        )
        bullet_source = decision["source_version"] or policy.get("bullets", "version_b")
        chosen_bullet = bullets_a[idx] if bullet_source == "version_a" else bullets_b[idx]
        selected_bullets.append(deepcopy(chosen_bullet))
        bullet_decisions.append(
            {
                "slot": slot,
                "source_version": bullet_source,
                "selection_reason": decision["selection_reason"],
                "disqualified": deepcopy(decision["disqualified"]),
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
        "title": field_values.get("title"),
        "bullets": list(field_values.get("bullets") or []) if field_values.get("bullets") is not None else None,
        "description": field_values.get("description"),
        "faq": list(field_values.get("faq") or []) if field_values.get("faq") is not None else None,
        "search_terms": list(field_values.get("search_terms") or []) if field_values.get("search_terms") is not None else None,
        "aplus_content": field_values.get("aplus_content"),
        "metadata": {
            **base_metadata,
            "visible_copy_mode": "hybrid_postselect",
            "visible_copy_status": "hybrid_mixed",
            "hybrid_sources": field_sources,
            "visible_llm_fallback_fields": recomputed_visible_fallbacks,
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


def build_hybrid_launch_decision(
    *,
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
    hybrid_copy: Dict[str, Any],
) -> Dict[str, Any]:
    reasons: list[str] = []
    listing_status = ((risk_report.get("listing_status") or {}).get("status")) or ""
    if listing_status != "READY_FOR_LISTING":
        reasons.append("listing not ready")

    dimensions = scoring_results.get("dimensions") or {}
    a10 = ((dimensions.get("traffic") or {}).get("score")) or 0
    cosmo = ((dimensions.get("content") or {}).get("score")) or ((dimensions.get("conversion") or {}).get("score")) or 0
    rufus = ((dimensions.get("conversion") or {}).get("score")) or ((dimensions.get("answerability") or {}).get("score")) or 0
    fluency = ((dimensions.get("readability") or {}).get("score")) or 0
    if a10 < 80:
        reasons.append("A10 below threshold")
    if cosmo < 90:
        reasons.append("COSMO below threshold")
    if rufus < 90:
        reasons.append("Rufus below threshold")
    if fluency < 24:
        reasons.append("Fluency below threshold")

    metadata = hybrid_copy.get("metadata") or {}
    if metadata.get("visible_llm_fallback_fields"):
        reasons.append("visible fallback present")
    if hybrid_copy.get("_no_eligible_source"):
        reasons.append("no eligible source present")

    return {
        "recommended_output": "hybrid" if not reasons else "version_a",
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

    assigned_l2 = _collect_hybrid_l2_keywords(hybrid_copy)
    missing_l2 = collect_missing_l2_keywords(hybrid_copy.get("bullets") or [], assigned_l2)
    repaired_bullets, repair_actions = repair_hybrid_bullets_for_l2(
        hybrid_copy.get("bullets") or [],
        missing_keywords=missing_l2,
        max_repairs=2,
    )
    if repair_actions:
        hybrid_copy["bullets"] = repaired_bullets
        metadata["hybrid_repairs"] = repair_actions

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
    return {
        "generated_copy": hybrid_copy,
        "risk_report": risk_report,
        "scoring_results": scoring_results,
        "listing_report_path": str(output_dir / "listing_report.md"),
        "readiness_summary_path": str(output_dir / "readiness_summary.md"),
    }
