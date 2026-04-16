#!/usr/bin/env python3
"""Dynamic STAG scene localization across locales."""

from __future__ import annotations

from typing import Dict, Optional


_STAG_SCENE_MAP: Dict[str, Dict[str, str]] = {
    "fr": {
        "cycling_recording": "Filmage lors de sorties cyclistes",
        "underwater_exploration": "Exploration et plongée sous-marine",
        "hiking_adventure": "Randonnée et aventure en plein air",
        "ski_snowboard": "Ski et snowboard",
        "surfing_water_sports": "Surf et sports nautiques",
        "family_travel": "Voyages en famille",
        "vlog_daily_life": "Vlog et vie quotidienne",
        "pet_recording": "Capture de moments avec animaux",
        "professional_inspection": "Inspection professionnelle",
        "real_estate_tour": "Visite immobilière",
    },
    "de": {
        "cycling_recording": "Aufnahmen bei Radtouren",
        "underwater_exploration": "Unterwasser-Erkundung",
        "hiking_adventure": "Wander- und Outdoor-Abenteuer",
        "ski_snowboard": "Ski- und Snowboardeinsätze",
        "surfing_water_sports": "Surf- und Wassersport",
        "family_travel": "Familienreisen",
        "vlog_daily_life": "Vlog & Alltag",
        "pet_recording": "Momente mit Haustieren",
        "professional_inspection": "Professionelle Inspektion",
        "real_estate_tour": "Immobilien-Besichtigungen",
    },
}


def register_stag_locale(locale: str, mapping: Dict[str, str]) -> None:
    locale = (locale or "").lower()
    if not locale:
        return
    current = _STAG_SCENE_MAP.setdefault(locale, {})
    current.update(mapping)


def get_stag_display(scene_id: str, locale: str) -> str:
    locale = (locale or "").lower()
    if not scene_id:
        return ""
    candidates = _STAG_SCENE_MAP.get(locale)
    if candidates:
        label = candidates.get(scene_id)
        if label:
            return label
    return scene_id.replace("_", " ").capitalize()
