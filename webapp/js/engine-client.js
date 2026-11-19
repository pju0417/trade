// Main-thread handle to the engine worker. Every method returns a Promise.
export class EngineClient {
  constructor(workerUrl = new URL('./engine-worker.js', import.meta.url)) {
    this.worker = new Worker(workerUrl, { type: 'module' });
    this.seq = 0;
    this.waiting = new Map();
    this.worker.onmessage = ({ data }) => {
      const p = this.waiting.get(data.id);
      if (!p) return;
      this.waiting.delete(data.id);
      data.ok ? p.resolve(data.result) : p.reject(new Error(data.error));
    };
    this.worker.onerror = (e) => {
      for (const p of this.waiting.values()) p.reject(new Error(e.message || 'worker error'));
      this.waiting.clear();
    };
  }

  call(cmd, ...args) {
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      this.worker.postMessage({ id, cmd, args });
    });
  }

  init() { return this.call('init'); }
  newSession(seed, students) { return this.call('newSession', seed, students); }
  replay(seed, students, log) { return this.call('replay', seed, students, log); }
  apply(action) { return this.call('apply', action); }
  view(country) { return this.call('view', country); }
  teacher() { return this.call('teacher'); }
  views(countries) { return this.call('views', countries); }
  log() { return this.call('log'); }
  meta() { return this.call('meta'); }
}
