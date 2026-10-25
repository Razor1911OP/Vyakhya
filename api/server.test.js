// Tests for server.js. Flask is mocked by stubbing global fetch; MongoDB runs
// in memory (mongodb-memory-server), so no local services are needed.
// All payloads are synthetic.
const request = require('supertest');
const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');
const { createApp, tierFor, Event, Case, Audit } = require('./server');

let mongo;
let app;
let userToken;
let analystToken;
let fetchMock;

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
    const res = await request(app)
      .post('/score')
      .set('Content-Type', 'application/json')
      .send('{not json');
    expect(res.status).toBe(400);
  });
});

describe('POST /score: tiers, cases, hold', () => {
  test('LOW: no case, no hold, audit written', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 20, reasons: [] }));
    const res = await score(body());

    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ R: 20, tier: 'LOW', hold: false, case_id: null, reasons: [], why: [] });
    expect(await Case.countDocuments()).toBe(0);
    expect(await Event.countDocuments()).toBe(1);
    const audit = await Audit.findOne().lean();
    expect(audit).toMatchObject({ action: 'score', tier: 'LOW', R: 20, scoring_ok: true });
  });

  test('MEDIUM (R=69): no case, no hold', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 69, reasons: ['NEW_PAYEE'] }));
    const res = await score(body());
    expect(res.body).toMatchObject({ tier: 'MEDIUM', hold: false, case_id: null });
    expect(await Case.countDocuments()).toBe(0);
  });

  test('HIGH (R=70): case created, no hold', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 70, reasons: ['OTP_REQUEST'] }));
    const res = await score(body());

    expect(res.body).toMatchObject({ tier: 'HIGH', hold: false });
    expect(res.body.case_id).toEqual(expect.any(String));
    const c = await Case.findById(res.body.case_id).lean();
    expect(c).toMatchObject({ status: 'open', tier: 'HIGH', R: 70, hold: false });
  });

  test('CRITICAL (R=85): case created and hold=true', async () => {
    fetchMock.mockResolvedValue(flaskReply({ R: 85, reasons: ['SCREEN_SHARE', 'OTP_REQUEST'] }));
    const res = await score(body());

    expect(res.body).toMatchObject({ tier: 'CRITICAL', hold: true });
    expect(await Case.countDocuments()).toBe(1);
    const audit = await Audit.findOne().lean();
    expect(String(audit.case_id)).toBe(res.body.case_id);
    expect(audit.hold).toBe(true);
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
    expect(res.body).toMatchObject({
      R: null, tier: 'MEDIUM', reasons: ['SCORING_UNAVAILABLE'], hold: false, case_id: null,
    });
    expect(res.body.why[0]).toMatch(/could not be reached/);
    expect(await Case.countDocuments()).toBe(0);
    // Still audited, flagged as a scoring failure.
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

describe('audit is append-only', () => {
  test('no update or delete routes', async () => {
    for (const method of ['put', 'patch', 'delete']) {
      const res = await request(app)[method]('/audit').set('Authorization', `Bearer ${analystToken}`);
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

  test('GET /audit is analyst-only', async () => {
    expect((await request(app).get('/audit').set('Authorization', `Bearer ${userToken}`)).status).toBe(403);
    expect((await request(app).get('/audit').set('Authorization', `Bearer ${analystToken}`)).status).toBe(200);
  });
});

describe('cases routes', () => {
  async function makeCase(R) {
    fetchMock.mockResolvedValueOnce(flaskReply({ R, reasons: ['OTP_REQUEST'] }));
    return (await score(body())).body.case_id;
  }

  test('user role gets 403, no token gets 401', async () => {
    expect((await request(app).get('/cases')).status).toBe(401);
    expect((await request(app).get('/cases').set('Authorization', `Bearer ${userToken}`)).status).toBe(403);
  });

  test('GET /cases sorted by R descending', async () => {
    await makeCase(72);
    await makeCase(95);
    await makeCase(80);
    const res = await request(app).get('/cases').set('Authorization', `Bearer ${analystToken}`);
    expect(res.status).toBe(200);
    expect(res.body.map((c) => c.R)).toEqual([95, 80, 72]);
  });

  test('decision: release once, then 409; audited', async () => {
    const id = await makeCase(90);
    const decide = (decision) =>
      request(app).post(`/cases/${id}/decision`).set('Authorization', `Bearer ${analystToken}`).send({ decision });

    const first = await decide('release');
    expect(first.status).toBe(200);
    expect(first.body).toMatchObject({ status: 'released', decided_by: 'analyst' });

    expect((await decide('block')).status).toBe(409);

    const decisions = await Audit.find({ action: 'decision' }).lean();
    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toMatchObject({ decision: 'release', actor: { username: 'analyst', role: 'analyst' } });
  });

  test('decision validation: bad value 400, bad id 400, unknown id 404', async () => {
    const auth = { Authorization: `Bearer ${analystToken}` };
    const id = await makeCase(90);
    expect((await request(app).post(`/cases/${id}/decision`).set(auth).send({ decision: 'maybe' })).status).toBe(400);
    expect((await request(app).post('/cases/nope/decision').set(auth).send({ decision: 'block' })).status).toBe(400);
    const unknown = new mongoose.Types.ObjectId();
    expect((await request(app).post(`/cases/${unknown}/decision`).set(auth).send({ decision: 'block' })).status).toBe(404);
  });
});

describe('route access matrix', () => {
  const id = new mongoose.Types.ObjectId();
  const routes = [
    ['get', '/cases'],
    ['post', `/cases/${id}/decision`],
    ['get', '/audit'],
  ];

  test.each(routes)('%s %s: 401 without token, 403 for user, allowed for analyst', async (method, path) => {
    expect((await request(app)[method](path)).status).toBe(401);
    expect((await request(app)[method](path).set('Authorization', `Bearer ${userToken}`)).status).toBe(403);
    const asAnalyst = await request(app)[method](path).set('Authorization', `Bearer ${analystToken}`).send({ decision: 'block' });
    expect([200, 404]).toContain(asAnalyst.status);
  });

  test('appeal: 401 without token, 403 for analyst, allowed for user', async () => {
    const path = `/cases/${id}/appeal`;
    expect((await request(app).post(path)).status).toBe(401);
    expect((await request(app).post(path).set('Authorization', `Bearer ${analystToken}`)).status).toBe(403);
    const asUser = await request(app).post(path).set('Authorization', `Bearer ${userToken}`).send({ session_id: 'sess-1' });
    expect(asUser.status).toBe(404);
  });
});

describe('POST /cases/:id/appeal', () => {
  const asUser = (id, b) => request(app).post(`/cases/${id}/appeal`).set('Authorization', `Bearer ${userToken}`).send(b);
  const decide = (id, decision) =>
    request(app).post(`/cases/${id}/decision`).set('Authorization', `Bearer ${analystToken}`).send({ decision });

  async function blockedCase() {
    fetchMock.mockResolvedValueOnce(flaskReply({ R: 92, reasons: ['OTP_REQUEST'] }));
    const id = (await score(body())).body.case_id;
    await decide(id, 'block');
    return id;
  }

  test('blocked -> appealed -> analyst releases; reason redacted; all audited', async () => {
    const id = await blockedCase();

    const res = await asUser(id, { session_id: 'sess-1', reason: 'It was my brother, call 9876543210' });
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('appealed');
    expect(res.body.appeal).toMatchObject({ reason: 'It was my brother, call [PHONE]', by: 'user' });
    expect(JSON.stringify(await Case.findById(id).lean())).not.toContain('9876543210');

    // Shows up for the analyst and can be decided again.
    const list = await request(app).get('/cases?status=appealed').set('Authorization', `Bearer ${analystToken}`);
    expect(list.body.map((c) => c._id)).toEqual([id]);
    expect((await decide(id, 'release')).body.status).toBe('released');

    const actions = (await Audit.find({ case_id: id }).sort({ created_at: 1 }).lean()).map((a) => a.action);
    expect(actions).toEqual(['score', 'decision', 'appeal', 'decision']);
  });

  test('only once per case', async () => {
    const id = await blockedCase();
    expect((await asUser(id, { session_id: 'sess-1' })).status).toBe(200);
    await decide(id, 'block');
    const again = await asUser(id, { session_id: 'sess-1' });
    expect(again.status).toBe(409);
    expect(again.body.error).toMatch(/already appealed/);
  });

  test('open or released cases cannot be appealed', async () => {
    fetchMock.mockResolvedValueOnce(flaskReply({ R: 90, reasons: [] }));
    const id = (await score(body())).body.case_id;
    expect((await asUser(id, { session_id: 'sess-1' })).status).toBe(409);
    await decide(id, 'release');
    expect((await asUser(id, { session_id: 'sess-1' })).status).toBe(409);
  });

  test('wrong session_id looks like "not found"', async () => {
    const id = await blockedCase();
    expect((await asUser(id, { session_id: 'someone-else' })).status).toBe(404);
    expect((await Case.findById(id).lean()).status).toBe('blocked');
  });

  test('validation', async () => {
    const id = await blockedCase();
    expect((await asUser(id, {})).status).toBe(400);
    expect((await asUser(id, { session_id: 'sess-1', reason: 'x'.repeat(1001) })).status).toBe(400);
    expect((await asUser('nope', { session_id: 'sess-1' })).status).toBe(400);
  });
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
