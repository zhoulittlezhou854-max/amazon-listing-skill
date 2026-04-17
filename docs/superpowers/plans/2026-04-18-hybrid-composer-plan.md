# Hybrid Composer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-generation hybrid composer that produces a third `hybrid` output from existing V3 and R1 dual-version artifacts without modifying either source version's generated outputs.

**Architecture:** Keep the current dual-version pipeline unchanged through Version A (`version_a`) and Version B (`version_b`) generation. After both are complete, run a new post-processing composer that reads their persisted artifacts, selects visible fields according to configurable rules, and writes a separate `hybrid/` artifact set. Deliver in two phases: Phase 1 composes a safe hybrid MVP with source trace only; Phase 2 rebuilds scoring/risk/readiness on top of that stable contract.

**Tech Stack:** Python, existing pipeline/reporting modules, pytest, JSON artifact readers/writers.

---

## File Map

### Phase 1
- Modify: `run_pipeline.py`
- Create: `modules/hybrid_composer.py`
- Create: `tests/test_hybrid_composer.py`
- Modify: `.learnings/LEARNINGS.md`
- Create outputs under: `output/runs/<sku>_<market>_<run_id>/hybrid/`

### Phase 2
- Modify: `modules/hybrid_composer.py`
- Modify: `modules/report_generator.py`
- Modify: `modules/report_builder.py` (only if hybrid readiness summary needs dedicated labeling)
- Modify: `tests/test_report_builder.py`
- Extend: `tests/test_hybrid_composer.py`

## Scope Guardrails

- Do not modify `version_a/generated_copy.json`
- Do not modify `version_b/generated_copy.json`
- Do not change current V3 generation logic
- Do not change current R1 generation logic
- Do not make hybrid the default winning output in this phase
- Hybrid is an additive third artifact only

## Hybrid Source Defaults

Phase 1 default policy:
- `title` → `version_a`
- `bullets` → `version_b`
- `description` → `version_a`
- `faq` → `version_a`
- `search_terms` → `version_a`
- `aplus_content` → `version_a`

This is a configurable selection policy, not a hard-coded product rule.

---

# Phase 1 — Compose MVP Only

## Task Package A: Define Hybrid Artifact Contract

**Files:**
- Create: `modules/hybrid_composer.py`
- Test: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write the failing contract test for hybrid output paths**

```python
def test_hybrid_composer_writes_to_separate_hybrid_directory(tmp_path):
    version_a = {"title": "A title", "bullets": ["A1", "A2", "A3", "A4", "A5"], "metadata": {}, "decision_trace": {}}
    version_b = {"title": "B title", "bullets": ["B1", "B2", "B3", "B4", "B5"], "metadata": {}, "decision_trace": {}}

    output = compose_hybrid_listing(
        version_a=version_a,
        version_b=version_b,
        output_dir=tmp_path / "hybrid",
        selection_policy={"title": "version_a", "bullets": "version_b"},
    )

    assert (tmp_path / "hybrid" / "generated_copy.json").exists()
    assert output["title"] == "A title"
    assert output["bullets"] == ["B1", "B2", "B3", "B4", "B5"]
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_composer_writes_to_separate_hybrid_directory -v`
Expected: FAIL because `compose_hybrid_listing` does not exist yet.

- [x] **Step 3: Implement the minimal hybrid contract**

```python
def compose_hybrid_listing(version_a, version_b, output_dir, selection_policy):
    hybrid = {
        "title": version_a["title"] if selection_policy["title"] == "version_a" else version_b["title"],
        "bullets": version_a["bullets"] if selection_policy["bullets"] == "version_a" else version_b["bullets"],
        "description": version_a.get("description", ""),
        "faq": version_a.get("faq", []),
        "search_terms": version_a.get("search_terms", []),
        "aplus_content": version_a.get("aplus_content", ""),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "generated_copy.json").write_text(json.dumps(hybrid, ensure_ascii=False, indent=2), encoding="utf-8")
    return hybrid
```

- [x] **Step 4: Re-run the test and verify it passes**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_composer_writes_to_separate_hybrid_directory -v`
Expected: PASS.

## Task Package B: Add Source Trace + Hybrid Metadata

**Files:**
- Modify: `modules/hybrid_composer.py`
- Test: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write a failing test for source trace metadata**

```python
def test_hybrid_metadata_records_field_sources(tmp_path):
    hybrid = compose_hybrid_listing(
        version_a={"title": "A", "bullets": ["A"] * 5, "metadata": {"generation_status": "live_success"}, "decision_trace": {}},
        version_b={"title": "B", "bullets": ["B"] * 5, "metadata": {"generation_status": "live_success"}, "decision_trace": {}},
        output_dir=tmp_path / "hybrid",
        selection_policy={"title": "version_a", "bullets": "version_b"},
    )

    assert hybrid["metadata"]["visible_copy_mode"] == "hybrid_postselect"
    assert hybrid["metadata"]["hybrid_sources"]["title"] == "version_a"
    assert hybrid["source_trace"]["bullets"][0]["source_version"] == "version_b"
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_metadata_records_field_sources -v`
Expected: FAIL because metadata/trace is incomplete.

- [x] **Step 3: Add hybrid-specific metadata without mutating source metadata**

```python
hybrid["metadata"] = {
    **base_metadata,
    "visible_copy_mode": "hybrid_postselect",
    "visible_copy_status": "hybrid_mixed",
    "hybrid_sources": {
        "title": title_source,
        "bullets": bullet_source,
        "description": description_source,
        "faq": faq_source,
        "search_terms": search_terms_source,
        "aplus_content": aplus_source,
    },
}
hybrid["source_trace"] = {
    "title": {"source_version": title_source},
    "bullets": [{"slot": f"B{i}", "source_version": bullet_source} for i in range(1, 6)],
    "description": {"source_version": description_source},
    "faq": {"source_version": faq_source},
    "search_terms": {"source_version": search_terms_source},
    "aplus_content": {"source_version": aplus_source},
}
```

- [x] **Step 4: Re-run the test and verify it passes**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_metadata_records_field_sources -v`
Expected: PASS.

## Task Package C: Carry Safe Trace Only, Do Not Re-Score Yet

**Files:**
- Modify: `modules/hybrid_composer.py`
- Test: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write a failing test for conservative trace inheritance**

```python
def test_hybrid_mvp_carries_only_safe_trace_segments(tmp_path):
    version_a = {
        "title": "A title",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "metadata": {},
        "decision_trace": {"search_terms_trace": {"byte_length": 180}},
    }
    version_b = {
        "title": "B title",
        "bullets": ["B1", "B2", "B3", "B4", "B5"],
        "metadata": {},
        "decision_trace": {"bullet_trace": [{"slot": "B1", "audience_group": "professional"}]},
    }

    hybrid = compose_hybrid_listing(
        version_a=version_a,
        version_b=version_b,
        output_dir=tmp_path / "hybrid",
        selection_policy={"title": "version_a", "bullets": "version_b"},
    )

    assert hybrid["decision_trace"]["bullet_trace"][0]["slot"] == "B1"
    assert hybrid["decision_trace"]["search_terms_trace"]["byte_length"] == 180
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_mvp_carries_only_safe_trace_segments -v`
Expected: FAIL because MVP trace inheritance is missing.

- [x] **Step 3: Implement conservative trace carry-over**

```python
hybrid["decision_trace"] = {
    "bullet_trace": deepcopy(version_b.get("decision_trace", {}).get("bullet_trace", [])),
    "search_terms_trace": deepcopy(version_a.get("decision_trace", {}).get("search_terms_trace", {})),
    "keyword_assignments": [],  # intentionally deferred to Phase 2
}
```

- [x] **Step 4: Re-run the test and verify it passes**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_mvp_carries_only_safe_trace_segments -v`
Expected: PASS.

## Task Package D: Wire MVP Into Dual-Version Runner

**Files:**
- Modify: `run_pipeline.py`
- Modify: `modules/hybrid_composer.py`
- Test: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write a failing integration test for dual-version hybrid directory creation**

```python
def test_dual_version_run_can_write_hybrid_directory(tmp_path, monkeypatch):
    # monkeypatch version_a/version_b payloads and hybrid composer invocation
    ...
    assert (tmp_path / "run" / "hybrid" / "generated_copy.json").exists()
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_dual_version_run_can_write_hybrid_directory -v`
Expected: FAIL because dual-version wrapper does not call composer yet.

- [x] **Step 3: Hook Phase 1 composer into `run_pipeline.py` only for `--dual-version`**

```python
hybrid_dir = output_dir / "hybrid"
hybrid_output = hybrid_composer.compose_hybrid_listing(
    version_a=version_a["generated_copy"],
    version_b=version_b["generated_copy"],
    output_dir=hybrid_dir,
    selection_policy=DEFAULT_HYBRID_SELECTION_POLICY,
)
```

- [x] **Step 4: Re-run focused tests and verify they pass**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -q`
Expected: PASS.

## Phase 1 Acceptance

- [ ] `version_a/` outputs unchanged
- [ ] `version_b/` outputs unchanged
- [ ] new `hybrid/generated_copy.json` exists
- [ ] new `hybrid/source_trace.json` exists (or embedded equivalent persisted with generated copy)
- [ ] hybrid metadata clearly records field-level source selection
- [ ] no hybrid scoring/readiness/report generation yet

---

# Phase 2 — Re-Audit And Reporting

## Task Package E: Rebuild Keyword Assignments For Hybrid

**Files:**
- Modify: `modules/hybrid_composer.py`
- Extend: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write a failing test for posthoc keyword assignment reconciliation**

```python
def test_hybrid_rebuilds_keyword_assignments_for_selected_fields(tmp_path):
    version_a = {
        "title": "Brand action camera",
        "bullets": ["A1", "A2", "A3", "A4", "A5"],
        "metadata": {},
        "decision_trace": {"keyword_assignments": [{"keyword": "action camera", "assigned_fields": ["title"]}]},
    }
    version_b = {
        "title": "Brand body camera",
        "bullets": ["body camera bullet", "B2", "B3", "B4", "B5"],
        "metadata": {},
        "decision_trace": {"keyword_assignments": [{"keyword": "body camera", "assigned_fields": ["B1"]}]},
    }

    hybrid = compose_hybrid_listing(...)
    rebuilt = rebuild_hybrid_decision_trace(hybrid, version_a, version_b)

    assignments = rebuilt["keyword_assignments"]
    assert any(row["keyword"] == "action camera" and "title" in row["assigned_fields"] for row in assignments)
    assert any(row["keyword"] == "body camera" and "B1" in row["assigned_fields"] for row in assignments)
    assert any(row["source_version"] == "version_a" for row in assignments)
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_rebuilds_keyword_assignments_for_selected_fields -v`
Expected: FAIL because trace rebuild does not exist yet.

- [x] **Step 3: Implement trace reconciliation by selected-field merge first, text scan second**

```python
def rebuild_hybrid_decision_trace(hybrid_copy, version_a, version_b):
    # merge rows from the chosen source per field
    # then backfill missing-but-visible keywords with source_version="reconciled"
    ...
```

- [x] **Step 4: Re-run the test and verify it passes**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_rebuilds_keyword_assignments_for_selected_fields -v`
Expected: PASS.

## Task Package F: Re-run Risk, Scoring, And Readiness On Hybrid

**Files:**
- Modify: `modules/hybrid_composer.py`
- Modify: `tests/test_report_builder.py`
- Extend: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write a failing test proving hybrid must produce fresh scoring + readiness artifacts**

```python
def test_hybrid_finalize_writes_scoring_and_readiness_outputs(tmp_path, sample_preprocessed, sample_policy):
    hybrid = compose_hybrid_listing(...)
    finalize_hybrid_outputs(
        hybrid_copy=hybrid,
        writing_policy=sample_policy,
        preprocessed_data=sample_preprocessed,
        output_dir=tmp_path / "hybrid",
    )

    assert (tmp_path / "hybrid" / "scoring_results.json").exists()
    assert (tmp_path / "hybrid" / "readiness_summary.md").exists()
    assert (tmp_path / "hybrid" / "listing_report.md").exists()
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_hybrid_finalize_writes_scoring_and_readiness_outputs -v`
Expected: FAIL because finalize step does not exist yet.

- [x] **Step 3: Implement hybrid finalization using existing modules**

```python
risk_report = perform_risk_check(...)
scoring_results = calculate_scores(..., risk_report=risk_report)
listing_report = generate_report(...)
readiness_summary = build_readiness_summary(...)
```

- [x] **Step 4: Persist results into `hybrid/` only**

```python
(output_dir / "risk_report.json").write_text(...)
(output_dir / "scoring_results.json").write_text(...)
(output_dir / "listing_report.md").write_text(...)
(output_dir / "readiness_summary.md").write_text(...)
```

- [x] **Step 5: Re-run focused tests and verify they pass**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_report_builder.py -q`
Expected: PASS.

## Task Package G: Add Human-Readable Hybrid Reporting

**Files:**
- Modify: `modules/report_generator.py`
- Extend: `tests/test_hybrid_composer.py`

- [x] **Step 1: Write a failing test for dual report surfacing hybrid block without replacing A/B**

```python
def test_dual_report_can_include_hybrid_appendix():
    report = generate_dual_version_report(..., hybrid={
        "generated_copy": {"title": "Hybrid title", "bullets": ["H1", "H2", "H3", "H4", "H5"]},
        "scoring_results": {"listing_status": "READY_FOR_LISTING"},
    })

    assert "## Hybrid Recommendation" in report
    assert "Hybrid title" in report
    assert "Version A" in report and "Version B" in report
```

- [x] **Step 2: Run the test and verify it fails**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_dual_report_can_include_hybrid_appendix -v`
Expected: FAIL because report generator only supports A/B.

- [x] **Step 3: Extend report generator additively**

```python
def generate_dual_version_report(..., hybrid: Dict[str, Any] | None = None):
    ...
    if hybrid:
        lines.extend([
            "",
            "## Hybrid Recommendation",
            ...
        ])
```

- [x] **Step 4: Re-run the report test and verify it passes**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py::test_dual_report_can_include_hybrid_appendix -v`
Expected: PASS.

## Phase 2 Acceptance

- [x] hybrid `keyword_assignments` rebuilt with `source_version`
- [x] hybrid `risk_report.json` exists
- [x] hybrid `scoring_results.json` exists
- [x] hybrid `readiness_summary.md` exists
- [x] hybrid `listing_report.md` exists
- [x] top-level `dual_version_report.md` includes A/B plus Hybrid appendix
- [x] `version_a/` and `version_b/` artifacts remain byte-for-byte untouched

---

## End-to-End Validation

- [ ] **Step 1: Run Phase 1 regression suite**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py -q`
Expected: PASS.

- [ ] **Step 2: Run a real dual-version + hybrid MVP pipeline**

Run:
```bash
OPENAI_COMPAT_VERIFY_SSL=0 .venv/bin/python run_pipeline.py \
  --product H91lite --market US \
  --run-id r17_hybrid_mvp --fresh --dual-version
```

Expected:
- `version_a/generated_copy.json` untouched
- `version_b/generated_copy.json` untouched
- new `hybrid/generated_copy.json` exists
- no hybrid scoring/readiness files yet in Phase 1

- [x] **Step 3: Run Phase 2 regression suite**

Run: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_report_builder.py tests/test_keyword_arsenal_report.py tests/test_production_guardrails.py -q`
Expected: PASS.

- [x] **Step 4: Run a real dual-version + hybrid full pipeline**

Run:
```bash
OPENAI_COMPAT_VERIFY_SSL=0 .venv/bin/python run_pipeline.py \
  --product H91lite --market US \
  --run-id r17_hybrid_full --fresh --dual-version
```

Expected:
- `version_a/generated_copy.json` untouched
- `version_b/generated_copy.json` untouched
- new `hybrid/generated_copy.json` exists
- new `hybrid/scoring_results.json` exists
- new `hybrid/readiness_summary.md` exists
- top-level `dual_version_report.md` includes Hybrid appendix

- [ ] **Step 5: Record learnings**

Update `.learnings/LEARNINGS.md` with:
- why hybrid must be post-generation instead of in Step 6
- why trace/scoring must be rebuilt after mixing
- why hybrid is additive and not a replacement for V3/R1 outputs
- why `source_trace` + `source_version` are required for debugging
