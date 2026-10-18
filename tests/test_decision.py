import pytest

from scam_shield.decision import (
    Decision,
    Thresholds,
    combined_score,
    decide_after_context,
    decide_after_money,
)

T = Thresholds(ask=0.40, hold=0.70, cooling_off=0.90)


@pytest.mark.parametrize(("money", "expected"), [
    (0.00, Decision.PASS),
    (0.39, Decision.PASS),
    (0.40, Decision.ASK),  # boundary is inclusive
    (0.89, Decision.ASK),
    (0.90, Decision.COOLING_OFF),
])
def test_after_money(money, expected):
    assert decide_after_money(money, T) is expected


# Demo scenarios: money score + honest taps -> expected final decision.
@pytest.mark.parametrize(("name", "money", "context", "expected"), [
    ("car_purchase", 0.48, 0.1, Decision.PASS),
    ("job_task_purpose_only", 0.60, 0.8, Decision.HOLD),  # lands exactly on 0.70
    ("kyc_update", 0.74, 0.8, Decision.HOLD),
    ("digital_arrest", 0.87, 1.0, Decision.HOLD),
])
def test_after_context_demo_scenarios(name, money, context, expected):
    assert decide_after_context(money, context, T) is expected


def test_after_context_never_asks_again():
    for money in (0.4, 0.6, 0.8):
        for context in (0.0, 0.5, 1.0):
            assert decide_after_context(money, context, T) is not Decision.ASK


def test_cooling_off_wins_even_with_calm_context():
    assert decide_after_context(0.95, 0.0, T) is Decision.COOLING_OFF


def test_combined_score_is_average():
    assert combined_score(0.6, 0.8) == 0.7


def test_bad_thresholds_rejected():
    with pytest.raises(ValueError):
        Thresholds(ask=0.8, hold=0.5, cooling_off=0.9)


def test_context_hold_threshold_validated():
    with pytest.raises(ValueError):
        Thresholds(ask=0.4, hold=0.7, cooling_off=0.9, context_hold=1.2)
