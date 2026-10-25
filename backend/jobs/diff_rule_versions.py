"""Compare rules v1 (frozen copy) vs current rules on the synthetic corpus. Prints template ids and counts, no text."""
import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from risk.config import MESSAGES_PATH, TRANSACTIONS_PATH  # noqa: E402
from risk import rules as v2  # noqa: E402

loader = importlib.machinery.SourceFileLoader("rules_v1", str(BACKEND / "risk" / "rules_v1_frozen.py.txt"))
spec = importlib.util.spec_from_loader("rules_v1", loader)
v1 = importlib.util.module_from_spec(spec)
loader.exec_module(v1)

with open(TRANSACTIONS_PATH, encoding="utf-8") as f:
    tx = {r["msg_id"]: r for r in csv.DictReader(f)}
changes = Counter()
floor = Counter()
with open(MESSAGES_PATH, encoding="utf-8") as f:
    for m in csv.DictReader(f):
        t = tx[m["msg_id"]]
        a = v1.evaluate(m["text"], float(t["amount"]), t["direction"])
        b = v2.evaluate(m["text"], float(t["amount"]), t["direction"])
        lab = "scam" if m["label"] == "1" else "benign"
        floor[(lab, "v1")] += a.floor > 0
        floor[(lab, "v2")] += b.floor > 0
        for k in ("reward_claim", "amount_mismatch"):
            if a.flags[k] != b.flags[k]:
                changes[(lab, m["template_id"], k, f"{a.flags[k]}->{b.flags[k]}")] += 1
print("Hard-floor hits:", {f"{lab}/{v}": n for (lab, v), n in sorted(floor.items())})
print("Flag changes v1 -> v2 (label, template, flag, change): rows")
for key, n in sorted(changes.items()):
    print("  ", key, n)
print("templates changed:", len({k[1] for k in changes}))
