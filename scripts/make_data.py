"""Generate made-up customers, payees, payment history and demo scenarios, and load
them into BigQuery.

Usage: python -m scripts.make_data [--dry-run]
  --dry-run  write CSVs to data/generated/ instead of BigQuery
"""

import argparse
from pathlib import Path

from google.cloud import bigquery

from scam_shield.bq import ensure_dataset, get_client, replace_table
from scam_shield.settings import get_settings
from scam_shield.synthetic import build_all

F = bigquery.SchemaField
SCHEMAS = {
    "customers": [
        F("customer_id", "STRING", mode="REQUIRED"),
        F("display_name", "STRING"),
        F("age", "INT64"),
        F("city", "STRING"),
        F("language", "STRING"),
        F("balance_inr", "FLOAT64"),
        F("active_from_hour", "INT64"),
        F("active_to_hour", "INT64"),
    ],
    "payees": [
        F("payee_id", "STRING", mode="REQUIRED"),
        F("display_name", "STRING"),
        F("category", "STRING"),
        F("account_age_days", "INT64"),
    ],
    "transactions": [
        F("txn_id", "STRING", mode="REQUIRED"),
        F("customer_id", "STRING", mode="REQUIRED"),
        F("payee_id", "STRING", mode="REQUIRED"),
        F("amount_inr", "FLOAT64", mode="REQUIRED"),
        F("ts", "TIMESTAMP", mode="REQUIRED"),
        F("balance_before_inr", "FLOAT64"),
    ],
    "scenarios": [
        F("scenario_id", "STRING", mode="REQUIRED"),
        F("title", "STRING"),
        F("customer_id", "STRING"),
        F("payee_id", "STRING"),
        F("amount_inr", "FLOAT64"),
        F("hour_ist", "INT64"),
        F("expected", "STRING"),
        F("scam_type", "STRING"),
    ],
}


def main(dry_run: bool) -> None:
    data = build_all()
    frames = {
        "customers": data.customers,
        "payees": data.payees,
        "transactions": data.transactions,
        "scenarios": data.scenarios,
    }

    if dry_run:
        out = Path("data/generated")
        out.mkdir(parents=True, exist_ok=True)
        for name, df in frames.items():
            df.to_csv(out / f"{name}.csv", index=False)
            print(f"{name}: {len(df):,} rows -> {out / name}.csv")
        return

    settings = get_settings()
    client = get_client(settings)
    ensure_dataset(client, settings)
    for name, df in frames.items():
        rows = replace_table(client, settings.table(name), df, SCHEMAS[name])
        print(f"{name}: {rows:,} rows loaded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    main(parser.parse_args().dry_run)
