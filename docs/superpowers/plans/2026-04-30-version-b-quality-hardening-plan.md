# Version B Quality Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `version_a` as the stable launch authority while making `version_b` pass a final-visible-text quality gate before it can contribute to `hybrid`.

**Architecture:** Preserve the current `version_b` R1 batch generation path for speed, then add a final-text slot gate, targeted rerender/repair, and stricter hybrid selection. The fix is scoped to `version_b`/`visible_copy_mode == r1_batch` and hybrid selection; it must not alter the `version_a` generation path.

**Tech Stack:** Python, pytest, existing modules `copy_generation.py`, `packet_rerender.py`, `slot_contracts.py`, `hybrid_composer.py`, `readiness_verdict.py`.

---

## Context And Contract

Current r47 evidence lives at:

`/Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r47_version_b_supervisor_smoke`

Observed issues:

- `version_b` B1-B5 all have `missing_keywords`.
- `version_b` B5 has `slot_contract_failed:multiple_primary_promises` and repeated root `card`.
- `version_b` scrub creates awkward final language such as `Wear comfortably extended-session`.
- `slot_rerender_plan` is empty because slot rules do not provide `repair_policy`.
- `hybrid` selects problematic B slots and can be dragged down by experimental output.
- `version_a` must remain the stable baseline and must not be rewritten by this work.

Non-goals:

- Do not rewrite the L1/L2/L3 keyword protocol.
- Do not change `version_a` prompts or main generation flow.
- Do not convert all `version_b` bullets back to independent slot generation in this branch.
- Do not rewrite the scorer.

---

## Files And Responsibilities

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
  - Rebuild/synchronize final `version_b` bullet packets after scrub/finalize.
  - Run slot rerender only after final visible text is available.
  - Add deterministic B5 fallback and scrub-repair triggers.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/packet_rerender.py`
  - Add versionB/R1-batch default repair policy when explicit `repair_policy` is missing.
  - Treat `missing_keywords`, `slot_contract_failed:*`, repeated roots, and header/body ruptures as rerender triggers for R1 batch output.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/slot_contracts.py`
  - Make B5 promise detection context-aware: package-list `lithium battery` is not runtime; `150 minutes battery life` is runtime.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
  - Prevent hard-failed B slots from replacing A slots.
  - Treat B keyword coverage regression as disqualifying when A is clean.

- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/readiness_verdict.py`
  - For review-only candidates, prefer fewer/lower-severity blockers and stable source over fixed `hybrid` preference.

- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_packet_rerender.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_slot_contracts.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_readiness_verdict.py`

---

## Task 1: Lock Current VersionB Failures As Tests

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_packet_rerender.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_slot_contracts.py`

- [ ] **Step 1: Add failing packet-rerender test for R1 batch missing keywords**

Append this test to `tests/test_packet_rerender.py`:

```python
def test_r1_batch_missing_keywords_builds_default_rerender_plan():
    from modules.packet_rerender import build_slot_rerender_plan

    generated_copy = {
        "metadata": {"visible_copy_mode": "r1_batch"},
        "bullets": [
            "Battery for Adventures -- Records for 150 minutes.",
            "Evidence Capture -- Weighs 0.1 kg.",
        ],
        "bullet_packets": [
            {"slot": "B1", "required_keywords": ["action camera"], "header": "Battery", "benefit": "Records long.", "proof": "150 minutes.", "guidance": "Use daily."},
            {"slot": "B2", "required_keywords": ["body camera"], "header": "Evidence", "benefit": "Wear it.", "proof": "0.1 kg.", "guidance": "Use at work."},
        ],
        "slot_quality_packets": [
            {"slot": "B1", "contract_pass": False, "fluency_pass": True, "unsupported_policy_pass": True, "issues": ["missing_keywords"]},
            {"slot": "B2", "contract_pass": False, "fluency_pass": True, "unsupported_policy_pass": True, "issues": ["missing_keywords"]},
        ],
    }

    plan = build_slot_rerender_plan(generated_copy, {"bullet_slot_rules": {}})

    assert [row["slot"] for row in plan] == ["B1", "B2"]
    assert all("missing_keywords" in row["rerender_reasons"] for row in plan)
```

- [ ] **Step 2: Add failing slot-contract test for package battery context**

Append this test to `tests/test_slot_contracts.py`:

```python
def test_b5_package_battery_is_not_runtime_promise():
    from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

    bullet = (
        "READY-TO-RECORD KIT -- Includes body camera, magnetic clip, back clip, "
        "USB-C cable, 32 GB microSD card, and lithium battery. "
        "Add higher-capacity storage up to 256 GB when needed."
    )

    result = validate_bullet_against_contract(bullet, build_slot_contract("B5"))

    assert result["passed"] is True
    assert "battery_runtime" not in result["detected_promises"]
```

- [ ] **Step 3: Add failing hybrid test for B keyword regression**

Append this test to `tests/test_hybrid_composer.py`:

```python
def test_hybrid_chooses_a_when_b_missing_slot_keywords_and_a_has_them():
    from modules.hybrid_composer import select_source_for_bullet_slot

    decision = select_source_for_bullet_slot(
        slot="B1",
        bullet_a="ACTION CAMERA POWER -- This action camera records for 150 minutes.",
        bullet_b="BATTERY POWER -- Records for 150 minutes.",
        meta_a={},
        risk_a={},
        meta_b={},
        risk_b={},
        slot_l2_targets=["action camera"],
        quality_a={"slot": "B1", "keyword_coverage_pass": True, "issues": []},
        quality_b={"slot": "B1", "keyword_coverage_pass": False, "issues": ["missing_keywords"]},
    )

    assert decision["source_version"] == "version_a"
    assert decision["selection_reason"] in {"version_b_quality_failed", "version_b_keyword_regression"}
```

- [ ] **Step 4: Run targeted tests and verify they fail**

Run:

```bash
./.venv/bin/pytest -q \
  tests/test_packet_rerender.py::test_r1_batch_missing_keywords_builds_default_rerender_plan \
  tests/test_slot_contracts.py::test_b5_package_battery_is_not_runtime_promise \
  tests/test_hybrid_composer.py::test_hybrid_chooses_a_when_b_missing_slot_keywords_and_a_has_them
```

Expected: FAIL before implementation.

---

## Task 2: Add R1 Batch Default Rerender Policy

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/packet_rerender.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_packet_rerender.py`

- [ ] **Step 1: Implement metadata-aware default repair policy**

In `modules/packet_rerender.py`, add helper functions near `_build_rerender_reasons`:

```python
_R1_BATCH_DEFAULT_REPAIR_POLICY = {
    "on_contract_fail": "rerender_slot",
    "on_fluency_fail": "rerender_slot",
    "on_keyword_coverage_fail": "rerender_slot",
}


def _is_r1_batch_surface(generated_copy: Dict[str, Any]) -> bool:
    metadata = generated_copy.get("metadata") or {}
    return str(metadata.get("visible_copy_mode") or "").strip() == "r1_batch"


def _resolve_repair_policy(slot_rule: Dict[str, Any], generated_copy: Dict[str, Any]) -> Dict[str, Any]:
    explicit = deepcopy(slot_rule.get("repair_policy") or {})
    if explicit:
        return explicit
    if _is_r1_batch_surface(generated_copy):
        return deepcopy(_R1_BATCH_DEFAULT_REPAIR_POLICY)
    return {}
```

- [ ] **Step 2: Extend rerender reason detection for keyword coverage**

Update `_build_rerender_reasons` so keyword coverage can trigger R1 batch rerender:

```python
def _build_rerender_reasons(slot_quality: Dict[str, Any], repair_policy: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    contract_action = str(repair_policy.get("on_contract_fail") or "").strip()
    fluency_action = str(repair_policy.get("on_fluency_fail") or "").strip()
    keyword_action = str(repair_policy.get("on_keyword_coverage_fail") or "").strip()

    if slot_quality.get("contract_pass") is False and contract_action == "rerender_slot":
        reasons.append("contract_fail")
    if slot_quality.get("fluency_pass") is False and fluency_action == "rerender_slot":
        reasons.append("fluency_fail")
    if slot_quality.get("keyword_coverage_pass") is False and keyword_action == "rerender_slot":
        reasons.append("keyword_coverage_fail")
    if slot_quality.get("unsupported_policy_pass") is False and "contract_fail" not in reasons and contract_action == "rerender_slot":
        reasons.append("unsupported_policy_fail")

    if not reasons:
        return []

    for issue in slot_quality.get("issues") or []:
        normalized = str(issue or "").strip()
        if normalized.startswith("slot_contract_failed:") and "slot_contract_failed" not in reasons:
            reasons.append("slot_contract_failed")
        if normalized in _REPAIRABLE_ISSUES and normalized not in reasons:
            reasons.append(normalized)
    return reasons
```

- [ ] **Step 3: Use resolved policy in `build_slot_rerender_plan`**

Replace:

```python
repair_policy = deepcopy(slot_rule.get("repair_policy") or {})
```

with:

```python
repair_policy = _resolve_repair_policy(slot_rule, generated_copy)
```

- [ ] **Step 4: Run packet rerender test**

Run:

```bash
./.venv/bin/pytest -q tests/test_packet_rerender.py::test_r1_batch_missing_keywords_builds_default_rerender_plan
```

Expected: PASS.

---

## Task 3: Rebuild VersionB Packets From Final Visible Bullets

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`

- [ ] **Step 1: Add packet synchronization helper**

In `modules/copy_generation.py`, near `_build_bullet_packet`, add:

```python
def _sync_bullet_packets_to_final_bullets(
    bullets: Sequence[str],
    bullet_packets: Sequence[Dict[str, Any]],
    bullet_trace: Sequence[Dict[str, Any]],
    slot_rule_contracts: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    synced: List[Dict[str, Any]] = []
    for idx, bullet in enumerate(bullets or []):
        slot = f"B{idx + 1}"
        previous = next(
            (
                packet for packet in bullet_packets or []
                if str((packet or {}).get("slot") or "").strip().upper() == slot
            ),
            {},
        )
        trace_entry = bullet_trace[idx] if idx < len(bullet_trace or []) and isinstance(bullet_trace[idx], dict) else {}
        rebuilt = _build_bullet_packet(
            slot,
            str(bullet or ""),
            trace_entry=trace_entry,
            slot_rule_contract=slot_rule_contracts.get(slot) or {},
        )
        rebuilt["required_keywords"] = list(previous.get("required_keywords") or rebuilt.get("required_keywords") or [])
        rebuilt["required_facts"] = list(previous.get("required_facts") or rebuilt.get("required_facts") or [])
        rebuilt["capability_mapping"] = list(previous.get("capability_mapping") or rebuilt.get("capability_mapping") or [])
        rebuilt["scene_mapping"] = list(previous.get("scene_mapping") or rebuilt.get("scene_mapping") or [])
        rebuilt["unsupported_capability_policy"] = deepcopy(
            previous.get("unsupported_capability_policy")
            or rebuilt.get("unsupported_capability_policy")
            or (slot_rule_contracts.get(slot) or {}).get("unsupported_capability_policy")
            or {}
        )
        synced.append(_normalize_bullet_packet(rebuilt))
    return synced
```

- [ ] **Step 2: Add unit test for packet synchronization**

Append to `tests/test_copy_generation.py`:

```python
def test_sync_bullet_packets_to_final_bullets_preserves_required_keywords():
    import modules.copy_generation as cg

    bullets = ["ACTION CAMERA POWER -- This action camera records for 150 minutes."]
    packets = [{"slot": "B1", "required_keywords": ["action camera"], "header": "Old", "benefit": "Old text."}]

    synced = cg._sync_bullet_packets_to_final_bullets(bullets, packets, [{"slot": "B1"}], {})

    assert synced[0]["slot"] == "B1"
    assert synced[0]["required_keywords"] == ["action camera"]
    assert synced[0]["header"] == "ACTION CAMERA POWER"
    assert "action camera" in (synced[0]["benefit"] + " " + synced[0].get("proof", "")).lower()
```

- [ ] **Step 3: Run the sync test and verify it passes**

Run:

```bash
./.venv/bin/pytest -q tests/test_copy_generation.py::test_sync_bullet_packets_to_final_bullets_preserves_required_keywords
```

Expected: PASS.

- [ ] **Step 4: Call sync helper after final bullet scrub/finalize**

In `modules/copy_generation.py`, after the loop that finalizes bullets and before slot quality packets are built, insert:

```python
    slot_rule_contracts = writing_policy.get("bullet_slot_rules") or {}
    if pure_r1_visible_batch and bullet_packets:
        bullet_packets = _sync_bullet_packets_to_final_bullets(
            bullets,
            bullet_packets,
            bullet_trace,
            slot_rule_contracts,
        )
```

Place it before the existing `slot_rule_contracts = writing_policy.get("bullet_slot_rules") or {}` block if needed, avoiding duplicate assignment.

- [ ] **Step 5: Run copy generation tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_copy_generation.py
```

Expected: PASS.

---

## Task 4: Make B5 Contract Context-Aware

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/slot_contracts.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_slot_contracts.py`

- [ ] **Step 1: Add runtime-specific battery patterns**

In `modules/slot_contracts.py`, add helper functions near `_detect_promises`:

```python
_BATTERY_RUNTIME_CONTEXT_RE = re.compile(
    r"\b(?:battery\s+life|runtime|continuous\s+recording|per\s+charge|single\s+charge|"
    r"\d+\s*(?:minutes?|mins?|hours?|hrs?)\b)",
    re.IGNORECASE,
)

_PACKAGE_BATTERY_CONTEXT_RE = re.compile(
    r"\b(?:includes?|included|comes\s+with|inside(?:\s+you'?ll\s+find)?|package|box)\b"
    r".{0,120}\b(?:lithium\s+)?battery\b",
    re.IGNORECASE,
)


def _detect_battery_runtime(text: str) -> bool:
    if not re.search(r"\bbattery\b|\bcharge\b|\bruntime\b|\bminutes?\b|\bhours?\b", text, re.IGNORECASE):
        return False
    if _PACKAGE_BATTERY_CONTEXT_RE.search(text) and not _BATTERY_RUNTIME_CONTEXT_RE.search(text):
        return False
    return bool(_BATTERY_RUNTIME_CONTEXT_RE.search(text))
```

- [ ] **Step 2: Update `_detect_promises` to use context-aware battery detection**

Change `_detect_promises` to skip generic battery pattern and call `_detect_battery_runtime`:

```python
def _detect_promises(text: str) -> list[str]:
    hits: list[str] = []
    for promise, patterns in _PROMISE_PATTERNS.items():
        if promise == "battery_runtime":
            if _detect_battery_runtime(text):
                hits.append(promise)
            continue
        if any(re.search(pattern, text) for pattern in patterns):
            hits.append(promise)
    return hits
```

- [ ] **Step 3: Add negative runtime test**

Append to `tests/test_slot_contracts.py`:

```python
def test_b5_explicit_runtime_still_fails_as_second_promise():
    from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract

    bullet = (
        "READY-TO-RECORD KIT -- Includes the camera and clip. "
        "Long battery life provides up to 150 minutes of continuous recording."
    )

    result = validate_bullet_against_contract(bullet, build_slot_contract("B5"))

    assert "battery_runtime" in result["detected_promises"]
    assert "multiple_primary_promises" in result["reasons"]
```

- [ ] **Step 4: Run slot contract tests**

Run:

```bash
./.venv/bin/pytest -q \
  tests/test_slot_contracts.py::test_b5_package_battery_is_not_runtime_promise \
  tests/test_slot_contracts.py::test_b5_explicit_runtime_still_fails_as_second_promise
```

Expected: PASS.

---

## Task 5: Add Deterministic B5 Fallback Repair

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_packet_rerender.py`

- [ ] **Step 1: Tighten local B5 fallback wording**

In `_build_local_slot_rerender_fallback`, replace the B5 fallback block with wording that has one primary promise and no repeated `card` root:

```python
    if slot == "B5" and (
        "slot_contract_failed" in rerender_reasons
        or "repeated_word_root" in rerender_reasons
        or any(str(issue or "").startswith("slot_contract_failed:") for issue in (slot_quality.get("issues") or []))
    ):
        required_keywords = list(packet.get("required_keywords") or [])
        lead_keyword = str(required_keywords[0] or "body camera").strip() if required_keywords else "body camera"
        header = "READY-TO-RECORD KIT"
        benefit = (
            f"Start with the included {lead_keyword}, magnetic clip, back clip, "
            "USB-C cable, and 32 GB microSD card."
        )
        proof = "Add higher-capacity storage up to 256 GB when needed."
        rebuilt_packet = _build_bullet_packet(
            slot,
            f"{header} -- {benefit} {proof}",
            trace_entry={
                "slot": slot,
                "keywords": required_keywords,
                "capability_mapping": list(packet.get("capability_mapping") or []),
                "scene_mapping": list(packet.get("scene_mapping") or []),
            },
            slot_rule_contract=slot_rule_contract,
        )
```

Keep the existing code after `rebuilt_packet` that restores required fields and builds `quality`.

- [ ] **Step 2: Add deterministic repair test**

Append to `tests/test_packet_rerender.py`:

```python
def test_execute_rerender_uses_clean_b5_local_fallback(monkeypatch):
    import modules.copy_generation as cg

    class FailingClient:
        def generate_text(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(cg, "get_llm_client", lambda: FailingClient())

    result = cg._rerender_slot_from_packet_plan(
        {
            "slot": "B5",
            "source_packet": {
                "slot": "B5",
                "required_keywords": ["body camera"],
                "header": "Everything You Need",
                "benefit": "Includes body camera and card.",
                "proof": "Supports 256 GB card.",
                "guidance": "Card not included.",
            },
            "slot_quality": {
                "issues": ["slot_contract_failed:multiple_primary_promises", "repeated_word_root"],
                "rerender_count": 0,
            },
            "rerender_reasons": ["slot_contract_failed", "repeated_word_root"],
        },
        {"bullet_slot_rules": {}, "copy_contracts": {}},
        "English",
    )

    assert result["status"] == "applied_local_fallback"
    assert result["bullet"].lower().count("card") <= 1
    assert "150 minutes" not in result["bullet"].lower()
    assert "long battery" not in result["bullet"].lower()
```

- [ ] **Step 3: Run B5 repair test**

Run:

```bash
./.venv/bin/pytest -q tests/test_packet_rerender.py::test_execute_rerender_uses_clean_b5_local_fallback
```

Expected: PASS.

---

## Task 6: Treat Scrub-Induced Awkward Text As VersionB Repair Trigger

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`

- [ ] **Step 1: Add awkward phrase detector**

In `modules/copy_generation.py`, near fluency helpers, add:

```python
_AWKWARD_SCRUB_PHRASES = (
    "comfortably extended-session",
    "suitable for smooth",
    "for suitable clarity",
)


def _has_scrub_induced_awkwardness(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(phrase in lowered for phrase in _AWKWARD_SCRUB_PHRASES)
```

- [ ] **Step 2: Add awkwardness to slot quality packet**

In `_build_slot_quality_packet`, after issue mapping and before `fluency_pass`, append:

```python
    if _has_scrub_induced_awkwardness(assembled_text):
        if "scrub_induced_awkwardness" not in issues:
            issues.append("scrub_induced_awkwardness")
```

Then include it in the `fluency_pass` failing set:

```python
            "scrub_induced_awkwardness",
```

- [ ] **Step 3: Make packet rerender recognize this issue**

In `modules/packet_rerender.py`, add to `_REPAIRABLE_ISSUES`:

```python
"scrub_induced_awkwardness",
```

- [ ] **Step 4: Add copy generation unit test**

Append to `tests/test_copy_generation.py`:

```python
def test_slot_quality_flags_scrub_induced_awkwardness():
    import modules.copy_generation as cg

    quality = cg._build_slot_quality_packet(
        {
            "slot": "B2",
            "header": "EVIDENCE CAPTURE",
            "benefit": "Wear comfortably extended-session and record details.",
            "proof": "Weighs 0.1 kg.",
            "guidance": "Use it during routine work.",
            "required_keywords": [],
        },
        copy_contracts={},
        slot_rule_contract={},
        target_language="English",
    )

    assert "scrub_induced_awkwardness" in quality["issues"]
    assert quality["fluency_pass"] is False
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
./.venv/bin/pytest -q \
  tests/test_copy_generation.py::test_slot_quality_flags_scrub_induced_awkwardness \
  tests/test_packet_rerender.py::test_r1_batch_missing_keywords_builds_default_rerender_plan
```

Expected: PASS.

---

## Task 7: Harden Hybrid Selection Against VersionB Quality Regressions

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`

- [ ] **Step 1: Treat keyword coverage regression as unhealthy when A is clean**

In `modules/hybrid_composer.py`, add helper near `_slot_quality_is_unhealthy`:

```python
def _slot_keyword_coverage_failed(slot_quality: Optional[Dict[str, Any]]) -> bool:
    return isinstance(slot_quality, dict) and slot_quality.get("keyword_coverage_pass") is False
```

- [ ] **Step 2: Update selection logic before L2 soft signals**

In `select_source_for_bullet_slot`, after `a_quality_failed` / `b_quality_failed` handling and before `a_has_l2`, add:

```python
    b_keyword_failed = _slot_keyword_coverage_failed(quality_b)
    a_keyword_failed = _slot_keyword_coverage_failed(quality_a)
    if b_keyword_failed and not a_keyword_failed:
        soft_signals.append("version_b_keyword_regression")
        return {
            "source_version": "version_a",
            "selection_reason": "version_b_keyword_regression",
            "disqualified": disqualified,
            "soft_signals": soft_signals,
        }
```

- [ ] **Step 3: Run hybrid regression test**

Run:

```bash
./.venv/bin/pytest -q tests/test_hybrid_composer.py::test_hybrid_chooses_a_when_b_missing_slot_keywords_and_a_has_them
```

Expected: PASS.

- [ ] **Step 4: Add hard B5 blocker test**

Append to `tests/test_hybrid_composer.py`:

```python
def test_hybrid_rejects_b_slot_contract_failure_when_a_is_clean():
    from modules.hybrid_composer import select_source_for_bullet_slot

    decision = select_source_for_bullet_slot(
        slot="B5",
        bullet_a="READY KIT -- Includes camera, clip, USB-C cable, and 32 GB microSD card.",
        bullet_b="READY KIT -- Includes card, supports card, card not included.",
        meta_a={},
        risk_a={},
        meta_b={},
        risk_b={},
        slot_l2_targets=[],
        quality_a={"slot": "B5", "fluency_pass": True, "unsupported_policy_pass": True, "issues": []},
        quality_b={"slot": "B5", "fluency_pass": True, "unsupported_policy_pass": True, "issues": ["slot_contract_failed:multiple_primary_promises"]},
    )

    assert decision["source_version"] == "version_a"
    assert decision["selection_reason"] == "version_b_quality_failed"
```

- [ ] **Step 5: Run hybrid composer tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_hybrid_composer.py
```

Expected: PASS.

---

## Task 8: Prefer Safer Stable Candidate In Review-Only Verdicts

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/readiness_verdict.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_readiness_verdict.py`

- [ ] **Step 1: Add blocker severity ranking**

In `modules/readiness_verdict.py`, add helpers below `_dedupe_blockers`:

```python
_SOURCE_REVIEW_TIEBREAK = {"stable": 0, "hybrid": 1, "experimental": 2, "unknown": 3}


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
```

- [ ] **Step 2: Sort review-only candidates by risk**

In `build_readiness_verdict`, replace:

```python
review_only = [row for row in rankings if row["eligibility"] == "review_only"]
```

with:

```python
review_only = sorted(
    [row for row in rankings if row["eligibility"] == "review_only"],
    key=_review_rank_key,
)
```

- [ ] **Step 3: Add readiness verdict test**

Append to `tests/test_readiness_verdict.py`:

```python
def test_review_only_prefers_stable_candidate_with_fewer_blockers():
    from modules.readiness_verdict import build_readiness_verdict

    verdict = build_readiness_verdict(
        candidates={
            "hybrid": {
                "source_type": "hybrid",
                "paste_ready_status": "blocked",
                "reviewable_status": "reviewable",
                "paste_ready_blockers": [
                    "slot_contract_failed:B5:multiple_primary_promises",
                    "risk_listing_not_ready",
                    "Repeated word root more than twice: card",
                ],
                "keyword_reconciliation": {"status": "complete"},
                "source_trace": {"bullets": []},
            },
            "version_a": {
                "source_type": "stable",
                "paste_ready_status": "blocked",
                "reviewable_status": "reviewable",
                "paste_ready_blockers": ["slot_contract_failed:B5:multiple_primary_promises"],
                "keyword_reconciliation": {"status": "complete"},
            },
        },
        run_state="success",
    )

    assert verdict["recommended_output"] == "version_a"
    assert verdict["operational_listing_status"] == "REVIEW_REQUIRED"
```

- [ ] **Step 4: Run readiness verdict tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_readiness_verdict.py
```

Expected: PASS.

---

## Task 9: Verify VersionA Path Is Not Mutated

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_packet_rerender.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`

- [ ] **Step 1: Add non-R1 no-default-rerender test**

Append to `tests/test_packet_rerender.py`:

```python
def test_non_r1_surface_does_not_get_default_rerender_policy():
    from modules.packet_rerender import build_slot_rerender_plan

    generated_copy = {
        "metadata": {"visible_copy_mode": "standard"},
        "bullets": ["Battery -- Records long."],
        "bullet_packets": [{"slot": "B1", "required_keywords": ["action camera"]}],
        "slot_quality_packets": [
            {"slot": "B1", "contract_pass": False, "keyword_coverage_pass": False, "issues": ["missing_keywords"]},
        ],
    }

    assert build_slot_rerender_plan(generated_copy, {"bullet_slot_rules": {}}) == []
```

- [ ] **Step 2: Run non-R1 test**

Run:

```bash
./.venv/bin/pytest -q tests/test_packet_rerender.py::test_non_r1_surface_does_not_get_default_rerender_policy
```

Expected: PASS.

---

## Task 10: Run Targeted Test Suite

**Files:**
- No source changes.

- [ ] **Step 1: Run versionB hardening tests**

Run:

```bash
./.venv/bin/pytest -q \
  tests/test_packet_rerender.py \
  tests/test_copy_generation.py \
  tests/test_slot_contracts.py \
  tests/test_hybrid_composer.py \
  tests/test_readiness_verdict.py
```

Expected: PASS.

- [ ] **Step 2: If a test fails, stop and classify**

Use this classification:

```text
Implementation bug: fix in the touched module.
Test expectation wrong: update only if current behavior is intentionally correct and explain why.
VersionA affected: stop and inspect before continuing.
```

---

## Task 11: Run Full Test Suite

**Files:**
- No source changes.

- [ ] **Step 1: Run all tests**

Run:

```bash
./.venv/bin/pytest -q
```

Expected: all tests pass. Current recent main baseline was `468 passed`; do not accept regressions without explicit review.

---

## Task 12: Run H91 Live Validation

**Files:**
- No source changes.
- Artifacts written under `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/`.

- [ ] **Step 1: Run fresh dual-version live**

Run:

```bash
./.venv/bin/python run_pipeline.py \
  --product H91lite \
  --market US \
  --run-id r48_version_b_quality_hardening \
  --dual-version \
  --fresh
```

Expected: pipeline completes with `version_a` success; `version_b` may be success or review-only, but must not block A.

- [ ] **Step 2: Inspect critical artifacts**

Run:

```bash
RUN=/Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r48_version_b_quality_hardening
jq '{listing_status,grade,total_score,a10_score,blocking_reasons}' "$RUN/version_a/scoring_results.json"
jq '{listing_status,grade,total_score,a10_score,blocking_reasons}' "$RUN/version_b/scoring_results.json"
jq '[.slot_quality_packets[] | {slot, keyword_coverage_pass, contract_pass, fluency_pass, issues}]' "$RUN/version_b/generated_copy.json"
jq '{recommended_output,listing_status,operational_listing_status,launch_gate,candidate_rankings}' "$RUN/final_readiness_verdict.json"
```

Expected acceptance:

```text
version_a remains successful and operationally stable.
version_b no longer ships with B1-B5 all missing_keywords.
version_b B5 has no repeated card blocker.
version_b B5 package lithium battery is not treated as runtime by itself.
hybrid does not select hard-failed B slots when A is cleaner.
final verdict does not recommend a B-contaminated hybrid over a cleaner version_a in review-only mode.
```

---

## Task 13: Commit The Branch

**Files:**
- Stage only files touched by this plan.

- [ ] **Step 1: Review diff**

Run:

```bash
git diff -- modules/copy_generation.py modules/packet_rerender.py modules/slot_contracts.py modules/hybrid_composer.py modules/readiness_verdict.py tests/test_packet_rerender.py tests/test_copy_generation.py tests/test_slot_contracts.py tests/test_hybrid_composer.py tests/test_readiness_verdict.py docs/superpowers/plans/2026-04-30-version-b-quality-hardening-plan.md docs/superpowers/plans/INDEX.md
```

Expected: diff contains only versionB hardening, hybrid safety, tests, and plan/index updates.

- [ ] **Step 2: Stage files**

Run:

```bash
git add \
  modules/copy_generation.py \
  modules/packet_rerender.py \
  modules/slot_contracts.py \
  modules/hybrid_composer.py \
  modules/readiness_verdict.py \
  tests/test_packet_rerender.py \
  tests/test_copy_generation.py \
  tests/test_slot_contracts.py \
  tests/test_hybrid_composer.py \
  tests/test_readiness_verdict.py \
  docs/superpowers/plans/2026-04-30-version-b-quality-hardening-plan.md \
  docs/superpowers/plans/INDEX.md
```

- [ ] **Step 3: Commit**

Run:

```bash
git commit -m "Harden version B quality gates"
```

---

## Self-Review Checklist

- [ ] Every change is scoped to `version_b`/R1 batch or hybrid/readiness selection.
- [ ] `version_a` generation path is not changed.
- [ ] `missing_keywords` triggers versionB repair but not global versionA repair.
- [ ] B5 package battery is separated from runtime claim.
- [ ] Hybrid never prefers a hard-failed B slot over a clean A slot.
- [ ] Review-only verdict does not blindly prefer hybrid over a cleaner stable candidate.
- [ ] Targeted tests pass.
- [ ] Full tests pass.
- [ ] Live H91 run confirms A remains operationally stable.
