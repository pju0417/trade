"""Write CPython reference games (random student actions) for the Pyodide cross-check.
Usage: python3 make_golden.py OUT.json A K"""
import json
import random
import sys

import paths  # noqa: F401
import classroom as C
from test_actions import random_action

out = []
a0, k = int(sys.argv[2]), int(sys.argv[3])
for seed in range(a0, a0 + k):
    rng = random.Random(seed)
    students = rng.sample(list(C.ORIGINAL), rng.choice((1, 3, 6)))
    s = C.Session(seed, students)
    mid = None
    while s.phase != 'finished':
        for _ in range(rng.randint(0, 15)):
            s.apply(random_action(rng, s, rng.choice(students)))
        s.apply({'type': 'advance'})
        if s.g.r == 5 and s.phase == 'listing' and mid is None:
            mid = {'log_len': len(s.log), 'views': {n: s.view(n) for n in students}, 'teacher': s.teacher_view()}
    out.append({'seed': seed, 'students': students, 'log': s.log, 'mid': mid,
                'final': {'views': {n: s.view(n) for n in students}, 'teacher': s.teacher_view()}})
json.dump(out, open(sys.argv[1], 'w'), ensure_ascii=False)
print('golden games', len(out), 'actions', sum(len(g['log']) for g in out))
