from types import SimpleNamespace

from modules.entity_profile import build_entity_profile


def _sample_preprocessed_data():
    return SimpleNamespace(
        run_config=SimpleNamespace(product_code="T70", brand_name="TOSBARRFT"),
        target_country="DE",
        language="German",
        capability_constraints={
            "runtime_minutes": 150,
            "waterproof_depth_m": 30,
            "waterproof_requires_case": True,
        },
        canonical_core_selling_points=["4k recording", "long battery life", "waterproof"],
        core_selling_points=["4K", "150min", "Waterproof"],
        canonical_accessory_descriptions=[
            {"name": "magnetic back clip", "experience": "hands-free commuting capture"},
            {"name": "waterproof case", "experience": "dive-ready underwater use"},
        ],
        accessory_descriptions=[
            {"name": "magnetic back clip"},
            {"name": "waterproof case"},
        ],
        attribute_data=SimpleNamespace(
            data={
                "brand": "TOSBARRFT",
                "model": "T70",
                "category": "action_camera",
            }
        ),
        review_data=SimpleNamespace(
            insights=[
                {"field_name": "battery", "positive": "battery lasts long"},
                {"field_name": "waterproof", "negative": "need the case for diving"},
            ]
        ),
        feedback_context={},
    )


def test_entity_profile_contains_core_sections():
    profile = build_entity_profile(_sample_preprocessed_data())

    assert set(profile) >= {
        "product_code",
        "brand_name",
        "core_specs",
        "capability_registry",
        "accessory_registry",
        "claim_registry",
        "compliance_constraints",
        "evidence_refs",
    }


def test_entity_profile_keeps_basic_product_facts():
    profile = build_entity_profile(_sample_preprocessed_data())

    assert profile["product_code"] == "T70"
    assert profile["brand_name"] == "TOSBARRFT"
    assert profile["core_specs"]["runtime_minutes"] == 150
    assert profile["core_specs"]["waterproof_depth_m"] == 30


def test_entity_profile_builds_claims_and_accessories():
    profile = build_entity_profile(_sample_preprocessed_data())

    assert profile["accessory_registry"][0]["name"] == "magnetic back clip"
    assert any(item["claim"] == "150 minute runtime" for item in profile["claim_registry"])
