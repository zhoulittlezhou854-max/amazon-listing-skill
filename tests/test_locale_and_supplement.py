from types import SimpleNamespace

from modules.copy_generation import (
    PreprocessedData,
    generate_search_terms,
    _localize_text_block,
)
from modules.keyword_utils import (
    find_blocklisted_terms,
    infer_category_type,
    is_blocklisted_brand,
    keyword_relevance_issue,
)
from modules.writing_policy import extract_scenes_from_keywords
from tools.preprocess import derive_capability_constraints, parse_supplement_signals


def test_supplement_signals_override_runtime_and_depth():
    text = "1. 带防水壳可达30M防水，2. 本机150MIN续航，电池仓210min，一共360min"
    signals = parse_supplement_signals(text, source_path="/tmp/supplement.txt")
    assert signals["runtime_total_minutes"] == 360
    assert signals["waterproof_depth_m"] == 30
    attr = {"Water Resistance Level": "Not Water Resistant", "Battery Average Life": "90 minutes"}
    constraints = derive_capability_constraints(attr, [], supplement_signals=signals)
    assert constraints["runtime_minutes"] == 360
    assert constraints["runtime_source"] == "supplement"
    assert constraints["waterproof_supported"] is True
    assert constraints["waterproof_requires_case"] is True
    assert constraints["waterproof_depth_m"] == 30


def test_supplement_signals_parse_bundle_variant_sections():
    text = """
【产品卖点】
- 4K录制
- 续航约150分钟

【本链接包含配件】
- 防水壳
- 自行车支架
- 头盔支架

【存储卡】
- 64GB

【备注】
- 当前链接为骑行+防水组合版本
"""
    signals = parse_supplement_signals(text, source_path="/tmp/supplement.txt")

    assert [item["name"] for item in signals["accessories"]] == ["防水壳", "自行车支架", "头盔支架"]
    assert signals["bundle_variant"]["included_accessories"] == ["防水壳", "自行车支架", "头盔支架"]
    assert signals["bundle_variant"]["card_capacity_gb"] == 64
    assert signals["bundle_variant"]["source"] == "supplement"


def test_search_terms_enforce_locale_filter():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["4k recording"],
        accessory_descriptions=[],
        quality_score=80,
        language="French",
        processed_at="2026-04-06T00:00:00",
        target_country="FR",
        capability_constraints={},
        keyword_metadata=[],
    )
    tiered_keywords = {
        "l1": ["caméra d'action 4k", "action camera 4k"],
        "l2": [],
        "l3": ["caméra corporelle", "body camera"],
        "_metadata": {
            "caméra d'action 4k": {"detected_locale": "fr", "source_country": "FR"},
            "action camera 4k": {"detected_locale": "en", "source_country": "US"},
            "caméra corporelle": {"detected_locale": "fr", "source_country": "FR"},
            "body camera": {"detected_locale": "en"},
        },
        "_preferred_locale": "fr",
    }
    writing_policy = {
        "search_term_plan": {"priority_tiers": ["l3"], "max_bytes": 249, "backend_only_terms": []},
        "scene_priority": [],
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {
            "waterproof": {"allow_visible": False},
            "stabilization": {"allow_visible": True},
        },
        "preferred_locale": "fr",
    }
    terms, trace = generate_search_terms(
        preprocessed,
        writing_policy,
        title="Caméra d'action 4K",
        bullets=[""],
        description="",
        language="French",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
    )
    assert "caméra corporelle" in terms
    assert all("action camera" not in term for term in terms)
    assert all("body" not in term for term in terms)
    assert trace["byte_length"] <= 249


def test_locale_filter_accepts_country_marked_keyword():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["4k recording"],
        accessory_descriptions=[],
        quality_score=80,
        language="German",
        processed_at="2026-04-06T00:00:00",
        target_country="DE",
        capability_constraints={},
        keyword_metadata=[],
    )
    tiered_keywords = {
        "l1": [],
        "l2": [],
        "l3": ["helmkamera"],
        "_metadata": {
            "helmkamera": {"detected_locale": "en", "source_country": "DE"},
        },
        "_preferred_locale": "de",
    }
    writing_policy = {
        "search_term_plan": {"priority_tiers": ["l3"], "max_bytes": 249, "backend_only_terms": []},
        "scene_priority": [],
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {},
        "preferred_locale": "de",
    }
    terms, trace = generate_search_terms(
        preprocessed,
        writing_policy,
        title="Actionkamera 4K",
        bullets=[""],
        description="",
        language="German",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
    )
    assert "helmkamera" in terms
    assert trace["byte_length"] > 0


def test_search_terms_skip_brand_keywords():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["4k recording"],
        accessory_descriptions=[],
        quality_score=80,
        language="German",
        processed_at="2026-04-06T00:00:00",
        target_country="DE",
        capability_constraints={},
        keyword_metadata=[],
    )
    tiered_keywords = {
        "l2": [],
        "l3": ["GoPro wasserdicht kamera"],
        "_metadata": {
            "gopro wasserdicht kamera": {"source_country": "DE"},
        },
        "_preferred_locale": "de",
    }
    writing_policy = {
        "search_term_plan": {"priority_tiers": ["l3"], "max_bytes": 249, "backend_only_terms": []},
        "scene_priority": [],
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {},
        "preferred_locale": "de",
    }
    terms, _ = generate_search_terms(
        preprocessed,
        writing_policy,
        title="Actionkamera",
        bullets=[""],
        description="",
        language="German",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
    )
    assert all("gopro" not in term.lower() for term in terms)


def test_generic_locale_words_are_not_treated_as_brands():
    assert is_blocklisted_brand("GoPro hero") in {"gopro", "go pro", "hero"}
    assert is_blocklisted_brand("casque velo") is None
    assert is_blocklisted_brand("starter pack") is None
    assert "casque" not in find_blocklisted_terms("support casque pour velo")
    assert "pack" not in find_blocklisted_terms("pack accessoires velo")


def test_action_camera_relevance_filter_blocks_wrong_subcategories():
    assert keyword_relevance_issue("mini camera espion sans fil", "action_camera")
    assert keyword_relevance_issue("camera pieton", "action_camera")
    assert keyword_relevance_issue("ace pro 2", "action_camera")
    assert keyword_relevance_issue("caméra sport 4k", "action_camera") is None


def test_wearable_body_camera_relevance_filter_blocks_glasses_noise():
    assert keyword_relevance_issue("camera glasses 4k", "wearable_body_camera")
    assert keyword_relevance_issue("video glasses mini", "wearable_body_camera")
    assert keyword_relevance_issue("thumb camera", "wearable_body_camera") is None
    assert keyword_relevance_issue("wearable body camera", "wearable_body_camera") is None


def test_infer_category_type_detects_wearable_body_camera():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={"Features": "WiFi 2.4GHz, magnetic back clip"}),
        keyword_data=SimpleNamespace(keywords=[{"keyword": "body camera"}, {"keyword": "thumb camera"}]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["wearable camera", "long battery life"],
        accessory_descriptions=[],
        quality_score=80,
        language="English",
        processed_at="2026-04-06T00:00:00",
        target_country="US",
        capability_constraints={},
        keyword_metadata=[],
    )
    assert infer_category_type(preprocessed) == "wearable_body_camera"


def test_extract_scenes_from_keywords_normalizes_bodycam_and_vlog_terms():
    keyword_data = SimpleNamespace(
        keywords=[
            {"keyword": "body camera"},
            {"keyword": "thumb camera"},
            {"keyword": "travel camera"},
            {"keyword": "vlog camera"},
        ]
    )
    scenes = extract_scenes_from_keywords(keyword_data, "English")
    assert "commuting_capture" in scenes
    assert "travel_documentation" in scenes
    assert "vlog_content_creation" in scenes
    assert all("_camera" not in scene for scene in scenes)


def test_search_terms_skip_constraint_conflict_keywords():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["4k recording"],
        accessory_descriptions=[],
        quality_score=80,
        language="French",
        processed_at="2026-04-06T00:00:00",
        target_country="FR",
        capability_constraints={"wifi_supported": True},
        keyword_metadata=[],
    )
    tiered_keywords = {
        "l1": [],
        "l2": [],
        "l3": ["caméra sans wifi", "caméra sport"],
        "_metadata": {
            "caméra sans wifi": {"detected_locale": "fr", "source_country": "FR"},
            "caméra sport": {"detected_locale": "fr", "source_country": "FR"},
        },
        "_preferred_locale": "fr",
    }
    writing_policy = {
        "search_term_plan": {"priority_tiers": ["l3"], "max_bytes": 249, "backend_only_terms": []},
        "scene_priority": [],
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {},
        "preferred_locale": "fr",
    }
    terms, _ = generate_search_terms(
        preprocessed,
        writing_policy,
        title="Caméra sport 4K",
        bullets=[""],
        description="",
        language="French",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
    )
    assert "caméra sans wifi" not in terms
    assert "caméra sport" in terms


def test_search_terms_do_not_inject_backend_only_terms_into_final_amazon_copy():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["long battery life"],
        accessory_descriptions=[],
        quality_score=80,
        language="English",
        processed_at="2026-04-06T00:00:00",
        target_country="US",
        capability_constraints={},
        keyword_metadata=[],
    )
    tiered_keywords = {
        "l1": [],
        "l2": [],
        "l3": ["thumb camera"],
        "_metadata": {"thumb camera": {"detected_locale": "en", "source_country": "US"}},
        "_preferred_locale": "en",
    }
    writing_policy = {
        "search_term_plan": {
            "priority_tiers": ["l3"],
            "max_bytes": 249,
            "backend_only_terms": ["waterproof", "stabilization"],
        },
        "scene_priority": ["commuting_capture"],
        "keyword_slots": {"search_terms": {"keywords": []}},
        "compliance_directives": {
            "backend_only_terms": ["waterproof", "stabilization"],
        },
        "preferred_locale": "en",
    }
    terms, _ = generate_search_terms(
        preprocessed,
        writing_policy,
        title="TestBrand body camera",
        bullets=[""],
        description="",
        language="English",
        tiered_keywords=tiered_keywords,
        keyword_slots=writing_policy["keyword_slots"],
    )
    assert "thumb camera" in terms
    assert "waterproof" not in terms
    assert "stabilization" not in terms


def test_rule_based_localization_preserves_numbers_and_logs():
    audit_log = []
    text = "magnetic clip locks onto gear for cycling recording 30 m runtime."
    localized = _localize_text_block(text, "French", "fr", ["TOSBARRFT"], audit_log, "title")
    assert "30 m" in localized
    assert "magnétique" in localized.lower()
    assert any(entry["action"] == "localized" for entry in audit_log)
