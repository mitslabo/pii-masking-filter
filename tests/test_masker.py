from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from presidio_analyzer import RecognizerResult

import pii_masking.masker as module
from pii_masking.masker import JapanesePiiMasker


@pytest.mark.parametrize(("text", "placeholder"), [
    ("メールはtaro@example.comです", "<メールアドレス_1>"),
    ("電話は090-1234-5678です", "<電話番号_1>"),
    ("電話は03-1234-5678です", "<電話番号_1>"),
    ("電話は09012345678です", "<電話番号_1>"),
    ("電話は090－１２３４－５６７８です", "<電話番号_1>"),
    ("郵便番号は〒123-4567です", "<郵便番号_1>"),
    ("住所は東京都新宿区西新宿1-2-3です", "<住所_1>"),
    ("マイナンバーは1234-5678-9012です", "<マイナンバー_1>"),
    ("パスポートはAB1234567です", "<パスポート番号_1>"),
    ("カードは4111-1111-1111-1111です", "<クレジットカード番号_1>"),
    ("山田太郎様", "<氏名_1>"),
    ("IPは 192.0.2.1 です", "<IPアドレス_1>"),
])
def test_japanese_patterns(masker, text, placeholder):
    result = masker.mask(text)
    assert result.has_pii
    assert placeholder in result.masked_text
    for entity in result.entities:
        assert text[entity.start:entity.end] not in result.masked_text
    assert not hasattr(result, "mapping")
    assert not hasattr(result, "original_text")


def test_repeated_values_and_request_isolation(masker):
    result = masker.mask("a@example.com、b@example.com、a@example.com")
    assert result.masked_text == (
        "<メールアドレス_1>、<メールアドレス_2>、<メールアドレス_1>"
    )
    assert len(result.entities) == 3
    assert masker.mask("b@example.com").masked_text == "<メールアドレス_1>"


def test_no_pii(masker):
    result = masker.mask("こんにちは。")
    assert result.masked_text == "こんにちは。"
    assert result.entities == []
    assert not result.has_pii


def test_overlap_priorities():
    phone = RecognizerResult("PHONE_NUMBER", 0, 13, 0.7)
    postal = RecognizerResult("JP_POSTAL_CODE", 5, 13, 0.6)
    date = RecognizerResult("DATE_TIME", 0, 13, 0.99)
    adjacent = RecognizerResult("PERSON", 13, 17, 0.85)
    assert JapanesePiiMasker._resolve_overlaps(
        [date, postal, adjacent, phone]
    ) == [phone, adjacent]


def test_ner_exclusions_and_names(masker):
    masker._analyzer = Mock()
    masker._analyzer.analyze.return_value = [
        RecognizerResult("PERSON", 0, 3, 0.85),
        RecognizerResult("PERSON", 4, 8, 0.85),
    ]
    assert masker.mask("担当者 山田太郎").masked_text == "担当者 <氏名_1>"


def test_missing_model_does_not_download(monkeypatch):
    monkeypatch.setattr(module.spacy.util, "is_package", lambda name: False)
    provider = Mock()
    monkeypatch.setattr(module, "NlpEngineProvider", provider)
    with pytest.raises(RuntimeError, match="Install"):
        JapanesePiiMasker()
    provider.assert_not_called()


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan")])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError, match="PII_SCORE_THRESHOLD"):
        JapanesePiiMasker(score_threshold=threshold)


def test_singleton_concurrent_initialization(monkeypatch):
    instance = Mock()
    factory = Mock(return_value=instance)
    monkeypatch.setattr(module, "_default_masker", None)
    monkeypatch.setattr(module, "JapanesePiiMasker", factory)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: module.get_masker(), range(8)))
    assert all(result is instance for result in results)
    factory.assert_called_once_with()
