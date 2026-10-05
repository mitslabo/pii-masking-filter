from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from pii_chat.masker import get_masker

app = FastAPI(title="pii-masking-filter", version="0.1.0")


class MaskRequest(BaseModel):
    text: str = Field(min_length=1, description="Text to mask")


class MaskResponse(BaseModel):
    masked_text: str
    has_pii: bool
    entity_count: int


class HealthResponse(BaseModel):
    status: str


@lru_cache(maxsize=1)
def _masker():
    return get_masker()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/mask", response_model=MaskResponse)
def mask(payload: MaskRequest) -> MaskResponse:
    try:
        result = _masker().mask(payload.text)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise HTTPException(status_code=500, detail="masking_failed") from exc
    return MaskResponse(
        masked_text=result.masked_text,
        has_pii=result.has_pii,
        entity_count=len(result.entities),
    )
