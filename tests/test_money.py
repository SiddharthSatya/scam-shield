import pytest

from scam_shield.money import PaymentFacts, money_score, rule_signals


def profile(balance: float, p95: float, start: int, end: int) -> dict:
    return {"balance_inr": balance, "p95_amount_inr": p95,
            "usual_from_hour": start, "usual_to_hour": end}


# Profiles taken from the demo personas in BigQuery.
MEERA = profile(600_000, 8_396, 9, 19)
ARJUN = profile(900_000, 20_959, 9, 21)


def facts(**overrides) -> PaymentFacts:
    base = {
        **MEERA,
        "amount_inr": 1_200,
        "hour_ist": 11,
        "is_new_payee": False,
        "payee_account_age_days": 3_100,
    }
    return PaymentFacts(**{**base, **overrides})


def test_normal_grocery_payment_is_low():
    result = money_score(facts(), model_probability=0.05)
    assert result.score < 0.1
    assert result.reasons == ()


def test_digital_arrest_payment_is_high_with_reasons():
    f = facts(amount_inr=480_000, hour_ist=21, is_new_payee=True, payee_account_age_days=2)
    result = money_score(f, model_probability=0.5)
    assert result.score > 0.75
    assert result.reasons[0] == "About 57x the usual amount"
    assert "First payment to this payee" in result.reasons
    assert "Payee account is only 2 days old" in result.reasons
    assert "Outside usual payment hours (9 PM)" in result.reasons


def test_car_purchase_is_medium_so_we_ask_not_hold():
    f = facts(**ARJUN, amount_inr=480_000, hour_ist=12, is_new_payee=True,
              payee_account_age_days=2_900)
    result = money_score(f, model_probability=0.1)
    assert 0.35 < result.score < 0.6


def test_model_missing_falls_back_to_rules():
    f = facts(amount_inr=480_000, is_new_payee=True)
    result = money_score(f, model_probability=None)
    assert result.score == result.rules_score
    assert result.model_probability is None


def test_no_history_uses_defaults():
    f = facts(p95_amount_inr=None, usual_from_hour=None, usual_to_hour=None, hour_ist=3)
    signals = rule_signals(f)
    assert signals["off_hours"] == 1.0
    assert signals["amount_spike"] == 0.0  # 1,200 is below the 5,000 default


def test_full_balance_counts_as_draining():
    signals = rule_signals(facts(amount_inr=600_000))
    assert signals["drains_account"] == 1.0
    assert signals["balance_share"] == 1.0


def test_zero_balance_does_not_divide_by_zero():
    assert facts(balance_inr=0).share_of_balance == 1.0


@pytest.mark.parametrize("bad", [{"amount_inr": 0}, {"amount_inr": -5}, {"hour_ist": 24}])
def test_invalid_input_rejected(bad):
    with pytest.raises(ValueError):
        facts(**bad)


def test_score_is_bounded():
    f = facts(amount_inr=10_000_000, balance_inr=1, hour_ist=3, is_new_payee=True,
              payee_account_age_days=0)
    assert money_score(f, model_probability=5.0).score <= 1.0


def test_model_can_raise_but_never_lower_the_score():
    f = facts(amount_inr=480_000, is_new_payee=True)
    rules_only = money_score(f, model_probability=None).score
    assert money_score(f, model_probability=0.0).score == rules_only
    assert money_score(f, model_probability=1.0).score > rules_only


def test_one_day_old_payee_reads_naturally():
    f = facts(amount_inr=480_000, is_new_payee=True, payee_account_age_days=1)
    assert "Payee account is only 1 day old" in money_score(f, None).reasons
