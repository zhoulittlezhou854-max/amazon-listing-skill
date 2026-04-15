#!/usr/bin/env python3
"""Cross-field coherence heuristics for titles and bullets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence


@dataclass
class CoherenceIssue:
    issue_type: str
    severity: str
    fields: List[str]
    message: str


_DIMENSION_PATTERNS: Dict[str, List[str]] = {
    'weight_portability': ['35g', '0.1 kilograms', 'lightweight', 'portable', 'thumb-sized', 'compact'],
    'battery_runtime': ['battery', 'minutes', 'minute', 'hours', 'runtime', 'recording time'],
    'video_quality': ['4k', '1080p', 'hd', 'resolution', 'uhd'],
    'waterproof': ['waterproof', 'ipx', 'diving', 'water resistant', 'underwater'],
    'audio': ['audio', 'mic', 'microphone', 'sound'],
    'stabilization': ['stabilization', 'eis', 'smooth', 'stable'],
    'view_angle': ['degree', '°', 'wide angle', 'view angle'],
}
_SPEC_PATTERN = re.compile(
    r"\b(?:\d+[kK]|\d+[pP]|\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|g|kg|°|degree))\b"
)


def _normalized(text: str) -> str:
    return str(text or '').lower()


def _detect_dimensions(text: str) -> List[str]:
    value = _normalized(text)
    hits: List[str] = []
    for dimension, patterns in _DIMENSION_PATTERNS.items():
        if any(pattern in value for pattern in patterns):
            hits.append(dimension)
    return hits


def _header_segment(text: str) -> str:
    value = str(text or '').strip()
    if '—' in value:
        return value.partition('—')[0].strip()
    return value[:40].strip()


def _classify_dimensions(headers: Sequence[str]) -> Dict[str, List[int]]:
    dimension_map: Dict[str, List[int]] = {}
    for idx, header in enumerate(headers):
        for dimension in _detect_dimensions(header):
            dimension_map.setdefault(dimension, []).append(idx)
    return dimension_map


def _check_bullet_dimension_overlap(bullets: Sequence[str]) -> List[CoherenceIssue]:
    headers = [_header_segment(str(bullet or '')) for bullet in bullets or []]
    dimension_to_fields = _classify_dimensions(headers)
    issues: List[CoherenceIssue] = []
    for dimension, field_indices in dimension_to_fields.items():
        if len(field_indices) >= 2:
            issues.append(
                CoherenceIssue(
                    issue_type='duplicate_dimension',
                    severity='medium',
                    fields=[f'bullet_b{idx + 1}' for idx in field_indices],
                    message=f'Headers repeat the {dimension} selling dimension',
                )
            )
    return issues


def _extract_title_specs(title: str) -> List[str]:
    specs = [match.group(0).lower().strip() for match in _SPEC_PATTERN.finditer(title or '')]
    deduped: List[str] = []
    for spec in specs:
        if spec not in deduped:
            deduped.append(spec)
    return deduped


def _check_title_claims_expanded(title: str, bullets: Sequence[str]) -> List[CoherenceIssue]:
    bullet_text = ' '.join(str(bullet or '') for bullet in bullets or []).lower()
    missing_specs: List[str] = []
    for spec in _extract_title_specs(title):
        if spec not in bullet_text:
            missing_specs.append(spec)
    if not missing_specs:
        return []
    return [
        CoherenceIssue(
            issue_type='title_claim_not_expanded',
            severity='medium',
            fields=['title'] + [f'bullet_b{idx}' for idx, _ in enumerate(bullets or [], start=1)],
            message=f'Title spec claims are not expanded in bullets: {", ".join(missing_specs)}',
        )
    ]


def check_coherence(title: str, bullets: Sequence[str], aplus: str) -> List[CoherenceIssue]:
    issues: List[CoherenceIssue] = []
    issues.extend(_check_bullet_dimension_overlap(bullets))
    issues.extend(_check_title_claims_expanded(title, bullets))
    return issues


__all__ = ['CoherenceIssue', 'check_coherence']
