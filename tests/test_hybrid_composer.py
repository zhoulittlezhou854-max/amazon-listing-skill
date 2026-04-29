import json
from pathlib import Path
from types import SimpleNamespace

from modules.hybrid_composer import (
    DEFAULT_HYBRID_SELECTION_POLICY,
    build_hybrid_launch_decision,
    finalize_hybrid_outputs,
    rebuild_hybrid_decision_trace,
    compose_hybrid_listing,
    select_source_for_field,
)
from modules.report_generator import generate_dual_version_report, generate_report


def test_hybrid_composer_writes_to_separate_hybrid_directory(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "metadata": {},
        "decision_trace": {},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "metadata": {},
        "decision_trace": {},
    }

    output = compose_hybrid_listing(
        version_a=version_a,
        version_b=version_b,
        output_dir=tmp_path / "hybrid",
        selection_policy={"title": "version_a", "bullets": "version_b"},
    )

    assert (tmp_path / "hybrid" / "generated_copy.json").exists()
    assert output["title"] == "A title"
    assert output["bullets"] == ["B1", "B2", "B3", "B4", "B5"]


def test_hybrid_metadata_records_field_sources(tmp_path):
    hybrid = compose_hybrid_listing(
        version_a={
            "title": "A",
            "bullets": ["A"] * 5,
            "metadata": {"generation_status": "live_success"},
            "decision_trace": {},
        },
        version_b={
            "title": "B",
            "bullets": ["B"] * 5,
            "metadata": {"generation_status": "live_success"},
            "decision_trace": {},
        },
        output_dir=tmp_path / "hybrid",
        selection_policy={"title": "version_a", "bullets": "version_b"},
    )

    assert hybrid["metadata"]["visible_copy_mode"] == "hybrid_postselect"
    assert hybrid["metadata"]["hybrid_sources"]["title"] == "version_a"
    assert hybrid["source_trace"]["bullets"][0]["source_version"] == "version_b"


def test_hybrid_mvp_carries_only_safe_trace_segments(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "metadata": {},
        "decision_trace": {"search_terms_trace": {"byte_length": 180}},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "metadata": {},
        "decision_trace": {"bullet_trace": [{"slot": "B1", "audience_group": "professional"}]},
    }

    hybrid = compose_hybrid_listing(
        version_a=version_a,
        version_b=version_b,
        output_dir=tmp_path / "hybrid",
        selection_policy={"title": "version_a", "bullets": "version_b"},
    )

    assert hybrid["decision_trace"]["bullet_trace"][0]["slot"] == "B1"
    assert hybrid["decision_trace"]["search_terms_trace"]["byte_length"] == 180
    assert hybrid["decision_trace"]["keyword_assignments"] == []


def test_dual_version_run_can_write_hybrid_directory(tmp_path):
    version_a = {
        "generated_copy": {
            "title": "A title",
            "bullets": ["A1", "A2", "A3", "A4", "A5"],
            "description": "A desc",
            "faq": [],
            "search_terms": ["a"],
            "aplus_content": "A+",
            "metadata": {"generation_status": "live_success"},
            "decision_trace": {"search_terms_trace": {"byte_length": 180}},
        }
    }
    version_b = {
        "generated_copy": {
            "title": "B title",
            "bullets": ["B1", "B2", "B3", "B4", "B5"],
            "description": "B desc",
            "faq": [],
            "search_terms": ["b"],
            "aplus_content": "B+",
            "metadata": {"generation_status": "live_success"},
            "decision_trace": {"bullet_trace": [{"slot": "B1"}]},
        }
    }

    output = compose_hybrid_listing(
        version_a=version_a["generated_copy"],
        version_b=version_b["generated_copy"],
        output_dir=tmp_path / "run" / "hybrid",
        selection_policy=DEFAULT_HYBRID_SELECTION_POLICY,
    )

    assert (tmp_path / "run" / "hybrid" / "generated_copy.json").exists()
    assert (tmp_path / "run" / "hybrid" / "source_trace.json").exists()
    persisted = json.loads((tmp_path / "run" / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))
    assert persisted["title"] == output["title"]


def _sample_preprocessed():
    return SimpleNamespace(
        run_config=SimpleNamespace(brand_name="TOSBARRFT", target_country="US", input_files={}),
        processed_at="2026-04-18T00:00:00",
        language="English",
        target_country="US",
        quality_score=90,
        real_vocab=None,
        data_alerts=[],
        core_selling_points=["150 minute runtime", "magnetic clip"],
        attribute_data=SimpleNamespace(data={"video_resolution": "1080P", "storage": "256GB"}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        capability_constraints={},
        keyword_metadata=[
            {"keyword": "action camera", "tier": "L1"},
            {"keyword": "body camera", "tier": "L2"},
            {"keyword": "travel cam", "tier": "L3"},
        ],
        ingestion_audit={"tables": []},
        raw_human_insights="",
        asin_entity_profile={},
    )


def test_hybrid_rebuilds_keyword_assignments_for_selected_fields(tmp_path):
    version_a = {
        "title": "Brand action camera",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "description": "",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "",
        "metadata": {},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "action camera", "tier": "L1", "assigned_fields": ["title"]},
                {"keyword": "travel cam", "tier": "L3", "assigned_fields": ["search_terms"]},
            ]
        },
    }
    version_b = {
        "title": "Brand body camera",
        "bullets": ["body camera bullet", "B2", "B3", "B4", "B5"],
        "description": "",
        "faq": [],
        "search_terms": [],
        "aplus_content": "",
        "metadata": {},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "body camera", "tier": "L2", "assigned_fields": ["B1"]},
            ]
        },
    }

    hybrid = compose_hybrid_listing(
        version_a=version_a,
        version_b=version_b,
        output_dir=tmp_path / "hybrid",
        selection_policy=DEFAULT_HYBRID_SELECTION_POLICY,
    )
    rebuilt = rebuild_hybrid_decision_trace(hybrid, version_a, version_b)

    assignments = rebuilt["keyword_assignments"]
    assert any(row["keyword"] == "action camera" and "title" in row["assigned_fields"] for row in assignments)
    assert any(row["keyword"] == "body camera" and "B1" in row["assigned_fields"] for row in assignments)
    assert any(row["source_version"] == "version_a" for row in assignments)


def test_hybrid_rebuild_normalizes_legacy_bullet_field_aliases(tmp_path):
    version_a = {
        "title": "Brand action camera",
        "bullets": ["travel camera bullet", "body camera bullet", "A3", "A4", "A5"],
        "description": "",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "",
        "metadata": {},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["bullet_1"]},
                {"keyword": "body camera", "tier": "L2", "assigned_fields": ["bullet_2"]},
            ]
        },
    }
    version_b = {
        "title": "Brand body camera",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "",
        "faq": [],
        "search_terms": [],
        "aplus_content": "",
        "metadata": {"visible_llm_fallback_fields": ["bullet_b1", "bullet_b2"]},
        "decision_trace": {"keyword_assignments": []},
    }

    hybrid = compose_hybrid_listing(
        version_a=version_a,
        version_b=version_b,
        output_dir=tmp_path / "hybrid",
        selection_policy=DEFAULT_HYBRID_SELECTION_POLICY,
    )
    rebuilt = rebuild_hybrid_decision_trace(hybrid, version_a, version_b)

    assignments = rebuilt["keyword_assignments"]
    assert any(row["keyword"] == "travel camera" and "B1" in row["assigned_fields"] for row in assignments)
    assert any(row["keyword"] == "body camera" and "B2" in row["assigned_fields"] for row in assignments)


def test_hybrid_finalize_writes_scoring_and_readiness_outputs(tmp_path):
    preprocessed = _sample_preprocessed()
    writing_policy = {"market_pack": {"locale": "US"}, "target_language": "English"}
    version_a = {
        "title": "TOSBARRFT action camera for travel",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "description": "Portable camera for daily recording.",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [{"keyword": "action camera", "tier": "L1", "assigned_fields": ["title"]}],
            "search_terms_trace": {"byte_length": 100, "max_bytes": 249},
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    version_b = {
        "title": "TOSBARRFT body camera",
        "bullets": [
            "BODY CAMERA READY — body camera for daily capture.",
            "LONG BATTERY — 150 minutes runtime.",
            "TRAVEL CLIP — easy mounting setup.",
            "GUIDANCE — stable use only.",
            "KIT VALUE — cable included.",
        ],
        "description": "R1 desc",
        "faq": [],
        "search_terms": [],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [{"keyword": "body camera", "tier": "L2", "assigned_fields": ["B1"]}],
            "bullet_trace": [{"slot": "B1", "audience_group": "professional"}],
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    finalize_hybrid_outputs(
        hybrid_copy=hybrid,
        version_a=version_a,
        version_b=version_b,
        writing_policy=writing_policy,
        preprocessed_data=preprocessed,
        output_dir=tmp_path / "hybrid",
        language="English",
        intent_graph=None,
    )

    assert (tmp_path / "hybrid" / "scoring_results.json").exists()
    assert (tmp_path / "hybrid" / "readiness_summary.md").exists()
    assert (tmp_path / "hybrid" / "listing_report.md").exists()
    persisted = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))
    assert persisted["decision_trace"]["keyword_assignments"]
    assert persisted["keyword_reconciliation"]["status"] == "complete"
    assert persisted["decision_trace"]["keyword_reconciliation_status"] == "complete"


def test_hybrid_finalize_records_repair_trace_when_l2_is_missing(tmp_path):
    preprocessed = _sample_preprocessed()
    writing_policy = {"market_pack": {"locale": "US"}, "target_language": "English"}
    version_a = {
        "title": "TOSBARRFT action camera for travel",
        "bullets": [
            "A1 travel camera coverage.",
            "A2 body camera evidence capture.",
            "A3 helmet camera support.",
            "A4 guidance.",
            "A5 kit.",
        ],
        "description": "Portable camera for daily recording.",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["B1"]},
                {"keyword": "mini camera", "tier": "L2", "assigned_fields": ["B1"]},
            ],
            "search_terms_trace": {"byte_length": 100, "max_bytes": 249},
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    version_b = {
        "title": "TOSBARRFT body camera",
        "bullets": [
            "B1 commuting capture.",
            "B2 security evidence coverage.",
            "B3 helmet camera support.",
            "B4 guidance.",
            "B5 kit.",
        ],
        "description": "R1 desc",
        "faq": [],
        "search_terms": [],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["B1"]},
                {"keyword": "mini camera", "tier": "L2", "assigned_fields": ["B1"]},
            ],
            "bullet_trace": [{"slot": f"B{i}", "audience_group": "general"} for i in range(1, 6)],
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    finalize_hybrid_outputs(
        hybrid_copy=hybrid,
        version_a=version_a,
        version_b=version_b,
        writing_policy=writing_policy,
        preprocessed_data=preprocessed,
        output_dir=tmp_path / "hybrid",
        language="English",
        intent_graph=None,
    )

    persisted = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))
    diagnostics = persisted["metadata"].get("hybrid_l2_diagnostics") or {}
    assert diagnostics["missing_keywords"] == ["travel camera", "mini camera"]
    assert diagnostics["repair_actions"] == []
    assert diagnostics["repair_skipped_reason"] == "text_suffix_injection_disabled"
    assert all("mini camera" not in bullet.lower() for bullet in persisted["bullets"])


def test_hybrid_finalize_skips_repair_when_listing_l2_threshold_is_already_met(tmp_path):
    preprocessed = _sample_preprocessed()
    writing_policy = {"market_pack": {"locale": "US"}, "target_language": "English"}
    version_a = {
        "title": "TOSBARRFT action camera for travel",
        "bullets": [
            "A1 travel camera coverage.",
            "A2 body camera with audio evidence capture.",
            "A3 thumb camera support.",
            "A4 guidance.",
            "A5 kit.",
        ],
        "description": "Portable camera for daily recording.",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["B1"]},
                {"keyword": "body camera with audio", "tier": "L2", "assigned_fields": ["B2"]},
                {"keyword": "thumb camera", "tier": "L2", "assigned_fields": ["B3"]},
            ],
            "search_terms_trace": {"byte_length": 100, "max_bytes": 249},
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    version_b = {
        "title": "TOSBARRFT body camera",
        "bullets": [
            "B1 travel camera commute coverage.",
            "B2 body camera with audio evidence capture.",
            "B3 thumb camera support.",
            "B4 guidance.",
            "B5 kit.",
        ],
        "description": "R1 desc",
        "faq": [],
        "search_terms": [],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["B1"]},
                {"keyword": "body camera with audio", "tier": "L2", "assigned_fields": ["B2"]},
                {"keyword": "thumb camera", "tier": "L2", "assigned_fields": ["B3"]},
            ],
            "bullet_trace": [{"slot": f"B{i}", "audience_group": "general"} for i in range(1, 6)],
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    finalize_hybrid_outputs(
        hybrid_copy=hybrid,
        version_a=version_a,
        version_b=version_b,
        writing_policy=writing_policy,
        preprocessed_data=preprocessed,
        output_dir=tmp_path / "hybrid",
        language="English",
        intent_graph=None,
    )

    persisted = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))
    diagnostics = persisted["metadata"].get("hybrid_l2_diagnostics") or {}
    assert diagnostics == {}


def test_hybrid_finalize_uses_union_slot_targets_to_trigger_repair_for_b_selected_bullets(tmp_path):
    preprocessed = _sample_preprocessed()
    writing_policy = {"market_pack": {"locale": "US"}, "target_language": "English"}
    version_a = {
        "title": "TOSBARRFT action camera for travel",
        "bullets": [
            "A1 travel camera coverage.",
            "A2 body camera with audio evidence capture.",
            "A3 thumb camera support.",
            "A4 guidance.",
            "A5 kit.",
        ],
        "description": "Portable camera for daily recording.",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["B1"]},
                {"keyword": "body camera with audio", "tier": "L2", "assigned_fields": ["B2"]},
                {"keyword": "thumb camera", "tier": "L2", "assigned_fields": ["B3"]},
            ],
            "search_terms_trace": {"byte_length": 100, "max_bytes": 249},
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    version_b = {
        "title": "TOSBARRFT body camera",
        "bullets": [
            "B1 commute recording with magnetic clip.",
            "B2 evidence capture for security professionals.",
            "B3 creative POV filming for rides.",
            "B4 guidance.",
            "B5 kit.",
        ],
        "description": "R1 desc",
        "faq": [],
        "search_terms": [],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [{"slot": f"B{i}", "audience_group": "general"} for i in range(1, 6)],
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    finalize_hybrid_outputs(
        hybrid_copy=hybrid,
        version_a=version_a,
        version_b=version_b,
        writing_policy=writing_policy,
        preprocessed_data=preprocessed,
        output_dir=tmp_path / "hybrid",
        language="English",
        intent_graph=None,
    )

    persisted = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))
    assert persisted["metadata"]["hybrid_l2_coverage"]["coverage_count"] == 0
    diagnostics = persisted["metadata"].get("hybrid_l2_diagnostics") or {}
    assert diagnostics["missing_keywords"]
    assert diagnostics["repair_actions"] == []
    assert diagnostics["repair_skipped_reason"] == "text_suffix_injection_disabled"


def test_hybrid_finalize_records_repaired_l2_assignments_into_decision_trace(tmp_path):
    preprocessed = _sample_preprocessed()
    writing_policy = {"market_pack": {"locale": "US"}, "target_language": "English"}
    version_a = {
        "title": "TOSBARRFT action camera for travel",
        "bullets": [
            "A1 travel camera coverage.",
            "A2 body camera with audio evidence capture.",
            "A3 thumb camera support.",
            "A4 guidance.",
            "A5 kit.",
        ],
        "description": "Portable camera for daily recording.",
        "faq": [],
        "search_terms": ["travel cam"],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["B1"]},
                {"keyword": "body camera with audio", "tier": "L2", "assigned_fields": ["B2"]},
                {"keyword": "thumb camera", "tier": "L2", "assigned_fields": ["B3"]},
            ],
            "search_terms_trace": {"byte_length": 100, "max_bytes": 249},
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    version_b = {
        "title": "TOSBARRFT body camera",
        "bullets": [
            "Extended-session wearable recording with magnetic clip support and lightweight hands-free capture across daily commutes and walking scenes, ideal for content creators and adventurers.",
            "Evidence-ready design with 1080P video and AAC audio for reliable incident documentation during full shifts.",
            "Thumb-sized commuting companion for cyclists and urban commuters in steady-paced scenes.",
            "Guidance for stable walking tours and clipped scenes.",
            "Complete kit with USB Type-C cable and storage support.",
        ],
        "description": "R1 desc",
        "faq": [],
        "search_terms": [],
        "aplus_content": "word " * 520,
        "metadata": {"generation_status": "live_success", "target_language": "English"},
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [{"slot": f"B{i}", "audience_group": "general"} for i in range(1, 6)],
        },
        "audit_trail": [],
        "compute_tier_map": {},
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
    }
    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    finalize_hybrid_outputs(
        hybrid_copy=hybrid,
        version_a=version_a,
        version_b=version_b,
        writing_policy=writing_policy,
        preprocessed_data=preprocessed,
        output_dir=tmp_path / "hybrid",
        language="English",
        intent_graph=None,
    )

    persisted = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))
    assignments = persisted["decision_trace"]["keyword_assignments"]
    assert not any(row.get("source_version") == "hybrid_repair" for row in assignments)
    diagnostics = persisted["metadata"].get("hybrid_l2_diagnostics") or {}
    assert "travel camera" in diagnostics["missing_keywords"]


def test_dual_report_can_include_hybrid_appendix():
    report = generate_dual_version_report(
        sku="H91lite",
        market="US",
        run_id="r17",
        version_a={"generated_copy": {"title": "A title", "bullets": ["A1"] * 5}, "scoring_results": {}, "generation_status": "live_success"},
        version_b={"generated_copy": {"title": "B title", "bullets": ["B1"] * 5}, "scoring_results": {}, "generation_status": "live_success"},
        hybrid={
            "generated_copy": {"title": "Hybrid title", "bullets": ["H1", "H2", "H3", "H4", "H5"]},
            "scoring_results": {"listing_status": "READY_FOR_LISTING"},
            "generation_status": "composed",
        },
    )

    assert "## Hybrid Recommendation" in report
    assert "Hybrid title" in report
    assert "Version A" in report and "Version B" in report


def test_description_falls_back_to_b_when_a_is_fallback_marked():
    meta_a = {"visible_llm_fallback_fields": ["description"]}
    meta_b = {"visible_llm_fallback_fields": []}
    risk_a = {"blocking_fields": []}
    risk_b = {"blocking_fields": []}

    result = select_source_for_field("description", meta_a, risk_a, meta_b, risk_b)

    assert result["source_version"] == "version_b"
    assert result["selection_reason"] == "version_a_fallback_marked"
    assert any(d["version"] == "version_a" for d in result["disqualified"])


def test_no_eligible_source_when_both_fallback_marked():
    meta_a = {"visible_llm_fallback_fields": ["description"]}
    meta_b = {"visible_llm_fallback_fields": ["description"]}
    risk_a = {"blocking_fields": []}
    risk_b = {"blocking_fields": []}

    result = select_source_for_field("description", meta_a, risk_a, meta_b, risk_b)

    assert result["source_version"] is None
    assert result["selection_reason"] == "no_eligible_source"
    assert len(result["disqualified"]) == 2


def test_compose_hybrid_normalizes_no_eligible_description_to_string(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "description": "A fallback desc",
        "faq": [],
        "search_terms": ["a"],
        "aplus_content": "A+",
        "metadata": {"visible_llm_fallback_fields": ["description"]},
        "risk_report": {},
        "decision_trace": {},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "B fallback desc",
        "faq": [],
        "search_terms": ["b"],
        "aplus_content": "B+",
        "metadata": {"visible_llm_fallback_fields": ["description"]},
        "risk_report": {},
        "decision_trace": {},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)
    persisted = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text(encoding="utf-8"))

    assert hybrid["description"] == ""
    assert persisted["description"] == ""
    assert "description" in hybrid["_no_eligible_source"]
    assert hybrid["source_trace"]["description"]["source_version"] is None


def test_compose_hybrid_does_not_launch_select_fallback_descriptions(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "description": "A fallback desc",
        "faq": [],
        "search_terms": ["a"],
        "aplus_content": "A+",
        "metadata": {"visible_llm_fallback_fields": ["description"]},
        "risk_report": {},
        "decision_trace": {},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "B fallback desc",
        "faq": [],
        "search_terms": ["b"],
        "aplus_content": "B+",
        "metadata": {"visible_llm_fallback_fields": ["description"]},
        "risk_report": {},
        "decision_trace": {},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    description_provenance = hybrid["metadata"]["field_provenance"]["description"]
    assert description_provenance["eligibility"] == "review_only"
    assert description_provenance["launch_eligible"] is False
    assert hybrid["metadata"]["hybrid_sources"]["description"] is None
    assert "description" in hybrid["_no_eligible_source"]
    assert hybrid["description"] == ""


def test_risk_blocked_field_falls_back_to_a():
    meta_a = {"visible_llm_fallback_fields": []}
    meta_b = {"visible_llm_fallback_fields": []}
    risk_a = {"blocking_fields": []}
    risk_b = {"blocking_fields": ["bullets"]}

    result = select_source_for_field("bullets", meta_a, risk_a, meta_b, risk_b)

    assert result["source_version"] == "version_a"
    assert result["selection_reason"] == "version_b_risk_blocked"


def test_default_preference_when_both_eligible():
    meta_a = {"visible_llm_fallback_fields": []}
    meta_b = {"visible_llm_fallback_fields": []}
    risk_a = {"blocking_fields": []}
    risk_b = {"blocking_fields": []}

    assert select_source_for_field("title", meta_a, risk_a, meta_b, risk_b)["source_version"] == "version_a"
    assert select_source_for_field("bullets", meta_a, risk_a, meta_b, risk_b)["source_version"] == "version_b"
    assert select_source_for_field("description", meta_a, risk_a, meta_b, risk_b)["source_version"] == "version_a"


def test_compose_hybrid_listing_recomputes_visible_fallback_fields_from_selected_sources(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "description": "A desc",
        "faq": [],
        "search_terms": ["a"],
        "aplus_content": "A+",
        "metadata": {"visible_llm_fallback_fields": ["description"]},
        "risk_report": {},
        "decision_trace": {},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "B desc",
        "faq": [],
        "search_terms": ["b"],
        "aplus_content": "B+",
        "metadata": {"visible_llm_fallback_fields": []},
        "risk_report": {},
        "decision_trace": {},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["source_trace"]["description"]["source_version"] == "version_b"
    assert "description" not in ((hybrid.get("metadata") or {}).get("visible_llm_fallback_fields") or [])


def test_hybrid_launch_gate_recommends_hybrid_when_thresholds_pass():
    decision = build_hybrid_launch_decision(
        risk_report={"listing_status": {"status": "READY_FOR_LISTING"}},
        scoring_results={
            "dimensions": {
                "traffic": {"score": 85},
                "content": {"score": 92},
                "conversion": {"score": 95},
                "readability": {"score": 30},
            }
        },
        hybrid_copy={"metadata": {"visible_llm_fallback_fields": []}},
    )

    assert decision["recommended_output"] == "hybrid"
    assert decision["reasons"] == []
    assert decision["passed"] is True
    assert decision["scores"] == {"A10": 85, "COSMO": 92, "Rufus": 95, "Fluency": 30}
    assert decision["thresholds"] == {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24}


def test_hybrid_launch_gate_falls_back_to_version_a_when_thresholds_fail():
    decision = build_hybrid_launch_decision(
        risk_report={"listing_status": {"status": "READY_FOR_LISTING"}},
        scoring_results={
            "dimensions": {
                "traffic": {"score": 70},
                "content": {"score": 80},
                "conversion": {"score": 100},
                "readability": {"score": 30},
            }
        },
        hybrid_copy={"metadata": {"visible_llm_fallback_fields": []}},
    )

    assert decision["recommended_output"] == "version_a"
    assert decision["passed"] is False
    assert "a10_below_threshold" in decision["reasons"]
    assert "cosmo_below_threshold" in decision["reasons"]


def test_compose_hybrid_listing_degrades_to_version_a_when_version_b_bullets_missing(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "description": "A desc",
        "faq": [],
        "search_terms": ["k1"],
        "aplus_content": "A+",
        "metadata": {"generation_status": "live_success"},
        "risk_report": {},
        "decision_trace": {},
    }
    version_b = {
        "title": "B title",
        "bullets": [],
        "description": "B desc",
        "faq": [],
        "search_terms": ["k2"],
        "aplus_content": "B+",
        "metadata": {"generation_status": "FAILED_AT_BLUEPRINT"},
        "risk_report": {},
        "decision_trace": {},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["bullets"] == ["A1", "A2", "A3", "A4", "A5"]
    assert hybrid["source_trace"]["bullets"][0]["source_version"] == "version_a"
    assert hybrid["source_trace"]["bullets"][0]["selection_reason"] == "degraded_fallback_to_a"
    assert hybrid["source_trace"]["bullets"][0]["degraded_mode"] is True


def test_generate_report_includes_hybrid_launch_decision():
    report = generate_report(
        preprocessed_data=_sample_preprocessed(),
        generated_copy={
            "title": "Hybrid title",
            "bullets": ["B1", "B2", "B3", "B4", "B5"],
            "description": "desc",
            "faq": [],
            "search_terms": ["term"],
            "aplus_content": "word " * 520,
            "metadata": {
                "visible_copy_mode": "hybrid_postselect",
                "launch_decision": {
                    "passed": True,
                    "recommended_output": "hybrid",
                    "scores": {"A10": 85, "COSMO": 92, "Rufus": 95, "Fluency": 30},
                    "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
                    "reasons": [],
                },
                "hybrid_repairs": [{"action": "l2_backfill", "slot": "B2", "keyword": "body camera"}],
                "hybrid_sources": {"title": "version_a", "bullets": "mixed"},
            },
            "source_trace": {
                "title": {"source_version": "version_a"},
                "bullets": [{"slot": "B1", "source_version": "version_b", "selection_reason": "slot_default_preference", "disqualified": []}],
            },
            "decision_trace": {},
            "audit_trail": [],
            "compute_tier_map": {},
            "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
        },
        writing_policy={"market_pack": {"locale": "US"}, "target_language": "English"},
        risk_report={"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}, "truth_consistency": {"passed": 1, "total": 1, "issues": [], "all_passed": True}},
        scoring_results={
            "dimensions": {
                "traffic": {"score": 85, "label": "A10", "status": "pass"},
                "content": {"score": 92, "label": "COSMO", "status": "pass"},
                "conversion": {"score": 95, "label": "Rufus", "status": "pass"},
                "readability": {"score": 30, "label": "Fluency", "status": "pass"},
            },
            "production_readiness": {"generation_status": "live_success", "returned_model": "deepseek-chat", "authenticity_score": 8, "penalty": 0, "advisory": "ok"},
        },
        language="English",
        intent_graph=None,
    )

    assert "## Hybrid Launch Decision" in report
    assert "Recommended Output: `hybrid`" in report
    assert "l2_backfill" in report


def test_select_source_for_bullet_slot_keeps_but_records_soft_signal_when_b_misses_slot_l2():
    from modules.hybrid_composer import select_source_for_bullet_slot

    decision = select_source_for_bullet_slot(
        slot="B2",
        bullet_a="Reliable body camera evidence capture for security shifts.",
        bullet_b="Reliable evidence capture for security shifts.",
        meta_a={"visible_llm_fallback_fields": []},
        risk_a={"blocking_fields": []},
        meta_b={"visible_llm_fallback_fields": []},
        risk_b={"blocking_fields": []},
        slot_l2_targets=["body camera"],
    )

    assert decision["source_version"] == "version_b"
    assert decision["selection_reason"] == "slot_default_preference"
    assert "version_b_missing_l2" in decision["soft_signals"]


def test_select_source_for_bullet_slot_prefers_other_version_when_bullet_was_scrub_rewritten():
    from modules.hybrid_composer import select_source_for_bullet_slot

    decision = select_source_for_bullet_slot(
        slot="B2",
        bullet_a="Reliable body camera evidence capture for security shifts.",
        bullet_b="Reliable evidence capture for security shifts.",
        meta_a={"visible_llm_fallback_fields": []},
        risk_a={"blocking_fields": []},
        meta_b={"visible_llm_fallback_fields": []},
        risk_b={"blocking_fields": []},
        slot_l2_targets=["body camera"],
        audit_a=[],
        audit_b=[
            {
                "field": "bullet_b2",
                "action": "delete",
                "reason": "forbidden_visible_terms_scrub",
                "terms": ["stabilization"],
            }
        ],
    )

    assert decision["source_version"] == "version_a"
    assert decision["selection_reason"] == "version_b_scrub_integrity_flag"
    assert "version_b_scrub_integrity_flag" in decision["soft_signals"]


def test_select_source_for_bullet_slot_prefers_version_a_when_version_b_quality_fails():
    from modules.hybrid_composer import select_source_for_bullet_slot

    decision = select_source_for_bullet_slot(
        slot="B4",
        bullet_a="A4 clean guidance for stable walking scenes.",
        bullet_b="B4 broken guidance tail.",
        meta_a={"visible_llm_fallback_fields": []},
        risk_a={"blocking_fields": []},
        meta_b={"visible_llm_fallback_fields": []},
        risk_b={"blocking_fields": []},
        slot_l2_targets=[],
        quality_a={
            "slot": "B4",
            "contract_pass": True,
            "fluency_pass": True,
            "unsupported_policy_pass": True,
            "issues": [],
        },
        quality_b={
            "slot": "B4",
            "contract_pass": False,
            "fluency_pass": False,
            "unsupported_policy_pass": True,
            "issues": ["dash_tail_without_predicate"],
        },
    )

    assert decision["source_version"] == "version_a"
    assert decision["selection_reason"] == "version_b_quality_failed"
    assert "version_b_quality_failed" in decision["soft_signals"]


def test_select_source_for_bullet_slot_prefers_version_a_when_version_b_slot_contract_fails():
    from modules.hybrid_composer import select_source_for_bullet_slot

    decision = select_source_for_bullet_slot(
        slot="B5",
        bullet_a="Ready-to-Record Kit — Includes the mini body camera, USB-C cable, mount, and 32GB memory card so setup is straightforward.",
        bullet_b="Unbox, Charge, and Start Capturing — Includes the kit, 256GB storage, 150-minute battery, and support team help.",
        meta_a={},
        risk_a={},
        meta_b={},
        risk_b={},
        slot_l2_targets=[],
        quality_a={"slot": "B5", "contract_pass": True, "fluency_pass": True, "unsupported_policy_pass": True, "issues": []},
        quality_b={
            "slot": "B5",
            "contract_pass": False,
            "fluency_pass": True,
            "unsupported_policy_pass": True,
            "issues": ["slot_contract_failed:multiple_primary_promises"],
        },
    )

    assert decision["source_version"] == "version_a"
    assert decision["selection_reason"] == "version_b_quality_failed"


def test_compose_hybrid_listing_records_per_slot_bullet_sources(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": [
            "A1 commuting capture",
            "A2 body camera coverage",
            "A3 helmet camera support",
            "A4 guidance",
            "A5 kit",
        ],
        "metadata": {},
        "risk_report": {},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "body camera", "tier": "L2", "assigned_fields": ["B2"]},
                {"keyword": "helmet camera", "tier": "L2", "assigned_fields": ["B3"]},
            ]
        },
    }
    version_b = {
        "title": "B title",
        "bullets": [
            "B1 commuting capture",
            "B2 security evidence coverage",
            "B3 helmet camera support",
            "B4 guidance",
            "B5 kit",
        ],
        "metadata": {},
        "risk_report": {},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "body camera", "tier": "L2", "assigned_fields": ["B2"]},
                {"keyword": "helmet camera", "tier": "L2", "assigned_fields": ["B3"]},
            ],
            "bullet_trace": [
                {"slot": "B1", "audience_group": "commuter"},
                {"slot": "B2", "audience_group": "professional"},
                {"slot": "B3", "audience_group": "cyclist"},
                {"slot": "B4", "audience_group": "general"},
                {"slot": "B5", "audience_group": "general"},
            ],
        },
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["bullets"][1] == "B2 security evidence coverage"
    assert hybrid["bullets"][2] == "B3 helmet camera support"
    assert hybrid["source_trace"]["bullets"][1]["source_version"] == "version_b"
    assert hybrid["source_trace"]["bullets"][1]["selection_reason"] == "slot_default_preference"
    assert "version_b_missing_l2" in hybrid["source_trace"]["bullets"][1]["soft_signals"]
    assert hybrid["source_trace"]["bullets"][2]["source_version"] == "version_b"
    assert hybrid["metadata"]["hybrid_sources"]["bullets"] == "version_b"


def test_compose_hybrid_listing_avoids_version_b_bullet_with_scrub_damage(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2 clean body camera coverage", "A3", "A4", "A5"],
        "metadata": {},
        "risk_report": {},
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [{"keyword": "body camera", "tier": "L2", "assigned_fields": ["B2"]}],
            "bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)],
        },
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2 scrubbed body camera coverage", "B3", "B4", "B5"],
        "metadata": {},
        "risk_report": {},
        "audit_trail": [
            {
                "field": "bullet_b2",
                "action": "delete",
                "reason": "forbidden_visible_terms_scrub",
                "terms": ["stabilization"],
            }
        ],
        "decision_trace": {
            "keyword_assignments": [{"keyword": "body camera", "tier": "L2", "assigned_fields": ["B2"]}],
            "bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)],
        },
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["bullets"][1] == "A2 clean body camera coverage"
    assert hybrid["source_trace"]["bullets"][1]["source_version"] == "version_a"
    assert hybrid["source_trace"]["bullets"][1]["selection_reason"] == "version_b_scrub_integrity_flag"


def test_compose_hybrid_listing_prefers_version_a_when_version_b_slot_quality_fails(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4 clean guidance for stable walking scenes.", "A5"],
        "metadata": {},
        "risk_report": {},
        "audit_trail": [],
        "decision_trace": {"bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)]},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4 broken guidance tail.", "B5"],
        "metadata": {},
        "risk_report": {},
        "audit_trail": [],
        "slot_quality_packets": [
            {"slot": "B1", "contract_pass": True, "fluency_pass": True, "unsupported_policy_pass": True, "issues": []},
            {"slot": "B2", "contract_pass": True, "fluency_pass": True, "unsupported_policy_pass": True, "issues": []},
            {"slot": "B3", "contract_pass": True, "fluency_pass": True, "unsupported_policy_pass": True, "issues": []},
            {"slot": "B4", "contract_pass": False, "fluency_pass": False, "unsupported_policy_pass": True, "issues": ["dash_tail_without_predicate"]},
            {"slot": "B5", "contract_pass": True, "fluency_pass": True, "unsupported_policy_pass": True, "issues": []},
        ],
        "decision_trace": {"bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)]},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["bullets"][3] == "A4 clean guidance for stable walking scenes."
    assert hybrid["source_trace"]["bullets"][3]["source_version"] == "version_a"
    assert hybrid["source_trace"]["bullets"][3]["selection_reason"] == "version_b_quality_failed"


def test_compose_hybrid_listing_understands_legacy_bullet_slot_aliases(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1 travel camera coverage", "A2 body camera with audio", "A3 thumb camera", "A4 guidance", "A5 kit"],
        "metadata": {},
        "risk_report": {},
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "travel camera", "tier": "L2", "assigned_fields": ["bullet_1"]},
                {"keyword": "body camera with audio", "tier": "L2", "assigned_fields": ["bullet_2"]},
            ]
        },
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1 commuting capture", "B2 security evidence coverage", "B3 thumb camera", "B4 guidance", "B5 kit"],
        "metadata": {"visible_llm_fallback_fields": ["bullet_b1", "bullet_b2"]},
        "risk_report": {},
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)]},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["source_trace"]["bullets"][0]["source_version"] == "version_a"
    assert hybrid["source_trace"]["bullets"][1]["source_version"] == "version_a"


def test_compose_hybrid_listing_shadows_selected_bullet_packets_from_mixed_sources(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": [
            "A1 HEADER — A1 benefit. A1 proof.",
            "A2 HEADER — A2 benefit. A2 proof.",
            "A3 HEADER — A3 benefit. A3 proof.",
            "A4 HEADER — A4 benefit. A4 proof.",
            "A5 HEADER — A5 benefit. A5 proof.",
        ],
        "metadata": {},
        "risk_report": {},
        "decision_trace": {
            "bullet_trace": [
                {"slot": "B1", "keywords": ["travel camera"], "capability_mapping": ["battery"], "scene_mapping": ["travel"]},
                {"slot": "B2", "keywords": ["body camera"], "capability_mapping": ["clip"], "scene_mapping": ["security"]},
                {"slot": "B3", "keywords": ["helmet camera"], "capability_mapping": ["wide angle"], "scene_mapping": ["cycling"]},
                {"slot": "B4", "keywords": [], "capability_mapping": ["setup"], "scene_mapping": ["desk"]},
                {"slot": "B5", "keywords": [], "capability_mapping": ["kit"], "scene_mapping": ["daily"]},
            ]
        },
    }
    version_b = {
        "title": "B title",
        "bullets": [
            "B1 HEADER — B1 benefit. B1 proof.",
            "B2 HEADER — B2 benefit. B2 proof.",
            "B3 HEADER — B3 benefit. B3 proof.",
            "B4 HEADER — B4 benefit. B4 proof.",
            "B5 HEADER — B5 benefit. B5 proof.",
        ],
        "metadata": {"visible_llm_fallback_fields": ["bullet_b1"]},
        "risk_report": {},
        "bullet_packets": [
            {"slot": "B1", "header": "B1 HEADER", "benefit": "B1 benefit.", "proof": "B1 proof.", "guidance": ""},
            {"slot": "B2", "header": "B2 HEADER", "benefit": "B2 benefit.", "proof": "B2 proof.", "guidance": ""},
            {"slot": "B3", "header": "B3 HEADER", "benefit": "B3 benefit.", "proof": "B3 proof.", "guidance": ""},
            {"slot": "B4", "header": "B4 HEADER", "benefit": "B4 benefit.", "proof": "B4 proof.", "guidance": ""},
            {"slot": "B5", "header": "B5 HEADER", "benefit": "B5 benefit.", "proof": "B5 proof.", "guidance": ""},
        ],
        "slot_quality_packets": [
            {"slot": "B1", "contract_pass": True, "fluency_pass": True, "keyword_coverage_pass": True, "proof_present": True, "unsupported_policy_pass": True, "format_pass": True, "fallback_used": False, "rerender_count": 0, "issues": []},
            {"slot": "B2", "contract_pass": False, "fluency_pass": True, "keyword_coverage_pass": False, "proof_present": True, "unsupported_policy_pass": True, "format_pass": True, "fallback_used": False, "rerender_count": 0, "issues": ["missing_keywords"]},
            {"slot": "B3", "contract_pass": True, "fluency_pass": True, "keyword_coverage_pass": True, "proof_present": True, "unsupported_policy_pass": True, "format_pass": True, "fallback_used": False, "rerender_count": 0, "issues": []},
            {"slot": "B4", "contract_pass": True, "fluency_pass": True, "keyword_coverage_pass": True, "proof_present": True, "unsupported_policy_pass": True, "format_pass": True, "fallback_used": False, "rerender_count": 0, "issues": []},
            {"slot": "B5", "contract_pass": True, "fluency_pass": True, "keyword_coverage_pass": True, "proof_present": True, "unsupported_policy_pass": True, "format_pass": True, "fallback_used": False, "rerender_count": 0, "issues": []},
        ],
        "decision_trace": {"bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)]},
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert [packet["slot"] for packet in hybrid["bullet_packets"]] == ["B1", "B2", "B3", "B4", "B5"]
    assert hybrid["source_trace"]["bullets"][0]["source_version"] == "version_a"
    assert hybrid["bullet_packets"][0]["header"] == "A1 HEADER"
    assert hybrid["bullet_packets"][1]["header"] == "B2 HEADER"
    assert hybrid["slot_quality_packets"][1]["issues"] == ["missing_keywords"]


def test_compose_hybrid_listing_rebuilds_shadow_packet_when_selected_source_lacks_packet(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2 NATURAL — Works well for secure evidence capture. Stable clip setup.", "A3", "A4", "A5"],
        "metadata": {},
        "risk_report": {},
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [{"keyword": "body camera", "tier": "L2", "assigned_fields": ["B2"]}],
            "bullet_trace": [
                {"slot": "B1"},
                {"slot": "B2", "keywords": ["body camera"], "capability_mapping": ["clip"], "scene_mapping": ["security"]},
                {"slot": "B3"},
                {"slot": "B4"},
                {"slot": "B5"},
            ],
        },
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2 scrubbed body camera coverage", "B3", "B4", "B5"],
        "metadata": {},
        "risk_report": {},
        "audit_trail": [
            {
                "field": "bullet_b2",
                "action": "delete",
                "reason": "forbidden_visible_terms_scrub",
                "terms": ["stabilization"],
            }
        ],
        "bullet_packets": [
            {"slot": "B1", "header": "B1", "benefit": "benefit", "proof": "", "guidance": ""},
            {"slot": "B2", "header": "B2", "benefit": "benefit", "proof": "", "guidance": ""},
            {"slot": "B3", "header": "B3", "benefit": "benefit", "proof": "", "guidance": ""},
            {"slot": "B4", "header": "B4", "benefit": "benefit", "proof": "", "guidance": ""},
            {"slot": "B5", "header": "B5", "benefit": "benefit", "proof": "", "guidance": ""},
        ],
        "slot_quality_packets": [
            {"slot": f"B{i}", "contract_pass": True, "fluency_pass": True, "keyword_coverage_pass": True, "proof_present": True, "unsupported_policy_pass": True, "format_pass": True, "fallback_used": False, "rerender_count": 0, "issues": []}
            for i in range(1, 6)
        ],
        "decision_trace": {
            "keyword_assignments": [{"keyword": "body camera", "tier": "L2", "assigned_fields": ["B2"]}],
            "bullet_trace": [{"slot": f"B{i}"} for i in range(1, 6)],
        },
    }

    hybrid = compose_hybrid_listing(version_a, version_b, tmp_path / "hybrid", DEFAULT_HYBRID_SELECTION_POLICY)

    assert hybrid["source_trace"]["bullets"][1]["source_version"] == "version_a"
    assert hybrid["bullet_packets"][1]["slot"] == "B2"
    assert hybrid["bullet_packets"][1]["header"] == "A2 NATURAL"
    assert hybrid["bullet_packets"][1]["benefit"] == "Works well for secure evidence capture."
    assert hybrid["slot_quality_packets"][1]["slot"] == "B2"


def test_hybrid_launch_gate_does_not_recommend_hybrid_with_field_fallback_blocker():
    decision = build_hybrid_launch_decision(
        risk_report={"listing_status": {"status": "READY_FOR_LISTING"}},
        scoring_results={
            "dimensions": {
                "traffic": {"score": 100},
                "content": {"score": 100},
                "conversion": {"score": 100},
                "readability": {"score": 30},
            }
        },
        hybrid_copy={
            "metadata": {
                "visible_llm_fallback_fields": [],
                "field_provenance": {
                    "description": {
                        "provenance_tier": "safe_fallback",
                        "eligibility": "review_only",
                        "blocking_reasons": ["fallback_not_launch_eligible"],
                    }
                },
            }
        },
    )

    assert decision["passed"] is False
    assert decision["recommended_output"] == "version_a"
    assert "field_safe_fallback_not_launch_eligible:description" in decision["reasons"]
