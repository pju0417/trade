"""Raw-material countries: AI-played vs human-style (H2) played, same seeds (descriptive, no criteria).

  Trio Oilia, Mechania, Mineria as H2 students in classroom.Session vs the same seeds all-AI
  (Session with no students = sim_lib.make_game(seed, fee=1.0, l3_flat=True)).
  Seeds 210000-210029 (30 paired games). For Oilia and Mineria: units produced, sold by channel,
  average unit price, units consumed at home, units left unused at the end, useful export.
"""
import json
import statistics as st
import sys
from collections import Counter
from multiprocessing import Pool

import paths  # noqa: F401
import classroom as C
import human_policy_h2 as H2
import sim_lib as L

TRIO = ['Oilia', 'Mechania', 'Mineria']
FOCUS = ['Oilia', 'Mineria']


def measure(s):
    g = s.g
    out = {}
    ex = L.export_measures(g)
    for n in FOCUS:
        d = {'produced': Counter(), 'sold': Counter(), 'revenue': Counter(), 'used_home': Counter(),
             'unused_end': Counter(), 'used_abroad': Counter()}
        for u in g.units.values():
            if u.origin != n or u.born == 0:
                continue
            d['produced'][u.good] += 1
            if u.used and u.use_country == n:
                d['used_home'][u.good] += 1
            elif u.used:
                d['used_abroad'][u.good] += 1
            elif u.owner == n:
                d['unused_end'][u.good] += 1
        for t in g.transactions:
            for leg in t['legs']:
                if leg['seller'] != n:
                    continue
                good = g.units[leg['ids'][0]].good
                d['sold'][(good, t['channel'])] += len(leg['ids'])
                if t['cash']:
                    d['revenue'][good] += t['cash'][2]
        out[n] = {k: {str(a): b for a, b in v.items()} for k, v in d.items()}
        out[n]['useful_export'] = ex[n]['useful_export_noswap']
        out[n]['final_cash'] = g.cs[n].cash
    return out


def one(seed):
    ai = C.Session(seed, [])
    while ai.phase != 'finished':
        ai.apply({'type': 'advance'})
    hu = C.Session(seed, TRIO)
    while hu.phase != 'finished':
        for n in TRIO:
            H2.play(hu, n)
        hu.apply({'type': 'advance'})
    return {'seed': seed, 'ai': measure(ai), 'human': measure(hu)}


def main(a0=210000, k=30):
    with Pool(2) as p:
        rows = p.map(one, range(a0, a0 + k))
    res = {}
    for who in ('ai', 'human'):
        for n in FOCUS:
            agg = {}
            for key in ('produced', 'sold', 'revenue', 'used_home', 'used_abroad', 'unused_end'):
                c = Counter()
                for r in rows:
                    for a, b in r[who][n][key].items():
                        c[a] += b / len(rows)
                agg[key] = {a: round(b, 1) for a, b in c.most_common()}
            agg['useful_export'] = round(st.mean(r[who][n]['useful_export'] for r in rows), 1)
            agg['final_cash'] = round(st.mean(r[who][n]['final_cash'] for r in rows), 1)
            res[f'{n}:{who}'] = agg
    print(json.dumps({'games': len(rows), 'seeds': [a0, a0 + k - 1], 'result': res}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(*(map(int, sys.argv[1:3])) if len(sys.argv) > 2 else ())
