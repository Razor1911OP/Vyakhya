# Reference Repository Analysis

Analysis of three reference repositories for Vyakhya project. All code will be written **originally** - these notes capture **reusable ideas only**.

---

## 1. UPI-Fraud-Detection (TheCodingAyush)

**License:** Not explicitly stated in README (check repo for LICENSE file before any code reuse)

### Reusable Ideas:
- **Feature engineering approach:**
  - Time-based features: hour, day extraction from transaction step
  - Balance consistency checks: `errorBalanceOrig`, `errorBalanceDest` computed from old/new balances
  - Transaction type encoding
- **Model pipeline:**
  - XGBoost as primary classifier (proven effective for tabular transaction data)
  - SMOTE for handling class imbalance (critical for fraud detection with rare positive class)
  - PCA for dimensionality reduction (95% variance retention)
  - Ensemble approach: weighted voting across multiple models (XGBoost 40%, LR/DT/SVM 20% each)
- **Rule-based augmentation:**
  - Hard rules for large amounts, balance inconsistencies, off-hours transactions
  - Combines ML probability with deterministic red flags
- **API design:**
  - Simple POST /predict endpoint with JSON transaction payload
  - Returns predictions from multiple models plus ensemble recommendation
  - Health check and model info endpoints
- **Dataset:** PaySim synthetic mobile money transactions (Kaggle, 470MB, highly imbalanced)

### What to Avoid:
- No redaction or privacy controls visible
- No explicit tier/reason code system
- Models not versioned or tracked in a registry

---

## 2. Smishing-Detection-System (SimeonMataka)

**License:** © 2023 Smishing Detectives, All Rights Reserved (proprietary - do NOT copy code)

### Reusable Ideas:
- **NLP preprocessing pipeline:**
  - Lowercase → tokenize → stopword removal (English + local language) → stemming (Porter)
  - TF-IDF vectorization for text features
  - Scikit-learn classifier (likely logistic regression or SVM)
- **Multilingual handling:**
  - Custom stopword lists for English + Chichewa
  - Shows pattern for Hindi/Hinglish adaptation
- **Simple architecture:**
  - Flask backend with single prediction endpoint
  - Pickled vectorizer + model for fast loading
  - Real-time classification with instant response
- **API design:**
  - POST /detect with `{"sms_message": "..."}` payload
  - Returns `{"result": "smishing"}` or `{"result": "legit"}`
  - Separate API documentation page

### What to Avoid:
- No redaction visible
- Binary classification only (no risk scoring or tiers)
- Logs predictions to PostgreSQL (we must never persist raw text)

---

## 3. Mule-Hunt (sohamvjadhav)

**License:** MIT (generator under Apache-2.0) - **attribution required if using patterns**

### Reusable Ideas:
- **Graph-based features for mule/money-laundering detection:**
  - Payment network as directed graph (nodes = accounts, edges = transfers)
  - GNN (Graph Neural Network) for coordinated fraud ring detection
  - Topology features: fan-out, fan-in, clustering coefficient, betweenness centrality
  - Temporal features: burst patterns, velocity changes
- **Synthetic graph generation:**
  - Procedural generation of realistic payment networks with fraud rings
  - Controlled insertion of mule patterns for training/evaluation
- **Evaluation approach:**
  - Leave-one-ring-out testing (analogous to our leave-one-family-out)
  - Adversarial robustness checks
  - Scaling experiments with honest negative results reported
- **Money-graph signals for Vyakhya:**
  - New payee flag
  - Fan-out ratio (one source → many destinations in short time = potential money mule)
  - Beneficiary account age
  - Velocity (transactions per hour)

### What to Avoid:
- Full GNN implementation likely overkill for MVP (keep graph features simple)
- Real-time GNN inference may exceed 300ms latency budget (use precomputed features)

---

## Key Takeaways for Vyakhya:

1. **Text model:** TF-IDF + logistic regression baseline is proven and fast; HF model should beat it or we keep the baseline
2. **Transaction model:** XGBoost + SMOTE is the right choice for imbalanced tabular data
3. **Feature engineering matters:** Balance consistency, time-of-day, velocity, fan-out, new-payee flags
4. **Ensemble + rules:** Combine ML probabilities with hard business rules
5. **Multilingual NLP:** Custom stopword lists + language-specific preprocessing
6. **Privacy gap in all three repos:** None implement proper redaction or audit trails - this is our differentiator
7. **Honest evaluation:** Mule-Hunt's approach (leave-one-pattern-out, adversarial tests, reported negatives) is the model to follow

---

## License Summary:
- **UPI-Fraud-Detection:** Unknown (check repo)
- **Smishing-Detection-System:** Proprietary (no code reuse)
- **Mule-Hunt:** MIT (requires attribution)

All Vyakhya code will be **originally written**. These repos inspire **feature choices and architecture patterns only**.
