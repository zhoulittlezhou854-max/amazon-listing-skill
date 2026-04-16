# V2.0 Listing Quality And Ops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade listing quality in two phases: first improve title/blueprint/bullet quality without regressing the live-success baseline, then add workspace-scoped history viewing and keyword arsenal visibility for operators.

**Architecture:** V2.0-A changes only the quality-control layer around the existing generation pipeline: unify length constants, improve title prompting, add audience allocation in blueprint planning, and inject bullet-dimension dedup into fluency/repair. V2.0-B leaves the generation pipeline untouched and adds a local-history UI plus a report block that surfaces L1/L2/L3 arsenal data already produced by the backend.

**Tech Stack:** Python, Streamlit, pytest, existing `main.py` + `run_pipeline.py` workflow, local JSON/Markdown run artifacts.

---

## File Map

**V2.0-A core files**
- Modify: `modules/copy_generation.py`
- Modify: `modules/writing_policy.py`
- Modify: `modules/blueprint_generator.py`
- Read only: `modules/stag_locale.py`
- Modify: `modules/fluency_check.py`
- Add: `tests/test_length_rules.py`
- Add: `tests/test_title_naturalness.py`
- Add: `tests/test_blueprint_audience_coverage.py`
- Add: `tests/test_bullet_dimension_dedup.py`
- Modify: `.learnings/LEARNINGS.md`

**V2.0-B core files**
- Modify: `app/streamlit_app.py`
- Modify: `app/services/run_service.py` (only if the history tab needs helper shaping)
- Modify: `app/services/workspace_service.py` (only if workspace run discovery helper is missing)
- Modify: `modules/report_generator.py`
- Modify or add: `modules/report_builder.py` (only if a compact arsenal block belongs there)
- Add: `tests/test_keyword_arsenal_report.py`
- Add/modify: `tests/test_streamlit_services.py`
- Modify: `.learnings/LEARNINGS.md`

---

## V2.0-A Task Packages

### Package A0: Read-Only Code Mapping

**Files:**
- Read: `modules/copy_generation.py`
- Read: `modules/writing_policy.py`
- Read: `modules/blueprint_generator.py`
- Read: `modules/stag_locale.py`
- Read: `modules/fluency_check.py`

- [ ] **Step 1: Record title-generation touchpoints**

Capture the exact functions/constants that currently shape title generation:
- `_llm_generate_title`
- `_generate_and_audit_title`
- `_compose_exact_match_title`
- title payload builder where `max_length` is set
- post-generation title trim/truncate block

Expected outcome: a short summary with function names and line numbers.

- [ ] **Step 2: Record blueprint and audience touchpoints**

Capture the blueprint entrypoints and prompt location:
- `_generate_bullet_blueprint_impl`
- `generate_bullet_blueprint`
- `generate_bullet_blueprint_r1`
- any current persona/scenes payload items injected into blueprint prompt

Expected outcome: exact insertion point for audience allocation plan.

- [ ] **Step 3: Record fluency aggregation and repair touchpoints**

Capture:
- `FluencyIssue`
- `check_fluency`
- result aggregation path
- repair prompt construction path

Expected outcome: exact insertion points for dimension dedup + repair injection.

- [ ] **Step 4: Commit readout into execution notes**

Save the mapping summary in the working notes for the implementation session.

Run: no code changes, no tests required.
Expected: implementation entrypoints are unambiguous.

### Package A1: Length Rules Unification

**Files:**
- Modify: `modules/writing_policy.py`
- Modify: `modules/copy_generation.py`
- Test: `tests/test_length_rules.py`

- [ ] **Step 1: Add centralized length constants**

Define one shared structure in `modules/writing_policy.py` (or a nearby existing config area):

```python
LENGTH_RULES = {
    "title": {
        "target_min": 160,
        "target_max": 190,
        "hard_ceiling": 200,
        "soft_warning": 150,
    },
    "bullet": {
        "target_min": 200,
        "target_max": 250,
        "hard_ceiling": 500,
        "seo_byte_limit": 1000,
    },
}
```

- [ ] **Step 2: Replace title hardcoded lengths with the shared constants**

Update title payload construction and post-trim logic so generation targets `160–190`, and hard trim is `200`.

- [ ] **Step 3: Replace bullet prompt/trim hardcoded lengths with the shared constants**

Update bullet prompt wording and length-enforcement helpers so they reference the centralized rules. Keep `500` as a hard ceiling only, not the writing target.

- [ ] **Step 4: Write the failing tests**

Create `tests/test_length_rules.py` covering:
- title hard ceiling = 200
- title soft warning threshold = 150 exposed/usable
- bullet hard ceiling = 500
- bullet SEO byte limit = 1000

- [ ] **Step 5: Run the targeted tests**

Run: `pytest tests/test_length_rules.py -v`
Expected: PASS

### Package A2: Title Naturalness Upgrade

**Files:**
- Modify: `modules/copy_generation.py`
- Modify: `modules/writing_policy.py` (only if title rule text still exposes old limits/instructions)
- Test: `tests/test_title_naturalness.py`

- [ ] **Step 1: Identify and neutralize full-title deterministic overwrite logic**

If a deterministic patch rewrites the whole title into a comma-stacked keyword string, reduce it to presence checking only.

- [ ] **Step 2: Replace title prompt instructions with semantic guidance**

Update the title prompt so it requires:
- brand-first
- at least 3 dynamic core keywords
- top 2 differentiators naturally embedded
- natural English product-name phrasing
- no pure comma-list keyword dump
- no bare technical parameter brackets

- [ ] **Step 3: Preserve keyword validation without replacing the sentence**

If post-generation repair runs, it may inject missing keywords, but it must not flatten the title into a keyword list.

- [ ] **Step 4: Write the failing tests**

Create `tests/test_title_naturalness.py` with checks for:
- at least 3 core keywords present
- length <= 200
- comma-count + no-verb heuristic catches keyword-list failure mode

- [ ] **Step 5: Run the targeted tests**

Run: `pytest tests/test_title_naturalness.py -v`
Expected: PASS

### Package A3: Blueprint Audience Allocation

**Files:**
- Modify: `modules/blueprint_generator.py`
- Read: `modules/stag_locale.py`
- Test: `tests/test_blueprint_audience_coverage.py`

- [ ] **Step 1: Define audience-allocation constants locally in blueprint generator**

Add `AUDIENCE_GROUPS` and `AUDIENCE_FALLBACK_PLAN` directly in `modules/blueprint_generator.py`. Do not move audience data into `modules/stag_locale.py`.

- [ ] **Step 2: Build audience allocation before prompt assembly**

Construct an `audience_allocation` object per blueprint run. Fallback groups must guarantee coverage for:
- professional/work use
- daily/personal use
- kit/value proposition

- [ ] **Step 3: Inject the allocation plan into both V3 and R1 blueprint prompts**

Ensure `_generate_bullet_blueprint_impl(...)` always includes the allocation plan, so `generate_bullet_blueprint()` and `generate_bullet_blueprint_r1()` stay consistent automatically.

- [ ] **Step 4: Write the failing tests**

Create `tests/test_blueprint_audience_coverage.py` asserting that generated blueprint metadata or slot tags include at least 2 different audience groups.

- [ ] **Step 5: Run the targeted tests**

Run: `pytest tests/test_blueprint_audience_coverage.py -v`
Expected: PASS

### Package A4: Bullet Dimension Dedup + Repair Injection

**Files:**
- Modify: `modules/fluency_check.py`
- Test: `tests/test_bullet_dimension_dedup.py`

- [ ] **Step 1: Add header extraction + dimension clusters**

Implement `check_bullet_dimension_dedup(bullets: list[str]) -> dict` using simple keyword-cluster matching with no new dependencies.

- [ ] **Step 2: Add bullet byte-limit check**

Implement `check_bullet_total_bytes(bullets: list[str]) -> dict` with a `1000` byte soft warning ceiling.

- [ ] **Step 3: Integrate both checks into the fluency aggregation path**

`bullet_dimension_dedup` should be `medium` severity and eligible for repair.
`bullet_total_bytes` should be `soft` severity and warning-only.

- [ ] **Step 4: Inject dimension-repeat details into repair prompt context**

When dimension dedup fails, append the duplicated dimension and affected bullet indexes so repair knows which bullets must change core angle rather than paraphrase.

- [ ] **Step 5: Write the failing tests**

Create `tests/test_bullet_dimension_dedup.py` covering:
- all 5 bullets distinct => pass
- 3 commute/travel bullets => fail
- only 2 repeated => pass

- [ ] **Step 6: Run the targeted tests**

Run: `pytest tests/test_bullet_dimension_dedup.py -v`
Expected: PASS

### Package A5: V2.0-A Regression + Live Validation

**Files:**
- Modify: `.learnings/LEARNINGS.md`
- Read artifacts in: `output/runs/H91lite_US_r16_v2a`

- [ ] **Step 1: Run full regression**

Run: `pytest tests/ -q`
Expected: all tests pass; baseline must not regress.

- [ ] **Step 2: Run live validation**

Run:
```bash
python run_pipeline.py --product H91lite --market US --run-id r16_v2a --fresh
```

Expected:
- `generation_status = live_success`
- `listing_status = READY_FOR_LISTING`
- A10 >= 100
- COSMO >= 100
- Rufus >= 90
- Fluency >= 30
- title looks like natural English, not comma-stack
- bullets cover at least 2 audience groups
- 5 bullet headers do not collapse into a single repeated dimension

- [ ] **Step 3: Update learnings**

Log:
- title guidance change location/method
- audience allocation structure/fallback
- bullet dedup threshold + repair injection
- length-rule constant location
- `r16_v2a` vs `r15_v3only`

---

## V2.0-B Task Packages (execute only after V2.0-A is green)

### Package B1: Keyword Arsenal Report Block

**Files:**
- Modify: `modules/report_generator.py`
- Possibly read: `modules/keyword_arsenal.py`
- Test: `tests/test_keyword_arsenal_report.py`

- [ ] **Step 1: Identify existing keyword-routing data in report generation**

Reuse already-computed L1/L2/L3/routing data; do not recalculate tiers from scratch.

- [ ] **Step 2: Add a `## Keyword Arsenal` section to `listing_report.md`**

Must include:
- L1 — Title Keywords
- L2 — Bullet Keywords
- L3 — Search Terms Keywords
- Routing Summary

- [ ] **Step 3: Write the failing test**

Create `tests/test_keyword_arsenal_report.py` verifying the new section and all three tier headings are present and populated.

- [ ] **Step 4: Run the targeted test**

Run: `pytest tests/test_keyword_arsenal_report.py -v`
Expected: PASS

### Package B2: Workspace-Scoped History Reports Tab

**Files:**
- Modify: `app/streamlit_app.py`
- Modify: `app/services/run_service.py` only if helper shaping is needed
- Modify: `app/services/workspace_service.py` only if run discovery helper is missing
- Test: `tests/test_streamlit_services.py`

- [ ] **Step 1: Add a new `历史报告` tab**

It must:
- let user choose one workspace
- list only runs under that workspace
- default each run to expanded detail view

- [ ] **Step 2: Show per-run expanded sections**

For each run show:
- basic info (time, generation_status, listing_status)
- title / bullets / description / search terms
- scoring dimensions + breakdown
- clickable/expandable report files

- [ ] **Step 3: Add dual-version presentation**

If the run has `version_a`/`version_b`, display both side-by-side or in clearly separated sections.

- [ ] **Step 4: Add/extend tests**

Update `tests/test_streamlit_services.py` to cover workspace run discovery and history payload rendering assumptions.

- [ ] **Step 5: Run the targeted tests**

Run: `pytest tests/test_streamlit_services.py -v`
Expected: PASS

### Package B3: V2.0-B Regression

**Files:**
- Modify: `.learnings/LEARNINGS.md`

- [ ] **Step 1: Run full regression**

Run: `pytest tests/ -q`
Expected: all tests pass; V2.0-A baseline remains intact.

- [ ] **Step 2: Manual UI validation**

Verify:
- workspace-scoped history loads correctly
- runs default open with copy and scoring visible
- dual-version runs show both versions
- `Keyword Arsenal` block is visible inside report content

- [ ] **Step 3: Update learnings**

Log data paths, UI structure, and validation notes.

---

## Recommended Execution Order

1. Package A0
2. Package A1
3. Package A2
4. Package A3
5. Package A4
6. Package A5
7. Package B1
8. Package B2
9. Package B3

## Acceptance Gates

**Gate 1 (after A5):** quality pipeline remains live-success and readable enough to replace the current V2.0 baseline.

**Gate 2 (after B3):** operators can inspect past runs inside the frontend without opening raw artifact folders, and reports expose the exact L1/L2/L3 arsenal used for that run.
