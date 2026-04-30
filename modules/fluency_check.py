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
DIMENSION_CLUSTERS = {
    "mobility_commute": ["commut", "cycling", "bike", "ride", "on-the-go", "pov"],
    "professional_evidence": ["evidence", "security", "service", "work", "professional"],
    "technical_spec": ["resolution", "1080p", "4k", "battery", "runtime", "storage"],
    "kit_value": ["include", "package", "kit", "accessor", "memory card"],
    "usage_guidance": ["not", "avoid", "compatible", "support", "guidance", "best-use"],
}


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


def _keyword_append_fragment(text: str) -> bool:
    return bool(
        re.search(
            r"\bIncludes\s+(?:pov|action|travel|wearable|thumb|body)\.?\s*$",
            text or "",
            re.IGNORECASE,
        )
    )


def _orphan_the_artifact(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:documentation|recording|walk|ride)\s+The\.?\s*(?:$|[A-Z])",
            text or "",
        )
    )


def _capitalized_join_artifact(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:wear|clips?|recording|capture)\s+(?:Capture|The|For)\b",
            text or "",
        )
    )


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


def _extract_bullet_header(text: str) -> str:
    header, body = _split_header_body(text)
    if header:
        return header
    tokens = re.findall(r"\S+", str(text or "").strip())
    return " ".join(tokens[:10]).strip()


def _match_dimension_cluster(header: str) -> Optional[str]:
    lowered = str(header or "").lower()
    roots = {_normalize_word_root(token) for token in _tokenize_words(lowered)}
    for dimension, markers in DIMENSION_CLUSTERS.items():
        for marker in markers:
            marker_root = _normalize_word_root(marker)
            if marker_root and marker_root in roots:
                return dimension
            if marker.lower() in lowered:
                return dimension
    return None


def check_bullet_dimension_dedup(bullets: Sequence[str]) -> dict:
    matched: dict[str, List[int]] = {}
    for idx, bullet in enumerate(bullets or [], start=1):
        header = _extract_bullet_header(str(bullet or ""))
        dimension = _match_dimension_cluster(header)
        if not dimension:
            continue
        matched.setdefault(dimension, []).append(idx)
    for dimension, indices in matched.items():
        if len(indices) >= 3:
            return {
                "pass": False,
                "check": "bullet_dimension_dedup",
                "severity": "medium",
                "issue": "dimension_repeat",
                "duplicated_dimension": dimension,
                "affected_bullets": indices,
            }
    return {
        "pass": True,
        "check": "bullet_dimension_dedup",
        "severity": "medium",
        "issue": None,
        "duplicated_dimension": None,
        "affected_bullets": [],
    }


def check_bullet_total_bytes(bullets: Sequence[str]) -> dict:
    total = sum(len(str(bullet or "").encode("utf-8")) for bullet in bullets or [])
    return {
        "pass": total <= 1000,
        "check": "bullet_total_bytes",
        "severity": "soft",
        "total_bytes": total,
        "limit": 1000,
    }


def build_bullet_dimension_repair_instruction(duplicated_dimension: str, affected_bullets: Sequence[int]) -> str:
    indices = ", ".join(f"B{idx}" for idx in affected_bullets or [])
    return (
        "Repair instruction - Bullet Dimension Dedup:\n"
        f'The following bullets are repeating the same selling point dimension "{duplicated_dimension}":\n'
        f"  Affected bullets: {indices or 'none'}\n\n"
        "When rewriting these bullets, change their CORE DIMENSION - do not just rephrase the same idea. "
        "Each rewritten bullet must address a clearly different audience or feature angle from the others."
    )


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

    if _keyword_append_fragment(value):
        issues.append(
            FluencyIssue(
                field=field,
                rule_id="keyword_append_fragment",
                severity="high",
                message="Keyword was appended as a fragment instead of a natural sentence",
                span=value[:80],
            )
        )
    if _orphan_the_artifact(value):
        issues.append(
            FluencyIssue(
                field=field,
                rule_id="orphan_the_artifact",
                severity="high",
                message="Postprocess left an orphan 'The' sentence artifact",
                span=value[:80],
            )
        )
    if _capitalized_join_artifact(value):
        issues.append(
            FluencyIssue(
                field=field,
                rule_id="capitalized_join_artifact",
                severity="high",
                message="Postprocess joined two sentences without punctuation",
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
