-- Each customer's "normal": typical amounts, usual hours (IST) and known payees.
CREATE OR REPLACE VIEW `${dataset}.customer_profile` AS
SELECT
  t.customer_id,
  COUNT(*) AS payment_count,
  APPROX_QUANTILES(t.amount_inr, 100)[OFFSET(50)] AS median_amount_inr,
  APPROX_QUANTILES(t.amount_inr, 100)[OFFSET(95)] AS p95_amount_inr,
  MAX(t.amount_inr) AS max_amount_inr,
  MIN(EXTRACT(HOUR FROM t.ts AT TIME ZONE 'Asia/Kolkata')) AS usual_from_hour,
  MAX(EXTRACT(HOUR FROM t.ts AT TIME ZONE 'Asia/Kolkata')) AS usual_to_hour,
  ARRAY_AGG(DISTINCT t.payee_id) AS known_payees,
  MAX(t.ts) AS last_payment_ts
FROM `${dataset}.transactions` AS t
GROUP BY t.customer_id;
