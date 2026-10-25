"""
Vyakhya Validation & Redaction Engine
Defence-in-depth: server-side validation and redaction
NEVER allows raw OTP/account/card/phone to pass through
"""
import re
import hashlib
from typing import Tuple, Optional
from backend.app.schemas import RedactedText
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


# Redaction patterns (India-specific).
# ORDER MATTERS: specific/long patterns run before the generic 4-6 digit OTP rule,
# otherwise amounts, cards and phones get chopped up and mislabelled as OTPs.
PATTERNS = {
    # Amounts are not PII, but normalising them keeps exact values out of the text model
    # (amount magnitude is a transaction-model feature, not a text feature).
    'amount': re.compile(r'(?:₹|\bRs\.?|\bINR)\s?\d+(?:,\d+)*(?:\.\d+)?', re.IGNORECASE),
    'card': re.compile(r'\b(?:\d{4}[\s-]?){3}\d{4}\b'),  # 16-digit cards, optional separators
    'phone': re.compile(r'(?:\+91[\s-]?)?\b[6-9]\d{9}\b'),  # Indian mobiles, optional +91
    'account': re.compile(r'\b\d{9,18}\b'),  # Bank account numbers
    'ifsc': re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b'),  # IFSC codes
    'vpa': re.compile(r'\b[\w.\-]+@[a-zA-Z]+\b'),  # UPI VPAs
    'otp': re.compile(r'\b\d{4,6}\b'),  # 4-6 digit OTPs (last: most generic)
}


def redact_text(text: Optional[str], preserve_length: bool = False) -> Tuple[str, int]:
    """
    Redact sensitive patterns from text
    
    Args:
        text: Input text (may be None)
        preserve_length: If True, replace with X's; if False, use [REDACTED]
    
    Returns:
        (redacted_text, redaction_count)
    """
    if not text:
        return "", 0
    
    redacted = text
    total_redactions = 0
    
    for pattern_name, pattern in PATTERNS.items():
        # subn replaces each match in place (str.replace could hit a different occurrence)
        if preserve_length:
            redacted, n = pattern.subn(lambda m: 'X' * len(m.group()), redacted)
        else:
            redacted, n = pattern.subn(f"[{pattern_name.upper()}]", redacted)
        total_redactions += n
    
    if total_redactions > 0:
        logger.info(f"Redacted {total_redactions} sensitive patterns", extra={
            'redaction_count': total_redactions,
            'original_length': len(text),
            'redacted_length': len(redacted)
        })
    
    return redacted, total_redactions


def hash_text(text: str) -> str:
    """Generate SHA256 hash for deduplication (not reversible)"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def detect_language(text: str) -> str:
    """
    Simple language detection (English / Hindi / Hinglish)
    Production would use langdetect or fasttext
    """
    # Count Devanagari characters
    devanagari_count = sum(1 for char in text if '\u0900' <= char <= '\u097F')
    latin_count = sum(1 for char in text if char.isalpha() and char.isascii())
    
    total_alpha = devanagari_count + latin_count
    if total_alpha == 0:
        return "unknown"
    
    devanagari_ratio = devanagari_count / total_alpha
    
    if devanagari_ratio > 0.7:
        return "hi"  # Hindi
    elif devanagari_ratio > 0.2:
        return "hi-en"  # Hinglish (mixed)
    else:
        return "en"  # English


PREVIEW_MAX_CHARS = 100


def validate_and_redact(message_text: Optional[str]) -> Tuple[Optional[RedactedText], str]:
    """
    Validate input and produce redacted representation
    
    Args:
        message_text: Raw message text (may be None)
    
    Returns:
        (RedactedText or None, full_redacted_text)
        RedactedText is safe to persist (hash + short preview).
        full_redacted_text is for in-memory model scoring only; never persist it.
    """
    if not message_text:
        return None, ""
    
    # Length validation
    if len(message_text) > 1000:
        logger.warning("Message text exceeds 1000 chars, truncating")
        message_text = message_text[:1000]
    
    # Redact sensitive patterns
    redacted, redaction_count = redact_text(message_text, preserve_length=False)
    
    # Create preview that never exceeds PREVIEW_MAX_CHARS (ellipsis included)
    if len(redacted) > PREVIEW_MAX_CHARS:
        preview = redacted[:PREVIEW_MAX_CHARS - 3] + "..."
    else:
        preview = redacted
    
    # Detect language
    language = detect_language(message_text)
    
    # Hash original (for deduplication only, never for reconstruction)
    text_hash = hash_text(message_text)
    
    redacted_meta = RedactedText(
        text_hash=text_hash,
        redacted_preview=preview,
        redaction_count=redaction_count,
        language=language
    )
    return redacted_meta, redacted


def extract_features_from_text(redacted_text: str) -> dict:
    """
    Extract statistical features from redacted text (safe for ML)
    Never includes raw tokens
    """
    features = {
        'length': len(redacted_text),
        'word_count': len(redacted_text.split()),
        'digit_ratio': sum(c.isdigit() for c in redacted_text) / max(len(redacted_text), 1),
        'upper_ratio': sum(c.isupper() for c in redacted_text) / max(len(redacted_text), 1),
        'has_url': 1 if ('http' in redacted_text.lower() or 'www.' in redacted_text.lower()) else 0,
        'redaction_count': redacted_text.count('['),
        'urgency_keywords': sum(
            keyword in redacted_text.lower() 
            for keyword in ['urgent', 'immediately', 'expire', 'suspend', 'verify', 'confirm', 'now', 'today']
        ),
    }
    return features
