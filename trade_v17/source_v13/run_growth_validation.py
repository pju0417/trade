"""v12 staged calibration, frozen targets, and untouched holdout validation.

Stage1 records780 calibration trajectories, freezes goals/source/tests/plan,
then exits. Stage2 requires the explicitly reviewed freeze-file SHA256 and
executes3100 holdout plus300 isolated stress trajectories. Four score views
reuse each trajectory. Importing this module performs no simulation or writes.
"""
from __future__ import annotations

import argparse
import copy
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import unittest

from growth_scoring import (Game, VIEWS, GOAL_METHOD, HEADROOM, extract_metrics,
                            make_goals, score_record, validate_goals)
from reference_engine import NAMES, ECON_GOAL, GROWTH_GOAL
from run_evaluation_validation import (normalize_and_validate as normalize_v11,
    validate_evaluation_records, ECONOMIC_FILES as OLD_ECONOMIC_FILES,
    TEST_FILES as OLD_TEST_FILES, scenario, scenario_manifest)
from run_routing_validation import validate_routing_records
from run_development_validation import validate_development_records
from run_raw_validation import validate_raw_ledger, grouped, pair, stats

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'growth_results'
INHERITED_TESTS=337
ECONOMIC_FILES=OLD_ECONOMIC_FILES+('growth_scoring.py',)
SOURCE_FILES=ECONOMIC_FILES+('run_raw_validation.py','run_development_validation.py',
    'run_routing_validation.py','run_evaluation_validation.py','run_growth_validation.py')
TEST_FILES=OLD_TEST_FILES+('test_growth_scoring.py',)
CALIBRATION_START=90000
HOLDOUT_START=92000
STRESS_START=94000
CALIBRATION_N=60
HOLDOUT_N=100
STRESS_N=30
CALIBRATION_SCENARIOS=(scenario(),)+tuple(scenario(n,s) for n in NAMES for s in ('invest','trade'))
HOLDOUT_SCENARIOS=(scenario(),)+tuple(scenario(n,s) for n in NAMES for s in ('invest','trade','cheap','minimum','idle'))
STRESS_SCENARIOS=tuple(scenario(n,'minimum_passive') for n in NAMES)+(
    scenario('Mechania','idle'),scenario('Mechania','idle',(('Technia','minimum'),)),
    scenario('Mechania','idle',(('Novia','minimum'),)),scenario(None,'no_trade'))
PHASES={
    'calibration':(CALIBRATION_START,CALIBRATION_N,CALIBRATION_SCENARIOS),
    'holdout':(HOLDOUT_START,HOLDOUT_N,HOLDOUT_SCENARIOS),
    'stress':(STRESS_START,STRESS_N,STRESS_SCENARIOS),
}
IDENTITY_FIELDS=('phase','mode','scenario','seed','focal','style','behaviors')
METRIC_KEYS=('start_asset_value','end_asset_value','asset_gain','cash','tax','investment',
    'unused_stock_value','used_stock_value','stock_value','initial_capacity','final_capacity',
    'capacity_growth','reserve_target','reserve_score','produced_units','used_units','utilization',
    'utilization_score','wellbeing_score','trade_score')
VIEW_KEYS=('economic_target','industrial_target','economic_ratio','industrial_ratio',
    'economic_growth','reserve','economic','capacity','utilization','industry','wellbeing','trade','score',
    'economic_growth_at_cap','capacity_at_cap','economic_growth_near_cap','capacity_near_cap',
    'economic_at_cap','economic_5pct_sensitivity','capacity_5pct_sensitivity')
VIEW_DIFFERENCE_KEYS=('economic_growth','economic','capacity','industry','score',
    'economic_growth_at_cap','capacity_at_cap','economic_growth_near_cap','capacity_near_cap',
    'economic_5pct_sensitivity','capacity_5pct_sensitivity')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def hashes(files):return {name:digest(ROOT/name) for name in files}


def inherited_hashes():
    expected=json.loads((ROOT/'V11_PROVENANCE.json').read_text())['files']
    actual=hashes(expected)
    assert len(actual)==69 and actual==expected,'Inherited v11 files changed'
    return actual


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def now():return datetime.now(timezone.utc).isoformat()


def build_tasks(phases=('calibration','holdout','stress')):
    tasks=[]
    for phase in phases:
        start,count,conditions=PHASES[phase]
        tasks.extend((phase,seed,*condition) for condition in conditions for seed in range(start,start+count))
    assert len(tasks)==len(set(tasks))
    return tasks


def representative(task):return task[1]==PHASES[task[0]][0]


def trace_key(row):return f'{row["phase"]}:market_first:{row["scenario"]}:{row["seed"]}'


def close(a,b,label):assert math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-9),(label,a,b)


def validate_invest_attempts(game,result):
    """v11 snapshot contracts with the inherited invest household exception.

    The v11 validator assumes ordinary household guards. This independent
    branch verifies those same evidence links while explicitly allowing only
    style='invest' to bypass the ordinary household/reserve policy.
    """
    rows=game.evaluation_attempts
    assert len(rows)==81 and len(game.evaluation_index)==81
    assert {(a['round'],a['country']) for a in rows}=={(r,n) for r in range(1,10) for n in game.cs}
    for i,a in enumerate(rows):
        assert game.evaluation_index[(a['round'],a['country'])]==i
        legal=bool(1<=a['round']<=7 and a['style'] not in ('idle','trade') and a['goal'] and
            a['levels'].get(a['goal'],0)<4 and (a['goal'] in a['levels'] or (a['goal']==a['expand'] and a['round']>=3)))
        assert a['legal']==legal
        assert a['cash_ok']==(a['cash']>=a['cash_cost']+a['reserve'])
        if a['style']=='invest':assert a['reserve']==0
        assert a['household_ok']==(a['style']=='invest' or (a['food_met'] and a['living_free']>=a['living_needed']))
        assert a['raw_ok']==all(a['raw_free'].get(g,0)>=q for g,q in a['raw_required'].items())
        ready=bool(a['cached'] and legal and a['machine_min_gen'] and a['cash_ok'] and a['household_ok'] and a['raw_ok'])
        assert a['ready']==ready
        units=a['qualified_units']
        assert [u['uid'] for u in units]==a['qualified_ids']
        assert len(a['qualified_ids'])==len(set(a['qualified_ids']))
        assert [u['uid'] for u in units if u['order'] is None]==a['free_qualified_ids']
        assert [u['uid'] for u in units if u['origin']==a['country']]==a['own_qualified_ids']
        for u in units:
            actual=game.units[u['uid']]
            assert actual.good=='machine' and actual.gen==u['generation']>=a['machine_min_gen'] and actual.origin==u['origin']
            if u['import_transaction'] is not None:
                tx=game.transactions[u['import_transaction']]
                assert tx['round']<=a['round']
                assert any(leg['buyer']==a['country'] and u['uid'] in leg['ids'] for leg in tx['legs'])
        machine=a['machine_used']
        assert a['external']==int(bool(a['machine_min_gen']) and not a['own_qualified_ids'])
        assert a['fulfilled']==int(bool(a['external'] and machine and machine['origin']!=a['country'] and machine['import_transaction'] is not None))
        assert a['already_credited']==bool(a['fulfilled'] and machine['uid'] in a['prior_credited_equipment_ids'])
        if a['successful']:
            e=game.development_log[a['event_id']]
            assert (e['round'],e['country'],e['industry'],e['to_level'])==(a['round'],a['country'],a['goal'],a['target_level'])
            assert e['cash_cost']==a['cash_cost'] and e['machine']==machine
        else:assert a['event_id'] is None and machine is None
        if machine:assert ready and machine['uid'] in a['free_qualified_ids']
        elif ready:assert not a['free_qualified_ids']
        for uid in a['prior_credited_equipment_ids']:
            assert any(r['round']==a['round'] and r['country']==a['country'] and r['good']=='machine' and
                r['purpose'].startswith('equipment:') and r['fulfilled'] and uid in r['used_ids'] for r in game.needs_ledger)
    for name,c in result['countries'].items():
        attempts=[a for a in rows if a['country']==name and a['machine_min_gen']]
        d=c['evaluation']
        assert d['machine_attempts']==len(attempts)
        assert d['ready_opportunities']==sum(a['ready'] for a in attempts)
        assert d['successful_machine_uses']==sum(bool(a['machine_used']) for a in attempts)
        foreign=[a['machine_used'] for a in attempts if a['machine_used'] and a['machine_used']['origin']!=name and a['machine_used']['import_transaction'] is not None]
        assert d['foreign_machine_uses']==len(foreign)
        assert d['unique_foreign_development_machines']==len({u['uid'] for u in foreign})
        assert d['ready_unfulfilled']==sum(a['ready'] and a['external'] and not a['fulfilled'] for a in attempts)
        for label in ('cash','household','raw'):assert d['blocked_'+label]==sum(label in a['blockers'] for a in attempts)
        for mode,v in d['scores'].items():
            expected=[]
            if mode!='legacy':
                expected=[a for a in attempts if (a['successful'] if mode=='success_only' else a['ready'])
                          and not(mode=='ready_once' and a['already_credited'])]
            actual=[r for r in game.evaluation_rows(mode) if r['country']==name]
            assert len(actual)==len(expected)==v['added_needed']
            for a,r in zip(expected,actual):
                assert (r['round'],r['external'],r['fulfilled'],r['event_id'])==(a['round'],a['external'],a['fulfilled'],a['event_id'])
            base=[r for r in game.needs_ledger if r['country']==name]
            ext=sum(r['external'] for r in base)+sum(a['external'] for a in expected)
            filled=sum(r['fulfilled'] for r in base)+sum(a['fulfilled'] for a in expected)
            assert (v['external_need'],v['external_fulfilled'])==(ext,filled)


def validate_metrics(result):
    for name,c in result['countries'].items():
        m=c['growth_metrics']
        assert set(m)==set(METRIC_KEYS),(name,'growth metric schema')
        assert all(type(v) in (int,float) and math.isfinite(v) for v in m.values())
        for key in ('cash','tax','investment','start_asset_value','end_asset_value','capacity_growth'):
            close(m[key],c[key],(name,key))
        close(m['asset_gain'],m['end_asset_value']-m['start_asset_value'],(name,'gain'))
        close(m['end_asset_value'],m['cash']+m['stock_value']+.45*m['investment'],(name,'assets'))
        close(m['stock_value'],m['unused_stock_value']+m['used_stock_value'],(name,'stock valuation'))
        assert m['initial_capacity']>0 and m['reserve_target']>0
        close(m['capacity_growth'],(m['final_capacity']-m['initial_capacity'])/m['initial_capacity'],(name,'capacity'))
        assert m['produced_units']==sum(c['produced'].values())
        assert m['used_units']==c['all_goods_unique_used']==sum(c['use_by_good'].values())
        assert 0<=m['used_units']<=m['produced_units']
        close(m['utilization'],m['used_units']/max(1,m['produced_units']),(name,'utilization'))
        close(m['utilization_score'],c['industry_use_score'],(name,'use score'))
        close(m['reserve_score'],5*min(1,max(0,m['cash']/m['reserve_target'])),(name,'reserve score'))
        close(m['wellbeing_score'],c['happy']/4,(name,'wellbeing'))
        assert m['trade_score']==c['trade']


def validate_scored(record,goals):
    validate_metrics(record)
    for name,c in record['countries'].items():
        views=c['growth_evaluation'];assert set(views)==set(VIEWS)
        if name not in NAMES:
            assert all(v is None for v in views.values()) and c['score'] is None
            continue
        m=c['growth_metrics']
        for view,v in views.items():
            assert set(v)==set(VIEW_KEYS)
            assert all(type(x) in (int,float) and math.isfinite(x) for x in v.values())
            et=goals['economic'][name] if view.startswith('targets') else ECON_GOAL[name]
            it=goals['industrial'][name] if view.startswith('targets') else GROWTH_GOAL[name]
            assert v['economic_target']==et and v['industrial_target']==it
            close(v['economic_ratio'],m['asset_gain']/et,(name,view,'economic ratio'))
            close(v['industrial_ratio'],m['capacity_growth']/it,(name,view,'industrial ratio'))
            for key,source in (('reserve','reserve_score'),('utilization','utilization_score'),('wellbeing','wellbeing_score'),('trade','trade_score')):
                assert v[key]==m[source]
            close(v['economic'],v['economic_growth']+v['reserve'],(name,view,'economic'))
            close(v['industry'],v['capacity']+v['utilization'],(name,view,'industry'))
            close(v['score'],sum(v[k] for k in ('economic','industry','wellbeing','trade')),(name,view,'score'))
            for key,limit in (('economic_growth',20),('reserve',5),('economic',25),('capacity',15),('utilization',10),('industry',25),('wellbeing',25),('trade',25),('score',100)):
                assert -1e-9<=v[key]<=limit+1e-9,(name,view,key,v[key])
            for key,threshold,source in (('economic_growth_at_cap',20,'economic_growth'),('capacity_at_cap',15,'capacity'),
                    ('economic_growth_near_cap',19,'economic_growth'),('capacity_near_cap',14.25,'capacity'),('economic_at_cap',25,'economic')):
                assert v[key]==int(v[source]>=threshold-1e-9)
            assert v['economic_5pct_sensitivity']>=-1e-12 and v['capacity_5pct_sensitivity']>=-1e-12
        for key in ('economic','industry','score'):assert views['legacy'][key]==c[key]
    config=record['world']['growth_evaluation_config']
    assert config['views']==list(VIEWS) and config['headroom']==HEADROOM and config['ranked_countries']==list(NAMES)
    assert config['economic_rules_unchanged'] and config['official_scores_unchanged'] and not config['score_feedback_to_actions']


def run_one(task):
    phase,seed,sid,focal,style,overrides=task
    game=Game(seed,focal=focal,style='normal' if style=='no_trade' else style,
              trade_enabled=style!='no_trade',behaviors=dict(overrides))
    result=normalize_v11(game.run())
    for key in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
        assert result['world'][key]==0,(phase,seed,sid,key)
    for name,behavior in game.behaviors.items():
        c=result['countries'][name]
        if behavior=='idle':assert c['imports']==c['exports']==c['investment']==c['routing']['routes_started']==0
        if behavior in ('trade','minimum_passive'):assert c['investment']==c['routing']['routes_started']==0
    if style=='no_trade':assert result['world']['transactions']==0
    validate_raw_ledger(game,result);validate_development_records(game,result);validate_routing_records(game,result)
    if 'invest' in game.behaviors.values():validate_invest_attempts(game,result)
    else:validate_evaluation_records(game,result)
    metrics=extract_metrics(game,result)
    for name,m in metrics.items():result['countries'][name]['growth_metrics']=m
    validate_metrics(result)
    identity={'phase':phase,'mode':'market_first','scenario':sid,'seed':seed,'focal':focal,'style':style,'behaviors':dict(game.behaviors)}
    record={**identity,**result}
    cash={**identity,'rows':game.cash_ledger} if phase=='holdout' else None
    raw={**identity,'rows':game.raw_round_ledger} if phase=='holdout' else None
    trace={**game.trace(),**identity,'result':record} if representative(task) else None
    return record,cash,raw,trace


def protocol():
    return {'schema':'v12-growth-protocol-1','planned_games':4180,'calibration_games':780,'holdout_games':3100,'stress_games':300,
        **{phase+'_seed_range':[start,start+count-1] for phase,(start,count,cases) in PHASES.items()},
        **{phase+'_scenarios':scenario_manifest(cases) for phase,(start,count,cases) in PHASES.items()},
        'rounds':9,'countries':9,'ranked_countries':list(NAMES),'views':list(VIEWS),'goal_method':GOAL_METHOD,'headroom':HEADROOM,
        'original_economic_goals':ECON_GOAL,'original_industrial_goals':GROWTH_GOAL,
        'test_seed_band':[87000,87099],'old_v11_data_role':'previously seen diagnostics only; not v12 calibration or holdout',
        'baseline_reference':'frozen v11 economy and official score; existing invest/trade AI styles exposed without rule changes',
        'holdout_ledger_rows_planned':251100,'representative_traces_planned':54,
        'identity_fields':list(IDENTITY_FIELDS),'unique_trajectory_identity_fields':['phase','scenario','seed'],
        'calibration_policies_per_country':['own normal','own invest','own trade'],
        'exclude_peer_policy_observations':True,'shared_normal_control':True,'score_views_are_extra_games':False,
        'holdout_requires_reviewed_freeze_hash':True,'no_tuning_after_holdout':True,
        'policy_selection':{'source':'calibration_only','choices':['normal','invest','trade'],
            'criterion':'own mean candidate total score','tie_order':['normal','invest','trade'],'tie_tolerance':1e-9,
            'scope':'one focal country changes policy in each world; not six jointly optimized policies'},
        'primary_endpoints':['original-six within-world score spread under fixed behavior conditions',
            '95-percent near-cap frequencies and response to5-percent growth increases',
            'paired within-country normal/aggressive-investment/trade/price/idle differences',
            'holdout outcome of each view/country policy selected only on calibration among three fixed policies',
            'score-win and original-six top-score frequencies; not a target of equal one-sixth wins',
            'actual used output, production denominator, asset/cash/investment decomposition'],
        'limitations':['all candidates are posthoc; no behavior is optimized against the new score',
            'economic asset definition including operating income and inventory valuation is unchanged',
            'utilization10 points and reserve5 points remain unchanged, including their existing caps',
            'additional-three official and candidate totals stayNone',
            'minimum means public1G asks; direct negotiation and barter keep their existing rules',
            'invest is aggressive investment, not guaranteed investment or waived resource/machine costs',
            'stress minimum_passive/no_trade have no same-seed normal control and are standalone diagnostics',
            'only Mechania-idle stress has same-seed paired compound-condition controls',
            'seed intervals describe this model, not human learning, student win chances or classroom time']}


def run_tests(output):
    before=hashes(SOURCE_FILES);test_hashes=hashes(TEST_FILES);inherited=inherited_hashes();started=time.monotonic()
    suite=unittest.defaultTestLoader.loadTestsFromNames([Path(n).stem for n in TEST_FILES])
    with (output/'tests.log').open('w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    m={'passed':result.wasSuccessful(),'test_count':result.testsRun,'inherited_tests':INHERITED_TESTS,
        'new_tests':result.testsRun-INHERITED_TESTS,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'elapsed_seconds':time.monotonic()-started,'test_sha256':test_hashes,'economic_source_sha256':hashes(ECONOMIC_FILES),
        'validation_source_sha256':before,'inherited_source_sha256':inherited,'source_unchanged':before==hashes(SOURCE_FILES),
        'tests_unchanged':test_hashes==hashes(TEST_FILES),'inherited_unchanged':inherited==inherited_hashes()}
    write_json(output/'tests_manifest.json',m)
    assert m['passed'] and m['test_count']>INHERITED_TESTS and m['failures']==m['errors']==m['skipped']==0,m
    assert m['source_unchanged'] and m['tests_unchanged'] and m['inherited_unchanged']
    print(f'TESTS {m["test_count"]} passed, {m["elapsed_seconds"]:.2f}s',flush=True)
    return m


def verified_tests(output):
    path=output/'tests_manifest.json'
    if not path.exists():return run_tests(output)
    m=read_json(path)
    assert m['passed'] and m['test_count']>INHERITED_TESTS and m['inherited_tests']==INHERITED_TESTS
    assert m['failures']==m['errors']==m['skipped']==0
    assert m['test_sha256']==hashes(TEST_FILES) and m['validation_source_sha256']==hashes(SOURCE_FILES)
    assert m['economic_source_sha256']==hashes(ECONOMIC_FILES)
    assert m['inherited_source_sha256']==inherited_hashes()
    assert m['source_unchanged'] and m['tests_unchanged'] and m['inherited_unchanged']
    return m


def preserve_absent(output,names):
    for name in names:
        if (output/name).exists():raise FileExistsError(f'Preserve existing validation artifacts: {output/name}')


def read_rows(path):
    with gzip.open(path,'rt') as stream:return [json.loads(line) for line in stream]


def assert_schedule(rows,phases):
    expected={(phase,seed,sid,focal,style,overrides) for phase,seed,sid,focal,style,overrides in build_tasks(phases)}
    actual=set()
    for r in rows:
        focal=r['focal'];style=r['style'];behaviors=dict(r['behaviors'])
        if focal is not None:
            assert behaviors.pop(focal)==style
        key=(r['phase'],r['seed'],r['scenario'],focal,style,tuple(sorted(behaviors.items())))
        assert key not in actual and r['mode']=='market_first'
        actual.add(key)
    assert actual==expected and len(rows)==len(expected)


def select_policies(scored_calibration):
    """Select among three fixed policies using calibration only, never holdout."""
    if not scored_calibration or any(r['phase']!='calibration' for r in scored_calibration):
        raise ValueError('policy selection requires calibration records only')
    groups=defaultdict(list)
    identities=set()
    for r in scored_calibration:
        identity=r['scenario'],r['seed']
        if identity in identities:raise ValueError('duplicate calibration policy record')
        identities.add(identity);groups[r['scenario']].append(r)
    seeds={r['seed'] for r in groups['None:normal']}
    expected={'None:normal'}|{f'{n}:{s}' for n in NAMES for s in ('invest','trade')}
    if len(seeds)<2 or set(identities)!={(sid,seed) for sid in expected for seed in seeds}:
        raise ValueError('policy selection requires the paired thirteen calibration conditions')
    selection={}
    for view in VIEWS:
        selection[view]={}
        for name in NAMES:
            values={style:statistics.mean(r['countries'][name]['growth_evaluation'][view]['score']
                for r in groups['None:normal' if style=='normal' else f'{name}:{style}'])
                for style in ('normal','invest','trade')}
            best=max(values.values());chosen=next(style for style in ('normal','invest','trade') if values[style]>=best-1e-9)
            selection[view][name]={'policy':chosen,'scenario':'None:normal' if chosen=='normal' else f'{name}:{chosen}',
                'calibration_mean_score':values[chosen],'calibration_n':len(seeds),'policy_means':values}
    return {'schema':'v12-policy-selection-1','source':'calibration_only',
        'criterion':'own mean candidate total score','tie_order':['normal','invest','trade'],'tie_tolerance':1e-9,
        'calibration_seeds':sorted(seeds),'selections':selection,
        'scope':'Each selected policy belongs to a separate focal-country world; no jointly optimized world was simulated.'}


def calibrate(output,workers):
    names=('pre_run_plan.json','calibration_manifest.json','goals.json','frozen_selection.json','freeze_manifest.json',
        'calibration_runs.jsonl.gz','calibration_runs.partial.jsonl.gz','calibration_traces.json.gz')
    preserve_absent(output,names);tests=verified_tests(output)
    sources=hashes(SOURCE_FILES);test_hashes=hashes(TEST_FILES);inherited=inherited_hashes()
    plan=protocol();write_json(output/'pre_run_plan.json',plan)
    started=time.monotonic();rows=[];traces={};tasks=build_tasks(('calibration',))
    with ProcessPoolExecutor(max_workers=workers) as pool,gzip.open(output/'calibration_runs.partial.jsonl.gz','wt') as stream:
        for i,(record,cash,raw,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            assert cash is None and raw is None
            rows.append(record);stream.write(json.dumps(record,ensure_ascii=False)+'\n')
            if trace is not None:traces[trace_key(record)]=trace
            if i%130==0:print(f'CALIBRATION {i}/780 complete; {time.monotonic()-started:.1f}s',flush=True)
    assert_schedule(rows,('calibration',))
    goals=make_goals(rows);validate_goals(goals)
    assert goals['calibration']['seeds']==list(range(90000,90060)) and goals['calibration']['samples_per_country']==180
    assert sources==hashes(SOURCE_FILES) and test_hashes==hashes(TEST_FILES) and inherited==inherited_hashes()
    assert len(traces)==13
    (output/'calibration_runs.partial.jsonl.gz').replace(output/'calibration_runs.jsonl.gz')
    with gzip.open(output/'calibration_traces.json.gz','wt') as stream:json.dump(traces,stream,ensure_ascii=False)
    write_json(output/'goals.json',goals)
    selection=select_policies([score_record(r,goals) for r in rows])
    write_json(output/'frozen_selection.json',selection)
    manifest={'phase':'calibration','completed_games':780,'calibration_games':780,'holdout_games':0,'stress_games':0,
        'verification_calls':sum(r['world']['verify_calls'] for r in rows),'verification_failures':0,
        'representative_traces':13,'elapsed_seconds':time.monotonic()-started,'source_unchanged':True,'tests_completed':tests['test_count'],
        'source_sha256':sources,'test_sha256':test_hashes,'inherited_source_sha256':inherited,
        'protocol_sha256':digest(output/'pre_run_plan.json'),'goals_sha256':digest(output/'goals.json'),
        'selection_sha256':digest(output/'frozen_selection.json'),
        'calibration_runs_sha256':digest(output/'calibration_runs.jsonl.gz'),'calibration_traces_sha256':digest(output/'calibration_traces.json.gz'),
        'tests_manifest_sha256':digest(output/'tests_manifest.json'),'completed_at':now()}
    write_json(output/'calibration_manifest.json',manifest)
    freeze={'schema':'v12-growth-freeze-1','created_at':now(),'holdout_not_executed':True,
        'protocol_sha256':manifest['protocol_sha256'],'goals_sha256':manifest['goals_sha256'],
        'selection_sha256':manifest['selection_sha256'],
        'calibration_runs_sha256':manifest['calibration_runs_sha256'],'calibration_traces_sha256':manifest['calibration_traces_sha256'],
        'calibration_manifest_sha256':digest(output/'calibration_manifest.json'),'source_sha256':sources,
        'test_sha256':test_hashes,'inherited_source_sha256':inherited,'tests_manifest_sha256':manifest['tests_manifest_sha256'],
        'calibration_games':780,'holdout_games_planned':3100,'stress_games_planned':300}
    write_json(output/'freeze_manifest.json',freeze)
    print('CALIBRATION COMPLETE; HOLDOUT NOT RUN',flush=True)
    print('FREEZE_SHA256 '+digest(output/'freeze_manifest.json'),flush=True)
    print(json.dumps({'economic':goals['economic'],'industrial':goals['industrial']},ensure_ascii=False),flush=True)


def verify_freeze(output,approved):
    path=output/'freeze_manifest.json'
    if not approved or approved!=digest(path):raise ValueError('Explicitly reviewed freeze SHA256 is required')
    freeze=read_json(path)
    assert freeze['schema']=='v12-growth-freeze-1' and freeze['holdout_not_executed']
    files={'protocol_sha256':'pre_run_plan.json','goals_sha256':'goals.json',
        'selection_sha256':'frozen_selection.json',
        'calibration_runs_sha256':'calibration_runs.jsonl.gz','calibration_traces_sha256':'calibration_traces.json.gz',
        'calibration_manifest_sha256':'calibration_manifest.json','tests_manifest_sha256':'tests_manifest.json'}
    for key,name in files.items():assert freeze[key]==digest(output/name),(key,'changed after target freeze')
    assert read_json(output/'pre_run_plan.json')==protocol(),'Protocol changed after calibration'
    assert freeze['source_sha256']==hashes(SOURCE_FILES),'Source changed after calibration'
    assert freeze['test_sha256']==hashes(TEST_FILES),'Tests changed after calibration'
    assert freeze['inherited_source_sha256']==inherited_hashes()
    tests=verified_tests(output);goals=read_json(output/'goals.json');validate_goals(goals)
    rows=read_rows(output/'calibration_runs.jsonl.gz');assert_schedule(rows,('calibration',))
    assert make_goals(rows)==goals,'Frozen target values differ from declared calibration records'
    assert select_policies([score_record(r,goals) for r in rows])==read_json(output/'frozen_selection.json')
    return freeze,goals,rows,tests


def summarize(rows,metadata):
    groups=defaultdict(list)
    for r in rows:groups[(r['phase'],r['scenario'])].append(r)
    experiments={f'{phase}:market_first:{sid}':grouped(group) for (phase,sid),group in groups.items()}
    paired={}
    for phase,conditions in (('calibration',CALIBRATION_SCENARIOS),('holdout',HOLDOUT_SCENARIOS)):
        control=groups[(phase,'None:normal')]
        for sid,focal,style,overrides in conditions:
            if sid!='None:normal':paired[f'{phase}:market_first:{sid}']=pair(control,groups[(phase,sid)],focal)
    for name in ('Technia','Novia'):
        sid=f'Mechania:idle+{name}:minimum'
        paired[f'stress:market_first:Mechania:idle->{sid}']=pair(groups[('stress','Mechania:idle')],groups[('stress',sid)],name)
    diagnostics={};view_pairs={}
    for (phase,sid),group in groups.items():
        key=f'{phase}:market_first:{sid}';diagnostics[key]={};view_pairs[key]={}
        for view in VIEWS:
            scores=[[r['countries'][n]['growth_evaluation'][view] for n in NAMES] for r in group]
            diagnostics[key][view]={
                'original_score_spread':stats([max(v['score'] for v in row)-min(v['score'] for v in row) for row in scores]),
                'original_mean_score':stats([statistics.mean(v['score'] for v in row) for row in scores]),
                'economic_growth_near_cap_share':stats([statistics.mean(v['economic_growth_near_cap'] for v in row) for row in scores]),
                'capacity_near_cap_share':stats([statistics.mean(v['capacity_near_cap'] for v in row) for row in scores]),
                'economic_5pct_sensitivity':stats([statistics.mean(v['economic_5pct_sensitivity'] for v in row) for row in scores]),
                'capacity_5pct_sensitivity':stats([statistics.mean(v['capacity_5pct_sensitivity'] for v in row) for row in scores]),
            }
            if view=='legacy':continue
            d={f'countries.{name}.{field}':stats([r['countries'][name]['growth_evaluation'][view][field]-r['countries'][name]['growth_evaluation']['legacy'][field] for r in group]) for name in NAMES for field in VIEW_DIFFERENCE_KEYS}
            d['world.original_score_spread']=stats([
                (max(r['countries'][n]['growth_evaluation'][view]['score'] for n in NAMES)-min(r['countries'][n]['growth_evaluation'][view]['score'] for n in NAMES))-
                (max(r['countries'][n]['growth_evaluation']['legacy']['score'] for n in NAMES)-min(r['countries'][n]['growth_evaluation']['legacy']['score'] for n in NAMES)) for r in group])
            view_pairs[key]['legacy->'+view]=d
    return {'metadata':metadata,'experiments':experiments,'paired':paired,'growth_diagnostics':diagnostics,'score_view_pairs':view_pairs}


def holdout(output,workers,approved):
    names=('holdout_start.json','run_manifest.json','summary.json','runs.jsonl.gz','runs.partial.jsonl.gz',
        'round_ledgers.jsonl.gz','round_ledgers.partial.jsonl.gz','raw_round_ledgers.jsonl.gz',
        'raw_round_ledgers.partial.jsonl.gz','first_seed_traces.json.gz')
    preserve_absent(output,names)
    freeze,goals,calibration,tests=verify_freeze(output,approved)
    write_json(output/'holdout_start.json',{'started_at':now(),'approved_freeze_sha256':approved,
        'goals_sha256':freeze['goals_sha256'],'protocol_sha256':freeze['protocol_sha256'],
        'selection_sha256':freeze['selection_sha256'],
        'source_sha256':freeze['source_sha256'],'test_sha256':freeze['test_sha256']})
    started=time.monotonic();rows=[];traces={};tasks=build_tasks(('holdout','stress'))
    with gzip.open(output/'calibration_traces.json.gz','rt') as stream:cal_traces=json.load(stream)
    with ProcessPoolExecutor(max_workers=workers) as pool,gzip.open(output/'runs.partial.jsonl.gz','wt') as runfile, \
         gzip.open(output/'round_ledgers.partial.jsonl.gz','wt') as cashfile,gzip.open(output/'raw_round_ledgers.partial.jsonl.gz','wt') as rawfile:
        for raw_record in calibration:
            scored=score_record(raw_record,goals);validate_scored(scored,goals);rows.append(scored)
            runfile.write(json.dumps(scored,ensure_ascii=False)+'\n')
            key=trace_key(scored)
            if key in cal_traces:
                trace=cal_traces[key];trace['result']=scored;traces[key]=trace
        for i,(raw_record,cash,raw,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            scored=score_record(raw_record,goals);validate_scored(scored,goals);rows.append(scored)
            runfile.write(json.dumps(scored,ensure_ascii=False)+'\n')
            if cash is not None:cashfile.write(json.dumps(cash,ensure_ascii=False)+'\n')
            if raw is not None:rawfile.write(json.dumps(raw,ensure_ascii=False)+'\n')
            if trace is not None:trace['result']=scored;traces[trace_key(scored)]=trace
            if i%200==0:print(f'HOLDOUT/STRESS {i}/3400 complete; {time.monotonic()-started:.1f}s',flush=True)
    assert_schedule(rows,('calibration','holdout','stress'))
    assert freeze['source_sha256']==hashes(SOURCE_FILES) and freeze['test_sha256']==hashes(TEST_FILES)
    assert freeze['inherited_source_sha256']==inherited_hashes()
    assert freeze['goals_sha256']==digest(output/'goals.json') and approved==digest(output/'freeze_manifest.json')
    assert freeze['selection_sha256']==digest(output/'frozen_selection.json')
    expected_traces={f'{phase}:market_first:{sid}:{seed}' for phase,seed,sid,focal,style,overrides in build_tasks() if seed==PHASES[phase][0]}
    assert len(traces)==54 and set(traces)==expected_traces
    cal_manifest=read_json(output/'calibration_manifest.json')
    metadata={**protocol(),'completed_games':4180,'calibration_games':780,'holdout_games':3100,'stress_games':300,
        'representative_traces':54,'holdout_cash_ledger_rows':251100,'holdout_raw_ledger_rows':251100,
        'verification_calls':sum(r['world']['verify_calls'] for r in rows),'verification_failures':0,
        'source_unchanged':True,'source_sha256_before':freeze['source_sha256'],'source_sha256_after':hashes(SOURCE_FILES),
        'source_sha256':freeze['source_sha256'],'test_sha256_before':freeze['test_sha256'],'test_sha256_after':hashes(TEST_FILES),
        'inherited_source_sha256':freeze['inherited_source_sha256'],'tests_completed':tests['test_count'],
        'tests_manifest_sha256':freeze['tests_manifest_sha256'],'goals_sha256':freeze['goals_sha256'],
        'selection_sha256':freeze['selection_sha256'],
        'freeze_sha256':approved,'protocol_sha256':freeze['protocol_sha256'],
        'calibration_runs_sha256':freeze['calibration_runs_sha256'],'calibration_manifest_sha256':freeze['calibration_manifest_sha256'],
        'holdout_start_sha256':digest(output/'holdout_start.json'),'calibration_elapsed_seconds':cal_manifest['elapsed_seconds'],
        'holdout_stress_elapsed_seconds':time.monotonic()-started,'holdout_started_after_freeze':True,
        'test_and_smoke_games_excluded':True,'score_views_are_extra_games':False,'completed_at':now()}
    summary=summarize(rows,metadata)
    for name in ('runs','round_ledgers','raw_round_ledgers'):(output/f'{name}.partial.jsonl.gz').replace(output/f'{name}.jsonl.gz')
    with gzip.open(output/'first_seed_traces.json.gz','wt') as stream:json.dump(traces,stream,ensure_ascii=False)
    write_json(output/'summary.json',summary);write_json(output/'run_manifest.json',metadata)
    print(f'DONE 4180 unique trajectories; {metadata["verification_calls"]} invariant calls; holdout/stress {metadata["holdout_stress_elapsed_seconds"]:.2f}s',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('calibrate','holdout'))
    parser.add_argument('--approve-freeze');parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--dry-run',action='store_true');parser.add_argument('--tests-only',action='store_true')
    args=parser.parse_args()
    if args.workers<1:parser.error('workers must be positive')
    if args.dry_run:
        print(json.dumps({**protocol(),'executed_games':0},ensure_ascii=False));return
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    if args.tests_only:run_tests(output);return
    if args.stage is None:parser.error('choose --stage calibrate or --stage holdout')
    if args.stage=='calibrate':calibrate(output,args.workers)
    else:
        if not args.approve_freeze:parser.error('--stage holdout requires --approve-freeze SHA256')
        holdout(output,args.workers,args.approve_freeze)


if __name__=='__main__':main()
