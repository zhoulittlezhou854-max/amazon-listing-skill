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
