from modules.hybrid_optimizer import (
    LISTING_L2_COVERAGE_THRESHOLD,
    analyze_listing_l2_coverage,
    collect_missing_l2_keywords,
    repair_hybrid_bullets_for_l2,
)


def test_collect_missing_l2_keywords_returns_uncovered_keywords():
    bullets = [
        "Capture hands-free commuting footage.",
        "Wear it discreetly for shift recording.",
        "Clip it to your helmet for cycling.",
        "Use stable mounts for smoother results.",
        "Includes cable and storage support.",
    ]
    assigned_l2 = ["travel camera", "shift camera", "helmet camera"]

    missing = collect_missing_l2_keywords(bullets, assigned_l2)

    assert "travel camera" in missing
    assert "shift camera" in missing
    assert "helmet camera" in missing


def test_analyze_listing_l2_coverage_meets_threshold_with_three_slots():
    bullets = [
        "Travel camera coverage for commuting capture.",
        "Body camera with audio for shift documentation.",
        "Thumb camera versatility for POV content.",
        "Stable guidance for walking scenes.",
        "Kit details and storage support.",
    ]
    slot_targets = {
        "B1": ["travel camera"],
        "B2": ["body camera with audio"],
        "B3": ["thumb camera"],
    }

    result = analyze_listing_l2_coverage(bullets, slot_targets, threshold=LISTING_L2_COVERAGE_THRESHOLD)

    assert result["coverage_count"] == 3
    assert result["meets_threshold"] is True
    assert result["missing_keywords"] == []


def test_analyze_listing_l2_coverage_below_threshold_collects_missing_keywords():
    bullets = [
        "Travel camera coverage for commuting capture.",
        "Shift documentation for daily use.",
        "Generic POV recording.",
        "Stable guidance for walking scenes.",
        "Kit details and storage support.",
    ]
    slot_targets = {
        "B1": ["travel camera"],
        "B2": ["body camera with audio"],
        "B3": ["thumb camera"],
    }

    result = analyze_listing_l2_coverage(bullets, slot_targets, threshold=LISTING_L2_COVERAGE_THRESHOLD)

    assert result["coverage_count"] == 1
    assert result["meets_threshold"] is False
    assert "body camera with audio" in result["missing_keywords"]
    assert "thumb camera" in result["missing_keywords"]


def test_repair_hybrid_bullets_for_l2_returns_diagnostics_without_mutating_text():
    bullets = [
        "Thumb-Sized POV Companion — Clip this mini camera to your helmet or bike for hands-free recording.",
        "Reliable Evidence Capture — Designed for security and service professionals.",
        "Extended Runtime — Capture more with a 150-minute battery.",
        "Recording Guidance — Use stable mounts for smoother footage.",
        "Complete Kit — Includes cable and storage support.",
    ]

    diagnostics = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera"],
        max_repairs=1,
    )

    assert diagnostics["bullets"] == bullets
    assert diagnostics["missing_keywords"] == ["travel camera"]
    assert diagnostics["repair_actions"] == []
    assert diagnostics["repair_skipped_reason"] == "text_suffix_injection_disabled"
    assert diagnostics["candidate_slots"][0]["slot"] == "B1"


def test_repair_hybrid_bullets_for_l2_ranks_candidate_slots_without_patching_copy():
    bullets = [
        "Daily commute recording with a magnetic clip.",
        "Professional documentation for security shifts and incident evidence.",
        "Hands-free POV capture for cycling and helmet use.",
        "Stable guidance for walking scenes.",
        "Accessories and storage support in the box.",
    ]

    diagnostics = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["pov camera"],
        max_repairs=1,
    )

    assert diagnostics["repair_actions"] == []
    assert diagnostics["candidate_slots"][0]["slot"] == "B3"
    assert diagnostics["bullets"] == bullets


def test_repair_hybrid_bullets_for_l2_reports_empty_state_cleanly():
    diagnostics = repair_hybrid_bullets_for_l2([], missing_keywords=[], max_repairs=2)

    assert diagnostics["bullets"] == []
    assert diagnostics["missing_keywords"] == []
    assert diagnostics["candidate_slots"] == []
    assert diagnostics["repair_actions"] == []
    assert diagnostics["repair_skipped_reason"] == "no_missing_keywords"
