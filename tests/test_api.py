import logging
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from presidio_analyzer import RecognizerResult

import app as api


@pytest.fixture
def client(monkeypatch, masker):
    monkeypatch.setattr(api, "get_masker", lambda: masker)
    with TestClient(api.app) as client:
        yield client


def test_health_does_not_load_model(monkeypatch):
    factory = Mock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(api, "get_masker", factory)
    with TestClient(api.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    factory.assert_not_called()


def test_mask_success(client, caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.post("/mask", json={
            "text": "山田太郎様の電話は090-1234-5678、メールはtaro@example.comです。"
        })
    assert response.status_code == 200
    assert response.json() == {
        "masked_text": "<氏名_1>様の電話は<電話番号_1>、メールは<メールアドレス_1>です。",
        "has_pii": True,
        "entity_count": 3,
    }
    for pii in ("山田太郎", "090-1234-5678", "taro@example.com"):
        assert pii not in response.text
        assert pii not in caplog.text


def test_mask_without_pii(client):
    response = client.post("/mask", json={"text": "こんにちは。"})
    assert response.status_code == 200
    assert response.json() == {
        "masked_text": "こんにちは。", "has_pii": False, "entity_count": 0
    }


def test_mask_multiple_chunks(client):
    padding = "あ" * 6000 + " "
    response = client.post("/mask", json={
        "text": padding + "a@example.com\r\n\r\n"
        + padding + "b@example.com\n" + padding + "a@example.com",
    })
    assert response.status_code == 200
    assert response.json() == {
        "masked_text": padding + "<メールアドレス_1>\r\n\r\n"
        + padding + "<メールアドレス_2>\n" + padding + "<メールアドレス_1>",
        "has_pii": True,
        "entity_count": 3,
    }


def test_later_chunk_failure_is_private(client, masker, caplog):
    masker._analyzer = Mock()
    masker._analyzer.analyze.side_effect = [
        [RecognizerResult("EMAIL_ADDRESS", 0, 13, 0.9)],
        RuntimeError("PII: a@example.com"),
    ]
    line = "a@example.com " + "あ" * 6000 + "\n"
    with caplog.at_level(logging.DEBUG):
        response = client.post("/mask", json={"text": line * 3})
    assert response.status_code == 500
    assert response.json() == {"detail": "masking_failed"}
    assert masker._analyzer.analyze.call_count == 2
    assert "a@example.com" not in caplog.text


@pytest.mark.parametrize("payload", [
    {}, {"text": ""}, {"text": None}, {"text": 123},
    {"text": ["taro@example.com"]}, {"text": "a" * (1024 ** 2 + 1)},
    {"text": "hello", "extra": "taro@example.com"},
    ["taro@example.com"],
])
def test_mask_validation(client, payload, caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.post("/mask", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_request"}
    assert "taro@example.com" not in caplog.text


def test_malformed_json(client, caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/mask", content='{"text":"taro@example.com"',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_request"}
    assert "taro@example.com" not in caplog.text


def test_masking_failure_is_private(client, monkeypatch, caplog):
    masker = Mock()
    masker.mask.side_effect = RuntimeError("PII: taro@example.com")
    monkeypatch.setattr(api, "get_masker", lambda: masker)
    with caplog.at_level(logging.DEBUG):
        response = client.post("/mask", json={"text": "taro@example.com"})
    assert response.status_code == 500
    assert response.json() == {"detail": "masking_failed"}
    assert "taro@example.com" not in caplog.text


def test_missing_model_is_private(monkeypatch, caplog):
    monkeypatch.setattr(
        api, "get_masker", Mock(side_effect=RuntimeError("PII: taro@example.com"))
    )
    with TestClient(api.app) as client, caplog.at_level(logging.DEBUG):
        response = client.post("/mask", json={"text": "taro@example.com"})
        invalid = client.post("/mask", json={})
    assert response.status_code == 503
    assert response.json() == {"detail": "masker_unavailable"}
    assert invalid.status_code == 422
    assert "taro@example.com" not in caplog.text


def test_only_public_endpoints():
    assert {(route.path, frozenset(route.methods)) for route in api.app.routes} == {
        ("/health", frozenset({"GET"})), ("/mask", frozenset({"POST"})),
    }


@pytest.mark.parametrize("length", [100_001, 1024 ** 2])
def test_text_length_accepted(client, monkeypatch, length):
    text = "あ" * length
    masker = Mock()
    masker.mask.return_value = Mock(masked_text=text, has_pii=False, entities=[])
    monkeypatch.setattr(api, "get_masker", lambda: masker)
    response = client.post("/mask", json={"text": text})
    assert response.status_code == 200
    assert response.json()["masked_text"] == text
    masker.mask.assert_called_once_with(text)


def test_invalid_filter_configuration_returns_503(client, monkeypatch):
    monkeypatch.setenv("PII_FILTERS", "UNKNOWN")
    monkeypatch.setattr(api, "get_masker", api.JapanesePiiMasker)
    response = client.post("/mask", json={"text": "taro@example.com"})
    assert response.status_code == 503
    assert response.json() == {"detail": "masker_unavailable"}
