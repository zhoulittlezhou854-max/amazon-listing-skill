from __future__ import annotations

import re
from typing import Any, List, Tuple

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MAX_BULLET_CHARS = 255
LISTING_L2_COVERAGE_THRESHOLD = 3

_SEMANTIC_HINTS = {
    "travel": {"travel", "commute", "commuting", "journey", "trip", "daily"},
    "camera": {"camera", "recording", "capture"},
    "body": {"body", "body-worn", "wearable", "worn", "security", "evidence"},
    "audio": {"audio", "aac", "sound", "voice"},
    "thumb": {"thumb", "mini", "small", "compact"},
    "pov": {"pov", "helmet", "cycling", "hands-free", "bike", "cyclist"},
}


def _normalize_text(value: Any) -> str:
    return _NON_ALNUM_RE.sub(" ", str(value or "").lower()).strip()


def _tokenize(value: Any) -> list[str]:
    normalized = _normalize_text(value)
    return [token for token in normalized.split() if token]


def _expanded_keyword_tokens(keyword: str) -> set[str]:
    tokens = set(_tokenize(keyword))
    expanded = set(tokens)
    for token in tokens:
        expanded.update(_SEMANTIC_HINTS.get(token, set()))
    return expanded


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


def analyze_listing_l2_coverage(
    bullets: List[str],
    slot_targets: dict[str, list[str]],
    threshold: int = LISTING_L2_COVERAGE_THRESHOLD,
) -> dict:
    covered_slots: list[str] = []
    missing_keywords: list[str] = []
    for idx, bullet in enumerate(bullets or [], start=1):
        slot = f"B{idx}"
        targets = [str(item).strip() for item in (slot_targets.get(slot) or []) if str(item).strip()]
        if not targets:
            continue
        normalized_bullet = _normalize_text(bullet)
        slot_hit = False
        for keyword in targets:
            if _normalize_text(keyword) in normalized_bullet:
                slot_hit = True
            elif keyword not in missing_keywords:
                missing_keywords.append(keyword)
        if slot_hit:
            covered_slots.append(slot)
    return {
        "covered_slots": covered_slots,
        "coverage_count": len(covered_slots),
        "missing_keywords": missing_keywords,
        "meets_threshold": len(covered_slots) >= threshold,
        "threshold": threshold,
    }


def _append_keyword_phrase(bullet: str, keyword: str) -> str:
    bullet = str(bullet or "").strip()
    keyword = str(keyword or "").strip()
    if not bullet or not keyword:
        return bullet
    suffix = f" ideal for {keyword} use."
    if bullet.endswith("."):
        return f"{bullet[:-1]}{suffix}"
    return f"{bullet}{suffix}"


def _candidate_keyword_injections(bullet: str, keyword: str) -> list[str]:
    bullet = str(bullet or "").strip()
    keyword = str(keyword or "").strip()
    if not bullet or not keyword:
        return [bullet]

    candidates: list[str] = []
    tail_variants = [
        f"ideal for {keyword}.",
        f"{keyword} support.",
        f"{keyword}.",
    ]
    if re.search(r"ideal for [^.]+\.$", bullet, flags=re.IGNORECASE):
        for variant in tail_variants:
            candidate = re.sub(r"ideal for [^.]+\.$", variant, bullet, flags=re.IGNORECASE)
            if candidate not in candidates:
                candidates.append(candidate)

    can_swap_tail_sentence = len(bullet) >= (_MAX_BULLET_CHARS - 10) and bool(re.search(r"[.?!]", bullet))
    if can_swap_tail_sentence:
        for variant in tail_variants:
            sentence_swap = re.sub(r"[^.?!]+[.?!]?$", variant, bullet).strip()
            if sentence_swap and sentence_swap not in candidates:
                candidates.append(sentence_swap)

    appended = _append_keyword_phrase(bullet, keyword)
    if appended not in candidates:
        candidates.append(appended)
    return candidates


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


def _semantic_slot_score(slot: str, bullet: str, keyword: str) -> float:
    bullet_tokens = set(_tokenize(bullet))
    keyword_tokens = _expanded_keyword_tokens(keyword)
    overlap = len(bullet_tokens & keyword_tokens)
    score = float(overlap)
    normalized_bullet = _normalize_text(bullet)
    if _normalize_text(keyword) in normalized_bullet:
        score += 5.0
    if slot == "B5":
        score -= 0.5
    return score


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
        ranked_candidates = sorted(
            (
                (idx, bullet, _semantic_slot_score(f"B{idx + 1}", bullet, keyword))
                for idx, bullet in enumerate(repaired)
                if idx not in used_slots
            ),
            key=lambda item: item[2],
            reverse=True,
        )
        for idx, bullet, _score in ranked_candidates:
            if idx in used_slots:
                continue
            for candidate in _candidate_keyword_injections(bullet, keyword):
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
            if idx in used_slots:
                break
    return repaired, actions
