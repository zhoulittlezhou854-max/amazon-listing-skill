# Protocol Audit (Phase 1)

## Keyword Tiering Map
| Pipeline stage | Data / fields | Alignment with scoring.py |
| --- | --- | --- |
| `tools.preprocess.preprocess_data` | Populates `PreprocessedData.keyword_data.keywords` from CSV and, for DE/FR, loads `real_vocab` via `load_real_country_vocab` storing top 20 rows with `keyword`, `search_volume`, `conversion_rate`. | Scoring tiers keywords straight off this structure (`keyword`/`search_term` + `search_volume`), so any normalization must land here before step 8. |
| `modules.keyword_arsenal.build_arsenal` | Builds `reserve_keywords`. When `real_vocab` exists, mirrors those terms back onto `preprocessed_data.keyword_data.keywords` so downstream nodes and scoring use local-language keywords. | Keeps fields compatible with `scoring._tier_keywords`, but currently only copies top 20 lower-case entries and drops tiers, causing later steps to guess at tiering again. |
| `modules.copy_generation.extract_tiered_keywords` | Recomputes L1/L2/L3 with hard-coded thresholds (>=10k, >=1k) using `real_vocab` first, fallback to `keyword_data`, else static mapping / `[SYNTH]`. Returns lowercase lists stored in-memory only. | Matches scoring thresholds, but limits each tier to 5–10 terms and lowercases them before insertion, meaning generated DE/FR text may not preserve original capitalization/orthography. |
| `modules.copy_generation.generate_title` & `generate_bullet_points` | Title uses `l1_keywords` verbatim; bullets/B3-B4 insert `l2`/`l3` tokens into English templates before translating. Search terms intentionally collects L2/L3 + category terms. | Scoring expects L1 in Title/B1-B2, L2 anywhere, L3 in `search_terms`. Current templates do not enforce slot coverage, and translation path can drop or Anglicize DE/FR tokens before scoring sees them, causing A10.keyword_tiering deficits. |
| `modules.scoring._score_keyword_tiering` | Builds three buckets: L1 hits from Title+Bullets, L2 hits from entire listing text, L3 hits from `search_terms`. Needs at least one hit per bucket for 30/30. | When the generated copy never embeds DE/FR tier keywords into Title/B1/B2 (or Search Terms), scoring records 0 despite `real_vocab` being loaded. |

**Observed issues:**
1. `extract_tiered_keywords` returns lower-cased tokens, but `_generate_title_in_language` and translators later mix English fallback phrases (`action camera 4k`) with partially translated scene words, so DE/FR L1 keywords rarely surface.
2. No structural hand-off ensures `writing_policy` reserves L1 slots for Title/B1/B2; templates can be satisfied with generic English terms even if DE/FR real keywords exist, leading to missing hits in the exact sections scoring checks.

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
