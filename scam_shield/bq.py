"""Small BigQuery helpers shared by scripts and the API."""

import pandas as pd
from google.cloud import bigquery

from scam_shield.settings import Settings


def get_client(settings: Settings) -> bigquery.Client:
    return bigquery.Client(project=settings.gcp_project, location=settings.gcp_region)


def ensure_dataset(client: bigquery.Client, settings: Settings) -> None:
    """Create the dataset in our region if it does not exist yet."""
    dataset = bigquery.Dataset(f"{settings.gcp_project}.{settings.bq_dataset}")
    dataset.location = settings.gcp_region
    client.create_dataset(dataset, exists_ok=True)


def replace_table(
    client: bigquery.Client,
    table_id: str,
    df: pd.DataFrame,
    schema: list[bigquery.SchemaField],
) -> int:
    """Overwrite a table with a DataFrame. Returns rows loaded."""
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    return job.output_rows or 0
