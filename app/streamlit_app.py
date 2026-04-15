#!/usr/bin/env python3
"""Local Streamlit control console for new listing runs and feedback-loop rebuilds."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.services.run_service import run_workspace_workflow
from app.services.workspace_service import (
    attach_feedback_snapshot,
    attach_intent_weight_snapshot,
    initialize_workspace,
    list_workspaces,
)
from modules.csv_parser import parse_keyword_feedback_table
from modules.feedback_loop import save_feedback_snapshot
from modules.intent_weights import save_intent_weight_snapshot

DEFAULT_STEPS = [0, 2, 4, 5, 6, 7, 8, 9]


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
    risk_report = result.get("risk_report") or {}
    scoring_results = result.get("scoring_results") or {}
    evidence_summary = result.get("evidence_summary") or {}
    compute_tier_summary = result.get("compute_tier_summary") or {}
    listing_status = (risk_report.get("listing_status") or {}).get("status") or result.get("status") or "-"
    total_score = scoring_results.get("total_score")
    grade = scoring_results.get("grade") or "-"
    blocking_reasons = (risk_report.get("listing_status") or {}).get("blocking_reasons") or scoring_results.get("blocking_reasons") or []

    top = st.columns(4)
    top[0].metric("Listing Status", listing_status)
    top[1].metric("Total Score", total_score if total_score is not None else "-")
    top[2].metric("Grade", grade)
    top[3].metric("Run Status", result.get("status") or "-")
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
    st.write(f"Report Path: `{result.get('report_path', '-')}`")
    if blocking_reasons:
        st.warning("阻断原因：" + " / ".join(str(item) for item in blocking_reasons))

    report_text = result.get("report_text") or ""
    if report_text:
        st.download_button(
            "📥 下载报告",
            data=report_text,
            file_name=Path(result.get("report_path") or "listing_report.md").name,
            mime="text/markdown",
            use_container_width=True,
        )
        st.markdown(report_text)
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
            }
        )


def render_new_product_tab() -> None:
    st.subheader("新品上架")
    with st.form("new_product_form"):
        col1, col2, col3 = st.columns(3)
        site = col1.selectbox("目标国家", ["US", "DE", "FR", "IT", "ES", "JP"], index=0)
        brand_name = col2.text_input("品牌名称", value="TOSBARRFT")
        product_code = col3.text_input("内部产品代号", value="T70")
        attribute_table = st.file_uploader("属性表", type=["txt", "csv", "xlsx"], key="attr")
        keyword_table = st.file_uploader("关键词表", type=["csv", "xlsx"], key="kw")
        aba_merged = st.file_uploader("ABA 表", type=["csv", "xlsx"], key="aba")
        review_table = st.file_uploader("Review 全维表", type=["csv", "xlsx", "txt"], key="review")
        manual_notes = st.text_area("产品特性描述/补充说明", height=160)
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
        result = run_workspace_workflow(workspace["run_config_path"], workspace["workspace_dir"], steps=DEFAULT_STEPS)

    st.success(f"工作区已创建：{workspace['workspace_dir']}")
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
    tab1, tab2 = st.tabs(["新品上架", "老品数据反补"])
    with tab1:
        render_new_product_tab()
    with tab2:
        render_feedback_tab()


if __name__ == "__main__":
    main()
