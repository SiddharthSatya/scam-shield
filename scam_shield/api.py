"""Scam Shield HTTP API (FastAPI).

Called only by the bank's backend, never by the phone directly.
Run locally: uvicorn scam_shield.api:app --reload
"""

import base64
import binascii
import hmac
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from google.cloud import bigquery
from pydantic import BaseModel, Field

from scam_shield import service, tokens
from scam_shield.context import ContextInput, Purpose
from scam_shield.decision import Decision
from scam_shield.gemini import get_client as get_gemini_client
from scam_shield.money_repo import CustomerNotFound
from scam_shield.scam_types import DISPLAY_NAMES, ScamType
from scam_shield.screens import Screen
from scam_shield.settings import get_settings

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
GEMINI_TIMEOUT_MS = 15_000  # context step must stay snappy; on timeout we fall back to taps


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.deps = service.Deps(
        settings=settings,
        bq=bigquery.Client(project=settings.gcp_project, location=settings.gcp_region),
        gemini=get_gemini_client(settings, timeout_ms=GEMINI_TIMEOUT_MS),
    )
    yield


# API docs (/docs, /redoc, /openapi.json) are off by default so the public URL doesn't
# reveal the API's shape. Set ENABLE_DOCS=true locally to browse them. Read straight from
# the environment because the app object is built at import time, before Settings load.
_DOCS = os.getenv("ENABLE_DOCS", "false").lower() == "true"

app = FastAPI(
    title="Scam Shield",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)


# ---------- Dependencies ----------

def get_deps(request: Request) -> service.Deps:
    return request.app.state.deps


def require_api_key(
    deps: Annotated[service.Deps, Depends(get_deps)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = deps.settings.api_key.get_secret_value()
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


DepsDep = Annotated[service.Deps, Depends(get_deps)]
Auth = [Depends(require_api_key)]


# ---------- Schemas ----------

class CheckPaymentRequest(BaseModel):
    customer_id: str = Field(min_length=3, max_length=64)
    payee_id: str = Field(min_length=3, max_length=64)
    amount_inr: float = Field(gt=0, le=100_000_000)
    hour_ist: int | None = Field(default=None, ge=0, le=23, description="Defaults to now (IST)")


class CheckPaymentResponse(BaseModel):
    check_id: str
    decision: Decision
    money_score: float
    reasons: list[str]
    screen: Screen | None
    token: str | None = Field(description="Send back to /v1/context when decision is 'ask'")


class ContextRequest(BaseModel):
    token: str = Field(min_length=10, max_length=4_000)
    purpose: Purpose | None = None
    on_call: bool | None = None
    told_to_keep_secret: bool | None = None
    message_text: str | None = Field(default=None, max_length=5_000)
    image_base64: str | None = Field(default=None, max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)
    image_mime_type: Literal["image/png", "image/jpeg", "image/webp"] = "image/png"


class ContextResponse(BaseModel):
    check_id: str
    decision: Decision
    money_score: float
    context_score: float
    combined_score: float
    scam_type: ScamType
    scam_name: str
    red_flags: list[str]
    explanation: str
    context_source: str
    screen: Screen | None


# ---------- Routes ----------

@app.get("/health")  # not /healthz: Cloud Run reserves paths ending in "z"
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/check-payment", dependencies=Auth)
def check_payment(
    req: CheckPaymentRequest, deps: DepsDep, background: BackgroundTasks
) -> CheckPaymentResponse:
    hour = req.hour_ist if req.hour_ist is not None else datetime.now(IST).hour
    try:
        step, row = service.check_payment(deps, req.customer_id, req.payee_id,
                                          req.amount_inr, hour)
    except CustomerNotFound as e:
        raise HTTPException(status_code=404, detail="Unknown customer") from e
    background.add_task(service.write_log, deps.bq, deps.settings.table("decisions"), row)
    return CheckPaymentResponse(check_id=step.check_id, decision=step.decision,
                                money_score=step.money_score, reasons=step.reasons,
                                screen=step.screen, token=step.token)


@app.post("/v1/context", dependencies=Auth)
def submit_context(
    req: ContextRequest, deps: DepsDep, background: BackgroundTasks
) -> ContextResponse:
    image = _decode_image(req.image_base64)
    ctx = ContextInput(purpose=req.purpose, on_call=req.on_call,
                       told_to_keep_secret=req.told_to_keep_secret,
                       message_text=req.message_text, image_bytes=image,
                       image_mime_type=req.image_mime_type)
    try:
        step, row = service.submit_context(deps, req.token, ctx)
    except tokens.InvalidToken as e:
        raise HTTPException(status_code=400, detail=f"Invalid check token: {e}") from e
    background.add_task(service.write_log, deps.bq, deps.settings.table("decisions"), row)
    c = step.context
    return ContextResponse(
        check_id=step.check_id, decision=step.decision, money_score=step.money_score,
        context_score=c.score, combined_score=step.combined_score, scam_type=c.scam_type,
        scam_name=DISPLAY_NAMES[c.scam_type], red_flags=c.red_flags,
        explanation=c.explanation, context_source=c.source, screen=step.screen,
    )


class OutcomeRequest(BaseModel):
    token: str = Field(min_length=10, max_length=4_000)
    action: service.CustomerAction


@app.post("/v1/outcome", dependencies=Auth, status_code=204)
def record_outcome(req: OutcomeRequest, deps: DepsDep, background: BackgroundTasks) -> None:
    """What the customer did after a warning. Feeds the dashboard's "money protected"."""
    try:
        row = service.record_outcome(deps, req.token, req.action)
    except tokens.InvalidToken as e:
        raise HTTPException(status_code=400, detail=f"Invalid check token: {e}") from e
    background.add_task(service.write_log, deps.bq, deps.settings.table("decisions"), row)


def _decode_image(data: str | None) -> bytes | None:
    if not data:
        return None
    try:
        image = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=422, detail="image_base64 is not valid base64") from e
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image larger than 5 MB")
    return image
