#!/usr/bin/env python3
"""Repair telemetry helpers for step-level rewrite loops."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List

from modules.fluency_check import check_fluency

LEARNINGS_DIR = Path('.learnings')
_FIELD_WEIGHTS = {
    'title': 10,
    'bullet_b1': 4,
    'bullet_b2': 3,
    'bullet_b3': 3,
    'bullet_b4': 2,
    'bullet_b5': 2,
    'aplus': 6,
    'aplus_content': 6,
}


@dataclass
class RepairRecord:
    timestamp: str
    run_id: str
    field: str
    rule_id: str
    severity: str
    original: str
    repaired: str
    repair_success: bool
    attempts: int
    benchmark_used: bool
    fluency_score_before: int
    fluency_score_after: int


def _run_root_from_artifact_dir(artifact_dir: str | Path) -> Path:
    path = Path(artifact_dir)
    return path.parent if path.name == 'step6_artifacts' else path


def _run_id_from_artifact_dir(artifact_dir: str | Path) -> str:
    return _run_root_from_artifact_dir(artifact_dir).name


def _repair_log_path(artifact_dir: str | Path) -> Path:
    return _run_root_from_artifact_dir(artifact_dir) / 'repair_log.jsonl'


def _repair_summary_path(artifact_dir: str | Path) -> Path:
    return _run_root_from_artifact_dir(artifact_dir) / 'repair_summary.json'


def _field_fluency_score(field: str, text: str) -> int:
    normalized_field = 'aplus_content' if field == 'aplus' else field
    max_score = _FIELD_WEIGHTS.get(normalized_field, _FIELD_WEIGHTS.get(field, 0))
    if not text or not max_score:
        return max_score
    issues = check_fluency(normalized_field, text)
    severities = {str(issue.severity).lower() for issue in issues}
    if 'high' in severities:
        return 0
    if 'medium' in severities:
        return max_score // 2
    return max_score


def _edit_distance_ratio(original: str, repaired: str) -> float:
    if original == repaired:
        return 0.0
    similarity = SequenceMatcher(a=original or '', b=repaired or '').ratio()
    return max(0.0, 1.0 - similarity)


def _is_false_positive_candidate(
    original: str,
    repaired: str,
    rule_id: str,
    *,
    fluency_score_before: int,
    fluency_score_after: int,
) -> bool:
    if not rule_id:
        return False
    ratio = _edit_distance_ratio(original, repaired)
    if ratio < 0.1:
        return True
    return fluency_score_before == fluency_score_after


def _append_false_positive_candidate(
    record: RepairRecord,
    *,
    edit_distance_ratio: float,
) -> Dict[str, Any]:
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        'date': record.timestamp[:10],
        'run_id': record.run_id,
        'field': record.field,
        'rule_id': record.rule_id,
        'original': record.original,
        'repaired': record.repaired,
        'edit_distance_ratio': round(edit_distance_ratio, 4),
        'suggested_action': 'raise threshold or add exemption',
    }
    path = LEARNINGS_DIR / 'false_positive_candidates.jsonl'
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')
    return payload


def _load_records(artifact_dir: str | Path) -> List[Dict[str, Any]]:
    path = _repair_log_path(artifact_dir)
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _write_summary(artifact_dir: str | Path) -> Dict[str, Any]:
    records = _load_records(artifact_dir)
    by_rule: Dict[str, Dict[str, int]] = {}
    false_positive_candidates: List[Dict[str, Any]] = []
    for record in records:
        rule_id = str(record.get('rule_id') or 'unknown')
        bucket = by_rule.setdefault(rule_id, {'attempted': 0, 'succeeded': 0, 'warned': 0})
        bucket['attempted'] += 1
        if record.get('repair_success'):
            bucket['succeeded'] += 1
        else:
            bucket['warned'] += 1
        if record.get('false_positive_candidate'):
            false_positive_candidates.append(record['false_positive_candidate'])

    summary = {
        'total_repairs_attempted': len(records),
        'total_repairs_succeeded': sum(1 for record in records if record.get('repair_success')),
        'total_repairs_warned': sum(1 for record in records if not record.get('repair_success')),
        'by_rule': by_rule,
        'false_positive_candidates': false_positive_candidates,
    }
    path = _repair_summary_path(artifact_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def initialize_repair_logs(artifact_dir: str | Path) -> None:
    run_root = _run_root_from_artifact_dir(artifact_dir)
    run_root.mkdir(parents=True, exist_ok=True)
    log_path = _repair_log_path(artifact_dir)
    if not log_path.exists():
        log_path.write_text('', encoding='utf-8')
    _write_summary(artifact_dir)


def record_repair(
    *,
    artifact_dir: str | Path,
    field: str,
    rule_id: str,
    severity: str,
    original: str,
    repaired: str,
    repair_success: bool,
    attempts: int = 1,
    benchmark_used: bool = False,
) -> Dict[str, Any]:
    run_root = _run_root_from_artifact_dir(artifact_dir)
    run_root.mkdir(parents=True, exist_ok=True)
    before_score = _field_fluency_score(field, original)
    after_score = _field_fluency_score(field, repaired)
    record = RepairRecord(
        timestamp=datetime.now().isoformat(timespec='seconds'),
        run_id=_run_id_from_artifact_dir(artifact_dir),
        field=field,
        rule_id=rule_id,
        severity=severity,
        original=original,
        repaired=repaired,
        repair_success=bool(repair_success),
        attempts=max(1, int(attempts or 1)),
        benchmark_used=bool(benchmark_used),
        fluency_score_before=before_score,
        fluency_score_after=after_score,
    )
    payload = asdict(record)
    ratio = _edit_distance_ratio(original, repaired)
    if _is_false_positive_candidate(
        original,
        repaired,
        rule_id,
        fluency_score_before=before_score,
        fluency_score_after=after_score,
    ):
        payload['false_positive_candidate'] = _append_false_positive_candidate(record, edit_distance_ratio=ratio)
    log_path = _repair_log_path(artifact_dir)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')
    _write_summary(artifact_dir)
    return payload


__all__ = [
    'LEARNINGS_DIR',
    'initialize_repair_logs',
    'record_repair',
    '_is_false_positive_candidate',
]
