"""Reproduce marked v11 report numbers from frozen formal result files.

No economic imports or simulation. Means, paired seed differences, intervals
and presence counts are independently recomputed from raw saved game rows.
Unmarked narrative and table-label meaning remain outside the numeric claim.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

from validate_routing_report import MarkerParser, nested, read_json

ROOT = Path(__file__).resolve().parent
NAMES = ('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
SCORE_VIEWS = ('legacy','success_only','ready','ready_once')
MAIN_SCENARIOS = ('None:normal',)+tuple(f'{n}:{s}' for n in NAMES for s in ('cheap','minimum','idle'))
STRESS_SCENARIOS = ('None:normal',)+tuple(f'{n}:{s}' for n in NAMES for s in ('minimum','minimum_passive'))+(
    'Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum',
    'Technia:no_high_machine','Novia:no_high_machine','Technia:no_raw','None:no_trade',
)


def statistics_for(values):
    mean = statistics.mean(values)
    error = statistics.stdev(values)/math.sqrt(len(values)) if len(values)>1 else 0
    return {'n':len(values),'mean':mean,'ci95':[mean-1.96*error,mean+1.96*error],
            'min':min(values),'max':max(values)}


def same_stats(actual,expected,label):
    assert actual['n']==expected['n'],(label,'n')
    for key in ('mean','min','max'):
        assert math.isclose(actual[key],expected[key],rel_tol=1e-12,abs_tol=1e-9),(label,key,actual[key],expected[key])
    for a,b in zip(actual['ci95'],expected['ci95']):
        assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-9),(label,'ci95',actual['ci95'],expected['ci95'])


def verify_report(results,report,output):
    summary = read_json(results/'summary.json');manifest = read_json(results/'run_manifest.json')
    assert summary['metadata']==manifest,'Summary/manifest mismatch'
    assert manifest['completed_games']==4400 and manifest['main_games']==3800 and manifest['stress_games']==600
    assert manifest['main_seed_range']==[78000,78199] and manifest['stress_seed_range']==[80000,80029]
    assert manifest['source_unchanged'] and manifest['verification_failures']==0
    assert manifest['rounds']==9 and manifest['countries']==9
    assert manifest['main_cash_ledger_rows']==manifest['main_raw_ledger_rows']==307800
    assert manifest['representative_traces']==39
    assert manifest['scoring_modes']==list(SCORE_VIEWS)
    assert manifest['scoring_views_per_trajectory']==4 and not manifest['shadow_views_are_extra_games']
    assert manifest['main_normal_control_reused']
    assert tuple(s['scenario'] for s in manifest['main_scenarios'])==MAIN_SCENARIOS
    assert tuple(s['scenario'] for s in manifest['stress_scenarios'])==STRESS_SCENARIOS
    specifications = {(phase,s['scenario']):s for phase in ('main','stress') for s in manifest[phase+'_scenarios']}
    groups = defaultdict(list);seen = set()
    with gzip.open(results/'runs.jsonl.gz','rt') as stream:
        for line in stream:
            row = json.loads(line)
            key = row['phase'],row['scenario'],row['seed']
            assert key not in seen,'Duplicate formal trajectory identity'
            seen.add(key)
            assert row['mode']=='market_first'
            spec = specifications[(row['phase'],row['scenario'])]
            assert (row['focal'],row['style'])==(spec['focal'],spec['style'])
            behavior = dict(spec['behaviors'])
            if spec['focal'] is not None:behavior[spec['focal']] = spec['style']
            assert row['behaviors']==behavior
            groups[f'{row["phase"]}:market_first:{row["scenario"]}'].append(row)
    expected = {('main',sid,seed) for sid in MAIN_SCENARIOS for seed in range(78000,78200)}
    expected.update(('stress',sid,seed) for sid in STRESS_SCENARIOS for seed in range(80000,80030))
    assert len(seen)==4400 and seen==expected,'Formal schedule coverage mismatch'
    assert set(groups)==set(summary['experiments'])
    for group,rows in groups.items():assert len(rows)==summary['experiments'][group]['n']
    pairs = {}
    for phase,scenarios in (('main',MAIN_SCENARIOS),('stress',STRESS_SCENARIOS)):
        for sid in scenarios:
            if sid=='None:normal':continue
            key = f'{phase}:market_first:{sid}'
            pairs[key] = (f'{phase}:market_first:None:normal',key,specifications[(phase,sid)]['focal'])
    for name in NAMES:
        pairs[f'main:market_first:{name}:cheap->minimum'] = (
            f'main:market_first:{name}:cheap',f'main:market_first:{name}:minimum',name)
    for name in ('Technia','Novia'):
        key = f'stress:market_first:Mechania:idle->Mechania:idle+{name}:minimum'
        pairs[key] = ('stress:market_first:Mechania:idle',f'stress:market_first:Mechania:idle+{name}:minimum',name)
    assert set(pairs)==set(summary['paired'])
    parser = MarkerParser();parser.feed(report.read_text(encoding='utf-8'));parser.close()
    assert parser.active is None,'Unclosed numeric marker'
    coverage = set();numeric_values = 0
    means_cache = {};pairs_cache = {}

    def precision(descriptor):
        value = descriptor.get('digits',2)
        if type(value) is not int or not 0<=value<=8:raise ValueError('Invalid numeric precision')
        return value

    def values_for(experiment,metric):
        values = [nested(row,metric) for row in groups[experiment]]
        assert all(type(v) in (int,float) and math.isfinite(v) for v in values)
        return values

    def mean_stats(experiment,metric):
        key = experiment,metric
        if key not in means_cache:
            measured = statistics_for(values_for(experiment,metric))
            same_stats(measured,summary['experiments'][experiment]['metrics'][metric],key)
            means_cache[key] = measured
        return means_cache[key]

    def paired_stats(pair,metric):
        key = pair,metric
        if key not in pairs_cache:
            left_key,right_key,focal = pairs[pair]
            left = {row['seed']:row for row in groups[left_key]}
            right = {row['seed']:row for row in groups[right_key]}
            assert left.keys()==right.keys()
            if metric=='world.other_original_five_happy':
                assert focal in NAMES
                values = [statistics.mean(right[s]['countries'][n]['happy']-left[s]['countries'][n]['happy']
                           for n in NAMES if n!=focal) for s in sorted(left)]
            else:values = [nested(right[s],metric)-nested(left[s],metric) for s in sorted(left)]
            measured = statistics_for(values)
            same_stats(measured,summary['paired'][pair][metric],key)
            pairs_cache[key] = measured
        return pairs_cache[key]

    def render(descriptor):
        nonlocal numeric_values
        if not isinstance(descriptor,dict) or 'kind' not in descriptor:raise ValueError('Malformed numeric descriptor')
        kind = descriptor['kind']
        if kind=='literal':
            if not isinstance(descriptor.get('text'),str):raise ValueError('Literal text must be a string')
            return descriptor['text']
        if kind=='concat':
            if not isinstance(descriptor.get('parts'),list) or not descriptor['parts']:raise ValueError('Empty numeric concatenation')
            return ''.join(render(part) for part in descriptor['parts'])
        if kind=='mean':
            experiment,metric = descriptor['experiment'],descriptor['metric']
            measured = mean_stats(experiment,metric)
            factor = descriptor.get('factor',1)
            if type(factor) not in (int,float) or not math.isfinite(factor):
                raise ValueError('Mean scaling factor must be a finite number')
            coverage.add((experiment,metric));numeric_values+=1
            return f'{measured["mean"]*factor:,.{precision(descriptor)}f}'
        if kind=='ci':
            pair,metric = descriptor['pair'],descriptor['metric']
            measured = paired_stats(pair,metric);digits = precision(descriptor)
            coverage.add(('pair:'+pair,metric));numeric_values+=1
            return f'{measured["mean"]:+,.{digits}f} [{measured["ci95"][0]:+,.{digits}f}, {measured["ci95"][1]:+,.{digits}f}]'
        if kind=='count':
            experiment,metric = descriptor['experiment'],descriptor['metric']
            values = values_for(experiment,metric)
            coverage.add((experiment,metric));numeric_values+=1
            return f'{sum(v>0 for v in values)}/{len(values)}'
        if kind=='anycount':
            experiment,metrics = descriptor['experiment'],descriptor['metrics']
            if not isinstance(metrics,list) or not metrics:raise ValueError('Any-count requires metric paths')
            values = [values_for(experiment,metric) for metric in metrics]
            numerator = sum(any(column[i]>0 for column in values) for i in range(len(groups[experiment])))
            for metric in metrics:coverage.add((experiment,metric))
            numeric_values+=1
            return f'{numerator}/{len(groups[experiment])}'
        if kind=='paired_greater_count':
            experiment,control,metric = descriptor['experiment'],descriptor['control'],descriptor['metric']
            selected = {row['seed']:row for row in groups[experiment]}
            baseline = {row['seed']:row for row in groups[control]}
            assert selected.keys()==baseline.keys()
            assert len(selected)==len(groups[experiment]) and len(baseline)==len(groups[control])
            numerator = sum(nested(selected[s],metric)>nested(baseline[s],metric)+1e-9 for s in selected)
            coverage.add((experiment,metric));coverage.add((control,metric));numeric_values+=1
            return f'{numerator}/{len(selected)}'
        if kind=='top_count':
            experiment,metric,metrics = descriptor['experiment'],descriptor['metric'],descriptor['metrics']
            if not isinstance(metrics,list) or len(metrics)!=6 or metric not in metrics:
                raise ValueError('Top-count requires six original-country score paths including the focal path')
            assert {path.split('.')[1] for path in metrics}==set(NAMES)
            numerator = sum(nested(row,metric)>=max(nested(row,path) for path in metrics)-1e-9
                            for row in groups[experiment])
            for path in metrics:coverage.add((experiment,path))
            numeric_values+=1
            return f'{numerator}/{len(groups[experiment])}'
        raise ValueError('Unknown numeric marker kind: '+str(kind))

    errors = []
    for index,cell in enumerate(parser.markers):
        try:
            expected_text = render(cell['descriptor'])
            if cell['text']!=expected_text:
                errors.append({'cell':index,'actual':cell['text'],'expected':expected_text,'descriptor':cell['descriptor']})
        except Exception as exc:
            errors.append({'cell':index,'error':str(exc),'descriptor':cell['descriptor']})
    if len(parser.markers)<150:errors.append({'coverage':'Fewer than150 numeric cells were labelled'})
    required_main = {f'main:market_first:{sid}' for sid in MAIN_SCENARIOS}
    covered_main = {g for g,m in coverage if g.startswith('main:')}
    if not required_main<=covered_main:
        errors.append({'coverage':'Missing main behavioral condition','missing':sorted(required_main-covered_main)})
    for mode in SCORE_VIEWS:
        if not any(f'.evaluation.scores.{mode}.' in metric for group,metric in coverage):
            errors.append({'coverage':'Missing shadow scoring view','missing':mode})
    for name in ('Technia','Novia'):
        for scenario in ('Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum'):
            key = f'stress:market_first:{scenario}',f'countries.{name}.routing.g3_electronics_used'
            if key not in coverage:errors.append({'coverage':'Missing actual-use stress endpoint','missing':key})
    receipt = {
        'status':'passed' if not errors else 'failed','report':str(report),
        'report_sha256':hashlib.sha256(report.read_bytes()).hexdigest(),
        'summary_sha256':hashlib.sha256((results/'summary.json').read_bytes()).hexdigest(),
        'run_manifest_sha256':hashlib.sha256((results/'run_manifest.json').read_bytes()).hexdigest(),
        'validator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'checked_numeric_cells':len(parser.markers),'checked_numeric_values':numeric_values,
        'independently_recomputed_means':len(means_cache),'independently_recomputed_paired_metrics':len(pairs_cache),
        'tables':parser.tables,'formal_games':len(seen),'errors':errors,
        'covered_experiments':sorted({g for g,m in coverage if not g.startswith('pair:')}),
        'scope':['All4,400 unique raw trajectory identities and exact19+20 condition schedule',
                 'Marked means independently recomputed from saved raw trajectories and cross-checked with summary',
                 'Explicit finite mean scale factors, including satisfaction divided by4',
                 'Marked paired means and95% seed intervals independently recomputed with exact seed matching',
                 'Marked event-presence and any-country counts from saved raw trajectories',
                 'Marked paired score-win and original-six top-score frequencies with1e-9 tolerance',
                 'All19 main conditions, four scoring views and Technia/Novia actual-use stress endpoints'],
        'limits':'Unmarked prose and table-label semantics are not exhaustively checked by this numeric validator.',
    }
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,json.dumps(errors,ensure_ascii=False)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=ROOT/'evaluation_results')
    parser.add_argument('--report',type=Path,default=ROOT/'TRADE_PRICE_SCORE_REVIEW_V11_KO.html')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args();results = args.results.resolve();report = args.report.resolve()
    output = args.output.resolve() if args.output else results/'report_numeric_qa.json'
    print(json.dumps(verify_report(results,report,output),ensure_ascii=False))


if __name__=='__main__':
    main()
