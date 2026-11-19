// Replays CPython golden games in Pyodide (Node) through engine-core.js and compares every view.
// Usage: node node_crosscheck.mjs golden.json   (needs: npm install pyodide@0.27.7 in NODE_PATH dir)
import fs from 'fs';
import { createEngine } from '../js/engine-core.js';
const { loadPyodide } = await import(process.env.PYODIDE_MODULE || 'pyodide');

const stable = (v) => JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x))
  ? Object.fromEntries(Object.keys(x).sort().map((key) => [key, x[key]])) : x);
const bundle = JSON.parse(fs.readFileSync(new URL('../engine_bundle.json', import.meta.url)));
const games = JSON.parse(fs.readFileSync(process.argv[2]));
const t0 = Date.now();
const engine = await createEngine({ loadPyodide, bundle });
console.log('python', engine.pythonVersion().split(' ')[0], 'boot ms', Date.now() - t0);
let checked = 0;
for (const g of games) {
  const t = Date.now();
  // mid-game: replay the prefix of the log
  engine.replay(g.seed, g.students, g.log.slice(0, g.mid.log_len));
  for (const n of g.students) if (stable(engine.view(n)) !== stable(g.mid.views[n])) throw new Error(`mid view ${g.seed} ${n}`);
  if (stable(engine.teacher()) !== stable(g.mid.teacher)) throw new Error(`mid teacher ${g.seed}`);
  // full game: new session and apply one action at a time (as the host does)
  engine.newSession(g.seed, g.students);
  for (const a of g.log) engine.apply(a);
  for (const n of g.students) if (stable(engine.view(n)) !== stable(g.final.views[n])) throw new Error(`final view ${g.seed} ${n}`);
  if (stable(engine.teacher()) !== stable(g.final.teacher)) throw new Error(`final teacher ${g.seed}`);
  if (stable(engine.log()) !== stable(g.log)) throw new Error(`log ${g.seed}`);
  checked++;
  console.log('seed', g.seed, 'students', g.students.length, 'actions', g.log.length, 'ms', Date.now() - t);
}
console.log(`crosscheck ok: ${checked} games identical in Pyodide`);
