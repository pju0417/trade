// Message layer between the teacher's host page and the student pages.
//
// A "server" is one Firebase project (one Realtime Database, max 100 simultaneous connections on
// the free plan). A page opens ONE connection per server and talks to many rooms through it.
//
//   const server = await openServer(serverId)         // '1', '2', ... from config.js, or 'L' (local)
//   const t = server.room('2-K7QPM-1')                // room-scoped transport
//   Host side:    await t.hostStart({ onAction })      onAction({id, country, token, action}) -> Promise<result>
//                 await t.publish(country, json, seq)  latest state of one country (JSON string)
//   Student side: await t.studentStart(country, onState)
//                 await t.send(country, token, action) -> result (rejects on timeout)
//   Presence:     const leave = server.presence.join({ role, room, country })
//                 const stop = server.presence.watch((entries) => ...)   entries: [{role, room, country}]
//
// Kinds: LocalServer (same browser, BroadcastChannel), MemoryHub().server() (tests),
//        FirebaseServer (Realtime Database). countOnline(info) reads a server's head count
//        without opening a lasting connection (REST, for the lobby).
import { SERVERS } from './config.js';

const TIMEOUT_MS = 20000;
const HEARTBEAT_MS = 3000;
const STALE_MS = 9000;
export const rid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

function withTimeout(promise, ms, onTimeout) {
  let timer;
  return Promise.race([
    promise.finally(() => clearTimeout(timer)),
    new Promise((_, reject) => {
      timer = setTimeout(() => { onTimeout && onTimeout(); reject(new Error('선생님 화면의 응답이 없어요. 잠시 후 다시 해 보세요.')); }, ms);
    }),
  ]);
}

// ---------------------------------------------------------------- room codes
// "<server>-<CLASS>-<room>", e.g. "2-K7QPM-1". Local test mode uses server "L".
export function parseRoomCode(code) {
  const m = /^([0-9]+|L)-([A-Z0-9]{3,8})-([0-9]{1,2})$/.exec(String(code || '').trim().toUpperCase());
  if (!m) return null;
  return { server: m[1], cls: m[2], room: Number(m[3]), code: `${m[1]}-${m[2]}-${Number(m[3])}` };
}
export const roomCode = (server, cls, n) => `${server}-${cls}-${n}`;

export function serverList() {
  if (!SERVERS || !SERVERS.length) return [{ id: 'L', name: '로컬 시험(같은 브라우저)', capacity: 90, local: true }];
  return SERVERS.map((s, i) => ({ id: String(i + 1), name: s.name || `${i + 1}서버`, capacity: s.capacity || 90, firebase: s.firebase }));
}

// ---------------------------------------------------------------- message-based rooms (local, memory)
class MessageRoom {
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

  async hostStart({ onAction }) { this.role = 'host'; this.onAction = onAction; }

  async publish(country, json, seq) {
    this.last[country] = { json, seq };
    this.post({ k: 'state', country, json, seq });
  }

  async studentStart(country, onState) {
    this.role = 'student'; this.country = country; this.onState = onState;
    this.post({ k: 'hello', country });
  }

  send(country, token, action) {
    const id = rid();
    const p = new Promise((resolve) => this.pending.set(id, resolve));
    this.post({ k: 'action', id, country, token, action });
    return withTimeout(p, TIMEOUT_MS, () => this.pending.delete(id));
  }

  async clear() {}
  close() { this.closed = true; }
}

// Presence over a broadcast medium: every member re-announces itself every few seconds.
class BroadcastPresence {
  constructor(post) {
    this.post = post;
    this.seen = new Map(); // id -> {info, at}
    this.mine = new Map();
    this.watchers = new Set();
    this.timer = null;
  }
  receive(msg) {
    if (msg.k === 'presence') { this.seen.set(msg.id, { info: msg.info, at: Date.now() }); this._emit(); }
    if (msg.k === 'presence-leave') { this.seen.delete(msg.id); this._emit(); }
  }
  _beat() { for (const [id, info] of this.mine) this.post({ k: 'presence', id, info }); }
  _ensureTimer() {
    if (this.timer) return;
    this.timer = setInterval(() => { this._beat(); this._emit(); }, HEARTBEAT_MS);
    if (this.timer.unref) this.timer.unref();
  }
  join(info) {
    const id = rid();
    this.mine.set(id, info);
    this.seen.set(id, { info, at: Date.now() });
    this._ensureTimer(); this._beat(); this._emit();
    return () => { this.mine.delete(id); this.seen.delete(id); this.post({ k: 'presence-leave', id }); this._emit(); };
  }
  list() {
    const now = Date.now();
    for (const [id, v] of this.seen) if (!this.mine.has(id) && now - v.at > STALE_MS) this.seen.delete(id);
    return [...this.seen.values()].map((v) => v.info);
  }
  _emit() { const l = this.list(); for (const w of this.watchers) w(l); }
  watch(fn) { this.watchers.add(fn); this._ensureTimer(); fn(this.list()); return () => this.watchers.delete(fn); }
  close() {
    for (const id of [...this.mine.keys()]) this.post({ k: 'presence-leave', id });
    this.mine.clear(); clearInterval(this.timer); this.timer = null;
  }
}

class BroadcastServer {
  constructor(makeChannel) {
    this.makeChannel = makeChannel;
    const pc = makeChannel('presence', (m) => this.presence.receive(m));
    this.presence = new BroadcastPresence((m) => pc.post(m));
    this.channels = [pc];
  }
  room(code) {
    let r;
    const ch = this.makeChannel('room-' + code, (m) => r.receive(m));
    this.channels.push(ch);
    r = new MessageRoom((m) => ch.post(m));
    r.close = () => { r.closed = true; ch.close(); };
    return r;
  }
  close() { this.presence.close(); for (const c of this.channels) c.close(); }
}

export class LocalServer extends BroadcastServer {
  constructor() {
    super((name, onMsg) => {
      const bc = new BroadcastChannel('trade-game-' + name);
      bc.onmessage = (e) => onMsg(e.data);
      return { post: (m) => bc.postMessage(m), close: () => bc.close() };
    });
  }
}

// In-process hub for automated tests: every server() from the same hub sees the others.
export class MemoryHub {
  constructor() { this.channels = new Map(); }
  server() {
    const hub = this;
    return new BroadcastServer((name, onMsg) => {
      if (!hub.channels.has(name)) hub.channels.set(name, new Set());
      const set = hub.channels.get(name);
      const me = { onMsg };
      set.add(me);
      return {
        post: (m) => { const copy = JSON.parse(JSON.stringify(m)); for (const o of set) if (o !== me) setTimeout(() => o.onMsg(copy), 0); },
        close: () => set.delete(me),
      };
    });
  }
}

// ---------------------------------------------------------------- Firebase Realtime Database
// Layout:
//   presence/{id}                {role, room, country}    removed by the database when the page disconnects
//   rooms/{room}/state/{country} {json, seq}              written by the host only
//   rooms/{room}/actions/{id}    {country, token, action} pushed by students, removed by the host
//   rooms/{room}/results/{id}    {json}                   written by the host, removed by the student
const FIREBASE_VERSION = '10.12.2';

class FirebaseRoom {
  constructor(server, code) { this.s = server; this.code = code; this.unsubs = []; }
  ref(path) { return this.s.fb.ref(this.s.db, `rooms/${this.code}${path ? '/' + path : ''}`); }

  async hostStart({ onAction }) {
    const { onChildAdded, set, remove } = this.s.fb;
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

  async publish(country, json, seq) { await this.s.fb.set(this.ref('state/' + country), { json, seq }); }

  async studentStart(country, onState) {
    let seen = -1;
    this.unsubs.push(this.s.fb.onValue(this.ref('state/' + country), (snap) => {
      const v = snap.val();
      if (v && v.seq >= seen) { seen = v.seq; onState(v.json); }
    }));
  }

  async send(country, token, action) {
    const { push, set, onValue, remove } = this.s.fb;
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

  async clear() { await this.s.fb.remove(this.ref('')); }
  close() { for (const u of this.unsubs) u(); this.unsubs = []; }
}

class FirebasePresence {
  constructor(server) { this.s = server; this.joined = new Map(); this.unsubs = []; }
  join(info) {
    const { ref, push, set, onValue, onDisconnect, remove } = this.s.fb;
    const me = push(ref(this.s.db, 'presence'));
    const clean = { role: info.role || '', room: info.room || '', country: info.country || '' };
    const off = onValue(ref(this.s.db, '.info/connected'), (snap) => {
      if (snap.val() === true) onDisconnect(me).remove().then(() => set(me, clean));
    });
    this.joined.set(me.key, { me, off });
    return () => { off(); remove(me); this.joined.delete(me.key); };
  }
  watch(fn) {
    const off = this.s.fb.onValue(this.s.fb.ref(this.s.db, 'presence'), (snap) => fn(Object.values(snap.val() || {})));
    this.unsubs.push(off);
    return off;
  }
  close() { for (const { off } of this.joined.values()) off(); for (const u of this.unsubs) u(); }
}

export class FirebaseServer {
  static async create(config, modules = null) {
    const base = `https://www.gstatic.com/firebasejs/${FIREBASE_VERSION}/`;
    const app = modules ? modules.app : await import(base + 'firebase-app.js');
    const db = modules ? modules.database : await import(base + 'firebase-database.js');
    const s = new FirebaseServer();
    s.fb = db;
    s.app = app.initializeApp(config, 'trade-' + rid());
    s.db = db.getDatabase(s.app);
    s.presence = new FirebasePresence(s);
    s.rooms = [];
    return s;
  }
  room(code) { const r = new FirebaseRoom(this, code); this.rooms.push(r); return r; }
  close() {
    this.presence.close();
    for (const r of this.rooms) r.close();
    if (this.fb.goOffline) this.fb.goOffline(this.db);
  }
}

// ---------------------------------------------------------------- helpers
const opened = new Map();
export async function openServer(id) {
  const key = String(id).toUpperCase();
  if (opened.has(key)) return opened.get(key);
  const info = serverList().find((s) => s.id === key);
  if (!info) throw new Error('없는 서버예요: ' + id);
  const s = info.local ? new LocalServer() : await FirebaseServer.create(info.firebase);
  s.info = info;
  opened.set(key, s);
  return s;
}

// Head count of a server without holding a connection (lobby): REST read of presence keys.
export async function countOnline(info, fetchFn = (typeof fetch !== 'undefined' ? fetch : null)) {
  if (info.local) {
    const s = await openServer(info.id);
    return s.presence.list().length;
  }
  const url = info.firebase.databaseURL.replace(/\/$/, '') + '/presence.json?shallow=true';
  const res = await fetchFn(url);
  if (!res.ok) throw new Error('접속 인원을 읽지 못했어요 (' + res.status + ')');
  const v = await res.json();
  return v ? Object.keys(v).length : 0;
}
