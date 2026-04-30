from modules.packet_rerender import (
    apply_slot_rerender_result,
    build_slot_rerender_plan,
    execute_slot_rerender_plan,
)



def test_build_slot_rerender_plan_returns_only_unhealthy_slots():
    generated_copy = {
        "bullets": ["B1 text", "B2 text"],
        "bullet_packets": [
            {"slot": "B1", "header": "B1", "benefit": "ok", "proof": "ok", "guidance": ""},
            {"slot": "B2", "header": "B2", "benefit": "bad", "proof": "", "guidance": "tail"},
        ],
        "slot_quality_packets": [
            {
                "slot": "B1",
                "contract_pass": True,
                "fluency_pass": True,
                "unsupported_policy_pass": True,
                "issues": [],
            },
            {
                "slot": "B2",
                "contract_pass": False,
                "fluency_pass": False,
                "unsupported_policy_pass": True,
                "issues": ["missing_keywords", "dash_tail_without_predicate"],
            },
        ],
    }
    writing_policy = {
        "bullet_slot_rules": {
            "B1": {"repair_policy": {"on_contract_fail": "rerender_slot", "on_fluency_fail": "rerender_slot"}},
            "B2": {"repair_policy": {"on_contract_fail": "rerender_slot", "on_fluency_fail": "rerender_slot"}},
        }
    }

    plan = build_slot_rerender_plan(generated_copy, writing_policy)

    assert [row["slot"] for row in plan] == ["B2"]
    assert plan[0]["rerender_reasons"] == [
        "contract_fail",
        "fluency_fail",
        "missing_keywords",
        "dash_tail_without_predicate",
    ]
    assert plan[0]["strategy"] == "slot_packet_rerender"
    assert plan[0]["current_bullet"] == "B2 text"



def test_build_slot_rerender_plan_skips_slots_without_rerender_policy():
    generated_copy = {
        "bullets": ["B4 text"],
        "bullet_packets": [
            {
                "slot": "B4",
                "header": "B4",
                "benefit": "benefit",
                "proof": "",
                "guidance": "guidance",
            }
        ],
        "slot_quality_packets": [
            {
                "slot": "B4",
                "contract_pass": False,
                "fluency_pass": False,
                "unsupported_policy_pass": False,
                "issues": ["unsupported_capability_negative_literal"],
            }
        ],
    }
    writing_policy = {
        "bullet_slot_rules": {
            "B4": {"repair_policy": {"on_contract_fail": "diagnose_only", "on_fluency_fail": "diagnose_only"}}
        }
    }

    assert build_slot_rerender_plan(generated_copy, writing_policy) == []



def test_apply_slot_rerender_result_replaces_only_target_slot_rows():
    generated_copy = {
        "bullets": ["B1 old", "B2 old"],
        "bullet_packets": [{"slot": "B1", "header": "KEEP"}, {"slot": "B2", "header": "OLD"}],
        "slot_quality_packets": [{"slot": "B1", "issues": []}, {"slot": "B2", "issues": ["missing_keywords"]}],
    }
    rerender_result = {
        "slot": "B2",
        "bullet": "B2 new",
        "packet": {"slot": "B2", "header": "NEW"},
        "quality": {"slot": "B2", "issues": []},
    }

    updated = apply_slot_rerender_result(generated_copy, rerender_result)

    assert updated["bullets"] == ["B1 old", "B2 new"]
    assert updated["bullet_packets"][0]["header"] == "KEEP"
    assert updated["bullet_packets"][1]["header"] == "NEW"
    assert updated["slot_quality_packets"][1]["issues"] == []


def test_execute_slot_rerender_plan_applies_only_planned_slot_results():
    generated_copy = {
        "bullets": ["B1 old", "B2 old"],
        "bullet_packets": [
            {"slot": "B1", "header": "KEEP"},
            {"slot": "B2", "header": "OLD"},
        ],
        "slot_quality_packets": [
            {"slot": "B1", "issues": []},
            {"slot": "B2", "issues": ["missing_keywords"]},
        ],
    }
    rerender_plan = [
        {
            "slot": "B2",
            "current_bullet": "B2 old",
            "source_packet": {"slot": "B2", "header": "OLD"},
            "slot_quality": {"slot": "B2", "issues": ["missing_keywords"]},
            "repair_policy": {"on_contract_fail": "rerender_slot"},
            "rerender_reasons": ["contract_fail", "missing_keywords"],
            "priority": "high",
            "strategy": "slot_packet_rerender",
        }
    ]

    def _fake_rerender_slot(plan_entry, current_copy):
        assert plan_entry["slot"] == "B2"
        assert current_copy["bullets"][1] == "B2 old"
        return {
            "slot": "B2",
            "bullet": "B2 new",
            "packet": {"slot": "B2", "header": "NEW"},
            "quality": {"slot": "B2", "issues": [], "rerender_count": 1},
        }

    updated, results = execute_slot_rerender_plan(
        generated_copy,
        rerender_plan,
        _fake_rerender_slot,
    )

    assert updated["bullets"] == ["B1 old", "B2 new"]
    assert updated["bullet_packets"][0]["header"] == "KEEP"
    assert updated["bullet_packets"][1]["header"] == "NEW"
    assert updated["slot_quality_packets"][1]["rerender_count"] == 1
    assert results == [{"slot": "B2", "status": "applied"}]


def test_r1_batch_missing_keywords_builds_default_rerender_plan():
    from modules.packet_rerender import build_slot_rerender_plan

    generated_copy = {
        "metadata": {"visible_copy_mode": "r1_batch"},
        "bullets": [
            "Battery for Adventures -- Records for 150 minutes.",
            "Evidence Capture -- Weighs 0.1 kg.",
        ],
        "bullet_packets": [
            {"slot": "B1", "required_keywords": ["action camera"], "header": "Battery", "benefit": "Records long.", "proof": "150 minutes.", "guidance": "Use daily."},
            {"slot": "B2", "required_keywords": ["body camera"], "header": "Evidence", "benefit": "Wear it.", "proof": "0.1 kg.", "guidance": "Use at work."},
        ],
        "slot_quality_packets": [
            {"slot": "B1", "contract_pass": False, "fluency_pass": True, "unsupported_policy_pass": True, "keyword_coverage_pass": False, "issues": ["missing_keywords"]},
            {"slot": "B2", "contract_pass": False, "fluency_pass": True, "unsupported_policy_pass": True, "keyword_coverage_pass": False, "issues": ["missing_keywords"]},
        ],
    }

    plan = build_slot_rerender_plan(generated_copy, {"bullet_slot_rules": {}})

    assert [row["slot"] for row in plan] == ["B1", "B2"]
    assert all("missing_keywords" in row["rerender_reasons"] for row in plan)


def test_execute_rerender_uses_clean_b5_local_fallback(monkeypatch):
    import modules.copy_generation as cg

    class FailingClient:
        def generate_text(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(cg, "get_llm_client", lambda: FailingClient())

    result = cg._rerender_slot_from_packet_plan(
        {
            "slot": "B5",
            "source_packet": {
                "slot": "B5",
                "required_keywords": ["body camera"],
                "header": "Everything You Need",
                "benefit": "Includes body camera and card.",
                "proof": "Supports 256 GB card.",
                "guidance": "Card not included.",
            },
            "slot_quality": {
                "issues": ["slot_contract_failed:multiple_primary_promises", "repeated_word_root"],
                "rerender_count": 0,
            },
            "rerender_reasons": ["slot_contract_failed", "repeated_word_root"],
        },
        {"bullet_slot_rules": {}, "copy_contracts": {}},
        "English",
    )

    assert result["status"] == "applied_local_fallback"
    assert result["bullet"].lower().count("card") <= 1
    assert "150 minutes" not in result["bullet"].lower()
    assert "long battery" not in result["bullet"].lower()


def test_execute_rerender_rejects_failed_llm_b5_and_preserves_keywords(monkeypatch):
    import modules.copy_generation as cg

    class BadClient:
        def generate_text(self, *args, **kwargs):
            return """{
                "slot": "B5",
                "header": "Ready Kit",
                "benefit": "Includes a camera, card, and clip.",
                "proof": "The card supports hours of clips.",
                "guidance": "Use the card for recording."
            }"""

    monkeypatch.setattr(cg, "get_llm_client", lambda: BadClient())

    result = cg._rerender_slot_from_packet_plan(
        {
            "slot": "B5",
            "source_packet": {
                "slot": "B5",
                "required_keywords": ["wearable camera", "thumb camera"],
                "header": "Everything You Need",
                "benefit": "Includes wearable camera and card.",
                "proof": "Supports 256 GB card.",
                "guidance": "Card not included.",
            },
            "slot_quality": {
                "issues": ["missing_keywords", "repeated_word_root"],
                "keyword_coverage_pass": False,
                "rerender_count": 0,
            },
            "rerender_reasons": ["keyword_coverage_fail", "missing_keywords", "repeated_word_root"],
        },
        {"bullet_slot_rules": {}, "copy_contracts": {}},
        "English",
    )

    lowered = result["bullet"].lower()
    assert result["status"] == "applied_local_fallback"
    assert "wearable camera" in lowered
    assert "thumb camera" in lowered
    assert lowered.count("card") <= 1
    assert result["quality"]["keyword_coverage_pass"] is True


def test_b5_local_fallback_keeps_scene_binding_when_required(monkeypatch):
    import modules.copy_generation as cg

    class FailingClient:
        def generate_text(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(cg, "get_llm_client", lambda: FailingClient())

    result = cg._rerender_slot_from_packet_plan(
        {
            "slot": "B5",
            "source_packet": {
                "slot": "B5",
                "required_keywords": ["small camera"],
                "required_facts": ["package_contents", "compatibility_or_capacity"],
                "capability_mapping": ["easy operation"],
                "scene_mapping": ["travel_documentation", "vlog_content_creation"],
                "header": "Ready Kit",
                "benefit": "Includes small camera and card.",
                "proof": "Supports 256 GB card.",
                "guidance": "",
            },
            "slot_quality": {
                "issues": ["missing_keywords"],
                "keyword_coverage_pass": False,
                "rerender_count": 0,
            },
            "rerender_reasons": ["keyword_coverage_fail", "missing_keywords"],
        },
        {
            "bullet_slot_rules": {},
            "copy_contracts": {"scene_capability_numeric_binding": {"require_scene_and_capability": True}},
        },
        "English",
    )

    lowered = result["bullet"].lower()
    assert "travel" in lowered
    assert "vlog" in lowered
    assert "scene_binding_missing" not in result["quality"]["issues"]
    assert result["quality"]["contract_pass"] is True


def test_non_r1_surface_does_not_get_default_rerender_policy():
    from modules.packet_rerender import build_slot_rerender_plan

    generated_copy = {
        "metadata": {"visible_copy_mode": "standard"},
        "bullets": ["Battery -- Records long."],
        "bullet_packets": [{"slot": "B1", "required_keywords": ["action camera"]}],
        "slot_quality_packets": [
            {"slot": "B1", "contract_pass": False, "keyword_coverage_pass": False, "issues": ["missing_keywords"]},
        ],
    }

    assert build_slot_rerender_plan(generated_copy, {"bullet_slot_rules": {}}) == []
