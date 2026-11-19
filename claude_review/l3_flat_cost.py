"""Option 3: make the mid-game level-up affordable (Claude, 2026-11-19).

Why this factor: in option 1 (main_industry.py) five of six countries could not reach main
industry level 3 because, in R2-R7, they never held its cost (115-185G, plus ore). Cash builds
up only after R7. The cost step chosen to test: level 3 costs the same as level 2 (the 1.5x
step is removed; the 2x step to level 4 and all ore/machine requirements are unchanged). It
applies to every country, AI included.

Pre-registered before running (do not change after seeing results)
  One factor   upgrade cost to level 3: base x1.5 -> base x1 (sim_lib.Emergency.l3_flat).
               Economy otherwise: v17 baseline + light + emergency purchase 1.0x.
  Score        same as main_industry.py (export economic score; industrial = main-industry
               level-ups / 2).
  Games        normal AI under the new cost: seeds 130000-130099 (100) and 132000-132029 (30);
               main-industry student policy for each country, seeds 132000-132029 (6x30).
               Student games are paired with normal games under the SAME new cost.
  Criteria     J1-J4 = I1-I4 of main_industry.py under the new cost.
               J5 side effect, normal AI play (seeds 130000-130099), new vs old cost: operating
                  shortage country-rounds per game of the six original countries rise by <= 0.5
                  (the old-cost runs stored only per-country values for these six) and their
                  mean satisfaction falls by <= 1 point.
Usage: python3 l3_flat_cost.py run ; python3 l3_flat_cost.py report
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
    tag, seed, focal = spec
    kw = dict(fee=1.0, l3_flat=True)
    if focal:
        kw['main_k'] = {focal: MI.K}
    try:
        g = L.make_game(seed, **kw)
        m = L.run_metrics(g)
        return {'tag': tag, 'seed': seed, 'focal': focal, 'ok': True, 'm': m,
                'op_short_world': sum(e['missing']['ore'] > 0 or e['missing']['fuel'] > 0 for e in g.operating_ledger)}
    except Exception as e:
        return {'tag': tag, 'seed': seed, 'focal': focal, 'ok': False, 'error': repr(e)[:300]}


def run():
    sp = [('valid', x, None) for x in range(130000, 130100)]
    sp += [('stress', x, None) for x in MI.STRESS]
    sp += [('student', x, n) for n in L.NAMES for x in MI.STRESS]
    with Pool(2) as p:
        rows = p.map(task, sp, chunksize=4)
    with gzip.open(os.path.join(OUT, 'l3_flat_games.jsonl.gz'), 'wt', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')
    bad = [r for r in rows if not r['ok']]
    print('games', len(rows), 'ok', len(rows) - len(bad), 'fail', len(bad), bad[:2])


def report():
    rows = MI.load('l3_flat_games.jsonl.gz')
    T = json.load(open(os.path.join(OUT, 'export_noswap_report.json')))['targets_useful_export']
    pair = {r['seed']: r for r in rows if r['tag'] == 'stress'}
    out, crit = MI.evaluate([r for r in rows if r['tag'] == 'student'], pair, T)
    crit = {k.replace('I', 'J', 1): v for k, v in crit.items()}
    # J5 side effects vs old cost: old normal games = industrial_levelup 'valid' rows (same economy, seeds)
    old = {r['seed']: r for r in MI.load('levelup_games.jsonl.gz') if r['tag'] == 'valid'}
    new = [r for r in rows if r['tag'] == 'valid']
    mean = lambda a: sum(a) / len(a)
    old_short = mean([sum(old[r['seed']]['m'][n]['op_short'] for n in L.NAMES) for r in new])
    new_short = mean([sum(r['m'][n]['op_short'] for n in L.NAMES) for r in new])
    happy_old = mean([mean([old[r['seed']]['m'][n]['happy'] for n in L.NAMES]) for r in new])
    happy_new = mean([mean([r['m'][n]['happy'] for n in L.NAMES]) for r in new])
    side = {'op_short_6country_per_game_old': old_short, 'op_short_6country_per_game_new': new_short,
            'op_short_9country_per_game_new': mean([r['op_short_world'] for r in new]),
            'happy6_old': happy_old, 'happy6_new': happy_new,
            'normal_ai': {n: {'mean_upgrades_old': mean([old[r['seed']]['m'][n]['upgrades'] for r in new]),
                              'mean_upgrades_new': mean([r['m'][n]['upgrades'] for r in new]),
                              'main_reach_new': mean([MI.main_ups(r['m'], n) >= MI.K for r in new]),
                              'econ_attain_old': mean([min(1, old[r['seed']]['m'][n]['useful_export_noswap'] / T[n]) for r in new]),
                              'econ_attain_new': mean([min(1, r['m'][n]['useful_export_noswap'] / T[n]) for r in new])}
                          for n in L.NAMES}}
    # J5 uses the six original countries' shortages: the old runs did not store 9-country totals.
    crit['J5_side_effects'] = (new_short - old_short <= .5) and (happy_old - happy_new <= 1)
    res = {'countries': out, 'side_effects': side, 'criteria': crit, 'games': len(rows),
           'note': 'J5 shortage check uses the six original countries (9-country totals were not stored for the old-cost runs).'}
    json.dump(res, open(os.path.join(OUT, 'l3_flat_report.json'), 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    run() if sys.argv[1] == 'run' else report()
