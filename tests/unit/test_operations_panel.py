from types import SimpleNamespace

from modules.operations_panel import build_prelaunch_checklist, build_thirty_day_iteration_panel


def _preprocessed(country: str = "FR"):
    return SimpleNamespace(
        run_config=SimpleNamespace(target_country=country, brand_name="TestBrand"),
        target_country=country,
    )


def test_prelaunch_checklist_flags_blockers_and_missing_signals():
    generated_copy = {
        "metadata": {"generation_status": "live_with_fallback"},
        "evidence_bundle": {
            "claim_support_matrix": [{"claim": "stormproof use", "support_status": "unsupported"}],
            "rufus_readiness": {"score": 0.0, "supported_claim_count": 0, "total_claim_count": 1},
        },
        "compute_tier_map": {
            "title": {"tier_used": "rule_based", "rerun_recommended": True, "rerun_priority": "high"},
        },
        "decision_trace": {"search_terms_trace": {"byte_length": 80, "max_bytes": 249}},
    }
    writing_policy = {"market_pack": {"locale": "FR"}}
    risk_report = {"listing_status": {"status": "NOT_READY_FOR_LISTING", "blocking_reasons": ["restricted claim"]}}
    scoring_results = {
        "production_readiness": {"generation_status": "live_with_fallback"},
        "aplus_word_count_check": {"meets_minimum": False},
    }

    checklist = build_prelaunch_checklist(_preprocessed(), generated_copy, writing_policy, risk_report, scoring_results)

    assert checklist["blocking_count"] >= 1
    statuses = {item["key"]: item["status"] for item in checklist["items"]}
    assert statuses["listing_status"] == "fail"
    assert statuses["unsupported_claims"] == "fail"


def test_thirty_day_iteration_panel_returns_four_stages():
    generated_copy = {
        "evidence_bundle": {
            "claim_support_matrix": [{"claim": "180 minute runtime", "support_status": "supported"}],
            "rufus_readiness": {"score": 1.0, "supported_claim_count": 1, "total_claim_count": 1},
        },
        "compute_tier_map": {
            "title": {"tier_used": "native", "rerun_recommended": False, "rerun_priority": "normal"},
        },
    }
    writing_policy = {
        "market_pack": {"locale": "FR", "after_sales_promises": ["FR support"]},
        "intent_weight_summary": {"updated_keyword_count": 3, "top_external_themes": ["commuter vlog setup"]},
    }
    risk_report = {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}}
    scoring_results = {"total_score": 268, "ai_os_score": 72}

    panel = build_thirty_day_iteration_panel(_preprocessed(), generated_copy, writing_policy, risk_report, scoring_results)

    assert [stage["day"] for stage in panel["stages"]] == [0, 7, 14, 30]
    assert panel["stages"][0]["focus"]
