from modules import coherence_check as cc
from modules.risk_check import perform_risk_check


def test_duplicate_dimension_detected_when_two_bullets_both_mention_weight():
    bullets = [
        "LIGHTWEIGHT BODY — At just 35g, it disappears on your shirt during every commute.",
        "PORTABLE BUILD — The lightweight 0.1 kilograms frame stays comfortable on long rides.",
        "CLEAR AUDIO — Built-in mic keeps voice notes crisp.",
    ]

    issues = cc.check_coherence("1080P body camera", bullets, "")

    assert any(issue.issue_type == "duplicate_dimension" for issue in issues)


def test_duplicate_dimension_not_triggered_when_each_bullet_covers_different_spec():
    bullets = [
        "LIGHTWEIGHT BODY — At just 35g, it disappears on your shirt during every commute.",
        "LONG BATTERY — Up to 150 minutes keeps errands covered without recharging.",
        "CRISP VIDEO — 1080P footage keeps license plates and package drops easy to review.",
        "CLEAR AUDIO — Built-in mic keeps voice notes crisp.",
    ]

    issues = cc.check_coherence("1080P body camera", bullets, "")

    assert not any(issue.issue_type == "duplicate_dimension" for issue in issues)


def test_title_claim_not_expanded_detected_when_4k_missing_from_all_bullets():
    title = "4K Body Camera, 150 Minutes, Thumb Camera"
    bullets = [
        "LIGHTWEIGHT BODY — At just 35g, it disappears on your shirt during every commute.",
        "LONG BATTERY — Up to 150 minutes keeps errands covered without recharging.",
    ]

    issues = cc.check_coherence(title, bullets, "")

    assert any(issue.issue_type == "title_claim_not_expanded" for issue in issues)
    expanded_issue = next(issue for issue in issues if issue.issue_type == "title_claim_not_expanded")
    assert expanded_issue.fields == ["title"]


def test_title_claim_expanded_passes_when_at_least_one_bullet_covers_spec():
    title = "4K Body Camera, 150 Minutes, Thumb Camera"
    bullets = [
        "CRISP VIDEO — 4K footage keeps license plates and package drops easy to review.",
        "LONG BATTERY — Up to 150 minutes keeps errands covered without recharging.",
    ]

    issues = cc.check_coherence(title, bullets, "")

    assert not any(issue.issue_type == "title_claim_not_expanded" for issue in issues)


def test_coherence_issues_do_not_block_listing_status():
    generated_copy = {
        "title": "4K Body Camera, 150 Minutes, Thumb Camera",
        "bullets": [
            "LIGHTWEIGHT BODY — At just 35g, it disappears on your shirt during every commute.",
            "TRAVEL READY BUILD — The lightweight 0.1 kilograms frame stays comfortable on long rides.",
            "LONG BATTERY — Up to 150 minutes keeps errands covered without recharging.",
            "CLEAR AUDIO — Built-in mic keeps voice notes crisp.",
            "WIDE VIEW — 170 degree coverage keeps sidewalks visible.",
        ],
        "description": "Compact wearable camera for commuting.",
        "aplus_content": "Module 1: 35g build. Module 2: 150 minutes runtime.",
        "metadata": {"generation_status": "live_success", "llm_response_state": "ok", "target_language": "English"},
    }

    risk = perform_risk_check(generated_copy, writing_policy={"target_language": "English"}, attribute_data={}, preprocessed_data=None)

    assert risk["listing_status"]["status"] == "READY_FOR_LISTING"
    assert risk["coherence"]["issues"]


def test_coherence_issues_appear_in_review_queue_as_p2():
    generated_copy = {
        "title": "4K Body Camera, 150 Minutes, Thumb Camera",
        "bullets": [
            "LIGHTWEIGHT BODY — At just 35g, it disappears on your shirt during every commute.",
            "TRAVEL READY BUILD — The lightweight 0.1 kilograms frame stays comfortable on long rides.",
            "LONG BATTERY — Up to 150 minutes keeps errands covered without recharging.",
            "CLEAR AUDIO — Built-in mic keeps voice notes crisp.",
            "WIDE VIEW — 170 degree coverage keeps sidewalks visible.",
        ],
        "description": "Compact wearable camera for commuting.",
        "aplus_content": "Module 1: 35g build. Module 2: 150 minutes runtime.",
        "metadata": {"generation_status": "live_success", "llm_response_state": "ok", "target_language": "English"},
    }

    risk = perform_risk_check(generated_copy, writing_policy={"target_language": "English"}, attribute_data={}, preprocessed_data=None)

    assert any(item["priority"] == "P2" and item["dimension"] == "Coherence" for item in risk["review_queue"])


def test_shared_numeric_in_body_does_not_trigger_duplicate_dimension():
    bullets = [
        "LONG BATTERY — Records up to 150 minutes on a single charge.",
        "4K UHD VIDEO — Captures crisp footage with 150 minutes runtime.",
        "LIGHTWEIGHT BUILD — At 35g, wear it for the full 150-minute session.",
    ]

    issues = cc.check_coherence("title", bullets, "")

    assert not any(issue.issue_type == "duplicate_dimension" for issue in issues)


def test_duplicate_header_dimension_still_detected():
    bullets = [
        "LIGHTWEIGHT DESIGN — At 35g, clips to any gear.",
        "PORTABLE BUILD — Weighs just 35g for all-day wear.",
        "4K UHD VIDEO — Crisp footage at 30fps.",
    ]

    issues = cc.check_coherence("title", bullets, "")

    assert any(issue.issue_type == "duplicate_dimension" for issue in issues)


def test_time_words_alone_do_not_trigger_battery_dimension_overlap():
    bullets = [
        "150-MINUTE RECORDING — Covers your full shift without a second take.",
        "2-HOUR COVERAGE — Keeps roadside footage rolling through the return trip.",
        "CRISP VIDEO — 1080P footage stays easy to review.",
    ]

    issues = cc.check_coherence("title", bullets, "")

    assert not any(issue.issue_type == "duplicate_dimension" for issue in issues)
