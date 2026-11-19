"""Bundle the frozen v17 engine, sim_lib and the classroom module for the browser (Pyodide).

The files are copied byte-for-byte into webapp/engine_bundle.json with their SHA-256, under
the same relative paths as in the repository, so `import sim_lib` works unchanged in Pyodide.
Usage:  python3 webapp/build_bundle.py          (write)
        python3 webapp/build_bundle.py --check  (fail if the bundle differs from the repo files)
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'webapp', 'engine_bundle.json')
SRC = 'trade_v17/source_v13'
FILES = (
    ['claude_review/sim_lib.py', 'webapp/py/classroom.py',
     'trade_v17/operating_engine.py', 'trade_v17/run_operating_validation.py', 'trade_v17/SCORE_TARGETS_V15.json']
    + [f'{SRC}/{n}.py' for n in (
        'reference_engine', 'core_engine', 'engine', 'expansion_engine', 'budget_engine', 'budget_trace',
        'machinery_engine', 'recommendation_engine', 'raw_engine', 'development_engine', 'routing_engine',
        'evaluation_engine', 'growth_scoring', 'causal_engine',
        'run_causal_validation', 'run_development_validation', 'run_evaluation_validation',
        'run_growth_validation', 'run_raw_validation', 'run_routing_validation')]
)


def build():
    files, sha = {}, {}
    for f in FILES:
        b = open(os.path.join(ROOT, f), 'rb').read()
        files[f] = b.decode('utf-8')
        sha[f] = hashlib.sha256(b).hexdigest()
    return {'format': 1, 'files': files, 'sha256': sha,
            'entry': {'paths': ['claude_review', 'webapp/py'], 'module': 'classroom'}}


if __name__ == '__main__':
    b = build()
    if '--check' in sys.argv:
        old = json.load(open(OUT, encoding='utf-8'))
        if old['sha256'] != b['sha256'] or old['files'] != b['files']:
            sys.exit('engine_bundle.json is out of date: run python3 webapp/build_bundle.py')
        print('bundle up to date:', len(b['files']), 'files')
    else:
        json.dump(b, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
        print('wrote', OUT, len(b['files']), 'files', os.path.getsize(OUT), 'bytes')
