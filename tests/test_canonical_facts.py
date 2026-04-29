from modules.canonical_facts import build_canonical_facts, summarize_fact_readiness


def test_h91_attribute_aliases_become_canonical_facts():
    result = build_canonical_facts(
        attribute_data={
            "Video capture resolution": "1080P",
            "Battery Average Life": "150 minutes",
            "Item Weight": "0.1 kg",
            "Included components": "Body Camera, USB Cable (Type-C), 32GB memory card",
            "Water Resistance Leve": "Not Water Resistant",
        },
        supplemental_data={},
        capability_constraints={},
    )

    by_id = {fact["fact_id"]: fact for fact in result["facts"]}
    assert by_id["video_resolution"]["value"] == "1080P"
    assert by_id["battery_life"]["value"] == 150
    assert by_id["battery_life"]["unit"] == "minutes"
    assert by_id["weight"]["value"] == 0.1
    assert by_id["weight"]["unit"] == "kg"
    assert by_id["storage_included"]["value"] == "32GB memory card"
    assert by_id["waterproof_supported"]["value"] is False
    assert by_id["waterproof_supported"]["claim_permission"] == "blocked"


def test_fact_readiness_treats_explicit_not_waterproof_as_known_boundary():
    facts = {
        "facts": [
            {"fact_id": "video_resolution", "value": "1080P", "confidence": 0.95, "claim_permission": "visible_allowed"},
            {"fact_id": "battery_life", "value": 150, "unit": "minutes", "confidence": 0.95, "claim_permission": "visible_allowed"},
            {"fact_id": "weight", "value": 0.1, "unit": "kg", "confidence": 0.9, "claim_permission": "visible_allowed"},
            {"fact_id": "waterproof_supported", "value": False, "confidence": 0.95, "claim_permission": "blocked"},
        ]
    }

    summary = summarize_fact_readiness(facts, category_type="wearable_body_camera")

    assert summary["required_fact_status"]["waterproof_supported"] == "known_blocked"
    assert summary["coverage"] == {"known": 4, "required": 4, "ratio": 1.0}
    assert summary["blocking_missing"] == []
    assert summary["blocking_missing_facts"] == []
    assert summary["readiness_score"] >= 80


def test_waterproof_unknown_text_does_not_become_positive_evidence():
    unknown_values = [
        "No IP rating mentioned",
        "Waterproof status unknown",
        "waterproof: unknown",
        "Unknown waterproof rating",
    ]

    for value in unknown_values:
        result = build_canonical_facts(
            attribute_data={"Water Resistance Leve": value},
            supplemental_data={},
            capability_constraints={},
        )

        fact = result["fact_map"]["waterproof_supported"]
        assert fact["value"] == value
        assert fact["claim_permission"] == "unknown"

        summary = summarize_fact_readiness(result, category_type="wearable_body_camera")
        assert summary["required_fact_status"]["waterproof_supported"] == "missing"
        assert "waterproof_supported" in summary["blocking_missing"]
