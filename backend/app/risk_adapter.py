"""
Adapter: /score request -> frozen risk engine (model_registry/risk/<version>/) -> ScoreResponse.

Tier mapping (documented policy):
  band low -> LOW, medium -> MEDIUM, high -> HIGH;
  any hard-rule hit (floor 90: PIN/collect to receive money, or amount mismatch) -> CRITICAL + soft_hold.
  Soft-hold is limited to hard-rule hits because those had 0 benign hits on synthetic data; the score-based
  high band does not hold money (its realistic FPR on the hand-written set is far above target).
Notes:
  - Raw message text is used in memory only (rules need amounts); never logged or stored. The response
    carries only the redacted preview + hash.
  - Context signals (call, screen-share, device...) are NOT used by the frozen risk engine; they are
    accepted for API compatibility only.
  - Balance fields are accepted for compatibility and ignored (PaySim balance features are artefacts).
"""
import re
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from risk import config as RC  # noqa: E402
from risk.engine import RiskEngine  # noqa: E402
from risk.rules import RULES_VERSION  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.engine.tier_policy import get_tier_policy  # noqa: E402
from backend.app.engine.validate_redact import validate_and_redact  # noqa: E402
from backend.app.schemas import ModelVersion, ReasonCode, ScoreRequest, ScoreResponse, TierEnum  # noqa: E402

_engine = None
BAND_TO_TIER = {"low": TierEnum.LOW, "medium": TierEnum.MEDIUM, "high": TierEnum.HIGH}


def get_risk_engine() -> RiskEngine:
    global _engine
    if _engine is None:
        _engine = RiskEngine()
    return _engine


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48]


def score_request(req: ScoreRequest) -> ScoreResponse:
    t0 = time.perf_counter()
    redacted_meta, _ = validate_and_redact(req.message_text)
    tx = req.transaction
    txn = {"amount": tx.amount, "hour": tx.hour,
           "direction": tx.direction or "debit",
           "beneficiary_prior_txns": tx.beneficiary_prior_txns,
           "amount_vs_history_percentile": tx.amount_vs_history_percentile,
           "txn_count_last_hour": tx.txn_count_last_hour, "txn_count_last_day": tx.txn_count_last_day,
           "fan_out_count": tx.fan_out_count}
    r = get_risk_engine().score(text=req.message_text, txn=txn)

    hard = r["hard_rule_floor"] >= RC.HARD_RULE_FLOOR
    tier = TierEnum.CRITICAL if hard else BAND_TO_TIER[r["band"]]
    soft_hold = bool(hard and settings.soft_hold_enabled)
    conf = round(r["risk_score"] / 100, 2)
    reasons = [ReasonCode(code=_slug(x), explanation=x, confidence=1.0 if hard and i < 2 else conf)
               for i, x in enumerate(r["reasons"])]
    friction_type, friction_message = get_tier_policy().get_friction_config(tier, reasons)
    if r["disclaimer"]:
        friction_message = (friction_message + "\n\n" if friction_message else "") + r["disclaimer"]

    comps = {k: r[k] for k in ("text_prob", "txn_prob", "rule_prob") if r[k] is not None}
    comps["hard_rule_floor"] = float(r["hard_rule_floor"])
    return ScoreResponse(
        risk_score=int(r["risk_score"]), tier=tier, soft_hold=soft_hold, reason_codes=reasons,
        model_versions=[
            ModelVersion(model_name="vyakhya_risk", version=RC.MODEL_VERSION, used=True),
            ModelVersion(model_name="rules", version=RULES_VERSION, used=True),
            ModelVersion(model_name="tfidf_lr_text", version=RC.MODEL_VERSION, used=r["text_prob"] is not None),
            ModelVersion(model_name="paysim_xgb_behaviour", version=RC.MODEL_VERSION, used=r["txn_prob"] is not None),
        ],
        latency_ms=int(round((time.perf_counter() - t0) * 1000)),
        component_scores=comps, friction_type=friction_type, friction_message=friction_message,
        redacted_input=redacted_meta,
    )
