#!/usr/bin/env python3
"""Node 8 - 最终仲裁报告生成器"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Sequence


def _safe_get(obj: Any, *attrs, default=None):
    current = obj
    for attr in attrs:
        if current is None:
            return default
        current = getattr(current, attr, None)
    return current if current is not None else default


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        rows = [["-" for _ in headers]]
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def _extract_keyword_tiers(preprocessed_data: Any) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    keywords = _safe_get(preprocessed_data, "keyword_data", "keywords", default=[]) or []
    for row in keywords:
        keyword = row.get("keyword") or row.get("search_term")
        if not keyword:
            continue
        try:
            volume = float(row.get("search_volume", 0))
        except (TypeError, ValueError):
            volume = 0
        if volume >= 10000:
            tier = "L1"
        elif volume >= 1000:
            tier = "L2"
        else:
            tier = "L3"
        mapping[keyword] = tier
    return mapping


def _keyword_locations(keyword: str, generated_copy: Dict[str, Any]) -> str:
    locations = []
    if not keyword:
        return "-"
    keyword_lower = keyword.lower()
    if keyword_lower in generated_copy.get("title", "").lower():
        locations.append("Title")
    for idx, bullet in enumerate(generated_copy.get("bullets", []) or [], 1):
        if keyword_lower in bullet.lower():
            locations.append(f"B{idx}")
    if keyword_lower in generated_copy.get("description", "").lower():
            locations.append("Description")
    st_text = " ".join(generated_copy.get("search_terms", []) or [])
    if keyword_lower in st_text.lower():
        locations.append("Search Terms")
    if not locations:
        locations.append("未覆盖")
    return "、".join(locations)


def _keyword_coverage_rows(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> List[List[str]]:
    mapping = _extract_keyword_tiers(preprocessed_data)
    rows: List[List[str]] = []
    for keyword, tier in list(mapping.items())[:12]:
        rows.append([keyword, tier, _keyword_locations(keyword, generated_copy)])
    if not rows:
        rows.append(["样例关键词", "L2", "Search Terms"])
    return rows


def _compliance_section(risk_report: Dict[str, Any]) -> str:
    compliance = (risk_report or {}).get("compliance", {})
    passed = compliance.get("passed", 0)
    total = compliance.get("total", 0)
    issues = compliance.get("issues", [])
    lines = [f"- 通过情况：{passed}/{total}", f"- 风险条目：{len(issues)}"]
    if issues:
        for issue in issues[:5]:
            lines.append(f"  - [{issue.get('severity', 'n/a')}] {issue.get('description', '未知')} ({issue.get('pattern', '-')})")
    else:
        lines.append("  - 未检测到违规词。")
    return "\n".join(lines)


def _policy_audit_section(risk_report: Dict[str, Any]) -> str:
    audit = (risk_report or {}).get("policy_audit", {})
    passed = audit.get("passed", 0)
    total = audit.get("total", 0)
    issues = audit.get("issues", [])
    lines = [f"- 约束通过：{passed}/{total}", f"- 未通过条目：{len(issues)}"]
    if issues:
        for issue in issues[:6]:
            lines.append(f"  - {issue.get('rule', '规则')}: {issue.get('description', '未提供描述')}")
    else:
        lines.append("  - 六条硬性约束均满足。")
    return "\n".join(lines)


def _competitor_diff_points(preprocessed_data: Any) -> List[str]:
    attr_data = _safe_get(preprocessed_data, "attribute_data", "data", default={}) or {}
    selling_points = getattr(preprocessed_data, "core_selling_points", []) or []
    notes: List[str] = []
    if attr_data.get("waterproof_depth"):
        notes.append(f"- 水下场景：强调 {attr_data['waterproof_depth']} 防水，与竞品 10m 方案区分。")
    if attr_data.get("image_stabilization"):
        notes.append(f"- 防抖表现：突出 {attr_data['image_stabilization']} 在高速运动中的稳定性。")
    if attr_data.get("battery_life"):
        notes.append(f"- 续航里程：对比竞品 90 分钟，给出 {attr_data['battery_life']} 实测场景。")
    for point in selling_points[:3]:
        notes.append(f"- 核心卖点「{point}」结合参数输出差异化故事。")
    if not notes:
        notes.append("- 属性与卖点信息不足，需补充竞品差异化素材。")
    return notes[:5]


def _stag_rows(writing_policy: Dict[str, Any], generated_copy: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    scenes = writing_policy.get("scene_priority", []) or []
    search_terms = generated_copy.get("search_terms", []) or []

    # 场景到目标人群的映射
    scene_to_audience = {
        "骑行记录": "骑行爱好者25-45岁，通勤族，户外运动达人",
        "户外运动": "户外运动爱好者20-40岁，登山、滑雪、徒步爱好者",
        "水下探索": "潜水爱好者25-50岁，水上运动爱好者，海洋摄影师",
        "旅行记录": "旅行爱好者22-55岁，背包客，旅游博主，家庭出游",
        "运动训练": "健身爱好者18-35岁，运动员，体育教练，训练记录者",
        "家庭使用": "家庭用户25-45岁，宠物主人，亲子家庭，生活记录者",
        "骑行": "骑行爱好者25-45岁，自行车通勤者，户外运动爱好者",
        "滑雪": "滑雪爱好者20-40岁，冬季运动爱好者，极限运动玩家",
        "登山": "登山爱好者25-50岁，徒步旅行者，户外探险家",
        "潜水": "潜水爱好者25-50岁，水下摄影师，海洋探索者",
        "旅行": "旅行爱好者22-55岁，背包客，旅游达人，度假家庭",
        "运动": "运动爱好者18-40岁，健身人群，运动员，体育爱好者",
        "家庭": "家庭用户25-45岁，父母，宠物主人，家庭活动记录者",
        "宠物": "宠物主人20-50岁，宠物爱好者，动物记录者",
        "儿童": "父母25-40岁，家庭用户，儿童成长记录者"
    }

    for scene in scenes[:5]:
        linked_terms = [kw for kw in search_terms if kw.lower().startswith(scene[:2].lower())][:2]
        if not linked_terms:
            linked_terms = search_terms[:2]

        # 获取目标人群描述，如果找不到则使用通用描述
        audience = scene_to_audience.get(scene)
        if not audience:
            # 尝试部分匹配
            for key, value in scene_to_audience.items():
                if key in scene:
                    audience = value
                    break
            if not audience:
                audience = f"目标人群：{scene or '泛用'}爱好者20-45岁"
        else:
            audience = f"目标人群：{audience}"

        rows.append([
            scene or "—",
            "、".join(linked_terms) if linked_terms else "—",
            audience,
            f"建议：围绕{scene or '该'}场景组合 SB/SP 广告，融入高转化词。"
        ])
    if not rows:
        rows.append(["未定义", "—", "—", "缺少 STAG 数据"])
    return rows


def _rufus_seed_rows(preprocessed_data: Any, generated_copy: Dict[str, Any]) -> List[List[str]]:
    rows: List[List[str]] = []
    review_insights = _safe_get(preprocessed_data, "review_data", "insights", default=[]) or []
    faq = generated_copy.get("faq", []) or []
    source_pairs = []
    for insight in review_insights[:3]:
        question = f"用户担忧：{insight.get('field_name', 'Pain Point')}"
        answer = insight.get("content_text", "")[:80] or "需要补充洞察。"
        source_pairs.append((question, answer))
    for item in faq[:3]:
        source_pairs.append((item.get("q", "FAQ"), item.get("a", "")[:80]))
    for idx, (question, answer) in enumerate(source_pairs[:5], 1):
        rows.append([str(idx), question, answer])
    if not rows:
        rows.append(["1", "暂无历史问答", "需补充全维度表数据。"])
    return rows


def _scoring_tables(scoring_results: Dict[str, Any]) -> str:
    if not scoring_results:
        return "评分数据缺失，模块 8 无法生成。"

    sections: List[str] = []
    for block_key, title in (("a10", "A10 维度"), ("cosmo", "COSMO 维度"), ("rufus", "Rufus 维度")):
        block = scoring_results.get(block_key, {})
        rows = []
        for metric_key, metric in block.items():
            if metric_key == "subtotal":
                continue
            rows.append([
                metric_key,
                str(metric.get("max", "-")),
                str(metric.get("score", "-")),
                metric.get("note", "-")
            ])
        sections.append(f"### {title}\n" + _markdown_table(["指标", "满分", "得分", "说明"], rows))
        sections.append(f"> 小计：{block.get('subtotal', 0)} 分")

    price = scoring_results.get("price_competitiveness", {})
    price_rows = [[
        str(price.get("price_median", "—")),
        str(price.get("current_price", "—")),
        price.get("range", "—"),
        str(price.get("score")) if price.get("score") is not None else "—"
    ]]
    sections.append("### 价格竞争力\n" + _markdown_table(["品类中位价", "当前定价", "区间判断", "得分"], price_rows))
    sections.append(f"- 数据可用: {'是' if price.get('data_available') else '否'}\n- 说明: {price.get('note', '—')}")

    boundary = scoring_results.get("boundary_declaration_check", {})
    aplus = scoring_results.get("aplus_word_count_check", {})
    sections.append(
        "### 规则附加检查\n"
        f"- 边界声明: {'已检测' if boundary.get('exists') else '缺失'} → {boundary.get('sentence', '未找到句子')}\n"
        f"- A+ 字数: {aplus.get('word_count', 0)} 词，满足下限: {aplus.get('meets_minimum', False)}"
    )

    sections.append(
        "### 算法对齐摘要\n"
        f"- 总分: {scoring_results.get('total_score', 0)}/{scoring_results.get('max_total', 310)}\n"
        f"- 综合评级: {scoring_results.get('rating', 'N/A')} ({scoring_results.get('grade_percent', 0)}%)"
    )

    return "\n\n".join(sections)


def generate_report(
    preprocessed_data: Any,
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    risk_report: Dict[str, Any],
    scoring_results: Dict[str, Any],
    language: str
) -> str:
    brand = _safe_get(preprocessed_data, "run_config", "brand_name", default="TOSBARRFT")
    site = _safe_get(preprocessed_data, "run_config", "target_country", default="-")
    processed_at = getattr(preprocessed_data, "processed_at", datetime.utcnow().isoformat())
    listing_lang = language or getattr(preprocessed_data, "language", "English")

    lines: List[str] = []
    lines.append("# Amazon Listing 最终仲裁报告")
    lines.append(f"- 生成时间：{processed_at}")
    lines.append(f"- 站点：{site}")
    lines.append(f"- 品牌：{brand}")
    lines.append(f"- Listing 语言：{listing_lang}")
    lines.append("")

    lines.append("## Module 1：最终 Listing（目标语言输出）")
    lines.append("**Title**")
    lines.append(generated_copy.get("title", "N/A"))
    lines.append("")
    lines.append("**Bullets**")
    for idx, bullet in enumerate(generated_copy.get("bullets", []) or [], 1):
        lines.append(f"{idx}. {bullet}")
    lines.append("")
    lines.append("**Description**")
    lines.append(generated_copy.get("description", "N/A"))
    lines.append("")
    lines.append("**FAQ**")
    for item in generated_copy.get("faq", []) or []:
        lines.append(f"- Q: {item.get('q', '')}")
        lines.append(f"  A: {item.get('a', '')}")
    lines.append("")
    lines.append("**Search Terms**")
    lines.append(", ".join(generated_copy.get("search_terms", []) or []))
    lines.append("")
    lines.append("**A+ Content**")
    lines.append(generated_copy.get("aplus_content", "N/A"))
    lines.append("")

    lines.append("## Module 2：关键词覆盖审计表")
    lines.append(_markdown_table(["关键词", "层级", "出现位置"], _keyword_coverage_rows(preprocessed_data, generated_copy)))
    lines.append("")

    lines.append("## Module 3：合规红线检查")
    lines.append(_compliance_section(risk_report))
    lines.append("")

    lines.append("## Module 4：writing_policy 执行审计")
    lines.append(_policy_audit_section(risk_report))
    lines.append("")

    lines.append("## Module 5：竞品差异化分析")
    lines.extend(_competitor_diff_points(preprocessed_data))
    lines.append("")

    lines.append("## Module 6：STAG 广告投放建议")
    lines.append(_markdown_table(["STAG 场景", "优先关键词", "目标人群", "投放建议"], _stag_rows(writing_policy, generated_copy)))
    lines.append("")

    lines.append("## Module 7：Rufus Q&A 种子列表")
    lines.append(_markdown_table(["序号", "问题种子", "答案要点"], _rufus_seed_rows(preprocessed_data, generated_copy)))
    lines.append("")

    lines.append("## Module 8：算法对齐评分 & 摘要")
    lines.append(_scoring_tables(scoring_results))
    lines.append("")

    return "\n".join(lines)


__all__ = ["generate_report"]
