// Multi-room class with progress modes (Pyodide engine, in-memory transport, fake clock).
import fs from 'fs';
import assert from 'assert/strict';
import { createEngine } from '../js/engine-core.js';
import { ClassHost, savedClasses } from '../js/host.js';
import { StudentClient } from '../js/student-client.js';
import { MemoryHub, parseRoomCode } from '../js/transport.js';
const { loadPyodide } = await import(process.env.PYODIDE_MODULE || 'pyodide');

const bundle = JSON.parse(fs.readFileSync(new URL('../engine_bundle.json', import.meta.url)));
const sync = await createEngine({ loadPyodide, bundle });
const engine = Object.fromEntries(Object.entries(sync).map(([k, f]) => [k, async (...a) => f(...a)]));
const mem = new Map();
const storage = { get: (k) => mem.get(k) ?? null, set: (k, v) => mem.set(k, v), remove: (k) => mem.delete(k), keys: () => [...mem.keys()] };
const wait = (ms = 20) => new Promise((r) => setTimeout(r, ms));
let T = 1_000_000;
const now = () => T;

const hub = new MemoryHub();
const hostServer = hub.server(); hostServer.info = { id: 'L' };
let summary = null;
const cls = new ClassHost({ engine, server: hostServer, storage, now, onChange: (s) => { summary = s; } });
const STU = ['Tropia', 'Oilia', 'Mineria'];
await cls.create({ students: STU, rooms: 3, settings: { mode: 'ready_timer', firstRoundTeacher: true, timer: { listing: 120, trading: 240, invest: 60 } } });
const codes = [...cls.rooms.keys()];
assert.equal(codes.length, 3);
assert.ok(codes.every((c) => parseRoomCode(c) && parseRoomCode(c).server === 'L'));
const R = codes.map((c) => cls.room(c));
assert.notEqual(R[0].seed, R[1].seed, 'rooms are separate games');
assert.notEqual(JSON.stringify(R[0].view.market), JSON.stringify(R[1].view.market));

// students of room 1 (Tropia played by a team of two devices)
const students = {};
for (const n of STU) {
  const srv = hub.server();
  srv.presence.join({ role: 'student', room: codes[0], country: n });
  students[n] = new StudentClient({ transport: srv.room(codes[0]), country: n, token: R[0].tokens[n] });
  assert.equal((await students[n].connect()).ok, true);
}
const mate = new StudentClient({ transport: hub.server().room(codes[0]), country: 'Tropia', token: R[0].tokens.Tropia });
assert.equal((await mate.connect()).ok, true);
// a room-1 PIN does not open room 2 (unless the random PINs coincide)
if (R[0].tokens.Oilia !== R[1].tokens.Oilia) {
  const wrong = new StudentClient({ transport: hub.server().room(codes[1]), country: 'Oilia', token: R[0].tokens.Oilia });
  assert.equal((await wrong.connect()).ok, false);
}
await wait(50);
assert.equal(students.Oilia.state.room.mode, 'teacher', 'round 1 is teacher-led');

// round 1: everyone ready, but teacher mode -> no automatic advance
for (const n of STU) assert.equal((await students[n].ready(true)).ok, true);
await wait(); T += 60_000; await cls.tick(); await wait();
assert.equal(R[0].view.phase, 'listing');
assert.equal(students.Tropia.state.room.ready.length, 3);
// teacher advances all rooms: R1 listing -> trading -> invest -> R2 listing
for (let i = 0; i < 3; i++) await cls.advanceAll();
await wait();
for (const r of R) assert.deepEqual([r.view.round, r.view.phase], [2, 'listing']);
assert.equal(students.Mineria.state.room.mode, 'ready_timer');
assert.equal(students.Mineria.state.room.ready.length, 0, 'ready marks reset each phase');
assert.equal(students.Mineria.state.room.deadline_ms, 120_000);

// round 2 room 1: all ready -> 5 s countdown; one cancels; again; advance after 5 s
for (const n of STU) await students[n].ready(true);
await wait();
assert.equal(R[0].info().countdown_ms, 5000);
T += 4000; await cls.tick();
assert.equal(R[0].view.phase, 'listing');
await students.Oilia.ready(false); await wait();
assert.equal(R[0].info().countdown_ms, null, 'cancel stops the countdown');
await mate.ready(true); // Tropia's team mate: already ready, no change
await students.Oilia.ready(true); await wait();
T += 5000; await cls.tick(); await wait();
assert.equal(R[0].view.phase, 'trading', 'room 1 advanced by ready');
assert.equal(R[1].view.phase, 'listing', 'room 2 waits');
// room 2 advances when its listing time (120 s from phase start) runs out
T += 120_000; await cls.tick(); await wait();
assert.equal(R[1].view.phase, 'trading', 'room 2 advanced by timer');

// pause freezes timers in every room
const left = R[0].info().deadline_ms;
await cls.pause();
T += 1_000_000; await cls.tick(); await wait();
assert.equal(R[0].view.phase, 'trading');
assert.equal(R[0].info().deadline_ms, left);
assert.equal(students.Tropia.state.room.paused, true);
await cls.resume();
T += left - 1; await cls.tick(); assert.equal(R[0].view.phase, 'trading');
T += 1; await cls.tick(); await wait();
assert.equal(R[0].view.phase, 'invest', 'timer resumes where it stopped');

// switching to teacher mode stops automatic progress
await cls.setSettings({ mode: 'teacher' });
for (const n of STU) await students[n].ready(true);
T += 1_000_000; await cls.tick(); await wait();
assert.equal(R[0].view.phase, 'invest');
await cls.setSettings({ mode: 'ready_timer' });

// presence: the teacher sees who is online in room 1
await wait(50);
assert.deepEqual(new Set(summary.rooms[0].online), new Set(STU), JSON.stringify(summary.rooms[0].online));

// students cannot advance; per-room advance by the teacher
assert.equal((await students.Tropia.send({ type: 'advance' })).ok, false);
await cls.advance(codes[2]);
await wait();
const before = Object.fromEntries(R.map((r) => [r.code, JSON.stringify(r.view)]));

// resume the whole class from storage with fresh sessions
const meta = savedClasses(storage).find((m) => m.cls === cls.cls);
for (const c of codes) await engine.drop(c);
const cls2 = new ClassHost({ engine, server: hub.server(), storage, now, onChange: () => {} });
cls2.server.info = { id: 'L' };
await cls2.restore(meta);
for (const c of codes) assert.equal(JSON.stringify(cls2.room(c).view), before[c], 'resumed room equals saved room ' + c);
assert.equal(cls2.settings.mode, 'ready_timer');
console.log('class test ok:', JSON.stringify({ rooms: codes, phases: R.map((r) => `${r.view.round}:${r.view.phase}`) }));
process.exit(0);
