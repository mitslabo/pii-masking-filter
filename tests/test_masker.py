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


@pytest.mark.parametrize(("lines", "expected"), [
    (["a" * 16383 + "\n", "b" * 16383 + "\n", "tail"], [2, 1]),
    (["a" * 32766 + "\n", "x\n"], [1, 1]),
    (["あ" * 10922 + "\r\n", "終端"], [1, 1]),
    (["😀" * 8191 + "\r\n", "z\n", "tail"], [2, 1]),
    (["a" * 32768 + "\n", "tail"], [1, 1]),
    (["あ" * 10923 + "\r\n", "tail"], [1, 1]),
    (["a" * 32766 + "\r\n", "\r\n", " \t\r\n", "終端"], [1, 3]),
    (["\n", "\r\n", " \t\n"], [3]),
    (["no terminal newline"], [1]),
    ([], []),
])
def test_chunk_byte_boundaries_and_lossless_join(masker, lines, expected):
    masker._analyzer = Mock()
    masker._analyzer.analyze.return_value = []
    text = "".join(lines)

    result = masker.mask(text)

    chunks = [
        call.kwargs["text"] for call in masker._analyzer.analyze.call_args_list
    ]
    expected_chunks = []
    index = 0
    for count in expected:
        expected_chunks.append("".join(lines[index:index + count]))
        index += count
    assert chunks == expected_chunks
    assert "".join(chunks) == text
    assert result.masked_text == text
    assert not result.has_pii
    assert result.entities == []
    for chunk in chunks:
        if len(chunk.encode("utf-8")) > 32 * 1024:
            assert len(chunk.splitlines(keepends=True)) == 1


def test_chunked_values_offsets_and_request_isolation(masker):
    padding = "あ" * 6000 + " "
    originals = ["a@example.com", "b@example.com", "a@example.com"]
    endings = ["\r\n", "\n", ""]
    lines = [
        padding + original + ending
        for original, ending in zip(originals, endings)
    ]
    analyze = Mock(wraps=masker._analyzer.analyze)
    masker._analyzer.analyze = analyze
    result = masker.mask("".join(lines))

    tokens = ["<メールアドレス_1>", "<メールアドレス_2>", "<メールアドレス_1>"]
    assert result.masked_text == "".join(
        padding + token + ending for token, ending in zip(tokens, endings)
    )
    assert result.has_pii
    assert len(result.entities) == 3
    assert [call.kwargs["text"] for call in analyze.call_args_list] == lines
    offset = 0
    for entity, original, line, token in zip(
        result.entities, originals, lines, tokens
    ):
        assert entity.start == offset + len(padding)
        assert entity.end == entity.start + len(original)
        assert "".join(lines)[entity.start:entity.end] == original
        assert entity.placeholder == token
        offset += len(line)
    assert masker.mask("b@example.com").masked_text == "<メールアドレス_1>"


def test_chunked_overlap_exclusions_and_analyzer_options(masker):
    padding = "あ" * 10922 + "\r\n"
    chunk = "担当者 山田太郎 090-1234-5678"
    masker._analyzer = Mock()
    masker._analyzer.analyze.side_effect = [
        [],
        [
            RecognizerResult("PERSON", 0, 3, 0.85),
            RecognizerResult("PERSON", 4, 8, 0.8544),
            RecognizerResult("DATE_TIME", 9, 22, 0.99),
            RecognizerResult("PHONE_NUMBER", 9, 22, 0.7),
        ],
    ]
    masker.filters = ["PERSON", "PHONE_NUMBER"]
    masker.score_threshold = 0.6

    result = masker.mask(padding + chunk)

    assert result.masked_text == padding + "担当者 <氏名_1> <電話番号_1>"
    assert len(result.entities) == 2
    assert result.entities[0].score == 0.854
    for call in masker._analyzer.analyze.call_args_list:
        assert call.kwargs["entities"] == masker.filters
        assert call.kwargs["score_threshold"] == 0.6
        assert call.kwargs["language"] == "ja"


def test_later_chunk_failure_propagates_and_resets_state(masker):
    line = "a@example.com " + "あ" * 6000 + "\n"
    masker._analyzer = Mock()
    masker._analyzer.analyze.side_effect = [
        [RecognizerResult("EMAIL_ADDRESS", 0, 13, 0.9)],
        RuntimeError("analysis failed"),
    ]
    with pytest.raises(RuntimeError, match="analysis failed"):
        masker.mask(line * 3)
    assert masker._analyzer.analyze.call_count == 2
    masker._analyzer.analyze.side_effect = None
    masker._analyzer.analyze.return_value = [
        RecognizerResult("EMAIL_ADDRESS", 0, 13, 0.9),
    ]
    assert masker.mask("b@example.com").masked_text == "<メールアドレス_1>"


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
