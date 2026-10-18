"""The two steps of a payment check, wired to BigQuery and Gemini.

The API layer stays thin: it validates input, calls these functions, and maps errors.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from google import genai
from google.cloud import bigquery

from scam_shield import tokens
from scam_shield.context import ContextInput, ContextResult, read_context
from scam_shield.decision import (
    Decision,
    Thresholds,
    combined_score,
    decide_after_context,
    decide_after_money,
)
from scam_shield.money import money_score
from scam_shield.money_repo import fetch_money_inputs
from scam_shield.screens import Screen, cooling_off_screen, safety_check_screen, warning_screen
from scam_shield.settings import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Deps:
    settings: Settings
    bq: bigquery.Client
    gemini: genai.Client

    @property
    def thresholds(self) -> Thresholds:
        s = self.settings
        return Thresholds(ask=s.ask_threshold, hold=s.hold_threshold,
                          cooling_off=s.cooling_off_threshold,
                          context_hold=s.context_hold_threshold)


@dataclass(frozen=True)
class MoneyStep:
    check_id: str
    decision: Decision
    money_score: float
    reasons: list[str]
    screen: Screen | None
    token: str | None  # only when decision is ASK


@dataclass(frozen=True)
class FinalStep:
    check_id: str
    decision: Decision
    money_score: float
    context: ContextResult
    combined_score: float
    screen: Screen | None


def check_payment(
    deps: Deps, customer_id: str, payee_id: str, amount_inr: float, hour_ist: int
) -> tuple[MoneyStep, dict[str, Any]]:
    """Step 1. Returns the result and a log row (written by the caller in the background)."""
    inputs = fetch_money_inputs(deps.bq, deps.settings, customer_id, payee_id,
                                amount_inr, hour_ist)
    money = money_score(inputs.facts, inputs.model_probability)
    decision = decide_after_money(money.score, deps.thresholds)
    check_id = uuid.uuid4().hex
    reasons = list(money.reasons)

    screen, token = None, None
    if decision is Decision.ASK:
        screen = safety_check_screen()
        token = tokens.issue(
            {"check_id": check_id, "customer_id": customer_id, "payee_id": payee_id,
             "amount_inr": amount_inr, "hour_ist": hour_ist, "money_score": money.score,
             "reasons": reasons, "language": inputs.language},
            deps.settings.token_secret.get_secret_value(),
            deps.settings.token_ttl_seconds,
        )
    elif decision is Decision.COOLING_OFF:
        screen = cooling_off_screen(reasons)

    step = MoneyStep(check_id, decision, money.score, reasons, screen, token)
    row = _log_row(check_id, "money", customer_id, payee_id, amount_inr, hour_ist,
                   decision, money.score, reasons)
    return step, row


class AlreadyDecided(RuntimeError):
    """The context step for this check already ran. Stops a coached customer (or a
    scammer) from resubmitting softer answers on the same token to flip a hold."""


def submit_context(deps: Deps, token: str, ctx: ContextInput) -> tuple[FinalStep, dict[str, Any]]:
    """Step 2. Raises tokens.InvalidToken (bad/expired token) or AlreadyDecided (replay)."""
    p = tokens.verify(token, deps.settings.token_secret.get_secret_value())
    if final_already_recorded(deps.bq, deps.settings.table("decisions"), p["check_id"]):
        raise AlreadyDecided(p["check_id"])
    ctx = ctx.model_copy(update={"language": p["language"]})
    context = read_context(ctx, deps.gemini, deps.settings.gemini_model)

    money = p["money_score"]
    decision = decide_after_context(money, context.score, deps.thresholds)
    combined = combined_score(money, context.score)
    if decision is Decision.HOLD:
        screen = warning_screen(context, p["reasons"])
    elif decision is Decision.COOLING_OFF:
        screen = cooling_off_screen(p["reasons"])
    else:
        screen = None

    step = FinalStep(p["check_id"], decision, money, context, combined, screen)
    row = _log_row(p["check_id"], "final", p["customer_id"], p["payee_id"], p["amount_inr"],
                   p["hour_ist"], decision, money, p["reasons"], context, combined)
    return step, row


class CustomerAction(StrEnum):
    """What the customer chose on a warning or cooling-off screen."""
    CANCEL_PAYMENT = "cancel_payment"
    CONTINUE_ANYWAY = "continue_anyway"
    CALL_BANK = "call_bank"


def record_outcome(deps: Deps, token: str, action: CustomerAction) -> dict[str, Any]:
    """Step 3 (optional). Returns a log row. Raises tokens.InvalidToken on a bad token."""
    p = tokens.verify(token, deps.settings.token_secret.get_secret_value())
    return _log_row(p["check_id"], "outcome", p["customer_id"], p["payee_id"], p["amount_inr"],
                    p["hour_ist"], action, p["money_score"], p["reasons"])


def _log_row(
    check_id: str, stage: str, customer_id: str, payee_id: str, amount_inr: float,
    hour_ist: int, decision: Decision | CustomerAction, money: float, reasons: list[str],
    context: ContextResult | None = None, combined: float | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "ts": datetime.now(UTC).isoformat(),
        "stage": stage,
        "customer_id": customer_id,
        "payee_id": payee_id,
        "amount_inr": amount_inr,
        "hour_ist": hour_ist,
        "decision": decision.value,
        "money_score": money,
        "money_reasons": reasons,
        "context_score": context.score if context else None,
        "combined_score": combined,
        "scam_type": context.scam_type.value if context else None,
        "red_flags": context.red_flags if context else [],
        "context_source": context.source if context else None,
    }


def final_already_recorded(bq: bigquery.Client, table_id: str, check_id: str) -> bool:
    """True if the decision log already has a final row for this check.

    Fails open (returns False) if BigQuery is unreachable: a log outage must not block
    payments. The log is written right after each response, so the replay window is the
    second or so it takes that write to land.
    """
    sql = f"SELECT 1 FROM `{table_id}` WHERE check_id = @check_id AND stage = 'final' LIMIT 1"
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("check_id", "STRING", check_id)])
    try:
        return next(iter(bq.query_and_wait(sql, job_config=config, wait_timeout=5.0)),
                    None) is not None
    except Exception:
        log.exception("Replay check failed; allowing the context step")
        return False


def write_log(bq: bigquery.Client, table_id: str, row: dict[str, Any]) -> None:
    """Best effort: a logging failure must never affect the payment decision."""
    try:
        errors = bq.insert_rows_json(table_id, [row])
        if errors:
            log.error("Decision log insert errors: %s", errors)
    except Exception:
        log.exception("Decision log write failed")
