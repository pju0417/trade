"""v15 pure score candidates; no game actions, no price or production changes.

Capital means a game bookkeeping convention, not resale or liquidation value.
Targets are fitted exclusively to the already separated v12 calibration set.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAMES = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')
ADDED = ('Novia', 'Agrea', 'Ferria')
VIEWS = ('legacy', 'targets', 'steps', 'capital', 'steps_capital', 'capital_fixed_goal')
OFFICIAL_ECON = dict(zip(NAMES, (250, 240, 140, 160, 140, 160)))
OFFICIAL_INDUSTRY = dict(zip(NAMES, (.90, .90, .48, .25, .48, .27)))
WEIGHTS = dict(economic_growth=20, reserve=5, capacity=15,
               utilization=10, wellbeing=25, trade=25)
CALIBRATION_SHA = 'a87d6cc7fc622e1c800b2a5f50f9245320b637f5cb3aef1f272247cb9c38719b'
OLD_GOALS_SHA = '47e78fe6a9cebab256bb52a3b7dbef9c9b46cec4363d15700290ddfa2e4620d5'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def finite(x):
    if type(x) not in (int, float) or not math.isfinite(x):
        raise ValueError('finite numeric value required')
    return x


def clip(x):
    return min(1.0, max(0.0, finite(x)))


def quantile(values, q=.75):
    a = sorted(finite(x) for x in values)
    if not a or not 0 <= q <= 1:
        raise ValueError('nonempty sample and valid quantile required')
    pos = (len(a)-1)*q
    lo = math.floor(pos)
    w = pos-lo
    return a[lo]*(1-w)+a[min(lo+1, len(a)-1)]*w


def make_targets(calibration, old_path, opportunities):
    if digest(calibration) != CALIBRATION_SHA or digest(old_path) != OLD_GOALS_SHA:
        raise ValueError('Calibration or original targets changed')
    old = json.loads(Path(old_path).read_text())
    steps = json.loads(Path(opportunities).read_text())
    if steps.get('status') not in ('PASS', 'passed'):
        raise ValueError('Attainability review must pass before target freezing')
    with gzip.open(calibration, 'rt') as f:
        rows = [json.loads(line) for line in f]
    seeds = list(range(90000, 90060))
    cases = {'None:normal': (None, 'normal')}
    cases.update({f'{n}:{s}': (n, s) for n in NAMES for s in ('invest', 'trade')})
    expected = {(sid, seed) for sid in cases for seed in seeds}
    keyed = {}
    for r in rows:
        key = (r['scenario'], r['seed'])
        assert r['phase'] == 'calibration' and key in expected and key not in keyed
        assert (r['focal'], r['style']) == cases[r['scenario']]
        keyed[key] = r
    assert len(rows) == 780 and set(keyed) == expected
    economic = {}; raw = {}; by_policy = {}; matched_old = {}
    for name in NAMES:
        samples = []; original = []; by_policy[name] = {}
        for style in ('normal', 'invest', 'trade'):
            case = 'None:normal' if style == 'normal' else f'{name}:{style}'
            policy = []
            for seed in seeds:
                m = keyed[case, seed]['countries'][name]['growth_metrics']
                gain = finite(m['asset_gain'])
                investment = finite(m['investment'])
                assert investment >= 0
                policy.append(gain + .55*investment)
                original.append(gain)
            by_policy[name][style] = {'n': len(policy), 'mean': sum(policy)/len(policy),
                                      'p75': quantile(policy)}
            samples.extend(policy)
        assert len(samples) == 180
        raw[name] = quantile(samples)
        economic[name] = 5*math.ceil(max(50, raw[name])/5-1e-12)
        matched_old[name] = 5*math.ceil(max(50, quantile(original))/5-1e-12)
        assert matched_old[name] == old['economic'][name]
        assert math.isclose(old['raw_quantiles']['economic'][name], quantile(original), abs_tol=1e-8)
        assert finite(steps['industrial'][name]) > 0
        assert math.isclose(steps['industrial'][name], old['raw_quantiles']['industrial'][name], abs_tol=1e-12)
    return {
        'schema': 'v15-score-targets-1',
        'status': 'FROZEN_CANDIDATES',
        'meaning': 'Research comparison candidates; original game result score remains unchanged.',
        'names': list(NAMES), 'views': list(VIEWS), 'weights': WEIGHTS,
        'calibration': {'source': 'existing_v12_calibration_only', 'sha256': CALIBRATION_SHA,
                        'unique_archived_games': 780, 'seeds': seeds,
                        'policies': ['normal', 'invest', 'trade'], 'samples_per_country': 180,
                        'equal_policy_weight': True, 'peer_policy_outcomes_excluded': True,
                        'new_calibration_games': 0},
        'method': {'economic_quantile': .75, 'economic_floor': 50, 'economic_step': 5,
                   'industrial': 'Smallest actually observed calibration growth at or above the original raw P75, without percent rounding.',
                   'capital_recognition_fraction': 1.0, 'previous_capital_fraction': .45,
                   'curve': 'linear capped at target; no headroom curve'},
        'source_old_targets_sha256': OLD_GOALS_SHA,
        'target_opportunities_sha256': digest(opportunities),
        'economic_old': old['economic'], 'economic_capital': economic,
        'raw_economic_capital': raw, 'capital_calibration_by_policy': by_policy,
        'industrial_old': old['industrial'], 'industrial_steps': steps['industrial'],
        'official_economic': OFFICIAL_ECON, 'official_industrial': OFFICIAL_INDUSTRY,
        'warnings': [
            'A bookkeeping convention for the game; neither liquidation prices nor real-world accounting advice.',
            'Includes development and research cash spending as capital; no depreciation or proof of usefulness.',
            'Automatic satisfaction-linked income and inventory valuations are kept.',
            'Targets are not fitted to v13, v14, smoke or v15 formal validation outcomes.',
            'AI policies do not read these alternative scores.'
        ]
    }


def validate_targets(goals):
    if goals.get('schema') != 'v15-score-targets-1' or goals.get('views') != list(VIEWS):
        raise ValueError('Unexpected target schema/views')
    assert goals['weights'] == WEIGHTS and goals['names'] == list(NAMES)
    assert goals['calibration']['sha256'] == CALIBRATION_SHA
    assert goals['source_old_targets_sha256'] == OLD_GOALS_SHA
    assert goals['method']['capital_recognition_fraction'] == 1.0
    for field in ('economic_old', 'economic_capital', 'industrial_old', 'industrial_steps',
                  'official_economic', 'official_industrial'):
        assert set(goals[field]) == set(NAMES)
        assert all(finite(x) > 0 for x in goals[field].values())


def metric_view(m, economic_goal, industrial_goal, neutral):
    gain = finite(m['asset_gain']) + (.55*finite(m['investment']) if neutral else 0.0)
    growth = finite(m['capacity_growth'])
    econ = 20*clip(gain/economic_goal)
    capacity = 15*clip(growth/industrial_goal)
    out = dict(economic_target=economic_goal, industrial_target=industrial_goal,
               economic_gain=gain, economic_ratio=gain/economic_goal,
               industrial_ratio=growth/industrial_goal,
               economic_growth=econ, reserve=finite(m['reserve_score']), capacity=capacity,
               utilization=finite(m['utilization_score']), wellbeing=finite(m['wellbeing_score']),
               trade=finite(m['trade_score']))
    out['economic'] = out['economic_growth']+out['reserve']
    out['industry'] = out['capacity']+out['utilization']
    out['score'] = out['economic']+out['industry']+out['wellbeing']+out['trade']
    out.update(economic_growth_at_cap=int(econ >= 20-1e-9), capacity_at_cap=int(capacity >= 15-1e-9),
               economic_growth_near_cap=int(econ >= 19-1e-9), capacity_near_cap=int(capacity >= 14.25-1e-9),
               economic_10g_sensitivity=20*(clip((gain+10)/economic_goal)-clip(gain/economic_goal)),
               capacity_010_sensitivity=15*(clip((growth+.10)/industrial_goal)-clip(growth/industrial_goal)))
    assert 0 <= out['score'] <= 100+1e-9
    return out


def score_record(record, goals):
    """Return a deep copy; preserve official scores and all economic inputs."""
    validate_targets(goals)
    assert set(record['countries']) == set(NAMES+ADDED)
    out = deepcopy(record)
    for name, c in out['countries'].items():
        if name not in NAMES:
            assert c['score'] is None
            c['revised_evaluation'] = {v: None for v in VIEWS}
            c['economic_metrics_v15'] = None
            continue
        m = c['growth_metrics']
        for value in m.values():
            finite(value)
        assert m['investment'] >= 0
        assert math.isclose(m['asset_gain'], m['end_asset_value']-m['start_asset_value'], abs_tol=1e-8)
        assert math.isclose(m['end_asset_value'], m['cash']+m['stock_value']+.45*m['investment'], abs_tol=1e-8)
        specs = {
            'legacy': ('official_economic', 'official_industrial', False),
            'targets': ('economic_old', 'industrial_old', False),
            'steps': ('economic_old', 'industrial_steps', False),
            'capital': ('economic_capital', 'industrial_old', True),
            'steps_capital': ('economic_capital', 'industrial_steps', True),
            'capital_fixed_goal': ('economic_old', 'industrial_steps', True),
        }
        views = {v: metric_view(m, goals[e][name], goals[i][name], neutral)
                 for v, (e,i,neutral) in specs.items()}
        assert math.isclose(views['legacy']['score'], c['score'], abs_tol=1e-8)
        for old, new in (('targets','steps'), ('capital','steps_capital')):
            assert math.isclose(views[new]['score']-views[old]['score'],
                                views[new]['capacity']-views[old]['capacity'], abs_tol=1e-8)
        for old, new in (('targets','capital'), ('steps','steps_capital')):
            assert math.isclose(views[new]['score']-views[old]['score'],
                                views[new]['economic_growth']-views[old]['economic_growth'], abs_tol=1e-8)
        initial_stock = m['start_asset_value']-c['start_cash']
        stock_change = m['stock_value']-initial_stock
        cash_identity = c['revenue']-c['purchases']+c['tax']-c['investment']
        assert math.isclose(c['cash']-c['start_cash'], cash_identity, abs_tol=1e-8)
        neutral_gain = m['asset_gain']+.55*m['investment']
        assert math.isclose(neutral_gain, c['revenue']-c['purchases']+c['tax']+stock_change, abs_tol=1e-8)
        c['economic_metrics_v15'] = {
            'old_gain': m['asset_gain'], 'capital_gain': neutral_gain,
            'old_end_asset': m['end_asset_value'],
            'capital_end_asset': m['cash']+m['stock_value']+m['investment'],
            'recognition_difference': .55*m['investment'],
            'sales': c['revenue'], 'purchases': c['purchases'],
            'automatic_income': c['tax'], 'investment': c['investment'],
            'starting_stock_value': initial_stock, 'ending_stock_value': m['stock_value'],
            'stock_value_change': stock_change,
            'unused_stock_value': m['unused_stock_value'], 'used_stock_value': m['used_stock_value'],
            'old_investment_asset_effect': -.55*m['investment'],
            'capital_investment_asset_effect': 0.0,
        }
        c['revised_evaluation'] = views
    world = {}
    for v in VIEWS:
        scores = [out['countries'][n]['revised_evaluation'][v]['score'] for n in NAMES]
        high = max(scores)
        top = [n for n,s in zip(NAMES,scores) if s >= high-1e-9]
        for n in NAMES:
            out['countries'][n]['revised_evaluation'][v]['top'] = int(n in top)
        world[v] = {'original_score_spread': high-min(scores), 'top_countries': top}
    out['world']['score_revision_v15'] = world
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--calibration', type=Path, default=ROOT/'calibration_input/calibration_runs.jsonl.gz')
    p.add_argument('--old-goals', type=Path, default=ROOT/'V12_FROZEN_GOALS.json')
    p.add_argument('--opportunities', type=Path, default=ROOT/'target_opportunities.json')
    p.add_argument('--output', type=Path, default=ROOT/'SCORE_TARGETS_V15.json')
    a = p.parse_args()
    value = make_targets(a.calibration, a.old_goals, a.opportunities)
    validate_targets(value)
    payload = json.dumps(value, ensure_ascii=False, indent=2)+'\n'
    if a.output.exists():
        assert a.output.read_text() == payload, 'Preserve an existing frozen target file'
    else:
        a.output.write_text(payload)
    print(json.dumps({'path':str(a.output), 'sha256':digest(a.output),
                      'economic_capital':value['economic_capital'],
                      'industrial_steps':value['industrial_steps'], 'new_economic_games':0}))


if __name__ == '__main__':
    main()
