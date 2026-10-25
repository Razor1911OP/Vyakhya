"""
Vyakhya synthetic data generator (SYNTHETIC DATA ONLY - never production performance).

Produces one row per payment event: a forwarded message + the payment it prompted
+ simulated context signals. Output: data/synthetic/events.csv and summary.json.

Design choices (documented so results can be judged honestly):
- Fixed seed, stdlib `random` only -> identical output on every run.
- 5 scam families x 3 languages x 4 templates, 7 benign subtypes x 3 languages.
- Every row carries `template_id` and `family`, so evaluation can split by
  template or hold out a whole family (no leakage via paraphrases).
- Benign data includes hard negatives (genuine KYC/refund/courier/job messages).
- Transaction and context distributions OVERLAP between scam and benign on purpose
  (benign users also pay new payees at night while on a call; scams also pay small
  amounts in daytime). Without overlap every model would trivially score ~1.0.
- Balances are kept internally consistent for every row, so PaySim-style
  "balance error" features carry no signal here (they were a PaySim artefact).
- Context signals are SIMULATED: the prototype cannot observe calls/screen-share.

Usage: python jobs/gen_synthetic.py [--seed 42] [--out ../data/synthetic]
"""
import argparse
import csv
import json
import math
import random
import string
from collections import Counter, defaultdict
from pathlib import Path

from synthetic_templates import BENIGN_SUBTYPES, FILLERS, ROWS_PER_KEY, SCAM_FAMILIES, TEMPLATES

GENERATOR_VERSION = "2.0.0"  # v2: more benign hard-negative + scam templates, gendered name slots
REPO_ROOT = Path(__file__).resolve().parents[2]
N_USERS = 500
LANG_WEIGHTS = {"en": 0.40, "hi-en": 0.35, "hi": 0.25}

# Per-family behaviour. amount = (low, high) log-uniform INR, unless noted.
# p_* are probabilities of each SIMULATED context signal.
PROFILES = {
    "digital_arrest": dict(amount=(20_000, 300_000), odd_hour=0.10, types={"TRANSFER": .85, "PAYMENT": .15},
                           hour_lambda=0.8, day_lambda=2.0,
                           p=dict(call=.90, screen=.35, device=.05, geo=.03, login=.05, pasted=.50, new_payee=.95, mule=.15)),
    "kyc_refund":     dict(amount=(2_000, 50_000), tiny_prob=0.30, odd_hour=0.15, types={"PAYMENT": .5, "TRANSFER": .5},
                           hour_lambda=0.4, day_lambda=2.0,
                           p=dict(call=.75, screen=.55, device=.10, geo=.05, login=.10, pasted=.40, new_payee=.90, mule=.12)),
    "lottery":        dict(amount=(499, 15_000), odd_hour=0.20, types={"PAYMENT": .7, "TRANSFER": .3},
                           hour_lambda=0.4, day_lambda=2.0,
                           p=dict(call=.35, screen=.05, device=.05, geo=.03, login=.05, pasted=.60, new_payee=.95, mule=.12)),
    "upi_collect":    dict(amount=(1_000, 40_000), odd_hour=0.15, types={"DEBIT": .6, "PAYMENT": .4},
                           hour_lambda=0.4, day_lambda=2.0,
                           p=dict(call=.55, screen=.10, device=.05, geo=.03, login=.05, pasted=.20, new_payee=.90, mule=.12)),
    "job_task":       dict(amount=(200, 30_000), odd_hour=0.30, types={"PAYMENT": .5, "TRANSFER": .5},
                           hour_lambda=1.5, day_lambda=5.0,
                           p=dict(call=.10, screen=.05, device=.05, geo=.03, login=.05, pasted=.80, new_payee=.70, mule=.15)),
    "benign":         dict(amount=None, large_prob=0.08, odd_hour=0.08, types={"PAYMENT": .65, "TRANSFER": .25, "DEBIT": .10},
                           hour_lambda=0.3, day_lambda=2.0,
                           p=dict(call=.08, screen=.02, device=.06, geo=.02, login=.05, pasted=.15, new_payee=.25, mule=.005)),
}
SIGNAL_COLUMNS = {
    "call": "call_in_progress", "screen": "screen_share_active", "device": "new_device",
    "geo": "geo_velocity_anomaly", "login": "new_login_recent", "pasted": "pasted_vpa",
    "new_payee": "new_payee", "mule": "payee_is_mule",
}


def poisson(rng, lam):
    """Knuth's Poisson sampler (stdlib only)."""
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def log_uniform(rng, low, high):
    return math.exp(rng.uniform(math.log(low), math.log(high)))


def weighted_choice(rng, weights):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def digits(rng, n, first="123456789"):
    return rng.choice(first) + "".join(rng.choice(string.digits) for _ in range(n - 1))


def fmt_amount(rng, amount):
    return f"{amount:,}" if rng.random() < 0.5 else str(amount)


def make_users(rng):
    users = []
    for i in range(N_USERS):
        typical = math.exp(rng.gauss(math.log(800), 0.8))   # typical payment size, INR
        users.append(dict(user_id=f"u_{i:04d}", mu=math.log(typical), sigma=0.9,
                          balance=typical * rng.uniform(20, 200)))
    return users


def sample_amount(rng, profile, user):
    if profile["amount"] is None:  # benign: user's own spending pattern, sometimes rent/fees
        if rng.random() < profile["large_prob"]:
            return int(rng.uniform(10_000, 60_000))
        return max(1, int(math.exp(rng.gauss(user["mu"], user["sigma"]))))
    if rng.random() < profile.get("tiny_prob", 0.0):  # "verify with Rs 1" style
        return rng.randint(1, 10)
    return int(log_uniform(rng, *profile["amount"]))


def history_percentile(amount, user):
    z = (math.log(amount) - user["mu"]) / user["sigma"]
    return round(50 * (1 + math.erf(z / math.sqrt(2))), 1)


def sample_hour(rng, odd_prob):
    if rng.random() < odd_prob:
        return rng.choice([22, 23, 0, 1, 2, 3, 4, 5])
    return rng.randint(6, 21)


def fill_slots(rng, lang, amount):
    vals = {}
    for slot, options in FILLERS.items():
        pool = options[lang] if isinstance(options, dict) else options
        vals[slot] = rng.choice(pool)
    name = vals["name"]
    vals.update(
        amount=fmt_amount(rng, amount),
        earn=fmt_amount(rng, rng.choice([500, 800, 1200, 2000, 3500, 5000])),
        otp=digits(rng, 6),
        phone=digits(rng, 10, first="6789"),
        acct=digits(rng, rng.randint(11, 14)),
        last4=digits(rng, 4, first=string.digits),
        ref=digits(rng, 12),
        case_id=f"{rng.choice(['CBI', 'MH', 'DL'])}/{digits(rng, 4)}/2026",
        task=str(rng.randint(1, 30)),
        date=f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/2026",
        vpa=rng.choice([f"{name.lower()}{rng.randint(10, 99)}@ybl", f"claim.prize{rng.randint(1, 999)}@paytm",
                        f"refund.desk{rng.randint(1, 99)}@okaxis"]),
    )
    return vals


def perturb(rng, text):
    """Light, realistic surface noise (case, punctuation, spacing)."""
    if rng.random() < 0.25:
        text = text.lower()
    if rng.random() < 0.10:
        text = text.rstrip(".!।")
    if rng.random() < 0.05:
        text = text.replace(" ", "  ", 1)
    return text


def make_row(rng, idx, key, label, users, seen_texts):
    family = key if label == 1 else "benign"
    profile = PROFILES[family]
    user = rng.choice(users)
    amount = sample_amount(rng, profile, user)

    # Message: retry until unique so duplicate rows don't inflate metrics
    for _ in range(50):
        lang = weighted_choice(rng, LANG_WEIGHTS)
        templates = TEMPLATES[key][lang]
        t_idx = rng.randrange(len(templates))
        text = perturb(rng, templates[t_idx].format(**fill_slots(rng, lang, amount)))
        if text not in seen_texts:
            break
    else:
        raise RuntimeError(f"Could not generate a unique message for {key}")
    seen_texts.add(text)

    hour = sample_hour(rng, profile["odd_hour"])
    old_orig = round(max(amount * rng.uniform(1.05, 6.0), user["balance"] * rng.uniform(0.5, 1.5)), 2)
    old_dest = round(math.exp(rng.gauss(math.log(20_000), 1.5)), 2)  # same distribution for all rows
    last_hour = poisson(rng, profile["hour_lambda"])

    row = dict(
        event_id=f"evt_{idx:05d}", user_id=user["user_id"], data_source="synthetic",
        text=text, label=label, family=family, subtype=key,
        template_id=f"{key}_{lang.replace('-', '')}_{t_idx + 1:02d}", language=lang,
        amount=float(amount), amount_vs_history_percentile=history_percentile(amount, user),
        oldbalance_orig=old_orig, newbalance_orig=round(old_orig - amount, 2),
        oldbalance_dest=old_dest, newbalance_dest=round(old_dest + amount, 2),
        hour=hour, day=rng.randint(1, 28), transaction_type=weighted_choice(rng, profile["types"]),
        txn_count_last_hour=last_hour, txn_count_last_day=last_hour + poisson(rng, profile["day_lambda"]),
        fan_out_count=1 + poisson(rng, 1.0 if label == 0 else 0.8),
        odd_hour=int(hour < 6 or hour >= 22),  # derived from hour, not sampled independently
    )
    for short, col in SIGNAL_COLUMNS.items():
        row[col] = int(rng.random() < profile["p"][short])
    return row


def generate(seed):
    rng = random.Random(seed)
    users = make_users(rng)
    plan = [(f, 1, ROWS_PER_KEY[f]) for f in SCAM_FAMILIES] + \
           [(s, 0, ROWS_PER_KEY[s]) for s in BENIGN_SUBTYPES]
    rows, seen = [], set()
    for key, label, n in plan:
        for _ in range(n):
            rows.append(make_row(rng, len(rows), key, label, users, seen))
    rng.shuffle(rows)
    return rows


def summarise(rows, seed):
    by_family_lang = defaultdict(Counter)
    templates = defaultdict(set)
    for r in rows:
        by_family_lang[r["family"]][r["language"]] += 1
        templates[r["family"]].add(r["template_id"])

    signal_cols = ["call_in_progress", "screen_share_active", "pasted_vpa", "new_payee", "odd_hour"]
    signal_rates, amount_median = {}, {}
    for fam in SCAM_FAMILIES + ["benign"]:
        fam_rows = [r for r in rows if r["family"] == fam]
        signal_rates[fam] = {c: round(sum(r[c] for r in fam_rows) / len(fam_rows), 2) for c in signal_cols}
        amounts = sorted(r["amount"] for r in fam_rows)
        amount_median[fam] = amounts[len(amounts) // 2]

    return {
        "data_source": "synthetic", "generator_version": GENERATOR_VERSION, "seed": seed,
        "total_rows": len(rows),
        "label_counts": dict(Counter(r["label"] for r in rows)),
        "rows_by_family_and_language": {f: dict(c) for f, c in by_family_lang.items()},
        "templates_per_family": {f: len(t) for f, t in templates.items()},
        "signal_rates": signal_rates,
        "median_amount_inr": amount_median,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "synthetic")
    args = parser.parse_args()

    rows = generate(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "events.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = summarise(rows, args.seed)
    with open(args.out / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # ---- human-readable report
    print(f"Wrote {len(rows)} rows -> {csv_path}")
    print(f"Labels: {summary['label_counts']}  (1 = scam, 0 = benign)")
    print("\nRows by family x language:")
    print(f"  {'family':<16}{'en':>6}{'hi-en':>7}{'hi':>6}{'templates':>11}")
    for fam, c in summary["rows_by_family_and_language"].items():
        print(f"  {fam:<16}{c.get('en', 0):>6}{c.get('hi-en', 0):>7}{c.get('hi', 0):>6}"
              f"{summary['templates_per_family'][fam]:>11}")
    print("\nSimulated signal rates (shows scam/benign overlap):")
    cols = list(next(iter(summary["signal_rates"].values())))
    print("  " + f"{'family':<16}" + "".join(f"{c[:12]:>14}" for c in cols) + f"{'median Rs':>12}")
    for fam, rates in summary["signal_rates"].items():
        print("  " + f"{fam:<16}" + "".join(f"{rates[c]:>14}" for c in cols)
              + f"{summary['median_amount_inr'][fam]:>12,.0f}")
    print("\nOne sample per family:")
    for fam in SCAM_FAMILIES + ["benign"]:
        r = next(r for r in rows if r["family"] == fam)
        print(f"  [{fam} | {r['language']} | {r['template_id']}] {r['text'][:110]}")


if __name__ == "__main__":
    main()
