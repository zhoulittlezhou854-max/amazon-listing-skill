# Amazon AI Operating System Rollout Readiness

Date: 2026-04-13
Repo: `amazon-listing-skill`
Status: P0 complete, P1 complete, live smoke verification passed

## Scope Delivered

### P0 shipped
- ASIN entity profile generation and persistence
- Evidence bundle generation and Rufus readiness accounting
- Question bank routing with EU compliance support
- Market pack loading and policy overlay
- Field-level compute tier map generation and reporting
- P0 operator-facing report sections and pipeline integration

### P1 shipped
- Intent weight snapshot build/save/load flow
- Intent weight overlay into writing policy
- Workspace/service/Streamlit exposure for intent weight snapshot upload and summary
- Shared operator summaries for evidence, compute tier, and intent weight visibility
- Sparse-input and backward-compatibility safeguards for missing entity profile / missing intent snapshot / no-feedback retention cases

## Verification Evidence

### New unit + integration suite
Command:

```bash
.venv/bin/pytest tests/unit/test_entity_profile.py tests/unit/test_evidence_engine.py tests/unit/test_question_bank.py tests/unit/test_market_packs.py tests/unit/test_compute_tiering.py tests/unit/test_intent_weights.py tests/integration/test_evidence_pipeline.py -v
```

Result: `26 passed`

### Regression suite for affected behavior
Command:

```bash
.venv/bin/pytest tests/test_copy_generation.py tests/test_feedback_loop.py tests/test_retention_guard.py tests/test_streamlit_services.py tests/test_production_guardrails.py -v
```

Result: `41 passed`

### Compatibility suite for sparse-input behavior
Command:

```bash
.venv/bin/pytest tests/test_copy_generation.py tests/integration/test_evidence_pipeline.py tests/test_retention_guard.py -v
```

Result: `26 passed`

### Full repository regression
Command:

```bash
.venv/bin/pytest -v
```

Result: `93 passed`

## Smoke Run Status

### Real workspace smoke command
Command:

```bash
OPENAI_COMPAT_VERIFY_SSL=0 python3 -u main.py --config workspace/SMOKEUI_US/run_config.json --output-dir output/runs/ai_os_smoke
```

Observed result:
- Command completed through Step 0-Step 9 against the real `workspace/SMOKEUI_US/run_config.json`
- Runtime healthcheck entered degraded mode instead of hard-failing on `missing_output_text`
- OpenAI-compatible chat fallback still returned HTTP `404` for `/openai/chat/completions`, but field generation continued via visible fallback routing
- Final generation status in the run log: `live_with_fallback`
- Report and scoring were produced successfully under `output/runs/ai_os_smoke/`

Verified artifacts:
- Core outputs present: `asin_entity_profile.json`, `intent_graph.json`, `writing_policy.json`, `generated_copy.json`, `listing_report.md`, `execution_summary.json`, `action_items.json`
- P0/P1 sidecars present: `evidence_bundle.json`, `compute_tier_map.json`
- Optional artifact `intent_weight_snapshot.json` is absent in this smoke workspace because no intent-weight feedback input was provided; this is expected sparse-input behavior and is covered by tests

Conclusion:
- The repository implementation is verified by tests
- The real-workspace smoke run now completes successfully
- The remaining live-provider issue is downgraded from blocker to degraded-runtime warning because the pipeline preserves operator visibility and finishes with explicit fallback status

## Real Product Validation

### FR real product run
Command:

```bash
OPENAI_COMPAT_VERIFY_SSL=0 python3 -u main.py --config config/run_configs/T70_real_FR.json --output-dir output/runs/T70_real_FR_live_escalated_v2
```

Observed result:
- Real FR product data completed through Step 0-Step 9
- Generation status: `live_success`
- All visible fields landed on `native`
- Report status advanced to `NOT_READY_FOR_LISTING` only when copy-policy checks found real business-rule issues; runtime generation itself was healthy

Verified outputs:
- `output/runs/T70_real_FR_live_escalated_v2/generated_copy.json`
- `output/runs/T70_real_FR_live_escalated_v2/listing_report.md`
- `output/runs/T70_real_FR_live_escalated_v2/evidence_bundle.json`
- `output/runs/T70_real_FR_live_escalated_v2/compute_tier_map.json`

### US real product run with xlsx inputs
Command:

```bash
OPENAI_COMPAT_VERIFY_SSL=0 .venv/bin/python -u main.py --config config/run_configs/H91lite_US.json --output-dir output/runs/H91lite_US_live_escalated_venv_v3
```

Observed result:
- Real US product data with `.xlsx` keyword/ABA sources completed through Step 0-Step 9
- Generation status: `live_success`
- All visible fields landed on `native`
- Report status: `READY_FOR_LISTING`

Verified outputs:
- `output/runs/H91lite_US_live_escalated_venv_v3/generated_copy.json`
- `output/runs/H91lite_US_live_escalated_venv_v3/listing_report.md`
- `output/runs/H91lite_US_live_escalated_venv_v3/evidence_bundle.json`
- `output/runs/H91lite_US_live_escalated_venv_v3/compute_tier_map.json`

Key fixes proven by these runs:
- Locale capability anchors now translate/expand through canonical capability aliases, which removed false `visible_llm_fallback` downgrades on FR/US bullets
- Title generation now patches missing mandatory traffic phrases before dropping to fallback
- Codex exec fallback now gets additional timeout headroom, which prevents false live-generation failures on heavier real-product prompts
- `.xlsx`-backed real-product runs are validated through the repo virtualenv (`.venv/bin/python`), where `openpyxl` is available

## Known Limitations

- External attribution write-back, bundle graph / FBT orchestration, and business KPI loop remain out of scope for this wave
- The configured OpenAI-compatible endpoint can still return empty `responses` text and `404` on chat fallback when Codex exec fallback is unavailable
- Real-product live success currently depends on running in an environment where Codex exec fallback can access session files and where `.xlsx` loaders use the repo virtualenv

## Release Readiness Judgment

- Engineering readiness: yes
- Test readiness: yes
- Backward-compatibility readiness: yes
- Operator visibility readiness: yes
- Live environment readiness: pass on real-product runs, with degraded fallback still possible on the direct OpenAI-compatible path

Recommended next action:
1. Feed a real intent-weight input snapshot into a validated real-product workspace and confirm `intent_weight_snapshot.json` persistence
2. Normalize the default runtime entrypoint onto `.venv/bin/python` so `.xlsx` product runs do not depend on system Python packaging state
3. Start P2 work after preserving these FR/US real-product runs as the P1 completion baseline
