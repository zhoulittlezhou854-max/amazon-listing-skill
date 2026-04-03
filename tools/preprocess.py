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
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path


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
    core_selling_points_raw: str = ""
    accessory_params_raw: str = ""
    input_files: Optional[Dict[str, str]] = None

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'RunConfig':
        """从字典创建RunConfig"""
        return cls(
            target_country=config_dict.get("target_country", ""),
            brand_name=config_dict.get("brand_name", DEFAULT_BRAND),
            core_selling_points_raw=config_dict.get("core_selling_points_raw", ""),
            accessory_params_raw=config_dict.get("accessory_params_raw", ""),
            input_files=config_dict.get("input_files")
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
    review_count: int = 0               # 评论抽取关键词数
    top_keywords: List[Dict[str, Any]] = []  # Top 20 高搜索量关键词（本地词）
    data_mode: str = "SYNTHETIC_COLD_START"  # 基于真实数据量判断


@dataclass
class PreprocessedData:
    """预处理后的完整数据"""
    run_config: RunConfig
    attribute_data: AttributeData
    keyword_data: KeywordData
    review_data: ReviewData
    aba_data: ABAData
    real_vocab: Optional[RealVocabData] = None  # 真实国家词表（Priority 1）
    core_selling_points: List[str]
    accessory_descriptions: List[Dict[str, Any]]
    quality_score: int
    language: str  # target_language from COUNTRY_LANGUAGE_MAP
    target_country: str
    reasoning_language: str = "EN"  # PRD v8.2: 固定为EN
    data_mode: str = "SYNTHETIC_COLD_START"  # DATA_DRIVEN or SYNTHETIC_COLD_START
    processed_at: str = ""


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
    读取CSV文件，支持多种表头格式
    """
    data = []

    if not os.path.exists(file_path):
        return data

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # 检测编码和分隔符
            sample = f.read(1024)
            f.seek(0)

            # 尝试推断分隔符
            delimiter = ','
            if '\t' in sample and sample.count('\t') > sample.count(','):
                delimiter = '\t'

            # 读取CSV
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                cleaned_row = {}
                for key, value in row.items():
                    if key:
                        cleaned_key = key.strip()
                        cleaned_value = value.strip() if value else ""
                        cleaned_row[cleaned_key] = cleaned_value
                data.append(cleaned_row)
    except Exception as e:
        print(f"读取CSV文件出错 {file_path}: {e}", file=sys.stderr)

    return data


def read_keyword_table(file_path: str) -> KeywordData:
    """
    读取关键词表（竞品出单词表）
    支持两种格式：26字段德语格式和其他格式
    """
    raw_data = read_csv_file(file_path)

    # 标准化字段名
    standard_data = []
    for row in raw_data:
        standardized = {}

        # 字段映射
        field_mapping = {
            "keyword": ["keyword", "关键词", "search_term"],
            "search_volume": ["search_volume", "月搜索量", "volume"],
            "conversion_rate": ["conversion_rate", "购买率", "cvr"],
            "avg_price": ["avg_price", "均价", "price"],
            "monthly_purchases": ["monthly_purchases", "购买量", "purchases"]
        }

        for std_field, possible_names in field_mapping.items():
            for name in possible_names:
                if name in row:
                    standardized[std_field] = row[name]
                    break

        # 数值清洗
        for field in ["search_volume", "conversion_rate", "avg_price", "monthly_purchases"]:
            if field in standardized:
                value = standardized[field]
                if value:
                    # 移除千分位逗号、百分比符号等
                    cleaned = re.sub(r'[%,]', '', value)
                    try:
                        if '.' in cleaned:
                            standardized[field] = float(cleaned)
                        else:
                            standardized[field] = int(cleaned)
                    except ValueError:
                        standardized[field] = 0

        standard_data.append(standardized)

    return KeywordData(keywords=standard_data)


def read_aba_table(file_path: str) -> ABAData:
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
                if value:
                    cleaned = re.sub(r'[%,]', '', value)
                    try:
                        if '.' in cleaned:
                            standardized[field] = float(cleaned)
                        else:
                            standardized[field] = int(cleaned)
                    except ValueError:
                        standardized[field] = 0

        standard_data.append(standardized)

    return ABAData(trends=standard_data)


def read_review_table(file_path: str) -> ReviewData:
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

    return ReviewData(insights=insights)


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

    descriptions = []

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

        descriptions.append({
            "name": accessory_type or "其他配件",
            "specification": item,
            "original": item,
            "params": params
        })

    return descriptions


def extract_accessories_from_attributes(attr_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    从属性表included_components字段自动提取配件描述
    """
    if not attr_data or "included_components" not in attr_data:
        return []

    components_text = str(attr_data["included_components"])
    descriptions = []

    # 分割逗号分隔的列表
    components = [c.strip() for c in components_text.split(",") if c.strip()]

    for comp in components:
        # 查找配件类型
        accessory_type = None
        for eng, chi in ACCESSORY_TYPES.items():
            if eng.lower() in comp.lower():
                accessory_type = chi
                break

        descriptions.append({
            "name": accessory_type or "其他配件",
            "specification": comp,
            "original": comp,
            "params": {}
        })

    return descriptions


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
    if accessory_status == "parsed":
        score += 20
    elif accessory_status == "explicitly_skipped":
        score += 15
    elif accessory_status == "auto_extracted":
        score += 10

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

    从 language_data/DE/*.csv 和 language_data/FR/*.csv 读取
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
    attribute_data = read_attribute_table(attribute_path) if attribute_path else {}
    keyword_data = read_keyword_table(keyword_path) if keyword_path else KeywordData(keywords=[])
    review_data = read_review_table(review_path) if review_path else ReviewData(insights=[])
    aba_data = read_aba_table(aba_path) if aba_path else ABAData(trends=[])

    # 3b. 加载真实国家词表（Priority 1，DE/FR 专用）
    real_vocab = None
    target_ctry = run_config.target_country.upper()
    if target_ctry in ("DE", "FR"):
        real_vocab = load_real_country_vocab(target_ctry)

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
    if run_config.accessory_params_raw == "":  # 显式跳过
        accessory_descriptions = []
        accessory_status = "explicitly_skipped"
    elif run_config.accessory_params_raw:  # 用户提供了配件描述
        accessory_descriptions = extract_accessories_from_text(run_config.accessory_params_raw)
        accessory_status = "parsed"
    else:  # 未提供，尝试自动提取
        accessory_descriptions = extract_accessories_from_attributes(attribute_data)
        accessory_status = "auto_extracted" if accessory_descriptions else "missing"

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
        attribute_data=AttributeData(data=attribute_data),
        keyword_data=keyword_data,
        review_data=review_data,
        aba_data=aba_data,
        real_vocab=real_vocab,
        core_selling_points=core_selling_points,
        accessory_descriptions=accessory_descriptions,
        quality_score=quality_score,
        language=target_language,
        target_country=run_config.target_country,
        reasoning_language="EN",
        data_mode=data_mode,
        processed_at=datetime.datetime.now().isoformat()
    )

    # 8. 输出到文件（如果指定了输出路径）
    if output_path:
        output_dict = {
            "preprocessed_data": {
                "run_config": {
                    "target_country": run_config.target_country,
                    "brand_name": run_config.brand_name,
                    "core_selling_points_raw": run_config.core_selling_points_raw,
                    "accessory_params_raw": run_config.accessory_params_raw,
                    "selling_points_source": selling_points_source,
                    "accessory_status": accessory_status
                },
                "attribute_data": attribute_data,
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
                "accessory_descriptions": accessory_descriptions,
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
                "data_mode_note": f"ABA rows: {len(aba_data.trends)}, Review rows: {len(review_data.insights)}, Total: {total_data_rows}",
                "processed_at": preprocessed.processed_at
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
            }
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