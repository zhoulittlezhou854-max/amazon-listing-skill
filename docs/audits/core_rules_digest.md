# Core Rules Digest — 2026-04-06

## Report & Scoring Dimensions (Module 8 Truth Table)
- **A10 (Traffic Muscle)** — Scores click-to-purchase readiness: Title front‑80 must contain brand + ≥1 L1 term + primary scene; keyword tiering coverage expects L1 in Title/B1/B2, L2 in remaining copy, L3 in Search Terms; conversion signals check B1–B5 for P0→P2 structure; Title length capped at 200 chars, repetition <2x.
- **COSMO (Semantic Brain)** — Measures scene coverage vs `scene_priority`, capability-scene bindings across used_for_func / used_for_eve / used_for_aud / capable_of; STAG tables must translate High‑Conv intents into persona/campaign plans; binding gaps or missing boundary statements lose COSMO points.
- **Rufus (QA / Dialog Layer)** — Audits FAQ sourcing, Review/Q&A alignment, description purity (no HTML/Markdown), A+ ≥500 words, 5× FAQ answers tied to verified specs; conflict_check penalizes hallucinations or claims lacking labelling/boundary clauses.
- **Price Competitiveness** — Median price from `price_context`; 85%–110% of median = 10 pts, 70%–85% = 7 pts, 110%–115% = 6 pts, outside ranges drop to 3 or 0; missing context removes the dimension from denominator.
- **Boundary & A+ sub-checks** — Module 8 now logs `boundary_declaration_check` (+/-10) and `aplus_word_count_check` (+/-15) to prove Rule 3b and Rule 6 compliance.

## Module Roles Across Workflow
- **A10 Toolkit (Node 3 + scoring)** — Builds tiered arsenal, labels 🔥High-Conv vs 🚀High-Traffic, routes L1 keywords into hero slots, enforces Title/Bullet gating.
- **COSMO Intent Graph (Node 3.5)** — Produces English-only user_identity + purchase_intent + pain_point + STAG groupings so downstream writing_policy sets scene priority.
- **Rufus QA Interface (Node 6/7/8)** — Requires structured bullets (answer blocks), FAQ seeds tied to review pain points, ensures Listing-as-datasource consistency.
- **QA / Policy Guard (writing_policy + risk_check)** — Encodes Rule 1–6 (Title formula, bullet format, HTML ban, boundary statement, ST byte caps, A+ 500 words) and surfaces auto-fix hooks.
- **Alt Text & Visual Brief (copy_generation/report_generator)** — Must follow `[Product] [Hero Spec] [Visual Hook] for [Scenario] - [Audience]` ≤120 chars, reuse High-Conv keywords w/out duplication.
- **Search Terms Subsystem** — Two-mode (Aggressive vs Defensive) outputs ≤249 bytes (JP 500, IN 200) with residual L2/L3 + backend-only or [SYNTH] placeholders; Ontology + capability fuse scrub duplicates & taboo terms.

## Keyword Tiering & Routing Principles
1. **Tier definitions** — L1 ≥10k monthly search volume (or top 20% real vocab); L2 1k–10k / COSMO scene words; L3 <1k but intent-safe. 🔥High-Conv = conversion ≥1.5% or purchase/search outliers; 🚀High-Traffic = CTR power terms.
2. **Routing** — L1 → Title + B1/B2 (always within front 80 chars). L2 → B3/B4 and description paragraphs to extend scene coverage. L3 + long-tail/residual → Search Terms + FAQ triggers; duplicates with Title banned.
3. **Source hierarchy** — Real vocab (country-specific) > order-winning CSV > ABA > synthetic fallback; scoring_mode `C_SYNTHETIC` zeros reserve_keywords so writing_policy triggers `[SYNTH]` generation and Harvest Loop instructions.
4. **Byte governance** — Search Terms trimmed per site limit via UTF-8 bytes, removing competitor brands, taboo concepts, capability-incompatible terms before final join.

## Capability · Scene · Audience Dimensions
- **Four binding types** — `used_for_func` (function), `used_for_eve` (event), `used_for_aud` (audience), `capable_of` (inferred capacity). Writing policy must populate all; missing type requires audit note.
- **Scene priority stack** — Minimum three: cycling_recording, underwater_exploration, travel_documentation; review/ABA signals can inject family_use, extreme_sports, etc. Scene list drives bullet focus, STAG groups, and ad routing.
- **Audience alignment** — Each scene maps to persona descriptors (commuter, diver, travel blogger, etc.) used in report_generator STAG table and bullet tone (formal `vous/Sie` as required).
- **Capability tiers** — P0 = hero spec + mount system; P1 = numeric proof (battery mins, waterproof depth); P2 = boundary/safety/accessory messaging. Capability-scene bindings must cite numeric evidence or degrade claim severity.

## Field Roles & Structural Expectations
- **Title** — `[Brand] + [Core product noun] + [Key quantified spec] + [Differentiator/Mount] + [Compatibility/Audience]`; front 70 chars must include hero spec, L1 keyword, target scene. Max 200 chars; no promo language.
- **Bullets** — 5 required, each `HEADER — Body`, EM DASH separator. B1 = mount system + primary scene; B2 = quantified capability; B3 = competitor pain point relief; B4 = boundary statement (Rule 3b) referencing constraints; B5 = warranty/accessories/compatibility. Each <200 chars, three headers need numerics.
- **Description** — Plain text (no HTML/Markdown) with headline + 3–4 sentence intro + `[Technical Specifications]` block listing Label: Value per verified_specs; mention accessory packaging plus boundary notes.
- **Search Terms** — Residual intent terms only (no Title/Bullet duplicates, no competitor brands, no taboo words). Accepts backend-only allowances (e.g., “4k action camera” if spec missing) and `[SYNTH]` placeholders until Harvest Loop recycles real data.
- **Alt Text** — ≤120 chars, include hero spec + visual hook + scenario + audience; reuse High-Conv keywords sparingly to avoid duplication penalties.

## Compliance Hardlines (Static_Compliance_Rules)
- Ban contact info, URLs, price/promotional talk (“best”, “#1”, “discount”), competitor comparisons, subjective absolutes (“100% safe”, “indestructible”).
- Backend Search Terms cannot contain brands, ASINs, or time-sensitive words (“new”, “sale”).
- Evidence claims require proof: environmental (“eco-friendly”), medical (“relieves pain”), antimicrobial, BPA-free all need lab data; otherwise replace with factual material statements.
- Review manipulation language (“contact us before leaving a review”, “free gift for review”) forbidden anywhere.
- Mandatory warnings for children/small parts when applicable.

## ActionCam & BodyCam Specific Restrictions
- **4K/UHD** — Visible fields may claim only if `video_resolution ≥ 3840x2160`; otherwise delete or rephrase to actual spec (“1080P”). Backend may retain keyword marked backend_only.
- **Waterproof / Underwater** — Visible claims allowed only with IP68 or waterproof case depth ≥10 m; must mention housing + depth same sentence. Without proof: downgrade to “splash-resistant”; underwater scenes removed.
- **Stabilization/EIS** — Require non-“None” `image_stabilization`. If unsupported, remove from visible areas; ST may keep.
- **Wireless/Bluetooth/WiFi** — Must appear in specs’ connectivity before surfacing; else delete.
- **Form-factor taboos** — Clip-on devices cannot imply helmet-only/tripod-only; body cams cannot suggest “police-only / law enforcement exclusive”.

## Claim Allow / Downgrade / Delete Logic
1. **Truth layer precedence** — Attribute table + parameter supplement = absolute facts. Conflicts resolved by removing downstream content.
2. **Allow** — When specs validate the trigger (e.g., `waterproof_case_max_depth_m = 30`), keep claim but append boundary (“only with case, 30 m max”).
3. **Downgrade** — When capability partially true (e.g., splash resistance), rewrite with precise limitation or shift to FAQ-only bucket.
4. **Delete** — When capability absent or prohibited (e.g., “military grade”, “bodycam for police only”): strip from visible + backend fields, log in audit trail.
5. **Backend-only tagging** — Some high-traffic terms (4K, stabilization) may stay in Search Terms even when deleted elsewhere, but flagged `[backend_only]` so Seller Central input stays compliant.
6. **Synthetic fallback** — When data_mode = SYNTHETIC_COLD_START, claims lean on safe descriptors + `[SYNTH]` placeholders; Module 5 instructs operator to replace after 14-day STR ingestion.
