/**
 * server.js: Vyakhya API (Express + MongoDB)
 *
 * POST /score flow
 *   1. validate body
 *   2. redact() the text AGAIN (never trust the browser alone)
 *   3. ask the Flask scoring service (frozen risk engine) for R + tier (3 s timeout)
 *      -> on any failure: tier MEDIUM, reason SCORING_UNAVAILABLE
 *   4. tier: the engine's evaluated band (hard-rule hit -> CRITICAL). Fallback when the
 *      service sends no tier: LOW <40, MEDIUM 40-69, HIGH 70-84, CRITICAL >=85
 *   5. save event (redacted text only). MEDIUM, HIGH and CRITICAL open a case
 *      and put the payment on a soft hold for HOLD_SECONDS (env, default 60).
 *   6. append an audit record (every call, success or not)
 *
 * Hold life cycle (one case per held payment)
 *
 *              appeal + confirm         hold expires          analyst
 *   MEDIUM/HIGH  held -> released        held -> released      held -> released|blocked
 *   CRITICAL     held -> escalated       held -> escalated     held|escalated -> released|blocked
 *
 *   A CRITICAL hold is NEVER released automatically. A verified call-back or
 *   the expiry only moves it to the analyst queue (status "escalated");
 *   only an analyst release/block closes it.
 *
 *   Appeal = mock verified call-back, two steps (user role):
 *     POST /cases/:id/appeal          -> "we are calling you", returns callback_id
 *     POST /cases/:id/appeal/confirm  -> the call verified the payer
 *   In a real system the confirm would come from the bank's call system, not
 *   the payer's app; here the demo UI plays that part.
 *
 *   Every close (release/block) stores and audits seconds_held = hold -> close.
 *
 * Collections
 *   events : one per /score call. Stores REDACTED text only, never raw.
 *   cases  : one per held payment (see life cycle above).
 *   audit  : append-only log. No update/delete routes, and the model itself
 *            refuses updates and deletes (see auditSchema hooks).
 *
 * Auth: POST /login gives a signed token with role "user" or "analyst".
 *   POST /score, GET /health                        -> public, no login
 *   GET /events, /stream, /stats, /metrics           -> public (demo); no text, no payee ids
 *   GET /cases, POST /cases/:id/decision, GET /audit -> analyst only
 *   POST /cases/:id/appeal, .../appeal/confirm       -> user only
 */

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');
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

// How long a soft hold lasts before it expires (60 in the demo).
const HOLD_SECONDS = Number(process.env.HOLD_SECONDS) > 0 ? Number(process.env.HOLD_SECONDS) : 60;
// How often the expiry sweep looks for expired holds.
const EXPIRY_SWEEP_MS = 1000;

// Evaluation outputs served by GET /metrics (Panel 4). Default: <repo>/metrics.
const METRICS_DIR = process.env.METRICS_DIR || path.join(__dirname, '..', '..', 'metrics');

// Live feed for GET /stream (Panel 2). Module-level so /score can emit to it.
const bus = new EventEmitter();
bus.setMaxListeners(100);

// All "now" reads go through here, so tests can move time forward.
const clock = { now: () => new Date() };

/** Seconds between two dates, 1 decimal. */
const secondsBetween = (from, to) => Math.round((to - from) / 100) / 10;

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

const TIERS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

/**
 * Map a risk score R (0-100) to a tier. FALLBACK ONLY: the scoring service returns the tier
 * from the frozen engine's evaluated bands (hard-rule hit -> CRITICAL), and that tier wins.
 */
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
  SCAM_TEXT: 'The message reads like a known scam pattern.',
  OTP_REQUEST: 'The message asks you to share an OTP or PIN. Banks never ask for these.',
  URGENCY: 'The message pushes you to act fast, a common scam pressure tactic.',
  IMPERSONATION: 'The message claims to be from a bank, police or government office.',
  KYC_THREAT: 'The message threatens to block your account over KYC.',
  REFUND_LURE: 'The message promises a refund or prize if you pay first.',
  // codes from the frozen risk engine (ml_service/app.py)
  PIN_TO_RECEIVE: 'The message asks for your UPI PIN to receive money. You never need a PIN to receive money.',
  AMOUNT_MISMATCH: 'The message promises you money, but this payment sends the same amount out of your account.',
  COLLECT_REQUEST: 'The message asks you to approve a collect request or scan a QR code.',
  PAYEE_NO_HISTORY: 'The receiving account has never received money before.',
  PAYEE_LITTLE_HISTORY: 'The receiving account has very little payment history.',
  PAYEE_UNKNOWN: 'We have no history for the receiving account, so it is treated as new.',
  HAS_LINK: 'The message contains a link.',
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
    // Optional fields used by the frozen risk engine (see ml_service/app.py).
    if (payment.payee_prior_txns !== undefined && (!isNum(payment.payee_prior_txns) || payment.payee_prior_txns < 0)) {
      errors.push('payment.payee_prior_txns must be a number >= 0');
    }
    if (payment.hour !== undefined && !(Number.isInteger(payment.hour) && payment.hour >= 0 && payment.hour <= 23)) {
      errors.push('payment.hour must be an integer 0-23');
    }
    if (payment.direction !== undefined && !['debit', 'collect', 'credit'].includes(payment.direction)) {
      errors.push('payment.direction must be one of debit, collect, credit');
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
  const str = (v) => (typeof v === 'string' ? v : null);
  return {
    R: data.R,
    reasons,
    tier: TIERS.includes(data.tier) ? data.tier : null, // engine's evaluated band; null -> tierFor(R)
    model_version: str(data.model_version),
    rules_version: str(data.rules_version),
    disclaimer: str(data.disclaimer),
    ask_user: str(data.ask_user),
    context_flags: Array.isArray(data.context_flags) ? data.context_flags.filter((c) => typeof c === 'string') : [],
    cutoffs: isObj(data.cutoffs) && isNum(data.cutoffs.medium) && isNum(data.cutoffs.high)
      ? { medium: data.cutoffs.medium, high: data.cutoffs.high } : null,
    components: {
      text_prob: isNum(data.text_prob) ? data.text_prob : null,
      txn_prob: isNum(data.txn_prob) ? data.txn_prob : null,
      rule_prob: isNum(data.rule_prob) ? data.rule_prob : null,
      hard_rule_floor: isNum(data.hard_rule_floor) ? data.hard_rule_floor : null,
      signal_mode: str(data.signal_mode),
    },
  };
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
    model_version: String, // frozen engine version that produced R (null if scoring unavailable)
    rules_version: String,
    latency_ms: Number, // validate -> redact -> score -> tier, before storage
  },
  { timestamps: { createdAt: 'created_at', updatedAt: false }, versionKey: false }
);

// held      : payment paused, waiting for call-back, expiry or analyst
// escalated : CRITICAL only, in the analyst queue, still held
// released / blocked : closed
const CASE_STATUSES = ['held', 'escalated', 'released', 'blocked'];
const OPEN_STATUSES = ['held', 'escalated'];

const caseSchema = new mongoose.Schema(
  {
    event_id: { type: mongoose.Schema.Types.ObjectId, ref: 'Event', required: true },
    session_id: String,
    R: { type: Number, index: true },
    tier: String,
    reasons: [String],
    why: [String],
    hold: Boolean, // true until the case is released or blocked
    payment: paymentShape,
    redacted_text: String,
    status: { type: String, enum: CASE_STATUSES, default: 'held' },
    held_at: Date,
    hold_expires_at: Date,
    // Mock verified call-back. reason is REDACTED text.
    callback: { id: String, reason: String, started_at: Date, confirmed_at: Date },
    escalated_at: Date,
    escalated_via: { type: String, enum: ['callback', 'expiry'] },
    closed_at: Date,
    closed_via: { type: String, enum: ['callback', 'expiry', 'analyst'] },
    seconds_held: Number, // held_at -> closed_at
    decided_by: String, // analyst username, when an analyst closed it
    decision_note: String, // analyst's reason, REDACTED before storage
  },
  { timestamps: { createdAt: 'created_at', updatedAt: false }, versionKey: false }
);
// The expiry sweep looks up "held and past hold_expires_at".
caseSchema.index({ status: 1, hold_expires_at: 1 });

const auditSchema = new mongoose.Schema(
  {
    // score     : a /score call
    // appeal    : payer started a call-back
    // release   : hold released by call-back or expiry (MEDIUM/HIGH)
    // escalate  : CRITICAL sent to the analyst queue by call-back or expiry
    // decision  : analyst release/block
    action: { type: String, enum: ['score', 'appeal', 'release', 'escalate', 'decision'], required: true },
    via: String, // callback | expiry | analyst
    seconds_held: Number, // on every release/block
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
    note: String, // analyst decision note, redacted
    model_version: String,
    rules_version: String,
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

/** "kyc.verify@ybl" -> "ky••••@ybl". Enough for a dashboard row, not enough to pay. */
function maskVpa(vpa) {
  if (typeof vpa !== 'string' || !vpa.includes('@')) return null;
  const [local, handle] = vpa.split('@');
  return `${local.slice(0, 2)}${'•'.repeat(Math.max(2, Math.min(6, local.length - 2)))}@${handle}`;
}

/** Dashboard-safe view of an event: no text, no full payee id, no session id. */
const publicEvent = (e) => ({
  id: String(e._id), created_at: e.created_at, R: e.R, tier: e.tier,
  reasons: e.reasons, why: explain(e.reasons || []), hold: e.hold, scoring_ok: e.scoring_ok,
  amount: e.payment && e.payment.amount, payee_masked: maskVpa(e.payment && e.payment.payee_vpa),
  latency_ms: e.latency_ms ?? null, model_version: e.model_version || null,
});

// ---------------------------------------------------------------------------
// Hold handling (shared by call-back confirm and the expiry sweep)
// ---------------------------------------------------------------------------
const SYSTEM_ACTOR = { username: null, role: 'system' };

/** Append an audit record about a case. */
function auditCase(action, c, actor, extra = {}) {
  return Audit.create({
    action, actor, session_id: c.session_id, event_id: c.event_id, case_id: c._id,
    R: c.R, tier: c.tier, hold: c.hold, ...extra,
  });
}

/**
 * End the "held" stage of a case, because of a verified call-back or expiry.
 *   MEDIUM / HIGH -> released (hold off), seconds_held recorded
 *   CRITICAL      -> escalated to the analyst queue, hold stays ON
 *
 * Atomic: only succeeds if the case is still "held" (plus any extra filter),
 * so a call-back and the expiry can never both act on the same case.
 * Returns the updated case, or null if something else got there first.
 */
async function resolveHold(c, via, actor, { filter = {}, set = {} } = {}) {
  const now = clock.now();
  const where = { _id: c._id, status: 'held', ...filter };

  if (c.tier === 'CRITICAL') {
    const updated = await Case.findOneAndUpdate(
      where,
      { ...set, status: 'escalated', escalated_at: now, escalated_via: via },
      { returnDocument: 'after' }
    ).lean();
    if (updated) await auditCase('escalate', updated, actor, { via });
    return updated;
  }

  const seconds_held = secondsBetween(c.held_at, now);
  const updated = await Case.findOneAndUpdate(
    where,
    { ...set, status: 'released', hold: false, closed_at: now, closed_via: via, seconds_held },
    { returnDocument: 'after' }
  ).lean();
  if (updated) await auditCase('release', updated, actor, { via, seconds_held });
  return updated;
}

/**
 * Expiry sweep: every held case past hold_expires_at is resolved
 * (MEDIUM/HIGH released, CRITICAL escalated). Safe to run any time.
 */
async function expireHolds() {
  const due = await Case.find({ status: 'held', hold_expires_at: { $lte: clock.now() } }).lean();
  const result = { released: 0, escalated: 0 };
  for (const c of due) {
    const updated = await resolveHold(c, 'expiry', SYSTEM_ACTOR);
    if (updated) result[updated.status] += 1;
  }
  return result;
}

/**
 * Run expireHolds() every intervalMs. Deadlines live in Mongo, so a restart
 * just picks up where it left off. Returns the timer (clearInterval to stop).
 */
function startHoldExpiry(intervalMs = EXPIRY_SWEEP_MS) {
  let running = false; // skip a tick if the previous sweep is still going
  const timer = setInterval(async () => {
    if (running) return;
    running = true;
    try {
      await expireHolds();
    } catch (err) {
      console.error('[expiry] sweep failed:', err.message);
    } finally {
      running = false;
    }
  }, intervalMs);
  timer.unref(); // don't keep the process alive just for this
  return timer;
}

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
    const started = process.hrtime.bigint();
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
    let extra = { model_version: null, rules_version: null, disclaimer: null, ask_user: null, context_flags: [] };
    try {
      const scored = await callScoringService({ session_id, redacted_text: redacted, context, payment });
      R = scored.R;
      reasons = scored.reasons;
      tier = scored.tier || tierFor(R);
      extra = scored;
    } catch (err) {
      scoringOk = false;
      reasons = ['SCORING_UNAVAILABLE'];
      tier = 'MEDIUM';
      console.warn(`[score] scoring unavailable: ${err.message}`); // no request text in logs
    }

    // 4-5. Policy: everything except LOW gets a case and a soft hold.
    const hold = tier !== 'LOW';
    const why = explain(reasons);

    const versions = { model_version: extra.model_version, rules_version: extra.rules_version };
    const latency_ms = Math.round(Number(process.hrtime.bigint() - started) / 1e6);
    const event = await Event.create({
      session_id, redacted_text: redacted, redaction_counts: counts,
      context, payment, R, tier, reasons, hold, scoring_ok: scoringOk, latency_ms, ...versions,
    });
    bus.emit('event', publicEvent(event)); // live feed (Panel 2)

    let caseDoc = null;
    if (hold) {
      const heldAt = clock.now();
      caseDoc = await Case.create({
        event_id: event._id, session_id, R, tier, reasons, why, hold,
        payment, redacted_text: redacted,
        status: 'held',
        held_at: heldAt,
        hold_expires_at: new Date(heldAt.getTime() + HOLD_SECONDS * 1000),
      });
    }

    // 6. Audit every call.
    await Audit.create({
      action: 'score', actor: { username: null, role: 'public' }, session_id,
      event_id: event._id, case_id: caseDoc ? caseDoc._id : undefined,
      R, tier, hold, reasons, scoring_ok: scoringOk, redaction_counts: counts, ...versions,
    });

    res.json({
      R, tier, reasons, why, hold,
      event_id: String(event._id),
      latency_ms,
      cutoffs: extra.cutoffs || null, // engine band cutoffs used for this tier (medium/high)
      components: extra.components || null, // text_prob, txn_prob, rule_prob, hard_rule_floor, signal_mode
      case_id: caseDoc ? String(caseDoc._id) : null,
      hold_expires_at: caseDoc ? caseDoc.hold_expires_at : null, // for the UI countdown
      // From the frozen engine; absent values are null / [].
      disclaimer: extra.disclaimer, // "You never enter your UPI PIN to receive money..." on reward messages
      ask_user: extra.ask_user, // "Did someone ask you to share this?" when an OTP/PIN request fired
      context_flags: extra.context_flags, // SIMULATED signals, shown in the UI but not part of R
      ...versions,
    });
  });

  // --- cases (analyst only) ---
  app.get('/cases', requireRole('analyst'), async (req, res) => {
    const filter = {};
    if (CASE_STATUSES.includes(req.query.status)) filter.status = req.query.status;
    // callback.id is the payer's one-time call-back code: never shown to analysts.
    const cases = await Case.find(filter).select('-callback.id').sort({ R: -1, created_at: -1 }).limit(200).lean();
    res.json(cases);
  });

  app.post('/cases/:id/decision', requireRole('analyst'), async (req, res) => {
    const { decision, note = '' } = req.body || {};
    if (decision !== 'release' && decision !== 'block') {
      return res.status(400).json({ error: 'decision must be "release" or "block"' });
    }
    if (typeof note !== 'string' || note.length > 1000) {
      return res.status(400).json({ error: 'note must be a string of at most 1000 chars' });
    }
    const decision_note = redact(note).redacted; // free text: redact before storing
    if (!mongoose.isValidObjectId(req.params.id)) return res.status(400).json({ error: 'bad case id' });

    // Atomic: only a HELD or ESCALATED case can be decided, so two analysts
    // (or an analyst and the expiry sweep) can't both close it.
    const current = await Case.findById(req.params.id).lean();
    if (!current) return res.status(404).json({ error: 'case not found' });

    const now = clock.now();
    const seconds_held = secondsBetween(current.held_at, now);
    const updated = await Case.findOneAndUpdate(
      { _id: current._id, status: { $in: OPEN_STATUSES } },
      {
        status: decision === 'release' ? 'released' : 'blocked',
        hold: false,
        closed_at: now,
        closed_via: 'analyst',
        seconds_held,
        decided_by: req.user.username,
        decision_note,
      },
      { returnDocument: 'after' }
    ).select('-callback.id').lean();

    if (!updated) return res.status(409).json({ error: `case already closed (${current.status})` });

    await auditCase('decision', updated, req.user, { decision, via: 'analyst', seconds_held, note: decision_note });
    res.json(updated);
  });

  // --- appeal = mock verified call-back (user only) ---
  // Both steps need the case's session_id, so a payer can only appeal their own
  // payment. "not found" and "not your session" give the same 404 (no probing).
  const findOwnCase = async (req, res) => {
    const { session_id } = req.body || {};
    if (typeof session_id !== 'string' || !session_id) {
      res.status(400).json({ error: 'session_id is required' });
      return null;
    }
    if (!mongoose.isValidObjectId(req.params.id)) {
      res.status(400).json({ error: 'bad case id' });
      return null;
    }
    const c = await Case.findOne({ _id: req.params.id, session_id }).lean();
    if (!c) {
      res.status(404).json({ error: 'case not found' });
      return null;
    }
    if (c.status !== 'held') {
      res.status(409).json({ error: `case is not on hold (${c.status})`, status: c.status });
      return null;
    }
    return c;
  };

  // Step 1: start the call-back. body: { session_id, reason? }
  app.post('/cases/:id/appeal', requireRole('user'), async (req, res) => {
    const { reason = '' } = req.body || {};
    if (typeof reason !== 'string' || reason.length > 1000) {
      return res.status(400).json({ error: 'reason must be a string of at most 1000 chars' });
    }
    const c = await findOwnCase(req, res);
    if (!c) return;

    const callbackId = crypto.randomUUID();
    // Atomic: only one call-back per case.
    const updated = await Case.findOneAndUpdate(
      { _id: c._id, status: 'held', 'callback.id': { $exists: false } },
      // The reason is free text, so it is redacted before it is stored.
      { callback: { id: callbackId, reason: redact(reason).redacted, started_at: clock.now() } },
      { returnDocument: 'after' }
    ).lean();
    if (!updated) return res.status(409).json({ error: 'call-back already started' });

    await auditCase('appeal', updated, req.user);
    res.json({
      case_id: String(updated._id),
      status: updated.status,
      callback: 'calling', // mock: "your bank is calling you to verify"
      callback_id: callbackId, // the demo UI sends this back to confirm
      hold_expires_at: updated.hold_expires_at,
    });
  });

  // Step 2: the call verified the payer. body: { session_id, callback_id }
  //   MEDIUM/HIGH -> released, returns seconds_held
  //   CRITICAL    -> escalated to the analyst queue, still held
  app.post('/cases/:id/appeal/confirm', requireRole('user'), async (req, res) => {
    const { callback_id } = req.body || {};
    if (typeof callback_id !== 'string' || !callback_id) {
      return res.status(400).json({ error: 'callback_id is required' });
    }
    const c = await findOwnCase(req, res);
    if (!c) return;
    if (!c.callback || !c.callback.id) return res.status(409).json({ error: 'no call-back in progress, appeal first' });
    if (c.callback.id !== callback_id) return res.status(400).json({ error: 'callback_id does not match' });

    const updated = await resolveHold(c, 'callback', req.user, {
      filter: { 'callback.id': callback_id, 'callback.confirmed_at': { $exists: false } },
      set: { 'callback.confirmed_at': clock.now() },
    });
    // Lost a race with the expiry sweep or an analyst.
    if (!updated) return res.status(409).json({ error: 'case is no longer on hold' });

    res.json({
      case_id: String(updated._id),
      status: updated.status, // released | escalated
      hold: updated.hold,
      seconds_held: updated.seconds_held ?? null, // null while still held (CRITICAL)
    });
  });

  // --- audit (analyst only, read-only) ---
  app.get('/audit', requireRole('analyst'), async (req, res) => {
    const records = await Audit.find().sort({ created_at: -1 }).limit(500).lean();
    res.json(records);
  });

  // --- live feed + stats + metrics (dashboards; PUBLIC for demo speed) ---
  // They expose only scores, tiers, reason codes and amounts, never text or payee ids.
  // To restrict: wrap /events, /stats, /metrics in requireRole('analyst'). Keep /stream public:
  // the browser's EventSource cannot send an Authorization header.
  app.get('/events', async (req, res) => {
    const rows = await Event.find().sort({ created_at: -1 }).limit(100).lean();
    res.json(rows.map(publicEvent));
  });

  app.get('/stream', (req, res) => {
    res.set({ 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
    res.flushHeaders();
    const send = (ev) => res.write(`data: ${JSON.stringify(ev)}\n\n`);
    const ping = setInterval(() => res.write(': keepalive\n\n'), 15000);
    bus.on('event', send);
    req.on('close', () => { clearInterval(ping); bus.off('event', send); });
  });

  // ?range=7d|30d limits to recent events; no range = all events.
  app.get('/stats', async (req, res) => {
    const days = { '7d': 7, '30d': 30 }[req.query.range];
    const match = days ? { created_at: { $gte: new Date(clock.now().getTime() - days * 86400000) } } : {};
    const tiers = Object.fromEntries(
      (await Event.aggregate([{ $match: match }, { $group: { _id: '$tier', n: { $sum: 1 } } }])).map((d) => [d._id, d.n]));
    const total = Object.values(tiers).reduce((a, b) => a + b, 0);
    const trend = await Event.aggregate([
      { $match: match },
      { $group: { _id: { $dateToString: { format: '%Y-%m-%d %H:00', date: '$created_at' } },
                  n: { $sum: 1 }, avgR: { $avg: '$R' } } },
      { $sort: { _id: 1 } }]);
    const byDayRows = await Event.aggregate([
      { $match: match },
      { $group: { _id: { date: { $dateToString: { format: '%Y-%m-%d', date: '$created_at' } }, tier: '$tier' }, n: { $sum: 1 } } }]);
    const byDay = {};
    for (const d of byDayRows) {
      byDay[d._id.date] = byDay[d._id.date] || { date: d._id.date, LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
      byDay[d._id.date][d._id.tier] = d.n;
    }
    const reasonCounts = Object.fromEntries(
      (await Event.aggregate([{ $match: match }, { $unwind: '$reasons' }, { $group: { _id: '$reasons', n: { $sum: 1 } } },
        { $sort: { n: -1 } }])).map((d) => [d._id, d.n]));
    // Alert budget: a "user" is a session; an alert is any non-LOW decision.
    const perUser = await Event.aggregate([
      { $match: match },
      { $group: { _id: '$session_id', alerts: { $sum: { $cond: [{ $ne: ['$tier', 'LOW'] }, 1, 0] } } } }]);
    const weeks = (days || 7) / 7;
    const alerts = perUser.reduce((a, u) => a + u.alerts, 0);
    const lat = (await Event.find({ ...match, latency_ms: { $type: 'number' } }).select('latency_ms').lean())
      .map((e) => e.latency_ms).sort((a, b) => a - b);
    res.json({
      total, tiers, trend, reasons: reasonCounts,
      by_day: Object.values(byDay).sort((a, b) => a.date.localeCompare(b.date)),
      holds: await Event.countDocuments({ ...match, hold: true }),
      users: perUser.length,
      users_over_budget: perUser.filter((u) => u.alerts > weeks).length,
      alerts_per_user_week: perUser.length ? Math.round(100 * alerts / perUser.length / weeks) / 100 : 0,
      p95_latency_ms: lat.length ? lat[Math.min(lat.length - 1, Math.floor(lat.length * 0.95))] : null,
      zero_friction_pct: total ? Math.round(1000 * (tiers.LOW || 0) / total) / 10 : null,
      range: days ? req.query.range : 'all',
      data_note: 'demo traffic from the simulator (synthetic), not production',
    });
  });

  app.get('/metrics', (req, res) => {
    const out = {};
    if (fs.existsSync(METRICS_DIR)) {
      for (const f of fs.readdirSync(METRICS_DIR).filter((x) => x.endsWith('.json'))) {
        try {
          out[f.slice(0, -5)] = JSON.parse(fs.readFileSync(path.join(METRICS_DIR, f), 'utf8'));
        } catch {
          out[f.slice(0, -5)] = { error: 'unreadable metrics file' };
        }
      }
    }
    res.json(out);
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
  startHoldExpiry();
  createApp().listen(PORT, () =>
    console.log(`Vyakhya API on http://localhost:${PORT} (holds expire after ${HOLD_SECONDS}s)`)
  );
}

if (require.main === module) {
  start().catch((err) => {
    console.error('failed to start:', err.message);
    process.exit(1);
  });
}

module.exports = {
  createApp, tierFor, explain, validateScoreBody, publicEvent, bus,
  expireHolds, startHoldExpiry, clock, HOLD_SECONDS,
  Event, Case, Audit,
};
