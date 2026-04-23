# AMZ image master

Working directory for the Amazon image planning and `amazon-image-prep` workflow.

## Purpose

This folder collects the current project assets for:

- messy-folder intake
- product evidence extraction
- image classification
- prompt generation for `image2`
- dynamic shot planning for Amazon listing and A+ images

## Current contents

- `config/`
  - brand and prompt templates
- `docs/specs/`
  - runnable spec and implementation plan
- `docs/workflows/`
  - workflow definition and planning rules
- `docs/templates/`
  - report templates
- `docs/skills/`
  - skill design drafts

## Immediate next build targets

1. finalize dynamic slot planning
2. implement the runnable `amazon-image-prep` CLI
3. generate `shot_list.json` from evidence + fallback rules
4. prepare anchor-first runs for `IMG01` and `IMG02`

## Notes

This folder is currently seeded from working drafts and uploaded source files. It is intended to become the GitHub-backed source of truth that Codex can sync from.
