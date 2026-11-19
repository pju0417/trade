"""Re-derive country targets on the new economy with the v15 method (Claude, 2026-11-19).

Pre-registered before running (do not change after seeing results):
  Conditions   A = v17 engine, operating 'none'        (separates engine drift since v12)
               B = v17 engine, operating 'light' + emergency purchase 1.0x base price
  Calibration  seeds 90000-90059 (separate from validation seeds 130000/132000);
               per condition: all-normal game + each original country as focal 'invest'
               and 'trade' -> 60 + 6*2*60 = 780 games; 180 own samples per country,
               equal policy weight, peers' outcomes under another country's policy excluded.
  Method       economic = 5*ceil(max(50, P75(asset_gain))/5), asset_gain with 45% capital;
               industrial = smallest observed own-policy capacity growth >= max(P75, 0.10).
  Validation   condition B, normal seeds 130000-130099 (100) and each country idle
               seeds 132000-132029 (6*30).
  Criteria     C1 idle student's economic attainment (gain/target) mean < 0.8 for all 6.
               C2 normal-play share reaching the economic target: range across countries
                  narrower with new targets than with v15 targets on the same games.
               C3 same for industrial targets, and every country reaches it in >= 1 game.

Usage: python3 recalibrate_targets.py run <A|B|valid> ; python3 recalibrate_targets.py report
"""
import gzip
import json
import math
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

OUT = os.path.join(HERE, 'new_games')
CAL_SEEDS = range(90000, 90060)
COND = {'A': dict(profile='none', fee=None), 'B': dict(profile='light', fee=1.0)}


def task(spec):
    tag, cond, seed, focal, style = spec
    try:
        g = L.make_game(seed, focal=focal, style=style, **COND[cond]) if style != 'idle' else \
            L.make_game(seed, behaviors={focal: 'idle'}, **COND[cond])
        return {'tag': tag, 'cond': cond, 'seed': seed, 'focal': focal, 'style': style,
                'ok': True, 'm': L.run_metrics(g)}
    except Exception as e:  # recorded, never silently dropped
        return {'tag': tag, 'cond': cond, 'seed': seed, 'focal': focal, 'style': style,
                'ok': False, 'error': repr(e)[:300]}


def specs_for(stage):
    if stage in COND:
        s = [('cal', stage, x, None, 'normal') for x in CAL_SEEDS]
        s += [('cal', stage, x, n, st) for n in L.NAMES for st in ('invest', 'trade') for x in CAL_SEEDS]
        return s
    if stage == 'valid':
        s = [('valid', 'B', x, None, 'normal') for x in range(130000, 130100)]
        s += [('valid', 'B', x, n, 'idle') for n in L.NAMES for x in range(132000, 132030)]
        return s
    raise SystemExit('unknown stage')


def run(stage):
    specs = specs_for(stage)
    with Pool(2) as p:
        rows = p.map(task, specs, chunksize=4)
    path = os.path.join(OUT, f'recal_{stage}.jsonl.gz')
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print(stage, 'games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def load(stage):
    with gzip.open(os.path.join(OUT, f'recal_{stage}.jsonl.gz'), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows), 'failed games present'
    return rows


def quantile(a, q=.75):
    a = sorted(a); pos = (len(a) - 1) * q; lo = math.floor(pos); w = pos - lo
    return a[lo] * (1 - w) + a[min(lo + 1, len(a) - 1)] * w


def derive(rows):
    keyed = {(r['focal'], r['style'], r['seed']): r for r in rows}
    out = {'economic': {}, 'industrial': {}, 'raw_p75': {}}
    for n in L.NAMES:
        gains, growths = [], []
        for style in ('normal', 'invest', 'trade'):
            focal = None if style == 'normal' else n
            for s in CAL_SEEDS:
                m = keyed[(focal, style, s)]['m'][n]
                gains.append(m['asset_gain']); growths.append(m['capacity_growth'])
        assert len(gains) == 180
        pe, pi = quantile(gains), quantile(growths)
        out['economic'][n] = 5 * math.ceil(max(50, pe) / 5 - 1e-12)
        floor = max(pi, .10)
        out['industrial'][n] = min(g for g in growths if g >= floor - 1e-12)
        out['raw_p75'][n] = {'economic': pe, 'industrial': pi}
    return out


def report():
    old = {'economic': L.GOALS['economic_old'], 'industrial': L.GOALS['industrial_steps']}
    tA, tB = derive(load('A')), derive(load('B'))
    valid = load('valid')
    normal = [r for r in valid if r['style'] == 'normal']
    idle = [r for r in valid if r['style'] == 'idle']

    def reach(rows, targets, key, metric):
        return {n: sum(r['m'][n][metric] >= targets[key][n] - 1e-12 for r in rows) / len(rows) for n in L.NAMES}

    res = {'targets': {'v15': old, 'A_v17_none': {k: tA[k] for k in ('economic', 'industrial')},
                       'B_light_fee1': {k: tB[k] for k in ('economic', 'industrial')}},
           'raw_p75': {'A': tA['raw_p75'], 'B': tB['raw_p75']}}
    for label, t in (('v15', old), ('B', tB)):
        er = reach(normal, t, 'economic', 'asset_gain')
        ir = reach(normal, t, 'industrial', 'capacity_growth')
        idle_ratio = {n: sum(r['m'][n]['asset_gain'] for r in idle if r['focal'] == n) / 30 / t['economic'][n]
                      for n in L.NAMES}
        tax_ratio = {n: sum(r['m'][n]['tax'] for r in normal) / len(normal) / t['economic'][n] for n in L.NAMES}
        res[label] = {'normal_econ_reach': er, 'normal_ind_reach': ir,
                      'econ_reach_range': max(er.values()) - min(er.values()),
                      'ind_reach_range': max(ir.values()) - min(ir.values()),
                      'idle_econ_attainment': idle_ratio, 'auto_income_over_target': tax_ratio,
                      'normal_econ_attainment_mean': {n: sum(min(1, r['m'][n]['asset_gain'] / t['economic'][n]) for r in normal) / len(normal) for n in L.NAMES},
                      'normal_ind_attainment_mean': {n: sum(min(1, r['m'][n]['capacity_growth'] / t['industrial'][n]) for r in normal) / len(normal) for n in L.NAMES}}
    res['criteria'] = {
        'C1_idle_econ_below_0.8_all': all(v < .8 for v in res['B']['idle_econ_attainment'].values()),
        'C2_econ_reach_range_narrower': res['B']['econ_reach_range'] < res['v15']['econ_reach_range'],
        'C3_ind_reach_range_narrower': res['B']['ind_reach_range'] < res['v15']['ind_reach_range'],
        'C3_every_country_reaches_ind': all(v > 0 for v in res['B']['normal_ind_reach'].values()),
    }
    res['games'] = {'A': len(load('A')), 'B': len(load('B')), 'valid': len(valid)}
    path = os.path.join(OUT, 'recal_report.json')
    json.dump(res, open(path, 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    if sys.argv[1] == 'run':
        run(sys.argv[2])
    elif sys.argv[1] == 'report':
        report()
