"""Independent numerical QA for the compact v13 causal experiment report.

Only saved formal/pilot records and fixed provenance files are read. No engine
imports, new games, parameter selection or source mutation occur here.
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

ROOT=Path(__file__).resolve().parent
NAMES=('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
MODES=('baseline','operating_first','no_durable_boost','ai_combined','electronics_input','combined_input')
NORMAL=('None:normal',)
STRESS=NORMAL+tuple(f'{n}:{s}' for n in NAMES for s in ('minimum','idle'))+(
    'Technia:cheap','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum',
    'Mineria:idle+Grainia:normal+Technia:minimum',
    'Technia:idle+Grainia:normal+Mineria:minimum',
    'Grainia:idle+Mineria:normal+Technia:minimum','None:no_trade',
    'Mineria:invest','Mineria:trade','Technia:invest','Technia:trade')
PHASES={
    'pilot_ai':(MODES[:4],NORMAL,range(96000,96030)),
    'pilot_economic':(MODES[4:],NORMAL,range(96000,96030)),
    'main':(MODES,NORMAL,range(100000,100100)),
    'stress':(MODES,STRESS,range(102000,102030)),
}
MODE_PAIRS=(('baseline','operating_first'),('baseline','no_durable_boost'),
    ('baseline','ai_combined'),('baseline','electronics_input'),
    ('ai_combined','combined_input'),('baseline','combined_input'))
GOALS_SHA='47e78fe6a9cebab256bb52a3b7dbef9c9b46cec4363d15700290ddfa2e4620d5'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def expected_contrasts():
    definitions={}
    def group(phase,mode,scenario):
        if phase=='pilot':phase='pilot_ai' if mode in MODES[:4] else 'pilot_economic'
        return f'{phase}:{mode}:{scenario}'
    for phase,scenarios in (('pilot',NORMAL),('main',NORMAL),('stress',STRESS)):
        for sid in scenarios:
            for left,right in MODE_PAIRS:
                definitions[f'{phase}:{left}->{right}:{sid}']={'kind':'mode','terms':{
                    group(phase,left,sid):-1,group(phase,right,sid):1}}
            definitions[f'{phase}:ai_interaction:{sid}']={'kind':'interaction','terms':{
                group(phase,'ai_combined',sid):1,group(phase,'operating_first',sid):-1,
                group(phase,'no_durable_boost',sid):-1,group(phase,'baseline',sid):1}}
    for mode in MODES:
        control=f'stress:{mode}:None:normal'
        for sid in STRESS[1:]:
            definitions[f'stress:{mode}:{sid}']={'kind':'behavior','terms':{
                control:-1,f'stress:{mode}:{sid}':1}}
        for name in ('Technia','Novia'):
            sid=f'Mechania:idle+{name}:minimum'
            definitions[f'stress:{mode}:Mechania:idle->{sid}']={'kind':'compound_behavior','terms':{
                f'stress:{mode}:Mechania:idle':-1,f'stress:{mode}:{sid}':1}}
    return definitions


def verify_report(results,report,output):
    summary=read_json(results/'summary.json');manifest=read_json(results/'run_manifest.json')
    freeze=read_json(results/'freeze_manifest.json');start=read_json(results/'formal_start.json')
    ai=read_json(results/'ai_pilot_manifest.json');economic=read_json(results/'economic_pilot_manifest.json')
    economic_start=read_json(results/'economic_pilot_start.json')
    assert summary['metadata']==manifest
    assert manifest['completed_games']==5100 and manifest['formal_games']==4920
    assert manifest['pilot_ai_games']==120 and manifest['pilot_economic_games']==60 and manifest['pilot_games']==180
    assert manifest['main_games']==600 and manifest['stress_games']==4320
    assert manifest['formal_cash_ledger_rows']==manifest['formal_raw_ledger_rows']==398520
    assert manifest['representative_traces']==156 and manifest['rounds']==manifest['countries']==9
    assert manifest['source_unchanged'] and manifest['verification_failures']==0
    assert not manifest['fixed_targets_refitted'] and not manifest['posthoc_reference_is_extra_game']
    assert manifest['formal_started_after_freeze'] and manifest['pilot_not_formal_evidence']
    assert manifest['freeze_sha256']==start['approved_freeze_sha256']==digest(results/'freeze_manifest.json')
    assert economic_start['approved_ai_pilot_sha256']==freeze['ai_pilot_manifest_sha256']==digest(results/'ai_pilot_manifest.json')
    assert datetime.fromisoformat(ai['completed_at'])<datetime.fromisoformat(economic_start['started_at'])
    assert datetime.fromisoformat(economic['completed_at'])<=datetime.fromisoformat(freeze['created_at'])<datetime.fromisoformat(start['started_at'])
    assert manifest['goals_sha256']==freeze['goals_sha256']==start['goals_sha256']==digest(ROOT/'V12_FROZEN_GOALS.json')==GOALS_SHA
    for key,filename in (('declared_protocol_sha256','CAUSAL_PROTOCOL_V13.json'),):
        assert manifest[key]==freeze[key]==digest(ROOT/filename)
    for key,filename in (('run_plan_sha256','pre_run_plan.json'),('tests_manifest_sha256','tests_manifest.json')):
        assert manifest[key]==freeze[key]==digest(results/filename)
    assert manifest['source_sha256']==manifest['source_sha256_after']==freeze['source_sha256']==start['source_sha256']
    assert manifest['test_sha256']==manifest['test_sha256_after']==freeze['test_sha256']==start['test_sha256']
    for field in ('source_sha256','test_sha256','inherited_source_sha256'):
        for name,expected in freeze[field].items():assert digest(ROOT/name)==expected,(name,'source hash')
    assert len(freeze['inherited_source_sha256'])==76
    specifications={}
    for phase,(modes,scenarios,seeds) in PHASES.items():
        spec=manifest['phases'][phase]
        assert spec['modes']==list(modes) and spec['seed_range']==[seeds.start,seeds.stop-1]
        assert tuple(s['scenario'] for s in spec['scenarios'])==scenarios
        specifications.update({(phase,s['scenario']):s for s in spec['scenarios']})
    groups=defaultdict(list);seen=set()
    with gzip.open(results/'runs.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line);identity=row['phase'],row['mode'],row['scenario'],row['seed']
            assert identity not in seen,'Duplicate trajectory identity'
            seen.add(identity);spec=specifications[(row['phase'],row['scenario'])]
            assert (row['focal'],row['style'])==(spec['focal'],spec['style'])
            behaviors=dict(spec['behaviors'])
            if spec['focal'] is not None:behaviors[spec['focal']]=spec['style']
            assert row['behaviors']==behaviors
            groups[f'{row["phase"]}:{row["mode"]}:{row["scenario"]}'].append(row)
    expected={(phase,mode,sid,seed) for phase,(modes,scenarios,seeds) in PHASES.items()
              for mode in modes for sid in scenarios for seed in seeds}
    assert seen==expected and len(seen)==5100
    assert set(groups)==set(summary['experiments'])
    for group,rows in groups.items():assert len(rows)==summary['experiments'][group]['n']
    definitions=expected_contrasts()
    assert definitions==summary['contrast_definitions'] and set(definitions)==set(summary['paired'])
    parser=MarkerParser();parser.feed(report.read_text(encoding='utf-8'));parser.close()
    assert parser.active is None,'Unclosed numeric marker'
    coverage=set();numeric_values=0;means_cache={};pairs_cache={}
    raw_only_means=set();raw_only_pairs=set()

    def declared_raw_only(metric):
        parts=metric.split('.')
        if parts[0]=='countries' and len(parts)>=3:
            return parts[2] not in manifest['country_summary_fields']
        if parts[0]=='world' and len(parts)>=2:
            return parts[1] not in manifest['world_summary_fields']
        return False

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
            saved=summary['experiments'][experiment]['metrics']
            if metric in saved:
                same_stats(measured,saved[metric],key)
            else:
                assert declared_raw_only(metric),('Required summary metric missing',metric)
                raw_only_means.add(key)
            means_cache[key] = measured
        return means_cache[key]

    def paired_stats(pair,metric):
        key = pair,metric
        if key not in pairs_cache:
            terms = definitions[pair]['terms']
            indexed = {group:{row['seed']:row for row in groups[group]} for group in terms}
            seedsets = [set(rows) for rows in indexed.values()]
            assert all(seeds==seedsets[0] for seeds in seedsets)
            values = [sum(weight*nested(indexed[group][seed],metric)
                          for group,weight in terms.items()) for seed in sorted(seedsets[0])]
            measured = statistics_for(values)
            saved=summary['paired'][pair]
            if metric in saved:
                same_stats(measured,saved[metric],key)
            else:
                assert declared_raw_only(metric),('Required paired metric missing',metric)
                raw_only_pairs.add(key)
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

    errors=[]
    for index,cell in enumerate(parser.markers):
        try:
            expected_text=render(cell['descriptor'])
            if cell['text']!=expected_text:
                errors.append({'cell':index,'actual':cell['text'],'expected':expected_text,'descriptor':cell['descriptor']})
        except Exception as exc:
            errors.append({'cell':index,'error':str(exc),'descriptor':cell['descriptor']})
    if len(parser.markers)<100:errors.append({'coverage':'Fewer than 100 numeric cells labelled'})
    required_main={f'main:{mode}:None:normal' for mode in MODES}
    covered_main={group for group,metric in coverage if group.startswith('main:')}
    if not required_main<=covered_main:
        errors.append({'coverage':'Missing formal main mode','missing':sorted(required_main-covered_main)})
    if not any(group=='pair:main:ai_interaction:None:normal' for group,metric in coverage):
        errors.append({'coverage':'Missing declared AI-factor interaction contrast'})
    receipt={
        'status':'passed' if not errors else 'failed','report':str(report),'errors':errors,
        'report_sha256':digest(report),'summary_sha256':digest(results/'summary.json'),
        'run_manifest_sha256':digest(results/'run_manifest.json'),'freeze_sha256':digest(results/'freeze_manifest.json'),
        'goals_sha256':GOALS_SHA,'validator_sha256':digest(__file__),
        'checked_numeric_cells':len(parser.markers),'checked_numeric_values':numeric_values,
        'independently_recomputed_means':len(means_cache),'independently_recomputed_paired_metrics':len(pairs_cache),
        'declared_raw_only_means':len(raw_only_means),'declared_raw_only_paired_metrics':len(raw_only_pairs),
        'tables':parser.tables,'unique_games':len(seen),'formal_games':4920,'pilot_games':180,
        'covered_experiments':sorted({group for group,metric in coverage if not group.startswith('pair:')}),
        'scope':['Exact 5,100 identities: 180 exploratory pilot and 4,920 independently seeded formal trajectories',
                 'All full behavior profiles, six modes and 24 stress conditions kept distinct',
                 'Fixed v12 target, source/test/protocol hashes and reviewed-stage timing',
                 'Marked raw means, paired seed confidence intervals and factorial interaction independently recomputed',
                 'Declared contrast terms reconstructed without importing the game or runner',
                 'Fields explicitly excluded from the frozen summary whitelist are independently calculated from raw records',
                 'Marked event, score-gain and original-six top-score frequencies from saved trajectories',
                 'All six formal main modes and the declared AI-factor interaction represented'],
        'limits':'Unmarked prose and table-label semantics are not exhaustively checked by this numeric validator.',
    }
    output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    assert not errors,json.dumps(errors,ensure_ascii=False)
    return receipt


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=ROOT/'causal_results')
    parser.add_argument('--report',type=Path,default=ROOT/'TRADE_CAUSAL_REVIEW_V13_KO.html')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();results=args.results.resolve();report=args.report.resolve()
    output=args.output.resolve() if args.output else results/'report_numeric_qa.json'
    print(json.dumps(verify_report(results,report,output),ensure_ascii=False))


if __name__=='__main__':main()
