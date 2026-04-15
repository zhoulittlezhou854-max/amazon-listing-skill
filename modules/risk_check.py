#!/usr/bin/env python3
"""
风险检查模块 (Step 7)
版本: v1.0
功能: 三层风险检查：合规红线、writing_policy审计、Rufus幻觉风险
"""

import re
from typing import Dict, List, Any, Optional

from modules import fluency_check as fc
from modules import coherence_check as cc
from modules.language_utils import get_scene_display
from modules.listing_status import build_review_queue, derive_listing_status
from modules.retention_guard import calculate_retention_report
from tools.preprocess import standardize_attribute_data, derive_capability_constraints


LANGUAGE_SENTINELS = {
    "french": [" avec ", " pour ", " camera", " et ", " votre ", " etanche", "étanche", "caméra", "prise"],
    "german": [" mit ", " für ", " und ", "aufnahme", "wasserdicht", "kamera", "stabil"],
    "spanish": [" con ", " para ", " y ", "camara", "cámara", "impermeable"],
    "italian": [" con ", " per ", " e ", "fotocamera", "impermeabile"],
}

ENGLISH_SENTINELS = [" the ", " with ", " for ", " your ", " and ", "camera", "recording"]
CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
WATERPROOF_TOKENS = ["waterproof", "防水", "étanche", "wasserdicht", "impermeable"]
HOUSING_TOKENS = ["housing", "case", "boîtier", "caisson", "壳", "carcasa", "custodia"]
STABILIZATION_TOKENS = ["stabilization", "stabilisation", "防抖", "eis", "bildstabilisierung"]
WIFI_TOKENS = ["wifi", "wi-fi", "wlan", "无线"]
DUAL_SCREEN_TOKENS = ["dual screen", "dual-screen", "双屏", "double screen"]
LIVE_STREAMING_TOKENS = ["live stream", "live streaming", "直播", "livestream"]
VOICE_CONTROL_TOKENS = ["voice control", "voice command", "语音控制"]
FLUENCY_HEADER_TRAILING_PREPOSITIONS = {"with", "for", "and", "or", "of"}
FLUENCY_DASH_CHARS = ("—", "–")
FLUENCY_REPEAT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "you",
    "camera",
    "action",
    "audio",
    "video",
    "record",
    "recording",
}
FLUENCY_CONTENT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "you",
}
FLUENCY_INDEPENDENT_STARTERS = {
    "capture",
    "document",
    "record",
    "create",
    "share",
    "take",
    "keep",
    "use",
    "enjoy",
    "you",
    "this",
    "it",
}
FLUENCY_VERB_HINTS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "can",
    "could",
    "will",
    "would",
    "should",
    "may",
    "might",
    "must",
    "do",
    "does",
    "did",
    "captures",
    "capture",
    "documents",
    "document",
    "records",
    "record",
    "keeps",
    "keep",
    "supports",
    "support",
    "delivers",
    "deliver",
}


def _visible_text(generated_copy: Dict[str, Any]) -> str:
    fields = [
        generated_copy.get("title", ""),
        " ".join(generated_copy.get("bullets", []) or []),
        generated_copy.get("description", ""),
    ]
    return " ".join(text for text in fields if text).strip()


def _all_text(generated_copy: Dict[str, Any]) -> str:
    parts = [_visible_text(generated_copy), generated_copy.get("aplus_content", "")]
    for faq_item in generated_copy.get("faq", []) or []:
        parts.append(faq_item.get("q", ""))
        parts.append(faq_item.get("a", ""))
    return " ".join(text for text in parts if text).strip()


def _extract_backend_only_terms(writing_policy: Dict[str, Any]) -> List[str]:
    directives = writing_policy.get("compliance_directives", {}) or {}
    search_plan = writing_policy.get("search_term_plan", {}) or {}
    terms = []
    terms.extend(directives.get("backend_only_terms", []) or [])
    terms.extend(search_plan.get("backend_only_terms", []) or [])
    return list(dict.fromkeys(term for term in terms if term))


def _extract_taboo_terms(writing_policy: Dict[str, Any]) -> List[str]:
    directives = writing_policy.get("compliance_directives", {}) or {}
    search_plan = writing_policy.get("search_term_plan", {}) or {}
    terms = []
    terms.extend(directives.get("taboo_terms", []) or [])
    terms.extend(search_plan.get("taboo_terms", []) or [])
    return list(dict.fromkeys(term for term in terms if term))


def _extract_faq_only_terms(writing_policy: Dict[str, Any]) -> List[str]:
    terms = writing_policy.get("faq_only_capabilities", []) or []
    return list(dict.fromkeys(str(term).strip() for term in terms if str(term).strip()))


def _contains_any_token(text: str, tokens: List[str]) -> bool:
    lowered = (text or "").lower()
    return any(token and token.lower() in lowered for token in tokens)


def _scene_aliases(scene_code: str, language: str) -> List[str]:
    aliases: List[str] = []
    if not scene_code:
        return aliases
    aliases.append(scene_code.replace("_", " ").lower())
    aliases.append(scene_code.lower())
    localized = (get_scene_display(scene_code, language) or "").strip().lower()
    if localized:
        aliases.append(localized)
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _split_header_body(text: str) -> tuple[str, str]:
    value = str(text or "").strip()
    for separator in [" — ", " – ", " - "]:
        if separator in value:
            header, body = value.split(separator, 1)
            return header.strip(), body.strip()
    return "", value


def _tokenize_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ']+", (text or "").lower())


def _normalize_word_root(token: str) -> str:
    value = str(token or "").lower().replace("'", "").strip()
    if len(value) <= 3:
        return value
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[:-len(suffix)]
    return value


def _content_roots(text: str) -> set[str]:
    roots: set[str] = set()
    for token in _tokenize_words(text):
        root = _normalize_word_root(token)
        if len(root) < 3 or root in FLUENCY_CONTENT_STOPWORDS:
            continue
        roots.add(root)
    return roots


def _looks_like_noun_phrase(text: str) -> bool:
    tokens = _tokenize_words(text)
    if not tokens or len(tokens) > 8:
        return False
    for token in tokens:
        root = _normalize_word_root(token)
        if root in FLUENCY_VERB_HINTS:
            return False
    return True


def _contains_predicate(text: str) -> bool:
    tokens = _tokenize_words(text)
    for token in tokens:
        root = _normalize_word_root(token)
        if root in FLUENCY_VERB_HINTS:
            return True
    return bool(re.search(r"\b\w+(ed|ing)\b", text or "", flags=re.IGNORECASE))


def _semantic_rupture(header: str, body: str) -> bool:
    if not header or not body:
        return False
    if not _looks_like_noun_phrase(header):
        return False
    body_tokens = _tokenize_words(body)
    if len(body_tokens) < 5:
        return False
    if body_tokens[0] not in FLUENCY_INDEPENDENT_STARTERS:
        return False
    if not _contains_predicate(body):
        return False
    header_roots = _content_roots(header)
    body_roots = _content_roots(body)
    if len(header_roots) < 2 or len(body_roots) < 3:
        return False
    return len(header_roots.intersection(body_roots)) == 0


def _has_dangling_dash(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    return any(stripped.endswith(dash) for dash in FLUENCY_DASH_CHARS)


def _dash_tail_without_predicate(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    parts = re.split(r"\s*[—–]\s*", value)
    if len(parts) < 2:
        return False
    tail = parts[-1].strip().strip(".,;:!?")
    if not tail:
        return False
    tail_tokens = _tokenize_words(tail)
    if not tail_tokens or len(tail_tokens) > 5:
        return False
    if not all(re.match(r"^[A-Za-z0-9]+$", token) for token in tail_tokens):
        return False
    return not _contains_predicate(tail)


def _repeated_word_roots(text: str) -> List[str]:
    counts: Dict[str, int] = {}
    for token in _tokenize_words(text):
        root = _normalize_word_root(token)
        if len(root) < 4 or root in FLUENCY_REPEAT_STOPWORDS:
            continue
        counts[root] = counts.get(root, 0) + 1
    return sorted(root for root, count in counts.items() if count > 2)


def _check_fluency(generated_copy: Dict[str, Any], writing_policy: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    _ = writing_policy or {}
    issues: List[Dict[str, Any]] = []
    bullets = generated_copy.get("bullets", []) or []

    for idx, bullet in enumerate(bullets, start=1):
        field_name = f"bullet_b{idx}"
        for issue in fc.check_fluency(field_name, str(bullet or "")):
            description = issue.message
            if issue.rule_id == "header_body_rupture":
                description = f"B{idx} Header 与正文语义断裂，像两个独立句拼接"
            issues.append(
                {
                    "rule": f"fluency_{issue.rule_id}",
                    "description": description,
                    "severity": issue.severity,
                    "field": field_name,
                }
            )

    for field_name in ["title", "aplus_content"]:
        text = str(generated_copy.get(field_name, "") or "")
        if not text:
            continue
        for issue in fc.check_fluency(field_name, text):
            if issue.rule_id == "repeated_word_root":
                continue
            issues.append(
                {
                    "rule": f"fluency_{issue.rule_id}",
                    "description": issue.message,
                    "severity": issue.severity,
                    "field": field_name,
                }
            )

    return issues


def collect_fluency_issues(generated_copy: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Public helper for scoring and diagnostics; keeps fluency logic in one place."""
    return _check_fluency(generated_copy, {})


def _check_coherence_risks(generated_copy: Dict[str, Any]) -> List[Dict[str, Any]]:
    bullets = generated_copy.get("bullets") or []
    issues: List[Dict[str, Any]] = []
    for issue in cc.check_coherence(
        str(generated_copy.get("title") or ""),
        bullets,
        str(generated_copy.get("aplus_content") or ""),
    ):
        issues.append(
            {
                "issue_type": issue.issue_type,
                "rule": f"coherence_{issue.issue_type}",
                "description": issue.message,
                "severity": issue.severity,
                "fields": issue.fields,
            }
        )
    return issues


def _extract_production_warnings(generated_copy: Dict[str, Any], writing_policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    copy_contracts = writing_policy.get("copy_contracts", {}) or {}
    bullets = generated_copy.get("bullets", []) or []
    bullet_opening = copy_contracts.get("bullet_opening", {}) or {}
    weak_openers = {str(item).strip().lower() for item in (bullet_opening.get("forbidden_weak_openers") or []) if str(item).strip()}

    opener_counter: Dict[str, int] = {}
    for idx, bullet in enumerate(bullets, start=1):
        header, body = _split_header_body(bullet)
        if not header or not body:
            warnings.append(
                {
                    "rule": "bullet_format_contract",
                    "description": f"B{idx} 缺少大写前缀或长破折号结构，发布感不足",
                    "severity": "low",
                }
            )
            continue
        first_token = next(iter(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", body.lower())), "")
        if first_token:
            opener_counter[first_token] = opener_counter.get(first_token, 0) + 1
        if first_token and first_token in weak_openers:
            warnings.append(
                {
                    "rule": "weak_bullet_opener",
                    "description": f"B{idx} 正文以弱介词 '{first_token}' 起句，能力词前置不够明显",
                    "severity": "low",
                }
            )

    repetitive_openers = [token for token, count in opener_counter.items() if token and count >= 3]
    if repetitive_openers:
        warnings.append(
            {
                "rule": "repetitive_bullet_openers",
                "description": f"多个 Bullet 重复使用相同起句 {', '.join(repetitive_openers[:3])}，容易形成 AI 套路感",
                "severity": "low",
            }
        )

    title = generated_copy.get("title", "") or ""
    title_contract = copy_contracts.get("title_dewater", {}) or {}
    weak_connectors = [str(item).strip() for item in (title_contract.get("weak_connectors") or []) if str(item).strip()]
    connector_hits = 0
    for connector in weak_connectors:
        connector_hits += len(re.findall(rf"\b{re.escape(connector)}\b", title, flags=re.IGNORECASE))
    if connector_hits >= 2:
        warnings.append(
            {
                "rule": "title_weak_connector_density",
                "description": "标题中弱连接词使用过多，核心能力与场景前置不够干净",
                "severity": "low",
            }
        )

    occupancy = copy_contracts.get("keyword_slot_occupancy", {}) or {}
    slot_keywords = occupancy.get("bullet_keyword_slots", {}) or {}
    top_slots = occupancy.get("top_conversion_slots", []) or ["B1", "B2", "B3"]
    for idx, slot_name in enumerate(top_slots):
        if idx >= len(bullets):
            break
        bullet_text = str(bullets[idx] or "")
        bullet_lower = bullet_text.lower()
        assigned = [str(item).strip() for item in (slot_keywords.get(slot_name) or []) if str(item).strip()]
        if assigned and not any(keyword.lower() in bullet_lower for keyword in assigned[:2]):
            warnings.append(
                {
                    "rule": "keyword_slot_occupancy_gap",
                    "description": f"{slot_name} 未明显承接分配关键词槽位 {', '.join(assigned[:2])}",
                    "severity": "low",
                }
            )

    return warnings


def _visible_field_fallback_issues(generated_copy: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = generated_copy.get("metadata", {}) or {}
    visible_fields = [str(item).strip() for item in (metadata.get("visible_llm_fallback_fields") or []) if str(item).strip()]
    if not visible_fields:
        return []
    return [
        {
            "rule": "visible_field_fallback",
            "description": "可见文案字段仍使用本地 fallback，无法作为正式上架版本："
            + ", ".join(visible_fields),
            "severity": "high",
        }
    ]


def _language_consistency_issues(generated_copy: Dict[str, Any], target_language: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    target_language = (target_language or "").lower()
    visible = " " + _visible_text(generated_copy).lower() + " "
    if target_language in {"english", "en"}:
        if CHINESE_CHAR_PATTERN.search(visible):
            issues.append(
                {
                    "rule": "语言一致性",
                    "description": "目标语言为 English，但可见文案仍包含大量中文字符",
                    "severity": "medium",
                }
            )
        return issues
    if target_language in {"chinese", "zh"}:
        return issues
    sentinels = LANGUAGE_SENTINELS.get(target_language, [])
    if not sentinels:
        return issues
    hits = sum(1 for token in sentinels if token in visible)
    english_hits = sum(1 for token in ENGLISH_SENTINELS if token in visible)
    if CHINESE_CHAR_PATTERN.search(visible):
        issues.append(
            {
                "rule": "语言一致性",
                "description": f"目标语言为 {target_language}，但可见文案仍包含中文字符",
                "severity": "high",
            }
        )
    if hits == 0:
        issues.append(
            {
                "rule": "语言一致性",
                "description": f"目标语言为 {target_language}，但可见文案缺少明显本地语言特征",
                "severity": "high",
            }
        )
    elif english_hits >= 4 and hits <= 1:
        issues.append(
            {
                "rule": "语言一致性",
                "description": f"目标语言为 {target_language}，但可见文案仍以英语表达为主",
                "severity": "medium",
            }
        )
    return issues


def _truth_consistency_checks(
    generated_copy: Dict[str, Any],
    writing_policy: Dict[str, Any],
    attribute_data: Dict[str, Any],
    capability_constraints: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    normalized_attr = standardize_attribute_data(attribute_data or {})
    constraints = dict(capability_constraints or {})
    if not constraints:
        constraints = derive_capability_constraints(normalized_attr, [])
    visible = _visible_text(generated_copy).lower()
    issues: List[Dict[str, Any]] = []

    backend_only_terms = _extract_backend_only_terms(writing_policy)
    for term in backend_only_terms:
        if term and term.lower() in visible:
            issues.append(
                {
                    "rule": "backend_only_visible",
                    "description": f"backend-only 词 '{term}' 出现在可见文案",
                    "severity": "high",
                }
            )

    taboo_terms = _extract_taboo_terms(writing_policy)
    for term in taboo_terms:
        if term and term.lower() in visible:
            issues.append(
                {
                    "rule": "taboo_term_visible",
                    "description": f"禁用词 '{term}' 出现在可见文案",
                    "severity": "high",
                }
            )

    faq_only_terms = _extract_faq_only_terms(writing_policy)
    for term in faq_only_terms:
        if term and term.lower() in visible:
            issues.append(
                {
                    "rule": "faq_only_visible",
                    "description": f"FAQ-only 能力 '{term}' 出现在可见文案",
                    "severity": "high",
                }
            )

    competitor_terms = ["gopro", "dji", "insta360", "akaso", "sjcam", "osmo"]
    for term in competitor_terms:
        if term in visible:
            issues.append(
                {
                    "rule": "competitor_visible",
                    "description": f"竞品词 '{term}' 出现在可见文案",
                    "severity": "high",
                }
            )

    if _contains_any_token(visible, WATERPROOF_TOKENS) and not constraints.get("waterproof_supported"):
        issues.append(
            {
                "rule": "unsupported_waterproof_claim",
                "description": "文案包含防水宣称，但真值层未支持可见防水",
                "severity": "high",
            }
        )
    if constraints.get("waterproof_supported") and constraints.get("waterproof_requires_case"):
        if _contains_any_token(visible, WATERPROOF_TOKENS) and not _contains_any_token(visible, HOUSING_TOKENS):
            issues.append(
                {
                    "rule": "missing_waterproof_boundary",
                    "description": "防水宣称缺少“需使用防水壳/外壳”边界说明",
                    "severity": "high",
                }
            )

    if _contains_any_token(visible, STABILIZATION_TOKENS) and not constraints.get("stabilization_supported"):
        issues.append(
            {
                "rule": "unsupported_stabilization_claim",
                "description": "文案包含防抖/EIS 宣称，但真值层未支持",
                "severity": "high",
            }
        )
    unsupported_modes = {str(item).lower() for item in constraints.get("forbidden_claims", []) or []}
    if any(mode in visible for mode in unsupported_modes) and _contains_any_token(visible, STABILIZATION_TOKENS):
        issues.append(
            {
                "rule": "mode_conflict_claim",
                "description": "文案在受限模式下仍使用防抖相关宣称",
                "severity": "high",
            }
        )

    if _contains_any_token(visible, WIFI_TOKENS) and not constraints.get("wifi_supported"):
        issues.append(
            {
                "rule": "unsupported_wifi_claim",
                "description": "文案包含 Wi-Fi 宣称，但真值层未支持",
                "severity": "high",
            }
        )
    if _contains_any_token(visible, DUAL_SCREEN_TOKENS) and not constraints.get("dual_screen_supported"):
        issues.append(
            {
                "rule": "unsupported_dual_screen_claim",
                "description": "文案包含双屏宣称，但真值层未支持",
                "severity": "medium",
            }
        )
    if _contains_any_token(visible, LIVE_STREAMING_TOKENS) and not constraints.get("live_streaming_supported"):
        issues.append(
            {
                "rule": "unsupported_live_streaming_claim",
                "description": "文案包含直播功能宣称，但真值层未支持",
                "severity": "high",
            }
        )
    if _contains_any_token(visible, VOICE_CONTROL_TOKENS) and not constraints.get("voice_control_supported"):
        issues.append(
            {
                "rule": "unsupported_voice_control_claim",
                "description": "文案包含语音控制宣称，但真值层未支持",
                "severity": "medium",
            }
        )

    return issues


def check_compliance_redlines(generated_copy: Dict[str, Any], language: str = "Chinese") -> Dict[str, Any]:
    """
    合规红线检查
    检查文案中是否包含禁止内容
    """
    redline_issues = []
    passed_checks = 0
    total_checks = 0

    # 所有文案文本
    all_text = ""
    if "title" in generated_copy:
        all_text += generated_copy["title"] + " "
    if "bullets" in generated_copy:
        all_text += " ".join(generated_copy["bullets"]) + " "
    if "description" in generated_copy:
        all_text += generated_copy["description"] + " "
    if "aplus_content" in generated_copy:
        all_text += generated_copy["aplus_content"] + " "

    # 检查FAQ
    if "faq" in generated_copy:
        for faq_item in generated_copy["faq"]:
            all_text += faq_item.get("q", "") + " " + faq_item.get("a", "") + " "

    all_text = all_text.lower()

    competitor_terms = [
        "gopro",
        "go pro",
        "dji",
        "大疆",
        "insta360",
        "影石",
        "akaso",
        "sjcam",
        "osmo",
    ]
    chinese_compare_pattern = re.compile(r'(比[^。！？]*好|优于[^。！？]*)', re.IGNORECASE)

    # 合规红线规则
    compliance_rules = [
        {
            "name": "联系方式/URL/社交媒体",
            "patterns": [r'@\w+', r'#\w+', r'http[s]?://', r'www\.', r'\.com', r'\.net', r'\.org'],
            "severity": "high",
            "description": "禁止包含联系方式、URL或社交媒体"
        },
        {
            "name": "价格/折扣信息",
            "patterns": [r'\$\d+', r'\bprice\b', r'\bdiscount\b', r'\bsale\b', r'\bdeal\b', r'\bcoupon\b', r'优惠', r'打折', r'促销'],
            "severity": "high",
            "description": "禁止提及价格、折扣或促销信息"
        },
        {
            "name": "竞品贬低",
            "patterns": [r'better than', r'beats', r'vs\.', r'versus', r'compared to', r'打败'],
            "severity": "high",
            "description": "禁止贬低竞争对手"
        },
        {
            "name": "绝对化宣称",
            "patterns": [
                r'100%',
                r'\bbest\b',
                r'#1',
                r'\btop rated\b',
                r'\bhot\b',
                r'\bamazing\b',
                r'完美',
                r'最好',
                r'顶级',
            ],
            "severity": "medium",
            "description": "避免使用绝对化宣称"
        },
        {
            "name": "保证/退款宣称",
            "patterns": [r'guaranteed', r'money back', r'risk-free', r'warranty', r'保证', r'退款', r'无风险'],
            "severity": "medium",
            "description": "谨慎使用保证或退款宣称"
        },
        {
            "name": "运动相机专项禁止",
            "patterns": [r'indestructible', r'military grade', r'bulletproof', r'fully shockproof', r'防弹', r'军用级', r'完全防震'],
            "severity": "high",
            "description": "运动相机专项禁止词汇"
        }
    ]

    # 执行检查
    for rule in compliance_rules:
        total_checks += 1
        found = False
        for pattern in rule["patterns"]:
            if re.search(pattern, all_text, re.IGNORECASE):
                found = True
                redline_issues.append({
                    "rule": rule["name"],
                    "pattern": pattern,
                    "severity": rule["severity"],
                    "description": rule["description"]
                })
                break
        if not found and rule["name"] == "竞品贬低":
            for match in chinese_compare_pattern.finditer(all_text):
                snippet = match.group(0)
                if any(term in snippet for term in competitor_terms):
                    found = True
                    redline_issues.append({
                        "rule": rule["name"],
                        "pattern": "competitor_chinese_comparison",
                        "severity": rule["severity"],
                        "description": rule["description"]
                    })
                    break

        if not found:
            passed_checks += 1

    return {
        "passed": passed_checks,
        "total": total_checks,
        "issues": redline_issues,
        "all_passed": len(redline_issues) == 0
    }


def check_writing_policy_compliance(generated_copy: Dict[str, Any],
                                   writing_policy: Dict[str, Any],
                                   language: str = "Chinese") -> Dict[str, Any]:
    """
    writing_policy审计
    检查文案是否遵循writing_policy中的硬性约束
    """
    policy_issues = []
    passed_checks = 0
    total_checks = 0

    # 1. 检查场景优先级锁定
    total_checks += 1
    scene_priority = writing_policy.get("scene_priority", [])
    if scene_priority:
        # 检查文案中是否按优先级使用场景词
        all_text = ""
        if "title" in generated_copy:
            all_text += generated_copy["title"] + " "
        if "bullets" in generated_copy:
            all_text += " ".join(generated_copy["bullets"]) + " "
        all_text_lower = all_text.lower()
        language = (
            generated_copy.get("metadata", {}).get("target_language")
            or generated_copy.get("metadata", {}).get("language")
            or writing_policy.get("target_language")
            or "English"
        )

        found_scenes = []
        first_scene_index = None
        earliest_hit = None
        for i, scene in enumerate(scene_priority):
            aliases = _scene_aliases(scene, language)
            positions = [all_text_lower.find(alias) for alias in aliases if alias and all_text_lower.find(alias) != -1]
            if positions:
                found_scenes.append(scene)
                scene_pos = min(positions)
                if earliest_hit is None or scene_pos < earliest_hit:
                    earliest_hit = scene_pos
                    first_scene_index = i

        # 检查是否按优先级出现
        top_priority_scenes = set(scene_priority[:3])
        if found_scenes:
            if any(scene in top_priority_scenes for scene in found_scenes):
                passed_checks += 1
            else:
                policy_issues.append({
                    "rule": "场景优先级锁定",
                    "description": f"文案仅命中低优先级场景，首个命中场景为'{found_scenes[0] if found_scenes else '无'}'",
                    "severity": "medium"
                })
        else:
            policy_issues.append({
                "rule": "场景优先级锁定",
                "description": "文案中未使用writing_policy中的场景词",
                "severity": "medium"
            })
    else:
        passed_checks += 1

    # 2. 检查能力场景绑定
    total_checks += 1
    capability_bindings = writing_policy.get("capability_scene_bindings", [])
    if capability_bindings:
        issues_found = False
        for binding in capability_bindings:
            capability = binding.get("capability", "")
            allowed_scenes = binding.get("allowed_scenes", [])
            forbidden_scenes = binding.get("forbidden_scenes", [])

            # 检查文案中能力是否与正确场景一起出现
            all_text = ""
            if "title" in generated_copy:
                all_text += generated_copy["title"] + " "
            if "bullets" in generated_copy:
                all_text += " ".join(generated_copy["bullets"]) + " "

            if capability in all_text:
                # 检查是否出现在禁止场景中
                for scene in forbidden_scenes:
                    if scene in all_text:
                        issues_found = True
                        policy_issues.append({
                            "rule": "能力场景绑定",
                            "description": f"能力'{capability}'出现在禁止场景'{scene}'中",
                            "severity": "high"
                        })

        if not issues_found:
            passed_checks += 1
    else:
        passed_checks += 1

    # 3. 检查禁止组合
    total_checks += 1
    forbidden_pairs = writing_policy.get("forbidden_pairs", [])
    if forbidden_pairs:
        all_text = ""
        if "title" in generated_copy:
            all_text += generated_copy["title"] + " "
        if "bullets" in generated_copy:
            all_text += " ".join(generated_copy["bullets"]) + " "

        issues_found = False
        for pair in forbidden_pairs:
            if len(pair) >= 2:
                item1, item2 = pair[0], pair[1]
                if item1 in all_text and item2 in all_text:
                    issues_found = True
                    policy_issues.append({
                        "rule": "禁止组合",
                        "description": f"禁止组合'{item1}'和'{item2}'同时出现在文案中",
                        "severity": "high"
                    })

        if not issues_found:
            passed_checks += 1
    else:
        passed_checks += 1

    # 4. 检查边界声明强制
    total_checks += 1
    # 检查B4或B5是否包含边界声明
    bullets = generated_copy.get("bullets", [])
    if len(bullets) >= 4:
        b4_text = bullets[3] if len(bullets) > 3 else ""
        b5_text = bullets[4] if len(bullets) > 4 else ""

        # 边界声明关键词
        boundary_keywords = ["（", "）", "(", ")", "需", "要求", "requires", "with", "in"]
        has_boundary = any(keyword in b4_text for keyword in boundary_keywords) or \
                      any(keyword in b5_text for keyword in boundary_keywords)

        if has_boundary:
            passed_checks += 1
        else:
            policy_issues.append({
                "rule": "边界声明强制",
                "description": "B4或B5中未包含边界声明",
                "severity": "medium"
            })
    else:
        passed_checks += 1

    # 5. 检查FAQ only限制
    total_checks += 1
    faq_only_capabilities = writing_policy.get("faq_only_capabilities", [])
    if faq_only_capabilities:
        # 检查FAQ only能力是否出现在FAQ以外的部分
        main_text = ""
        if "title" in generated_copy:
            main_text += generated_copy["title"] + " "
        if "bullets" in generated_copy:
            main_text += " ".join(generated_copy["bullets"]) + " "
        if "description" in generated_copy:
            main_text += generated_copy["description"] + " "

        issues_found = False
        for capability in faq_only_capabilities:
            if capability in main_text:
                issues_found = True
                policy_issues.append({
                    "rule": "FAQ only限制",
                    "description": f"FAQ only能力'{capability}'出现在FAQ以外的文案中",
                    "severity": "high"
                })

        if not issues_found:
            passed_checks += 1
    else:
        passed_checks += 1

    # 6. 检查A+字数下限
    total_checks += 1
    aplus_content = generated_copy.get("aplus_content", "")
    if aplus_content:
        word_count = len(aplus_content.strip())
        if word_count >= 500:
            passed_checks += 1
        else:
            policy_issues.append({
                "rule": "A+字数下限",
                "description": f"A+内容字数不足，当前{word_count}字，要求至少500字",
                "severity": "medium"
            })
    else:
        policy_issues.append({
            "rule": "A+字数下限",
            "description": "A+内容为空",
            "severity": "medium"
        })

    return {
        "passed": passed_checks,
        "total": total_checks,
        "issues": policy_issues,
        "all_passed": len(policy_issues) == 0
    }


def check_hallucination_risk(generated_copy: Dict[str, Any],
                            attribute_data: Dict[str, Any],
                            language: str = "Chinese",
                            capability_constraints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Rufus幻觉风险检查
    检查文案中的宣称是否有属性表数据支持
    """
    hallucination_issues = []
    passed_checks = 0
    total_checks = 0

    standardized_attr = standardize_attribute_data(attribute_data or {})
    constraints = dict(capability_constraints or {})
    if not constraints:
        constraints = derive_capability_constraints(standardized_attr, [])

    support_lookup = {
        "video_resolution": standardized_attr.get("video_resolution") or constraints.get("max_resolution"),
        "waterproof_depth": constraints.get("waterproof_depth_m") or standardized_attr.get("water_resistance_level"),
        "battery_life": constraints.get("runtime_minutes") or standardized_attr.get("battery_life"),
        "weight": standardized_attr.get("weight"),
        "image_stabilization": constraints.get("stabilization_supported") or standardized_attr.get("has_image_stabilization"),
        "connectivity": constraints.get("wifi_supported") or standardized_attr.get("connectivity"),
        "screen_type": constraints.get("dual_screen_supported") or standardized_attr.get("dual_screen"),
        "live_streaming": constraints.get("live_streaming_supported") or standardized_attr.get("live_streaming"),
    }

    # 提取所有宣称
    claims = []

    # 从标题提取宣称
    title = generated_copy.get("title", "")
    if title:
        claims.append({"text": title, "source": "title"})

    # 从bullet points提取宣称
    bullets = generated_copy.get("bullets", [])
    for i, bullet in enumerate(bullets):
        claims.append({"text": bullet, "source": f"bullet_{i+1}"})

    # 从描述提取宣称
    description = generated_copy.get("description", "")
    if description:
        # 分割描述为句子
        sentences = re.split(r'[。！？.!?]', description)
        for sentence in sentences:
            if sentence.strip():
                claims.append({"text": sentence.strip(), "source": "description"})

    # 宣称检查规则
    claim_patterns = [
        {
            "pattern": r'(\d+)\s*(?:k|K)\s*(?:录像|视频|录制|video|recording)',
            "field": "video_resolution",
            "description": "视频分辨率宣称"
        },
        {
            "pattern": r'(\d+)\s*(?:米|m|meter)\s*(?:防水|waterproof)',
            "field": "waterproof_depth",
            "description": "防水深度宣称"
        },
        {
            "pattern": r'(?:étanche|wasserdicht|impermeable)',
            "field": "waterproof_depth",
            "description": "防水能力宣称"
        },
        {
            "pattern": r'(\d+)\s*(?:分钟|min|minute)\s*(?:续航|电池|battery)',
            "field": "battery_life",
            "description": "电池续航宣称"
        },
        {
            "pattern": r'(\d+)\s*(?:克|g|gram)\s*(?:重量|weight)',
            "field": "weight",
            "description": "产品重量宣称"
        },
        {
            "pattern": r'防抖|stabilization',
            "field": "image_stabilization",
            "description": "防抖功能宣称"
        },
        {
            "pattern": r'WiFi|无线|wireless',
            "field": "connectivity",
            "description": "连接功能宣称"
        },
        {
            "pattern": r'双屏|dual screen',
            "field": "screen_type",
            "description": "屏幕类型宣称"
        },
        {
            "pattern": r'live stream|live streaming|直播',
            "field": "live_streaming",
            "description": "直播能力宣称"
        }
    ]

    # 检查每个宣称
    for claim in claims:
        claim_text = claim["text"]
        source = claim["source"]

        for pattern_info in claim_patterns:
            pattern = pattern_info["pattern"]
            field = pattern_info["field"]
            description = pattern_info["description"]

            match = re.search(pattern, claim_text, re.IGNORECASE)
            if match:
                total_checks += 1

                support_value = support_lookup.get(field)
                if support_value not in (None, "", False, "none", "无", "未知"):
                    passed_checks += 1
                else:
                    hallucination_issues.append({
                        "claim": claim_text,
                        "source": source,
                        "field": field,
                        "description": f"{description}: 真值层缺少 {field} 的结构化证据支持",
                        "severity": "high"
                    })

    # 如果没有检查到任何宣称，添加一个默认检查
    if total_checks == 0:
        total_checks += 1
        # 检查是否有基本属性数据
        required_fields = ["video_resolution", "battery_life", "waterproof_depth"]
        missing_fields = [field for field in required_fields if not support_lookup.get(field)]

        if len(missing_fields) == 0:
            passed_checks += 1
        else:
            hallucination_issues.append({
                "claim": "基本属性宣称",
                "source": "整体文案",
                "field": ",".join(missing_fields),
                "description": f"属性表中缺少关键字段: {', '.join(missing_fields)}",
                "severity": "medium"
            })

    return {
        "passed": passed_checks,
        "total": total_checks,
        "issues": hallucination_issues,
        "all_passed": len(hallucination_issues) == 0
    }


def perform_risk_check(generated_copy: Dict[str, Any],
                      writing_policy: Dict[str, Any],
                      attribute_data: Dict[str, Any],
                      capability_constraints: Optional[Dict[str, Any]] = None,
                      preprocessed_data: Any = None) -> Dict[str, Any]:
    """
    执行三层风险检查

    Args:
        generated_copy: 生成的文案
        writing_policy: writing_policy策略
        attribute_data: 属性表数据

    Returns:
        风险检查结果
    """
    metadata = generated_copy.get("metadata", {}) or {}
    language = metadata.get("target_language") or metadata.get("language") or writing_policy.get("target_language") or "English"

    # 1. 合规红线检查
    compliance_result = check_compliance_redlines(generated_copy, language)

    # 2. writing_policy审计
    policy_result = check_writing_policy_compliance(generated_copy, writing_policy, language)

    # 3. 幻觉风险检查
    hallucination_result = check_hallucination_risk(
        generated_copy,
        attribute_data,
        language,
        capability_constraints=capability_constraints,
    )

    truth_issues = _truth_consistency_checks(
        generated_copy,
        writing_policy,
        attribute_data,
        capability_constraints=capability_constraints,
    )
    truth_issues.extend(_visible_field_fallback_issues(generated_copy))
    truth_result = {
        "passed": 0 if truth_issues else 1,
        "total": 1,
        "issues": truth_issues,
        "all_passed": len(truth_issues) == 0,
    }

    language_issues = _language_consistency_issues(generated_copy, language)
    language_result = {
        "passed": 0 if language_issues else 1,
        "total": 1,
        "issues": language_issues,
        "all_passed": len(language_issues) == 0,
    }
    fluency_issues = _check_fluency(generated_copy, writing_policy)
    fluency_result = {
        "passed": 0 if fluency_issues else 1,
        "total": 1,
        "issues": fluency_issues,
        "all_passed": len(fluency_issues) == 0,
    }
    coherence_issues = _check_coherence_risks(generated_copy)
    coherence_result = {
        "passed": 1 if not coherence_issues else 0,
        "total": 1,
        "issues": coherence_issues,
        "all_passed": len(coherence_issues) == 0,
    }

    retention_result = calculate_retention_report(preprocessed_data, generated_copy) if preprocessed_data else {
        "enabled": False,
        "reference_keywords": [],
        "retained_keywords": [],
        "missing_keywords": [],
        "retention_rate": 1.0,
        "threshold": 0.6,
        "is_blocking": False,
        "blocking_reason": "",
    }
    production_warnings = _extract_production_warnings(generated_copy, writing_policy)

    metadata = generated_copy.get("metadata", {}) or {}
    listing_status = derive_listing_status(
        metadata.get("generation_status") or "offline",
        risk_report={
            "compliance": compliance_result,
            "policy_audit": policy_result,
            "hallucination_risk": hallucination_result,
            "truth_consistency": truth_result,
            "language_consistency": language_result,
            "fluency": fluency_result,
            "production_warnings": {"issues": production_warnings},
        },
        retention_report=retention_result,
        llm_response_state=metadata.get("llm_response_state", ""),
        visible_fallback_fields=metadata.get("visible_llm_fallback_fields") or [],
    )
    readability_blocking_fields = sorted(
        {
            str(issue.get("field") or "").strip()
            for issue in fluency_issues
            if str(issue.get("severity") or "").lower() in {"medium", "high", "critical", "blocker"}
            and str(issue.get("field") or "").strip()
        }
    )
    review_queue = build_review_queue(
        [
            {
                "label": "Fluency",
                "blocking_fields": readability_blocking_fields,
                "issue_summary": "fluency issues require manual review",
            }
        ]
        if readability_blocking_fields
        else []
    )
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    for issue in coherence_issues:
        for field in issue.get("fields") or []:
            if not field or any(item.get("field") == field and item.get("dimension") == "Coherence" for item in review_queue):
                continue
            review_queue.append(
                {
                    "field": field,
                    "dimension": "Coherence",
                    "issue": issue.get("description") or issue.get("rule") or "coherence issue",
                    "priority": "P2",
                    "sla": "72h内",
                }
            )
    review_queue = sorted(review_queue, key=lambda item: (priority_order.get(item.get("priority"), 99), item.get("field") or ""))

    # 综合评估
    overall_passed = (
        compliance_result["all_passed"] and
        policy_result["all_passed"] and
        hallucination_result["all_passed"] and
        truth_result["all_passed"] and
        language_result["all_passed"] and
        fluency_result["all_passed"] and
        not retention_result.get("is_blocking")
    )

    risk_score = 0
    max_score = 100

    # 计算风险分数
    risk_score += (compliance_result["passed"] / compliance_result["total"]) * 40 if compliance_result["total"] > 0 else 40
    risk_score += (policy_result["passed"] / policy_result["total"]) * 25 if policy_result["total"] > 0 else 25
    risk_score += (hallucination_result["passed"] / hallucination_result["total"]) * 20 if hallucination_result["total"] > 0 else 20
    risk_score += (truth_result["passed"] / truth_result["total"]) * 10 if truth_result["total"] > 0 else 10
    risk_score += (language_result["passed"] / language_result["total"]) * 5 if language_result["total"] > 0 else 5

    return {
        "compliance": compliance_result,
        "policy_audit": policy_result,
        "hallucination_risk": hallucination_result,
        "truth_consistency": truth_result,
        "language_consistency": language_result,
        "fluency": fluency_result,
        "coherence": coherence_result,
        "traffic_retention": retention_result,
        "production_warnings": {"issues": production_warnings, "count": len(production_warnings)},
        "listing_status": listing_status,
        "review_queue": review_queue,
        "overall_passed": overall_passed,
        "risk_score": int(risk_score),
        "risk_level": "低风险" if risk_score >= 90 else "中风险" if risk_score >= 70 else "高风险",
        "summary": {
            "compliance_issues": len(compliance_result["issues"]),
            "policy_issues": len(policy_result["issues"]),
            "hallucination_issues": len(hallucination_result["issues"]),
            "truth_issues": len(truth_result["issues"]),
            "language_issues": len(language_result["issues"]),
            "fluency_issues": len(fluency_result["issues"]),
            "coherence_issues": len(coherence_result["issues"]),
            "total_issues": (
                len(compliance_result["issues"])
                + len(policy_result["issues"])
                + len(hallucination_result["issues"])
                + len(truth_result["issues"])
                + len(language_result["issues"])
                + len(fluency_result["issues"])
                + len(coherence_result["issues"])
            )
        }
    }


if __name__ == "__main__":
    # 测试代码
    sample_generated_copy = {
        "title": "TOSBARRFT 4K运动相机 户外防水防抖相机",
        "bullets": [
            "【挂载系统+主场景+P0能力】配备多种挂载配件，专为户外运动设计，提供4K录像功能",
            "【P0核心能力+量化参数】支持4K 30fps高清录像，画面细腻流畅",
            "【P1竞品痛点对比+场景词】相比竞品，在骑行场景下防抖表现更优异",
            "【P1/P2能力+使用场景+边界声明句】支持防水，适用于水下探索（需使用防水壳）",
            "【P2质保/售后/兼容性】提供12个月质保，专业客服支持，兼容多种设备"
        ],
        "description": "TOSBARRFT 运动相机专为户外运动设计，带来专业级4K录像体验。具备4K录像、防抖、防水等多项功能...",
        "faq": [
            {"q": "产品是否防水？", "a": "是的，产品配备防水壳，支持30米防水。"},
            {"q": "电池续航多久？", "a": "电池续航约150分钟，支持边充边用。"}
        ],
        "search_terms": ["运动相机", "户外相机", "防水相机"],
        "aplus_content": "TOSBARRFT 运动相机 - 专业拍摄解决方案...（超过500字的内容）",
        "metadata": {
            "language": "Chinese"
        }
    }

    sample_writing_policy = {
        "scene_priority": ["户外运动", "骑行记录", "水下探索"],
        "capability_scene_bindings": [
            {
                "capability": "4K录像",
                "allowed_scenes": ["户外运动", "水下探索"],
                "forbidden_scenes": []
            }
        ],
        "faq_only_capabilities": ["数字防抖限制说明"],
        "forbidden_pairs": [["5K", "防抖"]],
        "bullet_slot_rules": {}
    }

    sample_attribute_data = {
        "video_resolution": "4K 30fps",
        "waterproof_depth": "30米",
        "battery_life": "150分钟",
        "weight": "150g",
        "image_stabilization": "EIS",
        "connectivity": "WiFi, Bluetooth"
    }

    result = perform_risk_check(sample_generated_copy, sample_writing_policy, sample_attribute_data)

    print("风险检查结果:")
    print(f"总体通过: {result['overall_passed']}")
    print(f"风险分数: {result['risk_score']}/100 ({result['risk_level']})")
    print(f"\n合规红线检查: {result['compliance']['passed']}/{result['compliance']['total']}")
    print(f"writing_policy审计: {result['policy_audit']['passed']}/{result['policy_audit']['total']}")
    print(f"幻觉风险检查: {result['hallucination_risk']['passed']}/{result['hallucination_risk']['total']}")
    print(f"\n总问题数: {result['summary']['total_issues']}")

    if result['summary']['total_issues'] > 0:
        print("\n详细问题:")
        for issue_type in ['compliance', 'policy_audit', 'hallucination_risk']:
            issues = result[issue_type]['issues']
            if issues:
                print(f"\n{issue_type}问题:")
                for i, issue in enumerate(issues[:3], 1):
                    print(f"  {i}. {issue.get('description', 'N/A')}")
