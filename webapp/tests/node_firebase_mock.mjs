// FirebaseServer against an in-memory imitation of the Realtime Database API
// (getDatabase, ref, set, push, remove, onValue, onChildAdded, onDisconnect, .info/connected,
// goOffline; asynchronous delivery). Checks: one connection per page for many rooms, the
// action -> host -> result flow and cleanup, presence (join, count, removal on disconnect),
// the REST head count, an action sent while the host is away, and a class restart.
import fs from 'fs';
import assert from 'assert/strict';
import { createEngine } from '../js/engine-core.js';
import { ClassHost, savedClasses } from '../js/host.js';
import { StudentClient } from '../js/student-client.js';
import { FirebaseServer, countOnline } from '../js/transport.js';
const { loadPyodide } = await import(process.env.PYODIDE_MODULE || 'pyodide');

// ---------------------------------------------------------------- fake RTDB
const tree = {};
const valueSubs = new Map();
const childSubs = new Map();
const onDisc = new Map(); // dbId -> Set(path)
let counter = 0; let dbs = 0; let apps = 0;
const later = (f) => setTimeout(f, Math.floor(Math.random() * 3));
const parts = (p) => p.split('/').filter(Boolean);
function get(p) { let n = tree; for (const k of parts(p)) { if (n == null || typeof n !== 'object') return null; n = n[k]; } return n === undefined ? null : n; }
function put(p, v) {
  const ks = parts(p); if (!ks.length) return; let n = tree;
  for (const k of ks.slice(0, -1)) { if (typeof n[k] !== 'object' || n[k] === null) n[k] = {}; n = n[k]; }
  if (v === null) delete n[ks.at(-1)]; else n[ks.at(-1)] = JSON.parse(JSON.stringify(v));
}
const snap = (p) => ({ key: parts(p).at(-1), ref: mkRef(p), val: () => (p === '.info/connected' ? true : JSON.parse(JSON.stringify(get(p)))) });
const mkRef = (p, db) => ({ path: p, key: parts(p).at(-1), db });
function notify(p, existed) {
  for (const [sp, subs] of valueSubs) if (p === sp || p.startsWith(sp + '/') || sp.startsWith(p + '/')) for (const cb of subs) later(() => cb(snap(sp)));
  const parent = parts(p).slice(0, -1).join('/');
  if (!existed && get(p) !== null && childSubs.has(parent)) for (const cb of childSubs.get(parent)) later(() => cb(snap(p)));
}
const database = {
  getDatabase: () => { const id = ++dbs; onDisc.set(id, new Set()); return { id }; },
  ref: (db, p) => mkRef(p, db),
  set: async (r, v) => { const existed = get(r.path) !== null; put(r.path, v); notify(r.path, existed); },
  remove: async (r) => { put(r.path, null); notify(r.path, true); },
  push: (r) => mkRef(`${r.path}/k${String(++counter).padStart(8, '0')}`, r.db),
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
  onDisconnect: (r) => ({ remove: async () => { onDisc.get(r.db.id).add(r.path); } }),
  goOffline: (db) => { for (const p of onDisc.get(db.id)) database.remove(mkRef(p)); onDisc.get(db.id).clear(); },
};
const modules = { app: { initializeApp: () => ({ n: ++apps }) }, database };
const CONFIG = { databaseURL: 'https://fake-default-rtdb.example.app' };
const fakeFetch = async (url) => {
  assert.ok(url.startsWith(CONFIG.databaseURL + '/presence.json?shallow=true'), url);
  const v = get('presence');
  return { ok: true, json: async () => (v ? Object.fromEntries(Object.keys(v).map((k) => [k, true])) : null) };
};
const page = async () => { const s = await FirebaseServer.create(CONFIG, modules); s.info = { id: '1' }; return s; };
const wait = (ms = 40) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- test
const bundle = JSON.parse(fs.readFileSync(new URL('../engine_bundle.json', import.meta.url)));
const sync = await createEngine({ loadPyodide, bundle });
const engine = Object.fromEntries(Object.entries(sync).map(([k, f]) => [k, async (...a) => f(...a)]));
const mem = new Map();
const storage = { get: (k) => mem.get(k) ?? null, set: (k, v) => mem.set(k, v), remove: (k) => mem.delete(k), keys: () => [...mem.keys()] };

const hostPage = await page();
const cls = new ClassHost({ engine, server: hostPage, storage, onChange: () => {} });
await cls.create({ students: ['Grainia', 'Technia'], rooms: 2, settings: { mode: 'teacher' } });
const [c1, c2] = [...cls.rooms.keys()];
assert.equal(apps, 1, 'one Firebase connection for a teacher page with two rooms');

const gPage = await page(); const tPage = await page();
const leaveG = gPage.presence.join({ role: 'student', room: c1, country: 'Grainia' });
tPage.presence.join({ role: 'student', room: c2, country: 'Technia' });
const g = new StudentClient({ transport: gPage.room(c1), country: 'Grainia', token: cls.room(c1).tokens.Grainia });
const t = new StudentClient({ transport: tPage.room(c2), country: 'Technia', token: cls.room(c2).tokens.Technia });
assert.equal((await g.connect()).ok, true);
assert.equal((await t.connect()).ok, true);
await wait();
assert.equal(g.state.room.code, c1); assert.equal(t.state.room.code, c2);
assert.equal(await countOnline({ firebase: CONFIG }, fakeFetch), 3, 'host + 2 students');
assert.deepEqual(cls.summary().rooms[0].online, ['Grainia']);

const r1 = await g.list('wheat', 1, 9);
assert.equal(r1.ok, true, r1.msg); await wait();
assert.ok(g.state.my_orders.some((o) => o.price === 9));
assert.deepEqual(Object.keys(get(`rooms/${c1}/actions`) || {}), [], 'actions removed after processing');
assert.deepEqual(Object.keys(get(`rooms/${c1}/results`) || {}), [], 'results removed after reading');
assert.ok(!(t.state.my_orders || []).some((o) => o.price === 9), 'rooms are separate');

// a student closes the tab: the database removes its presence entry
gPage.close(); leaveG; await wait();
assert.equal(await countOnline({ firebase: CONFIG }, fakeFetch), 2);

// the teacher page goes away; a student sends an action meanwhile; a new page restores the class
hostPage.close(); await wait();
assert.equal(await countOnline({ firebase: CONFIG }, fakeFetch), 1);
const pendingSend = t.list('electronics', 1, 200);
await wait(60);
assert.equal(Object.keys(get(`rooms/${c2}/actions`) || {}).length, 1, 'action waits in the database');
const host2 = await page();
const cls2 = new ClassHost({ engine, server: host2, storage, onChange: () => {} });
await cls2.restore(savedClasses(storage).find((m) => m.cls === cls.cls));
const r2 = await pendingSend;
assert.equal(r2.ok, true, r2.msg); await wait();
assert.ok(t.state.my_orders.some((o) => o.price === 200));
await cls2.advanceAll(); await wait();
assert.equal(t.state.phase, 'trading');
// finishing the class clears its rooms from the database
await cls2.finish({ clearServer: true });
assert.equal(get(`rooms/${c1}`), null); assert.equal(get(`rooms/${c2}`), null);
console.log('firebase server (mock RTDB) ok: rooms', c1, c2, '| connections opened', apps);
process.exit(0);
