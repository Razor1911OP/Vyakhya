"""
Signal A: TF-IDF char_wb (2-5) + logistic regression (class_weight=balanced), isotonic-calibrated.

Calibration uses CalibratedClassifierCV with GROUP folds (one group = one lofo_fold), so each
isotonic calibrator is fitted on a family the base model did not see. Calibration therefore
reflects unseen-family behaviour rather than in-distribution confidence.
"""
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from risk.config import SEED
from risk.data import FOLDS, check_template_leakage


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True,
                                  max_features=300_000, dtype=np.float32)),
        ("lr", LogisticRegression(class_weight="balanced", C=2.0, solver="liblinear", max_iter=3000,
                                  random_state=SEED)),
    ])


def fit_calibrated(texts, y, groups) -> CalibratedClassifierCV:
    n_groups = len(np.unique(groups))
    splits = list(GroupKFold(n_splits=n_groups).split(texts, y, groups))
    for tr, te in splits:  # every inner split needs both classes on both sides
        assert len(np.unique(y[tr])) == 2 and len(np.unique(y[te])) == 2, "inner fold missing a class"
    model = CalibratedClassifierCV(build_pipeline(), method="isotonic", cv=splits)
    model.fit(texts, y)
    return model


def lofo_oof(texts, y, folds, template_ids, log=print):
    """Out-of-fold calibrated probabilities: each row is scored by a model that never saw its fold."""
    oof = np.full(len(y), np.nan)
    for f in FOLDS:
        te = folds == f
        tr = ~te
        check_template_leakage(template_ids[tr], template_ids[te])
        model = fit_calibrated(texts[tr], y[tr], folds[tr])
        oof[te] = model.predict_proba(texts[te])[:, 1]
        log(f"  text fold {f:<15} held-out rows={int(te.sum()):>5}  template leakage: none")
    assert not np.isnan(oof).any()
    return oof
