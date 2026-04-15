from modules.compute_tiering import build_compute_tier_map, summarize_compute_tier_map


def test_compute_tier_map_contains_visible_fields():
    generated_copy = {
        "title": "Action Camera",
        "bullets": ["B1", "B2"],
        "description": "Compact camera",
        "search_terms": ["helmet camera"],
        "aplus_content": "Story",
        "metadata": {"visible_llm_fallback_fields": ["bullet_1", "description"]},
    }

    tier_map = build_compute_tier_map(generated_copy)

    assert set(tier_map) >= {"title", "bullet_1", "description", "search_terms", "aplus_content"}


def test_compute_tier_map_marks_fallback_fields_for_rerun():
    generated_copy = {
        "title": "Action Camera",
        "bullets": ["B1", "B2"],
        "metadata": {"visible_llm_fallback_fields": ["bullet_1"]},
    }

    tier_map = build_compute_tier_map(generated_copy)

    assert tier_map["bullet_1"]["rerun_recommended"] is True
    assert tier_map["title"]["tier_used"] in {"native", "polish", "rule_based"}


def test_compute_tier_map_understands_numeric_bullet_fallback_labels():
    generated_copy = {
        "title": "Action Camera",
        "bullets": ["B1", "B2"],
        "metadata": {"visible_llm_fallback_fields": ["1"]},
    }

    tier_map = build_compute_tier_map(generated_copy)

    assert tier_map["bullet_1"]["tier_used"] == "rule_based"


def test_summarize_compute_tier_map_counts_fallback_fields():
    summary = summarize_compute_tier_map(
        {
            "title": {"tier_used": "native", "rerun_recommended": False, "rerun_priority": "normal"},
            "bullet_1": {"tier_used": "rule_based", "rerun_recommended": True, "rerun_priority": "high"},
            "description": {"tier_used": "rule_based", "rerun_recommended": True, "rerun_priority": "normal"},
        }
    )

    assert summary["field_count"] == 3
    assert summary["fallback_field_count"] == 2
    assert summary["rerun_recommended_count"] == 2
    assert summary["high_priority_rerun_fields"] == ["bullet_1"]
