# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---
- 2026-04-13 | best_practice | For this repo, use `.venv/bin/pytest` instead of relying on `pytest` in PATH or system `python3 -m pytest`; the virtualenv already has pytest installed while the system interpreter does not.
- 2026-04-13 | best_practice | Add a lightweight `tests/conftest.py` that inserts the repo root into `sys.path` for new `tests/unit/*` modules; otherwise direct unit-test runs may fail to import `modules.*` even when the project root is the pytest rootdir.
- 2026-04-13 | best_practice | Reset `modules.llm_client` runtime globals and clear LLM-related env vars in `tests/conftest.py` to keep tests deterministic; otherwise local machine credentials can silently flip tests into live-mode behavior.
- 2026-04-13 | insight | `modules.copy_generation` needed deterministic fallback behavior for title/bullet/description when `LLMClientUnavailable` is raised; without catching that exception and dropping to rule-based fallback, offline/compliance regression tests fail and visible-field policy downgrades do not complete.
- 2026-04-13 | best_practice | When the same operator-facing counts must appear in report text, service payloads, and Streamlit, add shared summarizer helpers at the domain-module level (for example `summarize_evidence_bundle`, `summarize_compute_tier_map`, `summarize_intent_weight_snapshot`) instead of recomputing counts separately in each layer; this keeps report/UI numbers aligned and makes TDD cheaper.
- 2026-04-13 | best_practice | For sparse or backward-compatible runs, normalize optional sidecar payloads to stable empty shapes (`{"weights": []}` for intent snapshots, empty question bank arrays for missing entity profiles) instead of `{}`; this prevents legacy runs from accidentally activating new logic or forcing per-layer nil checks.
- 2026-04-13 | knowledge_gap | A real smoke run can fail before any workflow step when `main.py` performs live LLM healthcheck during generator init; if the OpenAI-compatible endpoint returns `response` payloads with missing text and chat fallback is `404`, the error surfaces as `missing_output_text`, so rollout docs should distinguish environment/runtime readiness from repository correctness.
- 2026-04-13 | best_practice | For learning-loop features, make write-back observable in the data structure that downstream modules already consume (here: reorder `intent_graph` nodes and enrich `scene_metadata` / `capability_metadata`) instead of only attaching a passive snapshot blob; otherwise the pipeline stores learning without any behavior change.
- 2026-04-13 | best_practice | The `api.gptclubapi.xyz/openai` gateway blocks non-browser user agents with Cloudflare 1010 (`browser_signature_banned`); keep the browser-style `User-Agent` in `modules.llm_client` when probing the OpenAI-compatible endpoint, or route verification through the existing client helper instead of ad-hoc scripts.
- 2026-04-13 | best_practice | Real product runs that depend on `.xlsx` inputs should use `.venv/bin/python -u main.py ...` instead of system `python3`; the repo virtualenv already has `openpyxl`, while the system interpreter may be PEP-668 managed and unable to install it.
- 2026-04-13 | insight | For Codex-backed live generation, stage-level HTTP timeouts are too tight if reused unchanged for `codex exec`; adding a fixed process-overhead buffer prevented false `LLMClientUnavailable` fallbacks on real-product title/bullet generation.

## 2026-04-13 - Listing score can decrease even when raw content quality increases
- In `scoring_results.json`, `raw_total_score` can be higher than an older run while `total_score` is lower if `listing_status == NOT_READY_FOR_LISTING` triggers the additional `-20` gate in `modules/scoring.py`.
- Example observed on `output/runs/T70_real_FR_live_escalated_v2`: raw score `288` > older real-product peak raw `284`, but total score became `268` because `blocking_reasons` included a restricted stabilization claim and the listing-status gate forced a 20-point deduction plus `待优化` rating.
- When users ask why a score is lower, compare `raw_total_score`, `production_readiness.penalty`, and `listing_status` before attributing it to weaker copy quality.

## 2026-04-13 - Recomputing historical listing scores offline can diverge from saved artifacts
- Re-running `modules.scoring.calculate_scores()` directly from saved `generated_copy.json` + `preprocessed_data.json` may not reproduce the historical `scoring_results.json` unless the original `intent_graph` and other step-time inputs are also provided.
- Observed on real-product runs where offline recomputation lowered COSMO-related totals compared with the saved Step 8 artifact.
- When comparing score changes across runs, prefer the saved `scoring_results.json` / `execution_summary.json` from that run, and treat offline recomputation as useful for new scoring fields only unless all original inputs are restored.
- 2026-04-13 | insight | In `modules.llm_client` + `modules.copy_generation`, do not collapse `missing_output_text` into a generic `LLMClientUnavailable("no API client")`; preserve the response error code and mark retryable empty-packet states explicitly, or title/bullet/description/FAQ loops will break on the first empty gateway packet and silently waste their configured retry budget.
- 2026-04-14 | preference | For the planned FBT/bundle system, the real product model should treat one camera model as a family of bundle variants (`base_machine + accessory_pack + sd_card_capacity`), not as a single fixed bundle; same model may differ by accessory mix and card size.
- 2026-04-14 | preference | The future bundle-variant system must be backward-compatible with the current product inputs; it should not require users to rewrite every run input. Prefer optional variant metadata layered on top of existing product files, with sensible defaults when bundle/accessory/card details are missing.
- 2026-04-14 | preference | Bundle/accessory modeling should use the explicit accessory names included in each sellable link/variant as the source of truth, not coarse labels like `cycling_pack` or `dive_pack`; real variants often mix scenes (e.g. waterproof housing + cycling kit) or only differ by a few clips/mounts.
- 2026-04-14 | preference | Bundle-variant inputs should be ingestible from the existing `产品卖点和配件等信息补充.txt` supplement file, so operators can maintain included accessories and SD card capacity there instead of editing run_config for every product link.
- 2026-04-14 | insight | On this machine, enabling `codex` failover from inside Python is still blocked by runtime behavior: `codex exec` works from the CLI harness as a top-level command, but the same command launched via Python `subprocess`/PTY consistently times out even after removing `-m`/`-c` overrides and isolating `CODEX_HOME`. Treat Codex subprocess failover as non-production-ready here until there is a more reliable invocation path.
- 2026-04-14 | best_practice | When users ask for a "failure probability" during live-generation debugging, answer with observed run-level rates and separate the failure modes: unusable live output (`missing_output_text`) vs true transport/process timeout. In the current H91 real run, visible-field fallback incidence was 8/8, but the primary gateway timeout rate was not 100% because the gateway usually returned quickly with empty output.
- 2026-04-14 | correction | For this project, any run where `title`, `B1`-`B5`, `description`, or `aplus_content` falls into `visible_llm_fallback_fields` must be treated as a severe failure, even if the workflow finishes and produces a report/score. Do not frame such runs as acceptable partial success.
- 2026-04-14 | best_practice | For this repo's live-generation recovery path, prefer HTTP-only provider failover reusing `modules.llm_client`'s existing OpenAI/DeepSeek client paths over Python-launched `codex exec`; the current machine/provider combination shows structural empty-response and subprocess-timeout failures rather than transient request errors.
- 2026-04-14 | correction | When the user asks for a direct code excerpt or command-shape confirmation during live-generation debugging, answer with the exact local snippet first instead of re-running heavy debugging workflows or skill overhead; keep the response tightly scoped to the requested lines and flags.
- 2026-04-14 | insight | Switching `modules/llm_client.py` from Codex `--json` PTY parsing to `-o <tmpfile>` fixes the local unit-path, but the real H91 live run still shows `codex exec` timing out at 60s during healthcheck/blueprint generation; the remaining blocker is now runtime latency/reliability under real prompts, not JSONL parsing.
- 2026-04-14 | insight | The new HTTP fallback path in `modules/llm_client.py` works locally, but `https://api.gptclubapi.xyz/v1/chat/completions` rejects the current key with `HTTPError 403: error code: 1010`; this blocks replacing Codex fallback with that provider until the endpoint/key combination is changed.

- 2026-04-14: Real run acceptance checks for `generated_copy.json` must read `metadata.generation_status`, `metadata.llm_fallback_count`, and `metadata.visible_llm_fallback_fields`; these fields are not top-level.
- 2026-04-14: Bullet post-validation repair should treat `missing_numeric` as repairable; otherwise live bullets can degrade to fallback even when a single explicit proof injection or repair pass would make them publishable.
- 2026-04-14: HTTP fallback timeouts must honor stage/payload `_request_timeout_seconds` for long-form fields like A+; a fixed 30s fallback budget is enough for short fields but causes avoidable long-form fallback.
## [LRN-20260414-001] best_practice

**Logged**: 2026-04-14T16:40:00+08:00
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
DeepSeek fallback outputs often need structured-output sanitation plus deterministic payload-scaffold repair to avoid false visible fallbacks.

### Details
During real H91lite_US runs, live HTTP fallback produced usable copy but some fields still hit `live_with_fallback` because the final LLM text missed a mandatory keyword, frontload anchor, or numeric proof by a narrow margin. The durable fix was: (1) strip fenced JSON / visual-brief artifacts before visible-field finalization, (2) strengthen title keyword repair under length pressure, and (3) add a deterministic payload-scaffold repair path for bullets before classifying the field as fallback. This converted the real run from `live_with_fallback` and 214/300 to `live_success` and 240/300.

### Suggested Action
Reuse the same scaffold-repair pattern anywhere a field is one repair away from passing, especially for keyword-frontload and forbidden-term retries on non-OpenAI HTTP fallbacks.

### Metadata
- Source: conversation
- Related Files: modules/copy_generation.py, tests/test_copy_generation.py
- Tags: llm-fallback, deterministic-repair, structured-output, scoring
- Pattern-Key: harden.llm_visible_field_repair

---
### 2026-04-14 — Preserve L2/L3 scoring by adding distinct policy L3 search terms instead of retiering shared keywords

When A10 scoring depends on both `L2` bullet distribution and `L3` search-term coverage, do not upgrade an already-routed keyword from `L2` to `L3` just because policy metadata later labels it `L3`. That collapses the single assignment record into one tier and can zero out the bullet-distribution score. The durable fix is: (1) keep existing routed keywords at their original tier, (2) merge policy keyword metadata only for search-term candidate discovery, and (3) inject distinct explicit `L3` keywords from `writing_policy.keyword_metadata` that were not already used in title/bullets. This restored `A10` from 70 back to 100 on the real `H91lite_US_r7` run while keeping `live_success`.

### Suggested Action
If a scoring model tracks one tier per keyword record, prefer adding new distinct keywords for backend/search coverage rather than mutating tier labels on already-assigned visible-field keywords.

### Metadata
- Source: conversation
- Related Files: modules/copy_generation.py, tests/test_copy_generation.py
- Tags: scoring, search-terms, tier-routing, a10
- Pattern-Key: preserve.distinct-l3-search-terms

---

- 2026-04-14 | best_practice | In live runs using OpenAI-compatible gateways, avoid logging the full response body on `missing_output_text` / empty `output`; some providers inject large `instructions` blocks (Codex-style) that flood logs and hide stage progress. Log only compact fields (`id`, `status`, `error`, `output_len`, `item_types`, provider/model) plus one short sample key for diagnosis.
- 2026-04-14 | insight | `listing_report.md` can show inconsistent quality signals when legacy evidence metrics (e.g., `Rufus readiness`) and the new scoring framework (`Rufus 100/100`) are rendered together without a shared definition. Add explicit metric provenance/namespace in reports to prevent operator misread of model quality.
- 2026-04-14 | correction | A10/COSMO/Rufus full score can still coexist with visibly awkward bullet phrasing because current scoring emphasizes routing/evidence/compliance coverage, while fluency/naturalness has no explicit penalty path. Treat readability as a first-class scoring dimension or enforce it as a medium/high blocking risk for publish-ready claims.

- 2026-04-14: Running two concurrent `run_pipeline.py` jobs with the same `--run-id` can pollute `step6_artifacts` and cause `resume from artifact` + `live_with_fallback` false negatives; use unique run IDs for parallel/debug runs or ensure only one job per run directory.

- 2026-04-14: End-to-end live runs can hang during Step 6 A+ HTTP reads (urllib chunked SSL read) when using the openai-compatible primary + http fallback chain. If Step 6 stalls after bullets/description, inspect `step6_artifacts/` first and avoid rerunning with the same run-id; prefer a fresh run-id and keep A+ timeout/fallback tuning separate from content-quality fixes.

## 2026-04-15 Task 1
- Added a stable repair logging API in `modules/repair_logger.py`, including `log_repair(...)`, JSONL output, summary aggregation, and repo-root learnings routing.
- Ensured Step 6 initializes repair artifacts from `main.py` so `repair_log.jsonl` and `repair_summary.json` always exist even when generation is mocked or exits early.
- Extended repair coverage to title, bullet, description, and FAQ fallback/repair paths; added unit and integration assertions for repair artifacts.

## 2026-04-15 Task 2
- Reworked `modules/coherence_check.py` into a minimal P0 coherence gate: title spec expansion, bullet-header duplicate selling dimensions, and fluency-driven header/body rupture surfacing.
- Wired coherence output into `modules/risk_check.py` so `risk_report.json` now carries a dedicated `coherence` section and P2 review queue entries without blocking healthy listings.
- Tightened duplicate-dimension heuristics to inspect bullet headers only and narrowed battery-runtime keywords to explicit endurance terms, avoiding false positives from shared time values in bullet bodies.

## 2026-04-15 Task 3
- Switched frontend workspace defaults in `app/services/workspace_service.py` from the legacy OpenAI-compatible gateway to the validated DeepSeek lane (`deepseek-chat`, `https://api.deepseek.com/v1`, `DEEPSEEK_API_KEY`).
- Added official run-config alignment checks so newly created workspaces carry an `llm_alignment_warning` when their LLM settings diverge from `config/run_configs/<product>_<market>.json`.
- Surfaced the mismatch warning in `app/streamlit_app.py` and covered both the default DeepSeek config and mismatch path in `tests/test_streamlit_services.py`.

## 2026-04-15 Task 4
- Hardened `modules/input_validator.py` to validate required columns plus numeric sample values for the four launch-critical input tables: `attribute_table`, `keyword_table`, `review_table`, and `aba_merged`.
- Kept validation non-blocking but made failures explicit and operator-friendly by returning structured warnings for missing files, missing columns, and bad numeric fields instead of letting later steps fail implicitly.
- Added regression coverage in `tests/test_input_validator.py` for both complete-table passes and friendly `数值类型` warnings when numeric columns contain invalid data.

## 2026-04-16 Dual Version
- `run_pipeline.py --dual-version` now runs two sibling outputs under `output/runs/{run_id}/version_a` and `version_b`; single-version mode remains unchanged and still writes directly into `output/runs/{run_id}`.
- DeepSeek reasoning-model calls must ignore `reasoning_content` and only return assistant `content`; `modules/llm_client.py` now supports per-call `override_model="deepseek-reasoner"` without changing the global V3 main lane.
- Validation snapshot: `r15_v3only` preserved the V3 baseline (`live_success`, `READY_FOR_LISTING`, 330/330, blueprint=`deepseek-chat`); `r15_dual` produced `version_b` with `deepseek-reasoner` blueprint and 330/330, while `version_a` still completed `live_success`/`READY_FOR_LISTING` but one run fell back to bullet generation without a persisted blueprint file after malformed V3 blueprint JSON, landing at 320/330.

## 2026-04-16 Frontend Dual-Version Toggle
- The Streamlit “新品上架” form now exposes a simple checkbox: `同时输出 R1 Blueprint 实验版（耗时更长）`; unchecked keeps the exact single-version V3 flow, checked adds the dual-version branch only for that run.
- Frontend service wiring keeps the workspace LLM default unchanged; `app/services/run_service.py` only enables the experimental branch at execution time via `dual_version=True`, and the UI shows/downloads `dual_version_report.md` when present.
- Regression coverage now includes the dual-version service path, and the full suite stays green at `218 passed`.

## 2026-04-16 V2.0-A Task A1
- Centralized title/bullet length policy in `modules/writing_policy.py` via `LENGTH_RULES`, covering title target `160–190`, title hard ceiling `200`, bullet target `200–250`, bullet hard ceiling `500`, and bullet SEO byte limit `1000`.
- Updated direct consumers in `modules/copy_generation.py` so title payloads and post-trim use the shared title ceiling, bullet prompt guidance reflects the new target range, and bullet hard trimming now honors the shared `500`-char ceiling without off-by-one overflow.
- Synced report-facing metadata in `modules/report_generator.py` and added regression coverage in `tests/test_length_rules.py`; targeted acceptance passed with `4 passed`.

## 2026-04-16 V2.0-A Task A2
- Reworked title generation in `modules/copy_generation.py` from comma-structure enforcement to semantic title guidance: titles now reject raw keyword-dump patterns, reject bare technical parameter brackets, and aim for natural product-name phrasing while still preserving dynamic keyword/numeric coverage.
- Replaced the deterministic title repair/fallback path with a natural-title scaffold that prioritizes required keywords, validated numeric proofs, and brand-first phrasing instead of whole-title comma stacking; exact-match title fallback now preserves all required exact keywords with scene-aware phrasing.
- Added `tests/test_title_naturalness.py` and updated title-specific regression assertions in `tests/test_copy_generation.py`; targeted acceptance passed with `3 passed` for `tests/test_title_naturalness.py` and `9 passed` across the impacted title-generation regression slice.

## 2026-04-16 V2.0-A Task A3
- Added audience-allocation scaffolding directly in `modules/blueprint_generator.py` instead of reading audience metadata from `modules/stag_locale.py`; the plan now hard-assigns five bullet slots across `hero`, `professional`, `daily`, `guidance`, and `kit` groups.
- Injected an explicit `Audience Allocation Plan - MUST follow this structure` block into the blueprint system prompt and payload, so both V3 and R1 blueprint paths inherit the same multi-audience coverage constraint through the shared `_generate_bullet_blueprint_impl(...)` path.
- Added `tests/test_blueprint_audience_coverage.py`; targeted acceptance passed with `2 passed`.

## 2026-04-16 V2.0-A Task A4
- Added bullet-level structural helpers in `modules/fluency_check.py`: `check_bullet_dimension_dedup(...)`, `check_bullet_total_bytes(...)`, and `build_bullet_dimension_repair_instruction(...)`. The dedup rule now flags a repeat only when 3+ bullet headers collapse into the same dimension cluster, while total bullet bytes is emitted as a soft SEO warning against the 1000-byte aggregate cap.
- Wired bullet-dimension repeat context into `modules/copy_generation.py` repair flow via `fluency_dimension_repeat`, so repair prompts can receive the duplicated dimension plus affected bullet indices before the existing deterministic fallback path takes over.
- Surfaced both new checks inside `modules/risk_check.py` and added regression coverage in `tests/test_bullet_dimension_dedup.py`; targeted acceptance passed with `28 passed` across the new dedup tests plus the existing fluency suite.

## 2026-04-16 Validation Note
- `r16_v2a` exposed a status-source mismatch: `risk_report.json` and `listing_report.md` correctly downgraded to `NOT_READY_FOR_LISTING` because of bullet-dimension repeat, but `readiness_summary.md` still rendered `READY_FOR_LISTING`. The readiness summary generator is reading a stale or different status source than the final risk adjudication and needs to be aligned before trusting that file as the single operator verdict.

## 2026-04-16 V2.0-A Fix Pack
- `readiness_summary.md` 状态错位的根因是 `modules/report_builder.py` 直接读取 `scoring_results["listing_status"]`，绕过了 `modules/listing_status.py::derive_listing_status(...)` 与 `modules/report_generator.py::_listing_readiness(...)` 的最终仲裁结果。修复后，readiness summary 会优先读取 `risk_report["listing_status"]`，若缺失则先调用 `derive_listing_status(...)` 补齐，再统一走 `_listing_readiness(...)`，从而与 `listing_report.md` / `risk_report.json` 保持同源一致。
- `r16_v2a` 的 audience 覆盖失效主因是 Blueprint 层虽然构建了 `audience_allocation`，但没有写入 `bullet_blueprint.json`，而 `modules/copy_generation.py` 也没有把 audience allocation 传入 bullet writer。修复后，`modules/blueprint_generator.py` 会把 `audience_allocation` 持久化到 blueprint 输出，`modules/copy_generation.py` 会读取每个 slot 的 `audience_group / audience_label / audience_focus` 并注入 bullet prompt。
- `DIMENSION_CLUSTERS` 中 `mobility_commute` 过宽会把 guidance/travel 文案误归为通勤维度。本次将其收窄为更强场景词：`commut`, `cycling`, `bike`, `ride`, `on-the-go`, `pov`，移除了过泛的 `travel` 和 `daily`，避免 B4 guidance 类 bullet 被错误吞入 commute 维度。
- 验收对比：`r16_v2a` 为 `live_success` 但最终 `NOT_READY_FOR_LISTING`，分数 `A10 100 / COSMO 92 / Rufus 90 / Fluency 30`；`r16_v2a_fix` 为 `live_success` 且三份状态一致 `READY_FOR_LISTING`，分数提升到 `A10 100 / COSMO 100 / Rufus 100 / Fluency 30`。相对 `r15` 基线，本轮修复没有回退主链路，并恢复到 330/330。
- V2.0-A 最终验收结论：长度规则统一、Title 自然化、Blueprint 受众分配、Bullet 维度去重，以及 fix pack 的状态源一致性/受众传递修复均已完成；当前全量测试 `232 passed`，`r16_v2a_fix` 可作为新的 V2.0-A 验收基线。

## 2026-04-16 GitHub Release Publish Note
- Publishing `v2.0.0` to GitHub hit two reusable issues: sandboxed git writes could not create `.git/index.lock`, and the remote `main` branch had unrelated history from an earlier snapshot. The safe release pattern was: escalate git write operations, `git fetch` remote `main`, merge with `--allow-unrelated-histories`, resolve add/add conflicts by keeping the validated local V2.0 tree, then push `main` plus the annotated `v2.0.0` tag.

## 2026-04-16 V2.0-B
- `modules/report_generator.py` now renders a dedicated `## Keyword Arsenal` block inside `listing_report.md`, sourced first from `generated_copy.decision_trace.keyword_assignments`, then `preprocessed_data.keyword_metadata`, and finally the keyword table tier fallback. This keeps the report aligned with the run’s actual routing decisions instead of recomputing a separate keyword view.
- Added `app/services/workspace_service.py::list_workspace_runs(...)` to read local run folders directly without a new backend API. It normalizes both single-version runs and dual-version runs (`version_a/`, `version_b/`, `dual_version_report.md`) into one UI-friendly payload.
- `app/streamlit_app.py` now exposes a new `历史报告` tab: select a workspace, load all runs under that workspace, and default-expand each record with visible copy, four-dimension scores, score breakdown JSON, plus embedded `listing_report.md` / `readiness_summary.md` / `dual_version_report.md` views.
- V2.0-B regression baseline: new targeted tests passed and full suite moved from `232 passed` to `234 passed`.

## 2026-04-16 GitHub Push Retry Note
- After completing V2.0-B and committing `634f5ef`, GitHub push retries failed twice with `Failed to connect to github.com port 443 after 7500x ms`. The repo state is ready to publish, but remote sync depends on network recovery rather than git/auth fixes.

## 2026-04-16 Dual-Version R1 Visible Copy
- Experimental dual-version runs no longer stop at `R1 blueprint only`. `main.py`, `run_pipeline.py`, and `app/services/run_service.py` now pass three independent model overrides so Version B can use `deepseek-reasoner` for blueprint planning, title generation, and bullet generation while leaving description / FAQ / search terms / A+ on the V3 path.
- `modules/copy_generation.py` now threads `model_overrides` through `generate_listing_copy(...)` / `generate_multilingual_copy(...)`, then attaches `_llm_override_model` to title and bullet payloads. `_llm_generate_title(...)` and `_llm_generate_bullet(...)` honor that override, and bullet repair generation inherits the same override so experimental visible copy stays on one model family.
- Backward-compatibility note: some unit-test fake clients still expose the old `generate_text(...)` / `generate_bullet(...)` signature without `override_model`. The safe pattern is to try the new keyword arg first and fall back to the legacy call on `TypeError`, which keeps existing test doubles and any thin local mock clients working.
- Validation baseline after this change: full suite moved from `234 passed` to `236 passed`.

## 2026-04-16 R1 Runtime Hang Note
- After shipping `feat: use r1 for experimental title and bullets`, both the full dual-version run (`H91lite_US_r16_dual_r1copy`) and a focused visible-copy validation against the cached Version A blueprint stalled before writing `version_b/generated_copy.json`. The strongest signal is that Version B stops before `bullet_blueprint.json` or any step6 partial artifact appears, which suggests the first `deepseek-reasoner` live request is hanging in this environment rather than failing fast.
- Practical ops guidance: keep the code path in place, but treat R1 validation as environment-dependent until we add an explicit outer watchdog around each experimental stage or confirm network reachability to the R1 endpoint.

## 2026-04-17 R1 Pure Visible Copy Batch
- `modules/copy_generation.py` now treats `model_overrides={"title": "deepseek-reasoner", "bullets": "deepseek-reasoner"}` as a dedicated pure-R1 visible-copy mode. Instead of six serial field calls, Version B makes one `visible_copy_batch` request for `title + 5 bullets`, records a single stage artifact, and marks metadata with `visible_copy_mode=r1_batch` plus `visible_copy_status=r1_pure`.
- Failure handling is now strict by design: the batch request sets `_disable_fallback=True`, uses `R1_BATCH_TIMEOUT_SEC` (default `180`), and raises `RuntimeError("R1 batch visible copy generation failed: ...")` on timeout / parse / validation failure. In that mode the pipeline does not fall back to V3 and does not silently emit mixed visible copy.
- Purity guardrail: when the pure-R1 batch path is active, the later per-bullet LLM polish step is skipped so Version B title and bullets are not re-written by the default V3 model after the initial R1 response.
- Regression baseline after adding the pure batch path: targeted R1 batch tests passed, related wrapper/service tests stayed green, and the full suite moved from `236 passed` to `238 passed`.
- Real-run note from `H91lite_US_r1_batch_verify`: Version B blueprint generation still timed out before writing `bullet_blueprint.json`, but the new `visible_copy_batch` stage completed successfully with `deepseek-reasoner` and produced pure R1 `title + 5 bullets` (`llm_fallback_count=0`, all visible subfields sourced from `visible_copy_batch`). This means visible-copy purity is now decoupled from blueprint-step instability; if the batch itself fails later, the run should error instead of emitting mixed copy.

## 2026-04-17 Experimental Version B Strict Blueprint Gate
- `main.py::run_step_5()` now treats R1 blueprint failure as a blocking error when `blueprint_model_override == "deepseek-reasoner"`. This prevents the experimental Version B branch from swallowing blueprint timeouts as warnings and then continuing into Step 6.
- `main.py::run_step_6()` now has a second guard: if experimental Version B is configured but `bullet_blueprint.json` is missing / unreadable, Step 6 returns `experimental_version_b_blueprint_missing` immediately instead of running `visible_copy_batch`.
- Real verification from `H91lite_US_r1_batch_strict_verify`: Version A completed normally, while Version B hit an R1 blueprint timeout in Step 5 and stopped there. No `bullet_blueprint.json`, no `generated_copy.json`, no `scoring_results.json`, and no `step6_artifacts/` were produced under `version_b/`; `execution_summary.json` recorded `workflow_status=failed` with no `step_6` entry.
