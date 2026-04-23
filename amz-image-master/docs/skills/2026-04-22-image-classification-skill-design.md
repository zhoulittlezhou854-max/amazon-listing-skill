# Image Classification Skill Design

Date: 2026-04-22
Status: Draft approved for spec writing
Scope: Initial skill for classifying mixed product images into Amazon-friendly folders and generating `prompt.txt` plus control files for `image2`

## 1. Goal

Build an initial Codex skill that turns a messy product image folder into a structured handoff package for `image2`.

The skill should:

1. Read a mixed image folder that may contain duplicate and near-duplicate images.
2. Read a structured product brief in `yaml` or `json`.
3. Classify images into a semi-fixed folder template for Amazon ecommerce image generation.
4. Keep only the strongest representative image from each near-duplicate group.
5. Copy selected images into output folders without modifying the original folder.
6. Generate one `prompt.txt` per output folder.
7. Generate one control summary in both machine-readable and human-readable form.

This first version is a preparation skill, not a final image-generation skill.

## 2. Non-Goals

The initial version does not:

- generate final Amazon images directly
- guarantee perfect classification accuracy
- generate fully localized multi-market copy variants
- perform deep Amazon policy validation
- optimize image layouts beyond folder-level prompt guidance
- replace manual review for ambiguous or low-confidence material

## 3. User Input

The skill accepts two required inputs:

### 3.1 Image folder

A local folder containing mixed product images. The folder may include:

- white-background product photos
- scene images
- close-up detail images
- packaging and accessories images
- installation or usage-step images
- duplicate or near-duplicate files
- files with poor or inconsistent naming

### 3.2 Structured product brief

The product brief must be provided as `yaml` or `json`.

Minimum required fields:

```yaml
product_name: ""
brand: ""
category: ""
five_bullets:
  - ""
  - ""
  - ""
  - ""
  - ""
keywords:
  - ""
  - ""
  - ""
features:
  - ""
  - ""
  - ""
constraints:
  must_have_white_background_main: true
  allow_comparison: true
  allow_people: false
  forbidden_elements:
    - "watermark"
    - "wrong structure"
```

Preferred optional fields:

```yaml
model: ""
marketplace: "Amazon"
language: "EN"
target_users:
  - ""
primary_goals:
  - "increase_ctr"
  - "increase_conversion"
specs:
  size: ""
  weight: ""
  material: ""
  color: ""
  package_contents:
    - ""
selling_points:
  - title: ""
    evidence:
      - ""
    benefit:
      - ""
    preferred_visuals:
      - "white_bg"
      - "dimension"
      - "feature"
      - "scene"
      - "comparison"
```

## 4. Output Package

The skill outputs a new folder and leaves the original image folder untouched.

Recommended output shape:

```text
<output_root>/
  00_brief.md
  00_manifest.json
  01_主图_白底/
    refs/
    prompt.txt
  02_尺寸图/
    refs/
    prompt.txt
  03_卖点图/
    refs/
    prompt.txt
  04_场景图/
    refs/
    prompt.txt
  05_对比图/
    refs/
    prompt.txt
  06_清单图/
    refs/
    prompt.txt
  07_安装使用图/
    refs/
    prompt.txt
  08_配件包装图/
    refs/
    prompt.txt
  90_unclassified/
  99_duplicates/
    exact/
    near/
```

Notes:

- The folder template is semi-fixed.
- A category folder is created only when there is enough evidence to support it.
- Images are copied, not moved.
- `refs/` stores the selected images used to anchor the prompt for that category.

## 5. Classification Model

The skill uses a hybrid decision model:

1. Visual content determines the base image type.
2. Product brief content adjusts category naming, selling-point emphasis, and prompt language.

This means classification is image-first, copy-corrected.

### 5.1 Visual signals

The classifier should look for these broad visual cues:

- `white_bg`: isolated product, clean or plain background, strong full-product visibility
- `dimension`: ruler, line annotation, proportion cue, hand-held scale, measurable structure
- `feature`: close-up component, material texture, mechanism detail, interface or structure proof
- `scene`: product used in a real or realistic environment
- `comparison`: two objects contrasted, before/after, product-vs-other construction
- `contents`: box contents, bundle spread, included parts, packing list layout
- `steps`: sequential use, installation, assembly, setup progression
- `packaging`: retail box, accessory trays, packed form, unopened or boxed presentation

### 5.2 Product-brief signals

The product brief should influence:

- which selling points deserve their own `卖点图` direction
- which dimensions or parameters should be emphasized
- whether `对比图` should exist
- whether scene images should lean toward DIY, home, outdoor, workshop, or professional use
- which forbidden elements must appear in every prompt restriction block

### 5.3 Category activation rules

Base categories:

- `01_主图_白底`
- `02_尺寸图`
- `03_卖点图`
- `04_场景图`
- `05_对比图`
- `06_清单图`
- `07_安装使用图`
- `08_配件包装图`

Activation logic:

- Create the folder only if there are enough source images or enough evidence from the brief to justify it.
- Keep uncertain images out of a category when confidence is low; send them to `90_unclassified` instead.
- `03_卖点图` may be internally driven by multiple selling points, but the first version keeps one shared folder and uses the prompt to structure sub-priorities.

## 6. Duplicate Handling

The skill must manage two duplicate levels:

### 6.1 Exact duplicates

Images that are byte-identical or trivially identical after basic normalization.

Rule:

- keep one primary file in the evaluation pipeline
- copy the rest into `99_duplicates/exact/`
- record all source-to-primary mappings in the manifest

### 6.2 Near duplicates

Images that are visually almost the same, such as:

- same angle with tiny crop differences
- burst shots with minimal product movement
- repeated export sizes of the same photo

Rule:

- group near duplicates
- keep only the best candidate in the main classification flow
- copy the non-selected files into `99_duplicates/near/`

### 6.3 Best-image scoring

The best representative is selected by weighted priority:

1. ecommerce usefulness for the target category
2. clarity and usable resolution
3. product completeness and visibility
4. composition quality

This priority order is intentional. A slightly less sharp image can still win if it is far more usable as a main image or feature anchor.

## 7. Category Assignment Strategy

Each image receives:

- a primary category
- an optional secondary category
- a confidence score
- a short reason string for the manifest

Rules:

- only the primary category controls where the copied image goes
- the secondary category is informational only in v1
- low-confidence images should not be forced into a category

Example reasoning strings:

- `clean isolated full-product shot, suitable for white-background main image`
- `close-up of jaw and pad structure, best used as feature proof`
- `tool shown clamping wood in context, suitable for scene image`
- `included parts arranged as a set, suitable for contents image`

## 8. Prompt Generation

Each active category folder gets one `prompt.txt`.

The prompt format is bilingual:

- Chinese explanation fields for review
- English main prompt for direct handoff to `image2`

### 8.1 Prompt structure

Each `prompt.txt` should contain:

1. category name
2. image objective
3. reference image usage guidance
4. recommended visual structure
5. copy hierarchy guidance
6. English main prompt
7. restriction block

### 8.2 Prompt principles

All prompts should follow these rules:

- keep Amazon detail-image logic, not poster-style campaign art
- focus on one main claim per image category
- preserve true product structure, color, and proportion
- do not invent nonexistent components or functions
- use concise, OCR-friendly headline logic
- emphasize measurable proof when possible

### 8.3 Prompt skeleton example

```text
Category: 卖点图 / Quick Release
目标说明:
- 突出单手快拆和稳定夹持，适合亚马逊详情页转化

参考图使用说明:
- 使用 refs 内图片作为产品结构、颜色、比例与关键部件依据
- 不改变真实结构，不添加不存在的部件

画面结构建议:
- 主体产品大图
- 一个关键部件特写
- 两到三个参数或功能信息块

文案层级建议:
- Title: Quick Release Clamp
- Subtitle: One-Hand Operation, Strong Holding Force
- Proof points: Non-Slip Pads / Durable Build / Secure Grip

English Prompt:
Create an Amazon-style ecommerce feature image for this product using the provided reference images. Keep the product structure, proportions, and colors accurate. Show the product as the hero object, add one supporting close-up detail, and include clean proof-oriented text blocks that highlight quick release, secure clamping, and durable construction. The image should feel professional, clear, conversion-focused, and suitable for an Amazon detail page, not a poster advertisement.

限制项:
- 保持亚马逊详情图风格
- 不做海报感设计
- 不添加水印、假徽章或夸张效果
- 不改变产品真实结构与颜色
```

## 9. Control Files

### 9.1 `00_manifest.json`

Machine-readable control file.

Required sections:

- product brief summary
- input path
- output path
- activated categories
- per-image classification result
- duplicate groups
- retained primary images
- unclassified images
- confidence notes

Recommended per-image record shape:

```json
{
  "source_file": "IMG_1023.jpg",
  "primary_category": "04_场景图",
  "secondary_category": "03_卖点图",
  "confidence": 0.84,
  "reason": "product shown in active use on wood surface",
  "duplicate_group": null,
  "kept": true
}
```

### 9.2 `00_brief.md`

Human-readable summary for fast review.

Required sections:

- product summary
- top visual directions inferred from the product brief
- activated category list
- what each category is trying to communicate
- material gaps or weak categories
- low-confidence calls that deserve manual review

## 10. Failure Handling

The skill should fail gracefully and explain what happened.

Expected failure modes:

- image folder missing or empty
- unsupported file types only
- product brief missing required fields
- too many low-confidence images
- no reliable white-background candidate when `must_have_white_background_main` is true

Behavior:

- still produce `00_brief.md` and `00_manifest.json` when possible
- include warnings instead of silently failing
- route ambiguous images to `90_unclassified`
- never delete original files

## 11. Review Philosophy

This skill is intended to produce an `image2`-ready draft package, not a final truth set.

Success for v1 means:

- the original image mess becomes navigable
- duplicates no longer pollute the main flow
- most high-value images land in the right category
- prompts become usable with minor manual edits
- a human can quickly see what is missing or suspicious

## 12. Implementation Outline for the Future Skill

This section is directional only and does not yet prescribe code.

Recommended future workflow:

1. load product brief
2. list image files and normalize file set
3. detect exact duplicates
4. detect near duplicates
5. score retained representatives
6. classify retained images by visual type
7. refine categories with product brief context
8. activate only justified output folders
9. copy selected images into `refs/`
10. write folder-level `prompt.txt`
11. write `00_manifest.json`
12. write `00_brief.md`

## 13. Open Decisions Deferred to Real-Product Testing

These choices are intentionally deferred until live product runs:

- whether `03_卖点图` should later split into multiple subfolders
- how aggressive near-duplicate grouping should be
- whether scene images should be split by persona or usage context
- how much prompt text should be standardized vs dynamically written
- whether low-confidence folders should still get prompts or only warnings

## 14. Acceptance Criteria for the Initial Skill

The first skill version is acceptable when it can:

1. take one image folder plus one product brief file
2. create a semi-fixed output package without touching originals
3. remove duplicate noise from the main flow
4. activate only justified categories
5. generate one usable `prompt.txt` per active category
6. generate both `00_manifest.json` and `00_brief.md`
7. surface ambiguity instead of hiding it

## 15. Naming

Recommended working skill name:

`amazon-image-prep`

Reason:

- short
- action-oriented
- describes the handoff purpose clearly
- flexible enough to grow later into a richer ecommerce-image preparation skill
