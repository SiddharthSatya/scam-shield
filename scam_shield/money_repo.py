"""BigQuery lookup for the money check: customer profile, payee facts and model probability.

One query gets everything. If the model part fails, we retry without it, so the
money check still works on rules alone.
"""

import logging
from dataclasses import dataclass

from google.cloud import bigquery

from scam_shield.money import PaymentFacts
from scam_shield.settings import Settings

log = logging.getLogger(__name__)

QUERY_TIMEOUT_S = 10.0

_FACTS_CTE = """
WITH cust AS (
  SELECT customer_id, balance_inr FROM `{ds}.customers` WHERE customer_id = @customer_id
),
prof AS (
  SELECT * FROM `{ds}.customer_profile` WHERE customer_id = @customer_id
),
facts AS (
  SELECT
    cust.balance_inr,
    prof.p95_amount_inr,
    prof.usual_from_hour,
    prof.usual_to_hour,
    @payee_id NOT IN UNNEST(IFNULL(prof.known_payees, [])) AS is_new_payee,
    (SELECT account_age_days FROM `{ds}.payees` WHERE payee_id = @payee_id)
      AS payee_account_age_days
  FROM cust LEFT JOIN prof USING (customer_id)
)
"""

FACTS_SQL = _FACTS_CTE + "SELECT *, CAST(NULL AS FLOAT64) AS model_probability FROM facts"

# Features must match sql/01_train_money_model.sql exactly.
FACTS_WITH_MODEL_SQL = _FACTS_CTE + """
SELECT
  facts.*,
  (SELECT p.prob FROM UNNEST(pred.predicted_is_fraud_probs) AS p WHERE p.label = 1)
    AS model_probability
FROM facts
CROSS JOIN ML.PREDICT(
  MODEL `{ds}.money_model`,
  (
    SELECT
      @amount AS amount,
      IF(balance_inr > 0, LEAST(@amount / balance_inr, 10), NULL) AS share_of_balance,
      CAST(balance_inr > 0 AND @amount >= balance_inr AS INT64) AS drains_account,
      @hour AS hour_of_day
    FROM facts
  )
) AS pred
"""


class CustomerNotFound(LookupError):
    pass


@dataclass(frozen=True)
class MoneyInputs:
    facts: PaymentFacts
    model_probability: float | None


def fetch_money_inputs(
    client: bigquery.Client,
    settings: Settings,
    customer_id: str,
    payee_id: str,
    amount_inr: float,
    hour_ist: int,
) -> MoneyInputs:
    params = [
        bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id),
        bigquery.ScalarQueryParameter("payee_id", "STRING", payee_id),
        bigquery.ScalarQueryParameter("amount", "FLOAT64", amount_inr),
        bigquery.ScalarQueryParameter("hour", "INT64", hour_ist),
    ]
    ds = f"{settings.gcp_project}.{settings.bq_dataset}"
    try:
        row = _query_one(client, FACTS_WITH_MODEL_SQL.format(ds=ds), params)
    except Exception:
        log.exception("Money model query failed; retrying with rules only")
        row = _query_one(client, FACTS_SQL.format(ds=ds), params)

    if row is None or row["balance_inr"] is None:
        raise CustomerNotFound(customer_id)

    facts = PaymentFacts(
        amount_inr=amount_inr,
        balance_inr=row["balance_inr"],
        hour_ist=hour_ist,
        is_new_payee=row["is_new_payee"],
        payee_account_age_days=row["payee_account_age_days"],
        p95_amount_inr=row["p95_amount_inr"],
        usual_from_hour=row["usual_from_hour"],
        usual_to_hour=row["usual_to_hour"],
    )
    return MoneyInputs(facts=facts, model_probability=row["model_probability"])


def _query_one(
    client: bigquery.Client, sql: str, params: list[bigquery.ScalarQueryParameter]
) -> bigquery.Row | None:
    rows = client.query_and_wait(
        sql,
        job_config=bigquery.QueryJobConfig(query_parameters=params),
        wait_timeout=QUERY_TIMEOUT_S,
    )
    return next(iter(rows), None)
