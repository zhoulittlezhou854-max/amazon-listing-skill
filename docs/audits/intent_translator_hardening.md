# Intent Translator Hardening (Step 4)

## Root Cause
- `_build_stag_groups` instantiated the `scene_templates` list but attempted to index into an empty `stag_groups` list (`stag_groups[1]`, `stag_groups[2]`, ...). Whenever keyword pools were empty—or smaller than expected—the code tried to access elements that never existed, producing `IndexError: list index out of range` and aborting Step 4.
- Additional minor assumptions (e.g., `kw.get("keyword")` returning non-empty strings) meant that even after the first crash was avoided, missing keyword text could trickle down into empty lists and leave later stages without any STAG keywords.

## Fixes Implemented
- Rewired `_build_stag_groups` to operate directly on `scene_templates`, with explicit length checks before any index access. Every branch now falls back to `scene_templates[0]` if the desired template slot is unavailable.
- Added placeholder inserts when zero real keywords are available so each STAG still receives at least one token. Synthetic keywords (`[SYNTH]_action_camera`, `[SYNTH]_keyword`) make it explicit in downstream audits that the data is generated.
- Guarded keyword extraction by coalescing to empty strings before calling `.lower()`, so `None` values can’t raise.
- Left the rest of the public JSON contract untouched; when there truly are no keywords, the module now emits empty intent/STAG arrays rather than throwing.

## Remaining Edge Cases
- The translator continues to mirror whatever keyword volume upstream provides. If both real vocab and keyword tables are empty, Step 4 now synthesizes placeholder STAG keywords but still has no grounded data to build intents; downstream stages must tolerate those placeholders.
- Future improvements could include logging soft warnings when synthetic fallbacks are inserted, or deriving default personas/scenarios from run_config metadata when keywords are scarce.
