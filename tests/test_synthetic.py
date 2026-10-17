from datetime import UTC, datetime, timedelta

import pytest

from scam_shield.synthetic import (
    DEMO_CUSTOMERS,
    DEMO_NEW_PAYEES,
    HISTORY_DAYS,
    IST,
    build_all,
    token,
)

END = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def data():
    return build_all(n_background=10, seed=7, end=END)


def test_token_is_stable_and_hashed():
    assert token("c", "meera") == token("c", "meera")
    assert token("c", "meera") != token("c", "rahul")
    assert "meera" not in token("c", "meera")


def test_build_is_deterministic():
    a = build_all(n_background=5, seed=1, end=END)
    b = build_all(n_background=5, seed=1, end=END)
    assert a.transactions.equals(b.transactions)
    assert a.customers.equals(b.customers)


def test_ids_are_unique(data):
    assert data.customers.customer_id.is_unique
    assert data.payees.payee_id.is_unique
    assert data.transactions.txn_id.is_unique


def test_every_transaction_links_to_known_customer_and_payee(data):
    assert set(data.transactions.customer_id) <= set(data.customers.customer_id)
    assert set(data.transactions.payee_id) <= set(data.payees.payee_id)


def test_history_window_and_ordering(data):
    ts = data.transactions.ts
    assert ts.max() <= END
    assert ts.min() >= END - timedelta(days=HISTORY_DAYS + 1)


def test_payments_fall_inside_usual_hours(data):
    hours = data.customers.set_index("customer_id")[["active_from_hour", "active_to_hour"]]
    tx = data.transactions.join(hours, on="customer_id")
    local_hour = tx.ts.dt.tz_convert(IST).dt.hour
    # A payment shifted back a day keeps its hour, so this always holds.
    assert ((local_hour >= tx.active_from_hour) & (local_hour <= tx.active_to_hour)).all()


def test_balance_walks_down_and_ends_at_current_balance(data):
    meera = DEMO_CUSTOMERS["meera"]
    tx = data.transactions[data.transactions.customer_id == meera.customer_id].sort_values("ts")
    last = tx.iloc[-1]
    assert last.balance_before_inr - last.amount_inr == pytest.approx(meera.balance_inr)
    assert tx.balance_before_inr.is_monotonic_decreasing


def test_demo_scam_payees_are_new_and_absent_from_history(data):
    for payee in DEMO_NEW_PAYEES.values():
        assert payee.payee_id not in set(data.transactions.payee_id)
    assert DEMO_NEW_PAYEES["mule-arrest"].account_age_days < 30


def test_demo_scam_amounts_dwarf_normal_spend(data):
    meera = DEMO_CUSTOMERS["meera"].customer_id
    usual_max = data.transactions[data.transactions.customer_id == meera].amount_inr.max()
    arrest = data.scenarios.set_index("scenario_id").loc["digital_arrest"]
    assert arrest.amount_inr > 20 * usual_max
