import json
from pathlib import Path
from types import SimpleNamespace

from modules import input_validator as iv


def _run_config(tmp_path: Path, **input_files):
    return SimpleNamespace(input_files=input_files, target_country='US', product_code='H91lite')


def test_validate_input_tables_warns_when_file_missing(tmp_path: Path):
    run_config = _run_config(tmp_path, attribute_table=str(tmp_path / 'missing.csv'))

    warnings = iv.validate_input_tables(run_config)

    assert any(w.table == 'attribute_table' and w.severity == 'medium' for w in warnings)


def test_validate_input_tables_warns_when_required_columns_missing(tmp_path: Path):
    keyword_path = tmp_path / 'keywords.csv'
    keyword_path.write_text('keyword\nbody camera\n', encoding='utf-8')
    run_config = _run_config(tmp_path, keyword_table=str(keyword_path))

    warnings = iv.validate_input_tables(run_config)

    assert any(w.table == 'keyword_table' and w.severity == 'high' for w in warnings)
    keyword_warning = next(w for w in warnings if w.table == 'keyword_table')
    assert 'search_volume' in keyword_warning.message


def test_validate_input_tables_accepts_complete_csvs(tmp_path: Path):
    paths = {
        'attribute_table': tmp_path / 'attr.csv',
        'keyword_table': tmp_path / 'kw.csv',
        'review_table': tmp_path / 'review.csv',
        'aba_merged': tmp_path / 'aba.csv',
    }
    paths['attribute_table'].write_text('Field_Name,Value,Source\nweight,35g,lab\n', encoding='utf-8')
    paths['keyword_table'].write_text('keyword,search_volume,tier\nbody camera,1200,L1\n', encoding='utf-8')
    paths['review_table'].write_text('ASIN,Bullet_1,BSR_Rank\nA1,Records 4K at 30fps,120\n', encoding='utf-8')
    paths['aba_merged'].write_text('keyword,search_volume,click_share\nbody camera,1200,0.2\n', encoding='utf-8')
    run_config = _run_config(tmp_path, **{k: str(v) for k, v in paths.items()})

    warnings = iv.validate_input_tables(run_config)

    assert warnings == []


def test_validate_input_tables_warns_when_numeric_columns_invalid(tmp_path: Path):
    keyword_path = tmp_path / 'kw.csv'
    keyword_path.write_text('keyword,search_volume\nbody camera,not_a_number\n', encoding='utf-8')
    run_config = _run_config(tmp_path, keyword_table=str(keyword_path))

    warnings = iv.validate_input_tables(run_config)

    warning = next(w for w in warnings if w.table == 'keyword_table')
    assert 'search_volume' in warning.message
    assert '数值类型' in warning.message


def test_validate_input_tables_accepts_old_bullet_1_bullet_2_review_schema(tmp_path: Path):
    review_path = tmp_path / 'review.csv'
    review_path.write_text('ASIN,Bullet_1,Bullet_2\nA1,Records commutes,Clips to bags\n', encoding='utf-8')
    run_config = _run_config(tmp_path, review_table=str(review_path))

    warnings = iv.validate_input_tables(run_config)

    assert not any(w.table == 'review_table' and '缺少必填列' in w.message for w in warnings)
