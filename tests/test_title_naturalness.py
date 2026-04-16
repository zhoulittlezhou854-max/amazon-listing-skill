import modules.copy_generation as cg


def test_title_keyword_list_detector_flags_comma_stack():
    title = "TOSBARRFT Action Camera, Body Camera, 1080P Vlogging Camera, 90-Minute Mini Camera, 180° Travel Camera"
    assert cg._title_is_keyword_dump(title) is True


def test_title_keyword_list_detector_allows_natural_phrase():
    title = "TOSBARRFT Action Camera for Daily Vlogging with 180° Lens, 1080P Video, and 90-Minute Runtime"
    assert cg._title_is_keyword_dump(title) is False


def test_deterministic_title_candidate_reads_like_natural_title():
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["body camera", "mini camera"],
        "assigned_keywords": ["travel camera", "vlogging camera"],
        "numeric_specs": ["1080P", "90-Minute Runtime"],
        "core_capability": "180° Rotatable Lens",
        "scene_priority": ["daily_vlogging", "commuting_capture"],
        "target_language": "English",
    }

    title = cg._build_deterministic_title_candidate(
        payload,
        required_keywords=["body camera", "travel camera", "vlogging camera"],
        numeric_specs=["1080P", "90-Minute Runtime"],
        max_length=200,
    )

    lowered = title.lower()
    hits = sum(keyword in lowered for keyword in ["body camera", "travel camera", "vlogging camera", "action camera"])
    assert title.startswith("TOSBARRFT")
    assert len(title) <= 200
    assert hits >= 3
    assert cg._title_is_keyword_dump(title) is False
