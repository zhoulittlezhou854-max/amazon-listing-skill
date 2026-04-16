from types import SimpleNamespace

from modules import report_builder as rb
from modules import report_generator as rg
from modules.listing_status import derive_listing_status


def test_readiness_summary_matches_listing_report_and_risk_status_on_medium_fluency_block():
    generated_copy = {
        "title": "TestBrand Action Camera for Daily Vlogging with 1080P Video and 150-Minute Runtime",
        "bullets": [
            "COMMUTE READY POV — Clip on and capture every train ride hands-free.",
            "EVIDENCE READY RECORDING — Keep a clear record for security rounds and service shifts.",
            "TRAVEL CLIP VIEW — Stay ready for daily rides and quick street moments.",
            "DAILY RIDE RECORDING — Keep spontaneous commute footage easy to catch.",
            "KIT READY VALUE — Includes the accessories you need to start fast.",
        ],
        "search_terms": ["body camera", "travel camera"],
        "metadata": {
            "generation_status": "live_success",
            "llm_response_state": "success",
            "visible_llm_fallback_fields": [],
        },
    }
    risk_report = {
        "overall_passed": True,
        "fluency": {
            "issues": [
                {
                    "rule": "fluency_bullet_dimension_dedup",
                    "description": 'Repeated bullet dimension "mobility_commute" across bullets [1, 3, 4]',
                    "severity": "medium",
                    "field": "bullets",
                }
            ]
        },
        "review_queue": [
            {"field": "bullets", "issue": "dimension_repeat", "priority": "P1"},
        ],
    }
    risk_report["listing_status"] = derive_listing_status(
        "live_success",
        risk_report,
        llm_response_state="success",
        visible_fallback_fields=[],
    )
    scoring_results = {
        "listing_status": "READY_FOR_LISTING",
        "dimensions": {
            "traffic": {"score": 100, "max": 100, "status": "pass"},
            "content": {"score": 92, "max": 100, "status": "pass"},
            "conversion": {"score": 90, "max": 100, "status": "pass"},
            "readability": {"score": 30, "max": 30, "status": "pass"},
        },
        "action_required": "",
    }

    report_lines = rg._listing_readiness_block(generated_copy["metadata"], risk_report)
    readiness_summary = rb.build_readiness_summary(
        sku="H91lite_US",
        run_id="r16_v2a_fix",
        generated_copy=generated_copy,
        scoring_results=scoring_results,
        risk_report=risk_report,
        generated_at="2026-04-16",
    )

    assert risk_report["listing_status"]["status"] == "NOT_READY_FOR_LISTING"
    assert any("Status: NOT_READY_FOR_LISTING" in line for line in report_lines)
    assert "NOT_READY_FOR_LISTING" in readiness_summary
    assert "READY_FOR_LISTING" not in readiness_summary.replace("NOT_READY_FOR_LISTING", "")
