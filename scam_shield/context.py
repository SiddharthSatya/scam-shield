"""Context check: why is the customer paying, and does the story look like a scam?

Inputs are the customer's taps, plus an optional message text or screenshot.
Gemini reads them and returns a structured verdict. If Gemini fails or is slow,
we fall back to a score from the taps alone, so a payment check never hangs.
"""

import logging
from enum import StrEnum

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from scam_shield.scam_types import DESCRIPTIONS, ScamType

log = logging.getLogger(__name__)

LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi", "ta": "Tamil",
                  "te": "Telugu", "bn": "Bengali"}


class Purpose(StrEnum):
    FAMILY = "family"
    SHOPPING_BILL = "shopping_bill"
    INVESTMENT = "investment"
    GOVT_POLICE_KYC = "govt_police_kyc"
    JOB_TASK_REWARD = "job_task_reward"
    SOMEONE_ASKED = "someone_asked"


# How suspicious each tap is on its own (used for the floor and the fallback).
PURPOSE_RISK: dict[Purpose, float] = {
    Purpose.FAMILY: 0.1,
    Purpose.SHOPPING_BILL: 0.1,
    Purpose.INVESTMENT: 0.5,
    Purpose.GOVT_POLICE_KYC: 0.8,
    Purpose.JOB_TASK_REWARD: 0.8,
    Purpose.SOMEONE_ASKED: 0.6,
}
PURPOSE_TO_SCAM: dict[Purpose, ScamType] = {
    Purpose.INVESTMENT: ScamType.INVESTMENT,
    Purpose.GOVT_POLICE_KYC: ScamType.DIGITAL_ARREST,
    Purpose.JOB_TASK_REWARD: ScamType.JOB_TASK,
}
ON_CALL_RISK = 0.3
SECRECY_RISK = 0.3


class ContextInput(BaseModel):
    purpose: Purpose | None = None
    on_call: bool | None = None
    told_to_keep_secret: bool | None = None
    message_text: str | None = Field(default=None, max_length=5_000)
    image_bytes: bytes | None = None
    image_mime_type: str = "image/png"
    language: str = "en"  # language for the customer-facing explanation


class ContextVerdict(BaseModel):
    """What Gemini must return."""
    scam_type: ScamType
    score: float = Field(ge=0, le=1, description="0 = clearly genuine, 1 = clearly a scam")
    red_flags: list[str] = Field(description="Short phrases: what gave it away. Empty if none.")
    explanation: str = Field(description="2-3 short sentences for the customer, plain words")


class ContextResult(ContextVerdict):
    source: str  # "gemini" or "fallback"


def tap_risk(ctx: ContextInput) -> float:
    """Score from taps alone, 0..1."""
    risk = PURPOSE_RISK.get(ctx.purpose, 0.0) if ctx.purpose else 0.0
    if ctx.on_call:
        risk += ON_CALL_RISK
    if ctx.told_to_keep_secret:
        risk += SECRECY_RISK
    return min(risk, 1.0)


def fallback_result(ctx: ContextInput) -> ContextResult:
    """Used when Gemini is unavailable. Conservative and based on taps only."""
    score = tap_risk(ctx)
    flags = []
    if ctx.on_call:
        flags.append("Someone is on a call with you while you pay")
    if ctx.told_to_keep_secret:
        flags.append("You were told to keep it secret or act fast")
    scam = PURPOSE_TO_SCAM.get(ctx.purpose, ScamType.NONE) if ctx.purpose else ScamType.NONE
    if score < 0.5:
        scam = ScamType.NONE
    explanation = (
        "This payment has signs of a scam. Banks, police and employers never ask you to "
        "move money urgently or in secret. Please pause and check with someone you trust."
        if score >= 0.5
        else "Nothing in your answers looks like a scam."
    )
    return ContextResult(scam_type=scam, score=score, red_flags=flags,
                         explanation=explanation, source="fallback")


SYSTEM_PROMPT = """You are the scam-check step inside an Indian bank's payment flow.
A customer is about to send money. You get their answers to a short safety check,
and sometimes the message or screenshot that made them pay.

Decide if this payment is being pushed by a scammer. Scam types:
{types}

Rules:
- Judge the whole story: answers + message. If there is no message, judge the answers.
- Being on a call while paying, or being told to keep it secret or hurry, are strong scam signs.
- Genuine cases (family, bills, purchases with real invoices, normal bank alerts) score low.
- red_flags: short phrases naming what gave it away. Empty list if genuine.
- explanation: write for a worried, non-technical person, in {language}. 2-3 short sentences.
  If it is a scam, name the scam in simple words and say what real banks/police never do.
- Never ask the customer for passwords, PINs or OTPs.
"""


def _build_prompt(ctx: ContextInput) -> str:
    answers = [
        f"Purpose of payment: {ctx.purpose.value if ctx.purpose else 'not answered'}",
        f"On a call with someone right now: {_yes_no(ctx.on_call)}",
        f"Told to keep it secret or act fast: {_yes_no(ctx.told_to_keep_secret)}",
        f"Message shared: {ctx.message_text!r}" if ctx.message_text else "Message shared: none",
    ]
    if ctx.image_bytes:
        answers.append("A screenshot is attached.")
    return "Customer's safety-check answers:\n" + "\n".join(f"- {a}" for a in answers)


def _yes_no(value: bool | None) -> str:
    return "not answered" if value is None else "yes" if value else "no"


def read_context(ctx: ContextInput, client: genai.Client, model: str) -> ContextResult:
    """Ask Gemini for a verdict. Never raises: falls back to taps on any error."""
    language = LANGUAGE_NAMES.get(ctx.language, "English")
    system = SYSTEM_PROMPT.format(
        types="\n".join(f"- {t.value}: {d}" for t, d in DESCRIPTIONS.items()),
        language=language,
    )
    parts: list = [_build_prompt(ctx)]
    if ctx.image_bytes:
        parts.append(types.Part.from_bytes(data=ctx.image_bytes, mime_type=ctx.image_mime_type))
    try:
        response = client.models.generate_content(
            model=model,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=ContextVerdict,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        verdict = response.parsed
        if not isinstance(verdict, ContextVerdict):
            raise ValueError("Gemini response did not match the schema")
    except Exception:
        log.exception("Context check fell back to taps")
        return fallback_result(ctx)

    # Strong taps are never overruled by a lenient model reading.
    score = max(verdict.score, tap_risk(ctx))
    return ContextResult(**{**verdict.model_dump(), "score": round(score, 3)}, source="gemini")
