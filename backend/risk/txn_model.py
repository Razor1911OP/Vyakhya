"""
Signal C: transaction model.

C1  PaySim XGBoost, behaviour-only: amount, type, hour, beneficiary_prior_txns, beneficiary_first_seen.
    Trained on public synthetic mobile-money data (PaySim), NOT UPI.
    - Payee history = count of EARLIER rows to the same nameDest (file order is step order).
    - No balances, balance-error features or drain ratio (simulator artefacts).
    - Only TRANSFER / CASH_OUT rows (PaySim has fraud only there); isFlaggedFraud rows dropped.
    - Time split: fit on steps < 400, isotonic calibration on 400-499, test on >= 500.
    - At inference a UPI payment is mapped to PaySim type TRANSFER.

C2  Sender-history model on data/transactions.csv (synthetic): logistic regression on
    [logit(C1 prob), amount vs own history, velocity (last hour / last day), fan-out],
    isotonic-calibrated with group folds. Its output is the calibrated txn_prob.
"""
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from risk.config import PAYSIM_LABEL, SEED
from risk.data import SYNTH_FOLDS
from risk.metrics import auc, recall_at_fpr

PAYSIM_FEATURES = ["amount", "type", "hour", "beneficiary_prior_txns", "beneficiary_first_seen"]
PAYSIM_TYPES = ["CASH_OUT", "TRANSFER"]
ALL_PAYSIM_TYPES = ["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]
FIT_END, CAL_END = 400, 500
UPI_AS_PAYSIM_TYPE = "TRANSFER"
SENDER_FEATURES = ["paysim_logit", "amount_pct", "txn_count_last_hour", "txn_count_last_day", "fan_out_count"]


# ----------------------------------------------------------------------------- C1 PaySim
def load_paysim(path) -> pd.DataFrame:
    parts = []
    reader = pd.read_csv(path, usecols=["step", "type", "amount", "nameDest", "isFraud", "isFlaggedFraud"],
                         dtype={"step": np.int16, "type": str, "amount": np.float64, "nameDest": str,
                                "isFraud": np.int8, "isFlaggedFraud": np.int8}, chunksize=1_000_000)
    for ch in reader:
        dest = ch.pop("nameDest")
        ch["dest"] = dest.str[1:].astype(np.int64) * 2 + dest.str[0].eq("M").astype(np.int64)
        ch["type"] = pd.Categorical(ch["type"], categories=ALL_PAYSIM_TYPES)
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    assert df["step"].is_monotonic_increasing, "PaySim rows must be in step order for no-lookahead history"
    prior = df.groupby("dest", sort=False).cumcount()   # counts strictly earlier rows
    df["beneficiary_prior_txns"] = prior.astype(np.int32)
    df["beneficiary_first_seen"] = (prior == 0).astype(np.int8)
    df["hour"] = (df["step"] % 24).astype(np.int8)
    keep = df["type"].isin(PAYSIM_TYPES) & (df["isFlaggedFraud"] == 0)
    out = df.loc[keep, ["step", "type", "amount", "hour", "beneficiary_prior_txns",
                        "beneficiary_first_seen", "isFraud"]].reset_index(drop=True)
    out["type"] = pd.Categorical(out["type"].astype(str), categories=PAYSIM_TYPES)
    return out


def _paysim_X(frame: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame({
        "amount": frame["amount"].astype(float).to_numpy(),
        "type": pd.Categorical(frame["type"].astype(str).to_numpy(), categories=PAYSIM_TYPES),
        "hour": frame["hour"].astype(float).to_numpy(),
        "beneficiary_prior_txns": frame["beneficiary_prior_txns"].astype(float).to_numpy(),
        "beneficiary_first_seen": frame["beneficiary_first_seen"].astype(float).to_numpy(),
    })
    return X[PAYSIM_FEATURES]


def train_paysim(df: pd.DataFrame, log=print):
    y = df["isFraud"].astype(int).to_numpy()
    fit = (df["step"] < FIT_END).to_numpy()
    cal = ((df["step"] >= FIT_END) & (df["step"] < CAL_END)).to_numpy()
    test = (df["step"] >= CAL_END).to_numpy()
    pos_w = float((y[fit] == 0).sum() / (y[fit] == 1).sum())
    model = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.08, subsample=0.8,
                              colsample_bytree=0.8, tree_method="hist", enable_categorical=True,
                              scale_pos_weight=pos_w, eval_metric="aucpr", n_jobs=-1, random_state=SEED)
    model.fit(_paysim_X(df[fit]), y[fit])
    p_cal = model.predict_proba(_paysim_X(df[cal]))[:, 1]
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p_cal, y[cal])
    p_test = model.predict_proba(_paysim_X(df[test]))[:, 1]
    report = {
        "data": PAYSIM_LABEL, "features": PAYSIM_FEATURES,
        "split": f"fit step<{FIT_END}, calibrate {FIT_END}-{CAL_END - 1}, test step>={CAL_END}",
        "rows": {"fit": int(fit.sum()), "calibrate": int(cal.sum()), "test": int(test.sum())},
        "prevalence": {"fit": float(y[fit].mean()), "test": float(y[test].mean())},
        "test_roc_auc": round(auc(y[test], p_test), 4),
        "test_pr_auc": round(float(average_precision_score(y[test], p_test)), 4),
        "test_recall_at_1pct_fpr": round(recall_at_fpr(y[test], p_test, 0.01), 4),
        "test_recall_at_0_1pct_fpr": round(recall_at_fpr(y[test], p_test, 0.001), 4),
    }
    log(f"  PaySim test: ROC-AUC={report['test_roc_auc']} PR-AUC={report['test_pr_auc']} "
        f"recall@1%FPR={report['test_recall_at_1pct_fpr']}  [{PAYSIM_LABEL}]")
    return {"model": model, "calibrator": iso}, report


def paysim_prob(bundle, frame: pd.DataFrame) -> np.ndarray:
    """Calibrated PaySim probability for UPI-style payments (type mapped to TRANSFER)."""
    f = frame.copy()
    f["type"] = UPI_AS_PAYSIM_TYPE
    raw = bundle["model"].predict_proba(_paysim_X(f))[:, 1]
    return bundle["calibrator"].predict(raw)


# ------------------------------------------------------------------- C2 sender history
def sender_frame(frame: pd.DataFrame, paysim_p: np.ndarray) -> pd.DataFrame:
    p = np.clip(np.asarray(paysim_p, dtype=float), 1e-4, 1 - 1e-4)
    return pd.DataFrame({
        "paysim_logit": np.log(p / (1 - p)),
        "amount_pct": frame["amount_vs_history_percentile"].astype(float).to_numpy() / 100.0,
        "txn_count_last_hour": frame["txn_count_last_hour"].astype(float).to_numpy(),
        "txn_count_last_day": frame["txn_count_last_day"].astype(float).to_numpy(),
        "fan_out_count": frame["fan_out_count"].astype(float).to_numpy(),
    })[SENDER_FEATURES]


def _sender_pipeline() -> Pipeline:
    return Pipeline([("scale", StandardScaler()),
                     ("lr", LogisticRegression(class_weight="balanced", C=1.0, max_iter=2000, random_state=SEED))])


def fit_sender(X: pd.DataFrame, y, groups) -> CalibratedClassifierCV:
    splits = list(GroupKFold(n_splits=len(np.unique(groups))).split(X, y, groups))
    return CalibratedClassifierCV(_sender_pipeline(), method="isotonic", cv=splits).fit(X, y)


def sender_lofo_oof(X: pd.DataFrame, y, folds) -> np.ndarray:
    oof = np.full(len(y), np.nan)
    for f in SYNTH_FOLDS:
        te = folds == f
        oof[te] = fit_sender(X[~te], y[~te], folds[~te]).predict_proba(X[te])[:, 1]
    assert not np.isnan(oof).any()
    return oof
