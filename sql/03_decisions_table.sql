-- Every decision the API makes. Feeds the bank dashboard.
-- One row per step: stage = 'money' (after /check-payment) or 'final' (after /context).
CREATE TABLE IF NOT EXISTS `${dataset}.decisions` (
  check_id STRING NOT NULL,
  ts TIMESTAMP NOT NULL,
  stage STRING NOT NULL,
  customer_id STRING NOT NULL,
  payee_id STRING NOT NULL,
  amount_inr FLOAT64 NOT NULL,
  hour_ist INT64 NOT NULL,
  decision STRING NOT NULL,
  money_score FLOAT64 NOT NULL,
  money_reasons ARRAY<STRING>,
  context_score FLOAT64,
  combined_score FLOAT64,
  scam_type STRING,
  red_flags ARRAY<STRING>,
  context_source STRING
)
PARTITION BY DATE(ts);
