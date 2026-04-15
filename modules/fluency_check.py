#!/usr/bin/env python3
"""Shared fluency checks and repair-prompt helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set


FLUENCY_HEADER_TRAILING_PREPOSITIONS = {"with", "for", "and", "or", "of"}
FLUENCY_DASH_CHARS = ("—", "–")
FLUENCY_REPEAT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "you",
    "camera",
    "audio",
    "video",
    "recording",
}
FLUENCY_CONTENT_STOPWORDS = (FLUENCY_REPEAT_STOPWORDS - {"camera"}) | {
    "lightweight",
    "design",
    "ready",
    "smart",
    "easy",
    "clear",
    "daily",
}
FLUENCY_VERB_HINTS = {
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "can",
    "could",
    "will",
    "would",
    "should",
    "may",
    "might",
    "must",
    "do",
    "does",
    "did",
    "capture",
    "captures",
    "document",
    "documents",
    "record",
    "records",
    "keep",
    "keeps",
    "support",
    "supports",
    "deliver",
    "delivers",
    "weigh",
    "weighs",
    "disappears",
    "clips",
    "stays",
    "means",
}
FLUENCY_RUPTURE_STARTERS = {"it", "this", "the", "these", "our", "you"}
SPEC_PATTERN = re.compile(r"\b(?:\d+[Kk]|(?:\d+(?:\.\d+)?(?:fps|g|kg|oz|min|mins|minutes|m|ft|%|°)))\b")


@dataclass
class FluencyIssue:
    field: str
    rule_id: str
    severity: str
    message: str
    span: str


def _split_header_body(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    parts = re.split(r"\s*[—–]\s*", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", str(text or "").strip()


def _tokenize_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9À-ÖØ-öø-ÿ%°']+", text or "")


def _normalize_word_root(token: str) -> str:
    value = re.sub(r"[^a-z0-9%°]+", "", str(token or "").lower())
    if len(value) <= 3:
        return value
    if value.endswith("ies") and len(value) > 4:
        return value[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if value.endswith(suffix) and len(value) - len(suffix) >= 3:
            return value[:-len(suffix)]
    return value


def _has_verb(text: str) -> bool:
    tokens = [_normalize_word_root(token) for token in _tokenize_words(text)]
    if not tokens:
        return False
    if any(token in FLUENCY_VERB_HINTS for token in tokens):
        return True
    return any(token.endswith("ed") or token.endswith("ing") for token in tokens if len(token) >= 4)


def _contains_predicate(text: str) -> bool:
    return _has_verb(text)


def _content_roots(text: str) -> Set[str]:
    roots: Set[str] = set()
    for token in _tokenize_words(text):
        root = _normalize_word_root(token)
        if len(root) < 3 or root in FLUENCY_CONTENT_STOPWORDS or root in FLUENCY_VERB_HINTS:
            continue
        roots.add(root)
    return roots


def _semantic_overlap(header: str, body: str) -> bool:
    header_roots = _content_roots(header)
    body_roots = _content_roots(body)
    if not header_roots or not body_roots:
        return False
    return bool(header_roots.intersection(body_roots))


def _has_dangling_dash(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    return any(stripped.endswith(dash) for dash in FLUENCY_DASH_CHARS)


def _dash_tail_without_predicate(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    parts = re.split(r"\s*[—–]\s*", value)
    if len(parts) < 2:
        return False
    tail = parts[-1].strip().strip(".,;:!?")
    if not tail:
        return False
    tail_tokens = _tokenize_words(tail)
    if not tail_tokens:
        return False
    if _contains_predicate(tail):
        return False
    if "," in tail:
        return False
    if len(tail_tokens) >= 8:
        return False
    first_token = tail_tokens[0].lower()
    if first_token in {"featuring", "including", "delivering"} or first_token.endswith("ing"):
        return False
    if len(tail_tokens) > 5:
        return False
    if not all(re.match(r"^[A-Za-z0-9%°]+$", token) for token in tail_tokens):
        return False
    return True


def _repeated_word_roots(text: str) -> List[str]:
    counts = {}
    for token in _tokenize_words(text):
        root = _normalize_word_root(token)
        if len(root) < 4 or root in FLUENCY_REPEAT_STOPWORDS:
            continue
        counts[root] = counts.get(root, 0) + 1
    return sorted(root for root, count in counts.items() if count > 2)


def _extract_specs(text: str) -> str:
    specs = SPEC_PATTERN.findall(text or "")
    return ", ".join(specs) if specs else "none"


def _check_header_body_rupture(field: str, text: str) -> Optional[FluencyIssue]:
    if "—" not in text:
        return None
    header, _, body = text.partition("—")
    header = header.strip()
    body = body.strip()
    if not header or not body:
        return None

    body_tokens = _tokenize_words(body)
    if len(body_tokens) < 2:
        return None

    first_token = re.sub(r"[^a-z0-9%°]+", "", body_tokens[0].lower())
    if first_token not in FLUENCY_RUPTURE_STARTERS:
        return None
    if _has_verb(header):
        return None
    if not _contains_predicate(body):
        return None
    if _semantic_overlap(header, body):
        return None

    return FluencyIssue(
        field=field,
        rule_id="header_body_rupture",
        severity="high",
        message=(
            "Header is a noun phrase but body opens as an independent sentence "
            "- rewrite body to flow from header using a comma or participial phrase"
        ),
        span=text[:80],
    )


def check_fluency(field: str, text: str) -> List[FluencyIssue]:
    issues: List[FluencyIssue] = []
    value = str(text or "")
    header, body = _split_header_body(value)

    if header:
        header_tokens = [_normalize_word_root(token) for token in _tokenize_words(header)]
        if header_tokens and header_tokens[-1] in FLUENCY_HEADER_TRAILING_PREPOSITIONS:
            issues.append(
                FluencyIssue(
                    field=field,
                    rule_id="header_trailing_preposition",
                    severity="medium",
                    message=f"Header ends with a trailing preposition '{header_tokens[-1]}'",
                    span=value[:80],
                )
            )
        rupture = _check_header_body_rupture(field, value)
        if rupture:
            issues.append(rupture)

    if _has_dangling_dash(value):
        issues.append(
            FluencyIssue(
                field=field,
                rule_id="dangling_dash",
                severity="medium",
                message="Sentence ends with a dangling dash",
                span=value[:80],
            )
        )
    elif _dash_tail_without_predicate(value):
        issues.append(
            FluencyIssue(
                field=field,
                rule_id="dash_tail_without_predicate",
                severity="medium",
                message="Dash tail is a noun phrase without a predicate",
                span=value[:80],
            )
        )

    repeated_roots = _repeated_word_roots(body or value)
    if repeated_roots:
        issues.append(
            FluencyIssue(
                field=field,
                rule_id="repeated_word_root",
                severity="medium",
                message=f"Repeated word root more than twice: {', '.join(repeated_roots[:3])}",
                span=value[:80],
            )
        )

    return issues


def build_rupture_repair_prompt(
    original_text: str,
    benchmark_bullets: Sequence[str],
    required_specs: str,
) -> str:
    benchmark_block = "\n".join(str(item).strip() for item in benchmark_bullets[:3] if str(item).strip()) or "none"
    return (
        "You are an Amazon copywriter fixing a bullet point.\n\n"
        "The bullet has a Header - Body structure where the header and body read\n"
        "as two disconnected sentences. Fix it so they flow as one cohesive thought.\n\n"
        "Rewrite options (pick the best fit):\n"
        "A) Keep header, rewrite body to open with a participial phrase or comma clause\n"
        '   e.g. "LIGHTWEIGHT DESIGN - At just 35g, it disappears on your chest..."\n'
        "B) Keep header, rewrite body to start with a quantified benefit\n"
        '   e.g. "LIGHTWEIGHT DESIGN - 35g of featherlight build means all-day wear..."\n'
        "C) Merge header concept into body as a strong action opener\n"
        '   e.g. "Weighs Just 35g - clips to chest or helmet so you shoot hands-free..."\n\n'
        "Reference examples of well-connected Header - Body bullets:\n"
        f"{benchmark_block}\n\n"
        "Rules:\n"
        f"- Keep ALL keywords and numeric specs intact: {required_specs}\n"
        "- Do NOT add new claims\n"
        "- Return the fixed bullet only, no explanation\n\n"
        "Bullet to fix:\n"
        f"{original_text}"
    )
