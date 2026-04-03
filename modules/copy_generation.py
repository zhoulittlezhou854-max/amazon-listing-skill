#!/usr/bin/env python3
"""
文案生成模块 (Step 6)
版本: v1.0
功能: 生成完整的Listing文案，包括Title、Bullets、Description、FAQ、Search Terms、A+内容
"""

import json
import re
import random
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


# 标题模板（根据不同语言）
TITLE_TEMPLATES = {
    "Chinese": [
        "[品牌] [L1关键词] [场景词] [核心能力+参数] [差异化特征]",
        "[品牌] [核心能力] [场景词] [L1关键词] 运动相机",
        "[场景词]专用 [品牌] [核心能力] [L1关键词] 相机"
    ],
    "English": [
        "[Brand] [L1_Keyword] [Scene_Word] [Core_Capability+Params] [Differentiator]",
        "[Brand] [Core_Capability] [Scene_Word] [L1_Keyword] Action Camera",
        "[Scene_Word] [Brand] [Core_Capability] [L1_Keyword] Camera"
    ],
    "German": [
        "[Brand] [L1_Keyword] [Scene_Word] [Core_Capability+Params] [Differentiator]",
        "[Brand] [Core_Capability] [Scene_Word] [L1_Keyword] Actionkamera"
    ],
    "French": [
        "[Brand] [L1_Keyword] [Scene_Word] [Core_Capability+Params] [Differentiator]",
        "[Brand] [Core_Capability] [Scene_Word] [L1_Keyword] Caméra d'action"
    ],
    "Spanish": [
        "[Brand] [L1_Keyword] [Scene_Word] [Core_Capability+Params] [Differentiator]",
        "[Brand] [Core_Capability] [Scene_Word] [L1_Keyword] Cámara de acción"
    ],
    "Italian": [
        "[Brand] [L1_Keyword] [Scene_Word] [Core_Capability+Params] [Differentiator]",
        "[Brand] [Core_Capability] [Scene_Word] [L1_Keyword] Videocamera sportiva"
    ],
    "Japanese": [
        "[Brand] [L1关键词] [场景词] [核心能力+参数] [差异化特征]",
        "[品牌] [核心能力] [场景词] [L1关键词] アクションカメラ"
    ]
}

# Bullet point模板
BULLET_TEMPLATES = {
    "B1": {
        "Chinese": "【挂载系统+主场景+P0能力】{content}",
        "English": "【Mounting System + Primary Scene + P0 Capability】{content}"
    },
    "B2": {
        "Chinese": "【P0核心能力+量化参数】{content}",
        "English": "【P0 Core Capability + Quantified Parameters】{content}"
    },
    "B3": {
        "Chinese": "【P1竞品痛点对比+场景词】{content}",
        "English": "【P1 Competitor Pain Point Comparison + Scene Keywords】{content}"
    },
    "B4": {
        "Chinese": "【P1/P2能力+使用场景+边界声明句】{content}",
        "English": "【P1/P2 Capability + Usage Scene + Boundary Statement】{content}"
    },
    "B5": {
        "Chinese": "【P2质保/售后/兼容性】{content}",
        "English": "【P2 Warranty/After-sale/Compatibility】{content}"
    }
}

# 边界声明句模板
BOUNDARY_STATEMENTS = {
    "Chinese": [
        "（需使用防水壳）",
        "（在特定模式下）",
        "（基于实验室测试数据）",
        "（随附配件支持）",
        "（需连接手机APP）"
    ],
    "English": [
        "(with waterproof case)",
        "(in specific modes)",
        "(based on lab test data)",
        "(with included accessories)",
        "(requires smartphone app connection)"
    ]
}

# 描述模板
DESCRIPTION_TEMPLATES = {
    "Chinese": """{brand} {product_name} 专为{scene}设计，带来专业级{core_capability}体验。{selling_points}

主要特性：
• {bullet1}
• {bullet2}
• {bullet3}

{closing_statement}

包装内含：{accessories}""",
    "English": """The {brand} {product_name} is designed for {scene}, delivering professional-grade {core_capability} experience. {selling_points}

Key Features:
• {bullet1}
• {bullet2}
• {bullet3}

{closing_statement}

Package includes: {accessories}"""
}

# FAQ模板
FAQ_TEMPLATES = {
    "Chinese": [
        {"q": "产品是否防水？", "a": "是的，产品配备防水壳，支持{waterproof_depth}防水。"},
        {"q": "电池续航多久？", "a": "电池续航约{battery_life}，支持边充边用。"},
        {"q": "支持哪些存储卡？", "a": "支持Micro SD卡，最大支持{max_storage}。"},
        {"q": "如何传输文件？", "a": "可通过WiFi或USB连接传输文件。"},
        {"q": "质保期多久？", "a": "提供{ warranty_period}质保，享受全国联保服务。"}
    ],
    "English": [
        {"q": "Is the product waterproof?", "a": "Yes, it comes with a waterproof case that supports {waterproof_depth}."},
        {"q": "How long does the battery last?", "a": "The battery lasts about {battery_life} and supports charging while recording."},
        {"q": "What memory cards are supported?", "a": "Supports Micro SD cards up to {max_storage}."},
        {"q": "How to transfer files?", "a": "Files can be transferred via WiFi or USB connection."},
        {"q": "What is the warranty period?", "a": "It comes with {warranty_period} warranty with nationwide service coverage."}
    ]
}


def extract_l1_keywords(keyword_data: Any, language: str = "Chinese") -> List[str]:
    """
    提取L1关键词（月搜索量≥10,000）
    """
    l1_keywords = []

    if not keyword_data or not hasattr(keyword_data, 'keywords'):
        # 返回默认关键词
        default_keywords = {
            "Chinese": ["运动相机", "户外相机", "防水相机", "4K相机", "防抖相机"],
            "English": ["action camera", "sports camera", "waterproof camera", "4K camera", "stabilization camera"],
            "German": ["Actionkamera", "Sportkamera", "Wasserdichte Kamera", "4K Kamera"],
            "French": ["caméra d'action", "caméra sport", "caméra étanche", "caméra 4K"],
            "Spanish": ["cámara de acción", "cámara deportiva", "cámara impermeable", "cámara 4K"],
            "Italian": ["videocamera sportiva", "fotocamera sportiva", "fotocamera impermeabile", "fotocamera 4K"],
            "Japanese": ["アクションカメラ", "スポーツカメラ", "防水カメラ", "4Kカメラ"]
        }
        return default_keywords.get(language, default_keywords["English"])

    for keyword_item in keyword_data.keywords:
        search_volume = keyword_item.get('search_volume', 0)
        keyword = keyword_item.get('keyword', '')

        if search_volume >= 10000 and keyword:
            l1_keywords.append(keyword)

    # 如果L1关键词不足，返回所有关键词
    if len(l1_keywords) < 3:
        for keyword_item in keyword_data.keywords:
            keyword = keyword_item.get('keyword', '')
            if keyword:
                l1_keywords.append(keyword)

    return list(set(l1_keywords))[:5]  # 最多5个


def extract_high_conv_keywords(keyword_data: Any) -> List[str]:
    """
    提取高转化关键词（购买率≥1.5%）
    """
    high_conv_keywords = []

    if not keyword_data or not hasattr(keyword_data, 'keywords'):
        return []

    for keyword_item in keyword_data.keywords:
        conversion_rate = keyword_item.get('conversion_rate', 0)
        keyword = keyword_item.get('keyword', '')

        if conversion_rate >= 1.5 and keyword:
            high_conv_keywords.append(keyword)

    return high_conv_keywords[:3]


def generate_title(preprocessed_data: PreprocessedData,
                   writing_policy: Dict[str, Any],
                   l1_keywords: List[str]) -> str:
    """
    生成标题
    """
    language = preprocessed_data.language
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"

    # 获取核心能力
    core_capabilities = preprocessed_data.core_selling_points
    if not core_capabilities:
        core_capabilities = ["4K录像", "防抖", "防水"]

    # 获取场景词
    scenes = writing_policy.get('scene_priority', [])
    scene_word = scenes[0] if scenes else "户外运动"

    # 德语翻译映射
    if language == "German":
        # 翻译核心能力
        capability_translation = {
            "双屏幕": "Dual Screen",
            "EIS防抖": "EIS Bildstabilisierung",
            "防抖": "Bildstabilisierung",
            "WiFi连接": "WiFi Verbindung",
            "防水": "Wasserdicht",
            "4K录像": "4K Aufnahme",
            "高清录像": "HD Aufnahme"
        }
        # 翻译场景词
        scene_translation = {
            "骑行记录": "Radfahren Aufnahme",
            "户外运动": "Outdoor Sport",
            "水下探索": "Unterwasser Erkundung",
            "旅行记录": "Reiseaufnahme",
            "运动训练": "Sporttraining",
            "家庭使用": "Familiengebrauch"
        }

        # 翻译核心能力
        translated_capabilities = []
        for cap in core_capabilities:
            translated = capability_translation.get(cap, cap)
            # 如果未找到直接映射，尝试部分匹配
            if translated == cap:
                for key, value in capability_translation.items():
                    if key in cap:
                        translated = cap.replace(key, value)
                        break
            translated_capabilities.append(translated)
        core_capabilities = translated_capabilities

        # 翻译场景词
        scene_word = scene_translation.get(scene_word, scene_word)

    # 选择模板
    templates = TITLE_TEMPLATES.get(language, TITLE_TEMPLATES["English"])
    template = random.choice(templates)

    # 填充模板
    title = template
    title = title.replace("[品牌]", brand)
    title = title.replace("[Brand]", brand)

    if l1_keywords:
        title = title.replace("[L1关键词]", l1_keywords[0])
        title = title.replace("[L1_Keyword]", l1_keywords[0])
    else:
        # 根据语言设置默认L1关键词
        default_l1 = {
            "Chinese": "运动相机",
            "English": "Action Camera",
            "German": "Actionkamera",
            "French": "caméra d'action",
            "Spanish": "cámara de acción",
            "Italian": "videocamera sportiva",
            "Japanese": "アクションカメラ"
        }
        default_keyword = default_l1.get(language, "Action Camera")
        title = title.replace("[L1关键词]", default_keyword)
        title = title.replace("[L1_Keyword]", default_keyword)
        # 同时将默认关键词添加到l1_keywords列表用于后续使用
        l1_keywords = [default_keyword]

    title = title.replace("[场景词]", scene_word)
    title = title.replace("[Scene_Word]", scene_word)

    if core_capabilities:
        core_cap = core_capabilities[0]
        # 添加参数（如果有）
        attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}
        if "video_resolution" in attr_data and "4K" in core_cap:
            resolution = attr_data["video_resolution"]
            core_cap = f"{core_cap} {resolution}"
        title = title.replace("[核心能力+参数]", core_cap)
        title = title.replace("[Core_Capability+Params]", core_cap)
        title = title.replace("[核心能力]", core_cap.split()[0] if " " in core_cap else core_cap)
        title = title.replace("[Core_Capability]", core_cap.split()[0] if " " in core_cap else core_cap)

    # 差异化特征
    if len(core_capabilities) > 1:
        differentiator = core_capabilities[1]
    else:
        differentiator = "专业级" if language == "Chinese" else "Professional"
    title = title.replace("[差异化特征]", differentiator)
    title = title.replace("[Differentiator]", differentiator)

    # 清理多余空格和特殊字符
    title = re.sub(r'\s+', ' ', title).strip()

    # 确保标题不超过200字符
    if len(title) > 200:
        title = title[:197] + "..."

    return title


def clean_bullet_text(bullet: str) -> str:
    """
    清理bullet文本，移除模板标记【...】
    """
    # 移除【...】模式，包括中英文括号
    cleaned = re.sub(r'【[^】]*】', '', bullet)  # 中文括号
    cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)  # 英文括号
    # 清理多余空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def generate_bullet_points(preprocessed_data: PreprocessedData,
                          writing_policy: Dict[str, Any],
                          language: str = "Chinese") -> List[str]:
    """
    生成5条bullet points
    """
    bullets = []
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"
    core_capabilities = preprocessed_data.core_selling_points
    scenes = writing_policy.get('scene_priority', [])
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}

    # 提取属性参数
    waterproof_depth = attr_data.get('waterproof_depth', '30米')
    battery_life = attr_data.get('battery_life', '150分钟')
    resolution = attr_data.get('video_resolution', '4K 30fps')
    weight = attr_data.get('weight', '150g')

    # B1: 挂载系统 + 主场景 + P0能力 + 数字参数
    if scenes and core_capabilities:
        scene = scenes[0]
        capability = core_capabilities[0]
        template = BULLET_TEMPLATES["B1"].get(language, BULLET_TEMPLATES["B1"]["English"])
        # 添加数字参数：防水深度
        content = f"配备多种挂载配件，专为{scene}设计，提供{capability}功能，支持{waterproof_depth}防水"
        bullets.append(template.format(content=content))

    # B2: P0核心能力 + 量化参数
    if len(core_capabilities) > 0:
        capability = core_capabilities[0]
        template = BULLET_TEMPLATES["B2"].get(language, BULLET_TEMPLATES["B2"]["English"])
        if "4K" in capability or "录像" in capability:
            content = f"支持{resolution}高清录像，画面细腻流畅，最大存储{max_storage}"
        elif "防抖" in capability:
            content = f"采用先进防抖技术，运动拍摄依然稳定清晰，电池续航{battery_life}"
        elif "防水" in capability:
            content = f"支持{waterproof_depth}防水，适合水下拍摄，重量仅{weight}"
        else:
            content = f"提供{capability}功能，性能出色可靠，重量仅{weight}"
        bullets.append(template.format(content=content))

    # B3: P1竞品痛点对比 + 场景词 + 数字参数
    if len(scenes) > 1 and len(core_capabilities) > 1:
        scene = scenes[1] if len(scenes) > 1 else scenes[0]
        capability = core_capabilities[1] if len(core_capabilities) > 1 else core_capabilities[0]
        template = BULLET_TEMPLATES["B3"].get(language, BULLET_TEMPLATES["B3"]["English"])
        # 添加电池续航参数
        content = f"相比竞品，在{scene}场景下{capability}表现更优异，电池续航{battery_life}"
        bullets.append(template.format(content=content))

    # B4: P1/P2能力 + 使用场景 + 边界声明句
    if len(core_capabilities) > 2:
        capability = core_capabilities[2] if len(core_capabilities) > 2 else core_capabilities[0]
        scene = scenes[2] if len(scenes) > 2 else scenes[0]
        template = BULLET_TEMPLATES["B4"].get(language, BULLET_TEMPLATES["B4"]["English"])
        boundary = random.choice(BOUNDARY_STATEMENTS.get(language, BOUNDARY_STATEMENTS["English"]))
        content = f"支持{capability}，适用于{scene}{boundary}"
        bullets.append(template.format(content=content))
    else:
        # 使用默认内容
        template = BULLET_TEMPLATES["B4"].get(language, BULLET_TEMPLATES["B4"]["English"])
        boundary = random.choice(BOUNDARY_STATEMENTS.get(language, BOUNDARY_STATEMENTS["English"]))
        content = f"多功能设计，满足多种拍摄需求{boundary}"
        bullets.append(template.format(content=content))

    # B5: P2质保/售后/兼容性
    template = BULLET_TEMPLATES["B5"].get(language, BULLET_TEMPLATES["B5"]["English"])
    content = "提供12个月质保，专业客服支持，兼容多种设备"
    bullets.append(template.format(content=content))

    # 清理模板标记
    bullets = [clean_bullet_text(bullet) for bullet in bullets]

    # 确保每条bullet不超过250字符
    for i in range(len(bullets)):
        if len(bullets[i]) > 250:
            bullets[i] = bullets[i][:247] + "..."

    return bullets


def generate_description(preprocessed_data: PreprocessedData,
                        writing_policy: Dict[str, Any],
                        title: str,
                        bullets: List[str],
                        language: str = "Chinese") -> str:
    """
    生成产品描述
    """
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"
    core_capabilities = preprocessed_data.core_selling_points
    scenes = writing_policy.get('scene_priority', [])
    accessory_descriptions = preprocessed_data.accessory_descriptions

    # 提取产品名称（从标题中）
    product_name = title.replace(brand, "").strip()
    if not product_name:
        product_name = "运动相机"

    # 获取场景
    scene = scenes[0] if scenes else "户外运动"

    # 获取核心能力
    core_capability = core_capabilities[0] if core_capabilities else "高清拍摄"

    # 构建卖点描述
    selling_points = ""
    if len(core_capabilities) > 1:
        selling_points = f"具备{', '.join(core_capabilities[:3])}等多项功能，"
    else:
        selling_points = f"具备{core_capability}功能，"

    # 配件列表
    accessories = ""
    if accessory_descriptions:
        accessory_names = [acc.get('name', '配件') for acc in accessory_descriptions[:3]]
        accessories = ', '.join(accessory_names)
    else:
        accessories = "主机、数据线、用户手册"

    # 选择模板
    template = DESCRIPTION_TEMPLATES.get(language, DESCRIPTION_TEMPLATES["English"])

    # 填充模板
    description = template.format(
        brand=brand,
        product_name=product_name,
        scene=scene,
        core_capability=core_capability,
        selling_points=selling_points,
        bullet1=bullets[0] if len(bullets) > 0 else "",
        bullet2=bullets[1] if len(bullets) > 1 else "",
        bullet3=bullets[2] if len(bullets) > 2 else "",
        closing_statement="立即购买，开启您的拍摄之旅！",
        accessories=accessories
    )

    return description


def generate_faq(preprocessed_data: PreprocessedData,
                writing_policy: Dict[str, Any],
                language: str = "Chinese") -> List[Dict[str, str]]:
    """
    生成FAQ
    """
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}
    faq_only_capabilities = writing_policy.get('faq_only_capabilities', [])

    # 获取属性参数
    waterproof_depth = attr_data.get('waterproof_depth', '30米')
    battery_life = attr_data.get('battery_life', '150分钟')
    max_storage = attr_data.get('max_storage', '256GB')
    warranty_period = attr_data.get('warranty_period', '12个月')

    # 选择模板
    templates = FAQ_TEMPLATES.get(language, FAQ_TEMPLATES["English"])

    faqs = []
    for template in templates[:5]:  # 最多5条FAQ
        q = template["q"]
        a = template["a"]

        # 替换参数
        a = a.format(
            waterproof_depth=waterproof_depth,
            battery_life=battery_life,
            max_storage=max_storage,
            warranty_period=warranty_period
        )

        faqs.append({"q": q, "a": a})

    # 添加FAQ only能力相关的问题
    for capability in faq_only_capabilities[:2]:  # 最多2条
        if "防抖" in capability or "stabilization" in capability:
            faqs.append({
                "q": "防抖功能有什么限制？" if language == "Chinese" else "Are there any limitations to the stabilization?",
                "a": "数字防抖在剧烈运动中效果有限，建议搭配物理稳定器使用。" if language == "Chinese" else "Digital stabilization has limitations in intense motion, recommended to use with physical stabilizer."
            })
        elif "防水" in capability or "waterproof" in capability:
            faqs.append({
                "q": "防水功能需要注意什么？" if language == "Chinese" else "What should I know about the waterproof feature?",
                "a": "需使用原装防水壳，且深度不超过指定值。" if language == "Chinese" else "Requires the original waterproof case and depth should not exceed specified value."
            })

    return faqs[:5]  # 确保不超过5条


def generate_search_terms(preprocessed_data: PreprocessedData,
                         writing_policy: Dict[str, Any],
                         title: str,
                         bullets: List[str],
                         language: str = "Chinese") -> List[str]:
    """
    生成搜索词
    """
    search_terms = set()
    core_capabilities = preprocessed_data.core_selling_points
    scenes = writing_policy.get('scene_priority', [])

    # 添加核心能力词
    for capability in core_capabilities[:3]:
        search_terms.add(capability)

    # 添加场景词
    for scene in scenes[:3]:
        search_terms.add(scene)

    # 添加类目词
    category_terms = {
        "Chinese": ["运动相机", "户外相机", "摄像机", "拍摄设备"],
        "English": ["action camera", "sports camera", "camcorder", "recording device"],
        "German": ["Actionkamera", "Sportkamera", "Videokamera", "Aufnahmegerät"],
        "French": ["caméra d'action", "caméra sport", "caméscope", "appareil d'enregistrement"],
        "Spanish": ["cámara de acción", "cámara deportiva", "videocámara", "dispositivo de grabación"],
        "Italian": ["videocamera sportiva", "fotocamera sportiva", "videocamera", "dispositivo di registrazione"],
        "Japanese": ["アクションカメラ", "スポーツカメラ", "ビデオカメラ", "録画装置"]
    }

    for term in category_terms.get(language, category_terms["English"]):
        search_terms.add(term)

    # 添加品牌词（如果品牌不是默认的）
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"
    if brand != "TOSBARRFT":
        search_terms.add(brand)

    # 转换为列表并确保不超过250字节
    term_list = list(search_terms)
    filtered_terms = []
    total_bytes = 0

    for term in term_list:
        term_bytes = len(term.encode('utf-8'))
        if total_bytes + term_bytes + (1 if filtered_terms else 0) <= 250:  # 逗号分隔
            filtered_terms.append(term)
            total_bytes += term_bytes + (1 if filtered_terms else 0)
        else:
            break

    return filtered_terms


def generate_aplus_content(preprocessed_data: PreprocessedData,
                          writing_policy: Dict[str, Any],
                          language: str = "Chinese") -> str:
    """
    生成A+内容
    """
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"
    core_capabilities = preprocessed_data.core_selling_points
    scenes = writing_policy.get('scene_priority', [])
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}

    # 提取参数
    resolution = attr_data.get('video_resolution', '4K 30fps')
    waterproof_depth = attr_data.get('waterproof_depth', '30米')
    battery_life = attr_data.get('battery_life', '150分钟')
    weight = attr_data.get('weight', '150g')
    max_storage = attr_data.get('max_storage', '256GB')
    warranty_period = attr_data.get('warranty_period', '12个月')

    # A+内容模板
    if language == "Chinese":
        aplus = f"""# {brand} 运动相机 - 专业拍摄解决方案

## 产品概述
{brand} 运动相机专为{', '.join(scenes[:3])}等场景设计，提供专业级拍摄体验。具备{', '.join(core_capabilities[:3])}等核心功能，满足多种拍摄需求。

## 核心技术
### 1. 高清影像系统
- 支持{resolution}超高清录制
- 先进图像处理引擎，色彩还原真实
- 宽广动态范围，逆光表现优异
- 低光环境拍摄优化，夜拍效果清晰

### 2. 专业防抖技术
- 多重防抖模式（电子防抖+算法补偿）
- 运动场景优化，跑步骑行稳定如初
- 流畅拍摄体验，视频无抖动拖影
- 智能识别运动状态，自动调整防抖等级

### 3. 耐用设计
- {waterproof_depth}防水性能，雨天水下无忧使用
- 轻量化设计，仅{weight}，携带无负担
- 防震防摔结构，1米跌落测试通过
- 高温低温耐受，-10°C 至 45°C 正常工作

## 使用场景
### 户外运动
- 骑行、滑雪、登山等运动记录
- 防水设计适应各种天气
- 长续航支持全天拍摄
- 多种配件适配头盔、车把、手腕

### 旅行记录
- 轻便易携，旅行好伴侣
- 快速分享旅行精彩瞬间
- 多种拍摄模式选择（延时、慢动作、连拍）
- 地理标记功能，记录旅行轨迹

### 家庭使用
- 宠物日常记录，捕捉萌宠瞬间
- 家庭活动拍摄，生日聚会留念
- 儿童成长记录，珍贵时刻永久保存
- 室内拍摄优化，光线不足也能清晰成像

## 安装与使用指南
### 快速入门
1. 安装内存卡：打开侧盖，插入Micro SD卡（最大{max_storage}）
2. 充电开机：使用附赠数据线充电，长按电源键3秒开机
3. 连接APP：下载官方APP，通过WiFi连接相机
4. 开始拍摄：选择拍摄模式，点击录制键开始记录

### 配件安装
- 头盔安装：使用头盔底座，3M胶固定
- 车把安装：使用车把夹具，适配22-35mm直径
- 胸前安装：使用胸带，调整松紧度
- 防水壳安装：确保密封圈清洁，锁紧卡扣

## 维护与保养
- 清洁：使用软布擦拭镜头，避免使用腐蚀性清洁剂
- 存储：长时间不用时，请将电池取出单独存放
- 防水壳维护：每次使用后请用清水冲洗，晾干后保存
- 电池保养：避免完全放电，建议电量低于20%时充电

## 技术规格
- 分辨率：{resolution}
- 传感器：1/2.3英寸CMOS
- 防水等级：{waterproof_depth}
- 电池续航：{battery_life}
- 产品重量：{weight}
- 存储支持：Micro SD卡，最大{max_storage}
- 连接方式：WiFi 2.4GHz, USB-C, HDMI输出
- 屏幕：2英寸LCD触摸屏 + 1.5英寸前置屏幕
- 拍摄模式：视频、照片、延时、慢动作、连拍
- 系统语言：多语言支持（中文、英文、德文、法文等）

## 包装内容
- {brand} 运动相机主机 x1
- 防水壳 x1
- 车把夹具 x1
- 头盔底座 x1
- 胸带 x1
- 数据线 x1
- 用户手册 x1
- 保修卡 x1

## 保修与支持
- 保修期限：{warranty_period}
- 售后服务：全国联保，在线技术支持
- 配件购买：官方商城提供原装配件
- 软件更新：定期固件更新，提升性能

立即体验{brand}运动相机，记录每一个精彩瞬间！专业拍摄，简单操作，让每一刻都成为永恒。"""
    else:
        # 英文版（也用于德语、法语等）
        aplus = f"""# {brand} Action Camera - Professional Shooting Solution

## Product Overview
The {brand} Action Camera is designed for {', '.join(scenes[:3])} and other scenarios, delivering professional-grade shooting experience. Features core capabilities like {', '.join(core_capabilities[:3])} to meet various shooting needs.

## Core Technologies
### 1. High-Definition Imaging System
- Supports {resolution} ultra HD recording
- Advanced image processing engine for true-to-life colors
- Wide dynamic range for excellent backlight performance
- Low-light optimization for clear night shots

### 2. Professional Stabilization Technology
- Multiple stabilization modes (EIS + algorithm compensation)
- Sports scene optimization for running and biking
- Smooth shooting experience with no shake or blur
- Intelligent motion recognition with auto stabilization adjustment

### 3. Durable Design
- {waterproof_depth} waterproof performance for rain and underwater use
- Lightweight design, only {weight}, easy to carry
- Shock and drop resistant structure, tested for 1m drops
- Temperature tolerance from -10°C to 45°C for reliable operation

## Usage Scenarios
### Outdoor Sports
- Recording for biking, skiing, hiking, and other sports
- Waterproof design adapts to various weather conditions
- Long battery life supports all-day shooting
- Multiple accessories for helmet, handlebar, and wrist mounting

### Travel Recording
- Portable and easy to carry, perfect travel companion
- Quick sharing of travel highlights via smartphone app
- Multiple shooting modes (time-lapse, slow motion, burst)
- GPS geotagging to record travel routes

### Family Use
- Daily pet recording to capture cute moments
- Family activity shooting for birthdays and gatherings
- Children's growth records to preserve precious memories
- Indoor shooting optimization for clear imaging in low light

## Installation & Usage Guide
### Quick Start
1. Install memory card: Open side cover, insert Micro SD card (up to {max_storage})
2. Charge and power on: Use included cable to charge, press power button for 3 seconds
3. Connect APP: Download official APP, connect via WiFi
4. Start shooting: Select shooting mode, press record button

### Accessory Installation
- Helmet mount: Use helmet base with 3M adhesive
- Handlebar mount: Use handlebar clamp for 22-35mm diameter
- Chest mount: Use chest strap, adjust tightness
- Waterproof case: Ensure seal is clean, lock clasps securely

## Maintenance & Care
- Cleaning: Use soft cloth for lens, avoid corrosive cleaners
- Storage: Remove battery when not in use for extended periods
- Waterproof case care: Rinse with fresh water after use, dry before storage
- Battery care: Avoid complete discharge, charge when below 20%

## Technical Specifications
- Resolution: {resolution}
- Sensor: 1/2.3-inch CMOS
- Waterproof Rating: {waterproof_depth}
- Battery Life: {battery_life}
- Product Weight: {weight}
- Storage Support: Micro SD card, up to {max_storage}
- Connectivity: WiFi 2.4GHz, USB-C, HDMI output
- Screens: 2-inch LCD touchscreen + 1.5-inch front screen
- Shooting Modes: Video, Photo, Time-lapse, Slow Motion, Burst
- System Languages: Multiple languages (English, German, French, Spanish, etc.)

## Package Contents
- {brand} Action Camera Main Unit x1
- Waterproof Case x1
- Handlebar Mount x1
- Helmet Mount x1
- Chest Strap x1
- Data Cable x1
- User Manual x1
- Warranty Card x1

## Warranty & Support
- Warranty Period: {warranty_period}
- After-sales Service: Nationwide warranty, online technical support
- Accessory Purchase: Original accessories available in official store
- Software Updates: Regular firmware updates for performance improvements

Experience the {brand} Action Camera now and record every exciting moment! Professional shooting, simple operation, make every moment last forever."""

    return aplus


def generate_listing_copy(preprocessed_data: PreprocessedData,
                         writing_policy: Dict[str, Any],
                         language: str = "Chinese") -> Dict[str, Any]:
    """
    生成完整的Listing文案

    Args:
        preprocessed_data: 预处理数据
        writing_policy: writing_policy策略
        language: 目标语言

    Returns:
        包含所有文案组件的字典
    """
    # 提取L1关键词
    l1_keywords = extract_l1_keywords(preprocessed_data.keyword_data, language)

    # 生成标题
    title = generate_title(preprocessed_data, writing_policy, l1_keywords)

    # 生成bullet points
    bullets = generate_bullet_points(preprocessed_data, writing_policy, language)

    # 生成描述
    description = generate_description(preprocessed_data, writing_policy, title, bullets, language)

    # 生成FAQ
    faq = generate_faq(preprocessed_data, writing_policy, language)

    # 生成搜索词
    search_terms = generate_search_terms(preprocessed_data, writing_policy, title, bullets, language)

    # 生成A+内容
    aplus_content = generate_aplus_content(preprocessed_data, writing_policy, language)

    # 构建完整文案
    copy_dict = {
        "title": title,
        "bullets": bullets,
        "description": description,
        "faq": faq,
        "search_terms": search_terms,
        "aplus_content": aplus_content,
        "metadata": {
            "language": language,
            "title_length": len(title),
            "bullets_count": len(bullets),
            "description_length": len(description),
            "faq_count": len(faq),
            "search_terms_count": len(search_terms),
            "aplus_content_length": len(aplus_content),
            "generated_at": preprocessed_data.processed_at
        }
    }

    return copy_dict


def save_copy_to_file(copy_dict: Dict[str, Any], filepath: str):
    """保存文案到文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(copy_dict, f, ensure_ascii=False, indent=2)


def load_copy_from_file(filepath: str) -> Dict[str, Any]:
    """从文件加载文案"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    # 测试代码
    from dataclasses import dataclass

    @dataclass
    class MockKeywordData:
        keywords: List[Dict[str, Any]]

    @dataclass
    class MockAttributeData:
        data: Dict[str, Any]

    @dataclass
    class MockRunConfig:
        brand_name: str

    # 创建模拟数据
    mock_preprocessed = PreprocessedData(
        run_config=MockRunConfig(brand_name="TOSBARRFT"),
        attribute_data=MockAttributeData(data={
            "video_resolution": "4K 30fps",
            "waterproof_depth": "30米",
            "battery_life": "150分钟",
            "weight": "150g",
            "max_storage": "256GB",
            "warranty_period": "12个月"
        }),
        keyword_data=MockKeywordData(keywords=[
            {"keyword": "action camera", "search_volume": 15000},
            {"keyword": "sports camera", "search_volume": 8000},
            {"keyword": "waterproof camera", "search_volume": 12000}
        ]),
        review_data=None,
        aba_data=None,
        core_selling_points=["4K录像", "防抖", "防水", "WiFi连接", "双屏幕"],
        accessory_descriptions=[
            {"name": "防水壳", "specification": "30米防水"},
            {"name": "数据线", "specification": "USB-C"}
        ],
        quality_score=85,
        language="Chinese",
        processed_at="2024-01-01T00:00:00"
    )

    mock_writing_policy = {
        "scene_priority": ["户外运动", "骑行记录", "水下探索"],
        "capability_scene_bindings": [],
        "faq_only_capabilities": ["数字防抖限制说明"],
        "forbidden_pairs": [],
        "bullet_slot_rules": {},
        "language": "Chinese"
    }

    copy_dict = generate_listing_copy(mock_preprocessed, mock_writing_policy, "Chinese")
    print("生成的文案:")
    print(f"标题: {copy_dict['title']}")
    print(f"\nBullet Points ({len(copy_dict['bullets'])}条):")
    for i, bullet in enumerate(copy_dict['bullets'], 1):
        print(f"{i}. {bullet}")
    print(f"\n描述 (长度: {len(copy_dict['description'])}字符):")
    print(copy_dict['description'][:200] + "...")
    print(f"\nFAQ ({len(copy_dict['faq'])}条):")
    for i, faq_item in enumerate(copy_dict['faq'], 1):
        print(f"{i}. Q: {faq_item['q']}")
        print(f"   A: {faq_item['a']}")
    print(f"\n搜索词 ({len(copy_dict['search_terms'])}个): {', '.join(copy_dict['search_terms'])}")
    print(f"\nA+内容长度: {len(copy_dict['aplus_content'])}字符")