# Repository Rules

This file defines the required repository structure, naming conventions,
storage rules, and cleanup policy for this project.

All agents (Codex, CC, other coding assistants) must read and follow this
document before creating, moving, renaming, archiving, or deleting files.

---

## Core Principles

1. Do not create random files in the repository root.
2. Do not use vague file names like:
   - final_v2
   - final_v3_fixed
   - test_new
   - new_copy
   - tmp_fix2
3. Every file must belong to a clear category:
   - source code
   - config
   - raw data
   - processed data
   - run output
   - docs
   - tests
   - archive
   - temporary/debug
4. Before deleting anything, first classify it and list it in a cleanup report.
5. If uncertain whether a file is still used, mark it as `needs_manual_review`.
6. Do not modify `modules/scoring.py` unless explicitly authorized.
7. Preserve backward compatibility for existing JSON/Markdown output contracts
   unless explicitly authorized.

---

## Canonical Repository Structure

The repository should follow this structure as closely as possible:

```text
repo-root/
├── README.md
├── REPO_RULES.md
├── REPO_INDEX.md
├── cleanup_candidates.md
├── .gitignore
├── requirements.txt
├── main.py
│
├── modules/
├── tools/
├── config/
├── data/
├── output/
├── docs/
├── tests/
└── archive/
```

### Folder meanings

- `modules/`
  - Core workflow/business logic modules.
  - Examples: scoring, report generation, copy generation, writing policy,
    keyword arsenal, intent translator, visual audit.

- `tools/`
  - Utility modules and data loading/preprocessing helpers.

- `config/`
  - Run configs, sample configs, product configs, environment-specific configs.
  - No large raw data files should live here.

- `data/`
  - Input and intermediate data only.
  - Must be subdivided into:
    - `data/raw/`
    - `data/processed/`
    - `data/fixtures/`
    - `data/archive/`

- `output/`
  - Generated run outputs only.
  - Must be subdivided into:
    - `output/runs/`
    - `output/reports/`
    - `output/debug/`

- `docs/`
  - Human-readable project docs.
  - Must be subdivided when possible into:
    - `docs/prd/`
    - `docs/knowledge-base/`
    - `docs/progress/`
    - `docs/audits/`
    - `docs/summaries/`

- `tests/`
  - Regression tests, fixtures, and integration checks.

- `archive/`
  - Deprecated, legacy, or retained-but-not-active files.
  - Must be subdivided when possible into:
    - `archive/legacy/`
    - `archive/tmp_snapshots/`
    - `archive/deprecated_docs/`

---

## File Placement Rules

### Source code
- Python source files that define workflow logic must go in:
  - `modules/`
  - `tools/`
  - `tests/`
- Do not place source code in `output/`, `docs/`, or repository root
  unless it is `main.py`.

### Config files
- All run configs must go in `config/`.
- Product-specific configs should go in:
  - `config/products/`
- Sample configs should go in:
  - `config/samples/`

### Raw input data
- Raw CSV/XLSX/JSON input files must go in:
  - `data/raw/<country>/`
  - or `data/raw/shared/`
- Do not scatter raw data across root, docs, or config folders.

### Processed/intermediate data
- Intermediate normalized data must go in:
  - `data/processed/`
- Test fixtures must go in:
  - `data/fixtures/`

### Outputs
- Each run must write to:
  - `output/runs/<run_name>/`
- Stable summary reports may additionally be copied to:
  - `output/reports/`
- Debug artifacts must go in:
  - `output/debug/`

### Docs
- PRD files go in:
  - `docs/prd/`
- Knowledge base files go in:
  - `docs/knowledge-base/`
- Progress logs go in:
  - `docs/progress/`
- Audit / alignment / investigation docs go in:
  - `docs/audits/`
- Summary docs go in:
  - `docs/summaries/`

### Archive
- Deprecated but retained files go in:
  - `archive/`
- Never leave deprecated files mixed with active source/config/data files.

---

## Naming Conventions

### General naming
- Use lowercase only when practical.
- Use hyphen `-` or underscore `_`, but do not use spaces.
- Country codes should use lowercase:
  - `de`, `fr`, `it`, `es`
- Product codes may preserve established internal identifiers if needed,
  but file names should still remain machine-friendly.

### Config names
Preferred pattern:
- `<country>-<product>-<purpose>.json`

Examples:
- `de-t70m-run.json`
- `fr-h88-regression.json`
- `de-h88-sample.json`

### Output folder names
Preferred pattern:
- `<yyyy-mm-dd>_<country>_<product>_<purpose>`

Examples:
- `2026-04-03_de_t70m_run`
- `2026-04-03_fr_h88_regression`

### Output files
Preferred pattern:
- `<yyyy-mm-dd>_<country>_<product>_<artifact>.<ext>`

Examples:
- `2026-04-03_de_t70m_scoring-results.json`
- `2026-04-03_de_t70m_listing-report.md`
- `2026-04-03_fr_h88_execution-summary.json`

### Debug/temp files
Must use one of these prefixes:
- `tmp_`
- `debug_`
- `scratch_`

Debug/temp files must only be stored in:
- `output/debug/`
- `archive/tmp_snapshots/`

They must not be created in repo root.

---

## Rules for Agents (Codex / CC / other assistants)

1. Always read `REPO_RULES.md` before large repo-wide changes.
2. Prefer modifying existing files over creating new duplicate files.
3. Do not create root-level files unless they are explicitly requested.
4. Do not create alternate versions like:
   - `copy_generation_new.py`
   - `copy_generation_fixed.py`
   - `report_generator_v2.py`
5. If a file must be superseded, update the original file or move the old one to archive.
6. Before deleting or archiving anything, generate a report first.
7. If a file appears unused but there is any uncertainty, label it:
   - `needs_manual_review`
8. If creating a new report, summary, or audit file, place it in:
   - `docs/summaries/` or `docs/audits/`
9. If creating a new run artifact, place it in:
   - `output/runs/<run_name>/`

---

## Cleanup Classification Policy

Before any deletion, every candidate must be classified as one of:

- `do_not_delete`
  - active code, active config, important docs, current datasets,
    current outputs, referenced files

- `safe_to_archive`
  - old but potentially useful outputs, deprecated docs, historical snapshots

- `likely_temp`
  - obvious temporary/debug/test artifacts with no long-term value

- `duplicate_candidate`
  - multiple files that appear to contain overlapping content or versions

- `needs_manual_review`
  - uncertain purpose, unclear references, or ambiguous status

### Required cleanup workflow
1. Scan repository.
2. Generate `cleanup_candidates.md`.
3. Categorize each suspicious file/folder.
4. Explain why it received that label.
5. Do not delete anything until explicitly authorized.

---

## Deletion Rules

No file may be deleted unless:
1. It has been listed in `cleanup_candidates.md`.
2. It has a classification.
3. It has been explicitly approved for deletion or archival.

If deletion is not explicitly approved:
- move to `archive/` instead of deleting when appropriate.

---

## Documentation Rules

- `REPO_INDEX.md` should describe the current repository structure.
- `cleanup_candidates.md` should describe cleanup candidates and rationale.
- `optimization_summary.md` or similar summaries must go to:
  - `docs/summaries/`
  - or `docs/audits/`

---

## Priority Rule

If there is a conflict between:
- convenience
- speed
- and repository clarity / maintainability

always choose repository clarity and maintainability.