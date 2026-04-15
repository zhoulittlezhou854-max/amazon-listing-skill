from modules.question_bank import build_question_bank_context


def test_question_bank_returns_action_camera_templates():
    entity_profile = {
        "product_code": "T70",
        "category": "action_camera",
        "core_specs": {"waterproof_requires_case": True},
        "claim_registry": [{"claim": "150 minute runtime"}],
    }

    context = build_question_bank_context(entity_profile, "DE")

    assert "questions" in context
    assert any("battery" in item["topic"] for item in context["questions"])
    assert any(item["market"] == "DE" for item in context["questions"])


def test_question_bank_provides_evidence_hints_from_entity_profile():
    entity_profile = {
        "product_code": "T70",
        "category": "action_camera",
        "core_specs": {"waterproof_requires_case": True},
        "claim_registry": [{"claim": "30 m waterproof with case"}],
    }

    context = build_question_bank_context(entity_profile, "FR")

    assert "evidence_hints" in context
    assert any("30 m waterproof with case" in hint for hint in context["evidence_hints"])


def test_question_bank_returns_empty_defaults_for_missing_entity_profile():
    context = build_question_bank_context({}, "DE")

    assert context["questions"] == []
    assert context["evidence_hints"] == []
