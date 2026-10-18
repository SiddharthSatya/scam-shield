"""Turn scores into a decision. Pure functions only."""

from dataclasses import dataclass
from enum import StrEnum

CONTEXT_WEIGHT = 0.5  # combined = (1 - w) * money + w * context


class Decision(StrEnum):
    PASS = "pass"  # let the payment go
    ASK = "ask"  # show the safety check
    HOLD = "hold"  # pause and explain; customer chooses
    COOLING_OFF = "cooling_off"  # very risky: delay + bank call


@dataclass(frozen=True)
class Thresholds:
    ask: float
    hold: float
    cooling_off: float
    context_hold: float = 0.85  # context score alone that triggers a hold

    def __post_init__(self) -> None:
        if not 0 <= self.ask <= self.hold <= 1 or not 0 <= self.cooling_off <= 1:
            raise ValueError("thresholds must satisfy 0 <= ask <= hold <= 1")
        if not 0 <= self.context_hold <= 1:
            raise ValueError("context_hold must be between 0 and 1")


def combined_score(money: float, context: float) -> float:
    return round((1 - CONTEXT_WEIGHT) * money + CONTEXT_WEIGHT * context, 3)


def decide_after_money(money: float, t: Thresholds) -> Decision:
    """First step: money score alone."""
    if money >= t.cooling_off:
        return Decision.COOLING_OFF
    if money >= t.ask:
        return Decision.ASK
    return Decision.PASS


def decide_after_context(money: float, context: float, t: Thresholds) -> Decision:
    """Second step: money + context. Never returns ASK."""
    if money >= t.cooling_off:
        return Decision.COOLING_OFF
    # The customer's own answers can be enough: a near-certain scam story is held even when
    # the money looks only slightly unusual.
    if context >= t.context_hold or combined_score(money, context) >= t.hold:
        return Decision.HOLD
    return Decision.PASS
