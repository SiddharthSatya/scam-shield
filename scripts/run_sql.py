"""Run a SQL file against BigQuery. `${dataset}` is replaced with project.dataset.

Usage: python -m scripts.run_sql sql/01_train_money_model.sql [more.sql ...]
"""

import sys
from pathlib import Path
from string import Template

from scam_shield.bq import get_client
from scam_shield.settings import get_settings


def render(sql: str) -> str:
    settings = get_settings()
    return Template(sql).substitute(dataset=f"{settings.gcp_project}.{settings.bq_dataset}")


def main(paths: list[str]) -> None:
    if not paths:
        sys.exit(__doc__)
    client = get_client(get_settings())
    for path in paths:
        print(f"Running {path} ...")
        rows = client.query_and_wait(render(Path(path).read_text()))
        for row in list(rows)[:20]:
            print(dict(row))
        print(f"Done: {path}")


if __name__ == "__main__":
    main(sys.argv[1:])
