"""
Signal B: keyword / rule layer (English, Hindi, Hinglish). Pure functions, no I/O, no logging of text.

Flags: asks_otp, otp_notice, asks_pin, collect_approval, reward_claim, fee_to_claim, urgency,
has_link, amount_mismatch. otp_notice is informational and never raises risk.

Hard rules (floor = 90):
  - reward_claim AND (asks_pin OR collect_approval)   -> receiving money never needs a UPI PIN
  - amount_mismatch: message promises money IN, pending transaction sends the same amount OUT
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from risk.config import HARD_RULE_FLOOR, MAX_INPUT_CHARS

FLAG_NAMES = ["asks_otp", "otp_notice", "asks_pin", "collect_approval", "reward_claim",
              "fee_to_claim", "urgency", "has_link", "amount_mismatch"]

# Note: Python's \b is unreliable inside Devanagari words (vowel signs are not \w),
# so Hindi terms are matched as plain substrings.
_I = re.IGNORECASE

OTP_TERM = r"(?:\botp\b|one[\s-]?time[\s-]?password|verification code|\b\d{1,2}[\s-]?digit code|\bcode\b|ओटीपी|कोड)"
SHARE_VERB = (r"(?:\bshare\b|\bsend\b|\btell\b|\bgive\b|\bforward\b|\bprovide\b|\bread out\b|\bbata\w*|\bbhej\w*"
              r"|\bde\s?do\b|\bdijiye\b|बताएं|बताइए|बताओ|बता दें|भेजें|भेजो|साझा कर|दीजिए)")
PIN_TERM = r"(?:\bupi[\s-]?pin\b|\bm-?pin\b|\bpin\b|पिन)"
PIN_VERB = (r"(?:\benter\b|\btype\b|\bput\b|\binput\b|\bshare\b|\bsend\b|\btell\b|\bdaal\w*|\bdal\w*"
            r"|डालें|डालिए|डालो|दर्ज कर|बताएं|भेजें)")

OTP_NOTICE = re.compile(
    r"(do not share|don'?t share|never share|not share|is your otp|share na kar|share mat kar|kisi ke saath share na"
    r"|kabhi otp nahi|never ask for (your )?otp|साझा न कर|साझा मत|कभी ओटीपी नहीं|आपका .{0,20}ओटीपी है)", _I)

COLLECT = re.compile(
    r"(collect request|approve (the |this )?(collect |payment )?request|accept (the |this )?request"
    r"|request (accept|approve) kar\w*|request approve|request accept|approve kar\w*|accept kar\w*"
    r"|(sent|bheji|bheja) (you )?(a |hai )?(collect )?request|request (bheji|sent)|की रिक्वेस्ट भेजी"
    r"|रिक्वेस्ट स्वीकार|स्वीकार करें|scan (the )?qr|qr (code )?scan|क्यूआर स्कैन|pay to receive)", _I)

REWARD = re.compile(
    r"(cash\s?back|refund|prize|lottery|lucky draw|jackpot|bonanza|reward|you (have )?won|\bwon\b|winner"
    r"|\bjeet\w*|\binaam\b|on hold|कैशबैक|रिफंड|इनाम|जीते|लॉटरी|लकी ड्रा|विजेता"
    # money-in PROMISES addressed to the user (the scam premise is "you will receive money")
    r"|to receive (the )?(money|it|payment)|receive (the )?money|paise aa jayenge|paise milenge"
    r"|पैसे पाने)", _I)

# v2 fix: direction-ambiguous "received / credited" verbs. "बिल के ₹799 प्राप्त हुए" (a merchant
# acknowledging YOUR payment) is not money promised to you. These verbs count as money-in only when
# the same sentence names the user as recipient (dative "to you", or "your account") or names a
# sender ("से" / "se" / "from"); a sender who is the user ("from you", "आपसे") means money OUT.
RECEIVED_VERB = re.compile(r"(प्राप्त हुए|\bmile hain\b|\bcredit ho jayega\b|\breceived from\b)", _I)
YOU_RECIPIENT = re.compile(
    r"(\baapko\b|\baap ko\b|\btumhe\b|\btumko\b|\bto you\b"
    r"|(?<!\S)(आपको|तुम्हें|तुमको)(?!\S)"
    r"|\b(aapke|tumhare|your)\s+(\w+\s+)?(account|a/c|khate|wallet|bank)\b"
    r"|(?<!\S)(आपके|तुम्हारे)\s+(\S+\s+)?(खाते|खाता|अकाउंट|वॉलेट|बैंक)(?!\S))", _I)
SENDER = re.compile(r"(\bfrom\b|\bse\b|(?<!\S)से(?!\S))", _I)
FROM_YOU = re.compile(r"(\bfrom you\b|\baapse\b|\baap se\b|\btumse\b|(?<!\S)(आपसे|तुमसे)(?!\S)|(?<!\S)आप से(?!\S))", _I)
_SENTENCE = re.compile(r"[^.!?।\n]+")


def directional_money_in(text: str) -> bool:
    """True if some sentence uses an ambiguous received/credited verb AND names the user as
    recipient or names a (non-user) sender."""
    for m in _SENTENCE.finditer(text):
        s = m.group()
        if RECEIVED_VERB.search(s) and not FROM_YOU.search(s) and (YOU_RECIPIENT.search(s) or SENDER.search(s)):
            return True
    return False


def _sentence_at(text: str, pos: int) -> str:
    for m in _SENTENCE.finditer(text):
        if m.start() <= pos < m.end():
            return m.group()
    return ""


RULES_VERSION = "v2"
RULES_CHANGELOG = {
    "v1": "initial rule layer",
    "v2": ("Direction fix: 'प्राप्त हुए', 'mile hain', 'credit ho jayega', 'received from' no longer count as "
           "money-in by themselves; they need the user named as recipient or a non-user sender in the same "
           "sentence. Found via a benign Hindi bill-receipt template (merchant_bill_hi_07) hitting the "
           "amount-mismatch floor; because it was found by looking at evaluation failures, the separate "
           "validation set is the cleaner check that it generalises. Measured effect on synthetic data: benign "
           "hard-floor hits 6 -> 0 (all merchant_bill_hi_07); scam hard-floor hits unchanged (231); "
           "digital_arrest_hien_01 loses reward_claim on 10 rows ('drugs mile hain' = 'drugs were found', "
           "which v1 misread as money-in)."),
}

# Hindi: only the imperative "जमा कर(ें)" means "deposit/pay"; "जमा हो गया / जमा हुए" means "credited".
FEE = re.compile(r"(processing fee|\bfees?\b|\bcharges?\b|\bgst\b|\btax\b|registration|deposit|security deposit"
                 r"|शुल्क|जीएसटी|जमा कर)", _I)
CLAIM = re.compile(r"(\bclaim\b|release|unlock|withdraw|दावा|निकासी|खोलने|refund|prize|इनाम)", _I)

URGENCY = re.compile(
    r"(urgent|immediately|right now|\bnow\b|\btoday\b|tonight|within \d+ ?(hours|hrs|minutes|mins)|before midnight"
    r"|last chance|expire[sd]?\b|\bblock(ed)?\b|suspend\w*|arrest\w*|\bturant\b|\bjaldi\b|\babhi\b|\baaj\b|ghante"
    r"|तुरंत|अभी|आज|घंटे|गिरफ्तार|बंद कर)", _I)

LINK = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|in|co|xyz|top|ly|link|info|net|org|me|site|online|app)\b(/\S*)?)", _I)

AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr)\s?(\d[\d,]*(?:\.\d+)?)", _I)

NEG_BEFORE = {"not", "never", "don't", "dont", "no", "nobody", "nahi", "kabhi"}
NEG_AFTER = {"na", "mat", "nahi", "nahin", "not", "न", "मत", "नहीं"}


def normalise(text: str) -> str:
    """NFKC, cap length, collapse whitespace, undo simple spacing tricks like 'O T P' / 'P.I.N'."""
    text = unicodedata.normalize("NFKC", text or "")[:MAX_INPUT_CHARS]
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\bo[\s.\-]*t[\s.\-]*p\b", "otp", text, flags=_I)
    text = re.sub(r"\bp[\s.\-]+i[\s.\-]+n\b", "pin", text, flags=_I)
    return text


def _tokens(s: str):
    return [t.strip(".,!?:;()'\"।").lower() for t in s.split()]


def _negated(text: str, start: int, end: int) -> bool:
    before = _tokens(text[max(0, start - 30):start])[-4:]
    after = _tokens(text[end:end + 25])[:3]
    if any(t in NEG_BEFORE for t in before) or " ".join(before[-2:]) == "do not":
        return True
    return any(t in NEG_AFTER for t in after)


def _asks(text: str, term: str, verb: str, gap: int) -> bool:
    """verb ... term  OR  term ... verb within `gap` chars, and the verb is not negated."""
    patterns = [rf"({verb})[^.?!।]{{0,{gap}}}?{term}", rf"{term}[^.?!।]{{0,{gap}}}?({verb})"]
    for p in patterns:
        for m in re.finditer(p, text, _I):
            v = m.group(1)
            v_start = m.start(1)
            if not _negated(text, v_start, v_start + len(v)):
                return True
    return False


def money_in_amounts(text: str) -> list:
    """Amounts the message PROMISES to the user (reward/money-in context, not a fee)."""
    out = []
    for m in AMOUNT.finditer(text):
        before, after = text[max(0, m.start() - 50):m.start()], text[m.end():m.end() + 50]
        near_before, near_after = text[max(0, m.start() - 25):m.start()], text[m.end():m.end() + 25]
        money_in = REWARD.search(before + " " + after) or directional_money_in(_sentence_at(text, m.start()))
        if money_in and not FEE.search(near_before) and not FEE.search(near_after):
            out.append(float(m.group(1).replace(",", "")))
    return out


@dataclass
class RuleResult:
    flags: dict
    floor: int = 0
    reasons: list = field(default_factory=list)
    show_pin_disclaimer: bool = False
    ask_feedback: bool = False
    rule_score: float = 0.0   # used only for the "rules only" ablation


RULE_WEIGHTS = {"asks_otp": 60, "asks_pin": 70, "collect_approval": 50, "fee_to_claim": 50,
                "reward_claim": 15, "urgency": 15, "has_link": 15}


def evaluate(text: str, txn_amount: Optional[float] = None, txn_direction: str = "debit") -> RuleResult:
    t = normalise(text)
    otp_notice = bool(OTP_NOTICE.search(t))
    flags = {
        "asks_otp": _asks(t, OTP_TERM, SHARE_VERB, 40),
        "otp_notice": otp_notice,
        "asks_pin": _asks(t, PIN_TERM, PIN_VERB, 25),
        "collect_approval": bool(COLLECT.search(t)),
        "reward_claim": bool(REWARD.search(t)) or directional_money_in(t),
        "fee_to_claim": bool(FEE.search(t)) and bool(CLAIM.search(t) or REWARD.search(t)),
        "urgency": bool(URGENCY.search(t)),
        "has_link": bool(LINK.search(t)),
        "amount_mismatch": False,
    }
    if txn_amount is not None and txn_direction in ("debit", "collect"):
        flags["amount_mismatch"] = any(abs(a - txn_amount) <= max(1.0, 0.01 * txn_amount)
                                       for a in money_in_amounts(t))

    r = RuleResult(flags=flags)
    if flags["reward_claim"] and (flags["asks_pin"] or flags["collect_approval"]):
        r.floor = HARD_RULE_FLOOR
        r.reasons.append("Asks for UPI PIN to receive money" if flags["asks_pin"]
                         else "Asks you to approve a request to receive money")
    if flags["amount_mismatch"]:
        r.floor = HARD_RULE_FLOOR
        r.reasons.append("Message promises money to you, but this payment sends the same amount out")
    reason_text = {
        "asks_pin": "Asks for your UPI PIN",
        "asks_otp": "Asks you to share an OTP or code",
        "collect_approval": "Asks you to approve a collect request or scan a QR",
        "fee_to_claim": "Asks for a fee before you can claim money",
        "reward_claim": "Promises cashback, a refund, a prize or money",
        "urgency": "Pressures you to act urgently",
        "has_link": "Contains a link",
    }
    for k, msg in reason_text.items():
        if flags[k] and not (k == "asks_pin" and r.floor and flags["reward_claim"]):
            r.reasons.append(msg)
    r.show_pin_disclaimer = flags["reward_claim"]
    r.ask_feedback = flags["asks_otp"] or flags["asks_pin"]
    score = sum(w for k, w in RULE_WEIGHTS.items() if flags[k])
    r.rule_score = max(float(r.floor), min(score, 100) * (0.5 if otp_notice and not flags["asks_otp"] else 1.0))
    return r
