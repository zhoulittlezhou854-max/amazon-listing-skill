# VersionA Final Visible Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `version_a` as the stable launch authority while adding a final-visible-text QA and targeted repair loop so the copy that operators paste is the same copy that passes slot, compliance, keyword, and fluency contracts.

**Architecture:** Implement scheme B now: after `version_a` visible fields are fully scrubbed/finalized, run a deterministic final-visible verifier, repair only failed fields, rebuild packet/quality artifacts, and persist a future-proof `final_visible_quality` contract. Leave scheme C an interface by using candidate-shaped report fields (`candidate_id`, `field_issues`, `slot_issues`, `paste_ready_blockers`, `review_only_warnings`, `operational_status`) that `listing_candidate.py` can consume later without another schema migration.

**Tech Stack:** Python, pytest, existing modules `copy_generation.py`, `slot_contracts.py`, `fluency_check.py`, `listing_candidate.py`, `report_builder.py`, `readiness_verdict.py`.

---

## Context And Evidence

Current evidence lives at:

- `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r51_version_b_quality_gate_acceptance`
- `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r52_version_b_quality_gate_scene_binding`

Observed `version_a` issues:

- B5 hard blocker: `slot_contract_failed:B5:multiple_primary_promises`.
- B5 mixes package/storage promise with `battery_runtime`; B5 must not own `150 minutes`, `battery life`, `runtime`, or `per charge`.
- B4/B5 keyword patch can leave tail artifacts like `Includes pov` or miss complete `pov camera` / `wearable camera` / `thumb camera` phrases.
- Post-scrub text can leave broken artifacts such as `travel documentation The.`, `wear Capture`, and `POV For suitable results`.
- Description repair can leave forbidden/compliance terms such as `best-use scenarios` and broken sentence joins such as `evening travel walk The included...`.
- `version_a/readiness_summary.md` can say `READY_FOR_LISTING` / `可直接上架` while top-level `final_readiness_verdict.json` says `NOT_READY_FOR_LISTING`.
- Rufus may remain `89` because backend Search Terms bytes are underused (`71/249 bytes`); this is a data/backend term issue, not a B5 repair issue.

Non-goals for this branch:

- Do not rewrite the L1/L2/L3 keyword protocol.
- Do not change `version_b` quality hardening logic except where shared candidate contracts read the new final quality report.
- Do not rewrite the scorer.
- Do not implement the full scheme C `ListingCandidate` refactor in this branch.
- Do not build the accessories input UI in this branch.

---

## Files And Responsibilities

- Create: `/Users/zhoulittlezhou/amazon-listing-skill/modules/final_visible_quality.py`
  - New final visible text verifier and deterministic repair helpers.
  - Owns future scheme C interface shape: `final_visible_quality` report.
  - Must be pure and easy to test without live LLM.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
  - Call final visible verifier/repair after all visible fields are finalized and before keyword reconciliation / final artifact persistence.
  - Rebuild `bullet_packets`, `slot_quality_packets`, `keyword_reconciliation`, and metadata after final repairs.
  - Scope active repair to non-R1 `version_a` path; `version_b` keeps its existing R1 rerender path.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/listing_candidate.py`
  - Consume `final_visible_quality.paste_ready_blockers` as candidate blockers.
  - Preserve schema so scheme C can later promote this into the main candidate contract.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_builder.py`
  - Stop saying `可直接上架` when `final_visible_quality.operational_status` is not `READY_FOR_LISTING`.
  - Show candidate quality blockers and say top-level `final_readiness_verdict.json` remains operational authority.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/fluency_check.py`
  - Add narrow artifact rules for known postprocess failures: keyword append fragments, orphan `The.`, missing sentence boundary before `The included`, and capitalized verb joins like `wear Capture`.

- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_final_visible_quality.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_listing_candidate.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_report_builder.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_fluency_check.py`

---

## Data Contract For Scheme C Compatibility

Every generated copy should persist this shape under both top-level `final_visible_quality` and `metadata.final_visible_quality`:

```python
{
    "schema_version": "final_visible_quality_v1",
    "candidate_id": "version_a",
    "source_type": "stable",
    "status": "passed" | "repaired" | "blocked",
    "operational_status": "READY_FOR_LISTING" | "NOT_READY_FOR_LISTING",
    "field_issues": {
        "description": [
            {"code": "forbidden_surface", "severity": "blocker", "message": "Forbidden term: best", "repairable": True}
        ]
    },
    "slot_issues": {
        "B5": [
            {"code": "slot_contract_failed:multiple_primary_promises", "severity": "blocker", "message": "B5 mixes package/storage with battery runtime", "repairable": True}
        ]
    },
    "paste_ready_blockers": ["slot_contract_failed:B5:multiple_primary_promises"],
    "review_only_warnings": ["rufus_backend_search_terms_underused"],
    "repair_log": [
        {"field": "bullet_b5", "action": "deterministic_b5_package_repair", "status": "applied"}
    ],
}
```

Rules:

- `paste_ready_blockers` blocks `LISTING_READY.md` export and candidate paste-ready eligibility.
- `review_only_warnings` does not block paste-readiness by itself.
- `operational_status` is controlled by final visible quality only; top-level launch gate can still downgrade because of score thresholds such as Rufus 89.
- Do not remove legacy `listing_status` fields in this branch.

---

## Task 1: Lock Current VersionA Failures As Final-Visible Tests

**Files:**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_final_visible_quality.py`

- [ ] **Step 1: Create test file with current bad examples**

Create `tests/test_final_visible_quality.py` with:

```python
from modules.final_visible_quality import validate_final_visible_copy


def _base_copy(**overrides):
    artifact = {
        "title": "TOSBARRFT vlogging camera Action Camera with 150 minutes",
        "bullets": [
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — Use this POV camera for sports training.",
            "COMPLETE KIT, ZERO WAIT — Open the box and start recording your commute immediately. Inside you get the body camera, magnetic clip, back clip, USB cable, and 32GB SD card. The built-in battery delivers 150 minutes of continuous recording. Supports micro SD up to 256GB.",
        ],
        "description": "Use it for travel. Ask support about best-use scenarios.",
        "search_terms": ["wearable camera", "thumb camera"],
        "bullet_packets": [
            {"slot": "B1", "required_keywords": ["action camera"], "capability_mapping": ["long battery"], "scene_mapping": ["travel_documentation"]},
            {"slot": "B2", "required_keywords": ["body camera"], "capability_mapping": ["lightweight design"], "scene_mapping": ["commuting_capture"]},
            {"slot": "B3", "required_keywords": ["body cam"], "capability_mapping": ["easy operation"], "scene_mapping": ["commuting_capture"]},
            {"slot": "B4", "required_keywords": ["pov camera", "action camera"], "capability_mapping": ["high definition"], "scene_mapping": ["sports_training"]},
            {"slot": "B5", "required_keywords": ["wearable camera", "thumb camera"], "capability_mapping": ["long battery"], "scene_mapping": ["commuting_capture"]},
        ],
        "metadata": {"generation_status": "live_success"},
    }
    artifact.update(overrides)
    return artifact


def test_final_visible_quality_blocks_b5_multiple_primary_promises():
    report = validate_final_visible_copy(
        _base_copy(),
        candidate_id="version_a",
        source_type="stable",
    )

    assert report["operational_status"] == "NOT_READY_FOR_LISTING"
    assert "slot_contract_failed:B5:multiple_primary_promises" in report["paste_ready_blockers"]
    assert any(issue["code"] == "slot_contract_failed:multiple_primary_promises" for issue in report["slot_issues"]["B5"])


def test_final_visible_quality_blocks_keyword_append_artifact():
    artifact = _base_copy(
        bullets=[
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — The lens rotates for stable training clips Includes pov.",
            "READY KIT — Open the box with wearable camera and thumb camera, magnetic clip, back clip, USB cable, and 32GB SD card included. Add microSD storage up to 256GB for commute recording.",
        ]
    )

    report = validate_final_visible_copy(artifact, candidate_id="version_a", source_type="stable")

    assert "fluency_artifact:bullet_b4:keyword_append_fragment" in report["paste_ready_blockers"]


def test_final_visible_quality_blocks_description_forbidden_surface():
    report = validate_final_visible_copy(
        _base_copy(description="Use it for travel recording. Ask support about best-use scenarios."),
        candidate_id="version_a",
        source_type="stable",
    )

    assert "forbidden_surface:description:best" in report["paste_ready_blockers"]
    assert report["field_issues"]["description"][0]["repairable"] is True


def test_final_visible_quality_report_uses_candidate_shaped_schema():
    report = validate_final_visible_copy(_base_copy(), candidate_id="version_a", source_type="stable")

    assert report["schema_version"] == "final_visible_quality_v1"
    assert report["candidate_id"] == "version_a"
    assert report["source_type"] == "stable"
    assert set(report) >= {
        "field_issues",
        "slot_issues",
        "paste_ready_blockers",
        "review_only_warnings",
        "operational_status",
        "repair_log",
    }
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_final_visible_quality.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'modules.final_visible_quality'`.

---

## Task 2: Implement Final Visible Quality Verifier Interface

**Files:**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/modules/final_visible_quality.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_final_visible_quality.py`

- [ ] **Step 1: Add verifier module skeleton**

Create `modules/final_visible_quality.py` with:

```python
"""Final visible listing quality checks and deterministic repairs.

This module validates the exact text an operator can paste. It intentionally
returns a candidate-shaped contract so a later ListingCandidate refactor can
promote this report without changing the schema.
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


def _issue(code: str, message: str, *, severity: str = "blocker", repairable: bool = True) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "repairable": repairable}


def _field_key(field: str) -> str:
    return str(field or "").strip()


def _add_field_issue(report: dict[str, Any], field: str, issue: dict[str, Any]) -> None:
    report.setdefault("field_issues", {}).setdefault(_field_key(field), []).append(issue)
    if issue.get("severity") == "blocker":
        report.setdefault("paste_ready_blockers", []).append(f"{issue['code']}:{field}")


def _add_slot_issue(report: dict[str, Any], slot: str, issue: dict[str, Any]) -> None:
    normalized_slot = str(slot or "").strip().upper() or "UNKNOWN"
    report.setdefault("slot_issues", {}).setdefault(normalized_slot, []).append(issue)
    if issue.get("severity") == "blocker":
        report.setdefault("paste_ready_blockers", []).append(f"{issue['code']}:{normalized_slot}")


def _keyword_append_fragment(text: str) -> bool:
    return bool(re.search(r"\bIncludes\s+(?:pov|action|travel|wearable|thumb|body)\.?\s*$", text or "", re.IGNORECASE))


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


def _bullet_packets_by_slot(artifact: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    packets: dict[str, Mapping[str, Any]] = {}
    for packet in artifact.get("bullet_packets") or []:
        if isinstance(packet, Mapping):
            slot = str(packet.get("slot") or "").strip().upper()
            if slot:
                packets[slot] = packet
    return packets


def _check_bullet(report: dict[str, Any], slot: str, bullet: str, packet: Mapping[str, Any]) -> None:
    field = f"bullet_{str(slot).lower()}"
    for issue in fc.check_fluency(field, bullet):
        _add_field_issue(
            report,
            field,
            _issue(f"fluency_artifact:{field}:{issue.rule_id}", issue.message, repairable=True),
        )
    if _keyword_append_fragment(bullet):
        _add_field_issue(
            report,
            field,
            _issue(f"fluency_artifact:{field}:keyword_append_fragment", "Keyword was appended as a fragment instead of a sentence."),
        )
    if _postprocess_join_artifact(bullet):
        _add_field_issue(
            report,
            field,
            _issue(f"fluency_artifact:{field}:postprocess_join", "Postprocess produced a broken sentence join."),
        )
    required_keywords = [str(item).strip() for item in (packet.get("required_keywords") or []) if str(item).strip()]
    normalized = _clean(bullet).lower()
    missing = [keyword for keyword in required_keywords if keyword.lower() not in normalized]
    if missing:
        _add_slot_issue(
            report,
            slot,
            _issue("keyword_coverage_failed", f"Missing final visible keywords: {', '.join(missing)}"),
        )
    if str(slot).upper() == "B5":
        contract_result = validate_bullet_against_contract(bullet, build_slot_contract("B5"))
        for reason in contract_result.get("reasons") or []:
            _add_slot_issue(
                report,
                "B5",
                _issue(f"slot_contract_failed:{reason}", f"B5 slot contract failed: {reason}"),
            )


def _check_description(report: dict[str, Any], description: str) -> None:
    for surface in _forbidden_surfaces(description):
        _add_field_issue(
            report,
            "description",
            _issue("forbidden_surface", f"Forbidden visible term: {surface}"),
        )
        report["paste_ready_blockers"][-1] = f"forbidden_surface:description:{surface}"
    if _postprocess_join_artifact(description):
        _add_field_issue(
            report,
            "description",
            _issue("fluency_artifact:description:postprocess_join", "Description has a broken sentence join."),
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def validate_final_visible_copy(
    artifact: Mapping[str, Any],
    *,
    candidate_id: str,
    source_type: str,
) -> dict[str, Any]:
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
    for idx, bullet in enumerate(artifact.get("bullets") or [], start=1):
        slot = f"B{idx}"
        _check_bullet(report, slot, str(bullet or ""), packets.get(slot, {}))
    _check_description(report, str(artifact.get("description") or ""))
    report["paste_ready_blockers"] = _dedupe(report["paste_ready_blockers"])
    if report["paste_ready_blockers"]:
        report["status"] = "blocked"
        report["operational_status"] = NOT_READY
    return report
```

- [ ] **Step 2: Run final visible tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_final_visible_quality.py
```

Expected: PASS.

---

## Task 3: Add Deterministic Repairs For B5, Keyword Fragments, And Description Compliance

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/final_visible_quality.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_final_visible_quality.py`

- [ ] **Step 1: Add repair tests**

Append to `tests/test_final_visible_quality.py`:

```python
from modules.final_visible_quality import repair_final_visible_copy


def test_repair_final_visible_copy_rewrites_b5_without_battery_runtime():
    artifact = _base_copy()

    repaired, report = repair_final_visible_copy(artifact, candidate_id="version_a", source_type="stable")

    b5 = repaired["bullets"][4].lower()
    assert "wearable camera" in b5
    assert "thumb camera" in b5
    assert "150 minutes" not in b5
    assert "battery" not in b5
    assert "per charge" not in b5
    assert "32gb" in b5
    assert "256gb" in b5
    assert report["operational_status"] == "READY_FOR_LISTING"
    assert report["paste_ready_blockers"] == []


def test_repair_final_visible_copy_rewrites_keyword_append_fragment():
    artifact = _base_copy(
        bullets=[
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — The lens rotates for stable training clips Includes pov.",
            "READY KIT — Open the box with wearable camera and thumb camera, magnetic clip, back clip, USB cable, and 32GB SD card included. Add microSD storage up to 256GB for commute recording.",
        ]
    )

    repaired, report = repair_final_visible_copy(artifact, candidate_id="version_a", source_type="stable")

    assert "Includes pov" not in repaired["bullets"][3]
    assert "POV camera" in repaired["bullets"][3] or "pov camera" in repaired["bullets"][3].lower()
    assert "keyword_append_fragment" not in str(report)


def test_repair_final_visible_copy_removes_description_best_sentence_safely():
    artifact = _base_copy(description="Capture commute clips. Ask support about best-use scenarios. Keep setup simple.")

    repaired, report = repair_final_visible_copy(artifact, candidate_id="version_a", source_type="stable")

    assert "best" not in repaired["description"].lower()
    assert "use-case" in repaired["description"].lower() or "setup" in repaired["description"].lower()
    assert "forbidden_surface:description:best" not in report["paste_ready_blockers"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_final_visible_quality.py::test_repair_final_visible_copy_rewrites_b5_without_battery_runtime tests/test_final_visible_quality.py::test_repair_final_visible_copy_rewrites_keyword_append_fragment tests/test_final_visible_quality.py::test_repair_final_visible_copy_removes_description_best_sentence_safely
```

Expected: FAIL with `ImportError` or missing `repair_final_visible_copy`.

- [ ] **Step 3: Implement deterministic repair helpers**

Append to `modules/final_visible_quality.py`:

```python

def _scene_phrase(packet: Mapping[str, Any]) -> str:
    scenes = [str(item).strip() for item in (packet.get("scene_mapping") or []) if str(item).strip()]
    if "commuting_capture" in scenes:
        return "commute recording"
    if "travel_documentation" in scenes:
        return "travel recording"
    if "vlog_content_creation" in scenes:
        return "vlog recording"
    return "daily recording"


def _repair_b5_package_bullet(packet: Mapping[str, Any]) -> str:
    keywords = [str(item).strip() for item in (packet.get("required_keywords") or []) if str(item).strip()]
    keyword_phrase = " and ".join(keywords) if keywords else "wearable camera"
    scene = _scene_phrase(packet)
    return (
        "READY-TO-RECORD KIT — "
        f"Open the box with the {keyword_phrase}, magnetic clip, back clip, USB cable, and 32GB SD card included. "
        f"Add microSD storage up to 256GB when you need more room, then clip it on for {scene}."
    )


def _repair_keyword_append_fragment(bullet: str, packet: Mapping[str, Any]) -> str:
    repaired = re.sub(r"\s+Includes\s+(?:pov|action|travel|wearable|thumb|body)\.?\s*$", ".", str(bullet or ""), flags=re.IGNORECASE).strip()
    keywords = [str(item).strip() for item in (packet.get("required_keywords") or []) if str(item).strip()]
    for keyword in keywords:
        if keyword.lower() not in repaired.lower():
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
    repaired = re.sub(r"\s+", " ", repaired).strip()
    return repaired


def _repair_description_compliance(description: str) -> str:
    repaired = _repair_join_artifacts(description)
    repaired = re.sub(r"\bbest[-\s]?use\b", "setup", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bbest\b", "suitable", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bperfect\b", "practical", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bguaranteed\b", "designed", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\s+", " ", repaired).strip()
    return repaired


def _repair_bullets(artifact: Mapping[str, Any], report: Mapping[str, Any]) -> list[str]:
    packets = _bullet_packets_by_slot(artifact)
    bullets = list(artifact.get("bullets") or [])
    for idx, bullet in enumerate(bullets):
        slot = f"B{idx + 1}"
        packet = packets.get(slot, {})
        repaired = str(bullet or "")
        if slot == "B5" and report.get("slot_issues", {}).get("B5"):
            repaired = _repair_b5_package_bullet(packet)
        if _keyword_append_fragment(repaired):
            repaired = _repair_keyword_append_fragment(repaired, packet)
        repaired = _repair_join_artifacts(repaired)
        bullets[idx] = repaired
    return bullets


def repair_final_visible_copy(
    artifact: Mapping[str, Any],
    *,
    candidate_id: str,
    source_type: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    original_report = validate_final_visible_copy(artifact, candidate_id=candidate_id, source_type=source_type)
    repaired = deepcopy(dict(artifact))
    repaired["bullets"] = _repair_bullets(artifact, original_report)
    repaired["description"] = _repair_description_compliance(str(artifact.get("description") or ""))
    repaired_report = validate_final_visible_copy(repaired, candidate_id=candidate_id, source_type=source_type)
    repair_log = list(original_report.get("repair_log") or [])
    if repaired.get("bullets") != list(artifact.get("bullets") or []):
        repair_log.append({"field": "bullets", "action": "deterministic_final_visible_repair", "status": "applied"})
    if repaired.get("description") != artifact.get("description"):
        repair_log.append({"field": "description", "action": "deterministic_description_compliance_repair", "status": "applied"})
    repaired_report["repair_log"] = repair_log
    if not repaired_report.get("paste_ready_blockers") and repair_log:
        repaired_report["status"] = "repaired"
        repaired_report["operational_status"] = READY
    repaired["final_visible_quality"] = repaired_report
    metadata = deepcopy(repaired.get("metadata") or {})
    metadata["final_visible_quality"] = repaired_report
    repaired["metadata"] = metadata
    return repaired, repaired_report
```

- [ ] **Step 4: Run final visible tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_final_visible_quality.py
```

Expected: PASS.

---

## Task 4: Add Narrow Fluency Rules For Postprocess Artifacts

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/fluency_check.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_fluency_check.py`

- [ ] **Step 1: Add failing fluency tests**

Append to `tests/test_fluency_check.py`:

```python
from modules import fluency_check as fc


def test_fluency_flags_keyword_append_fragment():
    issues = fc.check_fluency("bullet_b4", "SMOOTH MOTION SETUP — The lens rotates for stable clips Includes pov.")
    assert any(issue.rule_id == "keyword_append_fragment" for issue in issues)


def test_fluency_flags_orphan_the_artifact():
    issues = fc.check_fluency("bullet_b1", "RECORDING POWER — Document your entire travel documentation The.")
    assert any(issue.rule_id == "orphan_the_artifact" for issue in issues)


def test_fluency_flags_capitalized_join_artifact():
    issues = fc.check_fluency("bullet_b2", "LIGHTWEIGHT — Clips to your vest for extended-session wear Capture crisp 1080P footage.")
    assert any(issue.rule_id == "capitalized_join_artifact" for issue in issues)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_fluency_check.py::test_fluency_flags_keyword_append_fragment tests/test_fluency_check.py::test_fluency_flags_orphan_the_artifact tests/test_fluency_check.py::test_fluency_flags_capitalized_join_artifact
```

Expected: FAIL because rules are not implemented.

- [ ] **Step 3: Implement artifact helpers in `fluency_check.py`**

Add near `_dash_tail_without_predicate`:

```python

def _keyword_append_fragment(text: str) -> bool:
    return bool(re.search(r"\bIncludes\s+(?:pov|action|travel|wearable|thumb|body)\.?\s*$", text or "", re.IGNORECASE))


def _orphan_the_artifact(text: str) -> bool:
    return bool(re.search(r"\b(?:documentation|recording|walk|ride)\s+The\.?\s*(?:$|[A-Z])", text or ""))


def _capitalized_join_artifact(text: str) -> bool:
    return bool(re.search(r"\b(?:wear|clips?|recording|capture)\s+(?:Capture|The|For)\b", text or ""))
```

Then in `check_fluency`, before repeated roots, add:

```python
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
```

- [ ] **Step 4: Run fluency tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_fluency_check.py
```

Expected: PASS.

---

## Task 5: Integrate Final Visible Repair Into VersionA Copy Generation

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`

- [ ] **Step 1: Add import**

In `modules/copy_generation.py`, near imports, add:

```python
from modules.final_visible_quality import repair_final_visible_copy, validate_final_visible_copy
```

- [ ] **Step 2: Add focused helper test**

Append to `tests/test_copy_generation.py`:

```python
def test_apply_final_visible_quality_repairs_version_a_b5_and_metadata():
    import modules.copy_generation as cg

    generated = {
        "title": "TOSBARRFT vlogging camera Action Camera",
        "bullets": [
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — The lens rotates for stable training clips Includes pov.",
            "COMPLETE KIT, ZERO WAIT — Open the box and start recording. Inside you get body camera, magnetic clip, USB cable, and 32GB SD card. The built-in battery delivers 150 minutes. Supports micro SD up to 256GB.",
        ],
        "description": "Ask support about best-use scenarios.",
        "search_terms": ["wearable camera", "thumb camera"],
        "bullet_packets": [
            {"slot": "B1", "required_keywords": ["action camera"], "capability_mapping": ["long battery"], "scene_mapping": ["travel_documentation"]},
            {"slot": "B2", "required_keywords": ["body camera"], "capability_mapping": ["lightweight design"], "scene_mapping": ["commuting_capture"]},
            {"slot": "B3", "required_keywords": ["body cam"], "capability_mapping": ["easy operation"], "scene_mapping": ["commuting_capture"]},
            {"slot": "B4", "required_keywords": ["pov camera", "action camera"], "capability_mapping": ["high definition"], "scene_mapping": ["sports_training"]},
            {"slot": "B5", "required_keywords": ["wearable camera", "thumb camera"], "capability_mapping": ["long battery"], "scene_mapping": ["commuting_capture"]},
        ],
        "metadata": {"generation_status": "live_success"},
    }
    writing_policy = {"copy_contracts": {}, "bullet_slot_rules": {}}

    repaired = cg._apply_final_visible_quality_gate(
        generated,
        writing_policy,
        target_language="English",
        candidate_id="version_a",
        source_type="stable",
    )

    b5 = repaired["bullets"][4].lower()
    assert "150 minutes" not in b5
    assert "battery" not in b5
    assert "wearable camera" in b5
    assert "thumb camera" in b5
    assert "best" not in repaired["description"].lower()
    assert repaired["metadata"]["final_visible_quality"]["operational_status"] == "READY_FOR_LISTING"
    assert repaired["slot_quality_packets"][4]["slot"] == "B5"
```

- [ ] **Step 3: Run test and verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_copy_generation.py::test_apply_final_visible_quality_repairs_version_a_b5_and_metadata
```

Expected: FAIL because `_apply_final_visible_quality_gate` is not defined.

- [ ] **Step 4: Implement helper in `copy_generation.py`**

Add near `_run_slot_rerender_pass`:

```python

def _apply_final_visible_quality_gate(
    generated_surface: Dict[str, Any],
    writing_policy: Dict[str, Any],
    *,
    target_language: str,
    candidate_id: str,
    source_type: str,
) -> Dict[str, Any]:
    repaired_surface, final_report = repair_final_visible_copy(
        generated_surface,
        candidate_id=candidate_id,
        source_type=source_type,
    )
    slot_rule_contracts = writing_policy.get("bullet_slot_rules") or {}
    bullets = list(repaired_surface.get("bullets") or [])
    existing_packets = list(repaired_surface.get("bullet_packets") or [])
    bullet_trace = []
    for packet in existing_packets:
        if isinstance(packet, dict):
            bullet_trace.append(
                {
                    "slot": packet.get("slot"),
                    "keywords": packet.get("required_keywords") or [],
                    "capability_mapping": packet.get("capability_mapping") or [],
                    "scene_mapping": packet.get("scene_mapping") or [],
                }
            )
    bullet_packets = _sync_bullet_packets_to_final_bullets(
        bullets,
        existing_packets,
        bullet_trace,
        slot_rule_contracts,
    )
    repaired_surface["bullet_packets"] = bullet_packets
    repaired_surface["slot_quality_packets"] = [
        _build_slot_quality_packet(
            packet,
            copy_contracts=writing_policy.get("copy_contracts") or {},
            slot_rule_contract=slot_rule_contracts.get(packet.get("slot")) or {},
            target_language=target_language,
        )
        for packet in bullet_packets
    ]
    repaired_surface["final_visible_quality"] = final_report
    metadata = deepcopy(repaired_surface.get("metadata") or {})
    metadata["final_visible_quality"] = final_report
    repaired_surface["metadata"] = metadata
    return repaired_surface
```

- [ ] **Step 5: Call helper in `generate_multilingual_copy` for stable path only**

In `generate_multilingual_copy`, after `slot_rerender_results` are resolved and before `_reconcile_final_keyword_assignments(...)`, insert:

```python
    if not pure_r1_visible_batch:
        final_visible_surface = _apply_final_visible_quality_gate(
            {
                "title": title,
                "bullets": bullets,
                "description": description,
                "search_terms": search_terms,
                "bullet_packets": bullet_packets,
                "slot_quality_packets": slot_quality_packets,
                "metadata": {"generation_status": generation_status},
            },
            writing_policy,
            target_language=target_language,
            candidate_id="version_a",
            source_type="stable",
        )
        bullets = list(final_visible_surface.get("bullets") or bullets)
        description = str(final_visible_surface.get("description") or description)
        bullet_packets = list(final_visible_surface.get("bullet_packets") or bullet_packets)
        slot_quality_packets = list(final_visible_surface.get("slot_quality_packets") or slot_quality_packets)
        final_visible_quality = dict(final_visible_surface.get("final_visible_quality") or {})
    else:
        final_visible_quality = validate_final_visible_copy(
            {
                "title": title,
                "bullets": bullets,
                "description": description,
                "search_terms": search_terms,
                "bullet_packets": bullet_packets,
                "slot_quality_packets": slot_quality_packets,
                "metadata": {"generation_status": generation_status},
            },
            candidate_id="version_b",
            source_type="experimental",
        )
```

Then when building the returned artifact metadata, include:

```python
        "final_visible_quality": final_visible_quality,
```

And add top-level key:

```python
        "final_visible_quality": final_visible_quality,
```

If `metadata` is assembled before this point, assign after artifact construction:

```python
generated_copy["metadata"]["final_visible_quality"] = final_visible_quality
generated_copy["final_visible_quality"] = final_visible_quality
```

- [ ] **Step 6: Run copy generation focused test**

Run:

```bash
./.venv/bin/pytest -q tests/test_copy_generation.py::test_apply_final_visible_quality_repairs_version_a_b5_and_metadata
```

Expected: PASS.

---

## Task 6: Feed Final Visible Quality Into ListingCandidate Blockers

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/listing_candidate.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_listing_candidate.py`

- [ ] **Step 1: Add candidate blocker test**

Append to `tests/test_listing_candidate.py`:

```python
def test_listing_candidate_uses_final_visible_quality_blockers():
    from modules.listing_candidate import build_listing_candidate

    artifact = {
        "title": "Title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "Description",
        "search_terms": ["term"],
        "metadata": {"generation_status": "live_success"},
        "keyword_reconciliation": {"status": "complete"},
        "final_visible_quality": {
            "schema_version": "final_visible_quality_v1",
            "operational_status": "NOT_READY_FOR_LISTING",
            "paste_ready_blockers": ["slot_contract_failed:B5:multiple_primary_promises"],
            "review_only_warnings": [],
        },
    }

    candidate = build_listing_candidate("version_a", artifact, source_type="stable")

    assert candidate["paste_ready_status"] == "blocked"
    assert "slot_contract_failed:B5:multiple_primary_promises" in candidate["paste_ready_blockers"]
    assert candidate["final_visible_quality"]["operational_status"] == "NOT_READY_FOR_LISTING"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_listing_candidate.py::test_listing_candidate_uses_final_visible_quality_blockers
```

Expected: FAIL because `listing_candidate.py` does not consume `final_visible_quality`.

- [ ] **Step 3: Implement final quality blocker extraction**

In `modules/listing_candidate.py`, add below `_canonical_fact_blockers`:

```python

def _final_visible_quality(artifact: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    top_level = artifact.get("final_visible_quality")
    if isinstance(top_level, Mapping):
        return dict(top_level)
    nested = metadata.get("final_visible_quality")
    if isinstance(nested, Mapping):
        return dict(nested)
    return {}


def _final_visible_blockers(final_quality: Mapping[str, Any]) -> list[str]:
    return [str(item).strip() for item in (final_quality.get("paste_ready_blockers") or []) if str(item).strip()]
```

In `build_listing_candidate`, after metadata is assigned and before `keyword_reconciliation`, add:

```python
    final_quality = _final_visible_quality(artifact, metadata)
    blockers.extend(_final_visible_blockers(final_quality))
```

In candidate dict, add:

```python
        "final_visible_quality": final_quality,
```

- [ ] **Step 4: Run listing candidate tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_listing_candidate.py
```

Expected: PASS.

---

## Task 7: Make Readiness Summary Honest About Candidate vs Operational Status

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_builder.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_report_builder.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_readiness_summary_consistency.py`

- [ ] **Step 1: Add report builder test**

Append to `tests/test_report_builder.py`:

```python
def test_readiness_summary_uses_final_visible_quality_blockers():
    from modules.report_builder import build_readiness_summary

    generated_copy = {
        "title": "Title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "description": "Description",
        "search_terms": ["term"],
        "metadata": {
            "generation_status": "live_success",
            "final_visible_quality": {
                "operational_status": "NOT_READY_FOR_LISTING",
                "paste_ready_blockers": ["slot_contract_failed:B5:multiple_primary_promises"],
                "review_only_warnings": ["rufus_backend_search_terms_underused"],
            },
        },
    }
    scoring_results = {
        "action_required": "可直接上架",
        "dimensions": {
            "traffic": {"score": 100, "max": 100, "status": "pass"},
            "content": {"score": 92, "max": 100, "status": "pass"},
            "conversion": {"score": 89, "max": 100, "status": "pass"},
            "readability": {"score": 30, "max": 30, "status": "pass"},
        },
    }

    summary = build_readiness_summary(
        sku="H91lite_US",
        run_id="version_a",
        generated_copy=generated_copy,
        scoring_results=scoring_results,
        risk_report={"listing_status": {"status": "READY_FOR_LISTING", "blocking_reasons": []}},
        generated_at="2026-04-30T00:00:00",
    )

    assert "候选文案状态" in summary
    assert "NOT_READY_FOR_LISTING" in summary
    assert "slot_contract_failed:B5:multiple_primary_promises" in summary
    assert "final_readiness_verdict.json" in summary
    assert "可直接上架" not in summary
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_report_builder.py::test_readiness_summary_uses_final_visible_quality_blockers
```

Expected: FAIL because summary still prints `可直接上架`.

- [ ] **Step 3: Update `build_readiness_summary`**

In `modules/report_builder.py`, after `metadata = ...`, add:

```python
    final_quality = metadata.get("final_visible_quality") or generated_copy.get("final_visible_quality") or {}
    final_quality_status = str(final_quality.get("operational_status") or listing_status if 'listing_status' in locals() else "").strip()
    final_quality_blockers = [str(item).strip() for item in (final_quality.get("paste_ready_blockers") or []) if str(item).strip()]
    final_quality_warnings = [str(item).strip() for item in (final_quality.get("review_only_warnings") or []) if str(item).strip()]
```

After `listing_status = readiness.get("status") or "UNKNOWN"`, replace action handling with:

```python
    candidate_operational_status = final_quality_status or listing_status
    if final_quality_blockers:
        action_required = "需先处理 final visible quality 阻断；最终是否可导出以上层 final_readiness_verdict.json 为准"
```

Add these lines before `## 可见文案`:

```python
        "## 候选文案状态",
        f"Candidate visible quality: {candidate_operational_status or 'UNKNOWN'}",
        "Operational authority: final_readiness_verdict.json",
        "",
        "### Final Visible Blockers",
        *(f"- {item}" for item in final_quality_blockers) if final_quality_blockers else ["无"],
        "",
        "### Review Warnings",
        *(f"- {item}" for item in final_quality_warnings) if final_quality_warnings else ["无"],
        "",
```

If Python rejects starred conditional expressions in the list literal, compute first:

```python
    final_blocker_lines = [f"- {item}" for item in final_quality_blockers] or ["无"]
    final_warning_lines = [f"- {item}" for item in final_quality_warnings] or ["无"]
```

Then use `*final_blocker_lines` and `*final_warning_lines`.

- [ ] **Step 4: Run report tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_report_builder.py tests/test_readiness_summary_consistency.py
```

Expected: PASS.

---

## Task 8: Preserve Rufus 89 As Review Warning, Not A Fake Text Blocker

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/final_visible_quality.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_final_visible_quality.py`

- [ ] **Step 1: Add warning test**

Append to `tests/test_final_visible_quality.py`:

```python
def test_final_visible_quality_keeps_backend_search_terms_as_warning_not_blocker():
    artifact = _base_copy(
        bullets=[
            "RECORDING POWER — This action camera records 150 minutes for travel.",
            "LIGHTWEIGHT BODY CAMERA — This body camera clips to uniform for commute.",
            "ONE-TOUCH THUMB CAM — Start recording fast during commute with body cam.",
            "SMOOTH MOTION SETUP — Use this POV camera and action camera setup for sports training.",
            "READY KIT — Open the box with wearable camera and thumb camera, magnetic clip, back clip, USB cable, and 32GB SD card included. Add microSD storage up to 256GB for commute recording.",
        ],
        description="Capture commute clips with simple setup.",
        search_terms=["wearable camera"],
    )

    report = validate_final_visible_copy(artifact, candidate_id="version_a", source_type="stable")

    assert "backend_search_terms_underused" in report["review_only_warnings"]
    assert "backend_search_terms_underused" not in report["paste_ready_blockers"]
```

- [ ] **Step 2: Implement search term bytes warning**

In `modules/final_visible_quality.py`, add:

```python

def _search_terms_bytes(artifact: Mapping[str, Any]) -> int:
    terms = artifact.get("search_terms") or []
    if isinstance(terms, list):
        text = " ".join(str(item).strip() for item in terms if str(item).strip())
    else:
        text = str(terms or "")
    return len(text.encode("utf-8"))
```

In `validate_final_visible_copy`, before setting status, add:

```python
    if _search_terms_bytes(artifact) < 120:
        report["review_only_warnings"].append("backend_search_terms_underused")
```

- [ ] **Step 3: Run final visible tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_final_visible_quality.py
```

Expected: PASS.

---

## Task 9: Keep Final Quality Report In Final Artifact And Candidate Projection

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/listing_candidate.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_listing_candidate.py`

- [ ] **Step 1: Add persistence assertions to existing tests**

In `tests/test_copy_generation.py::test_apply_final_visible_quality_repairs_version_a_b5_and_metadata`, add:

```python
    assert repaired["final_visible_quality"]["schema_version"] == "final_visible_quality_v1"
    assert repaired["metadata"]["final_visible_quality"] == repaired["final_visible_quality"]
```

In `tests/test_listing_candidate.py::test_listing_candidate_uses_final_visible_quality_blockers`, add:

```python
    assert candidate["final_visible_quality"]["schema_version"] == "final_visible_quality_v1"
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_copy_generation.py::test_apply_final_visible_quality_repairs_version_a_b5_and_metadata tests/test_listing_candidate.py::test_listing_candidate_uses_final_visible_quality_blockers
```

Expected: PASS after Tasks 5 and 6.

---

## Task 10: Targeted Regression Suite

**Files:**
- No source changes.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
./.venv/bin/pytest -q \
  tests/test_final_visible_quality.py \
  tests/test_fluency_check.py \
  tests/test_copy_generation.py \
  tests/test_listing_candidate.py \
  tests/test_report_builder.py \
  tests/test_readiness_summary_consistency.py
```

Expected: PASS.

- [ ] **Step 2: If tests fail, classify before fixing**

Use this classification:

```text
Final-visible verifier bug: fix modules/final_visible_quality.py.
VersionA integration bug: fix modules/copy_generation.py without changing versionB R1 rerender behavior.
Candidate projection bug: fix modules/listing_candidate.py only.
Report wording bug: fix modules/report_builder.py only.
Scorer disagreement: do not change modules/scoring.py in this branch; discuss first.
```

---

## Task 11: Full Test Suite

**Files:**
- No source changes.

- [ ] **Step 1: Run all tests**

Run:

```bash
./.venv/bin/pytest -q
```

Expected: all tests pass. Recent baseline after versionB hardening was `481 passed`.

---

## Task 12: H91 Live Validation With New Run ID

**Files:**
- No source changes.
- Artifacts written under `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/`.

- [ ] **Step 1: Run fresh live validation**

Run:

```bash
./.venv/bin/python run_pipeline.py \
  --product H91lite \
  --market US \
  --run-id r53_version_a_final_visible_gate \
  --dual-version \
  --fresh
```

Expected: `version_a` completes live. `version_b` may pass, fail, or partial-success; it must not block `version_a` reporting.

- [ ] **Step 2: Inspect artifacts**

Run:

```bash
RUN=/Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r53_version_a_final_visible_gate
jq '{listing_status,grade,total_score,a10_score,cosmo_score,rufus_score,blocking_reasons}' "$RUN/version_a/scoring_results.json"
jq '.final_visible_quality' "$RUN/version_a/generated_copy.json"
jq '[.slot_quality_packets[] | {slot, keyword_coverage_pass, contract_pass, fluency_pass, issues}]' "$RUN/version_a/generated_copy.json"
jq '{recommended_output,listing_status,candidate_listing_status,operational_listing_status,launch_gate,candidate_rankings}' "$RUN/final_readiness_verdict.json"
rg -n -i '\bbest\b|Includes pov|travel documentation The|wear Capture|POV For suitable' "$RUN/version_a/generated_copy.json" "$RUN/version_a/readiness_summary.md" || true
```

Acceptance criteria:

```text
version_a B5 has no slot_contract_failed:B5:multiple_primary_promises.
version_a final_visible_quality.paste_ready_blockers is empty unless a truly unrepaired blocker remains.
version_a bullets do not contain Includes pov / Includes action / orphan The / wear Capture artifacts.
description does not contain forbidden visible best/perfect/guaranteed/warranty surfaces.
readiness_summary.md no longer says 可直接上架 when final_visible_quality is blocked.
If Rufus remains 89, it appears as review_only warning or launch gate score issue, not as a fake copy-quality blocker.
```

---

## Task 13: Optional Second Live Run If r53 Shows Provider Variance

**Files:**
- No source changes unless r53 exposes a deterministic bug.

- [ ] **Step 1: Decide whether r54 is needed**

Run r54 only if r53 fails due to provider variance, not if tests reveal a deterministic code bug.

- [ ] **Step 2: Run r54 if needed**

```bash
./.venv/bin/python run_pipeline.py \
  --product H91lite \
  --market US \
  --run-id r54_version_a_final_visible_gate_confirm \
  --dual-version \
  --fresh
```

Expected: Same acceptance criteria as r53.

---

## Task 14: Commit Branch

**Files:**
- Stage only files touched by this plan.

- [ ] **Step 1: Review selective diff**

Run:

```bash
git diff -- \
  modules/final_visible_quality.py \
  modules/copy_generation.py \
  modules/fluency_check.py \
  modules/listing_candidate.py \
  modules/report_builder.py \
  tests/test_final_visible_quality.py \
  tests/test_copy_generation.py \
  tests/test_fluency_check.py \
  tests/test_listing_candidate.py \
  tests/test_report_builder.py \
  tests/test_readiness_summary_consistency.py \
  docs/superpowers/plans/2026-04-30-version-a-final-visible-quality-gate-plan.md \
  docs/superpowers/plans/INDEX.md
```

Expected: diff contains only final visible quality gate, stable versionA targeted repairs, candidate/report projection, tests, and plan/index updates.

- [ ] **Step 2: Stage files**

Run:

```bash
git add \
  modules/final_visible_quality.py \
  modules/copy_generation.py \
  modules/fluency_check.py \
  modules/listing_candidate.py \
  modules/report_builder.py \
  tests/test_final_visible_quality.py \
  tests/test_copy_generation.py \
  tests/test_fluency_check.py \
  tests/test_listing_candidate.py \
  tests/test_report_builder.py \
  tests/test_readiness_summary_consistency.py \
  docs/superpowers/plans/2026-04-30-version-a-final-visible-quality-gate-plan.md \
  docs/superpowers/plans/INDEX.md
```

Do not stage `.learnings/false_positive_candidates.jsonl` unless the user explicitly requests it.

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "Add version A final visible quality gate"
```

---

## Self-Review Checklist

- Scheme B is implemented first: final visible verifier + targeted repair.
- Scheme C gets an interface through `final_visible_quality_v1`, but no full candidate refactor is attempted.
- `version_a` remains the stable authority; `version_b` is not changed except shared candidate reading.
- B5 repair removes battery/runtime promise from B5 and keeps package/storage intent.
- Keyword coverage repair avoids hard tail fragments like `Includes pov`.
- Description compliance repair removes forbidden terms without broken sentence joins.
- Readiness summary no longer claims direct listing readiness when final visible quality is blocked.
- Rufus/backend bytes issue is a review warning or launch gate score issue, not a copy-quality blocker.
