// Tests for server.js. Flask is mocked by stubbing global fetch; MongoDB runs
// in memory (mongodb-memory-server), so no local services are needed.
// Time is faked through server.clock, so hold expiry is tested without waiting.
// All payloads are synthetic.
const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');
const {
  createApp, tierFor, expireHolds, startHoldExpiry, clock, HOLD_SECONDS, Event, Case, Audit,
} = require('./server');

let mongo;
let app;
let userToken;
let analystToken;
let fetchMock;

// Fake clock: starts at T0 in every test; advance(s) moves it forward.
const T0 = new Date('2026-10-24T10:00:00.000Z').getTime();
let nowMs;
const advance = (seconds) => { nowMs += seconds * 1000; };

// A fake fetch Response.
const flaskReply = (data, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });

// A valid /score body; override fields per test.
const body = (overrides = {}) => ({
  session_id: 'sess-1',
  redacted_text: 'Sir I am from bank, share OTP [OTP] quickly',
  context: { new_device: false, new_geo: false, screen_share: false, call_active: false },
  payment: { payee_vpa: 'demo.payee@okaxis', amount: 2500, payee_age_days: 3, user_avg_amount: 800 },
  ...overrides,
});

// /score is public: no Authorization header.
const score = (b) => request(app).post('/score').send(b);

const login = async (username, password) =>
  (await request(app).post('/login').send({ username, password })).body.token;

const asAnalyst = (req) => req.set('Authorization', `Bearer ${analystToken}`);
const asUser = (req) => req.set('Authorization', `Bearer ${userToken}`);

const decide = (id, decision) => asAnalyst(request(app).post(`/cases/${id}/decision`)).send({ decision });
const appeal = (id, b = { session_id: 'sess-1' }) => asUser(request(app).post(`/cases/${id}/appeal`)).send(b);
const confirm = (id, b) => asUser(request(app).post(`/cases/${id}/appeal/confirm`)).send(b);

/** Score a payment that Flask rates R; returns the /score response body. */
async function scored(R) {
  fetchMock.mockResolvedValueOnce(flaskReply({ R, reasons: ['OTP_REQUEST'] }));
  return (await score(body())).body;
}

/** Audit actions for a case, oldest first. */
const auditTrail = async (caseId) =>
  (await Audit.find({ case_id: caseId }).sort({ _id: 1 }).lean()).map((a) => a.action);

beforeAll(async () => {
  mongo = await MongoMemoryServer.create();
  await mongoose.connect(mongo.getUri());
  app = createApp();
  userToken = await login('user', 'user123');
  analystToken = await login('analyst', 'analyst123');
});

afterAll(async () => {
  await mongoose.disconnect();
  await mongo.stop();
});

beforeEach(async () => {
  fetchMock = jest.spyOn(global, 'fetch');
  nowMs = T0;
  jest.spyOn(clock, 'now').mockImplementation(() => new Date(nowMs));
  await Event.deleteMany({});
  await Case.deleteMany({});
  // The Audit model refuses deletes by design, so clear it via the raw driver.
  await Audit.collection.deleteMany({});
});

afterEach(() => jest.restoreAllMocks());

describe('tier policy', () => {
  test.each([
    [0, 'LOW'], [39, 'LOW'], [39.9, 'LOW'],
    [40, 'MEDIUM'], [69, 'MEDIUM'],
    [70, 'HIGH'], [84, 'HIGH'],
    [85, 'CRITICAL'], [100, 'CRITICAL'],
  ])('R=%p -> %s', (R, tier) => expect(tierFor(R)).toBe(tier));

  test('demo hold length defaults to 60 s', () => expect(HOLD_SECONDS).toBe(60));
});

describe('POST /score: public access and validation', () => {
  test('works without a token; audit actor is "public"', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 10, reasons: [] }));
    const res = await request(app).post('/score').send(body());
    expect(res.status).toBe(200);
    const audit = await Audit.findOne().lean();
    expect(audit.actor).toEqual({ username: null, role: 'public' });
  });

  test('an Authorization header is ignored, even a garbage one', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 10, reasons: [] }));
    const res = await request(app).post('/score').set('Authorization', 'Bearer not.a.token').send(body());
    expect(res.status).toBe(200);
  });

  test.each([
    ['missing session_id', { session_id: undefined }],
    ['text not a string', { redacted_text: 42 }],
    ['context flag not boolean', { context: { new_device: 'yes', new_geo: false, screen_share: false, call_active: false } }],
    ['negative amount', { payment: { payee_vpa: 'a.b@ybl', amount: -5, payee_age_days: 1, user_avg_amount: 1 } }],
    ['bad vpa', { payment: { payee_vpa: 'not-a-vpa', amount: 5, payee_age_days: 1, user_avg_amount: 1 } }],
    ['missing payment', { payment: undefined }],
  ])('400 when %s', async (_name, overrides) => {
    const res = await score(body(overrides));
    expect(res.status).toBe(400);
    expect(res.body.details.length).toBeGreaterThan(0);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(await Audit.countDocuments()).toBe(0);
  });

  test('400 on malformed JSON', async () => {
    const res = await request(app).post('/score').set('Content-Type', 'application/json').send('{not json');
    expect(res.status).toBe(400);
  });
});

describe('POST /score: tiers, cases, hold', () => {
  test('LOW: no case, no hold, audit written', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 20, reasons: [] }));
    const res = await score(body());

    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({
      R: 20, tier: 'LOW', hold: false, case_id: null, hold_expires_at: null, reasons: [], why: [],
    });
    expect(await Case.countDocuments()).toBe(0);
    expect(await Event.countDocuments()).toBe(1);
    const audit = await Audit.findOne().lean();
    expect(audit).toMatchObject({ action: 'score', tier: 'LOW', R: 20, scoring_ok: true });
  });

  test.each([
    [40, 'MEDIUM'], [69, 'MEDIUM'], [70, 'HIGH'], [84, 'HIGH'], [85, 'CRITICAL'], [99, 'CRITICAL'],
  ])('R=%p (%s): case opened and held for HOLD_SECONDS', async (R, tier) => {
    const res = await scored(R);

    expect(res).toMatchObject({ tier, hold: true });
    expect(res.case_id).toEqual(expect.any(String));
    expect(res.hold_expires_at).toBe(new Date(T0 + 60_000).toISOString());

    const c = await Case.findById(res.case_id).lean();
    expect(c).toMatchObject({ status: 'held', tier, R, hold: true });
    expect(c.held_at.getTime()).toBe(T0);

    const audit = await Audit.findOne().lean();
    expect(audit).toMatchObject({ action: 'score', hold: true });
    expect(String(audit.case_id)).toBe(res.case_id);
  });

  test('why: plain-language sentence per reason, with fallback for unknown codes', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 90, reasons: ['SCREEN_SHARE', 'WEIRD_NEW_SIGNAL'] }));
    const res = await score(body());

    expect(res.body.why).toHaveLength(2);
    expect(res.body.why[0]).toMatch(/screen is being shared/i);
    expect(res.body.why[1]).toBe('Risk signal: weird new signal.');
  });
});

describe('POST /score: scoring service failures -> MEDIUM / SCORING_UNAVAILABLE', () => {
  const timeoutError = Object.assign(new Error('The operation was aborted due to timeout'), { name: 'TimeoutError' });

  test.each([
    ['network error', () => fetchMock.mockRejectedValue(new TypeError('fetch failed'))],
    ['timeout', () => fetchMock.mockRejectedValue(timeoutError)],
    ['HTTP 500', () => fetchMock.mockResolvedValue(flaskReply({ error: 'boom' }, 500))],
    ['R out of range', () => fetchMock.mockResolvedValue(flaskReply({ R: 150, reasons: [] }))],
    ['R missing', () => fetchMock.mockResolvedValue(flaskReply({ reasons: ['X'] }))],
    ['non-JSON reply', () => fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => { throw new SyntaxError('bad'); } })],
  ])('%s', async (_name, arrange) => {
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    arrange();
    const res = await score(body());

    expect(res.status).toBe(200);
    // MEDIUM -> held like any MEDIUM, so it expires on its own after 60 s.
    expect(res.body).toMatchObject({ R: null, tier: 'MEDIUM', reasons: ['SCORING_UNAVAILABLE'], hold: true });
    expect(res.body.why[0]).toMatch(/could not be reached/);
    expect(await Case.countDocuments({ status: 'held', tier: 'MEDIUM' })).toBe(1);
    const audit = await Audit.findOne().lean();
    expect(audit).toMatchObject({ action: 'score', tier: 'MEDIUM', scoring_ok: false });
  });

  test('calls Flask /predict with a timeout signal', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 10, reasons: [] }));
    await score(body());

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('http://127.0.0.1:8000/predict');
    expect(options.method).toBe('POST');
    expect(options.signal).toBeInstanceOf(AbortSignal);
  });
});

describe('POST /score: raw text never stored or forwarded', () => {
  test('server re-redacts text the browser missed', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 88, reasons: ['OTP_REQUEST'] }));
    const leaky = 'OTP is 4 8 2 9 1 3, call +91 98765 43210, pay to scam.x@ybl';
    const res = await score(body({ redacted_text: leaky }));
    expect(res.status).toBe(200);

    const expected = 'OTP is [OTP], call [PHONE], pay to [UPI]';

    // Sent to Flask: redacted only.
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent.redacted_text).toBe(expected);

    // Stored: redacted only, in events and cases. Nothing in Mongo has the raw text.
    const event = await Event.findOne().lean();
    expect(event.redacted_text).toBe(expected);
    expect(event.redaction_counts).toMatchObject({ OTP: 1, PHONE: 1, UPI: 1 });
    const c = await Case.findOne().lean();
    expect(c.redacted_text).toBe(expected);

    const everything = JSON.stringify([
      await Event.find().lean(), await Case.find().lean(), await Audit.find().lean(),
    ]);
    expect(everything).not.toContain('98765');
    expect(everything).not.toContain('4 8 2 9');
    expect(everything).not.toContain('scam.x@ybl');
  });
});

describe('appeal: mock verified call-back (two steps)', () => {
  test.each(['MEDIUM', 'HIGH'])('%s: appeal -> confirm releases the hold and returns seconds_held', async (tier) => {
    const { case_id } = await scored(tier === 'MEDIUM' ? 55 : 75);

    advance(4);
    const started = await appeal(case_id, { session_id: 'sess-1', reason: 'It is my sister, 9876543210' });
    expect(started.status).toBe(200);
    expect(started.body).toMatchObject({ case_id, status: 'held', callback: 'calling' });
    expect(started.body.callback_id).toEqual(expect.any(String));

    advance(8.3);
    const done = await confirm(case_id, { session_id: 'sess-1', callback_id: started.body.callback_id });
    expect(done.status).toBe(200);
    expect(done.body).toEqual({ case_id, status: 'released', hold: false, seconds_held: 12.3 });

    const c = await Case.findById(case_id).lean();
    expect(c).toMatchObject({ status: 'released', hold: false, closed_via: 'callback', seconds_held: 12.3 });
    expect(c.callback.confirmed_at.getTime()).toBe(T0 + 12_300);
    expect(c.callback.reason).toBe('It is my sister, [PHONE]'); // redacted before storing

    const release = await Audit.findOne({ action: 'release' }).lean();
    expect(release).toMatchObject({ via: 'callback', seconds_held: 12.3, hold: false, actor: { username: 'user', role: 'user' } });
    expect(await auditTrail(case_id)).toEqual(['score', 'appeal', 'release']);
  });

  test('CRITICAL: confirm does NOT release; it escalates to the analyst queue', async () => {
    const { case_id } = await scored(92);
    const { callback_id } = (await appeal(case_id)).body;

    advance(10);
    const done = await confirm(case_id, { session_id: 'sess-1', callback_id });
    expect(done.status).toBe(200);
    expect(done.body).toEqual({ case_id, status: 'escalated', hold: true, seconds_held: null });

    const c = await Case.findById(case_id).lean();
    expect(c).toMatchObject({ status: 'escalated', hold: true, escalated_via: 'callback' });
    expect(c.closed_at).toBeUndefined();
    expect(await Audit.findOne({ action: 'escalate' }).lean()).toMatchObject({ via: 'callback', hold: true });

    // Shows in the analyst queue.
    const queue = await asAnalyst(request(app).get('/cases?status=escalated'));
    expect(queue.body.map((x) => x._id)).toEqual([case_id]);

    // Expiry no longer touches it; only the analyst can close it.
    advance(120);
    expect(await expireHolds()).toEqual({ released: 0, escalated: 0 });
    expect((await Case.findById(case_id).lean()).hold).toBe(true);

    const closed = await decide(case_id, 'release');
    expect(closed.status).toBe(200);
    expect(closed.body).toMatchObject({ status: 'released', hold: false, closed_via: 'analyst', seconds_held: 130 });
    expect(await auditTrail(case_id)).toEqual(['score', 'appeal', 'escalate', 'decision']);
  });

  test('confirm needs an appeal first, and the right callback_id', async () => {
    const { case_id } = await scored(60);
    const noAppeal = await confirm(case_id, { session_id: 'sess-1', callback_id: 'x' });
    expect(noAppeal.status).toBe(409);
    expect(noAppeal.body.error).toMatch(/appeal first/);

    await appeal(case_id);
    const wrong = await confirm(case_id, { session_id: 'sess-1', callback_id: 'not-the-id' });
    expect(wrong.status).toBe(400);
    expect((await Case.findById(case_id).lean()).status).toBe('held');
  });

  test('one call-back per case; confirm only once', async () => {
    const { case_id } = await scored(60);
    const { callback_id } = (await appeal(case_id)).body;
    const again = await appeal(case_id);
    expect(again.status).toBe(409);
    expect(again.body.error).toMatch(/already started/);

    expect((await confirm(case_id, { session_id: 'sess-1', callback_id })).status).toBe(200);
    const twice = await confirm(case_id, { session_id: 'sess-1', callback_id });
    expect(twice.status).toBe(409);
    expect(twice.body.status).toBe('released');
    expect(await Audit.countDocuments({ action: 'release' })).toBe(1);
  });

  test('wrong session_id looks like "not found" on both steps', async () => {
    const { case_id } = await scored(60);
    expect((await appeal(case_id, { session_id: 'someone-else' })).status).toBe(404);
    const { callback_id } = (await appeal(case_id)).body;
    expect((await confirm(case_id, { session_id: 'someone-else', callback_id })).status).toBe(404);
    expect((await Case.findById(case_id).lean()).status).toBe('held');
  });

  test('cannot appeal or confirm once the hold has ended', async () => {
    const { case_id } = await scored(60);
    const { callback_id } = (await appeal(case_id)).body;
    advance(60);
    await expireHolds(); // released by expiry before the call was confirmed

    const late = await confirm(case_id, { session_id: 'sess-1', callback_id });
    expect(late.status).toBe(409);
    expect((await appeal(case_id)).status).toBe(409);
  });

  test('validation', async () => {
    const { case_id } = await scored(60);
    expect((await appeal(case_id, {})).status).toBe(400);
    expect((await appeal(case_id, { session_id: 'sess-1', reason: 'x'.repeat(1001) })).status).toBe(400);
    expect((await appeal('nope')).status).toBe(400);
    expect((await confirm(case_id, { session_id: 'sess-1' })).status).toBe(400);
  });

  test('analysts never see the call-back code', async () => {
    const { case_id } = await scored(60);
    await appeal(case_id);
    const list = await asAnalyst(request(app).get('/cases'));
    expect(list.body[0].callback.started_at).toBeDefined();
    expect(list.body[0].callback.id).toBeUndefined();
  });
});

describe('hold expiry', () => {
  async function oneOfEach() {
    return {
      medium: (await scored(50)).case_id,
      high: (await scored(75)).case_id,
      critical: (await scored(90)).case_id,
    };
  }

  test('nothing happens before HOLD_SECONDS', async () => {
    await oneOfEach();
    advance(59.9);
    expect(await expireHolds()).toEqual({ released: 0, escalated: 0 });
    expect(await Case.countDocuments({ status: 'held' })).toBe(3);
  });

  test('at HOLD_SECONDS: MEDIUM/HIGH released, CRITICAL escalated (still held)', async () => {
    const ids = await oneOfEach();
    advance(60);
    expect(await expireHolds()).toEqual({ released: 2, escalated: 1 });

    for (const id of [ids.medium, ids.high]) {
      expect(await Case.findById(id).lean()).toMatchObject({
        status: 'released', hold: false, closed_via: 'expiry', seconds_held: 60,
      });
    }
    expect(await Case.findById(ids.critical).lean()).toMatchObject({
      status: 'escalated', hold: true, escalated_via: 'expiry',
    });

    const releases = await Audit.find({ action: 'release' }).lean();
    expect(releases).toHaveLength(2);
    releases.forEach((a) => expect(a).toMatchObject({ via: 'expiry', seconds_held: 60, actor: { role: 'system' } }));
    expect(await Audit.findOne({ action: 'escalate' }).lean()).toMatchObject({ via: 'expiry', tier: 'CRITICAL' });

    // Running again changes nothing.
    advance(60);
    expect(await expireHolds()).toEqual({ released: 0, escalated: 0 });
  });

  test('escalated CRITICAL: no appeal possible, analyst block closes it', async () => {
    const { case_id } = await scored(95);
    advance(61);
    await expireHolds();

    expect((await appeal(case_id)).status).toBe(409);
    advance(30);
    const closed = await decide(case_id, 'block');
    expect(closed.body).toMatchObject({ status: 'blocked', hold: false, seconds_held: 91, decided_by: 'analyst' });
    expect(await Audit.findOne({ action: 'decision' }).lean()).toMatchObject({ decision: 'block', seconds_held: 91 });
  });

  test('the background timer runs the sweep', async () => {
    const { case_id } = await scored(50);
    advance(61);
    const timer = startHoldExpiry(20);
    try {
      for (let i = 0; i < 100 && (await Case.findById(case_id).lean()).status === 'held'; i++) {
        await new Promise((r) => setTimeout(r, 20));
      }
    } finally {
      clearInterval(timer);
    }
    expect((await Case.findById(case_id).lean()).status).toBe('released');
  });
});

describe('audit is append-only', () => {
  test('no update or delete routes', async () => {
    for (const method of ['put', 'patch', 'delete']) {
      const res = await asAnalyst(request(app)[method]('/audit'));
      expect(res.status).toBe(404);
    }
  });

  test('model refuses updates and deletes', async () => {
    const rec = await Audit.create({ action: 'score', tier: 'LOW' });
    await expect(Audit.updateOne({ _id: rec._id }, { tier: 'HIGH' })).rejects.toThrow('append-only');
    await expect(Audit.findOneAndUpdate({ _id: rec._id }, { tier: 'HIGH' })).rejects.toThrow('append-only');
    await expect(Audit.deleteOne({ _id: rec._id })).rejects.toThrow('append-only');
    await expect(Audit.deleteMany({})).rejects.toThrow('append-only');
    rec.tier = 'HIGH';
    await expect(rec.save()).rejects.toThrow('append-only');
    expect((await Audit.findById(rec._id).lean()).tier).toBe('LOW');
  });
});

describe('cases routes (analyst)', () => {
  test('GET /cases sorted by R descending', async () => {
    await scored(72);
    await scored(95);
    await scored(50);
    const res = await asAnalyst(request(app).get('/cases'));
    expect(res.status).toBe(200);
    expect(res.body.map((c) => c.R)).toEqual([95, 72, 50]);
  });

  test('decision on a held case: closes it once, records seconds_held, then 409', async () => {
    const { case_id } = await scored(75);
    advance(7.5);

    const first = await decide(case_id, 'release');
    expect(first.status).toBe(200);
    expect(first.body).toMatchObject({ status: 'released', hold: false, seconds_held: 7.5, decided_by: 'analyst' });

    expect((await decide(case_id, 'block')).status).toBe(409);

    const decisions = await Audit.find({ action: 'decision' }).lean();
    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toMatchObject({
      decision: 'release', via: 'analyst', seconds_held: 7.5, actor: { username: 'analyst', role: 'analyst' },
    });
  });

  test('decision validation: bad value 400, bad id 400, unknown id 404', async () => {
    const { case_id } = await scored(90);
    expect((await decide(case_id, 'maybe')).status).toBe(400);
    expect((await decide('nope', 'block')).status).toBe(400);
    expect((await decide(new mongoose.Types.ObjectId(), 'block')).status).toBe(404);
  });
});

describe('route access matrix', () => {
  const id = new mongoose.Types.ObjectId();

  test.each([
    ['get', '/cases'],
    ['post', `/cases/${id}/decision`],
    ['get', '/audit'],
  ])('%s %s: 401 without token, 403 for user, allowed for analyst', async (method, path) => {
    expect((await request(app)[method](path)).status).toBe(401);
    expect((await asUser(request(app)[method](path))).status).toBe(403);
    const res = await asAnalyst(request(app)[method](path)).send({ decision: 'block' });
    expect([200, 404]).toContain(res.status);
  });

  test.each([`/cases/${id}/appeal`, `/cases/${id}/appeal/confirm`])(
    'POST %s: 401 without token, 403 for analyst, allowed for user',
    async (path) => {
      expect((await request(app).post(path)).status).toBe(401);
      expect((await asAnalyst(request(app).post(path))).status).toBe(403);
      const res = await asUser(request(app).post(path)).send({ session_id: 'sess-1', callback_id: 'x' });
      expect(res.status).toBe(404);
    }
  );
});

describe('login and health', () => {
  test('wrong password and unknown user are rejected', async () => {
    expect((await request(app).post('/login').send({ username: 'analyst', password: 'nope' })).status).toBe(401);
    expect((await request(app).post('/login').send({ username: 'ghost', password: 'x' })).status).toBe(401);
  });

  test('GET /health is public', async () => {
    const res = await request(app).get('/health');
    expect(res.body).toEqual({ ok: true, db: 'up' });
  });
});


// --- integration with the frozen risk engine + dashboard routes (added 2026-10-25) ---
describe('engine tier and extras from the scoring service', () => {
  test('the service tier wins over the R thresholds; versions are stored and audited', async () => {
    fetchMock.mockResolvedValue(flaskReply({
      R: 62, tier: 'HIGH', reasons: ['PAYEE_NO_HISTORY'], model_version: 'risk-0.2.0', rules_version: 'v2',
      disclaimer: null, ask_user: null, context_flags: ['SCREEN_SHARE'],
    }));
    const res = await score(body());
    expect(res.body).toMatchObject({ R: 62, tier: 'HIGH', model_version: 'risk-0.2.0', rules_version: 'v2',
      context_flags: ['SCREEN_SHARE'] });
    expect(await Event.findOne().lean()).toMatchObject({ model_version: 'risk-0.2.0', rules_version: 'v2' });
    expect(await Audit.findOne({ action: 'score' }).lean()).toMatchObject({ model_version: 'risk-0.2.0' });
  });

  test('an unknown tier from the service falls back to tierFor(R)', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 90, tier: 'SEVERE', reasons: [] }));
    expect((await score(body())).body.tier).toBe('CRITICAL');
  });

  test('new engine codes have plain-language text', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 93, tier: 'CRITICAL', reasons: ['PIN_TO_RECEIVE', 'AMOUNT_MISMATCH'] }));
    const { why } = (await score(body())).body;
    expect(why[0]).toMatch(/never need a PIN to receive money/);
    expect(why[1]).toMatch(/sends the same amount out/);
  });

  test.each([
    ['payee_prior_txns', { payee_prior_txns: -1 }],
    ['hour', { hour: 24 }],
    ['direction', { direction: 'sideways' }],
  ])('400 on a bad optional payment.%s', async (_n, extra) => {
    const p = { payee_vpa: 'a.b@ybl', amount: 5, payee_age_days: 1, user_avg_amount: 1, ...extra };
    expect((await score(body({ payment: p }))).status).toBe(400);
  });
});

describe('dashboard routes', () => {
  test('GET /events: newest first, no text, no payee id', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 20, reasons: [] }));
    await score(body());
    const res = await request(app).get('/events');
    expect(res.status).toBe(200);
    expect(res.body).toHaveLength(1);
    const ev = res.body[0];
    expect(ev).toMatchObject({ R: 20, tier: 'LOW', amount: 2500 });
    expect(JSON.stringify(ev)).not.toMatch(/OTP|payee_vpa|demo\.payee|sess-1/);
  });

  test('/score emits a dashboard-safe event on the bus', async () => {
    const { bus } = require('./server');
    const seen = [];
    const listener = (e) => seen.push(e);
    bus.on('event', listener);
    fetchMock.mockResolvedValue(flaskReply({ R: 20, reasons: [] }));
    await score(body());
    bus.off('event', listener);
    expect(seen).toHaveLength(1);
    expect(seen[0]).not.toHaveProperty('redacted_text');
  });

  test('GET /stats: tier counts and zero-friction share', async () => {
    fetchMock.mockResolvedValueOnce(flaskReply({ R: 20, reasons: [] }));
    await score(body());
    fetchMock.mockResolvedValueOnce(flaskReply({ R: 90, reasons: ['OTP_REQUEST'] }));
    await score(body());
    const res = await request(app).get('/stats');
    expect(res.body).toMatchObject({ total: 2, tiers: { LOW: 1, CRITICAL: 1 }, zero_friction_pct: 50 });
    expect(res.body.reasons).toMatchObject({ OTP_REQUEST: 1 });
  });

  test('GET /metrics returns a JSON object', async () => {
    const res = await request(app).get('/metrics');
    expect(res.status).toBe(200);
    expect(typeof res.body).toBe('object');
  });
});
