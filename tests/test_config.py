import pytest

import pii_masking.config as config
from pii_masking.masker import JapanesePiiMasker


def test_default_filters(masker):
    assert masker.filters is None


def test_environment_filters(masker, monkeypatch):
    monkeypatch.setenv("PII_FILTERS", " PHONE_NUMBER, EMAIL_ADDRESS,PHONE_NUMBER ")
    configured = JapanesePiiMasker()
    assert configured.filters == ["PHONE_NUMBER", "EMAIL_ADDRESS"]
    result = configured.mask("山田太郎様、電話090-1234-5678、taro@example.com")
    assert result.masked_text == "山田太郎様、電話<電話番号_1>、<メールアドレス_1>"
    assert len(result.entities) == 2


def test_dotenv_filters_and_settings(masker):
    config.DOTENV_PATH.write_text(
        "PII_FILTERS=EMAIL_ADDRESS\nSPACY_MODEL=ja_core_news_sm\n"
        "PII_SCORE_THRESHOLD=0.8\n", encoding="utf-8",
    )
    configured = JapanesePiiMasker()
    assert configured.spacy_model == "ja_core_news_sm"
    assert configured.score_threshold == 0.8
    assert configured.mask("電話090-1234-5678、taro@example.com").masked_text == (
        "電話090-1234-5678、<メールアドレス_1>"
    )


def test_environment_overrides_dotenv(masker, monkeypatch):
    config.DOTENV_PATH.write_text(
        "PII_FILTERS=EMAIL_ADDRESS\nSPACY_MODEL=ja_core_news_sm\n"
        "PII_SCORE_THRESHOLD=0.8\n", encoding="utf-8",
    )
    monkeypatch.setenv("PII_FILTERS", "PHONE_NUMBER")
    monkeypatch.setenv("SPACY_MODEL", "ja_core_news_lg")
    monkeypatch.setenv("PII_SCORE_THRESHOLD", "0.4")
    configured = JapanesePiiMasker()
    assert configured.spacy_model == "ja_core_news_lg"
    assert configured.score_threshold == 0.4
    assert configured.mask("電話090-1234-5678、taro@example.com").masked_text == (
        "電話<電話番号_1>、taro@example.com"
    )


@pytest.mark.parametrize("value", ["", " ", "UNKNOWN", "PERSON,", "person"])
def test_invalid_filters_fail_before_model_loading(monkeypatch, value):
    monkeypatch.setenv("PII_FILTERS", value)
    with pytest.raises(ValueError, match="PII_FILTERS"):
        JapanesePiiMasker()


def test_all_documented_filters_supported(masker, monkeypatch):
    monkeypatch.setenv("PII_FILTERS", ",".join(config.ENTITY_LABELS_JA))
    configured = JapanesePiiMasker()
    assert set(configured.filters) <= set(
        configured._analyzer.get_supported_entities(language="ja")
    )


def test_nlp_length_limit(masker):
    assert masker._analyzer.nlp_engine.nlp["ja"].max_length >= 1024 ** 2
