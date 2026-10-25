"""
Smoke test of POST /api/v1/score through the full FastAPI app (in-process ASGI via TestClient).
Sends one scam message and one benign payment; checks R, tier, reason codes, soft_hold, latency < 300 ms.
Prints scores and reason codes only, never message text.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

BAL = {"oldbalance_orig": 50000, "newbalance_orig": 48500, "oldbalance_dest": 2000, "newbalance_dest": 3500}
CASES = {
    "scam: cashback + PIN + collect": {
        "message_text": "Congratulations! Cashback of Rs 1,499 is waiting. Approve the collect request and enter your UPI PIN to receive it.",
        "transaction": {"amount": 1499, "hour": 21, "day": 12, "transaction_type": "DEBIT", "direction": "collect",
                        "beneficiary_prior_txns": 0, **BAL},
        "context": {"simulated": True}, "user_id": "smoke_user_scam"},
    "benign: grocery to known payee": {
        "transaction": {"amount": 640, "hour": 18, "day": 12, "transaction_type": "PAYMENT", "direction": "debit",
                        "beneficiary_prior_txns": 85, "amount_vs_history_percentile": 55, **BAL},
        "context": {"simulated": True}, "user_id": "smoke_user_benign"},
}
EXPECT = {"scam: cashback + PIN + collect": ("CRITICAL", True), "benign: grocery to known payee": ("LOW", False)}


def main():
    failures = []
    with TestClient(app) as client:          # runs startup -> loads frozen registry artifacts
        client.post("/api/v1/score", json=CASES["benign: grocery to known payee"])   # warm-up, not measured
        for name, body in CASES.items():
            lat = []
            for _ in range(20):
                t0 = time.perf_counter()
                resp = client.post("/api/v1/score", json=body)
                lat.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200, (name, resp.status_code, resp.text[:200])
            r = resp.json()
            lat.sort()
            p95 = lat[int(0.95 * len(lat)) - 1]
            print(f"\n{name}")
            print(f"  R={r['risk_score']}  tier={r['tier']}  soft_hold={r['soft_hold']}  "
                  f"server latency_ms={r['latency_ms']}  round-trip p50={lat[len(lat)//2]:.1f} ms p95={p95:.1f} ms (n=20)")
            print(f"  reason codes: {[c['code'] for c in r['reason_codes']]}")
            print(f"  model_versions: {[(m['model_name'], m['version'], m['used']) for m in r['model_versions']]}")
            print(f"  component_scores: {r['component_scores']}  friction_type={r['friction_type']}")
            for key in ("risk_score", "tier", "reason_codes", "soft_hold", "latency_ms"):
                if key not in r:
                    failures.append(f"{name}: missing {key}")
            if not r["reason_codes"]:
                failures.append(f"{name}: no reason codes")
            if p95 >= 300:
                failures.append(f"{name}: p95 {p95:.0f} ms >= 300 ms")
            tier, hold = EXPECT[name]
            if (r["tier"], r["soft_hold"]) != (tier, hold):
                failures.append(f"{name}: expected tier={tier} soft_hold={hold}, got {r['tier']} {r['soft_hold']}")
    print("\nRESULT:", "PASS" if not failures else "FAIL")
    for f in failures:
        print("  -", f)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
