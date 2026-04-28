from __future__ import annotations

from types import SimpleNamespace

from modules.capability_check import check_capabilities
from modules.report_generator import generate_report
from modules.risk_check import perform_risk_check
from modules.scoring import calculate_scores
from tools.preprocess import (
    derive_capability_constraints,
    parse_supplement_signals,
    standardize_attribute_data,
)


def _preprocessed(capability_constraints=None):
    capability_constraints = capability_constraints or {}
    return SimpleNamespace(
        run_config=SimpleNamespace(
            brand_name="TestBrand",
            target_country="FR",
            input_files={},
        ),
        processed_at="2026-04-10T12:00:00",
        language="French",
        target_country="FR",
        quality_score=88,
        real_vocab=None,
        data_alerts=[],
        core_selling_points=["4K recording", "long battery life", "dual screen"],
        attribute_data=SimpleNamespace(data={"video_resolution": "4K 30fps"}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        capability_constraints=capability_constraints,
        keyword_metadata=[],
        ingestion_audit={"tables": []},
        raw_human_insights="",
    )


def test_a10_rejects_bad_keyword_even_when_visible():
    generated = {
        "title": "Hidden spy camera body camera",
        "bullets": [
            "Travel camera with clip support",
            "Body camera with audio",
            "Thumb camera for walks",
        ],
        "search_terms": ["mini cam synonym"],
        "decision_trace": {
            "keyword_assignments": [
                {
                    "keyword": "hidden spy camera",
                    "tier": "L1",
                    "traffic_tier": "REJECTED",
                    "quality_status": "rejected",
                    "routing_role": "rejected",
                    "assigned_fields": ["title"],
                },
                {
                    "keyword": "body camera",
                    "tier": "L1",
                    "traffic_tier": "L1",
                    "quality_status": "qualified",
                    "routing_role": "title",
                    "assigned_fields": ["title"],
                },
                {
                    "keyword": "travel camera",
                    "tier": "L2",
                    "traffic_tier": "L2",
                    "quality_status": "qualified",
                    "routing_role": "bullet",
                    "assigned_fields": ["bullet_1"],
                },
                {
                    "keyword": "body camera with audio",
                    "tier": "L2",
                    "traffic_tier": "L2",
                    "quality_status": "qualified",
                    "routing_role": "bullet",
                    "assigned_fields": ["bullet_2"],
                },
                {
                    "keyword": "thumb camera",
                    "tier": "L3",
                    "traffic_tier": "L3",
                    "quality_status": "qualified",
                    "routing_role": "bullet",
                    "assigned_fields": ["bullet_3"],
                },
                {
                    "keyword": "mini cam synonym",
                    "tier": "L3",
                    "traffic_tier": "L3",
                    "quality_status": "qualified",
                    "routing_role": "backend",
                    "assigned_fields": ["search_terms"],
                },
            ]
        },
    }

    scores = calculate_scores(generated, {}, _preprocessed())

    assert scores["a10"]["keyword_quality_penalty"]["score"] == 0
    assert scores["listing_status"] == "NOT_READY_FOR_LISTING"


def test_a10_backend_residual_coverage_uses_routing_role():
    from modules.scoring import _score_a10

    assignments = [
        {
            "keyword": "body camera",
            "tier": "L1",
            "traffic_tier": "L1",
            "quality_status": "qualified",
            "routing_role": "title",
            "assigned_fields": ["title"],
        },
        {
            "keyword": "travel camera",
            "tier": "L2",
            "traffic_tier": "L2",
            "quality_status": "qualified",
            "routing_role": "bullet",
            "assigned_fields": ["bullet_1"],
        },
        {
            "keyword": "body camera with audio",
            "tier": "L2",
            "traffic_tier": "L2",
            "quality_status": "qualified",
            "routing_role": "bullet",
            "assigned_fields": ["bullet_2"],
        },
        {
            "keyword": "thumb camera",
            "tier": "L3",
            "traffic_tier": "L3",
            "quality_status": "qualified",
            "routing_role": "bullet",
            "assigned_fields": ["bullet_3"],
        },
        {
            "keyword": "mini cam synonym",
            "tier": "L2",
            "traffic_tier": "L2",
            "quality_status": "qualified",
            "routing_role": "backend",
            "assigned_fields": ["search_terms"],
        },
    ]

    a10 = _score_a10(assignments)

    assert a10["backend_residual_coverage"]["score"] > 0
    assert a10["l3_search_terms"]["score"] == a10["backend_residual_coverage"]["score"]


def test_standardized_constraints_feed_capability_gate():
    attr = {
        "Video Capture Resolution": "4K 30fps",
        "Connectivity Technology": "Wi-Fi, Bluetooth",
        "Features": "Dual screen, voice control, live streaming",
        "Battery Average Life": "180 minutes",
        "Has Image Stabilization": "Yes",
        "Water Resistance Level": "Not Waterproof",
    }
    signals = parse_supplement_signals("带防水壳可达30M防水；5K下不支持防抖；磁吸挂脖和车把固定")
    standardized = standardize_attribute_data(attr)
    constraints = derive_capability_constraints(attr, [], supplement_signals=signals)
    result = check_capabilities(attr, capability_constraints=constraints)

    assert standardized["connectivity"] == "Wi-Fi, Bluetooth"
    assert constraints["wifi_supported"] is True
    assert constraints["dual_screen_supported"] is True
    assert constraints["voice_control_supported"] is True
    assert constraints["live_streaming_supported"] is True
    assert constraints["waterproof_supported"] is True
    assert constraints["waterproof_requires_case"] is True
    assert constraints["waterproof_depth_m"] == 30
    assert "防水宣称" in result["allowed_with_condition"]
    assert "语音控制" in result["allowed_visible"]
    assert "直播功能" in result["allowed_visible"]
    mode_guidance = constraints["recording_mode_guidance"]
    assert mode_guidance["guidance_by_mode"]["1080P"]["stabilization_visibility"] == "primary"
    assert "5K" in mode_guidance["guidance_by_mode"]
    assert mode_guidance["guidance_by_mode"]["5K"]["stabilization_visibility"] == "avoid"


def test_dual_screen_can_be_inferred_from_model_name():
    attr = {
        "型号": "X12 双屏运动相机",
        "Video Capture Resolution": "4K 60fps",
        "Connectivity Technology": "Wi-Fi",
    }

    standardized = standardize_attribute_data(attr)
    constraints = derive_capability_constraints(attr, [], supplement_signals={})
    result = check_capabilities(attr, capability_constraints=constraints)

    assert standardized["dual_screen_supported"] == "yes"
    assert constraints["dual_screen_supported"] is True
    assert "双屏幕" in result["allowed_visible"]


def test_risk_check_blocks_backend_truth_and_language_mismatch():
    attr = {
        "Video Capture Resolution": "4K 30fps",
        "Battery Average Life": "150 minutes",
        "Connectivity Technology": "Bluetooth",
    }
    constraints = derive_capability_constraints(attr, [], supplement_signals={})
    generated_copy = {
        "title": "GoPro waterproof action camera with live streaming",
        "bullets": [
            "WATERPROOF RIDE — waterproof action camera keeps your trips ready.",
            "LIVE MODE — live streaming for every ride.",
        ],
        "description": "English only copy without French localization.",
        "faq": [],
        "aplus_content": "",
        "metadata": {"language": "French", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "French",
        "faq_only_capabilities": ["live streaming"],
        "search_term_plan": {
            "backend_only_terms": ["waterproof", "waterproof action camera"],
            "taboo_terms": ["spy camera"],
            "max_bytes": 249,
            "priority_tiers": ["l3"],
        },
        "compliance_directives": {
            "backend_only_terms": ["waterproof"],
            "taboo_terms": ["spy camera"],
            "waterproof": {"allow_visible": False},
            "stabilization": {"allow_visible": False},
        },
        "scene_priority": [],
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data=standardize_attribute_data(attr),
        capability_constraints=constraints,
    )

    truth_rules = {issue["rule"] for issue in risk["truth_consistency"]["issues"]}
    language_rules = {issue["rule"] for issue in risk["language_consistency"]["issues"]}
    assert "backend_only_visible" in truth_rules
    assert "competitor_visible" in truth_rules
    assert "unsupported_waterproof_claim" in truth_rules
    assert "faq_only_visible" in truth_rules
    assert "语言一致性" in language_rules
    assert risk["overall_passed"] is False


def test_visible_field_fallback_blocks_listing_readiness():
    generated_copy = {
        "title": "TestBrand action camera 4k",
        "bullets": ["RIDE READY CONTROL — Capture your route with steadier clips."],
        "description": "Travel-ready copy.",
        "faq": [],
        "aplus_content": "## A+",
        "metadata": {
            "language": "English",
            "target_language": "English",
            "generation_status": "live_with_fallback",
            "visible_llm_fallback_fields": ["B1", "description"],
        },
    }
    writing_policy = {
        "target_language": "English",
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
        "scene_priority": [],
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data={"Video Capture Resolution": "4K 30fps"},
        capability_constraints={"max_resolution": "4K 30fps"},
    )

    truth_rules = {issue["rule"] for issue in risk["truth_consistency"]["issues"]}
    assert "visible_field_fallback" in truth_rules
    assert risk["listing_status"]["status"] == "NOT_READY_FOR_LISTING"


def test_risk_check_does_not_flag_shot_as_hot_claim():
    attr = {
        "Video Capture Resolution": "4K 30fps",
        "Battery Average Life": "125 minutes",
        "Connectivity Technology": "Wi-Fi",
    }
    constraints = derive_capability_constraints(attr, [], supplement_signals={})
    generated_copy = {
        "title": "TestBrand caméra sport 4K",
        "bullets": [
            "SHOT PRET — Chaque shot reste net pendant vos sorties velo.",
        ],
        "description": "Cette camera aide a filmer chaque shot du trajet sans promesse absolue.",
        "faq": [],
        "aplus_content": "",
        "metadata": {"language": "French", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "French",
        "faq_only_capabilities": [],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
        "scene_priority": [],
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data=standardize_attribute_data(attr),
        capability_constraints=constraints,
    )

    patterns = {issue.get("pattern") for issue in risk["compliance"]["issues"]}
    assert "hot" not in patterns


def test_policy_scene_priority_accepts_localized_scene_terms():
    attr = {
        "Video Capture Resolution": "4K 30fps",
        "Battery Average Life": "125 minutes",
        "Connectivity Technology": "Wi-Fi",
    }
    constraints = derive_capability_constraints(attr, [], supplement_signals={})
    generated_copy = {
        "title": "TestBrand caméra d'action pour voyage et famille",
        "bullets": ["VOYAGE MALIN — Une caméra légère pour les souvenirs de famille."],
        "description": "",
        "faq": [],
        "aplus_content": "",
        "metadata": {"language": "French", "target_language": "French", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "French",
        "scene_priority": ["travel_documentation", "family_use", "cycling_recording"],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data=standardize_attribute_data(attr),
        capability_constraints=constraints,
    )

    policy_rules = {issue.get("rule") for issue in risk["policy_audit"]["issues"]}
    assert "场景优先级锁定" not in policy_rules


def test_risk_check_emits_non_blocking_production_warnings():
    generated_copy = {
        "title": "TestBrand camera with 4K, with EIS, for travel",
        "bullets": [
            "STABLE SPORT COVERAGE — With 1080P EIS for bike camera clips on every commute.",
            "LONG BATTERY PROOF — With 150 minutes ready for route review and travel days.",
            "SHARE READY VIEW — With helmet camera framing for quick social edits.",
        ],
        "description": "",
        "faq": [],
        "aplus_content": "",
        "metadata": {"language": "English", "target_language": "English", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "English",
        "scene_priority": ["cycling_recording", "travel_documentation"],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
        "copy_contracts": {
            "bullet_opening": {"forbidden_weak_openers": ["with", "avec", "mit", "con"]},
            "title_dewater": {"weak_connectors": ["with", "avec", "mit", "con"]},
            "keyword_slot_occupancy": {
                "top_conversion_slots": ["B1", "B2", "B3"],
                "bullet_keyword_slots": {
                    "B1": ["action camera 4k"],
                    "B2": ["bike camera"],
                    "B3": ["helmet camera"],
                },
            },
        },
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data={"Video Capture Resolution": "4K 30fps", "Battery Average Life": "150 minutes"},
        capability_constraints={"stabilization_supported": True, "max_resolution": "4K 30fps", "runtime_minutes": 150},
    )

    warning_rules = {issue.get("rule") for issue in risk["production_warnings"]["issues"]}
    assert "weak_bullet_opener" in warning_rules
    assert "title_weak_connector_density" in warning_rules
    assert "keyword_slot_occupancy_gap" in warning_rules
    assert risk["listing_status"]["status"] == "READY_FOR_LISTING"


def test_fluency_gate_blocks_medium_fluency_issues():
    generated_copy = {
        "title": "TestBrand thumb camera for commute",
        "bullets": [
            "BODY CAMERA WITH — Document travel using a body camera with audio for every route — Thumb Camera.",
        ],
        "description": "Simple travel recording copy.",
        "faq": [],
        "aplus_content": "word " * 520,
        "metadata": {"language": "English", "target_language": "English", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "English",
        "scene_priority": [],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data={"Video Capture Resolution": "1080P"},
        capability_constraints={"max_resolution": "1080P"},
    )

    fluency_rules = {issue.get("rule") for issue in risk["fluency"]["issues"]}
    assert "fluency_header_trailing_preposition" in fluency_rules
    assert "fluency_dash_tail_without_predicate" in fluency_rules
    assert risk["listing_status"]["status"] == "NOT_READY_FOR_LISTING"


def test_fluency_semantic_rupture_skips_when_header_body_share_domain_roots():
    generated_copy = {
        "title": "TestBrand mini camera for commute",
        "bullets": [
            "FEATHERWEIGHT TRAVEL CAMERA — This thumb camera's lightweight design keeps commute capture hands-free and easy.",
        ],
        "description": "Simple travel recording copy.",
        "faq": [],
        "aplus_content": "word " * 520,
        "metadata": {"language": "English", "target_language": "English", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "English",
        "scene_priority": [],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data={"Video Capture Resolution": "1080P"},
        capability_constraints={"max_resolution": "1080P"},
    )

    fluency_rules = {issue.get("rule") for issue in risk["fluency"]["issues"]}
    assert "fluency_header_body_rupture" not in fluency_rules


def test_aplus_repeated_roots_do_not_block_listing_status():
    generated_copy = {
        "title": "TestBrand mini camera for commute",
        "bullets": [
            "BODY CAMERA WITH AUDIO — Capture your daily commute with 150 minutes of runtime and easy operation.",
        ],
        "description": "Simple travel recording copy.",
        "faq": [],
        "aplus_content": (
            "Daily recording gives you the time to record daily moments every time you ride. " * 12
        ),
        "metadata": {"language": "English", "target_language": "English", "generation_status": "live_success"},
    }
    writing_policy = {
        "target_language": "English",
        "scene_priority": [],
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data={"Video Capture Resolution": "1080P"},
        capability_constraints={"max_resolution": "1080P"},
    )

    fluency_rules = {issue.get("rule") for issue in risk["fluency"]["issues"]}
    assert "fluency_repeated_word_root" not in fluency_rules


def test_scoring_penalizes_non_live_generation():
    preprocessed = _preprocessed()
    generated_copy = {
        "title": "",
        "bullets": [],
        "description": "",
        "search_terms": [],
        "aplus_content": "",
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "camera 4k", "tier": "L1", "assigned_fields": ["title"]},
                {"keyword": "helmet cam", "tier": "L2", "assigned_fields": ["bullet_b1", "bullet_b2", "bullet_b3"]},
                {"keyword": "petite camera sport", "tier": "L3", "assigned_fields": ["search_terms"]},
            ],
            "bullet_trace": [
                {"slot": "B1", "scene_code": "cycling_recording", "capability": "4K recording", "numeric_expectation": True, "numeric_met": True},
                {"slot": "B2", "scene_code": "travel_documentation", "capability": "long battery life", "numeric_expectation": True, "numeric_met": True},
                {"slot": "B4", "scene_code": "family_use", "capability": "boundary note", "numeric_expectation": False, "numeric_met": False},
            ],
            "search_terms_trace": {"byte_length": 180, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {
            "generation_status": "offline",
            "llm_fallback_count": 0,
            "returned_model": "unknown",
        },
    }
    writing_policy = {"scene_priority": ["cycling_recording", "travel_documentation"], "capability_scene_bindings": []}
    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert scores["production_readiness"]["generation_status"] == "offline"
    assert scores["production_readiness"]["penalty"] == 15
    assert scores["total_score"] < scores["raw_total_score"]
    assert scores["rating"] == "待优化"


def test_scoring_treats_live_generation_status_as_success():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TestBrand action camera, mini camera, travel camera, 4k, 150 minutes",
        "bullets": [
            "RIDE READY CAMERA — Capture every route with 150 minutes of runtime and 4K proof.",
            "LIGHTWEIGHT BODY CAM — Keep hands-free travel recording simple with 0.1 kilograms carry weight.",
            "WIDE VIEW RECORDING — Document each route with a 154° lens for street and travel coverage.",
        ],
        "description": "Travel-ready copy with 4K proof, 150 minutes runtime, and lightweight carry.",
        "search_terms": ["travel camera", "helmet camera"],
        "aplus_content": "Module 1: 4K at 30fps. Module 2: 150 minutes runtime. Module 3: 0.1 kilograms build.",
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [
                {"keyword": "mini camera", "tier": "L1", "assigned_fields": ["title"]},
                {"keyword": "travel camera", "tier": "L1", "assigned_fields": ["title"]},
                {"keyword": "helmet camera", "tier": "L2", "assigned_fields": ["bullet_1", "bullet_2", "bullet_3"]},
                {"keyword": "commute camera", "tier": "L3", "assigned_fields": ["search_terms"]},
            ],
            "bullet_trace": [
                {"slot": "B1", "scene_code": "cycling_recording", "capability": "long battery life", "numeric_expectation": True, "numeric_met": True},
                {"slot": "B2", "scene_code": "travel_documentation", "capability": "lightweight design", "numeric_expectation": True, "numeric_met": True},
                {"slot": "B3", "scene_code": "cycling_recording", "capability": "wide angle lens", "numeric_expectation": True, "numeric_met": True},
            ],
            "search_terms_trace": {"byte_length": 170, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {
            "generation_status": "live",
            "llm_fallback_count": 0,
            "returned_model": "deepseek-chat",
        },
    }
    writing_policy = {"scene_priority": ["cycling_recording"], "capability_scene_bindings": []}
    risk_report = {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}}
    intent_graph = {
        "capability_metadata": [
            {"capability": "long battery life", "is_supported": True},
            {"capability": "lightweight design", "is_supported": True},
            {"capability": "wide angle lens", "is_supported": True},
        ],
        "scene_metadata": [
            {"scene": "cycling_recording", "visibility": "visible"},
            {"scene": "travel_documentation", "visibility": "visible"},
        ],
    }

    scores = calculate_scores(generated_copy, writing_policy, preprocessed, intent_graph=intent_graph, risk_report=risk_report)

    assert scores["production_readiness"]["generation_status"] == "live"
    assert scores["production_readiness"]["penalty"] == 0
    assert scores["listing_status"] == "READY_FOR_LISTING"
    assert scores["max_total"] == 330


def test_scoring_adds_readability_component_from_fluency_checks():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TRAVEL CAMERA — Thumb Camera.",
        "bullets": [
            "BODY CAMERA WITH — Document travel using a body camera with audio for every route — Thumb Camera.",
            "TRAVEL CAMERA SMOOTH CONTROL — Capture commute with travel camera, travel camera, travel camera clips.",
            "THUMB CAMERA READY — Keep commute clips simple.",
            "LIGHTWEIGHT CLIP — Weighs 0.1 kilograms for travel carry.",
            "AUDIO READY RECORDING — Record clear audio on daily commutes.",
        ],
        "description": "Travel-ready copy with 1080p proof and 150 minutes runtime.",
        "search_terms": ["travel camera", "thumb camera"],
        "aplus_content": "TRAVEL CAMERA — Thumb Camera.",
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [
                {"slot": "B1", "scene_code": "travel_documentation", "capability": "body camera", "numeric_expectation": False, "numeric_met": False}
            ],
            "search_terms_trace": {"byte_length": 170, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {"generation_status": "live_success", "llm_fallback_count": 0, "returned_model": "deepseek-chat"},
    }
    writing_policy = {"scene_priority": ["travel_documentation"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert "readability" in scores
    assert scores["readability"]["score"] < 30
    assert scores["readability_score"] == scores["readability"]["subtotal"]
    assert scores["max_total"] == 330


def test_scoring_report_has_four_dimensions():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TestBrand mini camera, 1080p, 150 minutes, travel camera",
        "bullets": [
            "RIDE READY CAMERA — Capture daily commute clips with 1080p clarity and 150 minutes of runtime.",
            "LIGHTWEIGHT BODY CAM — Keep hands-free travel recording simple with 0.1 kilograms carry weight.",
            "WIDE VIEW RECORDING — Document each route with a 154° lens for street and travel coverage.",
            "EASY CLIP MOUNT — Wear the mini camera on shirts, straps, and packs for quick travel capture.",
            "CLEAR AUDIO SUPPORT — Record body camera footage with simple controls for daily journaling.",
        ],
        "description": "Travel-ready body camera with 1080p proof, 150 minutes runtime, and lightweight carry.",
        "search_terms": ["travel camera", "mini camera", "body camera"],
        "aplus_content": "Module 1: 1080p at 30fps. Module 2: 150 minutes runtime. Module 3: 0.1 kilograms build.",
        "audit_trail": [],
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [], "search_terms_trace": {"byte_length": 180, "max_bytes": 249}},
        "metadata": {"generation_status": "live_success", "llm_fallback_count": 0, "returned_model": "deepseek-chat"},
    }
    writing_policy = {"scene_priority": ["travel_documentation"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert set(scores["dimensions"].keys()) == {"traffic", "content", "conversion", "readability"}
    assert scores["dimensions"]["traffic"]["label"] == "A10"
    assert scores["dimensions"]["readability"]["label"] == "Fluency"


def test_readability_dimension_blocks_listing_on_high_fluency_issue():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TRAVEL CAMERA — Thumb Camera.",
        "bullets": [
            "LIGHTWEIGHT DESIGN — It weighs only 35g perfect for daily commute.",
            "RIDE READY CAMERA — Capture daily commute clips with 1080p clarity and 150 minutes of runtime.",
        ],
        "description": "Travel-ready body camera with 1080p proof and 150 minutes runtime.",
        "search_terms": ["travel camera"],
        "aplus_content": "TRAVEL CAMERA — Thumb Camera.",
        "audit_trail": [],
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [], "search_terms_trace": {"byte_length": 180, "max_bytes": 249}},
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"scene_priority": ["travel_documentation"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert scores["dimensions"]["readability"]["status"] == "fail"
    assert scores["listing_status"] == "NOT_READY_FOR_LISTING"
    readability_block = next(item for item in scores["blocking_dimensions"] if item["dimension"] == "readability")
    assert "bullet_b1" in readability_block["blocking_fields"]


def test_action_required_message_names_blocking_fields():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TRAVEL CAMERA — Thumb Camera.",
        "bullets": [
            "LIGHTWEIGHT DESIGN — It weighs only 35g perfect for daily commute.",
            "TRAVEL CAMERA SMOOTH CONTROL — Capture commute with travel camera, travel camera, travel camera clips.",
        ],
        "description": "Travel-ready copy with 1080p proof and 150 minutes runtime.",
        "search_terms": ["travel camera"],
        "aplus_content": "TRAVEL CAMERA — Thumb Camera.",
        "audit_trail": [],
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [], "search_terms_trace": {"byte_length": 170, "max_bytes": 249}},
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"scene_priority": ["travel_documentation"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert "问题字段" in scores["action_required"]
    assert "bullet_b1" in scores["action_required"]


def test_review_queue_sorted_by_priority():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TRAVEL CAMERA — Thumb Camera.",
        "bullets": [
            "BODY CAMERA WITH — Record travel using body camera with audio, easy operation, 150 minutes so every clip feels ready to share.",
            "RIDE READY CAMERA — Capture commute with 1080p proof and 150 minutes runtime.",
        ],
        "description": "Travel-ready copy with 1080p proof and 150 minutes runtime.",
        "search_terms": ["travel camera"],
        "aplus_content": "TRAVEL CAMERA — Thumb Camera.",
        "audit_trail": [],
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [], "search_terms_trace": {"byte_length": 170, "max_bytes": 249}},
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"scene_priority": ["travel_documentation"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    priorities = [item["priority"] for item in scores["review_queue"]]
    assert priorities == sorted(priorities)


def test_total_score_still_present_but_deprecated():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TestBrand mini camera, 1080p, 150 minutes, travel camera",
        "bullets": ["RIDE READY CAMERA — Capture daily commute clips with 1080p clarity and 150 minutes of runtime."],
        "description": "Travel-ready body camera with 1080p proof and 150 minutes runtime.",
        "search_terms": ["travel camera"],
        "aplus_content": "1080p and 150 minutes support.",
        "audit_trail": [],
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [], "search_terms_trace": {"byte_length": 170, "max_bytes": 249}},
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"scene_priority": ["travel_documentation"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert "total_score" in scores
    assert scores["_deprecated"]


def test_scoring_counts_compliance_mitigation_actions():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TestBrand action camera",
        "bullets": ["RIDE READY — Capture every route with reliable 150 minutes runtime."],
        "description": "Travel-ready copy with specific proof.",
        "search_terms": ["travel camera"],
        "aplus_content": "word " * 520,
        "audit_trail": [
            {"field": "search_terms", "action": "backend_only_deferred", "term": "waterproof"},
            {"field": "search_terms", "action": "brand_skip", "term": "snaproll camera"},
            {"field": "description", "action": "downgrade", "reason": "absolute_claim_rewritten"},
        ],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [],
            "search_terms_trace": {"byte_length": 180, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {"generation_status": "live_success", "llm_fallback_count": 0, "returned_model": "deepseek-chat"},
    }
    writing_policy = {"scene_priority": ["cycling_recording"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert scores["cosmo"]["compliance_actions"]["score"] > 0
    assert "backend_only" in scores["cosmo"]["compliance_actions"]["note"]


def test_scoring_uses_visible_spec_dimensions_for_rufus():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 150})
    generated_copy = {
        "title": "TestBrand mini camera, 1080p, 150 minutes",
        "bullets": [
            "LIGHTWEIGHT CLIP — Weighs 0.1 kilograms for travel carry.",
            "WIDE VIEW READY — Wide angle lens keeps commute capture framed.",
        ],
        "description": "1080p recording with 150 minutes runtime for daily travel.",
        "search_terms": ["travel camera"],
        "aplus_content": "## Core Technologies\nWide angle lens with 1080p capture and 0.1 kilograms body.",
        "audit_trail": [],
        "evidence_bundle": {
            "attribute_evidence": {
                "video capture resolution": "1080p",
                "item weight": "0.1 Kilograms",
                "lens type": "Wide Angle",
                "battery average life": "150 minutes",
            }
        },
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [
                {"slot": "B1", "numeric_expectation": True, "numeric_met": True},
            ],
            "search_terms_trace": {"byte_length": 180, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {"generation_status": "live_success", "llm_fallback_count": 0, "returned_model": "deepseek-chat"},
    }
    writing_policy = {"scene_priority": ["cycling_recording"], "capability_scene_bindings": []}

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert scores["rufus"]["spec_signal_coverage"]["score"] == 40
    assert "visible_specs=4/4" in scores["rufus"]["spec_signal_coverage"]["note"]


def test_scoring_uses_capability_bundle_and_scene_mapping_for_cosmo():
    preprocessed = _preprocessed(
        capability_constraints={"runtime_minutes": 150, "waterproof_depth_m": 30, "accessory_catalog_count": 3}
    )
    generated_copy = {
        "title": "TestBrand action camera 4k",
        "bullets": ["B1", "B2", "B3", "B4"],
        "description": "",
        "search_terms": ["travel camera", "underwater camera", "helmet camera"],
        "aplus_content": "word " * 520,
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [
                {
                    "slot": "B1",
                    "scene_code": "underwater_exploration",
                    "scene_mapping": ["underwater_exploration", "travel_documentation", "family_use"],
                    "capability": "4K 60fps video capture",
                    "capability_bundle": ["4K 60fps video capture", "dual screen framing", "WiFi connectivity"],
                },
                {
                    "slot": "B2",
                    "scene_code": "cycling_recording",
                    "scene_mapping": ["cycling_recording", "sports_training"],
                    "capability": "portable action camera for commuting",
                    "capability_bundle": ["portable action camera for commuting", "cycling recording"],
                },
            ],
            "search_terms_trace": {"byte_length": 165, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {"generation_status": "live_success", "llm_fallback_count": 0, "returned_model": "gpt-5.4"},
    }
    writing_policy = {
        "scene_priority": ["underwater_exploration", "cycling_recording", "travel_documentation", "family_use"],
        "capability_scene_bindings": [],
    }
    intent_graph = {
        "scene_metadata": [
            {"scene": "underwater_exploration", "visibility": "visible"},
            {"scene": "cycling_recording", "visibility": "visible"},
            {"scene": "travel_documentation", "visibility": "visible"},
            {"scene": "family_use", "visibility": "visible"},
            {"scene": "sports_training", "visibility": "visible"},
        ],
        "capability_metadata": [
            {"capability": "dual screen", "is_supported": True},
            {"capability": "4k recording", "is_supported": True},
            {"capability": "waterproof", "is_supported": True},
            {"capability": "wifi connectivity", "is_supported": True},
            {"capability": "portable action camera for commuting", "is_supported": True},
            {"capability": "cycling", "is_supported": True},
        ],
    }

    scores = calculate_scores(generated_copy, writing_policy, preprocessed, intent_graph=intent_graph)

    assert scores["cosmo"]["capability_coverage"]["score"] >= 30
    assert scores["cosmo"]["scene_distribution"]["score"] >= 32


def test_scoring_cosmo_reads_visible_text_when_trace_is_sparse():
    preprocessed = _preprocessed(
        capability_constraints={"runtime_minutes": 150, "waterproof_depth_m": 30, "accessory_catalog_count": 3}
    )
    generated_copy = {
        "title": "TestBrand action camera 4k for underwater exploration and cycling recording",
        "bullets": [
            "B1 — WiFi and dual screen support help every travel vlog feel easier.",
            "B2 — Built for outdoor sports, family trips, and daily commute capture.",
        ],
        "description": "Portable action camera for commuting with 4K recording, travel and vlog capture, and sports-ready use.",
        "search_terms": ["travel camera"],
        "aplus_content": "word " * 520,
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [
                {"slot": "B1", "scene_code": "", "scene_mapping": [], "capability": "", "capability_bundle": [], "capability_mapping": []},
            ],
            "search_terms_trace": {"byte_length": 120, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {"generation_status": "live_success", "llm_fallback_count": 0, "returned_model": "gpt-5.4"},
    }
    writing_policy = {
        "scene_priority": ["underwater_exploration", "cycling_recording", "travel_documentation", "family_use"],
        "capability_scene_bindings": [],
    }
    intent_graph = {
        "scene_metadata": [
            {"scene": "outdoor_sports", "visibility": "visible"},
            {"scene": "cycling_recording", "visibility": "visible"},
            {"scene": "underwater_exploration", "visibility": "visible"},
            {"scene": "travel_documentation", "visibility": "visible"},
            {"scene": "family_use", "visibility": "visible"},
            {"scene": "daily_lifelogging", "visibility": "visible"},
            {"scene": "vlog_content_creation", "visibility": "visible"},
        ],
        "capability_metadata": [
            {"capability": "wifi connectivity", "is_supported": True},
            {"capability": "dual screen", "is_supported": True},
            {"capability": "sports compatible", "is_supported": True},
            {"capability": "4k recording", "is_supported": True},
            {"capability": "portable action camera for commuting", "is_supported": True},
            {"capability": "travel and vlog capture", "is_supported": True},
        ],
    }

    scores = calculate_scores(generated_copy, writing_policy, preprocessed, intent_graph=intent_graph)

    assert scores["cosmo"]["capability_coverage"]["score"] >= 33
    assert scores["cosmo"]["scene_distribution"]["score"] >= 34


def test_report_surfaces_truth_language_and_keyword_routing():
    constraints = {
        "runtime_minutes": 180,
        "waterproof_depth_m": 30,
        "accessory_catalog_count": 2,
    }
    preprocessed = _preprocessed(capability_constraints=constraints)
    preprocessed.supplement_signals = {
        "bundle_variant": {
            "included_accessories": ["防水壳", "自行车支架"],
            "card_capacity_gb": 64,
            "source": "supplement",
        }
    }
    preprocessed.asin_entity_profile = {
        "bundle_variant": {
            "included_accessories": ["防水壳", "自行车支架"],
            "card_capacity_gb": 64,
        }
    }
    preprocessed.attribute_data = SimpleNamespace(data={"video_resolution": "4K 30fps"})
    generated_copy = {
        "title": "Caméra d'action 4K TestBrand",
        "bullets": ["AUTONOMIE LONGUE — 180 minutes pour vos sorties."],
        "description": "Description FR.",
        "faq": [],
        "search_terms": ["camera sport 4k"],
        "aplus_content": "mot " * 520,
        "evidence_bundle": {
            "claim_support_matrix": [{"claim": "30 m waterproof with case", "support_status": "supported"}],
            "rufus_readiness": {"score": 1.0, "supported_claim_count": 1, "total_claim_count": 1},
        },
        "compute_tier_map": {
            "title": {"tier_used": "native", "rerun_recommended": False},
            "bullet_1": {"tier_used": "rule_based", "rerun_recommended": True},
        },
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [{"slot": "B4", "scene_code": "travel_documentation", "capability": "boundary note", "numeric_expectation": False, "numeric_met": False}],
            "search_terms_trace": {"byte_length": 180, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {
            "generation_status": "live_with_fallback",
            "llm_fallback_count": 1,
            "llm_provider": "openai-compatible",
            "returned_model": "gpt-5.4",
            "configured_model": "gpt-5.4",
            "llm_mode": "live",
        },
    }
    writing_policy = {
        "scene_priority": ["travel_documentation", "family_use"],
        "capability_scene_bindings": [],
        "search_term_plan": {"priority_tiers": ["l3"], "max_bytes": 249, "backend_only_terms": ["waterproof"]},
        "keyword_routing": {
            "title_traffic_keywords": ["camera sport 4k"],
            "bullet_conversion_keywords": ["caméra d'action"],
            "backend_longtail_keywords": ["camera embarquée voyage"],
        },
        "compliance_directives": {
            "waterproof": {"allow_visible": True, "requires_case": True, "depth_m": 30, "note": "Use housing."},
            "stabilization": {"allow_visible": True, "modes": ["1080P"], "note": "EIS only."},
            "runtime_minutes": 180,
        },
        "market_pack": {
            "locale": "FR",
            "lexical_preferences": ["camera sport"],
            "faq_templates": ["cold_weather"],
            "compliance_reminders": ["avoid unsupported battery safety guarantees"],
            "after_sales_promises": ["Support client FR via seller messaging within 24h"],
            "support_sop": ["Confirmer la compatibilite des accessoires avant remplacement"],
        },
    }
    risk_report = {
        "overall_passed": False,
        "compliance": {"passed": 1, "total": 1, "issues": []},
        "policy_audit": {"passed": 1, "total": 1, "issues": []},
        "hallucination_risk": {"passed": 1, "total": 1, "issues": []},
        "truth_consistency": {"passed": 0, "total": 1, "issues": [{"severity": "high", "description": "backend-only term visible"}]},
        "language_consistency": {"passed": 0, "total": 1, "issues": [{"severity": "medium", "description": "still partly English"}]},
    }
    scoring_results = calculate_scores(generated_copy, writing_policy, preprocessed)

    report = generate_report(
        preprocessed_data=preprocessed,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report=risk_report,
        scoring_results=scoring_results,
        language="French",
        intent_graph=None,
    )

    assert "## Part 1：运营部分" in report
    assert "## Part 2：系统部分" in report
    assert "## Part 3：诊断与优化部分" in report
    assert "### 真值一致性" in report
    assert "### 语言一致性" in report
    assert "### Keyword Routing" in report
    assert "### Production Readiness" in report
    assert "### Evidence Alignment" in report
    assert "30 m waterproof with case: supported" in report
    assert "### Operator Summary" in report
    assert "Unsupported claims: 0" in report
    assert "### Market Pack" in report
    assert "Locale: FR" in report
    assert "### Bundle Variant" in report
    assert "Included Accessories: 防水壳, 自行车支架" in report
    assert "Card Capacity: 64 GB" in report
    assert "### EU After-Sales & SOP" in report
    assert "Support client FR via seller messaging within 24h" in report
    assert "### Pre-Launch Checklist" in report
    assert "### 30-Day Iteration Panel" in report
    assert "### Compute Tier Map" in report
    assert "[Bullet 1: Rule-Based]" in report
    assert "Intent weight updates: 0" in report


def test_scoring_surfaces_ai_os_readiness_from_prd_sidecars():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 180})
    generated_copy = {
        "title": "Action Camera TestBrand",
        "bullets": ["4K ride capture", "180 minute battery"],
        "description": "Built for travel and commuting.",
        "search_terms": ["helmet camera"],
        "aplus_content": "word " * 520,
        "evidence_bundle": {
            "claim_support_matrix": [
                {"claim": "180 minute runtime", "support_status": "supported"},
                {"claim": "stormproof blizzard use", "support_status": "unsupported"},
            ],
            "rufus_readiness": {"score": 0.5, "supported_claim_count": 1, "total_claim_count": 2},
        },
        "compute_tier_map": {
            "title": {"tier_used": "native", "rerun_recommended": False, "rerun_priority": "normal"},
            "bullet_1": {"tier_used": "rule_based", "rerun_recommended": True, "rerun_priority": "high"},
            "description": {"tier_used": "native", "rerun_recommended": False, "rerun_priority": "normal"},
        },
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [],
            "search_terms_trace": {"byte_length": 120, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {
            "generation_status": "live_success",
            "llm_provider": "openai-compatible",
            "returned_model": "gpt-5.4",
            "configured_model": "gpt-5.4",
            "llm_mode": "live",
            "unsupported_claim_count": 1,
            "fallback_density": 1,
        },
    }
    writing_policy = {
        "scene_priority": ["travel_documentation"],
        "market_pack": {
            "locale": "FR",
            "lexical_preferences": ["camera sport"],
            "faq_templates": ["battery"],
            "compliance_reminders": ["avoid unsupported waterproof promises"],
            "after_sales_promises": ["Support client FR via seller messaging within 24h"],
            "support_sop": ["Confirmer la compatibilite des accessoires avant remplacement"],
            "regulatory_watchouts": ["Clarify waterproof limits when the case is required"],
        },
        "intent_weight_snapshot": {
            "weights": [
                {
                    "keyword": "helmet camera",
                    "scene": "cycling_recording",
                    "capability": "hands free",
                    "traffic_weight": 0.12,
                    "conversion_weight": 0.08,
                    "scene_weight": 0.1,
                    "capability_weight": 0.09,
                }
            ]
        },
    }

    scores = calculate_scores(generated_copy, writing_policy, preprocessed)

    assert "ai_os_readiness" in scores
    assert scores["ai_os_readiness"]["evidence_alignment"]["score"] > 0
    assert scores["ai_os_readiness"]["market_localization"]["score"] == 25
    assert scores["ai_os_readiness"]["compute_observability"]["score"] > 0
    assert scores["ai_os_readiness"]["intent_learning"]["score"] > 0
    assert scores["ai_os_score"] == scores["ai_os_readiness"]["subtotal"]


def test_report_surfaces_ai_os_readiness_block():
    preprocessed = _preprocessed(capability_constraints={"runtime_minutes": 180})
    generated_copy = {
        "title": "Action Camera TestBrand",
        "bullets": ["4K ride capture"],
        "description": "Travel-ready camera.",
        "faq": [],
        "search_terms": ["helmet camera"],
        "aplus_content": "word " * 520,
        "evidence_bundle": {
            "claim_support_matrix": [{"claim": "180 minute runtime", "support_status": "supported"}],
            "rufus_readiness": {"score": 1.0, "supported_claim_count": 1, "total_claim_count": 1},
        },
        "compute_tier_map": {
            "title": {"tier_used": "native", "rerun_recommended": False, "rerun_priority": "normal"},
            "bullet_1": {"tier_used": "rule_based", "rerun_recommended": True, "rerun_priority": "high"},
        },
        "audit_trail": [],
        "decision_trace": {
            "keyword_assignments": [],
            "bullet_trace": [],
            "search_terms_trace": {"byte_length": 180, "max_bytes": 249, "backend_only_used": 0},
        },
        "metadata": {
            "generation_status": "live_success",
            "llm_provider": "openai-compatible",
            "returned_model": "gpt-5.4",
            "configured_model": "gpt-5.4",
            "llm_mode": "live",
        },
    }
    writing_policy = {
        "scene_priority": ["travel_documentation"],
        "market_pack": {
            "locale": "FR",
            "lexical_preferences": ["camera sport"],
            "faq_templates": ["battery"],
            "compliance_reminders": ["avoid unsupported waterproof promises"],
        },
        "intent_weight_snapshot": {
            "weights": [
                {
                    "keyword": "helmet camera",
                    "scene": "cycling_recording",
                    "capability": "hands free",
                    "traffic_weight": 0.12,
                    "conversion_weight": 0.08,
                    "scene_weight": 0.1,
                    "capability_weight": 0.09,
                }
            ]
        },
    }
    risk_report = {
        "overall_passed": True,
        "compliance": {"passed": 1, "total": 1, "issues": []},
        "policy_audit": {"passed": 1, "total": 1, "issues": []},
        "hallucination_risk": {"passed": 1, "total": 1, "issues": []},
        "truth_consistency": {"passed": 1, "total": 1, "issues": []},
        "language_consistency": {"passed": 1, "total": 1, "issues": []},
    }

    scoring_results = calculate_scores(generated_copy, writing_policy, preprocessed)
    report = generate_report(
        preprocessed_data=preprocessed,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report=risk_report,
        scoring_results=scoring_results,
        language="French",
        intent_graph=None,
    )

    assert "### AI OS Readiness" in report
    assert "Readiness grade" in report


def test_non_eu_report_uses_generic_after_sales_label():
    preprocessed = _preprocessed(capability_constraints={})
    preprocessed.target_country = "US"
    preprocessed.run_config = SimpleNamespace(brand_name="TestBrand", target_country="US", input_files={})
    generated_copy = {
        "title": "Body Camera TestBrand",
        "bullets": ["Clip-on recording"],
        "description": "Portable POV camera.",
        "faq": [],
        "search_terms": ["body camera"],
        "aplus_content": "word " * 520,
        "evidence_bundle": {"claim_support_matrix": [], "rufus_readiness": {"score": 0.0}},
        "compute_tier_map": {},
        "audit_trail": [],
        "decision_trace": {"keyword_assignments": [], "bullet_trace": [], "search_terms_trace": {"byte_length": 120, "max_bytes": 249}},
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"market_pack": {"locale": "US"}}
    scoring_results = calculate_scores(generated_copy, writing_policy, preprocessed)

    report = generate_report(
        preprocessed_data=preprocessed,
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        risk_report={},
        scoring_results=scoring_results,
        language="English",
        intent_graph=None,
    )

    assert "### After-Sales & SOP" in report
    assert "### EU After-Sales & SOP" not in report


def test_too_many_bullet_fallbacks_force_not_ready_listing_status():
    generated_copy = {
        "title": "TestBrand action camera 4k",
        "bullets": [
            "B1 copy",
            "B2 copy",
            "B3 copy",
            "B4 copy",
            "B5 copy",
        ],
        "description": "Travel-ready copy.",
        "faq": [],
        "aplus_content": "## A+",
        "metadata": {
            "language": "English",
            "target_language": "English",
            "generation_status": "live_with_fallback",
            "visible_llm_fallback_fields": ["B1", "B2", "B3"],
        },
    }
    writing_policy = {
        "target_language": "English",
        "search_term_plan": {"backend_only_terms": [], "taboo_terms": [], "max_bytes": 249, "priority_tiers": ["l3"]},
        "compliance_directives": {"waterproof": {"allow_visible": True}, "stabilization": {"allow_visible": True}},
        "scene_priority": [],
    }

    risk = perform_risk_check(
        generated_copy=generated_copy,
        writing_policy=writing_policy,
        attribute_data={"Video Capture Resolution": "4K 30fps"},
        capability_constraints={"max_resolution": "4K 30fps"},
    )

    assert risk["listing_status"]["status"] == "NOT_READY_FOR_LISTING"
    assert "too_many_bullet_fallbacks" in (risk["listing_status"]["blocking_reasons"] or [])
