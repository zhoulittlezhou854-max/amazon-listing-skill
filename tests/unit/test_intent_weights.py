from types import SimpleNamespace

from modules.intent_weights import (
    apply_intent_weight_overrides,
    apply_intent_weight_to_intent_graph,
    build_intent_weight_snapshot,
    load_intent_weight_snapshot,
    save_intent_weight_snapshot,
    summarize_intent_weight_snapshot,
)
from modules.intent_translator import generate_intent_graph


def test_intent_weight_snapshot_has_weight_rows():
    rows = [
        {
            "keyword": "helmet camera",
            "ctr": 0.12,
            "cvr": 0.08,
            "orders": 12,
            "scene": "cycling_recording",
            "capability": "hands_free",
        }
    ]

    snapshot = build_intent_weight_snapshot(rows)

    assert "weights" in snapshot
    assert isinstance(snapshot["weights"], list)


def test_intent_weight_snapshot_promotes_high_signal_rows():
    rows = [
        {
            "keyword": "helmet camera",
            "ctr": 0.12,
            "cvr": 0.08,
            "orders": 12,
            "scene": "cycling_recording",
            "capability": "hands_free",
        }
    ]

    snapshot = build_intent_weight_snapshot(rows)

    assert snapshot["weights"][0]["scene_weight"] > 0
    assert snapshot["weights"][0]["conversion_weight"] > 0


def test_intent_weight_snapshot_accepts_external_theme_rows():
    rows = [
        {
            "search term": "motorcycle helmet cam",
            "ctr": "12%",
            "conversion rate": "8%",
            "sales": 14,
            "scene": "cycling_recording",
            "capability": "hands_free",
            "theme": "commuter vlog setup",
            "channel": "youtube_review",
            "source": "external_review",
        }
    ]

    snapshot = build_intent_weight_snapshot(rows)
    summary = summarize_intent_weight_snapshot(snapshot)

    assert snapshot["weights"][0]["keyword"] == "motorcycle helmet cam"
    assert snapshot["weights"][0]["theme"] == "commuter vlog setup"
    assert snapshot["weights"][0]["traffic_channel"] == "youtube_review"
    assert snapshot["weights"][0]["source_type"] == "external_review"
    assert summary["external_theme_count"] == 1
    assert summary["channel_count"] == 1
    assert summary["top_external_themes"] == ["commuter vlog setup"]


def test_intent_weight_snapshot_can_roundtrip_to_disk(tmp_path):
    rows = [
        {
            "keyword": "helmet camera",
            "ctr": 0.12,
            "cvr": 0.08,
            "orders": 12,
            "scene": "cycling_recording",
            "capability": "hands_free",
        }
    ]

    target = save_intent_weight_snapshot(str(tmp_path), rows, "T70", "DE", source_file="ppc.csv")
    payload = load_intent_weight_snapshot(target)

    assert payload["product_code"] == "T70"
    assert payload["site"] == "DE"
    assert payload["weights"][0]["keyword"] == "helmet camera"


def test_apply_intent_weight_overrides_promotes_high_signal_keywords():
    policy = {
        "keyword_routing": {
            "title_traffic_keywords": ["action camera"],
            "bullet_conversion_keywords": ["bike camera"],
            "backend_longtail_keywords": [],
        }
    }
    retention_strategy = {"title_anchor_keywords": ["action camera"]}
    snapshot = {
        "weights": [
            {
                "keyword": "helmet camera",
                "traffic_weight": 0.12,
                "conversion_weight": 0.08,
                "scene_weight": 0.1,
                "capability_weight": 0.09,
            }
        ]
    }

    updated = apply_intent_weight_overrides(policy, retention_strategy, snapshot)

    assert "helmet camera" in updated["keyword_routing"]["title_traffic_keywords"]
    assert updated["intent_weight_summary"]["updated_keyword_count"] == 1


def test_apply_intent_weight_overrides_reorders_scenes_and_exposes_external_themes():
    policy = {
        "scene_priority": ["travel_documentation", "cycling_recording", "family_use"],
        "keyword_routing": {
            "title_traffic_keywords": ["action camera"],
            "bullet_conversion_keywords": ["bike camera"],
            "backend_longtail_keywords": [],
        },
    }
    retention_strategy = {"title_anchor_keywords": ["action camera"]}
    snapshot = {
        "weights": [
            {
                "keyword": "helmet camera",
                "traffic_weight": 0.12,
                "conversion_weight": 0.08,
                "scene_weight": 0.24,
                "capability_weight": 0.09,
                "scene": "cycling_recording",
                "theme": "commuter vlog setup",
                "traffic_channel": "youtube_review",
                "source_type": "external_review",
            }
        ]
    }

    updated = apply_intent_weight_overrides(policy, retention_strategy, snapshot)

    assert updated["scene_priority"][0] == "cycling_recording"
    assert updated["intent_weight_summary"]["top_external_themes"] == ["commuter vlog setup"]
    assert updated["intent_weight_summary"]["channel_count"] == 1


def test_summarize_intent_weight_snapshot_collects_keywords_and_dimensions():
    summary = summarize_intent_weight_snapshot(
        {
            "weights": [
                {
                    "keyword": "helmet camera",
                    "scene": "cycling_recording",
                    "capability": "hands_free",
                    "traffic_weight": 0.12,
                    "conversion_weight": 0.08,
                },
                {
                    "keyword": "bike camera",
                    "scene": "travel_documentation",
                    "capability": "stabilization",
                    "traffic_weight": 0.11,
                    "conversion_weight": 0.06,
                },
            ]
        }
    )

    assert summary["updated_keyword_count"] == 2
    assert summary["scene_count"] == 2
    assert summary["capability_count"] == 2
    assert summary["top_promoted_keywords"] == ["helmet camera", "bike camera"]


def test_apply_intent_weight_overrides_normalizes_empty_snapshot():
    updated = apply_intent_weight_overrides(
        {"keyword_routing": {"title_traffic_keywords": [], "bullet_conversion_keywords": []}},
        {"title_anchor_keywords": []},
        {},
    )

    assert updated["intent_weight_snapshot"] == {"weights": []}
    assert updated["intent_weight_summary"]["updated_keyword_count"] == 0


def test_apply_intent_weight_to_intent_graph_promotes_matching_scene_and_capability():
    intent_graph_data = {
        "intent_graph": [
            {
                "id": "intent_1",
                "source_keywords": ["travel camera"],
                "usage_scenarios": ["travel_documentation"],
                "capabilities": ["wifi connectivity"],
                "search_volume": 1200,
            },
            {
                "id": "intent_2",
                "source_keywords": ["helmet camera"],
                "usage_scenarios": ["cycling_recording"],
                "capabilities": ["stabilization"],
                "search_volume": 900,
            },
        ],
        "scene_metadata": [
            {"scene": "travel_documentation"},
            {"scene": "cycling_recording"},
        ],
        "capability_metadata": [
            {"capability": "wifi connectivity"},
            {"capability": "stabilization"},
        ],
        "metadata": {},
    }
    snapshot = {
        "weights": [
            {
                "keyword": "helmet camera",
                "scene": "cycling_recording",
                "capability": "stabilization",
                "traffic_weight": 0.12,
                "conversion_weight": 0.08,
                "scene_weight": 0.104,
                "capability_weight": 0.092,
            }
        ]
    }

    updated = apply_intent_weight_to_intent_graph(intent_graph_data, snapshot)

    assert updated["intent_graph"][0]["id"] == "intent_2"
    assert updated["intent_graph"][0]["learned_rank_score"] > 0
    assert updated["scene_metadata"][1]["learned_weight"] > 0
    assert updated["capability_metadata"][1]["learned_weight"] > 0
    assert updated["metadata"]["intent_weight_summary"]["updated_keyword_count"] == 1


def test_generate_intent_graph_applies_intent_weight_snapshot_to_rank_nodes():
    preprocessed = SimpleNamespace(
        data_mode="DATA_DRIVEN",
        language="English",
        target_country="US",
        canonical_core_selling_points=[],
        canonical_capability_notes={},
        capability_constraints={},
        feedback_context={},
        intent_weight_snapshot={
            "weights": [
                {
                    "keyword": "helmet camera",
                    "scene": "cycling_recording",
                    "capability": "stabilization",
                    "traffic_weight": 0.12,
                    "conversion_weight": 0.08,
                    "scene_weight": 0.104,
                    "capability_weight": 0.092,
                }
            ]
        },
        keyword_data=SimpleNamespace(
            keywords=[
                {"keyword": "travel camera", "search_volume": 1300},
                {"keyword": "helmet camera", "search_volume": 1100},
            ]
        ),
    )

    result = generate_intent_graph(None, preprocessed)

    assert result["intent_graph"][0]["source_keywords"][0] == "helmet camera"
    assert any(
        row["scene"] == "cycling_recording" and row.get("learned_weight", 0) > 0
        for row in result["scene_metadata"]
    )
