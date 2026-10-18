"""Delete all rows from the `decisions` log (e.g. before a live demo). Asks to confirm.

Usage: python -m scripts.reset_decisions
"""

from scam_shield.bq import get_client
from scam_shield.settings import get_settings


def main() -> None:
    settings = get_settings()
    table = settings.table("decisions")
    if input(f"Delete ALL rows from {table}? Type 'yes': ").strip() != "yes":
        print("Cancelled.")
        return
    get_client(settings).query_and_wait(f"TRUNCATE TABLE `{table}`")
    print("Done. The dashboard is empty.")


if __name__ == "__main__":
    main()
