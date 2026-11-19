"""Web-app export targets from human-style play (user decision 2026-11-20: option 2).

Pre-registered before running (do not change after seeing results)
  One factor changed from final_validation.targets(): how the student country is played.
    simulator targets  AI-like students in the AI economy (P75, min 50, round up to 5G)
    web targets        policy H2 (human_policy_h2.py) in classroom.Session, same formula
  Calibration  all 20 trios of the 6 original countries x 9 seeds (180 games), every country of
               the trio is an H2 student; seeds 180000 + 100*trio + j (j = 0..8).
               Each country: 90 observations of useful_export_noswap.
               Target = 5 * ceil(max(50, P75) / 5)  (P75 by linear interpolation, as before).
  Validation   separate seeds 190000 + 100*trio + j (j = 0..5), 120 games, scored with the
               new targets (H2 students). Criteria:
    W1  every country: H2 mean total >= 85 and A+B share >= 80%
    W2  every country: share of student-games at full export points between 10% and 50%
    W3  max - min of the six countries' H2 mean totals <= 10 points
  Also reported (no criterion): the same validation games scored with the simulator targets.
v2 (pre-registered 2026-11-20, after the phase-order fix E1 in order_fix_eval.py): the same design
  and criteria W1-W3 with the new phase order. Calibration seeds as above (new runs); validation on
  NEW seeds 195000 + 100*trio + j (j = 0..5) because 190000 was used to evaluate E1.
  Files: web_calibrate_v2, web_validate_v2, web_targets_report_v2.json.
Usage: python3 web_targets.py calibrate | validate | report  [v2]
"""
import gzip
import itertools
import json
import math
import os
import statistics as st
import sys
from multiprocessing import Pool

import paths  # noqa: F401
import classroom as C
import human_policy_h2 as H2

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
TRIOS = list(itertools.combinations(C.ORIGINAL, 3))
SIM_TARGETS = dict(C.SIM_TARGETS) if hasattr(C, 'SIM_TARGETS') else dict(C.TARGETS)


def play_game(spec):
    trio_i, seed = spec
    trio = list(TRIOS[trio_i])
    s = C.Session(seed, trio)
    while s.phase != 'finished':
        for n in trio:
            H2.play(s, n)
        assert s.apply({'type': 'advance'})['ok']
    import sim_lib as L
    m = L.run_metrics(s.g)
    return {'trio': trio, 'seed': seed, 'm': {n: m[n] for n in C.ORIGINAL}}


V = '_v2' if 'v2' in sys.argv else ''


def run(kind):
    base, k = (180000, 9) if kind == 'calibrate' else ((195000 if V else 190000), 6)
    specs = [(i, base + 100 * i + j) for i in range(len(TRIOS)) for j in range(k)]
    with Pool(2) as p:
        rows = p.map(play_game, specs, chunksize=3)
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(os.path.join(OUT, f'web_{kind}{V}.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    print(kind, 'games', len(rows))


def load(kind):
    with gzip.open(os.path.join(OUT, f'web_{kind}{V}.jsonl.gz'), 'rt', encoding='utf-8') as f:
        return [json.loads(l) for l in f]


def p75(v):
    v = sorted(v); pos = (len(v) - 1) * .75; lo = math.floor(pos); w = pos - lo
    return v[lo] * (1 - w) + v[min(lo + 1, len(v) - 1)] * w


def web_targets():
    obs = {n: [] for n in C.ORIGINAL}
    for r in load('calibrate'):
        for n in r['trio']:
            obs[n].append(r['m'][n]['useful_export_noswap'])
    T = {n: 5 * math.ceil(max(50, p75(v)) / 5 - 1e-12) for n, v in obs.items()}
    return T, {n: len(v) for n, v in obs.items()}, {n: {'median': st.median(v), 'p75': p75(v), 'max': max(v)}
                                                     for n, v in obs.items()}


def total(m, n, T):
    x = m[n]
    return (x['score'] - x['econ_old'] + 20 * min(1, x['useful_export_noswap'] / T[n]) - x['cap_old']
            + (15 if x['main_ups'] >= 1 else 0) - min(x['happy'] / 4, x['op_short']))


def report():
    T, nobs, dist = web_targets()
    val = load('validate')
    out = {'web_targets': T, 'sim_targets': SIM_TARGETS, 'observations': nobs, 'calibration_export': dist,
           'validation_games': len(val), 'countries': {}}
    means = {}
    for n in C.ORIGINAL:
        rows = [r['m'][n] for r in val if n in r['trio']]
        tw = [total({n: x}, n, T) for x in rows]
        ts = [total({n: x}, n, SIM_TARGETS) for x in rows]
        gw = [C.grade(t) for t in tw]
        full = sum(x['useful_export_noswap'] >= T[n] for x in rows) / len(rows)
        means[n] = st.mean(tw)
        out['countries'][n] = {
            'n': len(rows), 'mean_web': st.mean(tw), 'mean_sim_targets': st.mean(ts),
            'grades_web': {g: gw.count(g) for g in 'ABCD'}, 'ab_share': (gw.count('A') + gw.count('B')) / len(gw),
            'full_export_share': full, 'export_pts_web': st.mean(20 * min(1, x['useful_export_noswap'] / T[n]) for x in rows),
            'export_value_mean': st.mean(x['useful_export_noswap'] for x in rows), 'min_web': min(tw)}
    c = out['countries']
    out['criteria'] = {
        'W1': all(v['mean_web'] >= 85 and v['ab_share'] >= .8 for v in c.values()),
        'W2': all(.10 <= v['full_export_share'] <= .50 for v in c.values()),
        'W3': max(means.values()) - min(means.values()) <= 10,
        'W3_spread': max(means.values()) - min(means.values()),
    }
    json.dump(out, open(os.path.join(OUT, f'web_targets_report{V}.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    {'calibrate': lambda: run('calibrate'), 'validate': lambda: run('validate'), 'report': report}[sys.argv[1]]()
