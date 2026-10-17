"""Honest evaluation of money_model on the held-out days (time split).

Prints weights, AUC computed from ML.ROC_CURVE (BigQuery's roc_auc is unreliable when
scores have many ties), and the best operating points.

Usage: python -m scripts.eval_money_model
"""

from scam_shield.bq import get_client
from scam_shield.settings import get_settings


def main() -> None:
    settings = get_settings()
    client = get_client(settings)
    model = f"`{settings.table('money_model')}`"

    print("Weights:")
    for row in client.query_and_wait(f"SELECT * FROM ML.WEIGHTS(MODEL {model})"):
        print(f"  {row['processed_input']:15} {row['weight']:+.3f}")

    auc_sql = f"""
    WITH c AS (
      SELECT false_positive_rate AS fpr, recall AS tpr FROM ML.ROC_CURVE(MODEL {model})
      UNION ALL SELECT 0, 0 UNION ALL SELECT 1, 1
    ),
    o AS (
      SELECT fpr, tpr, LAG(fpr) OVER w AS pf, LAG(tpr) OVER w AS pt
      FROM c WINDOW w AS (ORDER BY fpr, tpr)
    )
    SELECT SUM((fpr - pf) * (tpr + pt) / 2) AS auc FROM o WHERE pf IS NOT NULL
    """
    auc = next(iter(client.query_and_wait(auc_sql)))["auc"]
    print(f"AUC on unseen days (from ROC curve): {auc:.3f}")

    print("Operating points (threshold: catches / false alarms):")
    roc_sql = f"""
    SELECT threshold, recall, false_positive_rate FROM ML.ROC_CURVE(MODEL {model})
    WHERE false_positive_rate < 0.05 ORDER BY threshold DESC LIMIT 5
    """
    for row in client.query_and_wait(roc_sql):
        print(f"  {row['threshold']:.3f}: {row['recall']:.0%} of fraud / "
              f"{row['false_positive_rate']:.2%} of normal")


if __name__ == "__main__":
    main()
