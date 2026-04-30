"""Final visible listing quality checks.

This module validates the exact copy an operator can paste. It is deliberately
deterministic and returns the candidate-shaped schema planned for later
ListingCandidate integration.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from modules import fluency_check as fc
from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

SCHEMA_VERSION = "final_visible_quality_v1"
READY = "READY_FOR_LISTING"
NOT_READY = "NOT_READY_FOR_LISTING"
FORBIDDEN_VISIBLE_SURFACES = ("best", "perfect", "guaranteed", "warranty")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _issue(
    code: str,
    message: str,
    *,
    severity: str = "blocker",
    repairable: bool = True,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "repairable": repairable,
    }


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped


def _add_blocker(report: dict[str, Any], blocker: str) -> None:
    report.setdefault("paste_ready_blockers", []).append(blocker)


def _add_field_issue(
    report: dict[str, Any],
    field: str,
    issue: dict[str, Any],
    *,
    blocker: str | None = None,
) -> None:
    report.setdefault("field_issues", {}).setdefault(field, []).append(issue)
    if issue.get("severity") == "blocker":
        _add_blocker(report, blocker or f"{issue['code']}:{field}")


def _add_slot_issue(
    report: dict[str, Any],
    slot: str,
    issue: dict[str, Any],
    *,
    blocker: str | None = None,
) -> None:
    normalized_slot = str(slot or "").strip().upper() or "UNKNOWN"
    report.setdefault("slot_issues", {}).setdefault(normalized_slot, []).append(issue)
    if issue.get("severity") == "blocker":
        _add_blocker(report, blocker or f"{issue['code']}:{normalized_slot}")


def _keyword_append_fragment(text: str) -> bool:
    return bool(
        re.search(
            r"\bIncludes\s+(?:pov|action|travel|wearable|thumb|body)\.?\s*$",
            text or "",
            re.IGNORECASE,
        )
    )


def _postprocess_join_artifact(text: str) -> bool:
    value = str(text or "")
    return bool(
        re.search(r"\b(?:documentation|walk|ride|recording)\s+The\.?\b", value)
        or re.search(r"\bwear\s+Capture\b", value)
        or re.search(r"\bPOV\s+For\s+suitable\b", value)
    )


def _forbidden_surfaces(text: str) -> list[str]:
    lowered = str(text or "").lower()
    hits: list[str] = []
    for surface in FORBIDDEN_VISIBLE_SURFACES:
        if surface == "best":
            if re.search(r"\bbest(?:[-\s]?use)?\b", lowered):
                hits.append(surface)
            continue
        if re.search(rf"\b{re.escape(surface)}\b", lowered):
            hits.append(surface)
    return hits


def _search_terms_bytes(artifact: Mapping[str, Any]) -> int:
    terms = artifact.get("search_terms") or []
    if isinstance(terms, list):
        text = " ".join(str(item).strip() for item in terms if str(item).strip())
    else:
        text = str(terms or "")
    return len(text.encode("utf-8"))


def _bullet_packets_by_slot(artifact: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    packets: dict[str, Mapping[str, Any]] = {}
    for packet in artifact.get("bullet_packets") or []:
        if not isinstance(packet, Mapping):
            continue
        slot = str(packet.get("slot") or "").strip().upper()
        if slot:
            packets[slot] = packet
    return packets


def _required_keywords(packet: Mapping[str, Any]) -> list[str]:
    return [
        str(item).strip()
        for item in (packet.get("required_keywords") or [])
        if str(item).strip()
    ]


def _check_bullet(
    report: dict[str, Any],
    slot: str,
    bullet: str,
    packet: Mapping[str, Any],
) -> None:
    normalized_slot = str(slot or "").strip().upper()
    field = f"bullet_{normalized_slot.lower()}"

    for fluency_issue in fc.check_fluency(field, bullet):
        code = f"fluency_artifact:{field}:{fluency_issue.rule_id}"
        _add_field_issue(report, field, _issue(code, fluency_issue.message, repairable=True), blocker=code)

    if _keyword_append_fragment(bullet):
        code = f"fluency_artifact:{field}:keyword_append_fragment"
        _add_field_issue(
            report,
            field,
            _issue(code, "Keyword was appended as a fragment instead of a sentence."),
            blocker=code,
        )

    if _postprocess_join_artifact(bullet):
        code = f"fluency_artifact:{field}:postprocess_join"
        _add_field_issue(
            report,
            field,
            _issue(code, "Postprocess produced a broken sentence join."),
            blocker=code,
        )

    normalized_bullet = _clean(bullet).lower()
    missing = [keyword for keyword in _required_keywords(packet) if keyword.lower() not in normalized_bullet]
    if missing:
        _add_slot_issue(
            report,
            normalized_slot,
            _issue("keyword_coverage_failed", f"Missing final visible keywords: {', '.join(missing)}"),
        )

    if normalized_slot == "B5":
        contract = build_slot_contract("B5")
        contract_result = validate_bullet_against_contract(bullet, contract)
        for reason in contract_result.get("reasons") or []:
            code = f"slot_contract_failed:{reason}"
            blocker = f"slot_contract_failed:B5:{reason}"
            _add_slot_issue(
                report,
                "B5",
                _issue(code, f"B5 slot contract failed: {reason}"),
                blocker=blocker,
            )


def _check_description(report: dict[str, Any], description: str) -> None:
    for surface in _forbidden_surfaces(description):
        _add_field_issue(
            report,
            "description",
            _issue("forbidden_surface", f"Forbidden visible term: {surface}"),
            blocker=f"forbidden_surface:description:{surface}",
        )

    if _postprocess_join_artifact(description):
        code = "fluency_artifact:description:postprocess_join"
        _add_field_issue(
            report,
            "description",
            _issue(code, "Description has a broken sentence join."),
            blocker=code,
        )


def validate_final_visible_copy(
    artifact: Mapping[str, Any],
    *,
    candidate_id: str,
    source_type: str,
) -> dict[str, Any]:
    """Validate final visible copy and return a candidate-compatible report."""
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "source_type": source_type,
        "status": "passed",
        "operational_status": READY,
        "field_issues": {},
        "slot_issues": {},
        "paste_ready_blockers": [],
        "review_only_warnings": [],
        "repair_log": [],
    }

    packets = _bullet_packets_by_slot(artifact)
    for index, bullet in enumerate(artifact.get("bullets") or [], start=1):
        slot = f"B{index}"
        _check_bullet(report, slot, str(bullet or ""), packets.get(slot, {}))

    _check_description(report, str(artifact.get("description") or ""))

    if _search_terms_bytes(artifact) < 120:
        report["review_only_warnings"].append("backend_search_terms_underused")

    report["paste_ready_blockers"] = _dedupe(report["paste_ready_blockers"])
    if report["paste_ready_blockers"]:
        report["status"] = "blocked"
        report["operational_status"] = NOT_READY

    return report


def _scene_phrase(packet: Mapping[str, Any]) -> str:
    scenes = [
        str(item).strip()
        for item in (packet.get("scene_mapping") or [])
        if str(item).strip()
    ]
    if "commuting_capture" in scenes:
        return "commute recording"
    if "travel_documentation" in scenes:
        return "travel recording"
    if "vlog_content_creation" in scenes:
        return "vlog recording"
    return "daily recording"


def _repair_b5_package_bullet(packet: Mapping[str, Any]) -> str:
    keywords = [
        str(item).strip()
        for item in (packet.get("required_keywords") or [])
        if str(item).strip()
    ]
    keyword_phrase = " and ".join(keywords) if keywords else "wearable camera"
    scene = _scene_phrase(packet)
    return (
        "READY-TO-RECORD KIT — "
        f"Open the box with the {keyword_phrase}, magnetic clip, back clip, USB cable, and 32GB SD card included. "
        f"Add microSD storage up to 256GB when you need more room, then attach it for {scene}."
    )


def _repair_keyword_append_fragment(bullet: str, packet: Mapping[str, Any]) -> str:
    repaired = re.sub(
        r"\s+Includes\s+(?:pov|action|travel|wearable|thumb|body)\.?\s*$",
        ".",
        str(bullet or ""),
        flags=re.IGNORECASE,
    ).strip()
    keywords = [
        str(item).strip()
        for item in (packet.get("required_keywords") or [])
        if str(item).strip()
    ]
    for keyword in keywords:
        if keyword.lower() in repaired.lower():
            continue
        if keyword.lower() == "pov camera":
            repaired = repaired.rstrip(".") + ". Use it as a POV camera for stable training and commute clips."
        elif keyword.lower() == "action camera":
            repaired = repaired.rstrip(".") + ". Keep the action camera setup focused on smooth daily recording."
        else:
            repaired = repaired.rstrip(".") + f". Use the {keyword} for daily recording."
    return repaired


def _repair_join_artifacts(text: str) -> str:
    repaired = str(text or "")
    repaired = re.sub(r"\b(documentation|walk|ride|recording)\s+The\.?\s+", r"\1. The ", repaired)
    repaired = re.sub(r"\bwear\s+Capture\b", "wear. Capture", repaired)
    repaired = re.sub(r"\bPOV\s+For\s+suitable\b", "POV. For suitable", repaired)
    return re.sub(r"\s+", " ", repaired).strip()


def _repair_missing_keywords(bullet: str, packet: Mapping[str, Any]) -> str:
    repaired = str(bullet or "").strip()
    keywords = [
        str(item).strip()
        for item in (packet.get("required_keywords") or [])
        if str(item).strip()
    ]
    for keyword in keywords:
        if keyword.lower() in repaired.lower():
            continue
        if keyword.lower() == "action camera":
            repaired = repaired.rstrip(".") + ". Keep the action camera ready for smooth daily recording."
        elif keyword.lower() == "pov camera":
            repaired = repaired.rstrip(".") + ". Use it as a POV camera for stable training and commute clips."
        else:
            repaired = repaired.rstrip(".") + f". Use the {keyword} for daily recording."
    return repaired


def _repair_description_compliance(description: str) -> str:
    repaired = _repair_join_artifacts(description)
    repaired = re.sub(r"\bbest[-\s]?use\b", "setup", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bbest\b", "suitable", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bperfect\b", "practical", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bguaranteed\b", "designed", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bwarranty\b", "support", repaired, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", repaired).strip()


def _repair_bullets(artifact: Mapping[str, Any], report: Mapping[str, Any]) -> list[str]:
    packets = _bullet_packets_by_slot(artifact)
    bullets = list(artifact.get("bullets") or [])
    for index, bullet in enumerate(bullets):
        slot = f"B{index + 1}"
        packet = packets.get(slot, {})
        repaired = str(bullet or "")
        if slot == "B5" and report.get("slot_issues", {}).get("B5"):
            repaired = _repair_b5_package_bullet(packet)
        if _keyword_append_fragment(repaired):
            repaired = _repair_keyword_append_fragment(repaired, packet)
        if report.get("slot_issues", {}).get(slot):
            repaired = _repair_missing_keywords(repaired, packet)
        repaired = _repair_join_artifacts(repaired)
        bullets[index] = repaired
    return bullets


def repair_final_visible_copy(
    artifact: Mapping[str, Any],
    *,
    candidate_id: str,
    source_type: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Repair deterministic final-visible blockers, then revalidate the copy."""
    original_report = validate_final_visible_copy(
        artifact,
        candidate_id=candidate_id,
        source_type=source_type,
    )
    repaired = deepcopy(dict(artifact))
    repaired["bullets"] = _repair_bullets(artifact, original_report)
    repaired["description"] = _repair_description_compliance(str(artifact.get("description") or ""))

    repaired_report = validate_final_visible_copy(
        repaired,
        candidate_id=candidate_id,
        source_type=source_type,
    )
    repair_log = list(original_report.get("repair_log") or [])
    if repaired.get("bullets") != list(artifact.get("bullets") or []):
        repair_log.append(
            {
                "field": "bullets",
                "action": "deterministic_final_visible_repair",
                "status": "applied",
            }
        )
    if repaired.get("description") != artifact.get("description"):
        repair_log.append(
            {
                "field": "description",
                "action": "deterministic_description_compliance_repair",
                "status": "applied",
            }
        )

    repaired_report["repair_log"] = repair_log
    if not repaired_report.get("paste_ready_blockers") and repair_log:
        repaired_report["status"] = "repaired"
        repaired_report["operational_status"] = READY

    repaired["final_visible_quality"] = repaired_report
    metadata = deepcopy(repaired.get("metadata") or {})
    metadata["final_visible_quality"] = repaired_report
    repaired["metadata"] = metadata
    return repaired, repaired_report
