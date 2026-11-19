"""Final simulation of the confirmed rules (RULES_v1) with mixed student behaviours, 3 vs 6 students.

Pre-registered before running (do not change after seeing results)
  Rules        docs/RULES_v1.md: make_game(fee=1.0, l3_flat=True); score/grade = final_validation
               total()/grade() with export targets re-derived for this economy (final_cal).
  Student types (assigned per student; otherwise the engine's AI trading)
               good      trades like the AI and levels up its main industry once
               no_invest trades like the AI but never invests
               skip_ops  good, but never buys/keeps national-operation fuel and ore
               cheap     good, but public selling price is half the reference price
               minimum   good, but public selling price is 1G
               idle      no trade, no investment
  Mix          each student independently: good 40%, no_invest 15%, skip_ops 15%, cheap 10%,
               minimum 10%, idle 10% (random.Random(seed)).
  Settings     S3: 3 students (a uniformly random 3 of the 6 original countries), 600 games,
                   seeds 140000-140599; the other countries are AI.
               S6: 6 students (all six original countries), 600 games, seeds 141000-141599;
                   the three added countries stay AI.
               Baselines (reported, not judged): all-AI 100 games (142000-142099), all-good
               3 students 100 games (142100-142199), all-good 6 students 100 games (142200-142299).
  Criteria     F1 good students A/B >= 80%, every country, in S3 and in S6.
               F2 good students A/B >= 70% in games where at least half of the OTHER students
                  are not 'good' (S3: >= 1 of 2; S6: >= 3 of 5), pooled over countries.
               F3 by mean total score, 'good' is the highest type and 'idle' the lowest (S3, S6).
               F4 no other type has a higher A-rate than 'good' (S3, S6).
               F5 mean food-shortage rounds per non-idle country (all 9 countries) <= 0.2 (S3, S6).
               F6 good students: mean total in S6 within 3 points of S3; A/B-rate gap <= 0.10.
               F7 idle students D >= 90% (S3, S6).
Usage: python3 final_simulation.py run ; python3 final_simulation.py report
"""
import gzip
import json
import os
import random
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L
import final_validation as FV

OUT = os.path.join(HERE, 'new_games')
TYPES = ('good', 'no_invest', 'skip_ops', 'cheap', 'minimum', 'idle')
WEIGHTS = (40, 15, 15, 10, 10, 10)


def assign(seed, setting):
    rng = random.Random(seed)
    if setting == 'S3':
        students = list(rng.choice(FV.TRIOS))
    elif setting == 'S6':
        students = list(L.NAMES)
    else:
        students = []
    return {n: rng.choices(TYPES, WEIGHTS)[0] for n in students}


def build(seed, roles):
    kw = dict(fee=1.0, l3_flat=True)
    main_k, beh, skip, noinv = {}, {}, [], []
    for n, t in roles.items():
        if t in ('good', 'skip_ops', 'cheap', 'minimum'):
            main_k[n] = 1
        if t in ('cheap', 'minimum', 'idle'):
            beh[n] = t
        if t == 'skip_ops':
            skip.append(n)
        if t == 'no_invest':
            noinv.append(n)
    if main_k: kw['main_k'] = main_k
    if beh: kw['behaviors'] = beh
    if skip: kw['skip'] = tuple(skip)
    if noinv: kw['no_invest'] = tuple(noinv)
    return L.make_game(seed, **kw)


def task(spec):
    setting, seed = spec
    if setting in ('S3', 'S6'):
        roles = assign(seed, setting)
    elif setting == 'AI':
        roles = {}
    else:  # all-good baselines
        rng = random.Random(seed)
        roles = {n: 'good' for n in (rng.choice(FV.TRIOS) if setting == 'G3' else L.NAMES)}
    try:
        m, w = L.run_metrics(build(seed, roles), with_world=True)
        return {'setting': setting, 'seed': seed, 'roles': roles, 'ok': True, 'm': m, 'w': w}
    except Exception as e:
        return {'setting': setting, 'seed': seed, 'roles': roles, 'ok': False, 'error': repr(e)[:300]}


def specs():
    s = [('S3', x) for x in range(140000, 140600)] + [('S6', x) for x in range(141000, 141600)]
    s += [('AI', x) for x in range(142000, 142100)] + [('G3', x) for x in range(142100, 142200)]
    s += [('G6', x) for x in range(142200, 142300)]
    return s


def run():
    with Pool(2) as p:
        rows = p.map(task, specs(), chunksize=4)
    with gzip.open(os.path.join(OUT, 'final_sim_games.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def report():
    rows = FV.load('final_sim_games.jsonl.gz')
    T = FV.targets()
    mean = lambda a: sum(a) / len(a) if a else float('nan')
    G = {4: 'A', 3: 'B', 2: 'C', 1: 'D'}
    res = {'targets': T, 'settings': {}}
    for st in ('S3', 'S6', 'AI', 'G3', 'G6'):
        R = [r for r in rows if r['setting'] == st]
        by_type = defaultdict(list); by_country_good = defaultdict(list); mixed_good = []
        peers = defaultdict(list); kingmaker = {'with': [], 'without': []}; ai = []
        for r in R:
            roles = r['roles']
            for n in L.NAMES:
                t = FV.total(r['m'], n, T); g = FV.grade(t)
                if n in roles:
                    typ = roles[n]
                    by_type[typ].append((t, g))
                    if typ == 'good':
                        by_country_good[n].append(g)
                        others = [roles[k] for k in roles if k != n]
                        bad = sum(o != 'good' for o in others)
                        peers[bad].append((t, g))
                        if others and bad >= len(others) / 2:
                            mixed_good.append(g)
                        key = 'with' if any(o in ('cheap', 'minimum') for o in others) else 'without'
                        kingmaker[key].append(t)
                else:
                    ai.append((t, g))
        non_idle = [r['w']['food_short'][k] for r in R for k in r['w']['food_short'] if r['roles'].get(k) != 'idle']
        d = {'games': len(R),
             'types': {k: {'n': len(v), 'mean_total': mean([t for t, _ in v]),
                           'dist': {G[x]: sum(g == x for _, g in v) for x in (4, 3, 2, 1)},
                           'A': mean([g == 4 for _, g in v]), 'AB': mean([g >= 3 for _, g in v]),
                           'D': mean([g == 1 for _, g in v])} for k, v in by_type.items()},
             'good_by_country_AB': {n: mean([g >= 3 for g in v]) for n, v in by_country_good.items()},
             'good_by_country_n': {n: len(v) for n, v in by_country_good.items()},
             'good_AB_when_half_peers_not_good': mean([g >= 3 for g in mixed_good]), 'n_mixed_good': len(mixed_good),
             'good_by_number_of_non_good_peers': {k: {'n': len(v), 'mean_total': mean([t for t, _ in v]), 'AB': mean([g >= 3 for _, g in v])} for k, v in sorted(peers.items())},
             'good_total_with_cheap_or_minimum_peer': mean(kingmaker['with']), 'n_with': len(kingmaker['with']),
             'good_total_without': mean(kingmaker['without']), 'n_without': len(kingmaker['without']),
             'ai_original_countries': {'n': len(ai), 'mean_total': mean([t for t, _ in ai]), 'AB': mean([g >= 3 for _, g in ai])},
             'food_short_per_non_idle_country': mean(non_idle),
             'op_short_per_country': mean([v for r in R for v in r['w']['op_short'].values()]),
             'trade_units_per_game': mean([r['w']['trade_units'] for r in R]),
             'transactions_per_game': mean([r['w']['transactions'] for r in R]),
             'role_counts': dict(Counter(t for r in R for t in r['roles'].values()))}
        res['settings'][st] = d
    S3, S6 = res['settings']['S3'], res['settings']['S6']
    def typ_ok(S):
        mt = {k: v['mean_total'] for k, v in S['types'].items()}
        return max(mt, key=mt.get) == 'good' and min(mt, key=mt.get) == 'idle'
    res['criteria'] = {
        'F1_good_AB_0.8_each_country': all(v >= .8 for S in (S3, S6) for v in S['good_by_country_AB'].values()),
        'F2_good_AB_0.7_with_half_non_good_peers': all(S['good_AB_when_half_peers_not_good'] >= .7 for S in (S3, S6)),
        'F3_good_highest_idle_lowest': typ_ok(S3) and typ_ok(S6),
        'F4_no_type_A_rate_above_good': all(S['types'][k]['A'] <= S['types']['good']['A'] + 1e-12 for S in (S3, S6) for k in S['types']),
        'F5_food_short_le_0.2': all(S['food_short_per_non_idle_country'] <= .2 for S in (S3, S6)),
        'F6_scale_3_vs_6': abs(S6['types']['good']['mean_total'] - S3['types']['good']['mean_total']) <= 3 and abs(S6['types']['good']['AB'] - S3['types']['good']['AB']) <= .1,
        'F7_idle_D_0.9': all(S['types']['idle']['D'] >= .9 for S in (S3, S6)),
    }
    json.dump(res, open(os.path.join(OUT, 'final_sim_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res['criteria'], indent=1))


if __name__ == '__main__':
    run() if sys.argv[1] == 'run' else report()
