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


def test_b5_package_battery_is_not_runtime_promise():
    from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

    bullet = (
        "READY-TO-RECORD KIT -- Includes body camera, magnetic clip, back clip, "
        "USB-C cable, 32 GB microSD card, and lithium battery. "
        "Add higher-capacity storage up to 256 GB when needed."
    )

    result = validate_bullet_against_contract(bullet, build_slot_contract("B5"))

    assert result["passed"] is True
    assert "battery_runtime" not in result["detected_promises"]


def test_b5_explicit_runtime_still_fails_as_second_promise():
    from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

    bullet = (
        "READY-TO-RECORD KIT -- Includes the camera and clip. "
        "Long battery life provides up to 150 minutes of continuous recording."
    )

    result = validate_bullet_against_contract(bullet, build_slot_contract("B5"))

    assert "battery_runtime" in result["detected_promises"]
    assert "multiple_primary_promises" in result["reasons"]
