#!/usr/bin/env python3
"""Shared language utilities for capability/scene canonicalization and translations."""

from __future__ import annotations

import re
from typing import Dict, Optional

# --- Translation dictionaries reused across modules ---
CAPABILITY_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "German": {
        "4k recording": "4K-Aufnahme",
        "4k": "4K",
        "stabilization": "Stabilisierung",
        "electronic stabilization": "elektronische Stabilisierung",
        "wifi connection": "WiFi-Verbindung",
        "wifi connectivity": "WiFi-Konnektivität",
        "dual screen": "Dual-Screen",
        "waterproof": "wasserdicht",
        "high definition": "hohe Auflosung",
        "long battery life": "lange Akkulaufzeit",
        "long battery": "lange Akkulaufzeit",
        "easy operation": "einfache Bedienung",
        "lightweight design": "Leichtbau-Design",
        "voice control": "Sprachsteuerung",
        "live streaming": "Live-Streaming",
        "magnetic mounting": "Magnetische Befestigung",
        "versatile mounting": "Vielseitiges Montagesystem",
        "helmet mount": "Helmhalterung",
        "handlebar mount": "Lenkerhalterung",
        "waterproof case": "Wasserdichtes Gehäuse",
        "accessories": "Zubehör",
        "battery life": "Akkulaufzeit",
        "long battery": "lange Batterie",
        "battery": "Akku",
        "charging": "Laden",
        "storage": "Speicher",
        "memory card": "Speicherkarte",
        "Micro SD": "Micro SD",
        "mount": "Halterung",
        "warranty": "Garantie",
        "12 months": "12 Monate",
        "action camera": "Actionkamera",
        "sports camera": "Sportkamera",
    },
    "French": {
        "4k recording": "enregistrement 4K",
        "stabilization": "stabilisation",
        "electronic stabilization": "stabilisation électronique",
        "wifi connection": "connexion WiFi",
        "wifi connectivity": "connectivité WiFi",
        "dual screen": "double écran",
        "waterproof": "étanche",
        "high definition": "haute definition",
        "long battery life": "longue autonomie",
        "long battery": "longue autonomie",
        "easy operation": "utilisation simple",
        "lightweight design": "design leger",
        "voice control": "commande vocale",
        "live streaming": "diffusion en direct",
        "magnetic mounting": "fixation magnétique",
        "versatile mounting": "montage polyvalent",
        "helmet mount": "support tête",
        "handlebar mount": "support guidon",
        "waterproof case": "boîtier étanche",
        "accessories": "accessoires",
        "battery life": "autonomie de batterie",
        "battery": "batterie",
        "storage": "stockage",
        "memory card": "carte mémoire",
        "Micro SD": "Micro SD",
        "mount": "support",
        "warranty": "garantie",
        "12 months": "12 mois",
        "action camera": "caméra d'action",
        "sports camera": "caméra sportive",
    },
    "Spanish": {
        "4k recording": "grabación 4K",
        "stabilization": "estabilización",
        "wifi connection": "conexión WiFi",
        "dual screen": "pantalla doble",
        "waterproof": "impermeable",
        "high definition": "alta definicion",
        "long battery": "larga autonomia",
        "easy operation": "uso sencillo",
        "lightweight design": "diseno ligero",
    },
    "Italian": {
        "4k recording": "registrazione 4K",
        "stabilization": "stabilizzazione",
        "wifi connection": "connessione WiFi",
        "dual screen": "doppio schermo",
        "waterproof": "impermeabile",
        "high definition": "alta definizione",
        "long battery": "lunga autonomia",
        "easy operation": "uso semplice",
        "lightweight design": "design leggero",
    },
}

CHINESE_CHAR_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")

# 运动相机品类：中文 -> 标准英文 映射表 (Canonical Map)
ACTION_CAMERA_CANONICAL_MAP = {
    # 1. 核心配件 (Accessories & Mounts)
    "防水壳": "waterproof case",
    "壳": "housing",
    "磁吸背夹": "magnetic back clip",
    "磁吸": "magnetic",
    "挂脖绳": "neck lanyard",
    "可挂脖": "wearable neck mount",
    "吸附各种金属表面": "attaches to metal surfaces",
    "车吧": "handlebar mount",
    "车把": "handlebar mount",
    "头盔支架": "helmet mount",
    "头盔": "helmet",
    "胸前固定带": "chest strap mount",
    "胸带": "chest mount",
    "电池仓": "battery compartment",
    "数据线": "charging cable",
    "充电线": "charging cable",
    "说明书": "user manual",
    "其他固件": "other mounting accessories",
    "固件": "mounts",
    "配件": "accessories",

    # 2. 核心功能与卖点 (Features & Capabilities)
    "防抖": "electronic image stabilization (EIS)",
    "续航": "battery life",
    "广角": "wide-angle lens",
    "高清": "high definition",
    "夜视": "night vision",
    "裸机防水": "waterproof without case",
    "潜水": "diving",
    "骑行": "cycling",
    "滑雪": "skiing",
    "第一人称": "POV",
}

# Canonical accessory -> experience storytelling hints (posture + pain point)
ACCESSORY_EXPERIENCE_MAP = {
    "magnetic back clip": {
        "canonical": "magnetic back clip",
        "aliases": ["clip dorsal", "magnetic clip"],
        "experience": "clip the magnetic back clip to your jacket collar for true hands-free POV recording without bulky chest straps",
        "localized": {
            "French": "Fixez le clip dorsal magnétique sur la veste pour filmer mains libres sans harnais volumineux.",
            "German": "Klemme den magnetischen Rückenclip an die Jacke und filme freihändig ohne sperrige Brustgurte.",
        },
    },
    "magnetic necklace": {
        "canonical": "magnetic necklace",
        "aliases": ["magnetic neck strap", "wearable neck mount"],
        "experience": "snap the magnetic necklace under your jersey so the camera floats at chest height without restricting arm swings",
        "localized": {
            "French": "Glissez le tour de cou magnétique pour garder la caméra mains libres à hauteur de poitrine.",
            "German": "Führe das magnetische Halsband unter das Trikot, damit die Kamera auf Brusthöhe schwebt und die Arme frei bleiben.",
        },
    },
    "magnetic accessories": {
        "canonical": "magnetic accessories",
        "aliases": ["magnetic mount", "magnetic base"],
        "experience": "lock the magnetic base onto any metal railing to frame third-person shots without dragging a tripod",
        "localized": {
            "French": "Accrochez la base magnétique sur une rambarde métallique pour cadrer des plans tierce personne sans trépied.",
            "German": "Setze die magnetische Basis auf jede Metallfläche, um Third-Person-Shots ohne Stativ zu erhalten.",
        },
    },
    "waterproof case": {
        "canonical": "waterproof case",
        "aliases": ["diving case", "housing"],
        "experience": "seal the waterproof case before dives to keep sensors dry and stop lens fogging all the way to 30m",
        "localized": {
            "French": "Verrouillez le boîtier étanche avant la plongée pour éviter la buée et garder les capteurs au sec jusqu'à 30 m.",
            "German": "Verriegele das wasserdichte Gehäuse vor dem Abtauchen, damit Sensoren trocken bleiben und keine Beschlagung entsteht – bis 30 m.",
        },
    },
    "helmet mount": {
        "canonical": "helmet mount",
        "aliases": ["helmet base", "helmet strap"],
        "experience": "mount the camera on your helmet to mirror natural head turns so viewers never feel woozy on rough trails",
        "localized": {
            "French": "Montez la caméra sur le casque pour suivre naturellement vos mouvements et éviter le mal de mer visuel.",
            "German": "Befestige die Kamera am Helm, damit sie natürliche Kopfbewegungen übernimmt und niemandem schlecht wird.",
        },
    },
    "handlebar mount": {
        "canonical": "handlebar mount",
        "aliases": ["bike mount", "bar mount"],
        "experience": "secure the handlebar mount tightly to keep the horizon level over cobblestones instead of wobbling footage",
        "localized": {
            "French": "Serrez la fixation guidon pour garder l'horizon stable sur les pavés au lieu de filmer des secousses.",
            "German": "Ziehe die Lenkerhalterung fest, damit der Horizont über Kopfsteinpflaster ruhig bleibt statt zu wackeln.",
        },
    },
    "chest strap mount": {
        "canonical": "chest strap mount",
        "aliases": ["chest harness", "chest strap"],
        "experience": "tighten the chest strap across your sternum to capture a steady mid-body POV while stopping wind buffet",
        "localized": {
            "French": "Ajustez le harnais poitrine sur le sternum pour capter un POV stable tout en coupant les rafales de vent.",
            "German": "Spannt den Brustgurt über dem Brustbein, um eine ruhige Mid-Body-Perspektive ohne Windruckler zu sichern.",
        },
    },
    "neck lanyard": {
        "canonical": "neck lanyard",
        "aliases": ["neck strap", "wearable lanyard"],
        "experience": "hang the neck lanyard high on your chest for instant POV swaps without fumbling with buckles",
        "localized": {
            "French": "Suspendez la dragonne au niveau de la poitrine pour changer de POV instantanément sans chercher les boucles.",
            "German": "Hänge die Halslanyard hoch an die Brust, um blitzschnell den POV zu wechseln ohne mit Schnallen zu fummeln.",
        },
    },
}

def _match_accessory_meta(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    normalized = re.sub(r"[()]", " ", str(text).lower())
    normalized = re.sub(r"\s+", " ", normalized)
    for key, meta in ACCESSORY_EXPERIENCE_MAP.items():
        aliases = [key] + meta.get("aliases", [])
        for alias in aliases:
            if alias and alias in normalized:
                return meta
    return None


def get_accessory_experience(text: str) -> str:
    meta = _match_accessory_meta(text)
    return meta.get("experience", "") if meta else ""


def get_accessory_experience_key(text: str) -> str:
    meta = _match_accessory_meta(text)
    return meta.get("canonical", "") if meta else ""


def get_localized_accessory_experience_by_key(key: str, language: str) -> str:
    if not key or not language:
        return ""
    meta = ACCESSORY_EXPERIENCE_MAP.get(key)
    if not meta:
        return ""
    localized = meta.get("localized", {})
    return localized.get(language, "")

# 3. 正则表达式：处理带有数字的单位 (Units)
UNIT_REGEX_MAP = [
    (r'(\d+(?:\.\d+)?)\s*[mM](?![a-zA-Z])', r'\1m'),
    (r'(\d+)\s*米', r'\1m'),
    (r'(\d+)\s*厘米', r'\1cm'),
    (r'(\d+)\s*毫米', r'\1mm'),
    (r'(\d+)\s*分钟', r'\1 minutes'),
    (r'(\d+)\s*小时', r'\1 hours'),
    (r'(\d+)\s*个月', r'\1 months'),
    (r'(\d+)\s*毫安时?', r'\1mAh'),
    (r'(\d+)\s*克', r'\1g'),
]

SCENE_TRANSLATIONS: Dict[str, Dict[str, str]] = {
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
        "commuting_capture": "Pendeln",
        "service_interaction": "Arbeitseinsatz",
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
        "commuting_capture": "trajets quotidiens",
        "service_interaction": "service terrain",
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
        "commuting_capture": "trayectos diarios",
        "service_interaction": "servicio en ruta",
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
        "commuting_capture": "tragitti quotidiani",
        "service_interaction": "lavoro sul campo",
    },
}

CATEGORY_TRANSLATIONS: Dict[str, Dict[str, str]] = {
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
        "helmet camera": "caméra frontale",
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
    },
}

CHINESE_TO_ENGLISH = {
    "4K画质": "4k recording",
    "电子防抖": "electronic stabilization",
    "WiFi连接": "wifi connection",
    "双屏幕": "dual screen",
    "高清录像": "hd recording",
    "4K录像": "4k recording",
    "防抖": "stabilization",
    "防水": "waterproof",
    "长续航": "long battery life",
    "防水壳": "waterproof case",
    "防水外壳": "waterproof case",
    "防水壳30米": "waterproof case (30m)",
    "30米防水壳": "waterproof case (30m)",
    "防水壳20米": "waterproof case (20m)",
    "20米防水壳": "waterproof case (20m)",
    "潜水壳": "diving case",
    "潜水外壳": "diving case",
    "磁吸背夹": "magnetic back clip",
    "磁吸挂绳": "magnetic lanyard",
    "磁吸支架": "magnetic mount",
    "磁吸底座": "magnetic base",
    "车把支架": "handlebar mount",
    "头盔底座": "helmet mount",
    "支架": "mount",
    "胸带": "chest strap",
    "头盔绑带": "helmet strap",
    "绑带": "strap",
    "腕带": "wrist strap",
    "肩带": "shoulder strap",
    "头盔支架": "helmet mount",
    "快拆底座": "quick-release base",
    "自拍杆": "selfie stick",
    "背夹": "back clip",
    "主机": "main unit",
    "配件": "accessory",
    "支持": "supports",
    "最大": "max",
    "轻便": "lightweight design",
    "轻量": "lightweight design",
    "小巧": "compact design",
    "便携": "portable design",
    "便携设计": "portable design",
    "易操作": "easy operation",
    "易于操作": "easy operation",
    "易于使用": "easy operation",
    "易用": "easy operation",
    "简单操作": "easy operation",
    "高清视频录制": "hd recording",
    "其他配件": "accessory",
}


def _strip_remaining_cjk(text: str) -> str:
    if text is None:
        return ""
    cleaned = CHINESE_CHAR_PATTERN.sub(" ", str(text))
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_zh_units_to_canonical(text: str) -> str:
    if text is None:
        return ""

    def _trim(num: str) -> str:
        return num[:-2] if num.endswith(".0") else num

    normalized = str(text)
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:米|公尺)',
        lambda m: f"{_trim(m.group(1))}m",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:分钟|分|mins?|MIN)',
        lambda m: f"{_trim(m.group(1))} minutes",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:小时|hrs?|H)',
        lambda m: f"{_trim(m.group(1))} hours",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:秒|s)',
        lambda m: f"{_trim(m.group(1))} seconds",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:个月|月)',
        lambda m: f"{_trim(m.group(1))} months",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r'(\d+(?:\.\d+)?)\s*(?:天|日)',
        lambda m: f"{_trim(m.group(1))} days",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized


def _normalize_to_canonical_english(text: str) -> str:
    """Normalize accessory/spec fragments into canonical English strings."""
    if text is None:
        return ""
    normalized = _normalize_zh_units_to_canonical(str(text))
    normalized = (
        normalized.replace("：", ":")
        .replace("，", ",")
        .replace("。", ".")
        .replace("【", " ")
        .replace("】", " ")
    )
    for pattern, repl in UNIT_REGEX_MAP:
        normalized = re.sub(pattern, repl, normalized, flags=re.IGNORECASE)
    accessory_keys = sorted(ACTION_CAMERA_CANONICAL_MAP.keys(), key=len, reverse=True)
    for zh_key in accessory_keys:
        if zh_key in normalized:
            normalized = normalized.replace(zh_key, f" {ACTION_CAMERA_CANONICAL_MAP[zh_key]} ")
    extra_keys = sorted(CHINESE_TO_ENGLISH.keys(), key=len, reverse=True)
    for zh_key in extra_keys:
        if zh_key in normalized:
            normalized = normalized.replace(zh_key, f" {CHINESE_TO_ENGLISH[zh_key]} ")
    normalized = re.sub(r'(waterproof case)\s*(\d+m)', r'\1 (\2)', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'(\d+m)\s*(waterproof case)', r'waterproof case (\1)', normalized, flags=re.IGNORECASE)
    normalized = _strip_remaining_cjk(normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'\s+([,.;:])', r'\1', normalized)
    normalized = re.sub(r'([,.;:])([^\s])', r'\1 \2', normalized)
    return normalized.strip(" ,.;:-")

# Canonical capability definitions with alias lists and translations.
CANONICAL_CAPABILITIES: Dict[str, Dict[str, object]] = {
    "4k_recording": {
        "aliases": ["4k", "uhd", "超高清", "4k录像", "4k画质"],
        "translations": {
            "German": "4K-Aufnahme",
            "French": "enregistrement 4K",
        },
    },
    "stabilization": {
        "aliases": ["防抖", "stabilization", "stabilisierung", "eis"],
        "translations": {
            "German": "Stabilisierung",
            "French": "stabilisation",
        },
    },
    "waterproof": {
        "aliases": ["防水", "waterproof", "wasserdicht", "étanche"],
        "translations": {
            "German": "wasserdicht",
            "French": "étanche",
        },
    },
    "high_definition": {
        "aliases": [
            "high definition",
            "high-definition",
            "hd",
            "1080p",
            "1080p video",
            "高清",
            "haute definition",
            "haute définition",
            "hohe auflosung",
        ],
        "translations": {
            "German": "hohe Auflosung",
            "French": "haute definition",
        },
    },
    "wifi_connectivity": {
        "aliases": ["wifi", "wi-fi", "无线", "连接"],
        "translations": {
            "German": "WiFi-Verbindung",
            "French": "connexion WiFi",
        },
    },
    "dual_screen": {
        "aliases": ["双屏", "dual screen"],
        "translations": {
            "German": "Dual-Screen",
            "French": "double écran",
        },
    },
    "long_battery": {
        "aliases": ["长续航", "long battery", "battery", "battery life", "rechargeable battery", "长电池"],
        "translations": {
            "German": "lange Akkulaufzeit",
            "French": "longue autonomie",
        },
    },
    "voice_control": {
        "aliases": ["语音", "voice"],
        "translations": {
            "German": "Sprachsteuerung",
            "French": "commande vocale",
        },
    },
    "live_streaming": {
        "aliases": ["直播", "stream"],
        "translations": {
            "German": "Live-Streaming",
            "French": "diffusion en direct",
        },
    },
    "versatile_mounting": {
        "aliases": ["挂载", "mount", "安装"],
        "translations": {
            "German": "Vielseitiges Montagesystem",
            "French": "montage polyvalent",
        },
    },
    "lightweight_design": {
        "aliases": ["lightweight", "lightweight design", "portable design", "compact design", "轻便", "轻量", "小巧", "便携", "便携设计"],
        "translations": {
            "German": "Leichtbau-Design",
            "French": "design léger",
        },
    },
    "easy_operation": {
        "aliases": ["easy operation", "easy control", "simple operation", "易操作", "易于操作", "易于使用", "易用", "简单操作"],
        "translations": {
            "German": "Einfache Bedienung",
            "French": "utilisation simple",
        },
    },
}

SCENE_ALIASES: Dict[str, Dict[str, str]] = {
    "cycling_recording": {"骑行": "cycling_recording", "biking": "cycling_recording"},
    "underwater_exploration": {"水下": "underwater_exploration", "underwater": "underwater_exploration"},
    "travel_documentation": {"旅行": "travel_documentation", "travel": "travel_documentation"},
    "family_use": {"家庭": "family_use", "family": "family_use"},
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def canonicalize_capability(label: str) -> str:
    """Return canonical capability slug for any raw label."""
    raw = _normalize(label)
    if not raw:
        return "unknown_capability"
    for slug, data in CANONICAL_CAPABILITIES.items():
        for alias in data.get("aliases", []):
            if _normalize(alias) in raw or raw in _normalize(alias):
                return slug
    # fallback: normalized words joined with underscore
    return raw.replace(" ", "_")


def canonicalize_scene_label(scene: str) -> str:
    raw = _normalize(scene)
    if not raw:
        return "unknown_scene"
    for base, alias_map in SCENE_ALIASES.items():
        for alias in alias_map.keys():
            if _normalize(alias) in raw:
                return base
    return raw.replace(" ", "_")


def english_capability_label(slug: str) -> str:
    return slug.replace("_", " ")


def get_capability_display(slug: str, language: str) -> str:
    entry = CANONICAL_CAPABILITIES.get(slug)
    if not entry:
        return english_capability_label(slug)
    translations = entry.get("translations", {})
    return translations.get(language, english_capability_label(slug))


def get_scene_display(scene_code: str, language: str) -> str:
    translations = SCENE_TRANSLATIONS.get(language, {})
    return translations.get(scene_code, scene_code.replace("_", " "))
