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


def test_deterministic_title_candidate_avoids_redundant_recording_tail():
    payload = {
        "brand_name": "TOSBARRFT",
        "primary_category": "Action Camera",
        "l1_keywords": ["action camera", "body camera"],
        "assigned_keywords": ["mini camera", "vlogging camera", "travel camera"],
        "numeric_specs": ["1080P", "150 Minutes Runtime"],
        "core_capability": "180° Rotatable Lens",
        "scene_priority": ["commuting_capture", "travel_documentation"],
        "target_language": "English",
        "exact_match_keywords": ["action camera", "body camera", "mini camera"],
        "required_keywords": ["action camera", "body camera", "mini camera"],
    }

    title = cg._build_deterministic_title_candidate(
        payload,
        required_keywords=["action camera", "body camera", "mini camera"],
        numeric_specs=["1080P", "150 Minutes Runtime"],
        max_length=200,
    )

    lowered = title.lower()
    assert len(title) <= 200
    assert "recording for travel documentation" not in lowered
    assert "built for body camera, mini camera, and vlogging camera recording" not in lowered
    assert lowered.count(" for ") <= 2
