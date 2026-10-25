"""Rule-layer tests: scam patterns fire, hard negatives don't. Run: python -m pytest tests/test_rules.py -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from risk.rules import evaluate  # noqa: E402

SCAMS = [
    # (text, flags that must be True, expect hard floor)
    ("Cashback of Rs 4,878 is waiting for you. Scan the QR code and enter your PIN to receive it.",
     ["reward_claim", "asks_pin", "collect_approval"], True),
    ("Bhai main aapka sofa OLX pe kharid raha hoon. Rs 5000 ki request bheji hai, PIN daalo paise aa jayenge.",
     ["asks_pin", "collect_approval", "reward_claim"], True),
    ("₹2000 का कैशबैक आपका इंतज़ार कर रहा है। क्यूआर स्कैन करें और पिन डालें।",
     ["reward_claim", "asks_pin", "collect_approval"], True),
    ("Your refund is on hold. Share the OTP sent to your phone with our executive to release it.",
     ["asks_otp", "reward_claim"], False),
    ("Congratulations! You won Rs 25,00,000 in the Jio Lucky Draw. Pay processing fee of Rs 4999 to claim.",
     ["reward_claim", "fee_to_claim"], False),
    ("Your KYC expired. Account will be blocked today. Update now: bank-secure-login.xyz",
     ["urgency", "has_link"], False),
    ("Aapka refund pending hai. O T P bata do jaldi", ["asks_otp", "reward_claim", "urgency"], False),
]

HARD_NEGATIVES = [
    "482913 is your OTP for login to HDFC NetBanking. Valid for 10 minutes. Do not share it with anyone.",
    "Aapka SBI OTP 551203 hai. Kisi ke saath share na karein.",
    "839201 आपका ICICI ओटीपी है। 10 मिनट के लिए मान्य। इसे किसी के साथ साझा न करें।",
    "Dear customer, Rs 2,500 has been debited from your Axis account XX4821 on 12/03/2026.",
    "Rs 1200 credited to your SBI a/c XX9921 by UPI ref 402911223344. Available balance updated.",
    "Your electricity bill of Rs 1,340 for this month is generated. Due date 15/04/2026.",
    "Refund of Rs 499 for your Amazon order has been initiated. It will reflect in 5-7 days.",
    "Never share your UPI PIN with anyone. SBI will never ask for it.",
]


@pytest.mark.parametrize("text,must,floor", SCAMS)
def test_scam_flags(text, must, floor):
    r = evaluate(text)
    missing = [f for f in must if not r.flags[f]]
    assert not missing, f"missing flags {missing}; got {r.flags}"
    assert (r.floor == 90) == floor


@pytest.mark.parametrize("text", HARD_NEGATIVES)
def test_hard_negatives_no_scam_flags(text):
    r = evaluate(text)
    fired = [f for f in ("asks_otp", "asks_pin", "collect_approval", "fee_to_claim") if r.flags[f]]
    assert not fired, f"false flags {fired}"
    assert r.floor == 0


def test_otp_notice_is_not_a_scam_signal():
    r = evaluate("482913 is your OTP. Do not share it with anyone.")
    assert r.flags["otp_notice"] and not r.flags["asks_otp"]


def test_amount_mismatch_floor():
    msg = "Congratulations, cashback of Rs 1,499 credited. Approve to receive."
    assert evaluate(msg, txn_amount=1499, txn_direction="collect").flags["amount_mismatch"]
    assert evaluate(msg, txn_amount=1499, txn_direction="collect").floor == 90
    assert not evaluate(msg, txn_amount=1499, txn_direction="credit").flags["amount_mismatch"]


def test_fee_amount_is_not_a_promise():
    # Rs 4999 is a FEE, not money promised in -> paying it is not an "amount mismatch"
    msg = "You won Rs 25,00,000. Pay processing fee of Rs 4999 to claim."
    assert not evaluate(msg, txn_amount=4999, txn_direction="debit").flags["amount_mismatch"]


def test_disclaimer_and_feedback():
    r = evaluate("Refund on hold. Share OTP to release.")
    assert r.show_pin_disclaimer and r.ask_feedback


def test_input_is_capped():
    r = evaluate("a" * 100_000 + " share otp")
    assert not r.flags["asks_otp"]  # tail beyond MAX_INPUT_CHARS is ignored


if __name__ == "__main__":  # lets run.bat execute it: .\run.bat tests\test_rules.py
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))


def test_hindi_credited_is_not_a_fee():
    r = evaluate("₹499 का रिफंड जमा हो गया है, आपको कुछ करने की ज़रूरत नहीं।")
    assert r.flags["reward_claim"] and not r.flags["fee_to_claim"]
    assert evaluate("अगला टास्क खोलने के लिए ₹500 जमा करें।").flags["fee_to_claim"]


# ---- v2 direction fix: one bill-receipt case (no money-in) and one directional case (money-in) per verb.
# Receipts mirror template merchant_bill_hi_07, paired with a DEBIT of the same amount.
RECEIPT_NOT_MONEY_IN = [
    ("प्राप्त हुए", "ब्रॉडबैंड बिल के ₹799 प्राप्त हुए, धन्यवाद।"),
    ("mile hain", "Broadband bill ke Rs 799 mile hain, dhanyavaad."),
    ("credit ho jayega", "Broadband bill ka Rs 799 credit ho jayega, dhanyavaad."),
    ("received from (you)", "Payment of Rs 799 received from you towards broadband bill, thank you."),
    ("प्राप्त हुए (आपसे)", "ब्रॉडबैंड बिल के ₹799 आपसे प्राप्त हुए, धन्यवाद।"),
    ("mile hain (aapse)", "Broadband bill ke Rs 799 aapse mile hain, dhanyavaad."),
]
DIRECTIONAL_MONEY_IN = [
    ("प्राप्त हुए", "आपको राहुल से ₹799 प्राप्त हुए हैं। पैसे खाते में लेने के लिए अनुरोध स्वीकार करें।"),
    ("mile hain", "Aapko Rahul se Rs 799 mile hain. Request approve karo."),
    ("credit ho jayega", "Rs 799 aapke account mein credit ho jayega, bas request accept karo."),
    ("received from", "Payment of Rs 799 received from Rahul. Approve the request to credit it."),
]


@pytest.mark.parametrize("verb,text", RECEIPT_NOT_MONEY_IN)
def test_receipt_verbs_are_not_money_in(verb, text):
    r = evaluate(text, txn_amount=799, txn_direction="debit")
    assert not r.flags["amount_mismatch"], f"{verb}: receipt read as money promised to the user"
    assert not r.flags["reward_claim"], f"{verb}: receipt flagged as reward"
    assert r.floor == 0


@pytest.mark.parametrize("verb,text", DIRECTIONAL_MONEY_IN)
def test_directional_verbs_are_money_in(verb, text):
    r = evaluate(text, txn_amount=799, txn_direction="collect")
    assert r.flags["reward_claim"], f"{verb}: directional money-in not recognised"
    assert r.flags["amount_mismatch"] and r.floor == 90, f"{verb}: mismatch floor did not fire"


def _bill_receipt_rows():
    """The 6 benign rows of template merchant_bill_hi_07 (Hindi bill receipt) with their matching debit."""
    import csv
    from risk.config import MESSAGES_PATH, TRANSACTIONS_PATH
    with open(TRANSACTIONS_PATH, encoding="utf-8") as f:
        tx = {r["msg_id"]: r for r in csv.DictReader(f)}
    with open(MESSAGES_PATH, encoding="utf-8") as f:
        return [(m["text"], float(tx[m["msg_id"]]["amount"]), tx[m["msg_id"]]["direction"])
                for m in csv.DictReader(f) if m["template_id"] == "merchant_bill_hi_07"]


def test_regression_hindi_bill_receipt_no_floor():
    rows = _bill_receipt_rows()
    assert len(rows) == 6 and all(d == "debit" for _, _, d in rows)
    for text, amount, direction in rows:
        r = evaluate(text, txn_amount=amount, txn_direction=direction)
        assert r.floor == 0 and not r.flags["amount_mismatch"]
