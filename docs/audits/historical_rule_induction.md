# Historical Rule Induction — Cross-Sample Synthesis (H91lite_US / H91POR_US / T70_real_DE)

> Rules apply across bodycam/action-cam workflows regardless of site. Use as guardrails for writing_policy, copy_generation, scoring, and compliance modules.

## 1. Title Strategy
1. **Slot order**: `[Brand] + [Hero runtime or resolution] + [Mount/optics capability] + [Primary scenario audience] + (Spec pack with language, storage, form factor)`. Front-70 characters must contain brand, ≥1 L1 keyword, and the primary scene persona (security, vlog, commuting). Runtime or resolution must be quantified (minutes, 4K, dual display) rather than adjectives.
2. **Capability gating**: Only elevate capabilities verified by attribute/supplement truth layer. Waterproof, EIS, dual-screen, or storage claims must appear with the appropriate qualifier (e.g., “with case” or “1080P EIS”). Unsupported modes (5K stabilization, waterproof-without-housing) are never allowed in Title.
3. **Persona mix**: Pair functional noun (“action camera”, “bodycam”, localized terms) with scenario nouns (“hands-free content creation”, “Beweissicherung”, “commuting security”) to signal A10 + COSMO simultaneously. Reserve compatibility lists (mount types, battery pods) for parentheses after main clause.
4. **Clutter control**: No duplicated keywords, promo adjectives, or competitor references. Each unique value (runtime, mount system, weight) appears once. Keep ≤200 characters.

## 2. Bullet Role Model
| Slot | Responsibility | Content Rules | Typical Evidence |
| --- | --- | --- | --- |
| B1 | Mount + primary scenario | Name the mounting system (magnetic clip, helmet/bike mount) + top scene (daily vlog, security, cycling). Mention capability, not brand slogans. | Attachment types, POV use cases. |
| B2 | Numeric runtime / power tier | Quantify minutes, capacity split (internal vs pod), or battery endurance. Tie to workday/shift context. If EIS is present, pair with motion scenario (cycling). | Minutes, mAh, shift duration. |
| B3 | Capability + persona expansion | Cover opto/electronic feature (rotatable lens, dual display, evidence-grade 1080P). Map to persona (security staff, delivery riders, travellers). | Resolution, field of view, persona labeling. |
| B4 | Boundary + accessory-enabled capability | Surface any claim requiring qualifiers (waterproof depth, stabilization limit, accessory pack). Always mention condition (“only with housing”, “EIS active in 1080P/4K”). | 30 m depth, supported modes, kit list. |
| B5 | Comfort / after-sales / compatibility | Address ergonomics (weight), app control, warranty, compatibility statements. Use to reassure reviewers and Rufus. | Weight (g), warranty months, WiFi/app features. |
**Format rules**: EM DASH separator, uppercase/language-appropriate headers, <200 characters each, minimum three headers containing numerics or technical tokens.

## 3. Search Terms Principles
1. **Residual-only**: Include L2/L3 long-tail terms not already present in Title/Bullets. Combine plural/synonym variants (English + local language). Avoid punctuation and duplicate tokens.
2. **Backend-only markers**: Allow high-traffic but disallowed claims (e.g., “4k action camera”, “stabilization camera”) only if flagged `backend_only` upstream. Visible copy must omit unsupported claims.
3. **Byte discipline**: Enforce UTF-8 byte limits per site (US/EU=249, JP=500, IN=200). Trim from least-specific tail first.
4. **Taboo removal**: No competitor brands, promo words, subjective adjectives, or country names. Automatically strip terms conflicting with physical_form/taboo_concepts.

## 4. Data Source Hierarchy & Routing
1. **Priority order**: Real vocab (localized spreadsheet) → order-winning CSV (conversion) → ABA (volume) → synthetic fallback. Reserve keywords inherit metadata (tier, source) for audit trails.
2. **Tier thresholds**: Approximate L1 = top 20% volume (≥10k), L2 = 20–60%, L3 = remainder or conversion-driven long tail. Always log tier in arsenal and pass to writing_policy.
3. **Routing**: L1 feeds Title + B1/B2 and first Alt Text entries; L2 populates B3/B4, description, STAG groups; L3 fuels Search Terms, FAQ seeds, backend-only slots. When `data_mode=SYNTHETIC_COLD_START`, leave reserve_keywords empty so writing_policy triggers `[SYNTH]` generation plus Harvest Loop instructions.
4. **Traceability**: Every keyword entry must keep `source_type` (real_vocab / aba / order_winning / synthetic) for report_generator to explain slot decisions.

## 5. Capability–Scene–Audience Bindings
1. **Coverage**: writing_policy must emit bindings for all four COSMO types—used_for_func (mechanical ability), used_for_eve (event/time), used_for_aud (persona), capable_of (numeric proof). Missing types require explicit audit notes.
2. **Scene priority**: Always include at least three scenes ordered by data evidence (e.g., security/evidence → commuting/cycling → vlog/travel → underwater/adventure). Scenes feed bullet slot plan, Alt Text, STAG rows.
3. **Evidence pairings**: Capabilities with numeric proof (battery minutes, waterproof depth, weight, resolution) must cite numbers in whichever slot they appear. When capability is accessory-dependent, mention condition in same sentence.
4. **Persona tone**: Align pronouns and register with locale (German formal “Sie”, French “vous”). Persona tags (security staff, delivery riders, content creators) animate STAG rows and bullet contexts.

## 6. Compliance & ActionCam Claim Governance
1. **Truth-layer enforcement**: All copy modules consume `verified_specs`, `parameter_constraints`, and `capability_fuse` rules before emitting claims. Unsupported capabilities trigger either downgrade text (“splash-resistant”) or deletion. Backend retention allowed only via explicit flag.
2. **Waterproof gating**: Only allow visible waterproof/underwater statements when (a) spec depth ≥10 m and (b) text states housing requirement in same clause. Otherwise, degrade to “splash-resistant” or omit entirely.
3. **EIS/Resolution gating**: EIS language only when `Has Image Stabilization != None`. For products where only certain modes support EIS (e.g., 1080P/4K), mention the supported modes; never imply stabilization at 5K.
4. **Runtime messaging**: Advertise battery pod/extension only if accessory list includes those items; split runtime numbers (internal vs pod) to avoid overclaiming.
5. **Taboo scenes**: Clip-on/bodycam devices must avoid “police-only / law enforcement exclusive” wording; focus on generic safety/evidence use cases. Helmet-only or tripod-only statements are forbidden unless form factor supports them exclusively.
6. **Downgrade vs delete vs backend**: When facts partially support a claim, downgrade in-place with explicit limiter (e.g., “splash resistant for light rain”). If the claim is unsupported, delete from visible copy and only retain the keyword in Search Terms when flagged `backend_only`. Backend retention requires a log entry noting the taboo reason so Seller Central uploads are traceable.
7. **Audit reporting**: writing_policy should expose `forbidden_pairs`, `faq_only_capabilities`, and `capability_scene_bindings` so report_generator can explain every downgrade/delete decision. Copy generation must log when [backend_only] or downgrade actions occur for Module 8 review.

## 7. Data-to-Module Hooks
- Preprocess must tag each fact with `confidence_source` (attribute / supplement / ABA / competitor / synthetic).
- keyword_arsenal outputs `keyword_route_plan` summarizing tier → field mapping.
- writing_policy includes `title_slots`, `bullet_slot_rules`, `search_term_plan`, `boundary_hooks`, `compliance_directives` (housing requirement, EIS limitation) to ensure deterministic behavior.
- copy_generation strictly consumes the policy: Title uses defined slots, bullets inherit rule per slot, Search Terms implement `priority_tiers` and `backend_only` masks. No free-form rewrites.
- report_generator states (a) which rules fired, (b) what claims were downgraded/deleted, and (c) which scenes/personas were covered, ensuring auditability.

These rules are derived from the three training artifacts but expressed generically so they can govern any future SKU or locale.
