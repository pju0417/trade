// FirebaseTransport against an in-memory imitation of the Realtime Database API
// (getDatabase, ref, set, push, remove, onValue, onChildAdded; asynchronous delivery).
// Checks the message flow: actions -> host -> results -> student, state fan-out, action/result
// cleanup, an action sent while the host is away, and a host restart (no double application).
import fs from 'fs';
import assert from 'assert/strict';
import { createEngine } from '../js/engine-core.js';
import { HostController } from '../js/host.js';
import { StudentClient } from '../js/student-client.js';
import { FirebaseTransport } from '../js/transport.js';
const { loadPyodide } = await import(process.env.PYODIDE_MODULE || 'pyodide');

// ---------------------------------------------------------------- fake RTDB
const tree = {};
const valueSubs = new Map(); // path -> Set(cb)
const childSubs = new Map(); // path -> Set(cb)
let counter = 0;
const later = (f) => setTimeout(f, Math.floor(Math.random() * 3));
const parts = (p) => p.split('/').filter(Boolean);
function get(p) { let n = tree; for (const k of parts(p)) { if (n == null || typeof n !== 'object') return null; n = n[k]; } return n === undefined ? null : n; }
function put(p, v) {
  const ks = parts(p); let n = tree;
  for (const k of ks.slice(0, -1)) { if (typeof n[k] !== 'object' || n[k] === null) n[k] = {}; n = n[k]; }
  if (v === null) delete n[ks.at(-1)]; else n[ks.at(-1)] = JSON.parse(JSON.stringify(v));
}
const snap = (p) => ({ key: parts(p).at(-1), ref: mkRef(p), val: () => JSON.parse(JSON.stringify(get(p))) });
const mkRef = (p) => ({ path: p, key: parts(p).at(-1) });
function notify(p, existed) {
  for (const [sp, subs] of valueSubs) if (p === sp || p.startsWith(sp + '/') || sp.startsWith(p + '/')) for (const cb of subs) later(() => cb(snap(sp)));
  const parent = parts(p).slice(0, -1).join('/');
  if (!existed && get(p) !== null && childSubs.has(parent)) for (const cb of childSubs.get(parent)) later(() => cb(snap(p)));
}
const database = {
  getDatabase: () => ({}),
  ref: (db, p) => mkRef(p),
  set: async (r, v) => { const existed = get(r.path) !== null; put(r.path, v); notify(r.path, existed); },
  remove: async (r) => { put(r.path, null); notify(r.path, true); },
  push: (r) => mkRef(`${r.path}/k${String(++counter).padStart(8, '0')}`),
  onValue: (r, cb) => {
    if (!valueSubs.has(r.path)) valueSubs.set(r.path, new Set());
    valueSubs.get(r.path).add(cb); later(() => cb(snap(r.path)));
    return () => valueSubs.get(r.path).delete(cb);
  },
  onChildAdded: (r, cb) => {
    if (!childSubs.has(r.path)) childSubs.set(r.path, new Set());
    childSubs.get(r.path).add(cb);
    const cur = get(r.path) || {};
    for (const k of Object.keys(cur).sort()) later(() => cb(snap(`${r.path}/${k}`)));
    return () => childSubs.get(r.path).delete(cb);
  },
};
const modules = { app: { initializeApp: () => ({}) }, database };
const mk = () => FirebaseTransport.create({ fake: true }, 'ROOM9', modules);
const wait = (ms = 30) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- test
const bundle = JSON.parse(fs.readFileSync(new URL('../engine_bundle.json', import.meta.url)));
const sync = await createEngine({ loadPyodide, bundle });
const engine = Object.fromEntries(Object.entries(sync).map(([k, f]) => [k, async (...a) => f(...a)]));
const mem = new Map();
const storage = { get: (k) => mem.get(k) ?? null, set: (k, v) => mem.set(k, v), remove: (k) => mem.delete(k) };
let teacher = null;
const host = new HostController({ engine, transport: await mk(), room: 'ROOM9', storage, onChange: (t) => { teacher = t; } });
await host.newGame({ students: ['Grainia', 'Technia'], seed: 99 });

const g = new StudentClient({ transport: await mk(), country: 'Grainia', token: host.tokens.Grainia });
const t = new StudentClient({ transport: await mk(), country: 'Technia', token: host.tokens.Technia });
assert.equal((await g.connect()).ok, true);
assert.equal((await t.connect()).ok, true);
await wait();
assert.equal(g.state.country, 'Grainia'); assert.equal(t.state.country, 'Technia');
const bad = new StudentClient({ transport: await mk(), country: 'Grainia', token: '1' });
assert.equal((await bad.connect()).ok, false);

const r1 = await g.list('wheat', 1, 9);
assert.equal(r1.ok, true, r1.msg);
await wait();
assert.ok(g.state.my_orders.some((o) => o.price === 9));
assert.deepEqual(Object.keys(get('rooms/ROOM9/actions') || {}), [], 'actions are removed after processing');
assert.deepEqual(Object.keys(get('rooms/ROOM9/results') || {}), [], 'results are removed after reading');

// host goes away; a student sends an action meanwhile; a new host resumes from the saved log
host.transport.close();
const pendingSend = t.list('electronics', 1, 200);
await wait(50);
assert.equal(Object.keys(get('rooms/ROOM9/actions') || {}).length, 1, 'action waits in the database');
const saved = JSON.parse(storage.get('trade-game-host-ROOM9'));
const host2 = new HostController({ engine, transport: await mk(), room: 'ROOM9', storage, onChange: (x) => { teacher = x; } });
await host2.resume(saved);
const r2 = await pendingSend;
assert.equal(r2.ok, true, r2.msg);
await wait();
assert.ok(t.state.my_orders.some((o) => o.price === 200));
const log = await engine.log();
assert.equal(log.filter((a) => a.type === 'list' && a.price === 9).length, 1, 'no double application after restart');
// teacher advances; both students follow
await host2.teacherAction({ type: 'advance' });
await wait();
assert.equal(g.state.phase, 'trading'); assert.equal(t.state.phase, 'trading');
console.log('firebase transport (mock RTDB) ok: log', log.length + 1, 'actions; phase', teacher.phase);
