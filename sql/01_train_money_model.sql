-- Money model: BigQuery ML boosted tree trained on PaySim transfers.
-- Features are chosen so they also exist for a live bank payment:
--   amount, share of balance sent, whether it empties the account, hour of day.
-- Destination-balance columns are left out: a bank does not know them and they leak the label.
-- Negatives are downsampled to 10% (deterministic) to speed up training on a 0.3% fraud rate.
CREATE OR REPLACE MODEL `${dataset}.money_model`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['is_fraud'],
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  max_iterations = 50,
  early_stop = TRUE,
  enable_global_explain = TRUE
) AS
WITH base AS (
  SELECT
    amount,
    IF(oldbalanceOrg > 0, LEAST(amount / oldbalanceOrg, 10), NULL) AS share_of_balance,
    CAST(oldbalanceOrg > 0 AND amount >= oldbalanceOrg AS INT64) AS drains_account,
    MOD(step, 24) AS hour_of_day,
    isFraud AS is_fraud,
    MOD(ABS(FARM_FINGERPRINT(CONCAT(nameOrig, '-', CAST(step AS STRING)))), 10) AS bucket
  FROM `${dataset}.paysim_raw`
  WHERE type IN ('TRANSFER', 'CASH_OUT')
)
SELECT amount, share_of_balance, drains_account, hour_of_day, is_fraud
FROM base
WHERE is_fraud = 1 OR bucket = 0;
