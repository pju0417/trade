"""Grade schemes for 'goal attainment' display: two candidates compared (Claude, 2026-11-19).

Pre-registered before running (do not change after seeing results)
  Economy      v17 baseline + light + emergency purchase 1.0x + level-3 cost = level-2 cost.
  Score (100)  economic 20 = 20*min(1, useful_export_noswap / export target);
               industrial capacity 15 = 15 if the main industry was levelled up at least once;
               reserve 5, utilization 10, wellbeing 25, trade 25 = v17 fixed score parts.
  Scheme S     total score: A >= 90, B >= 80, C >= 60, D < 60.
  Scheme M     four goal checks; A = 4, B = 3, C = 2, D <= 1:
                 export   useful_export_noswap >= export target
                 industry main industry levelled up at least once
                 living   mean satisfaction over 9 rounds >= 90
                 trade    trade points >= 20 (of 25)
  Behaviours   (focal country, seeds 132000-132029, 6 countries x 30 each)
                 good       MainIndustryStudent K=1 (normal AI trading + one main level-up)
                 minimum    good + public selling price 1G
                 skip_ops   good + ignores national operating needs (emergency purchase applies)
                 no_invest  AI 'trade' style (no investment)
                 idle       no trade, no investment
  Criteria (each scheme, every country)
               Q1 good: A or B in >= 80% of games.
               Q2 good: A-rates differ across countries by <= 0.30.
               Q3 good: A-rate >= 0.30 (A is reachable).
               Q4 idle: D in >= 90% of games.
               Q5 minimum: lower grade than the paired good game in >= 80% of games.
               Q6 skip_ops: grade not higher than paired good in >= 90% and lower on average.
               Q7 no_invest: A-rate <= 0.05.
Usage: python3 grades.py run ; python3 grades.py report
"""
import gzip
import json
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

OUT = os.path.join(HERE, 'new_games')
SEEDS = range(132000, 132030)
BEHAVIOURS = ('good', 'minimum', 'skip_ops', 'no_invest', 'idle')
GRADE = {4: 'A', 3: 'B', 2: 'C', 1: 'D'}


def make(seed, n, b):
    kw = dict(fee=1.0, l3_flat=True)
    if b in ('good', 'minimum', 'skip_ops'):
        kw['main_k'] = {n: 1}
    if b == 'minimum':
        kw['behaviors'] = {n: 'minimum'}
    if b == 'skip_ops':
        kw['skip'] = (n,)
    if b == 'no_invest':
        kw.update(focal=n, style='trade')
    if b == 'idle':
        kw['behaviors'] = {n: 'idle'}
    return L.make_game(seed, **kw)


def task(spec):
    seed, n, b = spec
    try:
        return {'seed': seed, 'focal': n, 'b': b, 'ok': True, 'm': L.run_metrics(make(seed, n, b))}
    except Exception as e:
        return {'seed': seed, 'focal': n, 'b': b, 'ok': False, 'error': repr(e)[:300]}


def run():
    sp = [(x, n, b) for b in BEHAVIOURS for n in L.NAMES for x in SEEDS]
    with Pool(2) as p:
        rows = p.map(task, sp, chunksize=4)
    with gzip.open(os.path.join(OUT, 'grades_games.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def parts(m, n, T):
    x = m[n]
    main_up = x['main_ups'] >= 1
    total = (x['score'] - x['econ_old'] + 20 * min(1, x['useful_export_noswap'] / T[n])
             - x['cap_old'] + (15 if main_up else 0))
    checks = {'export': x['useful_export_noswap'] >= T[n], 'industry': main_up,
              'living': x['happy'] >= 90, 'trade': x['trade_pts'] >= 20}
    s = 4 if total >= 90 else 3 if total >= 80 else 2 if total >= 60 else 1
    mm = max(1, sum(checks.values()))
    return total, checks, s, mm


def report():
    with gzip.open(os.path.join(OUT, 'grades_games.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows)
    T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    idx = {(r['b'], r['focal'], r['seed']): parts(r['m'], r['focal'], T) for r in rows}
    mean = lambda a: sum(a) / len(a)
    res = {'export_targets': T, 'schemes': {}}
    for si, scheme in ((2, 'S_score_bands'), (3, 'M_goal_checks')):
        per = {}
        for n in L.NAMES:
            d = {}
            for b in BEHAVIOURS:
                g = [idx[(b, n, x)][si] for x in SEEDS]
                d[b] = {'dist': {GRADE[k]: g.count(k) for k in (4, 3, 2, 1)},
                        'A_rate': g.count(4) / 30, 'AB_rate': (g.count(4) + g.count(3)) / 30,
                        'D_rate': g.count(1) / 30, 'mean_total': mean([idx[(b, n, x)][0] for x in SEEDS])}
                if b != 'good':
                    diff = [idx[(b, n, x)][si] - idx[('good', n, x)][si] for x in SEEDS]
                    d[b]['lower_than_good'] = sum(v < 0 for v in diff) / 30
                    d[b]['not_higher_than_good'] = sum(v <= 0 for v in diff) / 30
                    d[b]['mean_grade_diff'] = mean(diff)
            d['good']['check_rates'] = {k: mean([idx[('good', n, x)][1][k] for x in SEEDS]) for k in ('export', 'industry', 'living', 'trade')}
            per[n] = d
        A = [per[n]['good']['A_rate'] for n in L.NAMES]
        crit = {'Q1_good_AB_ge_0.8': all(per[n]['good']['AB_rate'] >= .8 for n in L.NAMES),
                # tolerance: 9/30 - 0/30 style differences must not fail on floating-point error
                'Q2_good_A_range_le_0.3': max(A) - min(A) <= .3 + 1e-9,
                'Q3_good_A_ge_0.3': all(a >= .3 for a in A),
                'Q4_idle_D_ge_0.9': all(per[n]['idle']['D_rate'] >= .9 for n in L.NAMES),
                'Q5_minimum_lower_ge_0.8': all(per[n]['minimum']['lower_than_good'] >= .8 for n in L.NAMES),
                'Q6_skip_not_higher_ge_0.9_and_lower_mean': all(per[n]['skip_ops']['not_higher_than_good'] >= .9 and per[n]['skip_ops']['mean_grade_diff'] < 0 for n in L.NAMES),
                'Q7_no_invest_A_le_0.05': all(per[n]['no_invest']['A_rate'] <= .05 for n in L.NAMES)}
        res['schemes'][scheme] = {'countries': per, 'criteria': crit}
    res['games'] = len(rows)
    json.dump(res, open(os.path.join(OUT, 'grades_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    run() if sys.argv[1] == 'run' else report()
