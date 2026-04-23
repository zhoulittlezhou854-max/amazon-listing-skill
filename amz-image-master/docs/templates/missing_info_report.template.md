# Missing Info Report Template

Date: [generated_at]
Product Folder: [source_folder]
Product Name: [product_name_or_unknown]
Brand: [brand]
Marketplace: [marketplace]
Mode: best_effort

## 1. Executive Summary

- Intake status: [partial_ready / blocked / ready_for_prep]
- Overall confidence: [low / medium / high]
- Can proceed to image classification: [yes/no]
- Can proceed to prompt generation: [yes/no]
- Can proceed to anchor generation: [yes/no]

Short conclusion:

> [One short paragraph explaining what was found, what is missing, and whether the current folder is already usable for `image2` prep.]

## 2. What Was Found

### 2.1 Structured product info found

- Product name: [value or missing]
- Category: [value or missing]
- Title: [value or missing]
- Five bullets: [count found]
- Keywords: [count found]
- Selling points: [count found]
- Specs: [summary]
- Package contents: [summary]

### 2.2 Asset inventory found

- Hero/white-background product images: [count]
- Detail/feature images: [count]
- Scene/lifestyle images: [count]
- Dimension/spec images: [count]
- Package/accessory images: [count]
- Competitor references: [count]
- Brand assets/logo: [count]
- Unknown files: [count]
- Exact duplicates: [count]
- Near-duplicate groups: [count]

## 3. What Can Be Done Right Now

These outputs can already be created from the current folder:

- [ ] Draft product brief
- [ ] Image classification folders
- [ ] Main-image prompt
- [ ] Feature-image prompts
- [ ] Scene-image prompts
- [ ] Dimension/spec prompts
- [ ] Comparison prompt
- [ ] Package-contents prompt
- [ ] `shot_list.json`
- [ ] Anchor generation for `IMG01`
- [ ] Anchor generation for `IMG02`

Notes:

- [Explain which outputs are strong, weak, or partial.]

## 4. Missing Information

### 4.1 P0 - Must fix before reliable execution

Use this section only for blockers that materially prevent a reliable workflow.

| Field / Asset | Why it matters | Suggested source | Current impact |
| --- | --- | --- | --- |
| [example: clear hero product image] | [needed for main image and consistency] | [manufacturer image / reshoot / existing listing] | [cannot build reliable IMG01] |

### 4.2 P1 - Strongly recommended

These items do not fully block the workflow, but the output quality will likely suffer.

| Field / Asset | Why it matters | Suggested source | Current impact |
| --- | --- | --- | --- |
| [example: keywords] | [helps prompt wording and ecommerce phrasing] | [listing draft / ad keywords] | [prompt language weaker] |

### 4.3 P2 - Optional improvements

These items improve quality or speed, but are not essential for the first pass.

| Field / Asset | Why it matters | Suggested source | Current impact |
| --- | --- | --- | --- |
| [example: more competitor refs] | [helps style targeting] | [ASIN screenshots / saved refs] | [style range narrower] |

## 5. Low-Confidence Extractions

These fields were inferred or extracted with weak evidence and should be reviewed:

| Field | Current value | Confidence | Source | Recommended action |
| --- | --- | --- | --- | --- |
| [field] | [value] | [0.00-1.00] | [file] | [confirm / replace / ignore] |

## 6. Recommended Next Inputs

If the user only has time to add a few things, request them in this order:

1. [highest-priority missing item]
2. [second-priority missing item]
3. [third-priority missing item]

## 7. Suggested Next Action

Choose one:

- `Proceed now` - enough material exists to prepare `image2` folders and prompts
- `Proceed with caution` - partial materials exist; prompts can be generated but some outputs will be weak
- `Stop and collect missing inputs` - too many P0 blockers remain

Recommended action for this folder:

> [one short directive sentence]

## 8. Handoff Notes for Image2 Prep

- Brand master used: `/Users/zhoulittlezhou/image master/config/style_profile.yaml`
- Product brief target: `/Users/zhoulittlezhou/image master/config/product_brief.template.yaml`
- Expected output root: `workup/`
- Anchor-first recommendation: `IMG01` then `IMG02`

## 9. File References

Most important supporting files found during intake:

- [path 1]
- [path 2]
- [path 3]
