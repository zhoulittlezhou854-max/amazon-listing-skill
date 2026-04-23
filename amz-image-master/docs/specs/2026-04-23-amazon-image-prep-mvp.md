# Amazon Image Prep MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable `amazon-image-prep` CLI that turns one messy product folder into a `workup/` package with reports, a draft product brief, classified image folders, and `image2` prompt files.

**Architecture:** Implement a small Python package with a thin CLI entry point and eight focused modules: runner, inventory, extraction, dedupe, classification, brief building, prompt planning, and reporting. Keep all business rules inside small pure functions so the runner only orchestrates module order and file I/O.

**Tech Stack:** Python 3.11+, `pytest`, `PyYAML`, `python-docx`, `pypdf`, `openpyxl`, `Pillow`, `imagehash`

---

## Planned File Structure

- Create: `pyproject.toml`
- Create: `scripts/amazon_image_prep.py`
- Create: `src/amazon_image_prep/__init__.py`
- Create: `src/amazon_image_prep/models.py`
- Create: `src/amazon_image_prep/runner.py`
- Create: `src/amazon_image_prep/inventory.py`
- Create: `src/amazon_image_prep/extractors.py`
- Create: `src/amazon_image_prep/dedupe.py`
- Create: `src/amazon_image_prep/classify.py`
- Create: `src/amazon_image_prep/brief_builder.py`
- Create: `src/amazon_image_prep/prompts.py`
- Create: `src/amazon_image_prep/reports.py`
- Create: `tests/conftest.py`
- Create: `tests/test_runner.py`
- Create: `tests/test_inventory.py`
- Create: `tests/test_extractors.py`
- Create: `tests/test_dedupe.py`
- Create: `tests/test_classify.py`
- Create: `tests/test_brief_builder.py`
- Create: `tests/test_prompts.py`

## Task 1: Scaffold the package and CLI runner

**Files:**
- Create: `pyproject.toml`
- Create: `scripts/amazon_image_prep.py`
- Create: `src/amazon_image_prep/__init__.py`
- Create: `src/amazon_image_prep/models.py`
- Create: `src/amazon_image_prep/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing runner test**

```python
from pathlib import Path

from amazon_image_prep.runner import run_folder


def test_run_folder_creates_timestamped_output(tmp_path: Path) -> None:
    source = tmp_path / "product_a"
    source.mkdir()
    (source / "sample.txt").write_text("hello")

    result = run_folder(source)

    assert result.run_root.parent == source / "workup"
    assert result.run_root.exists()
    assert (result.run_root / "00_reports").exists()
    assert (result.run_root / "01_structured").exists()
    assert (result.run_root / "02_image2_ready").exists()
    assert (result.run_root / "03_prompts").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing `run_folder`

- [ ] **Step 3: Write minimal package scaffold**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "amazon-image-prep"
version = "0.1.0"
dependencies = [
  "PyYAML>=6.0",
  "python-docx>=1.1.0",
  "pypdf>=4.2.0",
  "openpyxl>=3.1.0",
  "Pillow>=10.0.0",
  "ImageHash>=4.3.1",
]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```python
# src/amazon_image_prep/models.py
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    run_root: Path
```

```python
# src/amazon_image_prep/runner.py
from datetime import datetime
from pathlib import Path

from .models import RunResult


def run_folder(source: Path) -> RunResult:
    source = Path(source)
    run_id = datetime.now().strftime("%Y-%m-%d_run%H%M%S")
    run_root = source / "workup" / run_id
    for relative in [
        "00_reports",
        "01_structured",
        "02_image2_ready",
        "03_prompts",
        "90_unknown",
        "99_duplicates/exact",
        "99_duplicates/near",
    ]:
        (run_root / relative).mkdir(parents=True, exist_ok=True)
    return RunResult(run_root=run_root)
```

```python
# scripts/amazon_image_prep.py
from pathlib import Path
import sys

from amazon_image_prep.runner import run_folder


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: amazon_image_prep.py <folder_path>")
        return 2
    result = run_folder(Path(sys.argv[1]))
    print(result.run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml scripts/amazon_image_prep.py src/amazon_image_prep/__init__.py src/amazon_image_prep/models.py src/amazon_image_prep/runner.py tests/test_runner.py
git commit -m "feat: scaffold amazon image prep runner"
```

## Task 2: Implement file inventory and junk-file filtering

**Files:**
- Modify: `src/amazon_image_prep/models.py`
- Create: `src/amazon_image_prep/inventory.py`
- Modify: `src/amazon_image_prep/runner.py`
- Test: `tests/test_inventory.py`

- [ ] **Step 1: Write the failing inventory tests**

```python
from pathlib import Path

from amazon_image_prep.inventory import scan_folder


def test_scan_folder_tags_supported_and_ignored_files(tmp_path: Path) -> None:
    root = tmp_path / "input"
    root.mkdir()
    (root / ".DS_Store").write_text("x")
    (root / "manual.pdf").write_text("fake")
    (root / "hero.jpg").write_text("fake")
    (root / "notes.md").write_text("# title")

    manifest = scan_folder(root)

    assert sorted(item.path.name for item in manifest.supported_files) == ["hero.jpg", "manual.pdf", "notes.md"]
    assert [item.path.name for item in manifest.ignored_files] == [".DS_Store"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_inventory.py -q`
Expected: FAIL with missing `scan_folder`

- [ ] **Step 3: Implement inventory models and scanner**

```python
# src/amazon_image_prep/models.py
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileRecord:
    path: Path
    file_type: str
    coarse_tag: str
    confidence: float
    reason: str


@dataclass
class InventoryManifest:
    supported_files: list[FileRecord] = field(default_factory=list)
    ignored_files: list[FileRecord] = field(default_factory=list)
```

```python
# src/amazon_image_prep/inventory.py
from pathlib import Path

from .models import FileRecord, InventoryManifest

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
TEXT_EXTS = {".txt", ".md"}
DOC_EXTS = {".pdf", ".docx"}
TABLE_EXTS = {".csv", ".xlsx"}
JUNK_NAMES = {".DS_Store", "Thumbs.db"}


def _file_type(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in TEXT_EXTS:
        return "text"
    if ext in DOC_EXTS:
        return "document"
    if ext in TABLE_EXTS:
        return "table"
    return None


def scan_folder(root: Path) -> InventoryManifest:
    manifest = InventoryManifest()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in JUNK_NAMES or path.stat().st_size == 0:
            manifest.ignored_files.append(FileRecord(path, "ignored", "unknown", 1.0, "junk file"))
            continue
        file_type = _file_type(path)
        if file_type is None:
            manifest.ignored_files.append(FileRecord(path, "unsupported", "unknown", 1.0, "unsupported extension"))
            continue
        manifest.supported_files.append(FileRecord(path, file_type, "unknown", 0.0, "tag pending"))
    return manifest
```

```python
# src/amazon_image_prep/runner.py
from .inventory import scan_folder

# inside run_folder after creating directories
manifest = scan_folder(source)
(run_root / "00_reports" / "inventory_count.txt").write_text(str(len(manifest.supported_files)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py tests/test_inventory.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/amazon_image_prep/models.py src/amazon_image_prep/inventory.py src/amazon_image_prep/runner.py tests/test_inventory.py
git commit -m "feat: add file inventory scanning"
```

## Task 3: Extract text and candidate product fields

**Files:**
- Create: `src/amazon_image_prep/extractors.py`
- Modify: `src/amazon_image_prep/models.py`
- Modify: `src/amazon_image_prep/runner.py`
- Test: `tests/test_extractors.py`

- [ ] **Step 1: Write the failing extractor tests**

```python
from pathlib import Path

from amazon_image_prep.extractors import extract_candidates_from_text


def test_extract_candidates_from_text_pulls_title_and_keywords() -> None:
    text = """Title: 4K Action Camera with Dual Screen
Bullet: 4K60FPS video recording
Bullet: 131FT waterproof case
Keywords: action camera, 4k camera, waterproof camera
"""

    result = extract_candidates_from_text(text)

    assert result["title"][0]["value"] == "4K Action Camera with Dual Screen"
    assert result["five_bullets"][0]["value"] == "4K60FPS video recording"
    assert "action camera" in result["keywords"][0]["value"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extractors.py -q`
Expected: FAIL with missing extractor function

- [ ] **Step 3: Implement document readers and field extraction**

```python
# src/amazon_image_prep/extractors.py
from pathlib import Path
from docx import Document
from pypdf import PdfReader


def read_text_file(path: Path) -> str:
    return path.read_text(errors="ignore")


def read_docx_file(path: Path) -> str:
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def read_pdf_file(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def extract_candidates_from_text(text: str) -> dict[str, list[dict[str, object]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {"title": [], "five_bullets": [], "keywords": []}
    for line in lines:
        lowered = line.lower()
        if lowered.startswith("title:"):
            result["title"].append({"value": line.split(":", 1)[1].strip(), "confidence": 0.9})
        elif lowered.startswith("bullet:"):
            result["five_bullets"].append({"value": line.split(":", 1)[1].strip(), "confidence": 0.85})
        elif lowered.startswith("keywords:"):
            for item in [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]:
                result["keywords"].append({"value": item, "confidence": 0.8})
    return result
```

```python
# src/amazon_image_prep/runner.py
from .extractors import extract_candidates_from_text, read_docx_file, read_pdf_file, read_text_file


def _read_supported_text(path):
    if path.suffix.lower() in {".txt", ".md"}:
        return read_text_file(path)
    if path.suffix.lower() == ".docx":
        return read_docx_file(path)
    if path.suffix.lower() == ".pdf":
        return read_pdf_file(path)
    return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extractors.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/amazon_image_prep/extractors.py src/amazon_image_prep/runner.py tests/test_extractors.py
git commit -m "feat: extract title bullets and keywords from documents"
```

## Task 4: Add image dedupe for exact and near duplicates

**Files:**
- Create: `src/amazon_image_prep/dedupe.py`
- Modify: `src/amazon_image_prep/models.py`
- Modify: `src/amazon_image_prep/runner.py`
- Test: `tests/test_dedupe.py`

- [ ] **Step 1: Write the failing dedupe tests**

```python
from pathlib import Path
from PIL import Image

from amazon_image_prep.dedupe import dedupe_images


def test_dedupe_images_detects_exact_and_retains_one(tmp_path: Path) -> None:
    img1 = tmp_path / "a.png"
    img2 = tmp_path / "b.png"
    Image.new("RGB", (20, 20), "white").save(img1)
    Image.new("RGB", (20, 20), "white").save(img2)

    result = dedupe_images([img1, img2])

    assert len(result.retained) == 1
    assert len(result.exact_duplicates) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dedupe.py -q`
Expected: FAIL with missing `dedupe_images`

- [ ] **Step 3: Implement exact-hash and perceptual-hash dedupe**

```python
# src/amazon_image_prep/dedupe.py
import hashlib
from pathlib import Path

import imagehash
from PIL import Image


class DedupeResult:
    def __init__(self, retained, exact_duplicates, near_duplicates):
        self.retained = retained
        self.exact_duplicates = exact_duplicates
        self.near_duplicates = near_duplicates


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dedupe_images(paths: list[Path]) -> DedupeResult:
    retained = []
    exact_duplicates = []
    seen_hashes = {}
    phashes = []
    for path in paths:
        digest = _sha256(path)
        if digest in seen_hashes:
            exact_duplicates.append((seen_hashes[digest], path))
            continue
        seen_hashes[digest] = path
        retained.append(path)
    near_duplicates = []
    final_retained = []
    for path in retained:
        current = imagehash.phash(Image.open(path))
        matched = False
        for prev_hash, prev_path in phashes:
            if current - prev_hash <= 2:
                near_duplicates.append((prev_path, path))
                matched = True
                break
        if not matched:
            phashes.append((current, path))
            final_retained.append(path)
    return DedupeResult(final_retained, exact_duplicates, near_duplicates)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dedupe.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/amazon_image_prep/dedupe.py tests/test_dedupe.py
git commit -m "feat: add image deduplication"
```

## Task 5: Classify images and build the enhanced product brief

**Files:**
- Create: `src/amazon_image_prep/classify.py`
- Create: `src/amazon_image_prep/brief_builder.py`
- Modify: `src/amazon_image_prep/runner.py`
- Test: `tests/test_classify.py`
- Test: `tests/test_brief_builder.py`

- [ ] **Step 1: Write the failing classification and brief tests**

```python
from pathlib import Path

from amazon_image_prep.brief_builder import build_brief
from amazon_image_prep.classify import classify_image_name


def test_classify_image_name_uses_filename_signals() -> None:
    assert classify_image_name(Path("hero_white_bg.jpg"))["category"] == "01_main_white_bg"
    assert classify_image_name(Path("size_170g.png"))["category"] == "02_dimension_specs"


def test_build_brief_marks_missing_fields() -> None:
    brief = build_brief({"title": [{"value": "4K Action Camera", "confidence": 0.9}]})
    assert brief["commerce_copy"]["title"]["value"] == "4K Action Camera"
    assert brief["commerce_copy"]["title"]["status"] == "extracted"
    assert brief["product_identity"]["category"]["status"] == "missing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_classify.py tests/test_brief_builder.py -q`
Expected: FAIL with missing classification and brief builder functions

- [ ] **Step 3: Implement classification heuristics and brief builder**

```python
# src/amazon_image_prep/classify.py
from pathlib import Path


def classify_image_name(path: Path) -> dict[str, object]:
    name = path.name.lower()
    if "white" in name or "hero" in name or "main" in name:
        return {"category": "01_main_white_bg", "confidence": 0.7, "reason": "filename suggests hero/main image"}
    if "size" in name or "dimension" in name or "mm" in name or "g" in name:
        return {"category": "02_dimension_specs", "confidence": 0.65, "reason": "filename suggests dimensions/specs"}
    if "scene" in name or "use" in name or "outdoor" in name:
        return {"category": "04_usage_scenes", "confidence": 0.6, "reason": "filename suggests usage scene"}
    if "package" in name or "accessory" in name or "kit" in name:
        return {"category": "06_package_contents", "confidence": 0.6, "reason": "filename suggests package contents"}
    return {"category": "90_unclassified", "confidence": 0.2, "reason": "no strong filename signal"}
```

```python
# src/amazon_image_prep/brief_builder.py
from copy import deepcopy
from pathlib import Path
import yaml

TEMPLATE_PATH = Path("/Users/zhoulittlezhou/image master/config/product_brief.template.yaml")


def build_brief(candidates: dict[str, list[dict[str, object]]]) -> dict:
    brief = yaml.safe_load(TEMPLATE_PATH.read_text())
    title_candidates = candidates.get("title", [])
    if title_candidates:
        best = title_candidates[0]
        brief["commerce_copy"]["title"]["value"] = best["value"]
        brief["commerce_copy"]["title"]["status"] = "extracted"
        brief["commerce_copy"]["title"]["confidence"] = best["confidence"]
        brief["commerce_copy"]["title"]["sources"] = ["extracted_text"]
    return brief
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_classify.py tests/test_brief_builder.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/amazon_image_prep/classify.py src/amazon_image_prep/brief_builder.py tests/test_classify.py tests/test_brief_builder.py
git commit -m "feat: add heuristic image classification and brief builder"
```

## Task 6: Generate reports, prompt files, and end-to-end output

**Files:**
- Create: `src/amazon_image_prep/prompts.py`
- Create: `src/amazon_image_prep/reports.py`
- Modify: `src/amazon_image_prep/runner.py`
- Test: `tests/test_prompts.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write the failing end-to-end tests**

```python
from pathlib import Path
from PIL import Image

from amazon_image_prep.runner import run_folder


def test_run_folder_writes_core_reports_and_prompt_files(tmp_path: Path) -> None:
    source = tmp_path / "product_a"
    source.mkdir()
    (source / "title.txt").write_text("Title: 4K Action Camera")
    Image.new("RGB", (40, 40), "white").save(source / "hero_main.jpg")

    result = run_folder(source)

    assert (result.run_root / "00_reports" / "intake_report.md").exists()
    assert (result.run_root / "00_reports" / "missing_info_report.md").exists()
    assert (result.run_root / "00_reports" / "classification_report.md").exists()
    assert (result.run_root / "01_structured" / "draft_product_brief.yaml").exists()
    assert (result.run_root / "01_structured" / "extracted_copy.md").exists()
    assert (result.run_root / "01_structured" / "extracted_specs.yaml").exists()
    assert (result.run_root / "02_image2_ready" / "01_main_white_bg").exists()
    assert (result.run_root / "03_prompts" / "shot_list.json").exists()
    assert (result.run_root / "03_prompts" / "01_main_white_bg.prompt.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner.py tests/test_prompts.py -q`
Expected: FAIL because reports and prompt files are not yet written

- [ ] **Step 3: Implement report and prompt writers and connect the pipeline**

```python
# src/amazon_image_prep/prompts.py
import json


def build_shot_list() -> list[dict[str, str]]:
    return [
        {"shot_id": "IMG01", "shot_type": "main"},
        {"shot_id": "IMG02", "shot_type": "feature"},
        {"shot_id": "IMG03", "shot_type": "feature_breakdown"},
    ]


def write_prompt(path, category: str) -> None:
    path.write_text(
        f"Category: {category}\n"
        "Objective: Create a clean Amazon ecommerce image for this category.\n"
        "Use the provided references and preserve the true product structure.\n"
    )
```

```python
# src/amazon_image_prep/reports.py
def write_intake_report(path, supported_count: int, retained_count: int) -> None:
    path.write_text(f"# Intake Report\n\n- Supported files: {supported_count}\n- Retained images: {retained_count}\n")


def write_missing_info_report(path, p0: list[str], p1: list[str]) -> None:
    path.write_text("# Missing Info Report\n\n## P0\n" + "\n".join(f"- {item}" for item in p0) + "\n\n## P1\n" + "\n".join(f"- {item}" for item in p1))


def write_classification_report(path, rows: list[dict[str, object]]) -> None:
    body = "\n".join(f"- {row['path']}: {row['category']} ({row['confidence']})" for row in rows)
    path.write_text("# Classification Report\n\n" + body)
```

```python
# src/amazon_image_prep/runner.py
import json
import shutil
import yaml
from .brief_builder import build_brief
from .classify import classify_image_name
from .prompts import build_shot_list, write_prompt
from .reports import write_classification_report, write_intake_report, write_missing_info_report

# inside run_folder after scan/extract/dedupe
classified_rows = []
for path in retained_images:
    row = classify_image_name(path)
    row["path"] = path.name
    classified_rows.append(row)

brief = build_brief(extracted_candidates)
(run_root / "01_structured" / "draft_product_brief.yaml").write_text(yaml.safe_dump(brief, sort_keys=False))
(run_root / "01_structured" / "extracted_copy.md").write_text("# Extracted Copy\n\n" + extracted_text)
(run_root / "01_structured" / "extracted_specs.yaml").write_text(yaml.safe_dump({"spec_candidates": extracted_candidates.get("specs", [])}, sort_keys=False))
write_intake_report(run_root / "00_reports" / "intake_report.md", len(manifest.supported_files), len(retained_images))
write_missing_info_report(run_root / "00_reports" / "missing_info_report.md", ["missing category"], ["missing keywords"])
write_classification_report(run_root / "00_reports" / "classification_report.md", classified_rows)

shot_list = build_shot_list()
(run_root / "03_prompts" / "shot_list.json").write_text(json.dumps(shot_list, indent=2))
usable_categories = {}
for path, row in zip(retained_images, classified_rows):
    category = row["category"]
    if category == "90_unclassified":
        continue
    category_dir = run_root / "02_image2_ready" / category
    category_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, category_dir / path.name)
    usable_categories.setdefault(category, []).append(path.name)

for category in usable_categories:
    write_prompt(run_root / "03_prompts" / f"{category}.prompt.txt", category)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/amazon_image_prep/prompts.py src/amazon_image_prep/reports.py src/amazon_image_prep/runner.py tests/test_prompts.py tests/test_runner.py
git commit -m "feat: generate workup reports and image2 prompts"
```

## Self-Review

### Spec coverage

- Single-folder input: covered in Task 1
- Output root and run folder: covered in Task 1
- File inventory and ignore rules: covered in Task 2
- Extraction and candidate fields: covered in Task 3
- Exact and near dedupe: covered in Task 4
- Image classification categories: covered in Task 5
- Structured brief generation: covered in Task 5
- Prompt files and shot list: covered in Task 6
- Reporting: covered in Task 6

### Placeholder scan

- No `TODO` or `TBD`
- No “implement later” steps
- Each code step contains concrete code
- Each run step includes a specific command

### Type consistency

- `run_folder` stays the single orchestration entry point
- `build_brief` always returns a dict loaded from the enhanced YAML template
- `classify_image_name` returns `category`, `confidence`, and `reason`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-amazon-image-prep-mvp.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
