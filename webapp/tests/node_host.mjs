// End-to-end in Node: Pyodide engine + HostController + 3 StudentClients over an in-memory hub.
// Simulated students play a whole game; checks PINs, phases, duplicate delivery, state sync,
// and that resuming from the saved log reproduces the teacher view.
import fs from 'fs';
import assert from 'assert/strict';
import { createEngine } from '../js/engine-core.js';
import { HostController } from '../js/host.js';
import { StudentClient } from '../js/student-client.js';
import { MemoryHub } from '../js/transport.js';
const { loadPyodide } = await import(process.env.PYODIDE_MODULE || 'pyodide');

const bundle = JSON.parse(fs.readFileSync(new URL('../engine_bundle.json', import.meta.url)));
const sync = await createEngine({ loadPyodide, bundle });
const engine = Object.fromEntries(Object.entries(sync).map(([k, f]) => [k, async (...a) => f(...a)]));
const mem = new Map();
const storage = { get: (k) => mem.get(k) ?? null, set: (k, v) => mem.set(k, v), remove: (k) => mem.delete(k) };
const tick = () => new Promise((r) => setTimeout(r, 5));

const hub = new MemoryHub();
let teacher = null;
const host = new HostController({ engine, transport: hub.connect(), room: 'TEST1', storage, onChange: (t) => { teacher = t; } });
const STU = ['Tropia', 'Mechania', 'Mineria'];
await host.newGame({ students: STU, seed: 777 });
assert.equal(teacher.round, 1); assert.equal(teacher.phase, 'listing');

// wrong PIN / wrong country / teacher-only actions are refused
const intruder = new StudentClient({ transport: hub.connect(), country: 'Tropia', token: '0000' });
assert.equal((await intruder.connect()).ok, false);
const ai = new StudentClient({ transport: hub.connect(), country: 'Grainia', token: host.tokens.Tropia });
assert.equal((await ai.connect()).ok, false);

const me = {};
for (const n of STU) {
  me[n] = new StudentClient({ transport: hub.connect(), country: n, token: host.tokens[n] });
  const r = await me[n].connect();
  assert.equal(r.ok, true, r.msg);
}
await tick();
for (const n of STU) assert.equal(me[n].state.country, n);
assert.equal((await me.Tropia.send({ type: 'advance' })).ok, false);
// a student cannot act for another country: the host forces the authenticated country
const r0 = await me.Tropia.send({ type: 'list', country: 'Mechania', good: 'banana', qty: 1, price: 999 });
assert.equal(r0.ok, true); await tick();
assert.ok(me.Tropia.state.my_orders.some((o) => o.price === 999));
assert.ok(!me.Mechania.state.my_orders.some((o) => o.price === 999));
// duplicate delivery of the same action id is applied once
const dupe = { id: 'same-id', country: 'Tropia', token: host.tokens.Tropia, action: { type: 'list', good: 'wheat', qty: 1, price: 777 } };
const d1 = await host.studentAction(dupe); const d2 = await host.studentAction(dupe);
assert.deepEqual(d1, d2); await tick();
assert.equal(me.Tropia.state.my_orders.filter((o) => o.price === 777).length, 1);

let actions = 0;
async function play(n) {
  const c = me[n]; const S = c.state;
  if (S.phase === 'listing') {
    for (const o of S.my_orders) { await c.cancel(o.oid); actions++; }
    const S2 = c.state;
    for (const r of S2.stock) {
      const need = S2.settlement.rows.filter((x) => x.good === r.good).reduce((a, x) => a + x.need, 0);
      const extra = r.free - need - (r.good === 'ore' ? 1 : 0);
      if (extra > 0) { await c.list(r.good, extra, S2.quotes[r.good][r.gen], r.gen); actions++; }
    }
  } else if (S.phase === 'trading') {
    for (const row of S.settlement.rows.filter((x) => x.short > 0)) {
      const o = c.state.market.filter((m) => m.good === row.good && m.seller !== n && m.price <= 2 * m.reference)
        .sort((a, b) => a.price - b.price)[0];
      if (o) { await c.buy(o.oid, Math.min(row.short, o.qty)); actions++; }
    }
  } else if (S.phase === 'invest') {
    const main = S.invest_options.find((o) => o.good === S.main);
    if (main && main.ok && !S.progress.main_levelled) { const r = await c.invest(S.main); assert.equal(r.ok, true, r.msg); actions++; }
    await c.focus(S.main); actions++;
  }
}

// one student-to-student deal in round 1 trading
let offered = false;
while (teacher.phase !== 'finished') {
  await Promise.all(STU.map(play));            // students act concurrently
  if (teacher.phase === 'trading' && !offered) {
    const r = await me.Tropia.offerSell('Mechania', { good: 'banana', qty: 1 }, 9);
    assert.equal(r.ok, true, r.msg); await tick();
    const o = me.Mechania.state.offers.find((x) => x.status === 'pending');
    assert.ok(o, 'offer reached Mechania');
    assert.equal((await me.Mechania.respond(o.id, true)).ok, true);
    offered = true;
  }
  const before = teacher.round;
  const r = await host.teacherAction({ type: 'advance' });
  assert.equal(r.ok, true, r.msg);
  await tick();
  for (const n of STU) {
    assert.equal(me[n].state.round, teacher.round);
    assert.equal(me[n].state.phase, teacher.phase);
  }
  if (teacher.round !== before) process.stdout.write(`R${before} `);
}
console.log();
assert.ok(teacher.results);
for (const n of STU) assert.ok(me[n].state.results && me[n].state.results[n].total >= 0);
const scores = Object.fromEntries(STU.map((n) => [n, [Number(teacher.results[n].total.toFixed(1)), teacher.results[n].grade]]));

// resume from the saved log reproduces the same teacher view
const saved = JSON.parse(storage.get('trade-game-host-TEST1'));
const finalTeacher = JSON.stringify(teacher);
const host2 = new HostController({ engine, transport: new MemoryHub().connect(), room: 'TEST1', storage: null, onChange: (t) => { teacher = t; } });
await host2.resume(saved);
assert.equal(JSON.stringify(teacher), finalTeacher);
console.log('node host test ok:', JSON.stringify({ actions, log: saved.log.length, scores }));
