# Amazon AI Operating System Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current listing pipeline into an evidence-aware, market-aware, intent-learning Amazon AI Operating System without breaking the existing generation, retention, and review workflows.

**Architecture:** Preserve the current pipeline centered on `tools/preprocess.py`, `modules/intent_translator.py`, `modules/writing_policy.py`, `modules/copy_generation.py`, `modules/scoring.py`, and `modules/report_generator.py`. Add sidecar modules for entity profiling, evidence auditing, question-bank routing, market packs, compute tiering, and intent-weight write-back; inject them at existing pipeline boundaries instead of rewriting the whole stack.

**Tech Stack:** Python 3, dataclasses/dicts, JSON config in `config/`, pytest, existing Streamlit app, run artifacts in `output/runs/`.

---

## File Structure Lock-In

### New runtime modules
- Create: `modules/entity_profile.py`
- Create: `modules/evidence_engine.py`
- Create: `modules/question_bank.py`
- Create: `modules/market_packs.py`
- Create: `modules/compute_tiering.py`
- Create: `modules/intent_weights.py`

### New config assets
- Create: `config/market_packs/DE.json`
- Create: `config/market_packs/FR.json`
- Create: `config/market_packs/IT.json`
- Create: `config/market_packs/ES.json`
- Create: `config/market_packs/UK.json`
- Create: `config/question_banks/action_camera.json`
- Create: `config/question_banks/eu_compliance.json`

### Existing pipeline files to extend
- Modify: `tools/preprocess.py`
- Modify: `main.py`
- Modify: `modules/intent_translator.py`
- Modify: `modules/writing_policy.py`
- Modify: `modules/copy_generation.py`
- Modify: `modules/scoring.py`
- Modify: `modules/report_generator.py`
- Modify: `app/services/run_service.py`
- Modify: `app/streamlit_app.py`

### Tests to add
- Create: `tests/unit/test_entity_profile.py`
- Create: `tests/unit/test_evidence_engine.py`
- Create: `tests/unit/test_question_bank.py`
- Create: `tests/unit/test_market_packs.py`
- Create: `tests/unit/test_compute_tiering.py`
- Create: `tests/unit/test_intent_weights.py`
- Create: `tests/integration/test_evidence_pipeline.py`
- Modify: `tests/test_copy_generation.py`
- Modify: `tests/test_feedback_loop.py`
- Modify: `tests/test_retention_guard.py`
- Modify: `tests/test_streamlit_services.py`

### Delivery sequence
1. P0 foundations and schemas
2. P0 evidence + FAQ + market pack integration
3. P0 compute tier visibility
4. P1 intent weight write-back
5. P1 report/Streamlit visibility and integration tests

### Task 1: Freeze data contracts and fixtures

**Files:**
- Create: `modules/entity_profile.py`
- Create: `modules/evidence_engine.py`
- Create: `modules/market_packs.py`
- Create: `modules/compute_tiering.py`
- Create: `modules/intent_weights.py`
- Test: `tests/unit/test_entity_profile.py`
- Test: `tests/unit/test_evidence_engine.py`
- Test: `tests/unit/test_market_packs.py`
- Test: `tests/unit/test_compute_tiering.py`
- Test: `tests/unit/test_intent_weights.py`

- [ ] **Step 1: Write contract tests for new payloads**

```python
from modules.entity_profile import build_entity_profile
from modules.evidence_engine import build_evidence_bundle
from modules.market_packs import load_market_pack


def test_entity_profile_contains_core_sections(sample_preprocessed_data):
    profile = build_entity_profile(sample_preprocessed_data)
    assert set(profile) >= {
        "product_code",
        "core_specs",
        "capability_registry",
        "accessory_registry",
        "claim_registry",
        "compliance_constraints",
        "evidence_refs",
    }


def test_evidence_bundle_contains_support_matrix(sample_preprocessed_data):
    bundle = build_evidence_bundle(sample_preprocessed_data, {"claim_registry": []})
    assert set(bundle) >= {
        "attribute_evidence",
        "review_positive_clusters",
        "review_negative_clusters",
        "qa_clusters",
        "claim_support_matrix",
        "rufus_readiness",
    }


def test_market_pack_loader_returns_default_shape_for_de():
    pack = load_market_pack("DE")
    assert pack["locale"] == "DE"
    assert "lexical_preferences" in pack
    assert "faq_templates" in pack
```

- [ ] **Step 2: Run the contract tests and verify they fail**

Run: `pytest tests/unit/test_entity_profile.py tests/unit/test_evidence_engine.py tests/unit/test_market_packs.py tests/unit/test_compute_tiering.py tests/unit/test_intent_weights.py -v`
Expected: FAIL with import errors or missing function definitions.

- [ ] **Step 3: Create module skeletons with stable interfaces**

```python
# modules/entity_profile.py
from __future__ import annotations
from typing import Any, Dict


def build_entity_profile(preprocessed_data: Any) -> Dict[str, Any]:
    return {}
```

```python
# modules/evidence_engine.py
from __future__ import annotations
from typing import Any, Dict


def build_evidence_bundle(preprocessed_data: Any, entity_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {}
```

```python
# modules/market_packs.py
from __future__ import annotations
from typing import Any, Dict


def load_market_pack(country_code: str) -> Dict[str, Any]:
    return {"locale": country_code, "lexical_preferences": [], "faq_templates": []}
```

- [ ] **Step 4: Re-run the tests and verify imports now pass but assertions fail**

Run: `pytest tests/unit/test_entity_profile.py tests/unit/test_evidence_engine.py tests/unit/test_market_packs.py -v`
Expected: FAIL on missing required keys rather than import errors.

- [ ] **Step 5: Commit the interface freeze**

```bash
git add modules/entity_profile.py modules/evidence_engine.py modules/market_packs.py modules/compute_tiering.py modules/intent_weights.py tests/unit/test_entity_profile.py tests/unit/test_evidence_engine.py tests/unit/test_market_packs.py tests/unit/test_compute_tiering.py tests/unit/test_intent_weights.py
git commit -m "test: freeze contracts for evidence and market pack modules"
```

### Task 2: Build the ASIN entity profile in preprocessing

**Files:**
- Modify: `tools/preprocess.py`
- Create: `modules/entity_profile.py`
- Modify: `main.py`
- Test: `tests/unit/test_entity_profile.py`
- Test: `tests/integration/test_evidence_pipeline.py`

- [ ] **Step 1: Add failing tests for profile normalization and persistence**

```python
def test_build_entity_profile_maps_specs_accessories_and_claims(sample_preprocessed_data):
    profile = build_entity_profile(sample_preprocessed_data)
    assert profile["core_specs"]["runtime_minutes"]
    assert profile["accessory_registry"]
    assert profile["claim_registry"]


def test_pipeline_persists_asin_entity_profile(tmp_path, sample_run_config):
    result = run_pipeline(sample_run_config)
    assert (tmp_path / "output" / "runs" / "sample" / "asin_entity_profile.json").exists()
```

- [ ] **Step 2: Implement the entity profile builder**

```python
def build_entity_profile(preprocessed_data: Any) -> Dict[str, Any]:
    constraints = getattr(preprocessed_data, "capability_constraints", {}) or {}
    return {
        "product_code": getattr(getattr(preprocessed_data, "run_config", None), "product_code", ""),
        "core_specs": {
            "runtime_minutes": constraints.get("runtime_minutes"),
            "waterproof_depth_m": constraints.get("waterproof_depth_m"),
            "waterproof_requires_case": constraints.get("waterproof_requires_case"),
        },
        "capability_registry": _extract_capabilities(preprocessed_data),
        "accessory_registry": _extract_accessories(preprocessed_data),
        "claim_registry": _seed_claim_registry(preprocessed_data),
        "compliance_constraints": _extract_compliance(preprocessed_data),
        "evidence_refs": [],
    }
```

- [ ] **Step 3: Inject profile generation into preprocessing output and run persistence**

```python
# tools/preprocess.py
entity_profile = build_entity_profile(preprocessed_data)
preprocessed_payload["asin_entity_profile"] = entity_profile

# main.py
_write_json(run_dir / "asin_entity_profile.json", preprocessed_data.asin_entity_profile)
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/unit/test_entity_profile.py tests/integration/test_evidence_pipeline.py -v`
Expected: PASS with profile keys and run artifact written.

- [ ] **Step 5: Commit the profile foundation**

```bash
git add tools/preprocess.py main.py modules/entity_profile.py tests/unit/test_entity_profile.py tests/integration/test_evidence_pipeline.py
git commit -m "feat: add asin entity profile generation"
```

### Task 3: Build the evidence bundle and claim-support audit

**Files:**
- Create: `modules/evidence_engine.py`
- Modify: `modules/copy_generation.py`
- Modify: `modules/scoring.py`
- Modify: `modules/report_generator.py`
- Test: `tests/unit/test_evidence_engine.py`
- Test: `tests/integration/test_evidence_pipeline.py`

- [ ] **Step 1: Write failing tests for support classification**

```python
def test_claim_support_matrix_marks_supported_and_unsupported_claims(sample_preprocessed_data, sample_entity_profile):
    bundle = build_evidence_bundle(sample_preprocessed_data, sample_entity_profile)
    statuses = {row["claim"]: row["support_status"] for row in bundle["claim_support_matrix"]}
    assert statuses["waterproof dive use"] == "supported"
    assert statuses["works in freezing storms"] == "unsupported"
```

- [ ] **Step 2: Implement evidence clustering and support matrix generation**

```python
def build_evidence_bundle(preprocessed_data: Any, entity_profile: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "attribute_evidence": _extract_attribute_evidence(preprocessed_data),
        "review_positive_clusters": _cluster_review_topics(preprocessed_data, polarity="positive"),
        "review_negative_clusters": _cluster_review_topics(preprocessed_data, polarity="negative"),
        "qa_clusters": _cluster_qa_topics(preprocessed_data),
        "claim_support_matrix": _build_claim_support_matrix(entity_profile, preprocessed_data),
        "rufus_readiness": _build_rufus_readiness(entity_profile, preprocessed_data),
    }
```

- [ ] **Step 3: Wire the audit into scoring and report generation**

```python
# modules/scoring.py
evidence_bundle = generated_copy.get("evidence_bundle", {}) or {}
rufus_readiness = (evidence_bundle.get("rufus_readiness") or {}).get("score", 0)

# modules/report_generator.py
lines.append("### Evidence Alignment")
for row in evidence_bundle.get("claim_support_matrix", [])[:8]:
    lines.append(f"- {row['claim']}: {row['support_status']}")
```

- [ ] **Step 4: Ensure copy payload carries the evidence artifact through the pipeline**

```python
# modules/copy_generation.py
result["evidence_bundle"] = evidence_bundle
metadata["unsupported_claim_count"] = unsupported_claim_count
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/unit/test_evidence_engine.py tests/integration/test_evidence_pipeline.py tests/test_copy_generation.py -v`
Expected: PASS with evidence bundle persisted and surfaced.

```bash
git add modules/evidence_engine.py modules/copy_generation.py modules/scoring.py modules/report_generator.py tests/unit/test_evidence_engine.py tests/integration/test_evidence_pipeline.py tests/test_copy_generation.py
git commit -m "feat: add claim support audit and evidence bundle"
```

### Task 4: Add question-bank driven Rufus FAQ seeding

**Files:**
- Create: `modules/question_bank.py`
- Create: `config/question_banks/action_camera.json`
- Create: `config/question_banks/eu_compliance.json`
- Modify: `modules/copy_generation.py`
- Modify: `modules/report_generator.py`
- Test: `tests/unit/test_question_bank.py`
- Modify: `tests/test_copy_generation.py`

- [ ] **Step 1: Write failing tests for question-bank loading and FAQ prioritization**

```python
from modules.question_bank import build_question_bank_context


def test_question_bank_returns_action_camera_templates(sample_entity_profile):
    context = build_question_bank_context(sample_entity_profile, "DE")
    assert any("battery" in item["topic"] for item in context["questions"])
    assert any(item["market"] == "DE" for item in context["questions"])
```

- [ ] **Step 2: Add baseline question-bank assets**

```json
{
  "category": "action_camera",
  "questions": [
    {"topic": "battery_in_cold_weather", "question": "Can it record reliably in cold outdoor conditions?", "priority": "high"},
    {"topic": "waterproof_limit", "question": "Does waterproof use require the case and what is the depth limit?", "priority": "high"}
  ]
}
```

- [ ] **Step 3: Implement loader and context builder**

```python
def build_question_bank_context(entity_profile: Dict[str, Any], country_code: str) -> Dict[str, Any]:
    base = _load_bank("action_camera")
    market = _load_bank("eu_compliance") if country_code in {"DE", "FR", "IT", "ES", "UK"} else {"questions": []}
    return {
        "questions": _rank_questions(base["questions"] + market["questions"], entity_profile),
        "evidence_hints": _derive_evidence_hints(entity_profile),
    }
```

- [ ] **Step 4: Feed the question bank into FAQ generation and reporting**

```python
# modules/copy_generation.py
question_bank_context = build_question_bank_context(entity_profile, target_country)
payload["question_bank_context"] = question_bank_context
fallback_faq = _compose_faq_fallback(preprocessed_data, directives, faq_only_capabilities, language, question_bank_context)

# modules/report_generator.py
lines.append("### Rufus Question Coverage")
for item in question_bank_context.get("questions", [])[:5]:
    lines.append(f"- {item['topic']}: queued")
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/unit/test_question_bank.py tests/test_copy_generation.py -v`
Expected: PASS with market-aware FAQ seeding.

```bash
git add modules/question_bank.py config/question_banks/action_camera.json config/question_banks/eu_compliance.json modules/copy_generation.py modules/report_generator.py tests/unit/test_question_bank.py tests/test_copy_generation.py
git commit -m "feat: seed faq generation with rufus question bank"
```

### Task 5: Implement EU market packs and apply them to policy generation

**Files:**
- Create: `config/market_packs/DE.json`
- Create: `config/market_packs/FR.json`
- Create: `config/market_packs/IT.json`
- Create: `config/market_packs/ES.json`
- Create: `config/market_packs/UK.json`
- Create: `modules/market_packs.py`
- Modify: `modules/intent_translator.py`
- Modify: `modules/writing_policy.py`
- Modify: `modules/report_generator.py`
- Test: `tests/unit/test_market_packs.py`

- [ ] **Step 1: Write failing tests for pack loading and policy overlays**

```python
def test_writing_policy_uses_market_pack_overrides(sample_preprocessed_data):
    policy = generate_writing_policy(sample_preprocessed_data, "German")
    assert policy["market_pack"]["locale"] == "DE"
    assert policy["market_pack"]["compliance_reminders"]
```

- [ ] **Step 2: Add market-pack configs with minimal stable schema**

```json
{
  "locale": "DE",
  "lexical_preferences": ["action kamera", "fahrradhelm kamera"],
  "compound_word_rules": ["prefer_compound_noun_forms_for_mounting_terms"],
  "compliance_reminders": ["avoid unsupported battery safety guarantees"],
  "faq_templates": ["compatibility", "cold_weather", "waterproof_limit"]
}
```

- [ ] **Step 3: Implement loader and overlay helpers**

```python
def apply_market_pack(base_policy: Dict[str, Any], market_pack: Dict[str, Any]) -> Dict[str, Any]:
    base_policy["market_pack"] = market_pack
    base_policy["compliance_directives"] = {
        **(base_policy.get("compliance_directives") or {}),
        "market_pack_reminders": market_pack.get("compliance_reminders", []),
    }
    return base_policy
```

- [ ] **Step 4: Inject packs into translator and writing policy**

```python
# modules/writing_policy.py
market_pack = load_market_pack(target_country)
policy = apply_market_pack(policy, market_pack)

# modules/intent_translator.py
intent_graph_metadata["market_pack_locale"] = market_pack.get("locale")
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/unit/test_market_packs.py tests/test_copy_generation.py tests/integration/test_evidence_pipeline.py -v`
Expected: PASS with country-specific pack data in the policy.

```bash
git add config/market_packs/DE.json config/market_packs/FR.json config/market_packs/IT.json config/market_packs/ES.json config/market_packs/UK.json modules/market_packs.py modules/intent_translator.py modules/writing_policy.py modules/report_generator.py tests/unit/test_market_packs.py
git commit -m "feat: add eu market packs and policy overlays"
```

### Task 6: Add field-level compute tier maps and rerun signals

**Files:**
- Create: `modules/compute_tiering.py`
- Modify: `modules/copy_generation.py`
- Modify: `modules/report_generator.py`
- Modify: `modules/scoring.py`
- Test: `tests/unit/test_compute_tiering.py`
- Modify: `tests/test_production_guardrails.py`

- [ ] **Step 1: Write failing tests for field-level tier rendering**

```python
from modules.compute_tiering import build_compute_tier_map


def test_compute_tier_map_marks_fallback_fields(sample_generated_copy):
    tier_map = build_compute_tier_map(sample_generated_copy)
    assert tier_map["title"]["tier_used"] in {"native", "polish", "rule_based"}
    assert "rerun_recommended" in tier_map["bullet_1"]
```

- [ ] **Step 2: Implement tier map construction from existing metadata**

```python
def build_compute_tier_map(generated_copy: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    metadata = generated_copy.get("metadata", {}) or {}
    visible_fallbacks = set(metadata.get("visible_llm_fallback_fields") or [])
    tier_map = {}
    for field in ["title", "description", "search_terms", "aplus_content", "bullet_1", "bullet_2", "bullet_3", "bullet_4", "bullet_5"]:
        tier_map[field] = {
            "tier_used": "rule_based" if field in visible_fallbacks else "native",
            "fallback_reason": "llm_fallback" if field in visible_fallbacks else "",
            "rerun_recommended": field in visible_fallbacks,
            "rerun_priority": "high" if field in {"title", "bullet_1", "bullet_2"} and field in visible_fallbacks else "normal",
        }
    return tier_map
```

- [ ] **Step 3: Persist tier map and expose it to scoring/reporting**

```python
# modules/copy_generation.py
result["compute_tier_map"] = build_compute_tier_map(result)

# modules/report_generator.py
for field, info in compute_tier_map.items():
    lines.append(f"- [{field}: {info['tier_used']}] rerun={info['rerun_recommended']}")
```

- [ ] **Step 4: Add scoring hooks for fallback density**

```python
fallback_count = sum(1 for item in compute_tier_map.values() if item["tier_used"] == "rule_based")
production_readiness["fallback_density"] = fallback_count
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/unit/test_compute_tiering.py tests/test_production_guardrails.py tests/test_copy_generation.py -v`
Expected: PASS with compute tier map rendered and scored.

```bash
git add modules/compute_tiering.py modules/copy_generation.py modules/report_generator.py modules/scoring.py tests/unit/test_compute_tiering.py tests/test_production_guardrails.py
git commit -m "feat: add field-level compute tier reporting"
```

### Task 7: Add intent weight ingestion and write-back

**Files:**
- Create: `modules/intent_weights.py`
- Modify: `modules/feedback_loop.py`
- Modify: `modules/retention_guard.py`
- Modify: `modules/writing_policy.py`
- Modify: `app/streamlit_app.py`
- Test: `tests/unit/test_intent_weights.py`
- Modify: `tests/test_feedback_loop.py`
- Modify: `tests/test_retention_guard.py`

- [ ] **Step 1: Write failing tests for weight snapshot calculation**

```python
from modules.intent_weights import build_intent_weight_snapshot


def test_build_intent_weight_snapshot_promotes_high_ctr_scene_terms():
    rows = [{"keyword": "helmet camera", "ctr": 0.12, "cvr": 0.08, "scene": "cycling_recording", "capability": "hands_free"}]
    snapshot = build_intent_weight_snapshot(rows)
    assert snapshot["weights"][0]["scene_weight"] > 0
    assert snapshot["weights"][0]["conversion_weight"] > 0
```

- [ ] **Step 2: Implement the write-back model and snapshot persistence**

```python
def build_intent_weight_snapshot(rows: list[dict]) -> dict:
    weights = []
    for row in rows:
        weights.append({
            "keyword": row["keyword"],
            "scene": row.get("scene", ""),
            "capability": row.get("capability", ""),
            "traffic_weight": row.get("ctr", 0),
            "conversion_weight": row.get("cvr", 0),
            "scene_weight": row.get("ctr", 0) * 0.6 + row.get("cvr", 0) * 0.4,
            "confidence_score": 1.0 if row.get("orders", 0) else 0.5,
        })
    return {"weights": weights}
```

- [ ] **Step 3: Overlay weight snapshot into writing policy without breaking retention**

```python
# modules/writing_policy.py
intent_weight_snapshot = getattr(preprocessed_data, "intent_weight_snapshot", {}) or {}
policy["intent_weight_snapshot"] = intent_weight_snapshot
policy = apply_intent_weight_overrides(policy, retention_strategy, intent_weight_snapshot)
```

- [ ] **Step 4: Add Streamlit upload/review entry point for performance snapshots**

```python
# app/streamlit_app.py
uploaded_metrics = st.file_uploader("上传 PPC / Search Term / CTR-CVR 反馈", type=["csv", "xlsx"], key="intent_weight_upload")
if uploaded_metrics:
    snapshot = save_intent_weight_snapshot(...)
    st.success(f"Intent weight snapshot saved: {snapshot}")
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/unit/test_intent_weights.py tests/test_feedback_loop.py tests/test_retention_guard.py tests/test_streamlit_services.py -v`
Expected: PASS with weight snapshot persistence and policy overlay.

```bash
git add modules/intent_weights.py modules/feedback_loop.py modules/retention_guard.py modules/writing_policy.py app/streamlit_app.py tests/unit/test_intent_weights.py tests/test_feedback_loop.py tests/test_retention_guard.py tests/test_streamlit_services.py
git commit -m "feat: add intent weight snapshot write-back"
```

### Task 8: Surface evidence, market, and weight intelligence in reports and services

**Files:**
- Modify: `modules/report_generator.py`
- Modify: `app/services/run_service.py`
- Modify: `app/streamlit_app.py`
- Test: `tests/test_streamlit_services.py`
- Test: `tests/integration/test_evidence_pipeline.py`

- [ ] **Step 1: Add failing tests for report sections and service payloads**

```python
def test_run_service_returns_evidence_and_compute_summary(tmp_path):
    result = run_workspace_workflow("config.json", str(tmp_path), steps=[0])
    assert "evidence_summary" in result
    assert "compute_tier_summary" in result
```

- [ ] **Step 2: Extend report sections with operator-facing summaries**

```python
lines.extend([
    "### Evidence Summary",
    f"- Unsupported claims: {unsupported_claim_count}",
    f"- Rufus readiness: {rufus_score}",
    f"- Market pack: {market_pack_locale}",
    f"- Intent weight updates: {intent_weight_delta_count}",
])
```

- [ ] **Step 3: Add service payload summaries for Streamlit**

```python
result["evidence_summary"] = summarize_evidence_bundle(evidence_bundle)
result["compute_tier_summary"] = summarize_compute_tier_map(compute_tier_map)
result["intent_weight_summary"] = summarize_intent_weight_snapshot(intent_weight_snapshot)
```

- [ ] **Step 4: Add Streamlit panels for the new summaries**

```python
st.metric("Unsupported Claims", result["evidence_summary"]["unsupported_claim_count"])
st.metric("Fallback Fields", result["compute_tier_summary"]["fallback_field_count"])
st.metric("Intent Weight Updates", result["intent_weight_summary"]["updated_keyword_count"])
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_streamlit_services.py tests/integration/test_evidence_pipeline.py -v`
Expected: PASS with summaries visible in service payloads and report output.

```bash
git add modules/report_generator.py app/services/run_service.py app/streamlit_app.py tests/test_streamlit_services.py tests/integration/test_evidence_pipeline.py
git commit -m "feat: expose evidence and compute summaries to operators"
```

### Task 9: Add backward-compatibility coverage and migration safeguards

**Files:**
- Modify: `tools/preprocess.py`
- Modify: `modules/market_packs.py`
- Modify: `modules/question_bank.py`
- Modify: `modules/intent_weights.py`
- Test: `tests/integration/test_evidence_pipeline.py`
- Modify: `tests/test_copy_generation.py`

- [ ] **Step 1: Write failing tests for no-feedback/no-market-pack/no-review cases**

```python
def test_pipeline_degrades_gracefully_without_feedback_or_reviews(sample_preprocessed_data):
    sample_preprocessed_data.feedback_context = {}
    sample_preprocessed_data.review_data = {}
    profile = build_entity_profile(sample_preprocessed_data)
    bundle = build_evidence_bundle(sample_preprocessed_data, profile)
    assert bundle["claim_support_matrix"] == [] or isinstance(bundle["claim_support_matrix"], list)
```

- [ ] **Step 2: Implement empty-state defaults in sidecar modules**

```python
def load_market_pack(country_code: str) -> Dict[str, Any]:
    if not pack_path.exists():
        return _default_market_pack(country_code)
```

```python
def build_question_bank_context(entity_profile: Dict[str, Any], country_code: str) -> Dict[str, Any]:
    return {"questions": [], "evidence_hints": []} if not entity_profile else _build_context(entity_profile, country_code)
```

- [ ] **Step 3: Guard pipeline writes so existing runs do not fail on missing data**

```python
result["intent_weight_snapshot"] = intent_weight_snapshot or {"weights": []}
result["compute_tier_map"] = compute_tier_map or {}
```

- [ ] **Step 4: Run compatibility suite**

Run: `pytest tests/test_copy_generation.py tests/integration/test_evidence_pipeline.py tests/test_retention_guard.py -v`
Expected: PASS with sparse-input runs staying alive.

- [ ] **Step 5: Commit compatibility fixes**

```bash
git add tools/preprocess.py modules/market_packs.py modules/question_bank.py modules/intent_weights.py tests/integration/test_evidence_pipeline.py tests/test_copy_generation.py tests/test_retention_guard.py
git commit -m "fix: preserve backward compatibility for sparse evidence inputs"
```

### Task 10: Run the full verification suite and document rollout readiness

**Files:**
- Modify: `docs/progress/2026-04-13_amazon_ai_operating_system_rollout.md`
- Test: `tests/unit/test_entity_profile.py`
- Test: `tests/unit/test_evidence_engine.py`
- Test: `tests/unit/test_question_bank.py`
- Test: `tests/unit/test_market_packs.py`
- Test: `tests/unit/test_compute_tiering.py`
- Test: `tests/unit/test_intent_weights.py`
- Test: `tests/integration/test_evidence_pipeline.py`
- Modify: `tests/test_copy_generation.py`
- Modify: `tests/test_feedback_loop.py`
- Modify: `tests/test_retention_guard.py`
- Modify: `tests/test_streamlit_services.py`
- Modify: `tests/test_production_guardrails.py`

- [ ] **Step 1: Run all new unit and integration tests**

Run: `pytest tests/unit/test_entity_profile.py tests/unit/test_evidence_engine.py tests/unit/test_question_bank.py tests/unit/test_market_packs.py tests/unit/test_compute_tiering.py tests/unit/test_intent_weights.py tests/integration/test_evidence_pipeline.py -v`
Expected: PASS.

- [ ] **Step 2: Run regression tests for affected existing behavior**

Run: `pytest tests/test_copy_generation.py tests/test_feedback_loop.py tests/test_retention_guard.py tests/test_streamlit_services.py tests/test_production_guardrails.py -v`
Expected: PASS.

- [ ] **Step 3: Record rollout notes and known limitations**

```markdown
# Rollout Notes
- P0 shipped: entity profile, evidence bundle, question bank, market packs, compute tier map
- P1 shipped: intent weight snapshot and operator visibility
- Known limitation: external attribution and bundle graph remain out of scope
```

- [ ] **Step 4: Produce a smoke-run command for real workspace verification**

Run: `python3 main.py --config workspace/SMOKEUI_US/run_config.json --output-dir output/runs/ai_os_smoke`
Expected: run completes and writes `asin_entity_profile.json`, `evidence_bundle.json`, `compute_tier_map.json`.

- [ ] **Step 5: Commit rollout readiness docs**

```bash
git add docs/progress/2026-04-13_amazon_ai_operating_system_rollout.md
git commit -m "docs: record rollout readiness for amazon ai operating system upgrade"
```

## Execution Notes

- Implement P0 first; do not start intent-weight write-back until entity profile and evidence bundle are stable.
- Keep write responsibilities separated by module; do not grow `copy_generation.py` into a second policy engine.
- Preserve existing artifact names and add new ones alongside them.
- Prefer adapter functions at module boundaries over broad in-place rewrites.
- If runtime data is sparse, degrade to empty bundles and keep listing generation alive.

## Suggested Milestones

- **Milestone A (P0 Foundation):** Tasks 1-3 complete
- **Milestone B (P0 Operator Readiness):** Tasks 4-6 complete
- **Milestone C (P1 Learning Loop):** Task 7 complete
- **Milestone D (P1 UI + Verification):** Tasks 8-10 complete

Plan complete and saved to `docs/prd/2026-04-13_amazon_ai_operating_system_execution_plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
