# Project Status — Launch Review Snapshot

## Snapshot purpose

This repository is a clean GitHub snapshot of the current `amazon-listing-skill` launch candidate.

It was published so external reviewers can inspect:
- pipeline structure
- LLM routing and fallback behavior
- scoring and readiness logic
- fluency / coherence / risk gates
- tests and operational reporting

It is not a full mirror of the original local git history.

## Current launch baseline

The snapshot reflects a system that already supports:
- live LLM generation via the current primary provider path
- four-dimension scoring (`A10`, `COSMO`, `Rufus`, `Fluency`)
- listing readiness outputs for operations teams
- fluency repair and repair logging
- coherence checks and review queue output
- input-table validation and graceful degradation

## Reviewer focus

If you only have 20-30 minutes, review in this order:

1. `run_pipeline.py`
2. `main.py`
3. `modules/llm_client.py`
4. `modules/copy_generation.py`
5. `modules/scoring.py`
6. `modules/listing_status.py`
7. `modules/risk_check.py`
8. `modules/fluency_check.py`
9. `modules/coherence_check.py`
10. `tests/test_production_guardrails.py`

## What “ready” means in this project

A listing is considered ready only when:
- live generation succeeds without unacceptable visible fallback volume
- blocking risk checks do not fire
- the four scoring dimensions all meet threshold
- the runtime listing gate returns a publishable state
- the readiness report is readable by operations without opening raw artifacts

## Known boundaries

Current scope is strong for launch review, but still has boundaries:
- not packaged as a reusable SDK
- no full CI/CD deployment workflow in this snapshot
- some review workflows still assume human-in-the-loop validation
- output quality still depends on provider availability and prompt discipline

## Recent verification

The clean snapshot was verified locally before publishing.

Baseline used for this review snapshot:
- tests: `208 passed`
- repo published to GitHub on branch `main`
- commit family rooted at launch snapshot `e183662`

## Suggested review questions

Good review questions for this repo are:
- Are fallback protections strict enough to prevent templated bad copy from being marked ready?
- Are fluency and coherence heuristics precise enough to avoid noisy false positives?
- Is listing status derived from one clearly authoritative runtime gate?
- Are the four score dimensions explainable to non-engineering operators?
- Does the repair loop preserve evidence-backed numeric claims?

## Immediate next steps after review

The expected next actions after external review are:
- fix any launch-blocking correctness issues
- rerun a real SKU through the pipeline
- confirm readiness output matches human judgment
- then freeze a narrower release branch for production rollout
