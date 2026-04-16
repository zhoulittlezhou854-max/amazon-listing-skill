from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from modules.copy_generation import (
    LEGACY_BULLET_SLOT_RULES,
    PreprocessedData,
    generate_multilingual_copy,
)


def _policy_with_downgrade():
    slot_rules = deepcopy(LEGACY_BULLET_SLOT_RULES)
    return {
        "scene_priority": ["cycling_recording", "underwater_exploration"],
        "keyword_allocation_strategy": "balanced",
        "keyword_slots": {
            "title": ["action camera"],
            "bullet_1": {"keywords": ["action camera"]},
            "bullet_2": {"keywords": ["long battery camera"]},
            "bullet_3": {"keywords": ["dual screen"]},
            "bullet_4": {"keywords": ["waterproof action camera"]},
            "bullet_5": {"keywords": ["warranty"]},
            "search_terms": {"keywords": ["helmet cam"]},
        },
        "bullet_slot_rules": slot_rules,
        "title_slots": [
            {"slot": "brand", "required": True},
            {"slot": "l1_keyword", "required": True},
            {"slot": "scene", "scene": "cycling_recording", "required": True},
            {"slot": "hero_capability", "required": True},
            {"slot": "spec_pack", "required": False},
        ],
        "search_term_plan": {
            "priority_tiers": ["l3"],
            "max_bytes": 249,
            "backend_only_terms": ["waterproof action camera"],
        },
        "compliance_directives": {
            "waterproof": {
                "allow_visible": False,
                "requires_case": False,
                "depth_m": None,
                "note": "设备非防水，请保持干燥。",
            },
            "stabilization": {"allow_visible": True, "modes": [], "note": ""},
            "runtime_minutes": 150,
            "search_term_byte_limit": 249,
            "backend_only_terms": ["waterproof action camera"],
        },
        "product_profile": {"reasoning_language": "EN"},
    }


def test_waterproof_claim_downgraded_and_audited():
    preprocessed = PreprocessedData(
        run_config=SimpleNamespace(brand_name="TestBrand"),
        attribute_data=SimpleNamespace(data={"video_resolution": "4K"}),
        keyword_data=SimpleNamespace(
            keywords=[{"keyword": "waterproof action camera", "search_volume": 12000}]
        ),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        real_vocab=None,
        core_selling_points=["Waterproof build", "4K recording"],
        accessory_descriptions=[],
        quality_score=80,
        language="English",
        processed_at="2026-04-06T00:00:00",
        target_country="US",
        capability_constraints={
            "waterproof_supported": False,
            "waterproof_requires_case": False,
            "waterproof_depth_m": None,
            "waterproof_note": "设备非防水",
            "stabilization_supported": True,
            "stabilization_modes": ["1080P"],
            "stabilization_note": "",
            "max_resolution": "4K",
            "runtime_minutes": 150,
            "backend_only_terms": ["waterproof action camera"],
        },
        keyword_metadata=[],
    )

    policy = _policy_with_downgrade()
    result = generate_multilingual_copy(preprocessed, policy, language="English")

    visible_blob = " ".join(
        [result["title"], result["description"], *result.get("bullets", [])]
    ).lower()
    assert "waterproof" not in visible_blob

    audit_trail = result.get("audit_trail", [])
    assert audit_trail, "audit trail should capture downgrade actions"
    assert any(
        item.get("action") == "delete" and "waterproof" in item.get("term", "").lower()
        for item in audit_trail
    ), "expected waterproof delete log"

    assert any(
        item.get("action") == "backend_only"
        and "waterproof action camera" in item.get("term", "")
        for item in audit_trail
    ), "backend-only retention should be logged"
