from pathlib import Path

from modules.feedback_loop import build_feedback_context, load_feedback_snapshot, save_feedback_snapshot


def test_feedback_context_routes_keywords_by_source_and_slot():
    rows = [
        {"keep": True, "keyword": "body camera", "source": "organic", "suggested_slot": "title", "risk_flag": "ok"},
        {"keep": True, "keyword": "helmet mount vlog camera", "source": "sp", "suggested_slot": "backend", "risk_flag": "ok"},
        {"keep": False, "keyword": "gopro alt", "source": "organic", "suggested_slot": "title", "risk_flag": "blocked_brand"},
    ]
    context = build_feedback_context(rows)
    assert [row["keyword"] for row in context["organic_core"]] == ["body camera"]
    assert [row["keyword"] for row in context["backend_only"]] == ["helmet mount vlog camera"]
    assert [row["keyword"] for row in context["blocked_terms"]] == ["gopro alt"]


def test_save_and_load_feedback_snapshot(tmp_path: Path):
    snapshot = save_feedback_snapshot(
        workspace_dir=str(tmp_path),
        source_file="feedback.csv",
        rows=[{"keep": True, "keyword": "body camera", "source": "organic", "suggested_slot": "title", "risk_flag": "ok"}],
        product_code="H91",
        site="US",
        operator_notes="keep the winner",
    )
    payload = load_feedback_snapshot(snapshot)
    assert payload["product_code"] == "H91"
    assert payload["approved_keywords"]["organic_core"][0]["keyword"] == "body camera"
