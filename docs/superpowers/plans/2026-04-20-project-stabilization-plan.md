# Project Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the current production baseline, close the hybrid launch blockers, and restore a trustworthy single source of truth for readiness, tests, and project status.

**Architecture:** Keep the existing Step 0-9 pipeline and dual-version architecture intact. Prioritize failure-handling hardening, readiness-state unification, hybrid launch-gate regression protection, and repository governance cleanup before starting any new feature wave.

**Tech Stack:** Python 3, pytest, Streamlit, JSON run artifacts, Markdown project docs

---

## Today Delivery Track

**Today Goal:** ship one trustworthy launch-ready listing document today, even if the final recommendation falls back to `version_a`.

**Today Done Definition:**
- `.venv/bin/pytest -q` returns `0 failed`
- one fresh run (target `r28_hybrid_stabilize`) produces a single final verdict
- one operator-readable output document points to the recommended launch copy

**Today Critical Path:**
1. stop the hybrid crash
2. unify final readiness into one authority artifact
3. enforce a single launch decision
4. rerun one real dual-version + hybrid validation
5. emit one ready-to-use listing document

**Today Launch Gate:**

```text
A10 >= 80
AND COSMO >= 90
AND Rufus >= 90
AND Fluency >= 24
=> recommended_output = "hybrid"

otherwise
=> recommended_output = "version_a"
```

**Today Scope Rule:** if `hybrid` does not pass the gate, that is still a successful day as long as the system explicitly recommends `version_a` and emits the final launch-ready copy without ambiguity or crashes.

---

## File Map

**Critical runtime files**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_generator.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_builder.py` (if readiness summary rendering still forks)

**Regression and verification files**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/integration/test_run_pipeline_wrapper.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_report_builder.py`

**Project-status and governance docs**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/PROJECT_STATUS.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/docs/progress/PROGRESS.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/docs/INDEX.md`
- Create/Modify: directory `INDEX.md` files under config/docs/app paths that are still missing

**Today-delivery artifacts**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/<run_id>/final_readiness_verdict.json`
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/<run_id>/LISTING_READY.md`

---

### Task 1: Restore Green Baseline For Dual-Version Failure Handling

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/integration/test_run_pipeline_wrapper.py`

- [ ] **Step 1: Preserve the current failing regression as the entry gate**

Run: `.venv/bin/pytest /Users/zhoulittlezhou/amazon-listing-skill/tests/integration/test_run_pipeline_wrapper.py::test_main_dual_version_reports_explicit_version_b_failure -v`
Expected: FAIL with `IndexError` when `version_b` contains no bullets.

- [ ] **Step 2: Harden hybrid bullet selection against missing Version B payloads**

Implementation target in `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`:

```python
if bullet_source == "version_a":
    chosen_bullet = bullets_a[idx] if idx < len(bullets_a) else None
else:
    chosen_bullet = bullets_b[idx] if idx < len(bullets_b) else None

if chosen_bullet is None and idx < len(bullets_a):
    bullet_source = "version_a"
    chosen_bullet = bullets_a[idx]
```

- [ ] **Step 2A: Mark the composed payload as degraded when a source is missing**

Implementation intent:

```python
degraded_reasons.append("version_b_missing_bullet_payload")
hybrid_metadata["degraded_mode"] = True
hybrid_metadata["degraded_reasons"] = degraded_reasons
```

- [ ] **Step 3: Keep the dual report explicit about Version B failure**

Assertion target in `/Users/zhoulittlezhou/amazon-listing-skill/tests/integration/test_run_pipeline_wrapper.py`:

```python
assert "Version B generation status: FAILED_AT_BLUEPRINT" in stdout
assert "Generation Status: FAILED_AT_BLUEPRINT" in dual_report
assert "experimental_version_b_blueprint_failed: timeout" in dual_report
```

- [ ] **Step 4: Re-run the focused regression**

Run: `.venv/bin/pytest /Users/zhoulittlezhou/amazon-listing-skill/tests/integration/test_run_pipeline_wrapper.py::test_main_dual_version_reports_explicit_version_b_failure -v`
Expected: PASS

- [ ] **Step 5: Re-run full repository tests**

Run: `.venv/bin/pytest -q`
Expected: PASS with `0 failed`

---

### Task 2: Create A Single Final Verdict Artifact

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_generator.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_builder.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_report_builder.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/PROJECT_STATUS.md`

- [ ] **Step 1: Define `final_readiness_verdict.json` as the only operator-facing authority**

Rule:
- `final_readiness_verdict.json` is the operator-facing truth
- `risk_report.json` and `scoring_results.json` remain diagnostic/intermediate artifacts
- `listing_report.md`, `LISTING_READY.md`, and `PROJECT_STATUS.md` must read from the final verdict, not recompute it separately

- [ ] **Step 2: Freeze the verdict schema**

Target payload:

```json
{
  "run_id": "r28_hybrid_stabilize",
  "recommended_output": "version_a",
  "listing_status": "READY_FOR_LISTING",
  "launch_gate": {
    "passed": false,
    "thresholds": {
      "A10": 80,
      "COSMO": 90,
      "Rufus": 90,
      "Fluency": 24
    }
  },
  "reasons": ["hybrid_a10_below_threshold"],
  "artifact_paths": {
    "recommended_generated_copy": "output/runs/.../version_a/generated_copy.json"
  }
}
```

- [ ] **Step 3: Add a regression test for verdict consistency**

Test shape in `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_report_builder.py`:

```python
def test_final_readiness_verdict_is_the_only_rendered_status_source():
    assert final_verdict["listing_status"] == "READY_FOR_LISTING"
    assert final_verdict["recommended_output"] == "version_a"
    assert "READY_FOR_LISTING" in report_text
```

- [ ] **Step 4: Write the verdict at the end of hybrid finalization**

Implementation target:

```python
final_verdict = {
    "recommended_output": recommended_output,
    "listing_status": listing_status,
    "launch_gate": launch_gate,
    "reasons": reasons,
    "artifact_paths": artifact_paths,
}
(output_dir / "final_readiness_verdict.json").write_text(
    json.dumps(final_verdict, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
```

- [ ] **Step 5: Re-verify known hybrid runs**

Run:
- `jq '{listing_status, dimensions}' /Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r24_hybrid_v3_fix4/hybrid/scoring_results.json`
- `jq '{listing_status, metadata}' /Users/zhoulittlezhou/amazon-listing-skill/output/runs/H91lite_US_r27_hybrid_v3_direction1_fix2/hybrid/risk_report.json`

Expected: historical discrepancies may remain in old runs, but the new final verdict artifact removes ambiguity for fresh runs.

- [ ] **Step 6: Update `/Users/zhoulittlezhou/amazon-listing-skill/PROJECT_STATUS.md`**

Required refresh:
- current baseline run
- latest full test count
- current hybrid status
- current blocking items

---

### Task 3: Lock The Hybrid Launch Gate With Real Regression Coverage

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_optimizer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`

- [ ] **Step 1: Freeze the intended launch criteria in tests**

Test target in `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`:

```python
def test_hybrid_launch_gate_rejects_listing_when_l2_distribution_drops_below_threshold():
    assert result["listing_status"] == "NOT_READY_FOR_LISTING"
    assert result["dimensions"]["traffic"]["score"] < 80
```

- [ ] **Step 2: Add a positive regression for the known-good direction**

```python
def test_hybrid_launch_gate_accepts_listing_when_l2_distribution_is_restored():
    assert result["listing_status"] == "READY_FOR_LISTING"
    assert result["dimensions"]["traffic"]["score"] >= 80
```

- [ ] **Step 3: Make slot-level selection preserve L2 coverage before naturalness preference**

Priority rule:
1. risk-blocked source loses
2. missing bullet source loses
3. source with required L2 coverage wins
4. only then prefer Version B for naturalness

- [ ] **Step 4: Implement `build_hybrid_launch_decision(...)`**

Implementation target:

```python
def build_hybrid_launch_decision(scoring_results: dict) -> dict:
    dims = scoring_results.get("dimensions") or {}
    scores = {
        "A10": ((dims.get("traffic") or {}).get("score")) or 0,
        "COSMO": ((dims.get("content") or {}).get("score")) or 0,
        "Rufus": ((dims.get("conversion") or {}).get("score")) or 0,
        "Fluency": ((dims.get("readability") or {}).get("score")) or 0,
    }
    thresholds = {"A10": 80, "COSMO": 90, "Rufus": 90, "Fluency": 24}
    failed = [name for name, threshold in thresholds.items() if scores[name] < threshold]
    return {
        "passed": not failed,
        "recommended_output": "hybrid" if not failed else "version_a",
        "scores": scores,
        "thresholds": thresholds,
        "reasons": [f"{name.lower()}_below_threshold" for name in failed],
    }
```

- [ ] **Step 5: Persist `launch_decision` into hybrid outputs**

Required write points:
- `hybrid/generated_copy.json`
- `hybrid/final_readiness_verdict.json`
- `dual_version_report.md`

- [ ] **Step 6: Run the hybrid-focused suites**

Run:
- `.venv/bin/pytest /Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py -q`
- `.venv/bin/pytest /Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_optimizer.py -q`

Expected: PASS

- [ ] **Step 7: Re-run one real hybrid validation**

Run example:
- `.venv/bin/python /Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py --product H91lite --market US --run-id r28_hybrid_stabilize --dual-version --fresh`

Expected:
- `hybrid/generated_copy.json` exists
- `hybrid/risk_report.json` exists
- `hybrid/final_readiness_verdict.json` exists
- `hybrid/scoring_results.json` reaches launch gate or clearly explains why it failed

---

### Task 4: Make The Launch Decision Operator-Readable

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_generator.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py`

- [ ] **Step 1: Add `Hybrid Launch Decision` section to the report**

Required section content:
- recommended output
- launch gate scores vs thresholds
- blocking reasons
- fallback target when hybrid is rejected

- [ ] **Step 2: Make the report consumable by operations**

Rendering target:

```markdown
## Hybrid Launch Decision

- Recommended Output: `version_a`
- Hybrid Gate: failed
- Blocking Reasons: `a10_below_threshold`
- Launch Copy Source: `version_a/generated_copy.json`
```

- [ ] **Step 3: Re-run the real validation and inspect `listing_report.md`**

Run:
- `.venv/bin/python /Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py --product H91lite --market US --run-id r28_hybrid_stabilize --dual-version --fresh`

Expected: report includes the launch decision section with no ambiguity.

---

### Task 5: Emit One Launch-Ready Listing Document For Today

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py`

- [ ] **Step 1: Read the recommended source from `final_readiness_verdict.json`**

Selection rule:
- if `recommended_output == "hybrid"`, read from `hybrid/generated_copy.json`
- else read from the recommended fallback path, defaulting to `version_a/generated_copy.json`

- [ ] **Step 2: Write `LISTING_READY.md`**

Required shape:

```markdown
# Listing Ready

## Recommended Source
- Output: `version_a`
- Status: `READY_FOR_LISTING`

## Title
...

## Bullets
1. ...
2. ...
3. ...
4. ...
5. ...
```

- [ ] **Step 3: Re-run the real validation and verify output**

Run:
- `.venv/bin/python /Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py --product H91lite --market US --run-id r28_hybrid_stabilize --dual-version --fresh`

Expected:
- `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/r28_hybrid_stabilize/LISTING_READY.md` exists
- document can be handed to operations without opening multiple JSON files

---

### Task 6: Clean Project Governance Drift And Repository Hygiene

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/docs/INDEX.md`
- Modify/Create: missing directory indexes under `/Users/zhoulittlezhou/amazon-listing-skill/config/`, `/Users/zhoulittlezhou/amazon-listing-skill/docs/`, `/Users/zhoulittlezhou/amazon-listing-skill/app/`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/REPO_INDEX.md`

- [ ] **Step 1: Freeze the missing-index scope**

Current stable gaps observed:
- `/Users/zhoulittlezhou/amazon-listing-skill/config/run_configs`
- `/Users/zhoulittlezhou/amazon-listing-skill/config/market_packs`
- `/Users/zhoulittlezhou/amazon-listing-skill/config/question_banks`
- `/Users/zhoulittlezhou/amazon-listing-skill/app/services`
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers`
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers/plans`

- [ ] **Step 2: Add missing `INDEX.md` files for active directories first**

Template requirement:

```markdown
# <dir> INDEX

## 目的
## 内容结构
## 文件说明
## 使用指南
## 相关链接
```

- [ ] **Step 3: Fix naming-rule violations in active config paths**

Priority rename candidates:
- `/Users/zhoulittlezhou/amazon-listing-skill/config/products/H88/H88_4K_pro_U K`
- `/Users/zhoulittlezhou/amazon-listing-skill/config/products/H88/H88_4K_pro_US `
- `*_tmp.json` under `/Users/zhoulittlezhou/amazon-listing-skill/config/run_configs/`

- [ ] **Step 4: Refresh repository index docs**

Update:
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/INDEX.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/REPO_INDEX.md`

- [ ] **Step 5: Verify directory-index compliance for active paths**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
roots = [Path("config"), Path("docs"), Path("app")]
for base in roots:
    for d in sorted(p for p in base.rglob("*") if p.is_dir() and "__pycache__" not in p.parts):
        files = [p for p in d.iterdir() if p.name != ".DS_Store"]
        if files and not (d / "INDEX.md").exists() and not (d / "README.md").exists():
            print(d)
PY
```

Expected: no active config/docs/app directories reported.

---

### Task 7: Normalize Runtime Entry And Project Narrative Before New Feature Work

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/README.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/PROJECT_STATUS.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/docs/progress/PROGRESS.md`

- [ ] **Step 1: Standardize execution commands on repo virtualenv**

Target examples:

```bash
.venv/bin/python /Users/zhoulittlezhou/amazon-listing-skill/main.py --config /Users/zhoulittlezhou/amazon-listing-skill/config/run_configs/H91lite_US.json
.venv/bin/pytest -q
```

- [ ] **Step 2: Replace stale status claims**

Must update:
- `232 passed`
- `93 passed`
- `v1.0` style stale project narrative when describing the current production system

- [ ] **Step 3: Record the new project narrative**

Project message should become:
- baseline production path exists
- AI OS P0/P1 shipped
- hybrid launch remains the current top stabilization thread

- [ ] **Step 4: Verify docs reference the same current state**

Manual check list:
- `/Users/zhoulittlezhou/amazon-listing-skill/README.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/PROJECT_STATUS.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/progress/PROGRESS.md`

- [ ] **Step 5: Re-run final verification**

Run:
- `.venv/bin/pytest -q`
- `git status --short`

Expected:
- tests green
- only intended doc/runtime changes remain

---

## Self-Review

- Spec coverage: covers runtime blocker, launch blocker, readiness drift, repo-governance drift, and stale project narrative
- Placeholder scan: no `TODO` or `TBD` placeholders used as execution content
- Type consistency: keeps existing module/test names and uses current repo paths
