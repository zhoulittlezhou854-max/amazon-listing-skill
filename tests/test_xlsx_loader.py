from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from modules.keyword_utils import extract_tiered_keywords
from tools import country_vocab, preprocess


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
