#!/usr/bin/env python3
"""
能力熔断与合规检查模块 (Step 3)
版本: v1.0
功能: 基于属性表检查可宣称的能力，执行能力熔断规则
"""

import re
from typing import Dict, List, Any, Tuple


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

    screen_fields = ["screen_type", "display", "屏幕", "屏幕类型"]

    for field in screen_fields:
        if field in attr:
            screen = str(attr[field]).lower()
            if any(keyword in screen for keyword in ["dual", "双屏", "前后屏", "two", "前后"]):
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


def check_capabilities(attribute_data: Dict[str, Any], language: str = "English") -> Dict[str, List[str]]:
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

    allowed = []
    restricted = []
    forbidden = []
    details = []

    # 检查专项规则
    for rule in ACTION_CAMERA_RULES:
        capability = rule["capability"]
        condition = rule["condition"]
        action = rule["action"]
        description = rule["description"]

        try:
            if condition(attribute_data):
                if action == "ALLOW":
                    allowed.append(capability)
                    details.append(f"✓ {capability}: {description}")
                elif action == "ALLOW_WITH_DEPTH":
                    allowed.append(capability)
                    details.append(f"✓ {capability}: {description}（需说明深度）")
                elif action == "ALLOW_IF_NOT_DIGITAL":
                    # 检查是否为数字防抖
                    stabilization = str(attribute_data.get("image_stabilization", "")).lower()
                    if "digital" in stabilization or "数字" in stabilization:
                        restricted.append(capability)
                        details.append(f"⚠ {capability}: {description}（仅限数字防抖，需降级说明）")
                    else:
                        allowed.append(capability)
                        details.append(f"✓ {capability}: {description}")
                else:
                    allowed.append(capability)
                    details.append(f"✓ {capability}: {description}")
            else:
                details.append(f"✗ {capability}: 不满足条件")
        except Exception as e:
            details.append(f"✗ {capability}: 检查失败 ({e})")

    # 检查绝对禁止的能力
    for capability in FORBIDDEN_CAPABILITIES:
        forbidden.append(capability)
        details.append(f"❌ {capability}: 绝对禁止宣称")

    # 检查属性表中未标注但用户可能想宣称的能力
    # 提取属性表中的special_feature字段
    special_features = []
    if "special_feature" in attribute_data:
        features = str(attribute_data["special_feature"]).split(",")
        special_features = [f.strip() for f in features if f.strip()]

    # 对于特殊功能，检查是否在属性表中有支持
    for feature in special_features:
        # 简单检查：如果特征不在已检查的能力中，且不包含禁止词汇，则允许
        feature_lower = feature.lower()
        is_forbidden = any(forbidden_word in feature_lower for forbidden_word in [f.lower() for f in FORBIDDEN_CAPABILITIES])

        if is_forbidden:
            forbidden.append(feature)
            details.append(f"❌ {feature}: 包含禁止词汇")
        elif feature not in allowed and feature not in restricted:
            # 检查是否在限制列表中
            is_restricted = any(restricted_word.lower() in feature_lower for restricted_word in RESTRICTED_CAPABILITIES)

            if is_restricted:
                restricted.append(feature)
                details.append(f"⚠ {feature}: 需要特定说明或条件")
            else:
                allowed.append(feature)
                details.append(f"✓ {feature}: 属性表中标注的特殊功能")

    # 移除重复项
    allowed = list(dict.fromkeys(allowed))
    restricted = list(dict.fromkeys(restricted))
    forbidden = list(dict.fromkeys(forbidden))

    return {
        "allowed": allowed,
        "restricted": restricted,
        "forbidden": forbidden,
        "details": details,
        "summary": {
            "allowed_count": len(allowed),
            "restricted_count": len(restricted),
            "forbidden_count": len(forbidden),
            "total_checked": len(ACTION_CAMERA_RULES) + len(FORBIDDEN_CAPABILITIES) + len(special_features)
        }
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
            "pattern": r'\$\d+|price|discount|sale|deal|coupon',
            "description": "价格/折扣信息",
            "severity": "high"
        },
        {
            "pattern": r'better than|beats|vs\.|versus|compared to',
            "description": "竞品贬低",
            "severity": "high"
        },
        {
            "pattern": r'100%|best|#1|top rated|hot|amazing',
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