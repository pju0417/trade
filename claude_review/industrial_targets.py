"""Diagnosis of industrial (capacity) targets: what each target means in upgrades and gold.

No rule or target is changed; 0 new games. Reads export_valid.jsonl.gz (normal play,
seeds 130000-130099, v17 baseline + light + emergency purchase 1.0x).
For each original country, enumerates level combinations reachable by upgrading existing
industries and the designated expansion industry (each to level <= 4, at most 7 upgrades
because AI/students may invest once per round in R1-R7), using the engine's own
upgrade_cost / upgrade_requirements / capacity functions.
"""
import copy
import gzip
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sim_lib as L

GOAL = L.GOALS['industrial_steps']


def combos(game, c):
    inds = list(c.levels) + ([c.expand] if c.expand not in c.levels else [])
    cap0 = game.capacity(c)
    out = []
    ranges = [range(c.levels.get(g, 0), 5) for g in inds]
    for target in itertools.product(*ranges):
        n = copy.deepcopy(c)
        cost = ore = steps = 0; machine = 0
        for g, lv in zip(inds, target):
            while n.levels.get(g, 0) < lv:
                cost += game.upgrade_cost(n, g)
                o, m = game.upgrade_requirements(n, g)
                ore += o; machine = max(machine, m); steps += 1
                n.levels[g] = n.levels.get(g, 0) + 1; n.bases.setdefault(g, 1)
        if steps > 7:
            continue
        out.append({'levels': dict(zip(inds, target)), 'cost': cost, 'ore': ore,
                    'machine_grade': machine, 'upgrades': steps,
                    'growth': (game.capacity(n) - cap0) / cap0})
    return out


def main():
    game = L.make_game(130000, fee=1.0)  # fresh state: initial levels only
    rows = [json.loads(x) for x in gzip.open(os.path.join(HERE, 'new_games', 'export_valid.jsonl.gz'), 'rt')]
    normal = [r for r in rows if r['tag'] == 'valid']
    mean = lambda a: sum(a) / len(a)
    res = {}
    for name in L.NAMES:
        c = game.cs[name]
        cs = combos(game, c)
        ok = [x for x in cs if x['growth'] >= GOAL[name] - 1e-12]
        cheapest = min(ok, key=lambda x: (x['cost'], x['upgrades']))
        fewest = min(ok, key=lambda x: (x['upgrades'], x['cost']))
        m = [r['m'][name] for r in normal]
        income = mean([x['tax'] + x['revenue'] for x in m])
        res[name] = {
            'target_growth': GOAL[name], 'start_levels': dict(c.levels), 'expand': c.expand,
            'cheapest': cheapest, 'fewest_upgrades': fewest,
            'max_growth_7_upgrades': max(x['growth'] for x in cs),
            'normal_play': {'reach': mean([x['capacity_growth'] >= GOAL[name] - 1e-12 for x in m]),
                            'no_growth_share': mean([x['capacity_growth'] <= 1e-12 for x in m]),
                            'mean_growth': mean([x['capacity_growth'] for x in m]),
                            'mean_investment': mean([x['investment'] for x in m]),
                            'mean_income_tax_plus_sales': income},
            'cheapest_cost_over_income': cheapest['cost'] / income,
            # cheapest way to make k upgrades (any industries), k = 1..4
            'by_upgrades': {k: {'cost': b['cost'], 'cost_over_income': b['cost'] / income,
                                'growth': b['growth'], 'levels': b['levels'], 'ore': b['ore'],
                                'machine_grade': b['machine_grade']}
                            for k in range(1, 5)
                            for b in [min((x for x in cs if x['upgrades'] == k), key=lambda x: (x['cost'], -x['growth']))]},
        }
    path = os.path.join(HERE, 'new_games', 'industrial_targets.json')
    json.dump(res, open(path, 'w'), ensure_ascii=False, indent=1)
    for n, v in res.items():
        ch, np_ = v['cheapest'], v['normal_play']
        print(n, 'target', round(v['target_growth'], 3), '| cheapest', ch['levels'], ch['cost'], 'G', ch['upgrades'], 'upg',
              'ore', ch['ore'], 'mg', ch['machine_grade'], '| fewest', v['fewest_upgrades']['upgrades'], 'upg',
              v['fewest_upgrades']['cost'], 'G | max7', round(v['max_growth_7_upgrades'], 2),
              '| reach', np_['reach'], 'none', np_['no_growth_share'], 'inv', round(np_['mean_investment'], 1),
              'income', round(np_['mean_income_tax_plus_sales'], 1), 'cost/income', round(v['cheapest_cost_over_income'], 2))
        print('   by upgrades', {k: (b['cost'], round(b['cost_over_income'], 2), b['ore'], b['machine_grade']) for k, b in v['by_upgrades'].items()})


if __name__ == '__main__':
    main()
