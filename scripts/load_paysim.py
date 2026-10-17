"""Load the PaySim CSV into BigQuery table `paysim_raw`.

Usage: python -m scripts.load_paysim [path/to/paysim.csv]
"""

import sys
from pathlib import Path

from google.cloud import bigquery

from scam_shield.bq import ensure_dataset, get_client
from scam_shield.settings import get_settings

DEFAULT_CSV = Path("data/paysim.csv")
TABLE = "paysim_raw"

SCHEMA = [
    bigquery.SchemaField("step", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("amount", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("nameOrig", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("oldbalanceOrg", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("newbalanceOrig", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("nameDest", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("oldbalanceDest", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("newbalanceDest", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("isFraud", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("isFlaggedFraud", "INT64", mode="REQUIRED"),
]


def main(csv_path: Path) -> None:
    if not csv_path.is_file():
        sys.exit(f"CSV not found: {csv_path}")

    settings = get_settings()
    client = get_client(settings)
    ensure_dataset(client, settings)

    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    table_id = settings.table(TABLE)
    print(f"Uploading {csv_path} ({csv_path.stat().st_size / 1e6:.0f} MB) to {TABLE} ...")
    with csv_path.open("rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)
    job.result()
    print(f"Loaded {job.output_rows:,} rows into {TABLE}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV)
