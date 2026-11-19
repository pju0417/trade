"""Virtual 3-student class under the confirmed rules (RULES_v1): one narrated game + 200-game distribution.

Pre-registered before running (descriptive, no pass/fail; do not change after seeing results)
  Rules      make_game(fee=1.0, l3_flat=True); score/grade = final_validation.total()/grade(),
             export targets = final_validation.targets().
  Students   (trio Tropia, Mechania, Mineria is one of final_validation.TRIOS; others are AI)
             민준  Tropia   good: AI trading, levels up main industry once (main_k=1)
             서연  Mechania cheap: public selling price half the reference price, main_k=1
             지호  Mineria  no_invest + skip_ops: never invests, never buys/keeps operating fuel/ore
  Configs    P        the three students as above
             G        all three 'good' (reference)
             FIX_SY   서연 becomes good, others as P
             FIX_JH_OPS  지호 keeps operating resources (still no investment)
             FIX_JH_INV  지호 invests in main industry once (still skips operating resources)
             FIX_JH   지호 becomes good
  Seeds      150000-150199 for every config (same seeds, paired comparison). 1,200 games.
  Narrated   the P game whose three totals are jointly closest to the P medians
             (min sum |total - median|; ties -> lowest seed).
Usage: python3 virtual_students.py run ; python3 virtual_students.py report
"""
import gzip
import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L
import final_validation as FV

OUT = os.path.join(HERE, 'new_games')
STU = {'Tropia': '민준', 'Mechania': '서연', 'Mineria': '지호'}
SEEDS = range(150000, 150200)
GOOD = {'main_k': True}
ROLES = {
    'P':          {'Tropia': 'good', 'Mechania': 'cheap', 'Mineria': 'jiho'},
    'G':          {'Tropia': 'good', 'Mechania': 'good', 'Mineria': 'good'},
    'FIX_SY':     {'Tropia': 'good', 'Mechania': 'good', 'Mineria': 'jiho'},
    'FIX_JH_OPS': {'Tropia': 'good', 'Mechania': 'cheap', 'Mineria': 'no_invest'},
    'FIX_JH_INV': {'Tropia': 'good', 'Mechania': 'cheap', 'Mineria': 'skip_ops'},
    'FIX_JH':     {'Tropia': 'good', 'Mechania': 'cheap', 'Mineria': 'good'},
}


def build(seed, roles):
    main_k, beh, skip, noinv = {}, {}, [], []
    for n, t in roles.items():
        if t in ('good', 'cheap', 'skip_ops'):
            main_k[n] = 1
        if t == 'cheap':
            beh[n] = 'cheap'
        if t in ('skip_ops', 'jiho'):
            skip.append(n)
        if t in ('no_invest', 'jiho'):
            noinv.append(n)
    kw = dict(fee=1.0, l3_flat=True, main_k=main_k)
    if beh: kw['behaviors'] = beh
    if skip: kw['skip'] = tuple(skip)
    if noinv: kw['no_invest'] = tuple(noinv)
    return L.make_game(seed, **kw)


def task(spec):
    cfg, seed = spec
    try:
        m, w = L.run_metrics(build(seed, ROLES[cfg]), with_world=True)
        return {'cfg': cfg, 'seed': seed, 'ok': True, 'm': {n: m[n] for n in L.NAMES}, 'w': w}
    except Exception as e:
        return {'cfg': cfg, 'seed': seed, 'ok': False, 'error': repr(e)[:300]}


def run():
    specs = [(c, s) for c in ROLES for s in SEEDS]
    with Pool(2) as p:
        rows = p.map(task, specs, chunksize=5)
    with gzip.open(os.path.join(OUT, 'virtual_students.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


GOODS_KO = {'wheat': '밀', 'banana': '바나나', 'fuel': '연료', 'ore': '광물', 'machine': '기계', 'electronics': '전자제품'}
NAME_KO = {'Tropia': '트로피아', 'Grainia': '그레니아', 'Oilia': '오일리아', 'Mechania': '메카니아',
           'Mineria': '미네리아', 'Technia': '테크니아', 'Novia': '노비아', 'Agrea': '아그레아', 'Ferria': '페리아'}


def narrate(seed, T):
    g = build(seed, ROLES['P'])
    m = L.run_metrics(g)
    log = {n: {r: {'sold': Counter(), 'sold_g': 0, 'bought': Counter(), 'bought_g': 0, 'to': Counter(), 'from': Counter()}
               for r in range(1, 10)} for n in STU}
    for t in g.transactions:
        r = t['round']
        price = t['cash'][2] if t['cash'] else 0
        for leg in t['legs']:
            goods = Counter(GOODS_KO[g.units[u].good] for u in leg['ids'])
            if leg['seller'] in STU:
                d = log[leg['seller']][r]; d['sold'] += goods; d['sold_g'] += price; d['to'][NAME_KO[leg['buyer']]] += 1
            if leg['buyer'] in STU:
                d = log[leg['buyer']][r]; d['bought'] += goods; d['bought_g'] += price; d['from'][NAME_KO[leg['seller']]] += 1
    ops = {(x['country'], x['round']): x for x in g.operating_ledger if x['country'] in STU}
    out = {'seed': seed, 'students': {}}
    for n, who in STU.items():
        c = g.cs[n]
        rounds = []
        for r in range(1, 10):
            d = log[n][r]; o = ops.get((n, r), {})
            req = {GOODS_KO[k]: v for k, v in o.get('required', {}).items() if v}
            miss = {GOODS_KO[k]: v for k, v in o.get('missing', {}).items() if v}
            fee = sum(int(round(1.0 * L.BASE[k])) * v for k, v in o.get('missing', {}).items())
            rounds.append({'round': r,
                           'sold': dict(d['sold']), 'sold_cash': d['sold_g'], 'to': dict(d['to']),
                           'bought': dict(d['bought']), 'bought_cash': d['bought_g'], 'from': dict(d['from']),
                           'invest': [f'{GOODS_KO[gd]} 레벨 {lv}' for rr, gd, lv in c.upgrade_rounds if rr == r],
                           'ops_needed': req, 'ops_missing': miss, 'emergency_fee': fee,
                           'happy': c.happiness[r - 1], 'cash_end': c.cash_rounds[r - 1]})
        x = m[n]
        tot = FV.total(m, n, T)
        out['students'][n] = {
            'who': who, 'role': ROLES['P'][n], 'rounds': rounds,
            'score': {'수출': 20 * min(1, x['useful_export_noswap'] / T[n]), '산업': 15 if x['main_ups'] >= 1 else 0,
                      '국민 생활': x['well_pts'] - min(x['happy'] / 4, x['op_short']), '무역': x['trade_pts'],
                      '활용': x['util_pts'], '현금': x['reserve_pts'], 'total': tot, 'grade': 'DCBA'[FV.grade(tot) - 1]},
            'export_value': x['useful_export_noswap'], 'target': T[n], 'revenue': x['revenue'],
            'op_short': x['op_short'], 'emergency_total': x['emergency'], 'final_cash': x['cash'],
            'food_short': x['food_short']}
    return out


def report():
    T = FV.targets()
    with gzip.open(os.path.join(OUT, 'virtual_students.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(l) for l in f]
    bad = [r for r in rows if not r['ok']]
    by = defaultdict(dict)
    for r in rows:
        if r['ok']:
            by[r['cfg']][r['seed']] = r
    res = {'games': len(rows), 'failed': len(bad), 'targets': {n: T[n] for n in STU}, 'configs': {}}
    for cfg, R in by.items():
        d = {}
        for n, who in STU.items():
            tots = [FV.total(r['m'], n, T) for r in R.values()]
            gr = Counter('DCBA'[FV.grade(t) - 1] for t in tots)
            ms = [r['m'][n] for r in R.values()]
            d[who] = {'n': len(tots), 'mean': st.mean(tots), 'median': st.median(tots),
                      'min': min(tots), 'max': max(tots),
                      'grades': {k: gr.get(k, 0) for k in 'ABCD'},
                      'export_pts': st.mean(20 * min(1, x['useful_export_noswap'] / T[n]) for x in ms),
                      'industry_pts': st.mean(15 if x['main_ups'] >= 1 else 0 for x in ms),
                      'living_pts': st.mean(x['well_pts'] - min(x['happy'] / 4, x['op_short']) for x in ms),
                      'trade_pts': st.mean(x['trade_pts'] for x in ms), 'util_pts': st.mean(x['util_pts'] for x in ms),
                      'cash_pts': st.mean(x['reserve_pts'] for x in ms),
                      'op_short_days': st.mean(x['op_short'] for x in ms),
                      'emergency_G': st.mean(x['emergency'] for x in ms),
                      'food_short_rounds': st.mean(x['food_short'] for x in ms)}
        d['_ai_food_short_all9'] = st.mean(v for r in R.values() for v in r['w']['food_short'].values())
        res['configs'][cfg] = d
    # paired differences vs P
    P = by['P']
    res['paired_vs_P'] = {}
    for cfg in ROLES:
        if cfg == 'P':
            continue
        res['paired_vs_P'][cfg] = {who: st.mean(FV.total(by[cfg][s]['m'], n, T) - FV.total(P[s]['m'], n, T) for s in P)
                                   for n, who in STU.items()}
    med = {n: st.median(FV.total(r['m'], n, T) for r in P.values()) for n in STU}
    rep = min(P, key=lambda s: (sum(abs(FV.total(P[s]['m'], n, T) - med[n]) for n in STU), s))
    res['narrated'] = narrate(rep, T)
    json.dump(res, open(os.path.join(OUT, 'virtual_students_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ('games', 'failed', 'targets', 'paired_vs_P')}, ensure_ascii=False, indent=1))
    for cfg, d in res['configs'].items():
        print(cfg, {w: (round(v['mean'], 1), v['grades']) for w, v in d.items() if not w.startswith('_')},
              'food_short_all9', round(d['_ai_food_short_all9'], 3))


if __name__ == '__main__':
    run() if sys.argv[1] == 'run' else report()
