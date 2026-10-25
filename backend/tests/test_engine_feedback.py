"""Engine + feedback tests. Needs artifacts from train_eval.py. Run: .\\run.bat tests\\test_engine_feedback.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from risk import config as C  # noqa: E402

pytestmark = pytest.mark.skipif(not (C.ARTIFACT_DIR / "fusion.json").exists(), reason="run train_eval.py first")

SCAM = "Your refund of Rs 2,000 is on hold. Share the OTP with our executive and enter UPI PIN to receive it."
SECRET_TOKEN = "zq7unique9marker"


@pytest.fixture(scope="module")
def eng():
    from risk.engine import RiskEngine
    return RiskEngine()


def test_output_contract(eng):
    r = eng.score(text=SCAM, txn={"amount": 2000, "hour": 11, "direction": "debit"})
    for k in ("risk_score", "band", "reasons", "flags", "text_prob", "txn_prob", "model_version"):
        assert k in r
    assert 0 <= r["risk_score"] <= 100 and r["band"] in ("low", "medium", "high")
    assert r["hard_rule_floor"] == 90 and r["risk_score"] >= 90
    assert r["band"] == "high", "any hard-rule hit must be high band"
    assert r["action"] == "strong_warning"
    assert r["disclaimer"] == C.PIN_DISCLAIMER
    assert r["ask_user"] == C.FEEDBACK_QUESTION


def test_feedback_no_never_below_floor_and_no_raw_text(eng, tmp_path):
    fb = tmp_path / "fb.jsonl"
    text = SCAM + " " + SECRET_TOKEN
    r = eng.score(text=text, txn={"amount": 2000, "hour": 11, "direction": "debit"})
    no = eng.apply_feedback(text, r, answer_yes=False, feedback_file=fb)
    assert no["risk_score"] >= 90
    raw = fb.read_text(encoding="utf-8")
    assert SECRET_TOKEN not in raw and "refund" not in raw.lower()
    rec = json.loads(raw.splitlines()[0])
    assert set(rec) == {"ts", "model_version", "text_hmac", "flags", "answer", "risk_before", "risk_after"}


def test_feedback_yes_raises(eng, tmp_path):
    text = "Please share the OTP you just received."
    r = eng.score(text=text)
    assert r["ask_user"]
    yes = eng.apply_feedback(text, r, answer_yes=True, feedback_file=tmp_path / "fb.jsonl")
    assert yes["risk_score"] > r["risk_score"] or yes["risk_score"] == 100
    assert yes["band"] == "high"


def test_missing_payee_history_not_treated_as_safe(eng):
    known = eng.score(txn={"amount": 5000, "hour": 14, "direction": "debit", "beneficiary_prior_txns": 200})
    unknown = eng.score(txn={"amount": 5000, "hour": 14, "direction": "debit"})
    assert unknown["txn_prob"] >= known["txn_prob"]


def test_input_validation(eng):
    with pytest.raises(ValueError):
        eng.score(txn={"amount": -5, "hour": 3})
    with pytest.raises(ValueError):
        eng.score(txn={"amount": 5, "hour": 30})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))


def test_medium_is_never_a_block(eng):
    from risk.fusion import ACTIONS
    action, text = ACTIONS["medium"]
    assert action == "warn_verify" and "never block" in text.lower()


def test_regression_hindi_bill_receipt_scores_below_90(eng):
    """The 6 former false positives (merchant_bill_hi_07 + matching debit) must score below 90 end to end."""
    import csv
    with open(C.TRANSACTIONS_PATH, encoding="utf-8") as f:
        tx = {r["msg_id"]: r for r in csv.DictReader(f)}
    with open(C.MESSAGES_PATH, encoding="utf-8") as f:
        rows = [m for m in csv.DictReader(f) if m["template_id"] == "merchant_bill_hi_07"]
    assert len(rows) == 6
    for m in rows:
        t = tx[m["msg_id"]]
        r = eng.score(text=m["text"], txn={"amount": float(t["amount"]), "hour": int(t["hour"]), "direction": t["direction"],
                                           "beneficiary_prior_txns": int(t["beneficiary_prior_txns"]),
                                           "amount_vs_history_percentile": float(t["amount_vs_history_percentile"]),
                                           "txn_count_last_hour": int(t["txn_count_last_hour"]),
                                           "txn_count_last_day": int(t["txn_count_last_day"]),
                                           "fan_out_count": int(t["fan_out_count"])})
        assert r["hard_rule_floor"] == 0 and r["risk_score"] < 90, (m["msg_id"], r["risk_score"])
