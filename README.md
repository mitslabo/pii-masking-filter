# pii-masking-filter

A REST API server for Japanese PII masking based on Microsoft Presidio.

The masking components in `pii_masking/` are adapted from
[`kouki6951/pii-masking-chat`](https://github.com/kouki6951/pii-masking-chat/tree/main/pii_chat).
This product contains only masking: no conversational UI, external AI API, or
reversible mapping of original PII.

## Endpoints

- `GET /health` — health check
- `POST /mask` — mask Japanese PII in the submitted text

## Local run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m spacy download ja_core_news_lg
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Run these commands from the repository root with Python 3.10 or newer.
For development, add `--reload`. The Japanese model is installed explicitly;
the server never downloads it while processing a request. Internet access is
not needed after dependencies and the model have been installed.

## Example

```bash
curl -X POST http://127.0.0.1:8000/mask \
  -H 'Content-Type: application/json' \
  -d '{"text":"電話は090-1234-5678です。メールはtaro@example.comです。"}'
```

```json
{
  "masked_text": "電話は<電話番号_1>です。メールは<メールアドレス_1>です。",
  "has_pii": true,
  "entity_count": 2
}
```

`GET /health` returns `{"status":"ok"}` (HTTP 200). It is a liveness check,
not a model-readiness check. Only these two routes are exposed; interactive
documentation and the OpenAPI endpoint are disabled.

`POST /mask` accepts one string field, `text`, of 1–100,000 characters.
Unknown fields and invalid/malformed requests return HTTP 422 with
`{"detail":"invalid_request"}`. A missing model or invalid configuration returns
HTTP 503 with `{"detail":"masker_unavailable"}`; processing failures return
HTTP 500 with `{"detail":"masking_failed"}`. Errors never include submitted text.

Placeholders use Japanese labels and per-request numbering. Repeated values
of the same entity type share a placeholder; `entity_count` counts detected
occurrences, not unique values. Text without detected PII is returned unchanged.
Supported detection includes names, locations and organizations (spaCy NER),
email, phone, postal/address, personal number, passport, driver's license, bank
account, credit card, IP address and URL patterns.

## Configuration

- `SPACY_MODEL`: installed Japanese spaCy package (default `ja_core_news_lg`).
- `PII_SCORE_THRESHOLD`: detection score from 0 to 1 (default `0.4`).

The model is loaded lazily once per worker and shared across requests. The first
mask request can be slow; send a synthetic `/mask` request before routing traffic
to a worker. Each additional worker needs its own model memory.

## Tests

```bash
python -m pytest -q
```

Tests exercise the API and real Presidio recognizers while bypassing the heavy
spaCy model. They need no model download. To check the installed model as well,
start the server and run the example request above.

## Deployment and privacy

There is no application logging of request bodies, original PII, or reversible
mappings. Validation and processing errors are sanitized. Default Uvicorn access
logs contain paths and status codes, not bodies; never submit PII in URLs or query
parameters. Configure reverse proxies/observability tools not to capture bodies.

Use a trusted network or an authenticated, TLS-enabled reverse proxy; the API
itself does not implement authentication. Set request-body size limits, rate
limits, and timeouts at that boundary (the character limit is validated only
after JSON parsing). Do not use development reload in production.

Detection is heuristic and cannot guarantee that every PII value is removed.
Review accuracy on representative Japanese text before using output as anonymized
data; undetected PII remains in `masked_text`.
