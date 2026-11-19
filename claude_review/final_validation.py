"""Integrated validation of the current rule set (Claude, 2026-11-19).

Rule set (decisions + candidates as of this run)
  Economy  v17 baseline + operating 'light' (fuel R3/6/9, ore R4/8) + emergency purchase 1.0x
           base price + level-3 cost = level-2 cost.
  Score    economic 20 = 20*min(1, useful_export_noswap / export target)
           reserve 5, utilization 10, trade 25 = v17 fixed-score parts
           industrial capacity 15 = 15 if the main industry was levelled up at least once
           wellbeing 25 = v17 wellbeing - 1 per national-operation shortage day (>= 0)
  Grade    A >= 90, B >= 80, C >= 60, D < 60.

Pre-registered before running (do not change after seeing results)
  Targets  export targets re-derived for this economy with the v15 method on calibration seeds
           90000-90059 (normal + each country invest/trade, 780 games). These targets are used
           for every validation game below.
  Games    reused (same economy, deterministic): l3_flat_games (all-AI normal 130000-130099 and
           132000-132029), grades_games (single-student good/minimum/skip_ops/no_invest/idle).
           new: single 'cheap' (half price) + main level-up, 6x30, seeds 132000-132029;
                trios: every 3 of the 6 original countries (20 trios) all doing the same
                behaviour {good, minimum, cheap, idle, skip_ops}, seeds 132000-132014;
                mixed: each trio with one idle member and two good members (3 positions),
                seeds 132000-132004.
           'good' = normal AI trading + one main level-up (MainIndustryStudent K=1).
  Criteria V1 all-AI normal (130000-130099): no food-shortage rounds for the six original
              countries; operating shortage days (six original) <= 0.5 per game.
           V2 single student: Q1-Q7 of grades.py, and 'cheap' not higher than paired good in
              >= 90% of games (every country).
           V3 trios: good members A/B in >= 80% of trio games (every country); minimum, cheap
              and skip_ops members not higher than in the paired good-trio game in >= 90%;
              idle members D in >= 90%.
           V4 idle trio: the three AI-run original countries' mean total score falls by <= 10
              points versus the paired good-trio game (the economy keeps working).
           V5 mixed: the two good members A/B in >= 80% of games (every country).
Usage: python3 final_validation.py run cal|single|trio|mixed ; python3 final_validation.py report
"""
import gzip
import itertools
import json
import math
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

OUT = os.path.join(HERE, 'new_games')
ECON = dict(fee=1.0, l3_flat=True)
TRIOS = list(itertools.combinations(L.NAMES, 3))


def kw_for(members, b):
    kw = dict(ECON)
    if b in ('good', 'minimum', 'cheap', 'skip_ops'):
        kw['main_k'] = {n: 1 for n in members}
    if b in ('minimum', 'cheap', 'idle'):
        kw['behaviors'] = {n: b for n in members}
    if b == 'skip_ops':
        kw['skip'] = tuple(members)
    return kw


def task(spec):
    stage, seed, key = spec
    try:
        if stage == 'cal':
            focal, style = key
            kw = dict(ECON)
            if focal:
                kw.update(focal=focal, style=style)
        elif stage in ('single', 'trio'):
            members, b = key
            kw = kw_for(members, b)
        else:  # mixed: members (idle, good, good)
            idle, goods = key
            kw = dict(ECON, main_k={n: 1 for n in goods}, behaviors={idle: 'idle'})
        return {'stage': stage, 'seed': seed, 'key': key, 'ok': True, 'm': L.run_metrics(L.make_game(seed, **kw))}
    except Exception as e:
        return {'stage': stage, 'seed': seed, 'key': key, 'ok': False, 'error': repr(e)[:300]}


def specs(stage):
    if stage == 'cal':
        s = [('cal', x, (None, 'normal')) for x in range(90000, 90060)]
        return s + [('cal', x, (n, st)) for n in L.NAMES for st in ('invest', 'trade') for x in range(90000, 90060)]
    if stage == 'single':
        return [('single', x, ((n,), 'cheap')) for n in L.NAMES for x in range(132000, 132030)]
    if stage == 'trio':
        return [('trio', x, (t, b)) for b in ('good', 'minimum', 'cheap', 'idle', 'skip_ops')
                for t in TRIOS for x in range(132000, 132015)]
    if stage == 'mixed':
        return [('mixed', x, (t[i], tuple(n for n in t if n != t[i]))) for t in TRIOS for i in range(3)
                for x in range(132000, 132005)]
    raise SystemExit('unknown stage')


def run(stage):
    with Pool(2) as p:
        rows = p.map(task, specs(stage), chunksize=4)
    with gzip.open(os.path.join(OUT, f'final_{stage}.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print(stage, 'games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def load(name):
    with gzip.open(os.path.join(OUT, name), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows), name
    return rows


def targets():
    cal = load('final_cal.jsonl.gz')
    k = {(tuple(r['key'])[0], tuple(r['key'])[1], r['seed']): r for r in cal}
    T = {}
    for n in L.NAMES:
        v = [k[(None if s == 'normal' else n, s, x)]['m'][n]['useful_export_noswap']
             for s in ('normal', 'invest', 'trade') for x in range(90000, 90060)]
        v.sort(); pos = (len(v) - 1) * .75; lo = math.floor(pos); w = pos - lo
        q = v[lo] * (1 - w) + v[min(lo + 1, len(v) - 1)] * w
        T[n] = 5 * math.ceil(max(50, q) / 5 - 1e-12)
    return T


def total(m, n, T):
    x = m[n]
    if 'main_ups' in x:
        main_up = x['main_ups'] >= 1
    else:
        main = {'Tropia': 'banana', 'Grainia': 'wheat', 'Oilia': 'fuel', 'Mechania': 'machine',
                'Mineria': 'ore', 'Technia': 'electronics'}[n]
        main_up = any(g == main for _, g, _lv in x['upgrade_path'])
    well_cut = min(x['happy'] / 4, x['op_short'])
    return (x['score'] - x['econ_old'] + 20 * min(1, x['useful_export_noswap'] / T[n])
            - x['cap_old'] + (15 if main_up else 0) - well_cut)


def grade(t):
    return 4 if t >= 90 else 3 if t >= 80 else 2 if t >= 60 else 1


def report():
    T = targets()
    old_T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    mean = lambda a: sum(a) / len(a)
    res = {'targets': T, 'targets_previous_economy': old_T}
    # V1 all-AI normal
    l3 = load('l3_flat_games.jsonl.gz')
    normal = [r for r in l3 if r['tag'] == 'valid']
    res['V1'] = {'op_short_6_per_game': mean([sum(r['m'][n]['op_short'] for n in L.NAMES) for r in normal]),
                 'mean_total': {n: mean([total(r['m'], n, T) for r in normal]) for n in L.NAMES},
                 'grade_dist_ai': {n: {g: sum(grade(total(r['m'], n, T)) == g for r in normal) for g in (4, 3, 2, 1)} for n in L.NAMES}}
    # food shortages are not stored in run_metrics; satisfaction >= 75 means both foods fully met
    res['V1']['min_happy'] = min(r['m'][n]['happy'] for r in normal for n in L.NAMES)
    v1 = res['V1']['op_short_6_per_game'] <= .5 and res['V1']['min_happy'] >= 75
    # V2 single
    gr = load('grades_games.jsonl.gz')
    single = {(r['b'], r['focal'], r['seed']): r for r in gr}
    for r in load('final_single.jsonl.gz'):
        single[('cheap', r['key'][0][0], r['seed'])] = r
    S = {}
    for n in L.NAMES:
        S[n] = {}
        for b in ('good', 'minimum', 'cheap', 'skip_ops', 'no_invest', 'idle'):
            gs = [grade(total(single[(b, n, x)]['m'], n, T)) for x in range(132000, 132030)]
            gg = [grade(total(single[('good', n, x)]['m'], n, T)) for x in range(132000, 132030)]
            S[n][b] = {'dist': {g: gs.count(g) for g in (4, 3, 2, 1)},
                       'mean_total': mean([total(single[(b, n, x)]['m'], n, T) for x in range(132000, 132030)]),
                       'lower': mean([a < c for a, c in zip(gs, gg)]), 'not_higher': mean([a <= c for a, c in zip(gs, gg)]),
                       'mean_diff': mean([a - c for a, c in zip(gs, gg)])}
    A = [S[n]['good']['dist'][4] / 30 for n in L.NAMES]
    v2 = {'Q1': all((S[n]['good']['dist'][4] + S[n]['good']['dist'][3]) / 30 >= .8 for n in L.NAMES),
          'Q2': max(A) - min(A) <= .3 + 1e-9, 'Q3': all(a >= .3 for a in A),
          'Q4': all(S[n]['idle']['dist'][1] / 30 >= .9 for n in L.NAMES),
          'Q5': all(S[n]['minimum']['lower'] >= .8 for n in L.NAMES),
          'Q6': all(S[n]['skip_ops']['not_higher'] >= .9 and S[n]['skip_ops']['mean_diff'] < 0 for n in L.NAMES),
          'Q7': all(S[n]['no_invest']['dist'][4] / 30 <= .05 for n in L.NAMES),
          'cheap_not_higher_0.9': all(S[n]['cheap']['not_higher'] >= .9 for n in L.NAMES)}
    res['V2'] = {'countries': S, 'checks': v2}
    # V3 / V4 trios
    tri = load('final_trio.jsonl.gz')
    tk = {(tuple(r['key'][0]), r['key'][1], r['seed']): r for r in tri}
    agg = {b: {n: [] for n in L.NAMES} for b in ('good', 'minimum', 'cheap', 'idle', 'skip_ops')}
    idle_ai_drop = []
    for (t, b, x), r in tk.items():
        good = tk[(t, 'good', x)]
        for n in t:
            agg[b][n].append((grade(total(r['m'], n, T)), grade(total(good['m'], n, T)), total(r['m'], n, T)))
        if b == 'idle':
            others = [n for n in L.NAMES if n not in t]
            idle_ai_drop.append(mean([total(good['m'], n, T) - total(r['m'], n, T) for n in others]))
    trio = {b: {n: {'n': len(v), 'AB': mean([g >= 3 for g, _, _ in v]), 'D': mean([g == 1 for g, _, _ in v]),
                    'not_higher': mean([g <= h for g, h, _ in v]), 'lower': mean([g < h for g, h, _ in v]),
                    'mean_total': mean([t for _, _, t in v])} for n, v in d.items()} for b, d in agg.items()}
    v3 = {'good_AB_0.8': all(trio['good'][n]['AB'] >= .8 for n in L.NAMES),
          'minimum_not_higher_0.9': all(trio['minimum'][n]['not_higher'] >= .9 for n in L.NAMES),
          'cheap_not_higher_0.9': all(trio['cheap'][n]['not_higher'] >= .9 for n in L.NAMES),
          'skip_not_higher_0.9': all(trio['skip_ops'][n]['not_higher'] >= .9 for n in L.NAMES),
          'idle_D_0.9': all(trio['idle'][n]['D'] >= .9 for n in L.NAMES)}
    res['V3'] = {'trio': trio, 'checks': v3}
    res['V4'] = {'idle_trio_ai_mean_drop': mean(idle_ai_drop), 'max_drop': max(idle_ai_drop),
                 'check': mean(idle_ai_drop) <= 10}
    # V5 mixed
    mix = load('final_mixed.jsonl.gz')
    mg = {n: [] for n in L.NAMES}
    for r in mix:
        for n in r['key'][1]:
            mg[n].append(grade(total(r['m'], n, T)))
    res['V5'] = {'good_AB': {n: mean([g >= 3 for g in v]) for n, v in mg.items()},
                 'n': {n: len(v) for n, v in mg.items()}}
    res['V5']['check'] = all(v >= .8 for v in res['V5']['good_AB'].values())
    res['criteria'] = {'V1': v1, 'V2': all(v2.values()), 'V3': all(v3.values()), 'V4': res['V4']['check'], 'V5': res['V5']['check']}
    res['games'] = {'new_cal': len(load('final_cal.jsonl.gz')), 'new_single': len(load('final_single.jsonl.gz')),
                    'new_trio': len(tri), 'new_mixed': len(mix), 'reused_l3_flat': len(l3), 'reused_grades': len(gr)}
    json.dump(res, open(os.path.join(OUT, 'final_validation_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ('targets', 'targets_previous_economy', 'criteria', 'games')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    run(sys.argv[2]) if sys.argv[1] == 'run' else report()
