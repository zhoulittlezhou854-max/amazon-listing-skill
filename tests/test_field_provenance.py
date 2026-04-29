from modules.field_provenance import build_field_candidate, select_launch_eligible_field


def test_repaired_live_description_is_launch_eligible_when_risk_passes():
    candidate = build_field_candidate(
        "description",
        "Repaired description with verified claims.",
        "version_b",
        metadata={"field_provenance": {"description": "repaired_live"}},
        risk_summary={"blocking_fields": []},
    )

    assert candidate["field"] == "description"
    assert candidate["text_present"] is True
    assert candidate["source_version"] == "version_b"
    assert candidate["provenance_tier"] == "repaired_live"
    assert candidate["eligibility"] == "launch_eligible"
    assert candidate["blocking_reasons"] == []


def test_safe_fallback_description_is_review_only_and_not_selected_for_launch():
    candidate = build_field_candidate(
        "description",
        "Fallback description for review only.",
        "version_a",
        metadata={"visible_llm_fallback_fields": ["description"]},
        risk_summary={"blocking_fields": []},
    )

    selected = select_launch_eligible_field("description", [candidate])

    assert candidate["provenance_tier"] == "safe_fallback"
    assert candidate["eligibility"] == "review_only"
    assert "fallback_not_launch_eligible" in candidate["blocking_reasons"]
    assert selected["source_version"] == "version_a"
    assert selected["eligibility"] == "review_only"
    assert selected["launch_eligible"] is False


def test_field_matching_normalizes_case_aliases_and_metadata_keys():
    fallback_candidate = build_field_candidate(
        "description",
        "Fallback description for review only.",
        "version_a",
        metadata={"visible_llm_fallback_fields": ["Description"]},
        risk_summary={"blocking_fields": []},
    )
    unsafe_candidate = build_field_candidate(
        "DESCRIPTION",
        "Unsafe fallback description.",
        "version_a",
        metadata={"field_provenance": {"Description": {"provenance_tier": "unsafe_fallback"}}},
        risk_summary={"blocking_fields": []},
    )
    blocked_candidate = build_field_candidate(
        "product_description",
        "Risk-blocked description.",
        "version_a",
        metadata={},
        risk_summary={"blocking_fields": ["Description"]},
    )

    assert fallback_candidate["field"] == "description"
    assert fallback_candidate["provenance_tier"] == "safe_fallback"
    assert fallback_candidate["eligibility"] == "review_only"
    assert unsafe_candidate["field"] == "description"
    assert unsafe_candidate["provenance_tier"] == "unsafe_fallback"
    assert unsafe_candidate["eligibility"] == "blocked"
    assert blocked_candidate["field"] == "description"
    assert "risk_blocked:description" in blocked_candidate["blocking_reasons"]
