#!/usr/bin/env python3
"""
真实国家词表加载器 (Priority 1 关键词来源)
从 data/raw/<country>/ 目录读取 DE/FR 的真实 ABA / 出单词 / 模板词库。

词源优先级：
  Priority 1: 真实 target-country 词表（aba / 出单词 / review / template 抽取）
  Priority 2: 从真实词表归一的英文 intent/capability labels
  Priority 3: 语言映射表（CAPABILITY_TRANSLATIONS 等）
  Priority 4: [SYNTH]

关键词来源标记：
  - "aba"        → ABA 关键词表
  - "order_winning" → 出单词表
  - "template"  → 长尾模板关键词
  - "review"     → 全维度评论表抽取
  - "synthetic"  → 合成关键词（Fallback）
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 加载路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.data_loader import load_table, standardize_keywords, KEYWORD_FIELD_MAP


# ============================================================
# 路径常量
# ============================================================

_DATA_RAW_ROOT = Path(__file__).parent.parent / "data" / "raw"
_DE_LANG_ROOT = _DATA_RAW_ROOT / "de" / "DE"
_FR_LANG_ROOT = _DATA_RAW_ROOT / "fr" / "FR"
_US_LANG_ROOT = _DATA_RAW_ROOT / "us" / "US"
_UK_LANG_ROOT = _DATA_RAW_ROOT / "uk" / "UK"
_ES_LANG_ROOT = _DATA_RAW_ROOT / "es" / "ES"
_IT_LANG_ROOT = _DATA_RAW_ROOT / "it" / "IT"
_SHARED_LANG_ROOT = _DATA_RAW_ROOT / "shared"


# ============================================================
# 国家配置
# ============================================================

COUNTRY_CONFIGS: Dict[str, Dict[str, Any]] = {
    "DE": {
        "aba_files": [
            _DE_LANG_ROOT / "H88_DE_ABA_Merged.csv",
            _DE_LANG_ROOT / "T70M_DE_ABA关键词表_数据表.csv",
            _DE_LANG_ROOT / "ActionCam_DE_ABA_20260407.csv",
            _DE_LANG_ROOT / "KeywordList_DE_ABA_20260408.csv",
        ],
        "order_winning_files": [
            _DE_LANG_ROOT / "H88_DE_出单词表.csv",
            _DE_LANG_ROOT / "T70M_DE_出单词表_数据表.csv",
        ],
        "template_files": [
            _DE_LANG_ROOT / "de_longtail_template_keywords.csv",
        ],
        "review_file": _SHARED_LANG_ROOT / "H88_全维度表格_评论未合并.csv",
    },
    "FR": {
        "aba_files": [
            _FR_LANG_ROOT / "H88_FR_ABA.csv",
            _FR_LANG_ROOT / "T70M_FR_ABA关键词表_数据表.csv",
            _FR_LANG_ROOT / "ActionCam_FR_ABA_20260407.csv",
        ],
        "order_winning_files": [
            _FR_LANG_ROOT / "T70M_FR_出单词表_数据表.csv",
            # H88_FR_出单词.xlsx 通过 data_loader 读取（见下方）
            _FR_LANG_ROOT / "H88_FR_出单词.xlsx",
        ],
        "template_files": [
            _FR_LANG_ROOT / "fr_longtail_template_keywords.csv",
        ],
        "review_file": _SHARED_LANG_ROOT / "H88_全维度表格_评论未合并.csv",
    },
    "US": {
        "aba_files": [
            _US_LANG_ROOT / "ActionCam_US_ABA_20260407.csv",
        ],
        "order_winning_files": [],
        "template_files": [],
        "review_file": None,
    },
    "UK": {
        "aba_files": [
            _UK_LANG_ROOT / "ActionCam_UK_ABA_20260407.csv",
        ],
        "order_winning_files": [],
        "template_files": [],
        "review_file": None,
    },
    "ES": {
        "aba_files": [
            _ES_LANG_ROOT / "ActionCam_ES_ABA_20260407.csv",
        ],
        "order_winning_files": [],
        "template_files": [],
        "review_file": None,
    },
    "IT": {
        "aba_files": [
            _IT_LANG_ROOT / "ActionCam_IT_ABA_20260407.csv",
        ],
        "order_winning_files": [],
        "template_files": [],
        "review_file": None,
    },
}

# 模型/产品线映射（用于标注关键词来源的产品线）
MODEL_CONFIGS: Dict[str, List[str]] = {
    "H88": ["H88_DE_ABA_Merged", "H88_DE_出单词表", "H88_FR_ABA", "H88_FR_出单词"],
    "T70M": ["T70M_DE_ABA关键词表", "T70M_DE_出单词表", "T70M_FR_ABA关键词表", "T70M_FR_出单词表"],
}


# ============================================================
# 核心数据结构
# ============================================================

@dataclass
class CountryKeywordEntry:
    """单条关键词记录"""
    keyword: str
    source_type: str       # "aba" | "order_winning" | "review" | "template"
    source_file: str       # 来源文件名
    model: str             # "H88" | "T70M" | "H88_全维度"
    country: str           # "DE" | "FR"
    search_volume: Optional[float] = None
    conversion_rate: Optional[float] = None
    avg_cpc: Optional[float] = None
    spr: Optional[float] = None
    title_density: Optional[float] = None
    click_concentration: Optional[float] = None
    conv_concentration: Optional[float] = None
    ac_recommend: Optional[str] = None
    tags: Optional[str] = None
    product_count: Optional[int] = None
    rating_value: Optional[float] = None
    tier: Optional[str] = None
    # 原始行（保留给特殊字段使用）
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "model": self.model,
            "country": self.country,
            "search_volume": self.search_volume,
            "conversion_rate": self.conversion_rate,
            "avg_cpc": self.avg_cpc,
            "spr": self.spr,
            "title_density": self.title_density,
            "click_concentration": self.click_concentration,
            "conv_concentration": self.conv_concentration,
            "ac_recommend": self.ac_recommend,
            "tags": self.tags,
            "product_count": self.product_count,
            "rating_value": self.rating_value,
        }


# ============================================================
# 核心加载函数
# ============================================================

def _detect_model_from_filename(filename: str) -> str:
    """从文件名推断产品型号"""
    fn_lower = filename.lower()
    if "h88" in fn_lower:
        return "H88"
    elif "t70m" in fn_lower or "t70" in fn_lower:
        return "T70M"
    else:
        return "Unknown"


def _detect_source_type(filename: str) -> str:
    """从文件名推断来源类型"""
    fn_lower = filename.lower()
    if "aba" in fn_lower:
        return "aba"
    elif "template" in fn_lower or "模板" in filename or "长尾" in filename:
        return "template"
    elif any(kw in fn_lower for kw in ["出单词", "order", "winning"]):
        return "order_winning"
    elif "全维度" in filename or "review" in fn_lower or "评论" in filename:
        return "review"
    return "unknown"


def _load_single_file(file_path: Path, country: str) -> List[CountryKeywordEntry]:
    """加载单个词表文件"""
    if not file_path.exists():
        print(f"[country_vocab] ⚠️  文件不存在，跳过: {file_path}")
        return []

    filename = file_path.name
    source_type = _detect_source_type(filename)
    model = _detect_model_from_filename(filename)

    try:
        raw_rows = load_table(str(file_path))
    except Exception as e:
        print(f"[country_vocab] ⚠️  加载失败 {file_path}: {e}", file=sys.stderr)
        return []

    entries = []
    # 对关键词表进行标准化
    if source_type in ("aba", "order_winning"):
        std_rows = standardize_keywords(raw_rows)
    elif source_type == "template":
        std_rows = [_normalize_template_row(row) for row in raw_rows]
    else:
        # review/全维度表使用通用字段映射
        std_rows = raw_rows

    for row in std_rows:
        # 提取关键词（优先用 keyword 字段）
        kw = (
            row.get("keyword")
            or row.get("关键词")
            or row.get("search_term")
            or row.get("Search Term")
        )
        if not kw or str(kw).strip() == "":
            continue

        # 对于全维度表，country 字段在行内（Country 列）
        entry_country = str(
            row.get("country")
            or row.get("Country")
            or row.get("marketplace")
            or row.get("Marketplace")
            or country
        ).strip().upper()
        if not entry_country:
            entry_country = country
        # 只保留目标国家的评论数据
        if source_type == "review" and entry_country and entry_country != country:
            # 全维度表的 review 条目需要按 country 过滤
            pass  # 保留，后面会过滤

        # 过滤非目标国家的 review 条目
        if source_type == "review":
            entry_country_val = str(row.get("country") or row.get("Country") or "")
            if entry_country_val and entry_country_val != country:
                continue

        entry_model = model
        if source_type == "template":
            entry_model = str(row.get("root_word") or row.get("cluster_type") or "Template").strip() or "Template"

        entry = CountryKeywordEntry(
            keyword=str(kw).strip(),
            source_type=source_type,
            source_file=filename,
            model=entry_model,
            country=entry_country if source_type != "review" else entry_country,
            search_volume=_float(row.get("search_volume")),
            conversion_rate=_float(row.get("conversion_rate")),
            avg_cpc=_float(row.get("avg_cpc")),
            spr=_float(row.get("spr")),
            title_density=_float(row.get("title_density")),
            click_concentration=_float(row.get("click_concentration")),
            conv_concentration=_float(row.get("conv_concentration")),
            ac_recommend=row.get("ac_recommend") or row.get("AC推荐词") or row.get("notes"),
            tags=row.get("tags") or row.get("标签") or row.get("cluster_type"),
            product_count=_int(row.get("product_count")),
            rating_value=_float(row.get("rating_value")),
            tier=_normalize_tier(row),
            raw=row,
        )
        entries.append(entry)

    print(
        f"[country_vocab] {country}: {filename} ({source_type}) → {len(entries)} rows",
        file=sys.stderr,
    )

    return entries


def _float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _int(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _normalize_tier(row: Dict[str, Any]) -> Optional[str]:
    tier_val = (
        row.get("tier")
        or row.get("Tier")
        or row.get("TIER")
        or row.get("level")
        or row.get("Level")
    )
    if not tier_val:
        return None
    normalized = str(tier_val).strip().upper()
    if normalized in {"L1", "L2", "L3"}:
        return normalized
    return None


def _normalize_template_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """将模板词库行字段映射到标准字段名"""
    normalized = dict(row)

    def _copy_if_missing(target: str, *candidates: str):
        if normalized.get(target) not in (None, "", "None"):
            return
        for key in candidates:
            value = normalized.get(key)
            if value not in (None, "", "None"):
                normalized[target] = value
                return

    _copy_if_missing("country", "marketplace", "Marketplace", "站点")
    _copy_if_missing("search_volume", "searches", "Searches")
    _copy_if_missing("conversion_rate", "purchase_rate", "purchaseRate")
    _copy_if_missing("avg_cpc", "bid")
    _copy_if_missing("product_count", "products")
    _copy_if_missing("spr", "supply_demand_ratio")
    _copy_if_missing("click_concentration", "monopoly_click_rate")
    _copy_if_missing("tags", "cluster_type")

    if normalized.get("country"):
        normalized["country"] = str(normalized["country"]).strip().upper()

    return normalized


# ============================================================
# 主加载函数
# ============================================================

def load_country_vocab(country: str) -> Dict[str, List[CountryKeywordEntry]]:
    """
    加载指定国家的完整词表数据。

    Returns:
        {
            "aba": [...],           # ABA 关键词
            "order_winning": [...], # 出单词
            "review": [...],       # 从评论抽取的关键词（仅含目标国家）
            "all": [...],           # 合并所有来源
        }
    """
    config = COUNTRY_CONFIGS.get(country.upper())
    if not config:
        raise ValueError(f"未支持的国家: {country}，仅支持 {list(COUNTRY_CONFIGS.keys())}")

    country = country.upper()
    result: Dict[str, List[CountryKeywordEntry]] = {
        "aba": [],
        "order_winning": [],
        "template": [],
        "review": [],
        "all": [],
    }

    # 加载 ABA 文件
    for fpath in config.get("aba_files", []):
        entries = _load_single_file(fpath, country)
        result["aba"].extend(entries)
        result["all"].extend(entries)

    # 加载出单词文件
    for fpath in config.get("order_winning_files", []):
        entries = _load_single_file(fpath, country)
        result["order_winning"].extend(entries)
        result["all"].extend(entries)

    # 加载模板长尾词库
    for fpath in config.get("template_files", []):
        entries = _load_single_file(fpath, country)
        result["template"].extend(entries)
        result["all"].extend(entries)

    # 加载全维度评论表（按国家过滤）
    review_file = config.get("review_file")
    if review_file:
        entries = _load_single_file(review_file, country)
        # review entries 已在上游按 country 过滤
        result["review"].extend(entries)
        result["all"].extend(entries)

    # 全局去重（按 keyword + source_type）
    seen: set = set()
    deduped_all: List[CountryKeywordEntry] = []
    for e in result["all"]:
        key = (e.keyword.lower(), e.source_type)
        if key not in seen:
            seen.add(key)
            deduped_all.append(e)
    result["all"] = deduped_all

    return result


def build_vocab_index(
    vocab: Dict[str, List[CountryKeywordEntry]]
) -> Dict[str, CountryKeywordEntry]:
    """
    构建关键词 → 条目 的快速索引（取搜索量最高的条目）
    用于文案生成时快速查找本地词
    """
    index: Dict[str, CountryKeywordEntry] = {}
    for entry in vocab.get("all", []):
        key = entry.keyword.lower()
        existing = index.get(key)
        if existing is None:
            index[key] = entry
        else:
            # 取搜索量更高的
            if (entry.search_volume or 0) > (existing.search_volume or 0):
                index[key] = entry
    return index


# ============================================================
# 场景/能力关键词分组
# ============================================================

# 英文能力标签 → 本地语言关键词匹配模式
# 用于从真实词表中提取属于特定能力/场景的关键词
CAPABILITY_KEYWORD_PATTERNS: Dict[str, List[str]] = {
    "4K_video": [
        "4k", "4k video", "4k recording", "4k cam", "uhd",
        "4k拍摄", "4k录像", "4k视频",
        "enregistrement 4k", "vidéo 4k", "caméra 4k",
        "4k-aufzeichnung", "4k-video", "actionkamera 4k",
    ],
    "waterproof": [
        "waterproof", "water proof", "underwater", "diving", "dive cam",
        "30m", "防水", "潜水",
        "étanche", "imperméable", "plongée", "水下",
        "wasserdicht", "tauch", "unterwasser",
    ],
    "stabilization": [
        "stabilization", "eis", "stabilizer", "防抖", "电子防抖",
        "stabilisation", "stabilisation électronique",
        "stabilisierung", "bildstabilisierung",
    ],
    "wifi_connectivity": [
        "wifi", "wi-fi", "wireless", "app", "WiFi",
        "连接", "无线",
        "wifi", "connexion wifi", "sans fil",
        "wlan", "verbindung", "funk",
    ],
    "dual_screen": [
        "dual screen", "double screen", "双屏幕", "前后屏",
        "double écran", "écran avant",
        "zweibildschirm", "vorne display",
    ],
    "long_battery_life": [
        "battery", "150min", "180min", "batterie", "autonomie",
        "电池", "续航", "持久",
        "batterie", "autonomie", "durée",
        "akku", "laufzeit", "batterielebensdauer",
    ],
    "outdoor_sports": [
        "sports", "sport cam", "outdoor", "cycling", "bike", "helmet",
        "骑行", "户外", "滑雪", "登山",
        "sport", "cyclisme", "extérieure", "plein air",
        "sport", "fahrrad", "außen", "outdoor",
    ],
    "mounting": [
        "mount", "mounting", "bracket", "holder", "strap",
        "支架", "挂绳", "底座", "安装",
        "montage", "support", "fixation",
        "halterung", "befestigung", "gurt",
    ],
}


def find_keywords_for_capability(
    capability: str,
    vocab_index: Dict[str, CountryKeywordEntry]
) -> List[CountryKeywordEntry]:
    """查找与特定能力相关的所有本地关键词"""
    patterns = CAPABILITY_KEYWORD_PATTERNS.get(capability, [])
    results = []
    kw_lower = {k: v for k, v in vocab_index.items()}
    for pattern in patterns:
        pl = pattern.lower()
        for kw, entry in kw_lower.items():
            if pl in kw or kw in pl:
                results.append(entry)
    # 去重
    seen = set()
    deduped = []
    for e in results:
        if e.keyword.lower() not in seen:
            seen.add(e.keyword.lower())
            deduped.append(e)
    return sorted(deduped, key=lambda x: x.search_volume or 0, reverse=True)


def find_high_volume_keywords(
    vocab: Dict[str, List[CountryKeywordEntry]],
    min_volume: float = 0,
    top_n: int = 20
) -> List[CountryKeywordEntry]:
    """获取搜索量最高的前 N 条关键词。

    Keyword tiering is handled by modules.keyword_protocol; this helper should
    not impose the old 1000-volume tier gate by default.
    """
    all_entries = vocab.get("all", [])
    ranked = sorted(
        [e for e in all_entries if (e.search_volume or 0) >= min_volume],
        key=lambda x: x.search_volume or 0,
        reverse=True
    )
    result = ranked[:top_n]
    seen = {
        (e.keyword.lower(), e.source_type, e.source_file)
        for e in result
    }
    for entry in all_entries:
        if entry.tier and entry.tier.upper() in {"L1", "L2", "L3"}:
            key = (entry.keyword.lower(), entry.source_type, entry.source_file)
            if key not in seen:
                result.append(entry)
                seen.add(key)
    return result


# ============================================================
# CLI 测试入口
# ============================================================

if __name__ == "__main__":
    import json

    for country in ["DE", "FR"]:
        print(f"\n{'='*50}")
        print(f"加载国家词表: {country}")
        print(f"{'='*50}")
        try:
            vocab = load_country_vocab(country)
            print(f"  ABA 关键词:        {len(vocab['aba'])} 条")
            print(f"  出单词:            {len(vocab['order_winning'])} 条")
            print(f"  模板长尾词:        {len(vocab['template'])} 条")
            print(f"  评论抽取关键词:    {len(vocab['review'])} 条")
            print(f"  合计（去重后）:    {len(vocab['all'])} 条")

            # 显示 Top 5 关键词
            top5 = find_high_volume_keywords(vocab, top_n=5)
            print(f"\n  Top 5 高搜索量关键词:")
            for e in top5:
                print(f"    [{e.source_type}] {e.keyword}: vol={e.search_volume}")
        except Exception as ex:
            print(f"  错误: {ex}")
