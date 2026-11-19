"""Option 1: industrial target counts only level-ups of the country's main industry (Claude, 2026-11-19).

Pre-registered before running (do not change after seeing results)
  Economy      v17 baseline + operating 'light' + emergency purchase 1.0x.
  Score        economic 20 = 'useful_export_noswap' vs its targets (export_noswap_report.json);
               industrial capacity 15 = 15*min(1, main-industry level-ups / 2) for all six
               countries (main = initial main industry: Tropia banana, Grainia wheat, Oilia fuel,
               Mechania machine, Mineria ore, Technia electronics; i.e. reach level 3).
               Everything else = v17 fixed score.
  Policy       sim_lib.MainIndustryStudent: focal country plans its main industry every round
               until 2 main level-ups, investing without the AI-only cash reserve.
  Games        each country focal, seeds 132000-132029 (6x30); paired with the stored normal
               games of industrial_levelup.py (same economy and seeds).
  Criteria     I1 reach K=2 in >= 80% of games, every country.
               I2 mean satisfaction drop vs paired normal <= 5 and operating-shortage rounds <= 1.
               I3 I1 reach rates differ across countries by <= 0.30.
               I4 export attainment not lower than paired normal by more than 0.05, every country.
Usage: python3 main_industry.py run ; python3 main_industry.py report
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
K = 2
STRESS = range(132000, 132030)
NAME = os.environ.get('MAIN_INDUSTRY_TAG', 'main_industry')


def make(seed, focal):
    return L.make_game(seed, fee=1.0, main_k={focal: K})


def task(spec):
    seed, focal = spec
    try:
        return {'seed': seed, 'focal': focal, 'ok': True, 'm': L.run_metrics(make(seed, focal))}
    except Exception as e:
        return {'seed': seed, 'focal': focal, 'ok': False, 'error': repr(e)[:300]}


def run():
    with Pool(2) as p:
        rows = p.map(task, [(x, n) for n in L.NAMES for x in STRESS], chunksize=4)
    with gzip.open(os.path.join(OUT, f'{NAME}_games.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def load(name):
    with gzip.open(os.path.join(OUT, name), 'rt', encoding='utf-8') as f:
        rows = [json.loads(x) for x in f]
    assert all(r['ok'] for r in rows)
    return rows


MAIN = {'Tropia': 'banana', 'Grainia': 'wheat', 'Oilia': 'fuel', 'Mechania': 'machine',
        'Mineria': 'ore', 'Technia': 'electronics'}


def main_ups(m, n):
    # older stored games lack the field: count main-industry entries in the upgrade path
    return m[n]['main_ups'] if 'main_ups' in m[n] else sum(g == MAIN[n] for _, g, _lv in m[n]['upgrade_path'])


def evaluate(rows, pair, T):
    mean = lambda a: sum(a) / len(a)
    econ = lambda m, n: min(1, m[n]['useful_export_noswap'] / T[n])
    cap = lambda m, n: 15 * min(1, main_ups(m, n) / K)
    score = lambda m, n: m[n]['score'] - m[n]['econ_old'] + 20 * econ(m, n) - m[n]['cap_old'] + cap(m, n)
    out = {}
    for n in L.NAMES:
        rs = [r for r in rows if r['focal'] == n]
        out[n] = {
            'reach': mean([main_ups(r['m'], n) >= K for r in rs]),
            'normal_ai_reach': mean([main_ups(pair[r['seed']]['m'], n) >= K for r in rs]),
            'mean_main_ups': mean([r['m'][n]['main_ups'] for r in rs]),
            'blocked_attempts': mean([r['m'][n]['blocked'] for r in rs]),
            'd_happy': mean([r['m'][n]['happy'] - pair[r['seed']]['m'][n]['happy'] for r in rs]),
            'op_short': mean([r['m'][n]['op_short'] for r in rs]),
            'econ_attain': mean([econ(r['m'], n) for r in rs]),
            'econ_attain_normal': mean([econ(pair[r['seed']]['m'], n) for r in rs]),
            'score': mean([score(r['m'], n) for r in rs]),
            'score_normal_same_rule': mean([score(pair[r['seed']]['m'], n) for r in rs]),
            'better_than_normal': sum(score(r['m'], n) > score(pair[r['seed']]['m'], n) + 1e-9 for r in rs),
            'cash_by_round': [round(mean([r['m'][n]['cash_rounds'][i] for r in rs]), 1) for i in range(9)],
        }
    reach = [out[n]['reach'] for n in L.NAMES]
    crit = {'I1_reach_ge_0.8': all(x >= .8 for x in reach),
            'I2_burden': all(out[n]['d_happy'] >= -5 and out[n]['op_short'] <= 1 for n in L.NAMES),
            'I3_range_le_0.3': max(reach) - min(reach) <= .3,
            'I4_export_not_lower_0.05': all(out[n]['econ_attain'] >= out[n]['econ_attain_normal'] - .05 for n in L.NAMES)}
    return out, crit


def report():
    rows = load(f'{NAME}_games.jsonl.gz')
    pair = {r['seed']: r for r in load('levelup_games.jsonl.gz') if r['tag'] == 'stress' and r['style'] == 'normal'}
    T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    out, crit = evaluate(rows, pair, T)
    res = {'K': K, 'countries': out, 'criteria': crit, 'games': len(rows)}
    json.dump(res, open(os.path.join(OUT, f'{NAME}_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    run() if sys.argv[1] == 'run' else report()
