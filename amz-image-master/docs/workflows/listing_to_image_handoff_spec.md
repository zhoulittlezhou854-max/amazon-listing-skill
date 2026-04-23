# Listing to Image Handoff Spec

Date: 2026-04-24
Status: working draft
Purpose: define the one derived file that the listing workflow should generate so the image workflow can directly consume it for classification, missing-info analysis, shot planning, and prompt building.

## 1. Recommended output

The listing workflow should generate this file together with normal listing outputs:

- `image_handoff.md`

Recommended location:

- same run folder as the listing outputs
- or a predictable export folder that downstream image tooling can read

## 2. Why this exists

The image workflow does not need the full internal reasoning of the listing generator.
It needs a compact, structured handoff focused on:

- product identity
- listing copy
- selling points
- evidence
- specs
- compatibility
- package contents
- image-planning hints
- FAQ and risk-reduction notes

That is enough to support:

- image classification correction
- missing-information reporting
- dynamic slot planning
- prompt writing for `image2`

## 3. Required sections

The generated `image_handoff.md` should fill these sections:

1. Product Identity
2. Listing Copy
3. Selling Points With Evidence
4. Product Facts
5. Package Contents
6. Image Planning Hints
7. FAQ and Risk Reduction
8. Source Tracking

Use the template at:

- `amz-image-master/config/image_handoff_template.md`

## 4. Critical field rules

### 4.1 Product identity

Must include at minimum:

- Product Name
- Brand
- Category
- Marketplace
- Language

### 4.2 Selling points

Prefer 3-5 priority selling points.
Each point should include:

- title
- claim
- benefit
- priority
- preferred visuals
- evidence

### 4.3 Evidence

Every important selling point should include evidence when possible.
Evidence should contain:

- type
- value
- source
- confidence

If a claim has no evidence:

- either leave it out of the handoff
- or explicitly mark it weak

### 4.4 Specs

Prefer explicit values, not generic phrases.
Examples:

- use `4K60FPS` instead of `high-definition`
- use `131FT with case` instead of `deep waterproof`
- use enumerated compatibility instead of `universal compatibility`

### 4.5 Package contents

Always distinguish:

- what is included
- what is not included

### 4.6 Image planning hints

These fields are especially important for downstream image planning:

- Best Hero Claim
- Must Show In Images
- Comparison Available
- Scene Assets Available
- Package Assets Available
- Spec Strength
- Compliance Notes
- Forbidden Elements

## 5. Downstream usage mapping

The image workflow will use this handoff roughly like this:

- Product Identity -> resolve product consistency
- Listing Copy -> title, bullets, keyword support
- Selling Points With Evidence -> `IMG02`, `IMG03`, `A03`
- Product Facts -> `IMG05`, FAQ, OCR-friendly fact images
- Package Contents -> `IMG07`
- Image Planning Hints -> dynamic slot activation and fallback decisions
- FAQ and Risk Reduction -> trust, compatibility, reassurance images

## 6. Recommended generation behavior

When the listing workflow writes `image_handoff.md`:

- prefer concise structured text over long prose
- avoid marketing fluff without evidence
- keep one source of truth per value when possible
- leave blanks instead of guessing
- keep wording directly reusable for image prompts

## 7. Minimal acceptance check

A usable `image_handoff.md` should let the image workflow answer these questions without reopening the full listing job:

1. What is the product?
2. What are the top 3-5 selling points?
3. Which claims have evidence?
4. What specs and compatibility facts matter?
5. What is included in the package?
6. What should be prioritized in images?
7. What should be avoided in images?
8. Is comparison actually justified?

## 8. Implementation note for Codex

When updating the listing project, add a step that writes the completed handoff file after listing generation finishes.

Recommended name:

- `image_handoff.md`

Optional machine-readable companion:

- `image_handoff.yaml`

If only one file is implemented first, prefer:

- `image_handoff.md`
