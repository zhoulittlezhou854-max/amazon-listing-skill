from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from modules import report_builder, report_generator, risk_check, scoring


DEFAULT_HYBRID_SELECTION_POLICY: Dict[str, str] = {
    "title": "version_a",
    "bullets": "version_b",
    "description": "version_a",
    "faq": "version_a",
    "search_terms": "version_a",
    "aplus_content": "version_a",
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


def _build_source_trace(field_decisions: Dict[str, Dict[str, Any]], hybrid_copy: Dict[str, Any]) -> Dict[str, Any]:
    bullets = hybrid_copy.get("bullets") or []
    return {
        "title": field_decisions["title"],
        "bullets": [
            {
                "slot": f"B{idx}",
                "source_version": field_decisions["bullets"]["source_version"],
                "selection_reason": field_decisions["bullets"]["selection_reason"],
                "disqualified": deepcopy(field_decisions["bullets"]["disqualified"]),
            }
            for idx, _ in enumerate(bullets, start=1)
        ],
        "description": field_decisions["description"],
        "faq": field_decisions["faq"],
        "search_terms": field_decisions["search_terms"],
        "aplus_content": field_decisions["aplus_content"],
    }


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
    bullet_source = field_decisions["bullets"]["source_version"] or policy.get("bullets", "version_b")
    search_terms_source = field_decisions["search_terms"]["source_version"] or policy.get("search_terms", "version_a")

    field_sources = {field: (decision["source_version"] or None) for field, decision in field_decisions.items()}

    base_metadata = deepcopy((version_a if title_source == "version_a" else version_b).get("metadata") or {})
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
        },
    }
    if no_eligible_source:
        hybrid_copy["_no_eligible_source"] = no_eligible_source

    hybrid_copy["source_trace"] = _build_source_trace(field_decisions, hybrid_copy)
    hybrid_copy["decision_trace"] = {
        "bullet_trace": deepcopy((version_b if bullet_source == "version_b" else version_a).get("decision_trace", {}).get("bullet_trace", [])),
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
        for row in rows:
            assigned = [str(field) for field in (row.get("assigned_fields") or []) if str(field) in allowed_fields]
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
    bullet_source = (source_trace.get("bullets") or [{}])[0].get("source_version", field_sources.get("bullets", "version_b"))
    search_terms_source = field_sources.get("search_terms", "version_a")
    _ingest(title_source, {"title"})
    _ingest(bullet_source, {f"B{i}" for i in range(1, 6)} | {f"bullet_b{i}" for i in range(1, 6)})
    _ingest(search_terms_source, {"search_terms"})

    rebuilt = {
        "bullet_trace": deepcopy(hybrid_copy.get("decision_trace", {}).get("bullet_trace", [])),
        "search_terms_trace": deepcopy(hybrid_copy.get("decision_trace", {}).get("search_terms_trace", {})),
        "keyword_assignments": merged,
    }
    hybrid_copy["decision_trace"] = rebuilt
    return rebuilt


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
