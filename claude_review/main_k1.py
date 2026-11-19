"""Recommended option: one main-industry level-up = full industrial points (Claude, 2026-11-19).

Context: K = 2 failed I1/J1 (main_industry.py, l3_flat_cost.py). K = 1 was chosen AFTER seeing
those results, so it is tested here as a new, separately pre-registered experiment.

Pre-registered before running (do not change after seeing results)
  Economy      v17 baseline + light + emergency purchase 1.0x + level-3 cost = level-2 cost.
  Score        economic 20 = export measure 'useful_export_noswap' vs its targets;
               industrial capacity 15 = 15*min(1, main-industry level-ups / 1);
               everything else = v17 fixed score.
  Policy       sim_lib.MainIndustryStudent with K = 1 (plan the main industry until one main
               level-up, investing without the AI cash reserve; afterwards normal AI).
  Games        each country focal, seeds 132000-132029 (6x30), paired with the normal games of
               l3_flat_cost.py (same economy and seeds).
  Criteria     K1 one main level-up in >= 80% of games, every country.
               K2 mean satisfaction drop vs paired normal <= 5 and operating-shortage rounds <= 1.
               K3 K1 reach rates differ across countries by <= 0.30.
               K4 export attainment not lower than paired normal by more than 0.05.
  Reported only (for a higher grade later): share of games with a second main level-up, taken
               from the K = 2 student games of l3_flat_cost.py (same economy and seeds).
Usage: python3 main_k1.py run ; python3 main_k1.py report
"""
import gzip
import json
import os
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L
import main_industry as MI

OUT = MI.OUT


def task(spec):
    seed, focal = spec
    try:
        m = L.run_metrics(L.make_game(seed, fee=1.0, l3_flat=True, main_k={focal: 1}))
        return {'seed': seed, 'focal': focal, 'ok': True, 'm': m}
    except Exception as e:
        return {'seed': seed, 'focal': focal, 'ok': False, 'error': repr(e)[:300]}


def run():
    with Pool(2) as p:
        rows = p.map(task, [(x, n) for n in L.NAMES for x in MI.STRESS], chunksize=4)
    with gzip.open(os.path.join(OUT, 'main_k1_games.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def report():
    rows = MI.load('main_k1_games.jsonl.gz')
    l3 = MI.load('l3_flat_games.jsonl.gz')
    pair = {r['seed']: r for r in l3 if r['tag'] == 'stress'}
    T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    MI.K = 1
    out, crit = MI.evaluate(rows, pair, T)
    crit = {k.replace('I', 'K', 1): v for k, v in crit.items()}
    k2 = [r for r in l3 if r['tag'] == 'student']
    for n in L.NAMES:
        rs = [r for r in k2 if r['focal'] == n]
        out[n]['second_levelup_share_k2_policy'] = sum(MI.main_ups(r['m'], n) >= 2 for r in rs) / len(rs)
        out[n]['normal_ai_industrial_points'] = sum(15 * min(1, MI.main_ups(pair[s]['m'], n)) for s in pair) / len(pair)
    res = {'K': 1, 'countries': out, 'criteria': crit, 'games': len(rows)}
    json.dump(res, open(os.path.join(OUT, 'main_k1_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    run() if sys.argv[1] == 'run' else report()
