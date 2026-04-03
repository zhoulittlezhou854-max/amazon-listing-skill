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
from dataclasses import dataclass, field


@dataclass
class PreprocessedData:
    """预处理数据类（简化版）"""
    run_config: Any
    attribute_data: Any
    keyword_data: Any
    review_data: Any
    aba_data: Any
    real_vocab: Any = None  # 真实国家词表（Priority 1）
    core_selling_points: List[str] = field(default_factory=list)
    accessory_descriptions: List[Dict[str, Any]] = field(default_factory=list)
    quality_score: int = 0
    language: str = "English"
    processed_at: str = ""


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

# Bullet point模板 (English content only — final translation done by copy_generation layer)
BULLET_TEMPLATES = {
    "B1": {
        "Chinese": "【挂载系统+主场景+P0能力】{content}",
        "English": "【Mounting System + Primary Scene + P0 Capability】{content}",
        "German": "【Halterungssystem + Hauptszene + P0-Fähigkeit】{content}",
        "French": "【Système de montage + Scène principale + Capacité P0】{content}",
        "Spanish": "【Sistema de montaje + Escena principal + Capacidad P0】{content}",
        "Italian": "【Sistema di montaggio + Scena principale + Capacità P0】{content}"
    },
    "B2": {
        "Chinese": "【P0核心能力+量化参数】{content}",
        "English": "【P0 Core Capability + Quantified Parameters】{content}",
        "German": "【P0-Kernfähigkeit + Quantifizierte Parameter】{content}",
        "French": "【Capacité principale P0 + Paramètres quantifiés】{content}",
        "Spanish": "【Capacidad central P0 + Parámetros cuantificados】{content}",
        "Italian": "【Capacità core P0 + Parametri quantificati】{content}"
    },
    "B3": {
        "Chinese": "【P1竞品痛点对比+场景词】{content}",
        "English": "【P1 Competitor Pain Point Comparison + Scene Keywords】{content}",
        "German": "【P1-Wettbewerbsvergleich + Szenewörter】{content}",
        "French": "【Comparaison P1 avec concurrents + Mots-clés de scène】{content}",
        "Spanish": "【Comparación P1 con competidores + Palabras clave de escena】{content}",
        "Italian": "【Confronto P1 con concorrenti + Parole chiave di scena】{content}"
    },
    "B4": {
        "Chinese": "【P1/P2能力+使用场景+边界声明句】{content}",
        "English": "【P1/P2 Capability + Usage Scene + Boundary Statement】{content}",
        "German": "【P1/P2-Fähigkeit + Anwendungsszene + Einschränkungshinweis】{content}",
        "French": "【Capacité P1/P2 + Scène d'utilisation + Avertissement】{content}",
        "Spanish": "【Capacidad P1/P2 + Escena de uso + Aviso】{content}",
        "Italian": "【Capacità P1/P2 + Scena di utilizzo + Avviso】{content}"
    },
    "B5": {
        "Chinese": "【P2质保/售后/兼容性】{content}",
        "English": "【P2 Warranty/After-sale/Compatibility】{content}",
        "German": "【P2-Garantie/Kundendienst/Kompatibilität】{content}",
        "French": "【P2 Garantie/Service après-vente/Compatibilité】{content}",
        "Spanish": "【P2 Garantía/Servicio postventa/Compatibilidad】{content}",
        "Italian": "【P2 Garanzia/Assistenza post-vendita/Compatibilità】{content}"
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
    ],
    "German": [
        "(mit Wassergehäuse)",
        "(in bestimmten Modi)",
        "(basierend auf Labortests)",
        "(mit enthaltenem Zubehör)",
        "(erfordert Smartphone-App-Verbindung)"
    ],
    "French": [
        "(avec boîtier waterproof)",
        "(dans des modes spécifiques)",
        "(basé sur des tests en laboratoire)",
        "(avec accessoires inclus)",
        "(nécessite connexion à l'application smartphone)"
    ],
    "Spanish": [
        "(con carcasa waterproof)",
        "(en modos específicos)",
        "(basado en pruebas de laboratorio)",
        "(con accesorios incluidos)",
        "(requiere conexión a la aplicación del teléfono)"
    ],
    "Italian": [
        "(con custodia waterproof)",
        "(in modalità specifiche)",
        "(basato su test di laboratorio)",
        "(con accessori inclusi)",
        "(richiede connessione all'app smartphone)"
    ]
}

DESCRIPTION_CLOSING_STATEMENTS = {
    "English": "Buy now and start capturing your moments!",
    "German": "Jetzt kaufen und Ihre Aufnahmeerlebnisse beginnen!",
    "French": "Achetez maintenant et commencez à capturer vos moments!",
    "Spanish": "¡Compra ahora y comienza a capturar tus momentos!",
    "Italian": "Acquista ora e inizia a catturare i tuoi momenti!",
    "Chinese": "立即购买，开启您的拍摄之旅！"
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
    ],
    "German": [
        {"q": "Ist das Produkt wasserdicht?", "a": "Ja, es wird mit einem Wassergehäuse geliefert, das {waterproof_depth} unterstützt."},
        {"q": "Wie lange hält der Akku?", "a": "Der Akku hält ca. {battery_life} und unterstützt Aufladen während der Aufnahme."},
        {"q": "Welche Speicherkarten werden unterstützt?", "a": "Unterstützt Micro SD-Karten bis zu {max_storage}."},
        {"q": "Wie übertrage ich Dateien?", "a": "Dateien können über WLAN oder USB-Verbindung übertragen werden."},
        {"q": "Wie lang ist die Garantiezeit?", "a": "{warranty_period} Garantie mit deutschlandweitem Service."}
    ],
    "French": [
        {"q": "Le produit est-t-il waterproof?", "a": "Oui, il est livré avec un boîtier waterproof supportant {waterproof_depth}."},
        {"q": "Quelle est l'autonomie de la batterie?", "a": "La batterie dure environ {battery_life} et supporte la charge pendant l'enregistrement."},
        {"q": "Quelles cartes mémoire sont supportées?", "a": "Supporte les cartes Micro SD jusqu'à {max_storage}."},
        {"q": "Comment transférer les fichiers?", "a": "Les fichiers peuvent être transférés via WiFi ou connexion USB."},
        {"q": "Quelle est la période de garantie?", "a": "Garantie {warranty_period} avec couverture nationale."}
    ],
    "Spanish": [
        {"q": "¿El producto es resistente al agua?", "a": "Sí, viene con una carcasa waterproof que soporta {waterproof_depth}."},
        {"q": "¿Cuánto dura la batería?", "a": "La batería dura unos {battery_life} y soporta carga durante la grabación."},
        {"q": "¿Qué tarjetas de memoria son compatibles?", "a": "Soporta tarjetas Micro SD hasta {max_storage}."},
        {"q": "¿Cómo transfiero los archivos?", "a": "Los archivos se pueden transferir por WiFi o conexión USB."},
        {"q": "¿Cuál es el período de garantía?", "a": "Garantía de {warranty_period} con cobertura nacional."}
    ],
    "Italian": [
        {"q": "Il prodotto è impermeabile?", "a": "Sì, viene fornito con una custodia waterproof che supporta {waterproof_depth}."},
        {"q": "Quanto dura la batteria?", "a": "La batteria dura circa {battery_life} e supporta la ricarica durante la registrazione."},
        {"q": "Quali schede di memoria sono supportate?", "a": "Supporta schede Micro SD fino a {max_storage}."},
        {"q": "Come trasferisco i file?", "a": "I file possono essere trasferiti tramite WiFi o connessione USB."},
        {"q": "Qual è il periodo di garanzia?", "a": "Garanzia di {warranty_period} con copertura nazionale."}
    ]
}


def _has_real_vocab(preprocessed_data: Any) -> bool:
    """检查是否有真实国家词表（Priority 1）"""
    rv = getattr(preprocessed_data, "real_vocab", None)
    if rv is None:
        # Fallback: 检查 real_vocab 是否为 dict（来自JSON反序列化）
        rv_dict = getattr(preprocessed_data, "__dict__", {}).get("real_vocab")
        if rv_dict and isinstance(rv_dict, dict) and rv_dict.get("is_available"):
            return True
        return False
    return getattr(rv, "is_available", False)


def _reconstruct_real_vocab(preprocessed_data: Any) -> Any:
    """
    尝试从 preprocessed_data 重建 RealVocabData 对象。
    处理三种情况：
    1. real_vocab 是 RealVocabData 对象（正常情况）
    2. real_vocab 是 dict（来自 JSON 反序列化）
    3. real_vocab 嵌套在 preprocessed_data 的某个子对象中
    """
    # 情况1: 直接属性
    rv = getattr(preprocessed_data, "real_vocab", None)
    if rv is not None and not isinstance(rv, dict):
        if getattr(rv, "is_available", False):
            return rv
        return None

    # 情况2: __dict__ 中的 dict
    rv_dict = getattr(preprocessed_data, "__dict__", {}).get("real_vocab")
    if rv_dict and isinstance(rv_dict, dict) and rv_dict.get("is_available"):
        class ReconstructedRealVocab:
            def __init__(self, d):
                self.country = d.get("country", "")
                self.is_available = d.get("is_available", False)
                self.total_count = d.get("total_count", 0)
                self.aba_count = d.get("aba_count", 0)
                self.order_winning_count = d.get("order_winning_count", 0)
                self.review_count = d.get("review_count", 0)
                self.top_keywords = d.get("top_keywords", []) or []
                self.data_mode = d.get("data_mode", "SYNTHETIC_COLD_START")
        return ReconstructedRealVocab(rv_dict)

    # 情况3: 嵌套在 preprocessed_data.real_vocab 本身是 dict 的情况
    if isinstance(rv, dict) and rv.get("is_available"):
        class ReconstructedRealVocab:
            def __init__(self, d):
                self.country = d.get("country", "")
                self.is_available = d.get("is_available", False)
                self.total_count = d.get("total_count", 0)
                self.aba_count = d.get("aba_count", 0)
                self.order_winning_count = d.get("order_winning_count", 0)
                self.review_count = d.get("review_count", 0)
                self.top_keywords = d.get("top_keywords", []) or []
                self.data_mode = d.get("data_mode", "SYNTHETIC_COLD_START")
        return ReconstructedRealVocab(rv)

    return None


def extract_tiered_keywords(preprocessed_data: Any, language: str = "Chinese", real_vocab: Any = None) -> Dict[str, List[str]]:
    """
    提取分层关键词（L1/L2/L3），使用与scoring.py一致的阈值逻辑（>=10000是L1）

    优先级:
    - Priority 1: 真实国家词表（preprocessed_data.real_vocab）→ 本地语言关键词
    - Priority 2: keyword_data 中的关键词
    - Priority 3: mapping 中的关键词（默认映射表）
    - Priority 4: [SYNTH] 标记关键词
    """
    # ─── Priority 1: 真实国家词表（DE/FR 本地词） ───
    # 优先使用传入的 real_vocab，其次尝试从 preprocessed_data 重建
    rv = real_vocab
    if rv is None:
        rv = _reconstruct_real_vocab(preprocessed_data)

    if rv is not None and getattr(rv, "is_available", False):
        real_kw = getattr(rv, "top_keywords", []) or []
        if real_kw:
            l1_set, l2_set, l3_set = set(), set(), set()
            for row in real_kw:
                kw = row.get("keyword", "")
                if not kw:
                    continue
                vol = float(row.get("search_volume") or 0)
                if vol >= 10000:
                    l1_set.add(kw.lower())
                elif vol >= 1000:
                    l2_set.add(kw.lower())
                else:
                    l3_set.add(kw.lower())
            return {
                "l1": list(l1_set)[:10],
                "l2": list(l2_set)[:10],
                "l3": list(l3_set)[:10],
            }

    # ─── Priority 2: keyword_data（兼容旧逻辑）───
    keyword_data = getattr(preprocessed_data, "keyword_data", None)
    result = {"l1": [], "l2": [], "l3": []}

    if keyword_data and hasattr(keyword_data, 'keywords'):
        # 使用与scoring.py一致的阈值：L1 >= 10000, L2 >= 1000, L3 < 1000
        l1_set = set()
        l2_set = set()
        l3_set = set()

        for row in keyword_data.keywords:
            keyword = row.get('keyword', '') or row.get('search_term', '')
            if not keyword:
                continue
            volume = float(row.get('search_volume') or 0)

            if volume >= 10000:
                l1_set.add(keyword.lower())
            elif volume >= 1000:
                l2_set.add(keyword.lower())
            else:
                l3_set.add(keyword.lower())

        # 转换为列表
        result["l1"] = list(l1_set)[:5]
        result["l2"] = list(l2_set)[:5]
        result["l3"] = list(l3_set)[:5]
        return result

    # ─── Priority 3: mapping 中的关键词（默认映射表）───
    default_keywords = {
        "Chinese": {"l1": ["运动相机", "4K相机"], "l2": ["防水相机", "防抖相机"], "l3": ["户外相机"]},
        "English": {"l1": ["action camera 4k"], "l2": ["sports camera", "waterproof camera"], "l3": ["helmet camera"]},
        "German": {"l1": ["action camera 4k"], "l2": ["sports camera", "waterproof camera"], "l3": ["helmet camera"]},
        "French": {"l1": ["caméra d'action 4K"], "l2": ["caméra sport", "caméra étanche"], "l3": ["caméra casco"]},
        "Spanish": {"l1": ["cámara de acción 4K"], "l2": ["cámara deportiva", "cámara impermeable"], "l3": ["cámara casco"]},
        "Italian": {"l1": ["videocamera sportiva 4K"], "l2": ["fotocamera sportiva", "fotocamera impermeabile"], "l3": ["fotocamera casco"]},
        "Japanese": {"l1": ["アクションカメラ 4K"], "l2": ["スポーツカメラ", "防水カメラ"], "l3": ["ヘルメットカメラ"]}
    }

    if language in default_keywords:
        return default_keywords[language]

    # ─── Priority 4: [SYNTH] 标记关键词 ───
    return {
        "l1": ["[SYNTH] action camera"],
        "l2": ["[SYNTH] sports camera"],
        "l3": ["[SYNTH] waterproof camera"]
    }


def extract_l1_keywords(keyword_data: Any, language: str = "Chinese") -> List[str]:
    """
    提取L1关键词（月搜索量≥10,000）- 保留兼容性接口
    """
    tiered = extract_tiered_keywords(keyword_data, language)
    return tiered.get("l1", [])


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
                   l1_keywords: List[str],
                   tiered_keywords: Dict[str, List[str]] = None,
                   keyword_allocation_strategy: str = "balanced") -> str:
    """
    生成标题 - 优化版：确保L1关键词在前80字符，多场景覆盖

    keyword_allocation_strategy:
    - "balanced": L1在开头，1个L2
    - "aggressive_l1": 2个L1在开头
    - "l2_focus": L1+L2组合在开头
    - "conservative": 仅1个L1在开头
    """
    language = preprocessed_data.language
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "TOSBARRFT"

    # 获取L2关键词
    l2_keywords = tiered_keywords.get("l2", []) if tiered_keywords else []

    # 获取核心能力
    core_capabilities = preprocessed_data.core_selling_points
    if not core_capabilities:
        core_capabilities = ["4K录像", "防抖", "防水"]

    # 获取场景词（优先使用前4个场景）
    scenes = writing_policy.get('scene_priority', [])
    if len(scenes) < 4:
        scenes.extend(["户外运动", "运动训练", "旅行记录"][:4-len(scenes)])

    # 德语翻译映射
    capability_translation = {}
    scene_translation = {}
    if language == "German":
        capability_translation = {
            "双屏幕": "Dual Screen",
            "EIS防抖": "EIS Bildstabilisierung",
            "防抖": "Bildstabilisierung",
            "WiFi连接": "WiFi Verbindung",
            "防水": "Wasserdicht",
            "4K录像": "4K Aufnahme",
            "高清录像": "HD Aufnahme"
        }
        scene_translation = {
            "骑行记录": "Radfahren",
            "户外运动": "Outdoor Sport",
            "水下探索": "Unterwasser",
            "旅行记录": "Reise",
            "运动训练": "Sporttraining",
            "家庭使用": "Familie"
        }

    # 翻译核心能力
    translated_capabilities = []
    for cap in core_capabilities:
        translated = capability_translation.get(cap, cap)
        if translated == cap:
            for key, value in capability_translation.items():
                if key in cap:
                    translated = cap.replace(key, value)
                    break
        translated_capabilities.append(translated)
    core_capabilities = translated_capabilities

    # 翻译场景词（前4个）
    translated_scenes = []
    for scene in scenes[:4]:
        translated_scenes.append(scene_translation.get(scene, scene))

    # 获取L1关键词（确保至少有一个）
    if not l1_keywords:
        l1_keywords = ["Actionkamera 4K"] if language == "German" else ["action camera 4k"]

    # 构建标题：品牌 + L1关键词 + 场景1 + 核心能力 + 场景2
    # 确保L1关键词在最开始且在前80字符内
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}
    resolution = attr_data.get('video_resolution', '4K')

    # 标题结构：[品牌] [L1] [场景1] [核心能力] [场景2]
    if language == "German":
        # 德语标题模板
        title_parts = [brand]

        # 根据策略确定L1关键词
        if keyword_allocation_strategy == "aggressive_l1":
            # 激进L1策略：放2个L1
            l1_parts = []
            if l1_keywords:
                l1_parts.append(l1_keywords[0])
            if len(l1_keywords) > 1:
                l1_parts.append(l1_keywords[1])
            else:
                l1_parts.append("Actionkamera")
            l1_part = " ".join(l1_parts)
        elif keyword_allocation_strategy == "l2_focus":
            # L2聚焦策略：L1 + L2组合
            l1_part = l1_keywords[0] if l1_keywords else "Actionkamera"
            l2_part = l2_keywords[0] if l2_keywords else "Sportkamera"
            l1_part = f"{l1_part} {l2_part}"
        elif keyword_allocation_strategy == "conservative":
            # 保守策略：仅1个L1
            l1_part = l1_keywords[0] if l1_keywords else "Actionkamera 4K"
        else:
            # balanced默认：1个L1 + 可能1个L2
            l1_part = l1_keywords[0] if l1_keywords else "Actionkamera 4K"
            if l2_keywords and len(title_parts) + len(l1_part) < 50:
                l1_part = f"{l1_part} {l2_keywords[0]}"

        title_parts.append(l1_part)

        # 添加第一个场景
        if translated_scenes:
            title_parts.append(translated_scenes[0])

        # 添加核心能力（带分辨率）
        if core_capabilities:
            title_parts.append(f"{core_capabilities[0]} {resolution}")

        # 添加第二个场景增加覆盖率
        if len(translated_scenes) > 1:
            title_parts.append(translated_scenes[1])

        title = " ".join(title_parts)
    else:
        # 英文/其他语言模板
        title_parts = [brand]

        # 根据策略确定L1关键词
        if keyword_allocation_strategy == "aggressive_l1":
            l1_parts = []
            if l1_keywords:
                l1_parts.append(l1_keywords[0])
            if len(l1_keywords) > 1:
                l1_parts.append(l1_keywords[1])
            else:
                l1_parts.append("action camera")
            l1_part = " ".join(l1_parts)
        elif keyword_allocation_strategy == "l2_focus":
            l1_part = l1_keywords[0] if l1_keywords else "Action Camera"
            l2_part = l2_keywords[0] if l2_keywords else "sports camera"
            l1_part = f"{l1_part} {l2_part}"
        elif keyword_allocation_strategy == "conservative":
            l1_part = l1_keywords[0] if l1_keywords else "Action Camera 4K"
        else:
            l1_part = l1_keywords[0] if l1_keywords else "Action Camera"

        title_parts.append(l1_part)
        if translated_scenes:
            title_parts.append(translated_scenes[0])
        if core_capabilities:
            title_parts.append(f"{core_capabilities[0]} {resolution}")
        if len(translated_scenes) > 1:
            title_parts.append(translated_scenes[1])
        title = " ".join(title_parts)

    # 清理多余空格
    title = re.sub(r'\s+', ' ', title).strip()

    # 如果标题太长，确保L1关键词仍在80字符内
    if len(title) > 180:
        # 截断但保留L1关键词
        title = title[:177] + "..."

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
                          language: str = "English",
                          tiered_keywords: Dict[str, List[str]] = None,
                          keyword_allocation_strategy: str = "balanced") -> List[str]:
    """
    生成5条bullet points (English content — translated to target language by caller)

    keyword_allocation_strategy:
    - "balanced": L1 in B1, L2 in B2-B3, L3 in B4-B5
    - "aggressive_l1": L1 in B1-B3, L2 in B4, L3 in B5
    - "l2_focus": L2 in B1-B4, L3 in B5
    - "conservative": L1 only in B1-B2, L3 in B3-B5
    """
    bullets = []
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "Brand"
    core_capabilities = preprocessed_data.core_selling_points
    # scene_priority is now English labels (PRD v8.2)
    scenes = writing_policy.get('scene_priority', [])
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}

    # Fallback scenes (English)
    default_scenes = ["outdoor_sports", "cycling_recording", "underwater_exploration", "travel_documentation", "family_use"]
    while len(scenes) < 4:
        scenes.extend([s for s in default_scenes if s not in scenes][:4-len(scenes)])

    # Extract attributes
    waterproof_depth = attr_data.get('waterproof_depth', '30m')
    battery_life = attr_data.get('battery_life', '150min')
    resolution = attr_data.get('video_resolution', '4K 30fps')
    weight = attr_data.get('weight', '150g')
    max_storage = attr_data.get('max_storage', '256GB')
    warranty_period = attr_data.get('warranty_period', '12 months')

    # Get L1/L2/L3 keywords
    l1_keywords = tiered_keywords.get("l1", []) if tiered_keywords else []
    l2_keywords = tiered_keywords.get("l2", []) if tiered_keywords else []
    l3_keywords = tiered_keywords.get("l3", []) if tiered_keywords else []

    # English scene labels (internal)
    scene1 = scenes[0]  # e.g. "cycling_recording"
    scene2 = scenes[1] if len(scenes) > 1 else scenes[0]
    scene3 = scenes[2] if len(scenes) > 2 else scenes[0]
    scene4 = scenes[3] if len(scenes) > 3 else scenes[0]
    capability1 = core_capabilities[0] if core_capabilities else "4K recording"
    capability2 = core_capabilities[1] if len(core_capabilities) > 1 else capability1
    capability3 = core_capabilities[2] if len(core_capabilities) > 2 else capability1

    # B1: Mounting + Primary scene + P0 capability
    template = BULLET_TEMPLATES["B1"].get(language, BULLET_TEMPLATES["B1"]["English"])
    content = (f"Comes with multiple mounting accessories, designed for {scene1}, "
               f"features {capability1}, supports {waterproof_depth} waterproof")
    bullets.append(template.format(content=content))

    # B2: P0 core capability + second scene + quantified params
    template = BULLET_TEMPLATES["B2"].get(language, BULLET_TEMPLATES["B2"]["English"])
    if "4K" in capability1 or "录像" in capability1 or "recording" in capability1.lower():
        content = (f"Supports {resolution} HD recording, optimized for {scene2}, "
                   f"battery life {battery_life}")
    elif "防抖" in capability1 or "stabilization" in capability1.lower() or "stabil" in capability1.lower():
        content = (f"Advanced stabilization technology, ideal for {scene2}, "
                   f"battery life {battery_life}")
    elif "防水" in capability1 or "waterproof" in capability1.lower():
        content = (f"Supports {waterproof_depth} waterproof, suitable for {scene2}, "
                   f"weighs only {weight}")
    else:
        content = (f"Features {capability1}, suitable for {scene2}, "
                   f"reliable and excellent performance")
    bullets.append(template.format(content=content))

    # B3: L2 keyword + third scene + competitor comparison
    template = BULLET_TEMPLATES["B3"].get(language, BULLET_TEMPLATES["B3"]["English"])
    if keyword_allocation_strategy == "aggressive_l1":
        lx_word = l1_keywords[1] if len(l1_keywords) > 1 else (l1_keywords[0] if l1_keywords else "waterproof action camera")
    elif keyword_allocation_strategy == "l2_focus":
        lx_word = l2_keywords[0] if l2_keywords else "waterproof action camera"
    elif keyword_allocation_strategy == "conservative":
        lx_word = l3_keywords[0] if l3_keywords else "versatile design"
    else:  # balanced
        lx_word = l2_keywords[0] if l2_keywords else "waterproof action camera"

    content = (f"Compared to competitors, {lx_word} performs better in {scene3}, "
               f"battery life {battery_life}")
    bullets.append(template.format(content=content))

    # B4: L3 keyword + fourth scene + boundary statement
    template = BULLET_TEMPLATES["B4"].get(language, BULLET_TEMPLATES["B4"]["English"])
    boundary = random.choice(BOUNDARY_STATEMENTS.get(language, BOUNDARY_STATEMENTS["English"]))
    if keyword_allocation_strategy == "aggressive_l1":
        lx_word = l2_keywords[0] if l2_keywords else "versatile design"
    elif keyword_allocation_strategy == "l2_focus":
        lx_word = l2_keywords[1] if len(l2_keywords) > 1 else (l3_keywords[0] if l3_keywords else "versatile design")
    elif keyword_allocation_strategy == "conservative":
        lx_word = l3_keywords[0] if l3_keywords else "versatile design"
    else:  # balanced
        lx_word = l3_keywords[0] if l3_keywords else "versatile design"

    content = (f"{lx_word}, suitable for {scene4} {boundary}, "
               f"max storage {max_storage}")
    bullets.append(template.format(content=content))

    # B5: P2 warranty/after-sale + quantified params
    template = BULLET_TEMPLATES["B5"].get(language, BULLET_TEMPLATES["B5"]["English"])
    content = (f"Provides {warranty_period} warranty, professional customer support, "
               f"compatible with multiple devices, battery life {battery_life}")
    bullets.append(template.format(content=content))

    # Clean template markers
    bullets = [clean_bullet_text(bullet) for bullet in bullets]

    # Ensure each bullet ≤ 250 chars
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
        product_name = "action camera"

    # 获取场景 (English labels)
    scene = scenes[0] if scenes else "outdoor sports"

    # 获取核心能力
    core_capability = core_capabilities[0] if core_capabilities else "4K recording"

    # 构建卖点描述
    selling_points = ""
    if len(core_capabilities) > 1:
        selling_points = f"Features {', '.join(core_capabilities[:3])} and more, "
    else:
        selling_points = f"Features {core_capability}, "

    # 配件列表
    accessories = ""
    if accessory_descriptions:
        accessory_names = [acc.get('name', 'accessory') for acc in accessory_descriptions[:3]]
        accessories = ', '.join(accessory_names)
    else:
        accessories = "main unit, data cable, user manual"

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
        closing_statement=DESCRIPTION_CLOSING_STATEMENTS.get(language, DESCRIPTION_CLOSING_STATEMENTS["English"]),
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
                         language: str = "Chinese",
                         tiered_keywords: Dict[str, List[str]] = None) -> List[str]:
    """
    生成搜索词 - 优化版：优先使用L2/L3长尾关键词
    """
    search_terms = set()
    core_capabilities = preprocessed_data.core_selling_points
    scenes = writing_policy.get('scene_priority', [])

    # 获取L2/L3关键词（优先使用长尾词）
    l2_keywords = tiered_keywords.get("l2", []) if tiered_keywords else []
    l3_keywords = tiered_keywords.get("l3", []) if tiered_keywords else []

    # 添加L2/L3长尾关键词（优先）
    for kw in l2_keywords[:3]:
        search_terms.add(kw)
    for kw in l3_keywords[:3]:
        search_terms.add(kw)

    # 添加核心能力词
    for capability in core_capabilities[:3]:
        search_terms.add(capability)

    # 添加场景词
    for scene in scenes[:4]:  # 增加到4个场景
        search_terms.add(scene)

    # 添加L1类目词（英文原词用于搜索）
    l1_keywords = tiered_keywords.get("l1", []) if tiered_keywords else []
    for kw in l1_keywords[:2]:
        search_terms.add(kw)

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


# ==================== PRD v8.2 Node 4 多语言生成 ====================

# -----------------------------------------------------------------------
# 能力词翻译映射 (English / Chinese -> Target Language)
# 优先顺序: English精确匹配 > 中文能力词 > 英文子串匹配
# -----------------------------------------------------------------------
CAPABILITY_TRANSLATIONS = {
    "German": {
        # --- 4K/高清录像 (English phrases first for phrase-match priority) ---
        "4K recording": "4K-Aufnahme",
        "HD recording": "HD-Aufnahme",
        "advanced stabilization technology": "fortschrittliche Stabilisierungstechnologie",
        "stabilization technology": "Stabilisierungstechnologie",
        "action camera": "Actionkamera",
        "waterproof action camera": "wasserdichte Actionkamera",
        "sports camera": "Sportkamera",
        "versatile design": "vielseitiges Design",
        # --- 4K/高清录像 ---
        "4K录像": "4K-Aufnahme",
        "4K video": "4K-Video",
        "4K": "4K",
        "4K 30fps": "4K 30fps",
        "高清录像": "HD-Aufnahme",
        "HD video": "HD-Video",
        "高清": "HD",
        "recording": "Aufnahme",
        "video": "Video",
        # --- 防抖/Stabilization ---
        "防抖": "Bildstabilisierung",
        "EIS防抖": "EIS-Bildstabilisierung",
        "stabilization": "Bildstabilisierung",
        "stabilizer": "Stabilisierung",
        "EIS": "EIS",
        "image stabilization": "Bildstabilisierung",
        "electronic stabilization": "elektronische Bildstabilisierung",
        "electronic": "elektronisch",
        "stabilisation": "Bildstabilisierung",
        # --- 防水/Waterproof ---
        "防水": "wasserdicht",
        "防水壳": "Wassergehäuse",
        "waterproof": "wasserdicht",
        "30米防水": "30m wasserdicht",
        "waterproof case": "Wassergehäuse",
        "waterproof depth": "Wassertiefe",
        # --- WiFi/连接 ---
        "WiFi连接": "WLAN-Verbindung",
        "WiFi": "WLAN",
        "wifi": "WLAN",
        "wifi connection": "WLAN-Verbindung",
        "WLAN": "WLAN",
        "USB": "USB",
        "USB-C": "USB-C",
        "HDMI": "HDMI",
        # --- 双屏幕/Dual screen ---
        "双屏幕": "Dual-Display",
        "dual screen": "Dual-Display",
        "前屏幕": "Frontdisplay",
        "front screen": "Frontdisplay",
        "触摸屏": "Touchscreen",
        "touch screen": "Touchscreen",
        "LCD": "LCD",
        # --- 续航/Battery ---
        "长续航": "lange Akkulaufzeit",
        "电池续航": "Akkulaufzeit",
        "电池": "Akku",
        "battery life": "Akkulaufzeit",
        "long battery": "lange Akkulaufzeit",
        "battery": "Akku",
        "charging": "Aufladen",
        "边充边用": "Aufladen während der Aufnahme",
        # --- 存储/Storage ---
        "存储": "Speicher",
        "存储卡": "Speicherkarte",
        "Micro SD": "Micro SD",
        "256GB": "256GB",
        "max storage": "maximaler Speicher",
        "memory card": "Speicherkarte",
        # --- 安装配件/Mounting ---
        "挂载配件": "Montage-Zubehör",
        "头盔支架": "Helmhalterung",
        "helmet mount": "Helmhalterung",
        "车把支架": "Lenkerhalterung",
        "handlebar mount": "Lenkerhalterung",
        "胸带": "Brustgurt",
        "chest strap": "Brustgurt",
        "支架": "Halterung",
        "mount": "Halterung",
        "磁吸挂绳": "Magnet-Halsband",
        "magnetic strap": "Magnet-Halsband",
        # --- 拍摄模式/Shooting modes ---
        "延时": "Zeitraffer",
        "time-lapse": "Zeitraffer",
        "慢动作": "Zeitlupe",
        "slow motion": "Zeitlupe",
        "连拍": "Serienaufnahme",
        "burst": "Serienaufnahme",
        # --- 其他能力 ---
        "轻便": "leicht",
        "lightweight": "leicht",
        "GPS": "GPS",
        "geotagging": "Geotagging",
        "APP": "App",
        "app": "App",
        "智能手机": "Smartphone",
        "smartphone": "Smartphone",
        # --- 质保/Warranty ---
        "质保": "Garantie",
        "warranty": "Garantie",
        "保修": "Garantie",
        "12个月": "12 Monate",
        "12 months": "12 Monate",
        "全国联保": " deutschlandweiter Service",
        # --- 通用 ---
        "防水运动相机": "wasserdichte Action-Kamera",
        "运动相机": "Actionkamera",
        "action camera": "Actionkamera",
        "sports camera": "Sportkamera",
        "多功能": "vielseitig",
        "多场景": "multifunktional",
    },
    "French": {
        # --- English phrases first (phrase-match priority) ---
        "4K recording": "enregistrement 4K",
        "HD recording": "enregistrement HD",
        "advanced stabilization technology": "technologie de stabilisation avancée",
        "stabilization technology": "technologie de stabilisation",
        "action camera": "caméra d'action",
        "waterproof action camera": "caméra d'action waterproof",
        "sports camera": "caméra sportive",
        "versatile design": "conception polyvalente",
        # --- 4K/高清录像 ---
        "4K录像": "enregistrement 4K",
        "4K video": "vidéo 4K",
        "4K": "4K",
        "高清录像": "enregistrement HD",
        "HD video": "vidéo HD",
        # --- 防抖/Stabilization ---
        "防抖": "stabilisation",
        "EIS防抖": "stabilisation EIS",
        "stabilization": "stabilisation",
        "image stabilization": "stabilisation de l'image",
        # --- 防水/Waterproof ---
        "防水": "étanche",
        "防水壳": "boîtier waterproof",
        "waterproof": "étanche",
        "30米防水": "étanche à 30m",
        "waterproof case": "boîtier waterproof",
        # --- WiFi/连接 ---
        "WiFi连接": "connexion WiFi",
        "WiFi": "WiFi",
        "wifi": "WiFi",
        "USB": "USB",
        "USB-C": "USB-C",
        # --- 双屏幕/Dual screen ---
        "双屏幕": "écran double",
        "dual screen": "écran double",
        "触摸屏": "écran tactile",
        "touch screen": "écran tactile",
        # --- 续航/Battery ---
        "长续航": "autonomie longue",
        "电池续航": "autonomie",
        "电池": "batterie",
        "battery life": "autonomie",
        "long battery": "autonomie longue",
        "battery": "batterie",
        "charging": "chargement",
        # --- 存储/Storage ---
        "存储": "stockage",
        "存储卡": "carte mémoire",
        "Micro SD": "Micro SD",
        "256GB": "256 Go",
        "memory card": "carte mémoire",
        # --- 安装配件/Mounting ---
        "挂载配件": "accessoires de montage",
        "头盔支架": "support de casque",
        "helmet mount": "support de casque",
        "车把支架": "support de guidon",
        "handlebar mount": "support de guidon",
        "胸带": "sangle de poitrine",
        "chest strap": "sangle de poitrine",
        "支架": "support",
        "mount": "support",
        # --- 质保/Warranty ---
        "质保": "garantie",
        "warranty": "garantie",
        "12个月": "12 mois",
        "12 months": "12 mois",
        # --- 通用 ---
        "防水运动相机": "caméra d'action waterproof",
        "运动相机": "caméra d'action",
        "action camera": "caméra d'action",
        "sports camera": "caméra sportive",
    },
    "Spanish": {
        # --- English phrases first (phrase-match priority) ---
        "4K recording": "grabación 4K",
        "HD recording": "grabación HD",
        "advanced stabilization technology": "tecnología de estabilización avanzada",
        "stabilization technology": "tecnología de estabilización",
        "action camera": "cámara de acción",
        "waterproof action camera": "cámara de acción resistente al agua",
        "sports camera": "cámara deportiva",
        "versatile design": "diseño versátil",
        # --- 4K/高清录像 ---
        "4K录像": "grabación 4K",
        "4K video": "vídeo 4K",
        "4K": "4K",
        "高清录像": "grabación HD",
        "HD video": "vídeo HD",
        # --- 防抖/Stabilization ---
        "防抖": "estabilización",
        "EIS防抖": "estabilización EIS",
        "stabilization": "estabilización",
        "image stabilization": "estabilización de imagen",
        # --- 防水/Waterproof ---
        "防水": "resistente al agua",
        "防水壳": "carcasa waterproof",
        "waterproof": "resistente al agua",
        "30米防水": "resistente al agua 30m",
        "waterproof case": "carcasa waterproof",
        # --- WiFi/连接 ---
        "WiFi连接": "conexión WiFi",
        "WiFi": "WiFi",
        "wifi": "WiFi",
        "USB": "USB",
        "USB-C": "USB-C",
        # --- 双屏幕/Dual screen ---
        "双屏幕": "pantalla dual",
        "dual screen": "pantalla dual",
        "触摸屏": "pantalla táctil",
        "touch screen": "pantalla táctil",
        # --- 续航/Battery ---
        "长续航": "batería duradera",
        "电池续航": "duración de batería",
        "电池": "batería",
        "battery life": "duración de batería",
        "long battery": "batería duradera",
        "battery": "batería",
        "charging": "carga",
        # --- 存储/Storage ---
        "存储": "almacenamiento",
        "存储卡": "tarjeta de memoria",
        "Micro SD": "Micro SD",
        "256GB": "256GB",
        "memory card": "tarjeta de memoria",
        # --- 安装配件/Mounting ---
        "挂载配件": "accesorios de montaje",
        "头盔支架": "soporte para casco",
        "helmet mount": "soporte para casco",
        "车把支架": "soporte para manillar",
        "handlebar mount": "soporte para manillar",
        "胸带": "correa de pecho",
        "chest strap": "correa de pecho",
        "支架": "soporte",
        "mount": "soporte",
        # --- 质保/Warranty ---
        "质保": "garantía",
        "warranty": "garantía",
        "12个月": "12 meses",
        "12 months": "12 meses",
        # --- 通用 ---
        "防水运动相机": "cámara de acción resistente al agua",
        "运动相机": "cámara de acción",
        "action camera": "cámara de acción",
        "sports camera": "cámara deportiva",
    },
    "Italian": {
        # --- English phrases first (phrase-match priority) ---
        "4K recording": "registrazione 4K",
        "HD recording": "registrazione HD",
        "advanced stabilization technology": "tecnologia di stabilizzazione avanzata",
        "stabilization technology": "tecnologia di stabilizzazione",
        "action camera": "videocamera sportiva",
        "waterproof action camera": "fotocamera sportiva impermeabile",
        "sports camera": "fotocamera sportiva",
        "versatile design": "design versatile",
        # --- 4K/高清录像 ---
        "4K录像": "registrazione 4K",
        "4K video": "video 4K",
        "4K": "4K",
        "高清录像": "registrazione HD",
        "HD video": "video HD",
        # --- 防抖/Stabilization ---
        "防抖": "stabilizzazione",
        "EIS防抖": "stabilizzazione EIS",
        "stabilization": "stabilizzazione",
        "image stabilization": "stabilizzazione dell'immagine",
        # --- 防水/Waterproof ---
        "防水": "impermeabile",
        "防水壳": "custodia waterproof",
        "waterproof": "impermeabile",
        "30米防水": "impermeabile a 30m",
        "waterproof case": "custodia waterproof",
        # --- WiFi/连接 ---
        "WiFi连接": "connessione WiFi",
        "WiFi": "WiFi",
        "wifi": "WiFi",
        "USB": "USB",
        "USB-C": "USB-C",
        # --- 双屏幕/Dual screen ---
        "双屏幕": "schermo doppio",
        "dual screen": "schermo doppio",
        "触摸屏": "schermo tattile",
        "touch screen": "schermo tattile",
        # --- 续航/Battery ---
        "长续航": "batteria duratura",
        "电池续航": "durata batteria",
        "电池": "batteria",
        "battery life": "durata batteria",
        "long battery": "batteria duratura",
        "battery": "batteria",
        "charging": "ricarica",
        # --- 存储/Storage ---
        "存储": "archiviazione",
        "存储卡": "scheda di memoria",
        "Micro SD": "Micro SD",
        "256GB": "256GB",
        "memory card": "scheda di memoria",
        # --- 安装配件/Mounting ---
        "挂载配件": "accessori di montaggio",
        "头盔支架": "supporto per casco",
        "helmet mount": "supporto per casco",
        "车把支架": "supporto per manubrio",
        "handlebar mount": "supporto per manubrio",
        "胸带": "cinghia pettorale",
        "chest strap": "cinghia pettorale",
        "支架": "supporto",
        "mount": "supporto",
        # --- 质保/Warranty ---
        "质保": "garanzia",
        "warranty": "garanzia",
        "12个月": "12 mesi",
        "12 months": "12 mesi",
        # --- 通用 ---
        "防水运动相机": "fotocamera sportiva impermeabile",
        "运动相机": "videocamera sportiva",
        "action camera": "videocamera sportiva",
        "sports camera": "fotocamera sportiva",
    }
}

# 场景翻译映射 (English -> Target Language)
SCENE_TRANSLATIONS = {
    "German": {
        "cycling_recording": "Radfahren",
        "underwater_exploration": "Unterwasser",
        "travel_documentation": "Reisen",
        "family_use": "Familie",
        "outdoor_sports": "Outdoor-Sport",
        "hiking_trekking": "Wandern",
        "skiing": "Skifahren",
        "road_trip": "Autoreisen",
        "vlog_content_creation": "Vlog",
        "pet_photography": "Tieraufnahmen",
        "sports_training": "Sporttraining",
        "sports_event_recording": "Sportereignisse",
        "wilderness_exploration": "Naturabenteuer",
        "extreme_sports": "Extremsport",
        "daily_lifelogging": "Alltag",
        "selfie_vlog": "Selfie-Vlog",
        "rainy_use": "Regenwetter",
        "swimming": "Schwimmen",
        "surfing": "Surfen",
    },
    "French": {
        "cycling_recording": "cyclisme",
        "underwater_exploration": "plongée",
        "travel_documentation": "voyage",
        "family_use": "famille",
        "outdoor_sports": "sports outdoor",
        "hiking_trekking": "randonnée",
        "skiing": "ski",
        "road_trip": "road trip",
        "vlog_content_creation": "vlog",
        "pet_photography": "photos d'animaux",
        "sports_training": "entraînement",
        "sports_event_recording": "événements sportifs",
    },
    "Spanish": {
        "cycling_recording": "ciclismo",
        "underwater_exploration": "submarino",
        "travel_documentation": "viaje",
        "family_use": "familia",
        "outdoor_sports": "deportes al aire libre",
        "hiking_trekking": "senderismo",
        "skiing": "esquí",
        "road_trip": "viaje por carretera",
        "vlog_content_creation": "vlog",
        "pet_photography": "fotos de mascotas",
        "sports_training": "entrenamiento",
        "sports_event_recording": "eventos deportivos",
    },
    "Italian": {
        "cycling_recording": "ciclismo",
        "underwater_exploration": "subacqueo",
        "travel_documentation": "viaggio",
        "family_use": "famiglia",
        "outdoor_sports": "sport all'aperto",
        "hiking_trekking": "escursionismo",
        "skiing": "sci",
        "road_trip": "viaggio on the road",
        "vlog_content_creation": "vlog",
        "pet_photography": "foto di animali",
        "sports_training": "allenamento",
        "sports_event_recording": "eventi sportivi",
    }
}

# 品类核心词翻译 (English -> Target Language)
CATEGORY_TRANSLATIONS = {
    "German": {
        "action camera": "Actionkamera",
        "sports camera": "Sportkamera",
        "body camera": "Bodycam",
        "helmet camera": "Helmkamera",
        "camcorder": "Camcorder",
        "recording device": "Aufnahmegerät",
        "waterproof camera": "Wasserdichte Kamera",
        "digital camera": "Digitalkamera",
    },
    "French": {
        "action camera": "caméra d'action",
        "sports camera": "caméra sportive",
        "body camera": "caméra corporelle",
        "helmet camera": "caméra de casque",
        "camcorder": "caméscope",
        "recording device": "appareil d'enregistrement",
        "waterproof camera": "caméra waterproof",
        "digital camera": "appareil photo numérique",
    },
    "Spanish": {
        "action camera": "cámara de acción",
        "sports camera": "cámara deportiva",
        "body camera": "cámara corporal",
        "helmet camera": "cámara de casco",
        "camcorder": "videocámara",
        "recording device": "dispositivo de grabación",
        "waterproof camera": "cámara resistente al agua",
        "digital camera": "cámara digital",
    },
    "Italian": {
        "action camera": "videocamera sportiva",
        "sports camera": "fotocamera sportiva",
        "body camera": "bodycam",
        "helmet camera": "fotocamera per casco",
        "camcorder": "videocamera",
        "recording device": "dispositivo di registrazione",
        "waterproof camera": "fotocamera impermeabile",
        "digital camera": "fotocamera digitale",
    }
}


def _translate_capability(capability: str, target_language: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """将能力词翻译为目标语言，优先检查真实国家词表，若无则用映射表，若仍缺且data_mode=SYNTHETIC_COLD_START则加[SYNTH]"""
    if target_language == "English":
        return capability

    # 优先检查真实国家词表中是否有该能力词的本地关键词
    if real_vocab and hasattr(real_vocab, 'is_available') and real_vocab.is_available:
        top_keywords = getattr(real_vocab, 'top_keywords', []) or []
        # 先通过映射表得到可能的翻译
        translations = CAPABILITY_TRANSLATIONS.get(target_language, {})
        possible_translation = translations.get(capability, capability)

        # 检查真实国家词表的关键词中是否包含这个翻译（不区分大小写）
        for kw_entry in top_keywords:
            kw = kw_entry.get('keyword', '').lower()
            if possible_translation.lower() in kw or kw in possible_translation.lower():
                # 使用真实国家词表中的完整关键词（可能更长尾）
                return kw_entry.get('keyword', possible_translation)

    # 如果真实国家词表没有，使用映射表
    translations = CAPABILITY_TRANSLATIONS.get(target_language, {})
    translated = translations.get(capability, capability)

    # 如果映射表中也没有，且是SYNTHETIC_COLD_START模式，加[SYNTH]标记
    if translated == capability and target_language != "English" and data_mode == "SYNTHETIC_COLD_START":
        return f"[SYNTH]_{capability}"

    return translated


def _translate_scene(scene_label: str, target_language: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """将英文场景标签翻译为目标语言，优先检查真实国家词表，若无则用映射表，若仍缺且data_mode=SYNTHETIC_COLD_START则加[SYNTH]"""
    if target_language == "English":
        return scene_label

    # 优先检查真实国家词表中是否有该场景词的本地关键词
    if real_vocab and hasattr(real_vocab, 'is_available') and real_vocab.is_available:
        top_keywords = getattr(real_vocab, 'top_keywords', []) or []
        # 先通过映射表得到可能的翻译
        translations = SCENE_TRANSLATIONS.get(target_language, {})
        possible_translation = translations.get(scene_label, scene_label)

        # 检查真实国家词表的关键词中是否包含这个翻译（不区分大小写）
        for kw_entry in top_keywords:
            kw = kw_entry.get('keyword', '').lower()
            if possible_translation.lower() in kw or kw in possible_translation.lower():
                # 使用真实国家词表中的完整关键词（可能更长尾）
                return kw_entry.get('keyword', possible_translation)

    # 如果真实国家词表没有，使用映射表
    translations = SCENE_TRANSLATIONS.get(target_language, {})
    translated = translations.get(scene_label, scene_label)

    # 如果映射表中也没有，且是SYNTHETIC_COLD_START模式，加[SYNTH]标记
    if translated == scene_label and target_language != "English" and data_mode == "SYNTHETIC_COLD_START":
        return f"[SYNTH]_{scene_label}"
    return translated


def _translate_text_to_language(text: str, target_language: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """
    将英文文本翻译为目标语言 (用于 bullet/description 翻译)
    使用正则做大小写不敏感的整词替换
    """
    if target_language == "English":
        return text

    translations = CAPABILITY_TRANSLATIONS.get(target_language, {})
    scene_translations = SCENE_TRANSLATIONS.get(target_language, {})
    category_translations = CATEGORY_TRANSLATIONS.get(target_language, {})

    # 合并所有翻译表并按长度降序排列（优先匹配最长短语）
    all_trans = {**translations, **scene_translations, **category_translations}
    phrases = sorted(all_trans.keys(), key=len, reverse=True)

    for phrase in phrases:
        # 大小写不敏感的整词替换
        import re
        pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
        text = pattern.sub(all_trans[phrase], text)

    return text


# Chinese -> English 标准化映射 (用于 normalize core_selling_points)
CHINESE_TO_ENGLISH = {
    # Capabilities
    "4K画质": "4K recording",
    "电子防抖": "electronic stabilization",
    "WiFi连接": "WiFi connection",
    "双屏幕": "dual screen",
    "高清录像": "HD recording",
    "4K录像": "4K recording",
    "防抖": "stabilization",
    "防水": "waterproof",
    "长续航": "long battery life",
    # Accessories
    "防水壳": "waterproof case",
    "磁吸挂绳": "magnetic strap",
    "车把支架": "handlebar mount",
    "头盔底座": "helmet mount",
    "支架": "mount",
    "胸带": "chest strap",
    "头盔支架": "helmet mount",
    "防水壳30米": "30m waterproof case",
    # Other terms that appear in attribute data
    "防水壳": "waterproof case",
    "壳": "case",
    "配件": "accessory",
    "支持": "supports",
    "最大": "max",
}


def _normalize_to_english(text: str) -> str:
    """将中文术语标准化为英文（内部规划用）"""
    for cn, en in CHINESE_TO_ENGLISH.items():
        text = text.replace(cn, en)
    return text


def _normalize_core_selling_points(caps: List[str]) -> List[str]:
    """将中文 core_selling_points 标准化为英文"""
    return [_normalize_to_english(c) for c in caps]


def _normalize_accessory_descriptions(accessories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将中文 accessory_descriptions 标准化为英文"""
    result = []
    for acc in accessories:
        new_acc = dict(acc)
        new_acc["name"] = _normalize_to_english(acc.get("name", ""))
        new_acc["specification"] = _normalize_to_english(acc.get("specification", ""))
        result.append(new_acc)
    return result


def _build_english_title_structure(preprocessed_data: Any, writing_policy: Dict[str, Any],
                                    tiered_keywords: Dict[str, List[str]],
                                    keyword_allocation_strategy: str) -> Dict[str, Any]:
    """
    PRD v8.2: 第一阶段 - 用 English 构建标题信息结构
    返回: {brand, l1_keywords, scene_1, capability_1, scene_2, resolution}
    """
    brand = preprocessed_data.run_config.brand_name if hasattr(preprocessed_data.run_config, 'brand_name') else "Brand"

    # 获取 Profile 中的 hero_spec
    profile = writing_policy.get("product_profile", {})
    hero_spec_raw = profile.get("hero_spec", "action camera")
    # 标准化 hero_spec（可能是中文）→ English
    hero_spec = _normalize_to_english(hero_spec_raw)

    # 获取场景
    scenes_en = profile.get("primary_use_cases", ["outdoor_sports", "cycling_recording"])

    # 获取 L1 关键词
    l1_keywords = tiered_keywords.get("l1", [])
    if not l1_keywords:
        l1_keywords = ["action camera 4k"]

    # 获取分辨率
    attr_data = preprocessed_data.attribute_data.data if hasattr(preprocessed_data.attribute_data, 'data') else {}
    resolution = attr_data.get('video_resolution', '4K')

    return {
        "brand": brand,
        "l1_keywords": l1_keywords,
        "scene_1": scenes_en[0] if scenes_en else "outdoor_sports",
        "scene_2": scenes_en[1] if len(scenes_en) > 1 else scenes_en[0],
        "hero_spec": hero_spec,
        "resolution": resolution
    }


def _generate_title_in_language(title_struct: Dict[str, Any], target_language: str,
                                 keyword_allocation_strategy: str, real_vocab: Optional[Any] = None, data_mode: str = "SYNTHETIC_COLD_START") -> str:
    """
    PRD v8.2: 第二阶段 - 根据目标语言生成标题
    """
    brand = title_struct["brand"]
    l1_keywords = title_struct["l1_keywords"]
    scene_1_en = title_struct["scene_1"]
    scene_2_en = title_struct["scene_2"]
    hero_spec = title_struct["hero_spec"]
    resolution = title_struct["resolution"]

    # 翻译场景
    scene_1 = _translate_scene(scene_1_en, target_language, real_vocab, data_mode)
    scene_2 = _translate_scene(scene_2_en, target_language, real_vocab, data_mode)

    # 翻译 hero_spec
    hero_spec_translated = _translate_capability(hero_spec, target_language, real_vocab, data_mode)

    # 构建标题
    if target_language == "English":
        title = f"{brand} {l1_keywords[0]} {scene_1} {hero_spec_translated} {resolution}"
    elif target_language == "German":
        title = f"{brand} {l1_keywords[0]} {scene_1} {hero_spec_translated} {resolution} {scene_2}"
    else:
        title = f"{brand} {l1_keywords[0]} {scene_1} {hero_spec_translated} {resolution}"

    # 清理 [SYNTH] 标记在标题中的显示（可选择保留或移除）
    # 这里保留 [SYNTH] 用于审计
    return title


def generate_multilingual_copy(preprocessed_data: PreprocessedData,
                              writing_policy: Dict[str, Any],
                              language: str = None) -> Dict[str, Any]:
    """
    PRD v8.2 Node 4: 多语言文案生成

    流程:
    1. 从 writing_policy.product_profile 提取 English 策略
    2. 从 writing_policy.intent_graph 提取 English Intent Graph
    3. 内部规划用 English 构建信息结构
    4. 最后一步根据 target_language 翻译/生成目标语句子
    5. 缺本地词时添加 [SYNTH] 标记

    Args:
        preprocessed_data: 预处理数据
        writing_policy: writing_policy策略 (含 product_profile, intent_graph)
        language: 目标语言 (默认从 preprocessed_data.language 获取)

    Returns:
        包含所有文案组件的字典
    """
    # 确定目标语言
    target_language = language or getattr(preprocessed_data, 'language', 'English')

    # PRD v8.2: 从 Profile 获取 reasoning_language (固定为 EN)
    profile = writing_policy.get("product_profile", {})
    reasoning_language = profile.get("reasoning_language", "EN")
    data_mode = getattr(preprocessed_data, 'data_mode', 'SYNTHETIC_COLD_START')

    # 读取关键词分配策略
    keyword_allocation_strategy = writing_policy.get("keyword_allocation_strategy", "balanced")

    # 提取分层关键词（Priority 1: 真实国家词表，Priority 2: keyword_data）
    # 先尝试重建 real_vocab（处理 LazyPreprocessedData 无法直接访问 real_vocab 的情况）
    rv_for_tiering = _reconstruct_real_vocab(preprocessed_data)
    tiered_keywords = extract_tiered_keywords(preprocessed_data, "English", real_vocab=rv_for_tiering)
    l1_keywords = tiered_keywords.get("l1", [])

    # ---- PRD v8.2 Node 4 Phase 0: 标准化中文能力词/配件名为英文 ----
    # (内部规划统一用 English，不能有残留中文能力词嵌入英文句子)
    core_selling_points_en = _normalize_core_selling_points(preprocessed_data.core_selling_points)
    accessory_descriptions_en = _normalize_accessory_descriptions(preprocessed_data.accessory_descriptions)

    # 创建一个临时 preprocessed_data 副本用于后续调用（只改这两个字段）
    preprocessed_en = preprocessed_data
    # 使用 dataclass.replace 风格的浅拷贝（如果支持的话），否则手动构造
    try:
        import dataclasses
        preprocessed_en = dataclasses.replace(
            preprocessed_data,
            core_selling_points=core_selling_points_en,
            accessory_descriptions=accessory_descriptions_en
        )
    except Exception:
        # Fallback: 手动浅拷贝（仅适用于我们实际用到的字段）
        class _EnProxy:
            def __init__(self, pd, caps, accs):
                self.run_config = pd.run_config
                self.attribute_data = pd.attribute_data
                self.keyword_data = pd.keyword_data
                self.review_data = pd.review_data
                self.aba_data = pd.aba_data
                self.real_vocab = getattr(pd, "real_vocab", None)  # 保留真实词表
                self.core_selling_points = caps
                self.accessory_descriptions = accs
                self.quality_score = pd.quality_score
                self.language = pd.language
                self.processed_at = pd.processed_at
        preprocessed_en = _EnProxy(preprocessed_data, core_selling_points_en, accessory_descriptions_en)

    # 第一阶段: 用 English 构建标题结构
    title_struct = _build_english_title_structure(
        preprocessed_en, writing_policy, tiered_keywords, keyword_allocation_strategy
    )

    # 第二阶段: 生成目标语言标题
    title = _generate_title_in_language(title_struct, target_language, keyword_allocation_strategy, preprocessed_data.real_vocab, data_mode)

    # 生成 bullets (使用 English 标准化版本)
    bullets_en = generate_bullet_points(preprocessed_en, writing_policy, "English",
                                        tiered_keywords, keyword_allocation_strategy)

    # 翻译 bullets 到目标语言 (短语优先替换)
    bullets = []
    for bullet in bullets_en:
        bullet_translated = _translate_text_to_language(bullet, target_language, preprocessed_data.real_vocab, data_mode)

        # 如果是 SYNTHETIC_COLD_START 且有未被翻译的英文词，添加 [SYNTH]
        if data_mode == "SYNTHETIC_COLD_START" and bullet_translated == bullet:
            # 尝试找出未翻译的关键能力词并标记
            for cap in ["action camera", "stabilization", "waterproof", "4K", "recording"]:
                if cap in bullet:
                    bullet_translated = bullet_translated.replace(cap, f"[SYNTH]_{cap}")
                    break
        bullets.append(bullet_translated)

    # 生成描述 (使用 English 标准化版本)
    description_en = generate_description(preprocessed_en, writing_policy, title, bullets_en, "English")
    description = _translate_text_to_language(description_en, target_language, preprocessed_data.real_vocab, data_mode)

    # 生成 FAQ
    faq = generate_faq(preprocessed_en, writing_policy, target_language)

    # 生成搜索词 (使用 English 标准化版本)
    search_terms = generate_search_terms(preprocessed_en, writing_policy, title, bullets,
                                         target_language, tiered_keywords)

    # 生成 A+ 内容 (使用 English 标准化版本)
    aplus_content = generate_aplus_content(preprocessed_en, writing_policy, target_language)

    # 构建完整文案
    copy_dict = {
        "title": title,
        "bullets": bullets,
        "description": description,
        "faq": faq,
        "search_terms": search_terms,
        "aplus_content": aplus_content,
        "metadata": {
            "version": "v8.2",
            "reasoning_language": reasoning_language,
            "target_language": target_language,
            "data_mode": data_mode,
            "has_synthetic": "[SYNTH]" in title or any("[SYNTH]" in b for b in bullets),
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


def generate_listing_copy(preprocessed_data: PreprocessedData,
                         writing_policy: Dict[str, Any],
                         language: str = None) -> Dict[str, Any]:
    """
    生成完整的Listing文案 - PRD v8.2 多语言版

    委托给 generate_multilingual_copy() 处理多语言逻辑：
    - 内部推理使用 English (Reasoning_Language = EN)
    - 最终输出使用 target_language
    - 缺本地词时添加 [SYNTH] 标记

    Args:
        preprocessed_data: 预处理数据
        writing_policy: writing_policy策略 (含 product_profile, intent_graph)
        language: 目标语言 (默认从 preprocessed_data.language 获取)

    Returns:
        包含所有文案组件的字典
    """
    return generate_multilingual_copy(preprocessed_data, writing_policy, language)

    # 生成标题（确保L1在首80字符内，多场景）
    title = generate_title(preprocessed_data, writing_policy, l1_keywords, tiered_keywords, keyword_allocation_strategy)

    # 生成bullet points（多场景覆盖，使用L2/L3关键词）
    bullets = generate_bullet_points(preprocessed_data, writing_policy, language, tiered_keywords, keyword_allocation_strategy)

    # 生成描述
    description = generate_description(preprocessed_data, writing_policy, title, bullets, language)

    # 生成FAQ
    faq = generate_faq(preprocessed_data, writing_policy, language)

    # 生成搜索词（优先L2/L3长尾关键词）
    search_terms = generate_search_terms(preprocessed_data, writing_policy, title, bullets, language, tiered_keywords)

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
    from dataclasses import dataclass, field

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