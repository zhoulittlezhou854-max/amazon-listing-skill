#!/usr/bin/env python3
"""
能力熔断与合规检查模块 (Step 3)
版本: v1.0
功能: 基于属性表检查可宣称的能力，执行能力熔断规则
"""

import re
from typing import Dict, List, Any, Tuple

from tools.preprocess import standardize_attribute_data


# 运动相机专项能力熔断规则
ACTION_CAMERA_RULES = [
    {
        "capability": "4K宣称",
        "condition": lambda attr: _check_video_resolution(attr, min_width=3840, min_height=2160),
        "action": "ALLOW",
        "description": "视频分辨率达到4K标准"
    },
    {
        "capability": "防水宣称",
        "condition": lambda attr: _check_waterproof_depth(attr, min_depth=10),
        "action": "ALLOW_WITH_DEPTH",
        "description": "防水深度≥10米（需说明深度）"
    },
    {
        "capability": "防抖宣称",
        "condition": lambda attr: _check_image_stabilization(attr),
        "action": "ALLOW_IF_NOT_DIGITAL",
        "description": "图像防抖功能检查"
    },
    {
        "capability": "EIS防抖",
        "condition": lambda attr: _check_eis_stabilization(attr),
        "action": "ALLOW",
        "description": "电子图像防抖(EIS)"
    },
    {
        "capability": "WiFi宣称",
        "condition": lambda attr: _check_connectivity(attr, "WiFi"),
        "action": "ALLOW",
        "description": "WiFi连接功能"
    },
    {
        "capability": "蓝牙连接",
        "condition": lambda attr: _check_connectivity(attr, "Bluetooth"),
        "action": "ALLOW",
        "description": "蓝牙连接功能"
    },
    {
        "capability": "双屏幕",
        "condition": lambda attr: _check_dual_screen(attr),
        "action": "ALLOW",
        "description": "前后双屏幕设计"
    },
    {
        "capability": "长续航",
        "condition": lambda attr: _check_battery_life(attr, min_minutes=120),
        "action": "ALLOW",
        "description": "电池续航≥120分钟"
    },
    {
        "capability": "语音控制",
        "condition": lambda attr: _check_voice_control(attr),
        "action": "ALLOW",
        "description": "语音控制功能"
    },
    {
        "capability": "直播功能",
        "condition": lambda attr: _check_live_streaming(attr),
        "action": "ALLOW",
        "description": "实时直播功能"
    }
]

# 熔断禁止的能力（绝对禁止）
FORBIDDEN_CAPABILITIES = [
    "indestructible",
    "military grade",
    "100% waterproof without housing",
    "fully shockproof",
    "unbreakable",
    "bulletproof"
]

# 限制宣称的能力（需要特定条件）
RESTRICTED_CAPABILITIES = [
    "数字防抖",
    "digital stabilization",
    "防水（不包含防水壳）"
]


def _check_video_resolution(attr: Dict[str, Any], min_width: int = 3840, min_height: int = 2160) -> bool:
    """检查视频分辨率是否达到标准"""
    if not attr:
        return False

    # 尝试多种字段名
    resolution_fields = ["video_resolution", "resolution", "video_quality", "max_resolution"]

    for field in resolution_fields:
        if field in attr:
            resolution = str(attr[field]).lower()
            # 解析分辨率字符串，如 "3840x2160", "4K", "2160p"
            if "4k" in resolution or "3840" in resolution or "2160p" in resolution:
                return True

            # 尝试提取数字
            match = re.search(r'(\d+)\s*[x×]\s*(\d+)', resolution)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                if width >= min_width and height >= min_height:
                    return True

    return False


def _check_waterproof_depth(attr: Dict[str, Any], min_depth: int = 10) -> bool:
    """检查防水深度"""
    if not attr:
        return False

    # 尝试多种字段名
    depth_fields = ["waterproof_depth", "waterproof_case_max_depth_m", "water_resistance", "depth"]

    for field in depth_fields:
        if field in attr:
            depth_str = str(attr[field]).lower()
            # 提取数字
            match = re.search(r'(\d+)\s*(?:m|meter|米)', depth_str)
            if match:
                depth = int(match.group(1))
                if depth >= min_depth:
                    return True

    return False


def _check_image_stabilization(attr: Dict[str, Any]) -> bool:
    """检查图像防抖功能"""
    if not attr:
        return False

    stabilization_fields = ["image_stabilization", "stabilization", "防抖", "防抖功能"]

    for field in stabilization_fields:
        if field in attr:
            stabilization = str(attr[field]).lower()
            # 如果有防抖功能但不是"none"
            if stabilization and stabilization != "none" and stabilization != "无":
                return True

    return False


def _check_eis_stabilization(attr: Dict[str, Any]) -> bool:
    """检查EIS防抖"""
    if not attr:
        return False

    stabilization_fields = ["image_stabilization", "stabilization", "防抖类型"]

    for field in stabilization_fields:
        if field in attr:
            stabilization = str(attr[field]).lower()
            if "eis" in stabilization or "电子防抖" in stabilization:
                return True

    return False


def _check_connectivity(attr: Dict[str, Any], feature: str) -> bool:
    """检查连接功能"""
    if not attr:
        return False

    connectivity_fields = ["connectivity", "wireless_features", "无线功能", "连接功能"]

    for field in connectivity_fields:
        if field in attr:
            connectivity = str(attr[field]).lower()
            if feature.lower() in connectivity:
                return True

    return False


def _check_dual_screen(attr: Dict[str, Any]) -> bool:
    """检查双屏幕"""
    if not attr:
        return False

    screen_fields = ["screen_type", "display", "屏幕", "屏幕类型", "dual_screen", "型号", "model", "form_factor"]

    for field in screen_fields:
        if field in attr:
            screen = str(attr[field]).lower()
            if any(keyword in screen for keyword in ["dual", "双屏", "前后屏", "double screen", "two", "前后"]):
                return True

    return False


def _check_battery_life(attr: Dict[str, Any], min_minutes: int = 120) -> bool:
    """检查电池续航"""
    if not attr:
        return False

    battery_fields = ["battery_life", "recording_time", "续航时间", "电池续航"]

    for field in battery_fields:
        if field in attr:
            battery_str = str(attr[field]).lower()
            # 提取分钟数
            match = re.search(r'(\d+)\s*(?:min|分钟|minute)', battery_str)
            if match:
                minutes = int(match.group(1))
                if minutes >= min_minutes:
                    return True

            # 尝试直接匹配数字
            match = re.search(r'\b(\d{2,3})\b', battery_str)
            if match:
                minutes = int(match.group(1))
                if minutes >= min_minutes:
                    return True

    return False


def _check_voice_control(attr: Dict[str, Any]) -> bool:
    """检查语音控制"""
    if not attr:
        return False

    voice_fields = ["voice_control", "语音控制", "voice_command"]

    for field in voice_fields:
        if field in attr:
            voice = str(attr[field]).lower()
            if voice and voice != "no" and voice != "无" and voice != "none":
                return True

    return False


def _check_live_streaming(attr: Dict[str, Any]) -> bool:
    """检查直播功能"""
    if not attr:
        return False

    streaming_fields = ["live_streaming", "streaming", "直播功能", "实时流媒体"]

    for field in streaming_fields:
        if field in attr:
            streaming = str(attr[field]).lower()
            if streaming and streaming != "no" and streaming != "无" and streaming != "none":
                return True

    return False


def check_capabilities(
    attribute_data: Dict[str, Any],
    language: str = "English",
    capability_constraints: Dict[str, Any] | None = None,
) -> Dict[str, List[str]]:
    """
    检查可宣称的能力

    Args:
        attribute_data: 属性表数据
        language: 目标语言

    Returns:
        Dict with keys:
            - allowed: 允许宣称的能力列表
            - restricted: 限制宣称的能力列表（需要特定说明）
            - forbidden: 禁止宣称的能力列表
            - details: 详细检查结果
    """
    if not attribute_data:
        return {
            "allowed": [],
            "restricted": [],
            "forbidden": [],
            "details": [],
            "warning": "属性数据为空"
        }
    capability_constraints = capability_constraints or {}
    normalized = standardize_attribute_data(attribute_data)
    constraints = dict(capability_constraints)
    if not constraints:
        constraints = {
            "max_resolution": normalized.get("video_resolution", ""),
            "waterproof_supported": "waterproof" in normalized.get("water_resistance_level", "").lower(),
            "waterproof_requires_case": False,
            "waterproof_depth_m": None,
            "stabilization_supported": normalized.get("has_image_stabilization", "").lower() in {"yes", "true", "1"},
            "stabilization_modes": [],
            "stabilization_note": "",
            "runtime_minutes": None,
            "wifi_supported": any(
                token in normalized.get("connectivity", "").lower() for token in ["wifi", "wi-fi"]
            ),
            "dual_screen_supported": "dual" in " ".join(
                [normalized.get("features", ""), normalized.get("product features", "")]
            ).lower(),
            "live_streaming_supported": normalized.get("live_streaming", "").lower() in {"yes", "true", "1"},
            "voice_control_supported": normalized.get("voice_control", "").lower() in {"yes", "true", "1"},
            "faq_only_claims": [],
            "discouraged_claims": [],
            "forbidden_claims": [],
        }

    allowed_visible: List[str] = []
    allowed_with_condition: List[str] = []
    faq_only: List[str] = []
    forbidden: List[str] = list(FORBIDDEN_CAPABILITIES)
    details: List[str] = []

    max_resolution = str(constraints.get("max_resolution") or normalized.get("video_resolution", "")).lower()
    runtime_minutes = constraints.get("runtime_minutes") or 0
    stabilization_modes = constraints.get("stabilization_modes") or []
    discouraged_claims = constraints.get("discouraged_claims") or []

    if any(token in max_resolution for token in ["4k", "2160", "3840"]):
        allowed_visible.append("4K宣称")
        details.append("✓ 4K宣称: 已由标准化属性字段支持")
    else:
        details.append("✗ 4K宣称: 未找到可支持的分辨率证据")

    if constraints.get("waterproof_supported"):
        depth = constraints.get("waterproof_depth_m")
        if constraints.get("waterproof_requires_case"):
            allowed_with_condition.append("防水宣称")
            details.append(f"⚠ 防水宣称: 仅可带条件可见（需使用防水壳，深度={depth or '未标注'}m）")
        else:
            allowed_visible.append("防水宣称")
            details.append(f"✓ 防水宣称: 可见宣称允许（深度={depth or '未标注'}m）")
    else:
        details.append("✗ 防水宣称: 真值层未支持可见防水")

    if constraints.get("stabilization_supported"):
        if discouraged_claims or stabilization_modes:
            allowed_with_condition.append("防抖宣称")
            details.append(f"⚠ 防抖宣称: 有模式/文案限制（modes={stabilization_modes or ['GENERAL']}）")
        else:
            allowed_visible.append("防抖宣称")
            details.append("✓ 防抖宣称: 可见宣称允许")
        allowed_visible.append("EIS防抖")
        details.append("✓ EIS防抖: 真值层支持")
    else:
        details.append("✗ 防抖宣称: 真值层未支持")
        details.append("✗ EIS防抖: 真值层未支持")

    if constraints.get("wifi_supported"):
        allowed_visible.append("WiFi宣称")
        details.append("✓ WiFi宣称: 连接能力已验证")
    else:
        details.append("✗ WiFi宣称: 未检测到 Wi-Fi 连接能力")

    if constraints.get("dual_screen_supported"):
        allowed_visible.append("双屏幕")
        details.append("✓ 双屏幕: Features 字段支持")
    else:
        details.append("✗ 双屏幕: 未检测到双屏证据")

    if runtime_minutes and float(runtime_minutes) >= 120:
        allowed_visible.append("长续航")
        details.append(f"✓ 长续航: runtime_minutes={runtime_minutes}")
    elif runtime_minutes:
        allowed_with_condition.append("长续航")
        details.append(f"⚠ 长续航: runtime_minutes={runtime_minutes}，可见表达需谨慎")
    else:
        details.append("✗ 长续航: 未找到续航分钟数")

    if constraints.get("voice_control_supported"):
        allowed_visible.append("语音控制")
        details.append("✓ 语音控制: 属性字段支持")
    else:
        details.append("✗ 语音控制: 未检测到支持")

    if constraints.get("live_streaming_supported"):
        allowed_visible.append("直播功能")
        details.append("✓ 直播功能: 属性字段支持")
    else:
        faq_only.append("直播功能")
        details.append("⚠ 直播功能: 默认仅允许 FAQ/人工确认后使用")

    faq_only.extend(constraints.get("faq_only_claims") or [])
    forbidden.extend(str(item) for item in (constraints.get("forbidden_claims") or []))

    features_blob = " ".join(
        filter(None, [normalized.get("features", ""), normalized.get("product features", "")])
    )
    extra_feature_tokens = [item.strip() for item in re.split(r"[,/;；，]+", features_blob) if item.strip()]
    for feature in extra_feature_tokens:
        lowered = feature.lower()
        if any(word in lowered for word in [f.lower() for f in FORBIDDEN_CAPABILITIES]):
            forbidden.append(feature)
            details.append(f"❌ {feature}: 包含绝对禁止表达")
        elif feature not in allowed_visible and feature not in allowed_with_condition:
            allowed_visible.append(feature)
            details.append(f"✓ {feature}: 来自 Features / Product Features")

    allowed_visible = list(dict.fromkeys(allowed_visible))
    allowed_with_condition = list(dict.fromkeys(allowed_with_condition))
    faq_only = list(dict.fromkeys(faq_only))
    forbidden = list(dict.fromkeys(forbidden))

    return {
        "allowed_visible": allowed_visible,
        "allowed_with_condition": allowed_with_condition,
        "faq_only": faq_only,
        "allowed": allowed_visible + allowed_with_condition,
        "restricted": allowed_with_condition + faq_only,
        "forbidden": forbidden,
        "details": details,
        "summary": {
            "allowed_visible_count": len(allowed_visible),
            "allowed_with_condition_count": len(allowed_with_condition),
            "faq_only_count": len(faq_only),
            "forbidden_count": len(forbidden),
            "total_checked": 8 + len(extra_feature_tokens),
        },
        "normalized_attribute_keys": sorted(k for k in normalized.keys() if not k.startswith("__")),
    }


def check_compliance_redlines(text: str, language: str = "English") -> Dict[str, Any]:
    """
    检查文案中的合规红线

    Args:
        text: 要检查的文案文本
        language: 目标语言

    Returns:
        合规检查结果
    """
    redlines = []

    # 合规红线规则
    compliance_rules = [
        {
            "pattern": r'@|#|http[s]?://|www\.',
            "description": "联系方式/URL/社交媒体",
            "severity": "high"
        },
        {
            "pattern": r'\$\d+|\bprice\b|\bdiscount\b|\bsale\b|\bdeal\b|\bcoupon\b',
            "description": "价格/折扣信息",
            "severity": "high"
        },
        {
            "pattern": r'better than|beats|vs\.|versus|compared to',
            "description": "竞品贬低",
            "severity": "high"
        },
        {
            "pattern": r'100%|\bbest\b|#1|\btop rated\b|\bhot\b|\bamazing\b',
            "description": "绝对化宣称",
            "severity": "medium"
        },
        {
            "pattern": r'guaranteed|money back|risk-free|warranty',
            "description": "保证/退款宣称",
            "severity": "medium"
        }
    ]

    for rule in compliance_rules:
        pattern = rule["pattern"]
        if re.search(pattern, text, re.IGNORECASE):
            redlines.append({
                "pattern": pattern,
                "description": rule["description"],
                "severity": rule["severity"]
            })

    return {
        "passed": len(redlines) == 0,
        "redlines": redlines,
        "redline_count": len(redlines)
    }


if __name__ == "__main__":
    # 测试代码
    sample_attributes = {
        "video_resolution": "3840x2160",
        "waterproof_case_max_depth_m": "30米",
        "image_stabilization": "EIS",
        "connectivity": "WiFi, Bluetooth",
        "battery_life": "150分钟",
        "special_feature": "双屏幕,语音控制,直播功能"
    }

    result = check_capabilities(sample_attributes, "English")
    print("能力检查结果:")
    print(f"允许宣称: {result['allowed']}")
    print(f"限制宣称: {result['restricted']}")
    print(f"禁止宣称: {result['forbidden']}")
    print("\n详细结果:")
    for detail in result['details'][:10]:  # 只显示前10条
        print(f"  {detail}")
