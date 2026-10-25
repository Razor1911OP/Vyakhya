"""Tests for app.py. Run: .venv\\Scripts\\python -m pytest -q   (all data synthetic)"""

import copy

import joblib
import pytest

import app as service


class FakeModel:
    """Stands in for the scikit-learn model: always returns P(scam) = p."""

    def __init__(self, p):
        self.p = p

    def predict_proba(self, texts):
        return [[1 - self.p, self.p] for _ in texts]


QUIET = {
    "redacted_text": "Sending rent for this month",
    "context": {"new_device": False, "new_geo": False, "screen_share": False, "call_active": False},
    "payment": {"payee_vpa": "landlord@okaxis", "amount": 2000, "payee_age_days": 400, "user_avg_amount": 2000},
}


def body(**changes):
    """QUIET body with nested overrides, e.g. body(context={"screen_share": True})."""
    b = copy.deepcopy(QUIET)
    for key, value in changes.items():
        if isinstance(value, dict):
            b[key].update(value)
        else:
            b[key] = value
    return b


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(service, "MODEL", None)  # default: no model -> 0.5
    return service.app.test_client()


# --- /health -----------------------------------------------------------------
def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


# --- scoring -------------------------------------------------------------------
def test_quiet_payment_without_model_is_neutral_20(client):
    res = client.post("/predict", json=QUIET)
    assert res.status_code == 200
    # only the neutral text score contributes: 0.40 * 0.5 * 100
    assert res.get_json() == {"R": 20.0, "reasons": []}


def test_everything_firing_is_100_with_top_3_reasons(client, monkeypatch):
    monkeypatch.setattr(service, "MODEL", FakeModel(1.0))
    b = body(
        context={"new_device": True, "new_geo": True, "screen_share": True, "call_active": True},
        payment={"amount": 10000, "payee_age_days": 1, "user_avg_amount": 2000},
    )
    out = client.post("/predict", json=b).get_json()
    assert out["R"] == 100.0
    assert out["reasons"] == ["SCAM_TEXT", "SCREEN_SHARE", "NEW_PAYEE"]


def test_screen_share_call_new_payee_spike_no_model(client):
    # Same signals as api/body.json: 45000 vs avg 2000, payee 1 day old.
    b = body(
        context={"new_device": True, "screen_share": True, "call_active": True},
        payment={"amount": 45000, "payee_age_days": 1, "user_avg_amount": 2000},
    )
    out = client.post("/predict", json=b).get_json()
    # 20 text + 15 screen + 12 payee + 12 spike + 8 call + 8 device
    assert out["R"] == 75.0
    assert out["reasons"] == ["SCREEN_SHARE", "NEW_PAYEE", "AMOUNT_SPIKE"]


def test_scam_text_reason_needs_model_confidence(client, monkeypatch):
    monkeypatch.setattr(service, "MODEL", FakeModel(0.9))
    out = client.post("/predict", json=QUIET).get_json()
    assert out == {"R": 36.0, "reasons": ["SCAM_TEXT"]}

    monkeypatch.setattr(service, "MODEL", FakeModel(0.55))  # not confident enough
    assert client.post("/predict", json=QUIET).get_json()["reasons"] == []


def test_model_text_is_passed_to_model(client, monkeypatch):
    seen = []

    class Spy(FakeModel):
        def predict_proba(self, texts):
            seen.extend(texts)
            return super().predict_proba(texts)

    monkeypatch.setattr(service, "MODEL", Spy(0.2))
    client.post("/predict", json=body(redacted_text="share [OTP] now"))
    assert seen == ["share [OTP] now"]


def test_model_crash_falls_back_to_neutral(client, monkeypatch):
    class Broken:
        def predict_proba(self, texts):
            raise RuntimeError("boom")

    monkeypatch.setattr(service, "MODEL", Broken())
    assert client.post("/predict", json=QUIET).get_json()["R"] == 20.0


@pytest.mark.parametrize("days, is_new", [(0, True), (6.9, True), (7, False), (400, False)])
def test_new_payee_boundary(client, days, is_new):
    out = client.post("/predict", json=body(payment={"payee_age_days": days})).get_json()
    assert ("NEW_PAYEE" in out["reasons"]) is is_new


@pytest.mark.parametrize(
    "amount, avg, expected",
    [(1000, 2000, 0.0), (2000, 2000, 0.0), (4000, 2000, 0.25), (6000, 2000, 0.5), (10000, 2000, 1.0),
     (99999, 2000, 1.0), (500, 0, 0.5)],
)
def test_amount_spike_scale(amount, avg, expected):
    assert service.amount_spike(amount, avg) == expected


def test_amount_spike_reason_from_2x(client):
    assert "AMOUNT_SPIKE" not in client.post("/predict", json=body(payment={"amount": 3900})).get_json()["reasons"]
    assert "AMOUNT_SPIKE" in client.post("/predict", json=body(payment={"amount": 4000})).get_json()["reasons"]


def test_weights_sum_to_one():
    assert sum(service.WEIGHTS.values()) == pytest.approx(1.0)


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
        body(payment={"amount": True}),  # bool is not a number here
        body(payment={"payee_age_days": -1}),
        body(redacted_text="x" * 5001),
        [1, 2, 3],
    ],
)
def test_400_on_missing_or_bad_fields(client, bad):
    res = client.post("/predict", json=bad)
    assert res.status_code == 400
    assert res.get_json()["details"]


def test_400_on_missing_context_flag(client):
    b = copy.deepcopy(QUIET)
    del b["context"]["call_active"]
    res = client.post("/predict", json=b)
    assert res.status_code == 400
    assert "context.call_active must be true or false" in res.get_json()["details"]


def test_400_on_invalid_json(client):
    res = client.post("/predict", data="{oops", content_type="application/json")
    assert res.status_code == 400
    assert res.get_json() == {"error": "body must be valid JSON"}


def test_413_on_huge_body(client):
    res = client.post("/predict", data="x" * 40000, content_type="application/json")
    assert res.status_code == 413


def test_extra_fields_like_session_id_are_ignored(client):
    assert client.post("/predict", json=body(session_id="s1")).status_code == 200


# --- model loading ---------------------------------------------------------------
def test_load_model_missing_file_returns_none(tmp_path):
    assert service.load_model(tmp_path / "nope.joblib") is None


def test_load_model_corrupt_file_returns_none(tmp_path):
    p = tmp_path / "text.joblib"
    p.write_bytes(b"not a model")
    assert service.load_model(p) is None


def test_load_model_without_predict_proba_returns_none(tmp_path):
    p = tmp_path / "text.joblib"
    joblib.dump({"not": "a model"}, p)
    assert service.load_model(p) is None


def test_load_real_sklearn_pipeline(tmp_path, monkeypatch):
    # Tiny pipeline shaped like what ml/train.py will save.
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    texts = ["share [OTP] urgently or account blocked", "kyc expired send [OTP] now",
             "lunch at 1?", "sending rent for this month"]
    pipe = make_pipeline(TfidfVectorizer(), LogisticRegression()).fit(texts, [1, 1, 0, 0])
    p = tmp_path / "text.joblib"
    joblib.dump(pipe, p)

    model = service.load_model(p)
    assert model is not None
    monkeypatch.setattr(service, "MODEL", model)
    assert service.content_score("send [OTP] now") > service.content_score("rent for this month")
