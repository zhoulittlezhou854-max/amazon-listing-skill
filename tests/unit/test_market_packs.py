from types import SimpleNamespace

from modules.intent_weights import save_intent_weight_snapshot
from modules.market_packs import apply_market_pack, load_market_pack
from modules.writing_policy import generate_default_4scene_policy


def test_market_pack_loader_returns_default_shape_for_de():
    pack = load_market_pack("DE")

    assert pack["locale"] == "DE"
    assert "lexical_preferences" in pack
    assert "faq_templates" in pack
    assert "compliance_reminders" in pack
    assert "after_sales_promises" in pack
    assert "support_sop" in pack


def test_market_pack_loader_is_resilient_for_unknown_locale():
    pack = load_market_pack("ZZ")

    assert pack["locale"] == "ZZ"
    assert isinstance(pack["lexical_preferences"], list)


def test_apply_market_pack_adds_policy_overlay():
    policy = {"compliance_directives": {"backend_only_terms": []}, "bullet_slot_rules": {"B5": {"required_elements": []}}}
    pack = {
        "locale": "DE",
        "lexical_preferences": ["action kamera"],
        "faq_templates": ["cold_weather"],
        "compliance_reminders": ["avoid unsupported battery safety guarantees"],
        "after_sales_promises": ["DE support handled in seller message center"],
        "support_sop": ["Confirm mount compatibility before replacement approval"],
    }

    merged = apply_market_pack(policy, pack)

    assert merged["market_pack"]["locale"] == "DE"
    assert "market_pack_reminders" in merged["compliance_directives"]
    assert merged["bullet_slot_rules"]["B5"]["after_sales_promises"] == ["DE support handled in seller message center"]
    assert merged["operator_sop"] == ["Confirm mount compatibility before replacement approval"]


def test_default_policy_includes_market_pack_and_question_bank():
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(),
        attribute_data=SimpleNamespace(data={"category": "action_camera"}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        core_selling_points=["4K recording", "waterproof"],
        canonical_core_selling_points=["4k recording", "waterproof"],
        accessory_descriptions=[],
        canonical_accessory_descriptions=[],
        quality_score=88,
        language="German",
        processed_at="2026-04-13T00:00:00",
        real_vocab=None,
        target_country="DE",
        capability_constraints={},
        keyword_metadata=[],
        raw_human_insights="",
        feedback_context={},
        asin_entity_profile={"category": "action_camera", "claim_registry": [{"claim": "150 minute runtime"}]},
    )

    policy = generate_default_4scene_policy(preprocessed)

    assert policy["market_pack"]["locale"] == "DE"
    assert "question_bank_context" in policy


def test_default_policy_applies_intent_weight_snapshot(tmp_path):
    snapshot_path = save_intent_weight_snapshot(
        str(tmp_path),
        rows=[
            {
                "keyword": "helmet camera",
                "ctr": 0.12,
                "cvr": 0.08,
                "orders": 12,
                "scene": "cycling_recording",
                "capability": "hands_free",
            }
        ],
        product_code="T70",
        site="DE",
        source_file="ppc.csv",
    )
    preprocessed = SimpleNamespace(
        run_config=SimpleNamespace(workspace_dir=str(tmp_path)),
        attribute_data=SimpleNamespace(data={"category": "action_camera"}),
        keyword_data=SimpleNamespace(keywords=[]),
        review_data=SimpleNamespace(insights=[]),
        aba_data=SimpleNamespace(trends=[]),
        core_selling_points=["4K recording", "waterproof"],
        canonical_core_selling_points=["4k recording", "waterproof"],
        accessory_descriptions=[],
        canonical_accessory_descriptions=[],
        quality_score=88,
        language="German",
        processed_at="2026-04-13T00:00:00",
        real_vocab=None,
        target_country="DE",
        capability_constraints={},
        keyword_metadata=[],
        raw_human_insights="",
        feedback_context={},
        asin_entity_profile={"category": "action_camera", "claim_registry": [{"claim": "150 minute runtime"}]},
        intent_weight_snapshot={"weights": [{"keyword": "helmet camera", "traffic_weight": 0.12, "conversion_weight": 0.08, "scene_weight": 0.1}]},
    )

    policy = generate_default_4scene_policy(preprocessed)

    assert "helmet camera" in policy["keyword_routing"]["title_traffic_keywords"]
    assert policy["intent_weight_summary"]["updated_keyword_count"] == 1
