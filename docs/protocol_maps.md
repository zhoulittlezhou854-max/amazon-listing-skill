# Protocol Audit (Keyword Protocol)

## Keyword Protocol Flow

```text
preprocess -> keyword_protocol -> keyword_utils/keyword_arsenal -> writing_policy -> copy_generation reconciliation -> scoring -> report_generator
```

Authoritative keyword fields:
- `quality_status`: `qualified`, `watchlist`, `natural_only`, `rejected`, or `blocked`.
- `traffic_tier`: country/category-relative `L1` / `L2` / `L3` for qualified keywords only.
- `routing_role`: intended placement (`title`, `bullet`, `backend`, `residual`, `natural_only`, `rejected`).
- `opportunity_score` and `blue_ocean_score`: demand/fit/conversion/competition weighted opportunity signals.
- `assigned_fields`: final observed placement after title/bullets/search terms are finalized.

## Keyword Tiering Map
| Pipeline stage | Data / fields | Alignment with scoring.py |
| --- | --- | --- |
| `tools.preprocess.preprocess_data` | Preserves raw keyword metrics (`search_volume`, `click_share`, `ctr`, `conversion_rate`, `monthly_purchases`, `avg_cpc`, `product_count`, `title_density`) from country-specific tables. | It does not decide tiers; it preserves evidence for `modules.keyword_protocol`. |
| `modules.keyword_protocol.build_keyword_protocol` | Applies quality gates, country-relative traffic tiering, product-fit scoring, opportunity scoring, blue-ocean scoring, and routing-role assignment. | This is the single source of truth for `quality_status`, `traffic_tier`, `routing_role`, `opportunity_score`, and `blue_ocean_score`. |
| `modules.keyword_utils.extract_tiered_keywords` / `modules.keyword_arsenal.build_arsenal` | Consume protocol rows and expose compatibility lists (`l1`, `l2`, `l3`) plus `_metadata`. | Legacy tier lists are projections of qualified protocol rows, not independent thresholds. |
| `modules.writing_policy` | Routes by `routing_role`: title=head traffic anchors, bullets=conversion/blue-ocean opportunities, backend=residual safe terms. | L3 no longer means "always backend"; role metadata is authoritative. |
| `modules.copy_generation` | Generates final visible copy, then reconciles actual title/bullet/search-term placements into `assigned_fields`. | Trace records final observed placement after rerender and search terms are settled. |
| `modules.scoring._score_a10` | Scores head traffic anchors, qualified placement, bullet conversion coverage, backend residual coverage, and rejected/blocked visible keywords. | A10 rewards correct use of qualified protocol keywords, not raw keyword stuffing. |
| `modules.report_generator` | Renders keyword protocol decisions with traffic tier, quality status, routing role, opportunity, assigned fields, and reason. | Reports expose why a term was used, reserved, natural-only, or rejected. |

**Current invariant:**
1. Absolute numbers such as 1,000 or 10,000 are not global tier cutoffs; different countries/categories are tiered by relative demand and keyword quality.
2. Blue-ocean keywords must still have demand, product fit, engagement/conversion signal, and lower relative competition; "low volume" alone is not blue-ocean.
3. `assigned_fields` is an audit trail of final observed placement; scoring decides whether that placement is good.

## Capability Scene Binding Map
| Pipeline stage | Data / fields | Alignment with scoring.py |
| --- | --- | --- |
| `tools.preprocess` | Extracts `core_selling_points` mostly in Chinese (e.g., "防抖", "4K录像"). No canonical schema. | Scoring later expects whatever strings end up inside `writing_policy["capability_scene_bindings"]`, so inconsistent languages break downstream matching. |
| `modules.writing_policy.generate_policy` | `scene_priority` is a list of English labels ("cycling_recording"). `create_capability_scene_bindings` copies raw `core_selling_points` strings into `capability` fields and attaches English `allowed_scenes`. | Capability names stay Chinese, scenes stay English-with-underscores. |
| `modules.intent_translator.generate_intent_graph` | Produces English canonical capability tags ("waterproof", "4K_video", etc.) but these are never fed back into `writing_policy` or bindings. | Lost opportunity to unify naming. |
| `modules.copy_generation.generate_multilingual_copy` | Normalizes `core_selling_points` to English for internal generation, then translates outputs to target languages; `capability_scene_bindings` remain untouched. Bullets mention translated capability text (e.g., "4K-Aufnahme"), not the Chinese strings stored in bindings. | `scoring._score_capability_binding` looks for literal `binding["capability"]` and `allowed_scenes` substrings in the final listing. Because bindings use Chinese + English labels but the copy is German/French, none of the substrings align, yielding 0 bindings satisfied. |
| `scoring._score_capability_binding` | Counts binding satisfied when `capability` substring and any allowed scene substring both appear in listing text. Case-insensitive but otherwise literal. | Requires canonical shared vocabulary; current pipeline never ensures that. |

**Observed issues:**
1. Capabilities are stored in CN while final bullets are translated into DE/FR (with occasional English scaffolding). No canonical English layer is persisted back into `writing_policy`, so scoring can never detect the capability terms.
2. Scene labels inside bindings stay as camel/underscore English codes, yet copy generation translates them to localized words, so `allowed_scenes` strings never appear verbatim in the listing text, blocking bindings even if capability text matched.
