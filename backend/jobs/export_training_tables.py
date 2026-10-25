"""
Export data/messages.csv and data/transactions.csv from data/synthetic/events.csv (read-only).

messages.csv     : msg_id, text, label, family, language, template_id, lofo_fold
transactions.csv : msg_id, user_id, label, lofo_fold, amount, amount_vs_history_percentile, hour,
                   transaction_type, direction, txn_count_last_hour, txn_count_last_day,
                   fan_out_count, new_payee, beneficiary_prior_txns, beneficiary_first_seen

lofo_fold:
  - scam rows: their family (kyc_refund, digital_arrest, lottery, upi_collect, job_task)
  - benign rows: whole TEMPLATES are spread over the 5 folds (stratified by subtype), so every
    fold has benign test rows for FPR and no template_id is ever on both sides of a split.
  (UCI SMS rows get folds at training time; the UCI file is not copied here.)

direction: 'collect' for UPI-collect scams paid via a pull request, 'credit' for benign messages
that announce money coming in (genuine refunds / credit alerts), otherwise 'debit'.

beneficiary_prior_txns / beneficiary_first_seen are a SYNTHETIC ASSUMPTION (documented here):
  scam payees: 55% never seen before, else 1 + Poisson(3) prior txns (short-lived mule accounts)
  benign payees: 3% never seen before, else lognormal(median 40, sigma 1.5) (established payees)
Usage: python jobs/export_training_tables.py
"""
import csv
import math
import random
from collections import defaultdict
from pathlib import Path

from synthetic_templates import CREDIT_TEMPLATE_INDEX

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "data" / "synthetic" / "events.csv"
SEED = 42
SCAM_FOLDS = ["kyc_refund", "digital_arrest", "lottery", "upi_collect", "job_task"]


def is_credit_template(subtype: str, template_id: str) -> bool:
    if subtype not in CREDIT_TEMPLATE_INDEX:
        return False
    allowed = CREDIT_TEMPLATE_INDEX[subtype]
    return allowed is None or int(template_id.rsplit("_", 1)[1]) in allowed


def poisson(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def main():
    with open(SRC, encoding="utf-8", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: r["event_id"])
    rng = random.Random(SEED)

    # Benign templates -> folds, stratified by subtype, deterministic
    by_subtype = defaultdict(set)
    for r in rows:
        if r["label"] == "0":
            by_subtype[r["subtype"]].add(r["template_id"])
    fold_of_template, k = {}, 0
    for subtype in sorted(by_subtype):
        templates = sorted(by_subtype[subtype])
        rng.shuffle(templates)
        for t in templates:
            fold_of_template[t] = SCAM_FOLDS[k % len(SCAM_FOLDS)]
            k += 1

    msgs, txns = [], []
    for r in rows:
        msg_id = r["event_id"].replace("evt_", "msg_")
        scam = r["label"] == "1"
        fold = r["family"] if scam else fold_of_template[r["template_id"]]
        msgs.append(dict(msg_id=msg_id, text=r["text"], label=r["label"], family=r["family"],
                         language=r["language"], template_id=r["template_id"], lofo_fold=fold))

        if scam and r["family"] == "upi_collect" and r["transaction_type"] == "DEBIT":
            direction = "collect"
        elif (not scam) and is_credit_template(r["subtype"], r["template_id"]):
            direction = "credit"
        else:
            direction = "debit"

        if scam:
            first_seen = int(rng.random() < 0.55)
            prior = 0 if first_seen else 1 + poisson(rng, 3.0)
        else:
            first_seen = int(rng.random() < 0.03)
            prior = 0 if first_seen else max(1, int(math.exp(rng.gauss(math.log(40), 1.5))))

        txns.append(dict(msg_id=msg_id, user_id=r["user_id"], label=r["label"], lofo_fold=fold,
                         amount=r["amount"], amount_vs_history_percentile=r["amount_vs_history_percentile"],
                         hour=r["hour"], transaction_type=r["transaction_type"], direction=direction,
                         txn_count_last_hour=r["txn_count_last_hour"], txn_count_last_day=r["txn_count_last_day"],
                         fan_out_count=r["fan_out_count"], new_payee=r["new_payee"],
                         beneficiary_prior_txns=prior, beneficiary_first_seen=first_seen))

    for name, data in (("messages.csv", msgs), ("transactions.csv", txns)):
        path = REPO_ROOT / "data" / name
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
        print(f"Wrote {len(data):,} rows -> {path}")

    # Leakage check + fold composition (no message text printed)
    folds_per_template = defaultdict(set)
    for m in msgs:
        folds_per_template[m["template_id"]].add(m["lofo_fold"])
    leaked = [t for t, fs in folds_per_template.items() if len(fs) > 1]
    print(f"\nTemplate leakage check: {len(folds_per_template)} templates, {len(leaked)} appear in >1 fold "
          f"-> {'PASS' if not leaked else 'FAIL ' + str(leaked[:5])}")
    print(f"\n{'fold':<16}{'scam':>6}{'benign':>8}{'benign templates':>18}")
    for fold in SCAM_FOLDS:
        s = sum(1 for m in msgs if m["lofo_fold"] == fold and m["label"] == "1")
        b = [m for m in msgs if m["lofo_fold"] == fold and m["label"] == "0"]
        print(f"{fold:<16}{s:>6}{len(b):>8}{len({m['template_id'] for m in b}):>18}")
    dirs = defaultdict(int)
    for t in txns:
        dirs[(t["label"], t["direction"])] += 1
    print("\nDirection counts (label, direction):", dict(sorted(dirs.items())))


if __name__ == "__main__":
    main()
