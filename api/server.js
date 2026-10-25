/**
 * server.js: Vyakhya API (Express + MongoDB)
 *
 * POST /score flow
 *   1. validate body
 *   2. redact() the text AGAIN (never trust the browser alone)
 *   3. ask the Flask scoring service for a risk score R (3 s timeout)
 *      -> on any failure: tier MEDIUM, reason SCORING_UNAVAILABLE
 *   4. tier policy: LOW <40, MEDIUM 40-69, HIGH 70-84, CRITICAL >=85
 *   5. save event (redacted text only), open a case if HIGH+, hold if CRITICAL
 *   6. append an audit record (every call, success or not)
 *
 * Collections
 *   events : one per /score call. Stores REDACTED text only, never raw.
 *   cases  : HIGH/CRITICAL events waiting for an analyst decision.
 *            Life cycle: open -> released | blocked; blocked -> appealed
 *            (user appeal) -> released | blocked (analyst re-decides).
 *   audit  : append-only log. No update/delete routes, and the model itself
 *            refuses updates and deletes (see auditSchema hooks).
 *
 * Auth: POST /login gives a signed token with role "user" or "analyst".
 *   POST /score, GET /health          -> public, no login
 *   GET /cases, POST /cases/:id/decision, GET /audit -> analyst only
 *   POST /cases/:id/appeal             -> user only (the user role's only power)
 */

'use strict';

const crypto = require('crypto');
const express = require('express');
const cors = require('cors');
const mongoose = require('mongoose');
const jwt = require('jsonwebtoken');
const { redact } = require('./redact');

// ---------------------------------------------------------------------------
// Config (all from env, with dev defaults)
// ---------------------------------------------------------------------------
const PORT = Number(process.env.PORT) || 3000;
const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27017/vyakhya';
const SCORING_URL = process.env.SCORING_URL || 'http://127.0.0.1:8000/predict';
const SCORING_TIMEOUT_MS = 3000;
const CORS_ORIGIN = process.env.CORS_ORIGIN || '*';

// Token signing secret. If not set we make a random one, so tokens simply
// stop working after a restart (fine for a demo, set JWT_SECRET for real use).
const JWT_SECRET = process.env.JWT_SECRET || crypto.randomBytes(32).toString('hex');

// Two demo accounts. Passwords come from env; the defaults are for local
// demos only and are refused in production.
if (process.env.NODE_ENV === 'production' &&
    (!process.env.JWT_SECRET || !process.env.USER_PASSWORD || !process.env.ANALYST_PASSWORD)) {
  throw new Error('Set JWT_SECRET, USER_PASSWORD and ANALYST_PASSWORD in production');
}
const USERS = {
  user: { password: process.env.USER_PASSWORD || 'user123', role: 'user' },
  analyst: { password: process.env.ANALYST_PASSWORD || 'analyst123', role: 'analyst' },
};

// ---------------------------------------------------------------------------
// Tier policy and plain-language reasons
// ---------------------------------------------------------------------------

/** Map a risk score R (0-100) to a tier. */
function tierFor(R) {
  if (R >= 85) return 'CRITICAL';
  if (R >= 70) return 'HIGH';
  if (R >= 40) return 'MEDIUM';
  return 'LOW';
}

// Reason codes -> sentences a payer (or a judge) can understand.
// Unknown codes still get a readable fallback, see explain().
const REASON_TEXT = {
  SCORING_UNAVAILABLE:
    'Our risk checker could not be reached, so this payment gets a closer look as a precaution.',
  SCREEN_SHARE: 'Your screen is being shared. Scammers use this to watch your OTP and PIN.',
  CALL_ACTIVE: 'You are on a call right now. Many scams happen while the caller guides you.',
  NEW_DEVICE: 'This payment comes from a device we have not seen before.',
  NEW_GEO: 'This payment comes from an unusual location.',
  NEW_PAYEE: 'The receiving UPI ID was created very recently.',
  AMOUNT_SPIKE: 'This amount is much higher than you usually send.',
  OTP_REQUEST: 'The message asks you to share an OTP or PIN. Banks never ask for these.',
  URGENCY: 'The message pushes you to act fast, a common scam pressure tactic.',
  IMPERSONATION: 'The message claims to be from a bank, police or government office.',
  KYC_THREAT: 'The message threatens to block your account over KYC.',
  REFUND_LURE: 'The message promises a refund or prize if you pay first.',
};

/** Turn reason codes into plain-language sentences. */
function explain(reasons) {
  return reasons.map((code) => {
    if (REASON_TEXT[code]) return REASON_TEXT[code];
    // Fallback: "SOME_NEW_CODE" -> "Risk signal: some new code."
    return `Risk signal: ${String(code).replace(/_/g, ' ').toLowerCase()}.`;
  });
}

// ---------------------------------------------------------------------------
// Request validation for POST /score
// ---------------------------------------------------------------------------
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

/** Returns a list of error messages; empty list means the body is valid. */
function validateScoreBody(body) {
  const errors = [];
  if (!isObj(body)) return ['body must be a JSON object'];

  const { session_id, redacted_text, context, payment } = body;

  if (typeof session_id !== 'string' || session_id.length < 1 || session_id.length > 128) {
    errors.push('session_id must be a string of 1-128 chars');
  }
  if (typeof redacted_text !== 'string' || redacted_text.length > 5000) {
    errors.push('redacted_text must be a string of at most 5000 chars');
  }

  if (!isObj(context)) {
    errors.push('context must be an object');
  } else {
    for (const key of ['new_device', 'new_geo', 'screen_share', 'call_active']) {
      if (typeof context[key] !== 'boolean') errors.push(`context.${key} must be a boolean`);
    }
  }

  if (!isObj(payment)) {
    errors.push('payment must be an object');
  } else {
    if (typeof payment.payee_vpa !== 'string' || !/^[\w.-]{2,256}@[a-z][a-z0-9]{1,63}$/i.test(payment.payee_vpa)) {
      errors.push('payment.payee_vpa must look like name@bank');
    }
    if (!isNum(payment.amount) || payment.amount <= 0) {
      errors.push('payment.amount must be a positive number');
    }
    if (!isNum(payment.payee_age_days) || payment.payee_age_days < 0) {
      errors.push('payment.payee_age_days must be a number >= 0');
    }
    if (!isNum(payment.user_avg_amount) || payment.user_avg_amount < 0) {
      errors.push('payment.user_avg_amount must be a number >= 0');
    }
  }
  return errors;
}

// ---------------------------------------------------------------------------
// Flask scoring client
// ---------------------------------------------------------------------------

/**
 * Ask the Flask service for a score.
 * Expects back { R: number 0-100, reasons: [string] }.
 * Throws on timeout, network error, non-2xx, or a malformed reply.
 */
async function callScoringService(payload) {
  const res = await fetch(SCORING_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(SCORING_TIMEOUT_MS), // covers connect + body read
  });
  if (!res.ok) throw new Error(`scoring service returned HTTP ${res.status}`);

  const data = await res.json();
  if (!isNum(data.R) || data.R < 0 || data.R > 100) throw new Error('scoring service sent a bad R');
  const reasons = Array.isArray(data.reasons) ? data.reasons.filter((r) => typeof r === 'string') : [];
  return { R: data.R, reasons };
}

// ---------------------------------------------------------------------------
// Mongo models
// ---------------------------------------------------------------------------
const contextShape = { new_device: Boolean, new_geo: Boolean, screen_share: Boolean, call_active: Boolean };
const paymentShape = { payee_vpa: String, amount: Number, payee_age_days: Number, user_avg_amount: Number };
const countsShape = { UPI: Number, PAN: Number, CARD: Number, AADHAAR: Number, PHONE: Number, ACCT: Number, OTP: Number };

const eventSchema = new mongoose.Schema(
  {
    session_id: { type: String, required: true, index: true },
    redacted_text: String, // server-side redacted. Raw text is NEVER stored.
    redaction_counts: countsShape,
    context: contextShape,
    payment: paymentShape,
    R: Number, // null when scoring was unavailable
    tier: String,
    reasons: [String],
    hold: Boolean,
    scoring_ok: Boolean,
  },
  { timestamps: { createdAt: 'created_at', updatedAt: false }, versionKey: false }
);

const CASE_STATUSES = ['open', 'released', 'blocked', 'appealed'];

const caseSchema = new mongoose.Schema(
  {
    event_id: { type: mongoose.Schema.Types.ObjectId, ref: 'Event', required: true },
    session_id: String,
    R: { type: Number, index: true },
    tier: String,
    reasons: [String],
    why: [String],
    hold: Boolean,
    payment: paymentShape,
    redacted_text: String,
    status: { type: String, enum: CASE_STATUSES, default: 'open' },
    decided_by: String,
    decided_at: Date,
    // Filled when the payer appeals a block. reason is REDACTED text.
    appeal: { reason: String, by: String, at: Date },
  },
  { timestamps: { createdAt: 'created_at', updatedAt: false }, versionKey: false }
);

const auditSchema = new mongoose.Schema(
  {
    action: { type: String, enum: ['score', 'decision', 'appeal'], required: true },
    actor: { username: String, role: String },
    session_id: String,
    event_id: mongoose.Schema.Types.ObjectId,
    case_id: mongoose.Schema.Types.ObjectId,
    R: Number,
    tier: String,
    hold: Boolean,
    reasons: [String],
    scoring_ok: Boolean,
    redaction_counts: countsShape,
    decision: String,
  },
  { timestamps: { createdAt: 'created_at', updatedAt: false }, versionKey: false }
);

// Append-only: the audit model refuses every update / delete, even from code.
function refuseChange() {
  throw new Error('audit log is append-only');
}
auditSchema.pre(
  ['updateOne', 'updateMany', 'findOneAndUpdate', 'replaceOne', 'findOneAndReplace',
    'deleteOne', 'deleteMany', 'findOneAndDelete'],
  { document: true, query: true },
  refuseChange
);
auditSchema.pre('save', function () {
  if (!this.isNew) refuseChange(); // re-saving an existing record = an update
});

const Event = mongoose.models.Event || mongoose.model('Event', eventSchema, 'events');
const Case = mongoose.models.Case || mongoose.model('Case', caseSchema, 'cases');
const Audit = mongoose.models.Audit || mongoose.model('Audit', auditSchema, 'audit');

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/** Constant-time string compare, so timing does not leak the password. */
function safeEqual(a, b) {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
}

/** Middleware: require a valid token whose role is in `roles`. */
function requireRole(...roles) {
  return (req, res, next) => {
    const [scheme, token] = (req.get('authorization') || '').split(' ');
    if (scheme !== 'Bearer' || !token) return res.status(401).json({ error: 'login required' });

    let claims;
    try {
      claims = jwt.verify(token, JWT_SECRET, { algorithms: ['HS256'] });
    } catch {
      return res.status(401).json({ error: 'invalid or expired token' });
    }
    if (!roles.includes(claims.role)) return res.status(403).json({ error: 'forbidden for this role' });

    req.user = { username: claims.sub, role: claims.role };
    next();
  };
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
function createApp() {
  const app = express();
  app.use(cors({ origin: CORS_ORIGIN }));
  app.use(express.json({ limit: '32kb' }));

  // --- health (public) ---
  app.get('/health', (req, res) => {
    res.json({ ok: true, db: mongoose.connection.readyState === 1 ? 'up' : 'down' });
  });

  // --- login ---
  app.post('/login', (req, res) => {
    const { username, password } = req.body || {};
    const account = typeof username === 'string' ? USERS[username] : undefined;
    // Always run the compare, even for unknown users, so timing is uniform.
    const ok = safeEqual(password ?? '', account ? account.password : 'x') && Boolean(account);
    if (!ok) return res.status(401).json({ error: 'wrong username or password' });

    const token = jwt.sign({ sub: username, role: account.role }, JWT_SECRET, {
      algorithm: 'HS256',
      expiresIn: '8h',
    });
    res.json({ token, role: account.role });
  });

  // --- score (public: the payment app calls this before every debit) ---
  app.post('/score', async (req, res) => {
    const errors = validateScoreBody(req.body);
    if (errors.length) return res.status(400).json({ error: 'invalid body', details: errors });

    const { session_id, context, payment } = req.body;

    // 2. Redact again on the server. From here on only `redacted` is used.
    const { redacted, counts } = redact(req.body.redacted_text);

    // 3. Score. Any failure -> MEDIUM with SCORING_UNAVAILABLE.
    let R = null;
    let reasons;
    let tier;
    let scoringOk = true;
    try {
      const scored = await callScoringService({ session_id, redacted_text: redacted, context, payment });
      R = scored.R;
      reasons = scored.reasons;
      tier = tierFor(R);
    } catch (err) {
      scoringOk = false;
      reasons = ['SCORING_UNAVAILABLE'];
      tier = 'MEDIUM';
      console.warn(`[score] scoring unavailable: ${err.message}`); // no request text in logs
    }

    // 4-5. Policy: hold only on CRITICAL, case on HIGH or CRITICAL.
    const hold = tier === 'CRITICAL';
    const why = explain(reasons);

    const event = await Event.create({
      session_id, redacted_text: redacted, redaction_counts: counts,
      context, payment, R, tier, reasons, hold, scoring_ok: scoringOk,
    });

    let caseDoc = null;
    if (tier === 'HIGH' || tier === 'CRITICAL') {
      caseDoc = await Case.create({
        event_id: event._id, session_id, R, tier, reasons, why, hold,
        payment, redacted_text: redacted,
      });
    }

    // 6. Audit every call.
    await Audit.create({
      action: 'score', actor: { username: null, role: 'public' }, session_id,
      event_id: event._id, case_id: caseDoc ? caseDoc._id : undefined,
      R, tier, hold, reasons, scoring_ok: scoringOk, redaction_counts: counts,
    });

    res.json({ R, tier, reasons, why, hold, case_id: caseDoc ? String(caseDoc._id) : null });
  });

  // --- cases (analyst only) ---
  app.get('/cases', requireRole('analyst'), async (req, res) => {
    const filter = {};
    if (CASE_STATUSES.includes(req.query.status)) filter.status = req.query.status;
    const cases = await Case.find(filter).sort({ R: -1, created_at: -1 }).limit(200).lean();
    res.json(cases);
  });

  app.post('/cases/:id/decision', requireRole('analyst'), async (req, res) => {
    const { decision } = req.body || {};
    if (decision !== 'release' && decision !== 'block') {
      return res.status(400).json({ error: 'decision must be "release" or "block"' });
    }
    if (!mongoose.isValidObjectId(req.params.id)) return res.status(400).json({ error: 'bad case id' });

    // Atomic: only an OPEN or APPEALED case can be decided, so two analysts
    // can't both decide it.
    const updated = await Case.findOneAndUpdate(
      { _id: req.params.id, status: { $in: ['open', 'appealed'] } },
      {
        status: decision === 'release' ? 'released' : 'blocked',
        decided_by: req.user.username,
        decided_at: new Date(),
      },
      { returnDocument: 'after' }
    ).lean();

    if (!updated) {
      const exists = await Case.exists({ _id: req.params.id });
      return exists
        ? res.status(409).json({ error: 'case already decided' })
        : res.status(404).json({ error: 'case not found' });
    }

    await Audit.create({
      action: 'decision', actor: req.user, session_id: updated.session_id,
      event_id: updated.event_id, case_id: updated._id,
      R: updated.R, tier: updated.tier, hold: updated.hold, decision,
    });

    res.json(updated);
  });

  // --- appeal (user only) ---
  // The payer asks for a blocked payment to be reviewed again.
  // body: { session_id, reason? }. session_id must match the case, so a user
  // can only appeal a case from their own payment session.
  app.post('/cases/:id/appeal', requireRole('user'), async (req, res) => {
    const { session_id, reason = '' } = req.body || {};
    if (typeof session_id !== 'string' || !session_id) {
      return res.status(400).json({ error: 'session_id is required' });
    }
    if (typeof reason !== 'string' || reason.length > 1000) {
      return res.status(400).json({ error: 'reason must be a string of at most 1000 chars' });
    }
    if (!mongoose.isValidObjectId(req.params.id)) return res.status(400).json({ error: 'bad case id' });

    // The reason is free text, so redact it before it is stored.
    const { redacted } = redact(reason);

    // Atomic: only a BLOCKED case of this session can be appealed, and only once
    // (appealed -> re-decided cases can't be appealed a second time).
    const updated = await Case.findOneAndUpdate(
      { _id: req.params.id, session_id, status: 'blocked', appeal: { $exists: false } },
      {
        status: 'appealed',
        appeal: { reason: redacted, by: req.user.username, at: new Date() },
      },
      { returnDocument: 'after' }
    ).lean();

    if (!updated) {
      // Same 404 for "no such case" and "not your session", so ids can't be probed.
      const c = await Case.findOne({ _id: req.params.id, session_id }).lean();
      if (!c) return res.status(404).json({ error: 'case not found' });
      return res.status(409).json({ error: c.appeal ? 'case already appealed' : 'only blocked cases can be appealed' });
    }

    await Audit.create({
      action: 'appeal', actor: req.user, session_id: updated.session_id,
      event_id: updated.event_id, case_id: updated._id,
      R: updated.R, tier: updated.tier, hold: updated.hold,
    });

    res.json(updated);
  });

  // --- audit (analyst only, read-only) ---
  app.get('/audit', requireRole('analyst'), async (req, res) => {
    const records = await Audit.find().sort({ created_at: -1 }).limit(500).lean();
    res.json(records);
  });

  // --- errors ---
  app.use((err, req, res, next) => {
    if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'invalid JSON' });
    if (err.type === 'entity.too.large') return res.status(413).json({ error: 'body too large' });
    console.error('[api] unhandled error:', err.message);
    res.status(500).json({ error: 'internal error' });
  });

  return app;
}

// ---------------------------------------------------------------------------
// Start (only when run directly: `node server.js`, not when required by tests)
// ---------------------------------------------------------------------------
async function start() {
  await mongoose.connect(MONGO_URL);
  createApp().listen(PORT, () => console.log(`Vyakhya API on http://localhost:${PORT}`));
}

if (require.main === module) {
  start().catch((err) => {
    console.error('failed to start:', err.message);
    process.exit(1);
  });
}

module.exports = { createApp, tierFor, explain, validateScoreBody, Event, Case, Audit };
