from types import SimpleNamespace

from modules.report_generator import generate_report
from modules.scoring import calculate_scores


def _preprocessed():
    return SimpleNamespace(
        run_config=SimpleNamespace(
            brand_name="TOSBARRFT",
            target_country="US",
            input_files={},
        ),
        processed_at="2026-04-16T12:00:00",
        language="English",
        target_country="US",
        quality_score=90,
        real_vocab=None,
        data_alerts=[],
        core_selling_points=["180 minute runtime", "clip-on design"],
        attribute_data=SimpleNamespace(data={"video_resolution": "1080P"}),
        keyword_data=SimpleNamespace(
            keywords=[
                {"keyword": "action camera", "search_volume": 20000},
                {"keyword": "body camera", "search_volume": 3500},
                {"keyword": "clip on cam", "search_volume": 200},
            ]
        ),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        capability_constraints={},
        keyword_metadata=[
            {"keyword": "action camera", "tier": "L1"},
            {"keyword": "body camera", "tier": "L2"},
            {"keyword": "clip on cam", "tier": "L3"},
        ],
        ingestion_audit={"tables": []},
        raw_human_insights="",
    )


def test_generate_report_contains_keyword_arsenal_sections():
    preprocessed = _preprocessed()
    generated_copy = {
        "title": "TOSBARRFT action camera with clip design",
        "bullets": [
            "CLIP-ON READY — body camera setup for daily capture.",
            "LONG RUNTIME — records every shift with less charging.",
        ],
        "description": "Portable camera for daily recording.",
        "search_terms": ["clip on cam"],
        "faq": [],
        "aplus_content": "word " * 520,
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
        "compute_tier_map": {},
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "action camera", "tier": "L1", "assigned_fields": ["title"]},
                {"keyword": "body camera", "tier": "L2", "assigned_fields": ["bullet_b1"]},
                {"keyword": "clip on cam", "tier": "L3", "assigned_fields": ["search_terms"]},
            ],
            "bullet_trace": [],
            "search_terms_trace": {"byte_length": 100, "max_bytes": 249},
        },
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"market_pack": {"locale": "US"}}
    scoring_results = calculate_scores(generated_copy, writing_policy, preprocessed)

    report = generate_report(
        preprocessed_data=preprocessed,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report={},
        scoring_results=scoring_results,
        language="English",
        intent_graph=None,
    )

    assert "## Keyword Arsenal" in report
    assert "### Head Traffic Anchors" in report
    assert "### Bullet Conversion / Blue-Ocean Keywords" in report
    assert "### Backend Residual Keywords" in report
    assert "action camera" in report
    assert "body camera" in report
    assert "clip on cam" in report


def test_report_renders_protocol_keyword_decisions():
    from modules.report_generator import _keyword_arsenal_block

    preprocessed = SimpleNamespace(
        keyword_metadata=[
            {
                "keyword": "body camera",
                "traffic_tier": "L1",
                "tier": "L1",
                "quality_status": "qualified",
                "routing_role": "title",
                "opportunity_type": "head_traffic",
            },
            {
                "keyword": "body camera with audio",
                "traffic_tier": "L2",
                "tier": "L2",
                "quality_status": "qualified",
                "routing_role": "bullet",
                "opportunity_type": "conversion_blue_ocean",
            },
            {
                "keyword": "snaproll camera",
                "traffic_tier": "NON_TIER",
                "tier": "NON_TIER",
                "quality_status": "natural_only",
                "routing_role": "natural_only",
                "rejection_reason": "zero_search_volume",
            },
        ],
        keyword_data=SimpleNamespace(keywords=[]),
    )
    generated = {"decision_trace": {"keyword_assignments": []}}

    lines = _keyword_arsenal_block(preprocessed, generated)
    text = "\n".join(lines)

    assert "Traffic Tier" in text
    assert "Quality Status" in text
    assert "Routing Role" in text
    assert "conversion_blue_ocean" in text
    assert "zero_search_volume" in text
