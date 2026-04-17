# R1 Title Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate the R1 title generation path from the shared V3-oriented post-processing pipeline so Version B titles can be generated deterministically without retry inflation or timeout loops.

**Architecture:** Keep the existing V3 title path untouched. Add an R1-only title finalize path inside `modules/copy_generation.py` that takes recipe inputs, assembles the final title locally, runs only lightweight validation/repair, and never re-enters the shared generic audit loop.

**Tech Stack:** Python, pytest, existing listing pipeline, DeepSeek R1 for recipe generation only.

---

## File Map

- Modify: `modules/copy_generation.py`
- Modify: `tests/test_copy_generation.py`
- Modify: `.learnings/LEARNINGS.md`
- Verify runtime artifacts under: `output/runs/.../step6_artifacts/visible_copy_batch.json`

## Task Package A: Lock Boundaries

- [x] Confirm the R1-only scope in `modules/copy_generation.py`
- [x] Preserve V3 behavior exactly; no edits to V3 flow beyond a narrow branch gate
- [x] Record the root cause in `.learnings/LEARNINGS.md`: recipe titles fail because shared post-processing mutates already-assembled titles

## Task Package B: Add R1 Dedicated Title Finalize Path

- [x] Add an R1-only entry path in `modules/copy_generation.py` (e.g. `_generate_title_r1(...)`)
- [x] Route only payloads marked for recipe assembly into that path
- [x] Keep `_assemble_title_from_segments(...)` and recipe extraction logic as the title material source
- [x] Ensure the R1 path does not call shared retry-oriented post-processing

## Task Package C: Keep Only Lightweight Validation/Repair for R1

- [ ] Validate only the final constraints R1 actually needs: length, required keyword presence, basic anti-dump checks
- [ ] Use deterministic local repair only if needed
- [ ] Do not call `llm_adjusted_l1`, strong `title_dewater`, or any LLM retry in the R1 path
- [ ] Keep audit logging explicit so artifact review can prove the bypass worked

## Task Package D: Test Coverage

- [x] Add/adjust unit tests in `tests/test_copy_generation.py`
- [ ] Cover: one-LLM-call behavior, required keyword preservation, valid final length, and bypass of shared post-processing
- [ ] Add a regression check that non-R1/V3 payloads still use the original flow
- [x] Run: `./.venv/bin/pytest tests/test_copy_generation.py -q`

## Task Package E: Real Step 6 Validation

- [x] Run a real Step 6-oriented R1 validation with `deepseek-reasoner` for title + bullets
- [x] Inspect `visible_copy_batch.json`
- [x] Verify audit log no longer shows `llm_adjusted_l1`, strong `title_dewater`, or `llm_retry` for the title path
- [x] Verify the final title satisfies length + required keyword constraints

## Task Package F: Archive and Release Hygiene

- [ ] Update `.learnings/LEARNINGS.md` with the architectural fix and validation result
- [ ] Commit only after tests and real validation pass
- [ ] Push after local verification so GitHub reflects the final R1-only fix
