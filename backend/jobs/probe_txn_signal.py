"""
Probe whether a transaction dataset has learnable fraud signal (honest version).

Fixes a flaw in profile_txn_dataset.py: high-cardinality columns (customer_id,
date, time) were target-encoded IN-SAMPLE, which memorises labels and inflates AUC.
Here they are encoded OUT-OF-FOLD.

Then tests leak-free per-customer history features (computed from PAST rows only)
and an XGBoost baseline with a TIME split (train < 2023-01-01, test >= 2023-01-01).

Writes metrics/txn_signal_probe_<name>.json.
Usage: python jobs/probe_txn_signal.py "C:/path/to/file.csv"
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.model_selection import KFold

REPO_ROOT = Path(__file__).resolve().parents[2]
LABEL = "is_fraud"
SPLIT_DATE = "2023-01-01"


def auc_free(y, s):
    s = pd.Series(s).fillna(-1e9)
    if s.nunique() < 2:
        return 0.5
    a = roc_auc_score(y, s)
    return float(max(a, 1 - a))


def oof_target_encode(col, y, n_splits=5, seed=0):
    """Each row is encoded with fraud rates learned on the OTHER folds only."""
    out = np.full(len(col), y.mean())
    for tr, va in KFold(n_splits, shuffle=True, random_state=seed).split(col):
        rates = y.iloc[tr].groupby(col.iloc[tr]).mean()
        out[va] = col.iloc[va].map(rates).fillna(y.iloc[tr].mean()).to_numpy()
    return out


def recall_at_fpr(y, s, max_fpr=0.01):
    fpr, tpr, thr = roc_curve(y, s)
    ok = fpr <= max_fpr
    i = np.argmax(tpr[ok])
    return float(tpr[ok][i]), float(thr[ok][i])


def add_history_features(df):
    """Per-customer features from strictly earlier transactions (no look-ahead)."""
    df = df.sort_values(["customer_id", "ts"]).copy()
    la = np.log1p(df["transaction_amount"])
    df["log_amount"] = la
    g = df.groupby("customer_id", sort=False)  # built after log_amount exists
    df["past_n"] = g.cumcount()
    csum = la.groupby(df["customer_id"]).cumsum() - la
    csq = (la ** 2).groupby(df["customer_id"]).cumsum() - la ** 2
    n = df["past_n"].replace(0, np.nan)
    mean = csum / n
    var = (csq / n - mean ** 2).clip(lower=0)
    std = np.sqrt(var).where(df["past_n"] >= 2)
    df["amt_z_vs_past"] = (la - mean) / (std + 0.25)
    df["amt_minus_past_mean"] = la - mean
    prev = g["log_amount"].shift()
    df["amt_vs_past_max"] = la - prev.groupby(df["customer_id"]).cummax()
    df["hours_since_prev"] = g["ts"].diff().dt.total_seconds() / 3600
    df["same_day_count"] = df.groupby(["customer_id", "transaction_date"]).cumcount()
    df["amt_to_balance"] = df["transaction_amount"] / (df["account_balance"].abs() + 1)
    return df.sort_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    args = ap.parse_args()
    t0 = time.time()

    df = pd.read_csv(args.path)
    df["ts"] = pd.to_datetime(df["transaction_date"] + " " + df["transaction_time"], errors="coerce")
    y = df[LABEL].astype(int)
    print(f"Loaded {len(df):,} rows, prevalence {y.mean():.4%}  ({time.time() - t0:.0f}s)")

    # 1. Honest (out-of-fold) check of the suspected leaks
    print("\n1) Out-of-fold AUC for high-cardinality columns (in-sample value in brackets):")
    leak_check = {}
    in_sample = {"customer_id": 0.977, "transaction_date": 0.674, "transaction_time": 0.653}
    for c in in_sample:
        a = auc_free(y, oof_target_encode(df[c], y))
        leak_check[c] = round(a, 4)
        print(f"   {c:<18} OOF AUC = {a:.3f}   [in-sample {in_sample[c]}]")
    repeat = df.groupby("customer_id")[LABEL].sum()
    print(f"   customers with >=1 fraud: {(repeat > 0).sum():,}; with >=2 frauds: {(repeat >= 2).sum():,}")

    # 2. History features
    df = add_history_features(df)
    hist_cols = ["log_amount", "amt_z_vs_past", "amt_minus_past_mean", "amt_vs_past_max",
                 "hours_since_prev", "same_day_count", "past_n", "amt_to_balance"]
    print("\n2) Single-feature AUC of leak-free history features:")
    hist_auc = {}
    for c in hist_cols:
        a = auc_free(y, df[c])
        hist_auc[c] = round(a, 4)
        print(f"   {c:<22} {a:.3f}")

    # 3. XGBoost, time split
    cat_cols = ["account_type", "transaction_type", "transaction_direction", "merchant_category",
                "state", "loan_type", "transaction_status", "channel", "kyc_status"]
    num_cols = ["transaction_amount", "account_balance", "credit_score", "has_loan", "emi_amount",
                "transaction_hour"] + hist_cols
    X = df[cat_cols + num_cols].copy()
    for c in cat_cols:
        X[c] = X[c].fillna("None").astype("category")
    train = df["ts"] < SPLIT_DATE
    test = ~train & df["ts"].notna()
    pos_w = float((y[train] == 0).sum() / max((y[train] == 1).sum(), 1))

    model = xgb.XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.05, subsample=0.8,
                              colsample_bytree=0.8, tree_method="hist", enable_categorical=True,
                              scale_pos_weight=pos_w, eval_metric="aucpr", n_jobs=-1, random_state=42)
    t1 = time.time()
    model.fit(X[train], y[train])
    p = model.predict_proba(X[test])[:, 1]
    yt = y[test]
    rec, thr = recall_at_fpr(yt, p, 0.01)
    res = {
        "train_rows": int(train.sum()), "test_rows": int(test.sum()),
        "test_prevalence": float(yt.mean()),
        "roc_auc": round(float(roc_auc_score(yt, p)), 4),
        "pr_auc": round(float(average_precision_score(yt, p)), 4),
        "recall_at_fpr_1pct": round(rec, 4), "threshold_at_fpr_1pct": thr,
        "train_seconds": round(time.time() - t1, 1),
    }
    imp = model.get_booster().get_score(importance_type="gain")
    top = sorted(imp.items(), key=lambda kv: -kv[1])[:10]
    res["top_features_by_gain"] = {k: round(v, 2) for k, v in top}

    print(f"\n3) XGBoost, time split (train < {SPLIT_DATE}): train={res['train_rows']:,} test={res['test_rows']:,}")
    print(f"   ROC-AUC = {res['roc_auc']}")
    print(f"   PR-AUC  = {res['pr_auc']}   (chance level = prevalence = {res['test_prevalence']:.4f})")
    print(f"   Recall at FPR <= 1% = {res['recall_at_fpr_1pct']}")
    print(f"   Train time {res['train_seconds']}s")
    print("   Top features by gain:")
    for k, v in top:
        print(f"     {k:<22} {v:.1f}")

    out = REPO_ROOT / "metrics" / f"txn_signal_probe_{args.path.stem}.json"
    out.write_text(json.dumps({"data_source": "public (Kaggle-style) file, labels origin unknown",
                               "oof_leak_check": leak_check, "history_feature_auc": hist_auc,
                               "xgb_time_split": res}, indent=2), encoding="utf-8")
    print(f"\nSaved {out}  (total {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
