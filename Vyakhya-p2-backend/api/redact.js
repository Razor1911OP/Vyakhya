/**
 * redact.js
 *
 * Masks personal / financial identifiers in free text before it is scored.
 * The browser already redacts, this is the server-side safety net so raw
 * PII never reaches the scoring service, logs, or MongoDB.
 *
 *   redact("OTP is 482913, call +91 98765 43210")
 *   -> { redacted: "OTP is [OTP], call [PHONE]",
 *        counts: { UPI:0, PAN:0, CARD:0, AADHAAR:0, PHONE:1, ACCT:0, OTP:1 } }
 *
 * How it works
 * ------------
 * 1. Scammers dodge filters by splitting digits: "4 5 6 7 8 9", "98.76.54.32.10".
 *    So every digit pattern allows a small separator (space, dot or dash,
 *    up to 2 chars) between any two digits.
 * 2. A "digit run" is a maximal chain of digits joined by those separators.
 *    Each numeric rule only matches a WHOLE run of the right length
 *    (START/END guards below), so a 16-digit card is never half-matched
 *    as a 10-digit phone.
 * 3. Rules run in a fixed order, most specific first. Once text is replaced
 *    by a placeholder like [CARD] it has no digits left, so later rules
 *    cannot re-match it.
 *
 *    UPI -> PAN -> CARD -> AADHAAR -> PHONE -> ACCT -> OTP
 *
 *    UPI goes first because "9876543210@ybl" contains a phone number;
 *    we want one [UPI], not "[PHONE]@ybl".
 *    PAN goes before the numeric rules because it contains 4 digits.
 *    OTP goes last: it is 4-8 digits, so it never overlaps the 9+ digit
 *    rules, and it only fires near a keyword (otp / code / pin).
 *
 * Design choice: if we are unsure, we over-redact. Two numbers that sit
 * next to each other ("call 98765 43210. 5") merge into one longer run and
 * get labelled [ACCT] instead of [PHONE]; still masked, just a coarser label.
 */

'use strict';

// Separator allowed between two digits: up to 2 of space / dot / dash.
// Covers "4 5 6", "4.5.6", "4-5-6", "4 . 5", "4  5".
const SEP = '[ .\\-]{0,2}';

// Exactly min..max digits, with optional separators between them.
function digits(min, max = min) {
  return `\\d(?:${SEP}\\d){${min - 1},${max - 1}}`;
}

// Whole-run guards: no digit just before the match, and no digit just
// after it (even across a separator). This is what makes length checks work.
const START = `(?<!\\d${SEP})`;
const END = `(?!${SEP}\\d)`;

// OTP keywords. "code" also covers "verification code", "pin" covers "UPI PIN".
const OTP_KEYWORD = '\\b(?:otp|code|pin|passcode)\\b';
// Gap between keyword and code: up to 15 chars, but never crossing a digit
// or a sentence end, so "code expired. Pay Rs 5000" leaves 5000 alone.
const OTP_GAP = '[^\\d.!?\\n]{0,15}';

// Ordered rules. Order matters, see header comment.
const RULES = [
  {
    // name@bank handle. Also swallows a trailing domain so plain emails
    // (user@example.com) are fully masked too.
    label: 'UPI',
    pattern: /\b[a-z0-9][a-z0-9._-]*@[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*/gi,
  },
  {
    // PAN: 5 letters, 4 digits, 1 letter, e.g. ABCDE1234F.
    label: 'PAN',
    pattern: /\b[a-z]{5}\d{4}[a-z]\b/gi,
  },
  {
    // Card: 16 digits (Visa / Mastercard / RuPay), any grouping.
    label: 'CARD',
    pattern: new RegExp(`${START}${digits(16)}${END}`, 'g'),
  },
  {
    // Aadhaar: 12 digits, first digit 2-9 (UIDAI never issues 0/1).
    // Skipped when preceded by "+" or when it looks like 91 + mobile
    // ("919876543210"), so the PHONE rule can label those correctly.
    label: 'AADHAAR',
    pattern: new RegExp(
      `(?<![\\d+]${SEP})(?!9${SEP}1${SEP}[6-9])[2-9](?:${SEP}\\d){11}${END}`,
      'g'
    ),
  },
  {
    // Indian mobile: 10 digits starting 6-9, optional +91 / 91 / 0 prefix.
    label: 'PHONE',
    pattern: new RegExp(
      `${START}(?:\\+?9${SEP}1${SEP}|0${SEP})?[6-9](?:${SEP}\\d){9}${END}`,
      'g'
    ),
  },
  {
    // Bank account: any remaining run of 9-18 digits.
    label: 'ACCT',
    pattern: new RegExp(`${START}${digits(9, 18)}${END}`, 'g'),
  },
  {
    // OTP after the keyword: "OTP is 482913", "PIN: 4 8 2 1".
    label: 'OTP',
    pattern: new RegExp(
      `(?<=${OTP_KEYWORD}${OTP_GAP})${START}${digits(4, 8)}${END}`,
      'gi'
    ),
  },
  {
    // OTP before the keyword: "482913 is your OTP".
    label: 'OTP',
    pattern: new RegExp(
      `${START}${digits(4, 8)}${END}(?=${OTP_GAP}${OTP_KEYWORD})`,
      'gi'
    ),
  },
];

/**
 * Redact PII from a piece of text.
 * @param {string} text raw message text
 * @returns {{redacted: string, counts: Object<string, number>}}
 *   counts has every label (0 if not found) so callers can rely on the shape.
 */
function redact(text) {
  if (typeof text !== 'string') {
    throw new TypeError('redact(text): text must be a string');
  }

  const counts = { UPI: 0, PAN: 0, CARD: 0, AADHAAR: 0, PHONE: 0, ACCT: 0, OTP: 0 };
  let redacted = text;

  for (const { label, pattern } of RULES) {
    redacted = redacted.replace(pattern, () => {
      counts[label] += 1;
      return `[${label}]`;
    });
  }

  return { redacted, counts };
}

module.exports = { redact };
