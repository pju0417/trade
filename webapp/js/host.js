// Teacher side. One ClassHost runs several rooms (independent games) with ONE engine and ONE
// server connection. Each RoomHost checks PINs, applies actions in order, tracks "ready" and the
// phase timer, publishes every student's state, and saves its action log (seed + students + log
// reproduce a room exactly, so the class can be resumed after a reload).
//
//   const cls = new ClassHost({ engine, server, storage, onChange })
//   await cls.create({ students: ['Tropia', 'Oilia', 'Mineria'], rooms: 3, settings })   // or cls.restore(meta)
//   cls.rooms                      Map code -> RoomHost (room.tokens = {Tropia: '4821', ...})
//   await cls.advance(code) / cls.advanceAll() / cls.pause() / cls.resume() / cls.setSettings({...})
//   cls.tick()                     call about twice a second (startTicker() does it in the browser)
//
// Progress modes (settings.mode):
//   'teacher'      only the teacher advances (students' "ready" is shown, nothing automatic)
//   'ready'        when every student country is ready, the room advances after a short countdown
//   'ready_timer'  as 'ready', and also when the phase time runs out
// settings.firstRoundTeacher: round 1 is always teacher-led (time to explain the screen).

import { rid, roomCode } from './transport.js';

export const ORIGINAL = ['Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia'];
export const DEFAULT_SETTINGS = {
  mode: 'ready_timer',
  firstRoundTeacher: true,
  countdownSec: 5,
  timer: { listing: 120, trading: 240, invest: 60 },
  advisor: 'normal', // 학생 화면 '마루 선장' 도움 수준: many | normal | alerts | off (advisor-ui.js)
  events: 'off',     // 세계 사건 카드(RULES_v1 §10): off | random. 수업을 만들 때 정하고 게임 중에는 바뀌지 않는다
};
const TEACHER_ONLY = new Set(['advance', 'set_controller']);
const KEEP_IDS = 300;
const CLASS_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

const pin = () => String(1000 + Math.floor(Math.random() * 9000));
const randomSeed = () => Math.floor(Math.random() * 1e9);
export const classCode = () => Array.from({ length: 5 }, () => CLASS_CHARS[Math.floor(Math.random() * CLASS_CHARS.length)]).join('');

export class RoomHost {
  constructor({ cls, code, transport }) {
    this.cls = cls;
    this.engine = cls.engine;
    this.code = code;
    this.transport = transport;
    this.chain = Promise.resolve();
    this.seq = 0;
    this.done = new Map();
    this.view = null; // teacher view of this room
    this.ready = new Set();
    this.deadline = null; // ms timestamp, or remaining ms while paused
    this.countdownAt = null;
    this.phaseKey = null;
  }

  // ---------------------------------------------------------------- lifecycle
  async create({ students, seed = randomSeed(), events = false }) {
    this.seed = seed;
    this.events = !!events; // world event cards (RULES_v1 §10), fixed for the whole game
    this.initialStudents = [...students];
    this.tokens = Object.fromEntries(students.map((n) => [n, pin()]));
    await this.engine.newSession(this.code, seed, students, this.events);
    await this._start();
  }

  async restore(saved) {
    this.seed = saved.seed;
    this.events = !!saved.events;
    this.initialStudents = saved.students;
    this.tokens = saved.tokens;
    for (const [id, r] of saved.done || []) this.done.set(id, r);
    await this.engine.replay(this.code, saved.seed, saved.students, saved.log, this.events);
    await this._start();
  }

  async _start() {
    await this.transport.hostStart({ onAction: (m) => this.studentAction(m) });
    await this._afterChange();
  }

  get storageKey() { return 'trade-room-' + this.code; }

  // ---------------------------------------------------------------- student and teacher actions
  studentAction({ id, country, token, action }) {
    if (id && this.done.has(id)) return Promise.resolve(this.done.get(id));
    const remember = (r) => {
      if (id) {
        this.done.set(id, r);
        if (this.done.size > KEEP_IDS) this.done.delete(this.done.keys().next().value);
      }
      return r;
    };
    if (!this.tokens || !country || this.tokens[country] === undefined || String(token) !== this.tokens[country]) {
      return Promise.resolve({ ok: false, msg: '방 코드, 나라 또는 접속 번호가 맞지 않아요.' });
    }
    if (!action || typeof action !== 'object') return Promise.resolve({ ok: false, msg: '잘못된 요청이에요.' });
    if (action.type === 'hello') {
      return this._queue(async () => { await this._publishOne(country); return { ok: true, msg: '접속했어요.' }; });
    }
    if (action.type === 'ready') {
      return this._queue(() => this._setReady(country, !!action.ready)).then(async (r) => {
        remember(r); await this._schedulePublish(); return r;
      });
    }
    if (TEACHER_ONLY.has(action.type)) return Promise.resolve({ ok: false, msg: '선생님만 할 수 있어요.' });
    return this._queue(() => this.engine.apply(this.code, { ...action, country })).then(async (r) => {
      remember(r); await this._schedulePublish(); return r;
    });
  }

  teacherAction(action) {
    return this._queue(async () => {
      const r = await this.engine.apply(this.code, action);
      if (r.ok && action.type === 'set_controller' && action.mode === 'student' && !this.tokens[action.country]) {
        this.tokens[action.country] = pin();
      }
      return r;
    }).then(async (r) => { await this._schedulePublish(); return r; });
  }

  advance(reason = 'teacher') {
    return this._queue(async () => {
      if (!this.view || this.view.phase === 'finished') return { ok: false, msg: '게임이 끝났어요.' };
      const r = await this.engine.apply(this.code, { type: 'advance' });
      if (r.ok) this.lastAdvance = { reason, at: this.cls.now() };
      return r;
    }).then(async (r) => { await this._schedulePublish(); return r; });
  }

  async _setReady(country, on) {
    if (!this.view || this.view.phase === 'finished') return { ok: false, msg: '게임이 끝났어요.' };
    if (on) this.ready.add(country); else this.ready.delete(country);
    this._checkReady();
    const need = this.required();
    return { ok: true, msg: on ? `준비 완료 (${need.filter((n) => this.ready.has(n)).length}/${need.length})` : '준비를 취소했어요.' };
  }

  // ---------------------------------------------------------------- phase timing
  required() { return this.view ? [...this.view.students] : []; }  // countries students run now

  mode() {
    const s = this.cls.settings;
    if (s.firstRoundTeacher && this.view && this.view.round === 1) return 'teacher';
    return s.mode;
  }

  _onPhase() {
    // called after every change; resets the timer state when the phase moved on
    const key = this.view ? `${this.view.round}:${this.view.phase}` : null;
    if (key === this.phaseKey) return;
    this.phaseKey = key;
    this.ready.clear();
    this.countdownAt = null;
    this.deadline = null;
    if (!this.view || this.view.phase === 'finished') return;
    const secs = this.cls.settings.timer[this.view.phase];
    if (this.mode() === 'ready_timer' && secs > 0) {
      this.deadline = this.cls.paused ? secs * 1000 : this.cls.now() + secs * 1000;
    }
  }

  _checkReady() {
    const need = this.required();
    const all = need.length > 0 && need.every((n) => this.ready.has(n));
    const auto = this.mode() !== 'teacher' && this.view && this.view.phase !== 'finished';
    if (all && auto) {
      if (this.countdownAt === null) {
        const ms = this.cls.settings.countdownSec * 1000;
        this.countdownAt = this.cls.paused ? ms : this.cls.now() + ms;
      }
    } else {
      this.countdownAt = null;
    }
  }

  // re-evaluate after settings change (mode or timer)
  recompute() {
    return this._queue(async () => {
      this.phaseKey = null; // force timer reset with the new settings, keep ready marks
      const kept = new Set(this.ready);
      this._onPhase();
      this.ready = kept;
      this._checkReady();
    }).then(() => this._schedulePublish());
  }

  freeze(now) {
    if (this.deadline !== null) this.deadline = Math.max(0, this.deadline - now);
    if (this.countdownAt !== null) this.countdownAt = Math.max(0, this.countdownAt - now);
  }

  thaw(now) {
    if (this.deadline !== null) this.deadline = now + this.deadline;
    if (this.countdownAt !== null) this.countdownAt = now + this.countdownAt;
  }

  tick(now) {
    if (this.cls.paused || !this.view || this.view.phase === 'finished' || this._ticking) return null;
    let reason = null;
    if (this.countdownAt !== null && now >= this.countdownAt) reason = 'ready';
    else if (this.deadline !== null && now >= this.deadline) reason = 'timer';
    if (!reason) return null;
    this.countdownAt = null; this.deadline = null;
    this._ticking = true;
    return this.advance(reason).finally(() => { this._ticking = false; });
  }

  info(now = this.cls.now()) {
    const paused = this.cls.paused;
    const left = (t) => (t === null ? null : Math.max(0, paused ? t : t - now));
    const need = this.required();
    return {
      code: this.code, mode: this.mode(), paused,
      ready: need.filter((n) => this.ready.has(n)), need,
      countdown_ms: left(this.countdownAt), deadline_ms: left(this.deadline),
      phase_seconds: this.cls.settings.timer[this.view ? this.view.phase : ''] || null,
      advisor: this.cls.settings.advisor,
    };
  }

  // ---------------------------------------------------------------- publishing and saving
  _queue(fn) {
    const p = this.chain.then(fn);
    this.chain = p.catch(() => {});
    return p;
  }

  _schedulePublish() {
    if (this._publishing) return this._publishing;
    this._publishing = this._queue(() => this._afterChange()).finally(() => { this._publishing = null; });
    return this._publishing;
  }

  async _afterChange() {
    const countries = Object.keys(this.tokens);
    const v = await this.engine.views(this.code, countries);
    this.view = v.teacher;
    this._onPhase();
    this._checkReady();
    this.seq += 1;
    const info = this.info();
    await Promise.all(countries.map((n) => this.transport.publish(n, JSON.stringify({ ...v.students[n], room: info }), this.seq)));
    await this._save();
    this.cls._changed();
  }

  republish() { return this._schedulePublish(); }

  async _publishOne(country) {
    const v = await this.engine.view(this.code, country);
    await this.transport.publish(country, JSON.stringify({ ...v, room: this.info() }), this.seq);
  }

  async _save() {
    if (!this.cls.storage) return;
    const log = await this.engine.log(this.code);
    this.cls.storage.set(this.storageKey, JSON.stringify({
      code: this.code, seed: this.seed, students: this.initialStudents, tokens: this.tokens, events: this.events,
      log, done: [...this.done.entries()].slice(-KEEP_IDS), saved: new Date().toISOString(),
    }));
  }

  async exportLog() {
    return { code: this.code, seed: this.seed, students: this.initialStudents, events: this.events, log: await this.engine.log(this.code) };
  }
}

export class ClassHost {
  constructor({ engine, server, storage = null, now = () => Date.now(), onChange = () => {} }) {
    this.engine = engine;
    this.server = server;
    this.storage = storage; // {get, set, remove, keys()} or null
    this.now = now;
    this.onChange = onChange;
    this.rooms = new Map();
    this.paused = false;
    this.online = [];
    this.settings = JSON.parse(JSON.stringify(DEFAULT_SETTINGS));
  }

  get storageKey() { return 'trade-class-' + this.cls; }

  async create({ students, rooms = 1, settings = {}, cls = classCode(), seeds = null }) {
    if (!students.length) throw new Error('학생 나라를 1개 이상 골라 주세요.');
    if (rooms < 1 || rooms > 20) throw new Error('방은 1~20개까지 만들 수 있어요.');
    this.cls = cls;
    this.serverId = this.server.info ? this.server.info.id : 'L';
    this.settings = mergeSettings(settings);
    this._saveMeta();
    for (let i = 1; i <= rooms; i++) {
      const code = roomCode(this.serverId, cls, i);
      const room = new RoomHost({ cls: this, code, transport: this.server.room(code) });
      await room.create({ students, seed: seeds ? seeds[i - 1] : undefined, events: this.settings.events === 'random' });
      this.rooms.set(code, room); // listed only once it has a state
    }
    this._joinPresence();
    this._saveMeta();
  }

  async restore(meta) {
    this.cls = meta.cls;
    this.serverId = meta.server;
    this.settings = mergeSettings(meta.settings);
    this.paused = !!meta.paused;
    for (const code of meta.rooms) {
      const saved = JSON.parse(this.storage.get('trade-room-' + code));
      const room = new RoomHost({ cls: this, code, transport: this.server.room(code) });
      await room.restore(saved);
      this.rooms.set(code, room);
    }
    this._joinPresence();
  }

  _joinPresence() {
    if (!this.server.presence) return;
    this.leave = this.server.presence.join({ role: 'host', room: this.cls, country: '' });
    this.unwatch = this.server.presence.watch((entries) => {
      const key = JSON.stringify(entries.map((e) => [e.role, e.room, e.country]).sort());
      if (key === this._onlineKey) return; // heartbeats without a change do not redraw
      this._onlineKey = key; this.online = entries; this._changed();
    });
  }

  _saveMeta() {
    if (!this.storage) return;
    this.storage.set(this.storageKey, JSON.stringify({
      cls: this.cls, server: this.serverId, settings: this.settings, paused: this.paused,
      rooms: [...this.rooms.keys()], saved: new Date().toISOString(),
    }));
  }

  // ---------------------------------------------------------------- controls
  room(code) {
    const r = this.rooms.get(code);
    if (!r) throw new Error('없는 방이에요: ' + code);
    return r;
  }

  advance(code) { return this.room(code).advance('teacher'); }

  async advanceAll() {
    const out = {};
    for (const [code, r] of this.rooms) {
      if (r.view && r.view.phase !== 'finished') out[code] = await r.advance('teacher');
    }
    return out;
  }

  teacherAction(code, action) { return this.room(code).teacherAction(action); }

  pause() {
    if (this.paused) return;
    const now = this.now();
    for (const r of this.rooms.values()) r.freeze(now);
    this.paused = true;
    this._saveMeta();
    return Promise.all([...this.rooms.values()].map((r) => r.republish()));
  }

  resume() {
    if (!this.paused) return;
    const now = this.now();
    for (const r of this.rooms.values()) r.thaw(now);
    this.paused = false;
    this._saveMeta();
    return Promise.all([...this.rooms.values()].map((r) => r.republish()));
  }

  async setSettings(patch) {
    this.settings = mergeSettings({ ...this.settings, ...patch, timer: { ...this.settings.timer, ...(patch.timer || {}) } });
    this._saveMeta();
    await Promise.all([...this.rooms.values()].map((r) => r.recompute()));
  }

  tick() {
    const now = this.now();
    const ps = [];
    for (const r of this.rooms.values()) { const p = r.tick(now); if (p) ps.push(p); }
    return Promise.all(ps);
  }

  startTicker(ms = 500) {
    this.stopTicker();
    this._ticker = setInterval(() => { this.tick(); }, ms);
  }

  stopTicker() { if (this._ticker) clearInterval(this._ticker); this._ticker = null; }

  // ---------------------------------------------------------------- views
  _changed() {
    if (this._changeTimer) return;
    this._changeTimer = setTimeout(() => { this._changeTimer = null; this.onChange(this.summary(), this); }, 50);
  }

  onlineIn(code) {
    return this.online.filter((e) => e.role === 'student' && e.room === code);
  }

  summary() {
    const now = this.now();
    return {
      cls: this.cls, server: this.serverId, settings: this.settings, paused: this.paused,
      server_online: this.online.length,
      rooms: [...this.rooms.values()].filter((r) => r.view).map((r) => ({
        code: r.code, view: r.view, info: r.info(now), tokens: r.tokens,
        online: this.onlineIn(r.code).map((e) => e.country),
      })),
    };
  }

  async finish({ clearServer = true, forget = false } = {}) {
    this.stopTicker();
    for (const r of this.rooms.values()) {
      if (clearServer && r.transport.clear) await r.transport.clear();
      r.transport.close();
      await this.engine.drop(r.code);
      if (forget && this.storage) this.storage.remove(r.storageKey);
    }
    if (forget && this.storage) this.storage.remove(this.storageKey);
    if (this.leave) this.leave();
    if (this.unwatch) this.unwatch();
  }
}

function mergeSettings(s = {}) {
  const d = DEFAULT_SETTINGS;
  const mode = ['teacher', 'ready', 'ready_timer'].includes(s.mode) ? s.mode : d.mode;
  const t = { ...d.timer, ...(s.timer || {}) };
  for (const k of Object.keys(t)) t[k] = Math.max(0, Math.min(1800, Math.round(Number(t[k]) || 0)));
  const advisor = ['many', 'normal', 'alerts', 'off'].includes(s.advisor) ? s.advisor : d.advisor;
  const events = ['off', 'random'].includes(s.events) ? s.events : d.events;
  return {
    mode, timer: t, advisor, events,
    firstRoundTeacher: s.firstRoundTeacher === undefined ? d.firstRoundTeacher : !!s.firstRoundTeacher,
    countdownSec: Math.max(0, Math.min(30, Math.round(Number(s.countdownSec ?? d.countdownSec)))),
  };
}

export function savedClasses(storage) {
  const out = [];
  for (const k of storage.keys()) {
    if (!k.startsWith('trade-class-')) continue;
    try { out.push(JSON.parse(storage.get(k))); } catch (e) { /* ignore */ }
  }
  return out.sort((a, b) => String(b.saved).localeCompare(String(a.saved)));
}

export const browserStorage = {
  get: (k) => localStorage.getItem(k),
  set: (k, v) => localStorage.setItem(k, v),
  remove: (k) => localStorage.removeItem(k),
  keys: () => Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i)),
};

export { rid };
