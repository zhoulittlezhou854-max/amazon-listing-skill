#!/usr/bin/env python3
"""Non-blocking validation for listing input tables."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openpyxl import load_workbook  # type: ignore
except Exception:  # pragma: no cover
    load_workbook = None


REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "attribute_table": ["Field_Name", "Value"],
    "keyword_table": ["keyword", "search_volume"],
    "review_table": ["ASIN", "Bullet_1", "BSR_Rank"],
    "aba_merged": ["keyword", "search_volume"],
}


@dataclass
class ValidationWarning:
    table: str
    severity: str
    message: str


def _resolve_table_path(run_config: Any, table_name: str) -> Optional[Path]:
    input_files = getattr(run_config, "input_files", None) or {}
    path = input_files.get(table_name)
    if not path:
        return None
    return Path(path)


def _read_header(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"} and load_workbook is not None:
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
            return [str(cell).strip() for cell in first_row if cell is not None and str(cell).strip()]
        finally:
            wb.close()
    if suffix == ".txt":
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        first_row = next(reader, [])
    return [str(cell).strip() for cell in first_row if str(cell).strip()]


def validate_input_tables(run_config: Any) -> List[ValidationWarning]:
    warnings: List[ValidationWarning] = []
    for table_name, required_cols in REQUIRED_COLUMNS.items():
        path = _resolve_table_path(run_config, table_name)
        if not path or not path.exists():
            warnings.append(
                ValidationWarning(
                    table=table_name,
                    severity="medium",
                    message=f"{table_name} 文件不存在，将使用降级策略",
                )
            )
            continue
        try:
            header = _read_header(path)
        except Exception as exc:
            warnings.append(
                ValidationWarning(
                    table=table_name,
                    severity="high",
                    message=f"{table_name} 读取失败：{exc}",
                )
            )
            continue
        if not header:
            # Legacy text tables are still accepted by the current pipeline.
            continue
        missing = [col for col in required_cols if col not in header]
        if missing:
            warnings.append(
                ValidationWarning(
                    table=table_name,
                    severity="high",
                    message=f"{table_name} 缺少必填列：{missing}",
                )
            )
    return warnings


def warnings_as_dicts(warnings: List[ValidationWarning]) -> List[Dict[str, Any]]:
    return [asdict(item) for item in warnings]
