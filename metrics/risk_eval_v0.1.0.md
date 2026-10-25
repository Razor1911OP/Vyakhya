# Vyakhya risk engine evaluation

> **All metrics come from synthetic and public datasets (UCI SMS Spam, Vyakhya synthetic messages, PaySim). They are not production accuracy.**

Model version `risk-0.1.0`, seed 42. Folds are scam families (templates never shared across folds); UCI spam is the sixth fold `generic_spam`. Fusion weight and band thresholds are chosen on the other folds, then applied to the held-out fold.

## Leave-one-family-out (all signals combined; flagged = medium or high band)

| Held-out fold | Scam n | Benign n | Accuracy | Scam recall | FPR | AUC | Recall @1% FPR | Deck baseline | w_text |
|---|---|---|---|---|---|---|---|---|---|
| kyc_refund | 140 | 1007 | 0.945 | 0.564 | 0.002 | 0.960 | 0.679 | 0.84 | 0.20 |
| digital_arrest | 140 | 908 | 0.938 | 0.557 | 0.003 | 0.990 | 0.664 | 0.77 | 0.20 |
| lottery | 140 | 904 | 0.918 | 0.393 | 0.001 | 0.980 | 0.643 | 0.68 | 0.20 |
| upi_collect | 140 | 978 | 0.996 | 0.964 | 0.000 | 0.999 | 0.979 | 0.43 | 0.15 |
| job_task | 140 | 877 | 0.906 | 0.371 | 0.009 | 0.958 | 0.364 | 0.26 | 0.65 |
| generic_spam | 747 | 853 | 0.533 | 0.000 | 0.000 | 0.883 | 0.469 | n/a | 0.20 |

Mean unseen-family recall @1% FPR (5 synthetic families): **0.6657** vs deck text-only baseline 0.6 and target 0.8.

## Ablation (recall @1% FPR per held-out fold)

| Variant | kyc_refund | digital_arrest | lottery | upi_collect | job_task | generic_spam | Mean (5 synthetic) | Synthetic AUC |
|---|---|---|---|---|---|---|---|---|
| text only | 0.086 | 0.243 | 0.000 | 0.364 | 0.000 | 0.469 | 0.139 | 0.717 |
| rules only | 0.686 | 0.250 | 0.921 | 1.000 | 0.243 | 0.123 | 0.620 | 0.848 |
| transaction only | 0.000 | 0.450 | 0.143 | 0.500 | 0.343 | n/a | 0.287 | 0.876 |
| text + rules | 0.343 | 0.243 | 0.000 | 0.979 | 0.000 | 0.469 | 0.313 | 0.802 |
| all combined | 0.679 | 0.664 | 0.643 | 0.979 | 0.364 | 0.469 | 0.666 | 0.902 |

Variant definitions: *rules only* = weighted sum of all rule flags (with hard floor); *text + rules* and *all combined* follow the spec formula `max(hard_rule_floor, blend)`, so soft rule flags (asks_otp, fee_to_claim, urgency, ...) only contribute through the hard floor and the reasons.
Transaction-only is n/a on `generic_spam`: UCI messages have no paired payment.

## Hard negatives (benign messages that look like scams)

| Group | n | Flagged (FPR) | High band | Hard-floor hits | Text-only FPR @0.5 |
|---|---|---|---|---|---|
| OTP notices | 100 | 0.020 | 0.010 | 0 | 0.300 |
| Debit/credit alerts | 73 | 0.055 | 0.014 | 0 | 0.931 |
| Genuine KYC reminders | 27 | 0.000 | 0.000 | 0 | 0.000 |
| Bill reminders / receipts | 100 | 0.030 | 0.020 | 0 | 0.710 |
| Genuine refunds | 100 | 0.000 | 0.000 | 0 | 0.500 |
| UCI everyday SMS (ham) | 4827 | 0.000 | 0.000 | 0 | 0.007 |

## Transaction model: public synthetic mobile-money data (PaySim), not UPI

Features: amount, type, hour, beneficiary_prior_txns, beneficiary_first_seen. Split: fit step<400, calibrate 400-499, test step>=500. Test ROC-AUC 0.9298, PR-AUC 0.6162 (test prevalence 0.0208), recall @1% FPR 0.5831, @0.1% FPR 0.3553.

## Caveats

- Synthetic messages come from a small template set (4 per family and language); unseen-family numbers measure transfer between our own templates, not real-world scams.
- Payee-history values for synthetic payments are a documented generator assumption (see jobs/export_training_tables.py), so the transaction signal on synthetic data partly reflects that assumption.
- UCI SMS Spam is English, UK, mid-2000s; it adds generic spam vocabulary, not Indian UPI scams.
- The UPI 2024 and Indian banking CSVs were profiled and excluded: their labels showed no learnable signal (ROC-AUC 0.48 and 0.53 on time splits). See metrics/txn_signal_probe_*.json.
- Cutoffs are tuned on this data and must be re-calibrated on pilot data before any real use.
