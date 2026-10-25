// Tests for redact.js. All numbers are synthetic test values, not real PII.
const { redact } = require('./redact');

// Helper: redacted text only.
const r = (text) => redact(text).redacted;

describe('basic contract', () => {
  test('returns text unchanged and all-zero counts when nothing to mask', () => {
    const out = redact('Hello, please pay for the groceries today.');
    expect(out.redacted).toBe('Hello, please pay for the groceries today.');
    expect(out.counts).toEqual({ UPI: 0, PAN: 0, CARD: 0, AADHAAR: 0, PHONE: 0, ACCT: 0, OTP: 0 });
  });

  test('empty string is fine', () => {
    expect(redact('')).toEqual({
      redacted: '',
      counts: { UPI: 0, PAN: 0, CARD: 0, AADHAAR: 0, PHONE: 0, ACCT: 0, OTP: 0 },
    });
  });

  test('throws on non-string input', () => {
    expect(() => redact(null)).toThrow(TypeError);
    expect(() => redact(12345)).toThrow(TypeError);
  });

  test('same input gives same output on repeated calls (no regex state leaks)', () => {
    const msg = 'OTP 482913 card 4111 1111 1111 1111';
    expect(redact(msg)).toEqual(redact(msg));
  });

  test('is idempotent: redacting redacted text changes nothing', () => {
    const once = r('Call +91 98765 43210, OTP 482913, UPI rahul@okhdfc');
    const twice = redact(once);
    expect(twice.redacted).toBe(once);
    expect(Object.values(twice.counts).every((n) => n === 0)).toBe(true);
  });
});

describe('OTP', () => {
  test.each([
    ['Your OTP is 482913', 'Your OTP is [OTP]'],
    ['482913 is your OTP', '[OTP] is your OTP'],
    ['UPI PIN: 4821', 'UPI PIN: [OTP]'],
    ['verification code 48291367', 'verification code [OTP]'],
    ['otp=4829', 'otp=[OTP]'],
  ])('%s', (input, expected) => {
    expect(r(input)).toBe(expected);
  });

  test('evasion: digits split by spaces, dots, dashes', () => {
    expect(r('share the OTP 4 5 6 7 8 9 now')).toBe('share the OTP [OTP] now');
    expect(r('code: 4.5.6.7.8.9')).toBe('code: [OTP]');
    expect(r('pin 45-67')).toBe('pin [OTP]');
  });

  test('ignores numbers with no OTP keyword nearby', () => {
    expect(r('Pay Rs 5000 today')).toBe('Pay Rs 5000 today');
  });

  test('does not cross a sentence end to find a number', () => {
    expect(r('Your code expired. Pay Rs 5000 now')).toBe('Your code expired. Pay Rs 5000 now');
  });

  test('too short (3 digits) is not an OTP', () => {
    expect(r('OTP 123')).toBe('OTP 123');
  });

  test('counts', () => {
    expect(redact('OTP 482913 and pin 1234').counts.OTP).toBe(2);
  });
});

describe('CARD', () => {
  test.each([
    '4111 1111 1111 1111',
    '4111-1111-1111-1111',
    '4111111111111111',
    // evasion
    '4 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1',
    '4111.1111.1111.1111',
  ])('%s', (card) => {
    const out = redact(`card no ${card} pls`);
    expect(out.redacted).toBe('card no [CARD] pls');
    expect(out.counts.CARD).toBe(1);
    expect(out.counts.ACCT).toBe(0);
  });
});

describe('AADHAAR', () => {
  test.each([
    '2345 6789 0123',
    '234567890123',
    '2345-6789-0123',
    // evasion
    '2 3 4 5 6 7 8 9 0 1 2 3',
    '2.3.4.5.6.7.8.9.0.1.2.3',
  ])('%s', (aadhaar) => {
    const out = redact(`aadhaar ${aadhaar}`);
    expect(out.redacted).toBe('aadhaar [AADHAAR]');
    expect(out.counts.AADHAAR).toBe(1);
    expect(out.counts.ACCT).toBe(0);
  });

  test('12 digits starting with 0 or 1 is not Aadhaar (falls to ACCT)', () => {
    expect(r('a/c 012345678901')).toBe('a/c [ACCT]');
  });
});

describe('PHONE', () => {
  test.each([
    '9876543210',
    '98765 43210',
    '+91 98765 43210',
    '+91-9876543210',
    '+919876543210',
    '919876543210',
    '09876543210',
    // evasion
    '9 8 7 6 5 4 3 2 1 0',
    '98.76.54.32.10',
    '+91 9.8.7.6.5.4.3.2.1.0',
  ])('%s', (phone) => {
    const out = redact(`call me on ${phone} now`);
    expect(out.redacted).toBe('call me on [PHONE] now');
    expect(out.counts.PHONE).toBe(1);
    expect(out.counts.AADHAAR).toBe(0);
    expect(out.counts.ACCT).toBe(0);
  });

  test('10 digits starting 1-5 is not a mobile (falls to ACCT)', () => {
    expect(r('ref 1234567890')).toBe('ref [ACCT]');
  });
});

describe('ACCT', () => {
  test.each([
    '123456789', // 9 digits, minimum
    '50100123456789', // 14 digits
    '123456789012345678', // 18 digits, maximum
    // evasion
    '5 0 1 0 0 1 2 3 4 5 6 7 8 9',
    '5010.0123.4567.89',
  ])('%s', (acct) => {
    const out = redact(`account ${acct}`);
    expect(out.redacted).toBe('account [ACCT]');
    expect(out.counts.ACCT).toBe(1);
  });

  test('8 digits is too short for an account', () => {
    expect(r('ref 12345678')).toBe('ref 12345678');
  });
});

describe('PAN', () => {
  test.each(['ABCDE1234F', 'abcde1234f'])('%s', (pan) => {
    const out = redact(`PAN ${pan}.`);
    expect(out.redacted).toBe('PAN [PAN].');
    expect(out.counts.PAN).toBe(1);
  });

  test('PAN inside a longer word is not matched', () => {
    expect(r('XABCDE1234F')).toBe('XABCDE1234F');
  });
});

describe('UPI', () => {
  test.each(['rahul.sharma@okhdfc', 'test-user_1@ybl', 'shop@paytm'])('%s', (vpa) => {
    const out = redact(`send to ${vpa} now`);
    expect(out.redacted).toBe('send to [UPI] now');
    expect(out.counts.UPI).toBe(1);
  });

  test('phone-number VPA becomes one [UPI], not [PHONE]', () => {
    const out = redact('pay 9876543210@ybl');
    expect(out.redacted).toBe('pay [UPI]');
    expect(out.counts).toMatchObject({ UPI: 1, PHONE: 0 });
  });

  test('email address is fully masked', () => {
    expect(r('mail test.user@example.co.in today')).toBe('mail [UPI] today');
  });
});

describe('mixed scam message', () => {
  test('masks everything and counts each type', () => {
    const msg =
      'Sir this is SBI. Your KYC expired. Share OTP 4 8 2 9 1 3, card 4111-1111-1111-1111, ' +
      'Aadhaar 2345 6789 0123, PAN ABCDE1234F and a/c 50100123456789. ' +
      'Call +91 98765 43210 or pay refund@okaxis.';
    const out = redact(msg);

    expect(out.redacted).toBe(
      'Sir this is SBI. Your KYC expired. Share OTP [OTP], card [CARD], ' +
        'Aadhaar [AADHAAR], PAN [PAN] and a/c [ACCT]. ' +
        'Call [PHONE] or pay [UPI].'
    );
    expect(out.counts).toEqual({ UPI: 1, PAN: 1, CARD: 1, AADHAAR: 1, PHONE: 1, ACCT: 1, OTP: 1 });
    // No digit from the original identifiers survives.
    expect(out.redacted).not.toMatch(/\d/);
  });
});
