# Amazon Image Prep Runnable Spec

Date: 2026-04-23
Status: MVP implementation spec
Target Skill: `amazon-image-prep`
Goal: Turn one messy product folder into an `image2`-ready workup package

## 1. MVP Goal

The first runnable version must accept one messy product folder and produce:

1. an intake report
2. a missing-information report
3. a draft structured product brief
4. classified image folders
5. prompt files for usable image sets

The MVP does not need to fully automate final generation, A+ layout design, or perfect semantic understanding.

## 2. Single-Run Contract

### 2.1 Input

One folder path:

```text
amazon-image-prep <folder_path>
```

The folder may contain any mixture of:

- product images
- screenshots
- manuals
- PDFs
- DOCX files
- TXT or Markdown notes
- spreadsheets
- logos
- competitor references
- garbage or unknown files

### 2.2 Scope limitation

MVP assumes the folder is intended to represent one product.

If the system detects strong evidence of multiple unrelated products, it should:

- report the conflict
- continue in best-effort mode
- mark the product identity as low-confidence

### 2.3 Output location

Default output root:

```text
<folder_path>/workup/
```

If `workup/` already exists:

- create a timestamped subfolder or run folder under `workup/`
- do not overwrite previous runs by default

Example:

```text
<folder_path>/workup/2026-04-23_run01/
```

## 3. Required Output Structure

Each run must produce:

```text
workup/<run_id>/
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
    05_comparison.prompt.txt
    06_package_contents.prompt.txt
    07_installation_or_steps.prompt.txt
  90_unknown/
  99_duplicates/
    exact/
    near/
```

The system may omit empty prompt files, but it should still mention skipped categories in the reports.

## 4. Module Breakdown

The MVP is split into 8 modules.

### M1. Runner

Responsibilities:

- validate the input path
- create `run_id`
- create output folders
- orchestrate module order
- collect summary errors and warnings

Output:

- run metadata
- output folder scaffold

### M2. File Inventory

Responsibilities:

- recursively scan the folder
- identify supported files
- ignore junk files
- assign coarse file types

Output:

- full file manifest
- supported file list
- ignored file list

### M3. Content Extraction

Responsibilities:

- read text from supported documents
- OCR text from images when useful
- extract candidate product facts
- identify likely titles, bullets, specs, package contents, and keywords

Output:

- raw extracted text
- extracted field candidates
- source mapping

### M4. Image Deduplication

Responsibilities:

- detect exact duplicate images
- detect near-duplicate groups
- retain one best representative per group

Output:

- retained image set
- exact duplicate mapping
- near-duplicate groups

### M5. Image Classification

Responsibilities:

- classify retained images into Amazon-oriented categories
- assign confidence and reasoning
- route ambiguous cases to unknown

Output:

- classified image list
- per-category retained references

### M6. Structured Brief Builder

Responsibilities:

- merge extracted evidence into enhanced `product_brief`
- assign status, confidence, and sources
- leave unresolved fields visible

Output:

- `draft_product_brief.yaml`
- `extracted_copy.md`
- `extracted_specs.yaml`

### M7. Prompt and Shot Planner

Responsibilities:

- determine which image categories are usable
- build `shot_list.json`
- write folder-level prompt files
- write `master_prompt.md`

Output:

- `shot_list.json`
- prompt files

### M8. Reporting

Responsibilities:

- summarize what was found
- summarize what can be done now
- summarize what is missing
- summarize low-confidence fields

Output:

- `intake_report.md`
- `missing_info_report.md`
- `classification_report.md`

## 5. Supported File Types

### 5.1 Must support in MVP

- Images: `.jpg`, `.jpeg`, `.png`, `.webp`
- Text: `.txt`, `.md`
- Documents: `.docx`, `.pdf`
- Tables: `.csv`, `.xlsx`

### 5.2 Ignore in MVP

- videos
- archive files
- design-source files like `.psd`, `.ai`, `.fig`

The system should mention ignored unsupported files in the intake report.

### 5.3 Junk file ignore list

Always ignore:

- `.DS_Store`
- `Thumbs.db`
- hidden temporary office files
- zero-byte files

## 6. File Tagging Rules

Each supported file receives:

- `file_type`
- `coarse_tag`
- `confidence`
- `reason`

### 6.1 Coarse tags

Allowed MVP tags:

- `product_image`
- `scene_image`
- `dimension_image`
- `package_image`
- `competitor_ref`
- `logo`
- `spec_doc`
- `copy_doc`
- `spreadsheet`
- `unknown`

### 6.2 Initial tagging signals

Use these heuristics:

- filename keywords
- parent folder names
- OCR text snippets
- visual content cues for images

Examples:

- names containing `logo` -> likely `logo`
- names containing `manual`, `spec`, `参数`, `说明书` -> likely `spec_doc`
- names containing `竞品`, `competitor`, `asin` -> likely `competitor_ref`
- images with isolated product on white background -> likely `product_image`
- images with rulers, dimension lines, numbers -> likely `dimension_image`
- images with environment or people -> likely `scene_image`

## 7. Extraction Rules

The system should extract candidates, not force a single truth too early.

### 7.1 Fields to extract in MVP

- brand
- product name
- category
- title
- five bullets
- keywords
- top selling points
- dimensions
- recording specs
- battery / waterproof / stabilization if present
- package contents

### 7.2 Source priority

When conflicts occur, prefer:

1. explicit structured files such as YAML, CSV, XLSX
2. clean text documents
3. manuals / spec PDFs
4. image OCR
5. filename inference

### 7.3 Status rules

Use these values:

- `missing`
- `extracted`
- `inferred`
- `confirmed`

Interpretation:

- `missing`: no meaningful evidence found
- `extracted`: directly found in a file or image text
- `inferred`: guessed from weak or indirect evidence
- `confirmed`: explicitly provided or manually reviewed

### 7.4 Confidence rules

Use normalized float confidence from `0.0` to `1.0`.

Suggested anchors:

- `0.9 - 1.0`: explicit, structured, clear
- `0.7 - 0.89`: strong text evidence
- `0.4 - 0.69`: plausible but weak or indirect
- `< 0.4`: should usually remain unresolved or low-confidence

## 8. Image Deduplication Rules

### 8.1 Exact duplicates

Exact duplicates are files with identical binary hash.

Behavior:

- keep one representative
- copy others into `99_duplicates/exact/`
- record mapping in the reports

### 8.2 Near duplicates

Near duplicates are visually almost identical images.

Suggested detection basis:

- perceptual hash similarity
- identical content at different sizes
- burst-like minimal changes

Behavior:

- cluster into groups
- keep one best representative
- copy others into `99_duplicates/near/`

### 8.3 Best representative score

Score by:

1. ecommerce usefulness
2. clarity
3. completeness of product view
4. composition quality

## 9. Image Classification Rules

### 9.1 Allowed categories

- `01_main_white_bg`
- `02_dimension_specs`
- `03_feature_claims`
- `04_usage_scenes`
- `05_comparison`
- `06_package_contents`
- `07_installation_or_steps`
- `90_unclassified`

### 9.2 Category definitions

`01_main_white_bg`
- isolated product
- white or near-white background
- hero product visibility

`02_dimension_specs`
- dimension lines
- measurement text
- scale or size emphasis

`03_feature_claims`
- close-up parts
- product details
- structure, materials, or key functions

`04_usage_scenes`
- people or environment
- outdoor or real-use framing
- contextual product use

`05_comparison`
- before/after
- product-vs-other
- explicit side-by-side contrast

`06_package_contents`
- included accessories
- kit layout
- package spread

`07_installation_or_steps`
- step-by-step use
- how-to sequence
- mounting or setup progression

### 9.3 Classification output per image

Each retained image must store:

- primary category
- optional secondary category
- confidence
- reasoning note

### 9.4 Unknown routing

If confidence is too low or evidence conflicts strongly:

- route to `90_unclassified`
- explain why

## 10. Missing-Info Logic

The system must explicitly grade missing information.

### 10.1 P0 blockers

Typical P0 items:

- no usable product hero image
- no usable evidence of title or product identity
- no meaningful product-image set at all

### 10.2 P1 missing items

Typical P1 items:

- missing keywords
- missing structured dimensions
- missing package contents text
- missing reliable scene images

### 10.3 P2 missing items

Typical P2 items:

- extra competitor references
- richer scenario coverage
- more polished copy sources

### 10.4 Output decision

If P0 blockers exist:

- still produce reports
- still produce partial structured outputs when possible
- set recommendation to `Stop and collect missing inputs` or `Proceed with caution`

If only P1/P2 exist:

- proceed with workup generation

## 11. Structured Brief Generation Rules

The output target is:

- `/Users/zhoulittlezhou/image master/config/product_brief.template.yaml`

Generation rules:

- fill values when evidence exists
- keep source lists short but meaningful
- use `inferred` only when a reasonable conclusion helps downstream work
- do not fabricate technical specs
- preserve empty values when evidence is too weak

## 12. Image2-Ready Folder Rules

Each usable image set under `02_image2_ready/` should contain only the best references for that theme.

MVP rule:

- keep `1-5` strongest references per category
- do not dump every retained image into every category
- preserve original filenames where possible

If a category is too weak:

- either leave it empty and mention it in the reports
- or do not create the prompt file for it

## 13. Prompt Generation Rules

### 13.1 Prompt inputs

Each folder-level prompt must be built from:

1. brand master
2. product consistency constraints
3. category objective
4. available selling points
5. Amazon restrictions

### 13.2 Prompt outputs

Each category prompt should include:

- category name
- objective
- reference usage guidance
- layout suggestion
- copy hierarchy suggestion
- English generation prompt
- restrictions

### 13.3 Degradation behavior

If fields are missing:

- still generate a simpler prompt
- avoid mentioning unsupported claims
- use generic category objectives when needed

## 14. Shot Planning Rules

The MVP shot planner should generate likely targets from available materials:

- `IMG01` main image
- `IMG02` hero feature image
- `IMG03` feature breakdown
- `IMG04` scene image
- `IMG05` dimensions/specs
- `IMG06` comparison
- `IMG07` package or trust image

The planner does not need to guarantee all shots are feasible.
It should mark unavailable or weak shots clearly.

## 15. Reports

### 15.1 intake_report.md

Must contain:

- folder summary
- file counts by type
- extraction summary
- duplicate summary
- what is already usable

### 15.2 missing_info_report.md

Must contain:

- P0 / P1 / P2 sections
- low-confidence fields
- recommended next inputs
- suggested next action

### 15.3 classification_report.md

Must contain:

- retained image count
- category counts
- duplicate statistics
- notable unknown files
- suspicious or low-confidence classification calls

## 16. Logging and Error Handling

The runner should capture:

- fatal errors
- warnings
- skipped files
- unsupported file types

If one module partially fails:

- continue if downstream work is still possible
- note the degraded state in the reports

## 17. MVP Acceptance Criteria

The first runnable version is acceptable if it can reliably:

1. accept one folder path
2. scan and inventory mixed files
3. extract at least some useful structured product information
4. dedupe images
5. classify major image groups
6. produce all three reports
7. produce a draft structured brief
8. create at least one usable `image2` category folder and prompt when valid images exist

## 18. Non-Goals for MVP

Do not block MVP on:

- full A+ generation planning
- multilingual copy refinement
- perfect OCR
- support for every file format
- multi-product decomposition inside one folder
- automatic image rendering

## 19. Recommended Next Engineering Step

Implement in this order:

1. Runner + file inventory
2. Text extraction
3. Image dedupe
4. Image classification
5. Structured brief generation
6. Missing-info report
7. Prompt generation

That order is the shortest path to a usable first version.
