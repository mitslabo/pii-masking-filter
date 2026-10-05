# pii-masking-filter

A REST API server for Japanese PII masking based on Microsoft Presidio.

## Endpoints

- `GET /health` — health check
- `POST /mask` — mask Japanese PII in the submitted text

## Local run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m spacy download ja_core_news_lg
uvicorn app:app --reload
```

## Example

```bash
curl -X POST http://127.0.0.1:8000/mask \
  -H 'Content-Type: application/json' \
  -d '{"text":"私の名前は山田太郎です。電話は090-1234-5678です。"}'
```
