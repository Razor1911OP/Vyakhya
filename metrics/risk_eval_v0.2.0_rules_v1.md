# Vyakhya risk engine evaluation

> **All metrics come from synthetic and public datasets (UCI SMS Spam, Vyakhya synthetic messages, PaySim). They are not production accuracy.**

Model version `risk-0.2.0`, seed 42. Hand-written test set SHA-256 `9a1ade6b9f9b01e5…`, rules `0b87c4b90dfcb208…`.

Two fusion systems: **spec_baseline** = `max(hard_floor, blend(text, txn))`; **with_rule_score** (shipped) = `max(hard_floor, blend(text, txn, rule_prob))`. Hard-rule floors override both. Bands: medium ≈ 5% benign FPR (warn and ask the user to verify, never a block), high ≈ 1% benign FPR or any hard-rule hit, chosen per signal mode on validation folds.

## 1. Leave-one-family-out (synthetic + UCI; nested thresholds)

| Held-out | Scam n | Benign n | spec_baseline: recall@1%FPR | flagged recall | flagged FPR | high FPR | with_rule_score: recall@1%FPR | flagged recall | flagged FPR | high FPR | Deck baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| kyc_refund | 200 | 1031 | 0.675 | 0.630 | 0.003 | 0.000 | 0.925 | 0.830 | 0.004 | 0.001 | 0.84 |
| digital_arrest | 200 | 981 | 0.520 | 0.715 | 0.018 | 0.010 | 0.775 | 0.845 | 0.010 | 0.008 | 0.77 |
| lottery | 200 | 1027 | 0.565 | 0.505 | 0.009 | 0.006 | 0.915 | 0.920 | 0.034 | 0.001 | 0.68 |
| upi_collect | 200 | 1071 | 0.935 | 0.930 | 0.006 | 0.002 | 1.000 | 1.000 | 0.021 | 0.000 | 0.43 |
| job_task | 200 | 984 | 0.365 | 0.630 | 0.027 | 0.003 | 0.120 | 0.415 | 0.045 | 0.024 | 0.26 |
| generic_spam | 747 | 853 | 0.248 | 0.003 | 0.000 | 0.000 | 0.355 | 0.126 | 0.004 | 0.000 | n/a |

Mean unseen-family recall @1% FPR (5 synthetic families): **spec_baseline** 0.612, **with_rule_score** 0.747 (deck text-only baseline 0.60, target 0.80).
Weights per fold (text, txn, rule): spec_baseline: kyc_refund=(0.35, 0.65, 0.0), digital_arrest=(0.25, 0.75, 0.0), lottery=(0.9, 0.1, 0.0), upi_collect=(0.1, 0.9, 0.0), job_task=(0.6, 0.4, 0.0), generic_spam=(0.15, 0.85, 0.0); with_rule_score: kyc_refund=(0.3, 0.4, 0.3), digital_arrest=(0.2, 0.25, 0.55), lottery=(0.1, 0.3, 0.6), upi_collect=(0.1, 0.35, 0.55), job_task=(0.4, 0.15, 0.45), generic_spam=(0.35, 0.3, 0.35)

> rule_score was written while looking at the same synthetic templates, so its contribution on these folds is optimistic. Judge it on the hand-written set (section 5).

## 2. Ablation (recall @1% FPR per held-out fold)

| Variant | kyc_refund | digital_arrest | lottery | upi_collect | job_task | generic_spam | Mean (5 synthetic) | Synthetic AUC |
|---|---|---|---|---|---|---|---|---|
| text only | 0.235 | 0.735 | 0.405 | 0.535 | 0.115 | 0.248 | 0.405 | 0.825 |
| rules only | 0.820 | 0.170 | 0.825 | 1.000 | 0.120 | 0.123 | 0.587 | 0.828 |
| transaction only | 0.455 | 0.385 | 0.415 | 0.465 | 0.325 | n/a | 0.409 | 0.872 |
| text + rules (spec formula) | 0.445 | 0.615 | 0.425 | 0.910 | 0.115 | 0.248 | 0.502 | 0.856 |
| all, spec formula (baseline) | 0.675 | 0.520 | 0.565 | 0.935 | 0.365 | 0.248 | 0.612 | 0.928 |
| all + rule_score (shipped) | 0.925 | 0.775 | 0.915 | 1.000 | 0.120 | 0.355 | 0.747 | 0.952 |

*rules only* = weighted flag sum with hard floor. Transaction-only is n/a on `generic_spam` (no paired payment).

## 3. Bands: counts and precision (LOFO scores)

Precision depends on the scam share of the data (synthetic here is ~47% scam). The last column re-weights to an assumed 1% scam prevalence. Benign counts are small; treat FPR and precision as rough.

| System | Population | Band | Benign n | Scam n | Precision | Share of scams | Share of benign | Precision @1% prevalence |
|---|---|---|---|---|---|---|---|---|
| spec_baseline | synthetic (message + payment) | low | 1070 | 318 | 0.229 | 0.318 | 0.955 | n/a |
| spec_baseline | synthetic (message + payment) | medium | 31 | 203 | 0.868 | 0.203 | 0.028 | 0.069 |
| spec_baseline | synthetic (message + payment) | high | 19 | 479 | 0.962 | 0.479 | 0.017 | 0.222 |
| spec_baseline | UCI (message only) | low | 4813 | 745 | 0.134 | 0.997 | 0.997 | n/a |
| spec_baseline | UCI (message only) | medium | 12 | 2 | 0.143 | 0.003 | 0.003 | 0.011 |
| spec_baseline | UCI (message only) | high | 2 | 0 | 0.000 | 0.000 | 0.000 | 0.000 |
| with_rule_score | synthetic (message + payment) | low | 1050 | 198 | 0.159 | 0.198 | 0.938 | n/a |
| with_rule_score | synthetic (message + payment) | medium | 42 | 171 | 0.803 | 0.171 | 0.037 | 0.044 |
| with_rule_score | synthetic (message + payment) | high | 28 | 631 | 0.958 | 0.631 | 0.025 | 0.203 |
| with_rule_score | UCI (message only) | low | 4779 | 653 | 0.120 | 0.874 | 0.990 | n/a |
| with_rule_score | UCI (message only) | medium | 42 | 51 | 0.548 | 0.068 | 0.009 | 0.073 |
| with_rule_score | UCI (message only) | high | 6 | 43 | 0.878 | 0.058 | 0.001 | 0.319 |

## 4. Hard negatives (synthetic + UCI benign that look like scams; LOFO)

| Group | n | Templates | spec_baseline flagged (FPR, 95% CI) | spec_baseline high | with_rule_score flagged (FPR, 95% CI) | with_rule_score high | Hard-floor hits | Text-only FPR @0.5 |
|---|---|---|---|---|---|---|---|---|
| OTP notices | 200 | 24 | 12 (0.060, 0.0347–0.1019) | 3 | 18 (0.090, 0.0577–0.1378) | 15 | 0 | 0.415 |
| Debit/credit alerts | 196 | 24 | 11 (0.056, 0.0316–0.0977) | 2 | 3 (0.015, 0.0052–0.044) | 0 | 0 | 0.423 |
| Genuine KYC reminders | 24 | 3 | 0 (0.000, 0.0–0.138) | 0 | 0 (0.000, 0.0–0.138) | 0 | 0 | 0.000 |
| Bill reminders / receipts | 200 | 24 | 17 (0.085, 0.0537–0.1319) | 12 | 7 (0.035, 0.0171–0.0705) | 6 | 6 | 0.340 |
| Delivery updates | 200 | 24 | 8 (0.040, 0.0204–0.0769) | 1 | 31 (0.155, 0.1114–0.2116) | 6 | 0 | 0.115 |
| Genuine refunds | 100 | 6 | 0 (0.000, 0.0–0.037) | 0 | 9 (0.090, 0.0481–0.1623) | 1 | 0 | 0.190 |
| UCI everyday SMS (ham) | 4827 | 4517 | 14 (0.003, 0.0017–0.0049) | 2 | 48 (0.010, 0.0075–0.0132) | 6 | 0 | 0.004 |

## 5. Hand-written test set (120 messages: 62 scam, 58 benign)

Message-only mode (transaction model not used); amounts/direction feed the rule mismatch check. Written by the assistant before the v2 templates; not independent of the rule author.

Overlap with training text: exact duplicates 0, max char-5-gram Jaccard 0.358 (mean of per-message max 0.118); messages ≥ 0.5: none.

AUC: text only 0.885, rules only 0.781, spec_baseline 0.886, with_rule_score 0.915.

| System | Flagged recall | Flagged FPR (95% CI) | High recall | High FPR | Accuracy |
|---|---|---|---|---|---|
| spec_baseline | 0.790 | 0.241 (0.1496–0.3653) | 0.597 | 0.103 | 0.775 |
| with_rule_score | 0.903 | 0.259 (0.1635–0.3838) | 0.629 | 0.052 | 0.825 |

| System | Band | Benign n | Scam n | Precision | Precision @1% prevalence |
|---|---|---|---|---|---|
| spec_baseline | low | 44 | 13 | 0.228 | n/a |
| spec_baseline | medium | 8 | 12 | 0.600 | 0.014 |
| spec_baseline | high | 6 | 37 | 0.861 | 0.055 |
| with_rule_score | low | 43 | 6 | 0.122 | n/a |
| with_rule_score | medium | 12 | 17 | 0.586 | 0.013 |
| with_rule_score | high | 3 | 39 | 0.929 | 0.109 |

Per scam family (flagged recall / high recall):

| Family | n | spec_baseline | with_rule_score |
|---|---|---|---|
| digital_arrest | 11 | 0.909 / 0.545 | 0.909 / 0.545 |
| job_task | 11 | 0.727 / 0.636 | 0.818 / 0.364 |
| kyc_refund | 12 | 0.667 / 0.500 | 1.000 / 0.833 |
| lottery | 11 | 1.000 / 0.909 | 0.909 / 0.909 |
| other | 6 | 0.167 / 0.167 | 0.833 / 0.167 |
| upi_collect | 11 | 1.000 / 0.636 | 0.909 / 0.727 |

Per benign group (flagged / high, out of n):

| Group | n | spec_baseline | with_rule_score |
|---|---|---|---|
| advisory | 4 | 0 / 0 | 0 / 0 |
| bank_alert | 14 | 2 / 1 | 4 / 0 |
| bill | 10 | 6 / 3 | 4 / 2 |
| delivery | 8 | 0 / 0 | 2 / 1 |
| family | 8 | 3 / 1 | 2 / 0 |
| merchant | 4 | 2 / 0 | 2 / 0 |
| otp_notice | 10 | 1 / 1 | 1 / 0 |

Per language (flagged recall / flagged FPR):

| Language | Scam n | Benign n | spec_baseline | with_rule_score |
|---|---|---|---|---|
| en | 31 | 33 | 0.710 / 0.242 | 0.839 / 0.273 |
| hi-en | 17 | 14 | 0.765 / 0.214 | 0.941 / 0.214 |
| hi | 14 | 11 | 1.000 / 0.273 | 1.000 / 0.273 |

Flagged benign ids (shipped): hw108, hw114, hw116, hw123, hw124, hw129, hw135, hw136, hw137, hw139, hw141, hw148, hw149, hw155, hw158.
Missed scam ids (shipped, band low): hw014, hw029, hw043, hw046, hw055, hw057.

## 6. Optional text-model comparison (COMPARE_MODELS, not shipped)

- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: skipped — ModuleNotFoundError: No module named 'sentence_transformers'

## 7. Transaction model: public synthetic mobile-money data (PaySim), not UPI

Features: amount, type, hour, beneficiary_prior_txns, beneficiary_first_seen. Split: fit step<400, calibrate 400-499, test step>=500. Test ROC-AUC 0.9298, PR-AUC 0.6162 (test prevalence 0.0208), recall @1% FPR 0.5831, @0.1% FPR 0.3553.

## 8. Caveats

- Synthetic messages come from a template set (8 per scam family and language; 8–9 per language for the main hard-negative groups). Unseen-family numbers measure transfer between our own templates, not real-world scams.
- rule_score and the rules were written while looking at the synthetic templates; the hand-written set was written by the same assistant before the v2 templates were added. Neither is an independent test; a set written by someone else would be.
- Payee-history values for synthetic payments are a documented generator assumption (jobs/export_training_tables.py).
- UCI SMS Spam is English, UK, mid-2000s; it adds generic spam vocabulary, not Indian UPI scams.
- The UPI 2024 and Indian banking CSVs were profiled and excluded: no learnable label signal (ROC-AUC 0.48 and 0.53 on time splits). See metrics/txn_signal_probe_*.json.
- Cutoffs are tuned on this data and must be re-calibrated on pilot data before any real use.
