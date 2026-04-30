"""Build the operational readiness verdict from listing candidates."""

from collections.abc import Mapping
from typing import Any

PREFERENCE_ORDER = ("hybrid", "version_a", "version_b")
_PASTE_READY_STATUSES = {"eligible", "paste_ready"}


def _dedupe_blockers(blockers: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for blocker in blockers:
        clean = str(blocker).strip()
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped


_SOURCE_REVIEW_TIEBREAK = {
    "stable": 0,
    "version_a": 0,
    "hybrid": 1,
    "experimental": 2,
    "version_b": 2,
    "unknown": 3,
}


def _blocker_weight(blocker: str) -> int:
    clean = str(blocker or "")
    if clean.startswith("risk_listing_not_ready") or clean.startswith("field_unavailable"):
        return 5
    if clean.startswith("slot_contract_failed"):
        return 4
    if "Repeated word root" in clean or clean.startswith("repeated_word_root"):
        return 3
    if clean.startswith("keyword_reconciliation"):
        return 3
    if clean.startswith("experimental_version"):
        return 2
    return 1


def _review_rank_key(row: Mapping[str, Any]) -> tuple[int, int, int]:
    blockers = list(row.get("blockers") or [])
    source_type = str(row.get("source_type") or "unknown")
    return (
        sum(_blocker_weight(blocker) for blocker in blockers),
        len(blockers),
        _SOURCE_REVIEW_TIEBREAK.get(source_type, 3),
    )


def _candidate_blockers(candidate_id: str, candidate: Mapping[str, Any]) -> list[str]:
    blockers = [str(item) for item in (candidate.get("paste_ready_blockers") or [])]

    reconciliation = candidate.get("keyword_reconciliation") or {}
    if not isinstance(reconciliation, Mapping) or reconciliation.get("status") != "complete":
        blockers.append("keyword_reconciliation_incomplete")

    if candidate_id == "hybrid" and not candidate.get("source_trace"):
        blockers.append("source_trace_missing")

    if candidate_id == "version_b":
        blockers.append("experimental_version_b_not_launch_authority")

    return _dedupe_blockers(blockers)


def _rank_candidate(candidate_id: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    blockers = _candidate_blockers(candidate_id, candidate)
    paste_ready_status = str(candidate.get("paste_ready_status") or "").strip().lower()
    reviewable_status = str(candidate.get("reviewable_status") or "").strip().lower()

    if paste_ready_status in _PASTE_READY_STATUSES and not blockers:
        eligibility = "paste_ready"
    elif reviewable_status == "reviewable":
        eligibility = "review_only"
    else:
        eligibility = "ineligible"

    return {
        "candidate_id": candidate_id,
        "eligibility": eligibility,
        "blockers": blockers,
        "source_type": candidate.get("source_type") or "unknown",
    }


def build_readiness_verdict(*, candidates: Mapping[str, Mapping[str, Any]], run_state: str) -> dict[str, Any]:
    """Rank candidates and produce the single operational listing decision."""
    rankings = [
        _rank_candidate(candidate_id, candidates[candidate_id])
        for candidate_id in PREFERENCE_ORDER
        if candidate_id in candidates
    ]
    paste_ready = [row for row in rankings if row["eligibility"] == "paste_ready"]
    review_only = sorted(
        [row for row in rankings if row["eligibility"] == "review_only"],
        key=_review_rank_key,
    )

    if paste_ready:
        operational_status = "READY_FOR_LISTING"
        recommended_output = paste_ready[0]["candidate_id"]
        launch_gate = {"passed": True, "blockers": []}
    elif review_only:
        operational_status = "REVIEW_REQUIRED"
        recommended_output = review_only[0]["candidate_id"]
        launch_gate = {
            "passed": False,
            "blockers": review_only[0]["blockers"] or ["manual_review_required"],
        }
    else:
        operational_status = "BLOCKED"
        recommended_output = ""
        concrete_blockers = _dedupe_blockers(
            [
                blocker
                for row in rankings
                for blocker in row.get("blockers", [])
            ]
        )
        launch_gate = {
            "passed": False,
            "blockers": ["no_reviewable_candidate", *concrete_blockers],
        }

    return {
        "operational_listing_status": operational_status,
        "candidate_listing_status": operational_status,
        "recommended_output": recommended_output,
        "run_state": run_state,
        "launch_gate": launch_gate,
        "candidate_rankings": rankings,
    }
