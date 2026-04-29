from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract


def test_b5_rejects_multi_topic_package_battery_support_blend():
    contract = build_slot_contract("B5", canonical_facts={"fact_map": {}})
    bullet = (
        "Unbox, Charge, and Start Capturing — The box includes a mini body camera, mount, USB-C cable, "
        "and a 32GB memory card so you can record right out of the box. Supports up to 256GB cards; "
        "150-minute battery powers full adventures. Our support team is ready if you need help."
    )

    result = validate_bullet_against_contract(bullet, contract)

    assert result["passed"] is False
    assert "multiple_primary_promises" in result["reasons"]
    assert result["repair_payload"]["slot"] == "B5"


def test_b5_accepts_ready_kit_with_single_semantic_bridge():
    contract = build_slot_contract(
        "B5",
        canonical_facts={
            "fact_map": {
                "included_components": {
                    "value": ["mini body camera", "USB-C cable", "mount", "32GB memory card"],
                    "claim_permission": "visible_allowed",
                },
                "storage_supported": {"value": "up to 256GB", "claim_permission": "visible_allowed"},
            }
        },
    )
    bullet = (
        "Ready-to-Record Kit — Includes the mini body camera, USB-C cable, mount, and 32GB memory card "
        "so you can start recording after setup. Expand storage with cards up to 256GB for longer trips or daily recording."
    )

    result = validate_bullet_against_contract(bullet, contract)

    assert result["passed"] is True
    assert result["reasons"] == []
