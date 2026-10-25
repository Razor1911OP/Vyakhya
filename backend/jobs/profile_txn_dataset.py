"""
Profile an external transaction dataset before using it for training.

Answers, with real numbers:
  1. Size, columns, nulls, date range, fraud prevalence.
  2. Fraud rate by each categorical column.
  3. Single-feature AUC per column -> flags likely LABEL LEAKS (AUC > 0.95)
     and columns carrying no signal (AUC ~ 0.5).
  4. Which Vyakhya transaction features can actually be derived from it.

Writes metrics/dataset_profile_<name>.json. Does not copy or modify the source file.
Usage: python jobs/profile_txn_dataset.py "C:/path/to/file.csv" [--label is_fraud]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[2]


def single_feature_auc(series, y):
    """AUC of one column used alone as a score. Categoricals use their fraud rate."""
    s = series.copy()
    if s.dtype == object or str(s.dtype) == "category" or s.dtype == bool:
        rates = y.groupby(s.fillna("<NA>")).mean()
        s = s.fillna("<NA>").map(rates)
    s = pd.to_numeric(s, errors="coerce").fillna(-1)
    if s.nunique() < 2:
        return 0.5
    auc = roc_auc_score(y, s)
    return float(max(auc, 1 - auc))  # direction-free


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--label", default="is_fraud")
    args = ap.parse_args()

    df = pd.read_csv(args.path)
    y = df[args.label].astype(int)
    print(f"File: {args.path.name}  rows={len(df):,}  cols={df.shape[1]}")
    print(f"Fraud rows: {y.sum():,}  prevalence={y.mean():.4%}  (about 1 in {int(round(1 / max(y.mean(), 1e-9))):,})")

    report = {"file": args.path.name, "rows": int(len(df)), "fraud_rows": int(y.sum()),
              "prevalence": float(y.mean()), "columns": {}}

    if "transaction_date" in df:
        dates = pd.to_datetime(df["transaction_date"], errors="coerce")
        report["date_range"] = [str(dates.min().date()), str(dates.max().date())]
        print(f"Date range: {report['date_range'][0]} -> {report['date_range'][1]}")
    if "customer_id" in df:
        per_cust = df.groupby("customer_id").size()
        report["customers"] = int(per_cust.size)
        print(f"Customers: {per_cust.size:,}  txns/customer median={per_cust.median():.0f} "
              f"p90={per_cust.quantile(.9):.0f} max={per_cust.max()}")

    print("\nColumn | dtype | nulls | unique | single-feature AUC")
    feature_cols = [c for c in df.columns if c not in (args.label, "transaction_id")]
    for c in feature_cols:
        auc = single_feature_auc(df[c], y)
        flag = "  <-- POSSIBLE LEAK" if auc > 0.95 else ("  (no signal)" if auc < 0.52 else "")
        report["columns"][c] = {"dtype": str(df[c].dtype), "nulls": int(df[c].isna().sum()),
                                "unique": int(df[c].nunique()), "auc": round(auc, 4)}
        print(f"  {c:<22} {str(df[c].dtype):<8} {df[c].isna().sum():>7} {df[c].nunique():>9}   {auc:.3f}{flag}")

    print("\nFraud rate by category (top 8 values per column):")
    report["fraud_rate_by_category"] = {}
    for c in feature_cols:
        if df[c].dtype == object and df[c].nunique() <= 40 and c not in ("transaction_date", "transaction_time", "customer_id"):
            rates = df.groupby(c)[args.label].agg(["mean", "size"]).sort_values("mean", ascending=False)
            report["fraud_rate_by_category"][c] = {k: [round(float(r["mean"]), 5), int(r["size"])] for k, r in rates.iterrows()}
            top = ", ".join(f"{k}={r['mean']:.3%}" for k, r in rates.head(8).iterrows())
            print(f"  {c}: {top}")

    amt_col = "transaction_amount" if "transaction_amount" in df else None
    if amt_col:
        q = [0.1, 0.5, 0.9, 0.99]
        fr, lg = df.loc[y == 1, amt_col].quantile(q), df.loc[y == 0, amt_col].quantile(q)
        report["amount_quantiles"] = {"fraud": fr.round(2).tolist(), "legit": lg.round(2).tolist(), "q": q}
        print(f"\nAmount quantiles {q}:\n  fraud: {fr.round(0).tolist()}\n  legit: {lg.round(0).tolist()}")

    if "transaction_hour" in df:
        odd = df["transaction_hour"].lt(6) | df["transaction_hour"].ge(22)
        print(f"\nFraud rate odd-hour={y[odd].mean():.3%}  daytime={y[~odd].mean():.3%}")

    # Which Vyakhya txn features are derivable?
    derivable = {
        "amount": amt_col is not None,
        "hour / odd_hour": "transaction_hour" in df,
        "amount_vs_history_percentile": {"customer_id", "transaction_date"} <= set(df.columns),
        "txn_count_last_hour / last_day": {"customer_id", "transaction_date", "transaction_time"} <= set(df.columns),
        "new_payee / fan_out_count": any(c in df for c in ("payee_id", "beneficiary_id", "receiver_id", "merchant_id")),
        "beneficiary_age": any(c in df for c in ("beneficiary_id", "payee_id")),
    }
    report["vyakhya_features_derivable"] = derivable
    print("\nVyakhya features derivable from this file:")
    for k, v in derivable.items():
        print(f"  {'YES' if v else 'NO '}  {k}")

    out = REPO_ROOT / "metrics" / f"dataset_profile_{args.path.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
