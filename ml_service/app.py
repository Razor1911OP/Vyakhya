"""
app.py: Vyakhya scoring service (Flask).

Called by the Node API (api/server.js) for every payment:

    POST /predict  {redacted_text, context, payment}  ->  {R, reasons}
    GET  /health   ->  {"status": "ok"}

How R is computed
-----------------
Each risk factor is turned into a value between 0 and 1, multiplied by a
weight, and the weighted values are added up. The weights sum to 1.0, so
multiplying by 100 gives R in 0-100. The tier (LOW/MEDIUM/HIGH/CRITICAL) is
decided by the Node API, not here.

    factor        value (0-1)                             weight
    SCAM_TEXT     text model's scam probability             0.40
    SCREEN_SHARE  1 if the screen is being shared           0.15
    NEW_PAYEE     1 if the payee UPI ID is < 7 days old     0.12
    AMOUNT_SPIKE  0 at <=1x the user's average, 1 at >=5x   0.12
    CALL_ACTIVE   1 if the user is on a call                0.08
    NEW_DEVICE    1 if the device is new                    0.08
    NEW_GEO       1 if the location is new                  0.05

"reasons" = the factors that clearly fired, biggest contribution first,
at most 3, so the payer sees the main reasons and not a long list.

Text model
----------
../ml/models/text.joblib is loaded ONCE at startup. It must have
predict_proba() (e.g. a scikit-learn Pipeline); column 1 = P(scam).
If the file is missing or can't be loaded, content_score = 0.5 (neutral).

The text arriving here is already redacted by the browser and the API.
This service never logs or stores it.
"""

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

log = logging.getLogger("vyakhya.scoring")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "models" / "text.joblib"
NEUTRAL_CONTENT_SCORE = 0.5

WEIGHTS = {
    "SCAM_TEXT": 0.40,
    "SCREEN_SHARE": 0.15,
    "NEW_PAYEE": 0.12,
    "AMOUNT_SPIKE": 0.12,
    "CALL_ACTIVE": 0.08,
    "NEW_DEVICE": 0.08,
    "NEW_GEO": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1"

# A factor only becomes a "reason" if its value is at least this high.
# SCAM_TEXT needs 0.6 so the neutral 0.5 (no model) is never reported as scam text.
# AMOUNT_SPIKE 0.25 = amount is at least 2x the user's average.
REASON_THRESHOLD = {"SCAM_TEXT": 0.6, "AMOUNT_SPIKE": 0.25}
DEFAULT_THRESHOLD = 0.5  # binary flags: fires when True (value 1)
MAX_REASONS = 3

NEW_PAYEE_DAYS = 7


# ---------------------------------------------------------------------------
# Text model
# ---------------------------------------------------------------------------
def load_model(path=MODEL_PATH):
    """Load the text model, or return None (=> neutral score) if unavailable.

    joblib uses pickle, which can run code: only load model files we built.
    """
    if not path.exists():
        log.warning("text model not found at %s, using content_score=%.1f", path, NEUTRAL_CONTENT_SCORE)
        return None
    try:
        import joblib  # imported here so the service still runs without it

        model = joblib.load(path)
        if not hasattr(model, "predict_proba"):
            raise TypeError("model has no predict_proba()")
        log.info("text model loaded from %s", path)
        return model
    except Exception as exc:  # corrupt file, version mismatch, etc.
        log.error("could not load text model (%s), using content_score=%.1f", exc, NEUTRAL_CONTENT_SCORE)
        return None


MODEL = load_model()  # once, at startup


def content_score(text):
    """P(scam) for the redacted text, 0-1. Neutral 0.5 without a model."""
    if MODEL is None:
        return NEUTRAL_CONTENT_SCORE
    try:
        p = float(MODEL.predict_proba([text])[0][1])
        return min(max(p, 0.0), 1.0)
    except Exception as exc:
        log.error("text model failed (%s), using neutral score", type(exc).__name__)
        return NEUTRAL_CONTENT_SCORE


# ---------------------------------------------------------------------------
# Rule-based fusion
# ---------------------------------------------------------------------------
def amount_spike(amount, user_avg_amount):
    """0 when amount <= average, rising linearly to 1 at 5x the average.

    No history (average 0) is unknown risk, so it counts as half.
    """
    if user_avg_amount <= 0:
        return 0.5
    ratio = amount / user_avg_amount
    return min(max((ratio - 1) / 4, 0.0), 1.0)


def score(text_score, context, payment):
    """Combine all factors into R (0-100) and the top reasons."""
    values = {
        "SCAM_TEXT": text_score,
        "SCREEN_SHARE": float(context["screen_share"]),
        "NEW_PAYEE": 1.0 if payment["payee_age_days"] < NEW_PAYEE_DAYS else 0.0,
        "AMOUNT_SPIKE": amount_spike(payment["amount"], payment["user_avg_amount"]),
        "CALL_ACTIVE": float(context["call_active"]),
        "NEW_DEVICE": float(context["new_device"]),
        "NEW_GEO": float(context["new_geo"]),
    }
    contributions = {name: WEIGHTS[name] * v for name, v in values.items()}

    R = round(100 * sum(contributions.values()), 1)
    R = min(max(R, 0.0), 100.0)

    fired = [n for n, v in values.items() if v >= REASON_THRESHOLD.get(n, DEFAULT_THRESHOLD)]
    fired.sort(key=lambda n: contributions[n], reverse=True)
    return R, fired[:MAX_REASONS]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
CONTEXT_FLAGS = ("new_device", "new_geo", "screen_share", "call_active")
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
    return jsonify(status="ok")


@app.post("/predict")
def predict():
    body = request.get_json(silent=True)  # None on bad/missing JSON
    if body is None:
        return jsonify(error="body must be valid JSON"), 400
    errors = validate(body)
    if errors:
        return jsonify(error="invalid body", details=errors), 400

    R, reasons = score(content_score(body["redacted_text"]), body["context"], body["payment"])
    return jsonify(R=R, reasons=reasons)


@app.errorhandler(413)
def too_large(_err):
    return jsonify(error="body too large"), 413


if __name__ == "__main__":
    # Local only: bound to 127.0.0.1 so it's not reachable from the network.
    app.run(host="127.0.0.1", port=8000, debug=False)
