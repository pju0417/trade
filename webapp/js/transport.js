// Message layer between the teacher's host page and the student pages.
//
//   LocalTransport     same browser, other tabs (BroadcastChannel). For testing and demos.
//   FirebaseTransport  Firebase Realtime Database. For students on their own devices.
//   MemoryHub          in-process hub for automated tests (Node).
//
// Host side:    await t.hostStart({ onAction })        onAction({id, country, token, action}) -> Promise<result>
//               await t.publish(country, json, seq)    latest state of one country (JSON string)
// Student side: await t.studentStart(country, onState) onState(json) on every new state
//               await t.send(country, token, action)   -> result (rejects on timeout)

const TIMEOUT_MS = 20000;
const rid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

function withTimeout(promise, ms, onTimeout) {
  let timer;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => {
      timer = setTimeout(() => { onTimeout && onTimeout(); reject(new Error('선생님 화면의 응답이 없어요. 잠시 후 다시 해 보세요.')); }, ms);
    }),
  ]);
}

// ---------------------------------------------------------------- shared message logic
class MessageTransport {
  constructor(post) {
    this.post = post;
    this.pending = new Map();
    this.last = {};
    this.role = null;
  }

  receive(msg) {
    if (!msg || typeof msg !== 'object') return;
    if (this.role === 'host') {
      if (msg.k === 'action') {
        Promise.resolve(this.onAction({ id: msg.id, country: msg.country, token: msg.token, action: msg.action }))
          .then((result) => this.post({ k: 'result', id: msg.id, result }))
          .catch((e) => this.post({ k: 'result', id: msg.id, result: { ok: false, msg: String(e.message || e) } }));
      } else if (msg.k === 'hello' && this.last[msg.country]) {
        this.post({ k: 'state', country: msg.country, ...this.last[msg.country] });
      }
    } else if (this.role === 'student') {
      if (msg.k === 'state' && msg.country === this.country) {
        if (this.seq === undefined || msg.seq >= this.seq) {
          this.seq = msg.seq;
          this.onState(msg.json);
        }
      } else if (msg.k === 'result' && this.pending.has(msg.id)) {
        this.pending.get(msg.id)(msg.result);
        this.pending.delete(msg.id);
      }
    }
  }

  async hostStart({ onAction }) {
    this.role = 'host';
    this.onAction = onAction;
  }

  async publish(country, json, seq) {
    this.last[country] = { json, seq };
    this.post({ k: 'state', country, json, seq });
  }

  async studentStart(country, onState) {
    this.role = 'student';
    this.country = country;
    this.onState = onState;
    this.post({ k: 'hello', country });
  }

  send(country, token, action) {
    const id = rid();
    const p = new Promise((resolve) => this.pending.set(id, resolve));
    this.post({ k: 'action', id, country, token, action });
    return withTimeout(p, TIMEOUT_MS, () => this.pending.delete(id));
  }

  close() {}
}

export class LocalTransport extends MessageTransport {
  constructor(room) {
    const ch = new BroadcastChannel('trade-game-' + room);
    super((m) => ch.postMessage(m));
    this.ch = ch;
    ch.onmessage = (e) => this.receive(e.data);
  }
  close() { this.ch.close(); }
}

export class MemoryHub {
  constructor() { this.members = new Set(); }
  connect() {
    const hub = this;
    const t = new MessageTransport((m) => {
      const copy = JSON.parse(JSON.stringify(m));
      for (const other of hub.members) if (other !== t) setTimeout(() => other.receive(copy), 0);
    });
    hub.members.add(t);
    return t;
  }
}

// ---------------------------------------------------------------- Firebase Realtime Database
// Layout under rooms/{room}:
//   state/{country}  {json, seq}               written by the host only
//   actions/{id}     {country, token, action}  pushed by students, removed by the host
//   results/{id}     {json}                    written by the host, removed by the student
const FIREBASE_VERSION = '10.12.2';

export class FirebaseTransport {
  static async create(config, room, modules = null) {
    const base = `https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/`;
    const app = modules ? modules.app : await import(base + 'firebase-app.js');
    const db = modules ? modules.database : await import(base + 'firebase-database.js');
    const t = new FirebaseTransport();
    t.fb = db;
    t.app = app.initializeApp(config, 'trade-' + room + '-' + rid());
    t.db = db.getDatabase(t.app);
    t.room = room;
    t.unsubs = [];
    return t;
  }

  ref(path) { return this.fb.ref(this.db, `rooms/${this.room}/${path}`); }

  async hostStart({ onAction }) {
    const { onChildAdded, set, remove } = this.fb;
    this.unsubs.push(onChildAdded(this.ref('actions'), (snap) => {
      const v = snap.val() || {};
      let action = null;
      try { action = JSON.parse(v.action); } catch (e) { /* malformed */ }
      Promise.resolve(onAction({ id: snap.key, country: v.country, token: v.token, action }))
        .catch((e) => ({ ok: false, msg: String(e.message || e) }))
        .then((result) => set(this.ref('results/' + snap.key), { json: JSON.stringify(result) }))
        .then(() => remove(snap.ref));
    }));
  }

  async publish(country, json, seq) {
    await this.fb.set(this.ref('state/' + country), { json, seq });
  }

  async studentStart(country, onState) {
    let seen = -1;
    this.unsubs.push(this.fb.onValue(this.ref('state/' + country), (snap) => {
      const v = snap.val();
      if (v && v.seq >= seen) { seen = v.seq; onState(v.json); }
    }));
  }

  async send(country, token, action) {
    const { push, set, onValue, remove } = this.fb;
    const r = push(this.ref('actions'));
    let off = null;
    const p = new Promise((resolve) => {
      off = onValue(this.ref('results/' + r.key), (snap) => {
        const v = snap.val();
        if (!v) return;
        off && off();
        remove(snap.ref);
        resolve(JSON.parse(v.json));
      });
    });
    await set(r, { country, token: String(token), action: JSON.stringify(action) });
    return withTimeout(p, TIMEOUT_MS, () => off && off());
  }

  close() { for (const u of this.unsubs) u(); }
}

export async function makeTransport(room, firebaseConfig) {
  if (firebaseConfig) return FirebaseTransport.create(firebaseConfig, room);
  return new LocalTransport(room);
}
