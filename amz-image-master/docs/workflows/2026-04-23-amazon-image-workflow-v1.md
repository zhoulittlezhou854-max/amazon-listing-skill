# Amazon Image Workflow v1

Date: 2026-04-23
Status: Upgraded Day-1 foundation
Brand: Tosbarrft
Platform: Amazon
Skill target: `amazon-image-prep`

## 1. Purpose

Build one practical skill that takes a messy product asset folder and turns it into an `image2`-ready workup package.

The workflow should:

- accept a chaotic folder without requiring pre-sorting
- extract as much product information as possible from images and documents
- tell the user what is still missing
- keep going in best-effort mode when enough material exists
- output organized image sets plus prompts that can be fed into `image2`

This workflow is not a full autopilot image factory. It is a semi-automated preparation system.

## 2. Core Idea

The user should be able to drop one messy product folder into the workflow.

That folder may contain:

- raw product images
- manufacturer images
- competitor screenshots
- package and accessory images
- logos
- spec sheets
- manuals
- title and bullet drafts
- keyword notes
- random screenshots or copied assets

The skill should then answer three questions:

1. What is already in this folder?
2. What is still missing?
3. What can already be fed to `image2`?

## 3. Upgraded Skill Scope

The upgraded `amazon-image-prep` skill combines two functions inside one skill:

### Stage A: Messy intake

- scan the folder recursively
- recognize image and document types
- extract text and likely product facts
- group duplicates and near-duplicates
- identify candidate brand assets, product assets, competitor refs, and unknown files
- produce a missing-information report

### Stage B: Image2 prep

- build a draft product brief from available evidence
- classify usable images into Amazon-oriented folders
- generate prompt files for each usable folder
- generate a `shot_list`
- assemble an `image2`-ready workup package

This remains one skill from the user's perspective.

## 4. Default Behavior

The skill runs in best-effort mode.

That means:

- do not stop just because the folder is incomplete
- produce a partial but useful package whenever possible
- clearly mark missing data and low-confidence decisions
- avoid inventing facts when the evidence is weak

Best-effort mode should be the default because real product folders are usually messy and incomplete.

## 5. Inputs

### 5.1 Required minimum

At minimum, the user provides one local folder.

### 5.2 Optional structured inputs

If present, the workflow should also merge:

- `product_brief.yaml`
- title and bullets text files
- keyword lists
- spec documents
- package-content notes

### 5.3 Brand context

The workflow may inherit:

- `config/style_profile.yaml`
- `config/master_prompt.template.md`

This allows the skill to stay aligned with the Tosbarrft brand system even when the product folder is messy.

## 6. Stage A: Messy Intake

### S1. Folder scan

Scan the entire folder recursively and inventory all supported files.

Supported file groups:

- images
- PDFs
- DOCX
- TXT and Markdown
- CSV and spreadsheet-like files

### S2. File tagging

Assign coarse tags such as:

- `product_image`
- `scene_image`
- `dimension_image`
- `package_image`
- `competitor_ref`
- `logo`
- `spec_doc`
- `copy_doc`
- `screenshot`
- `unknown`

The tagging can be imperfect, but it should be explicit.

### S3. Extraction

Extract or infer what can be found:

- product name
- brand name
- category
- title
- five bullets
- keywords
- specs
- package contents
- selling points
- compliance clues

If extraction is uncertain, keep the field but mark it low-confidence or empty.

### S4. Duplicate handling

Before downstream prep:

- detect exact duplicates
- group near-duplicates
- keep one best representative for each group
- route others into duplicate buckets

## 7. Stage B: Image2 Prep

### S5. Structured draft

Use extracted evidence to generate:

- `draft_product_brief.yaml`
- `extracted_copy.md`
- `extracted_specs.yaml`

### S6. Image classification

Organize retained images into semi-fixed working folders:

- `01_main_white_bg`
- `02_dimension_specs`
- `03_feature_claims`
- `04_usage_scenes`
- `05_comparison`
- `06_package_contents`
- `07_installation_or_steps`
- `90_unclassified`
- `99_duplicates`

Classification remains image-first and brief-corrected.

### S7. Prompt generation

Create folder-level prompts for every usable image set.

Each prompt should be compatible with `image2` and should inherit:

- the brand master
- product consistency constraints
- category objective
- Amazon output rules

### S8. Shot planning

Produce a `shot_list` that maps likely deliverables such as:

- `IMG01` main image
- `IMG02` hero selling point
- `IMG03` feature breakdown
- `IMG04` scene
- `IMG05` dimensions or specs
- `IMG06` comparison
- `IMG07` package or trust image

### S9. Anchor-first recommendation

Recommend testing only `IMG01` and `IMG02` first before a full run.

## 8. Output Package

Recommended output shape:

```text
workup/
  00_reports/
    intake_report.md
    missing_info_report.md
    classification_report.md
  01_structured/
    draft_product_brief.yaml
    extracted_copy.md
    extracted_specs.yaml
  02_image2_ready/
    01_main_white_bg/
    02_dimension_specs/
    03_feature_claims/
    04_usage_scenes/
    05_comparison/
    06_package_contents/
    07_installation_or_steps/
  03_prompts/
    master_prompt.md
    shot_list.json
    01_main_white_bg.prompt.txt
    02_dimension_specs.prompt.txt
    03_feature_claims.prompt.txt
    04_usage_scenes.prompt.txt
  90_unknown/
  99_duplicates/
```

This package should be usable even if some folders remain empty or partial.

## 9. Missing-Information Reporting

The skill must explicitly report missing information instead of merely failing.

Use priority levels:

- `P0`: must-have before reliable execution
- `P1`: strong improvement if added
- `P2`: optional enhancement

Examples:

- `P0`: no clear product hero images
- `P0`: no title or bullet evidence at all
- `P1`: no keyword set
- `P1`: no structured dimensions
- `P1`: no package contents text
- `P2`: no extra competitor references

## 10. What the Skill Should Automate

Codex should automate:

- folder scanning
- extraction and structuring
- dedupe and grouping
- classification
- prompt assembly
- shot planning
- reporting

Codex should not fully automate:

- final design approval
- final main-image compliance sign-off
- nuanced brand copy polishing without review

## 11. Current Brand Context

The current Tosbarrft brand base remains:

- Amazon-first
- balanced between youthful-cool and professional-reliable
- weighted slightly toward professional-reliable
- visually clean, sharp, and outdoor-tech
- above cheap generic devices, below intimidating flagship positioning

## 12. Tomorrow's Product Test

Tomorrow's first real-product test should validate this upgraded skill by checking whether one messy product folder can yield:

1. a usable intake report
2. a missing-info report
3. a draft product brief
4. usable `image2` image folders
5. usable prompts
6. a first `shot_list`

Success means the workup package is practical, not perfect.
