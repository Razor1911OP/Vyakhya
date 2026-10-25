"""
Text preparation shared by training and inference.

model_text(): what the TF-IDF model sees. Amounts -> <amt>, any run of 3+ digits (OTP, phone,
account, card, short codes) -> <num>. The model therefore never learns specific numbers, and
identifiers are not kept in the trained vocabulary.

text_hmac(): keyed hash for the feedback file. A plain SHA-256 of a short message can be
brute-forced (e.g. "Your OTP is 123456" has only 10^6 variants), so a secret salt is used.
Salt comes from env VYAKHYA_FEEDBACK_SALT, else a per-install random file (never committed).
"""
import hashlib
import hmac
import os
import re
import secrets

from risk.config import FEEDBACK_FILE
from risk.rules import normalise

_AMT = re.compile(r"(?:₹|\brs\.?|\binr)\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
_DIGIT_RUN = re.compile(r"\d(?:[\d\s\-]{1,}\d)?")


def _mask_digits(m: re.Match) -> str:
    digits = sum(ch.isdigit() for ch in m.group())
    return " <num> " if digits >= 3 else m.group()


def model_text(text: str) -> str:
    t = normalise(text).lower()
    t = _AMT.sub(" <amt> ", t)
    t = _DIGIT_RUN.sub(_mask_digits, t)
    return re.sub(r"\s+", " ", t).strip()


def _salt() -> bytes:
    env = os.getenv("VYAKHYA_FEEDBACK_SALT")
    if env:
        return env.encode()
    salt_file = FEEDBACK_FILE.parent / ".salt"
    if not salt_file.exists():
        salt_file.parent.mkdir(parents=True, exist_ok=True)
        salt_file.write_text(secrets.token_hex(32), encoding="utf-8")
    return salt_file.read_text(encoding="utf-8").strip().encode()


def text_hmac(text: str) -> str:
    return hmac.new(_salt(), normalise(text).encode("utf-8"), hashlib.sha256).hexdigest()
