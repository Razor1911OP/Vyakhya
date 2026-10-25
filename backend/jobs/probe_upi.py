"""
Probe the UPI 2024 CSVs (raw / clean / standardized / featured + segment_profiles)
for usable fraud signal. Read-only. Writes metrics/txn_signal_probe_upi2024.json.

Checks: are the 4 files the same rows; prevalence; leak-prone columns
(daily_fraud_rate, segment fraud_rate are computed FROM labels); single-feature
AUC; XGBoost on a time split (train Jan-Sep, test Oct-Dec) with leaky columns removed.
Usage: python jobs/probe_upi.py <downloads_dir>
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve

REPO_ROOT = Path(__file__).resolve().parents[2]


def auc_free(y, s):
    s = pd.Series(np.asarray(s, dtype=float)).fillna(-1e18)
    if s.nunique() < 2:
        return 0.5
    a = roc_auc_score(y, s)
    return float(max(a, 1 - a))


def main():
    d = Path(sys.argv[1])
    t0 = time.time()
    files = {k: d / f"upi_transactions_{k}.csv" for k in ["2024_raw", "clean", "standardized", "featured"]}
    dfs = {k: pd.read_csv(p) for k, p in files.items()}
    for k, df in dfs.items():
        print(f"{k:<13} rows={len(df):>8,} cols={df.shape[1]:>3}")
    base = dfs["clean"]
    same_ids = all(dfs[k].iloc[:, 0].equals(base["transaction_id"]) for k in dfs)
    same_labels = all(dfs[k]["fraud_flag"].equals(base["fraud_flag"]) for k in dfs)
    print(f"Same transaction ids in all 4: {same_ids}; same labels: {same_labels}")

    df = dfs["featured"].copy()
    y = df["fraud_flag"].astype(int)
    print(f"\nFraud: {int(y.sum()):,} / {len(df):,}  prevalence={y.mean():.4%} (1 in {int(1 / y.mean())})")
    print("ID columns present (sender/receiver/VPA/device id)? ",
          [c for c in df.columns if any(t in c.lower() for t in ("vpa", "upi_id", "sender_id", "receiver_id", "device_id", "account"))] or "NONE")

    print("\nSingle-feature AUC (categoricals scored by in-sample fraud rate; low cardinality so safe):")
    single = {}
    skip = {"transaction_id", "timestamp", "fraud_flag", "date_only"}
    for c in df.columns:
        if c in skip:
            continue
        s = df[c]
        if s.dtype == object or s.dtype == bool:
            s = s.astype(str).map(y.groupby(s.astype(str)).mean())
        single[c] = round(auc_free(y, s), 4)
        flag = "  <-- computed from labels (LEAK)" if c in ("daily_fraud_rate",) else ""
        print(f"  {c:<20} {single[c]:.3f}{flag}")

    seg = pd.read_csv(d / "segment_profiles.csv")
    m = df.merge(seg[["sender_state", "sender_age_group", "fraud_rate"]], on=["sender_state", "sender_age_group"], how="left")
    seg_auc = auc_free(y, m["fraud_rate"])
    print(f"\nsegment_profiles: {len(seg)} segments (state x age). Segment fraud_rate as a score: AUC={seg_auc:.3f} "
          f"(in-sample aggregate of the label -> leak if used as a feature)")

    # XGBoost, time split, leaky/derived-from-label columns removed
    df["ts"] = pd.to_datetime(df["timestamp"])
    feats = ["transaction_type", "category", "amount", "status", "sender_age_group", "receiver_age_group",
             "sender_state", "sender_bank", "receiver_bank", "device_type", "network_type", "hour",
             "day_of_week", "is_weekend", "is_night"]
    X = df[feats].copy()
    for c in X.columns:
        if X[c].dtype == object or X[c].dtype == bool:
            X[c] = X[c].astype(str).astype("category")
    train = df["ts"] < "2024-10-01"
    test = ~train
    pw = float((y[train] == 0).sum() / max((y[train] == 1).sum(), 1))
    model = xgb.XGBClassifier(n_estimators=300, max_depth=5, learning_rate=0.05, subsample=0.8,
                              colsample_bytree=0.8, tree_method="hist", enable_categorical=True,
                              scale_pos_weight=pw, random_state=42, n_jobs=-1)
    model.fit(X[train], y[train])
    p = model.predict_proba(X[test])[:, 1]
    yt = y[test]
    fpr, tpr, _ = roc_curve(yt, p)
    res = {"train_rows": int(train.sum()), "test_rows": int(test.sum()), "test_prevalence": float(yt.mean()),
           "roc_auc": round(float(roc_auc_score(yt, p)), 4),
           "pr_auc": round(float(average_precision_score(yt, p)), 4),
           "recall_at_fpr_1pct": round(float(tpr[fpr <= 0.01].max()), 4)}
    print(f"\nXGBoost time split (train Jan-Sep 2024, test Oct-Dec), no leaky columns:")
    print(f"  train={res['train_rows']:,} test={res['test_rows']:,}  ROC-AUC={res['roc_auc']}  "
          f"PR-AUC={res['pr_auc']} (chance={res['test_prevalence']:.4f})  recall@FPR1%={res['recall_at_fpr_1pct']}")

    out = REPO_ROOT / "metrics" / "txn_signal_probe_upi2024.json"
    out.write_text(json.dumps({"files_identical_rows": bool(same_ids and same_labels), "rows": int(len(df)),
                               "prevalence": float(y.mean()), "single_feature_auc": single,
                               "segment_fraud_rate_auc": round(seg_auc, 4), "xgb_time_split": res}, indent=2),
                   encoding="utf-8")
    print(f"\nSaved {out}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
