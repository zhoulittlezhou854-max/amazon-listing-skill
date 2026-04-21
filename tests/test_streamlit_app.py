from app.streamlit_app import (
    build_result_display_state,
    build_report_guide_rows,
    build_result_summary_rows,
    build_score_explanation_rows,
    summarize_run_failure,
)


def test_summarize_run_failure_marks_run_as_finished_not_background():
    notice = summarize_run_failure(
        {
            "status": "RUN_FAILED",
            "error": "LLM 初始化失败：missing api key",
            "run_dir": "/tmp/demo-run",
            "report_path": "",
            "logs": "traceback...",
        }
    )

    assert notice is not None
    assert "LLM 初始化失败" in notice["headline"]
    assert "没有在后台继续运行" in notice["detail"]
    assert "/tmp/demo-run" in notice["detail"]


def test_summarize_run_failure_returns_none_without_error():
    assert summarize_run_failure({"status": "success"}) is None


def test_build_result_display_state_prefers_final_verdict_payload():
    state = build_result_display_state(
        {
            "status": "success",
            "risk_report": {"listing_status": {"status": "READY_FOR_LISTING"}},
            "scoring_results": {"total_score": 283, "grade": "待优化"},
            "final_readiness_verdict": {
                "recommended_output": "hybrid",
                "listing_status": "READY_FOR_LISTING",
                "reasons": ["cosmo_below_threshold"],
            },
            "dual_report_path": "/tmp/all_report_compare.md",
            "listing_ready_path": "/tmp/LISTING_READY.md",
            "final_readiness_verdict_path": "/tmp/final_readiness_verdict.json",
            "hybrid": {
                "generated_copy": {"metadata": {"generation_status": "reaudited"}},
                "risk_report": {"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
                "scoring_results": {"total_score": 301, "grade": "优秀"},
            },
        }
    )

    assert state["recommended_output"] == "hybrid"
    assert state["listing_status"] == "READY_FOR_LISTING"
    assert state["total_score"] == 301
    assert state["grade"] == "优秀"
    assert state["primary_report_path"] == "/tmp/all_report_compare.md"
    assert state["listing_ready_path"] == "/tmp/LISTING_READY.md"
    assert state["blocking_reasons"] == ["cosmo_below_threshold"]


def test_build_score_explanation_rows_translates_gate_into_human_readable_rows():
    rows = build_score_explanation_rows(
        {
            "final_readiness_verdict": {
                "launch_gate": {
                    "passed": False,
                    "scores": {"A10": 100, "COSMO": 77, "Rufus": 100, "Fluency": 30},
                    "thresholds": {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24},
                }
            }
        }
    )

    assert rows[0]["指标"] == "A10（流量覆盖）"
    assert rows[0]["当前分数"] == 100
    assert rows[1]["是否通过"] == "未通过"
    assert "关键词覆盖" in rows[0]["怎么理解"]
    assert rows[3]["建议门槛"] == 24


def test_build_result_summary_rows_explains_machine_fields_in_chinese():
    rows = build_result_summary_rows(
        {
            "status": "success",
            "final_readiness_verdict": {
                "recommended_output": "version_a",
                "listing_status": "READY_FOR_LISTING",
                "reasons": ["cosmo_below_threshold"],
            },
            "scoring_results": {"total_score": 288, "grade": "待优化"},
        }
    )

    assert rows[0]["字段"] == "上线状态（Listing Status）"
    assert rows[0]["当前值"] == "READY_FOR_LISTING"
    assert "能否直接作为上线候选" in rows[0]["怎么理解"]
    assert rows[1]["当前值"] == "version_a"
    assert "V3 基线版" in rows[1]["怎么理解"]
    assert rows[4]["当前值"] == "success"


def test_build_report_guide_rows_clarifies_three_reports():
    rows = build_report_guide_rows(
        {
            "dual_report_path": "/tmp/all_report_compare.md",
            "final_readiness_verdict_path": "/tmp/final_readiness_verdict.json",
            "listing_ready_path": "/tmp/LISTING_READY.md",
            "final_readiness_verdict": {"recommended_output": "hybrid"},
        }
    )

    assert rows[0]["报告"] == "LISTING_READY.md"
    assert "最终推荐版" in rows[0]["对应版本"]
    assert rows[1]["报告"] == "final_readiness_verdict.json"
    assert "不是文案" in rows[1]["用途"]
    assert rows[2]["报告"] == "all_report_compare.md"
    assert "V3 基线版" in rows[2]["对应版本"]
