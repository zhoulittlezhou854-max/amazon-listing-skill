from modules.hybrid_optimizer import collect_missing_l2_keywords, repair_hybrid_bullets_for_l2


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
