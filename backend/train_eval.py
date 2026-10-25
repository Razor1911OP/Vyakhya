"""
ONE COMMAND: train every model, run leave-one-family-out evaluation, evaluate on the frozen
hand-written test set, write tables, save artifacts.

    cd backend
    .\\run_all.bat        (rule tests -> this script -> engine tests; logs in backend/logs/)

Outputs
  metrics/risk_eval.json, metrics/risk_eval.md   evaluation tables
  model_registry/risk/<version>/                 text, PaySim, sender, rule-calibrator models + fusion.json

Two fusion systems are evaluated side by side:
  spec_baseline    risk = max(hard_floor, blend(text, txn))            (original spec formula)
  with_rule_score  risk = max(hard_floor, blend(text, txn, rule_prob)) (shipped)

Honesty rules enforced here
  - Every number is from synthetic (Vyakhya) or public (UCI SMS Spam, PaySim) data, not production.
  - Folds are families / templates, never random rows; template leakage is asserted per fold.
  - Weights and band thresholds are chosen on the OTHER folds (nested) for LOFO numbers, and on
    validation (out-of-fold) scores for the shipped model. The hand-written set is never used for
    training, calibration, weights or thresholds, and is checked for overlap with training text.
  - No raw message text is printed or logged.
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from risk import config as C
from risk.data import (FOLDS, HARD_NEGATIVE_GROUPS, SYNTH_FOLDS, handwritten_leakage, load_handwritten,
                       load_synthetic_transactions, load_text_corpus, load_validation, read_feedback)
from risk.fusion import (MODES, band_array, blend, choose_bands, choose_mode_bands, choose_weights, risk)
from risk.metrics import auc, band_table, binary_report, recall_at_fpr, wilson
from risk.redact import model_text
from risk.rules import RULES_CHANGELOG, RULES_VERSION, evaluate, normalise
from risk.text_model import fit_calibrated, lofo_oof
from risk.txn_model import (fit_sender, load_paysim, paysim_prob, sender_frame, sender_lofo_oof,
                            train_paysim)

np.random.seed(C.SEED)
T0 = time.time()
DECK_BASELINE = {"kyc_refund": 0.84, "digital_arrest": 0.77, "lottery": 0.68, "upi_collect": 0.43, "job_task": 0.26}
SYSTEMS = {"spec_baseline": False, "with_rule_score": True}   # name -> use rule_prob in the blend
SHIPPED = "with_rule_score"


def log(msg=""):
    print(f"[{time.time() - T0:6.0f}s] {msg}" if msg else "", flush=True)


def fmt(x, nd=3):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{nd}f}" if isinstance(x, (float, np.floating)) else str(x)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def iso():
    return IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")


# =============================================================================================
def main():
    for p in (C.SMS_SPAM_PATH, C.PAYSIM_PATH, C.MESSAGES_PATH, C.TRANSACTIONS_PATH, C.HANDWRITTEN_PATH):
        if not p.exists():
            sys.exit(f"Missing input: {p}")
    log(C.DATA_DISCLAIMER)
    hashes = {"handwritten_test.csv": sha256(C.HANDWRITTEN_PATH),
              "risk/rules.py": sha256(C.BACKEND_DIR / "risk" / "rules.py"),
              "jobs/synthetic_templates.py": sha256(C.BACKEND_DIR / "jobs" / "synthetic_templates.py")}
    log(f"Frozen hashes: handwritten={hashes['handwritten_test.csv'][:12]}  rules={hashes['risk/rules.py'][:12]}")

    # ------------------------------------------------------------------ data
    corpus = load_text_corpus()
    txns = load_synthetic_transactions()
    corpus = corpus.merge(txns.drop(columns=["label", "lofo_fold"]), on="msg_id", how="left")
    is_syn = (corpus["source"] == "synthetic").to_numpy()
    y = corpus["label"].to_numpy()
    folds = corpus["lofo_fold"].to_numpy()
    tids = corpus["template_id"].to_numpy()
    mode = np.where(is_syn, "both", "text")    # synthetic rows have a paired payment; UCI rows do not
    log(f"Text corpus: {len(corpus):,} rows  (uci={int((~is_syn).sum()):,}, synthetic={int(is_syn.sum()):,})")
    for f in FOLDS:
        m = folds == f
        log(f"  fold {f:<15} scam={int(y[m].sum()):>4}  benign={int((y[m] == 0).sum()):>5}")

    # ------------------------------------------------------- Signal A: text
    log("Signal A: text model, leave-one-family-out (6 folds, group-calibrated isotonic)")
    texts = np.array([model_text(t) for t in corpus["text"]], dtype=object)
    text_oof = lofo_oof(texts, y, folds, tids, log=log)

    # ------------------------------------------------------- Signal B: rules
    log("Signal B: rule layer (frozen; not tuned on the hand-written set)")
    rule_floor, rule_score, flag_rows = np.zeros(len(corpus)), np.zeros(len(corpus)), []
    for i, row in enumerate(corpus.itertuples(index=False)):
        amt = None if pd.isna(row.amount) else float(row.amount)
        r = evaluate(row.text, amt, row.direction if isinstance(row.direction, str) else "debit")
        rule_floor[i], rule_score[i] = r.floor, r.rule_score
        flag_rows.append(r.flags)
    flags = pd.DataFrame(flag_rows)
    flag_rates = {}
    for grp, m in (("scam_synthetic", is_syn & (y == 1)), ("benign_synthetic", is_syn & (y == 0)),
                   ("uci_spam", ~is_syn & (y == 1)), ("uci_ham", ~is_syn & (y == 0))):
        flag_rates[grp] = {k: round(float(flags.loc[m, k].mean()), 3) for k in flags.columns}
        flag_rates[grp]["hard_floor_90"] = round(float((rule_floor[m] >= C.HARD_RULE_FLOOR).mean()), 3)
    log("  hard-floor hit rate: " + ", ".join(f"{g}={v['hard_floor_90']}" for g, v in flag_rates.items()))
    rule_oof = np.full(len(corpus), np.nan)          # rule_score -> probability, calibrated out-of-fold
    for f in FOLDS:
        te = folds == f
        rule_oof[te] = iso().fit(rule_score[~te], y[~te]).predict(rule_score[te])

    # ------------------------------------------------ Signal C: transactions
    log(f"Signal C1: PaySim behaviour-only XGBoost  [{C.PAYSIM_LABEL}]")
    paysim_df = load_paysim(C.PAYSIM_PATH)
    log(f"  PaySim TRANSFER+CASH_OUT rows: {len(paysim_df):,}")
    paysim_bundle, paysim_report = train_paysim(paysim_df, log=log)
    del paysim_df
    log("Signal C2: sender-history model on synthetic transactions (leave-one-family-out)")
    tx = corpus.loc[is_syn].reset_index(drop=True)
    Xs = sender_frame(tx, paysim_prob(paysim_bundle, tx))
    txn_oof = np.full(len(corpus), np.nan)
    txn_oof[is_syn] = sender_lofo_oof(Xs, tx["label"].to_numpy(), tx["lofo_fold"].to_numpy())

    # ---------------------------------------------- Fusion systems (nested)
    nan_arr = np.full(len(corpus), np.nan)
    sysres = {}
    for name, use_rule in SYSTEMS.items():
        log(f"Fusion [{name}]: weights + per-mode bands from the other folds, applied to the held-out fold")
        rp = rule_oof if use_rule else nan_arr
        score, med, high = np.full(len(corpus), np.nan), np.full(len(corpus), np.nan), np.full(len(corpus), np.nan)
        params, lofo = {}, []
        for f in FOLDS:
            te, va = folds == f, folds != f
            vs = va & is_syn
            w = choose_weights(text_oof[vs], txn_oof[vs], rp[vs], rule_floor[vs], y[vs], use_rule)
            bands = choose_mode_bands(rule_floor[va], text_oof[va], txn_oof[va], rp[va], w, y[va], is_syn[va])
            s_te = risk(rule_floor[te], blend(text_oof[te], txn_oof[te], rp[te], w))
            score[te] = s_te
            med[te] = [bands[m]["medium"] for m in mode[te]]
            high[te] = [bands[m]["high"] for m in mode[te]]
            b_te = band_array(s_te, rule_floor[te], med[te], high[te])
            rep = binary_report(y[te], s_te, b_te != "low")
            rep.update(fold=f, weights=list(w), high_band_recall=round(float((b_te == "high")[y[te] == 1].mean()), 4),
                       high_band_fpr=round(float((b_te == "high")[y[te] == 0].mean()), 4))
            lofo.append(rep)
            params[f] = {"weights": list(w), "bands": bands}
            log(f"  {f:<15} w(text,txn,rule)={w}  recall={rep['scam_recall']} FPR={rep['fpr']} "
                f"high: recall={rep['high_band_recall']} FPR={rep['high_band_fpr']}  recall@1%FPR={rep['recall_at_1pct_fpr']}")
        sysres[name] = {"score": score, "med": med, "high": high, "params": params, "lofo": lofo,
                        "band": band_array(score, rule_floor, med, high)}

    # --------------------------------------------------------- Ablation
    log("Ablation (out-of-fold scores, recall@1%FPR per held-out fold)")
    variants = {
        "text only": 100 * text_oof,
        "rules only": rule_score,
        "transaction only": 100 * txn_oof,
        "text + rules (spec formula)": risk(rule_floor, text_oof),
        "all, spec formula (baseline)": sysres["spec_baseline"]["score"],
        "all + rule_score (shipped)": sysres["with_rule_score"]["score"],
    }
    ablation = {}
    for vname, s in variants.items():
        per_fold = {}
        for f in FOLDS:
            m = (folds == f) & ~np.isnan(s)
            per_fold[f] = None if (m.sum() == 0 or len(np.unique(y[m])) < 2) else round(recall_at_fpr(y[m], s[m]), 4)
        syn_vals = [per_fold[f] for f in SYNTH_FOLDS if per_fold[f] is not None]
        m_syn = is_syn & ~np.isnan(s)
        ablation[vname] = {"per_fold_recall_at_1pct_fpr": per_fold,
                           "mean_unseen_family_recall_at_1pct_fpr": round(float(np.mean(syn_vals)), 4) if syn_vals else None,
                           "synthetic_pooled_auc": round(auc(y[m_syn], s[m_syn]), 4)}
        log(f"  {vname:<30} mean={fmt(ablation[vname]['mean_unseen_family_recall_at_1pct_fpr'])}  "
            f"generic_spam={fmt(per_fold['generic_spam'])}  synthetic AUC={fmt(ablation[vname]['synthetic_pooled_auc'])}")

    # ------------------------------------------------- Band tables (LOFO)
    band_tables = {}
    for name, r in sysres.items():
        band_tables[name] = {"synthetic (message + payment)": band_table(y[is_syn], r["band"][is_syn]),
                             "UCI (message only)": band_table(y[~is_syn], r["band"][~is_syn])}

    # ------------------------------------------------------ Hard negatives
    log("Hard negatives (benign only; LOFO scores with fold- and mode-specific bands)")
    hard_neg = {}
    for gname, rule in HARD_NEGATIVE_GROUPS.items():
        idx = np.flatnonzero(rule(corpus).to_numpy() & (y == 0))
        if len(idx) == 0:
            continue
        entry = {"n": int(len(idx)), "n_templates": int(corpus.iloc[idx]["template_id"].nunique()),
                 "hard_floor_hits": int((rule_floor[idx] >= C.HARD_RULE_FLOOR).sum()),
                 "text_only_fpr_at_0_5": round(float((text_oof[idx] >= 0.5).mean()), 4)}
        for name, r in sysres.items():
            k = int((r["band"][idx] != "low").sum())
            entry[name] = {"flagged": k, "fpr_flagged": round(k / len(idx), 4), "fpr_ci95": wilson(k, len(idx)),
                           "high": int((r["band"][idx] == "high").sum())}
        hard_neg[gname] = entry
        s = entry[SHIPPED]
        log(f"  {gname:<27} n={len(idx):>5} templates={entry['n_templates']:>3}  shipped flagged={s['flagged']} "
            f"({s['fpr_flagged']:.3f}, 95% CI {s['fpr_ci95']})  high={s['high']}")

    # ----------------------------------------------------- Final models
    log("Fitting final models on all data and saving artifacts")
    text_final = fit_calibrated(texts, y, folds)
    rule_cal_final = iso().fit(rule_score, y)
    sender_final = fit_sender(Xs, tx["label"].to_numpy(), tx["lofo_fold"].to_numpy())
    final_systems = {}
    for name, use_rule in SYSTEMS.items():
        rp = rule_oof if use_rule else nan_arr
        w = choose_weights(text_oof[is_syn], txn_oof[is_syn], rp[is_syn], rule_floor[is_syn], y[is_syn], use_rule)
        final_systems[name] = {"weights": list(w), "uses_rule_score": use_rule,
                               "bands": choose_mode_bands(rule_floor, text_oof, txn_oof, rp, w, y, is_syn)}
        log(f"  {name:<16} weights(text,txn,rule)={w}  bands=" +
            ", ".join(f"{m}: med>={final_systems[name]['bands'][m]['medium']} high>={final_systems[name]['bands'][m]['high']}"
                      for m in MODES))
    # ------------------------------------- Cutoffs: synthetic folds only (decision 2026-10-25)
    if C.USE_VALIDATION_CUTOFFS:
        log(f"Validation set ({C.VALIDATION_LABEL}; frozen): choosing message-only band cutoffs")
        val_report = tune_on_validation(corpus, is_syn, text_final, rule_cal_final, final_systems)
    else:
        log(f"Cutoffs: synthetic validation folds only ({C.CUTOFF_LABEL}); validation_benign.csv not used")
        val_report = None
        for cfg in final_systems.values():
            cfg["bands_text_synthetic_folds"] = dict(cfg["bands"]["text"])
            for m in cfg["bands"].values():
                m["label"] = C.CUTOFF_LABEL

    feedback = read_feedback(C.FEEDBACK_FILE)
    C.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(text_final, C.ARTIFACT_DIR / "text_model.joblib")
    joblib.dump(paysim_bundle, C.ARTIFACT_DIR / "paysim_model.joblib")
    joblib.dump(sender_final, C.ARTIFACT_DIR / "sender_model.joblib")
    joblib.dump(rule_cal_final, C.ARTIFACT_DIR / "rule_calibrator.joblib")
    fusion_cfg = {"model_version": C.MODEL_VERSION, "shipped_system": SHIPPED, "systems": final_systems,
                  "hard_rule_floor": C.HARD_RULE_FLOOR,
                  "band_policy": ("medium ~5% benign FPR, high ~1% benign FPR or hard-rule hit, per signal mode, "
                                  f"on synthetic validation folds: {C.CUTOFF_LABEL}."),
                  "text_model_compare": {m: "not evaluated" for m in C.COMPARE_MODELS},
                  "frozen": True,
                  "frozen_note": "Shipped and frozen 2026-10-25: no further model, rule or cutoff changes in this version.",
                  "rules_version": RULES_VERSION, "rules_changelog": RULES_CHANGELOG,
                  "seed": C.SEED, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "data": {"text": "UCI SMS Spam (public, English, UK 2000s) + Vyakhya synthetic en/hi/hi-en (generator v2)",
                           "transaction": C.PAYSIM_LABEL + "; sender history from Vyakhya synthetic transactions"},
                  "frozen_hashes": hashes, "feedback_records_seen": len(feedback), "disclaimer": C.DATA_DISCLAIMER}
    (C.ARTIFACT_DIR / "fusion.json").write_text(json.dumps(fusion_cfg, indent=2), encoding="utf-8")
    registry_cfg = {
        "model_name": "vyakhya_risk", "version": C.MODEL_VERSION, "shipped_system": SHIPPED, "frozen": True,
        "rules_version": RULES_VERSION, "rules_sha256": hashes["risk/rules.py"],
        "handwritten_test_sha256": hashes["handwritten_test.csv"], "seed": C.SEED,
        "input_schema": {"text": "message, optional, capped at %d chars" % C.MAX_INPUT_CHARS,
                         "txn": "amount, hour, direction (debit|collect|credit), beneficiary_prior_txns, "
                                "amount_vs_history_percentile, txn_count_last_hour, txn_count_last_day, fan_out_count"},
        "artifacts": ["text_model.joblib", "paysim_model.joblib", "sender_model.joblib", "rule_calibrator.joblib", "fusion.json"],
        "weights": final_systems[SHIPPED]["weights"], "bands": final_systems[SHIPPED]["bands"],
        "cutoffs": C.CUTOFF_LABEL, "text_model_compare": {m: "not evaluated" for m in C.COMPARE_MODELS},
        "training_data": fusion_cfg["data"], "metrics_file": "metrics/risk_eval.json",
        "disclaimer": C.DATA_DISCLAIMER, "trained_at": fusion_cfg["trained_at"],
    }
    (C.ARTIFACT_DIR / "config.json").write_text(json.dumps(registry_cfg, indent=2), encoding="utf-8")

    # ------------------------------------------------- Hand-written test
    log("Hand-written test set (frozen; scored with the shipped artifacts; message-only mode)")
    hw_report = evaluate_handwritten(corpus, is_syn, text_final, rule_cal_final, final_systems)

    # ------------------------------------------------ Optional comparisons
    compare = {}
    if C.COMPARE_ENABLED:
        log("COMPARE_MODELS (optional, not shipped)")
        from risk.compare import run_compare
        hw = load_handwritten()
        hw_texts = np.array([model_text(t) for t in hw["text"]], dtype=object)
        compare = run_compare(C.COMPARE_MODELS, texts, y, folds, hw_texts, hw["label"].to_numpy(), log=log)
        for v in compare.values():
            v.pop("_oof", None)
            v.pop("_handwritten_prob", None)

    # ------------------------------------------------------------- Reports
    report = {"disclaimer": C.DATA_DISCLAIMER, "model_version": C.MODEL_VERSION, "seed": C.SEED,
              "frozen_hashes": hashes,
              "lofo": {n: r["lofo"] for n, r in sysres.items()},
              "summary": {n: round(float(np.mean([x["recall_at_1pct_fpr"] for x in r["lofo"] if x["fold"] in SYNTH_FOLDS])), 4)
                          for n, r in sysres.items()},
              "ablation": ablation, "band_tables": band_tables, "hard_negatives": hard_neg,
              "handwritten": hw_report, "validation": val_report, "compare_models": compare, "rule_flag_rates": flag_rates,
              "rules_version": RULES_VERSION, "rules_changelog": RULES_CHANGELOG,
              "paysim_model": paysim_report, "fusion_shipped": fusion_cfg,
              "fold_params": {n: r["params"] for n, r in sysres.items()}}
    report["weak_spots"] = weak_spots(report)
    C.METRICS_DIR.mkdir(parents=True, exist_ok=True)
    (C.METRICS_DIR / "risk_eval.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    write_markdown(report)
    for n, v in report["summary"].items():
        log(f"Mean unseen-family recall@1%FPR [{n}]: {v}  (deck text-only baseline 0.60, target 0.80)")
    log(f"Wrote {C.METRICS_DIR / 'risk_eval.md'}")
    smoke_test()
    log("DONE")


# =============================================================================================
def score_message_only(df, text_model, rule_cal, cfg):
    """Score messages without a payment (signal mode 'text'). Returns (risk, floor, text_p, rule_score)."""
    text_p = text_model.predict_proba(np.array([model_text(t) for t in df["text"]], dtype=object))[:, 1]
    floor, rscore = np.zeros(len(df)), np.zeros(len(df))
    for i, r in enumerate(df.itertuples(index=False)):
        amt = None if pd.isna(r.amount) else float(r.amount)
        res = evaluate(r.text, amt, r.direction)
        floor[i], rscore[i] = res.floor, res.rule_score
    nan = np.full(len(df), np.nan)
    rp = rule_cal.predict(rscore) if cfg["uses_rule_score"] else nan
    return risk(floor, blend(text_p, nan, rp, cfg["weights"])), floor, text_p, rscore


def overlap_check(texts, ids, other_texts, label):
    leak = handwritten_leakage(list(texts), list(other_texts), threshold=0.5)
    per_row = leak.pop("per_row_max_jaccard")
    leak["ids_above_0.5"] = [i for i, j in zip(ids, per_row) if j >= 0.5]
    log(f"  overlap vs {label}: exact={leak['exact_duplicates']}  max char-5gram Jaccard={leak['max_jaccard']}  "
        f"mean={leak['mean_max_jaccard']}  rows>=0.5: {leak['ids_above_0.5'] or 'none'}")
    return leak


def tune_on_validation(corpus, is_syn, text_final, rule_cal, final_systems):
    """Pick message-only cutoffs on the benign validation set. Mutates final_systems[*]['bands']['text']
    and keeps the synthetic-fold cutoffs under 'bands_text_synthetic_folds' for comparison."""
    val = load_validation()
    hw = load_handwritten()
    out = {"n": int(len(val)), "author": C.VALIDATION_LABEL,
           "use": "message-only band cutoffs only; never training, calibration, weights or rule edits",
           "overlap_vs_training": overlap_check(val["text"], val["val_id"], corpus["text"], "training text (synthetic + UCI)"),
           "overlap_vs_handwritten": overlap_check(val["text"], val["val_id"], hw["text"], "hand-written test set"),
           "systems": {}}
    if out["overlap_vs_training"]["exact_duplicates"] or out["overlap_vs_handwritten"]["exact_duplicates"]:
        sys.exit("ABORT: validation messages duplicate training or hand-written test messages")
    n = len(val)
    for name, cfg in final_systems.items():
        s, floor, _, _ = score_message_only(val, text_final, rule_cal, cfg)
        syn = dict(cfg["bands"]["text"])
        vb = choose_bands(s)
        rows = {}
        for src, bd in (("synthetic_folds", syn), ("validation_set", vb)):
            b = band_array(s, floor, np.full(n, bd["medium"]), np.full(n, bd["high"]))
            kf, kh = int((b != "low").sum()), int((b == "high").sum())
            rows[src] = {"medium": bd["medium"], "high": bd["high"],
                         "flagged": kf, "fpr_flagged": round(kf / n, 4), "fpr_flagged_ci95": wilson(kf, n),
                         "high_count": kh, "fpr_high": round(kh / n, 4), "fpr_high_ci95": wilson(kh, n),
                         "per_group_flagged": {g: int((b[(val["group"] == g).to_numpy()] != "low").sum())
                                               for g in sorted(val["group"].unique())},
                         "flagged_ids": val.loc[b != "low", "val_id"].tolist()}
        out["systems"][name] = {**rows, "hard_floor_hits": int((floor >= C.HARD_RULE_FLOOR).sum())}
        cfg["bands_text_synthetic_folds"] = syn
        cfg["bands"]["text"] = {"medium": vb["medium"], "high": vb["high"], "n_benign_validation": n,
                                "source": f"validation_benign.csv ({C.VALIDATION_LABEL})"}
        r = rows
        log(f"  {name:<16} synthetic-fold cutoffs med>={syn['medium']} high>={syn['high']}: flagged {r['synthetic_folds']['flagged']}/{n}, "
            f"high {r['synthetic_folds']['high_count']}/{n}  ->  validation cutoffs med>={vb['medium']} high>={vb['high']}: "
            f"flagged {r['validation_set']['flagged']}/{n} (CI {r['validation_set']['fpr_flagged_ci95']}), "
            f"high {r['validation_set']['high_count']}/{n}  floor hits={out['systems'][name]['hard_floor_hits']}")
    return out


def evaluate_handwritten(corpus, is_syn, text_final, rule_cal, final_systems):
    hw = load_handwritten()
    yh = hw["label"].to_numpy()
    leak = overlap_check(hw["text"], hw["hw_id"], corpus["text"], "training text (synthetic + UCI)")
    if leak["exact_duplicates"]:
        sys.exit("ABORT: hand-written test messages appear verbatim in training data")

    out = {"n": int(len(hw)), "n_scam": int(yh.sum()), "n_benign": int((yh == 0).sum()),
           "note": "Message-only mode (transaction model not used); amounts/direction feed the rule mismatch check. "
                   "Written by the assistant before the v2 templates; not independent of the rule author.",
           "leakage": leak, "auc": {}, "systems": {}}
    _, _, text_p, rscore = score_message_only(hw, text_final, rule_cal, final_systems[SHIPPED])
    out["auc"]["text only"] = round(auc(yh, text_p), 4)
    out["auc"]["rules only"] = round(auc(yh, rscore), 4)
    for (name, src), cfg, bd in [((n, s), c, c["bands_text_synthetic_folds"] if s == "synthetic-fold cutoffs" else c["bands"]["text"])
                                 for n, c in final_systems.items()
                                 for s in (("synthetic-fold cutoffs", "validation cutoffs") if C.USE_VALIDATION_CUTOFFS
                                           else ("synthetic-fold cutoffs",))]:
        key = f"{name} | {src}"
        s, floor, _, _ = score_message_only(hw, text_final, rule_cal, cfg)
        b = band_array(s, floor, np.full(len(hw), bd["medium"]), np.full(len(hw), bd["high"]))
        out["auc"][name] = round(auc(yh, s), 4)
        name = key
        rep = binary_report(yh, s, b != "low")
        rep["high_band_recall"] = round(float((b == "high")[yh == 1].mean()), 4)
        rep["high_band_fpr"] = round(float((b == "high")[yh == 0].mean()), 4)
        k = int((b != "low")[yh == 0].sum())
        rep["fpr_ci95"] = wilson(k, int((yh == 0).sum()))
        kh = int((b == "high")[yh == 0].sum())
        rep["high_fpr_ci95"] = wilson(kh, int((yh == 0).sum()))
        rep["recall_ci95"] = wilson(int((b != "low")[yh == 1].sum()), int((yh == 1).sum()))
        per_family = {f: {"n": int(m.sum()), "recall_flagged": round(float((b[m] != "low").mean()), 4),
                          "recall_high": round(float((b[m] == "high").mean()), 4)}
                      for f in sorted(hw.loc[yh == 1, "family"].unique())
                      for m in [(hw["family"] == f).to_numpy()]}
        per_group = {g: {"n": int(m.sum()), "flagged": int((b[m] != "low").sum()), "high": int((b[m] == "high").sum())}
                     for g in sorted(hw.loc[yh == 0, "group"].unique())
                     for m in [((hw["group"] == g) & (hw["label"] == 0)).to_numpy()]}
        per_lang = {}
        for lang in ("en", "hi-en", "hi"):
            m = (hw["language"] == lang).to_numpy()
            per_lang[lang] = {"n_scam": int(yh[m].sum()), "n_benign": int((yh[m] == 0).sum()),
                              "recall_flagged": round(float((b[m & (yh == 1)] != "low").mean()), 4) if (m & (yh == 1)).any() else None,
                              "fpr_flagged": round(float((b[m & (yh == 0)] != "low").mean()), 4) if (m & (yh == 0)).any() else None}
        out["systems"][name] = {"report": rep, "band_table": band_table(yh, b), "per_family": per_family,
                                "per_benign_group": per_group, "per_language": per_lang,
                                "flagged_benign_ids": hw.loc[(b != "low") & (yh == 0), "hw_id"].tolist(),
                                "missed_scam_ids": hw.loc[(b == "low") & (yh == 1), "hw_id"].tolist()}
        log(f"  {name:<42} flagged: recall={rep['scam_recall']} FPR={rep['fpr']} "
            f"(95% CI {rep['fpr_ci95']})  high: recall={rep['high_band_recall']} FPR={rep['high_band_fpr']}")
    log(f"  AUC: " + ", ".join(f"{k}={v}" for k, v in out["auc"].items()))

    # Rules v1 (archived run, same hand-written set, synthetic-fold cutoffs) for the rule-change comparison
    archived = C.METRICS_DIR / "risk_eval_v0.2.0_rules_v1.json"
    if archived.exists():
        old = json.loads(archived.read_text(encoding="utf-8"))["handwritten"]
        out["rules_v1_archived"] = {n: v["report"] for n, v in old["systems"].items()}
        out["rules_v1_archived_auc"] = old["auc"]
        comparison = {
            "disclaimer": C.DATA_DISCLAIMER, "test_set": "data/handwritten_test.csv",
            "test_set_sha256": sha256(C.HANDWRITTEN_PATH), "cutoffs": C.CUTOFF_LABEL,
            "note": ("v2 fix was found by inspecting evaluation failures; this comparison is not a clean test of "
                     "generalisation. Models and cutoffs were retrained between runs, so differences mix the rule "
                     "change with retraining noise."),
            "rules_v1": {"rules_sha256": sha256(C.BACKEND_DIR / "risk" / "rules_v1_frozen.py.txt"),
                         "auc": old["auc"], "systems": out["rules_v1_archived"]},
            "rules_v2": {"rules_sha256": sha256(C.BACKEND_DIR / "risk" / "rules.py"), "changelog": RULES_CHANGELOG["v2"],
                         "auc": out["auc"], "systems": {k: v["report"] for k, v in out["systems"].items()}},
        }
        (C.METRICS_DIR / "rules_v1_vs_v2_handwritten.json").write_text(json.dumps(comparison, indent=2, default=str),
                                                                       encoding="utf-8")
        log("  wrote metrics/rules_v1_vs_v2_handwritten.json")
    return out


def weak_spots(rep):
    """Named weak spots for the README and the evaluation panel. Never averaged away."""
    lofo = {r["fold"]: r for r in rep["lofo"][SHIPPED] if r["fold"] in SYNTH_FOLDS}
    worst = min(lofo, key=lambda f: lofo[f]["recall_at_1pct_fpr"])
    base = {r["fold"]: r for r in rep["lofo"]["spec_baseline"]}
    hw = rep["handwritten"]["systems"]
    src = "validation cutoffs" if C.USE_VALIDATION_CUTOFFS else "synthetic-fold cutoffs"
    k_ship, k_base = f"{SHIPPED} | {src}", f"spec_baseline | {src}"
    ci_s, ci_b = hw[k_ship]["report"]["fpr_ci95"], hw[k_base]["report"]["fpr_ci95"]
    overlap = not (ci_s[0] > ci_b[1] or ci_b[0] > ci_s[1])
    return {
        "weakest_family_lofo": worst,
        "weakest_family_detail": {
            "shipped_recall_at_1pct_fpr": lofo[worst]["recall_at_1pct_fpr"],
            "spec_baseline_recall_at_1pct_fpr": base[worst]["recall_at_1pct_fpr"],
            "shipped_flagged_recall": lofo[worst]["scam_recall"], "shipped_flagged_fpr": lofo[worst]["fpr"],
            "handwritten": hw[k_ship]["per_family"].get(worst)},
        "handwritten_flagged_fpr": {"shipped": [hw[k_ship]["report"]["fpr"], ci_s],
                                    "spec_baseline": [hw[k_base]["report"]["fpr"], ci_b]},
        "flagged_fpr_verdict": ("no worse: the flagged-FPR difference is within the 95% intervals, so the evidence "
                                "does not show an improvement" if overlap else
                                "intervals do not overlap; see the table for the direction"),
    }


# =============================================================================================
def write_markdown(rep):
    S = list(SYSTEMS)
    L = ["# Vyakhya risk engine evaluation", "", f"> **{rep['disclaimer']}**", "",
         f"Model version `{rep['model_version']}`, seed {rep['seed']}. Hand-written test set SHA-256 "
         f"`{rep['frozen_hashes']['handwritten_test.csv'][:16]}…`, rules `{rep['frozen_hashes']['risk/rules.py'][:16]}…`.", "",
         "Two fusion systems: **spec_baseline** = `max(hard_floor, blend(text, txn))`; "
         "**with_rule_score** (shipped) = `max(hard_floor, blend(text, txn, rule_prob))`. Hard-rule floors override both. "
         "Bands: medium ≈ 5% benign FPR (warn and ask the user to verify, never a block), high ≈ 1% benign FPR or any hard-rule hit, "
         f"All cutoffs come from synthetic validation folds: **{C.CUTOFF_LABEL}**. This version is shipped and frozen.", "",
         f"Rules version **{rep['rules_version']}**: {rep['rules_changelog'][rep['rules_version']]}", "",
         "## Known weak spots (read first)", "",
         f"- **Weakest scam family: `{rep['weak_spots']['weakest_family_lofo']}`.** Unseen-family recall @1% FPR "
         f"{fmt(rep['weak_spots']['weakest_family_detail']['shipped_recall_at_1pct_fpr'])} for the shipped system vs "
         f"{fmt(rep['weak_spots']['weakest_family_detail']['spec_baseline_recall_at_1pct_fpr'])} for spec_baseline. "
         "The mean over families hides this; do not quote the mean without it.",
         f"- **Hand-written flagged FPR:** shipped {fmt(rep['weak_spots']['handwritten_flagged_fpr']['shipped'][0])} "
         f"(95% CI {rep['weak_spots']['handwritten_flagged_fpr']['shipped'][1]}) vs spec_baseline "
         f"{fmt(rep['weak_spots']['handwritten_flagged_fpr']['spec_baseline'][0])} "
         f"(95% CI {rep['weak_spots']['handwritten_flagged_fpr']['spec_baseline'][1]}): {rep['weak_spots']['flagged_fpr_verdict']}.",
         f"- All band cutoffs are {C.CUTOFF_LABEL}. On the hand-written set the realistic benign FPR is far above the 5%/1% design targets (see section 5).", "",
         "## 1. Leave-one-family-out (synthetic + UCI; nested thresholds)", "",
         "| Held-out | Scam n | Benign n | " + " | ".join(f"{s}: recall@1%FPR | flagged recall | flagged FPR | high FPR" for s in S) +
         " | Deck baseline |", "|---|---|---|" + "---|---|---|---|" * len(S) + "---|"]
    by_fold = {s: {r["fold"]: r for r in rep["lofo"][s]} for s in S}
    for f in FOLDS:
        cells = []
        for s in S:
            r = by_fold[s][f]
            cells += [fmt(r["recall_at_1pct_fpr"]), fmt(r["scam_recall"]), fmt(r["fpr"]), fmt(r["high_band_fpr"])]
        r0 = by_fold[S[0]][f]
        L.append(f"| {f} | {r0['n_scam']} | {r0['n_benign']} | " + " | ".join(cells) +
                 f" | {fmt(DECK_BASELINE.get(f), 2) if f in DECK_BASELINE else 'n/a'} |")
    L += ["", "Mean unseen-family recall @1% FPR (5 synthetic families): " +
          ", ".join(f"**{s}** {rep['summary'][s]}" for s in S) + " (deck text-only baseline 0.60, target 0.80).",
          "Weights per fold (text, txn, rule): " +
          "; ".join(f"{s}: " + ", ".join(f"{r['fold']}={tuple(r['weights'])}" for r in rep["lofo"][s]) for s in S), "",
          "> rule_score was written while looking at the same synthetic templates, so its contribution on these folds is "
          "optimistic. Judge it on the hand-written set (section 5).", "",
          "## 2. Ablation (recall @1% FPR per held-out fold)", "",
          "| Variant | " + " | ".join(FOLDS) + " | Mean (5 synthetic) | Synthetic AUC |", "|---|" + "---|" * (len(FOLDS) + 2)]
    for name, a in rep["ablation"].items():
        L.append(f"| {name} | " + " | ".join(fmt(a["per_fold_recall_at_1pct_fpr"][f]) for f in FOLDS) +
                 f" | {fmt(a['mean_unseen_family_recall_at_1pct_fpr'])} | {fmt(a['synthetic_pooled_auc'])} |")
    L += ["", "*rules only* = weighted flag sum with hard floor. Transaction-only is n/a on `generic_spam` (no paired payment).", "",
          "## 3. Bands: counts and precision (LOFO scores)", "",
          "Precision depends on the scam share of the data (synthetic here is ~47% scam). The last column re-weights to an "
          "assumed 1% scam prevalence. Benign counts are small; treat FPR and precision as rough.", "",
          "| System | Population | Band | Benign n | Scam n | Precision | Share of scams | Share of benign | Precision @1% prevalence |",
          "|---|---|---|---|---|---|---|---|---|"]
    for s in S:
        for pop, tbl in rep["band_tables"][s].items():
            for b, r in tbl.items():
                L.append(f"| {s} | {pop} | {b} | {r['n_benign']} | {r['n_scam']} | {fmt(r['precision'])} | "
                         f"{fmt(r['share_of_scams'])} | {fmt(r['share_of_benign'])} | {fmt(r['precision_at_1%_prevalence'])} |")
    L += ["", "## 4. Hard negatives (synthetic + UCI benign that look like scams; LOFO)", "",
          "| Group | n | Templates | " + " | ".join(f"{s} flagged (FPR, 95% CI) | {s} high" for s in S) +
          " | Hard-floor hits | Text-only FPR @0.5 |", "|---|---|---|" + "---|---|" * len(S) + "---|---|"]
    for g, h in rep["hard_negatives"].items():
        cells = []
        for s in S:
            e = h[s]
            cells += [f"{e['flagged']} ({fmt(e['fpr_flagged'])}, {e['fpr_ci95'][0]}–{e['fpr_ci95'][1]})", str(e["high"])]
        L.append(f"| {g} | {h['n']} | {h['n_templates']} | " + " | ".join(cells) +
                 f" | {h['hard_floor_hits']} | {fmt(h['text_only_fpr_at_0_5'])} |")
    hw = rep["handwritten"]
    lk = hw["leakage"]
    L += ["", f"## 5. Hand-written test set ({hw['n']} messages: {hw['n_scam']} scam, {hw['n_benign']} benign)", "",
          f"{hw['note']}", "",
          f"Overlap with training text: exact duplicates {lk['exact_duplicates']}, max char-5-gram Jaccard {lk['max_jaccard']} "
          f"(mean of per-message max {lk['mean_max_jaccard']}); messages ≥ 0.5: {', '.join(lk['ids_above_0.5']) or 'none'}.", "",
          "AUC: " + ", ".join(f"{k} {fmt(v)}" for k, v in hw["auc"].items()) + ".", "",
          "Rows: system × cutoff source. *synthetic-fold cutoffs* = message-only bands from synthetic validation folds; "
          "*validation cutoffs* = message-only bands from `validation_benign.csv` (shipped).", "",
          "| System | Rules | Flagged recall (95% CI) | Flagged FPR (95% CI) | High recall | High FPR (95% CI) | Accuracy |",
          "|---|---|---|---|---|---|---|"]
    S = list(hw["systems"])
    for s in S:
        r = hw["systems"][s]["report"]
        L.append(f"| {s} | {rep['rules_version']} | {fmt(r['scam_recall'])} ({r['recall_ci95'][0]}–{r['recall_ci95'][1]}) | "
                 f"{fmt(r['fpr'])} ({r['fpr_ci95'][0]}–{r['fpr_ci95'][1]}) | {fmt(r['high_band_recall'])} | "
                 f"{fmt(r['high_band_fpr'])} ({r['high_fpr_ci95'][0]}–{r['high_fpr_ci95'][1]}) | {fmt(r['accuracy'])} |")
    for s, r in hw.get("rules_v1_archived", {}).items():
        ci = r.get("fpr_ci95", ["?", "?"])
        L.append(f"| {s} \\| synthetic-fold cutoffs (archived run) | v1 | {fmt(r['scam_recall'])} | "
                 f"{fmt(r['fpr'])} ({ci[0]}–{ci[1]}) | {fmt(r['high_band_recall'])} | {fmt(r['high_band_fpr'])} | {fmt(r['accuracy'])} |")
    if hw.get("rules_v1_archived"):
        L += ["", "Rule-change comparison: compare *rules v1 (archived run)* with *rules v2 | synthetic-fold cutoffs* "
              "(same cutoff policy). The v2 fix was found by looking at evaluation failures, so the validation-set "
              "results (section 5b) are the cleaner check that it generalises."]
    L += ["", "| System | Band | Benign n | Scam n | Precision | Precision @1% prevalence |", "|---|---|---|---|---|---|"]
    for s in S:
        for b, r in hw["systems"][s]["band_table"].items():
            L.append(f"| {s} | {b} | {r['n_benign']} | {r['n_scam']} | {fmt(r['precision'])} | {fmt(r['precision_at_1%_prevalence'])} |")
    L += ["", "Per scam family (flagged recall / high recall):", "",
          "| Family | n | " + " | ".join(S) + " |", "|---|---|" + "---|" * len(S)]
    for f, v in hw["systems"][S[0]]["per_family"].items():
        L.append(f"| {f} | {v['n']} | " + " | ".join(
            f"{fmt(hw['systems'][s]['per_family'][f]['recall_flagged'])} / {fmt(hw['systems'][s]['per_family'][f]['recall_high'])}"
            for s in S) + " |")
    L += ["", "Per benign group (flagged / high, out of n):", "", "| Group | n | " + " | ".join(S) + " |",
          "|---|---|" + "---|" * len(S)]
    for g, v in hw["systems"][S[0]]["per_benign_group"].items():
        L.append(f"| {g} | {v['n']} | " + " | ".join(
            f"{hw['systems'][s]['per_benign_group'][g]['flagged']} / {hw['systems'][s]['per_benign_group'][g]['high']}"
            for s in S) + " |")
    L += ["", "Per language (flagged recall / flagged FPR):", "", "| Language | Scam n | Benign n | " + " | ".join(S) + " |",
          "|---|---|---|" + "---|" * len(S)]
    for lang, v in hw["systems"][S[0]]["per_language"].items():
        L.append(f"| {lang} | {v['n_scam']} | {v['n_benign']} | " + " | ".join(
            f"{fmt(hw['systems'][s]['per_language'][lang]['recall_flagged'])} / {fmt(hw['systems'][s]['per_language'][lang]['fpr_flagged'])}"
            for s in S) + " |")
    shipped_key = f"{SHIPPED} | {'validation cutoffs' if C.USE_VALIDATION_CUTOFFS else 'synthetic-fold cutoffs'}"
    L += ["", "Flagged benign ids (shipped): " + (", ".join(hw["systems"][shipped_key]["flagged_benign_ids"]) or "none") + ".",
          "Missed scam ids (shipped, band low): " + (", ".join(hw["systems"][shipped_key]["missed_scam_ids"]) or "none") + ".", ""]
    v = rep["validation"]
    if v is None:
        L += ["## 5b. Validation set for cutoffs", "",
              f"Not used in this version (decision 2026-10-25). All cutoffs are {C.CUTOFF_LABEL}.", ""]
    else:
        L += _validation_section(rep, v)
    L += _after_validation(rep, hw)
    (C.METRICS_DIR / "risk_eval.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def _validation_section(rep, v):
    L = []
    L += [f"## 5b. Validation set for cutoffs ({v['n']} benign messages, **{v['author']}**)", "",
          f"Used only to pick message-only cutoffs ({v['use']}). Frozen before tuning; SHA-256 "
          f"`{rep['frozen_hashes']['validation_benign.csv'][:16]}…`. With {v['n']} messages, one message moves FPR by "
          f"{100 / v['n']:.0f} point; read the intervals, not the point estimates. Cutoffs are provisional until the pilot.", "",
          f"Overlap: vs training text exact {v['overlap_vs_training']['exact_duplicates']}, max Jaccard {v['overlap_vs_training']['max_jaccard']}; "
          f"vs hand-written set exact {v['overlap_vs_handwritten']['exact_duplicates']}, max Jaccard {v['overlap_vs_handwritten']['max_jaccard']}.", "",
          "| System | Cutoff source | Medium ≥ | High ≥ | Flagged (FPR, 95% CI) | High (FPR, 95% CI) | Hard-floor hits |",
          "|---|---|---|---|---|---|---|"]
    for s, sv in v["systems"].items():
        for src in ("synthetic_folds", "validation_set"):
            r = sv[src]
            L.append(f"| {s} | {src} | {r['medium']} | {r['high']} | {r['flagged']}/{v['n']} ({fmt(r['fpr_flagged'])}, "
                     f"{r['fpr_flagged_ci95'][0]}–{r['fpr_flagged_ci95'][1]}) | {r['high_count']}/{v['n']} ({fmt(r['fpr_high'])}, "
                     f"{r['fpr_high_ci95'][0]}–{r['fpr_high_ci95'][1]}) | {sv['hard_floor_hits']} |")
    groups = list(v["systems"][SHIPPED]["synthetic_folds"]["per_group_flagged"])
    L += ["", "Flagged per benign group, shipped system (synthetic-fold cutoffs → validation cutoffs): " +
          ", ".join(f"{g} {v['systems'][SHIPPED]['synthetic_folds']['per_group_flagged'][g]}→"
                    f"{v['systems'][SHIPPED]['validation_set']['per_group_flagged'][g]}" for g in groups) + ".",
          "These are in-sample by construction (the cutoffs were chosen on these messages); the hand-written set is the out-of-sample check.", ""]
    return L


def _after_validation(rep, hw):
    L = ["## 6. Optional text-model comparison (COMPARE_MODELS, not shipped)", ""]
    if not rep["compare_models"]:
        L += [f"- `{m}`: **not evaluated** (skipped by decision; not installed or run). No result is claimed for it. "
              "TF-IDF char n-grams + logistic regression remains the text baseline." for m in C.COMPARE_MODELS]
    for mid, v in rep["compare_models"].items():
        if v["status"] != "ok":
            L.append(f"- `{mid}`: **not evaluated** ({v['reason']}). No result is claimed for it.")
        else:
            L.append(f"- `{mid}` (frozen embeddings + logistic regression): mean unseen-family recall @1% FPR "
                     f"{v['mean_unseen_family_recall_at_1pct_fpr']} vs TF-IDF {fmt(rep['ablation']['text only']['mean_unseen_family_recall_at_1pct_fpr'])}; "
                     f"hand-written AUC {v['handwritten_auc']} vs TF-IDF {fmt(hw['auc']['text only'])}. Per fold: "
                     + ", ".join(f"{k}={fmt(x)}" for k, x in v["per_fold_recall_at_1pct_fpr"].items()))
    p = rep["paysim_model"]
    L += ["", f"## 7. Transaction model: {p['data']}", "",
          f"Features: {', '.join(p['features'])}. Split: {p['split']}. Test ROC-AUC {p['test_roc_auc']}, PR-AUC {p['test_pr_auc']} "
          f"(test prevalence {p['prevalence']['test']:.4f}), recall @1% FPR {p['test_recall_at_1pct_fpr']}, @0.1% FPR {p['test_recall_at_0_1pct_fpr']}.", "",
          "## 8. Caveats", "",
          "- Synthetic messages come from a template set (8 per scam family and language; 8–9 per language for the main hard-negative "
          "groups). Unseen-family numbers measure transfer between our own templates, not real-world scams.",
          "- rule_score and the rules were written while looking at the synthetic templates; the hand-written set was written by the "
          "same assistant before the v2 templates were added. Neither is an independent test; a set written by someone else would be.",
          "- Payee-history values for synthetic payments are a documented generator assumption (jobs/export_training_tables.py).",
          "- UCI SMS Spam is English, UK, mid-2000s; it adds generic spam vocabulary, not Indian UPI scams.",
          "- The UPI 2024 and Indian banking CSVs were profiled and excluded: no learnable label signal "
          "(ROC-AUC 0.48 and 0.53 on time splits). See metrics/txn_signal_probe_*.json.",
          f"- Cutoffs: {C.CUTOFF_LABEL}."]
    return L


def smoke_test():
    """Score fixed demo cases through the saved artifacts. Prints case names, never message text."""
    from risk.engine import RiskEngine
    eng = RiskEngine()
    cases = {
        "cashback + PIN + collect (hard rule)": ("Cashback of Rs 1,499 is waiting. Approve the collect request and enter UPI PIN to receive.",
                                                 {"amount": 1499, "hour": 21, "direction": "collect", "beneficiary_prior_txns": 0}),
        "genuine OTP notice": ("482913 is your OTP for login. Valid 10 minutes. Do not share it with anyone.", None),
        "debit alert": ("Rs 2,500 debited from your HDFC a/c XX4821 on 12/03/2026. Not you? Call the number on your card.", None),
        "grocery payment, known payee": (None, {"amount": 640, "hour": 18, "direction": "debit", "beneficiary_prior_txns": 85,
                                                "amount_vs_history_percentile": 55}),
        "refund + share OTP": ("Your refund of Rs 2,000 is on hold. Share the OTP with our executive to release it.",
                               {"amount": 2000, "hour": 11, "direction": "debit", "beneficiary_prior_txns": 1}),
    }
    log("Smoke test through saved artifacts:")
    for name, (text, txn) in cases.items():
        r = eng.score(text=text, txn=txn)
        log(f"  {name:<38} risk={r['risk_score']:>3} band={r['band']:<6} action={r['action']:<14} mode={r['signal_mode']:<4} "
            f"text={r['text_prob']} txn={r['txn_prob']} rule={r['rule_prob']} reasons={r['reasons'][:2]}")


if __name__ == "__main__":
    main()
