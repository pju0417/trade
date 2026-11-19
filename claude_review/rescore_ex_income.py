"""Experiment 3a (pre-registered before computing; rescoring only, 0 new games).

One factor changed: the economic-growth measure becomes asset_gain - automatic national
income (tax). Everything else (45% capital, P75/floor 50/step 5 method, calibration rows
of condition B, validation rows) is unchanged.
Criteria (same as recalibrate_targets.py):
  C1 idle economic attainment mean < 0.8 for all 6 countries.
  C2 normal-play economic-target reach range narrower than v15 targets (0.83).
"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import recalibrate_targets as RT
import sim_lib as L
cal = RT.load('B'); valid = RT.load('valid')
keyed = {(r['focal'], r['style'], r['seed']): r for r in cal}
ex = lambda m: m['asset_gain'] - m['tax']
targets, p75 = {}, {}
for n in L.NAMES:
    v = [ex(keyed[(None if s == 'normal' else n, s, x)]['m'][n]) for s in ('normal', 'invest', 'trade') for x in RT.CAL_SEEDS]
    p75[n] = RT.quantile(v); targets[n] = 5 * math.ceil(max(50, p75[n]) / 5 - 1e-12)
normal = [r for r in valid if r['style'] == 'normal']; idle = [r for r in valid if r['style'] == 'idle']
reach = {n: sum(ex(r['m'][n]) >= targets[n] for r in normal) / len(normal) for n in L.NAMES}
att = {n: sum(min(1, max(0, ex(r['m'][n]) / targets[n])) for r in normal) / len(normal) for n in L.NAMES}
idle_att = {n: sum(ex(r['m'][n]) for r in idle if r['focal'] == n) / 30 / targets[n] for n in L.NAMES}
res = {'targets': targets, 'raw_p75': p75, 'normal_reach': reach, 'normal_attainment_mean': att,
       'idle_attainment': idle_att, 'reach_range': max(reach.values()) - min(reach.values()),
       'criteria': {'C1': all(v < .8 for v in idle_att.values()),
                    'C2': max(reach.values()) - min(reach.values()) < .83}, 'new_games': 0}
json.dump(res, open(os.path.join(HERE, 'new_games', 'rescore_ex_income.json'), 'w'), ensure_ascii=False, indent=1)
r = lambda d: {k: round(v, 3) for k, v in d.items()}
for k in ('targets', 'raw_p75', 'normal_reach', 'normal_attainment_mean', 'idle_attainment'): print(k, r(res[k]))
print('range', round(res['reach_range'], 3), res['criteria'])
