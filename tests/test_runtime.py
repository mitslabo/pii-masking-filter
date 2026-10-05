import os

import httpx
import pytest


API_URL = os.environ.get("PII_TEST_URL")
pytestmark = pytest.mark.skipif(
    not API_URL, reason="Set PII_TEST_URL to test a running local or Docker API"
)


@pytest.mark.parametrize(("method", "path", "payload", "status", "expected"), [
    ("GET", "/health", None, 200, {"status": "ok"}),
    ("POST", "/mask", {
        "text": "電話は090-1234-5678です。メールはtaro@example.comです。",
    }, 200, {
        "masked_text": "電話は<電話番号_1>です。メールは<メールアドレス_1>です。",
        "has_pii": True,
        "entity_count": 2,
    }),
    ("POST", "/mask", {"text": ""}, 422, {"detail": "invalid_request"}),
])
def test_running_api(method, path, payload, status, expected):
    with httpx.Client(base_url=API_URL, timeout=90, trust_env=False) as client:
        response = client.request(method, path, json=payload)
    assert response.status_code == status
    assert response.json() == expected
