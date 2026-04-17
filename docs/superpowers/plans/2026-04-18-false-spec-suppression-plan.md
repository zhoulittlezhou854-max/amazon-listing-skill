# False Spec Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent unsupported boolean-false capabilities (starting with `live_streaming_supported=false`) from polluting Version B blueprint planning and downstream bullets.

**Architecture:** Add two defensive layers. First, suppress false capability specs during policy/intent enrichment so they do not become positive capability nodes. Second, add a deterministic blueprint scrubber that removes suppressed capability language from all blueprint fields before Step 6 consumes the plan.

**Tech Stack:** Python, pytest, existing writing_policy / intent enrichment / blueprint generation pipeline.

---

## Files
- Modify: `modules/intent_translator.py`
- Modify: `modules/blueprint_generator.py`
- Create/Modify: `tests/test_blueprint_generator.py`
- Modify: `.learnings/LEARNINGS.md`

## Scope Guardrails
- Do not change V3 or R1 visible copy generation logic in `modules/copy_generation.py`
- Do not weaken truth/risk blockers
- Do not special-case only live streaming in prompt text; build a reusable suppression path
- Fix upstream planning so bad capabilities never become bullet mandatory elements

## Task Package A: Failing Tests First
- [ ] Add a failing test that `live_streaming_supported=False` does not become a positive enriched capability node.
- [ ] Add a failing test that blueprint entries scrub suppressed terms from `theme`, `mandatory_elements`, `capabilities`, `proof_angle`, and `slot_directive`.
- [ ] Add a failing regression test that `live_streaming_supported=True` still allows live-streaming terms.
- [ ] Add a failing test for another suppressed false capability (`waterproof_supported=False`) to prove the filter is reusable.

## Task Package B: Suppress False Specs During Enrichment
- [ ] Add a reusable helper in `modules/intent_translator.py` to detect suppressed boolean-false capability specs.
- [ ] Ensure enrichment skips generating positive capability nodes for suppressed specs.
- [ ] Persist a machine-readable suppression set into the enriched policy so blueprint generation can consume it directly.

## Task Package C: Blueprint Deterministic Scrub
- [ ] Add a suppression term map in `modules/blueprint_generator.py` keyed by capability spec.
- [ ] Implement a deterministic scrubber over blueprint entry fields: `theme`, `mandatory_elements`, `capabilities`, `proof_angle`, `slot_directive`.
- [ ] Run the scrubber after blueprint parsing and before blueprint JSON is written to disk/returned.
- [ ] Ensure true-supported capabilities are not scrubbed.

## Task Package D: Verification
- [ ] Run focused tests for blueprint suppression.
- [ ] Re-run Version B real pipeline and confirm `bullet_blueprint.json` no longer carries live-streaming mandatory elements.
- [ ] Re-run Hybrid full pipeline and confirm `unsupported_live_streaming_claim` no longer blocks listing status.
- [ ] Record learnings in `.learnings/LEARNINGS.md`.
