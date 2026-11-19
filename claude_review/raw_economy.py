"""Why don't raw-material countries earn much? Supply, use and price of every good (descriptive).

No criteria: a diagnosis of the confirmed-rules economy, no rule change.
  Games: sim_lib.make_game(seed, fee=1.0, l3_flat=True), all AI, seeds 200000-200059 (60 games).
  Per good: units produced (by producer), initial stock, units used by purpose, units left unused
  at the end, units traded and average unit price (cash deals), producers' sales revenue.
  Per country: sales revenue by good, national income, emergency fees, final cash.
Usage: python3 raw_economy.py [A K]
"""
import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

GOODS = ('wheat', 'banana', 'fuel', 'ore', 'machine', 'electronics')


def one(seed):
    g = L.make_game(seed, fee=1.0, l3_flat=True)
    m = L.run_metrics(g)
    d = {'produced': Counter(), 'initial': Counter(), 'producer': defaultdict(Counter), 'use': defaultdict(Counter),
         'unused_end': Counter(), 'unused_by_owner': defaultdict(Counter), 'traded': Counter(), 'cash_units': Counter(),
         'cash_value': Counter(), 'barter_units': Counter(), 'revenue': defaultdict(Counter), 'sold_units': defaultdict(Counter)}
    for u in g.units.values():
        if u.born == 0:
            d['initial'][u.good] += 1
        else:
            d['produced'][u.good] += 1
            d['producer'][u.good][u.origin] += 1
        if u.used:
            d['use'][u.good][u.use_purpose] += 1
        elif u.owner is not None:
            d['unused_end'][u.good] += 1
            d['unused_by_owner'][u.good][u.owner] += 1
    for t in g.transactions:
        for leg in t['legs']:
            good = g.units[leg['ids'][0]].good
            k = len(leg['ids'])
            d['traded'][good] += k
            d['sold_units'][leg['seller']][good] += k
            if t['cash']:
                d['cash_units'][good] += k
                d['cash_value'][good] += t['cash'][2]
                d['revenue'][leg['seller']][good] += t['cash'][2]
            else:
                d['barter_units'][good] += k
    ex = L.export_measures(g)
    countries = {n: {'income': c.tax, 'final_cash': c.cash, 'emergency': getattr(g, 'emergency', {}).get(n, 0),
                     'useful_export': ex[n]['useful_export_noswap'], 'util_pts': m[n]['util_pts'] if n in m else None,
                     'produced': dict(c.produced)} for n, c in g.cs.items()}
    return {'seed': seed, 'd': json.loads(json.dumps(d)), 'countries': countries,
            'raw_use': Counter((x['good'], x['purpose']) for x in g.raw_use_log).most_common()}


def main(a0=200000, k=60):
    with Pool(2) as p:
        rows = p.map(one, range(a0, a0 + k))
    mean = lambda xs: st.mean(xs) if xs else 0
    out = {'games': len(rows), 'seeds': [a0, a0 + k - 1], 'goods': {}, 'countries': {}}
    for good in GOODS:
        prod = mean([r['d']['produced'].get(good, 0) for r in rows])
        use = Counter()
        for r in rows:
            for p_, v in r['d']['use'].get(good, {}).items():
                use[p_] += v / len(rows)
        cu = sum(r['d']['cash_units'].get(good, 0) for r in rows)
        cv = sum(r['d']['cash_value'].get(good, 0) for r in rows)
        producers = Counter()
        for r in rows:
            for n, v in r['d']['producer'].get(good, {}).items():
                producers[n] += v / len(rows)
        holders = Counter()
        for r in rows:
            for n, v in r['d']['unused_by_owner'].get(good, {}).items():
                holders[n] += v / len(rows)
        out['goods'][good] = {
            'initial': mean([r['d']['initial'].get(good, 0) for r in rows]), 'produced': prod,
            'producers': {n: round(v, 1) for n, v in producers.most_common()},
            'used_by_purpose': {p_: round(v, 1) for p_, v in use.most_common()},
            'unused_end': mean([r['d']['unused_end'].get(good, 0) for r in rows]),
            'unused_holders': {n: round(v, 1) for n, v in holders.most_common(5)},
            'traded': mean([r['d']['traded'].get(good, 0) for r in rows]),
            'barter_units': mean([r['d']['barter_units'].get(good, 0) for r in rows]),
            'avg_cash_price': cv / cu if cu else None, 'base_price': L.BASE.get(good) if hasattr(L, 'BASE') and good in L.BASE else None}
    for n in rows[0]['countries']:
        rev = Counter()
        for r in rows:
            for good, v in r['d']['revenue'].get(n, {}).items():
                rev[good] += v / len(rows)
        out['countries'][n] = {
            'sales_revenue': round(sum(rev.values()), 1), 'by_good': {k: round(v, 1) for k, v in rev.most_common()},
            'national_income': mean([r['countries'][n]['income'] for r in rows]),
            'emergency': mean([r['countries'][n]['emergency'] for r in rows]),
            'final_cash': mean([r['countries'][n]['final_cash'] for r in rows]),
            'useful_export': mean([r['countries'][n]['useful_export'] for r in rows]),
            'util_pts': mean([r['countries'][n]['util_pts'] for r in rows]) if rows[0]['countries'][n]['util_pts'] is not None else None}
    path = os.path.join(HERE, 'new_games', 'raw_economy.json')
    json.dump(out, open(path, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(*(map(int, sys.argv[1:3])) if len(sys.argv) > 2 else ())
