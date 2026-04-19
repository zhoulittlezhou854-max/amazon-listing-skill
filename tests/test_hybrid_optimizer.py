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


def test_repair_hybrid_bullets_for_l2_injects_keyword_without_rewriting_whole_bullet():
    bullets = [
        "Thumb-Sized POV Companion — Clip this mini camera to your helmet or bike for hands-free recording.",
        "Reliable Evidence Capture — Designed for security and service professionals.",
        "Extended Runtime — Capture more with a 150-minute battery.",
        "Recording Guidance — Use stable mounts for smoother footage.",
        "Complete Kit — Includes cable and storage support.",
    ]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera"],
        max_repairs=1,
    )

    assert repaired[0].startswith("Thumb-Sized POV Companion")
    assert any("travel camera" in bullet.lower() for bullet in repaired)
    assert actions[0]["action"] == "l2_backfill"
    assert actions[0]["keyword"] == "travel camera"


def test_repair_hybrid_bullets_skips_unsafe_candidate_and_tries_later_slot():
    bullets = ["A" * 245, "short", "short", "short", "short"]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera"],
        max_repairs=1,
    )

    assert repaired[0] == bullets[0]
    assert repaired[1] != bullets[1]
    assert actions[0]["slot"] == "B2"


def test_repair_hybrid_bullets_limits_total_repairs_to_two():
    bullets = [
        "Bullet one for daily capture.",
        "Bullet two for shift recording.",
        "Bullet three for helmet use.",
        "Bullet four for stable mounting.",
        "Bullet five for included accessories.",
    ]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera", "body camera", "helmet camera"],
        max_repairs=2,
    )

    assert len(actions) == 2
    assert sum(1 for before, after in zip(bullets, repaired) if before != after) == 2


def test_repair_hybrid_bullets_prefers_semantically_closest_slot():
    bullets = [
        "Daily commute recording with a magnetic clip.",
        "Professional documentation for security shifts and incident evidence.",
        "Hands-free POV capture for cycling and helmet use.",
        "Stable guidance for walking scenes.",
        "Accessories and storage support in the box.",
    ]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["pov camera"],
        max_repairs=1,
    )

    assert actions[0]["slot"] == "B3"
    assert "pov camera" in repaired[2].lower()
    assert repaired[0] == bullets[0]


def test_repair_hybrid_bullets_does_not_default_to_b5_when_earlier_slot_is_better_match():
    bullets = [
        "Travel-ready recording for daily commuting.",
        "Body-worn evidence capture for security professionals.",
        "POV support for cyclists and training rides.",
        "Stable-use guidance for walking scenes.",
        "Kit details and charging cable support.",
    ]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["body camera with audio"],
        max_repairs=1,
    )

    assert actions[0]["slot"] == "B2"
    assert "body camera with audio" in repaired[1].lower()
    assert repaired[4] == bullets[4]


def test_repair_hybrid_bullets_can_patch_realistic_long_bullet_without_for_with_blowup():
    bullets = [
        "Extended-session wearable recording for travel footage with magnetic clip support and lightweight hands-free capture across daily commutes and walking scenes.",
        "Discreet evidence-ready design with 1080P video and AAC audio for reliable incident documentation during full shifts.",
        "Thumb-sized commuting companion for cyclists and urban commuters in steady-paced scenes.",
        "Optimal use guidance for walking tours and static mounting in stable recording scenarios.",
        "Complete recording kit with USB Type-C cable and storage support for longer sessions.",
    ]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera"],
        max_repairs=1,
    )

    assert actions
    assert any("travel camera" in bullet.lower() for bullet in repaired)


def test_repair_hybrid_bullets_can_replace_generic_tail_on_overlong_real_run_bullet():
    bullets = [
        "extended-session Wearable Recording — Capture immersive 1080P HD travel footage for up to 150 minutes on a single charge. "
        "The lightweight 0.1 kg design with magnetic clip enables hands-free vlogging and documentation anywhere, ideal for content creators and adventurers.",
        "Discreet Evidence-Ready Design — Features 1080P video with audio and loop recording for reliable evidence capture during full shifts. "
        "The camera lens rotates 180° for flexible mounting, ideal for security, service professionals, or any accountability needs.",
    ]

    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera"],
        max_repairs=1,
    )

    assert actions
    assert actions[0]["slot"] == "B1"
    assert "travel camera" in repaired[0].lower()
    assert len(repaired[0]) <= 255
