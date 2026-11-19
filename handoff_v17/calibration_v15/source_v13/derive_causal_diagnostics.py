"""Read-only v13 strategy frequencies and trade-channel decompositions.

All calculations use existing saved trajectories. No game or scoring modules
are imported; no new simulation, policy choice or parameter fitting is done.
"""
from __future__ import annotations
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from validate_evaluation_report import statistics_for
from validate_routing_report import nested

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'causal_results'
NAMES = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')
MODES = ('baseline', 'operating_first', 'no_durable_boost', 'ai_combined', 'electronics_input', 'combined_input')
METRICS = ('score', 'cash', 'happy')
EPS = 1e-9


def compare(left, right, path):
    assert left.keys() == right.keys()
    differences = {seed: nested(right[seed], path) - nested(left[seed], path) for seed in sorted(left)}
    return {
        **statistics_for(list(differences.values())),
        'higher': sum(v > EPS for v in differences.values()),
        'same': sum(abs(v) <= EPS for v in differences.values()),
        'lower': sum(v < -EPS for v in differences.values()),
        'higher_seed_deltas': {str(seed): value for seed, value in differences.items() if value > EPS},
        'control_mean': statistics.mean(nested(row, path) for row in left.values()),
        'treatment_mean': statistics.mean(nested(row, path) for row in right.values()),
    }


def main():
    manifest = json.loads((OUT / 'run_manifest.json').read_text())
    assert manifest['completed_games'] == 5100 and manifest['formal_games'] == 4920
    groups = defaultdict(dict)
    with gzip.open(OUT / 'runs.jsonl.gz', 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            if row['phase'] not in ('main', 'stress'):
                continue
            key = row['phase'], row['mode'], row['scenario']
            assert row['seed'] not in groups[key]
            groups[key][row['seed']] = row
    main_effects, behaviors, channels, stress_controls = {}, {}, {}, {}
    for mode in MODES:
        normal = groups[('stress', mode, 'None:normal')]
        for name in NAMES:
            if mode != 'baseline':
                main_effects[f'{mode}:{name}'] = {
                    metric: compare(groups[('main', 'baseline', 'None:normal')],
                                    groups[('main', mode, 'None:normal')], f'countries.{name}.{metric}')
                    for metric in METRICS}
            for style in ('minimum', 'idle'):
                selected = groups[('stress', mode, f'{name}:{style}')]
                behaviors[f'{mode}:{name}:{style}'] = {
                    metric: compare(normal, selected, f'countries.{name}.{metric}') for metric in METRICS}
        for style in ('normal', 'cheap', 'minimum'):
            case = 'None:normal' if style == 'normal' else f'Technia:{style}'
            selected = groups[('stress', mode, case)]
            paths = [f'countries.Technia.channel_stats.{channel}.{field}'
                     for channel in ('market', 'direct', 'barter')
                     for field in ('sold_units', 'bought_units', 'sales_cash', 'purchase_cash')]
            paths += [f'countries.Technia.economic_decomposition.electronics.{field}.{key}'
                      for field, keys in (('cash_sale_origin', ('own_produced', 'own_initial', 'resold_foreign')),
                                          ('cash_sales_by_generation', ('1', '2', '3')),
                                          ('transferred_units_by_generation', ('1', '2', '3')))
                      for key in keys]
            paths += [f'countries.Technia.{metric}' for metric in
                      ('cash', 'happy', 'revenue', 'purchases', 'investment', 'score', 'all_goods_unique_used')]
            channels[f'{mode}:{style}'] = {path: statistics_for([nested(row, path) for row in selected.values()]) for path in paths}
        for case, control in (
            ('None:no_trade', 'None:normal'),
            ('Mechania:idle', 'None:normal'),
            ('Mechania:idle+Technia:minimum', 'Mechania:idle'),
            ('Mechania:idle+Novia:minimum', 'Mechania:idle'),
        ):
            paths = [f'countries.{name}.{metric}' for name in ('Mechania', 'Mineria', 'Technia', 'Novia')
                     for metric in ('cash', 'happy', 'investment')]
            paths += [f'countries.{name}.routing.g3_electronics_used' for name in ('Technia', 'Novia')]
            paths += ['world.happy', 'world.transactions', 'world.original_production_failures']
            stress_controls[f'{mode}:{control}->{case}'] = {
                path: compare(groups[('stress', mode, control)], groups[('stress', mode, case)], path)
                for path in paths}
    value = {
        'schema': 'v13-readonly-strategy-diagnostics-1',
        'source_run_manifest_sha256': hashlib.sha256((OUT / 'run_manifest.json').read_bytes()).hexdigest(),
        'source_summary_sha256': hashlib.sha256((OUT / 'summary.json').read_bytes()).hexdigest(),
        'source_raw_sha256': hashlib.sha256((OUT / 'runs.jsonl.gz').read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'new_games': 0, 'tolerance': EPS,
        'main_policy_effects': main_effects, 'stress_minimum_idle': behaviors,
        'technia_price_channels': channels, 'stress_controls': stress_controls,
        'limits': [
            'Higher frequencies compare one saved policy with its declared same-seed control, not student win probabilities.',
            'Public minimum asks do not replace negotiated or barter terms.',
            'Channel cash is all-goods receipts/outlays; generation and origin submaps here concern electronics only.',
            'Cash sales minus purchases is trade cash flow, not manufacturing profit.',
            'No policy is fitted or selected by this diagnostic script.',
        ],
    }
    path = OUT / 'strategy_frequency_diagnostics.json'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(path), 'new_games': 0, 'main_comparisons': len(main_effects),
                      'stress_behavior_comparisons': len(behaviors), 'channel_groups': len(channels),
                      'control_comparisons': len(stress_controls)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
