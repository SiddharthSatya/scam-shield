"""Made-up customers, payees and payment history for the demo.

Pure functions only (no cloud calls), so they are easy to test.
All IDs are hashed tokens, the same way a bank would send them to us.
"""

import hashlib
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from faker import Faker

IST = ZoneInfo("Asia/Kolkata")
HISTORY_DAYS = 90


def token(prefix: str, raw: str) -> str:
    """Stable hashed ID, e.g. token('c', 'meera') -> 'c_3f9a...'."""
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


# category -> (typical min amount, typical max amount, payments per 30 days)
CATEGORY_HABITS: dict[str, tuple[int, int, float]] = {
    "grocery": (300, 3_000, 4),
    "utility": (800, 3_000, 1),
    "rent": (10_000, 30_000, 1),
    "family": (1_000, 10_000, 2),
    "food": (150, 800, 6),
    "pharmacy": (200, 1_500, 2),
    "shopping": (500, 5_000, 2),
    "mobile": (199, 799, 1),
}


@dataclass(frozen=True)
class Customer:
    customer_id: str
    display_name: str
    age: int
    city: str
    language: str
    balance_inr: float
    active_from_hour: int  # usual payment hours, IST
    active_to_hour: int


@dataclass(frozen=True)
class Payee:
    payee_id: str
    display_name: str
    category: str
    account_age_days: int


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    customer_id: str
    payee_id: str
    amount_inr: float
    hour_ist: int
    expected: str  # final outcome if the customer answers honestly: pass | hold
    scam_type: str | None


# ---------- Demo personas (fixed, so the demo is repeatable) ----------

def _c(key: str, name: str, age: int, city: str, lang: str, bal: float, hours: tuple[int, int]):
    return Customer(token("c", key), name, age, city, lang, bal, *hours)


def _p(key: str, name: str, category: str, age_days: int) -> Payee:
    return Payee(token("p", key), name, category, age_days)


DEMO_CUSTOMERS = {
    "meera": _c("meera", "Meera Kulkarni", 62, "Pune", "mr", 600_000, (9, 19)),
    "rahul": _c("rahul", "Rahul Verma", 24, "Bengaluru", "hi", 85_000, (10, 23)),
    "anita": _c("anita", "Anita Desai", 41, "Mumbai", "en", 240_000, (8, 21)),
    "arjun": _c("arjun", "Arjun Mehta", 35, "Gurugram", "en", 900_000, (9, 22)),
}

# Regular payees of each demo persona.
DEMO_REGULAR_PAYEES = {
    "meera": [
        _p("meera-grocer", "Kulkarni Kirana Stores", "grocery", 3_100),
        _p("meera-power", "MSEDCL Electricity", "utility", 9_000),
        _p("meera-son", "Aditya Kulkarni", "family", 2_400),
        _p("meera-pharma", "Apollo Pharmacy Pune", "pharmacy", 4_200),
    ],
    "rahul": [
        _p("rahul-rent", "Sunil Reddy (Landlord)", "rent", 1_800),
        _p("rahul-food", "Swiggy", "food", 3_500),
        _p("rahul-mobile", "Jio Recharge", "mobile", 5_000),
        _p("rahul-friend", "Karan Singh", "family", 900),
    ],
    "anita": [
        _p("anita-grocer", "BigBasket", "grocery", 4_000),
        _p("anita-power", "Adani Electricity", "utility", 6_000),
        _p("anita-shop", "Myntra", "shopping", 3_800),
        _p("anita-mom", "Sunita Desai", "family", 3_000),
    ],
    "arjun": [
        _p("arjun-rent", "DLF Homes Rent", "rent", 2_600),
        _p("arjun-food", "Zomato", "food", 3_600),
        _p("arjun-shop", "Amazon", "shopping", 5_500),
        _p("arjun-power", "DHBVN Electricity", "utility", 8_000),
    ],
}

# New payees used only in the live demo payments (not in history).
DEMO_NEW_PAYEES = {
    "mule-arrest": _p("mule-arrest", "Rakesh Sharma", "unknown", 2),
    "mule-task": _p("mule-task", "TaskPro Rewards", "unknown", 5),
    "mule-kyc": _p("mule-kyc", "SBI KYC Help Desk", "unknown", 1),
    "car-dealer": _p("car-dealer", "Mehta Motors Pvt Ltd", "shopping", 2_900),
}


def demo_scenarios() -> list[Scenario]:
    c, reg, new = DEMO_CUSTOMERS, DEMO_REGULAR_PAYEES, DEMO_NEW_PAYEES
    return [
        Scenario("normal_grocery", "Meera pays her grocer", c["meera"].customer_id,
                 reg["meera"][0].payee_id, 1_200, 11, "pass", None),
        Scenario("digital_arrest", "Meera and the 'CBI officer'", c["meera"].customer_id,
                 new["mule-arrest"].payee_id, 480_000, 21, "hold", "digital_arrest"),
        Scenario("job_task", "Rahul's 'task reward' deposit", c["rahul"].customer_id,
                 new["mule-task"].payee_id, 40_000, 23, "hold", "job_task"),
        Scenario("kyc_update", "Anita's 'KYC re-verification'", c["anita"].customer_id,
                 new["mule-kyc"].payee_id, 195_000, 20, "hold", "kyc_update"),
        Scenario("car_purchase", "Arjun buys a car", c["arjun"].customer_id,
                 new["car-dealer"].payee_id, 480_000, 12, "pass", None),
    ]


# ---------- Background customers ----------

def make_background(n_customers: int, seed: int) -> tuple[list[Customer], dict[str, list[Payee]]]:
    """Random everyday customers, each with 3-6 regular payees."""
    fake = Faker("en_IN")
    fake.seed_instance(seed)
    rng = random.Random(seed)
    customers: list[Customer] = []
    payees: dict[str, list[Payee]] = {}
    for i in range(n_customers):
        start = rng.randint(7, 11)
        customer = Customer(
            customer_id=token("c", f"bg-{seed}-{i}"),
            display_name=fake.name(),
            age=rng.randint(21, 75),
            city=fake.city(),
            language=rng.choice(["en", "hi", "mr", "ta", "te", "bn"]),
            balance_inr=float(rng.randrange(20_000, 1_500_000, 1_000)),
            active_from_hour=start,
            active_to_hour=rng.randint(start + 8, 23),
        )
        customers.append(customer)
        categories = rng.sample(list(CATEGORY_HABITS), k=rng.randint(3, 6))
        payees[customer.customer_id] = [
            Payee(
                payee_id=token("p", f"bg-{seed}-{i}-{cat}"),
                display_name=fake.name() if cat in ("family", "rent") else fake.company(),
                category=cat,
                account_age_days=rng.randint(180, 5_000),
            )
            for cat in categories
        ]
    return customers, payees


# ---------- Payment history ----------

def make_history(
    customer: Customer, payees: list[Payee], end: datetime, rng: random.Random
) -> list[dict]:
    """Normal payments over the last HISTORY_DAYS, inside the customer's usual hours."""
    events: list[tuple[datetime, Payee, float]] = []
    start = end - timedelta(days=HISTORY_DAYS)
    for payee in payees:
        low, high, per_month = CATEGORY_HABITS[payee.category]
        count = max(1, round(per_month * HISTORY_DAYS / 30 * rng.uniform(0.7, 1.3)))
        for _ in range(count):
            day = start + timedelta(days=rng.uniform(0, HISTORY_DAYS))
            local = day.astimezone(IST).replace(
                hour=rng.randint(customer.active_from_hour, customer.active_to_hour),
                minute=rng.randint(0, 59),
            )
            ts = local.astimezone(UTC)
            if ts > end:  # setting the hour can push today's payment into the future
                ts -= timedelta(days=1)
            amount = round(rng.uniform(low, high), 2)
            events.append((ts, payee, amount))

    events.sort(key=lambda e: e[0])
    # Walk balance forward so balance_before is consistent and ends at today's balance.
    balance = customer.balance_inr + sum(amount for _, _, amount in events)
    rows = []
    for ts, payee, amount in events:
        rows.append({
            "txn_id": f"t_{rng.getrandbits(64):016x}",
            "customer_id": customer.customer_id,
            "payee_id": payee.payee_id,
            "amount_inr": amount,
            "ts": ts,
            "balance_before_inr": round(balance, 2),
        })
        balance -= amount
    return rows


@dataclass(frozen=True)
class SyntheticData:
    customers: pd.DataFrame
    payees: pd.DataFrame
    transactions: pd.DataFrame
    scenarios: pd.DataFrame


def build_all(n_background: int = 50, seed: int = 42, end: datetime | None = None) -> SyntheticData:
    """Everything the demo needs, as DataFrames ready to load."""
    end = end or datetime.now(UTC)
    rng = random.Random(seed)

    bg_customers, bg_payees = make_background(n_background, seed)
    customers = list(DEMO_CUSTOMERS.values()) + bg_customers
    payees_by_customer = {
        **{DEMO_CUSTOMERS[k].customer_id: v for k, v in DEMO_REGULAR_PAYEES.items()},
        **bg_payees,
    }

    transactions = [
        row
        for customer in customers
        for row in make_history(customer, payees_by_customer[customer.customer_id], end, rng)
    ]
    all_payees = [p for ps in payees_by_customer.values() for p in ps]
    all_payees += list(DEMO_NEW_PAYEES.values())

    return SyntheticData(
        customers=pd.DataFrame([asdict(c) for c in customers]),
        payees=pd.DataFrame([asdict(p) for p in all_payees]).drop_duplicates("payee_id"),
        transactions=pd.DataFrame(transactions),
        scenarios=pd.DataFrame([asdict(s) for s in demo_scenarios()]),
    )
