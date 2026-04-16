# Night Shift Plan — Pipeline & Research Map (2026-04-06)

## 1. Pipeline Graph (current implementation)
```
main.py workflow
└─ Step 0: tools.preprocess.preprocess_data
    • load run_config + attribute / keyword / review / ABA files
    • extract selling points, accessory info, quality score, real_vocab snapshot
└─ Step 1: visual_audit (modules/visual_audit.py)
└─ Step 2: modules.keyword_arsenal.build_arsenal
└─ Step 3: capability/risk checks (modules.capability_check + tools)
└─ Step 4: intent translator (modules.intent_translator)
└─ Step 5: modules.writing_policy.generate_writing_policy
└─ Step 6: modules.copy_generation.generate_listing
└─ Step 7: modules.risk_check.run_risk_checks
└─ Step 8: modules.scoring.calculate_scores
└─ Step 9: modules.report_generator.generate_listing_report
```
Supporting utilities:
- tools.data_loader handles CSV parsing (XLSX currently flaky before this shift).
- modules.keyword_utils builds tiered keywords and keyword slots.
- modules.language_utils canonicalizes capability/scene labels.

### 1.1 Module Boundaries Snapshot
| Module | Responsibility Snapshot | Primary Inputs | Outputs / Consumers |
| --- | --- | --- | --- |
| `tools.preprocess` | Normalize run_config + 4 core files, tag truth layers (`verified_specs`, parameter constraints), detect `real_vocab` + data_mode. | Attribute TXT, ABA CSV, competitor CSV, full-dimension CSV, manual supplements. | `PreprocessedData` object used by every later step. |
| `tools.data_loader` | Shared CSV/XLSX reader with field standardization + dependency messaging. | Filepaths from config/makefile. | Row dicts for preprocess + tests; also used by future regression fixtures. |
| `modules.keyword_arsenal` | Tier keywords (L1/L2/L3), assign 🔥/🚀, compute price_context + review pain points, store keyword provenance. | `PreprocessedData.keyword_data`, optional `real_vocab`, review insights. | Arsenal JSON powering writing_policy, copy_generation, scoring, report_generator. |
| `modules.intent_translator` | Build English-only intent graph + STAG table, infer capability tags, persona + scenario clusters. | Arsenal reserve keywords, preprocessed data meta. | Intent graph consumed by writing_policy, copy_generation, and Module 7 STAG report. |
| `modules.writing_policy` | Encode `scene_priority`, capability-scene bindings (used_for_func/eve/aud/capable_of), bullet slot roles, taboo pairs, search-term plan. | Preprocessed data, arsenal, intent graph, compliance snippets. | Policy JSON enforced by copy_generation + referenced by scoring/report_generator. |
| `modules.copy_generation` | Render Title/Bullets/Description/Search Terms/APLUS/FAQ per policy; apply `[SYNTH]` fallback, capability fuse, and boundary statements. | Writing policy, keyword slots, verified specs, target language. | Listing draft JSON reviewed by risk_check + scoring. |
| `modules.risk_check` / `modules.capability_check` | Apply static + actioncam compliance rules, log deletes/downgrades, enforce Rule 1–6 before Module 8. | Listing draft, compliance files, parameter constraints. | Risk report for report_generator + scoring. |
| `modules.scoring` | Module 8 ground truth (A10/COSMO/Rufus/Price + boundary/A+ sub-checks). | Preprocessed data, writing policy, generated copy. | `scoring_results.json` + per-dimension notes consumed by report_generator. |
| `modules.report_generator` | Merge data lineage, keyword placement tables, STAG summary, compliance verdicts for audits + docx export. | Preprocessed data, arsenal, policy, listing draft, scoring + risk outputs. | `listing_report.md` + feed for docx exporter. |

### 1.1 Module Boundaries Snapshot
| Module | Responsibility Snapshot | Primary Inputs | Outputs / Consumers |
| --- | --- | --- | --- |
| `tools.preprocess` | Normalize run_config + 4 core files, tag truth layers (`verified_specs`, parameter constraints), detect `real_vocab` + data_mode. | Attribute TXT, ABA CSV, competitor CSV, full-dimension CSV, manual supplements. | `PreprocessedData` object used by every later step. |
| `tools.data_loader` | Shared CSV/XLSX reader with field standardization + dependency messaging. | Filepaths from config/makefile. | Row dicts for preprocess + tests; also used by future regression fixtures. |
| `modules.keyword_arsenal` | Tier keywords (L1/L2/L3), assign 🔥/🚀, compute price_context + review pain points, store keyword provenance. | `PreprocessedData.keyword_data`, optional `real_vocab`, review insights. | Arsenal JSON powering writing_policy, copy_generation, scoring, report_generator. |
| `modules.intent_translator` | Build English-only intent graph + STAG table, infer capability tags, persona + scenario clusters. | Arsenal reserve keywords, preprocessed data meta. | Intent graph consumed by writing_policy, copy_generation, and Module 7 STAG report. |
| `modules.writing_policy` | Encode `scene_priority`, capability-scene bindings (used_for_func/eve/aud/capable_of), bullet slot roles, taboo pairs, search-term plan. | Preprocessed data, arsenal, intent graph, compliance snippets. | Policy JSON enforced by copy_generation + referenced by scoring/report_generator. |
| `modules.copy_generation` | Render Title/Bullets/Description/Search Terms/APLUS/FAQ per policy; apply `[SYNTH]` fallback, capability fuse, and boundary statements. | Writing policy, keyword slots, verified specs, target language. | Listing draft JSON reviewed by risk_check + scoring. |
| `modules.risk_check` / `modules.capability_check` | Apply static + actioncam compliance rules, log deletes/downgrades, enforce Rule 1–6 before Module 8. | Listing draft, compliance files, parameter constraints. | Risk report for report_generator + scoring. |
| `modules.scoring` | Module 8 ground truth (A10/COSMO/Rufus/Price + boundary/A+ sub-checks). | Preprocessed data, writing policy, generated copy. | `scoring_results.json` + per-dimension notes consumed by report_generator. |
| `modules.report_generator` | Merge data lineage, keyword placement tables, STAG summary, compliance verdicts for audits + docx export. | Preprocessed data, arsenal, policy, listing draft, scoring + risk outputs. | `listing_report.md` + feed for docx exporter.

## 2. Known Weaknesses (before historical induction)
1. **Loose rule encoding**
   - writing_policy defaults to `DEFAULT_4SCENE_POLICY` for most locales even when data suggests different scene/capability emphasis.
   - copy_generation frequently ignores per-bullet intentions; bullets collapse into generic feature lists.
2. **Keyword routing opacity**
   - keyword_arsenal records tier + `high_conv`, but there is no deterministic rule ensuring L1 terms land in Title/B1/B2 while L3 terms reserve Search Terms.
   - search terms often duplicate title/bullet phrases, hurting usefulness.
3. **Capability-scene bindings**
   - DEFAULT_CAPABILITY_SCENE_BINDINGS are static; intent_translator rarely overrides them with data-backed bindings, reducing COSMO scores when products emphasize niche scenes (e.g., moto vlog, FPV).
4. **Source prioritization**
   - preprocess loads ABA/order-winning/real_vocab but downstream modules don’t track provenance (order-winning vs ABA) when choosing hero keywords.
5. **Reporting/observability gaps**
   - report_generator outputs narrative but doesn’t clearly log which rule decided each slot; debugging is hard.
6. **Historical knowledge untapped**
   - config/products folders contain richly structured prior deliverables (docx, specs) but workflow never learns slot rules from them.

## 3. Rule-Based vs Weakly Specified Components
| Component | Current State |
| --- | --- |
| `tools.preprocess` | Partially rule-based (clear priority for attribute/specs) but real_vocab + source tagging underused downstream. |
| `modules.keyword_arsenal` | Tiering logic exists but routing rules are implicit/heuristic; lacks deterministic mapping to slots. |
| `modules.intent_translator` | Heuristic; relies on regex/canonical tables, limited coverage for new capabilities/scenes. |
| `modules.writing_policy` | Contains default slot plan, but real policies seldom deviate; lacks explicit numeric/spec placement rules. |
| `modules.copy_generation` | Template-style but not policy-driven: B1–B5 share similar structure, numeric proof & accessories wander. |
| `modules.report_generator` | Provides summaries but not explicit rationale per slot/keyword source. |

## 4. Historical Artifact Strategy
We will treat the four product folders as follows:
- **Training / rule induction**: `H91lite_US`, `H91POR_US`, `T70_real_DE`
  - Extract: structured inputs (attribute/ABA/order-winning/multi-dim), supplemental text, historical docx outputs.
  - Goal: map how professional writers placed keywords, capabilities, audiences, and numeric evidence without copying their text.
- **Held-out / blind validation**: `T70_real_FR`
  - Inputs inspected pre-run.
  - Historical docx kept unseen until after first blind run; later used only for structural comparison.

For each training product we will create `docs/audits/history_analysis_<product>.md` capturing:
- Available inputs and notable data signals (e.g., standout ABA terms, numeric specs, accessory focus).
- Historical output structure: title composition (brand + spec + scene), bullet roles (e.g., B1 mounting, B2 stabilization), search-term types.
- Source-to-slot deductions: which data types likely fueled each field.
These analyses will feed Phase 2 rule induction without preserving any literal phrasing.

## 5. Immediate Research Tasks
1. Finish full readings (REPO_RULES, REPO_INDEX, docs/prd, docs/knowledge-base, docs/audits, docs/summaries) as reference for constraints.
2. Skim the targeted modules to understand how current logic deviates from PRD specs.
3. Plan docx parsing / structural extraction approach (likely python-docx) that records bullet role + keyword types without storing raw text.
4. Inventory training-folder files, confirm naming conventions, and design a schema for `history_analysis_*.md`.

## 6. How Historical Artifacts Will Clarify Logic
- **Slot allocation**: Titles/bullets/search terms in legacy docs reveal how human writers balance hero specs vs. scenes vs. accessories.
- **Keyword provenance**: Compare historical wording with ABA/order-winning tables to infer which source each slot prioritized.
- **Capability coverage**: Identify consistent pairing between capabilities (EIS, waterproof, dual screens) and target scenes (cycling, underwater, travel).
- **Conversion proof**: Determine where numeric proof (battery mins, resolution, fps) sits (often B2/B3) and encode as general rule.
- **Accessory / kit mentions**: Understand whether accessories belong in B4/B5 vs. description.

## 7. Deliverables After Phase 0
- This plan (current file) anchors the multi-phase roadmap.
- Future docs listed in mission (historical_rule_induction, regression coverage, run summaries, holdout evaluation, final summary) will build on findings from training artifacts.
