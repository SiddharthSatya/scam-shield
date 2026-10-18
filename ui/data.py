"""BigQuery reads for the UI. Demo setup data is cached; dashboard data is short-lived."""

import pandas as pd
import streamlit as st
from google.cloud import bigquery

from ui.config import get_ui_settings


@st.cache_resource
def bq() -> bigquery.Client:
    s = get_ui_settings()
    return bigquery.Client(project=s.gcp_project, location=s.gcp_region)


def _query(sql: str, params: list | None = None) -> pd.DataFrame:
    config = bigquery.QueryJobConfig(query_parameters=params or [])
    return bq().query_and_wait(sql, job_config=config).to_dataframe()


@st.cache_data(ttl=3600)
def demo_customers() -> pd.DataFrame:
    """The customers that appear in demo scenarios."""
    s = get_ui_settings()
    return _query(f"""
        SELECT c.customer_id, c.display_name, c.age, c.city, c.language, c.balance_inr
        FROM {s.table('customers')} c
        WHERE c.customer_id IN (SELECT customer_id FROM {s.table('scenarios')})
        ORDER BY c.age DESC""")


@st.cache_data(ttl=3600)
def payees_for(customer_id: str) -> pd.DataFrame:
    """Known payees from history first, then new payees from demo scenarios."""
    s = get_ui_settings()
    return _query(f"""
        WITH known AS (
          SELECT DISTINCT payee_id, FALSE AS is_new FROM {s.table('transactions')}
          WHERE customer_id = @cid
        ),
        demo_new AS (
          SELECT payee_id, TRUE AS is_new FROM {s.table('scenarios')}
          WHERE customer_id = @cid AND payee_id NOT IN (SELECT payee_id FROM known)
        )
        SELECT p.payee_id, p.display_name, p.category, x.is_new
        FROM (SELECT * FROM known UNION ALL SELECT * FROM demo_new) x
        JOIN {s.table('payees')} p USING (payee_id)
        ORDER BY x.is_new, p.display_name""",
        [bigquery.ScalarQueryParameter("cid", "STRING", customer_id)])


@st.cache_data(ttl=3600)
def scenarios() -> pd.DataFrame:
    s = get_ui_settings()
    return _query(f"SELECT * FROM {s.table('scenarios')} ORDER BY amount_inr")


@st.cache_data(ttl=8)
def recent_checks(hours: int = 24) -> pd.DataFrame:
    """One row per payment check: money step, final step and customer action combined."""
    s = get_ui_settings()
    return _query(f"""
        WITH d AS (
          SELECT * FROM {s.table('decisions')}
          WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
        ),
        money AS (SELECT * FROM d WHERE stage = 'money'),
        final AS (SELECT * FROM d WHERE stage = 'final'),
        outcome AS (
          SELECT check_id, ARRAY_AGG(decision ORDER BY ts DESC LIMIT 1)[OFFSET(0)] AS action
          FROM d WHERE stage = 'outcome' GROUP BY check_id
        )
        SELECT
          m.check_id, m.ts, c.display_name AS customer, p.display_name AS payee,
          m.amount_inr, m.money_score, m.decision AS money_decision,
          f.decision AS final_decision, f.context_score, f.combined_score, f.scam_type,
          f.red_flags, f.context_source, o.action
        FROM money m
        LEFT JOIN final f USING (check_id)
        LEFT JOIN outcome o USING (check_id)
        LEFT JOIN {s.table('customers')} c ON c.customer_id = m.customer_id
        LEFT JOIN {s.table('payees')} p ON p.payee_id = m.payee_id
        ORDER BY m.ts DESC""",
        [bigquery.ScalarQueryParameter("hours", "INT64", hours)])
