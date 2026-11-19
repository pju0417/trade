"""Web-app export targets v3: round DOWN to 5G instead of up (one factor changed from v2).

Pre-registered before running (2026-11-20)
  Motivation (seen in v2 results, so a fresh validation is required): with a tight export
  distribution, rounding P75 UP to 5G can put the target above almost every observed value
  (Tropia: P75 253 -> 255, max 254). Rounding down means "a P75-level student gets full points".
  Calibration  the existing v2 calibration games (results/web_calibrate_v2.jsonl.gz, 180 games),
               target = 5 * floor(max(50, P75) / 5).
  Validation   NEW seeds 196000 + 100*trio + j (j = 0..5), 120 games, H2 students, current code.
  Criteria     W1-W3 exactly as in web_targets.py. v3 is adopted only if all three pass.
  Also reported on the same new games: v2 (round-up) targets.
  Correction (before looking at a rerun): seeds 196000+100*trio+j overlap seed NUMBERS with the
  v2 validation (195000+100*trio+j for trio >= 10; different trios, so different games). The
  experiment is repeated unchanged on unused seeds 300000 + 100*trio + j: `python3 web_targets_floor.py clean`.
"""
import gzip
import json
import math
import os
import statistics as st
import sys
from multiprocessing import Pool

import paths  # noqa: F401
import web_targets as W


def calib_obs():
    with gzip.open(os.path.join(W.OUT, 'web_calibrate_v2.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(l) for l in f]
    obs = {n: [] for n in W.C.ORIGINAL}
    for r in rows:
        for n in r['trio']:
            obs[n].append(r['m'][n]['useful_export_noswap'])
    return obs, len(rows)


def evaluate(val, T):
    c, means = {}, {}
    for n in W.C.ORIGINAL:
        rows = [r['m'][n] for r in val if n in r['trio']]
        tw = [W.total({n: x}, n, T) for x in rows]
        gw = [W.C.grade(t) for t in tw]
        c[n] = {'mean': st.mean(tw), 'min': min(tw), 'grades': {g: gw.count(g) for g in 'ABCD'},
                'ab_share': (gw.count('A') + gw.count('B')) / len(gw),
                'full_export_share': sum(x['useful_export_noswap'] >= T[n] for x in rows) / len(rows),
                'export_pts': st.mean(20 * min(1, x['useful_export_noswap'] / T[n]) for x in rows),
                'export_value_mean': st.mean(x['useful_export_noswap'] for x in rows)}
        means[n] = c[n]['mean']
    crit = {'W1': all(v['mean'] >= 85 and v['ab_share'] >= .8 for v in c.values()),
            'W2': all(.10 <= v['full_export_share'] <= .50 for v in c.values()),
            'W3': max(means.values()) - min(means.values()) <= 10,
            'W3_spread': max(means.values()) - min(means.values())}
    return c, crit


def main():
    obs, ncal = calib_obs()
    p75 = {n: W.p75(v) for n, v in obs.items()}
    T3 = {n: 5 * math.floor(max(50, q) / 5 + 1e-12) for n, q in p75.items()}
    T2 = {n: 5 * math.ceil(max(50, q) / 5 - 1e-12) for n, q in p75.items()}
    clean = 'clean' in sys.argv
    path = os.path.join(W.OUT, 'web_validate_v3_clean.jsonl.gz' if clean else 'web_validate_v3.jsonl.gz')
    if not os.path.exists(path):
        base = 300000 if clean else 196000
        specs = [(i, base + 100 * i + j) for i in range(len(W.TRIOS)) for j in range(6)]
        with Pool(2) as p:
            rows = p.map(W.play_game, specs, chunksize=3)
        with gzip.open(path, 'wt', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r) + '\n')
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        val = [json.loads(l) for l in f]
    c3, k3 = evaluate(val, T3)
    c2, k2 = evaluate(val, T2)
    out = {'calibration_games': ncal, 'validation_games': len(val), 'p75': p75, 'targets_v3_floor': T3,
           'targets_v2_ceil': T2, 'v3': {'countries': c3, 'criteria': k3}, 'v2_on_new_seeds': {'countries': c2, 'criteria': k2}}
    json.dump(out, open(os.path.join(W.OUT, 'web_targets_report_v3_clean.json' if clean else 'web_targets_report_v3.json'), 'w'), ensure_ascii=False, indent=1)
    print('T3', T3, '\nT2', T2)
    for name, c, k in (('v3 floor', c3, k3), ('v2 ceil', c2, k2)):
        print('==', name, k)
        for n, v in c.items():
            print(' ', n, {a: (round(b, 2) if isinstance(b, float) else b) for a, b in v.items()})


if __name__ == '__main__':
    main()
