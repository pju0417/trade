"""Bounded saved-data check of the unchanged v12 targets reference view."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from validate_evaluation_report import statistics_for

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'causal_results'
NAMES = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')
MODES = ('baseline', 'operating_first', 'no_durable_boost', 'ai_combined', 'electronics_input', 'combined_input')
EPS = 1e-9


def main():
    manifest = json.loads((OUT / 'run_manifest.json').read_text())
    assert manifest['formal_games'] == 4920 and not manifest['fixed_targets_refitted']
    groups = defaultdict(dict)
    with gzip.open(OUT / 'runs.jsonl.gz', 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            if row['phase'] == 'main' or (row['phase'] == 'stress' and row['mode'] == 'electronics_input'):
                groups[(row['phase'], row['mode'], row['scenario'])][row['seed']] = {
                    name: row['countries'][name]['growth_evaluation']['targets']['score'] for name in NAMES}
    baseline = groups[('stress', 'electronics_input', 'None:normal')]
    stress = {}
    for name in NAMES:
        for style in ('minimum', 'idle'):
            selected = groups[('stress', 'electronics_input', f'{name}:{style}')]
            assert set(selected) == set(baseline) == set(range(102000, 102030))
            differences = {seed: selected[seed][name] - baseline[seed][name] for seed in sorted(baseline)}
            stress[f'{name}:{style}'] = {
                **statistics_for(list(differences.values())),
                'higher': sum(v > EPS for v in differences.values()),
                'higher_seed_deltas': {str(seed): value for seed, value in differences.items() if value > EPS},
            }
    highest = {}
    for mode in MODES:
        rows = groups[('main', mode, 'None:normal')]
        assert set(rows) == set(range(100000, 100100))
        highest[mode] = {
            name: sum(values[name] >= max(values.values()) - EPS for values in rows.values()) for name in NAMES}
    value = {
        'schema': 'v13-fixed-targets-check-1', 'new_games': 0, 'refitted': False, 'n_main_per_mode': 100,
        'n_stress_per_condition': 30, 'stress_pairs': 360, 'ties_included': True, 'tolerance': EPS,
        'fixed_goals_sha256': manifest['fixed_goals_sha256'],
        'source_manifest_sha256': hashlib.sha256((OUT / 'run_manifest.json').read_bytes()).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_only_stress': stress, 'main_top_frequencies': highest,
        'limits': 'The existing v12 targets are only a reference score; no goals, game rules or policies are fitted or adopted here.',
    }
    output = OUT / 'fixed_targets_diagnostics.json'
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
