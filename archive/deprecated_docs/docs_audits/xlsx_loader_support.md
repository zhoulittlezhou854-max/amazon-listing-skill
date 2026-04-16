# XLSX Loader Support Audit (2026-04-06)

## What changed
- Added `openpyxl>=3.1.0` to `requirements.txt` and made it the single XLSX dependency. `tools/data_loader.py` now raises a clear error if the package is missing instead of silently skipping spreadsheets.
- `tools/country_vocab.py` logs every file it ingests (country, filename, source_type, row count) so we can verify whether spreadsheets were actually read.
- Real vocabulary ingestion concatenates CSV + XLSX + template pools; FR order_winning data now includes rows from `data/raw/fr/FR/H88_FR_出单词.xlsx`.

## Dependency rationale
We chose **openpyxl** because it is the lightest viable dependency for reading vendor spreadsheets. Pandas is already available for analytics, but requiring it for ingestion was unnecessary overhead. Openpyxl keeps runtime memory low and is easier to vendor for offline agents.

## Loader details
- `_load_xlsx` now exclusively uses openpyxl and strips whitespace per cell, ensuring keyword normalization is identical to CSV handling.
- Missing dependency → deterministic RuntimeError with installation instructions.
- `_normalize_template_row` continues to cover template CSVs; XLSX ingestion feeds into the same standardization pipeline, so tiering logic remains unchanged.

## FR pipeline verification
Command:
```
python3 main.py --config products/FR_sample/run_config.json --output-dir output/output_fr_xlsx
```
Key log lines:
```
[country_vocab] FR: H88_FR_出单词.xlsx (order_winning) → 32 rows
[country_vocab] FR: fr_longtail_template_keywords.csv (template) → 406 rows
```
`output/output_fr_xlsx/preprocessed_data.json` shows `real_vocab.order_winning_count = 56` and `total_count = 505`, confirming the Excel rows were merged with existing CSV data. Search Terms & L3 buckets now pull from genuine FR order_winning signals instead of synthetic templates alone.

## Regression coverage
- New fixture: `tests/fixtures/xlsx/fr_order_winning_fixture.xlsx` (3 rows).
- `tests/test_xlsx_loader.py::test_load_country_vocab_ingests_xlsx` monkeypatches the FR config to use the fixture, exercises `load_country_vocab("FR")`, `preprocess.load_real_country_vocab`, and `extract_tiered_keywords`, asserting L2/L3 buckets contain the XLSX keywords.
- Run via `python3 -m pytest` (already green in this branch).

## Adding future Excel files
1. Drop the spreadsheet under `data/raw/<country>/<COUNTRY_CODE>/` (e.g., `data/raw/it/IT/<file>.xlsx`).
2. Update `tools/country_vocab.COUNTRY_CONFIGS` with the new path (aba/order_winning/review/template as appropriate).
3. Run `python3 -m pytest tests/test_xlsx_loader.py` to ensure ingestion still works.
4. Execute `main.py --config … --output-dir …` for the target locale and confirm the console logs list your XLSX file with the expected row count.
