"""Recompute marked v12 report numbers from frozen saved trajectories.

No scorer or engine imports, simulation, target fitting or source mutation.
Calibration-only policy selections are rechecked before held-out report cells.
Unmarked prose and table-label semantics remain outside numeric QA coverage.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

from validate_routing_report import MarkerParser, nested, read_json
from validate_evaluation_report import statistics_for, same_stats

ROOT = Path(__file__).resolve().parent
NAMES = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')
VIEWS = ('legacy', 'targets', 'headroom', 'targets_headroom')
POLICIES = ('normal', 'invest', 'trade')
CALIBRATION = ('None:normal',) + tuple(f'{n}:{s}' for n in NAMES for s in ('invest', 'trade'))
HOLDOUT = ('None:normal',) + tuple(f'{n}:{s}' for n in NAMES for s in ('invest', 'trade', 'cheap', 'minimum', 'idle'))
STRESS = tuple(f'{n}:minimum_passive' for n in NAMES) + (
    'Mechania:idle', 'Mechania:idle+Technia:minimum', 'Mechania:idle+Novia:minimum', 'None:no_trade',
)
PHASES = {
    'calibration': (CALIBRATION, range(90000, 90060)),
    'holdout': (HOLDOUT, range(92000, 92100)),
    'stress': (STRESS, range(94000, 94030)),
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def diagnostic(row, view, metric):
    values = [row['countries'][name]['growth_evaluation'][view] for name in NAMES]
    if metric == 'original_score_spread':
        return max(v['score'] for v in values) - min(v['score'] for v in values)
    if metric == 'original_mean_score':
        return statistics.mean(v['score'] for v in values)
    fields = {
        'economic_growth_near_cap_share': 'economic_growth_near_cap',
        'capacity_near_cap_share': 'capacity_near_cap',
        'economic_5pct_sensitivity': 'economic_5pct_sensitivity',
        'capacity_5pct_sensitivity': 'capacity_5pct_sensitivity',
    }
    return statistics.mean(v[fields[metric]] for v in values)


def verify_report(results, report, output):
    summary = read_json(results / 'summary.json')
    manifest = read_json(results / 'run_manifest.json')
    freeze = read_json(results / 'freeze_manifest.json')
    goals = read_json(results / 'goals.json')
    selection = read_json(results / 'frozen_selection.json')
    start = read_json(results / 'holdout_start.json')
    assert summary['metadata'] == manifest, 'Summary/manifest mismatch'
    assert manifest['completed_games'] == 4180
    assert (manifest['calibration_games'], manifest['holdout_games'], manifest['stress_games']) == (780, 3100, 300)
    assert manifest['rounds'] == manifest['countries'] == 9
    assert manifest['views'] == list(VIEWS) and manifest['ranked_countries'] == list(NAMES)
    assert manifest['source_unchanged'] and manifest['verification_failures'] == 0
    assert manifest['representative_traces'] == 54
    assert manifest['holdout_cash_ledger_rows'] == manifest['holdout_raw_ledger_rows'] == 251100
    assert not manifest['score_views_are_extra_games'] and manifest['holdout_started_after_freeze']
    assert manifest['exclude_peer_policy_observations'] and manifest['no_tuning_after_holdout']
    assert manifest['freeze_sha256'] == start['approved_freeze_sha256'] == digest(results / 'freeze_manifest.json')
    assert datetime.fromisoformat(freeze['created_at']) < datetime.fromisoformat(start['started_at'])
    for key, filename in (
        ('protocol_sha256', 'pre_run_plan.json'), ('goals_sha256', 'goals.json'),
        ('selection_sha256', 'frozen_selection.json'), ('tests_manifest_sha256', 'tests_manifest.json'),
        ('calibration_runs_sha256', 'calibration_runs.jsonl.gz'),
        ('calibration_manifest_sha256', 'calibration_manifest.json'),
    ):
        assert manifest[key] == freeze[key] == digest(results / filename), (key, 'frozen file mismatch')
    for key in ('protocol_sha256', 'goals_sha256', 'selection_sha256', 'source_sha256'):
        assert start[key] == freeze[key] == manifest[key]
    assert start['test_sha256'] == freeze['test_sha256'] == manifest['test_sha256_before'] == manifest['test_sha256_after']
    assert manifest['source_sha256_before'] == manifest['source_sha256_after'] == freeze['source_sha256']
    for filename, expected in freeze['source_sha256'].items():
        assert digest(ROOT / filename) == expected, (filename, 'source modified')
    for filename, expected in freeze['test_sha256'].items():
        assert digest(ROOT / filename) == expected, (filename, 'test modified')
    assert goals['source'] == selection['source'] == 'calibration_only'
    assert goals['calibration']['seeds'] == selection['calibration_seeds'] == list(range(90000, 90060))
    assert selection['tie_order'] == list(POLICIES) and selection['tie_tolerance'] == 1e-9

    specifications = {}
    for phase, (scenarios, seeds) in PHASES.items():
        assert manifest[phase + '_seed_range'] == [seeds.start, seeds.stop - 1]
        specs = manifest[phase + '_scenarios']
        assert tuple(s['scenario'] for s in specs) == scenarios
        specifications.update({(phase, s['scenario']): s for s in specs})
    groups = defaultdict(list)
    seen = set()
    with gzip.open(results / 'runs.jsonl.gz', 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            identity = row['phase'], row['scenario'], row['seed']
            assert identity not in seen, 'Duplicate economic trajectory'
            seen.add(identity)
            assert row['mode'] == 'market_first'
            spec = specifications[(row['phase'], row['scenario'])]
            assert (row['focal'], row['style']) == (spec['focal'], spec['style'])
            behaviors = dict(spec['behaviors'])
            if spec['focal'] is not None:
                behaviors[spec['focal']] = spec['style']
            assert row['behaviors'] == behaviors
            groups[f'{row["phase"]}:market_first:{row["scenario"]}'].append(row)
    expected = {(phase, scenario, seed) for phase, (scenarios, seeds) in PHASES.items()
                for scenario in scenarios for seed in seeds}
    assert seen == expected and len(seen) == 4180, 'Formal schedule coverage mismatch'
    assert set(groups) == set(summary['experiments'])
    for group, rows in groups.items():
        assert len(rows) == summary['experiments'][group]['n']

    # The selected policy must derive from the country's own three calibration
    # groups, not peers' focal worlds or a held-out best-policy search.
    checked_selections = 0
    for view in VIEWS:
        assert set(selection['selections'][view]) == set(NAMES)
        for name in NAMES:
            means = {}
            for policy in POLICIES:
                scenario = 'None:normal' if policy == 'normal' else f'{name}:{policy}'
                group = f'calibration:market_first:{scenario}'
                means[policy] = statistics.mean(r['countries'][name]['growth_evaluation'][view]['score'] for r in groups[group])
            best = max(means.values())
            chosen = next(policy for policy in POLICIES if means[policy] >= best - 1e-9)
            saved = selection['selections'][view][name]
            assert saved['policy'] == chosen and saved['calibration_n'] == 60
            assert saved['scenario'] == ('None:normal' if chosen == 'normal' else f'{name}:{chosen}')
            assert set(saved['policy_means']) == set(POLICIES)
            for policy in POLICIES:
                assert math.isclose(saved['policy_means'][policy], means[policy], abs_tol=1e-9, rel_tol=1e-12)
            assert math.isclose(saved['calibration_mean_score'], means[chosen], abs_tol=1e-9, rel_tol=1e-12)
            checked_selections += 1

    pairs = {}
    for phase, scenarios in (('calibration', CALIBRATION), ('holdout', HOLDOUT)):
        for scenario in scenarios:
            if scenario == 'None:normal':
                continue
            key = f'{phase}:market_first:{scenario}'
            pairs[key] = (f'{phase}:market_first:None:normal', key, specifications[(phase, scenario)]['focal'])
    for name in ('Technia', 'Novia'):
        key = f'stress:market_first:Mechania:idle->Mechania:idle+{name}:minimum'
        pairs[key] = ('stress:market_first:Mechania:idle', f'stress:market_first:Mechania:idle+{name}:minimum', name)
    assert set(pairs) == set(summary['paired'])
    assert set(summary['growth_diagnostics']) == set(summary['score_view_pairs']) == set(groups)

    parser = MarkerParser()
    parser.feed(report.read_text(encoding='utf-8'))
    parser.close()
    assert parser.active is None, 'Unclosed numeric marker'
    coverage = set()
    numeric_values = 0
    means_cache = {}
    pairs_cache = {}
    diagnostic_cache = {}
    view_cache = {}
    goals_checked = set()

    def precision(descriptor):
        value = descriptor.get('digits', 2)
        if type(value) is not int or not 0 <= value <= 8:
            raise ValueError('Invalid numeric precision')
        return value

    def values_for(experiment, metric):
        values = [nested(row, metric) for row in groups[experiment]]
        assert all(type(v) in (int, float) and math.isfinite(v) for v in values)
        return values

    def mean_stats(experiment, metric):
        key = experiment, metric
        if key not in means_cache:
            measured = statistics_for(values_for(experiment, metric))
            same_stats(measured, summary['experiments'][experiment]['metrics'][metric], key)
            means_cache[key] = measured
        return means_cache[key]

    def paired_stats(pair, metric):
        key = pair, metric
        if key not in pairs_cache:
            left_key, right_key, focal = pairs[pair]
            left = {row['seed']: row for row in groups[left_key]}
            right = {row['seed']: row for row in groups[right_key]}
            assert left.keys() == right.keys()
            if metric == 'world.other_original_five_happy':
                assert focal in NAMES
                values = [statistics.mean(right[s]['countries'][n]['happy'] - left[s]['countries'][n]['happy']
                          for n in NAMES if n != focal) for s in sorted(left)]
            else:
                values = [nested(right[s], metric) - nested(left[s], metric) for s in sorted(left)]
            measured = statistics_for(values)
            same_stats(measured, summary['paired'][pair][metric], key)
            pairs_cache[key] = measured
        return pairs_cache[key]

    def diagnostic_stats(experiment, view, metric):
        key = experiment, view, metric
        if key not in diagnostic_cache:
            measured = statistics_for([diagnostic(row, view, metric) for row in groups[experiment]])
            same_stats(measured, summary['growth_diagnostics'][experiment][view][metric], key)
            diagnostic_cache[key] = measured
        return diagnostic_cache[key]

    def view_stats(experiment, comparison, metric):
        key = experiment, comparison, metric
        if key not in view_cache:
            left, right = comparison.split('->')
            assert left == 'legacy' and right in VIEWS[1:]
            if metric == 'world.original_score_spread':
                values = [diagnostic(row, right, 'original_score_spread') - diagnostic(row, left, 'original_score_spread')
                          for row in groups[experiment]]
            else:
                prefix, country, field = metric.split('.')
                assert prefix == 'countries' and country in NAMES
                values = [row['countries'][country]['growth_evaluation'][right][field] -
                          row['countries'][country]['growth_evaluation'][left][field] for row in groups[experiment]]
            measured = statistics_for(values)
            same_stats(measured, summary['score_view_pairs'][experiment][comparison][metric], key)
            view_cache[key] = measured
        return view_cache[key]

    def ci_text(measured, digits):
        return f'{measured["mean"]:+,.{digits}f} [{measured["ci95"][0]:+,.{digits}f}, {measured["ci95"][1]:+,.{digits}f}]'

    def render(descriptor):
        nonlocal numeric_values
        if not isinstance(descriptor, dict) or 'kind' not in descriptor:
            raise ValueError('Malformed numeric descriptor')
        kind = descriptor['kind']
        if kind == 'literal':
            if not isinstance(descriptor.get('text'), str):
                raise ValueError('Literal text must be a string')
            return descriptor['text']
        if kind == 'concat':
            if not isinstance(descriptor.get('parts'), list) or not descriptor['parts']:
                raise ValueError('Empty numeric concatenation')
            return ''.join(render(part) for part in descriptor['parts'])
        if kind == 'mean':
            experiment, metric = descriptor['experiment'], descriptor['metric']
            measured = mean_stats(experiment, metric)
            factor = descriptor.get('factor', 1)
            if type(factor) not in (int, float) or not math.isfinite(factor):
                raise ValueError('Mean scaling factor must be a finite number')
            coverage.add((experiment, metric))
            numeric_values += 1
            return f'{measured["mean"] * factor:,.{precision(descriptor)}f}'
        if kind == 'ci':
            pair, metric = descriptor['pair'], descriptor['metric']
            measured = paired_stats(pair, metric)
            coverage.add(('pair:' + pair, metric))
            numeric_values += 1
            return ci_text(measured, precision(descriptor))
        if kind == 'goal':
            value = nested(goals, descriptor['metric'])
            assert type(value) in (int, float) and math.isfinite(value)
            goals_checked.add(descriptor['metric'])
            numeric_values += 1
            return f'{value:,.{precision(descriptor)}f}'
        if kind == 'diagnostic':
            experiment, view, metric = descriptor['experiment'], descriptor['view'], descriptor['metric']
            measured = diagnostic_stats(experiment, view, metric)
            coverage.add((experiment, f'world.growth_diagnostics.{view}.{metric}'))
            numeric_values += 1
            return f'{measured["mean"]:,.{precision(descriptor)}f}'
        if kind == 'view_ci':
            experiment, comparison, metric = descriptor['experiment'], descriptor['comparison'], descriptor['metric']
            measured = view_stats(experiment, comparison, metric)
            coverage.add((experiment, f'view_pair.{comparison}.{metric}'))
            numeric_values += 1
            return ci_text(measured, precision(descriptor))
        if kind == 'count':
            experiment, metric = descriptor['experiment'], descriptor['metric']
            values = values_for(experiment, metric)
            coverage.add((experiment, metric))
            numeric_values += 1
            return f'{sum(v > 0 for v in values)}/{len(values)}'
        if kind == 'anycount':
            experiment, metrics = descriptor['experiment'], descriptor['metrics']
            if not isinstance(metrics, list) or not metrics:
                raise ValueError('Any-count requires metric paths')
            values = [values_for(experiment, metric) for metric in metrics]
            numerator = sum(any(column[i] > 0 for column in values) for i in range(len(groups[experiment])))
            coverage.update((experiment, metric) for metric in metrics)
            numeric_values += 1
            return f'{numerator}/{len(groups[experiment])}'
        if kind == 'paired_greater_count':
            experiment, control, metric = descriptor['experiment'], descriptor['control'], descriptor['metric']
            assert experiment.split(':', 1)[0] == control.split(':', 1)[0], 'Different phases cannot be paired'
            selected = {row['seed']: row for row in groups[experiment]}
            baseline = {row['seed']: row for row in groups[control]}
            assert selected.keys() == baseline.keys()
            numerator = sum(nested(selected[s], metric) > nested(baseline[s], metric) + 1e-9 for s in selected)
            coverage.add((experiment, metric))
            coverage.add((control, metric))
            numeric_values += 1
            return f'{numerator}/{len(selected)}'
        if kind == 'top_count':
            experiment, metric, metrics = descriptor['experiment'], descriptor['metric'], descriptor['metrics']
            if not isinstance(metrics, list) or len(metrics) != 6 or metric not in metrics:
                raise ValueError('Top-count requires six original-country score paths including focal path')
            assert {path.split('.')[1] for path in metrics} == set(NAMES)
            assert len({'.'.join(path.split('.')[2:]) for path in metrics}) == 1, 'Top-count score views differ'
            numerator = sum(nested(row, metric) >= max(nested(row, path) for path in metrics) - 1e-9 for row in groups[experiment])
            coverage.update((experiment, path) for path in metrics)
            numeric_values += 1
            return f'{numerator}/{len(groups[experiment])}'
        raise ValueError('Unknown numeric marker kind: ' + str(kind))

    errors = []
    for index, cell in enumerate(parser.markers):
        try:
            expected_text = render(cell['descriptor'])
            if cell['text'] != expected_text:
                errors.append({'cell': index, 'actual': cell['text'], 'expected': expected_text, 'descriptor': cell['descriptor']})
        except Exception as exc:
            errors.append({'cell': index, 'error': str(exc), 'descriptor': cell['descriptor']})
    if len(parser.markers) < 150:
        errors.append({'coverage': 'Fewer than 150 numeric cells were labelled'})
    required_holdout = {f'holdout:market_first:{scenario}' for scenario in HOLDOUT}
    covered_holdout = {group for group, metric in coverage if group.startswith('holdout:')}
    if not required_holdout <= covered_holdout:
        errors.append({'coverage': 'Missing holdout condition', 'missing': sorted(required_holdout - covered_holdout)})
    for view in VIEWS:
        if not any(f'.growth_evaluation.{view}.' in metric for group, metric in coverage):
            errors.append({'coverage': 'Missing score view', 'missing': view})
    receipt = {
        'status': 'passed' if not errors else 'failed', 'report': str(report),
        'report_sha256': digest(report), 'summary_sha256': digest(results / 'summary.json'),
        'run_manifest_sha256': digest(results / 'run_manifest.json'),
        'goals_sha256': digest(results / 'goals.json'), 'freeze_sha256': digest(results / 'freeze_manifest.json'),
        'selection_sha256': digest(results / 'frozen_selection.json'), 'validator_sha256': digest(__file__),
        'checked_numeric_cells': len(parser.markers), 'checked_numeric_values': numeric_values,
        'independently_recomputed_means': len(means_cache),
        'independently_recomputed_paired_metrics': len(pairs_cache),
        'independently_recomputed_diagnostics': len(diagnostic_cache),
        'independently_recomputed_view_comparisons': len(view_cache),
        'checked_frozen_goal_values': len(goals_checked), 'checked_calibration_policy_selections': checked_selections,
        'tables': parser.tables, 'formal_games': len(seen), 'errors': errors,
        'covered_experiments': sorted({group for group, metric in coverage if not group.startswith('pair:')}),
        'scope': [
            'All 4,180 raw trajectory identities, phase boundaries and exact 13+31+10 condition schedule',
            'Frozen goals, source, tests, protocol and policy selections; freeze predates holdout',
            'All 24 fixed-policy selections recomputed exclusively from own-country calibration groups',
            'Marked means recomputed from raw trajectories and cross-checked with summary',
            'Marked paired seed intervals and within-trajectory score-view intervals independently recomputed',
            'Marked cap, presence, paired score-gain and original-six top-score frequencies',
            'Marked score-spread and cap/sensitivity diagnostics independently recomputed',
            'All 31 holdout conditions and all four score views represented in numeric markers',
        ],
        'limits': 'Unmarked prose and table-label semantics are not exhaustively checked by this numeric validator.',
    }
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors, json.dumps(errors, ensure_ascii=False)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=ROOT / 'growth_results')
    parser.add_argument('--report', type=Path, default=ROOT / 'TRADE_GROWTH_SCORE_REVIEW_V12_KO.html')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results, report = args.results.resolve(), args.report.resolve()
    output = args.output.resolve() if args.output else results / 'report_numeric_qa.json'
    print(json.dumps(verify_report(results, report, output), ensure_ascii=False))


if __name__ == '__main__':
    main()
