"""
Runtime risk engine. Loads artifacts from model_registry/risk/<version>/ and scores one event.

    from risk.engine import RiskEngine
    eng = RiskEngine()
    result = eng.score(text="...", txn={"amount": 1499, "hour": 14, "direction": "collect", ...})
    if result["ask_user"]:
        result = eng.apply_feedback(text, result, answer_yes=True)

Never logs or stores raw text. Inputs are capped at MAX_INPUT_CHARS.
Artifacts are joblib pickles produced by train_eval.py; only load artifacts you built yourself.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

from risk import config as C
from risk.fusion import ACTIONS, band, blend, signal_mode
from risk.redact import model_text, text_hmac
from risk.rules import evaluate
from risk.txn_model import paysim_prob, sender_frame

TXN_DEFAULTS = {  # missing payee history is treated as an unknown (new) payee, never as safe
    "beneficiary_prior_txns": 0, "beneficiary_first_seen": 1, "amount_vs_history_percentile": 50.0,
    "txn_count_last_hour": 0, "txn_count_last_day": 0, "fan_out_count": 1, "direction": "debit",
}
DIRECTIONS = {"debit", "collect", "credit"}


class RiskEngine:
    def __init__(self, artifact_dir: Path = C.ARTIFACT_DIR):
        d = Path(artifact_dir)
        self.text_model = joblib.load(d / "text_model.joblib")
        self.paysim = joblib.load(d / "paysim_model.joblib")
        self.sender = joblib.load(d / "sender_model.joblib")
        self.rule_calibrator = joblib.load(d / "rule_calibrator.joblib")
        self.fusion = json.loads((d / "fusion.json").read_text(encoding="utf-8"))
        shipped = self.fusion["systems"][self.fusion["shipped_system"]]
        self.weights = tuple(shipped["weights"])     # (text, txn, rule)
        self.bands = shipped["bands"]                # {"both": {...}, "text": {...}, "txn": {...}}

    # ------------------------------------------------------------------ scoring
    @staticmethod
    def _clean_txn(txn: Optional[dict]) -> Optional[dict]:
        if txn is None:
            return None
        t = {**TXN_DEFAULTS, **{k: v for k, v in txn.items() if v is not None}}
        missing_payee = txn.get("beneficiary_prior_txns") is None
        amount, hour = float(t["amount"]), int(t["hour"])
        if not (0 < amount <= 1e8):
            raise ValueError("amount must be in (0, 1e8]")
        if not 0 <= hour <= 23:
            raise ValueError("hour must be 0-23")
        if t["direction"] not in DIRECTIONS:
            raise ValueError(f"direction must be one of {sorted(DIRECTIONS)}")
        prior = max(0, int(t["beneficiary_prior_txns"]))
        t.update(amount=amount, hour=hour, beneficiary_prior_txns=prior,
                 beneficiary_first_seen=int(prior == 0), _missing_payee=missing_payee)
        return t

    def _txn_prob(self, t: dict) -> float:
        frame = pd.DataFrame([t])
        p_paysim = paysim_prob(self.paysim, frame)
        return float(self.sender.predict_proba(sender_frame(frame, p_paysim))[:, 1][0])

    def score(self, text: Optional[str] = None, txn: Optional[dict] = None) -> dict:
        text = (text or "")[:C.MAX_INPUT_CHARS]
        t = self._clean_txn(txn)
        has_text = bool(text.strip())
        mode = signal_mode(has_text, t is not None)
        bands = self.bands[mode]
        rules = evaluate(text, t["amount"] if t else None, t["direction"] if t else "debit")

        text_prob = float(self.text_model.predict_proba(np.array([model_text(text)], dtype=object))[:, 1][0]) \
            if has_text else None
        rule_prob = float(self.rule_calibrator.predict([rules.rule_score])[0]) if has_text else None
        txn_prob = self._txn_prob(t) if t else None

        nan = np.nan
        b = blend([nan if text_prob is None else text_prob], [nan if txn_prob is None else txn_prob],
                  [nan if rule_prob is None else rule_prob], self.weights)[0]
        score = int(round(max(float(rules.floor), 100.0 * b)))
        level = band(score, bands, rules.floor)

        reasons = list(rules.reasons)
        if text_prob is not None and text_prob >= 0.5:
            reasons.append("Wording matches known scam messages")
        if t:
            if t["_missing_payee"]:
                reasons.append("Payee history unknown, treated as a new payee")
            elif t["beneficiary_first_seen"]:
                reasons.append("Payee account has never received money before")
            elif t["beneficiary_prior_txns"] < 3:
                reasons.append("Payee account has very little payment history")
            if t["amount_vs_history_percentile"] >= 95:
                reasons.append("Amount is much larger than your usual payments")
            if t["txn_count_last_hour"] >= 3:
                reasons.append("Several payments in the last hour")
        if not reasons:
            reasons.append("No scam signals found")
        action, action_text = ACTIONS[level]

        return {
            "risk_score": score,
            "band": level,
            "action": action,
            "action_text": action_text,
            "reasons": reasons,
            "flags": rules.flags,
            "text_prob": None if text_prob is None else round(text_prob, 4),
            "txn_prob": None if txn_prob is None else round(txn_prob, 4),
            "rule_prob": None if rule_prob is None else round(rule_prob, 4),
            "model_version": C.MODEL_VERSION,
            "signal_mode": mode,
            "hard_rule_floor": rules.floor,
            "disclaimer": C.PIN_DISCLAIMER if rules.show_pin_disclaimer else None,
            "ask_user": C.FEEDBACK_QUESTION if rules.ask_feedback else None,
            "data_note": "Trained on synthetic and public data; transaction model uses " + C.PAYSIM_LABEL,
        }

    # ----------------------------------------------------------------- feedback
    def apply_feedback(self, text: str, result: dict, answer_yes: bool, feedback_file: Path = C.FEEDBACK_FILE) -> dict:
        """Yes: someone asked them to share an OTP/PIN -> band forced to high, score raised.
        No: score lowered by 40%, never below the hard-rule floor (band recomputed).
        Stores only flags, the answer, scores and a keyed hash of the text (never the text)."""
        if not result.get("ask_user"):
            raise ValueError("feedback is only collected when asks_otp or asks_pin fired")
        before = int(result["risk_score"])
        floor = int(result.get("hard_rule_floor", 0))
        bands = self.bands[result["signal_mode"]]
        if answer_yes:
            after = min(100, max(before + 25, int(np.ceil(min(bands["high"], 100)))))
            level = "high"
        else:
            after = max(floor, int(round(before * 0.6)))
            level = band(after, bands, floor)
        action, action_text = ACTIONS[level]
        out = {**result, "risk_score": after, "band": level, "action": action, "action_text": action_text,
               "ask_user": None,
               "reasons": result["reasons"] + ["You said someone asked you to share this" if answer_yes
                                               else "You said nobody asked you to share this"]}
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "model_version": C.MODEL_VERSION, "text_hmac": text_hmac(text),
                  "flags": result["flags"], "answer": "yes" if answer_yes else "no",
                  "risk_before": before, "risk_after": after}
        feedback_file.parent.mkdir(parents=True, exist_ok=True)
        with open(feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return out
