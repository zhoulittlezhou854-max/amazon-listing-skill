from __future__ import annotations

import re
from typing import Any, List, Tuple

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MAX_BULLET_CHARS = 255


def _normalize_text(value: Any) -> str:
    return _NON_ALNUM_RE.sub(" ", str(value or "").lower()).strip()


def collect_missing_l2_keywords(bullets: List[str], assigned_l2: List[str]) -> List[str]:
    visible = " ".join(str(item or "") for item in bullets)
    normalized_visible = _normalize_text(visible)
    missing: List[str] = []
    for keyword in assigned_l2 or []:
        clean = str(keyword or "").strip()
        if not clean:
            continue
        if _normalize_text(clean) not in normalized_visible and clean not in missing:
            missing.append(clean)
    return missing


def _append_keyword_phrase(bullet: str, keyword: str) -> str:
    bullet = str(bullet or "").strip()
    keyword = str(keyword or "").strip()
    if not bullet or not keyword:
        return bullet
    suffix = f" ideal for {keyword} use."
    if bullet.endswith("."):
        return f"{bullet[:-1]}{suffix}"
    return f"{bullet}{suffix}"


def _is_safe_bullet_candidate(original: str, candidate: str, keyword: str) -> bool:
    if not candidate or len(candidate) > _MAX_BULLET_CHARS:
        return False
    normalized_original = _normalize_text(original)
    normalized_candidate = _normalize_text(candidate)
    normalized_keyword = _normalize_text(keyword)
    if normalized_keyword in normalized_original:
        return False
    if normalized_candidate.count(" with ") > 2 or normalized_candidate.count(" for ") > 3:
        return False
    return True


def repair_hybrid_bullets_for_l2(
    bullets: List[str],
    missing_keywords: List[str],
    max_repairs: int = 2,
) -> Tuple[List[str], List[dict]]:
    repaired = list(bullets or [])
    actions: List[dict] = []
    used_slots: set[int] = set()

    for keyword in missing_keywords or []:
        if len(actions) >= max_repairs:
            break
        for idx, bullet in enumerate(repaired):
            if idx in used_slots:
                continue
            candidate = _append_keyword_phrase(bullet, keyword)
            if not _is_safe_bullet_candidate(bullet, candidate, keyword):
                continue
            repaired[idx] = candidate
            used_slots.add(idx)
            actions.append(
                {
                    "action": "l2_backfill",
                    "slot": f"B{idx + 1}",
                    "keyword": keyword,
                }
            )
            break
    return repaired, actions
