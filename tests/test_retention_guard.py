import json
from pathlib import Path
from types import SimpleNamespace

from modules.retention_guard import build_retention_strategy, calculate_retention_report


class _Preprocessed:
    def __init__(self):
        self.run_config = SimpleNamespace(workspace_dir="")
        self.feedback_context = {
            "organic_core": [
                {"keyword": "body camera"},
                {"keyword": "wearable camera"},
                {"keyword": "thumb camera"},
            ]
        }


def test_retention_guard_blocks_when_too_many_organic_keywords_drop():
    report = calculate_retention_report(
        _Preprocessed(),
        {
            "title": "Compact wearable camera for commuting",
            "bullets": ["FAST CLIP-ON POV — Capture your route hands-free."],
            "description": "Designed for daily commute capture.",
        },
    )
    assert report["enabled"] is True
    assert report["is_blocking"] is True
    assert "thumb camera" in report["missing_keywords"]


def test_retention_strategy_uses_historical_best_run(tmp_path: Path):
    workspace = tmp_path / "workspace" / "T70_US" / "runs" / "20260411_000001"
    workspace.mkdir(parents=True)
    (workspace / "generated_copy.json").write_text(
        json.dumps(
            {
                "decision_trace": {
                    "keyword_assignments": [
                        {
                            "keyword": "bike camera",
                            "tier": "L1",
                            "source_type": "feedback_organic_core",
                            "assigned_fields": ["title"],
                        },
                        {
                            "keyword": "helmet camera",
                            "tier": "L2",
                            "source_type": "feedback_sp_intent",
                            "assigned_fields": ["bullet_1"],
                        },
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / "scoring_results.json").write_text(
        json.dumps(
            {
                "listing_status": "READY_FOR_HUMAN_REVIEW",
                "total_score": 255,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    preprocessed = _Preprocessed()
    preprocessed.run_config = SimpleNamespace(workspace_dir=str(tmp_path / "workspace" / "T70_US"))
    preprocessed.feedback_context = {"organic_core": []}

    strategy = build_retention_strategy(preprocessed)

    assert strategy["historical_run"]
    assert "bike camera" in strategy["title_anchor_keywords"]
    assert "helmet camera" in strategy["bullet_anchor_keywords"]


def test_retention_guard_degrades_gracefully_without_feedback_or_history():
    preprocessed = _Preprocessed()
    preprocessed.run_config = SimpleNamespace(workspace_dir="")
    preprocessed.feedback_context = {}

    strategy = build_retention_strategy(preprocessed)
    report = calculate_retention_report(
        preprocessed,
        {
            "title": "Compact wearable camera",
            "bullets": ["Lightweight clip-on POV for commuting."],
            "description": "Simple sparse-input listing draft.",
        },
    )

    assert strategy["enabled"] is False
    assert strategy["title_anchor_keywords"] == []
    assert report["enabled"] is False
    assert report["is_blocking"] is False
