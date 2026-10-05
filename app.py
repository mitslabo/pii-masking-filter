from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from pii_masking.config import MAX_TEXT_LENGTH
from pii_masking.masker import JapanesePiiMasker, get_masker

app = FastAPI(
    title="pii-masking-filter", version="0.1.0",
    docs_url=None, redoc_url=None, openapi_url=None,
)


class MaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(
        min_length=1, max_length=MAX_TEXT_LENGTH, strict=True, description="Text to mask"
    )


class MaskResponse(BaseModel):
    masked_text: str
    has_pii: bool
    entity_count: int


class HealthResponse(BaseModel):
    status: str


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc) -> JSONResponse:
    # FastAPI's default validation details can echo the submitted PII.
    return JSONResponse(status_code=422, content={"detail": "invalid_request"})


def _masker() -> JapanesePiiMasker:
    try:
        return get_masker()
    except Exception:
        raise HTTPException(status_code=503, detail="masker_unavailable") from None


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/mask", response_model=MaskResponse)
def mask(payload: MaskRequest) -> MaskResponse:
    masker = _masker()
    try:
        result = masker.mask(payload.text)
        return MaskResponse(
            masked_text=result.masked_text,
            has_pii=result.has_pii,
            entity_count=len(result.entities),
        )
    except Exception:
        raise HTTPException(status_code=500, detail="masking_failed") from None
