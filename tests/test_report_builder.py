from modules import report_builder as rb


def test_build_readiness_summary_renders_expected_sections():
    generated_copy = {
        'title': 'Test title',
        'bullets': ['B1 text', 'B2 text', 'B3 text', 'B4 text', 'B5 text'],
        'search_terms': ['body camera', 'travel camera'],
        'metadata': {'generation_status': 'live_success'},
    }
    scoring_results = {
        'listing_status': 'READY_FOR_LISTING',
        'dimensions': {
            'traffic': {'label': 'A10', 'score': 100, 'max': 100, 'status': 'pass'},
            'content': {'label': 'COSMO', 'score': 100, 'max': 100, 'status': 'pass'},
            'conversion': {'label': 'Rufus', 'score': 90, 'max': 100, 'status': 'pass'},
            'readability': {'label': 'Fluency', 'score': 30, 'max': 30, 'status': 'pass'},
        },
        'action_required': '',
    }
    risk_report = {'review_queue': []}

    content = rb.build_readiness_summary(
        sku='H91lite_US',
        run_id='r14',
        generated_copy=generated_copy,
        scoring_results=scoring_results,
        risk_report=risk_report,
        generated_at='2026-04-15',
    )

    assert '# Listing Readiness Summary' in content
    assert 'READY_FOR_LISTING' in content
    assert '| A10 流量 | 100/100 | ✅ |' in content
    assert '**Title:** Test title' in content
    assert '- B5: B5 text' in content
    assert '**Search Terms:** body camera, travel camera' in content
    assert '无' in content
    assert '可直接上架' in content


def test_readiness_summary_uses_final_visible_quality_blockers():
    generated_copy = {
        "title": "Title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "Description",
        "search_terms": ["term"],
        "metadata": {
            "generation_status": "live_success",
            "final_visible_quality": {
                "operational_status": "NOT_READY_FOR_LISTING",
                "paste_ready_blockers": ["slot_contract_failed:B5:multiple_primary_promises"],
                "review_only_warnings": ["rufus_backend_search_terms_underused"],
            },
        },
    }
    scoring_results = {
        "action_required": "可直接上架",
        "dimensions": {
            "traffic": {"score": 100, "max": 100, "status": "pass"},
            "content": {"score": 92, "max": 100, "status": "pass"},
            "conversion": {"score": 89, "max": 100, "status": "pass"},
            "readability": {"score": 30, "max": 30, "status": "pass"},
        },
    }

    summary = rb.build_readiness_summary(
        sku="H91lite_US",
        run_id="version_a",
        generated_copy=generated_copy,
        scoring_results=scoring_results,
        risk_report={"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
        generated_at="2026-04-30T00:00:00",
    )

    assert "候选文案状态" in summary
    assert "NOT_READY_FOR_LISTING" in summary
    assert "slot_contract_failed:B5:multiple_primary_promises" in summary
    assert "final_readiness_verdict.json" in summary
    assert "可直接上架" not in summary
