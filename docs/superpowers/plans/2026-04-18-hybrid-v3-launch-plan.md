# Hybrid v3 Launch Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `hybrid/` a launchable output by preserving Version A's SEO strength while recovering Version B's bullet naturalness through slot-level selection, deterministic L2 keyword backfill, and a hard launch gate.

**Architecture:** Keep `version_a` and `version_b` generation untouched. Extend the existing post-generation hybrid path so it first picks each bullet slot independently, then runs a hybrid-only deterministic bullet optimizer to restore missing L2 coverage, then re-audits the resulting listing and decides whether hybrid is launch-recommended or must fall back to `version_a`.

**Tech Stack:** Python, existing `modules/hybrid_composer.py`, risk/scoring/report pipeline, pytest, JSON artifact readers/writers.

---

## File Map

- Modify: `modules/hybrid_composer.py`
- Create: `modules/hybrid_optimizer.py`
- Modify: `modules/report_generator.py`
- Modify: `run_pipeline.py`
- Create: `tests/test_hybrid_optimizer.py`
- Extend: `tests/test_hybrid_composer.py`
- Modify: `.learnings/LEARNINGS.md`
- Create/Update outputs under: `output/runs/<sku>_<market>_<run_id>/hybrid/`

## Scope Guardrails

- Do not modify `version_a/generated_copy.json`
- Do not modify `version_b/generated_copy.json`
- Do not change V3 or R1 copy generation prompts in this phase
- Do not add any new LLM calls in hybrid optimization
- Do not allow hybrid to become launch-recommended unless it passes the explicit launch gate
- Hybrid remains a third output, never an in-place mutation of A/B

## Success Criteria

- `hybrid/risk_report.json` reports `READY_FOR_LISTING`
- `hybrid/scoring_results.json` reaches at least `A10 >= 80`, `COSMO >= 90`, `Rufus >= 90`, `Fluency >= 24`
- `hybrid/source_trace.json` records slot-level bullet provenance and selection reason
- `hybrid/generated_copy.json` records deterministic repair actions applied after composition
- If the gate fails, hybrid remains available for inspection but launch recommendation falls back to `version_a`

---

## Task Package A: Add Bullet Slot-Level Selection

**Files:**
- Modify: `modules/hybrid_composer.py`
- Test: `tests/test_hybrid_composer.py`

- [ ] **Step 1: Write the failing slot-level selection tests**

```python
def test_select_source_for_bullet_slot_prefers_b_when_both_eligible():
    decision = select_source_for_bullet_slot(
        slot="B3",
        bullet_a="A bullet",
        bullet_b="B bullet",
        meta_a={"visible_llm_fallback_fields": []},
        risk_a={"blocking_fields": []},
        meta_b={"visible_llm_fallback_fields": []},
        risk_b={"blocking_fields": []},
        slot_metrics_a={"l2_hit": False, "audience_quality": 0.5},
        slot_metrics_b={"l2_hit": True, "audience_quality": 0.8},
    )
    assert decision["source_version"] == "version_b"
    assert decision["selection_reason"] == "slot_default_preference"


def test_select_source_for_bullet_slot_falls_back_to_a_when_b_is_risk_blocked():
    decision = select_source_for_bullet_slot(
        slot="B2",
        bullet_a="A bullet",
        bullet_b="B bullet",
        meta_a={"visible_llm_fallback_fields": []},
        risk_a={"blocking_fields": []},
        meta_b={"visible_llm_fallback_fields": []},
        risk_b={"blocking_fields": ["bullet_b2"]},
        slot_metrics_a={"l2_hit": True},
        slot_metrics_b={"l2_hit": True},
    )
    assert decision["source_version"] == "version_a"
    assert decision["selection_reason"] == "version_b_risk_blocked"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -k bullet_slot -v`
Expected: FAIL because `select_source_for_bullet_slot` does not exist yet.

- [ ] **Step 3: Implement slot-level selection in `modules/hybrid_composer.py`**

```python
def select_source_for_bullet_slot(...):
    # 1. Hard exclude fallback-marked / risk-blocked slot sources
    # 2. Prefer the slot with an L2 hit if only one source preserves it
    # 3. Otherwise prefer version_b for bullet naturalness
    return {
        "source_version": chosen,
        "selection_reason": reason,
        "disqualified": disqualified,
    }
```

- [ ] **Step 4: Re-run the slot tests and verify they pass**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -k bullet_slot -v`
Expected: PASS.

- [ ] **Step 5: Integrate slot-level bullet selection into hybrid composition**

```python
bullet_decisions = []
for idx in range(5):
    slot = f"B{idx + 1}"
    decision = select_source_for_bullet_slot(...)
    bullet_decisions.append(decision)
    chosen_payload = version_a if decision["source_version"] == "version_a" else version_b
    selected_bullets.append(chosen_payload["bullets"][idx])
```

- [ ] **Step 6: Run the focused hybrid composer suite**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add modules/hybrid_composer.py tests/test_hybrid_composer.py
git commit -m "feat: add slot-level hybrid bullet selection"
```

---

## Task Package B: Build Deterministic Hybrid Bullet Optimizer

**Files:**
- Create: `modules/hybrid_optimizer.py`
- Create: `tests/test_hybrid_optimizer.py`

- [ ] **Step 1: Write the failing tests for missing-L2 detection and deterministic repair**

```python
def test_collect_missing_l2_keywords_returns_uncovered_keywords():
    bullets = [
        "Capture hands-free commuting footage.",
        "Wear it discreetly for shift recording.",
        "Clip it to your helmet for cycling.",
        "Use stable mounts for smoother results.",
        "Includes cable and storage support.",
    ]
    assigned_l2 = ["travel camera", "body camera", "helmet camera"]
    missing = collect_missing_l2_keywords(bullets, assigned_l2)
    assert "travel camera" in missing


def test_repair_hybrid_bullets_for_l2_injects_keyword_without_rewriting_whole_bullet():
    bullets = [
        "Thumb-Sized POV Companion — Clip this mini camera to your helmet or bike for hands-free recording.",
        "Reliable Evidence Capture — Designed for security and service professionals.",
        "Extended Runtime — Capture more with a 150-minute battery.",
        "Recording Guidance — Use stable mounts for smoother footage.",
        "Complete Kit — Includes cable and storage support.",
    ]
    repaired, actions = repair_hybrid_bullets_for_l2(
        bullets,
        missing_keywords=["travel camera"],
        max_repairs=1,
    )
    assert "travel camera" in repaired[0].lower() or "travel camera" in repaired[1].lower()
    assert actions[0]["action"] == "l2_backfill"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `./.venv/bin/pytest tests/test_hybrid_optimizer.py -v`
Expected: FAIL because the optimizer module does not exist yet.

- [ ] **Step 3: Implement deterministic missing-L2 analysis**

```python
def collect_missing_l2_keywords(bullets, assigned_l2):
    visible = " ".join(bullets).lower()
    return [kw for kw in assigned_l2 if kw.lower() not in visible]
```

- [ ] **Step 4: Implement deterministic, bounded repair**

```python
def repair_hybrid_bullets_for_l2(bullets, missing_keywords, max_repairs=2):
    repaired = list(bullets)
    actions = []
    for keyword in missing_keywords[:max_repairs]:
        for idx, bullet in enumerate(repaired):
            candidate = _append_keyword_phrase(bullet, keyword)
            if _is_repair_safe(candidate):
                repaired[idx] = candidate
                actions.append({"action": "l2_backfill", "slot": f"B{idx+1}", "keyword": keyword})
                break
    return repaired, actions
```

- [ ] **Step 5: Add guardrail tests for byte length and connector overuse**

```python
def test_repair_hybrid_bullets_skips_unsafe_candidate():
    bullets = ["A" * 240, "short", "short", "short", "short"]
    repaired, actions = repair_hybrid_bullets_for_l2(bullets, ["travel camera"], max_repairs=1)
    assert repaired[0] == bullets[0]
    assert actions == []
```

- [ ] **Step 6: Run the optimizer suite and verify it passes**

Run: `./.venv/bin/pytest tests/test_hybrid_optimizer.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add modules/hybrid_optimizer.py tests/test_hybrid_optimizer.py
git commit -m "feat: add deterministic hybrid bullet optimizer"
```

---

## Task Package C: Wire Optimization Into Hybrid Finalization

**Files:**
- Modify: `modules/hybrid_composer.py`
- Modify: `run_pipeline.py`
- Test: `tests/test_hybrid_composer.py`
- Test: `tests/test_hybrid_optimizer.py`

- [ ] **Step 1: Write the failing integration test for optimizer-aware hybrid output**

```python
def test_finalize_hybrid_outputs_records_repair_trace_when_l2_is_missing(tmp_path):
    hybrid_copy = {
        "title": "A title",
        "bullets": [
            "Thumb-Sized POV Companion — Clip this mini camera to your helmet or bike for hands-free recording.",
            "Reliable Evidence Capture — Designed for security and service professionals.",
            "Extended Runtime — Capture more with a 150-minute battery.",
            "Recording Guidance — Use stable mounts for smoother footage.",
            "Complete Kit — Includes cable and storage support.",
        ],
        "metadata": {"hybrid_sources": {"title": "version_a", "bullets": "mixed"}},
        "decision_trace": {"keyword_assignments": []},
    }
    result = finalize_hybrid_outputs(...)
    saved = json.loads((tmp_path / "hybrid" / "generated_copy.json").read_text())
    assert saved["metadata"]["hybrid_repairs"][0]["action"] == "l2_backfill"
```

- [ ] **Step 2: Run the integration test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -k repair_trace -v`
Expected: FAIL because finalization does not call the optimizer yet.

- [ ] **Step 3: Call the optimizer before risk/scoring in `finalize_hybrid_outputs(...)`**

```python
missing_l2 = collect_missing_l2_keywords(hybrid_copy.get("bullets") or [], assigned_l2_keywords)
repaired_bullets, repair_actions = repair_hybrid_bullets_for_l2(
    hybrid_copy.get("bullets") or [],
    missing_keywords=missing_l2,
    max_repairs=2,
)
if repair_actions:
    hybrid_copy["bullets"] = repaired_bullets
    metadata = hybrid_copy.setdefault("metadata", {})
    metadata["hybrid_repairs"] = repair_actions
```

- [ ] **Step 4: Persist repair trace to the hybrid artifact set**

```python
(output_dir / "generated_copy.json").write_text(...)
(output_dir / "source_trace.json").write_text(...)
```

Ensure `generated_copy.json` now exposes `metadata.hybrid_repairs` for auditability.

- [ ] **Step 5: Run focused regression suites**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_hybrid_optimizer.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/hybrid_composer.py modules/hybrid_optimizer.py run_pipeline.py tests/test_hybrid_composer.py tests/test_hybrid_optimizer.py
git commit -m "feat: optimize hybrid bullets for L2 coverage"
```

---

## Task Package D: Add Hybrid Launch Gate

**Files:**
- Modify: `modules/hybrid_composer.py`
- Modify: `modules/report_generator.py`
- Test: `tests/test_hybrid_composer.py`

- [ ] **Step 1: Write the failing tests for launch decision logic**

```python
def test_hybrid_launch_gate_recommends_hybrid_when_scores_meet_thresholds():
    decision = build_hybrid_launch_decision(
        risk_report={"listing_status": {"status": "READY_FOR_LISTING"}},
        scoring_results={
            "dimensions": {
                "traffic": {"score": 85},
                "conversion": {"score": 92},
                "answerability": {"score": 95},
                "readability": {"score": 30},
            }
        },
        hybrid_copy={"_no_eligible_source": []},
    )
    assert decision["recommended_output"] == "hybrid"


def test_hybrid_launch_gate_falls_back_to_version_a_when_thresholds_fail():
    decision = build_hybrid_launch_decision(
        risk_report={"listing_status": {"status": "READY_FOR_LISTING"}},
        scoring_results={
            "dimensions": {
                "traffic": {"score": 70},
                "conversion": {"score": 80},
                "answerability": {"score": 100},
                "readability": {"score": 30},
            }
        },
        hybrid_copy={"_no_eligible_source": []},
    )
    assert decision["recommended_output"] == "version_a"
    assert "A10 below threshold" in decision["reasons"]
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -k launch_gate -v`
Expected: FAIL because `build_hybrid_launch_decision` does not exist yet.

- [ ] **Step 3: Implement the launch gate**

```python
def build_hybrid_launch_decision(risk_report, scoring_results, hybrid_copy):
    reasons = []
    if (risk_report.get("listing_status") or {}).get("status") != "READY_FOR_LISTING":
        reasons.append("listing not ready")
    if scoring_results["dimensions"]["traffic"]["score"] < 80:
        reasons.append("A10 below threshold")
    if scoring_results["dimensions"]["conversion"]["score"] < 90:
        reasons.append("COSMO below threshold")
    if scoring_results["dimensions"]["answerability"]["score"] < 90:
        reasons.append("Rufus below threshold")
    if scoring_results["dimensions"]["readability"]["score"] < 24:
        reasons.append("Fluency below threshold")
    return {
        "recommended_output": "hybrid" if not reasons else "version_a",
        "reasons": reasons,
    }
```

- [ ] **Step 4: Persist launch decision into hybrid metadata and reports**

```python
hybrid_copy.setdefault("metadata", {})["launch_decision"] = build_hybrid_launch_decision(...)
```

Add a short `Hybrid Launch Decision` appendix to `listing_report.md` showing the recommendation and blocking reasons.

- [ ] **Step 5: Run the focused suites and verify they pass**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_hybrid_optimizer.py tests/test_report_generator.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/hybrid_composer.py modules/report_generator.py tests/test_hybrid_composer.py
git commit -m "feat: add hybrid launch gate"
```

---

## Task Package E: End-to-End Validation

**Files:**
- Modify: `.learnings/LEARNINGS.md`

- [ ] **Step 1: Run the hybrid-focused regression suite**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_hybrid_optimizer.py tests/test_blueprint_generator.py tests/test_copy_generation.py tests/test_title_naturalness.py tests/test_length_rules.py -q`
Expected: PASS.

- [ ] **Step 2: Run a real dual-version pipeline validation**

Run: `OPENAI_COMPAT_VERIFY_SSL=0 .venv/bin/python run_pipeline.py --product H91lite --market US --run-id r20_hybrid_v3 --fresh --dual-version`
Expected: `version_a`, `version_b`, and `hybrid` directories all generated successfully.

- [ ] **Step 3: Inspect hybrid launch metrics**

Run:

```bash
python3 - <<'PY'
import json, pathlib
base = pathlib.Path('output/runs/H91lite_US_r20_hybrid_v3/hybrid')
copy = json.loads((base/'generated_copy.json').read_text())
risk = json.loads((base/'risk_report.json').read_text())
score = json.loads((base/'scoring_results.json').read_text())
print(copy['metadata'].get('launch_decision'))
print((risk.get('listing_status') or {}).get('status'))
print(score['dimensions']['traffic']['score'])
print(score['dimensions']['conversion']['score'])
print(score['dimensions']['answerability']['score'])
print(score['dimensions']['readability']['score'])
PY
```

Expected: Either hybrid meets all thresholds and is recommended, or the launch decision explicitly falls back to `version_a` with readable reasons.

- [ ] **Step 4: Record learnings**

Capture:
- which bullet slots most often prefer `version_a` vs `version_b`
- whether deterministic L2 repair improved A10 without reintroducing fluency issues
- whether the launch gate selected `hybrid` or `version_a`

- [ ] **Step 5: Commit**

```bash
git add .learnings/LEARNINGS.md
git commit -m "docs: record hybrid v3 validation learnings"
```
