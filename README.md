# Vyakhya
<<<<<<< HEAD

> **"The scam went AI-native. The payment still looks legitimate."**

Vyakhya is an AI-driven scam pattern recognition system for UPI/banking/wallet payments. It reads a scam as a **workflow** (message + call + device + transaction), not a single flag, and intervenes **before the debit** only when it truly matters, with a human analyst in control of every hold.

**Name Origin:** "Vyakhya" (व्याख्या) means "explanation" in Sanskrit. Every decision carries a plain-language **reason code**. Explainability is the product's identity.

---

## 🎯 Core Philosophy

1. **Workflow-aware detection**: Scams are multi-step social engineering attacks (message → call → screen-share → payment). We model the full attack chain.

2. **Explainability-first**: Every risk score comes with specific, plain-language reasons. No black boxes.

3. **Tiered friction**: 
   - **LOW (0-39)**: Silent logging
   - **MEDIUM (40-69)**: Gentle nudge
   - **HIGH (70-84)**: Named friction + 30s wait
   - **CRITICAL (85-100)**: Soft-hold before debit, analyst review

4. **Privacy by design**: Raw message text is **never stored**. Client-side + server-side redaction. Only minimized, redacted features are processed.

5. **Honest evaluation**: All metrics are measured on **synthetic data** and labeled as such. Production calibration noted as future work.

---

## 🏗️ Architecture

```
┌─────────────┐
│  Frontend   │  React + Vite (4 panels: Simulator, Detection, Analysis, Evaluation)
│  (TypeScript)│
└──────┬──────┘
       │ HTTPS + JWT
       ▼
┌─────────────────────────────────────────────────────────┐
│             FastAPI Backend (Python 3.11)                │
│                                                           │
│  ┌─────────────────────────────────────────────────┐   │
│  │       Detection Engine (In-Process)              │   │
│  │                                                   │   │
│  │  Validate/Redact → Text Model → Txn Model       │   │
│  │       ↓                                          │   │
│  │  Context Rules → Fusion → Tier Policy           │   │
│  │                                                   │   │
│  │  < 300ms latency budget (p95)                   │   │
│  └─────────────────────────────────────────────────┘   │
│                                                           │
│  Models:                                                 │
│  • HF multilingual text (+ TF-IDF fallback)             │
│  • XGBoost transaction fraud                             │
│  • Context rules (call, screen-share, velocity)         │
│  • Fusion + isotonic calibration → R ∈ [0, 100]        │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
                  ┌──────────┐
                  │ MongoDB  │  Events, cases, audit log (no raw text)
                  └──────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- MongoDB (via Docker or local install)

### 1. Clone and Setup

```bash
# Clone repository
cd vyakhya

# Backend setup
cd backend
pip install -r requirements.txt
cp .env.example .env  # Edit with your config

# Create dummy models (for testing - train real models before production)
python test_engine.py

# Start API server
python -m backend.app.main
# Server runs at http://localhost:8000
```

### 2. Test the Detection Engine

```bash
cd backend
python test_engine.py
```

Expected output:
```
TEST 1: Normal grocery payment
Risk Score: 15 / 100
Tier: LOW
Soft Hold: False
Latency: 45ms

TEST 2: Coached victim - digital arrest scam
Risk Score: 92 / 100
Tier: CRITICAL
Soft Hold: True ⚠️
Latency: 67ms
```

### 3. Test the API

```bash
# Health check
curl http://localhost:8000/health

# Model info
curl http://localhost:8000/api/v1/model-info

# Score a payment
curl -X POST http://localhost:8000/api/v1/score \
  -H "Content-Type: application/json" \
  -d '{
    "message_text": "URGENT: Verify your KYC now or account will be suspended",
    "transaction": {
      "amount": 50000,
      "oldbalance_orig": 100000,
      "newbalance_orig": 50000,
      "oldbalance_dest": 0,
      "newbalance_dest": 50000,
      "hour": 22,
      "day": 15,
      "transaction_type": "TRANSFER"
    },
    "context": {
      "call_in_progress": true,
      "new_payee": true,
      "odd_hour": true,
      "simulated": true
    },
    "user_id": "test_user_001"
  }'
```

---

## 📁 Project Structure

```
vyakhya/
├── README.md
├── docs/
│   └── reference_notes.md          # Reference repo analysis
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point
│   │   ├── engine/                 # Detection pipeline
│   │   │   ├── __init__.py         # Main orchestrator
│   │   │   ├── validate_redact.py  # Privacy layer
│   │   │   ├── text_model.py       # HF + TF-IDF fallback
│   │   │   ├── txn_model.py        # XGBoost transaction
│   │   │   ├── context_rules.py    # Session/velocity rules
│   │   │   ├── fusion.py           # Score fusion
│   │   │   └── tier_policy.py      # Tier assignment
│   │   ├── core/
│   │   │   ├── config.py           # Settings
│   │   │   └── logging.py          # Privacy-aware logging
│   │   └── schemas/
│   │       └── __init__.py         # Pydantic models
│   ├── requirements.txt
│   ├── test_engine.py              # Engine test suite
│   └── .env.example
├── model_registry/                 # Model weights + config
├── metrics/                        # Evaluation outputs (JSON)
├── data/                           # Synthetic data
└── notebooks/                      # Jupyter experiments (coming next)
```

---

## 🔒 Security & Privacy

### Redaction (Defence in Depth)
- **Client-side**: Preview redaction before submission
- **Server-side**: Re-validates and redacts OTP, account, card, phone patterns
- **Never stored**: Raw message text is NEVER persisted or logged

### What is Stored:
- ✅ Redacted text preview (first 100 chars)
- ✅ Text hash (SHA256, for deduplication only)
- ✅ Statistical features (length, digit ratio, urgency keywords)
- ✅ Risk score, tier, reason codes
- ✅ Model versions, timestamp
- ❌ **NEVER raw message text**
- ❌ **NEVER OTP, account numbers, card numbers, phone numbers**

### Audit Trail
- Every decision is logged with:
  - Risk score, tier, reason codes
  - Model versions used
  - Timestamp, latency
  - Analyst decision (if reviewed)
- **Immutable log** - no edits after creation
- Retention: features (90 days), cases (1 year)

---

## 🎨 Detection Engine Components

### 1. Validation & Redaction
- Schema validation
- Pattern-based redaction (OTP, account, card, phone, VPA, IFSC)
- Language detection (English / Hindi / Hinglish)
- Feature extraction (word count, digit ratio, urgency keywords)

### 2. Text Model
- **Primary**: HF multilingual transformer (DistilBERT-multilingual or similar)
- **Fallback**: TF-IDF (1-2 gram) + Logistic Regression
- **Timeout**: 200ms max for HF, falls back to TF-IDF if exceeded
- **Output**: Scam probability [0, 1]

### 3. Transaction Model
- **Algorithm**: XGBoost with SMOTE (class imbalance)
- **Features**:
  - Amount, amount vs history percentile
  - Balance consistency (errorBalanceOrig, errorBalanceDest)
  - Time features (hour, day)
  - Velocity (txn count last hour/day, fan-out count)
  - Transaction type (one-hot encoded)
- **Output**: Fraud probability [0, 1]

### 4. Context Rules
- **Signals**:
  - Call in progress (0.25 weight)
  - Screen-share active (0.30 weight)
  - New device (0.10)
  - Geo-velocity anomaly (0.15)
  - Pasted VPA (0.12)
  - Odd hour (0.08)
  - New payee (0.15)
- **Philosophy**: Missing signal widens review band, never silently lowers risk
- **Output**: Context risk score [0, 1] + reason codes

### 5. Fusion Layer
- **MVP**: Weighted ensemble (text 40%, txn 35%, context 25%)
- **Production**: Gradient-boosted fusion model + isotonic calibration
- **Output**: Risk score R ∈ [0, 100]

### 6. Tier Policy
| Tier | R Range | Behavior |
|------|---------|----------|
| **LOW** | 0-39 | Silent allow, log only |
| **MEDIUM** | 40-69 | One inline nudge, one-tap proceed |
| **HIGH** | 70-84 | Named-reason friction + 30s wait |
| **CRITICAL** | 85-100 | Soft-hold before debit, analyst review |

---

## 📊 Current Status

### ✅ Completed
- Detection engine architecture (all 6 components)
- FastAPI backend with `/score` endpoint
- Redaction & privacy layer (defence-in-depth)
- Dummy models for testing (TF-IDF, XGBoost)
- Tier policy with explainable reason codes
- Health check and model info endpoints
- Test suite for engine validation

### 🚧 In Progress
- Jupyter notebooks for model training/evaluation
- Real trained models (replacing dummies)
- Frontend panels (Simulator, Detection, Analysis, Evaluation)
- MongoDB integration (events, cases, audit log)
- Auth (JWT + RBAC)

### 📋 Roadmap
- Novelty detection (HDBSCAN clustering)
- Leave-one-family-out evaluation (target: mean recall >= 0.80)
- Synthetic data generator (1,200+ messages across 5 scam families)
- Dual-review workflow for CRITICAL releases
- Red-team test suite
- Docker Compose setup
- Production deployment guide

---

## 🧪 Testing

### Engine Tests
```bash
python backend/test_engine.py
```

Tests:
1. **Normal payment**: Low risk (< 40)
2. **Coached victim**: High/critical risk (> 85), soft-hold triggered
3. **Refund scam**: Medium/high risk
4. **Latency budget**: < 300ms p95

### API Tests
```bash
# Coming soon: pytest suite
pytest backend/tests/
```

---

## ⚠️ Honest Limitations (MVP)

### Labeled as **SIMULATED**:
- All context signals (call, screen-share, device, location) - prototype cannot detect these for real
- Money-graph features (payee-is-mule, fan-out) - requires full payment network integration
- Transaction history (amount percentiles, velocity) - uses mock values

### Labeled as **SYNTHETIC DATA**:
- All model metrics (precision, recall, F1) measured on synthetic messages
- Tier cutoffs calibrated on synthetic data (re-calibration needed at pilot)

### Labeled as **ROADMAP**:
- In-browser text inference (currently server-side only)
- Cross-bank intelligence (private set intersection for known scammer VPAs)
- Multi-factor authentication (MFA)
- Real-time money-graph analysis (GNN)

---

## 📚 Reference Repositories

Analysis in `docs/reference_notes.md`. Key ideas borrowed (all code originally written):

1. **UPI-Fraud-Detection** (TheCodingAyush): XGBoost + SMOTE, balance error features
2. **Smishing-Detection-System** (SimeonMataka): TF-IDF + multilingual NLP pipeline
3. **Mule-Hunt** (sohamvjadhav): Graph-based features, leave-one-pattern-out evaluation

**Licenses**: See `docs/reference_notes.md` for attribution requirements.

---

## 🤝 Contributing

This is a hackathon/research project. Contributions welcome:

1. **Honest evaluation**: Report real metrics, including failures
2. **Privacy-first**: Never commit real data, secrets, or PII
3. **Explainability**: Every decision needs a plain-language reason
4. **Label everything**: Synthetic data, simulated signals, roadmap features

---

## 📄 License

TBD (Add license before public release)

---

## 🙏 Acknowledgments

Built for the **RAKSHAM / Problem 02 Hackathon**.

Inspired by research on UPI fraud, smishing detection, and behavioral biometrics.

---

**Status**: Detection engine operational ✅ | Models: Dummy (train real ones next) ⚠️ | Latency: < 100ms avg 🚀
=======
AI + CyberSecurity Scam UPI owrkflow driven Project
>>>>>>> 2b1ab8f4eb6800b2d2b5e1fb115cf3ca5f066d23
