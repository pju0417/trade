"""v13 staged paired policy experiments on preserved v12 sources.

The AI pilot is reviewed before the optional input pilot; all source, tests,
the declared protocol and the old fixed targets are frozen before formal runs.
Importing this module performs no simulation, fitting or filesystem writes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import unittest

from causal_engine import Game, MODES, AI_MODES, ECONOMIC_MODES
from growth_scoring import extract_metrics, score_record, validate_goals
from reference_engine import NAMES, GOODS
from run_growth_validation import (ECONOMIC_FILES as OLD_ECONOMIC_FILES,
    SOURCE_FILES as OLD_SOURCE_FILES, TEST_FILES as OLD_TEST_FILES,
    validate_invest_attempts, validate_metrics)
from run_evaluation_validation import (normalize_and_validate, validate_evaluation_records,
    scenario, scenario_manifest)
from run_routing_validation import validate_routing_records
from run_development_validation import validate_development_records
from run_raw_validation import validate_raw_ledger, grouped, stats

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'causal_results'
PROTOCOL_FILE = ROOT / 'CAUSAL_PROTOCOL_V13.json'
GOALS_FILE = ROOT / 'V12_FROZEN_GOALS.json'
GOALS_SHA256 = '47e78fe6a9cebab256bb52a3b7dbef9c9b46cec4363d15700290ddfa2e4620d5'
ECONOMIC_FILES = OLD_ECONOMIC_FILES + ('causal_engine.py',)
SOURCE_FILES = OLD_SOURCE_FILES + ('causal_engine.py', 'run_causal_validation.py')
TEST_FILES = OLD_TEST_FILES + ('test_causal.py',)
INHERITED_TESTS = 375
ALL_MODES = ('baseline', 'operating_first', 'no_durable_boost', 'ai_combined', 'electronics_input', 'combined_input')
NORMAL = (scenario(),)
STRESS_SCENARIOS = NORMAL + tuple(scenario(n, s) for n in NAMES for s in ('minimum', 'idle')) + (
    scenario('Technia', 'cheap'),
    scenario('Mechania', 'idle', (('Technia', 'minimum'),)),
    scenario('Mechania', 'idle', (('Novia', 'minimum'),)),
    scenario('Mineria', 'idle', (('Technia', 'minimum'), ('Grainia', 'normal'))),
    scenario('Technia', 'idle', (('Mineria', 'minimum'), ('Grainia', 'normal'))),
    scenario('Grainia', 'idle', (('Technia', 'minimum'), ('Mineria', 'normal'))),
    scenario(None, 'no_trade'),
) + tuple(scenario(n, s) for n in ('Mineria', 'Technia') for s in ('invest', 'trade'))
PHASES = {
    'pilot_ai': (96000, 30, ALL_MODES[:4], NORMAL),
    'pilot_economic': (96000, 30, ALL_MODES[4:], NORMAL),
    'main': (100000, 100, ALL_MODES, NORMAL),
    'stress': (102000, 30, ALL_MODES, STRESS_SCENARIOS),
}
IDENTITY_FIELDS = ('phase', 'mode', 'scenario', 'seed', 'focal', 'style', 'behaviors')
MODE_COMPARISONS = (
    ('baseline', 'operating_first'), ('baseline', 'no_durable_boost'),
    ('baseline', 'ai_combined'), ('baseline', 'electronics_input'),
    ('ai_combined', 'combined_input'), ('baseline', 'combined_input'),
)
COUNTRY_SUMMARY_FIELDS = (
    'cash', 'happy', 'revenue', 'purchases', 'investment', 'tax', 'start_cash',
    'exports', 'imports', 'useful_exports', 'useful_imports', 'useful_partners',
    'coverage', 'food_short_rounds', 'low_cash_rounds', 'production_failures',
    'machine_gen', 'elec_gen', 'capacity_growth', 'economic', 'industry', 'trade', 'score',
    'all_goods_unique_used', 'industry_use_score', 'industry_capacity_score',
    'economic_at_cap', 'upgrades_total', 'start_asset_value', 'end_asset_value',
    'cash_plus_stock_value', 'funding_blocks', 'household_blocks', 'min_observed_cash',
    'produced', 'use_by_good', 'export_used_by_good', 'sale_by_good', 'purchase_by_good',
    'import_goods', 'export_goods', 'end_stock_by_good', 'unused_by_good',
    'production_raw', 'research_raw', 'raw_use', 'raw_unmet_production', 'end_levels',
    'causal', 'economic_decomposition', 'routing', 'growth_metrics', 'growth_evaluation',
)
WORLD_SUMMARY_FIELDS = (
    'transactions', 'trade_units', 'happy', 'original_happy', 'original_cash',
    'original_cash_gap', 'original_happy_gap', 'original_food_short',
    'original_production_failures', 'barter', 'counter_accepted', 'initial_cash',
    'cash_total', 'tax', 'investment', 'production', 'consumed', 'trade_goods',
    'remaining_goods', 'aged_unused_goods', 'end_prices', 'uncovered_investments',
    'all_goods_unique_used', 'raw_use', 'raw_unmet_production', 'raw_importing',
    'machine_g2', 'machine_g3', 'electronics_g2', 'electronics_g3',
    'causal_score_spread', 'v12_targets_score_spread',
)
CAUSAL_KEYS = (
    'cash_trade_balance', 'cash_before_investment_balance', 'cash_change',
    'legal_planned_attempts', 'cash_ready_attempts', 'feasible_planned_attempts',
    'successful_attempts', 'no_upgrade', 'blocked_cash_attempts',
    'blocked_household_attempts', 'blocked_raw_attempts', 'blocked_machine_attempts',
)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def hashes(files):
    return {name: digest(ROOT / name) for name in files}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def inherited_hashes():
    expected = read_json(ROOT / 'V12_PROVENANCE.json')['files']
    actual = hashes(expected)
    assert len(actual) == 76 and actual == expected, 'Inherited v12 Python files changed'
    return actual


def fixed_goals():
    assert digest(GOALS_FILE) == GOALS_SHA256, 'Fixed v12 targets changed'
    goals = read_json(GOALS_FILE)
    validate_goals(goals)
    return goals


def build_tasks(phases=tuple(PHASES)):
    tasks = [(phase, mode, seed, *condition)
             for phase in phases
             for start, count, modes, conditions in (PHASES[phase],)
             for mode in modes for condition in conditions for seed in range(start, start + count)]
    assert len(tasks) == len(set(tasks))
    return tasks


def representative(task):
    return task[2] == PHASES[task[0]][0]


def trace_key(record):
    return f'{record["phase"]}:{record["mode"]}:{record["scenario"]}:{record["seed"]}'


def close(actual, expected, label):
    assert math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9), (label, actual, expected)


def validate_causal_records(game, result):
    assert result['world']['causal_mode'] == game.causal_mode
    assert result['world']['causal_policy'] == asdict(MODES[game.causal_mode])
    assert not game.opt.storage_fees and not game.opt.bonus_inputs
    assert result['world']['causal_scope']['official_score_unchanged']
    assert result['world']['causal_scope']['student_rules_changed'] == bool(game.causal_policy.electronics_extra_raw)
    assert game.causal_buy_capture is None
    plan_keys = [(row['round'], row['country']) for row in game.causal_plan_log]
    assert len(plan_keys) == len(set(plan_keys))
    if not game.causal_policy.remove_durable_boost:
        assert not game.causal_plan_log
    for row in game.causal_plan_log:
        assert 1 <= row['round'] <= 7 and row['style'] not in ('idle', 'trade')
        for candidate in row['candidates']:
            common = candidate['base_price'] * candidate['marginal'] * candidate['remaining'] / candidate['cost'] / candidate['saturation']
            expected = (common + candidate['main_bonus']) * candidate['expansion_factor'] + candidate['adaptive']
            close(candidate['score'], expected, 'unboosted candidate')
            expected_original = (common * candidate['original_boost'] + candidate['main_bonus']) * candidate['expansion_factor'] + candidate['adaptive']
            close(candidate['original_score_same_state'], expected_original, 'same-state original candidate')
            boost = 1.8 if candidate['good'] in ('machine', 'electronics') and row['levels'].get(candidate['good'], 0) < 3 else 1
            assert candidate['original_boost'] == boost
        winner = max(row['candidates'], key=lambda c: (c['score'], c['good'])) if row['candidates'] else None
        expected = winner['good'] if winner else None
        if winner and row['threshold_applies'] and winner['score'] < .45:
            expected = None
        assert row['selected_base'] == expected
    if not game.causal_policy.operating_first:
        assert not game.causal_buy_log
    for capture in game.causal_buy_log:
        rows, allocation = capture['rows'], capture['allocation']
        assert capture['purchases_after'] - capture['purchases_before'] == capture['cash_before'] - capture['cash_after']
        assert 0 <= capture['purchases_after'] - capture['purchases_before'] <= sum(r['budget'] for r in rows)
        assert sum(r['budget'] for r in rows) <= capture['cash_before']
        ordinary = [r for r in rows if r['kind'] != 'replacement']
        assert len({r['good'] for r in ordinary}) == len(ordinary)
        ranks = {g: i for i, g in enumerate(('wheat', 'banana', 'electronics', 'ore', 'fuel', 'machine'))}
        assert [ranks[r['good']] for r in ordinary] == sorted(ranks[r['good']] for r in ordinary)
        for row in rows + allocation:
            assert 0 <= row['quantity'] <= row['want']
            assert row['budget'] == row['quantity'] * row['unit_price']
        if not allocation:
            assert not rows
            continue
        for row in allocation:
            if row['kind'] == 'operating':
                good = row['good']
                assert row['raw_goal'] == min(capture['target'][good], capture['operating'].get(good, 0))
                assert row['want'] == max(0, row['raw_goal'] - capture['initial_stock'][good])
        for row in ordinary:
            if row['good'] not in ('ore', 'fuel'):
                continue
            good = row['good']
            parts = [a for a in allocation if a['good'] == good]
            assert row['want'] == max(0, capture['target'][good] - capture['initial_stock'][good])
            assert row['quantity'] == sum(a['quantity'] for a in parts)
            assert row['budget'] == sum(a['budget'] for a in parts)
        transactions = game.transactions[capture['transaction_start']:capture['transaction_end']]
        spent = sum(t['cash'][2] for t in transactions if t['cash'] and t['cash'][0] == capture['country'])
        assert spent == capture['purchases_after'] - capture['purchases_before']
    for name, country in result['countries'].items():
        diagnostic = country['causal']
        assert set(diagnostic) == set(CAUSAL_KEYS)
        legal = [a for a in game.evaluation_attempts if a['country'] == name and a['legal']]
        feasible = [a for a in legal if a['cash_ok'] and a['household_ok'] and a['raw_ok']
                    and (not a['machine_min_gen'] or a['free_qualified_ids'])]
        assert diagnostic['legal_planned_attempts'] == len(legal)
        assert diagnostic['feasible_planned_attempts'] == len(feasible)
        assert diagnostic['cash_ready_attempts'] == sum(a['cash_ok'] for a in legal)
        assert diagnostic['successful_attempts'] == sum(a['successful'] for a in legal) == country['upgrades_total']
        assert diagnostic['successful_attempts'] <= diagnostic['feasible_planned_attempts'] <= len(legal) <= 7
        for field in ('cash', 'household', 'raw'):
            assert diagnostic['blocked_' + field + '_attempts'] == sum(not a[field + '_ok'] for a in legal)
        assert diagnostic['blocked_machine_attempts'] == sum(bool(a['machine_min_gen']) and not a['free_qualified_ids'] for a in legal)
        assert diagnostic['cash_trade_balance'] == country['revenue'] - country['purchases']
        assert diagnostic['cash_change'] == country['cash'] - country['start_cash']
        assert diagnostic['cash_change'] == country['revenue'] - country['purchases'] - country['investment'] + country['tax']
        assert diagnostic['no_upgrade'] == int(country['upgrades_total'] == 0)


def attach_fixed_reference(game, record):
    metrics = extract_metrics(game, record)
    for name, values in metrics.items():
        record['countries'][name]['growth_metrics'] = values
    validate_metrics(record)
    scored = score_record(record, fixed_goals())
    for name, country in record['countries'].items():
        country['growth_evaluation'] = {'targets': scored['countries'][name]['growth_evaluation']['targets']}
    record['world']['growth_reference_config'] = {
        'source': 'frozen_v12_targets', 'goals_sha256': GOALS_SHA256,
        'views': ['targets'], 'refitted': False, 'official_score_unchanged': True,
        'score_feedback_to_actions': False, 'ranked_countries': list(NAMES),
    }
    record['world']['causal_score_spread'] = max(record['countries'][n]['score'] for n in NAMES) - min(record['countries'][n]['score'] for n in NAMES)
    target_scores = [record['countries'][n]['growth_evaluation']['targets']['score'] for n in NAMES]
    record['world']['v12_targets_score_spread'] = max(target_scores) - min(target_scores)
    return record


def run_one(task):
    phase, mode, seed, sid, focal, style, overrides = task
    game = Game(seed, mode=mode, focal=focal, style='normal' if style == 'no_trade' else style,
                trade_enabled=style != 'no_trade', behaviors=dict(overrides))
    result = normalize_and_validate(game.run())
    for key in ('offer_price_mismatches', 'listing_plan_violations', 'protected_offer_violations', 'uncovered_investments'):
        assert result['world'][key] == 0, (phase, mode, seed, sid, key)
    for name, behavior in game.behaviors.items():
        actor = result['countries'][name]
        if behavior == 'idle':
            assert actor['imports'] == actor['exports'] == actor['investment'] == actor['routing']['routes_started'] == 0
        if behavior in ('trade', 'minimum_passive'):
            assert actor['investment'] == actor['routing']['routes_started'] == 0
    if style == 'no_trade':
        assert result['world']['transactions'] == 0
    validate_raw_ledger(game, result)
    validate_development_records(game, result)
    validate_routing_records(game, result)
    if 'invest' in game.behaviors.values():
        validate_invest_attempts(game, result)
    else:
        validate_evaluation_records(game, result)
    validate_causal_records(game, result)
    identity = dict(phase=phase, mode=mode, scenario=sid, seed=seed, focal=focal, style=style, behaviors=dict(game.behaviors))
    record = attach_fixed_reference(game, {**identity, **result})
    ledger = {**identity, 'rows': game.cash_ledger} if phase in ('main', 'stress') else None
    raw = {**identity, 'rows': game.raw_round_ledger} if phase in ('main', 'stress') else None
    trace = {**game.trace(), **identity, 'result': record} if representative(task) else None
    return record, ledger, raw, trace


def protocol():
    declared = read_json(PROTOCOL_FILE)
    assert declared['schema'] == 'v13-causal-protocol-1'
    assert declared['modes'] == list(ALL_MODES) == list(MODES)
    assert tuple(AI_MODES) == ALL_MODES[:4] and tuple(ECONOMIC_MODES) == ALL_MODES[4:]
    assert declared['fixed_v12_goals_sha256'] == GOALS_SHA256
    assert declared['formal_games'] == 4920 and declared['planned_total_if_six_modes'] == 5100
    return {
        'schema': 'v13-causal-run-plan-1', 'declared_protocol': declared,
        'declared_protocol_sha256': digest(PROTOCOL_FILE), 'fixed_goals_sha256': GOALS_SHA256,
        'modes': list(ALL_MODES), 'mode_policies': {m: asdict(MODES[m]) for m in ALL_MODES},
        'phases': {p: {'seed_range': [start, start + n - 1], 'n_per_condition': n,
                       'modes': list(modes), 'scenarios': scenario_manifest(conditions)}
                   for p, (start, n, modes, conditions) in PHASES.items()},
        'rounds': 9, 'countries': 9, 'ranked_countries': list(NAMES),
        'pilot_ai_games': 120, 'pilot_economic_games': 60, 'pilot_games': 180,
        'main_games': 600, 'stress_games': 4320, 'formal_games': 4920, 'planned_games': 5100,
        'formal_ledger_rows_per_type': 398520, 'representative_traces': 156,
        'identity_fields': list(IDENTITY_FIELDS), 'unique_identity_fields': ['phase', 'mode', 'scenario', 'seed'],
        'country_summary_fields': list(COUNTRY_SUMMARY_FIELDS), 'world_summary_fields': list(WORLD_SUMMARY_FIELDS),
        'mode_comparisons': [list(p) for p in MODE_COMPARISONS],
        'interaction': {'ai_combined': 1, 'operating_first': -1, 'no_durable_boost': -1, 'baseline': 1},
        'formal_after_reviewed_freeze': True, 'fixed_targets_refitted': False,
        'pilot_not_formal_evidence': True, 'source_and_tests_frozen_before_formal': True,
        'test_seed_range': [98000, 98099],
    }


def assert_schedule(rows, phases):
    expected = {(p, m, seed, sid, focal, style, overrides) for p, m, seed, sid, focal, style, overrides in build_tasks(phases)}
    actual = set()
    for row in rows:
        behavior = dict(row['behaviors'])
        if row['focal'] is not None:
            assert behavior.pop(row['focal']) == row['style']
        key = (row['phase'], row['mode'], row['seed'], row['scenario'], row['focal'], row['style'], tuple(sorted(behavior.items())))
        assert key not in actual, 'Duplicate trajectory identity'
        actual.add(key)
    assert actual == expected and len(rows) == len(expected), 'Scenario/seed schedule mismatch'


def run_tests(output):
    before = hashes(SOURCE_FILES)
    test_hashes = hashes(TEST_FILES)
    inherited = inherited_hashes()
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromNames([Path(name).stem for name in TEST_FILES])
    with (output / 'tests.log').open('w') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    manifest = {
        'passed': result.wasSuccessful(), 'test_count': result.testsRun, 'inherited_tests': INHERITED_TESTS,
        'new_tests': result.testsRun - INHERITED_TESTS, 'failures': len(result.failures),
        'errors': len(result.errors), 'skipped': len(result.skipped), 'elapsed_seconds': time.monotonic() - started,
        'test_sha256': test_hashes, 'source_sha256': before, 'economic_source_sha256': hashes(ECONOMIC_FILES),
        'inherited_source_sha256': inherited, 'source_unchanged': before == hashes(SOURCE_FILES),
        'tests_unchanged': test_hashes == hashes(TEST_FILES), 'inherited_unchanged': inherited == inherited_hashes(),
    }
    write_json(output / 'tests_manifest.json', manifest)
    assert manifest['passed'] and result.testsRun > INHERITED_TESTS and not result.skipped, manifest
    assert manifest['source_unchanged'] and manifest['tests_unchanged'] and manifest['inherited_unchanged']
    print(f'TESTS {result.testsRun} passed; {manifest["elapsed_seconds"]:.2f}s', flush=True)
    return manifest


def verified_tests(output):
    path = output / 'tests_manifest.json'
    if not path.exists():
        return run_tests(output)
    manifest = read_json(path)
    assert manifest['passed'] and manifest['test_count'] > INHERITED_TESTS
    assert manifest['failures'] == manifest['errors'] == manifest['skipped'] == 0
    assert manifest['source_sha256'] == hashes(SOURCE_FILES) and manifest['test_sha256'] == hashes(TEST_FILES)
    assert manifest['inherited_source_sha256'] == inherited_hashes()
    return manifest


def preserve_absent(output, filenames):
    for name in filenames:
        if (output / name).exists():
            raise FileExistsError(f'Preserve existing result: {output / name}')


def read_rows(path):
    with gzip.open(path, 'rt') as stream:
        return [json.loads(line) for line in stream]


def load_traces(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def write_traces(path, traces):
    with gzip.open(path, 'wt') as stream:
        json.dump(traces, stream, ensure_ascii=False)


def execute(output, phases, workers, prefix):
    names = [f'{prefix}_runs.partial.jsonl.gz', f'{prefix}_runs.jsonl.gz', f'{prefix}_traces.json.gz']
    formal = 'main' in phases or 'stress' in phases
    if formal:
        names += ['round_ledgers.partial.jsonl.gz', 'raw_round_ledgers.partial.jsonl.gz',
                  'round_ledgers.jsonl.gz', 'raw_round_ledgers.jsonl.gz']
    preserve_absent(output, names)
    tasks = build_tasks(phases)
    rows, traces = [], {}
    started = time.monotonic()
    cash_count = raw_count = 0
    cash_stream = gzip.open(output / 'round_ledgers.partial.jsonl.gz', 'wt') if formal else None
    raw_stream = gzip.open(output / 'raw_round_ledgers.partial.jsonl.gz', 'wt') if formal else None
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool, gzip.open(output / f'{prefix}_runs.partial.jsonl.gz', 'wt') as stream:
            for i, (row, cash, raw, trace) in enumerate(pool.map(run_one, tasks, chunksize=4), 1):
                rows.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                if cash is not None:
                    assert cash_stream is not None and raw_stream is not None
                    cash_stream.write(json.dumps(cash, ensure_ascii=False) + '\n')
                    raw_stream.write(json.dumps(raw, ensure_ascii=False) + '\n')
                    cash_count += len(cash['rows']); raw_count += len(raw['rows'])
                if trace is not None:
                    traces[trace_key(row)] = trace
                if i % (200 if formal else 30) == 0:
                    print(f'{prefix.upper()} {i}/{len(tasks)} complete; {time.monotonic() - started:.1f}s', flush=True)
    finally:
        if cash_stream is not None:
            cash_stream.close(); raw_stream.close()
    assert_schedule(rows, phases)
    (output / f'{prefix}_runs.partial.jsonl.gz').replace(output / f'{prefix}_runs.jsonl.gz')
    if formal:
        assert cash_count == raw_count == 398520
        for filename in ('round_ledgers', 'raw_round_ledgers'):
            (output / f'{filename}.partial.jsonl.gz').replace(output / f'{filename}.jsonl.gz')
    assert set(traces) == {f'{p}:{m}:{sid}:{seed}' for p, m, seed, sid, *_ in tasks if seed == PHASES[p][0]}
    write_traces(output / f'{prefix}_traces.json.gz', traces)
    return rows, traces, time.monotonic() - started, cash_count, raw_count


def selected_record(row):
    return {
        'countries': {n: {field: c[field] for field in COUNTRY_SUMMARY_FIELDS} for n, c in row['countries'].items()},
        'world': {field: row['world'][field] for field in WORLD_SUMMARY_FIELDS},
    }


def comparison_definitions(groups):
    definitions = {}
    cohorts = [(phase, sid) for phase, conditions in (('main', NORMAL), ('stress', STRESS_SCENARIOS))
               for sid, *_ in conditions]
    if any(k.startswith('pilot_ai:') for k in groups):
        cohorts.insert(0, ('pilot', 'None:normal'))
    def key(phase, mode, sid):
        if phase == 'pilot':
            phase = 'pilot_ai' if mode in AI_MODES else 'pilot_economic'
        return f'{phase}:{mode}:{sid}'
    for phase, sid in cohorts:
        for left, right in MODE_COMPARISONS:
            left_key, right_key = key(phase, left, sid), key(phase, right, sid)
            if left_key in groups and right_key in groups:
                definitions[f'{phase}:{left}->{right}:{sid}'] = {'kind': 'mode', 'terms': {left_key: -1, right_key: 1}}
        terms = {key(phase, mode, sid): weight for mode, weight in
                 (('ai_combined', 1), ('operating_first', -1), ('no_durable_boost', -1), ('baseline', 1))}
        if set(terms) <= set(groups):
            definitions[f'{phase}:ai_interaction:{sid}'] = {'kind': 'interaction', 'terms': terms}
    for mode in ALL_MODES:
        control = f'stress:{mode}:None:normal'
        if control not in groups:
            continue
        for sid, *_ in STRESS_SCENARIOS[1:]:
            definitions[f'stress:{mode}:{sid}'] = {'kind': 'behavior', 'terms': {control: -1, f'stress:{mode}:{sid}': 1}}
        for name in ('Technia', 'Novia'):
            sid = f'Mechania:idle+{name}:minimum'
            definitions[f'stress:{mode}:Mechania:idle->{sid}'] = {'kind': 'compound_behavior', 'terms': {
                f'stress:{mode}:Mechania:idle': -1, f'stress:{mode}:{sid}': 1}}
    return definitions


def flatten_numeric(value, prefix=''):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(flatten_numeric(child, f'{prefix}.{key}' if prefix else key))
        return result
    return {prefix: float(value)} if type(value) in (int, float) else {}


def summarize(rows, metadata):
    groups = defaultdict(list)
    for row in rows:
        groups[f'{row["phase"]}:{row["mode"]}:{row["scenario"]}'].append(row)
    selected = {key: [selected_record(row) for row in group] for key, group in groups.items()}
    experiments = {key: grouped(group) for key, group in selected.items()}
    definitions = comparison_definitions(groups)
    flat = {key: {row['seed']: flatten_numeric(selected_record(row)) for row in group} for key, group in groups.items()}
    paired = {}
    for key, definition in definitions.items():
        terms = definition['terms']
        seedsets = [set(flat[group]) for group in terms]
        assert all(seeds == seedsets[0] for seeds in seedsets), ('comparison seeds differ', key)
        metrics = set.intersection(*(set(values) for group in terms for values in flat[group].values()))
        paired[key] = {metric: stats([sum(weight * flat[group][seed][metric] for group, weight in terms.items())
                                      for seed in sorted(seedsets[0])]) for metric in sorted(metrics)}
    return {'metadata': metadata, 'experiments': experiments, 'paired': paired, 'contrast_definitions': definitions}


def freeze_state(output):
    return {
        'source_sha256': hashes(SOURCE_FILES), 'test_sha256': hashes(TEST_FILES),
        'inherited_source_sha256': inherited_hashes(), 'goals_sha256': digest(GOALS_FILE),
        'declared_protocol_sha256': digest(PROTOCOL_FILE), 'run_plan_sha256': digest(output / 'pre_run_plan.json'),
        'tests_manifest_sha256': digest(output / 'tests_manifest.json'),
    }


def verify_state(output, state):
    assert freeze_state(output) == {key: state[key] for key in freeze_state(output)}, 'Source/tests/protocol/targets changed'
    assert read_json(output / 'pre_run_plan.json') == protocol()
    assert digest(GOALS_FILE) == GOALS_SHA256


def ai_pilot(output, workers):
    preserve_absent(output, ('pre_run_plan.json', 'ai_pilot_manifest.json', 'ai_pilot_summary.json'))
    tests = verified_tests(output)
    fixed_goals()
    write_json(output / 'pre_run_plan.json', protocol())
    before = freeze_state(output)
    started = now()
    rows, traces, elapsed, _, _ = execute(output, ('pilot_ai',), workers, 'ai_pilot')
    verify_state(output, before)
    manifest = {**before, 'schema': 'v13-ai-pilot-1', 'started_at': started, 'completed_at': now(),
        'completed_games': 120, 'pilot_games': 120, 'formal_games': 0, 'economic_pilot_not_executed': True,
        'representative_traces': 4, 'elapsed_seconds': elapsed, 'tests_completed': tests['test_count'],
        'verification_calls': sum(r['world']['verify_calls'] for r in rows), 'verification_failures': 0,
        'source_unchanged': True, 'runs_sha256': digest(output / 'ai_pilot_runs.jsonl.gz'),
        'traces_sha256': digest(output / 'ai_pilot_traces.json.gz')}
    write_json(output / 'ai_pilot_manifest.json', manifest)
    write_json(output / 'ai_pilot_summary.json', summarize(rows, manifest))
    print('AI PILOT COMPLETE; ECONOMIC PILOT AND FORMAL NOT RUN', flush=True)
    print('AI_PILOT_SHA256 ' + digest(output / 'ai_pilot_manifest.json'), flush=True)


def economic_pilot(output, workers, approved):
    assert approved and approved == digest(output / 'ai_pilot_manifest.json'), 'Reviewed AI-pilot manifest SHA256 is required'
    preserve_absent(output, ('economic_pilot_start.json', 'economic_pilot_manifest.json', 'pilot_summary.json', 'freeze_manifest.json'))
    ai = read_json(output / 'ai_pilot_manifest.json')
    verify_state(output, ai)
    verified_tests(output)
    assert ai['runs_sha256'] == digest(output / 'ai_pilot_runs.jsonl.gz')
    assert ai['traces_sha256'] == digest(output / 'ai_pilot_traces.json.gz')
    write_json(output / 'economic_pilot_start.json', {'started_at': now(), 'approved_ai_pilot_sha256': approved, **freeze_state(output)})
    rows, traces, elapsed, _, _ = execute(output, ('pilot_economic',), workers, 'economic_pilot')
    verify_state(output, ai)
    manifest = {**freeze_state(output), 'schema': 'v13-economic-pilot-1', 'completed_at': now(),
        'completed_games': 60, 'pilot_games_total': 180, 'formal_games': 0,
        'approved_ai_pilot_sha256': approved, 'economic_pilot_start_sha256': digest(output / 'economic_pilot_start.json'),
        'representative_traces': 2, 'elapsed_seconds': elapsed,
        'verification_calls': sum(r['world']['verify_calls'] for r in rows), 'verification_failures': 0,
        'source_unchanged': True, 'runs_sha256': digest(output / 'economic_pilot_runs.jsonl.gz'),
        'traces_sha256': digest(output / 'economic_pilot_traces.json.gz')}
    write_json(output / 'economic_pilot_manifest.json', manifest)
    all_rows = read_rows(output / 'ai_pilot_runs.jsonl.gz') + rows
    assert_schedule(all_rows, ('pilot_ai', 'pilot_economic'))
    write_json(output / 'pilot_summary.json', summarize(all_rows, manifest))
    freeze = {**freeze_state(output), 'schema': 'v13-causal-freeze-1', 'created_at': now(), 'formal_not_executed': True,
        'pilot_games': 180, 'formal_games_planned': 4920,
        'ai_pilot_manifest_sha256': approved, 'economic_pilot_manifest_sha256': digest(output / 'economic_pilot_manifest.json'),
        'economic_pilot_start_sha256': digest(output / 'economic_pilot_start.json'),
        'pilot_summary_sha256': digest(output / 'pilot_summary.json'),
        'pilot_runs_sha256': {name: digest(output / name) for name in ('ai_pilot_runs.jsonl.gz', 'economic_pilot_runs.jsonl.gz')},
        'pilot_traces_sha256': {name: digest(output / name) for name in ('ai_pilot_traces.json.gz', 'economic_pilot_traces.json.gz')},
    }
    write_json(output / 'freeze_manifest.json', freeze)
    print('BOTH PILOTS COMPLETE; FORMAL NOT RUN', flush=True)
    print('FREEZE_SHA256 ' + digest(output / 'freeze_manifest.json'), flush=True)


def verify_freeze(output, approved):
    assert approved and approved == digest(output / 'freeze_manifest.json'), 'Reviewed final freeze SHA256 is required'
    freeze = read_json(output / 'freeze_manifest.json')
    assert freeze['schema'] == 'v13-causal-freeze-1' and freeze['formal_not_executed']
    verify_state(output, freeze)
    verified_tests(output)
    for key, filename in (('ai_pilot_manifest_sha256', 'ai_pilot_manifest.json'),
            ('economic_pilot_manifest_sha256', 'economic_pilot_manifest.json'),
            ('economic_pilot_start_sha256', 'economic_pilot_start.json'), ('pilot_summary_sha256', 'pilot_summary.json')):
        assert freeze[key] == digest(output / filename), (filename, 'changed after review')
    for key in ('pilot_runs_sha256', 'pilot_traces_sha256'):
        for filename, expected in freeze[key].items():
            assert digest(output / filename) == expected
    return freeze


def final(output, workers, approved):
    preserve_absent(output, ('formal_start.json', 'run_manifest.json', 'summary.json', 'runs.jsonl.gz', 'first_seed_traces.json.gz'))
    freeze = verify_freeze(output, approved)
    write_json(output / 'formal_start.json', {'started_at': now(), 'approved_freeze_sha256': approved, **freeze_state(output)})
    rows, traces, elapsed, cash_count, raw_count = execute(output, ('main', 'stress'), workers, 'formal')
    verify_state(output, freeze)
    assert approved == digest(output / 'freeze_manifest.json')
    for prefix in ('ai_pilot', 'economic_pilot'):
        rows.extend(read_rows(output / f'{prefix}_runs.jsonl.gz'))
        traces.update(load_traces(output / f'{prefix}_traces.json.gz'))
    assert_schedule(rows, tuple(PHASES))
    assert len(rows) == 5100 and len(traces) == 156
    with gzip.open(output / 'runs.jsonl.gz', 'wt') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    write_traces(output / 'first_seed_traces.json.gz', traces)
    metadata = {**protocol(), **freeze_state(output), 'completed_games': 5100, 'formal_games': 4920,
        'formal_cash_ledger_rows': cash_count, 'formal_raw_ledger_rows': raw_count,
        'verification_calls': sum(r['world']['verify_calls'] for r in rows),
        'formal_verification_calls': sum(r['world']['verify_calls'] for r in rows if r['phase'] in ('main', 'stress')),
        'verification_failures': 0, 'source_unchanged': True,
        'source_sha256_after': hashes(SOURCE_FILES), 'test_sha256_after': hashes(TEST_FILES),
        'tests_completed': read_json(output / 'tests_manifest.json')['test_count'],
        'freeze_sha256': approved, 'formal_start_sha256': digest(output / 'formal_start.json'),
        'formal_started_after_freeze': True, 'formal_elapsed_seconds': elapsed,
        'pilot_ai_elapsed_seconds': read_json(output / 'ai_pilot_manifest.json')['elapsed_seconds'],
        'pilot_economic_elapsed_seconds': read_json(output / 'economic_pilot_manifest.json')['elapsed_seconds'],
        'test_games_excluded': True, 'posthoc_reference_is_extra_game': False, 'completed_at': now()}
    write_json(output / 'summary.json', summarize(rows, metadata))
    write_json(output / 'run_manifest.json', metadata)
    print(f'DONE 5100 unique games: 180 pilot + 4920 formal; {metadata["verification_calls"]} invariant calls', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('ai-pilot', 'economic-pilot', 'final'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--approve-ai-pilot')
    parser.add_argument('--approve-freeze')
    parser.add_argument('--tests-only', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('workers must be positive')
    if args.dry_run:
        print(json.dumps({**protocol(), 'executed_games': 0}, ensure_ascii=False)); return
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.tests_only:
        run_tests(output); return
    if args.stage == 'ai-pilot':
        ai_pilot(output, args.workers)
    elif args.stage == 'economic-pilot':
        economic_pilot(output, args.workers, args.approve_ai_pilot)
    elif args.stage == 'final':
        final(output, args.workers, args.approve_freeze)
    else:
        parser.error('choose --stage or --tests-only')


if __name__ == '__main__':
    main()
