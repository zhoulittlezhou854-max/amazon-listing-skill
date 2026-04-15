from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


_CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "market_packs"


def _default_market_pack(country_code: str) -> Dict[str, Any]:
    return {
        "locale": country_code,
        "lexical_preferences": [],
        "faq_templates": [],
        "compliance_reminders": [],
        "after_sales_promises": [],
        "support_sop": [],
        "regulatory_watchouts": [],
        "launch_gate_checks": [],
        "compound_word_rules": [],
        "title_style_guidelines": [],
        "bullet_style_guidelines": [],
    }


def load_market_pack(country_code: str) -> Dict[str, Any]:
    normalized = (country_code or "").upper() or "US"
    path = _CONFIG_ROOT / f"{normalized}.json"
    if not path.exists():
        return _default_market_pack(normalized)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_market_pack(normalized)
    return {
        **_default_market_pack(normalized),
        **payload,
        "locale": payload.get("locale") or normalized,
    }


def apply_market_pack(base_policy: Dict[str, Any], market_pack: Dict[str, Any]) -> Dict[str, Any]:
    policy = dict(base_policy)
    policy["market_pack"] = market_pack
    compliance_directives = dict(policy.get("compliance_directives") or {})
    reminders = list(compliance_directives.get("market_pack_reminders") or [])
    for reminder in market_pack.get("compliance_reminders", []) or []:
        if reminder not in reminders:
            reminders.append(reminder)
    compliance_directives["market_pack_reminders"] = reminders
    watchouts = list(compliance_directives.get("regulatory_watchouts") or [])
    for reminder in market_pack.get("regulatory_watchouts", []) or []:
        if reminder not in watchouts:
            watchouts.append(reminder)
    compliance_directives["regulatory_watchouts"] = watchouts
    policy["compliance_directives"] = compliance_directives
    policy["operator_sop"] = list(market_pack.get("support_sop") or [])
    policy["launch_gate_checks"] = list(market_pack.get("launch_gate_checks") or [])
    policy["after_sales_guidance"] = {
        "promises": list(market_pack.get("after_sales_promises") or []),
        "support_sop": list(market_pack.get("support_sop") or []),
    }
    bullet_slot_rules = dict(policy.get("bullet_slot_rules") or {})
    b5 = dict(bullet_slot_rules.get("B5") or {})
    if b5:
        b5["after_sales_promises"] = list(market_pack.get("after_sales_promises") or [])
        b5["support_sop"] = list(market_pack.get("support_sop") or [])
        b5["launch_gate_checks"] = list(market_pack.get("launch_gate_checks") or [])
        required = list(b5.get("required_elements") or [])
        for item in ["localized_after_sales_reassurance", "service_handoff_clarity"]:
            if item not in required:
                required.append(item)
        b5["required_elements"] = required
        bullet_slot_rules["B5"] = b5
        policy["bullet_slot_rules"] = bullet_slot_rules
    metadata = dict(policy.get("metadata") or {})
    metadata["market_pack_locale"] = market_pack.get("locale", "")
    metadata["market_pack_after_sales_count"] = len(market_pack.get("after_sales_promises") or [])
    metadata["market_pack_sop_count"] = len(market_pack.get("support_sop") or [])
    policy["metadata"] = metadata
    return policy
