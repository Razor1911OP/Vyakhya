"""
Optional text-model comparison (COMPARE_MODELS slot). Not shipped, never used for fusion.

For each model id: sentence embeddings (frozen, no fine-tuning) + logistic regression
(class_weight=balanced), scored with the SAME leave-one-family-out folds as the TF-IDF model,
plus one fit on the full corpus scored on the hand-written set.

Needs `sentence-transformers` (see requirements-optional.txt) and a one-time model download
from the Hugging Face hub. If either fails, the model is reported as skipped with the reason.
Inputs are the masked model_text strings (digits/amounts already replaced), so no raw
identifiers are sent to the encoder.
"""
import time

import numpy as np
from sklearn.linear_model import LogisticRegression

from risk.config import SEED
from risk.data import FOLDS, SYNTH_FOLDS
from risk.metrics import auc, recall_at_fpr


def _encode(model, texts, batch=64):
    return model.encode(list(texts), batch_size=batch, show_progress_bar=False,
                        convert_to_numpy=True, normalize_embeddings=True)


def run_compare(model_ids, corpus_texts, y, folds, hw_texts, hw_y, log=print):
    results = {}
    for mid in model_ids:
        t0 = time.time()
        try:
            from sentence_transformers import SentenceTransformer  # optional dependency
            model = SentenceTransformer(mid, device="cpu")
        except Exception as e:  # ImportError, network, unknown id
            results[mid] = {"status": "skipped", "reason": f"{type(e).__name__}: {str(e)[:160]}"}
            log(f"  compare {mid}: SKIPPED ({results[mid]['reason']})")
            continue
        X = _encode(model, corpus_texts)
        Xh = _encode(model, hw_texts)
        oof = np.full(len(y), np.nan)
        for f in FOLDS:
            te = folds == f
            lr = LogisticRegression(class_weight="balanced", C=1.0, max_iter=3000, random_state=SEED)
            oof[te] = lr.fit(X[~te], y[~te]).predict_proba(X[te])[:, 1]
        per_fold = {f: round(recall_at_fpr(y[folds == f], oof[folds == f]), 4) for f in FOLDS}
        full = LogisticRegression(class_weight="balanced", C=1.0, max_iter=3000, random_state=SEED).fit(X, y)
        ph = full.predict_proba(Xh)[:, 1]
        results[mid] = {
            "status": "ok", "embedding_dim": int(X.shape[1]), "seconds": round(time.time() - t0, 1),
            "per_fold_recall_at_1pct_fpr": per_fold,
            "mean_unseen_family_recall_at_1pct_fpr": round(float(np.mean([per_fold[f] for f in SYNTH_FOLDS])), 4),
            "handwritten_auc": round(auc(hw_y, ph), 4),
            "handwritten_recall_at_0_5": round(float((ph[hw_y == 1] >= 0.5).mean()), 4),
            "handwritten_fpr_at_0_5": round(float((ph[hw_y == 0] >= 0.5).mean()), 4),
            "_oof": oof, "_handwritten_prob": ph,
        }
        log(f"  compare {mid}: mean unseen-family recall@1%FPR={results[mid]['mean_unseen_family_recall_at_1pct_fpr']} "
            f"handwritten AUC={results[mid]['handwritten_auc']} ({results[mid]['seconds']}s)")
    return results
