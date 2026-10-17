"""Run the money check on every demo scenario in BigQuery and print the results.

Usage: python -m scripts.score_scenarios
"""

from scam_shield.bq import get_client
from scam_shield.money import money_score
from scam_shield.money_repo import fetch_money_inputs
from scam_shield.settings import get_settings


def main() -> None:
    settings = get_settings()
    client = get_client(settings)
    scenarios = client.query_and_wait(
        f"SELECT * FROM `{settings.table('scenarios')}` ORDER BY scenario_id"
    )
    for s in scenarios:
        inputs = fetch_money_inputs(client, settings, s["customer_id"], s["payee_id"],
                                    s["amount_inr"], s["hour_ist"])
        result = money_score(inputs.facts, inputs.model_probability)
        model = "n/a" if result.model_probability is None else f"{result.model_probability:.2f}"
        print(f"{s['scenario_id']:15} money={result.score:.2f} rules={result.rules_score:.2f} "
              f"model={model}  expected={s['expected']}")
        for reason in result.reasons:
            print(f"{'':17}- {reason}")


if __name__ == "__main__":
    main()
