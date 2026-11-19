"""E1: AI lists before students (webapp phase order). Paired with the earlier H2 validation games.

Pre-registered (set before running)
  Same 120 games as web_targets.py validate (20 trios x seeds 190000+100*trio+j, j=0..5),
  H2 students, new phase order. Old results: results/web_validate.jsonl.gz (old order).
  Criteria
    E1a  all-AI equivalence still holds (test_equivalence.py, run separately)
    E1b  mean useful export of H2 Oilia and of H2 Mineria both increase (paired)
    E1c  no country's H2 mean total (simulator targets) drops by more than 2 points
"""
import gzip
import json
import os
import statistics as st
from multiprocessing import Pool

import paths  # noqa: F401
import web_targets as W

OUT = W.OUT


def main():
    specs = [(i, 190000 + 100 * i + j) for i in range(len(W.TRIOS)) for j in range(6)]
    with Pool(2) as p:
        rows = p.map(W.play_game, specs, chunksize=3)
    with gzip.open(os.path.join(OUT, 'web_validate_orderfix.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    old = {(tuple(r['trio']), r['seed']): r for r in W.load('validate')}
    T = W.SIM_TARGETS
    res = {}
    for n in W.C.ORIGINAL:
        pairs = [(old[(tuple(r['trio']), r['seed'])]['m'][n], r['m'][n]) for r in rows if n in r['trio']]
        res[n] = {
            'n': len(pairs),
            'export_old': st.mean(a['useful_export_noswap'] for a, b in pairs),
            'export_new': st.mean(b['useful_export_noswap'] for a, b in pairs),
            'total_old': st.mean(W.total({n: a}, n, T) for a, b in pairs),
            'total_new': st.mean(W.total({n: b}, n, T) for a, b in pairs),
            'util_old': st.mean(a['util_pts'] for a, b in pairs), 'util_new': st.mean(b['util_pts'] for a, b in pairs),
        }
    crit = {'E1b': all(res[n]['export_new'] > res[n]['export_old'] for n in ('Oilia', 'Mineria')),
            'E1c': all(res[n]['total_new'] - res[n]['total_old'] >= -2 for n in res)}
    out = {'games': len(rows), 'result': res, 'criteria': crit}
    json.dump(out, open(os.path.join(OUT, 'order_fix_report.json'), 'w'), ensure_ascii=False, indent=1)
    for n, v in res.items():
        print(n, {k: round(x, 1) for k, x in v.items()})
    print(crit)


if __name__ == '__main__':
    main()
