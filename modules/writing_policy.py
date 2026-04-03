#!/usr/bin/env python3
"""
writing_policy 生成模块 (Step 5)
版本: v1.0
功能: 生成文案写作策略，包括场景优先级、能力场景绑定等
"""

import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class PreprocessedData:
    """预处理数据类（简化版）"""
    run_config: Any
    attribute_data: Any
    keyword_data: Any
    review_data: Any
    aba_data: Any
    core_selling_points: List[str]
    accessory_descriptions: List[Dict[str, Any]]
    quality_score: int
    language: str
    processed_at: str


# 运动相机常见场景
ACTION_CAMERA_SCENES = [
    "户外运动", "骑行记录", "水下探索", "旅行记录", "家庭使用",
    "滑雪运动", "登山徒步", "自驾游", "宠物拍摄", "vlog制作",
    "运动训练", "赛事记录", "野外探险", "极限运动", "日常记录"
]

# 能力与场景的默认绑定关系
DEFAULT_CAPABILITY_SCENE_BINDINGS = {
    "4K录像": ["户外运动", "水下探索", "旅行记录", "赛事记录"],
    "防抖": ["骑行记录", "滑雪运动", "登山徒步", "运动训练"],
    "防水": ["水下探索", "雨天使用", "游泳", "冲浪"],
    "WiFi连接": ["家庭使用", "vlog制作", "日常记录", "宠物拍摄"],
    "双屏幕": ["自拍vlog", "家庭使用", "旅行记录", "宠物拍摄"],
    "长续航": ["户外运动", "登山徒步", "自驾游", "野外探险"],
    "语音控制": ["运动训练", "骑行记录", "滑雪运动", "极限运动"],
    "直播功能": ["赛事记录", "vlog制作", "户外运动", "旅行记录"]
}

# 需要限制的能力（只能在FAQ中提及）
FAQ_ONLY_CAPABILITIES = [
    "数字防抖限制说明",
    "防水深度限制",
    "电池更换说明",
    "兼容性限制",
    "质保条款细节"
]

# 禁止的能力组合
DEFAULT_FORBIDDEN_PAIRS = [
    ["5K", "防抖"],  # 5K分辨率下不支持防抖
    ["8K", "实时直播"],  # 8K分辨率下不支持实时直播
    ["防水", "充电"],  # 防水状态下不能充电
    ["极限温度", "长时间使用"]  # 极端温度下不建议长时间使用
]

# Bullet slot规则
DEFAULT_BULLET_SLOT_RULES = {
    "B1": "挂载系统 + 主场景 + P0能力",
    "B2": "P0核心能力 + 量化参数",
    "B3": "P1竞品痛点对比 + 场景词",
    "B4": "P1/P2能力 + 边界声明句",
    "B5": "P2质保/售后/兼容性"
}


def extract_scenes_from_keywords(keyword_data: Any, language: str = "Chinese") -> List[str]:
    """
    从关键词数据中提取场景
    """
    scenes = set()

    if not keyword_data or not hasattr(keyword_data, 'keywords'):
        return list(scenes)

    # 场景关键词模式
    scene_patterns = [
        r'户外', r'骑行', r'水下', r'旅行', r'家庭', r'滑雪', r'登山',
        r'自驾', r'宠物', r'vlog', r'运动', r'赛事', r'野外', r'极限',
        r'日常', r'sports', r'outdoor', r'biking', r'underwater',
        r'travel', r'family', r'skiing', r'hiking', r'pet', r'vlogging'
    ]

    for keyword_item in keyword_data.keywords:
        keyword = keyword_item.get('keyword', '')
        if not keyword:
            continue

        keyword_lower = keyword.lower()
        for pattern in scene_patterns:
            if re.search(pattern, keyword_lower, re.IGNORECASE):
                # 映射到中文场景
                scene_map = {
                    'outdoor': '户外运动',
                    'sports': '运动训练',
                    'biking': '骑行记录',
                    'underwater': '水下探索',
                    'travel': '旅行记录',
                    'family': '家庭使用',
                    'skiing': '滑雪运动',
                    'hiking': '登山徒步',
                    'pet': '宠物拍摄',
                    'vlogging': 'vlog制作',
                    '赛事': '赛事记录',
                    '野外': '野外探险',
                    '极限': '极限运动',
                    '日常': '日常记录'
                }

                for eng, chi in scene_map.items():
                    if eng in keyword_lower:
                        scenes.add(chi)
                        break
                else:
                    # 如果没有匹配的映射，使用原始模式
                    scenes.add(keyword)

    # 如果场景太少，使用默认场景
    if len(scenes) < 3:
        scenes.update(ACTION_CAMERA_SCENES[:5])

    # 确保包含三个关键场景：骑行、水下、旅行
    target_scenes = ["骑行记录", "水下探索", "旅行记录"]
    scenes.update(target_scenes)

    return list(scenes)[:8]  # 最多8个场景


def prioritize_scenes(scenes: List[str], review_data: Any, aba_data: Any) -> List[str]:
    """
    根据评论和ABA数据对场景进行优先级排序
    """
    if not scenes:
        return ACTION_CAMERA_SCENES[:5]

    # 简单的优先级排序（可根据实际数据增强）
    scene_scores = {}

    # 基础分数
    for i, scene in enumerate(scenes):
        scene_scores[scene] = len(scenes) - i  # 原始顺序的权重

    # 根据评论数据调整分数
    if review_data and hasattr(review_data, 'insights'):
        for insight in review_data.insights:
            content = insight.get('content_text', '').lower()
            for scene in scenes:
                # 简单关键词匹配
                scene_keywords = {
                    '户外运动': ['户外', '运动', 'outside', 'sport'],
                    '骑行记录': ['骑行', '自行车', 'biking', 'bicycle'],
                    '水下探索': ['水下', '游泳', '潜水', 'underwater', 'swim'],
                    '旅行记录': ['旅行', '旅游', 'travel', 'trip'],
                    '家庭使用': ['家庭', '孩子', '家庭', 'family', 'kid']
                }

                if scene in scene_keywords:
                    for keyword in scene_keywords[scene]:
                        if keyword in content:
                            scene_scores[scene] = scene_scores.get(scene, 0) + 2

    # 根据ABA数据调整分数（搜索量）
    if aba_data and hasattr(aba_data, 'trends'):
        for trend in aba_data.trends:
            keyword = trend.get('keyword', '').lower()
            search_volume = trend.get('search_volume', 0)

            for scene in scenes:
                scene_keywords = {
                    '户外运动': ['outdoor', 'sports'],
                    '骑行记录': ['biking', 'bicycle'],
                    '水下探索': ['underwater', 'waterproof'],
                    '旅行记录': ['travel', 'trip'],
                    '家庭使用': ['family', 'home']
                }

                if scene in scene_keywords:
                    for kw in scene_keywords[scene]:
                        if kw in keyword and search_volume > 0:
                            scene_scores[scene] = scene_scores.get(scene, 0) + min(search_volume / 1000, 5)

    # 按分数排序
    sorted_scenes = sorted(scene_scores.items(), key=lambda x: x[1], reverse=True)
    return [scene for scene, score in sorted_scenes]


def create_capability_scene_bindings(capabilities: List[str], prioritized_scenes: List[str]) -> List[Dict[str, Any]]:
    """
    创建能力与场景的绑定关系
    """
    bindings = []

    for capability in capabilities:
        # 查找默认绑定
        allowed_scenes = DEFAULT_CAPABILITY_SCENE_BINDINGS.get(capability, [])

        # 过滤掉不在优先场景列表中的场景
        allowed_scenes = [scene for scene in allowed_scenes if scene in prioritized_scenes]

        # 如果默认绑定为空，使用前3个优先场景
        if not allowed_scenes and prioritized_scenes:
            allowed_scenes = prioritized_scenes[:3]

        # 确定绑定类型
        binding_type = "used_for_func"
        if any(keyword in capability.lower() for keyword in ['防抖', 'stabilization']):
            binding_type = "performance_feature"
        elif any(keyword in capability.lower() for keyword in ['防水', 'waterproof']):
            binding_type = "environmental_feature"
        elif any(keyword in capability.lower() for keyword in ['连接', 'connectivity', 'wifi']):
            binding_type = "connectivity_feature"

        bindings.append({
            "capability": capability,
            "binding_type": binding_type,
            "allowed_scenes": allowed_scenes,
            "forbidden_scenes": [],  # 可基于规则添加
            "usage_notes": f"可在{', '.join(allowed_scenes[:2])}等场景中使用" if allowed_scenes else "无特定场景限制"
        })

    return bindings


def identify_faq_only_capabilities(capabilities: List[str], attribute_data: Any) -> List[str]:
    """
    识别只能在FAQ中提及的能力
    """
    faq_capabilities = []

    # 添加默认的FAQ only能力
    faq_capabilities.extend(FAQ_ONLY_CAPABILITIES)

    # 基于属性数据识别需要限制的能力
    if attribute_data and hasattr(attribute_data, 'data'):
        attr_data = attribute_data.data

        # 检查数字防抖
        stabilization = str(attr_data.get('image_stabilization', '')).lower()
        if 'digital' in stabilization or '数字' in stabilization:
            faq_capabilities.append("数字防抖限制说明")

        # 检查防水限制
        waterproof_depth = str(attr_data.get('waterproof_depth', '')).lower()
        if 'case' in waterproof_depth or '壳' in waterproof_depth:
            faq_capabilities.append("防水深度限制")

        # 检查电池限制
        battery_life = str(attr_data.get('battery_life', '')).lower()
        if 'non-removable' in battery_life or '不可拆卸' in battery_life:
            faq_capabilities.append("电池更换说明")

    # 添加能力列表中需要限制的项
    for capability in capabilities:
        capability_lower = capability.lower()
        if any(restricted in capability_lower for restricted in ['限制', '说明', '注意事项', '警告']):
            faq_capabilities.append(capability)

    return list(set(faq_capabilities))[:5]  # 最多5个


def identify_forbidden_pairs(capabilities: List[str], attribute_data: Any) -> List[List[str]]:
    """
    识别禁止的能力组合
    """
    forbidden_pairs = []

    # 添加默认禁止组合
    forbidden_pairs.extend(DEFAULT_FORBIDDEN_PAIRS)

    if attribute_data and hasattr(attribute_data, 'data'):
        attr_data = attribute_data.data

        # 基于属性数据识别禁止组合
        # 示例：如果分辨率是5K但防抖是数字防抖，则禁止组合
        resolution = str(attr_data.get('video_resolution', '')).lower()
        stabilization = str(attr_data.get('image_stabilization', '')).lower()

        if ('5k' in resolution or '5120' in resolution) and ('digital' in stabilization or '数字' in stabilization):
            forbidden_pairs.append(["5K录制", "数字防抖"])

        # 如果防水深度有限制
        waterproof = str(attr_data.get('waterproof_depth', '')).lower()
        if '30' in waterproof and '充电' in waterproof:
            forbidden_pairs.append(["30米防水", "水下充电"])

    # 基于能力列表识别可能冲突的组合
    capability_keywords = {
        '高分辨率': ['5k', '8k', '4k60fps'],
        '防抖': ['防抖', 'stabilization'],
        '直播': ['直播', 'streaming'],
        '防水': ['防水', 'waterproof'],
        '低温': ['低温', 'cold']
    }

    for i, cap1 in enumerate(capabilities):
        for j, cap2 in enumerate(capabilities):
            if i >= j:
                continue

            cap1_lower = cap1.lower()
            cap2_lower = cap2.lower()

            # 检查是否可能冲突
            if ('5k' in cap1_lower or '8k' in cap1_lower) and ('防抖' in cap2_lower or 'stabilization' in cap2_lower):
                forbidden_pairs.append([cap1, cap2])

            if ('直播' in cap1_lower or 'streaming' in cap1_lower) and ('8k' in cap2_lower):
                forbidden_pairs.append([cap1, cap2])

    return forbidden_pairs[:10]  # 最多10个禁止组合


def generate_policy(preprocessed_data: PreprocessedData,
                    core_selling_points: List[str],
                    language: str = "Chinese") -> Dict[str, Any]:
    """
    生成writing_policy

    Args:
        preprocessed_data: 预处理数据
        core_selling_points: 核心卖点列表
        language: 目标语言

    Returns:
        writing_policy字典
    """
    # 1. 提取场景并排序
    scenes = extract_scenes_from_keywords(preprocessed_data.keyword_data, language)
    prioritized_scenes = prioritize_scenes(scenes, preprocessed_data.review_data, preprocessed_data.aba_data)

    # 2. 创建能力场景绑定
    capability_scene_bindings = create_capability_scene_bindings(core_selling_points, prioritized_scenes)

    # 3. 识别FAQ only能力
    faq_only_capabilities = identify_faq_only_capabilities(core_selling_points, preprocessed_data.attribute_data)

    # 4. 识别禁止组合
    forbidden_pairs = identify_forbidden_pairs(core_selling_points, preprocessed_data.attribute_data)

    # 5. 根据语言调整bullet slot规则
    bullet_slot_rules = DEFAULT_BULLET_SLOT_RULES.copy()
    if language != "Chinese":
        # 英文版规则
        bullet_slot_rules = {
            "B1": "Mounting system + Primary scene + P0 capability",
            "B2": "P0 core capability + Quantified parameters",
            "B3": "P1 competitor pain point comparison + Scene keywords",
            "B4": "P1/P2 capability + Boundary statement",
            "B5": "P2 warranty/after-sale/compatibility"
        }

    # 6. 构建完整policy
    policy = {
        "scene_priority": prioritized_scenes,
        "capability_scene_bindings": capability_scene_bindings,
        "faq_only_capabilities": faq_only_capabilities,
        "forbidden_pairs": forbidden_pairs,
        "bullet_slot_rules": bullet_slot_rules,
        "language": language,
        "metadata": {
            "core_selling_points_count": len(core_selling_points),
            "scenes_count": len(prioritized_scenes),
            "bindings_count": len(capability_scene_bindings),
            "generated_at": preprocessed_data.processed_at
        }
    }

    return policy


def save_policy_to_file(policy: Dict[str, Any], filepath: str):
    """保存policy到文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(policy, f, ensure_ascii=False, indent=2)


def load_policy_from_file(filepath: str) -> Dict[str, Any]:
    """从文件加载policy"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    # 测试代码
    from dataclasses import dataclass

    @dataclass
    class MockKeywordData:
        keywords: List[Dict[str, Any]]

    @dataclass
    class MockReviewData:
        insights: List[Dict[str, Any]]

    @dataclass
    class MockABAData:
        trends: List[Dict[str, Any]]

    @dataclass
    class MockAttributeData:
        data: Dict[str, Any]

    # 创建模拟数据
    mock_preprocessed = PreprocessedData(
        run_config=None,
        attribute_data=MockAttributeData(data={
            "video_resolution": "4K",
            "image_stabilization": "Digital",
            "waterproof_depth": "30米（带防水壳）"
        }),
        keyword_data=MockKeywordData(keywords=[
            {"keyword": "outdoor sports camera"},
            {"keyword": "biking camera"},
            {"keyword": "underwater camera"}
        ]),
        review_data=MockReviewData(insights=[
            {"content_text": "户外运动拍摄效果很好", "field_name": "Feature_Praise"},
            {"content_text": "骑行时防抖效果不错", "field_name": "Feature_Praise"}
        ]),
        aba_data=MockABAData(trends=[
            {"keyword": "action camera outdoor", "search_volume": 5000},
            {"keyword": "bike camera", "search_volume": 3000}
        ]),
        core_selling_points=["4K录像", "防抖", "防水", "WiFi连接"],
        accessory_descriptions=[],
        quality_score=85,
        language="Chinese",
        processed_at="2024-01-01T00:00:00"
    )

    policy = generate_policy(mock_preprocessed, mock_preprocessed.core_selling_points, "Chinese")
    print("生成的writing_policy:")
    print(json.dumps(policy, ensure_ascii=False, indent=2))