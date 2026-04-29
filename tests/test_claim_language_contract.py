from modules.claim_language_contract import audit_claim_language, repair_claim_language


def test_best_is_forbidden_surface_but_usage_intent_is_repairable():
    audit = audit_claim_language("This is the best body camera for travel recording.")
    assert audit["passed"] is False
    assert audit["repairable"] is True
    assert audit["violations"][0]["surface"] == "best"
    assert audit["violations"][0]["reason"] == "unsupported_superlative"


def test_repair_claim_language_preserves_intent_without_best():
    repaired = repair_claim_language(
        "This is the best body camera for travel recording.",
        canonical_facts={"fact_map": {"video_resolution": {"value": "1080P", "claim_permission": "visible_allowed"}}},
    )
    assert "best" not in repaired.lower()
    assert "travel" in repaired.lower()
    assert "body camera" in repaired.lower()


def test_hyphenated_superlatives_are_blocking_not_repaired_into_broken_copy():
    audit = audit_claim_language("This is a best-in-class #1-rated camera, better than ever.")

    assert audit["passed"] is False
    assert audit["repairable"] is False
    assert set(audit["blocking_reasons"]) == {"unsupported_superlative", "unsupported_comparison"}

    repaired = repair_claim_language("best-in-class #1-rated better than ever")
    assert repaired == "best-in-class #1-rated better than ever"
