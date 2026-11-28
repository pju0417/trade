// Runs the validated Python engine (webapp/engine_bundle.json) inside Pyodide.
// Works in a browser Web Worker and in Node (tests). No UI code here.
//
// One engine holds many independent games, one per room code (separate seed, market and AI).
//
//   const engine = await createEngine({ loadPyodide, bundle, indexURL })
//   engine.newSession(room, seed, students, events=false)      -> {ok}   events = world event cards (RULES_v1 §10)
//   engine.replay(room, seed, students, log, events=false)     -> {ok}
//   engine.apply(room, action)                   -> {ok, msg, ...}
//   engine.view(room, country) / engine.teacher(room) / engine.views(room, [countries])
//   engine.log(room) / engine.drop(room) / engine.rooms()

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
_SESS = {}

def _call(fn, arg):
    a = json.loads(arg)
    if fn == 'rooms':
        return json.dumps(sorted(_SESS))
    room = a['room']
    if fn == 'new':
        _SESS[room] = C.Session(a['seed'], a['students'], a.get('events', False))
        return json.dumps({'ok': True})
    if fn == 'replay':
        _SESS[room] = C.Session.replay(a['seed'], a['students'], a['log'], a.get('events', False))
        return json.dumps({'ok': True})
    if fn == 'drop':
        _SESS.pop(room, None)
        return json.dumps({'ok': True})
    S = _SESS.get(room)
    if S is None:
        return json.dumps({'ok': False, 'msg': 'no session for room ' + str(room)})
    if fn == 'apply':
        return json.dumps(S.apply(a['action']), ensure_ascii=False)
    if fn == 'view':
        return json.dumps(S.view(a['country']), ensure_ascii=False)
    if fn == 'teacher':
        return json.dumps(S.teacher_view(), ensure_ascii=False)
    if fn == 'views':
        return json.dumps({'teacher': S.teacher_view(),
                           'students': {n: S.view(n) for n in a['countries']}}, ensure_ascii=False)
    if fn == 'log':
        return json.dumps(S.log, ensure_ascii=False)
    if fn == 'meta':
        return json.dumps({'seed': S.seed, 'initial_students': S.initial_students,
                           'students': sorted(S.g.students), 'round': S.g.r, 'phase': S.phase})
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
    newSession: (room, seed, students, events = false) => call('new', { room, seed, students, events }),
    replay: (room, seed, students, log, events = false) => call('replay', { room, seed, students, log, events }),
    apply: (room, action) => call('apply', { room, action }),
    view: (room, country) => call('view', { room, country }),
    teacher: (room) => call('teacher', { room }),
    views: (room, countries) => call('views', { room, countries }),
    log: (room) => call('log', { room }),
    meta: (room) => call('meta', { room }),
    drop: (room) => call('drop', { room }),
    rooms: () => call('rooms', {}),
    pythonVersion: () => py.runPython('import sys; sys.version'),
  };
}
