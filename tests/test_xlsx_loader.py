from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from modules.keyword_utils import extract_tiered_keywords
from tools import country_vocab, data_loader, preprocess


def test_keyword_table_preserves_blue_ocean_metrics(tmp_path):
    keyword_path = tmp_path / "keywords.csv"
    keyword_path.write_text(
        "\n".join(
            [
                "keyword,search_volume,conversion_rate,click_share,ctr,avg_cpc,product_count,title_density,click_concentration,conv_concentration,monthly_purchases",
                "body camera,1200,0.07,0.23,0.11,0.88,345,0.42,0.31,0.27,89",
            ]
        ),
        encoding="utf-8",
    )

    keyword_data, _audit = preprocess.read_keyword_table(str(keyword_path))

    row = keyword_data.keywords[0]
    assert row["search_volume"] == 1200
    assert row["conversion_rate"] == 0.07
    assert row["click_share"] == 0.23
    assert row["ctr"] == 0.11
    assert row["avg_cpc"] == 0.88
    assert row["product_count"] == 345
    assert row["title_density"] == 0.42
    assert row["click_concentration"] == 0.31
    assert row["conv_concentration"] == 0.27
    assert row["monthly_purchases"] == 89


def test_keyword_table_keeps_raw_purchases_distinct_from_monthly_purchases(tmp_path):
    keyword_path = tmp_path / "keywords.csv"
    keyword_path.write_text(
        "keyword,purchases\nbody camera,12\n",
        encoding="utf-8",
    )

    keyword_data, _audit = preprocess.read_keyword_table(str(keyword_path))

    row = keyword_data.keywords[0]
    assert row["purchases"] == 12
    assert "monthly_purchases" not in row


def test_keyword_table_maps_monthly_purchases_without_raw_purchases(tmp_path):
    keyword_path = tmp_path / "keywords.csv"
    keyword_path.write_text(
        "keyword,月购买量\nbody camera,34\n",
        encoding="utf-8",
    )

    keyword_data, _audit = preprocess.read_keyword_table(str(keyword_path))

    row = keyword_data.keywords[0]
    assert row["monthly_purchases"] == 34
    assert "purchases" not in row


def test_data_loader_keeps_raw_purchases_distinct_from_monthly_purchases():
    rows = data_loader.standardize_keywords([{"keyword": "body camera", "purchases": "12"}])

    row = rows[0]
    assert row["purchases"] == 12
    assert "monthly_purchases" not in row


def test_data_loader_maps_monthly_purchases_without_raw_purchases():
    rows = data_loader.standardize_keywords([{"keyword": "body camera", "月购买量": "34"}])

    row = rows[0]
    assert row["monthly_purchases"] == 34
    assert "purchases" not in row


def test_load_country_vocab_ingests_xlsx(monkeypatch):
    fixture = Path("tests/fixtures/xlsx/fr_order_winning_fixture.xlsx")
    original_fr_config = country_vocab.COUNTRY_CONFIGS["FR"]
    patched_config = {
        "aba_files": [],
        "order_winning_files": [fixture],
        "template_files": [],
        "review_file": None,
    }
    monkeypatch.setitem(country_vocab.COUNTRY_CONFIGS, "FR", patched_config)

    vocab = country_vocab.load_country_vocab("FR")
    assert len(vocab["order_winning"]) == 3

    real_vocab = preprocess.load_real_country_vocab("FR")
    assert real_vocab.order_winning_count == 3
    assert real_vocab.total_count == 3

    preprocessed = SimpleNamespace(
        real_vocab=real_vocab,
        keyword_data=SimpleNamespace(keywords=[]),
    )
    tiers = extract_tiered_keywords(preprocessed, language="French", real_vocab=real_vocab)
    assert "caméra sport nocturne" in tiers["l2"]
    assert set(tiers["l3"]) >= {"caméra sport casque", "caméra sport enfants"}

    monkeypatch.setitem(country_vocab.COUNTRY_CONFIGS, "FR", original_fr_config)
