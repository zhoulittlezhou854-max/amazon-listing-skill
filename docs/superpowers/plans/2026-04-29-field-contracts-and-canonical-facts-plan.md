# Field Contracts and Canonical Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Scheme B: fix remaining H91 readiness blockers from the bottom up by adding canonical product facts, field-level provenance, compliance-aware description repair, bullet slot contracts, and readiness projection without reworking `keyword_protocol`.

**Architecture:** Keep the existing pipeline and `version_a` stable. Add focused contract modules that upstream generation and downstream hybrid/readiness can share: `canonical_facts` answers what can be said, `claim_language_contract` answers how it can be said, `field_provenance` answers whether a field source is launch-eligible, and slot contracts ensure each bullet has one semantic promise. `keyword_protocol` remains the authoritative keyword tier/opportunity system and is only consumed, not redesigned.

**Tech Stack:** Python stdlib, existing pytest suite, existing live pipeline artifacts under `output/runs`, existing modules in `/Users/zhoulittlezhou/amazon-listing-skill/modules` and `/Users/zhoulittlezhou/amazon-listing-skill/tools`.

---

## Boundary Confirmation

### In Scope

- Add a canonical facts layer that normalizes product attributes, accessories, capability constraints, and claim permissions.
- Add a shared claim-language contract for forbidden surface phrases such as `best`, `guaranteed`, unsupported `warranty`, and unsafe waterproof claims.
- Change description handling from binary `success/fallback` to `native_live`, `repaired_live`, `safe_fallback`, `unsafe_fallback`, and `unavailable` provenance.
- Let description text that is semantically safe but contains forbidden surface wording be regenerated/repaired, then re-audited before fallback.
- Add field-level eligibility for hybrid selection so hybrid chooses only launch-eligible fields or blocks with explicit reasons.
- Add bullet slot contracts for B1-B5, starting with B5, so header/body share one promise and use only allowed facts.
- Preserve `KeywordProtocol` as the single source for `quality_status`, `traffic_tier`, `routing_role`, `opportunity_score`, and `blue_ocean_score`.
- Keep `scoring_results.json` score-only; readiness continues to come from candidate + risk + reconciliation + launch gate.
- Add tests before implementation for each task.
- Run focused tests, full tests, and one real H91 live run after all tasks are complete.

### Out Of Scope

- Do not rewrite `modules/keyword_protocol.py` tiering logic except for a regression test if needed.
- Do not change `modules/scoring.py` to make a run pass.
- Do not weaken `header_body_rupture`, compliance, risk, or launch-gate checks.
- Do not make fallback description paste-ready.
- Do not let `version_b` failure block final report generation.
- Do not rewrite Step 0-9 or split all of `copy_generation.py` in this iteration.
- Do not merge to `main` until a clean live H91 run and review pass are complete.

### Launch Eligibility Rules

| Field provenance | Meaning | Can enter `LISTING_READY.md`? |
|---|---|---|
| `native_live` | LLM/generated field passed audit without repair | Yes |
| `repaired_live` | LLM/generated field failed surface language audit, was semantically repaired, then passed audit | Yes, with trace |
| `safe_fallback` | Deterministic/local fallback text that is safe but not live/repaired | No, review only |
| `unsafe_fallback` | Fallback or generated text with unresolved compliance/truth/language risk | No |
| `unavailable` | Empty or no eligible field source | No |

---

## File Structure

### New Files

- `/Users/zhoulittlezhou/amazon-listing-skill/modules/canonical_facts.py`
  - Owns normalized facts, claim permissions, field aliases, and fact readiness summaries.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/claim_language_contract.py`
  - Owns forbidden phrase detection, safe replacements, repair prompts/payload helpers, and audit result shape.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/field_provenance.py`
  - Owns `FieldCandidate`, provenance tier calculation, and launch eligibility rules.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/slot_contracts.py`
  - Owns bullet slot contracts, header/body semantic bridge checks, and slot repair input payloads.
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_canonical_facts.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_claim_language_contract.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_field_provenance.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_slot_contracts.py`

### Modified Files

- `/Users/zhoulittlezhou/amazon-listing-skill/tools/preprocess.py`
  - Build and persist `canonical_facts`; compute data quality from fact contracts instead of only legacy column names.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/input_validator.py`
  - Accept localized/business schemas and surface fact-level warnings instead of false old-column errors.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
  - Use claim-language contract in description generation; record field provenance; use canonical facts in description repair; use slot contracts for B5 rerender input.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
  - Select fields using `FieldCandidate` provenance, not only `visible_llm_fallback_fields`.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/listing_candidate.py`
  - Block paste-ready on `safe_fallback`, `unsafe_fallback`, or `unavailable`; allow `repaired_live` with trace.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/readiness_verdict.py`
  - Surface field-provenance blockers in final verdict and report export reasons.
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_generator.py`
  - Include canonical facts and field provenance in operator-facing review output.
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_listing_candidate.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_readiness_verdict.py`
- `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers/plans/INDEX.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/modules/INDEX.md`
- `/Users/zhoulittlezhou/amazon-listing-skill/tests/INDEX.md`

---

## Task 1: Canonical Facts Registry

**Purpose:** Make the system answer one question consistently: what product facts are known, how strong is the evidence, and can each fact be used visibly?

**Files:**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/modules/canonical_facts.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tools/preprocess.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/input_validator.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_canonical_facts.py`

- [ ] **Step 1: Write failing tests for attribute alias normalization**

Add tests that prove raw H91-style fields become canonical facts:

```python
from modules.canonical_facts import build_canonical_facts


def test_h91_attribute_aliases_become_canonical_facts():
    result = build_canonical_facts(
        attribute_data={
            "Video capture resolution": "1080P",
            "Battery Average Life": "150 minutes",
            "Item Weight": "0.1 kg",
            "Included components": "Body Camera, USB Cable (Type-C), 32GB memory card",
            "Water Resistance Leve": "Not Water Resistant",
        },
        supplemental_data={},
        capability_constraints={},
    )

    by_id = {fact["fact_id"]: fact for fact in result["facts"]}
    assert by_id["video_resolution"]["value"] == "1080P"
    assert by_id["battery_life"]["value"] == 150
    assert by_id["battery_life"]["unit"] == "minutes"
    assert by_id["weight"]["value"] == 0.1
    assert by_id["weight"]["unit"] == "kg"
    assert by_id["storage_included"]["value"] == "32GB memory card"
    assert by_id["waterproof_supported"]["value"] is False
    assert by_id["waterproof_supported"]["claim_permission"] == "blocked"
```

- [ ] **Step 2: Write failing tests for fact readiness replacing false 0/4 coverage**

```python
from modules.canonical_facts import summarize_fact_readiness


def test_fact_readiness_treats_explicit_not_waterproof_as_known_boundary():
    facts = {
        "facts": [
            {"fact_id": "video_resolution", "value": "1080P", "confidence": 0.95, "claim_permission": "visible_allowed"},
            {"fact_id": "battery_life", "value": 150, "unit": "minutes", "confidence": 0.95, "claim_permission": "visible_allowed"},
            {"fact_id": "weight", "value": 0.1, "unit": "kg", "confidence": 0.9, "claim_permission": "visible_allowed"},
            {"fact_id": "waterproof_supported", "value": False, "confidence": 0.95, "claim_permission": "blocked"},
        ]
    }

    summary = summarize_fact_readiness(facts, category_type="wearable_body_camera")

    assert summary["required_fact_status"]["waterproof_supported"] == "known_blocked"
    assert summary["blocking_missing_facts"] == []
    assert summary["readiness_score"] >= 80
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd /Users/zhoulittlezhou/amazon-listing-skill
./.venv/bin/pytest tests/test_canonical_facts.py -q
```

Expected: FAIL because `modules.canonical_facts` does not exist.

- [ ] **Step 4: Implement `modules/canonical_facts.py`**

Implement these public functions and data shapes:

```python
def build_canonical_facts(attribute_data: dict, supplemental_data: dict | None = None, capability_constraints: dict | None = None) -> dict:
    """Return {'facts': [...], 'fact_map': {...}, 'warnings': [...]} with normalized fact ids."""


def summarize_fact_readiness(canonical_facts: dict, category_type: str = "generic") -> dict:
    """Return required fact coverage, blocking missing facts, and readiness_score."""
```

Required aliases:

```python
ALIASES = {
    "video_resolution": ["video_resolution", "Video capture resolution", "video capture resolution", "Resolution"],
    "battery_life": ["battery_life", "Battery Average Life", "Battery Life", "runtime"],
    "weight": ["weight", "Item Weight", "item weight", "Product Weight"],
    "included_components": ["included_components", "Included components", "Components Included"],
    "water_resistance": ["water_resistance", "Water Resistance Leve", "Water Resistance Level", "waterproof_depth"],
}
```

Required claim permissions:

```python
visible_allowed: supported fact may appear in title/bullets/description
boundary_only: fact may appear only as limitation or use guidance
blocked: do not make positive visible claim
unknown: missing or weak evidence
```

- [ ] **Step 5: Persist canonical facts in preprocessing output**

Modify `tools/preprocess.py` so preprocessed data includes:

```python
preprocessed_data.canonical_facts
preprocessed_data.fact_readiness
```

Also write the same data into run artifacts where `preprocessed_data.json` is generated.

- [ ] **Step 6: Update input validator schema warnings**

Modify `modules/input_validator.py` so Chinese/business columns are accepted as valid aliases:

```python
keyword: keyword, 关键词
search_volume: search_volume, 月搜索量
review field schema: Bullet_1/Bullet_2 style OR ASIN/Data_Type/Field_Name/Content_Text style
```

Keep validation non-blocking, but add fact-level warnings when canonical facts are missing or conflicting.

- [ ] **Step 7: Run focused tests**

Run:

```bash
./.venv/bin/pytest tests/test_canonical_facts.py -q
```

Expected: PASS.

---

## Task 2: Claim Language Contract and Description Repair

**Purpose:** Stop treating repairable compliance wording as fallback while still blocking unsafe unsupported claims.

**Files:**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/modules/claim_language_contract.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_claim_language_contract.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`

- [ ] **Step 1: Write failing tests for forbidden surface detection**

```python
from modules.claim_language_contract import audit_claim_language


def test_best_is_forbidden_surface_but_usage_intent_is_repairable():
    audit = audit_claim_language("This is the best body camera for travel recording.")

    assert audit["passed"] is False
    assert audit["repairable"] is True
    assert audit["violations"][0]["surface"] == "best"
    assert audit["violations"][0]["reason"] == "unsupported_superlative"
```

- [ ] **Step 2: Write failing tests for deterministic safe rewrite**

```python
from modules.claim_language_contract import repair_claim_language


def test_repair_claim_language_preserves_intent_without_best():
    repaired = repair_claim_language(
        "This is the best body camera for travel recording.",
        canonical_facts={"fact_map": {"video_resolution": {"value": "1080P", "claim_permission": "visible_allowed"}}},
    )

    assert "best" not in repaired.lower()
    assert "travel" in repaired.lower()
    assert "body camera" in repaired.lower()
```

- [ ] **Step 3: Write failing test for description status**

In `tests/test_copy_generation.py`, add a test around the description helper that simulates a candidate containing `best`, then verifies final metadata is not fallback if repair passes:

```python
def test_description_with_repairable_best_becomes_repaired_live_not_fallback(monkeypatch):
    # Use the existing description-generation helper in this file's current style.
    # Monkeypatch the LLM response to return a description containing "best" once.
    # Monkeypatch repair to return clean text.
    # Assert field_generation_trace.description.provenance_tier == "repaired_live".
    # Assert visible_llm_fallback_fields does not include "description".
```

Use actual helper signatures from `copy_generation.py` when implementing this test.

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest tests/test_claim_language_contract.py tests/test_copy_generation.py -q
```

Expected: new claim contract tests fail because module is missing; copy-generation test fails because provenance is not recorded.

- [ ] **Step 5: Implement `claim_language_contract.py`**

Public functions:

```python
def audit_claim_language(text: str, canonical_facts: dict | None = None) -> dict:
    """Return passed, repairable, violations, and blocking_reasons."""


def repair_claim_language(text: str, canonical_facts: dict | None = None) -> str:
    """Apply safe semantic phrase repair for repairable surface violations."""
```

Initial forbidden surfaces:

```python
best -> unsupported_superlative, repairable
better than -> unsupported_comparison, repairable
#1 -> unsupported_superlative, repairable
guaranteed -> guarantee_claim, blocking unless source fact allows
warranty -> warranty_claim, blocking unless source fact allows
waterproof -> truth_sensitive, blocking unless canonical fact permits
```

Safe phrase mapping:

```python
best for -> suitable for
best -> suitable
better than -> designed for
#1 -> compact
```

- [ ] **Step 6: Integrate description audit/repair/re-audit in `copy_generation.py`**

Change description lifecycle:

```text
generate candidate
=> audit_claim_language(candidate)
=> if passed: native_live
=> if repairable: repair_claim_language(candidate), then audit again
=> if repaired audit passes: repaired_live
=> otherwise retry
=> after retry exhaustion: safe_fallback or unsafe_fallback based on audit
```

Do not clear fallback metadata manually. Set provenance first, then derive fallback fields from provenance.

- [ ] **Step 7: Replace internal positive use of literal `Best`**

Change any local guidance constant that says `Best for ...` to safe language such as `Suitable for ...` or `Works well for ...`.

- [ ] **Step 8: Run focused tests**

Run:

```bash
./.venv/bin/pytest tests/test_claim_language_contract.py tests/test_copy_generation.py -q
```

Expected: PASS.

---

## Task 3: Field Provenance and Hybrid Description Eligibility

**Purpose:** Make hybrid field selection understand native, repaired, fallback, and unavailable sources instead of only eligible/not eligible.

**Files:**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/modules/field_provenance.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/listing_candidate.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_field_provenance.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_listing_candidate.py`

- [ ] **Step 1: Write failing tests for provenance tiers**

```python
from modules.field_provenance import build_field_candidate


def test_repaired_live_description_is_launch_eligible():
    candidate = build_field_candidate(
        field="description",
        text="Designed for travel recording with 1080P video.",
        source_version="version_a",
        metadata={"field_provenance": {"description": {"provenance_tier": "repaired_live"}}},
        risk_summary={"listing_status": {"status": "READY_FOR_LISTING"}},
    )

    assert candidate["provenance_tier"] == "repaired_live"
    assert candidate["eligibility"] == "launch_eligible"
```

- [ ] **Step 2: Write failing tests for fallback not paste-ready**

```python
from modules.field_provenance import build_field_candidate


def test_safe_fallback_description_is_review_only():
    candidate = build_field_candidate(
        field="description",
        text="Safe fallback text.",
        source_version="version_a",
        metadata={"visible_llm_fallback_fields": ["description"]},
        risk_summary={"listing_status": {"status": "READY_FOR_LISTING"}},
    )

    assert candidate["provenance_tier"] == "safe_fallback"
    assert candidate["eligibility"] == "review_only"
    assert "fallback_not_launch_eligible" in candidate["blocking_reasons"]
```

- [ ] **Step 3: Write failing hybrid test for no eligible description**

Add or update a test in `tests/test_hybrid_composer.py`:

```python
def test_hybrid_does_not_copy_fallback_description_into_launch_candidate():
    # Build version_a and version_b generated_copy payloads where description text exists
    # but metadata.visible_llm_fallback_fields includes description for both.
    # Compose hybrid.
    # Assert hybrid.metadata.hybrid_sources.description is None.
    # Assert hybrid.metadata.field_provenance.description.eligibility == "blocked" or "review_only".
    # Assert hybrid.description == "" or selected text is clearly review-only and readiness blocks paste-ready.
```

Use the existing test factory style in `tests/test_hybrid_composer.py`.

- [ ] **Step 4: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest tests/test_field_provenance.py tests/test_hybrid_composer.py tests/test_listing_candidate.py -q
```

Expected: field provenance tests fail because module is missing; hybrid test fails because provenance is not structured.

- [ ] **Step 5: Implement `field_provenance.py`**

Public functions:

```python
def build_field_candidate(field: str, text: str | None, source_version: str | None, metadata: dict | None = None, risk_summary: dict | None = None) -> dict:
    """Return field, text_present, source_version, provenance_tier, eligibility, blocking_reasons."""


def select_launch_eligible_field(field: str, candidates: list[dict]) -> dict:
    """Prefer native_live, then repaired_live; never choose safe_fallback for launch eligibility."""
```

Selection order:

```text
native_live > repaired_live > safe_fallback > unsafe_fallback > unavailable
```

Eligibility:

```text
native_live -> launch_eligible if risk pass
repaired_live -> launch_eligible if risk pass
safe_fallback -> review_only
unsafe_fallback -> blocked
unavailable -> blocked
```

- [ ] **Step 6: Integrate into `hybrid_composer.py`**

For `description`, `title`, `aplus_content`, and future visible fields:

```text
build FieldCandidate for version_a field
build FieldCandidate for version_b field
select launch eligible field
write metadata.field_provenance[field]
write metadata.hybrid_sources[field]
if no launch eligible source: record _no_eligible_source[field]
```

Do not let `version_b` become paste-ready by itself; this remains enforced by readiness.

- [ ] **Step 7: Integrate into `listing_candidate.py`**

Paste-ready blockers must include:

```text
field_safe_fallback_not_launch_eligible:<field>
field_unsafe_fallback:<field>
field_unavailable:<field>
```

Allow `repaired_live` when risk and reconciliation pass.

- [ ] **Step 8: Run focused tests**

Run:

```bash
./.venv/bin/pytest tests/test_field_provenance.py tests/test_hybrid_composer.py tests/test_listing_candidate.py -q
```

Expected: PASS.

---

## Task 4: Bullet Slot Contracts and B5 Semantic Repair Boundary

**Purpose:** Prevent B5 header/body rupture by requiring each bullet to use one slot promise, one semantic bridge, and allowed facts.

**Files:**
- Create: `/Users/zhoulittlezhou/amazon-listing-skill/modules/slot_contracts.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/copy_generation.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/hybrid_composer.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_slot_contracts.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_copy_generation.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_hybrid_composer.py`

- [ ] **Step 1: Write failing test for B5 slot contract**

```python
from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract


def test_b5_rejects_multi_topic_package_battery_support_blend():
    contract = build_slot_contract("B5", canonical_facts={"fact_map": {}})
    bullet = (
        "Unbox, Charge, and Start Capturing — The box includes a mini body camera, mount, USB-C cable, "
        "and a 32GB memory card so you can record right out of the box. Supports up to 256GB cards; "
        "150-minute battery powers full adventures. Our support team is ready if you need help."
    )

    result = validate_bullet_against_contract(bullet, contract)

    assert result["passed"] is False
    assert "multiple_primary_promises" in result["reasons"]
```

- [ ] **Step 2: Write passing target-shape test**

```python
from modules.slot_contracts import build_slot_contract, validate_bullet_against_contract


def test_b5_accepts_ready_kit_with_single_semantic_bridge():
    contract = build_slot_contract(
        "B5",
        canonical_facts={
            "fact_map": {
                "included_components": {"value": ["mini body camera", "USB-C cable", "mount", "32GB memory card"], "claim_permission": "visible_allowed"},
                "storage_supported": {"value": "up to 256GB", "claim_permission": "visible_allowed"},
            }
        },
    )
    bullet = (
        "Ready-to-Record Kit — Includes the mini body camera, USB-C cable, mount, and 32GB memory card "
        "so you can start recording after setup. Expand storage with cards up to 256GB for longer trips or daily recording."
    )

    result = validate_bullet_against_contract(bullet, contract)

    assert result["passed"] is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest tests/test_slot_contracts.py -q
```

Expected: FAIL because `modules.slot_contracts` does not exist.

- [ ] **Step 4: Implement `slot_contracts.py`**

Public functions:

```python
def build_slot_contract(slot: str, canonical_facts: dict | None = None, keyword_metadata: dict | None = None) -> dict:
    """Return slot role, allowed facts, forbidden surfaces, and semantic bridge requirements."""


def validate_bullet_against_contract(bullet: str, contract: dict) -> dict:
    """Return passed, reasons, detected_promises, and repair_payload."""
```

Initial B5 contract:

```python
slot_role = "kit_readiness_or_support_boundary"
allowed_primary_promises = ["ready_to_record_kit", "storage_setup", "compatibility_guidance"]
forbidden_surfaces = ["warranty", "guaranteed", "best"]
max_primary_promises = 1
```

- [ ] **Step 5: Feed slot contract failures into rerender plan**

Modify `copy_generation.py` where slot quality/rerender plan is built:

```text
if validate_bullet_against_contract fails:
  add rerender reason slot_contract_failed:<reason>
  include repair_payload with allowed facts and forbidden surfaces
```

Do not rerender all bullets; only repair the failing slot.

- [ ] **Step 6: Ensure hybrid selection sees contract failures**

Modify `hybrid_composer.py` so a version_b slot with `slot_contract_failed` is not selected over a clean version_a slot unless repaired and revalidated.

- [ ] **Step 7: Run focused tests**

Run:

```bash
./.venv/bin/pytest tests/test_slot_contracts.py tests/test_copy_generation.py tests/test_hybrid_composer.py -q
```

Expected: PASS.

---

## Task 5: Readiness Projection and Operator Reporting

**Purpose:** Make final verdict and review report explain exactly why a run is ready, review-only, or blocked.

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/readiness_verdict.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/report_generator.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/run_pipeline.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_readiness_verdict.py`
- Test: `/Users/zhoulittlezhou/amazon-listing-skill/tests/integration/test_run_pipeline_wrapper.py`

- [ ] **Step 1: Write failing test for `safe_fallback` review-only projection**

```python
def test_safe_fallback_candidate_exports_review_required_not_listing_ready():
    # Build candidate with field_provenance.description.provenance_tier = safe_fallback.
    # Build final verdict.
    # Assert operational_listing_status == "NOT_READY_FOR_LISTING" or "LISTING_REVIEW_REQUIRED" per current enum.
    # Assert launch_gate.passed is False.
    # Assert reasons include "description_safe_fallback_not_launch_eligible".
```

Use the exact candidate factory already present in `tests/test_readiness_verdict.py`.

- [ ] **Step 2: Write failing test for `repaired_live` launch eligibility**

```python
def test_repaired_live_description_can_be_paste_ready_when_risk_and_reconciliation_pass():
    # Build candidate with description provenance repaired_live, risk READY, reconciliation complete.
    # Assert no description fallback blocker is emitted.
    # Assert verdict may pass if all other gates pass.
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest tests/test_readiness_verdict.py tests/integration/test_run_pipeline_wrapper.py -q
```

Expected: FAIL because verdict does not yet understand field provenance details.

- [ ] **Step 4: Update readiness verdict reason model**

Add explicit reason codes:

```text
description_repaired_live
field_safe_fallback_not_launch_eligible:<field>
field_unsafe_fallback:<field>
field_unavailable:<field>
slot_contract_failed:<slot>:<reason>
canonical_fact_missing:<fact_id>
canonical_fact_blocked_claim:<fact_id>
```

- [ ] **Step 5: Update report output**

`LISTING_REVIEW_REQUIRED.md` should include a short block:

```markdown
## Field Provenance
- description: safe_fallback -> review only, reason: fallback_not_launch_eligible
- bullet_5: slot_contract_failed -> multiple_primary_promises

## Canonical Fact Readiness
- video_resolution: visible_allowed, source: attribute_table
- battery_life: visible_allowed, source: attribute_table
- waterproof_supported: blocked positive claim, source: attribute_table
```

`LISTING_READY.md` should include repaired-live trace when applicable:

```markdown
- description: repaired_live, repaired: unsupported_superlative
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
./.venv/bin/pytest tests/test_readiness_verdict.py tests/integration/test_run_pipeline_wrapper.py -q
```

Expected: PASS.

---

## Task 6: Regression Tests for Keyword Protocol Non-Regression

**Purpose:** Prove this refactor does not regress the completed L1/L2/L3 and blue-ocean logic.

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_keyword_protocol.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_writing_policy.py`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/test_blueprint_generator.py`

- [ ] **Step 1: Add test that blue-ocean does not replace L1 head term**

```python
def test_blue_ocean_bullet_term_does_not_replace_l1_title_anchor():
    rows = [
        {"keyword": "body camera", "search_volume": 25000, "conversion_rate": 0.017, "click_share": 0.1, "product_count": 3000, "title_density": 0.8, "product_fit_score": 0.96},
        {"keyword": "body camera with audio", "search_volume": 7600, "conversion_rate": 0.028, "click_share": 0.08, "product_count": 300, "title_density": 0.25, "product_fit_score": 0.92},
    ]
    protocol = build_keyword_protocol(rows, country="US", category_type="wearable_body_camera")
    meta = {row["keyword"]: row for row in protocol["keyword_metadata"]}

    assert meta["body camera"]["routing_role"] == "title"
    assert meta["body camera with audio"]["routing_role"] == "bullet"
```

- [ ] **Step 2: Run keyword tests**

Run:

```bash
./.venv/bin/pytest tests/test_keyword_protocol.py tests/test_writing_policy.py tests/test_blueprint_generator.py -q
```

Expected: PASS.

---

## Task 7: Index and Documentation Updates

**Purpose:** Keep repo docs/indexes aligned with new files and explain the operator-visible contract.

**Files:**
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/modules/INDEX.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/tests/INDEX.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers/plans/INDEX.md`
- Modify: `/Users/zhoulittlezhou/amazon-listing-skill/docs/superpowers/INDEX.md`

- [ ] **Step 1: Update module index**

Add rows for:

```text
canonical_facts.py | 产品事实标准化、claim permission 与 fact readiness
claim_language_contract.py | 合规语言合同、违规表面词审计与语义修复
field_provenance.py | 字段来源等级、fallback 语义与 launch eligibility
slot_contracts.py | bullet slot 责任、header/body 同源语义与修复 payload
```

- [ ] **Step 2: Update tests index**

Add rows for the new test files and their purpose.

- [ ] **Step 3: Update plans index**

Add this file to the tree and file table.

- [ ] **Step 4: Run index/doc smoke check**

Run:

```bash
rg -n "canonical_facts|claim_language_contract|field_provenance|slot_contracts" modules/INDEX.md tests/INDEX.md docs/superpowers/plans/INDEX.md docs/superpowers/INDEX.md
```

Expected: each new module and test appears in the relevant index.

---

## Task 8: Verification and Live H91 Run

**Purpose:** Prove the refactor works in tests and with real H91 live data.

**Files:**
- No planned code changes in this task.
- Artifacts generated under `/Users/zhoulittlezhou/amazon-listing-skill/output/runs/`.

- [ ] **Step 1: Run focused contract tests**

Run:

```bash
./.venv/bin/pytest \
  tests/test_canonical_facts.py \
  tests/test_claim_language_contract.py \
  tests/test_field_provenance.py \
  tests/test_slot_contracts.py \
  tests/test_copy_generation.py \
  tests/test_hybrid_composer.py \
  tests/test_listing_candidate.py \
  tests/test_readiness_verdict.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```bash
./.venv/bin/pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Run real H91 live dual-version validation**

Run:

```bash
RUN_ID="r44_field_contracts_live_$(date +%Y%m%d_%H%M%S)"
./.venv/bin/python run_pipeline.py --product H91lite --market US --run-id "$RUN_ID" --dual-version --fresh
```

Expected:

```text
version_a completes or produces reviewable artifact
version_b completes or records experimental failure without blocking final report
final_readiness_verdict.json exists
LISTING_READY.md exists only if launch gate passed
LISTING_REVIEW_REQUIRED.md exists if any safe_fallback, unavailable field, slot rupture, or risk blocker remains
```

- [ ] **Step 4: Inspect field provenance and canonical facts in live artifact**

Run:

```bash
LATEST="$(ls -td output/runs/H91lite_US_r44_field_contracts_live_* | head -1)"
./.venv/bin/python - <<'PY'
import json, os, pathlib
run = pathlib.Path(os.environ["LATEST"])
for rel in ["final_readiness_verdict.json", "hybrid/generated_copy.json", "version_a/generated_copy.json", "version_b/generated_copy.json"]:
    p = run / rel
    print("\n##", rel, p.exists())
    if p.exists():
        data = json.loads(p.read_text())
        if rel == "final_readiness_verdict.json":
            print("operational", data.get("operational_listing_status"))
            print("launch", data.get("launch_gate"))
        else:
            meta = data.get("metadata", {})
            print("field_provenance", meta.get("field_provenance"))
            print("canonical_fact_readiness", meta.get("canonical_fact_readiness"))
PY
```

Expected:

```text
description provenance is native_live or repaired_live for READY
safe_fallback/unavailable description blocks LISTING_READY
B5 slot contract failure is absent for READY
canonical fact readiness explains attribute/accessory status
```

- [ ] **Step 5: Write final launch-gap summary**

If not ready, summarize blockers in plain Chinese:

```text
还不能上线的具体原因：
1. description 是 safe_fallback / unavailable / unsafe_fallback
2. B5 slot_contract_failed: <reason>
3. canonical fact missing/conflict: <fact_id>
4. risk blocker: <reason>
```

If ready, summarize:

```text
可以进入合并评审：测试通过，H91 live 通过，LISTING_READY.md 生成，description 非 fallback，B5 无 semantic rupture，canonical facts 和 keyword reconciliation complete。
```

---

## Execution Order and Checkpoints

1. Task 1 creates the fact truth layer. Stop after Task 1 if H91 facts still cannot be normalized.
2. Task 2 fixes description lifecycle. Stop after Task 2 if `best` still becomes fallback instead of `repaired_live`.
3. Task 3 fixes hybrid field selection. Stop after Task 3 if fallback description can still enter paste-ready.
4. Task 4 fixes B5 slot contract. Stop after Task 4 if B5 rupture is only detected at final risk instead of slot quality.
5. Task 5 updates readiness/reporting. Stop after Task 5 if verdict and export disagree.
6. Task 6 protects keyword protocol. Stop if any L1/L2/L3 or blue-ocean regression appears.
7. Task 7 updates indexes.
8. Task 8 runs full verification and real H91 live.

## Success Criteria

- `keyword_protocol` tests still pass with existing blue-ocean semantics.
- Description containing repairable `best` becomes `repaired_live`, not `fallback`.
- Fallback description is never paste-ready.
- Hybrid does not produce empty description silently; it records unavailable/review-only blockers.
- B5 with multiple primary promises is rejected before final readiness.
- H91 data quality reflects canonical facts instead of false old-column misses.
- `LISTING_READY.md` is generated only when operational launch gate passes.
- Full test suite passes.
- A fresh H91 live run produces clear readiness artifacts.

## Commit Strategy

Commit after each task if tests pass:

```bash
git add <task files>
git commit -m "feat: add canonical listing fact contracts"
git commit -m "feat: repair description compliance language"
git commit -m "feat: gate hybrid fields by provenance"
git commit -m "feat: validate bullet slot contracts"
git commit -m "feat: surface readiness provenance blockers"
git commit -m "test: protect keyword protocol routing semantics"
git commit -m "docs: index field contract plan"
```

Do not merge to `main` until Task 8 is complete and the user approves the live-run result.
