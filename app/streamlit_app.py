#!/usr/bin/env python3
"""Local Streamlit control console for new listing runs and feedback-loop rebuilds."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.services.run_service import run_workspace_workflow
from app.services.workspace_service import (
    attach_feedback_snapshot,
    attach_intent_weight_snapshot,
    initialize_workspace,
    list_product_code_options,
    list_workspace_runs,
    list_workspaces,
)
from modules.csv_parser import parse_keyword_feedback_table
from modules.feedback_loop import save_feedback_snapshot
from modules.intent_weights import save_intent_weight_snapshot

DEFAULT_STEPS = [0, 2, 4, 5, 6, 7, 8, 9]
MANUAL_PRODUCT_CODE_OPTION = "__manual_product_code__"
VERSION_EXPLANATIONS = {
    "version_a": "version_a：V3 基线版，当前最稳定、最保守的主链路版本。",
    "version_b": "version_b：R1 Title/Bullets 实验版，主要测试新的标题与五点生成方式。",
    "hybrid": "hybrid：融合版，从多个版本里挑选更优字段后形成的最终候选。",
}
LAUNCH_GATE_METRICS = [
    (
        "A10",
        "A10（流量覆盖）",
        "看关键词覆盖和流量抓取能力；越高说明高价值搜索词覆盖越完整。",
    ),
    (
        "COSMO",
        "COSMO（内容匹配）",
        "看文案是否贴合用户关注点、卖点结构和竞品预期。",
    ),
    (
        "Rufus",
        "Rufus（转化说服）",
        "看文案是否把购买理由说清楚，是否能推动用户下单。",
    ),
    (
        "Fluency",
        "Fluency（语句自然度）",
        "看句子是否自然顺畅、像人写的，不会突兀或拼接感太强。",
    ),
]


def summarize_run_failure(result: dict) -> dict | None:
    error = str(result.get("error") or "").strip()
    if not error:
        return None
    run_dir = str(result.get("run_dir") or "").strip() or "-"
    return {
        "headline": f"运行失败：{error}",
        "detail": (
            "这次任务已经结束，没有在后台继续运行。"
            f" 当前失败 run 位于：`{run_dir}`。"
            " 如果需要排查，请先查看展开的系统过程数据。"
        ),
    }


def build_result_display_state(result: dict) -> dict:
    verdict = result.get("final_readiness_verdict") or {}
    recommended_output = str(verdict.get("recommended_output") or "").strip()
    dual_version = result.get("dual_version") or {}
    source_map = {
        "version_a": dual_version.get("version_a") or {},
        "version_b": dual_version.get("version_b") or {},
        "hybrid": result.get("hybrid") or {},
    }
    selected = source_map.get(recommended_output) or {}
    scoring_results = selected.get("scoring_results") or result.get("scoring_results") or {}
    risk_report = selected.get("risk_report") or result.get("risk_report") or {}
    blocking_reasons = list(verdict.get("reasons") or (risk_report.get("listing_status") or {}).get("blocking_reasons") or scoring_results.get("blocking_reasons") or [])
    primary_report_path = result.get("dual_report_path") or result.get("report_path") or ""
    return {
        "recommended_output": recommended_output or "-",
        "listing_status": str(verdict.get("listing_status") or (risk_report.get("listing_status") or {}).get("status") or result.get("status") or "-"),
        "total_score": scoring_results.get("total_score"),
        "grade": scoring_results.get("grade") or "-",
        "blocking_reasons": blocking_reasons,
        "report_path": result.get("report_path") or "",
        "primary_report_path": primary_report_path,
        "final_readiness_verdict_path": result.get("final_readiness_verdict_path") or "",
        "listing_ready_path": result.get("listing_ready_path") or "",
    }


def build_score_explanation_rows(result: dict) -> list[dict]:
    launch_gate = ((result.get("final_readiness_verdict") or {}).get("launch_gate") or {})
    scores = launch_gate.get("scores") or {}
    thresholds = launch_gate.get("thresholds") or {}
    rows: list[dict] = []
    for key, label, explanation in LAUNCH_GATE_METRICS:
        current_score = scores.get(key, 0)
        threshold = thresholds.get(key, 0)
        passed = current_score >= threshold if threshold else False
        rows.append(
            {
                "指标": label,
                "当前分数": current_score,
                "建议门槛": threshold,
                "是否通过": "通过" if passed else "未通过",
                "怎么理解": explanation,
            }
        )
    return rows


def build_result_summary_rows(result: dict) -> list[dict]:
    display_state = build_result_display_state(result)
    recommended_output = display_state["recommended_output"]
    recommended_explanation = VERSION_EXPLANATIONS.get(
        recommended_output,
        "系统当前没有给出明确版本结论，建议先看最终判定文件再排查。",
    )
    return [
        {
            "字段": "上线状态（Listing Status）",
            "当前值": display_state["listing_status"],
            "怎么理解": "表示这份文案能否直接作为上线候选；READY_FOR_LISTING 通常代表可以进入人工复核或直接上架。",
        },
        {
            "字段": "推荐版本（Recommended）",
            "当前值": recommended_output,
            "怎么理解": recommended_explanation,
        },
        {
            "字段": "综合分（Total Score）",
            "当前值": display_state["total_score"] if display_state["total_score"] is not None else "-",
            "怎么理解": "这是当前推荐版本的综合评分，用来快速判断整体质量高低。",
        },
        {
            "字段": "等级（Grade）",
            "当前值": display_state["grade"],
            "怎么理解": "这是系统给出的文字等级，便于不用看明细分时快速把握整体状态。",
        },
        {
            "字段": "任务执行状态（Run Status）",
            "当前值": result.get("status") or "-",
            "怎么理解": "看这次任务本身有没有顺利跑完；success 表示流程结束且结果已落盘，RUN_FAILED 表示本次已结束且需要排查。",
        },
    ]


def build_report_guide_rows(result: dict) -> list[dict]:
    verdict = result.get("final_readiness_verdict") or {}
    recommended_output = str(verdict.get("recommended_output") or "").strip()
    recommended_label = VERSION_EXPLANATIONS.get(recommended_output, "最终推荐版")
    rows: list[dict] = []
    if result.get("listing_ready_path"):
        rows.append(
            {
                "报告": "LISTING_READY.md",
                "对应版本": f"最终推荐版（当前为 {recommended_output or '-'}）",
                "用途": "这是可直接给运营或贴到亚马逊后台的最终文案，不是排查底层逻辑用的技术文件。",
                "什么时候看": "当你要直接拿标题、五点、描述去上架时先看它。",
            }
        )
    if result.get("final_readiness_verdict_path"):
        rows.append(
            {
                "报告": "final_readiness_verdict.json",
                "对应版本": recommended_label,
                "用途": "这是最终裁决文件，不是文案本身；它负责说明系统最后推荐谁、为什么、卡在哪些门槛上。",
                "什么时候看": "当你想确认到底该上 hybrid 还是回退 version_a 时看它。",
            }
        )
    if result.get("dual_report_path"):
        rows.append(
            {
                "报告": "all_report_compare.md",
                "对应版本": "V3 基线版 + R1 Title/Bullets 实验版 + Hybrid 融合版",
                "用途": "这是三版本对比总览，适合横向比较标题、五点、评分和最终推荐逻辑。",
                "什么时候看": "当你要排查为什么推荐某个版本，或比较 3 个版本差异时看它。",
            }
        )
    return rows


def build_keyword_protocol_display_rows(result: dict, limit: int = 25) -> list[dict]:
    copy_payload = result.get("generated_copy") or {}
    decision_trace = copy_payload.get("decision_trace") or result.get("decision_trace") or {}
    assignments = decision_trace.get("keyword_assignments") or result.get("keyword_metadata") or []
    rows: list[dict] = []
    for item in assignments[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "keyword": item.get("keyword") or "-",
                "traffic_tier": item.get("traffic_tier") or item.get("tier") or "-",
                "quality_status": item.get("quality_status") or "-",
                "routing_role": item.get("routing_role") or "-",
                "opportunity_type": item.get("opportunity_type") or "-",
                "opportunity_score": item.get("opportunity_score", "-"),
                "blue_ocean_score": item.get("blue_ocean_score", "-"),
                "rejection_reason": item.get("rejection_reason") or "-",
                "assigned_fields": ", ".join(str(field) for field in item.get("assigned_fields") or []) or "-",
                "tier": item.get("tier") or "-",
            }
        )
    return rows


def build_worker_status_rows(result: dict) -> list[dict]:
    supervisor_summary = result.get("supervisor_summary") or (result.get("final_readiness_verdict") or {}).get("supervisor_summary") or {}
    workers = supervisor_summary.get("workers") or {}
    rows: list[dict] = []
    for worker_name in ("version_a", "version_b"):
        worker = workers.get(worker_name) or {}
        if not worker:
            continue
        stage = str(worker.get("current_stage") or "").strip()
        field = str(worker.get("current_field") or "").strip()
        current = " / ".join(part for part in [stage, field] if part) or "-"
        state = str(worker.get("state") or "-")
        reference_status = str(worker.get("reference_status") or "-")
        if worker_name == "version_a" and state == "success":
            operator_note = "主结果可用于最终裁决"
        elif worker_name == "version_b" and state in {"failed", "timed_out", "terminated"}:
            operator_note = "实验版无参考结果，不阻塞 version_a"
        elif worker_name == "version_b" and reference_status == "usable_candidate":
            operator_note = "实验版可参考，但不直接作为上架权威"
        else:
            operator_note = str(worker.get("reference_reason") or "-")
        rows.append(
            {
                "worker": worker_name,
                "state": state,
                "reference_status": reference_status,
                "current": current,
                "operator_note": operator_note,
            }
        )
    return rows


def _render_metadata(metadata: dict) -> None:
    if not metadata:
        st.info("暂无模型元数据")
        return
    cols = st.columns(4)
    cols[0].metric("Generation", metadata.get("generation_status", "unknown"))
    cols[1].metric("Configured Model", metadata.get("configured_model") or metadata.get("llm_model") or "-")
    cols[2].metric("Returned Model", metadata.get("returned_model") or "-")
    cols[3].metric("Request ID", (metadata.get("llm_request_id") or "-")[:18])
    st.caption(f"Provider: {metadata.get('llm_provider', '-')} | Wire API: {metadata.get('llm_wire_api', '-')}")


def _render_run_result(result: dict) -> None:
    display_state = build_result_display_state(result)
    risk_report = result.get("risk_report") or {}
    scoring_results = result.get("scoring_results") or {}
    evidence_summary = result.get("evidence_summary") or {}
    compute_tier_summary = result.get("compute_tier_summary") or {}
    final_verdict = result.get("final_readiness_verdict") or {}
    launch_gate = final_verdict.get("launch_gate") or {}
    listing_status = display_state["listing_status"]
    total_score = display_state["total_score"]
    grade = display_state["grade"]
    blocking_reasons = display_state["blocking_reasons"]

    summary_rows = build_result_summary_rows(result)
    score_rows = build_score_explanation_rows(result)
    report_guide_rows = build_report_guide_rows(result)

    st.markdown("### 一眼看懂这次结果")
    st.table(pd.DataFrame(summary_rows))
    if launch_gate:
        gate_status = "通过" if launch_gate.get("passed") else "未通过"
        st.caption(f"Hybrid Launch Gate：{gate_status}。如果未通过，系统会保守回退到更稳的版本。")
    if score_rows:
        st.markdown("### 四维评分怎么解读")
        st.table(pd.DataFrame(score_rows))
    if report_guide_rows:
        st.markdown("### 这 3 份报告分别看什么")
        st.table(pd.DataFrame(report_guide_rows))
    keyword_protocol_rows = build_keyword_protocol_display_rows(result)
    if keyword_protocol_rows:
        st.markdown("### Keyword Protocol Decisions")
        st.dataframe(pd.DataFrame(keyword_protocol_rows), use_container_width=True)
    worker_status_rows = build_worker_status_rows(result)
    if worker_status_rows:
        st.markdown("### Dual-Version Worker Status")
        st.table(pd.DataFrame(worker_status_rows))

    top = st.columns(4)
    top[0].metric("推荐版本", display_state["recommended_output"])
    top[1].metric("上线状态", listing_status)
    top[2].metric("综合分", total_score if total_score is not None else "-")
    top[3].metric("等级", grade)
    intent_weight_summary = result.get("intent_weight_summary") or {}
    if intent_weight_summary:
        st.caption(
            "Intent Weight Updates: "
            f"{intent_weight_summary.get('updated_keyword_count', 0)} | "
            f"{', '.join(intent_weight_summary.get('top_promoted_keywords', [])[:3]) or 'n/a'} | "
            f"Themes: {', '.join(intent_weight_summary.get('top_external_themes', [])[:2]) or 'n/a'} | "
            f"Channels: {', '.join(intent_weight_summary.get('channels', [])[:2]) or 'n/a'}"
        )
    if evidence_summary or compute_tier_summary:
        summary_cols = st.columns(3)
        summary_cols[0].metric("Unsupported Claims", evidence_summary.get("unsupported_claim_count", 0))
        summary_cols[1].metric("Fallback Fields", compute_tier_summary.get("fallback_field_count", 0))
        summary_cols[2].metric("Intent Weight Updates", intent_weight_summary.get("updated_keyword_count", 0))
    checklist = result.get("prelaunch_checklist") or {}
    iteration_panel = result.get("thirty_day_iteration_panel") or {}
    if checklist:
        checklist_cols = st.columns(3)
        checklist_cols[0].metric("Checklist Blocking", checklist.get("blocking_count", 0))
        checklist_cols[1].metric("Checklist Warn", checklist.get("warn_count", 0))
        checklist_cols[2].metric("Checklist Pass", checklist.get("pass_count", 0))

    _render_metadata(result.get("metadata") or {})
    st.write(f"Run Dir: `{result.get('run_dir', '-')}`")
    st.write(f"Primary Report Path: `{display_state['primary_report_path'] or '-'}`")
    if display_state["final_readiness_verdict_path"]:
        st.write(f"Final Verdict Path: `{display_state['final_readiness_verdict_path']}`")
    if display_state["listing_ready_path"]:
        st.write(f"Listing Ready Path: `{display_state['listing_ready_path']}`")
    failure_notice = summarize_run_failure(result)
    if failure_notice:
        st.error(failure_notice["headline"])
        st.info(failure_notice["detail"])
    if blocking_reasons:
        st.warning("阻断原因：" + " / ".join(str(item) for item in blocking_reasons))
    if launch_gate:
        st.caption(
            "Launch Gate: "
            f"{'passed' if launch_gate.get('passed') else 'failed'} | "
            f"A10 {((launch_gate.get('scores') or {}).get('A10', 0))} / "
            f"COSMO {((launch_gate.get('scores') or {}).get('COSMO', 0))} / "
            f"Rufus {((launch_gate.get('scores') or {}).get('Rufus', 0))} / "
            f"Fluency {((launch_gate.get('scores') or {}).get('Fluency', 0))}"
        )

    report_text = result.get("report_text") or ""
    dual_report_text = result.get("dual_report_text") or ""
    dual_version = result.get("dual_version") or {}
    listing_ready_path = result.get("listing_ready_path") or ""
    final_verdict_path = result.get("final_readiness_verdict_path") or ""
    if listing_ready_path and Path(listing_ready_path).exists():
        st.download_button(
            "📥 下载最终文案（可直接贴后台）",
            data=Path(listing_ready_path).read_text(encoding="utf-8"),
            file_name=Path(listing_ready_path).name,
            mime="text/markdown",
            use_container_width=True,
        )
    if final_verdict_path and Path(final_verdict_path).exists():
        st.download_button(
            "📥 下载最终判定说明",
            data=Path(final_verdict_path).read_text(encoding="utf-8"),
            file_name=Path(final_verdict_path).name,
            mime="application/json",
            use_container_width=True,
        )
    if report_text:
        st.download_button(
            "📥 下载报告",
            data=report_text,
            file_name=Path(result.get("report_path") or "listing_report.md").name,
            mime="text/markdown",
            use_container_width=True,
        )
        st.markdown(report_text)
    if dual_report_text:
        st.info("已生成三版本对比报告：V3 基线版、R1 Title/Bullets 实验版、Hybrid 融合版。排查差异时先看它。")
        st.download_button(
            "📥 下载三版本对比报告",
            data=dual_report_text,
            file_name=Path(result.get("dual_report_path") or "all_report_compare.md").name,
            mime="text/markdown",
            use_container_width=True,
        )
        with st.expander("查看三版本对比详情"):
            st.markdown(dual_report_text)
    if dual_version:
        st.caption(
            "Dual-Version: "
            f"Version A = {((dual_version.get('version_a') or {}).get('generation_status') or '-')}, "
            f"Version B = {((dual_version.get('version_b') or {}).get('generation_status') or '-')}"
        )
    if result.get("hybrid"):
        st.caption(
            "Hybrid: "
            f"{(((result.get('hybrid') or {}).get('generated_copy') or {}).get('metadata') or {}).get('hybrid_generation_status', '-')}"
        )
    if result.get("logs"):
        with st.expander("执行日志"):
            st.code(result["logs"])
    if checklist:
        with st.expander("Pre-Launch Checklist"):
            st.json(checklist)
    if iteration_panel:
        with st.expander("30-Day Iteration Panel"):
            st.json(iteration_panel)
    with st.expander("系统过程数据"):
        st.json(
            {
                "execution_summary": result.get("execution_summary") or {},
                "risk_report": risk_report,
                "scoring_results": scoring_results,
                "evidence_summary": evidence_summary,
                "compute_tier_summary": compute_tier_summary,
                "intent_weight_summary": intent_weight_summary,
                "prelaunch_checklist": checklist,
                "thirty_day_iteration_panel": iteration_panel,
                "snapshots": result.get("snapshots") or {},
                "final_readiness_verdict": final_verdict,
            }
        )


def _render_history_copy(copy_payload: dict) -> None:
    st.markdown("**Title**")
    st.write(copy_payload.get("title") or "-")
    st.markdown("**Bullets**")
    bullets = copy_payload.get("bullets") or []
    for idx, bullet in enumerate(bullets, start=1):
        st.write(f"B{idx}. {bullet}")
    st.markdown("**Description**")
    st.write(copy_payload.get("description") or "-")
    st.markdown("**Search Terms**")
    search_terms = copy_payload.get("search_terms") or []
    if isinstance(search_terms, list):
        st.write(", ".join(search_terms) or "-")
    else:
        st.write(search_terms or "-")


def _render_history_scoring(scoring_results: dict, scores: dict) -> None:
    score_cols = st.columns(4)
    score_cols[0].metric("A10", scores.get("A10", 0))
    score_cols[1].metric("COSMO", scores.get("COSMO", 0))
    score_cols[2].metric("Rufus", scores.get("Rufus", 0))
    score_cols[3].metric("Fluency", scores.get("Fluency", 0))
    st.markdown("**Score Breakdown**")
    st.json(scoring_results or {})


def render_history_tab() -> None:
    st.subheader("历史报告")
    workspaces = list_workspaces()
    if not workspaces:
        st.info("还没有产品工作区，请先在“新品上架”中创建。")
        return

    workspace_options = [f"{item['product_code']}_{item['site']}" for item in workspaces]
    workspace_recency = []
    for item in workspaces:
        runs = list_workspace_runs(item["workspace_dir"])
        workspace_recency.append(runs[0]["created_at"] if runs else "")
    default_index = max(range(len(workspaces)), key=lambda idx: workspace_recency[idx] or "")

    selected_name = st.selectbox("选择 workspace", workspace_options, index=default_index, key="history_workspace")
    selected = workspaces[workspace_options.index(selected_name)]
    runs = list_workspace_runs(selected["workspace_dir"])

    if not runs:
        st.info("该 workspace 暂无历史 runs。")
        return

    for run in runs:
        label = (
            f"{run['created_at']} | {run['run_id']} | "
            f"{run.get('generation_status') or '-'} | {run.get('listing_status') or '-'}"
        )
        with st.expander(label, expanded=False):
            summary_cols = st.columns(7)
            summary_cols[0].metric("Generation", run.get("generation_status") or "-")
            summary_cols[1].metric("Listing", run.get("listing_status") or "-")
            summary_cols[2].metric("Recommended", run.get("recommended_output") or "-")
            summary_cols[3].metric("A10", (run.get("scores") or {}).get("A10", 0))
            summary_cols[4].metric("COSMO", (run.get("scores") or {}).get("COSMO", 0))
            summary_cols[5].metric("Rufus", (run.get("scores") or {}).get("Rufus", 0))
            summary_cols[6].metric("Fluency", (run.get("scores") or {}).get("Fluency", 0))
            st.caption(f"Run Dir: `{run.get('run_dir')}`")

            if run.get("is_dual_version"):
                col_a, col_b, col_h = st.columns(3)
                with col_a:
                    st.markdown("### Version A")
                    _render_history_copy((run.get("version_a") or {}).get("generated_copy") or {})
                    _render_history_scoring(
                        (run.get("version_a") or {}).get("scoring_results") or {},
                        (run.get("version_a") or {}).get("scores") or {},
                    )
                with col_b:
                    st.markdown("### Version B")
                    _render_history_copy((run.get("version_b") or {}).get("generated_copy") or {})
                    _render_history_scoring(
                        (run.get("version_b") or {}).get("scoring_results") or {},
                        (run.get("version_b") or {}).get("scores") or {},
                    )
                with col_h:
                    st.markdown("### Hybrid")
                    _render_history_copy((run.get("hybrid") or {}).get("generated_copy") or {})
                    _render_history_scoring(
                        (run.get("hybrid") or {}).get("scoring_results") or {},
                        (run.get("hybrid") or {}).get("scores") or {},
                    )
            else:
                _render_history_copy(run.get("generated_copy") or {})
                _render_history_scoring(run.get("scoring_results") or {}, run.get("scores") or {})

            st.markdown("**报告入口**")
            if run.get("report_text"):
                with st.expander("listing_report.md", expanded=False):
                    st.markdown(run["report_text"])
            if run.get("readiness_summary_text"):
                with st.expander("readiness_summary.md", expanded=False):
                    st.markdown(run["readiness_summary_text"])
            if run.get("dual_report_text"):
                with st.expander("all_report_compare.md", expanded=False):
                    st.markdown(run["dual_report_text"])
            if run.get("final_readiness_verdict"):
                with st.expander("final_readiness_verdict.json", expanded=False):
                    st.json(run["final_readiness_verdict"])
            if run.get("listing_ready_text"):
                with st.expander("LISTING_READY.md", expanded=False):
                    st.markdown(run["listing_ready_text"])


def render_new_product_tab() -> None:
    st.subheader("新品上架")
    with st.form("new_product_form"):
        col1, col2, col3 = st.columns(3)
        site = col1.selectbox("目标国家", ["US", "DE", "FR", "IT", "ES", "JP"], index=0)
        brand_name = col2.text_input("品牌名称", value="TOSBARRFT")
        historical_product_codes = list_product_code_options(site)
        product_code_options = historical_product_codes + [MANUAL_PRODUCT_CODE_OPTION]
        default_product_code_index = 0 if historical_product_codes else len(product_code_options) - 1
        selected_product_code = col3.selectbox(
            "内部产品代号",
            product_code_options,
            index=default_product_code_index,
            format_func=lambda value: "手动输入新代号" if value == MANUAL_PRODUCT_CODE_OPTION else value,
            help="优先复用历史产品代号，避免因为手误创建新的历史产品名称。",
        )
        product_code = selected_product_code
        if selected_product_code == MANUAL_PRODUCT_CODE_OPTION:
            product_code = col3.text_input("新的内部产品代号", value="")
        attribute_table = st.file_uploader("属性表", type=["txt", "csv", "xlsx"], key="attr")
        keyword_table = st.file_uploader("关键词表", type=["csv", "xlsx"], key="kw")
        aba_merged = st.file_uploader("ABA 表", type=["csv", "xlsx"], key="aba")
        review_table = st.file_uploader("Review 全维表", type=["csv", "xlsx", "txt"], key="review")
        manual_notes = st.text_area("产品特性描述/补充说明", height=160)
        st.caption(
            "推荐输入格式：\n"
            "【产品卖点】\n"
            "- 不防抖，无夜视，拇指相机，小巧便携，支持Wi-Fi模式\n\n"
            "【本链接包含配件】\n"
            "- 防水壳\n"
            "- 自行车支架\n"
            "- 头盔支架\n\n"
            "【存储卡】\n"
            "- 64GB\n\n"
            "【备注】\n"
            "- 4K模式120分钟"
        )
        dual_version = st.checkbox("同时输出 R1 Title/Bullets 实验版（耗时更长）", value=False)
        st.caption("实验版会使用 R1 生成 Blueprint、Title 和 5 条 Bullets，其余字段仍走当前 V3 主链路。")
        submitted = st.form_submit_button("🚀 初始化并生成 Listing", use_container_width=True)

    if not submitted:
        return

    if not all([attribute_table, keyword_table, aba_merged, review_table, product_code.strip()]):
        st.error("请完整上传 4 张核心表并填写产品代号")
        return

    workspace = initialize_workspace(
        product_code=product_code,
        site=site,
        brand_name=brand_name,
        files={
            "attribute_table": attribute_table,
            "keyword_table": keyword_table,
            "aba_merged": aba_merged,
            "review_table": review_table,
        },
        manual_notes=manual_notes,
    )
    with st.spinner("正在运行 workflow，请稍候..."):
        result = run_workspace_workflow(
            workspace["run_config_path"],
            workspace["workspace_dir"],
            steps=DEFAULT_STEPS,
            dual_version=dual_version,
        )

    st.success(f"工作区已创建：{workspace['workspace_dir']}")
    if workspace.get("llm_alignment_warning"):
        st.warning(workspace["llm_alignment_warning"])
    _render_run_result(result)


def render_feedback_tab() -> None:
    st.subheader("老品数据反补")
    workspaces = list_workspaces()
    if not workspaces:
        st.info("还没有产品工作区，请先在“新品上架”中创建。")
        return
    workspace_names = [f"{item['product_code']}_{item['site']}" for item in workspaces]
    selected_name = st.selectbox("选择老产品", workspace_names)
    selected = workspaces[workspace_names.index(selected_name)]

    uploaded = st.file_uploader("上传 SellerSprite / PPC 词表", type=["csv", "xlsx"], key="feedback_upload")
    uploaded_intent = st.file_uploader("上传 PPC / Search Term / CTR-CVR / 外部主题权重表", type=["csv", "xlsx"], key="intent_weight_upload")
    operator_notes = st.text_area("运营备注", height=120, key="feedback_notes")
    if not uploaded and not uploaded_intent:
        return

    if uploaded:
        feedback_input_path = Path(selected["workspace_dir"]) / "feedback" / uploaded.name
        feedback_input_path.write_bytes(uploaded.getvalue())
        parsed = parse_keyword_feedback_table(str(feedback_input_path))
        df = pd.DataFrame(parsed["rows"])
        summary = parsed.get("summary") or {}
        summary_cols = st.columns(4)
        summary_cols[0].metric("解析词数", len(parsed["rows"]))
        summary_cols[1].metric("Organic", summary.get("organic_count", summary.get("organic", 0)))
        summary_cols[2].metric("SP", summary.get("sp_count", summary.get("sp", 0)))
        summary_cols[3].metric("风险词", summary.get("flagged_count", summary.get("blocked", 0)))
        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "keep": st.column_config.CheckboxColumn("保留", default=True),
                "keyword": st.column_config.TextColumn("关键词", disabled=True),
                "source": st.column_config.TextColumn("流量来源", disabled=True),
                "search_volume": st.column_config.NumberColumn("搜索量", disabled=True),
                "conversion": st.column_config.NumberColumn("转化率", disabled=True),
                "suggested_slot": st.column_config.TextColumn("系统建议去向", disabled=True),
                "risk_flag": st.column_config.TextColumn("风险标记", disabled=True),
                "reason": st.column_config.TextColumn("说明", disabled=True),
            },
            key="feedback_editor",
        )

        col1, col2 = st.columns(2)
        save_clicked = col1.button("💾 保存反馈快照", use_container_width=True)
        rebuild_clicked = col2.button("🔄 确认选词并重构 Listing", use_container_width=True)

        if save_clicked or rebuild_clicked:
            snapshot_path = save_feedback_snapshot(
                workspace_dir=selected["workspace_dir"],
                source_file=str(feedback_input_path),
                rows=edited.to_dict(orient="records"),
                product_code=selected["product_code"],
                site=selected["site"],
                operator_notes=operator_notes,
            )
            st.success(f"反馈快照已保存：{snapshot_path}")
            attach_feedback_snapshot(selected["run_config_path"], snapshot_path)

            if rebuild_clicked:
                with st.spinner("正在基于反馈词表重构 Listing..."):
                    result = run_workspace_workflow(selected["run_config_path"], selected["workspace_dir"], steps=DEFAULT_STEPS)
                _render_run_result(result)

    if uploaded_intent:
        intent_input_path = Path(selected["workspace_dir"]) / "intent_weights" / uploaded_intent.name
        intent_input_path.parent.mkdir(parents=True, exist_ok=True)
        intent_input_path.write_bytes(uploaded_intent.getvalue())
        if uploaded_intent.name.lower().endswith(".csv"):
            intent_df = pd.read_csv(intent_input_path)
        else:
            intent_df = pd.read_excel(intent_input_path)
        st.dataframe(intent_df, use_container_width=True)
        if st.button("📈 保存意图权重快照并重构 Listing", use_container_width=True):
            snapshot_path = save_intent_weight_snapshot(
                workspace_dir=selected["workspace_dir"],
                rows=intent_df.to_dict(orient="records"),
                product_code=selected["product_code"],
                site=selected["site"],
                source_file=str(intent_input_path),
            )
            st.success(f"意图权重快照已保存：{snapshot_path}")
            attach_intent_weight_snapshot(selected["run_config_path"], snapshot_path)
            with st.spinner("正在基于意图权重重构 Listing..."):
                result = run_workspace_workflow(selected["run_config_path"], selected["workspace_dir"], steps=DEFAULT_STEPS)
            _render_run_result(result)


def main() -> None:
    st.set_page_config(page_title="Amazon Listing Control Console", layout="wide")
    st.title("Amazon Listing 自动化与数据反补控制台")
    tab1, tab2, tab3 = st.tabs(["新品上架", "老品数据反补", "历史报告"])
    with tab1:
        render_new_product_tab()
    with tab2:
        render_feedback_tab()
    with tab3:
        render_history_tab()


if __name__ == "__main__":
    main()
