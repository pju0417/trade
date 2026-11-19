// Runs the validated Python engine (webapp/engine_bundle.json) inside Pyodide.
// Works in a browser Web Worker and in Node (tests). No UI code here.
//
//   const engine = await createEngine({ loadPyodide, bundle, indexURL })
//   engine.newSession(seed, students)      -> {ok}
//   engine.replay(seed, students, log)     -> {ok}
//   engine.apply(action)                   -> {ok, msg, ...}
//   engine.view(country) / engine.teacher() / engine.views([countries]) / engine.log()

const BOOT = `
import sys, types, json
sys.dont_write_bytecode = True
# The engine's batch runner imports a process pool at module level; browsers have no processes.
_p = types.ModuleType('concurrent.futures.process')
class ProcessPoolExecutor:
    def __init__(self, *a, **k):
        raise RuntimeError('no process pool in the browser')
_p.ProcessPoolExecutor = ProcessPoolExecutor
sys.modules['concurrent.futures.process'] = _p
for _d in reversed(ENTRY_PATHS):
    sys.path.insert(0, '/trade/' + _d)
import importlib
C = importlib.import_module(ENTRY_MODULE)
_S = None

def _call(fn, arg):
    global _S
    a = json.loads(arg)
    if fn == 'new':
        _S = C.Session(a['seed'], a['students'])
        return json.dumps({'ok': True})
    if fn == 'replay':
        _S = C.Session.replay(a['seed'], a['students'], a['log'])
        return json.dumps({'ok': True})
    if _S is None:
        return json.dumps({'ok': False, 'msg': 'no session'})
    if fn == 'apply':
        return json.dumps(_S.apply(a), ensure_ascii=False)
    if fn == 'view':
        return json.dumps(_S.view(a), ensure_ascii=False)
    if fn == 'teacher':
        return json.dumps(_S.teacher_view(), ensure_ascii=False)
    if fn == 'views':
        return json.dumps({'teacher': _S.teacher_view(),
                           'students': {n: _S.view(n) for n in a}}, ensure_ascii=False)
    if fn == 'log':
        return json.dumps(_S.log, ensure_ascii=False)
    if fn == 'meta':
        return json.dumps({'seed': _S.seed, 'initial_students': _S.initial_students,
                           'students': sorted(_S.g.students), 'round': _S.g.r, 'phase': _S.phase})
    raise ValueError('unknown call ' + fn)
`;

function dirname(p) {
  return p.slice(0, p.lastIndexOf('/'));
}

export async function createEngine({ loadPyodide, bundle, indexURL }) {
  const py = await loadPyodide(indexURL ? { indexURL } : {});
  for (const [path, text] of Object.entries(bundle.files)) {
    const full = '/trade/' + path;
    py.FS.mkdirTree(dirname(full));
    py.FS.writeFile(full, text);
  }
  py.globals.set('ENTRY_PATHS', py.toPy(bundle.entry.paths));
  py.globals.set('ENTRY_MODULE', bundle.entry.module);
  py.runPython(BOOT);
  const fn = py.globals.get('_call');
  const call = (name, arg) => JSON.parse(fn(name, JSON.stringify(arg === undefined ? null : arg)));
  return {
    newSession: (seed, students) => call('new', { seed, students }),
    replay: (seed, students, log) => call('replay', { seed, students, log }),
    apply: (action) => call('apply', action),
    view: (country) => call('view', country),
    teacher: () => call('teacher'),
    views: (countries) => call('views', countries),
    log: () => call('log'),
    meta: () => call('meta'),
    pythonVersion: () => py.runPython('import sys; sys.version'),
  };
}
