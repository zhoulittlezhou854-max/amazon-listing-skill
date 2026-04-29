from modules.listing_candidate import build_listing_candidate


def test_reviewable_candidate_allows_missing_description_but_blocks_paste_ready():
    artifact = {
        "title": "4K Mini Camera for Travel",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "",
        "search_terms": "mini camera travel camera",
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_a", artifact, source_type="stable")

    assert candidate["candidate_id"] == "version_a"
    assert candidate["reviewable_status"] == "reviewable"
    assert "description_missing" in candidate["paste_ready_blockers"]
    assert candidate["paste_ready_status"] == "blocked"


def test_partial_version_b_is_debug_only_not_candidate():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three"],
        "description": "Body copy",
        "search_terms": "mini camera",
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_b", artifact, source_type="experimental")

    assert candidate["reviewable_status"] == "not_reviewable"
    assert candidate["paste_ready_status"] == "blocked"
    assert "insufficient_bullets" in candidate["paste_ready_blockers"]
    assert candidate["debug_only"] is True


def test_complete_experimental_version_b_is_reviewable_but_never_paste_ready():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_b", artifact, source_type="experimental")

    assert candidate["reviewable_status"] == "reviewable"
    assert candidate["paste_ready_status"] == "blocked"
    assert "experimental_version_not_paste_ready" in candidate["paste_ready_blockers"]
    assert candidate["debug_only"] is True


def test_failed_generation_is_not_reviewable():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": "mini camera",
        "generation_status": "timed_out",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_b", artifact, source_type="experimental")

    assert candidate["reviewable_status"] == "not_reviewable"
    assert "generation_timed_out" in candidate["paste_ready_blockers"]
    assert candidate["debug_only"] is True


def test_empty_search_terms_list_blocks_paste_ready():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": [],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_a", artifact, source_type="stable")

    assert candidate["search_terms"] == ""
    assert candidate["reviewable_status"] == "reviewable"
    assert candidate["paste_ready_status"] == "blocked"
    assert "search_terms_missing" in candidate["paste_ready_blockers"]


def test_missing_keyword_reconciliation_blocks_paste_ready_but_not_reviewable():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
    }

    candidate = build_listing_candidate("version_a", artifact, source_type="stable")

    assert candidate["reviewable_status"] == "reviewable"
    assert candidate["paste_ready_status"] == "blocked"
    assert "keyword_reconciliation_incomplete" in candidate["paste_ready_blockers"]


def test_complete_keyword_reconciliation_allows_otherwise_complete_paste_ready_candidate():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_a", artifact, source_type="stable")

    assert candidate["paste_ready_status"] == "paste_ready"
    assert candidate["paste_ready_blockers"] == []


def test_not_ready_risk_summary_blocks_paste_ready():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "risk_summary": {
            "listing_status": {
                "status": "NOT_READY_FOR_LISTING",
                "blocking_reasons": ["Repeated word root more than twice: record"],
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["reviewable_status"] == "reviewable"
    assert candidate["paste_ready_status"] == "blocked"
    assert "risk_listing_not_ready" in candidate["paste_ready_blockers"]
    assert "Repeated word root more than twice: record" in candidate["paste_ready_blockers"]


def test_failed_at_stage_status_is_not_reviewable():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "FAILED_AT_BLUEPRINT",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_b", artifact, source_type="experimental")

    assert candidate["reviewable_status"] == "not_reviewable"
    assert "generation_failed_at_blueprint" in candidate["paste_ready_blockers"]
    assert candidate["debug_only"] is True


def test_field_provenance_blocks_paste_ready_for_safe_fallback_description():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Fallback body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "metadata": {
            "field_provenance": {
                "description": {
                    "field": "description",
                    "provenance_tier": "safe_fallback",
                    "eligibility": "review_only",
                    "blocking_reasons": ["fallback_not_launch_eligible"],
                }
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "blocked"
    assert "field_safe_fallback_not_launch_eligible:description" in candidate["paste_ready_blockers"]


def test_field_provenance_allows_repaired_live_description_for_paste_ready():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Repaired body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "metadata": {
            "field_provenance": {
                "description": {
                    "field": "description",
                    "provenance_tier": "repaired_live",
                    "eligibility": "launch_eligible",
                    "blocking_reasons": [],
                }
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "paste_ready"
    assert candidate["paste_ready_blockers"] == []


def test_field_provenance_blocks_paste_ready_for_unsafe_fallback_description():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Unsafe fallback body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "metadata": {
            "field_provenance": {
                "description": {
                    "field": "description",
                    "provenance_tier": "unsafe_fallback",
                    "eligibility": "blocked",
                    "blocking_reasons": ["unsafe_fallback"],
                }
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "blocked"
    assert "field_unsafe_fallback:description" in candidate["paste_ready_blockers"]


def test_field_provenance_blocks_paste_ready_for_unavailable_description():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "metadata": {
            "field_provenance": {
                "description": {
                    "field": "description",
                    "provenance_tier": "unavailable",
                    "eligibility": "blocked",
                    "blocking_reasons": ["field_unavailable"],
                }
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "blocked"
    assert "field_unavailable:description" in candidate["paste_ready_blockers"]


def test_slot_contract_failure_blocks_paste_ready_with_slot_reason():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "slot_quality_packets": [
            {"slot": "B5", "issues": ["slot_contract_failed:multiple_primary_promises"]},
        ],
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "blocked"
    assert "slot_contract_failed:B5:multiple_primary_promises" in candidate["paste_ready_blockers"]


def test_missing_slot_quality_still_validates_visible_b5_before_paste_ready():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": [
            "One",
            "Two",
            "Three",
            "Four",
            (
                "Open Box, Start Recording — Includes the wearable camera, USB-C cable, and clip. "
                "With 150 minutes of battery life, it keeps up with travel. Supports 256GB cards."
            ),
        ],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
    }

    candidate = build_listing_candidate("version_a", artifact, source_type="stable")

    assert candidate["paste_ready_status"] == "blocked"
    assert "slot_contract_failed:B5:multiple_primary_promises" in candidate["paste_ready_blockers"]


def test_canonical_fact_readiness_blocks_missing_but_not_known_blocked_without_claim():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "metadata": {
            "canonical_fact_readiness": {
                "blocking_missing": ["battery_life"],
                "required_fact_status": {"waterproof_supported": "known_blocked"},
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "blocked"
    assert "canonical_fact_missing:battery_life" in candidate["paste_ready_blockers"]
    assert "canonical_fact_blocked_claim:waterproof_supported" not in candidate["paste_ready_blockers"]


def test_canonical_fact_blocked_claim_requires_explicit_claim_blocker():
    artifact = {
        "title": "4K Mini Camera",
        "bullets": ["One", "Two", "Three", "Four", "Five"],
        "description": "Body copy",
        "search_terms": ["mini camera"],
        "generation_status": "live_success",
        "keyword_reconciliation": {"status": "complete"},
        "metadata": {
            "canonical_fact_readiness": {
                "required_fact_status": {"waterproof_supported": "known_blocked"},
                "blocked_claim_facts": ["waterproof_supported"],
            }
        },
    }

    candidate = build_listing_candidate("hybrid", artifact, source_type="hybrid")

    assert candidate["paste_ready_status"] == "blocked"
    assert "canonical_fact_blocked_claim:waterproof_supported" in candidate["paste_ready_blockers"]
