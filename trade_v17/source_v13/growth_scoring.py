"""v12: frozen-economy, country-target and scoring-ceiling experiments.

The v11 economy and its official scores are inherited without edits.  This
module exposes two already-existing AI styles and provides pure, post-game
score views.  New target values are fitted only to a separate calibration set.
"""
from __future__ import annotations

from copy import deepcopy
import math

from evaluation_engine import Game as V11Game, BEHAVIORS as V11_BEHAVIORS
from reference_engine import NAMES, ECON_GOAL, GROWTH_GOAL, DURABLES

VIEWS = ('legacy', 'targets', 'headroom', 'targets_headroom')
CALIBRATION_STYLES = ('normal', 'invest', 'trade')
BEHAVIORS = V11_BEHAVIORS + ('invest', 'trade')
GOAL_METHOD = {
    'quantile': .75, 'economic_floor': 50, 'economic_step': 5,
    'industrial_floor': .10, 'industrial_step': .05,
    'policies': list(CALIBRATION_STYLES), 'equal_policy_weight': True,
    'original_countries_only': True,
    'exclude_peer_policy_observations': True,
}
HEADROOM = {'base_target_fraction': .8, 'challenge_target_multiple': 2.0}


class Game(V11Game):
    """Expose the inherited investment/trade policies; no economic rule change."""
    def __init__(self, seed=0, focal=None, style='normal', trade_enabled=True,
                 behaviors=None):
        if style not in BEHAVIORS:
            raise ValueError('unknown growth-validation behavior')
        if style in ('invest', 'trade'):
            if focal is None:
                raise ValueError('investment/trade behavior requires a focal country')
            other = dict(behaviors or {})
            if focal in other and other[focal] != style:
                raise ValueError('conflicting focal behavior')
            other.pop(focal, None)
            super().__init__(seed, focal=focal, style='normal',
                             trade_enabled=trade_enabled, behaviors=other)
            self.cs[focal].style = style
            self.behaviors[focal] = style
        else:
            super().__init__(seed, focal=focal, style=style,
                             trade_enabled=trade_enabled, behaviors=behaviors)


def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return value


def clip01(value):
    return min(1., max(0., value))


def curve(ratio, headroom=False):
    """Reach 80% at the base goal and 100% at twice that goal, if enabled."""
    finite(ratio, 'growth ratio')
    if not headroom:
        return clip01(ratio)
    return .8 * clip01(ratio) + .2 * clip01(ratio - 1.)


def percentile(values, quantile=.75):
    values = sorted(finite(v, 'calibration value') for v in values)
    if not values or not 0 <= quantile <= 1:
        raise ValueError('nonempty calibration values and a valid quantile required')
    position = (len(values)-1) * quantile
    index = int(position)
    fraction = position-index
    return values[index]*(1-fraction) + values[min(index+1, len(values)-1)]*fraction


def rounded_goal(value, floor, step):
    """Round up to a readable step; tolerate only binary representation noise."""
    value = max(floor, finite(value, 'goal quantile'))
    return round(math.ceil(value/step - 1e-12)*step, 10)


def extract_metrics(game, result):
    """Read final-state evidence, without choosing plans or issuing actions."""
    if game.r != 9 or len(game.round_history) != 9:
        raise ValueError('growth metrics require a completed nine-round game')
    out = {}
    for name, country in game.cs.items():
        x = result['countries'][name]
        owned = [game.units[i] for i in country.stock]
        unused_value = sum(game.unit_ref(u)*.15 for u in owned if not u.used)
        used_value = sum(game.unit_ref(u)*(.5 if u.good in DURABLES else .15)
                         for u in owned if u.used)
        initial_capacity = game.initial_capacity[name]
        final_capacity = game.capacity(country)
        reserve = game.reserve(country)
        produced = sum(x['produced'].values())
        used = x['all_goods_unique_used']
        if reserve <= 0 or initial_capacity <= 0 or not 0 <= used <= produced:
            raise AssertionError((name, 'invalid evidence for growth score'))
        stock_value = game.stock_value(country)
        assert math.isclose(unused_value+used_value, stock_value, abs_tol=1e-8)
        assert math.isclose(x['end_asset_value'],
                            country.cash+stock_value+.45*country.investment,
                            abs_tol=1e-8)
        growth = (final_capacity-initial_capacity)/initial_capacity
        assert math.isclose(growth, x['capacity_growth'], abs_tol=1e-12)
        out[name] = {
            'start_asset_value': x['start_asset_value'],
            'end_asset_value': x['end_asset_value'],
            'asset_gain': x['end_asset_value']-x['start_asset_value'],
            'cash': country.cash, 'tax': country.tax,
            'investment': country.investment,
            'unused_stock_value': unused_value,
            'used_stock_value': used_value,
            'stock_value': stock_value,
            'initial_capacity': initial_capacity,
            'final_capacity': final_capacity,
            'capacity_growth': growth,
            'reserve_target': reserve,
            'reserve_score': 5*clip01(country.cash/reserve),
            'produced_units': produced, 'used_units': used,
            'utilization': used/max(1, produced),
            'utilization_score': 10*used/max(1, produced),
            'wellbeing_score': x['happy']/4,
            'trade_score': x['trade'],
        }
    return out


def make_goals(records):
    """Fit each nation to its own normal/invest/trade results with equal weights.

    A control game is shared across nations, not counted as six independent
    economies. Outcomes of peers whose policy was not manipulated are excluded.
    """
    by_key = {}
    for row in records:
        if row.get('phase') != 'calibration':
            raise ValueError('only calibration records may define targets')
        key = (row['scenario'], row['seed'])
        if key in by_key:
            raise ValueError('duplicate calibration trajectory')
        by_key[key] = row
    normal_seeds = {seed for (sid, seed) in by_key if sid == 'None:normal'}
    if len(normal_seeds) < 2:
        raise ValueError('at least two paired calibration seeds required')
    expected_cases = {'None:normal'} | {f'{n}:{s}' for n in NAMES for s in ('invest','trade')}
    if set(by_key) != {(case, seed) for case in expected_cases for seed in normal_seeds}:
        raise ValueError('calibration must contain precisely the declared paired policies')
    economic = {}; industrial = {}; raw_economic = {}; raw_industrial = {}
    for name in NAMES:
        sample = []
        for style in CALIBRATION_STYLES:
            sid = 'None:normal' if style == 'normal' else f'{name}:{style}'
            for seed in sorted(normal_seeds):
                row = by_key[sid, seed]
                expected_focal = None if style == 'normal' else name
                if row['focal'] != expected_focal or row['style'] != style:
                    raise ValueError('calibration policy identity mismatch')
                sample.append(row['countries'][name]['growth_metrics'])
        raw_economic[name] = percentile([m['asset_gain'] for m in sample])
        raw_industrial[name] = percentile([m['capacity_growth'] for m in sample])
        economic[name] = rounded_goal(raw_economic[name], 50, 5)
        industrial[name] = rounded_goal(raw_industrial[name], .10, .05)
    return {
        'schema': 'v12-growth-targets-1', 'source': 'calibration_only',
        'method': deepcopy(GOAL_METHOD),
        'calibration': {
            'seeds': sorted(normal_seeds), 'n_per_policy': len(normal_seeds),
            'samples_per_country': 3*len(normal_seeds),
            'unique_economic_games': len(by_key),
        },
        'economic': economic, 'industrial': industrial,
        'raw_quantiles': {'economic': raw_economic, 'industrial': raw_industrial},
    }


def validate_goals(goals):
    if goals.get('schema') != 'v12-growth-targets-1' or goals.get('source') != 'calibration_only':
        raise ValueError('unexpected target file schema/source')
    if goals.get('method') != GOAL_METHOD:
        raise ValueError('target-setting method differs from the frozen protocol')
    for category in ('economic', 'industrial'):
        if set(goals[category]) != set(NAMES):
            raise ValueError('targets are required for precisely the original six nations')
        if any(finite(v, 'target') <= 0 for v in goals[category].values()):
            raise ValueError('targets must be positive')


def score_metrics(metrics, economic_target, industrial_target, headroom=False):
    for key, value in metrics.items():
        finite(value, key)
    if finite(economic_target, 'economic target') <= 0 or finite(industrial_target, 'industrial target') <= 0:
        raise ValueError('targets must be positive')
    m = metrics
    er = m['asset_gain']/economic_target
    ir = m['capacity_growth']/industrial_target
    econ_growth = 20*curve(er, headroom)
    capacity = 15*curve(ir, headroom)
    reserve = m['reserve_score']
    use = m['utilization_score']
    economic = econ_growth+reserve
    industry = capacity+use
    return {
        'economic_target': economic_target, 'industrial_target': industrial_target,
        'economic_ratio': er, 'industrial_ratio': ir,
        'economic_growth': econ_growth, 'reserve': reserve,
        'economic': economic, 'capacity': capacity,
        'utilization': use, 'industry': industry,
        'wellbeing': m['wellbeing_score'], 'trade': m['trade_score'],
        'score': economic+industry+m['wellbeing_score']+m['trade_score'],
        'economic_growth_at_cap': int(econ_growth >= 20-1e-9),
        'capacity_at_cap': int(capacity >= 15-1e-9),
        'economic_growth_near_cap': int(econ_growth >= 19-1e-9),
        'capacity_near_cap': int(capacity >= 14.25-1e-9),
        'economic_at_cap': int(economic >= 25-1e-9),
        'economic_5pct_sensitivity': 20*(curve(max(0, er)*1.05, headroom)-curve(er, headroom)),
        'capacity_5pct_sensitivity': 15*(curve(max(0, ir)*1.05, headroom)-curve(ir, headroom)),
    }


def score_record(record, goals):
    """Return a new record; official fields and economic trajectories stay intact."""
    validate_goals(goals)
    output = deepcopy(record)
    for name, country in output['countries'].items():
        if name not in NAMES:
            country['growth_evaluation'] = {view: None for view in VIEWS}
            continue
        metrics = country['growth_metrics']
        views = {}
        for view in VIEWS:
            fitted = view in ('targets','targets_headroom')
            et = goals['economic'][name] if fitted else ECON_GOAL[name]
            it = goals['industrial'][name] if fitted else GROWTH_GOAL[name]
            views[view] = score_metrics(metrics, et, it, 'headroom' in view)
        for key in ('economic', 'industry', 'score'):
            assert math.isclose(views['legacy'][key], country[key], abs_tol=1e-9), (name,key)
            views['legacy'][key] = country[key]
        assert math.isclose(views['legacy']['capacity'], country['industry_capacity_score'], abs_tol=1e-9)
        assert math.isclose(views['legacy']['utilization'], country['industry_use_score'], abs_tol=1e-9)
        country['growth_evaluation'] = views
    output['world']['growth_evaluation_config'] = {
        'views': list(VIEWS), 'headroom': deepcopy(HEADROOM),
        'economic_rules_unchanged': True, 'official_scores_unchanged': True,
        'score_feedback_to_actions': False, 'ranked_countries': list(NAMES),
        'v11_trade_view': 'legacy', 'asset_definition_unchanged': True,
        'utilization_definition_unchanged': True,
    }
    return output
