"""Money check: is this payment unusual for this customer?

Pure logic only. The BigQuery lookup lives in money_repo.py.
Score = profile rules (explainable), boosted by the BigQuery ML model.
The model is trained on PaySim, where fraud is mostly "empty the whole account", so it is
good at that one pattern and blind to others. It may therefore only raise the score.
"""

import math
from dataclasses import dataclass

# How much each rule counts. Rules are each 0..1.
RULE_WEIGHTS: dict[str, float] = {
    "new_payee": 0.20,
    "amount_spike": 0.25,
    "balance_share": 0.20,
    "off_hours": 0.10,
    "young_payee_account": 0.15,
    "drains_account": 0.10,
}
MODEL_WEIGHT = 0.2  # max boost the model can add on top of rules

# Fallbacks when a customer has no history yet.
DEFAULT_P95_INR = 5_000.0
DEFAULT_ACTIVE_HOURS = (7, 22)


@dataclass(frozen=True)
class PaymentFacts:
    amount_inr: float
    balance_inr: float
    hour_ist: int
    is_new_payee: bool
    payee_account_age_days: int | None
    p95_amount_inr: float | None = None
    usual_from_hour: int | None = None
    usual_to_hour: int | None = None

    def __post_init__(self) -> None:
        if self.amount_inr <= 0:
            raise ValueError("amount_inr must be positive")
        if not 0 <= self.hour_ist <= 23:
            raise ValueError("hour_ist must be 0..23")

    @property
    def share_of_balance(self) -> float:
        return 1.0 if self.balance_inr <= 0 else min(self.amount_inr / self.balance_inr, 1.0)

    @property
    def amount_vs_usual(self) -> float:
        return self.amount_inr / (self.p95_amount_inr or DEFAULT_P95_INR)


@dataclass(frozen=True)
class MoneyResult:
    score: float
    rules_score: float
    model_probability: float | None
    reasons: tuple[str, ...]


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _hour_label(hour: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    return f"{(hour % 12) or 12} {suffix}"


def _days(n: int | None) -> str:
    return f"{n} day" if n == 1 else f"{n} days"


def rule_signals(f: PaymentFacts) -> dict[str, float]:
    """Each rule as a 0..1 strength."""
    start, end = (
        (f.usual_from_hour, f.usual_to_hour)
        if f.usual_from_hour is not None and f.usual_to_hour is not None
        else DEFAULT_ACTIVE_HOURS
    )
    age = f.payee_account_age_days
    return {
        "new_payee": 1.0 if f.is_new_payee else 0.0,
        # 1x usual -> 0, 10x -> 0.5, 100x+ -> 1
        "amount_spike": _clamp(math.log10(max(f.amount_vs_usual, 1.0)) / 2),
        # under 20% of balance -> 0, 80%+ -> 1
        "balance_share": _clamp((f.share_of_balance - 0.2) / 0.6),
        "off_hours": 0.0 if start <= f.hour_ist <= end else 1.0,
        "young_payee_account": (
            0.0 if age is None else 1.0 if age < 30 else 0.5 if age < 180 else 0.0
        ),
        "drains_account": 1.0 if f.share_of_balance >= 1.0 else 0.0,
    }


def explain_signals(f: PaymentFacts, signals: dict[str, float]) -> tuple[str, ...]:
    """Plain-English reasons for the rules that fired, strongest first."""
    texts = {
        "new_payee": "First payment to this payee",
        "amount_spike": f"About {f.amount_vs_usual:.0f}x the usual amount",
        "balance_share": f"{f.share_of_balance:.0%} of the account balance",
        "off_hours": f"Outside usual payment hours ({_hour_label(f.hour_ist)})",
        "young_payee_account": f"Payee account is only {_days(f.payee_account_age_days)} old",
        "drains_account": "Empties the account",
    }
    fired = sorted(
        (name for name, value in signals.items() if value >= 0.25),
        key=lambda name: signals[name] * RULE_WEIGHTS[name],
        reverse=True,
    )
    return tuple(texts[name] for name in fired)


def money_score(f: PaymentFacts, model_probability: float | None) -> MoneyResult:
    """Rules score, boosted by the model (noisy-OR). Model can raise, never lower, the score.
    If the model is unavailable, use rules alone."""
    signals = rule_signals(f)
    rules_score = sum(RULE_WEIGHTS[k] * v for k, v in signals.items()) / sum(RULE_WEIGHTS.values())
    if model_probability is None:
        score = rules_score
    else:
        score = 1 - (1 - rules_score) * (1 - MODEL_WEIGHT * _clamp(model_probability))
    return MoneyResult(
        score=round(score, 3),
        rules_score=round(rules_score, 3),
        model_probability=model_probability,
        reasons=explain_signals(f, signals),
    )
