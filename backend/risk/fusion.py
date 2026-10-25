"""
Fusion.

  risk  = max(hard_rule_floor, 100 * blend)
  blend = (w_text * text_prob + w_txn * txn_prob + w_rule * rule_prob) / (sum of weights of AVAILABLE signals)

- Two systems are evaluated:
    spec_baseline   : w_rule fixed at 0 (the original spec formula)
    with_rule_score : w_rule free; rule_prob = isotonic-calibrated rule_score
  Weights are chosen on validation (out-of-fold) predictions: best recall at 1% FPR, ties by AUC.
- A missing signal (no payment, or no message) drops out of the weighted average; it never
  pushes risk down. If all available signals have weight 0, they are averaged equally.
- Bands per signal mode (message+payment / message only / payment only), picked on validation
  benign scores:  medium >= ~5% benign FPR,  high >= ~1% benign FPR  OR any hard-rule hit.
  medium means "warn and ask the user to verify", never a block.
"""
import numpy as np

from risk.config import HARD_RULE_FLOOR
from risk.metrics import auc, recall_at_fpr, threshold_at_fpr

MEDIUM_FPR = 0.05
HIGH_FPR = 0.01
W_STEP = 0.05
MODES = ("both", "text", "txn")
ACTIONS = {
    "low": ("allow", "No action."),
    "medium": ("warn_verify", "Warn and ask the user to verify the payee and the request. Never block."),
    "high": ("strong_warning", "Strong warning with the named reasons; eligible for human review before debit."),
}


def weight_grid(use_rule: bool):
    n = int(round(1 / W_STEP))
    if not use_rule:
        return [(i / n, (n - i) / n, 0.0) for i in range(n + 1)]
    return [(i / n, j / n, (n - i - j) / n) for i in range(n + 1) for j in range(n + 1 - i)]


def blend(text_p, txn_p, rule_p, w):
    P = np.vstack([np.asarray(a, dtype=float) for a in (text_p, txn_p, rule_p)])
    avail = ~np.isnan(P)
    Pz = np.nan_to_num(P)
    W = np.asarray(w, dtype=float)[:, None] * avail
    den = W.sum(axis=0)
    weighted = (W * Pz).sum(axis=0) / np.where(den > 0, den, 1.0)
    n_avail = avail.sum(axis=0)
    equal = Pz.sum(axis=0) / np.maximum(n_avail, 1)
    return np.where(den > 0, weighted, np.where(n_avail > 0, equal, 0.0))


def risk(floor, blended):
    return np.maximum(np.asarray(floor, dtype=float), np.round(100.0 * np.asarray(blended, dtype=float), 1))


def choose_weights(text_p, txn_p, rule_p, floor, y, use_rule: bool):
    best = None
    for w in weight_grid(use_rule):
        s = risk(floor, blend(text_p, txn_p, rule_p, w))
        key = (round(recall_at_fpr(y, s, 0.01), 4), round(auc(y, s), 4))
        if best is None or key > best[0]:
            best = (key, tuple(round(x, 2) for x in w))
    return best[1]


def choose_bands(benign_scores):
    medium = threshold_at_fpr(benign_scores, MEDIUM_FPR)
    high = threshold_at_fpr(benign_scores, HIGH_FPR)
    return {"medium": round(float(min(medium, high)), 1), "high": round(float(high), 1),
            "n_benign_validation": int(len(benign_scores))}


def mode_scores(floor, text_p, txn_p, rule_p, w, mode):
    """Score rows as if only the signals of `mode` were present."""
    nan = np.full(len(floor), np.nan)
    if mode == "both":
        return risk(floor, blend(text_p, txn_p, rule_p, w))
    if mode == "text":
        return risk(floor, blend(text_p, nan, rule_p, w))
    return risk(np.zeros(len(floor)), blend(nan, txn_p, nan, w))


def choose_mode_bands(floor, text_p, txn_p, rule_p, w, y, paired):
    floor, text_p, txn_p, rule_p = (np.asarray(a, dtype=float) for a in (floor, text_p, txn_p, rule_p))
    y, paired = np.asarray(y), np.asarray(paired, dtype=bool)
    benign = y == 0
    out = {}
    for mode in MODES:
        rows = paired if mode in ("both", "txn") else np.ones(len(y), dtype=bool)
        s = mode_scores(floor[rows], text_p[rows], txn_p[rows], rule_p[rows], w, mode)
        out[mode] = choose_bands(s[benign[rows]])
    return out


def band(score, bands, floor=0):
    if floor >= HARD_RULE_FLOOR or score >= bands["high"]:
        return "high"
    return "medium" if score >= bands["medium"] else "low"


def band_array(scores, floors, medium_thr, high_thr):
    s, f = np.asarray(scores, dtype=float), np.asarray(floors, dtype=float)
    high = (f >= HARD_RULE_FLOOR) | (s >= np.asarray(high_thr, dtype=float))
    medium = ~high & (s >= np.asarray(medium_thr, dtype=float))
    return np.where(high, "high", np.where(medium, "medium", "low"))


def signal_mode(has_text: bool, has_txn: bool) -> str:
    if has_text and has_txn:
        return "both"
    if has_text:
        return "text"
    if has_txn:
        return "txn"
    raise ValueError("need a message, a transaction, or both")
