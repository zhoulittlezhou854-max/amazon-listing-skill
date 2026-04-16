from modules.copy_generation import _enforce_bullet_length
from modules.writing_policy import LENGTH_RULES, DEFAULT_4SCENE_POLICY


def test_title_length_rules_are_centralized():
    title_rules = LENGTH_RULES["title"]

    assert title_rules["target_min"] == 160
    assert title_rules["target_max"] == 190
    assert title_rules["hard_ceiling"] == 200
    assert title_rules["soft_warning"] == 150
    assert DEFAULT_4SCENE_POLICY["title_keyword_slots"]["max_title_length"] == title_rules["hard_ceiling"]


def test_bullet_length_rules_are_centralized():
    bullet_rules = LENGTH_RULES["bullet"]

    assert bullet_rules["target_min"] == 200
    assert bullet_rules["target_max"] == 250
    assert bullet_rules["hard_ceiling"] == 500
    assert bullet_rules["seo_byte_limit"] == 1000


def test_enforce_bullet_length_uses_hard_ceiling():
    long_bullet = "HEADER — " + ("a" * 700)

    trimmed = _enforce_bullet_length(long_bullet)

    assert len(trimmed) <= LENGTH_RULES["bullet"]["hard_ceiling"]


def test_bullet_total_seo_bytes_limit_reference_is_1000():
    bullets = [
        "HEADER — Compact body camera for commuting capture.",
        "HEADER — Lightweight clip-on setup for travel days.",
        "HEADER — Records clear 1080P footage for daily use.",
        "HEADER — Includes kit pieces for flexible mounting.",
        "HEADER — Battery runtime supports full-shift recording.",
    ]

    total_bytes = sum(len(b.encode("utf-8")) for b in bullets)

    assert total_bytes <= LENGTH_RULES["bullet"]["seo_byte_limit"]
