from __future__ import annotations

from typing import Optional


LIVE_SUCCESS_STATUSES = {"live", "live_success"}
LIVE_GENERATION_STATUSES = {"live", "live_success", "live_with_fallback"}


def is_live_success_status(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in LIVE_SUCCESS_STATUSES


def is_live_generation_status(status: Optional[str]) -> bool:
    return str(status or "").strip().lower() in LIVE_GENERATION_STATUSES


__all__ = [
    "LIVE_SUCCESS_STATUSES",
    "LIVE_GENERATION_STATUSES",
    "is_live_generation_status",
    "is_live_success_status",
]
