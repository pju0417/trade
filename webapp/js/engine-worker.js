// Web Worker that owns the Python engine, so the teacher page stays responsive.
// Pyodide is loaded from ../vendor/pyodide/ if present, otherwise from the jsDelivr CDN.
import { createEngine } from './engine-core.js';

const PYODIDE_VERSION = '0.27.7';
const SOURCES = [
  new URL('../vendor/pyodide/', import.meta.url).href,
  `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`,
];
let engine = null;

async function loadPyodideModule() {
  const errors = [];
  for (const base of SOURCES) {
    try {
      const mod = await import(base + 'pyodide.mjs');
      return { loadPyodide: mod.loadPyodide, indexURL: base };
    } catch (e) {
      errors.push(`${base}: ${e && e.message}`);
    }
  }
  throw new Error('Pyodide를 불러오지 못했어요. ' + errors.join(' | '));
}

self.onmessage = async ({ data }) => {
  const { id, cmd, args } = data;
  try {
    let result;
    if (cmd === 'init') {
      const { loadPyodide, indexURL } = await loadPyodideModule();
      const res = await fetch(new URL('../engine_bundle.json', import.meta.url));
      if (!res.ok) throw new Error('engine_bundle.json을 불러오지 못했어요.');
      const bundle = await res.json();
      engine = await createEngine({ loadPyodide, bundle, indexURL });
      result = { python: engine.pythonVersion(), pyodide: indexURL, files: Object.keys(bundle.files).length };
    } else {
      if (!engine) throw new Error('엔진이 아직 준비되지 않았어요.');
      if (typeof engine[cmd] !== 'function') throw new Error('unknown command ' + cmd);
      result = engine[cmd](...(args || []));
    }
    self.postMessage({ id, ok: true, result });
  } catch (e) {
    self.postMessage({ id, ok: false, error: String((e && e.message) || e) });
  }
};
