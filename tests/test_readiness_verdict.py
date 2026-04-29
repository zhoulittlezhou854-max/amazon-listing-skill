from modules.readiness_verdict import build_readiness_verdict


def _candidate(
    candidate_id,
    *,
    paste_ready="eligible",
    reviewable="reviewable",
    blockers=None,
    source_trace=None,
    reconciliation_status="complete",
    source_type=None,
):
    return {
        "candidate_id": candidate_id,
        "paste_ready_status": paste_ready,
        "reviewable_status": reviewable,
        "paste_ready_blockers": blockers or [],
        "source_trace": source_trace if source_trace is not None else {"title": candidate_id},
        "keyword_reconciliation": {"status": reconciliation_status},
        "source_type": source_type or candidate_id,
    }


def _ranking(verdict, candidate_id):
    return next(row for row in verdict["candidate_rankings"] if row["candidate_id"] == candidate_id)


def test_hybrid_wins_when_complete_and_gate_passing():
    verdict = build_readiness_verdict(
        candidates={
            "version_a": _candidate("version_a"),
            "version_b": _candidate("version_b"),
            "hybrid": _candidate("hybrid", source_trace={"bullet_1": "version_b"}),
        },
        run_state="success",
    )

    assert verdict["recommended_output"] == "hybrid"
    assert verdict["operational_listing_status"] == "READY_FOR_LISTING"
    assert verdict["candidate_listing_status"] == "READY_FOR_LISTING"
    assert verdict["launch_gate"]["passed"] is True
    assert _ranking(verdict, "hybrid")["eligibility"] == "paste_ready"


def test_missing_hybrid_source_trace_blocks_paste_ready_and_falls_back_to_version_a():
    verdict = build_readiness_verdict(
        candidates={
            "version_a": _candidate("version_a"),
            "hybrid": _candidate("hybrid", source_trace={}),
        },
        run_state="success",
    )

    assert verdict["recommended_output"] == "version_a"
    assert verdict["operational_listing_status"] == "READY_FOR_LISTING"
    hybrid = _ranking(verdict, "hybrid")
    assert hybrid["eligibility"] == "review_only"
    assert "source_trace_missing" in hybrid["blockers"]


def test_no_paste_ready_but_reviewable_candidate_outputs_review_required_and_recommends_version_a():
    verdict = build_readiness_verdict(
        candidates={
            "version_a": _candidate(
                "version_a",
                paste_ready="blocked",
                blockers=["description_missing"],
            )
        },
        run_state="partial_success",
    )

    assert verdict["operational_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["candidate_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["launch_gate"]["passed"] is False
    assert verdict["recommended_output"] == "version_a"
    assert _ranking(verdict, "version_a")["eligibility"] == "review_only"


def test_paste_ready_status_value_is_compatible_with_paste_ready_eligibility():
    verdict = build_readiness_verdict(
        candidates={"version_a": _candidate("version_a", paste_ready="PASTE_READY")},
        run_state="success",
    )

    assert verdict["recommended_output"] == "version_a"
    assert verdict["operational_listing_status"] == "READY_FOR_LISTING"
    assert _ranking(verdict, "version_a")["eligibility"] == "paste_ready"


def test_incomplete_keyword_reconciliation_recomputed_as_blocker():
    verdict = build_readiness_verdict(
        candidates={
            "version_a": _candidate(
                "version_a",
                reconciliation_status="pending",
            )
        },
        run_state="success",
    )

    assert verdict["operational_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["recommended_output"] == "version_a"
    row = _ranking(verdict, "version_a")
    assert row["eligibility"] == "review_only"
    assert "keyword_reconciliation_incomplete" in row["blockers"]


def test_version_b_alone_is_review_required_not_launch_ready():
    verdict = build_readiness_verdict(
        candidates={"version_b": _candidate("version_b", paste_ready="eligible")},
        run_state="partial_success",
    )

    assert verdict["recommended_output"] == "version_b"
    assert verdict["operational_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["launch_gate"]["passed"] is False
    row = _ranking(verdict, "version_b")
    assert row["eligibility"] == "review_only"
    assert "experimental_version_b_not_launch_authority" in row["blockers"]


def test_blocked_verdict_preserves_concrete_candidate_blockers():
    verdict = build_readiness_verdict(
        candidates={
            "version_a": _candidate(
                "version_a",
                paste_ready="blocked",
                reviewable="not_reviewable",
                blockers=["generation_timed_out", "title_missing"],
            )
        },
        run_state="failed",
    )

    assert verdict["operational_listing_status"] == "BLOCKED"
    assert verdict["recommended_output"] == ""
    assert verdict["launch_gate"]["passed"] is False
    assert "no_reviewable_candidate" in verdict["launch_gate"]["blockers"]
    assert "generation_timed_out" in verdict["launch_gate"]["blockers"]
    assert "title_missing" in verdict["launch_gate"]["blockers"]


def test_safe_fallback_field_projects_review_required_not_listing_ready():
    verdict = build_readiness_verdict(
        candidates={
            "hybrid": _candidate(
                "hybrid",
                paste_ready="blocked",
                blockers=["field_safe_fallback_not_launch_eligible:description"],
                source_trace={"description": None},
            )
        },
        run_state="success",
    )

    assert verdict["operational_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["candidate_listing_status"] == "REVIEW_REQUIRED"
    assert verdict["launch_gate"]["passed"] is False
    assert verdict["recommended_output"] == "hybrid"
    assert "field_safe_fallback_not_launch_eligible:description" in verdict["launch_gate"]["blockers"]


def test_repaired_live_field_can_remain_paste_ready_when_other_gates_pass():
    verdict = build_readiness_verdict(
        candidates={
            "hybrid": _candidate(
                "hybrid",
                paste_ready="paste_ready",
                blockers=[],
                source_trace={"description": "version_a"},
            )
        },
        run_state="success",
    )

    assert verdict["operational_listing_status"] == "READY_FOR_LISTING"
    assert verdict["launch_gate"]["passed"] is True
    assert _ranking(verdict, "hybrid")["eligibility"] == "paste_ready"
