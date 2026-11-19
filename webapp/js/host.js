// Teacher-side controller: owns the engine, checks each student's PIN, applies actions one at a
// time, publishes every student's state, and saves the action log so the game can be resumed
// (the engine is deterministic: seed + students + log reproduce the game exactly).
//
//   const host = new HostController({ engine, transport, room, storage, onChange })
//   await host.newGame({ students: ['Tropia', 'Mechania', 'Mineria'] })   // or host.resume(saved)
//   await host.teacherAction({ type: 'advance' })
//   host.tokens  -> { Tropia: '4821', ... }   (show these to the students)

export const ORIGINAL = ['Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia'];
const TEACHER_ONLY = new Set(['advance', 'set_controller']);
const KEEP_IDS = 500;

const pin = () => String(1000 + Math.floor(Math.random() * 9000));
const randomSeed = () => Math.floor(Math.random() * 1e9);

export class HostController {
  constructor({ engine, transport, room, storage = null, onChange = () => {} }) {
    this.engine = engine;
    this.transport = transport;
    this.room = room;
    this.storage = storage; // { get(key), set(key, value), remove(key) } or null
    this.onChange = onChange;
    this.chain = Promise.resolve();
    this.seq = 0;
    this.done = new Map(); // action id -> result (duplicate deliveries)
    this.teacherView = null;
  }

  get storageKey() { return 'trade-game-host-' + this.room; }

  async newGame({ students, seed = randomSeed() }) {
    if (!students.length) throw new Error('학생 나라를 1개 이상 골라 주세요.');
    this.seed = seed;
    this.initialStudents = [...students];
    this.tokens = Object.fromEntries(students.map((n) => [n, pin()]));
    await this.engine.newSession(seed, students);
    await this._start();
  }

  async resume(saved) {
    this.seed = saved.seed;
    this.initialStudents = saved.students;
    this.tokens = saved.tokens;
    for (const [id, r] of saved.done || []) this.done.set(id, r);
    await this.engine.replay(saved.seed, saved.students, saved.log);
    await this._start();
  }

  loadSaved() {
    if (!this.storage) return null;
    const raw = this.storage.get(this.storageKey);
    return raw ? JSON.parse(raw) : null;
  }

  async _start() {
    await this.transport.hostStart({ onAction: (m) => this.studentAction(m) });
    await this._afterChange();
  }

  // ---------------------------------------------------------------- actions
  studentAction({ id, country, token, action }) {
    if (id && this.done.has(id)) return Promise.resolve(this.done.get(id));
    const finish = (result) => {
      if (id) {
        this.done.set(id, result);
        if (this.done.size > KEEP_IDS) this.done.delete(this.done.keys().next().value);
      }
      return result;
    };
    if (!this.tokens || !country || this.tokens[country] === undefined || String(token) !== this.tokens[country]) {
      return Promise.resolve({ ok: false, msg: '나라 또는 접속 번호가 맞지 않아요.' });
    }
    if (!action || typeof action !== 'object') return Promise.resolve({ ok: false, msg: '잘못된 요청이에요.' });
    if (action.type === 'hello') {
      return this._queue(async () => {
        await this._publishOne(country);
        return { ok: true, msg: '접속했어요.' };
      });
    }
    if (TEACHER_ONLY.has(action.type)) return Promise.resolve({ ok: false, msg: '선생님만 할 수 있어요.' });
    return this._queue(() => this.engine.apply({ ...action, country })).then(async (r) => {
      finish(r);
      await this._schedulePublish();
      return r;
    });
  }

  teacherAction(action) {
    return this._queue(async () => {
      const r = await this.engine.apply(action);
      if (r.ok && action.type === 'set_controller' && action.mode === 'student' && !this.tokens[action.country]) {
        this.tokens[action.country] = pin();
      }
      return r;
    }).then(async (r) => {
      await this._schedulePublish();
      return r;
    });
  }

  _queue(fn) {
    const p = this.chain.then(fn);
    this.chain = p.catch(() => {});
    return p;
  }

  // ---------------------------------------------------------------- publishing and saving
  _schedulePublish() {
    if (this._publishing) return this._publishing;
    this._publishing = this._queue(() => this._afterChange()).finally(() => { this._publishing = null; });
    return this._publishing;
  }

  async _afterChange() {
    const countries = Object.keys(this.tokens);
    const v = await this.engine.views(countries);
    this.seq += 1;
    await Promise.all(countries.map((n) => this.transport.publish(n, JSON.stringify(v.students[n]), this.seq)));
    this.teacherView = v.teacher;
    await this._save();
    this.onChange(v.teacher, this);
  }

  async _publishOne(country) {
    const v = await this.engine.view(country);
    await this.transport.publish(country, JSON.stringify(v), this.seq);
  }

  async _save() {
    if (!this.storage) return;
    const log = await this.engine.log();
    this.storage.set(this.storageKey, JSON.stringify({
      room: this.room, seed: this.seed, students: this.initialStudents, tokens: this.tokens,
      log, done: [...this.done.entries()].slice(-KEEP_IDS), saved: new Date().toISOString(),
    }));
  }

  async exportLog() {
    return { room: this.room, seed: this.seed, students: this.initialStudents, log: await this.engine.log() };
  }
}

export const browserStorage = {
  get: (k) => localStorage.getItem(k),
  set: (k, v) => localStorage.setItem(k, v),
  remove: (k) => localStorage.removeItem(k),
};
