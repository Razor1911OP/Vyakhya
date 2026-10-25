"""
app.py: Vyakhya scoring service (Flask), backed by the FROZEN risk engine.

Called by the Node API (api/server.js) for every payment:

    POST /predict  {redacted_text, context, payment}  ->  {R, tier, reasons, ...}
    GET  /health   ->  {"status": "ok" | "degraded", ...}

What computes R
---------------
R comes from the evaluated, frozen risk engine (vyakhya_risk risk-0.2.0, rules v2, shipped system
"with_rule_score"): TF-IDF text model + rule layer + PaySim behaviour model, fused as
max(hard_rule_floor, blend). Code lives in <repo>/backend/risk, artifacts in
<repo>/model_registry/risk/risk-0.2.0/ (override the code location with VYAKHYA_ENGINE_DIR).
This service only adapts the API's request shape to the engine; it does not change any score.
The earlier 7-factor weighted sum was removed so the demo runs the system that was evaluated.

Tier
----
Returned here so the API uses the engine's evaluated bands (cutoffs tuned on synthetic data,
re-calibrate at pilot):  band low/medium/high -> LOW/MEDIUM/HIGH, any hard-rule hit -> CRITICAL.

Input adaptation (documented approximations)
--------------------------------------------
- Redaction placeholders ([OTP], [PHONE], ...) are swapped for neutral stand-in digits in memory,
  because the engine was evaluated on text whose digits it masks itself. Nothing is stored.
- amount_vs_history_percentile is derived from amount / user_avg_amount with the same log-normal
  spread (sigma 0.9) the synthetic generator used.
- Payee history: payment.payee_prior_txns if sent; else payee_age_days < 7 -> 0 prior payments;
  else unknown, which the engine treats as a new payee (never as safe).
- payment.hour (0-23) if sent, else the server's local hour. payment.direction
  (debit | collect | credit) if sent, else debit.
- context flags (screen_share, call_active, new_device, new_geo) are SIMULATED in the prototype
  and are NOT used by the frozen engine. They are echoed back as context_flags, outside R.

If the engine cannot load or fails, /predict returns HTTP 503/500 and the API falls back to its
own SCORING_UNAVAILABLE policy. No neutral score is invented here.

The text arriving here is already redacted by the browser and the API. This service never logs
or stores it.
"""

import logging
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

log = logging.getLogger("vyakhya.scoring")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

ENGINE_DIR = Path(os.environ.get("VYAKHYA_ENGINE_DIR", Path(__file__).resolve().parents[2] / "backend"))
NEW_PAYEE_DAYS = 7
HISTORY_SIGMA = 0.9          # spread of a user's log-amounts in the synthetic generator
MAX_REASONS = 3              # the payer sees the main reasons, not a long list
DIRECTIONS = ("debit", "collect", "credit")
BAND_TO_TIER = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"}

# Neutral stand-ins for the API's redaction placeholders (in memory only).
STANDINS = {"OTP": "OTP 000000", "PHONE": "9000000000", "ACCT": "000000000000",
            "CARD": "0000 0000 0000 0000", "AADHAAR": "200000000000", "PAN": "ABCDE0000F", "UPI": "payee@upi"}
PLACEHOLDER = re.compile(r"\[(OTP|PHONE|ACCT|CARD|AADHAAR|PAN|UPI)\]")


# ---------------------------------------------------------------------------
# Frozen engine
# ---------------------------------------------------------------------------
def load_engine(engine_dir=ENGINE_DIR):
    """Load the frozen risk engine once. Returns (engine, info) or (None, None).
    joblib uses pickle, which can run code: only load artifacts we built ourselves."""
    try:
        if str(engine_dir) not in sys.path:
            sys.path.insert(0, str(engine_dir))
        from risk import config as RC
        from risk.engine import RiskEngine
        from risk.rules import RULES_VERSION

        engine = RiskEngine()
        info = {"model_version": RC.MODEL_VERSION, "rules_version": RULES_VERSION,
                "shipped_system": engine.fusion["shipped_system"],
                "cutoff_policy": "tuned on synthetic data, re-calibrate at pilot"}
        log.info("risk engine loaded: %s, rules %s", RC.MODEL_VERSION, RULES_VERSION)
        return engine, info
    except Exception as exc:  # missing artifacts, version mismatch, import error
        log.error("risk engine not available (%s)", type(exc).__name__)
        return None, None


ENGINE, ENGINE_INFO = load_engine()  # once, at startup


# ---------------------------------------------------------------------------
# Request -> engine adaptation
# ---------------------------------------------------------------------------
def for_engine(redacted_text):
    return PLACEHOLDER.sub(lambda m: STANDINS[m.group(1)], redacted_text)


def history_percentile(amount, user_avg_amount):
    """Where this amount sits in the user's own history (0-100). 50 = unknown/no history."""
    if user_avg_amount <= 0 or amount <= 0:
        return 50.0
    z = math.log(amount / user_avg_amount) / HISTORY_SIGMA
    return round(50 * (1 + math.erf(z / math.sqrt(2))), 1)


def to_engine_txn(payment, now=None):
    now = now or datetime.now()
    prior = payment.get("payee_prior_txns")
    if prior is None and payment["payee_age_days"] < NEW_PAYEE_DAYS:
        prior = 0
    return {
        "amount": float(payment["amount"]),
        "hour": int(payment.get("hour", now.hour)),
        "direction": payment.get("direction", "debit"),
        "beneficiary_prior_txns": None if prior is None else int(prior),
        "amount_vs_history_percentile": history_percentile(payment["amount"], payment["user_avg_amount"]),
    }


def reason_codes(result, txn):
    """Engine output -> API reason codes (api/server.js has the plain-language text). Strongest first."""
    f = result["flags"]
    hard = result["hard_rule_floor"] >= 90
    pin_to_receive = hard and f["reward_claim"] and (f["asks_pin"] or f["collect_approval"])
    codes = []
    if pin_to_receive:
        codes.append("PIN_TO_RECEIVE")
    if f["amount_mismatch"]:
        codes.append("AMOUNT_MISMATCH")
    if f["asks_otp"] or (f["asks_pin"] and not pin_to_receive):
        codes.append("OTP_REQUEST")
    if f["collect_approval"] and not pin_to_receive:
        codes.append("COLLECT_REQUEST")
    if f["fee_to_claim"] or (f["reward_claim"] and not pin_to_receive):
        codes.append("REFUND_LURE")
    if result["text_prob"] is not None and result["text_prob"] >= 0.5:
        codes.append("SCAM_TEXT")
    if f["urgency"]:
        codes.append("URGENCY")
    prior = txn["beneficiary_prior_txns"]
    if prior is None:
        codes.append("PAYEE_UNKNOWN")
    elif prior == 0:
        codes.append("PAYEE_NO_HISTORY")
    elif prior < 3:
        codes.append("PAYEE_LITTLE_HISTORY")
    if txn["amount_vs_history_percentile"] >= 95:
        codes.append("AMOUNT_SPIKE")
    if f["has_link"]:
        codes.append("HAS_LINK")
    return codes


CONTEXT_CODES = {"screen_share": "SCREEN_SHARE", "call_active": "CALL_ACTIVE",
                 "new_device": "NEW_DEVICE", "new_geo": "NEW_GEO"}


def score(body, now=None):
    txn = to_engine_txn(body["payment"], now)
    result = ENGINE.score(text=for_engine(body["redacted_text"]), txn=txn)
    hard = result["hard_rule_floor"] >= 90
    codes = reason_codes(result, txn)
    return {
        "R": float(result["risk_score"]),
        "tier": "CRITICAL" if hard else BAND_TO_TIER[result["band"]],
        "reasons": codes[:MAX_REASONS],
        "all_reasons": codes,
        "band": result["band"],
        "signal_mode": result["signal_mode"],
        "hard_rule_floor": result["hard_rule_floor"],
        "text_prob": result["text_prob"], "txn_prob": result["txn_prob"], "rule_prob": result["rule_prob"],
        "disclaimer": result["disclaimer"],
        "ask_user": result["ask_user"],
        "cutoffs": {k: ENGINE.bands[result["signal_mode"]][k] for k in ("medium", "high")},
        "context_flags": [c for k, c in CONTEXT_CODES.items() if body["context"][k]],
        "context_note": "SIMULATED signals, not used in R by the frozen engine",
        **(ENGINE_INFO or {}),
    }


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
CONTEXT_FLAGS = tuple(CONTEXT_CODES)
PAYMENT_NUMBERS = ("amount", "payee_age_days", "user_avg_amount")


def _is_number(v):
    # bool is a subclass of int in Python, so exclude it explicitly
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def validate(body):
    """Return a list of problems; empty list = valid."""
    if not isinstance(body, dict):
        return ["body must be a JSON object"]
    errors = []

    if not isinstance(body.get("redacted_text"), str):
        errors.append("redacted_text must be a string")
    elif len(body["redacted_text"]) > 5000:
        errors.append("redacted_text must be at most 5000 chars")

    context = body.get("context")
    if not isinstance(context, dict):
        errors.append("context must be an object")
    else:
        for key in CONTEXT_FLAGS:
            if not isinstance(context.get(key), bool):
                errors.append(f"context.{key} must be true or false")

    payment = body.get("payment")
    if not isinstance(payment, dict):
        errors.append("payment must be an object")
    else:
        for key in PAYMENT_NUMBERS:
            v = payment.get(key)
            if not _is_number(v) or v < 0:
                errors.append(f"payment.{key} must be a number >= 0")
        if _is_number(payment.get("amount")) and payment["amount"] == 0:
            errors.append("payment.amount must be > 0")
        # optional fields
        if "payee_prior_txns" in payment and (not _is_number(payment["payee_prior_txns"]) or payment["payee_prior_txns"] < 0):
            errors.append("payment.payee_prior_txns must be a number >= 0")
        if "hour" in payment and not (isinstance(payment["hour"], int) and not isinstance(payment["hour"], bool)
                                      and 0 <= payment["hour"] <= 23):
            errors.append("payment.hour must be an integer 0-23")
        if "direction" in payment and payment["direction"] not in DIRECTIONS:
            errors.append("payment.direction must be one of debit, collect, credit")
    return errors


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024  # same limit as the Node API

# Normally only the Node API (server-to-server) calls this; CORS is for the
# web demo. Comma-separated list, e.g. "http://localhost:5173,http://localhost:3000".
CORS(app, origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","))


@app.get("/health")
def health():
    if ENGINE is None:
        return jsonify(status="degraded", engine_loaded=False), 503
    return jsonify(status="ok", engine_loaded=True, **ENGINE_INFO)


@app.post("/predict")
def predict():
    body = request.get_json(silent=True)  # None on bad/missing JSON
    if body is None:
        return jsonify(error="body must be valid JSON"), 400
    errors = validate(body)
    if errors:
        return jsonify(error="invalid body", details=errors), 400
    if ENGINE is None:
        return jsonify(error="risk engine unavailable"), 503
    try:
        return jsonify(score(body))
    except ValueError as exc:  # engine-side input check (e.g. amount out of range)
        return jsonify(error="invalid body", details=[str(exc)]), 400
    except Exception as exc:
        log.error("scoring failed (%s)", type(exc).__name__)  # never log the text
        return jsonify(error="scoring failed"), 500


@app.errorhandler(413)
def too_large(_err):
    return jsonify(error="body too large"), 413


if __name__ == "__main__":
    # Local only: bound to 127.0.0.1 so it's not reachable from the network.
    app.run(host="127.0.0.1", port=8000, debug=False)
