# Amazon Listing Skill

Amazon listing generation and review pipeline for real-product launch workflows.

This repository contains the launch-ready snapshot of the `amazon-listing-skill` system used to:
- generate listing copy with live LLM providers
- score output across four independent dimensions
- detect compliance, fluency, and coherence risks
- produce reviewer-friendly readiness reports before listing goes live

## What this snapshot is

This GitHub repo is a clean review snapshot prepared for external code review.

It intentionally includes:
- core pipeline code
- configs, docs, scripts, and tests
- the current launch-ready logic used for real SKU validation

It intentionally excludes:
- local output artifacts
- private environment files and API keys
- unrelated dirty worktree changes from the original local repo

## Current system status

The current launch baseline has already reached:
- live generation on the primary LLM path
- four-dimension scoring output
- readiness summary generation for operations review
- repair logging and post-run risk reporting
- stable test baseline in this snapshot: `208 passed`

## Core workflow

The production pipeline follows this shape:

1. validate input tables
2. preprocess evidence and keyword sources
3. build writing policy and benchmark references
4. generate title / bullets / description / A+ / search terms
5. run fluency, coherence, and risk checks
6. score the listing across traffic, content, conversion, and readability
7. produce readiness outputs for human review or launch decision

## Scoring model

The system reports four dimensions instead of a single opaque score:

- `traffic` (`A10`): keyword and discoverability quality
- `content` (`COSMO`): content richness and policy fit
- `conversion` (`Rufus`): spec signal and selling effectiveness
- `readability` (`Fluency`): human readability and repair quality

The final `listing_status` is determined from per-dimension thresholds rather than a single blended total.

## Main entry points

- `main.py` — runs the end-to-end generator workflow from a config file
- `run_pipeline.py` — convenience wrapper for real-product runs
- `app/streamlit_app.py` — local review UI

Common commands:

```bash
python -m pip install -r requirements.txt
/.venv/bin/pytest tests/ -q
python run_pipeline.py --product H91lite --market US --run-id r14 --fresh
```

## Repository map

- `modules/` — generation, scoring, risk, fluency, coherence, repair logging
- `config/` — run configs and product data references
- `docs/` — PRDs, audits, operational specs, input table spec
- `scripts/` — diagnostics and utility scripts
- `tests/` — regression and integration coverage
- `tools/` — shared loaders and preprocessing helpers

## Recommended review path

If you are reviewing this codebase for launch readiness, start here:

1. `PROJECT_STATUS.md`
2. `run_pipeline.py`
3. `main.py`
4. `modules/llm_client.py`
5. `modules/copy_generation.py`
6. `modules/scoring.py`
7. `modules/risk_check.py`
8. `modules/fluency_check.py`
9. `modules/coherence_check.py`
10. `tests/`

## Key docs

- `PROJECT_STATUS.md` — current launch status, review focus, known limits
- `docs/input_tables_spec.md` — required input table format and fallback behavior
- `CLAUDE.md` — repo conventions and agent instructions carried from the local project

## Review focus areas

The most important things to challenge in code review are:
- provider routing and LLM failure handling
- fallback quality protections
- fluency and coherence rule precision
- listing status blocking logic
- score interpretability and operational usefulness
- input-table validation and graceful degradation

## Notes

This repo is meant for review and collaboration. It is not a packaged library and does not yet include full deployment automation.
