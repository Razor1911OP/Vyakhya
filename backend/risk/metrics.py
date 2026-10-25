"""Metric helpers. Scores are on any monotone scale (0-100 risk or 0-1 probability)."""
import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve


def recall_at_fpr(y, s, max_fpr=0.01):
    y, s = np.asarray(y), np.asarray(s, dtype=float)
    if y.min() == y.max():
        return float("nan")
    fpr, tpr, _ = roc_curve(y, s)
    return float(tpr[fpr <= max_fpr].max())


def auc(y, s):
    y = np.asarray(y)
    return float("nan") if len(y) == 0 or y.min() == y.max() else float(roc_auc_score(y, s))


def threshold_at_fpr(benign_scores, max_fpr):
    """Smallest threshold t with share(benign >= t) <= max_fpr. Exact under ties."""
    s = np.sort(np.asarray(benign_scores, dtype=float))
    if len(s) == 0:
        return float("inf")
    uniq = np.unique(s)
    share_ge = 1.0 - np.searchsorted(s, uniq, side="left") / len(s)
    ok = np.nonzero(share_ge <= max_fpr)[0]
    return float(uniq[ok[0]]) if len(ok) else float(np.nextafter(s[-1], np.inf))


def binary_report(y, s, pred):
    """pred = boolean 'flagged' (band medium or high)."""
    y, s, pred = np.asarray(y), np.asarray(s, dtype=float), np.asarray(pred, dtype=bool)
    pos, neg = y == 1, y == 0
    return {
        "n_scam": int(pos.sum()), "n_benign": int(neg.sum()),
        "accuracy": round(float((pred == pos).mean()), 4),
        "scam_recall": round(float(pred[pos].mean()), 4) if pos.any() else float("nan"),
        "fpr": round(float(pred[neg].mean()), 4) if neg.any() else float("nan"),
        "auc": round(auc(y, s), 4),
        "recall_at_1pct_fpr": round(recall_at_fpr(y, s, 0.01), 4),
    }


def wilson(k, n, z=1.96):
    """95% Wilson interval for a proportion k/n (useful for small benign counts)."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(float((c - h) / d), 4), round(float((c + h) / d), 4))


def precision_at_prevalence(recall, fpr, prevalence):
    denom = recall * prevalence + fpr * (1 - prevalence)
    return float("nan") if denom == 0 else recall * prevalence / denom


def band_table(y, bands, prevalence=0.01):
    """Per band: benign/scam counts, precision at the data's own mix, and precision if scams were
    `prevalence` of traffic (computed from per-band recall share and FPR share)."""
    y, bands = np.asarray(y), np.asarray(bands)
    n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
    rows = {}
    for b in ("low", "medium", "high"):
        m = bands == b
        tp, fp = int((m & (y == 1)).sum()), int((m & (y == 0)).sum())
        r = tp / n_pos if n_pos else float("nan")
        f = fp / n_neg if n_neg else float("nan")
        rows[b] = {"n_benign": fp, "n_scam": tp,
                   "precision": round(tp / (tp + fp), 4) if tp + fp else None,
                   "share_of_scams": round(r, 4), "share_of_benign": round(f, 4),
                   f"precision_at_{prevalence:.0%}_prevalence": (round(precision_at_prevalence(r, f, prevalence), 4)
                                                                 if b != "low" and n_pos and n_neg else None)}
    return rows
