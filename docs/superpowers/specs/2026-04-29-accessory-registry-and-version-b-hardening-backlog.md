# Accessory Registry and Version B Hardening Backlog

## Purpose
Record two non-blocking follow-up issues found after the field-contract refactor. These are not required for the current merge to `main`, but they should be handled before the next quality-improvement cycle.

## Follow-up 1: Accessory Checkbox Input Layer

### Problem
Step 0 data quality remains limited when product accessories are provided as loose text or incomplete attributes. The listing can be launch-safe, but conversion quality is capped because the system lacks structured facts about which accessories are actually included.

### Direction
Add an accessory registry with checkbox-style input for common camera accessories. Each checked accessory should produce canonical facts, allowed scenes, allowed claims, and slot guidance.

### Example Mapping
| Accessory | Enabled Facts | Enabled Scenes | Notes |
|-----------|---------------|----------------|-------|
| 32GB microSD card | included storage, ready-to-record kit | daily recording, travel recording | Can support B5 kit readiness. |
| USB-C cable | charging/data cable included | daily setup, travel setup | Should not imply fast charging unless supported. |
| magnetic pendant | hands-free wear | commuting, vlog, meeting notes | Can support wearable scenes. |
| back clip | clip-on mounting | service staff, commute, sports training | Can support body-worn scenarios. |
| waterproof case | water-side protection | outdoor, rain, water-side scenes | Only if explicitly included; never infer waterproof camera body. |

### Acceptance Criteria
- Product setup exposes common accessories as checkboxes or equivalent structured config.
- Selected accessories become canonical facts, not LLM-inferred prose.
- Scene variants can be auto-enabled by selected accessories.
- B5 package contract only uses checked accessories and supported attribute facts.

## Follow-up 2: Version B Rerender Acceptance Gate

### Problem
Version B is experimental and can still produce review-only bullets after rerender. In r45, B5 was rerendered but still failed slot contract because rerender results were marked `applied` even when the post-rerender slot contract still failed.

### Direction
Make slot rerender acceptance explicit: rerendered output must be revalidated. If it still fails, the result should be marked `failed_validation` or passed to deterministic local fallback. It should not be treated as a successful repair.

### Acceptance Criteria
- Every rerendered slot is rechecked by slot contract after rerender.
- Failed post-rerender validation is not reported as `applied`.
- B5 support/team/storage/package overloading is either deterministically simplified or remains blocked with a precise reason.
- Version B remains review-only unless all slot contracts pass, but it still must not be paste-ready by itself under the current product contract.
