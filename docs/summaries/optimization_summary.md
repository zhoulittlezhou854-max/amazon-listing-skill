# Optimization Summary

## Code Changes
- Introduced `modules/language_utils.py` and `modules/keyword_utils.py` to centralize canonical capability/scene naming, translation dictionaries, and tiered keyword allocation.
- Rebuilt `modules/writing_policy.py` to canonicalize capability labels, attach localized/English scene names, and emit structured `keyword_slots` consumed downstream (default 4-scene policy now reuses the same logic).
- Refactored `modules/copy_generation.py` to consume shared keyword/capability utilities so Titles/Bullets/Search Terms explicitly deploy L1/L2/L3 slots and bilingual capability-scene phrases that scoring can detect.
- Updated `modules/intent_translator.py` to emit canonical capability slugs, keeping COSMO planning aligned with scoring terminology.
- Added regression tests in `tests/minimal_protocol_tests.py` capturing K1–K3 keyword tiering and C1–C3 capability-scene binding behavior.
- Wired `main.py` to pass the full `preprocessed_data` object into the default writing policy generator so fallback flows also benefit from canonical names, keyword slots, and localized bindings.
- Documented audit findings in `docs/protocol_maps.md`.

## Protocol Maps
Detailed keyword_tiering and capability_scene_binding protocol audits live in `docs/protocol_maps.md`. They describe the scoring expectations, the pre-existing data flows, and the corrected handshakes between preprocess → arsenal → policy → copy generation.

## Minimal Test Cases
| Case | Scenario | Result |
| --- | --- | --- |
| K1 | Title/B1/B2 include L1/L2 + Search Terms hold L3 | `keyword_tiering` score 30 (note `L1:2 L2:1 L3:1`) |
| K2 | Only L3 long-tail phrases used | `keyword_tiering` score 10 (`L1:0 L2:0 L3:1`) |
| K3 | Keywords only appear in Search Terms | `keyword_tiering` score 10 (`L1:0 L2:0 L3:1`) |
| C1 | Canonical capability + scene strings match listing text | `capability_scene_binding` score 40 (`满足 2/2 条绑定`) |
| C2 | Internal labels left in CN while copy is EN/DE | `capability_scene_binding` score 0 |
| C3 | Capabilities defined but not surfaced in bullets | `capability_scene_binding` score 0 |

(See `tests/minimal_protocol_results.json` for raw outputs.)

## Real Sample Scores (After Fix)
| Sample | A10 (Title / Keyword / Conversion) | COSMO (Scenes / Bindings / Audience) | Rufus Subtotal | Total / Max |
| --- | --- | --- | --- | --- |
| DE (`output_de_opt2`) | 30 / 20 / 20 | 40 / 40 / 20 | 87 | 257 / 300 |
| FR (`output_fr_opt`) | 30 / 20 / 20 | 40 / 30 / 20 | 54 | 214 / 300 |

Both locales now keep non-zero `A10.keyword_tiering` and meaningful `COSMO.capability_scene_binding` thanks to bilingual keyword slots and canonical capability labels.

## Remaining Gaps / Next Steps
- Step 4 (intent graph) still throws `list index out of range`; the workflow falls back to the 4-scene policy, which now produces correct bindings, but stabilizing the intent translator would restore richer strategy variants.
- `keyword_tiering` L3 bucket remains 0 for the provided DE/FR samples because the source keyword tables lack genuine long-tail search terms; once more L3 data lands in real_vocab, the new slotting logic will propagate them into Search Terms automatically.
