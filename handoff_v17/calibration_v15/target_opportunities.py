"""v15: restore calibrated industry goals to observed development steps.

This program reads preserved v12 calibration records and detailed traces.  It
never imports or executes the economic engine.  It changes no original file.
All percentile and threshold decisions use only the 780 archived calibration
games; subsequent v13/v14 outcomes and new v15 validation outcomes are excluded.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
POLICIES = ('normal', 'invest', 'trade')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def rational(value):
    return Fraction(str(value)).limit_denominator(10**9)


def literal_constants(path):
    """Extract actual initial levels, expansions and base prices without import."""
    constants = {}
    for node in ast.parse(Path(path).read_text()).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if name in ('CONFIG', 'FOOD', 'GOODS', 'NAMES'):
            constants[name] = ast.literal_eval(node.value)
        elif name == 'PRICE':
            value = node.value
            assert isinstance(value, ast.Call) and value.func.id == 'dict'
            zipped = value.args[0]
            assert isinstance(zipped, ast.Call) and zipped.func.id == 'zip'
            constants[name] = dict(zip(constants[zipped.args[0].id], ast.literal_eval(zipped.args[1])))
    return constants


def capacity(constants, name, levels):
    bases = constants['CONFIG'][name][1]
    return sum(constants['PRICE'][good] * (bases.get(good, 1) +
               (level - 1) * (2 if good in constants['FOOD'] else 1))
               for good, level in levels.items() if level)


def enumerate_states(constants, name):
    """Relax cash/raw/household/machines; preserve the seven-round action space."""
    goods = constants['GOODS']
    bases, expansion = constants['CONFIG'][name][1], constants['CONFIG'][name][3]
    initial = tuple(int(good in bases) for good in goods)
    states = {initial: ()}
    for round_no in range(1, 8):
        after = {}
        for levels, actions in states.items():
            choices = [None] + [good for good, level in zip(goods, levels)
                                if 0 < level < 4 or
                                (level == 0 and good == expansion and round_no >= 3)]
            for choice in choices:
                nxt = list(levels)
                if choice is not None:
                    nxt[goods.index(choice)] += 1
                after.setdefault(tuple(nxt), actions + (choice,))
        states = after
    rows = []
    for levels, actions in states.items():
        value = capacity(constants, name, dict(zip(goods, levels)))
        rows.append({'capacity': value, 'developments': sum(g is not None for g in actions),
                     'levels': dict(zip(goods, levels)), 'round_actions': list(actions)})
    return rows


def quantile(values):
    values = sorted(values)
    pos = Fraction(3, 4) * (len(values) - 1)
    index = pos.numerator // pos.denominator
    part = pos - index
    return values[index] * (1 - part) + values[min(index + 1, len(values) - 1)] * part


def crossing(states, threshold):
    eligible = [s for s in states if s['capacity'] >= threshold]
    if not eligible:
        return {'reachable_under_relaxation': False}
    lowest = min(eligible, key=lambda s: (s['capacity'], s['developments']))
    shortest = min(eligible, key=lambda s: (s['developments'], s['capacity']))
    return {'reachable_under_relaxation': True,
            'threshold_capacity': float(threshold),
            'next_attainable_capacity': lowest['capacity'],
            'minimum_developments_lower_bound': shortest['developments'],
            'next_capacity_witness': lowest, 'minimum_developments_witness': shortest}


def record_growth(constants, name, record):
    country = record['countries'][name]
    initial = capacity(constants, name, {g: 1 for g in constants['CONFIG'][name][1]})
    final = capacity(constants, name, country['end_levels'])
    m = country['growth_metrics']
    assert m['initial_capacity'] == initial and m['final_capacity'] == final
    value = Fraction(final - initial, initial)
    assert abs(float(value) - m['capacity_growth']) < 1e-12
    assert abs(float(value) - country['capacity_growth']) < 1e-12
    return value


def record_evidence(constants, name, record):
    c = record['countries'][name]
    return {
        'identity': {k: record[k] for k in ('phase', 'mode', 'scenario', 'seed', 'focal', 'style', 'behaviors')},
        'record_sha256': object_digest(record),
        'growth': float(record_growth(constants, name, record)),
        'initial_capacity': c['growth_metrics']['initial_capacity'],
        'final_capacity': c['growth_metrics']['final_capacity'],
        'upgrade_rounds': c['upgrade_rounds'], 'end_levels': c['end_levels'],
        'investment_cash_cost': c['investment'], 'cash_end': c['cash'],
        'minimum_observed_cash': c['min_observed_cash'], 'wellbeing': c['happy'],
        'food_short_rounds': c['food_short_rounds'],
        'note': 'Archived completed execution; final evidence alone does not contain every pre-investment guard snapshot.',
    }


def inspect_trace(constants, name, key, trace, record):
    """Verify a completed archived execution witness under its actual policy."""
    assert trace['result'] == record
    c = record['countries'][name]
    attempts = [a for a in trace['evaluation_attempts'] if a['country'] == name and a['successful']]
    events = [e for e in trace['development'] if e['country'] == name]
    ledger = [r for r in trace['cash_ledger'] if r['country'] == name]
    assert len(attempts) == len(events) == c['upgrades_total']
    assert len(ledger) == 9 and {r['round'] for r in ledger} == set(range(1, 10))
    assert len({a['round'] for a in attempts}) == len(attempts)
    assert sum(e['cash_cost'] for e in events) == c['investment']
    expected_upgrades = [[e['round'], e['industry'], e['to_level']] for e in events]
    assert expected_upgrades == c['upgrade_rounds']
    levels = {g: int(g in constants['CONFIG'][name][1]) for g in constants['GOODS']}
    snapshots = []
    for attempt, event in zip(attempts, events):
        a, e = attempt, event
        assert a['legal'] and a['cached'] and 1 <= a['round'] <= 7
        assert a['event_id'] == e['event_id'] and a['round'] == e['round']
        assert a['goal'] == e['industry'] and a['target_level'] == e['to_level']
        assert a['cash_cost'] == e['cash_cost'] and a['cash'] >= a['cash_cost'] + a['reserve']
        assert a['cash_ok'] and a['raw_ok'] and a['household_ok']
        assert all(a['raw_free'].get(g, 0) >= q for g, q in a['raw_required'].items())
        assert a['research_ore'] == e['ore_required'] == len(e['ore_ids'])
        assert a['machine_min_gen'] == e['machine_min_gen']
        assert e['from_level'] == levels[e['industry']] and e['to_level'] == e['from_level'] + 1 <= 4
        assert e['from_level'] or (e['industry'] == constants['CONFIG'][name][3] and e['round'] >= 3)
        for uid in e['ore_ids']:
            unit = trace['units'][str(uid)]
            assert unit['good'] == 'ore' and unit['use_country'] == name and unit['used']
            assert unit['use_round'] == e['round'] and unit['use_purpose'] == 'development'
        machine = e['machine']
        assert bool(machine) == bool(a['machine_min_gen'])
        if machine:
            assert a['machine_used'] == machine
            assert machine['uid'] in a['free_qualified_ids']
            assert machine['generation'] >= a['machine_min_gen']
            if machine['import_transaction'] is not None:
                transaction = trace['transactions'][machine['import_transaction']]
                assert transaction['round'] <= e['round']
                assert any(leg['buyer'] == name and machine['uid'] in leg['ids'] for leg in transaction['legs'])
        ordinary_household_satisfied = a['food_met'] and a['living_free'] >= a['living_needed']
        if a['style'] != 'invest':
            assert ordinary_household_satisfied
        else:
            assert a['reserve'] == 0
        levels[e['industry']] += 1
        snapshots.append({
            'round': a['round'], 'industry': a['goal'], 'from_level': e['from_level'],
            'to_level': a['target_level'], 'capacity_after': capacity(constants, name, levels),
            'cash_before': a['cash'], 'cash_cost': a['cash_cost'], 'required_cash_reserve': a['reserve'],
            'raw_available': a['raw_free'], 'raw_required_for_next_production_and_development': a['raw_required'],
            'research_ore': e['ore_required'], 'research_ore_ids': e['ore_ids'],
            'machine_minimum_generation': a['machine_min_gen'], 'machine_used': machine,
            'food_met': a['food_met'], 'living_free': a['living_free'], 'living_needed': a['living_needed'],
            'household_guard_passed_under_actual_policy': a['household_ok'],
            'ordinary_household_condition_satisfied': ordinary_household_satisfied,
            'investment_policy_waives_cash_reserve_and_household_guard': a['style'] == 'invest',
            'successful': True,
        })
    assert levels == c['end_levels']
    previous_cash = c['start_cash']
    for row in ledger:
        assert row['cash_start'] == previous_cash
        expected = row['cash_start'] + row['sales'] - row['purchases'] - row['investment'] + row['operating_income']
        assert row['cash_end'] == expected >= 0
        assert row['investment'] == sum(e['cash_cost'] for e in events if e['round'] == row['round'])
        previous_cash = row['cash_end']
    assert previous_cash == c['cash']
    assert sum(r['sales'] for r in ledger) == c['revenue']
    assert sum(r['purchases'] for r in ledger) == c['purchases']
    assert sum(r['operating_income'] for r in ledger) == c['tax']
    result = record_evidence(constants, name, record)
    result.update(trace_key=key, trace_sha256=object_digest(trace), snapshots=snapshots,
                  cash_ledger=ledger,
                  all_actual_policy_conditions_verified=True,
                  has_investment_policy_waiver=any(a['style'] == 'invest' for a in attempts),
                  all_ordinary_household_conditions_satisfied=all(s['ordinary_household_condition_satisfied'] for s in snapshots),
                  normal_policy_witness=all(a['style'] != 'invest' for a in attempts),
                  note='Full archived witness under the named calibration policy only. Purchases/material costs are additional to displayed investment cash cost. It is not a guarantee of attainability in every seed or in the electronics-input candidate economy.')
    return result


def build(root=ROOT):
    root = Path(root)
    paths = {'old_goals': root/'V12_FROZEN_GOALS.json',
             'calibration_runs': root/'calibration_input/calibration_runs.jsonl.gz',
             'calibration_traces': root/'calibration_input/calibration_traces.json.gz',
             'provenance': root/'V14_PROVENANCE.json'}
    before = {name: digest(path) for name, path in paths.items()}
    provenance = load(paths['provenance'])
    assert before['old_goals'] == provenance['old_goals_sha256']
    assert before['calibration_runs'] == provenance['calibration_input_sha256']['calibration_runs.jsonl.gz']
    assert before['calibration_traces'] == provenance['calibration_input_sha256']['calibration_traces.json.gz']
    source_before = {name: digest(root/'source_v13'/name) for name in provenance['source_python_sha256']}
    assert len(source_before) == 85 and source_before == provenance['source_python_sha256']
    constants = literal_constants(root/'source_v13/reference_engine.py')
    names = constants['NAMES']
    goals = load(paths['old_goals'])
    assert goals['calibration']['seeds'] == list(range(90000, 90060))
    assert goals['method']['policies'] == list(POLICIES) and goals['method']['quantile'] == .75
    with gzip.open(paths['calibration_runs'], 'rt') as stream:
        records = [json.loads(line) for line in stream]
    with gzip.open(paths['calibration_traces'], 'rt') as stream:
        traces = json.load(stream)
    by_key = {(r['scenario'], r['seed']): r for r in records}
    cases = {'None:normal'} | {f'{name}:{style}' for name in names for style in ('invest', 'trade')}
    assert len(records) == len(by_key) == 780
    assert set(by_key) == {(case, seed) for case in cases for seed in range(90000, 90060)}
    assert all(r['phase'] == 'calibration' and r['mode'] == 'market_first' for r in records)
    assert len(traces) == 13
    for trace in traces.values():
        assert trace['seed'] == 90000 and trace['result'] == by_key[trace['scenario'], trace['seed']]
    out = {
        'schema': 'v15-discrete-industrial-targets-1', 'status': 'passed',
        'new_economic_games': 0,
        'official_rules_changed': False,
        'method': {
            'source': 'preserved_v12_calibration_only', 'quantile': .75,
            'policies': list(POLICIES), 'equal_policy_weight': True,
            'own_policy_records_only_for_target_selection': True,
            'raw_quantile_refitted': False,
            'rule': 'Smallest observed positive own-policy calibration growth at or above max(existing raw P75, existing 0.10 floor). Do not round it upward to a 0.05 grid.',
            'score_curve': 'Linear cap at the selected target; no headroom or twice-target challenge.',
            'per_country_samples': 180, 'total_source_games': 780,
            'target_seeds': [90000, 90059], 'v13_v14_or_v15_validation_used_for_selection': False,
        },
        'source_paths': {name: str(path.relative_to(root)) for name, path in paths.items()},
        'input_sha256': before, 'source_python_sha256': source_before,
        'generator_sha256': digest(Path(__file__)), 'industrial': {},
        'target_capacities': {}, 'countries': {},
        'limitations': [
            'The correction restores observed development steps. It does not equalize wins, investment counts, cost, or difficulty.',
            'Full target score frequency can increase. That alone is neither fairness nor unfairness.',
            'Archived successful paths prove feasibility only under their stated calibration policies and market trajectory.',
            'Invest policy waives the normal cash reserve and household guard; any such witness is explicitly identified.',
            'The relaxed state enumeration proves structural reachability, not affordability.',
            'The official source goals remain byte-for-byte unchanged; these are candidate score-view targets.',
        ],
    }
    for name in names:
        own = {style: [by_key['None:normal' if style == 'normal' else f'{name}:{style}', seed]
                       for seed in range(90000, 90060)] for style in POLICIES}
        values = [record_growth(constants, name, record) for style in POLICIES for record in own[style]]
        q = quantile(values)
        assert q == rational(goals['raw_quantiles']['industrial'][name])
        threshold = max(q, Fraction(1, 10))
        target = min(v for v in values if v > 0 and v >= threshold)
        c0 = capacity(constants, name, {g: 1 for g in constants['CONFIG'][name][1]})
        target_cap = c0 * (1 + target)
        assert target_cap.denominator == 1
        old = rational(goals['industrial'][name])
        assert target <= old
        states = enumerate_states(constants, name)
        old_crossing = crossing(states, c0 * (1 + old))
        new_crossing = crossing(states, target_cap)
        assert new_crossing['reachable_under_relaxation'] and new_crossing['next_attainable_capacity'] == target_cap
        own_trace_candidates = [(key, t) for key, t in traces.items()
                                if t['scenario'] in ('None:normal', f'{name}:invest', f'{name}:trade') and
                                record_growth(constants, name, t['result']) >= target]
        assert own_trace_candidates
        key, trace = min(own_trace_candidates, key=lambda kt: (
            record_growth(constants, name, kt[1]['result']),
            kt[1]['style'] == 'invest', kt[1]['result']['countries'][name]['investment'], kt[0]))
        witness = inspect_trace(constants, name, key, trace, by_key[trace['scenario'], trace['seed']])
        normal_achieved = [r for r in own['normal'] if record_growth(constants, name, r) >= target]
        assert normal_achieved, name
        normal_record = min(normal_achieved, key=lambda r: (record_growth(constants, name, r), r['seed']))
        supplemental = []
        if not witness['normal_policy_witness']:
            for candidate_key, candidate in traces.items():
                r = candidate['result']
                if r['behaviors'].get(name, 'normal') in ('invest', 'trade'):
                    continue
                if record_growth(constants, name, r) < target:
                    continue
                supplemental.append((candidate_key, candidate))
        supplemental_normal = None
        if supplemental:
            skey, strace = min(supplemental, key=lambda kt: (record_growth(constants, name, kt[1]['result']), kt[0]))
            supplemental_normal = inspect_trace(constants, name, skey, strace, strace['result'])
            supplemental_normal['note_on_scope'] = 'May be a normal peer in another country\'s calibration policy case. Used only as a feasibility witness, never included in this country\'s target samples.'
        counts = {}
        for style in POLICIES:
            counts[style] = {
                'n': 60,
                'old_target_met': sum(record_growth(constants, name, r) >= old for r in own[style]),
                'candidate_target_met': sum(record_growth(constants, name, r) >= target for r in own[style]),
                'exact_candidate_growth': sum(record_growth(constants, name, r) == target for r in own[style]),
            }
        out['industrial'][name] = float(target)
        out['target_capacities'][name] = int(target_cap)
        out['countries'][name] = {
            'initial_capacity': c0, 'old_target_growth': float(old),
            'raw_p75_growth': float(q), 'raw_p75_fraction': str(q),
            'candidate_target_growth': float(target), 'candidate_target_fraction': str(target),
            'candidate_target_capacity': int(target_cap),
            'target_capacity_increase': int(target_cap) - c0,
            'old_threshold_capacity': float(c0 * (1 + old)),
            'target_changed': target != old,
            'old_threshold_crossing': old_crossing, 'candidate_threshold_crossing': new_crossing,
            'relaxed_maximum_capacity': max(s['capacity'] for s in states),
            'relaxed_final_state_count': len(states),
            'maximum_same_outcome_capacity_score_increase': float(15 * (1 - target / old)),
            'own_policy_calibration_counts': counts,
            'complete_archived_witness': witness,
            'normal_policy_completed_record': record_evidence(constants, name, normal_record),
            'supplemental_normal_trace': supplemental_normal,
            'economic_reachability_scope': 'Observed baseline calibration only. New economy/policy outcomes must be checked separately without changing this target.',
        }
    after = {name: digest(path) for name, path in paths.items()}
    assert before == after
    assert source_before == {name: digest(root/'source_v13'/name) for name in source_before}
    out['source_unchanged'] = True
    out['input_sha256_after'] = after
    out['enumerated_final_states'] = sum(c['relaxed_final_state_count'] for c in out['countries'].values())
    assert out['enumerated_final_states'] == 400
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = build(args.root)
    path = args.output or args.root/'target_opportunities.json'
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': out['status'], 'industrial': out['industrial'],
                      'target_capacities': out['target_capacities'],
                      'enumerated_final_states': out['enumerated_final_states'],
                      'new_economic_games': 0, 'output': str(path), 'sha256': digest(path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
