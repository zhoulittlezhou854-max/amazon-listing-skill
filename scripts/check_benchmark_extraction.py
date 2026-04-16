#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import writing_policy as wp


def _load_config(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["input_files"] = raw.get("input_files", {}) or {}
    return SimpleNamespace(**raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    run_config = _load_config(Path(args.config))
    preprocessed = SimpleNamespace(run_config=run_config, ingestion_audit={})

    candidate_paths = wp._benchmark_candidate_paths(preprocessed)
    print("Candidate paths:")
    for path in candidate_paths:
        print(f"- {path}")

    bullets = wp._extract_benchmark_bullets(preprocessed)
    print(f"\nExtracted {len(bullets)} benchmark bullets:")
    for index, bullet in enumerate(bullets, 1):
        print(f"\n{index}. {bullet}")

    print("\nSource diagnostics:")
    for path in candidate_paths:
        resolved = Path(path)
        if not resolved.exists():
            print(f"- {resolved}: missing")
            continue
        passed = 0
        failed = 0
        with open(resolved, "r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                data_type = str(row.get("Data_Type", "") or "").lower()
                field_name = str(row.get("Field_Name", "") or "").lower()
                content = " ".join(str(row.get("Content_Text", "") or "").split())
                if "listing" not in data_type or not field_name.startswith("bullet"):
                    continue
                source_rank = wp._benchmark_source_rank(row)
                if wp._is_high_quality_bullet(content, bsr_rank=source_rank[1]):
                    passed += 1
                else:
                    failed += 1
        print(f"- {resolved}: passed={passed} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
