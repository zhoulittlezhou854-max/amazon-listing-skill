# Dynamic Slot Planning Rules

Date: 2026-04-23
Status: working draft
Scope: convert fixed IMG01-IMG07 / A01-A05 ideas into a dynamic planning system for Amazon image work

## 1. Principle

Do not treat `IMG01-IMG07` as a rigid mandatory sequence for every product.

Treat them as:

- a slot library
- with activation rules
- with evidence thresholds
- with fallback replacements

The planner should select the strongest 5-7 listing assets for the current product, not force the same structure every time.

## 2. Planning layers

### 2.1 Core required layer

These should usually be activated for almost every product:

- `IMG01` main image
- `IMG02` hero selling point image

### 2.2 Recommended layer

These are commonly useful but not always mandatory:

- `IMG03` feature / structure proof
- `IMG04` usage scene
- `IMG05` dimensions / specs / compatibility
- `IMG07` package / trust / FAQ-like reassurance

### 2.3 Conditional layer

These activate only when the evidence or product type justifies them:

- `IMG06` comparison
- installation / steps variant
- expanded FAQ / trust image
- extra scene image
- extra feature proof image

## 3. The real constraint is task coverage, not fixed numbering

The planner should try to cover these jobs:

1. Click task
   - at least 1 image
   - normally `IMG01`
2. Core persuasion task
   - at least 1 image
   - normally `IMG02`
3. Fact / proof task
   - at least 1-2 images
   - examples: `IMG03`, `IMG05`, installation, compatibility
4. Risk reduction task
   - at least 1 image
   - examples: comparison, package contents, FAQ, trust, compatibility

This means a product can still have a strong image set even when one standard slot is skipped.

## 4. Activation logic by slot

### `IMG01`
- required_level: core
- enable_by_default: yes
- minimum evidence:
  - clear hero product image
  - stable product identity
- if missing:
  - mark as `P0`

### `IMG02`
- required_level: core
- enable_by_default: yes
- minimum evidence:
  - one priority selling point
  - at least one supporting proof source
- if weak:
  - still generate in degraded mode
  - but lower confidence and note weak proof chain

### `IMG03`
- required_level: recommended
- enable_when:
  - product has structure / material / mechanism worth proving
  - there are useful detail refs or spec proof
- fallback:
  - can be replaced by stronger scene or trust slot if evidence is weak

### `IMG04`
- required_level: recommended
- enable_when:
  - use case, audience, or environment meaningfully affects conversion
  - there are scene refs or clear scenario definitions
- fallback:
  - if no scene evidence exists, use `IMG03B` or `IMG07`

### `IMG05`
- required_level: recommended
- enable_when:
  - dimensions, compatibility, weight, ports, capacity, or measurable specs matter
- common for:
  - 3C
  - accessories
  - installation-dependent products
- if missing:
  - usually `P1`
  - can become near-`P0` when the category is spec-heavy

### `IMG06`
- required_level: conditional
- enable_when any of:
  - clear competitor reference exists
  - old-vs-new model comparison exists
  - explicit comparison claim has evidence
- if not enabled:
  - do not force a comparison image
  - replace with another persuasion or risk-reduction image

### `IMG07`
- required_level: recommended
- enable_when:
  - package contents matter
  - buyer expectation mismatch is a likely return risk
  - FAQ / trust / included items are important
- fallback:
  - may also absorb FAQ, support, compatibility, or reassurance content

## 5. Replacement rules

When a slot is not justified, use a replacement instead of forcing weak content.

### 5.1 Comparison unavailable

If `IMG06` cannot be supported, replacement priority should be:

1. extra usage scene
2. extra feature proof
3. FAQ / trust image
4. package contents image

### 5.2 Specs unavailable

If `IMG05` cannot be fully supported:

- keep a lighter proof image if partial data exists
- mark missing structured dimensions / compatibility in the report
- replacement priority:
  1. feature proof
  2. package / trust
  3. extra scene

### 5.3 Scene unavailable

If `IMG04` cannot be supported:

- do not force a fake lifestyle image
- replacement priority:
  1. stronger feature proof
  2. package / trust
  3. FAQ / compatibility

### 5.4 Package unavailable

If `IMG07` package contents cannot be supported:

- replacement priority:
  1. FAQ / trust image
  2. extra feature proof
  3. extra scene

## 6. Suggested planner output model

Each planned slot should expose:

```yaml
slot_id: IMG06
slot_name: comparison
required_level: conditional
goal_layer: risk_reduction
enabled: false
enabled_reason: "No competitor reference or old-vs-new basis found"
fallback_selected: IMG04_ALT
replacement_priority:
  - usage_scene
  - feature_proof
  - faq_or_trust
minimum_evidence:
  - comparison_basis
```

## 7. Recommended listing planning behavior

The planner should:

1. lock `IMG01` and `IMG02` first
2. score candidate slots by:
   - business value
   - evidence strength
   - category fit
   - risk-reduction value
3. choose the strongest remaining slots until the target count is reached
4. fill missing planned slots with fallback choices
5. explain every skipped slot in the planning notes

## 8. Recommended target counts

- minimum practical listing set: 5 images
- normal target: 6-7 images
- first anchor-first validation:
  - `IMG01`
  - `IMG02`

## 9. A+ planning note

Use the same dynamic rule:

- `A01` brand banner is common
- `A02-A05` should activate based on evidence, audience clarity, and content depth
- do not force a comparison-style A+ module without a solid comparison basis

## 10. Summary

The system should be standardized at the rule level, not frozen at the final image sequence level.

The planner should output:

- a stable core
- dynamic optional slots
- explicit fallback replacements
- a clear explanation of what was skipped and why
