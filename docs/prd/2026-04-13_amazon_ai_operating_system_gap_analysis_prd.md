# Amazon AI Operating System Gap Analysis PRD v10.0

## 1. Document Summary

- **Document Type:** Formal PRD / Gap Analysis
- **Date:** 2026-04-13
- **Owner:** Amazon Listing Skill project
- **Decision:** Adopt the new algorithm document as the main direction for the next product cycle
- **Core Judgment:** The project should evolve from a `Listing Generation Engine` into a `Traffic Training + Evidence Alignment + Listing Deployment Engine`

## 2. Executive Summary

The current system already implements a meaningful part of the new Amazon AI operating logic. It is no longer a simple keyword-stuffing or static listing generator. The existing pipeline already contains:

- A10/COSMO/Rufus-aware writing policy and scoring foundations
- L1/L2/L3 keyword routing and report-side routing diagnostics
- Mini-brief and intent graph logic for scene, audience, and pain-point translation
- Accessory-to-experience transformation patterns inside preprocessing and copy generation
- Visual brief generation and intent-graph write-back hooks for A+ content
- Human-in-the-loop feedback, retention guardrails, and generation authenticity tracking
- Basic compute fallback metadata and listing readiness gating

However, the current system is still centered on producing listing assets. It does not yet operate as a closed-loop Amazon AI operating system that can answer:

- Is the ASIN evidence-rich enough for Rufus-style recommendation?
- Which traffic terms deserve budget to train future ranking and conversion?
- How should the same ASIN be expressed differently across DE/FR/IT/ES/UK?
- Which review negatives are currently undermining conversion or trust?
- Did a new content version damage historical organic traffic assets?

The next phase should not replace the existing architecture. It should extend it with four product epics and one cross-cutting control plane:

1. **ASIN Knowledge Base**
2. **Rufus Evidence Engine**
3. **Intent Weight Engine**
4. **EU Market Packs**
5. **Compute Tier Control Plane**

## 3. Current-State Assessment

### 3.1 What is already aligned

The following parts of the current repository already align with the new algorithm direction:

- `PRD.md` already shifts the roadmap toward traffic routing, COSMO micro-narratives, multimodal linkage, compute tiering, and ROI write-back.
- `modules/writing_policy.py` already implements L1/L2/L3 keyword routing, retention-aware routing, and strategy packaging for title/bullets/backend fields.
- `modules/intent_translator.py` already models scene, audience, pain point, resolution, supporting keywords, and mini-brief generation in `IntentNode`.
- `modules/copy_generation.py` already integrates scene/capability mapping, FAQ generation, audit metadata, visible fallback tracking, and localized field handling.
- `modules/report_generator.py` already exposes listing status, authenticity state, fallback field visibility, and routing diagnostics to operators.
- `modules/feedback_loop.py` and `modules/retention_guard.py` already establish feedback ingestion and historical traffic retention baselines.
- `app/streamlit_app.py` already supports new listing runs and manual feedback upload/re-run loops.

### 3.2 What the current architecture still is

The current architecture is best described as:

- A strong listing generation pipeline
- With partial routing intelligence
- With partial feedback incorporation
- With production-readiness guardrails
- But without a unified evidence substrate, market pack system, or intent-learning write-back engine

### 3.3 Product boundary shift required

The next-version product boundary should be explicitly redefined.

**Current boundary**
- Generate localized listing copy
- Score copy quality and readiness
- Preserve selected historical traffic terms
- Allow operator feedback upload

**Target boundary**
- Build a reusable ASIN entity and evidence base
- Audit claim-to-evidence consistency before and after copy generation
- Generate and validate Rufus-oriented question coverage
- Learn from PPC/Search Term/CTR/CVR signals and write back into intent weights
- Apply country-specific language, compliance, and intent strategy packs
- Make compute tier visibility actionable at the field level

## 4. Problem Statement

The project has reached the point where copy quality is no longer the main bottleneck. The highest-impact missing capabilities are:

1. Lack of a reusable ASIN entity knowledge layer
2. Weak review/Q&A evidence auditing
3. FAQ generation without a question-bank strategy
4. Shallow country-level localization strategy
5. No real intent-weight learning loop from performance metrics
6. Partial compute-tier metadata without operator-grade control
7. Weak bridge between content outputs and operating metrics

Without these capabilities, the system can generate better copy, but it cannot reliably train traffic, defend claims, localize intent deeply, or operate as a durable Amazon decision system.

## 5. Product Goals

### 5.1 Primary goals

- Convert dispersed product, review, Q&A, and feedback data into a reusable ASIN knowledge base
- Turn Rufus-related evidence sufficiency into an explicit audit instead of an implicit guess
- Turn PPC/Search Term/CTR/CVR signals into structured intent weights and future writing policy changes
- Support market-specific localization through strategy packs rather than hard-coded prompt variations
- Make compute tier status visible, configurable, and operationally meaningful

### 5.2 Non-goals for this cycle

- Building a full ad campaign management system
- Building a full BI platform or executive dashboard suite
- Fully automating off-Amazon attribution and creator ecosystem ingestion
- Building a complete FBT / bundle recommendation engine in the same cycle
- Replacing the existing pipeline with a new framework

## 6. Core Gaps to Close

### Gap 1: Missing ASIN entity knowledge layer

**Current state**
- Facts live across `preprocessed_data`, attribute parsing, copy-generation helpers, and report payloads.
- There is no stable `asin_entity_profile` or `asin_knowledge_graph` contract.

**Impact**
- Reuse is poor.
- Evidence is hard to trace.
- Claim validation becomes module-specific instead of system-wide.

**Required outcome**
- Build a unified entity profile that stores product facts, constraints, accessories, compatibility, scenes, pain points, claims, and evidence references.

### Gap 2: Missing review/Q&A evidence auditor

**Current state**
- FAQ generation exists.
- Risk checks exist.
- But review and Q&A are not systematically clustered and reconciled against attributes and generated copy.

**Impact**
- The system cannot reliably detect unsupported claims.
- Negative review themes are underused.
- Rufus evidence sufficiency cannot be measured.

**Required outcome**
- Add evidence clustering, consistency checks, evidence gaps, and structured operator reporting.

### Gap 3: Missing question-bank driven Rufus seeding

**Current state**
- `generate_faq()` can generate FAQs.
- There is no product-type and market-specific question bank.

**Impact**
- FAQ output remains generic.
- High-value conversion or compliance questions may be missed.

**Required outcome**
- Introduce templated question banks for product category, scenario class, and target market.

### Gap 4: Missing country-level market packs

**Current state**
- Multi-language support exists.
- Country-level expression strategy is not deep enough.

**Impact**
- DE/FR/IT/ES/UK differences are not systematically encoded.
- Local intent adaptation is inconsistent.

**Required outcome**
- Add market packs with language behavior, compliance prompts, lexical preferences, and risk reminders.

### Gap 5: Missing intent-weight write-back loop

**Current state**
- Feedback and retention logic exists.
- There is no structured ingestion and write-back layer for PPC/Search Term/CTR/CVR data.

**Impact**
- The system preserves traffic but does not learn traffic.
- High-performing terms do not materially reshape future policy.

**Required outcome**
- Build a metric-ingestion and write-back layer that updates scene and capability weights.

### Gap 6: Missing operator-grade compute tier control plane

**Current state**
- Fallback metadata exists.
- Visible fallback fields are tracked.
- Compute tier is not modeled per field in a way operators can act on.

**Impact**
- High-ROI fields cannot be selectively rerun.
- Reports do not clearly show tier provenance.

**Required outcome**
- Build field-level compute tier tags, rerun policy, and report rendering.

## 7. Target Architecture

The target architecture keeps the current pipeline but inserts structured sidecar engines at specific handoff points.

### 7.1 Pipeline shape

`tools/preprocess.py`
-> `modules/entity_profile.py`
-> `modules/evidence_engine.py`
-> `modules/intent_translator.py`
-> `modules/market_packs.py`
-> `modules/writing_policy.py`
-> `modules/copy_generation.py`
-> `modules/compute_tiering.py`
-> `modules/scoring.py`
-> `modules/report_generator.py`
-> `modules/intent_weights.py` write-back and historical learning

### 7.2 New core data objects

#### A. `asin_entity_profile`

Purpose: single reusable product/entity knowledge contract.

Suggested sections:
- `asin_id` / `product_code` / market identifiers
- `core_specs`
- `capability_registry`
- `accessory_registry`
- `compatibility_rules`
- `scene_candidates`
- `pain_point_candidates`
- `claim_registry`
- `faq_seed_candidates`
- `compliance_constraints`
- `evidence_refs`

#### B. `evidence_bundle`

Purpose: store structured evidence extracted from attributes, reviews, Q&A, and uploaded feedback.

Suggested sections:
- `attribute_evidence`
- `review_positive_clusters`
- `review_negative_clusters`
- `qa_clusters`
- `faq_gaps`
- `claim_support_matrix`
- `rufus_readiness`

#### C. `market_pack`

Purpose: country-level localization strategy contract.

Suggested sections:
- `locale`
- `lexical_preferences`
- `compound_word_rules`
- `value_narrative_bias`
- `compliance_reminders`
- `faq_templates`
- `risk_terms`
- `title_style_guidelines`
- `bullet_style_guidelines`

#### D. `compute_tier_map`

Purpose: track per-field generation provenance and rerun intent.

Suggested sections:
- `field_name`
- `tier_used`
- `fallback_reason`
- `rerun_recommended`
- `rerun_priority`
- `operator_note`

#### E. `intent_weight_snapshot`

Purpose: versioned learning output for future policy generation.

Suggested sections:
- `keyword`
- `scene_weight`
- `capability_weight`
- `traffic_weight`
- `conversion_weight`
- `retention_weight`
- `market_weight`
- `confidence_score`
- `source_window`

## 8. Product Epics

### Epic 1: ASIN Knowledge Base

**Objective**
Create a unified entity/evidence substrate that downstream modules can consume consistently.

**Scope**
- Normalize attribute-derived facts into a reusable profile
- Map accessories into posture/action/experience objects
- Consolidate compatibility, runtime, waterproof, and usage boundary facts
- Introduce claim registry with evidence references
- Persist the profile into run artifacts for audit and reuse

**Key outputs**
- `asin_entity_profile.json`
- `claim_registry.json`
- Preprocess integration hooks

**Primary consumers**
- `intent_translator.py`
- `writing_policy.py`
- `copy_generation.py`
- `report_generator.py`

**Acceptance criteria**
- Every visible claim can point to at least one source fact or rule
- Entity profile is generated for every run
- Existing generation flow remains backward-compatible when evidence is sparse

### Epic 2: Rufus Evidence Engine

**Objective**
Explicitly measure evidence sufficiency and question coverage for recommendation-friendly content.

**Scope**
- Cluster review positives and negatives
- Cluster Q&A by topic
- Compare attributes, evidence, and copy claims for consistency
- Detect unsupported claims and evidence gaps
- Generate question-bank-backed FAQ suggestions

**Key outputs**
- `evidence_bundle.json`
- `rufus_audit.json`
- FAQ gap diagnostics in reports

**Acceptance criteria**
- Top claims include support/weak/no-support status
- High-frequency negatives appear in operator-facing diagnostics
- FAQ generation can be seeded by question bank templates

### Epic 3: Intent Weight Engine

**Objective**
Let real performance data influence future content decisions.

**Scope**
- Ingest PPC and Search Term data
- Map terms to scenes/capabilities/intent nodes
- Update weight snapshots
- Feed weight changes into future routing and narrative prioritization
- Preserve historical organic anchors while allowing new winners to rise

**Key outputs**
- `intent_weight_snapshot.json`
- Updated weighting hooks in `writing_policy.py`
- Write-back-ready summary in report and Streamlit

**Acceptance criteria**
- High-CTR/high-CVR terms modify future prioritization
- Historical organic anchors remain protected unless explicitly downgraded
- Weight changes are auditable and versioned

### Epic 4: EU Market Packs

**Objective**
Move from translation support to country-specific expression strategy.

**Scope**
- Create market pack configs for DE/FR/IT/ES/UK
- Encode lexical preferences and compliance reminders
- Add market-specific FAQ templates and risk notes
- Apply market packs to routing, FAQ, and report generation

**Key outputs**
- `config/market_packs/*.json`
- Market pack loader and validation
- Localized report-side strategy summaries

**Acceptance criteria**
- Same ASIN can produce materially different strategy outputs by market
- Differences come from pack data and rules, not one-off prompt strings
- Compliance reminders are surfaced before listing export

### Epic 5: Compute Tier Control Plane

**Objective**
Turn generation provenance into an operator-facing control layer.

**Scope**
- Tag each visible field with compute tier
- Capture fallback reason and rerun recommendation
- Surface tier in reports and run artifacts
- Support high-ROI ASIN rerun strategy rules

**Key outputs**
- `compute_tier_map.json`
- Report rendering for `[Title: Native]` style tags
- Optional rerun configuration in run config or workspace metadata

**Acceptance criteria**
- Operators can see field-level tier provenance
- High-value fields can be selectively rerun
- Fallback-heavy outputs are clearly marked in reporting

## 9. Functional Requirements

### FR-1 Entity profile generation
- The system must generate a normalized `asin_entity_profile` during preprocessing.
- The profile must be available to downstream modules without re-parsing raw tables.

### FR-2 Claim registry
- The system must represent major visible claims as structured entries with source references.
- Claims must support `supported`, `weakly_supported`, and `unsupported` states.

### FR-3 Evidence clustering
- The system must cluster review and Q&A content by topic and sentiment polarity.
- Clusters must be reusable by reporting and FAQ generation.

### FR-4 Question bank
- The system must support product-type and market-specific question templates.
- FAQ generation must be able to consume question-bank prompts and evidence hints.

### FR-5 Market packs
- The system must load market packs by target country.
- Market pack load failure must degrade gracefully to existing language behavior.

### FR-6 Intent weight write-back
- The system must ingest structured performance rows and produce a versioned weight snapshot.
- The write-back layer must not overwrite retention anchors blindly.

### FR-7 Compute tier visibility
- The system must expose field-level compute tier and fallback reason in reports and run outputs.

### FR-8 Backward compatibility
- Existing listing generation must remain functional when new evidence sources are absent.

## 10. Non-Functional Requirements

- Maintain compatibility with current run/workspace model
- Keep run artifacts JSON-readable and auditable
- Avoid large-scale rewrites of `copy_generation.py` without contract isolation
- Ensure deterministic fallback paths for missing evidence or missing market pack data
- Preserve human-in-the-loop workflows in Streamlit

## 11. Data and Storage Strategy

### 11.1 New run artifacts
- `output/runs/<run>/asin_entity_profile.json`
- `output/runs/<run>/evidence_bundle.json`
- `output/runs/<run>/rufus_audit.json`
- `output/runs/<run>/compute_tier_map.json`
- `output/runs/<run>/intent_weight_snapshot.json` when feedback metrics exist

### 11.2 New config assets
- `config/market_packs/DE.json`
- `config/market_packs/FR.json`
- `config/market_packs/IT.json`
- `config/market_packs/ES.json`
- `config/market_packs/UK.json`
- `config/question_banks/action_camera.json`
- `config/question_banks/eu_compliance.json`

## 12. Operator Experience Changes

Operators should gain answers to the following questions directly in reports or Streamlit:

- Which visible claims are weakly supported?
- Which review negatives need copy or FAQ mitigation?
- Which FAQ gaps are blocking Rufus evidence completeness?
- Which country pack altered lexical strategy or compliance reminders?
- Which fields are fallback-driven and should be rerun?
- Which high-performing terms are now boosting specific scenes or capabilities?

## 13. Success Metrics

### 13.1 Product metrics
- Higher proportion of claims with explicit support references
- Higher FAQ coverage for predefined high-value question classes
- More market-specific variation quality across DE/FR/IT/ES/UK
- Higher operator trust in provenance and readiness reporting

### 13.2 System metrics
- Percentage of runs producing valid `asin_entity_profile`
- Percentage of visible claims with support classification
- Percentage of runs producing field-level `compute_tier_map`
- Percentage of feedback ingestions producing usable `intent_weight_snapshot`

### 13.3 Business-facing proxy metrics
- Better preservation of historical organic traffic anchors
- Improved operator ability to identify missing evidence before launch
- Improved prioritization of high-converting scene/capability combinations

## 14. Roadmap and Prioritization

### P0 - Must ship first
- ASIN Knowledge Base foundation
- Evidence bundle and claim consistency audit
- Rufus question bank for Action Camera and EU compliance
- DE/FR/IT/ES/UK market pack v1
- Field-level compute tier tags in reports

### P1 - Should ship next
- PPC/Search Term/CTR/CVR ingestion
- Intent weight snapshot and write-back
- Scene/capability reweighting in writing policy
- Streamlit visibility for evidence and weight changes

### P2 - Later extension
- FBT / bundle relationship graph
- External traffic / review-source theme ingestion
- EU after-sales and SOP modules
- 30-day iteration panel and pre-launch checklist automation

## 15. Risks and Mitigations

### Risk 1: Scope explosion
Mitigation: keep P0 focused on evidence, market packs, and compute tiering before revenue instrumentation sprawl.

### Risk 2: Monolithic file growth
Mitigation: add new sidecar modules rather than expanding `copy_generation.py` and `writing_policy.py` indefinitely.

### Risk 3: Evidence ambiguity
Mitigation: use explicit confidence levels and degrade to `weakly_supported` instead of binary pass/fail.

### Risk 4: Market pack brittleness
Mitigation: keep pack schema small and versioned; fall back to existing language behavior.

### Risk 5: Weight write-back corrupting stable traffic
Mitigation: combine write-back with existing retention guard logic and cap automatic demotion strength.

## 16. Dependency Map

- `tools/preprocess.py` must emit reusable structured profile input.
- `modules/intent_translator.py` must accept entity/evidence enrichments.
- `modules/writing_policy.py` must accept market pack and weight snapshot overlays.
- `modules/copy_generation.py` must consume question-bank and claim-support signals.
- `modules/report_generator.py` must surface evidence, market, and compute insights.
- `app/streamlit_app.py` and `app/services/run_service.py` should expose new artifacts gradually.

## 17. Release Recommendation

Approve this PRD as the mainline direction for the next product cycle.

Implementation should proceed in two waves:

- **Wave 1:** P0 evidence + localization + compute observability
- **Wave 2:** P1 intent learning and operator-facing feedback visibility

This sequencing preserves momentum, reuses the current architecture, and upgrades the project from a copy generator into an operating system for Amazon traffic, evidence, and deployment decisions.
