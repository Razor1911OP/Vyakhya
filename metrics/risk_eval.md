# Vyakhya risk engine evaluation

> **All metrics come from synthetic and public datasets (UCI SMS Spam, Vyakhya synthetic messages, PaySim). They are not production accuracy.**

Model version `risk-0.2.0`, seed 42. Hand-written test set SHA-256 `9a1ade6b9f9b01e5…`, rules `5e626a57a3b92c7d…`.

Two fusion systems: **spec_baseline** = `max(hard_floor, blend(text, txn))`; **with_rule_score** (shipped) = `max(hard_floor, blend(text, txn, rule_prob))`. Hard-rule floors override both. Bands: medium ≈ 5% benign FPR (warn and ask the user to verify, never a block), high ≈ 1% benign FPR or any hard-rule hit, All cutoffs come from synthetic validation folds: **tuned on synthetic data, re-calibrate at pilot**. This version is shipped and frozen.

Rules version **v2**: Direction fix: 'प्राप्त हुए', 'mile hain', 'credit ho jayega', 'received from' no longer count as money-in by themselves; they need the user named as recipient or a non-user sender in the same sentence. Found via a benign Hindi bill-receipt template (merchant_bill_hi_07) hitting the amount-mismatch floor; because it was found by looking at evaluation failures, the separate validation set is the cleaner check that it generalises. Measured effect on synthetic data: benign hard-floor hits 6 -> 0 (all merchant_bill_hi_07); scam hard-floor hits unchanged (231); digital_arrest_hien_01 loses reward_claim on 10 rows ('drugs mile hain' = 'drugs were found', which v1 misread as money-in).

## Known weak spots (read first)

- **Weakest scam family: `job_task`.** Unseen-family recall @1% FPR 0.135 for the shipped system vs 0.365 for spec_baseline. The mean over families hides this; do not quote the mean without it.
- **Hand-written flagged FPR:** shipped 0.276 (95% CI (0.1775, 0.402)) vs spec_baseline 0.241 (95% CI (0.1496, 0.3653)): no worse: the flagged-FPR difference is within the 95% intervals, so the evidence does not show an improvement.
- All band cutoffs are tuned on synthetic data, re-calibrate at pilot. On the hand-written set the realistic benign FPR is far above the 5%/1% design targets (see section 5).

## 1. Leave-one-family-out (synthetic + UCI; nested thresholds)

| Held-out | Scam n | Benign n | spec_baseline: recall@1%FPR | flagged recall | flagged FPR | high FPR | with_rule_score: recall@1%FPR | flagged recall | flagged FPR | high FPR | Deck baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kyc_refund | 200 | 1031 | 0.700 | 0.600 | 0.004 | 0.000 | 0.930 | 0.825 | 0.005 | 0.000 | 0.84 |
| digital_arrest | 200 | 981 | 0.685 | 0.715 | 0.012 | 0.004 | 0.950 | 0.815 | 0.004 | 0.002 | 0.77 |
| lottery | 200 | 1027 | 0.660 | 0.740 | 0.018 | 0.002 | 0.965 | 0.960 | 0.014 | 0.001 | 0.68 |
| upi_collect | 200 | 1071 | 0.940 | 0.935 | 0.009 | 0.003 | 1.000 | 1.000 | 0.012 | 0.002 | 0.43 |
| job_task | 200 | 984 | 0.365 | 0.680 | 0.038 | 0.010 | 0.135 | 0.475 | 0.048 | 0.029 | 0.26 |
| generic_spam | 747 | 853 | 0.248 | 0.003 | 0.000 | 0.000 | 0.333 | 0.126 | 0.004 | 0.001 | n/a |

Mean unseen-family recall @1% FPR (5 synthetic families): **spec_baseline** 0.67, **with_rule_score** 0.796 (deck text-only baseline 0.60, target 0.80).
Weights per fold (text, txn, rule): spec_baseline: kyc_refund=(0.55, 0.45, 0.0), digital_arrest=(0.25, 0.75, 0.0), lottery=(0.25, 0.75, 0.0), upi_collect=(0.25, 0.75, 0.0), job_task=(0.6, 0.4, 0.0), generic_spam=(0.25, 0.75, 0.0); with_rule_score: kyc_refund=(0.45, 0.3, 0.25), digital_arrest=(0.2, 0.25, 0.55), lottery=(0.3, 0.35, 0.35), upi_collect=(0.3, 0.35, 0.35), job_task=(0.4, 0.2, 0.4), generic_spam=(0.35, 0.25, 0.4)

> rule_score was written while looking at the same synthetic templates, so its contribution on these folds is optimistic. Judge it on the hand-written set (section 5).

## 2. Ablation (recall @1% FPR per held-out fold)

| Variant | kyc_refund | digital_arrest | lottery | upi_collect | job_task | generic_spam | Mean (5 synthetic) | Synthetic AUC |
|---|---|---|---|---|---|---|---|---|
| text only | 0.235 | 0.735 | 0.405 | 0.535 | 0.115 | 0.248 | 0.405 | 0.825 |
| rules only | 0.820 | 0.120 | 0.825 | 1.000 | 0.120 | 0.123 | 0.577 | 0.830 |
| transaction only | 0.455 | 0.385 | 0.415 | 0.465 | 0.325 | n/a | 0.409 | 0.872 |
| text + rules (spec formula) | 0.445 | 0.735 | 0.425 | 0.910 | 0.115 | 0.248 | 0.526 | 0.860 |
| all, spec formula (baseline) | 0.700 | 0.685 | 0.660 | 0.940 | 0.365 | 0.248 | 0.670 | 0.936 |
| all + rule_score (shipped) | 0.930 | 0.950 | 0.965 | 1.000 | 0.135 | 0.333 | 0.796 | 0.957 |

*rules only* = weighted flag sum with hard floor. Transaction-only is n/a on `generic_spam` (no paired payment).

## 3. Bands: counts and precision (LOFO scores)

Precision depends on the scam share of the data (synthetic here is ~47% scam). The last column re-weights to an assumed 1% scam prevalence. Benign counts are small; treat FPR and precision as rough.

| System | Population | Band | Benign n | Scam n | Precision | Share of scams | Share of benign | Precision @1% prevalence |
|---|---|---|---|---|---|---|---|---|
| spec_baseline | synthetic (message + payment) | low | 1053 | 266 | 0.202 | 0.266 | 0.940 | n/a |
| spec_baseline | synthetic (message + payment) | medium | 50 | 157 | 0.758 | 0.157 | 0.045 | 0.034 |
| spec_baseline | synthetic (message + payment) | high | 17 | 577 | 0.971 | 0.577 | 0.015 | 0.277 |
| spec_baseline | UCI (message only) | low | 4813 | 745 | 0.134 | 0.997 | 0.997 | n/a |
| spec_baseline | UCI (message only) | medium | 12 | 2 | 0.143 | 0.003 | 0.003 | 0.011 |
| spec_baseline | UCI (message only) | high | 2 | 0 | 0.000 | 0.000 | 0.000 | 0.000 |
| with_rule_score | synthetic (message + payment) | low | 1053 | 185 | 0.149 | 0.185 | 0.940 | n/a |
| with_rule_score | synthetic (message + payment) | medium | 40 | 153 | 0.793 | 0.153 | 0.036 | 0.042 |
| with_rule_score | synthetic (message + payment) | high | 27 | 662 | 0.961 | 0.662 | 0.024 | 0.217 |
| with_rule_score | UCI (message only) | low | 4808 | 653 | 0.120 | 0.874 | 0.996 | n/a |
| with_rule_score | UCI (message only) | medium | 12 | 42 | 0.778 | 0.056 | 0.003 | 0.186 |
| with_rule_score | UCI (message only) | high | 7 | 52 | 0.881 | 0.070 | 0.002 | 0.327 |

## 4. Hard negatives (synthetic + UCI benign that look like scams; LOFO)

| Group | n | Templates | spec_baseline flagged (FPR, 95% CI) | spec_baseline high | with_rule_score flagged (FPR, 95% CI) | with_rule_score high | Hard-floor hits | Text-only FPR @0.5 |
|---|---|---|---|---|---|---|---|---|
| OTP notices | 200 | 24 | 17 (0.085, 0.0537–0.1319) | 7 | 23 (0.115, 0.0779–0.1666) | 16 | 0 | 0.415 |
| Debit/credit alerts | 196 | 24 | 21 (0.107, 0.0712–0.1582) | 3 | 6 (0.031, 0.0141–0.0652) | 1 | 0 | 0.423 |
| Genuine KYC reminders | 24 | 3 | 0 (0.000, 0.0–0.138) | 0 | 0 (0.000, 0.0–0.138) | 0 | 0 | 0.000 |
| Bill reminders / receipts | 200 | 24 | 8 (0.040, 0.0204–0.0769) | 2 | 4 (0.020, 0.0078–0.0503) | 0 | 0 | 0.340 |
| Delivery updates | 200 | 24 | 13 (0.065, 0.0384–0.108) | 3 | 25 (0.125, 0.0861–0.178) | 9 | 0 | 0.115 |
| Genuine refunds | 100 | 6 | 3 (0.030, 0.0103–0.0845) | 1 | 7 (0.070, 0.0343–0.1375) | 1 | 0 | 0.190 |
| UCI everyday SMS (ham) | 4827 | 4517 | 14 (0.003, 0.0017–0.0049) | 2 | 19 (0.004, 0.0025–0.0061) | 7 | 0 | 0.004 |

## 5. Hand-written test set (120 messages: 62 scam, 58 benign)

Message-only mode (transaction model not used); amounts/direction feed the rule mismatch check. Written by the assistant before the v2 templates; not independent of the rule author.

Overlap with training text: exact duplicates 0, max char-5-gram Jaccard 0.358 (mean of per-message max 0.121); messages ≥ 0.5: none.

AUC: text only 0.885, rules only 0.781, spec_baseline 0.886, with_rule_score 0.912.

Rows: system × cutoff source. *synthetic-fold cutoffs* = message-only bands from synthetic validation folds; *validation cutoffs* = message-only bands from `validation_benign.csv` (shipped).

| System | Rules | Flagged recall (95% CI) | Flagged FPR (95% CI) | High recall | High FPR (95% CI) | Accuracy |
|---|---|---|---|---|---|---|
| spec_baseline | synthetic-fold cutoffs | v2 | 0.790 (0.6736–0.8732) | 0.241 (0.1496–0.3653) | 0.629 | 0.103 (0.0483–0.2079) | 0.775 |
| with_rule_score | synthetic-fold cutoffs | v2 | 0.887 (0.7848–0.9442) | 0.276 (0.1775–0.402) | 0.613 | 0.052 (0.0177–0.1414) | 0.808 |
| spec_baseline \| synthetic-fold cutoffs (archived run) | v1 | 0.790 | 0.241 (0.1496–0.3653) | 0.597 | 0.103 | 0.775 |
| with_rule_score \| synthetic-fold cutoffs (archived run) | v1 | 0.903 | 0.259 (0.1635–0.3838) | 0.629 | 0.052 | 0.825 |

Rule-change comparison: compare *rules v1 (archived run)* with *rules v2 | synthetic-fold cutoffs* (same cutoff policy). The v2 fix was found by looking at evaluation failures, so the validation-set results (section 5b) are the cleaner check that it generalises.

| System | Band | Benign n | Scam n | Precision | Precision @1% prevalence |
|---|---|---|---|---|---|
| spec_baseline | synthetic-fold cutoffs | low | 44 | 13 | 0.228 | n/a |
| spec_baseline | synthetic-fold cutoffs | medium | 8 | 10 | 0.556 | 0.012 |
| spec_baseline | synthetic-fold cutoffs | high | 6 | 39 | 0.867 | 0.058 |
| with_rule_score | synthetic-fold cutoffs | low | 42 | 7 | 0.143 | n/a |
| with_rule_score | synthetic-fold cutoffs | medium | 13 | 17 | 0.567 | 0.012 |
| with_rule_score | synthetic-fold cutoffs | high | 3 | 38 | 0.927 | 0.107 |

Per scam family (flagged recall / high recall):

| Family | n | spec_baseline | synthetic-fold cutoffs | with_rule_score | synthetic-fold cutoffs |
|---|---|---|---|
| digital_arrest | 11 | 0.909 / 0.636 | 0.909 / 0.545 |
| job_task | 11 | 0.727 / 0.636 | 0.727 / 0.273 |
| kyc_refund | 12 | 0.667 / 0.583 | 1.000 / 0.833 |
| lottery | 11 | 1.000 / 0.909 | 0.909 / 0.909 |
| other | 6 | 0.167 / 0.167 | 0.833 / 0.167 |
| upi_collect | 11 | 1.000 / 0.636 | 0.909 / 0.727 |

Per benign group (flagged / high, out of n):

| Group | n | spec_baseline | synthetic-fold cutoffs | with_rule_score | synthetic-fold cutoffs |
|---|---|---|---|
| advisory | 4 | 0 / 0 | 0 / 0 |
| bank_alert | 14 | 2 / 1 | 5 / 0 |
| bill | 10 | 6 / 3 | 4 / 2 |
| delivery | 8 | 0 / 0 | 2 / 1 |
| family | 8 | 3 / 1 | 2 / 0 |
| merchant | 4 | 2 / 0 | 2 / 0 |
| otp_notice | 10 | 1 / 1 | 1 / 0 |

Per language (flagged recall / flagged FPR):

| Language | Scam n | Benign n | spec_baseline | synthetic-fold cutoffs | with_rule_score | synthetic-fold cutoffs |
|---|---|---|---|---|
| en | 31 | 33 | 0.710 / 0.242 | 0.806 / 0.303 |
| hi-en | 17 | 14 | 0.765 / 0.214 | 0.941 / 0.214 |
| hi | 14 | 11 | 1.000 / 0.273 | 1.000 / 0.273 |

Flagged benign ids (shipped): hw108, hw114, hw116, hw122, hw123, hw124, hw129, hw135, hw136, hw137, hw139, hw141, hw148, hw149, hw155, hw158.
Missed scam ids (shipped, band low): hw014, hw029, hw043, hw046, hw053, hw055, hw057.

## 5b. Validation set for cutoffs

Not used in this version (decision 2026-10-25). All cutoffs are tuned on synthetic data, re-calibrate at pilot.

## 6. Optional text-model comparison (COMPARE_MODELS, not shipped)

- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: **not evaluated** (skipped by decision; not installed or run). No result is claimed for it. TF-IDF char n-grams + logistic regression remains the text baseline.

## 7. Transaction model: public synthetic mobile-money data (PaySim), not UPI

Features: amount, type, hour, beneficiary_prior_txns, beneficiary_first_seen. Split: fit step<400, calibrate 400-499, test step>=500. Test ROC-AUC 0.9298, PR-AUC 0.6162 (test prevalence 0.0208), recall @1% FPR 0.5831, @0.1% FPR 0.3553.

## 8. Caveats

- Synthetic messages come from a template set (8 per scam family and language; 8–9 per language for the main hard-negative groups). Unseen-family numbers measure transfer between our own templates, not real-world scams.
- rule_score and the rules were written while looking at the synthetic templates; the hand-written set was written by the same assistant before the v2 templates were added. Neither is an independent test; a set written by someone else would be.
- Payee-history values for synthetic payments are a documented generator assumption (jobs/export_training_tables.py).
- UCI SMS Spam is English, UK, mid-2000s; it adds generic spam vocabulary, not Indian UPI scams.
- The UPI 2024 and Indian banking CSVs were profiled and excluded: no learnable label signal (ROC-AUC 0.48 and 0.53 on time splits). See metrics/txn_signal_probe_*.json.
- Cutoffs: tuned on synthetic data, re-calibrate at pilot.
