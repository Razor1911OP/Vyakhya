"""Which BENIGN synthetic rows hit a hard-rule floor, and which rule fired? Prints ids/flags only, no text."""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from risk.config import MESSAGES_PATH, TRANSACTIONS_PATH  # noqa: E402
from risk.rules import evaluate  # noqa: E402

with open(TRANSACTIONS_PATH, encoding="utf-8") as f:
    tx = {r["msg_id"]: r for r in csv.DictReader(f)}
hits = Counter()
with open(MESSAGES_PATH, encoding="utf-8") as f:
    for m in csv.DictReader(f):
        if m["label"] != "0":
            continue
        t = tx[m["msg_id"]]
        r = evaluate(m["text"], float(t["amount"]), t["direction"])
        if r.floor:
            why = "amount_mismatch" if r.flags["amount_mismatch"] else "reward+pin/collect"
            hits[(m["template_id"], t["direction"], why)] += 1
for (tid, direction, why), n in sorted(hits.items()):
    print(f"{tid:<26} direction={direction:<7} rule={why:<20} rows={n}")
print("total benign floor hits:", sum(hits.values()))
