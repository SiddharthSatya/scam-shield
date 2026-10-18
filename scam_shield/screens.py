"""Server-driven screens: JSON the bank's app renders with its own components.

New questions or wording ship from here, without an app release.
"""

from typing import Literal

from pydantic import BaseModel

from scam_shield.context import PURPOSE_LABELS, ContextResult
from scam_shield.scam_types import DISPLAY_NAMES, ScamType

COOLING_OFF_MINUTES = 30


class Option(BaseModel):
    value: str
    label: str


class Question(BaseModel):
    id: str
    kind: Literal["single_choice", "yes_no", "upload_optional"]
    text: str
    options: list[Option] = []


class Button(BaseModel):
    action: Literal["submit", "cancel_payment", "call_bank", "continue_anyway"]
    label: str
    style: Literal["primary", "secondary", "danger"] = "secondary"


class Screen(BaseModel):
    kind: Literal["safety_check", "warning", "cooling_off"]
    title: str
    body: str | None = None
    scam_name: str | None = None
    bullets: list[str] = []
    questions: list[Question] = []
    buttons: list[Button] = []


def safety_check_screen() -> Screen:
    yes_no = [Option(value="yes", label="Yes"), Option(value="no", label="No")]
    return Screen(
        kind="safety_check",
        title="Quick safety check",
        body="This payment looks different from your usual ones. Three quick taps.",
        questions=[
            Question(id="purpose", kind="single_choice", text="What is this payment for?",
                     options=[Option(value=p.value, label=label)
                              for p, label in PURPOSE_LABELS.items()]),
            Question(id="on_call", kind="yes_no",
                     text="Is someone on a call with you right now?", options=yes_no),
            Question(id="told_to_keep_secret", kind="yes_no",
                     text="Were you told to keep this secret or act fast?", options=yes_no),
            Question(id="message", kind="upload_optional",
                     text="Got a message about this? Share a screenshot (optional)."),
        ],
        buttons=[Button(action="submit", label="Continue", style="primary")],
    )


def warning_screen(context: ContextResult, money_reasons: list[str]) -> Screen:
    scam = context.scam_type
    title = "Payment paused"
    name = DISPLAY_NAMES[scam] if scam is not ScamType.NONE else "This looks risky"
    bullets = (context.red_flags or money_reasons)[:4]
    return Screen(
        kind="warning",
        title=title,
        scam_name=name,
        body=context.explanation,
        bullets=bullets,
        buttons=[
            Button(action="cancel_payment", label="Cancel payment", style="primary"),
            Button(action="call_bank", label="Call my bank"),
            Button(action="continue_anyway", label="Continue anyway", style="danger"),
        ],
    )


def cooling_off_screen(money_reasons: list[str]) -> Screen:
    return Screen(
        kind="cooling_off",
        title="Payment on hold for your safety",
        body=(f"This payment is very unusual for your account. We will hold it for "
              f"{COOLING_OFF_MINUTES} minutes and our team will call you to confirm."),
        bullets=money_reasons[:4],
        buttons=[
            Button(action="cancel_payment", label="Cancel payment", style="primary"),
            Button(action="call_bank", label="Call my bank now"),
        ],
    )
