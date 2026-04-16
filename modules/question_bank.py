from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


_CONFIG_ROOT = Path(__file__).resolve().parents[1] / "config" / "question_banks"
_EU_LOCALES = {"DE", "FR", "IT", "ES", "UK"}


def _load_bank(name: str) -> Dict[str, Any]:
    path = _CONFIG_ROOT / f"{name}.json"
    if not path.exists():
        return {"category": name, "questions": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"category": name, "questions": []}


def _rank_questions(questions: List[Dict[str, Any]], entity_profile: Dict[str, Any], country_code: str) -> List[Dict[str, Any]]:
    claim_text = " ".join(str((row or {}).get("claim") or "") for row in entity_profile.get("claim_registry", []) or []).lower()
    ranked: List[Dict[str, Any]] = []
    seen = set()
    for item in questions:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "").strip()
        question = str(item.get("question") or "").strip()
        if not topic or not question or topic in seen:
            continue
        seen.add(topic)
        score = 0
        if str(item.get("priority") or "").lower() == "high":
            score += 10
        if topic.replace("_", " ") in claim_text:
            score += 5
        ranked.append(
            {
                "topic": topic,
                "question": question,
                "priority": item.get("priority") or "medium",
                "market": item.get("market") or country_code,
                "_score": score,
            }
        )
    ranked.sort(key=lambda row: (row["_score"], row["priority"] == "high"), reverse=True)
    for row in ranked:
        row.pop("_score", None)
    return ranked


def build_question_bank_context(entity_profile: Dict[str, Any], country_code: str) -> Dict[str, Any]:
    country_code = (country_code or "").upper() or "US"
    if not entity_profile:
        return {
            "category": "action_camera",
            "market": country_code,
            "questions": [],
            "evidence_hints": [],
        }
    category = str(entity_profile.get("category") or "action_camera")
    base_bank = _load_bank("action_camera" if "action" in category else category)
    market_bank = _load_bank("eu_compliance") if country_code in _EU_LOCALES else {"questions": []}
    questions = _rank_questions(
        list(base_bank.get("questions") or []) + list(market_bank.get("questions") or []),
        entity_profile,
        country_code,
    )
    evidence_hints = [
        str((row or {}).get("claim") or "").strip()
        for row in entity_profile.get("claim_registry", []) or []
        if str((row or {}).get("claim") or "").strip()
    ]
    return {
        "category": category,
        "market": country_code,
        "questions": questions,
        "evidence_hints": evidence_hints[:8],
    }
