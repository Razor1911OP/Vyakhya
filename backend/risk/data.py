"""
Loaders for the text corpus (UCI SMS Spam + Vyakhya synthetic) and synthetic transactions.
Source files are opened read-only and never modified.

Folds (leave-one-family-out):
  kyc_refund, digital_arrest, lottery, upi_collect, job_task : synthetic scam families
  generic_spam                                                : all UCI spam (sixth fold)
  Benign synthetic rows already carry a template-level fold in messages.csv.
  UCI ham is spread over all 6 folds by a hash of its normalised text, so exact duplicates
  (UCI has ~400) always land in the same fold.
"""
import hashlib
import json

import numpy as np
import pandas as pd

from risk.config import MESSAGES_PATH, SMS_SPAM_PATH, TRANSACTIONS_PATH
from risk.rules import normalise

SYNTH_FOLDS = ["kyc_refund", "digital_arrest", "lottery", "upi_collect", "job_task"]
FOLDS = SYNTH_FOLDS + ["generic_spam"]

# Hard-negative groups for reporting (benign rows that look like scams on the surface).
# Each takes the corpus DataFrame and returns a boolean mask (combined with label == 0 by the caller).
# bank_genuine templates: _01 debit alert, _02 KYC reminder, _03 credit alert.
HARD_NEGATIVE_GROUPS = {
    "OTP notices": lambda d: d["subtype"] == "otp_notice",
    "Debit/credit alerts": lambda d: (d["subtype"] == "bank_genuine") & ~d["template_id"].str.endswith("_02"),
    "Genuine KYC reminders": lambda d: (d["subtype"] == "bank_genuine") & d["template_id"].str.endswith("_02"),
    "Bill reminders / receipts": lambda d: d["subtype"] == "merchant_bill",
    "Delivery updates": lambda d: d["subtype"] == "delivery",
    "Genuine refunds": lambda d: d["subtype"] == "refund_genuine",
    "UCI everyday SMS (ham)": lambda d: d["subtype"] == "uci_ham",
}


def _digest(text: str) -> str:
    return hashlib.sha1(normalise(text).lower().encode("utf-8")).hexdigest()


def load_uci(path=SMS_SPAM_PATH) -> pd.DataFrame:
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\r\n")
            if not line:
                continue
            label, text = line.split("\t", 1)
            d = _digest(text)
            spam = label.strip().lower() == "spam"
            rows.append(dict(
                msg_id=f"uci_{i:05d}", text=text, label=int(spam), source="uci",
                family="generic_spam" if spam else "benign", subtype="uci_spam" if spam else "uci_ham",
                language="en", template_id=f"uci_{d[:12]}",
                lofo_fold="generic_spam" if spam else FOLDS[int(d, 16) % len(FOLDS)],
            ))
    df = pd.DataFrame(rows)
    # A text that appears as both ham and spam would put one template in two folds: resolve to spam's fold.
    spam_templates = set(df.loc[df.label == 1, "template_id"])
    df.loc[df.template_id.isin(spam_templates), "lofo_fold"] = "generic_spam"
    return df


def load_synthetic_messages(path=MESSAGES_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"msg_id": str, "text": str, "template_id": str}, encoding="utf-8")
    df["label"] = df["label"].astype(int)
    df["source"] = "synthetic"
    df["subtype"] = df["template_id"].str.rsplit("_", n=2).str[0]
    return df


def load_text_corpus() -> pd.DataFrame:
    cols = ["msg_id", "text", "label", "source", "family", "subtype", "language", "template_id", "lofo_fold"]
    return pd.concat([load_uci()[cols], load_synthetic_messages()[cols]], ignore_index=True)


def load_synthetic_transactions(path=TRANSACTIONS_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"msg_id": str})
    df["label"] = df["label"].astype(int)
    df["odd_hour"] = ((df["hour"] < 6) | (df["hour"] >= 22)).astype(int)
    return df


def load_handwritten(path=None) -> pd.DataFrame:
    """Hand-written test set. NEVER used for training, calibration, weights or thresholds."""
    from risk.config import HANDWRITTEN_PATH
    df = pd.read_csv(path or HANDWRITTEN_PATH, dtype={"hw_id": str, "text": str}, encoding="utf-8")
    df["label"] = df["label"].astype(int)
    df["direction"] = df["direction"].fillna("debit")
    return df


def load_validation(path=None) -> pd.DataFrame:
    """Benign validation set. Used ONLY to pick message-only band cutoffs; never for training or rule edits."""
    from risk.config import VALIDATION_PATH
    df = pd.read_csv(path or VALIDATION_PATH, dtype={"val_id": str, "text": str}, encoding="utf-8")
    df["label"] = df["label"].astype(int)
    assert (df["label"] == 0).all(), "validation set must be benign only"
    df["direction"] = df["direction"].fillna("debit")
    return df


def char_ngrams(text: str, n: int = 5) -> set:
    t = normalise(text).lower()
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 1))}


def handwritten_leakage(hw_texts, corpus_texts, threshold=0.5) -> dict:
    """Exact-duplicate and near-duplicate (char 5-gram Jaccard) check of hand-written vs training texts.
    Returns only ids/scores, never text."""
    corpus_norm = {normalise(t).lower() for t in corpus_texts}
    corpus_grams = [char_ngrams(t) for t in corpus_texts]
    exact, max_j = [], []
    for t in hw_texts:
        exact.append(normalise(t).lower() in corpus_norm)
        g = char_ngrams(t)
        best = 0.0
        for cg in corpus_grams:
            inter = len(g & cg)
            if inter:
                j = inter / len(g | cg)
                if j > best:
                    best = j
        max_j.append(best)
    max_j = np.array(max_j)
    return {"exact_duplicates": int(sum(exact)), "max_jaccard": round(float(max_j.max()), 3),
            "mean_max_jaccard": round(float(max_j.mean()), 3),
            f"n_above_{threshold}": int((max_j >= threshold).sum()), "per_row_max_jaccard": max_j}


def check_template_leakage(train_template_ids, test_template_ids) -> None:
    shared = set(train_template_ids) & set(test_template_ids)
    if shared:
        raise AssertionError(f"template leakage: {len(shared)} template_ids on both sides, e.g. {sorted(shared)[:3]}")


def read_feedback(path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
