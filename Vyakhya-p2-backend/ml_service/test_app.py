"""Tests for app.py against the FROZEN risk engine (all data synthetic).
Run with the engine's environment:  ..\\..\\backend\\.venv\\Scripts\\python -m pytest -q
Needs model_registry/risk/risk-0.2.0/ (built by backend/train_eval.py)."""

import copy
from datetime import datetime

import pytest

import app as service

pytestmark = pytest.mark.skipif(service.ENGINE is None, reason="frozen risk engine artifacts not found")

QUIET = {
    "redacted_text": "Sending rent for this month",
    "context": {"new_device": False, "new_geo": False, "screen_share": False, "call_active": False},
    "payment": {"payee_vpa": "landlord@okaxis", "amount": 2000, "payee_age_days": 400, "user_avg_amount": 2000,
                "payee_prior_txns": 40, "hour": 14},
}
SCAM = {
    "redacted_text": "Congratulations! Cashback of Rs 1,499 is waiting. Approve the collect request and enter your UPI PIN to receive it.",
    "context": {"new_device": False, "new_geo": False, "screen_share": True, "call_active": True},
    "payment": {"payee_vpa": "rewards.desk@okhdfc", "amount": 1499, "payee_age_days": 1, "user_avg_amount": 900,
                "direction": "collect", "hour": 21},
}


def body(base=QUIET, **changes):
    b = copy.deepcopy(base)
    for key, value in changes.items():
        if isinstance(value, dict):
            b[key].update(value)
        else:
            b[key] = value
    return b


@pytest.fixture
def client():
    return service.app.test_client()


# --- /health -----------------------------------------------------------------
def test_health_reports_frozen_versions(client):
    out = client.get("/health").get_json()
    assert out["status"] == "ok" and out["model_version"] == "risk-0.2.0" and out["rules_version"] == "v2"
    assert out["shipped_system"] == "with_rule_score"


# --- scoring -------------------------------------------------------------------
def test_quiet_known_payee_is_low(client):
    out = client.post("/predict", json=QUIET).get_json()
    assert out["tier"] == "LOW" and out["hard_rule_floor"] == 0
    assert 0 <= out["R"] < 40


def test_pin_to_receive_scam_is_critical(client):
    out = client.post("/predict", json=SCAM).get_json()
    assert out["R"] >= 90 and out["tier"] == "CRITICAL"
    assert out["reasons"][:2] == ["PIN_TO_RECEIVE", "AMOUNT_MISMATCH"]
    assert out["disclaimer"] and out["ask_user"]
    assert out["context_flags"] == ["SCREEN_SHARE", "CALL_ACTIVE"]


def test_r_equals_engine_score_exactly(client):
    """The service must not change the evaluated score."""
    txn = service.to_engine_txn(SCAM["payment"])
    direct = service.ENGINE.score(text=service.for_engine(SCAM["redacted_text"]), txn=txn)
    assert client.post("/predict", json=SCAM).get_json()["R"] == float(direct["risk_score"])


def test_context_flags_do_not_change_r(client):
    off = body(SCAM, context={"screen_share": False, "call_active": False})
    assert client.post("/predict", json=off).get_json()["R"] == client.post("/predict", json=SCAM).get_json()["R"]


def test_placeholder_standins_keep_otp_request(client):
    out = client.post("/predict", json=body(redacted_text="Pay now or face arrest, share [OTP]")).get_json()
    assert "OTP_REQUEST" in out["all_reasons"] and out["ask_user"]


def test_hindi_bill_receipt_regression(client):
    """Rules v2: a merchant acknowledging your payment is not money promised to you."""
    b = body(redacted_text="ब्रॉडबैंड बिल के ₹799 प्राप्त हुए, धन्यवाद।",
             payment={"amount": 799, "direction": "debit", "payee_prior_txns": 30})
    out = client.post("/predict", json=b).get_json()
    assert out["hard_rule_floor"] == 0 and out["R"] < 90 and "AMOUNT_MISMATCH" not in out["all_reasons"]


@pytest.mark.parametrize("days, expected", [(0, 0), (6.9, 0), (7, None), (400, None)])
def test_payee_history_from_age_when_prior_missing(days, expected):
    p = {"amount": 100, "payee_age_days": days, "user_avg_amount": 100}
    assert service.to_engine_txn(p)["beneficiary_prior_txns"] == expected


def test_unknown_payee_reason(client):
    b = body(payment={"payee_age_days": 400})
    del b["payment"]["payee_prior_txns"]
    assert "PAYEE_UNKNOWN" in client.post("/predict", json=b).get_json()["all_reasons"]


@pytest.mark.parametrize("amount, avg, low, high", [(100, 100, 49, 51), (1000, 100, 99, 100.1), (10, 100, 0, 1), (5, 0, 50, 50)])
def test_history_percentile(amount, avg, low, high):
    assert low <= service.history_percentile(amount, avg) <= high


def test_hour_defaults_to_server_clock():
    p = {"amount": 100, "payee_age_days": 400, "user_avg_amount": 100}
    assert service.to_engine_txn(p, now=datetime(2026, 10, 25, 3, 0))["hour"] == 3


def test_engine_unavailable_returns_503(client, monkeypatch):
    monkeypatch.setattr(service, "ENGINE", None)
    assert client.post("/predict", json=QUIET).status_code == 503
    assert client.get("/health").status_code == 503


def test_engine_crash_returns_500_without_text_in_body(client, monkeypatch):
    class Broken:
        def score(self, **_):
            raise RuntimeError("boom")

    monkeypatch.setattr(service, "ENGINE", Broken())
    res = client.post("/predict", json=QUIET)
    assert res.status_code == 500 and "rent" not in res.get_data(as_text=True)


# --- validation ----------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        {k: v for k, v in QUIET.items() if k != "redacted_text"},
        {k: v for k, v in QUIET.items() if k != "context"},
        {k: v for k, v in QUIET.items() if k != "payment"},
        body(redacted_text=123),
        body(context={"screen_share": "yes"}),
        body(context={"new_geo": None}),
        body(payment={"amount": "500"}),
        body(payment={"amount": True}),
        body(payment={"amount": 0}),
        body(payment={"payee_age_days": -1}),
        body(payment={"payee_prior_txns": -2}),
        body(payment={"hour": 24}),
        body(payment={"direction": "sideways"}),
        body(redacted_text="x" * 5001),
        [1, 2, 3],
    ],
)
def test_400_on_missing_or_bad_fields(client, bad):
    res = client.post("/predict", json=bad)
    assert res.status_code == 400
    assert res.get_json()["details"]


def test_400_on_invalid_json(client):
    res = client.post("/predict", data="{oops", content_type="application/json")
    assert res.status_code == 400
    assert res.get_json() == {"error": "body must be valid JSON"}


def test_413_on_huge_body(client):
    assert client.post("/predict", data="x" * 40000, content_type="application/json").status_code == 413


def test_extra_fields_like_session_id_are_ignored(client):
    assert client.post("/predict", json=body(session_id="s1")).status_code == 200


def test_cutoffs_are_the_engine_bands_for_the_signal_mode(client):
    out = client.post("/predict", json=SCAM).get_json()
    bands = service.ENGINE.bands[out["signal_mode"]]
    assert out["cutoffs"] == {"medium": bands["medium"], "high": bands["high"]}
