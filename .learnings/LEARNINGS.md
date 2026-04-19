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

## 2026-04-17 Failure Display + Title Length Tuning
- `run_pipeline.py`, `app/services/run_service.py`, and `app/services/workspace_service.py` now infer explicit experimental failure states from `execution_summary.json` when `generated_copy.json` is missing. The two named states currently surfaced are `FAILED_AT_BLUEPRINT` and `FAILED_AT_COPY`, replacing the previous ambiguous `unknown` display in dual-version CLI/UI summaries.
- `modules/report_generator.py::generate_dual_version_report(...)` now renders failed Version B runs as failure blocks instead of empty listings. The report includes `Generation Status`, `Failure Reason`, and `Visible Copy: not generated`, so operators can tell whether the experiment stopped at blueprint or copy generation.
- Title length rules were tightened without changing the 200-character ceiling: `modules/writing_policy.py` now targets `175-195` characters with a `160`-character soft warning, and `modules/copy_generation.py::_generate_and_audit_title(...)` retries titles that are too skeletal only when the active max length still supports a full title. This avoids regressing small-ceiling repair tests while nudging normal runs toward richer, less stubby titles.
- Regression baseline after this pass: full suite moved from `241 passed` to `244 passed`.

## 2026-04-17 Title 190-198 Target
- Title targeting was tightened again: `modules/writing_policy.py` now sets `target_min=190`, `target_max=198`, `soft_warning=185`, while keeping `hard_ceiling=200`. `modules/copy_generation.py` also now prefers the longest valid deterministic title candidate near the target window instead of returning the first merely-valid short candidate.
- Real verification run `H91lite_US_title_190_198_verify` completed with `live_success`; the generated title length was `196`, which lands inside the requested `190-198` window. The exact title was: `TOSBARRFT vlogging camera Action Camera with 150 minutes and 1080p for Commuting Capture and Vlog Content Creation, built for mini camera, body camera, and travel camera recording for Vlog Content`.
- Follow-up quality note: the length target is now working, but this title still reads somewhat mechanical because the model is packing keyword coverage aggressively near the ceiling. If we want the next iteration to improve *quality* rather than just *length compliance*, the next lever is title phrasing quality, not title length budget.

## 2026-04-17 Shared V3/R1 Title Naturalness Pass
- V3 and experimental R1 now share the same tightened title budget: `190-198` target characters, `185` soft warning, `200` hard ceiling. The centralized values remain in `modules/writing_policy.py::LENGTH_RULES["title"]`, so prompt guidance and post-generation repair stay aligned.
- `modules/copy_generation.py::_build_natural_title_candidate(...)` was tightened to prefer fuller natural product-name phrasing instead of keyword-stack tails: it now prioritizes richer differentiators, uses `... use` phrasing instead of awkward `... recording` tails for secondary keyword coverage, and only adds a generic fallback usage phrase when a title is still below the soft warning.
- `modules/copy_generation.py::_build_deterministic_title_candidate(...)` now prioritizes `core_capability` before raw numeric specs when constructing the natural scaffold. This keeps the fallback title closer to a real product name while still preserving required keyword hits.
- `modules/copy_generation.py::_compose_exact_match_title(...)` now refuses to accept a candidate that technically contains the secondary exact keywords but trims away the full framed phrase (for example `helmet camera for Helmet POV`). It falls through to the explicit exact-match title when needed so scene-framed exact keywords survive intact.
- Verification after this pass: targeted title tests plus the full suite are green at `245 passed`.

## 2026-04-17 V3 vs R1 Compare Run Note
- Fresh verification runs completed for `H91lite_US_compare_v3b_20260417` and `H91lite_US_compare_dual_20260417`. The V3-only run finished `live_success`, but the strict dual Version B path failed again at Step 5 with `FAILED_AT_BLUEPRINT` because the `deepseek-reasoner` blueprint request timed out before any visible copy was generated.
- To still inspect R1 visible-copy quality without mixing providers in title/bullets, a separate compare run `H91lite_US_compare_r1visible_20260417` used Steps `0-5` on the standard blueprint path, then Step `6` with `title_model_override=deepseek-reasoner` and `bullet_model_override=deepseek-reasoner`. This yields pure-R1 title + bullets for comparison while making the dependency explicit: it is an R1 visible-copy sample on top of a validated V3 blueprint, not a successful strict Version B run.
- Current quality gap observed from that run: the R1 visible-copy batch can still ignore the shared `190-198` title target and returned a 96-character title, so the next fix needs to be in the batch prompt / validation path rather than the stage-by-stage title generator alone.

## 2026-04-17 R1 Short Title Root Cause
- The `190-198` title lock is only enforced in the stage-by-stage title path (`_llm_generate_title` + `_generate_and_audit_title`). The pure R1 visible-copy batch path bypasses that logic entirely.
- Evidence: `modules/copy_generation.py::_r1_batch_generate_listing` only tells R1 to keep the title `under 200 characters` and only validates `len(title) <= hard_ceiling`; it never passes `target_min/target_max`, never calls `_generate_and_audit_title`, and never rejects a too-short title. The compare artifact `output/runs/H91lite_US_compare_r1visible_20260417/step6_artifacts/visible_copy_batch.json` shows a successful 96-char R1 title accepted on the first and only batch attempt.

## 2026-04-17 R1 Batch Title Audit Reuse
- `modules/copy_generation.py::_r1_batch_generate_listing(...)` now routes the batch-returned title through the shared `_generate_and_audit_title(...)` path before accepting it. The batch title is passed as `_prefetched_title_candidates`, so the shared validator sees the actual R1 batch output first instead of skipping straight to a second generator path.
- `_generate_and_audit_title(...)` now consumes `_prefetched_title_candidates` before calling `_llm_generate_title(...)`. When `_disable_fallback=True`, it also stops before deterministic fallback and raises `title_validation_failed_after_retry`, which keeps experimental R1 title paths strict instead of silently accepting or replacing invalid short titles.
- Regression coverage: `tests/test_copy_generation.py::test_r1_batch_generate_listing_reuses_shared_title_audit` locks the wiring so future R1 batch changes cannot bypass the shared title audit again.

## 2026-04-17 R1 Batch Prompt Tightening Verification
- The R1 batch prompt now explicitly mirrors the shared title contract: natural product-name phrasing, at least 3 core keywords, top differentiators, target length `190-198`, and `200` hard ceiling. Regression coverage lives in `tests/test_copy_generation.py::test_r1_batch_prompt_uses_shared_title_length_contract`.
- Fresh live verification `H91lite_US_compare_r1visible_fix2_20260417` still failed, but the failure mode shifted in a useful way: the first R1 batch title was no longer accepted silently, and the shared audit logged `length_exceeded` first, then a second retry returned a `131`-character title and failed `below_target_length`. This suggests the prompt is influencing the first answer, but R1 still needs a stronger single-pass title constraint or a batch-specific repair instruction to land inside `190-198` reliably.

## 2026-04-17 R1 Batch In-Path Title Repair
- `modules/copy_generation.py::_r1_batch_generate_listing(...)` now performs a batch-native title repair before handing the title to the shared audit path. If the first batch title falls outside the `190-198` target window, `_r1_batch_repair_title(...)` makes one more DeepSeek-R1 request with a title-only JSON contract and the same natural-title rules, then the repaired title is sent through `_generate_and_audit_title(...)` as the prefetched candidate.
- Regression coverage: `tests/test_copy_generation.py::test_r1_batch_repairs_title_in_batch_before_shared_audit` ensures the R1 batch path makes the extra repair call and forwards the repaired title into the shared audit instead of immediately dropping into the generic single-field retry pattern.
- Fresh live verification `H91lite_US_compare_r1visible_fix3_20260417` did not reach the new repair logic because the very first `visible_copy_batch` request timed out at the network layer (`HTTPSConnectionPool(host='api.deepseek.com', port=443): Read timed out.`). So the code path is now in place and fully tested locally, but the latest live run was blocked by provider/network instability before title-quality behavior could be observed.

## 2026-04-17 R1 Retry Verification Note
- A second fresh retry run `H91lite_US_compare_r1visible_fix4_20260417` failed at the same earliest network boundary as `fix3`: the initial `visible_copy_batch` DeepSeek-R1 request timed out before returning any JSON. This confirms the current blocker is provider/network instability rather than the new batch-native title repair logic.

## 2026-04-17 Deterministic R1 Title Length Repair
- Replaced the batch-title repair dependence on `_r1_batch_repair_title(...)` with a deterministic `_rule_repair_title_length(...)` helper. It now trims titles above the target window back to a word boundary at `198`, and extends short titles by appending non-duplicate keywords from `exact_match_keywords -> l1_keywords -> assigned_keywords`, all without any LLM call.
- The R1 batch path still keeps shared `_generate_and_audit_title(...)` as the final validator. That gives us deterministic length convergence while preserving one authoritative title quality gate for keyword dump detection, exact phrase handling, and final normalization.
- Regression coverage was expanded in `tests/test_copy_generation.py` for trim, extend, duplicate suppression, audit logging, exhausted keyword pool behavior, and confirmation that `_r1_batch_generate_listing(...)` now uses `_rule_repair_title_length(...)` instead of the old LLM repair path.
- Verification after this pass: targeted title/copy tests passed, and the full suite moved to `256 passed`.

## 2026-04-17 R1 Rule-Repair Live Attempt
- Fresh run `H91lite_US_compare_r1visible_rulefix_20260417` still did not produce a usable R1 visible-copy sample. Step 5 blueprint timed out once, and the Step 6 `visible_copy_batch` call failed with `Response ended prematurely` before any JSON payload was returned. This confirms the current blocker remains transport/provider instability, not the deterministic title repair logic.

## 2026-04-17 R1 Debug Retry Outcome
- Fresh dual-version verification runs `H91lite_US_r1debug_20260417b` and `H91lite_US_r1debug_retry_20260417` both reproduced the same transport-side blocker before Version B could reach `visible_copy_batch`: Version A finished `live_success`, but Version B failed at Step 5 blueprint with `experimental_version_b_blueprint_failed` caused by `HTTPSConnectionPool(host='api.deepseek.com', port=443): Read timed out.`
- Because both retries stopped at blueprint, no new `version_b/step6_artifacts/visible_copy_batch.json` was produced. So the new `llm_debug_context` persistence for R1 batch failures is still code/test verified, but not yet live-artifact verified in a real run.

## 2026-04-17 Step5 Blueprint Debug Artifact
- `modules/blueprint_generator.py` now attaches a `debug_context` payload when bullet blueprint generation fails, including `system_prompt`, structured `request_payload`, `llm_response_meta`, and the original error string.
- `main.py::run_step_5()` now persists failed blueprint artifacts to `step5_artifacts/bullet_blueprint.json` before returning `experimental_version_b_blueprint_failed`, so Version B no longer loses prompt/payload context when it times out before Step 6.
- Live verification run `H91lite_US_r1debug_step5ctx_20260417` confirmed the new artifact shape at `output/runs/H91lite_US_H91lite_US_r1debug_step5ctx_20260417/version_b/step5_artifacts/bullet_blueprint.json`; it captured the full blueprint system prompt, `override_model=deepseek-reasoner`, request payload keys, and DeepSeek timeout metadata (`latency_ms=45203`, `error=HTTPSConnectionPool(... Read timed out.)`).

## 2026-04-17 R1 Step6 Debug Attempt Still Blocked By Blueprint
- Fresh verification run `H91lite_US_r1debug_step6ctx_20260417` again completed Version A successfully but failed Version B at Step 5 with the same DeepSeek timeout before `visible_copy_batch` could start.
- This means the new Step 5 debug artifact path is now the practical source of truth for diagnosing current R1 instability; Step 6 `visible_copy_batch.json` still cannot be live-verified until the reasoner blueprint call survives long enough to hand off into visible copy generation.

## 2026-04-17 Blueprint V3 Primary + Streaming
- `modules/blueprint_generator.py` now uses a two-level streamed model strategy for Step 5: primary `deepseek-chat` (30s) and fallback `deepseek-reasoner` (120s). The blueprint prompt/payload and JSON schema remain unchanged; only the transport/model selection changed.
- Because the runtime `LLMClient` deepseek path does not expose `chat.completions.create`, blueprint generation now resolves a temporary OpenAI-compatible client from the existing DeepSeek API key/base URL solely for streamed Step 5 calls.
- Verification run `H91lite_US_blueprint_v3stream_fix_20260417` proved the intended outcome: Version B no longer died at Step 5 blueprint timeout, generated a `deepseek-chat` blueprint successfully, and advanced into Step 6 `visible_copy_batch`. The new blocker shifted downstream to `title_validation_failed_after_retry`, which is a copy-quality issue rather than a Step 5 transport timeout.

## 2026-04-17 Repair Keyword Pool For Strict R1 Titles
- `modules/copy_generation.py::_rule_repair_title_length(...)` now looks at `_repair_keyword_pool` after the visible title keyword slices (`exact_match_keywords`, `l1_keywords`, `assigned_keywords`). This keeps the normal title prompt compact while giving strict repair enough extra L1/L2 material to reach the `190-198` target window when the visible payload alone is too small.
- `generate_title(...)` and the R1 `visible_copy_batch` title payloads now pass `_repair_keyword_pool` built from the broader `tiered_keywords` L1+L2 set, so `title_validation_failed_after_retry` can fail for real quality reasons instead of simple keyword-pool starvation.

## 2026-04-17 Repair Pool Verification Result
- Fresh run `H91lite_US_r1repairpool_verify_20260417` proved the Step 5 fix is stable and the extra repair keyword pool alone is not enough to clear Version B. Version B reached `visible_copy_batch`, but still failed with `title_validation_failed_after_retry`.
- The new `visible_copy_batch.json` audit trail shows the blocker is no longer pool starvation: the first batch title came back too long (`rule_repair_trim` from 204 -> 194), then shared title audit still rejected it for missing required keywords (`mini camera`, `body camera`), and the follow-up R1 retry timed out. Final post-retry patch still reported missing `mini camera`, `body camera`, and `travel camera`.
- This means the next root cause is keyword-presence reconciliation inside `_generate_and_audit_title(...)` after the batch repair step, not the size of `_repair_keyword_pool`.

## 2026-04-17 Required Keyword Frontload Verification
- Added `_frontload_required_keywords(...)` before `_rule_repair_title_length(...)` trims overlong titles, so required/exact keywords that already exist in the title are moved out of the trailing danger zone before `_trim_to_word_boundary(...)` cuts the tail.
- Local regression coverage now includes a trim case that keeps `mini camera` and `body camera` present after the repair pass. Title-focused regression suite stayed green at `78 passed` across `tests/test_copy_generation.py`, `tests/test_title_naturalness.py`, and `tests/test_length_rules.py`.
- Real-data validation produced a partial win: the targeted Step 6 run `output/runs/H91lite_US_frontload_step6only_20260417` still ended with `title_validation_failed_after_retry`, but the audit trail no longer reported missing required keywords after trim. The failure signature changed from `missing_keywords + timeout` to `length_exceeded + timeout`, which means the frontload fix likely solved the keyword-loss bug and exposed the next issue: post-trim title reconciliation is still too long before the final retry times out.

## 2026-04-17 R1 Recipe Title Assembly Trial
- Added an R1-only recipe path inside `modules/copy_generation.py::_r1_batch_generate_listing(...)`: the R1 visible-copy batch prompt now asks for `title_recipe` (`lead_keyword`, `differentiators`, `use_cases`), and the new deterministic `_assemble_title_from_segments(...)` composes the final title before it enters the shared audit path. V3 title generation remains unchanged.
- Regression coverage now includes `TestAssembleTitleFromSegments` plus R1-batch tests that confirm the recipe prompt shape and that prefetched titles sent into shared audit come from the assembled recipe, not a raw full-title string.
- Real Step 6 verification run `output/runs/H91lite_US_r1recipe_step6only_20260417` shows another partial improvement: the old `missing_keywords` / `length_exceeded` blocker is gone. The audit trail now shows `recipe_assembled` at length `189`, then a deterministic extend to `198`, and the remaining failure moved to `missing_numeric` (`150 minutes`, `1080p`) before the retry timed out. So the next bottleneck is numeric/spec preservation in the recipe assembly path, not keyword retention or title length control.

## 2026-04-17 R1 Recipe Numeric Preservation Trial
- Extended the R1-only `_assemble_title_from_segments(...)` path to treat `numeric_specs[:2]` as must-keep material before optional differentiators/use cases, so the recipe title can carry validated proof like `150 minutes` and `1080p` without depending on a second LLM repair call.
- Title-focused regression stayed green at `82 passed` across `tests/test_copy_generation.py`, `tests/test_title_naturalness.py`, and `tests/test_length_rules.py`.
- Real Step 6 verification run `output/runs/H91lite_US_r1recipe_numeric_step6_20260417` shows another improvement: the old `missing_numeric` blocker is gone and `recipe_assembled` now lands directly at length `196`. The next blocker is structural rather than factual: shared title audit now rejects the assembled title for `weak_connector_overuse` (`with`, `with`), then the fallback retry times out and the final post-retry patch still misses `mini camera` / `body camera`.

## 2026-04-17 R1 Recipe Connector Consolidation Trial
- Simplified `_assemble_title_from_segments(...)` so required keywords are front-loaded as a comma list, differentiators/numeric proof are merged into a single `with ...` clause, and use cases are merged into a single `for ...` clause. This removes the earlier repeated `with ... with ...` structure while keeping the change scoped to the R1-only recipe assembly path.
- Title-focused regression still passed at `82 passed` across `tests/test_copy_generation.py`, `tests/test_title_naturalness.py`, and `tests/test_length_rules.py`.
- Real Step 6 run `output/runs/H91lite_US_r1recipe_connector_step6_20260417` shows the `weak_connector_overuse` blocker is gone, but the title still fails later for `length_exceeded` after shared audit prepends the primary L1 (`llm_adjusted_l1`) and the dewater pass reshapes the assembled title. So the next root cause is no longer connector repetition; it is post-assembly mutation inside `_generate_and_audit_title(...)` re-inflating the title before the retry timeout.

## 2026-04-17 R1 Title Isolation Branch-In
- `modules/copy_generation.py::_generate_and_audit_title(...)` now hard-branches on `payload["use_r1_recipe"]` into a new R1-only `_generate_title_r1(...)` finalize path, leaving the original V3/shared retry loop untouched for every non-R1 payload.
- The new `_generate_title_r1(...)` path only performs light cleanup, deterministic keyword/length repair, and final validation via `_validate_title_final(...)`; it deliberately skips shared `llm_adjusted_l1`, strong `title_dewater`, and any second title LLM call.
- `_r1_batch_generate_listing(...)` now marks its title payload with `use_r1_recipe=True`, so assembled recipe titles no longer re-enter the generic post-processing chain that was re-inflating them.
- Regression coverage added direct tests for R1 delegation and post-processing bypass, and `./.venv/bin/pytest tests/test_copy_generation.py -q` is green at `77 passed`.

## 2026-04-17 R1 Title Isolation Real Step6 Verification
- Real validation run `output/runs/H91lite_US_r1_title_isolation_step6_20260417` completed Step 6 successfully and produced `step6_artifacts/visible_copy_batch.json` with `status=success`.
- The title audit trail is now exactly the isolated path we wanted: only `recipe_assembled` and `r1_recipe_success` appear for the title field. There are no `llm_adjusted_l1`, `title_dewater`, or `llm_retry` entries in the title audit.
- The final R1 title came back at 198 characters, which proves the isolated finalize path can close the strict length window without falling back into the shared retry loop:
  `TOSBARRFT vlogging camera, mini camera and body camera, with 150 minutes, 1080p, long battery life, lightweight design, and easy operation, for daily commuting, vlog creation, travel camera, bodycam`
- This confirms the current blocker was architectural coupling, not endless prompt instability: once the recipe title stopped flowing through the V3-oriented post-processing chain, the Step 6 title path stabilized.

## 2026-04-18 Hybrid Composer Phase 1 MVP
- Added `modules/hybrid_composer.py` as a pure post-generation composer. It reads existing `version_a` and `version_b` artifacts, writes a separate `hybrid/generated_copy.json`, and never mutates either source version.
- Phase 1 intentionally stops before scoring/risk/readiness. The persisted hybrid payload carries only safe trace segments: `bullet_trace` comes from the selected bullet source, `search_terms_trace` comes from the selected search-term source, and `keyword_assignments` is left empty until Phase 2 rebuild logic exists.
- Every hybrid payload now includes both `metadata.hybrid_sources` and a separate `source_trace` structure so future debugging can answer which version supplied each visible field without reverse-engineering text provenance.
- `run_pipeline.py --dual-version` now creates `output/runs/.../hybrid/generated_copy.json` after Version A/B finish, but still leaves `version_a/` and `version_b/` byte-for-byte untouched. Phase 1 tests are green at `4 passed` in `tests/test_hybrid_composer.py`.

## 2026-04-18 Hybrid Composer Phase 2 Re-Audit
- `modules/hybrid_composer.py` now exposes `rebuild_hybrid_decision_trace(...)` and `finalize_hybrid_outputs(...)`. Phase 2 rebuilds hybrid `keyword_assignments` with a new `source_version` field, then reruns `perform_risk_check(...)`, `calculate_scores(...)`, `generate_report(...)`, and `build_readiness_summary(...)` strictly inside the `hybrid/` directory.
- `run_pipeline.py --dual-version` now finalizes hybrid outputs after composing them, so a real dual run writes `hybrid/generated_copy.json`, `hybrid/risk_report.json`, `hybrid/scoring_results.json`, `hybrid/listing_report.md`, and `hybrid/readiness_summary.md` without mutating `version_a/` or `version_b/`.
- `modules/report_generator.py::generate_dual_version_report(...)` now supports an additive `Hybrid Recommendation` appendix. This keeps the existing A/B sections intact while surfacing the recomputed hybrid result for comparison.
- Real validation run `output/runs/H91lite_US_r17_hybrid_full` proved the Phase 2 contract works end-to-end. The hybrid output used `version_a` title + `version_b` bullets, carried rebuilt keyword assignments, and produced its own listing status (`NOT_READY_FOR_LISTING`) because the mixed copy inherited unsupported live-streaming claims from the selected Version B bullets. This is exactly why hybrid must be re-audited instead of copying A/B scores.

## 2026-04-18 Version B Live-Streaming Risk Diagnosis
- First real Phase 2 hybrid run confirmed the `NOT_READY_FOR_LISTING` block is expected behavior, not a hybrid bug. `version_b` itself is already `NOT_READY_FOR_LISTING`, and hybrid inherits the same blocker when it selects Version B bullets.
- The concrete blocker is `bullet_3` / `B3`: `Ultra-Portable POV — ... WiFi 2.4GHz app control allow quick capture and live streaming in 1080P clarity.` Both `version_b/risk_report.json` and `hybrid/risk_report.json` flag this as `unsupported_live_streaming_claim`.
- The root cause is upstream prompt/data conditioning, not missing capability truth data. `preprocessed_data.json` already carries `live_streaming_supported = false`, but `writing_policy.json` still contains an `intent_graph` node for capability `live streaming` with `resolution=False`, and `bullet_blueprint.json` turns that into a mandatory element (`WiFi 2.4GHz for app control and live stream`). So the unsupported claim is introduced at blueprint time before visible bullet writing.
- Follow-up priority: fix Version B blueprint/prompt conditioning so unsupported boolean-false specs cannot become bullet mandatory elements, then rerun Version B and hybrid. Only if the blocker survives after that should hybrid selection rules start excluding risky bullet slots.

## 2026-04-18 False Spec Suppression Fix Verification
- Added two suppression layers: `intent_translator.enrich_policy_with_intent_graph(...)` now records `suppressed_capabilities` and skips positive nodes for boolean-false specs such as `live_streaming_supported=False`, while `blueprint_generator` now deterministically scrubs suppressed terms from blueprint `theme`, `mandatory_elements`, `capabilities`, `proof_angle`, and `slot_directive`.
- Focused regression for the new suppression behavior is green: `tests/test_blueprint_generator.py` now passes `11/11`, including false-live-streaming, true-live-streaming, and waterproof suppression cases.
- Real validation run `output/runs/H91lite_US_r18_false_spec_fix` confirms the original blocker is gone. `version_b/bullet_blueprint.json` no longer carries live-streaming mandatory elements, `version_b/generated_copy.json` no longer claims live streaming, and both `version_b/risk_report.json` and `hybrid/risk_report.json` have no `unsupported_live_streaming_claim`.
- The next blocker shifted cleanly: `hybrid` is still `NOT_READY_FOR_LISTING`, but now for a different and correct reason — it inherits `description` from `version_a`, whose metadata still marks `visible_llm_fallback_fields = ['description']`. This proves the false-spec suppression worked and that future hybrid selection logic should consider source-field eligibility (e.g. avoid inheriting fallback-marked visible fields).

## 2026-04-18 Hybrid Selection Policy v2
- `modules/hybrid_composer.py` now applies dynamic field eligibility before mixing outputs: it hard-excludes visible fields marked in `metadata.visible_llm_fallback_fields`, hard-excludes fields listed in `risk_report.blocking_fields`, and only then falls back to the default preference map (`title -> version_a`, `bullets -> version_b`, others -> `version_a`).
- `select_source_for_field(...)` now returns an explainable selection object with `source_version`, `selection_reason`, and `disqualified`, and `compose_hybrid_listing(...)` persists that into `hybrid/source_trace.json` so every mixed field can be audited later without diffing raw copy.
- Scheme X is now enforced: if both versions are ineligible for a visible field, hybrid writes that field as `null`, records it under `_no_eligible_source`, and `finalize_hybrid_outputs(...)` upgrades it into a blocking readiness reason instead of silently choosing a bad fallback.
- `run_pipeline.py` now passes each source version's `risk_report` into the hybrid composer (`{**generated_copy, "risk_report": risk_report}`), which was required because field selection cannot evaluate blocker-based eligibility from `generated_copy.json` alone.
- Focused regression remains green after the selection-policy change: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_blueprint_generator.py tests/test_copy_generation.py tests/test_title_naturalness.py tests/test_length_rules.py -q` passes at `107 passed`.
- First GitHub push attempt for commit `de35ea6` timed out with `Recv failure: Operation timed out`; when pushing this repo through the tokenized HTTPS remote, retry with the existing `--progress` push variant instead of assuming the first authenticated push will complete.
- A later retry from commit `ecf2225` still failed with `Failed to connect to github.com port 443 after 75015 ms`; this repo now has a repeatable outbound connectivity issue to GitHub, so treat push status as network-bound rather than auth- or git-state-bound until connectivity recovers.

## 2026-04-18 Hybrid v3 Early Implementation Notes
- Slot-level bullet selection is a better first upgrade than whole-bullet-package selection. `compose_hybrid_listing(...)` now decides each `B1..B5` independently, records per-slot provenance in `source_trace`, and marks `metadata.hybrid_sources["bullets"] = "mixed"` whenever A/B are both used.
- The most stable hard-signal inputs for Hybrid v3 are the ones that already exist: slot blockers can be inferred from `risk_report.blocking_fields` and `truth_consistency.issues`, while slot L2 targets can be rebuilt from `decision_trace.keyword_assignments`. This avoided inventing a new side-channel for slot routing.
- Deterministic hybrid repair is viable without new LLM calls: `modules/hybrid_optimizer.py` now backfills missing L2 keywords with bounded `ideal for <keyword> use` phrases, limits total repairs to 2, and stores the resulting audit trail in `generated_copy.metadata.hybrid_repairs` rather than introducing a new top-level artifact file.
- Launch gating also fits cleanly as orchestration metadata instead of score data. `build_hybrid_launch_decision(...)` reads `risk_report` plus `scoring_results.dimensions.{traffic,conversion,answerability,readability}` and writes the final recommendation to `generated_copy.metadata.launch_decision`, while `report_generator.generate_report(...)` renders a dedicated `## Hybrid Launch Report` block from that metadata.
- Focused Hybrid v3 regression is green: `./.venv/bin/pytest tests/test_hybrid_composer.py tests/test_hybrid_optimizer.py tests/test_blueprint_generator.py tests/test_copy_generation.py tests/test_title_naturalness.py tests/test_length_rules.py -q` passes at `117 passed`.
- Real validation run `output/runs/H91lite_US_r24_hybrid_v3_fix4` is the first clean pass for the new contract: `hybrid` finishes `READY_FOR_LISTING`, keeps `visible_llm_fallback_fields=[]`, scores `A10 100 / COSMO 100 / Rufus 100 / Fluency 30`, and records `launch_decision = {"recommended_output": "hybrid", "reasons": []}`.
- Two implementation details were essential to make the real run line up with the tests: rebuild logic must preserve legacy slot aliases (`bullet_1` as well as `B1`) so A10 can see L2 bullet coverage, and hybrid metadata must recompute visible fallback fields from the selected source fields instead of inheriting `version_a` blindly.

## 2026-04-19 Hybrid v3 Direction-One Relaxation
- Hybrid bullet routing no longer hard-rejects `version_b` at slot selection time just because a slot misses its L2 keyword. `select_source_for_bullet_slot(...)` now keeps Version B as the default when there is no blocker, records the miss as a soft signal (`version_b_missing_l2`), and defers correction to a listing-level check.
- Listing-level L2 coverage is now the real gate. `modules/hybrid_optimizer.py` introduced `LISTING_L2_COVERAGE_THRESHOLD = 3` plus `analyze_listing_l2_coverage(...)`, and `finalize_hybrid_outputs(...)` now builds slot targets from the union of Version A + Version B keyword assignments before deciding whether repair is needed.
- Deterministic repair needed two follow-up fixes to work on real bullets rather than toy tests: compact tail replacement for overlong bullets (replacing generic `ideal for ...` endings instead of only appending) and writing repair results back into `decision_trace.keyword_assignments` with `source_version = "hybrid_repair"` so A10 scoring can see the rescued L2 coverage.
- Replaying the completed A/B artifacts from `output/runs/H91lite_US_r26_hybrid_v3_direction1_fix` through the new hybrid finalizer now produces `hybrid_repairs` on `B1` + `B2`, upgrades A10 from `70` to `90`, and records `L2关键词覆盖 2 个 bullet 槽位`. Hybrid still falls back to `version_a`, but the remaining blockers have moved up-stack to COSMO/Rufus rather than the original missing-L2 blind spot.
- A fresh live rerun started at `output/runs/H91lite_US_r27_hybrid_v3_direction1_fix2`, but the end-to-end pipeline stalled during Version B generation before hybrid finalization completed. For this iteration, the trustworthy validation source is the posthoc recomposition of the finished `r26` A/B artifacts with the current code, not the incomplete `r27` partial run.
