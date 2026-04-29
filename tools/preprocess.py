#!/usr/bin/env python3
"""
Amazon Listing Generator - 数据预处理模块
版本: v1.1
功能: 执行Step 0数据预处理与填槽字段解析
"""

import json
import csv
import re
import os
import sys
import io
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from tools.data_loader import load_table
from modules.language_utils import (
    _normalize_to_canonical_english,
    canonicalize_capability,
    english_capability_label,
    get_accessory_experience,
    get_accessory_experience_key,
)
from modules.entity_profile import build_entity_profile
from modules.intent_weights import load_intent_weight_snapshot
from modules.canonical_facts import build_canonical_facts, summarize_fact_readiness


# ==================== 常量定义 ====================

# 口语化模式库 - 核心卖点提取
SELLING_POINT_PATTERNS = {
    "双屏幕": [r'两[个]?屏幕', r'双屏[幕]?', r'前后屏', r'dual screen', r'dual-screen'],
    "防抖": [r'防抖(效果)?(很|非常)?(好|不错|强)', r'EIS防抖', r'image stabilization', r'防抖功能'],
    "WiFi连接": [r'Wi[-\s]?Fi[连接]?', r'无线[连接]?', r'手机[连]?接', r'WiFi connect', r'wireless'],
    "4K画质": [r'4K[视频]?', r'超高清', r'高清画质', r'4K video', r'UHD'],
    "长续航": [r'电池[续航]?(长|久)', r'续航[时间]?长', r'150分钟', r'long battery', r'battery life'],
    "轻便": [r'轻[便]?', r'小巧', r'便携', r'方便携带', r'lightweight', r'compact'],
    "防水": [r'防水', r'防泼溅', r'雨天可用', r'waterproof', r'water resistance'],
    "易操作": [r'容易[使用]?', r'简单[操作]?', r'一键[录制]?', r'easy to use', r'simple operation']
}

# 配件类型映射
ACCESSORY_TYPES = {
    "body camera": "主机",
    "back clip": "背夹",
    "card reader": "读卡器",
    "magnetic neck strap": "磁吸挂绳",
    "waterproof case": "防水壳",
    "data cable": "数据线",
    "user manual": "用户手册",
    "battery": "电池",
    "charging cable": "充电线",
    "mount": "支架"
}

# 国家语言映射
COUNTRY_LANGUAGE_MAP = {
    "US": "English",
    "UK": "English",
    "DE": "German",
    "FR": "French",
    "IT": "Italian",
    "ES": "Spanish",
    "JP": "Japanese",
    "CA": "English",
    "AU": "English"
}

# 默认品牌名称
DEFAULT_BRAND = "TOSBARRFT"

# 通用卖点（用于补充）
GENERIC_SELLING_POINTS = [
    "高清视频录制", "便携设计", "长续航电池",
    "易于操作", "多场景适用", "耐用材质", "快速充电"
]


# ==================== 数据类定义 ====================

@dataclass
class RunConfig:
    """运行配置"""
    target_country: str
    brand_name: str = DEFAULT_BRAND
    product_code: str = ""
    workspace_dir: str = ""
    core_selling_points_raw: str = ""
    accessory_params_raw: str = ""
    manual_notes: str = ""
    feedback_snapshot_path: str = ""
    intent_weight_snapshot_path: str = ""
    previous_snapshot_path: str = ""
    input_files: Optional[Dict[str, str]] = None
    llm: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'RunConfig':
        """从字典创建RunConfig"""
        return cls(
            target_country=config_dict.get("target_country", ""),
            brand_name=config_dict.get("brand_name", DEFAULT_BRAND),
            product_code=config_dict.get("product_code", ""),
            workspace_dir=config_dict.get("workspace_dir", ""),
            core_selling_points_raw=config_dict.get("core_selling_points_raw", ""),
            accessory_params_raw=config_dict.get("accessory_params_raw", ""),
            manual_notes=config_dict.get("manual_notes", ""),
            feedback_snapshot_path=config_dict.get("feedback_snapshot_path", ""),
            intent_weight_snapshot_path=config_dict.get("intent_weight_snapshot_path", ""),
            previous_snapshot_path=config_dict.get("previous_snapshot_path", ""),
            input_files=config_dict.get("input_files"),
            llm=config_dict.get("llm", {}) or {}
        )


@dataclass
class AttributeData:
    """属性表数据"""
    data: Dict[str, Any]
    source: str = "attribute_table"


@dataclass
class KeywordData:
    """关键词表数据"""
    keywords: List[Dict[str, Any]]
    source: str = "keyword_table"


@dataclass
class ReviewData:
    """评论表数据"""
    insights: List[Dict[str, Any]]
    source: str = "review_table"


@dataclass
class ABAData:
    """ABA趋势数据"""
    trends: List[Dict[str, Any]]
    source: str = "aba_merged"


@dataclass
class RealVocabData:
    """真实国家词表数据 (Priority 1 关键词来源)"""
    country: str                          # "DE" / "FR"
    is_available: bool = False           # 是否有真实词表
    total_count: int = 0                # 总关键词数
    aba_count: int = 0                  # ABA 关键词数
    order_winning_count: int = 0        # 出单词数
    template_count: int = 0             # 模板长尾词数量
    review_count: int = 0               # 评论抽取关键词数
    top_keywords: List[Dict[str, Any]] = field(default_factory=list)  # Top 20 高搜索量关键词（本地词）
    data_mode: str = "SYNTHETIC_COLD_START"  # 基于真实数据量判断


@dataclass
class PreprocessedData:
    """预处理后的完整数据"""
    run_config: RunConfig
    attribute_data: AttributeData
    keyword_data: KeywordData
    review_data: ReviewData
    aba_data: ABAData
    core_selling_points: List[str]
    accessory_descriptions: List[Dict[str, Any]]
    quality_score: int
    language: str  # target_language from COUNTRY_LANGUAGE_MAP
    target_country: str
    canonical_core_selling_points: List[str] = field(default_factory=list)
    canonical_accessory_descriptions: List[Dict[str, Any]] = field(default_factory=list)
    canonical_capability_notes: Dict[str, Any] = field(default_factory=dict)
    real_vocab: Optional[RealVocabData] = None  # 真实国家词表（Priority 1）
    reasoning_language: str = "EN"  # PRD v8.2: 固定为EN
    data_mode: str = "SYNTHETIC_COLD_START"  # DATA_DRIVEN or SYNTHETIC_COLD_START
    processed_at: str = ""
    capability_constraints: Dict[str, Any] = field(default_factory=dict)
    keyword_metadata: List[Dict[str, Any]] = field(default_factory=list)
    supplement_signals: Dict[str, Any] = field(default_factory=dict)
    data_alerts: List[str] = field(default_factory=list)
    raw_human_insights: str = ""
    ingestion_audit: Dict[str, Any] = field(default_factory=dict)
    feedback_context: Dict[str, Any] = field(default_factory=dict)
    asin_entity_profile: Dict[str, Any] = field(default_factory=dict)
    intent_weight_snapshot: Dict[str, Any] = field(default_factory=dict)
    bundle_variant: Dict[str, Any] = field(default_factory=dict)
    canonical_facts: Dict[str, Any] = field(default_factory=dict)
    fact_readiness: Dict[str, Any] = field(default_factory=dict)


def _load_feedback_context(snapshot_path: str) -> Dict[str, Any]:
    path = (snapshot_path or "").strip()
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return {}
    approved = payload.get("approved_keywords") or {}
    return {
        "source_file": payload.get("source_file", ""),
        "saved_at": payload.get("saved_at", ""),
        "organic_core": payload.get("organic_core") or approved.get("organic_core") or [],
        "sp_intent": payload.get("sp_intent") or approved.get("sp_intent") or [],
        "backend_only": payload.get("backend_only") or approved.get("backend_only") or [],
        "blocked_terms": payload.get("blocked_terms") or approved.get("blocked_terms") or [],
    }


def _merge_feedback_keywords(
    keyword_rows: List[Dict[str, Any]],
    feedback_context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not feedback_context:
        return keyword_rows

    merged: Dict[str, Dict[str, Any]] = {}
    for row in keyword_rows or []:
        keyword = str(row.get("keyword") or row.get("search_term") or "").strip()
        if not keyword:
            continue
        merged[keyword.lower()] = dict(row)

    def _safe_float(value: Any) -> float:
        try:
            return float(str(value or "0").replace(",", "").replace("%", "").strip() or 0)
        except (TypeError, ValueError):
            return 0.0

    def _inject(rows: List[Dict[str, Any]], source_type: str, routing_role_hint: str, priority_boost: float) -> None:
        for row in rows or []:
            keyword = str((row or {}).get("keyword") or "").strip()
            if not keyword:
                continue
            key = keyword.lower()
            existing = merged.get(key, {"keyword": keyword, "search_term": keyword})
            volume = max(
                _safe_float(existing.get("search_volume")),
                _safe_float((row or {}).get("search_volume")),
            )
            conversion = max(
                _safe_float(existing.get("conversion_rate")),
                _safe_float((row or {}).get("conversion_rate") or (row or {}).get("conversion")),
            )
            existing.update(
                {
                    "keyword": keyword,
                    "search_term": keyword,
                    "search_volume": volume,
                    "conversion_rate": conversion,
                    "source_type": source_type,
                    "routing_role_hint": routing_role_hint,
                    "priority_boost": priority_boost,
                    "feedback_selected": True,
                }
            )
            merged[key] = existing

    _inject(feedback_context.get("organic_core") or [], "feedback_organic_core", "title", 0.20)
    _inject(feedback_context.get("sp_intent") or [], "feedback_sp_intent", "bullet", 0.15)
    _inject(feedback_context.get("backend_only") or [], "feedback_backend_only", "backend", 0.10)
    return list(merged.values())


def _load_intent_weight_snapshot(snapshot_path: str) -> Dict[str, Any]:
    path = (snapshot_path or "").strip()
    if not path or not os.path.exists(path):
        return {}
    try:
        payload = load_intent_weight_snapshot(path)
    except Exception:
        return {}
    return {
        "source_file": payload.get("source_file", ""),
        "saved_at": payload.get("saved_at", ""),
        "weights": payload.get("weights") or [],
    }


# ==================== 文件读取与解析 ====================

def read_attribute_table(file_path: str) -> Dict[str, Any]:
    """
    读取属性表文件（支持2列/3列格式）
    格式1: 键值对（2列） - "字段名: 值"
    格式2: 键值对（3列） - "字段名 | 值 | 备注"
    """
    attr_data = {}

    if not os.path.exists(file_path):
        return attr_data

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # 尝试3列格式 (字段名 | 值 | 备注)
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                field_name = parts[0]
                field_value = parts[1]
                attr_data[field_name] = field_value
            continue

        # 尝试2列格式 (字段名: 值)
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                field_name = parts[0].strip()
                field_value = parts[1].strip()
                attr_data[field_name] = field_value
            continue

    return attr_data


def read_csv_file(file_path: str, expected_headers: List[str] = None) -> List[Dict[str, Any]]:
    """
    通过统一 data_loader 读取 .csv / .xlsx 文件，保证字段格式一致。
    """
    if not file_path or not os.path.exists(file_path):
        return []

    try:
        rows = load_table(file_path)
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        print(f"读取数据文件出错 {file_path}: {exc}", file=sys.stderr)
        return []

    cleaned_rows: List[Dict[str, Any]] = []
    for row in rows:
        cleaned_row: Dict[str, Any] = {}
        for key, value in row.items():
            if key is None:
                continue
            cleaned_key = str(key).strip()
            if not cleaned_key:
                continue
            if isinstance(value, str):
                cleaned_value = value.strip()
            elif value is None:
                cleaned_value = ""
            else:
                cleaned_value = value
            cleaned_row[cleaned_key] = cleaned_value
        cleaned_rows.append(cleaned_row)

    return cleaned_rows


def read_keyword_table(file_path: str) -> Tuple[KeywordData, Dict[str, Any]]:
    """
    读取关键词表（竞品出单词表）
    支持两种格式：26字段德语格式和其他格式
    """
    raw_data = read_csv_file(file_path)

    # 标准化字段名
    standard_data = []
    for row in raw_data:
        standardized = {}

        field_mapping = {
            "keyword": ["keyword", "关键词", "search_term", "search query", "query", "Search Term"],
            "search_volume": ["search_volume", "月搜索量", "volume", "searches", "月搜索"],
            "conversion_rate": ["conversion_rate", "购买率", "cvr", "purchase_rate", "order_rate", "转化率", "purchaseRate"],
            "click_share": ["click_share", "点击份额", "click share"],
            "ctr": ["ctr", "click_through_rate", "click rate", "点击率"],
            "clicks": ["clicks", "点击量"],
            "impressions": ["impressions", "曝光", "展示量"],
            "cart_adds": ["cart_adds", "加购", "adds"],
            "purchases": ["purchases", "orders", "订单量"],
            "purchase_share": ["purchase_share", "购买份额"],
            "avg_cpc": ["avg_cpc", "平均点击成本", "PPC价格", "PPC竞价", "bid"],
            "spr": ["spr", "SPR"],
            "title_density": ["title_density", "标题密度", "titleDensity"],
            "product_count": ["product_count", "商品数", "competitor_count", "竞品数"],
            "click_concentration": ["click_concentration", "点击集中度"],
            "conv_concentration": ["conv_concentration", "转化集中度"],
            "avg_price": ["avg_price", "均价", "price", "平均价格"],
            "monthly_purchases": ["monthly_purchases", "月购买量", "购买量"],
            "country": ["country", "国家", "market", "站点", "Country"],
            "category": ["category", "类目"],
            "source_type": ["source_type", "source", "来源"],
        }

        for std_field, possible_names in field_mapping.items():
            for name in possible_names:
                if name in row:
                    standardized[std_field] = row[name]
                    break

        # 数值清洗：除文本类字段外，所有标准化指标都转成数字。
        text_fields = {"keyword", "country", "category", "source_type"}
        for field in [name for name in field_mapping if name not in text_fields]:
            if field in standardized:
                value = standardized[field]
                if value is not None and value != "":
                    value_str = str(value)
                    cleaned = re.sub(r'[%,]', '', value_str)
                    try:
                        if '.' in cleaned:
                            standardized[field] = float(cleaned)
                        else:
                            standardized[field] = int(float(cleaned))
                    except ValueError:
                        standardized[field] = 0

        standard_data.append(standardized)

    audit_entry = _summarize_rows_table("keyword_table", "Keyword Table", file_path, raw_data)
    return KeywordData(keywords=standard_data), audit_entry


def read_aba_table(file_path: str) -> Tuple[ABAData, Dict[str, Any]]:
    """
    读取ABA趋势分析表（16字段格式）
    """
    raw_data = read_csv_file(file_path)

    # 标准化字段名
    standard_data = []
    for row in raw_data:
        standardized = {}

        # ABA特定字段映射
        field_mapping = {
            "keyword": ["keyword", "关键词", "search_term"],
            "search_volume": ["search_volume", "月搜索量", "volume"],
            "conversion_rate": ["conversion_rate", "购买率", "cvr"],
            "click_share": ["click_share", "点击份额"],
            "avg_cpc": ["avg_cpc", "平均点击成本"]
        }

        for std_field, possible_names in field_mapping.items():
            for name in possible_names:
                if name in row:
                    standardized[std_field] = row[name]
                    break

        # 数值清洗
        for field in ["search_volume", "conversion_rate", "click_share", "avg_cpc"]:
            if field in standardized:
                value = standardized[field]
                if value is not None and value != "":
                    value_str = str(value)
                    cleaned = re.sub(r'[%,]', '', value_str)
                    try:
                        if '.' in cleaned:
                            standardized[field] = float(cleaned)
                        else:
                            standardized[field] = int(float(cleaned))
                    except ValueError:
                        standardized[field] = 0

        standard_data.append(standardized)

    audit_entry = _summarize_rows_table("aba_table", "ABA Table", file_path, raw_data)
    return ABAData(trends=standard_data), audit_entry


def read_review_table(file_path: str) -> Tuple[ReviewData, Dict[str, Any]]:
    """
    读取评论合并表（多行文本格式）
    """
    raw_data = read_csv_file(file_path)

    # 提取Review_Insight数据
    insights = []
    for row in raw_data:
        if row.get("Data_Type") == "Review_Insight":
            insight = {
                "field_name": row.get("Field_Name", ""),
                "content_text": row.get("Content_Text", ""),
                "sentiment": row.get("Sentiment", ""),
                "count": int(row.get("Count", 0)) if row.get("Count", "").isdigit() else 0
            }
            insights.append(insight)

    audit_entry = _summarize_rows_table("review_table", "Review Table", file_path, raw_data)
    return ReviewData(insights=insights), audit_entry


# ==================== 语义提取与填槽字段处理 ====================

def extract_selling_points_from_text(text: str) -> List[str]:
    """
    从自由文本中提取核心卖点（增强语义提取）
    支持口语化汉语、中英文混合输入
    """
    if not text:
        return []

    # 分割文本（支持逗号、分号、空格分隔）
    separators = r'[,;，；\n]'
    raw_points = [p.strip() for p in re.split(separators, text) if p.strip()]

    # 使用模式库匹配
    matched_points = []
    for point in raw_points:
        matched = False

        # 检查是否匹配已知模式
        for std_point, patterns in SELLING_POINT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, point, re.IGNORECASE):
                    if std_point not in matched_points:
                        matched_points.append(std_point)
                    matched = True
                    break
            if matched:
                break

        # 如果没有匹配到已知模式，保留原始文本
        if not matched and point:
            matched_points.append(point)

    return matched_points


def extract_selling_points_auto(attr_data: Dict[str, Any], review_insights: List[Dict[str, Any]]) -> List[str]:
    """
    从属性表和评论中自动提取5-8个核心卖点
    """
    selling_points = []

    # 1. 从属性表提取（优先级最高）
    if attr_data:
        # special_feature字段（逗号分隔）
        if "special_feature" in attr_data:
            points = str(attr_data["special_feature"]).split(",")
            selling_points.extend([p.strip() for p in points if p.strip()])

        # product_features字段
        if "product_features" in attr_data:
            points = str(attr_data["product_features"]).split(",")
            selling_points.extend([p.strip() for p in points if p.strip()])

    # 2. 从评论中补充（优先级较低）
    if review_insights and not selling_points:
        # 收集Feature_Praise评论
        praise_comments = []
        for review in review_insights:
            if (review.get("field_name") == "Feature_Praise" or
                review.get("field_name") == "功能赞扬"):
                praise_comments.append(review.get("content_text", ""))

        # 提取高频正面特征（简化版本）
        if praise_comments:
            # 合并所有评论文本
            all_text = " ".join(praise_comments)
            # 检查是否包含常见卖点关键词
            for point, patterns in SELLING_POINT_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, all_text, re.IGNORECASE):
                        if point not in selling_points:
                            selling_points.append(point)
                        break

    # 3. 去重、排序、限制数量
    selling_points = list(dict.fromkeys(selling_points))  # 保持顺序去重
    selling_points = selling_points[:8]  # 最多8个

    # 4. 数量约束：确保5-8个卖点
    if len(selling_points) < 5:
        for generic in GENERIC_SELLING_POINTS:
            if generic not in selling_points and len(selling_points) < 8:
                selling_points.append(generic)

    return selling_points


def extract_accessories_from_text(text: str) -> List[Dict[str, Any]]:
    """
    从自由文本中提取配件描述
    """
    if text == "":  # 显式跳过
        return []

    if not text:
        return None  # 表示未提供

    descriptions: List[Dict[str, Any]] = []

    # 分割文本
    separators = r'[,;，；\n]'
    raw_items = [item.strip() for item in re.split(separators, text) if item.strip()]

    for item in raw_items:
        # 查找配件类型
        accessory_type = None
        for eng, chi in ACCESSORY_TYPES.items():
            if eng.lower() in item.lower() or chi in item:
                accessory_type = chi
                break

        # 提取参数（如深度、长度等）
        params = {}
        depth_match = re.search(r'(\d+)\s*米', item)
        if depth_match:
            params["depth_meters"] = int(depth_match.group(1))

        entry = {
            "name": accessory_type or "其他配件",
            "specification": item,
            "original": item,
            "params": params
        }
        descriptions.append(entry)

    return descriptions


def extract_accessories_from_attributes(attr_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从属性表included_components字段自动提取配件描述
    """
    if not attr_data or "included_components" not in attr_data:
        return []

    components_text = str(attr_data["included_components"])
    descriptions: List[Dict[str, Any]] = []

    # 分割逗号分隔的列表
    components = [c.strip() for c in components_text.split(",") if c.strip()]

    for comp in components:
        # 查找配件类型
        accessory_type = None
        for eng, chi in ACCESSORY_TYPES.items():
            if eng.lower() in comp.lower():
                accessory_type = chi
                break

        entry = {
            "name": accessory_type or "其他配件",
            "specification": comp,
            "original": comp,
            "params": {}
        }
        descriptions.append(entry)

    return descriptions


def merge_accessory_lists(primary: List[Dict[str, Any]], secondary: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """合并配件描述，按 specification 去重"""
    if not secondary:
        return primary
    seen = {item.get("specification") for item in primary if item.get("specification")}
    for item in secondary:
        spec = item.get("specification")
        if spec and spec in seen:
            continue
        primary.append(item)
        if spec:
            seen.add(spec)
    return primary


def _build_canonical_core_selling_points(points: Optional[List[str]]) -> List[str]:
    canonical: List[str] = []
    seen: set = set()
    for point in points or []:
        normalized = _normalize_to_canonical_english(point)
        if not normalized:
            continue
        slug = canonicalize_capability(normalized)
        label = english_capability_label(slug)
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        canonical.append(label)
    if not canonical and points:
        fallback = _normalize_to_canonical_english(points[0])
        if fallback:
            canonical.append(fallback)
    return canonical


def _build_canonical_accessory_list(accessories: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    canonical_list: List[Dict[str, Any]] = []
    for item in accessories or []:
        canonical_name = _normalize_to_canonical_english(item.get("name", ""))
        canonical_spec = _normalize_to_canonical_english(item.get("specification", ""))
        experience = get_accessory_experience(canonical_spec or canonical_name)
        experience_key = get_accessory_experience_key(canonical_spec or canonical_name)
        canonical_list.append({
            "name": canonical_name,
            "specification": canonical_spec,
            "original": item.get("original", ""),
            "note": _normalize_to_canonical_english(item.get("note", "")),
            "description": _normalize_to_canonical_english(item.get("description", "")),
            "params": item.get("params", {}),
            "experience": experience,
            "experience_key": experience_key,
        })
    return canonical_list


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for value in values:
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _build_canonical_capability_notes(signals: Dict[str, Any]) -> Dict[str, List[str]]:
    notes: Dict[str, List[str]] = {
        "runtime": [],
        "waterproof": [],
        "accessories": [],
    }
    runtime_total = signals.get("runtime_total_minutes")
    if runtime_total:
        notes["runtime"].append(f"{runtime_total} minutes total runtime")
    for seg in signals.get("runtime_segments") or []:
        context = _normalize_to_canonical_english(seg.get("context", ""))
        if context:
            notes["runtime"].append(context)
    depth = signals.get("waterproof_depth_m")
    if depth:
        suffix = " (housing required)" if signals.get("waterproof_requires_case") else ""
        notes["waterproof"].append(f"{depth}m waterproof{suffix}")
    for entry in signals.get("waterproof_entries") or []:
        context = _normalize_to_canonical_english(entry.get("context", ""))
        if context:
            notes["waterproof"].append(context)
    for acc in signals.get("accessories") or []:
        context = _normalize_to_canonical_english(acc.get("specification") or acc.get("name") or acc.get("original", ""))
        if context:
            notes["accessories"].append(context)

    # Deduplicate and drop empty categories
    cleaned = {
        key: _dedupe_preserve_order(values)
        for key, values in notes.items()
        if values
    }
    return cleaned


SUPPLEMENT_RUNTIME_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(?:min|分钟)', re.IGNORECASE)
SUPPLEMENT_DEPTH_PATTERN = re.compile(r'(\d+(?:\.\d+)?)\s*(?:m(?![a-zA-Z])|米)', re.IGNORECASE)
SUPPLEMENT_CASE_PATTERN = re.compile(r'(?:防水壳|外壳|housing|case)', re.IGNORECASE)
SUPPLEMENT_IP_PATTERN = re.compile(r'ip\s*\d{2}', re.IGNORECASE)
SUPPLEMENT_NON_WATERPROOF_PATTERN = re.compile(r'(?:不防水|not waterproof|non[-\s]?waterproof)', re.IGNORECASE)
SUPPLEMENT_STABILIZATION_PATTERN = re.compile(r'(?:防抖|stabilization|stabilisation|eis)', re.IGNORECASE)
SUPPLEMENT_SUPPORT_PATTERN = re.compile(r'(?:支持|support)', re.IGNORECASE)
SUPPLEMENT_UNSUPPORTED_PATTERN = re.compile(r'(?:不支持|not support|unsupported)', re.IGNORECASE)
SUPPLEMENT_DISCOURAGED_PATTERN = re.compile(r'(?:不建议(?:突出)?宣传|avoid visible|do not highlight)', re.IGNORECASE)
SUPPLEMENT_MODE_PATTERN = re.compile(r'(?<![A-Za-z0-9])(1080p|4k|5k|2k)(?![A-Za-z0-9])', re.IGNORECASE)
SUPPLEMENT_BEST_STABILIZATION_PATTERN = re.compile(
    r'(?:1080p.*?(?:比|better).{0,12}?4k|1080p.*?(?:更好|更佳)|best.*?1080p)',
    re.IGNORECASE,
)

ATTRIBUTE_ALIAS_GROUPS: Dict[str, List[str]] = {
    "brand_name": ["brand", "brand name"],
    "video_resolution": ["video capture resolution", "video_resolution", "resolution", "video quality", "maximum display resolution"],
    "connectivity": ["connectivity technology", "connectivity technolog", "connectivity", "wireless features", "连接功能"],
    "features": ["features", "product features", "special feature", "special features"],
    "has_image_stabilization": ["has image stabilization", "image stabilization", "stabilization", "防抖功能"],
    "stabilization_type": ["image stabilization", "stabilization", "防抖类型"],
    "water_resistance_level": ["water resistance level", "water resistance leve", "water_resistance", "waterproof_depth", "waterproof depth"],
    "battery_life": ["battery average life", "battery average lif", "battery_life", "recording time", "battery runtime", "续航时间", "电池续航"],
    "weight": ["item weight", "weight", "产品重量"],
    "form_factor": ["form factor", "style name", "camcorder type"],
    "dual_screen": ["dual screen", "dual_screen", "screen_type"],
    "live_streaming": ["live_streaming", "live streaming", "streaming", "直播功能"],
    "voice_control": ["voice_control", "voice command", "voice commands", "语音控制"],
}


def extract_accessories_from_supplement(text: str) -> List[Dict[str, Any]]:
    """
    针对“产品卖点和配件等信息补充.txt”提取配件列表
    仅解析包含“配件/附件”的语段，避免把整段说明误判为配件
    """
    if not text:
        return []

    section_items = _extract_named_bullet_items(
        text,
        [
            "本链接包含配件",
            "本链接配件",
            "链接包含配件",
            "包含配件",
            "配件清单",
            "附件清单",
            "随机配件",
        ],
    )
    if section_items:
        return [
            {
                "name": item,
                "specification": item,
                "original": item,
                "params": {},
            }
            for item in section_items
        ]

    normalized = re.sub(r'\s+', ' ', text.replace("\u3000", " "))
    segments: List[str] = []
    pattern = re.compile(r'(?:配件|附件)[^:：]*[:：]?\s*([^\n。\r]+)', re.IGNORECASE)
    for match in pattern.finditer(normalized):
        segment = match.group(1)
        if segment:
            segments.append(segment)

    # 兼容 “包含XX配件” / “含有XX附件” 顺序
    pattern_tail = re.compile(r'(?:包含|含有)\s*([^\n。\r]+?)(?:配件|附件)', re.IGNORECASE)
    for match in pattern_tail.finditer(normalized):
        segment = match.group(1)
        if segment:
            segments.append(segment)

    accessories: List[Dict[str, Any]] = []
    blacklist_tokens = ["不防", "不可", "续航", "分钟", "min", "mah"]
    for segment in segments:
        parts = re.split(r'[+、，,;；/]|和', segment)
        for part in parts:
            cleaned = re.sub(r'^\d+[\.\)]\s*', '', part.strip())
            if not cleaned or len(cleaned) == 1:
                continue
            lowered = cleaned.lower()
            if any(token in lowered for token in blacklist_tokens):
                continue
            accessories.append({
                "name": cleaned,
                "specification": cleaned,
                "original": cleaned,
                "params": {}
            })
    return accessories


def _normalize_heading_token(line: str) -> str:
    cleaned = str(line or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.strip("[]【】")
    cleaned = re.sub(r'[:：]\s*$', '', cleaned)
    cleaned = re.sub(r'^\s*#+\s*', '', cleaned)
    return cleaned.strip().lower()


def _extract_named_bullet_items(text: str, heading_aliases: List[str]) -> List[str]:
    if not text:
        return []

    aliases = {_normalize_heading_token(alias) for alias in heading_aliases if alias}
    if not aliases:
        return []

    collected: List[str] = []
    active = False
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            if active and collected:
                break
            continue

        heading = _normalize_heading_token(line)
        if heading in aliases:
            active = True
            continue

        if active:
            if heading and heading not in aliases and (line.startswith("【") or line.startswith("[")):
                break
            item = re.sub(r'^\s*[-*•]+\s*', '', line).strip()
            item = re.sub(r'^\s*\d+[\.\)]\s*', '', item).strip()
            item = item.strip("，,;；")
            if item:
                collected.append(item)
    return _dedupe_preserve_order(collected)


def _extract_card_capacity_from_supplement(text: str) -> Optional[int]:
    section_items = _extract_named_bullet_items(
        text,
        ["存储卡", "内存卡", "sd卡", "tf卡", "卡容量", "存储容量"],
    )
    card_patterns = section_items or re.findall(r'(\d+)\s*gb\b', str(text or ""), flags=re.IGNORECASE)
    capacities: List[int] = []
    for item in card_patterns:
        if isinstance(item, str):
            match = re.search(r'(\d+)', item)
            if not match:
                continue
            capacities.append(int(match.group(1)))
    return max(capacities) if capacities else None


def _extract_runtime_segments(text: str) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    if not text:
        return segments
    normalized = text.replace("\u3000", " ")
    for match in SUPPLEMENT_RUNTIME_PATTERN.finditer(normalized):
        minutes = int(float(match.group(1)))
        window = normalized[max(0, match.start() - 30):match.end() + 30]
        context_lower = window.lower()
        label = "unspecified"
        if any(token in context_lower for token in ["一共", "total", "overall", "合计"]):
            label = "total"
        elif any(token in context_lower for token in ["本机", "机身", "internal"]):
            label = "internal"
        elif any(token in context_lower for token in ["电池仓", "pod", "battery pack", "外接", "扩展"]):
            label = "extension"
        segments.append({
            "minutes": minutes,
            "context": window.strip(),
            "label": label,
            "source": "supplement"
        })
    return segments


def _select_runtime_total(segments: List[Dict[str, Any]]) -> Optional[int]:
    if not segments:
        return None
    totals = [seg.get("minutes") for seg in segments if seg.get("label") == "total"]
    if totals:
        return max(totals)
    return max((seg.get("minutes", 0) for seg in segments), default=None)


def _extract_waterproof_signals(text: str) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    requires_case = False
    normalized = text.replace("\u3000", " ")
    for match in SUPPLEMENT_DEPTH_PATTERN.finditer(normalized):
        depth = int(float(match.group(1)))
        window = normalized[max(0, match.start() - 20):match.end() + 25]
        context_lower = window.lower()
        if not re.search(r'防水|water|潜水|水下|深度', context_lower):
            continue
        if SUPPLEMENT_CASE_PATTERN.search(window):
            requires_case = True
        entries.append({"depth_m": depth, "context": window.strip()})
    supported = bool(entries) or bool(SUPPLEMENT_IP_PATTERN.search(normalized))
    if SUPPLEMENT_NON_WATERPROOF_PATTERN.search(normalized):
        supported = False
    requires_case = requires_case or bool(SUPPLEMENT_CASE_PATTERN.search(normalized))
    return {
        "entries": entries,
        "requires_case": requires_case,
        "supported": supported,
    }


def parse_supplement_signals(text: str, source_path: Optional[str] = None) -> Dict[str, Any]:
    """
    从补充信息txt中提取 runtime / depth / accessory 结构化信息
    """
    normalized = (text or "").strip()
    runtime_segments = _extract_runtime_segments(normalized)
    runtime_total = _select_runtime_total(runtime_segments)
    depth_info = _extract_waterproof_signals(normalized) if normalized else {"entries": [], "requires_case": False, "supported": None}
    accessories = extract_accessories_from_supplement(normalized)
    included_accessories = [item.get("name") or item.get("specification") or "" for item in accessories]
    included_accessories = [str(item).strip() for item in included_accessories if str(item).strip()]
    card_capacity_gb = _extract_card_capacity_from_supplement(normalized)
    lower_text = normalized.lower()

    depth_entries = depth_info.get("entries", [])
    max_depth = max((entry["depth_m"] for entry in depth_entries), default=None)
    stabilization_supported_modes: List[str] = []
    stabilization_unsupported_modes: List[str] = []
    stabilization_discouraged_modes: List[str] = []
    discouraged_claims: List[str] = []
    forbidden_claims: List[str] = []
    conditional_claims: List[Dict[str, str]] = []
    mounting_modes: List[str] = []
    stabilization_best_mode = ""

    if normalized:
        for line in re.split(r'[\n。；;]+', normalized):
            segment = line.strip()
            if not segment:
                continue
            segment_lower = segment.lower()
            modes = [mode.upper() for mode in SUPPLEMENT_MODE_PATTERN.findall(segment_lower)]
            if SUPPLEMENT_STABILIZATION_PATTERN.search(segment):
                if SUPPLEMENT_UNSUPPORTED_PATTERN.search(segment):
                    stabilization_unsupported_modes.extend(modes or ["GENERAL"])
                    forbidden_claims.append(segment)
                elif SUPPLEMENT_SUPPORT_PATTERN.search(segment):
                    stabilization_supported_modes.extend(modes or ["GENERAL"])
                if SUPPLEMENT_DISCOURAGED_PATTERN.search(segment):
                    discouraged_claims.append(segment)
                    stabilization_discouraged_modes.extend(modes or ["GENERAL"])
                if SUPPLEMENT_BEST_STABILIZATION_PATTERN.search(segment_lower):
                    stabilization_best_mode = "1080P"
            if "防水" in segment or "waterproof" in segment_lower:
                if "壳" in segment or "housing" in segment_lower or "case" in segment_lower:
                    conditional_claims.append({"claim": "waterproof", "condition": segment})
                if SUPPLEMENT_UNSUPPORTED_PATTERN.search(segment):
                    forbidden_claims.append(segment)
            if any(token in segment for token in ["挂脖", "挂颈"]) or "neck" in segment_lower:
                mounting_modes.append("neck_wear")
            if any(token in segment for token in ["金属表面", "磁吸", "吸附"]) or "metal" in segment_lower:
                mounting_modes.append("magnetic_surface")
            if any(token in segment for token in ["车把", "bike handle"]) or "handlebar" in segment_lower:
                mounting_modes.append("handlebar_mount")
            if "头盔" in segment or "helmet" in segment_lower:
                mounting_modes.append("helmet_mount")

    stabilization_supported_modes = _dedupe_preserve_order(stabilization_supported_modes)
    stabilization_unsupported_modes = _dedupe_preserve_order(stabilization_unsupported_modes)
    stabilization_discouraged_modes = _dedupe_preserve_order(stabilization_discouraged_modes)
    discouraged_claims = _dedupe_preserve_order(discouraged_claims)
    forbidden_claims = _dedupe_preserve_order(forbidden_claims)
    mounting_modes = _dedupe_preserve_order(mounting_modes)

    return {
        "source_path": source_path,
        "raw_text_present": bool(normalized),
        "runtime_segments": runtime_segments,
        "runtime_total_minutes": runtime_total,
        "waterproof_depth_m": max_depth,
        "waterproof_requires_case": depth_info.get("requires_case", False),
        "waterproof_supported": depth_info.get("supported"),
        "waterproof_entries": depth_entries,
        "accessories": accessories,
        "bundle_variant": {
            "included_accessories": included_accessories,
            "card_capacity_gb": card_capacity_gb,
            "source": "supplement" if included_accessories or card_capacity_gb else "",
        },
        "stabilization_supported_modes": stabilization_supported_modes,
        "stabilization_unsupported_modes": stabilization_unsupported_modes,
        "stabilization_discouraged_modes": stabilization_discouraged_modes,
        "stabilization_best_mode": stabilization_best_mode,
        "discouraged_claims": discouraged_claims,
        "forbidden_claims": forbidden_claims,
        "conditional_claims": conditional_claims,
        "mounting_modes": mounting_modes,
    }


def _mode_rank(mode: str) -> int:
    normalized = str(mode or "").upper()
    mapping = {"1080P": 1, "2K": 2, "4K": 3, "5K": 4, "8K": 5}
    return mapping.get(normalized, 0)


def _ordered_modes(modes: List[str]) -> List[str]:
    cleaned = [str(mode or "").upper() for mode in modes if str(mode or "").strip()]
    return sorted(_dedupe_preserve_order(cleaned), key=_mode_rank)


def _extract_modes_from_runtime_segments(runtime_segments: List[Dict[str, Any]]) -> List[str]:
    collected: List[str] = []
    for segment in runtime_segments or []:
        label = str((segment or {}).get("label") or "")
        for mode in SUPPLEMENT_MODE_PATTERN.findall(label.lower()):
            collected.append(mode.upper())
    return _ordered_modes(collected)


def _build_recording_mode_guidance(
    constraints: Dict[str, Any],
    supplement_signals: Dict[str, Any],
) -> Dict[str, Any]:
    supported_modes = _ordered_modes(list(constraints.get("stabilization_modes") or []))
    unsupported_modes = _ordered_modes(list(supplement_signals.get("stabilization_unsupported_modes") or []))
    discouraged_modes = _ordered_modes(list(supplement_signals.get("stabilization_discouraged_modes") or []))
    runtime_modes = _extract_modes_from_runtime_segments(supplement_signals.get("runtime_segments") or [])
    max_resolution = str(constraints.get("max_resolution") or "").lower()
    all_modes = _ordered_modes(supported_modes + unsupported_modes + discouraged_modes + runtime_modes)

    if "5k" in max_resolution and "5K" not in all_modes:
        all_modes.append("5K")
    elif "4k" in max_resolution and "4K" not in all_modes:
        all_modes.append("4K")
    elif "1080" in max_resolution and "1080P" not in all_modes:
        all_modes.append("1080P")
    all_modes = _ordered_modes(all_modes)

    preferred_stabilization_mode = str(supplement_signals.get("stabilization_best_mode") or "").upper()
    if not preferred_stabilization_mode and "1080P" in supported_modes:
        preferred_stabilization_mode = "1080P"
    if not preferred_stabilization_mode and supported_modes:
        preferred_stabilization_mode = supported_modes[0]

    guidance_by_mode: Dict[str, Dict[str, Any]] = {}
    for mode in all_modes:
        if mode == "1080P":
            scenes = ["cycling_recording", "sports_training", "outdoor_sports", "commuting_capture"]
            stabilization_visibility = "primary" if mode in supported_modes else "avoid"
            buyer_outcome = "Smooth-motion recording for bike, helmet, commute, and active POV scenes"
            copy_rule = "Use 1080P as the motion-first recommendation when smoother playback matters."
        elif mode == "4K":
            scenes = ["travel_documentation", "outdoor_sports", "family_use"]
            stabilization_visibility = "qualified" if mode in supported_modes and mode not in discouraged_modes else "avoid"
            buyer_outcome = "Sharper travel, route-review, and everyday outdoor detail without overselling stabilization"
            copy_rule = "Position 4K as detail-first everyday capture; avoid making stabilization the hero promise."
        elif mode == "5K":
            scenes = ["travel_documentation", "family_use", "daily_lifelogging"]
            stabilization_visibility = "avoid"
            buyer_outcome = "Detail-first footage for relatively steady framing, scenic capture, and memory keeping"
            copy_rule = "Use 5K only for detail-first or relatively steady scenes; never pair it with stabilization-led claims."
        else:
            scenes = ["travel_documentation", "daily_lifelogging"]
            stabilization_visibility = "qualified" if mode in supported_modes else "avoid"
            buyer_outcome = f"Use {mode} according to verified scene fit and supported accessories."
            copy_rule = f"Keep {mode} claims tied to verified use cases only."

        guidance_by_mode[mode] = {
            "mode": mode,
            "scene_focus": scenes,
            "stabilization_visibility": stabilization_visibility,
            "buyer_outcome": buyer_outcome,
            "copy_rule": copy_rule,
            "is_stabilization_supported": mode in supported_modes,
            "is_stabilization_unsupported": mode in unsupported_modes,
            "is_stabilization_discouraged": mode in discouraged_modes,
        }

    return {
        "available_modes": all_modes,
        "supported_stabilization_modes": supported_modes,
        "unsupported_stabilization_modes": unsupported_modes,
        "discouraged_stabilization_modes": discouraged_modes,
        "preferred_stabilization_mode": preferred_stabilization_mode,
        "guidance_by_mode": guidance_by_mode,
    }


def standardize_attribute_data(attr_data: Dict[str, Any]) -> Dict[str, str]:
    """Map vendor/Amazon headers into stable internal attribute keys."""
    normalized = _normalize_attribute_map(attr_data)
    standardized = dict(normalized)
    source_map: Dict[str, str] = {}
    for canonical_key, aliases in ATTRIBUTE_ALIAS_GROUPS.items():
        if standardized.get(canonical_key):
            source_map[canonical_key] = canonical_key
            continue
        for alias in aliases:
            value = normalized.get(alias)
            if value:
                standardized[canonical_key] = value
                source_map[canonical_key] = alias
                break

    features_blob = " ".join(
        filter(
            None,
            [
                standardized.get("features", ""),
                normalized.get("features", ""),
                normalized.get("product features", ""),
            ],
        )
    ).lower()
    dual_screen_blob = " ".join(
        filter(
            None,
            [
                features_blob,
                standardized.get("dual_screen", ""),
                standardized.get("form_factor", ""),
                standardized.get("brand_name", ""),
                normalized.get("型号", ""),
                normalized.get("model", ""),
                normalized.get("style name", ""),
            ],
        )
    ).lower()
    connectivity_blob = standardized.get("connectivity", "").lower()
    if "wifi" in connectivity_blob or "wi-fi" in connectivity_blob:
        standardized.setdefault("wifi_supported", "yes")
    if any(token in dual_screen_blob for token in ["dual screen", "dual-screen", "双屏", "前后屏", "double screen"]):
        standardized.setdefault("dual_screen_supported", "yes")
        standardized.setdefault("dual_screen", standardized.get("dual_screen") or "dual screen")
    if any(token in features_blob for token in ["eis", "stabilization", "stabilisation"]):
        standardized.setdefault("stabilization_type", standardized.get("stabilization_type", "EIS"))
        standardized.setdefault("has_image_stabilization", "Yes")
    if "waterproof" in features_blob:
        standardized.setdefault("water_resistance_level", "Waterproof")
    if any(token in features_blob for token in ["voice control", "voice command", "语音控制"]):
        standardized.setdefault("voice_control", "Yes")
    if any(token in features_blob for token in ["live stream", "live streaming", "直播"]):
        standardized.setdefault("live_streaming", "Yes")

    standardized["__source_map__"] = json.dumps(source_map, ensure_ascii=False)
    return standardized


def _normalize_attribute_map(attr_data: Dict[str, Any]) -> Dict[str, str]:
    """将属性键统一为小写，便于匹配"""
    normalized: Dict[str, str] = {}
    if not attr_data:
        return normalized
    for key, value in attr_data.items():
        if not key:
            continue
        norm_key = str(key).strip().lower()
        if isinstance(value, str):
            normalized[norm_key] = value.strip()
        else:
            normalized[norm_key] = str(value).strip()
    return normalized


def _load_text_file(path: Optional[str]) -> str:
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.exists():
        return ""
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="utf-8", errors="ignore")


def _load_multi_dimension_table_dump(path: Optional[str]) -> Dict[str, Any]:
    """
    尽最大可能加载多维表格的所有文本（不依赖固定列名），并记录列/行信息。
    """
    info: Dict[str, Any] = {
        "path": path or "",
        "columns": [],
        "row_count": 0,
        "text": "",
        "raw_chars": 0,
        "truncated": False,
    }
    if not path:
        return info
    file_path = Path(path)
    if not file_path.exists():
        return info
    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
    info["raw_chars"] = len(raw_text or "")
    if not raw_text:
        return info

    rows: List[List[str]] = []
    try:
        rows = [
            [cell for cell in row]
            for row in csv.reader(io.StringIO(raw_text))
            if any((cell or "").strip() for cell in row)
        ]
    except csv.Error:
        rows = []

    columns: List[str] = []
    data_rows: List[List[str]] = []
    column_usage: Dict[str, bool] = {}
    if rows:
        # 如果第一行包含至少两个非空单元，则视为表头
        header = rows[0]
        header_non_empty = [cell.strip() for cell in header if (cell or "").strip()]
        if len(header_non_empty) >= 2:
            columns = header_non_empty
            data_rows = rows[1:]
        else:
            data_rows = rows
    else:
        data_rows = []

    if columns:
        column_usage = {col: False for col in columns}

    structured_lines: List[str] = []
    if columns:
        structured_lines.append("HEADER: " + " | ".join(columns))
    source_rows = data_rows if data_rows else rows
    for idx, row in enumerate(source_rows, 1):
        normalized_cells = [cell.strip() for cell in row if (cell or "").strip()]
        if not normalized_cells:
            continue
        if columns:
            for i, cell in enumerate(row):
                if i < len(columns):
                    value = (cell or "").strip()
                    if value:
                        column_usage[columns[i]] = True
        structured_lines.append(f"ROW {idx}: " + " | ".join(normalized_cells))

    # 如果 CSV 解析失败或全为空，则直接使用原始文本
    if not structured_lines:
        structured_lines = [raw_text]

    normalized = _normalize_insight_block("\n".join(structured_lines))
    max_len = 15000
    if len(normalized) > max_len:
        info["truncated"] = True
        normalized = normalized[:max_len]

    info["text"] = normalized
    info["columns"] = columns
    info["row_count"] = len(source_rows)
    info["path"] = str(file_path)
    info["column_usage"] = column_usage
    return info


def _format_table_entry(table_id: str, label: str, path: Optional[str],
                        headers: List[str], used_headers: Optional[set],
                        row_count: int = 0) -> Dict[str, Any]:
    used_headers = used_headers or set()
    header_entries = [{"name": header, "used": header in used_headers} for header in headers]
    return {
        "id": table_id,
        "label": label,
        "path": path or "",
        "row_count": row_count,
        "headers": header_entries
    }


def _summarize_rows_table(table_id: str, label: str, path: Optional[str],
                          rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    headers: List[str] = sorted({key for row in rows for key in row.keys() if key})
    used: set = set()
    for row in rows:
        for key, value in row.items():
            if not key:
                continue
            if value not in (None, "", [], {}):
                used.add(key)
    return _format_table_entry(table_id, label, path, headers, used, row_count=len(rows))


def _summarize_kv_table(table_id: str, label: str, path: Optional[str],
                        kv_map: Dict[str, Any]) -> Dict[str, Any]:
    headers = sorted(kv_map.keys())
    used = set()
    for key, value in kv_map.items():
        if isinstance(value, str):
            if value.strip():
                used.add(key)
        else:
            if value not in (None, "", [], {}):
                used.add(key)
    return _format_table_entry(table_id, label, path, headers, used, row_count=len(kv_map))


def _empty_table_entry(table_id: str, label: str, path: Optional[str]) -> Dict[str, Any]:
    return {
        "id": table_id,
        "label": label,
        "path": path or "",
        "row_count": 0,
        "headers": []
    }


def _normalize_insight_block(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r'\n{3,}', '\n\n', normalized)
    normalized = re.sub(r'[ \t]+', ' ', normalized)
    return normalized.strip()


def _collect_raw_human_insights(run_config: RunConfig, supplement_text: str,
                                supplement_path: Optional[str]) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
    insights: List[str] = []
    audit: Dict[str, Any] = {}
    table_entry: Optional[Dict[str, Any]] = None
    cleaned_manual_notes = _normalize_insight_block(run_config.manual_notes)
    if cleaned_manual_notes:
        insights.append("MANUAL_NOTES:\n" + cleaned_manual_notes)
    cleaned_supplement = _normalize_insight_block(supplement_text)
    if cleaned_supplement:
        insights.append("SUPPLEMENTARY_NOTES:\n" + cleaned_supplement)
    audit["supplementary_file"] = {
        "path": supplement_path or "",
        "chars": len(cleaned_supplement or ""),
        "loaded": bool(cleaned_supplement),
    }
    table_entry = _format_table_entry(
        "supplementary_file",
        "Supplementary File",
        supplement_path,
        ["raw_text"],
        {"raw_text"} if cleaned_supplement else set(),
        row_count=1 if cleaned_supplement else 0,
    )

    input_files = run_config.input_files or {}
    multi_path = (
        input_files.get("multi_dimension_table")
        or input_files.get("review_table")
        or input_files.get("full_dimension_table")
    )
    multi_dump = _load_multi_dimension_table_dump(multi_path) if multi_path else {
        "text": "",
        "columns": [],
        "row_count": 0,
        "path": multi_path or "",
        "raw_chars": 0,
        "truncated": False,
    }
    if multi_dump.get("text"):
        insights.append("MULTI_DIMENSION_TABLE:\n" + multi_dump["text"])
    audit["multi_dimension_table"] = {
        "path": multi_dump.get("path") or "",
        "columns": multi_dump.get("columns") or [],
        "rows": multi_dump.get("row_count", 0),
        "chars": len(multi_dump.get("text") or ""),
        "raw_chars": multi_dump.get("raw_chars", 0),
        "truncated": bool(multi_dump.get("truncated")),
        "loaded": bool(multi_dump.get("text")),
        "column_usage": multi_dump.get("column_usage") or {},
    }

    combined = "\n\n".join(insights).strip()
    max_len = 15000
    if len(combined) > max_len:
        audit.setdefault("raw_human_insights", {})["truncated"] = True
        combined = combined[:max_len]
    audit.setdefault("raw_human_insights", {})["chars"] = len(combined)
    return combined, audit, table_entry


def _infer_supplement_path(run_config: RunConfig, attribute_path: Optional[str]) -> Optional[str]:
    """在 input_files 或属性目录中寻找卖点/配件补充文本"""
    input_files = run_config.input_files or {}
    candidate = input_files.get("supplement_file")
    if candidate and Path(candidate).exists():
        return candidate

    if attribute_path:
        attr_dir = Path(attribute_path).parent
        default_name = attr_dir / "产品卖点和配件等信息补充.txt"
        if default_name.exists():
            return str(default_name)
        for fallback in attr_dir.glob("*补充*.txt"):
            if fallback.is_file():
                return str(fallback)
    return None


def derive_capability_constraints(attr_data: Dict[str, Any],
                                  accessory_descriptions: List[Dict[str, Any]],
                                  supplement_signals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    根据属性表与配件描述推断能力约束（防水、防抖、续航等）
    """
    standardized_attr = standardize_attribute_data(attr_data)
    normalized = _normalize_attribute_map(standardized_attr)
    supplement_signals = supplement_signals or {}
    constraints: Dict[str, Any] = {
        "waterproof_supported": False,
        "waterproof_requires_case": False,
        "waterproof_depth_m": None,
        "waterproof_note": "",
        "stabilization_supported": False,
        "stabilization_modes": [],
        "stabilization_note": "",
        "max_resolution": normalized.get("video capture resolution", normalized.get("video_resolution", "")),
        "runtime_minutes": None,
        "runtime_breakdown": [],
        "runtime_source": "",
        "supplement_source": supplement_signals.get("source_path"),
        "accessory_catalog": accessory_descriptions,
        "accessory_catalog_count": len(accessory_descriptions or []),
        "standardized_attributes": standardized_attr,
        "wifi_supported": False,
        "dual_screen_supported": False,
        "voice_control_supported": False,
        "live_streaming_supported": False,
        "faq_only_claims": [],
        "discouraged_claims": supplement_signals.get("discouraged_claims", []),
        "forbidden_claims": supplement_signals.get("forbidden_claims", []),
        "mounting_modes": supplement_signals.get("mounting_modes", []),
        "stabilization_discouraged_modes": supplement_signals.get("stabilization_discouraged_modes", []),
        "stabilization_best_mode": supplement_signals.get("stabilization_best_mode", ""),
        "recording_mode_guidance": {},
    }

    # Waterproof detection
    water_value = ""
    for key in normalized:
        if "water" in key:
            water_value = normalized[key]
            break
    water_value_lower = water_value.lower()
    if water_value_lower:
        if any(term in water_value_lower for term in ["waterproof", "ip", "防水"]):
            constraints["waterproof_supported"] = "not" not in water_value_lower and "无" not in water_value_lower
        if "case" in water_value_lower or "壳" in water_value_lower:
            constraints["waterproof_requires_case"] = True
    # accessory depth
    depth_m = None
    for acc in accessory_descriptions or []:
        params = acc.get("params") or {}
        if params.get("depth_meters"):
            depth_m = params["depth_meters"]
            break
        spec = (acc.get("specification") or acc.get("original") or "").lower()
        match = re.search(r'(\d+)\s*m', spec)
        if match:
            depth_m = int(match.group(1))
            if "case" in spec or "壳" in spec:
                constraints["waterproof_requires_case"] = True
            break
    if depth_m is None and water_value_lower:
        match = re.search(r'(\d+)\s*m', water_value_lower)
        if match:
            depth_m = int(match.group(1))
    constraints["waterproof_depth_m"] = depth_m

    # Stabilization detection
    stabilization_value = ""
    for key in normalized:
        if "stabilization" in key or "防抖" in key:
            stabilization_value = normalized[key]
            break
    stabilization_lower = stabilization_value.lower()
    if stabilization_lower:
        supports_eis = any(term in stabilization_lower for term in ["eis", "electronic", "数字", "yes", "ja"])
        constraints["stabilization_supported"] = supports_eis and "none" not in stabilization_lower and "无" not in stabilization_lower
        if "1080" in stabilization_lower:
            constraints["stabilization_modes"].append("1080P")
        if "4k" in stabilization_lower or "4 k" in stabilization_lower:
            constraints["stabilization_modes"].append("4K")
        if not constraints["stabilization_modes"] and constraints["stabilization_supported"]:
            constraints["stabilization_modes"] = ["1080P"]
    supported_modes = supplement_signals.get("stabilization_supported_modes") or []
    unsupported_modes = supplement_signals.get("stabilization_unsupported_modes") or []
    if supported_modes:
        constraints["stabilization_supported"] = True
        constraints["stabilization_modes"] = _dedupe_preserve_order(
            constraints["stabilization_modes"] + [mode for mode in supported_modes if mode != "GENERAL"]
        )
    if unsupported_modes:
        constraints["faq_only_claims"].append("stabilization limitations")
        constraints["forbidden_claims"].extend(unsupported_modes)
    if constraints["stabilization_supported"]:
        modes = ", ".join(constraints["stabilization_modes"]) if constraints["stabilization_modes"] else "supported modes"
        constraints["stabilization_note"] = f"EIS available in {modes}"
    else:
        constraints["stabilization_note"] = "Avoid visible stabilization claims"

    # Runtime estimate
    battery_value = ""
    for key in normalized:
        if "battery" in key:
            battery_value = normalized[key]
            break
    match = re.search(r'(\d+)\s*(min|分钟)', battery_value.lower())
    if match:
        constraints["runtime_minutes"] = int(match.group(1))
        constraints["runtime_source"] = "attribute"

    supplement_runtime = supplement_signals.get("runtime_total_minutes")
    if supplement_runtime:
        constraints["runtime_minutes"] = supplement_runtime
        constraints["runtime_source"] = "supplement"
    constraints["runtime_breakdown"] = supplement_signals.get("runtime_segments", [])

    supplement_water_supported = supplement_signals.get("waterproof_supported")
    if supplement_water_supported is True and supplement_signals.get("waterproof_depth_m"):
        constraints["waterproof_supported"] = True
        sup_depth = supplement_signals.get("waterproof_depth_m")
        if sup_depth:
            constraints["waterproof_depth_m"] = sup_depth
    elif supplement_water_supported is False:
        constraints["waterproof_supported"] = False
        constraints["waterproof_depth_m"] = None

    if supplement_signals.get("waterproof_requires_case"):
        constraints["waterproof_requires_case"] = True
        constraints["faq_only_claims"].append("waterproof condition")

    if supplement_signals.get("waterproof_depth_m") and not constraints["waterproof_depth_m"]:
        constraints["waterproof_depth_m"] = supplement_signals["waterproof_depth_m"]

    if constraints["waterproof_supported"]:
        depth_value = constraints.get("waterproof_depth_m")
        if constraints.get("waterproof_requires_case"):
            if depth_value:
                constraints["waterproof_note"] = f"Only waterproof when using included housing (up to {depth_value} m)"
            else:
                constraints["waterproof_note"] = "Only waterproof when using included housing"
        elif depth_value:
            constraints["waterproof_note"] = f"Supports up to {depth_value} m"
        else:
            constraints["waterproof_note"] = "Waterproof claim allowed per verified specs"
    else:
        constraints["waterproof_note"] = "Visible copy should avoid waterproof claims"

    features_blob = " ".join(
        filter(
            None,
            [
                normalized.get("features", ""),
                normalized.get("product features", ""),
                normalized.get("special feature", ""),
            ],
        )
    ).lower()
    dual_screen_blob = " ".join(
        filter(
            None,
            [
                features_blob,
                normalized.get("dual_screen", ""),
                normalized.get("screen_type", ""),
                normalized.get("form_factor", ""),
                normalized.get("brand_name", ""),
                normalized.get("型号", ""),
                normalized.get("model", ""),
                normalized.get("style name", ""),
            ],
        )
    ).lower()
    connectivity_blob = normalized.get("connectivity", "").lower()
    constraints["wifi_supported"] = any(token in connectivity_blob for token in ["wifi", "wi-fi"])
    constraints["dual_screen_supported"] = (
        any(token in dual_screen_blob for token in ["dual screen", "dual-screen", "双屏", "前后屏", "double screen"]) or
        normalized.get("dual_screen_supported", "").lower() in {"yes", "true", "1"}
    )
    constraints["voice_control_supported"] = (
        normalized.get("voice control", normalized.get("voice_control", "")).lower() in {"yes", "true", "1"}
        or any(token in features_blob for token in ["voice control", "voice command", "语音控制"])
    )
    constraints["live_streaming_supported"] = (
        normalized.get("live streaming", normalized.get("live_streaming", "")).lower() in {"yes", "true", "1"}
        or any(token in features_blob for token in ["live stream", "live streaming", "直播"])
    )
    constraints["faq_only_claims"] = _dedupe_preserve_order(constraints["faq_only_claims"])
    constraints["forbidden_claims"] = _dedupe_preserve_order(constraints["forbidden_claims"])
    constraints["recording_mode_guidance"] = _build_recording_mode_guidance(constraints, supplement_signals)
    if not constraints.get("stabilization_best_mode"):
        constraints["stabilization_best_mode"] = (
            constraints["recording_mode_guidance"].get("preferred_stabilization_mode") or ""
        )
    constraints["stabilization_discouraged_modes"] = _dedupe_preserve_order(
        constraints.get("stabilization_discouraged_modes", [])
    )

    return constraints


# ==================== 质量评分 ====================

def calculate_quality_score(
    selling_points: List[str],
    accessory_status: str,
    attr_data: Dict[str, Any],
    keyword_data: List[Dict[str, Any]],
    review_data: List[Dict[str, Any]]
) -> int:
    """
    计算预处理质量评分（0-100分）
    """
    score = 0

    # 1. 核心卖点完整性 (30分)
    if len(selling_points) >= 5:
        score += 30
    elif len(selling_points) >= 3:
        score += 20
    elif len(selling_points) >= 1:
        score += 10

    # 2. 配件描述明确性 (20分)
    if accessory_status in {"parsed", "supplement_enriched"}:
        score += 20
    elif accessory_status == "auto_extracted":
        score += 15

    # 3. 产品属性完整性 (25分)
    required_fields = ["video_resolution", "battery_life", "waterproof_depth", "weight"]
    present_fields = [field for field in required_fields if field in attr_data]
    coverage = len(present_fields) / len(required_fields)
    score += int(coverage * 25)

    # 4. 关键词数据可用性 (15分)
    if keyword_data and len(keyword_data) > 10:
        score += 15
    elif keyword_data and len(keyword_data) > 5:
        score += 10
    elif keyword_data:
        score += 5

    # 5. 评论洞察可用性 (10分)
    if review_data and len(review_data) > 5:
        score += 10
    elif review_data:
        score += 5

    return min(100, score)  # 确保不超过100分


# ==================== 真实国家词表加载 ====================

# 延迟导入以避免循环依赖
_COUNTRY_VOCAB_AVAILABLE = True


def load_real_country_vocab(country: str) -> RealVocabData:
    """
    为指定国家加载真实词表（Priority 1 关键词来源）。

    从 data/raw/de/DE/*.csv 与 data/raw/fr/FR/*.csv 读取
    ABA 关键词表和出单词表。

    Returns:
        RealVocabData 对象（is_available=False 表示加载失败或国家不支持）
    """
    try:
        # 动态导入避免循环依赖
        from tools.country_vocab import load_country_vocab, find_high_volume_keywords
    except ImportError:
        return RealVocabData(country=country, is_available=False)

    try:
        vocab = load_country_vocab(country)
    except Exception:
        return RealVocabData(country=country, is_available=False)

    all_entries = vocab.get("all", [])
    if not all_entries:
        return RealVocabData(country=country, is_available=False)

    # 取 Top 20 高搜索量本地关键词
    top_entries = find_high_volume_keywords(vocab, min_volume=0, top_n=20)
    top_keywords = []
    for e in top_entries:
        top_keywords.append({
            "keyword": e.keyword,
            "source_type": e.source_type,
            "source_file": e.source_file,
            "search_volume": e.search_volume,
            "conversion_rate": e.conversion_rate,
            "avg_cpc": e.avg_cpc,
            "spr": e.spr,
            "country": e.country,
            "model": e.model,
            "tier": e.tier,
        })

    # 判断 data_mode（基于真实词表行数）
    total = len(all_entries)
    vocab_data_mode = "DATA_DRIVEN" if total >= 10 else "SYNTHETIC_COLD_START"

    return RealVocabData(
        country=country,
        is_available=True,
        total_count=total,
        aba_count=len(vocab.get("aba", [])),
        order_winning_count=len(vocab.get("order_winning", [])),
        template_count=len(vocab.get("template", [])),
        review_count=len(vocab.get("review", [])),
        top_keywords=top_keywords,
        data_mode=vocab_data_mode,
    )


# ==================== 主预处理函数 ====================

def preprocess_data(
    run_config_path: Optional[str] = None,
    run_config_dict: Optional[Dict[str, Any]] = None,
    attribute_table_path: Optional[str] = None,
    keyword_table_path: Optional[str] = None,
    review_table_path: Optional[str] = None,
    aba_merged_path: Optional[str] = None,
    output_path: Optional[str] = None
) -> PreprocessedData:
    """
    主预处理函数 - 执行Step 0所有处理步骤
    """
    import datetime

    # 1. 读取运行配置
    if run_config_path:
        with open(run_config_path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
    elif run_config_dict:
        config_dict = run_config_dict
    else:
        raise ValueError("必须提供run_config_path或run_config_dict")

    run_config = RunConfig.from_dict(config_dict)

    # 2. 获取文件路径（优先使用input_files中的路径）
    if run_config.input_files:
        attribute_path = run_config.input_files.get("attribute_table") or attribute_table_path
        keyword_path = run_config.input_files.get("keyword_table") or keyword_table_path
        review_path = run_config.input_files.get("review_table") or review_table_path
        aba_path = run_config.input_files.get("aba_merged") or aba_merged_path
    else:
        attribute_path = attribute_table_path
        keyword_path = keyword_table_path
        review_path = review_table_path
        aba_path = aba_merged_path

    # 3. 读取数据文件
    ingestion_tables: List[Dict[str, Any]] = []

    attribute_data = read_attribute_table(attribute_path) if attribute_path else {}
    ingestion_tables.append(
        _summarize_kv_table(
            "attribute_table",
            "Attribute Table",
            attribute_path,
            attribute_data
        )
    )

    if keyword_path:
        keyword_data, keyword_audit = read_keyword_table(keyword_path)
    else:
        keyword_data = KeywordData(keywords=[])
        keyword_audit = _empty_table_entry("keyword_table", "Keyword Table", keyword_path)
    ingestion_tables.append(keyword_audit)

    feedback_context = _load_feedback_context(run_config.feedback_snapshot_path)
    if feedback_context:
        keyword_data.keywords = _merge_feedback_keywords(keyword_data.keywords, feedback_context)
        ingestion_tables.append(
            _format_table_entry(
                "feedback_snapshot",
                "Feedback Snapshot",
                run_config.feedback_snapshot_path,
                ["organic_core", "sp_intent", "backend_only", "blocked_terms"],
                {"organic_core", "sp_intent", "backend_only", "blocked_terms"},
                row_count=sum(len(feedback_context.get(key) or []) for key in ["organic_core", "sp_intent", "backend_only", "blocked_terms"]),
            )
        )
    intent_weight_snapshot = _load_intent_weight_snapshot(run_config.intent_weight_snapshot_path)
    if intent_weight_snapshot:
        ingestion_tables.append(
            _format_table_entry(
                "intent_weight_snapshot",
                "Intent Weight Snapshot",
                run_config.intent_weight_snapshot_path,
                ["weights"],
                {"weights"},
                row_count=len(intent_weight_snapshot.get("weights") or []),
            )
        )

    if review_path:
        review_data, review_audit = read_review_table(review_path)
    else:
        review_data = ReviewData(insights=[])
        review_audit = _empty_table_entry("review_table", "Review Table", review_path)
    ingestion_tables.append(review_audit)

    if aba_path:
        aba_data, aba_audit = read_aba_table(aba_path)
    else:
        aba_data = ABAData(trends=[])
        aba_audit = _empty_table_entry("aba_table", "ABA Table", aba_path)
    ingestion_tables.append(aba_audit)

    # 3b. 加载真实国家词表（Priority 1，DE/FR 专用）
    real_vocab = None
    data_alerts: List[str] = []
    target_ctry = run_config.target_country.upper()
    if target_ctry in ("DE", "FR"):
        real_vocab = load_real_country_vocab(target_ctry)
        vocab_count = real_vocab.total_count if (real_vocab and real_vocab.is_available) else 0
        if vocab_count < 50:
            data_alerts.append(
                f"⚠️ {target_ctry} 词库稀疏（当前 {vocab_count} 条），建议通过卖家精灵补充词库后重跑，当前分数可能低估真实潜力"
            )

    # 4. 处理填槽字段
    # 4.1 核心卖点处理
    if run_config.core_selling_points_raw:
        # 用户提供了卖点文本
        core_selling_points = extract_selling_points_from_text(run_config.core_selling_points_raw)
        selling_points_source = "user_input"
    else:
        # 自动提取卖点
        core_selling_points = extract_selling_points_auto(attribute_data, review_data.insights)
        selling_points_source = "auto_extracted"

    # 4.2 配件描述处理
    if run_config.accessory_params_raw:  # 用户提供了配件描述
        accessory_descriptions = extract_accessories_from_text(run_config.accessory_params_raw)
        accessory_status = "parsed"
    else:  # 未提供，尝试自动提取
        accessory_descriptions = extract_accessories_from_attributes(attribute_data)
        accessory_status = "auto_extracted" if accessory_descriptions else "missing"
    accessory_descriptions = accessory_descriptions or []

    supplement_path = _infer_supplement_path(run_config, attribute_path)
    supplement_text = _load_text_file(supplement_path)
    raw_human_insights, insight_audit, supplementary_entry = _collect_raw_human_insights(run_config, supplement_text, supplement_path)
    supplement_signals = parse_supplement_signals(supplement_text, supplement_path)
    supplement_accessories = supplement_signals.get("accessories") or []
    if supplement_accessories:
        before_len = len(accessory_descriptions)
        accessory_descriptions = merge_accessory_lists(accessory_descriptions, supplement_accessories)
        if len(accessory_descriptions) > before_len and accessory_status != "parsed":
            accessory_status = "supplement_enriched"
    if supplementary_entry:
        ingestion_tables.append(supplementary_entry)

    multi_audit = insight_audit.get("multi_dimension_table", {})
    if multi_audit:
        columns = multi_audit.get("columns") or []
        usage = multi_audit.get("column_usage") or {}
        used_headers = {col for col, used in usage.items() if used}
        ingestion_tables.append(
            _format_table_entry(
                "multi_dimension_table",
                "Multi-dimensional Table",
                multi_audit.get("path"),
                columns,
                used_headers,
                row_count=multi_audit.get("rows", 0),
            )
        )

    ingestion_audit = {
        "tables": ingestion_tables,
        "raw_human_insights": insight_audit.get("raw_human_insights", {}),
        "supplementary_file": insight_audit.get("supplementary_file", {}),
        "multi_dimension_table": insight_audit.get("multi_dimension_table", {})
    }

    canonical_core_selling_points = _build_canonical_core_selling_points(core_selling_points)
    if not canonical_core_selling_points and core_selling_points:
        canonical_core_selling_points = core_selling_points[:]
    canonical_accessory_descriptions = _build_canonical_accessory_list(accessory_descriptions)
    canonical_capability_notes = _build_canonical_capability_notes(supplement_signals)

    # 5. 计算质量评分
    quality_score = calculate_quality_score(
        core_selling_points,
        accessory_status,
        attribute_data,
        keyword_data.keywords,
        review_data.insights
    )

    # 6. 确定目标语言 (target_language)
    target_language = COUNTRY_LANGUAGE_MAP.get(run_config.target_country, "English")

    # 6b. 能力约束推断（供合规使用）
    capability_constraints = derive_capability_constraints(
        attribute_data,
        accessory_descriptions,
        supplement_signals=supplement_signals,
    )
    standardized_attribute_data = capability_constraints.get("standardized_attributes") or standardize_attribute_data(attribute_data)
    canonical_facts = build_canonical_facts(
        attribute_data,
        supplemental_data=supplement_signals,
        capability_constraints=capability_constraints,
    )
    category_type = "wearable_body_camera" if "body" in str(attribute_data).lower() else "generic"
    fact_readiness = summarize_fact_readiness(canonical_facts, category_type=category_type)

    # 7. PRD v8.2: 诊断 data_mode
    # DATA_DRIVEN: ABA + review 总有效行数 >= 10
    # SYNTHETIC_COLD_START: 有效行数 < 10，需要合成
    # 如果有真实国家词表且行数 >= 10，也视为 DATA_DRIVEN
    total_data_rows = len(aba_data.trends) + len(review_data.insights)
    if real_vocab and real_vocab.is_available and real_vocab.total_count >= 10:
        data_mode = "DATA_DRIVEN"
    elif total_data_rows >= 10:
        data_mode = "DATA_DRIVEN"
    else:
        data_mode = "SYNTHETIC_COLD_START"

    # 8. 构建预处理数据对象
    preprocessed = PreprocessedData(
        run_config=run_config,
        attribute_data=AttributeData(data=standardized_attribute_data),
        keyword_data=keyword_data,
        review_data=review_data,
        aba_data=aba_data,
        real_vocab=real_vocab,
        core_selling_points=core_selling_points,
        accessory_descriptions=accessory_descriptions,
        canonical_core_selling_points=canonical_core_selling_points,
        canonical_accessory_descriptions=canonical_accessory_descriptions,
        canonical_capability_notes=canonical_capability_notes,
        quality_score=quality_score,
        language=target_language,
        target_country=run_config.target_country,
        reasoning_language="EN",
        data_mode=data_mode,
        processed_at=datetime.datetime.now().isoformat(),
        capability_constraints=capability_constraints,
        supplement_signals=supplement_signals,
        raw_human_insights=raw_human_insights,
        ingestion_audit=ingestion_audit,
        feedback_context=feedback_context,
        intent_weight_snapshot=intent_weight_snapshot,
        bundle_variant=supplement_signals.get("bundle_variant") or {},
        canonical_facts=canonical_facts,
        fact_readiness=fact_readiness,
    )
    preprocessed.data_alerts = data_alerts
    preprocessed.asin_entity_profile = build_entity_profile(preprocessed)

    # 8. 输出到文件（如果指定了输出路径）
    if output_path:
        output_dict = {
            "preprocessed_data": {
                "run_config": {
                    "target_country": run_config.target_country,
                    "brand_name": run_config.brand_name,
                    "product_code": run_config.product_code,
                    "workspace_dir": run_config.workspace_dir,
                    "core_selling_points_raw": run_config.core_selling_points_raw,
                    "accessory_params_raw": run_config.accessory_params_raw,
                    "manual_notes": run_config.manual_notes,
                    "feedback_snapshot_path": run_config.feedback_snapshot_path,
                    "intent_weight_snapshot_path": run_config.intent_weight_snapshot_path,
                    "previous_snapshot_path": run_config.previous_snapshot_path,
                    "selling_points_source": selling_points_source,
                    "accessory_status": accessory_status
                },
                "attribute_data": attribute_data,
                "standardized_attribute_data": standardized_attribute_data,
                "keyword_summary": {
                    "total_keywords": len(keyword_data.keywords),
                    "keywords_sample": keyword_data.keywords[:5] if keyword_data.keywords else []
                },
                "review_summary": {
                    "total_insights": len(review_data.insights),
                    "insights_sample": review_data.insights[:5] if review_data.insights else []
                },
                "aba_summary": {
                    "total_trends": len(aba_data.trends),
                    "trends_sample": aba_data.trends[:5] if aba_data.trends else []
                },
                "core_selling_points": core_selling_points,
                "canonical_core_selling_points": canonical_core_selling_points,
                "accessory_descriptions": accessory_descriptions,
                "canonical_accessory_descriptions": canonical_accessory_descriptions,
                "quality_score": quality_score,
                "quality_breakdown": {
                    "selling_points_completeness": "优秀" if len(core_selling_points) >= 5 else "良好" if len(core_selling_points) >= 3 else "不足",
                    "accessory_clarity": accessory_status,
                    "attribute_coverage": f"{len([f for f in ['video_resolution', 'battery_life', 'waterproof_depth', 'weight'] if f in attribute_data])}/4",
                    "keyword_data_availability": "充足" if keyword_data.keywords and len(keyword_data.keywords) > 10 else "有限" if keyword_data.keywords else "缺失",
                    "review_insight_availability": "充足" if review_data.insights and len(review_data.insights) > 5 else "有限" if review_data.insights else "缺失"
                },
                "language": target_language,
                "target_country": run_config.target_country,
                "reasoning_language": "EN",
                "data_mode": data_mode,
                "data_mode_note": f"ABA rows: {len(aba_data.trends)}, Review rows: {len(review_data.insights)}, Real vocab rows: {real_vocab.total_count if real_vocab else 0}, Total: {total_data_rows}",
                "processed_at": preprocessed.processed_at,
                "capability_constraints": capability_constraints,
                "canonical_capability_notes": canonical_capability_notes,
                "canonical_facts": preprocessed.canonical_facts,
                "fact_readiness": preprocessed.fact_readiness,
                "raw_human_insights": raw_human_insights,
                "ingestion_audit": ingestion_audit,
                "feedback_context": feedback_context,
                "asin_entity_profile": preprocessed.asin_entity_profile,
                "intent_weight_snapshot": intent_weight_snapshot,
                "bundle_variant": preprocessed.bundle_variant,
            },
            "data_alerts": data_alerts,
            "supplement_source": {
                "path": supplement_path,
                "runtime_minutes": supplement_signals.get("runtime_total_minutes"),
                "waterproof_depth_m": supplement_signals.get("waterproof_depth_m"),
                "accessory_count": len(supplement_signals.get("accessories") or []),
                "bundle_variant": supplement_signals.get("bundle_variant") or {},
            },
            # 保存完整关键词数据供scoring.py使用
            "keyword_data": {
                "keywords": keyword_data.keywords if keyword_data.keywords else []
            },
            # 保存完整review数据
            "review_data": {
                "insights": review_data.insights if review_data.insights else []
            },
            # 保存完整aba数据
            "aba_data": {
                "trends": aba_data.trends if aba_data.trends else []
            },
            # 保存真实国家词表（Priority 1）
            "real_vocab": {
                "country": real_vocab.country if real_vocab else None,
                "is_available": real_vocab.is_available if real_vocab else False,
                "total_count": real_vocab.total_count if real_vocab else 0,
                "aba_count": real_vocab.aba_count if real_vocab else 0,
                "order_winning_count": real_vocab.order_winning_count if real_vocab else 0,
                "template_count": real_vocab.template_count if real_vocab else 0,
                "review_count": real_vocab.review_count if real_vocab else 0,
                "top_keywords": real_vocab.top_keywords if real_vocab else [],
                "data_mode": real_vocab.data_mode if real_vocab else "SYNTHETIC_COLD_START",
            } if real_vocab else {"is_available": False}
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_dict, f, ensure_ascii=False, indent=2)

    return preprocessed


# ==================== 命令行接口 ====================

def main():
    """命令行入口点"""
    import argparse

    parser = argparse.ArgumentParser(description='Amazon Listing Generator - 数据预处理')
    parser.add_argument('--run-config', required=True, help='run_config JSON文件路径')
    parser.add_argument('--attribute-table', help='本品属性表.txt路径')
    parser.add_argument('--keyword-table', help='关键词表.csv路径')
    parser.add_argument('--review-table', help='评论合并表.csv路径')
    parser.add_argument('--aba-merged', help='ABA合并表.csv路径')
    parser.add_argument('--output', default='preprocessed_data.json', help='输出JSON文件路径')
    parser.add_argument('--verbose', action='store_true', help='显示详细输出')

    args = parser.parse_args()

    try:
        # 执行预处理
        preprocessed = preprocess_data(
            run_config_path=args.run_config,
            attribute_table_path=args.attribute_table,
            keyword_table_path=args.keyword_table,
            review_table_path=args.review_table,
            aba_merged_path=args.aba_merged,
            output_path=args.output
        )

        if args.verbose:
            print("=" * 60)
            print("数据预处理完成")
            print("=" * 60)
            print(f"目标国家: {preprocessed.run_config.target_country}")
            print(f"品牌名称: {preprocessed.run_config.brand_name}")
            print(f"核心卖点 ({len(preprocessed.core_selling_points)}个):")
            for i, point in enumerate(preprocessed.core_selling_points, 1):
                print(f"  {i}. {point}")
            print(f"配件描述状态: {preprocessed.accessory_descriptions}")
            print(f"质量评分: {preprocessed.quality_score}/100")
            print(f"输出文件: {args.output}")

        print(f"预处理完成，结果已保存到 {args.output}")

    except Exception as e:
        print(f"预处理失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
