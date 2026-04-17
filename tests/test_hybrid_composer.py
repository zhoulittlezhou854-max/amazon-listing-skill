import json
from pathlib import Path
from types import SimpleNamespace

from modules.hybrid_composer import (
    DEFAULT_HYBRID_SELECTION_POLICY,
    finalize_hybrid_outputs,
    rebuild_hybrid_decision_trace,
    compose_hybrid_listing,
    select_source_for_field,
)
from modules.report_generator import generate_dual_version_report


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
