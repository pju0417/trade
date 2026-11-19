"""Frozen v17 national-operating-resource executions and read-only scoring.

The preserved economic source is never edited or monkeypatched.  National
consumption extends raw accounting, so this runner validates the extended
partition explicitly instead of calling a legacy two-purpose validator.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import io
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'source_v13'
PROTOCOL=ROOT/'OPERATING_PROTOCOL_V17.json'
GOALS=ROOT/'SCORE_TARGETS_V15.json'
PROVENANCE=ROOT/'INPUT_PROVENANCE_V17.json'
DEFAULT_OUTPUT=ROOT/'operating_results'
NAMES=('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
ADDED=('Novia','Agrea','Ferria')
GOODS=('wheat','banana','ore','fuel','machine','electronics')
RAW=('ore','fuel')
SOURCE_KINDS=('initial_own','initial_foreign','produced_own','produced_foreign')
MODES=('baseline','electronics_input')
PROFILES=('none','light','regular','daily')
STRESS_PROFILES=('none','light','regular')
STYLES=('minimum','idle','invest','trade','minimum_passive')
PHASES={'main':(130000,100),'stress':(132000,30)}
IDENTITY=('phase','mode','operating_profile','scenario','seed','focal','style','behaviors')
OUTPUT_FILES=('validation_runs.jsonl.gz','round_ledgers.jsonl.gz',
              'raw_round_ledgers.jsonl.gz','operating_round_ledgers.jsonl.gz',
              'representative_traces.json.gz')
_RUNTIME=None


def now():return datetime.now(timezone.utc).isoformat()


def read_json(p):return json.loads(Path(p).read_text())


def write_json_new(path,value):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1048576),b''):h.update(part)
    return h.hexdigest()


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def value_hash(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def scenario(focal=None,style='normal'):
    return {'scenario':f'{focal}:{style}','focal':focal,'style':style,'overrides':{}}


def scenarios(phase):
    if phase=='main':return [scenario()]
    if phase!='stress':raise ValueError('Unknown phase')
    return ([scenario()]+[scenario(n,s) for n in NAMES for s in STYLES]
            +[scenario('Technia','cheap'),scenario(None,'no_trade')])


def smoke_tasks():
    cases=(('baseline',None,'normal'),('electronics_input','Technia','invest'),
           ('baseline','Mineria','idle'),('electronics_input','Grainia','minimum'),
           ('baseline','Tropia','minimum_passive'),('electronics_input',None,'no_trade'))
    return [('smoke',mode,profile,128000+i,f'{focal}:{style}',focal,style,())
            for profile in PROFILES for i,(mode,focal,style) in enumerate(cases)]


def formal_tasks():
    tasks=[]
    for phase,(start,n) in PHASES.items():
        for mode in MODES:
            for profile in (PROFILES if phase=='main' else STRESS_PROFILES):
                for s in scenarios(phase):
                    for seed in range(start,start+n):
                        tasks.append((phase,mode,profile,seed,s['scenario'],s['focal'],s['style'],()))
    assert len(tasks)==len(set(tasks))==6740
    return tasks


def task_identity(task):
    phase,mode,profile,seed,sid,focal,style,overrides=task
    behaviors=dict(overrides)
    if focal is not None:behaviors[focal]=style
    return dict(phase=phase,mode=mode,operating_profile=profile,scenario=sid,
                seed=seed,focal=focal,style=style,behaviors=behaviors)


def identity_key(row):
    return tuple(row[k] for k in ('phase','mode','operating_profile','scenario','seed'))


def trace_key(row):return ':'.join(map(str,identity_key(row)))


def save_trace(task):return task[0] in ('main','smoke') or task[3]==PHASES['stress'][0]


def run_spec():
    return {
        'schema':'v17-fresh-operating-execution-plan-1','modes':list(MODES),
        'main_profiles':list(PROFILES),'stress_profiles':list(STRESS_PROFILES),
        'ranked_countries':list(NAMES),'unranked_countries':list(ADDED),
        'country_count':9,'rounds':9,
        'phases':{phase:{'seed_range':[start,start+n-1],'n_per_condition':n,
                         'profiles':list(PROFILES if phase=='main' else STRESS_PROFILES),
                         'scenarios':scenarios(phase)} for phase,(start,n) in PHASES.items()},
        'main_games':800,'stress_games':5940,'formal_games':6740,
        'smoke_games':24,'smoke_tasks':[task_identity(t) for t in smoke_tasks()],
        'formal_ledger_rows_per_kind':545940,'formal_traces':998,
        'trace_scope':'Every main trajectory and the first seed of each stress condition.',
        'score_reference':'v15 steps; frozen goals and capacity15+utilization10',
        'score_feedback_to_actions':False,
        'daily_scope':'Normal-operation boundary diagnostic only; no daily stress conclusions.',
        'actual_game_count_note':'Semantic/backward-compatibility test executions reported separately in their receipt.'}


def source_snapshot():
    p=read_json(PROVENANCE)
    actual={str(f.relative_to(SOURCE)):digest(f) for f in sorted(SOURCE.rglob('*.py'))}
    assert len(actual)==85
    assert actual==p['source_python_sha256'],'Inherited economic code changed'
    assert digest(GOALS)=='4a88b018c4adb9b21774b45e7f7b90fa4af1149aff76e29b126a3887b7d53ca3'
    selected=[PROTOCOL,GOALS,PROVENANCE,ROOT/'operating_engine.py',Path(__file__),ROOT/'analyze_operating_validation.py']
    selected+=sorted(ROOT.glob('test_*.py'))
    assert any(f.name.startswith('test_') for f in selected)
    return {'inherited_source_sha256':actual,
            'new_source_sha256':{str(f.relative_to(ROOT)):digest(f) for f in selected}}


def check_protocol():
    p=read_json(PROTOCOL)
    assert p['execution']==run_spec(),'Protocol execution plan differs from runner'
    return p


def runtime():
    global _RUNTIME
    if _RUNTIME is None:
        sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(ROOT))
        engine=importlib.import_module('operating_engine')
        old=importlib.import_module('run_causal_validation')
        growth=importlib.import_module('growth_scoring')
        _RUNTIME=engine,old,growth,read_json(GOALS)
    return _RUNTIME


def count_map(obj,key,goods):
    assert key in obj and isinstance(obj[key],dict),key
    assert set(obj[key])<=set(goods),(key,set(obj[key])-set(goods))
    assert all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in obj[key].values()),key
    obj[key]={g:obj[key].get(g,0) for g in goods}


def normalize_extended(result):
    """Only pad structurally absent good counts; no fabricated observed values."""
    assert set(result['countries'])==set(NAMES+ADDED)
    for n,c in result['countries'].items():
        for k in ('export_goods','import_goods','produced','purchase_by_good','sale_by_good',
                  'use_by_good','export_used_by_good','end_stock_by_good','unused_by_good','end_levels'):
            count_map(c,k,GOODS)
        for k in ('production_raw','research_raw'):count_map(c,k,RAW)
        assert c['all_goods_unique_used']==sum(c['use_by_good'].values())
        assert all(c['use_by_good'][g]<=c['produced'][g] for g in GOODS)
        assert c['cash']>=0 and 0<=c['happy']<=100
        assert c['cash']==c['start_cash']+c['revenue']-c['purchases']-c['investment']+c['tax']
        assert c['revenue']==sum(c['sale_by_good'].values())
        assert c['purchases']==sum(c['purchase_by_good'].values())
        if n in NAMES:
            assert math.isclose(c['score'],c['economic']+c['industry']+c['trade']+c['happy']/4,abs_tol=1e-8)
        else:assert c['score'] is c['industry'] is c['economic'] is None
    w=result['world']
    for k in ('production','consumed','trade_goods','remaining_goods','aged_unused_goods'):count_map(w,k,GOODS)
    assert sum(c['imports'] for c in result['countries'].values())==w['trade_units']
    assert sum(c['exports'] for c in result['countries'].values())==w['trade_units']
    assert sum(c['revenue'] for c in result['countries'].values())==sum(c['purchases'] for c in result['countries'].values())
    assert w['cash_total']==w['initial_cash']+w['tax']-w['investment']
    return result


def validate_extended_ledgers(game,result):
    expected={(r,n) for r in range(1,10) for n in game.cs}
    for rows in (game.cash_ledger,game.raw_round_ledger,game.operating_ledger):
        assert len(rows)==81 and {(r['round'],r['country']) for r in rows}==expected
    cash={(r['round'],r['country']):r for r in game.cash_ledger}
    previous={(n,g):game.starter_allocation[n][g] for n in game.cs for g in RAW}
    counts=Counter()
    for r in game.raw_round_ledger:
        n=r['country'];round_number=r['round'];money=cash[(round_number,n)]
        assert r['cash']==money['cash_end'] and r['happy']==money['happy']
        for g,x in r['goods'].items():
            national=x.get('national',0)
            assert x['consumed']==x['production']+x['research']+national
            assert x['consumed']==sum(x[s] for s in SOURCE_KINDS)
            assert x['opening_stock']==previous[n,g]
            assert x['stock']==x['opening_stock']+x['produced']+x['imports']-x['exports']-x['consumed']
            previous[n,g]=x['stock']
            assert x['purchases']==money['purchase_by_good'][g]
            assert x['sales']==money['sale_by_good'][g]
            assert 0<=x['imported_used']<=x['consumed']
            for k in ('consumed','production','research','national'):
                counts[n,g,k]+=x.get(k,0)
    for n,c in result['countries'].items():
        rows=[r for r in game.cash_ledger if r['country']==n]
        assert [r['round'] for r in rows]==list(range(1,10))
        previous_cash=c['start_cash']
        for r in rows:
            assert r['cash_start']==previous_cash
            assert r['cash_end']==r['cash_start']+r['sales']-r['purchases']-r['investment']+r['operating_income']
            assert sum(r['sale_by_good'].values())==r['sales']
            assert sum(r['purchase_by_good'].values())==r['purchases']
            previous_cash=r['cash_end']
        for field,source in (('revenue','sales'),('purchases','purchases'),('investment','investment'),('tax','operating_income')):
            assert c[field]==sum(r[source] for r in rows)
        assert previous_cash==c['cash']
        for g in RAW:
            for k in ('consumed','production','research','national'):
                assert c['raw_use'][g].get(k,0)==counts[n,g,k],(n,g,k)
            assert c['raw_use'][g]['production']==c['production_raw'][g]
            assert c['raw_use'][g]['research']==c['research_raw'][g]
    assert len({e['uid'] for e in game.raw_use_log})==len(game.raw_use_log)
    for e in game.raw_use_log:
        u=game.units[e['uid']]
        assert u.good==e['good'] and u.owner is None and u.used
        assert (u.use_round,u.use_country,u.use_purpose)==(e['round'],e['country'],e['purpose'])
    schedule={
        'none':{'fuel':(),'ore':()},
        'light':{'fuel':(3,6,9),'ore':(4,8)},
        'regular':{'fuel':(2,4,6,8),'ore':(3,6,9)},
        'daily':{'fuel':tuple(range(1,10)),'ore':(3,6,9)},
    }
    penalties={'fuel':8,'ore':4}
    operation_ids=[]
    need_rows={(r['round'],r['country'],r['good']):r for r in game.needs_ledger if r['purpose']=='national'}
    assert len(need_rows)==sum(r['purpose']=='national' for r in game.needs_ledger)
    by_country={n:[] for n in game.cs}
    for e in game.operating_ledger:
        n=e['country'];r=e['round'];by_country[n].append(e)
        assert e['profile']==game.operating_profile
        expected_due={g:int(r in schedule[game.operating_profile][g]) for g in RAW}
        assert e['required']==expected_due
        for g in RAW:
            used=e['used_ids'][g];proof=e['used_unit_evidence'][g]
            assert len(used)==len(set(used))==len(proof)==e['consumed'][g]
            assert used==[x['uid'] for x in proof]
            assert e['consumed'][g]==min(e['required'][g],e['available_before'][g])
            assert e['missing'][g]==e['required'][g]-e['consumed'][g]
            assert e['stock_before'][g]-e['stock_after'][g]==e['consumed'][g]
            assert 0<=e['available_before'][g]<=e['stock_before'][g]
            if e['required'][g]:
                need=need_rows.pop((r,n,g))
                assert need['needed']==e['required'][g] and need['used_ids']==used
                assert need['external']==max(0,e['required'][g]-e['own_origin_before'][g])
                foreign_used=sum(x['origin']!=n and x['last_import'] is not None for x in proof)
                assert need['fulfilled']==min(need['external'],foreign_used)
            else:assert (r,n,g) not in need_rows
            for x in proof:
                u=game.units[x['uid']]
                assert x['good']==u.good==g and x['origin']==u.origin and x['born']==u.born
                assert x['owner_before']==n and x['order_before'] is None
                assert u.owner is None and u.used and (u.use_round,u.use_country,u.use_purpose)==(r,n,'national')
                if x['last_import'] is not None:
                    tx=game.transactions[x['last_import']]
                    assert tx['round']<=r and any(z['buyer']==n and x['uid'] in z['ids'] for z in tx['legs'])
            operation_ids.extend(used)
        expected_penalty=sum(penalties[g]*e['missing'][g]/e['required'][g] for g in RAW if e['required'][g])
        assert math.isclose(e['penalty'],expected_penalty,abs_tol=1e-12)
        expected_happy=round(max(0,e['base_happy']-expected_penalty),6)
        assert e['happy']==expected_happy==cash[(r,n)]['happy']
        expected_tax=10+math.floor(expected_happy/10+.5)
        assert e['round_income']==expected_tax==cash[(r,n)]['operating_income']
        assert e['base_tax']==10+math.floor(e['base_happy']/10+.5)
        assert e['tax_effect']==e['round_income']-e['base_tax']
        for field in ('cash','tax','minted'):
            assert e[field+'_after']-e[field+'_before']==expected_tax
        assert e['need_slots_after']>=e['need_slots_before']+sum(e['required'].values())
    assert not need_rows
    logged=[x['uid'] for x in game.raw_use_log if x['purpose']=='national']
    assert len(operation_ids)==len(set(operation_ids)) and set(operation_ids)==set(logged)
    assert game.operating_use_log==[x for x in game.raw_use_log if x['purpose']=='national']
    for n,rows in by_country.items():
        q=result['countries'][n]['national_operation']
        for k in ('required','consumed','missing'):
            assert q[k]=={g:sum(e[k][g] for e in rows) for g in RAW}
        assert q['shortage_rounds']=={g:sum(e['missing'][g]>0 for e in rows) for g in RAW}
        assert q['any_shortage_rounds']==sum(any(e['missing'].values()) for e in rows)
        for k in ('penalty','tax_effect'):
            assert math.isclose(q['penalty_total' if k=='penalty' else k],sum(e[k] for e in rows),abs_tol=1e-9)
        assert math.isclose(q['penalty_mean'],sum(e['penalty'] for e in rows)/9,abs_tol=1e-9)
        assert math.isclose(q['base_happy_mean'],sum(e['base_happy'] for e in rows)/9,abs_tol=1e-9)
        assert math.isclose(q['final_happy_mean'],result['countries'][n]['happy'],abs_tol=1e-9)
        for g in RAW:assert q['consumed'][g]==counts[n,g,'national']
    world=result['world']['national_operation']
    for k in ('required','consumed','missing','shortage_rounds'):
        assert world[k]=={g:sum(c['national_operation'][k][g] for c in result['countries'].values()) for g in RAW}
    for k in ('any_shortage_rounds','penalty_total','tax_effect'):
        assert math.isclose(world[k],sum(c['national_operation'][k] for c in result['countries'].values()),abs_tol=1e-9)
    for e in game.operating_plan_log:
        assert e['profile']==game.operating_profile and any(e['due'].values())
        assert e['due']=={g:int(e['round'] in schedule[game.operating_profile][g]) for g in RAW}
        assert all(e['target'][g]==e['legacy_target'][g]+e['due'].get(g,0) for g in GOODS)
        ordinary=[x for x in e['rows'] if x['kind']!='replacement']
        assert len(ordinary)==len({x['good'] for x in ordinary})
        assert sum(x['budget'] for x in e['rows'])<=e['cash']
        for x in e['rows']:
            assert 0<=x['quantity']<=x['want'] and x['budget']==x['quantity']*x['unit_price']
            assert x['want']==sum(v['want'] for v in x['budget_parts'])
            assert x['quantity']==sum(v['quantity'] for v in x['budget_parts'])
            assert x['budget']==sum(v['budget'] for v in x['budget_parts'])
            if x['good'] in RAW:
                assert x['want']==max(0,e['target'][x['good']]-e['available'][x['good']])
        for g in RAW:
            parts=[p for x in e['rows'] if x['good']==g for p in x['budget_parts'] if p['purpose']=='national']
            assert sum(p['want'] for p in parts)==max(0,e['due'][g]-e['available'][g])


def attach_fixed_scores(game,record,growth,goals):
    for n,m in growth.extract_metrics(game,record).items():record['countries'][n]['growth_metrics']=m
    for n,c in record['countries'].items():
        if n not in NAMES:c['fixed_evaluation']=None;continue
        m=c['growth_metrics'];clip=lambda x:min(1,max(0,x))
        y={'economic_growth':20*clip(m['asset_gain']/goals['economic_old'][n]),
           'reserve':m['reserve_score'],'capacity':15*clip(m['capacity_growth']/goals['industrial_steps'][n]),
           'utilization':m['utilization_score'],'wellbeing':m['wellbeing_score'],'trade':m['trade_score']}
        y['economic']=y['economic_growth']+y['reserve'];y['industry']=y['capacity']+y['utilization']
        y['score']=y['economic']+y['industry']+y['wellbeing']+y['trade']
        y['economic_target']=goals['economic_old'][n];y['industrial_target']=goals['industrial_steps'][n]
        assert 0<=y['score']<=100+1e-9
        c['fixed_evaluation']=y
    scores={n:record['countries'][n]['fixed_evaluation']['score'] for n in NAMES}
    high=max(scores.values());top=[n for n in NAMES if scores[n]>=high-1e-9]
    for n in NAMES:record['countries'][n]['fixed_evaluation']['top']=int(n in top)
    record['world']['fixed_evaluation']={'score_spread':high-min(scores.values()),'top_countries':top,
        'score_feedback_to_actions':False,'goals_refitted':False,'reference':'v15 steps'}


def run_one(task):
    engine,old,growth,goals=runtime();identity=task_identity(task)
    phase,mode,profile,seed,sid,focal,style,overrides=task
    game=engine.Game(seed,mode=mode,operating_profile=profile,focal=focal,
        style='normal' if style=='no_trade' else style,trade_enabled=style!='no_trade',behaviors=dict(overrides))
    result=normalize_extended(game.run())
    assert identity['behaviors']==dict(game.behaviors)
    assert game.r==9 and len(game.round_history)==9
    for k in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
        assert result['world'][k]==0,(identity,k)
    for n,behavior in game.behaviors.items():
        c=result['countries'][n]
        if behavior=='idle':assert c['imports']==c['exports']==c['investment']==c['routing']['routes_started']==0
        if behavior in ('trade','minimum_passive'):assert c['investment']==c['routing']['routes_started']==0
    if style=='no_trade':assert result['world']['transactions']==0
    validate_extended_ledgers(game,result)
    old.validate_development_records(game,result);old.validate_routing_records(game,result)
    if 'invest' in game.behaviors.values():old.validate_invest_attempts(game,result)
    else:old.validate_evaluation_records(game,result)
    old.validate_causal_records(game,result)
    record={'schema':'v17-operating-execution-row-1',**identity,**result}
    attach_fixed_scores(game,record,growth,goals);old.validate_metrics(record)
    record['v17_evidence']={'development_events':deepcopy(game.development_log),
        'score_feedback_to_actions':False}
    ledgers=[{**identity,'rows':rows} for rows in (game.cash_ledger,game.raw_round_ledger,game.operating_ledger)]
    trace={**game.trace(),**identity,'result':record} if save_trace(task) else None
    return record,*ledgers,trace


@contextmanager
def gzip_text_new(path):
    with Path(path).open('xb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as gz:
            with io.TextIOWrapper(gz,encoding='utf-8',newline='\n') as f:yield f


def partial_path(directory,name):return directory/name.replace('.json','.partial.json',1)


def execute(directory,tasks,workers,stage):
    directory.mkdir(parents=True,exist_ok=True)
    manifest_name='smoke_manifest.json' if stage=='smoke' else 'run_manifest.json'
    for name in OUTPUT_FILES+(manifest_name,):
        assert not (directory/name).exists() and not partial_path(directory,name).exists()
    before=source_snapshot();check_protocol();started=now();clock=time.monotonic()
    expected={identity_key(task_identity(t)):task_identity(t) for t in tasks}
    expected_traces={trace_key(task_identity(t)) for t in tasks if save_trace(t)}
    seen=set();trace_seen=set();phases=Counter();profiles=Counter();styles=Counter();ledger_counts=Counter()
    status='FAIL';error=None
    try:
        with ExitStack() as stack:
            streams={n:stack.enter_context(gzip_text_new(partial_path(directory,n))) for n in OUTPUT_FILES}
            traces=streams['representative_traces.json.gz'];traces.write('{');first=True
            pool=stack.enter_context(ProcessPoolExecutor(max_workers=workers))
            for i,(row,cash,raw,operating,trace) in enumerate(pool.map(run_one,tasks,chunksize=2),1):
                key=identity_key(row);assert key in expected and key not in seen
                assert {k:row[k] for k in IDENTITY}==expected[key]
                seen.add(key);phases[row['phase']]+=1;profiles[row['operating_profile']]+=1;styles[row['style']]+=1
                streams['validation_runs.jsonl.gz'].write(encoded(row)+'\n')
                for name,ledger in zip(OUTPUT_FILES[1:4],(cash,raw,operating)):
                    assert {k:ledger[k] for k in IDENTITY}==expected[key]
                    streams[name].write(encoded(ledger)+'\n');ledger_counts[name]+=len(ledger['rows'])
                if trace is not None:
                    tk=trace_key(row);assert tk in expected_traces and tk not in trace_seen;trace_seen.add(tk)
                    if not first:traces.write(',')
                    traces.write(encoded(tk)+':'+encoded(trace));first=False
                if i%(1 if stage=='smoke' else 100)==0 or i==len(tasks):
                    print(f'{stage.upper()} {i}/{len(tasks)} verified; {time.monotonic()-clock:.1f}s',flush=True)
            traces.write('}\n')
        assert seen==set(expected) and trace_seen==expected_traces
        assert all(n==len(tasks)*81 for n in ledger_counts.values())
        after=source_snapshot();assert before==after,'Sources changed during execution'
        for n in OUTPUT_FILES:partial_path(directory,n).replace(directory/n)
        status='PASS'
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc)};raise
    finally:
        after=source_snapshot()
        manifest={'schema':'v17-operating-execution-manifest-1','stage':stage,'status':status,
          'started_at':started,'completed_at':now(),'elapsed_seconds':time.monotonic()-clock,'workers':workers,
          'source_before':before,'source_after':after,'source_unchanged':before==after,
          'planned_games':len(tasks),'completed_games':len(seen),'new_economic_games':len(seen),
          'unobserved_worker_completions_possible_if_failed':status!='PASS','phase_counts':dict(phases),
          'profile_counts':dict(profiles),'behavior_counts':dict(styles),'ledger_rows':dict(ledger_counts),
          'representative_traces':len(trace_seen),'score_feedback_to_actions':False,
          'ranked_countries':list(NAMES),'unranked_countries':list(ADDED),'preserved_python_sources':85,
          'per_game_validation':['extended cash/raw/national ledger conservation','development/routing/attempt links',
            'causal parent mode constraints','growth metrics','fixed v15 score bounds'],
          'legacy_raw_validator_replaced':'Explicit national consumption partition and source/stock conservation; old two-purpose assertions not applied.',
          'output_sha256':{n:digest(directory/n) for n in OUTPUT_FILES if (directory/n).exists()},
          'partial_sha256':{n:digest(partial_path(directory,n)) for n in OUTPUT_FILES if partial_path(directory,n).exists()},
          'errors':[] if error is None else [error]}
        write_json_new(directory/manifest_name,manifest)
    return manifest


def freeze(output,test_receipt):
    snapshot=source_snapshot();check_protocol();smoke=read_json(output/'smoke/smoke_manifest.json')
    assert smoke['status']=='PASS' and smoke['completed_games']==24 and not smoke['errors']
    assert smoke['source_before']==smoke['source_after']==snapshot
    assert smoke['representative_traces']==24
    for n,s in smoke['output_sha256'].items():assert digest(output/'smoke'/n)==s
    test=Path(test_receipt).resolve();receipt=read_json(test)
    assert receipt.get('status') in ('PASS','passed') or receipt.get('passed') is True
    assert not receipt.get('failures') and not receipt.get('errors')
    for n in OUTPUT_FILES+('run_manifest.json',):assert not (output/n).exists() and not partial_path(output,n).exists()
    frozen={'schema':'v17-operating-freeze-1','status':'PASS','created_at':now(),
            'source_snapshot':snapshot,'execution_plan':run_spec(),
            'smoke_manifest_sha256':digest(output/'smoke/smoke_manifest.json'),
            'test_receipt':str(test.relative_to(ROOT)),'test_receipt_sha256':digest(test),
            'formal_not_executed':True}
    write_json_new(output/'freeze_manifest.json',frozen);return frozen


def check_freeze(output):
    f=read_json(output/'freeze_manifest.json')
    assert f['status']=='PASS' and f['formal_not_executed'] and f['execution_plan']==run_spec()
    assert f['source_snapshot']==source_snapshot()
    assert f['smoke_manifest_sha256']==digest(output/'smoke/smoke_manifest.json')
    assert f['test_receipt_sha256']==digest(ROOT/f['test_receipt'])
    check_protocol()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=('smoke','freeze','formal'),required=True)
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--output-dir',type=Path,default=DEFAULT_OUTPUT)
    p.add_argument('--test-receipt',type=Path)
    a=p.parse_args();assert 1<=a.workers<=8
    output=a.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    if a.stage=='smoke':result=execute(output/'smoke',smoke_tasks(),a.workers,'smoke')
    elif a.stage=='freeze':result=freeze(output,a.test_receipt)
    else:
        check_freeze(output);result=execute(output,formal_tasks(),a.workers,'formal')
        assert result['completed_games']==6740 and result['representative_traces']==998
    print(encoded({k:result[k] for k in ('status','stage','completed_games','new_economic_games','elapsed_seconds','representative_traces') if k in result}),flush=True)


if __name__=='__main__':main()
