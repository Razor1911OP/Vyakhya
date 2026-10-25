"""
Probe PaySim for real vs artefactual fraud signal (honest version).

PaySim is known to give ~0.99+ AUC, largely via balance-bookkeeping artefacts
(e.g. errorBalanceOrig) that a bank cannot use pre-debit or that don't exist in UPI.
This script separates the two by training three XGBoost models on the SAME
time split, each with a stricter feature set:

  M1 all_incl_balances : everything, incl. post-transaction balances + error features
  M2 pre_debit_sender  : what a bank knows BEFORE debit: amount, type, hour,
                         sender's own balance, drain ratio, payee history
  M3 behaviour_only    : amount, type, hour, payee history (no balances at all)

Payee-history features use only EARLIER rows (no look-ahead).
Only TRANSFER and CASH_OUT are modelled (PaySim has fraud only in those types).
Writes metrics/txn_signal_probe_paysim.json.
Usage: python jobs/probe_paysim.py "C:/path/PS_...log.csv"
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLIT_STEP = 500  # train on hours 1-499, test on 500-743


def encode_name(s):
    """'C123' / 'M123' -> unique int64 without keeping millions of Python strings."""
    return s.str[1:].astype(np.int64) * 2 + (s.str[0] == "M").astype(np.int64)


def load(path):
    dtypes = {"step": np.int16, "amount": np.float64, "oldbalanceOrg": np.float64,
              "newbalanceOrig": np.float64, "oldbalanceDest": np.float64,
              "newbalanceDest": np.float64, "isFraud": np.int8, "isFlaggedFraud": np.int8}
    parts = []
    for chunk in pd.read_csv(path, dtype=dtypes, chunksize=1_000_000):
        chunk["orig"] = encode_name(chunk.pop("nameOrig"))
        chunk["dest_is_merchant"] = chunk["nameDest"].str[0].eq("M").astype(np.int8)
        chunk["dest"] = encode_name(chunk.pop("nameDest"))
        chunk["type"] = chunk["type"].astype("category")
        parts.append(chunk)
    df = pd.concat(parts, ignore_index=True)
    df["type"] = df["type"].astype("category")
    return df


def auc_free(y, s):
    s = pd.Series(np.asarray(s, dtype=float)).fillna(-1e18)
    if s.nunique() < 2:
        return 0.5
    a = roc_auc_score(y, s)
    return float(max(a, 1 - a))


def recall_at_fpr(y, s, max_fpr=0.01):
    fpr, tpr, _ = roc_curve(y, s)
    return float(tpr[fpr <= max_fpr].max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    args = ap.parse_args()
    t0 = time.time()

    df = load(args.path)
    y_all = df["isFraud"]
    print(f"Loaded {len(df):,} rows in {time.time() - t0:.0f}s. Steps {df.step.min()}-{df.step.max()} (1 step = 1 hour)")
    print(f"Fraud rows: {int(y_all.sum()):,}  prevalence={y_all.mean():.4%}  (about 1 in {int(1 / y_all.mean()):,})")
    print("\nFraud by type:")
    for t, g in df.groupby("type", observed=True)["isFraud"]:
        print(f"  {t:<9} rows={len(g):>9,}  fraud={int(g.sum()):>6,}  rate={g.mean():.4%}")
    flagged = df["isFlaggedFraud"]
    print(f"isFlaggedFraud=1 rows: {int(flagged.sum())} (all fraud: {bool(y_all[flagged == 1].all())}) -> dropped, it is a rule output")

    # Sender history: does PaySim even have repeat senders?
    orig_counts = df["orig"].value_counts()
    print(f"\nSenders: {len(orig_counts):,}; senders with >1 txn: {(orig_counts > 1).sum():,} "
          f"-> per-sender history is {'NOT ' if (orig_counts > 1).mean() < 0.01 else ''}usable")

    # Payee history from EARLIER rows only (file is ordered by step)
    g = df.groupby("dest", sort=False)
    df["dest_prior_txns"] = g.cumcount().astype(np.int32)
    df["dest_first_seen"] = (df["dest_prior_txns"] == 0).astype(np.int8)
    df["dest_prior_amount_sum"] = (g["amount"].cumsum() - df["amount"]).astype(np.float64)
    df["hour"] = (df["step"] % 24).astype(np.int8)
    df["log_amount"] = np.log1p(df["amount"])
    df["drain_ratio"] = df["amount"] / (df["oldbalanceOrg"] + 1)
    df["empties_account"] = ((df["oldbalanceOrg"] > 0) & (df["amount"] >= df["oldbalanceOrg"])).astype(np.int8)
    df["errorBalanceOrig"] = df["newbalanceOrig"] + df["amount"] - df["oldbalanceOrg"]
    df["errorBalanceDest"] = df["oldbalanceDest"] + df["amount"] - df["newbalanceDest"]
    df["dest_bal_zero_both"] = ((df["oldbalanceDest"] == 0) & (df["newbalanceDest"] == 0)).astype(np.int8)

    # Restrict to the only types that contain fraud
    m = df["type"].isin(["TRANSFER", "CASH_OUT"]) & (df["isFlaggedFraud"] == 0)
    d = df.loc[m].reset_index(drop=True)
    d["type"] = d["type"].cat.remove_unused_categories()
    y = d["isFraud"].astype(int)
    print(f"\nModelling subset TRANSFER+CASH_OUT: {len(d):,} rows, prevalence {y.mean():.4%}")

    probe_cols = ["amount", "oldbalanceOrg", "drain_ratio", "empties_account", "errorBalanceOrig",
                  "errorBalanceDest", "dest_bal_zero_both", "newbalanceOrig", "oldbalanceDest",
                  "dest_prior_txns", "dest_first_seen", "hour"]
    print("\nSingle-feature AUC (>0.95 = one column nearly gives away the label):")
    single = {}
    for c in probe_cols:
        single[c] = round(auc_free(y, d[c]), 4)
        flag = "  <-- ARTEFACT/LEAK RISK" if single[c] > 0.95 else ""
        print(f"  {c:<22} {single[c]:.3f}{flag}")
    rates = {
        "fraud_empties_account": float(d.loc[y == 1, "empties_account"].mean()),
        "legit_empties_account": float(d.loc[y == 0, "empties_account"].mean()),
        "fraud_dest_bal_zero_both": float(d.loc[y == 1, "dest_bal_zero_both"].mean()),
        "legit_dest_bal_zero_both": float(d.loc[y == 0, "dest_bal_zero_both"].mean()),
    }
    print(f"  Fraud empties sender account: {rates['fraud_empties_account']:.1%} vs legit {rates['legit_empties_account']:.1%}")
    print(f"  Dest balances both 0:         {rates['fraud_dest_bal_zero_both']:.1%} vs legit {rates['legit_dest_bal_zero_both']:.1%}")

    payee = ["dest_prior_txns", "dest_first_seen", "dest_prior_amount_sum"]
    feature_sets = {
        "M1_all_incl_balances": ["type", "log_amount", "hour", "oldbalanceOrg", "newbalanceOrig",
                                 "oldbalanceDest", "newbalanceDest", "errorBalanceOrig", "errorBalanceDest"] + payee,
        "M2_pre_debit_sender": ["type", "log_amount", "hour", "oldbalanceOrg", "drain_ratio", "empties_account"] + payee,
        "M3_behaviour_only": ["type", "log_amount", "hour"] + payee,
    }
    train = d["step"] < SPLIT_STEP
    test = ~train
    yt = y[test]
    print(f"\nTime split: train steps < {SPLIT_STEP} ({int(train.sum()):,} rows, prev {y[train].mean():.4%}) | "
          f"test ({int(test.sum()):,} rows, prev {yt.mean():.4%})")
    pos_w = float((y[train] == 0).sum() / (y[train] == 1).sum())

    results = {}
    for name, cols in feature_sets.items():
        t1 = time.time()
        model = xgb.XGBClassifier(n_estimators=300, max_depth=6, learning_rate=0.08, subsample=0.8,
                                  colsample_bytree=0.8, tree_method="hist", enable_categorical=True,
                                  scale_pos_weight=pos_w, eval_metric="aucpr", n_jobs=-1, random_state=42)
        model.fit(d.loc[train, cols], y[train])
        p = model.predict_proba(d.loc[test, cols])[:, 1]
        gain = model.get_booster().get_score(importance_type="gain")
        top = sorted(gain.items(), key=lambda kv: -kv[1])[:5]
        results[name] = {
            "features": cols,
            "roc_auc": round(float(roc_auc_score(yt, p)), 4),
            "pr_auc": round(float(average_precision_score(yt, p)), 4),
            "recall_at_fpr_1pct": round(recall_at_fpr(yt, p, 0.01), 4),
            "recall_at_fpr_0_1pct": round(recall_at_fpr(yt, p, 0.001), 4),
            "train_seconds": round(time.time() - t1, 1),
            "top_features_by_gain": {k: round(v, 1) for k, v in top},
        }
        r = results[name]
        print(f"\n{name}  ({r['train_seconds']}s)")
        print(f"  ROC-AUC={r['roc_auc']}  PR-AUC={r['pr_auc']} (chance={yt.mean():.4f})  "
              f"recall@FPR1%={r['recall_at_fpr_1pct']}  recall@FPR0.1%={r['recall_at_fpr_0_1pct']}")
        print("  top gain: " + ", ".join(f"{k}={v:.0f}" for k, v in top))

    out = REPO_ROOT / "metrics" / "txn_signal_probe_paysim.json"
    out.write_text(json.dumps({
        "data_source": "PaySim (public synthetic mobile-money simulator, Kaggle ealaxi/paysim1)",
        "rows": int(len(df)), "prevalence": float(y_all.mean()),
        "modelling_subset": "TRANSFER+CASH_OUT, isFlaggedFraud dropped", "split": f"step < {SPLIT_STEP} train",
        "single_feature_auc": single, "artefact_rates": rates, "models": results}, indent=2), encoding="utf-8")
    print(f"\nSaved {out}  (total {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
