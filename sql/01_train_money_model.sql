-- Money model: BigQuery ML logistic regression trained on PaySim transfers.
--
-- Why logistic regression (not boosted trees): PaySim fraud almost always sends EXACTLY
-- the full balance (98% of frauds, 0 normal payments). Boosted trees memorised that
-- simulator quirk and learned nothing else. A linear model on coarse features cannot.
--
-- Features (must match scam_shield/money_repo.py):
--   share_band: share of balance sent, capped at 1 and rounded to 0.1
--               (so "exactly 100%" can't be told apart from "over 95%")
--   is_night:   payment between midnight and 6 AM (29% of fraud vs 1% of normal)
-- Left out: raw amount (PaySim units are not INR) and drains_account (the leak).
-- Rows with zero starting balance are left out: a bank always knows the balance.
-- Honest evaluation: train on days 1-25, test on days 26-31 (time split).
-- No class weights: we want calibrated probabilities, because the money score uses the
-- model as a booster (a weighted model says ~0.5 for every daytime payment).
-- Note: BigQuery's reported roc_auc is unreliable here (only 22 distinct scores, many ties);
-- compute AUC from ML.ROC_CURVE instead (see scripts/eval_money_model.py).
CREATE OR REPLACE MODEL `${dataset}.money_model`
OPTIONS (
  model_type = 'LOGISTIC_REG',
  input_label_cols = ['is_fraud'],
  data_split_method = 'CUSTOM',
  data_split_col = 'is_eval',
  enable_global_explain = TRUE
) AS
SELECT
  ROUND(LEAST(amount / oldbalanceOrg, 1), 1) AS share_band,
  CAST(MOD(step, 24) BETWEEN 0 AND 6 AS INT64) AS is_night,
  isFraud AS is_fraud,
  step > 600 AS is_eval
FROM `${dataset}.paysim_raw`
WHERE type IN ('TRANSFER', 'CASH_OUT')
  AND oldbalanceOrg > 0;
