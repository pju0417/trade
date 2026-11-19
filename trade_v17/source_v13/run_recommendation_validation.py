"""Frozen v7 recommendation comparison; importing this module starts no games.

Main: six advice modes x 200 seeds (44000..44199) = 1200 games.
Stress: baseline/price/responsive/combined x 15 scenarios x 30 seeds
(46000..46029) = 1800 games. Pilot 42000..42029 and tests 421xx are excluded.
Default total: 3000 games. Use --dry-run to inspect the schedule without running.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import statistics
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from recommendation_engine import Game, ADVICE_MODES as MODES
from machinery_engine import MODES as PHYSICAL_MODES, CREDITS_PER_RAW, UPKEEP_USES
from budget_engine import POLICIES
from expansion_engine import BASE_OPTIONS, ADDITIONS, CONFIG, NAMES, GOODS

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'advice_results'
ECONOMIC_FILES=('reference_engine.py','core_engine.py','engine.py','expansion_engine.py',
                'budget_engine.py','budget_trace.py','machinery_engine.py','recommendation_engine.py')
SOURCE_FILES=ECONOMIC_FILES+('run_recommendation_validation.py',)
TEST_FILES=('test_previous.py','test_fixes.py','test_costs.py','test_expansion.py',
            'test_budget.py','test_machinery.py','test_recommendation.py')
STRESS_MODES=('baseline','price','responsive','combined')
MAIN_PAIRS=(('baseline','price'),('baseline','listing'),('baseline','planning'),
            ('baseline','responsive'),('baseline','combined'),('price','responsive'),
            ('planning','responsive'),('responsive','combined'),('listing','combined'))
STRESS_PAIRS=(('baseline','price'),('baseline','responsive'),('baseline','combined'),
              ('price','responsive'),('price','combined'),('responsive','combined'))
STRESS_SCENARIOS=tuple((n,s) for n in NAMES for s in ('cheap','idle'))+(
    (None,'normal'),(None,'no_trade'),('Mechania','no_raw'))
# Missing recommendation observations must fail rather than masquerade as zeros.
# A successful frozen test manifest remains a separate gate before any games run.
ADVICE_SCHEMA_READY=True
ADVICE_REQUIRED_COUNTRY=('grade_recalls','planning_decisions','planning_holds',
    'public_offer_units','all_goods_unique_used','industry_use_score','economic_at_cap',
    'offer_price_mismatches','listing_plan_violations','protected_offer_violations')
ADVICE_REQUIRED_WORLD=('grade_recalls','planning_decisions','planning_holds',
    'public_offer_units','all_goods_unique_used','offer_price_mismatches',
    'listing_plan_violations','protected_offer_violations')
CHANNELS=('market','direct','barter')
CHANNEL_FIELDS=('sold_units','bought_units','sales_cash','purchase_cash')

REQUIRED_COUNTRY=('cash','happy','revenue','purchases','investment','tax','useful_exports',
    'exports','imports','listed',
    'food_short_rounds','production_failures','machine_gen','elec_gen','upgrades',
    'uncovered_investments','fallback_without_deferral','fallback_after_deferral',
    'household_blocks','machine_pauses','machine_planned','machine_capacity_total',
    'machine_fallbacks','paid_for_basic_only','machine_upkeep_ore','upkeep_blocked',
    'material_work_left','machine_needed_episodes','machine_missing_episodes',
    'imported_machine_used','machine_unique_used','machine_unique_used_including_initial',
    'equipment_use_episodes','equipment_extra_output')
REQUIRED_WORLD=('countries','transactions','trade_units','happy','original_happy',
    'original_cash_gap','original_coverage','original_useful_exports','listed',
    'aged_unused','aged_unused_per_country','initial_cash','cash_total','tax','investment',
    'verify_calls','uncovered_investments','all_country_cash_gap','equipment_use_episodes',
    'equipment_extra_output','machine_unique_used','machine_unique_used_including_initial',
    'machine_missing_episodes','machine_needed_episodes','machine_upkeep_ore','upkeep_blocked',
    'machine_pauses','machine_fallbacks','paid_for_basic_only','material_work_left')
COUNTRY_GOOD_COUNTS=('export_goods','import_goods','produced','purchase_by_good','sale_by_good',
    'use_by_good','export_used_by_good','end_stock_by_good','unused_by_good')
WORLD_GOOD_COUNTS=('production','consumed','trade_goods','remaining_goods','aged_unused_goods')


def hashes(files):
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}


def numeric(value,label):
    assert type(value) in (int,float) and math.isfinite(value),(label,value)


def count_map(obj,key,allowed):
    """Only sparse, documented count maps get explicit zero entries.

    A missing map, misspelled good, or missing mandatory scalar is an error.
    """
    assert key in obj and isinstance(obj[key],dict),('missing count map',key)
    assert set(obj[key])<=set(allowed),('unknown count key',key,set(obj[key])-set(allowed))
    for good,value in obj[key].items():
        numeric(value,(key,good))
        assert value>=0,(key,good,value)
    obj[key]={good:obj[key].get(good,0) for good in allowed}


def normalize_and_validate(result):
    assert isinstance(result.get('countries'),dict) and isinstance(result.get('world'),dict)
    assert set(result['countries'])==set(CONFIG)|set(ADDITIONS)
    for name,x in result['countries'].items():
        for key in REQUIRED_COUNTRY+ADVICE_REQUIRED_COUNTRY:
            assert key in x,('missing required country scalar',name,key)
            numeric(x[key],(name,key))
        for key in COUNTRY_GOOD_COUNTS:count_map(x,key,GOODS)
        assert 'listed_by_good' in x and set(x['listed_by_good'])==set(GOODS),(name,'listed_by_good')
        for good,value in x['listed_by_good'].items():
            numeric(value,(name,'listed_by_good',good))
            assert value>=0
        assert sum(x['listed_by_good'].values())==x['listed'],(name,'listed inventory reconciliation')
        assert 'channel_stats' in x and set(x['channel_stats'])==set(CHANNELS),(name,'channel_stats')
        for channel,values in x['channel_stats'].items():
            assert set(values)==set(CHANNEL_FIELDS),(name,channel,'channel fields')
            for key,value in values.items():
                numeric(value,(name,channel,key))
                assert value>=0
        for channel_key,total_key in (('sold_units','exports'),('bought_units','imports'),
                                      ('sales_cash','revenue'),('purchase_cash','purchases')):
            assert sum(c[channel_key] for c in x['channel_stats'].values())==x[total_key],(name,channel_key)
        assert x['channel_stats']['barter']['sales_cash']==x['channel_stats']['barter']['purchase_cash']==0
        assert x['all_goods_unique_used']==sum(x['use_by_good'].values()),(name,'unique use reconciliation')
        assert x['planning_holds']<=x['planning_decisions'],(name,'planning holds')
        assert x['economic_at_cap'] in (0,1),(name,'economic_at_cap')
        for key in ('production_raw','research_raw'):count_map(x,key,('ore','fuel'))
        # An absent industry is Lv.0; this is structural absence, not imputation.
        count_map(x,'end_levels',GOODS)
        for key in ('machine_stock_by_gen','machine_produced_by_gen'):
            assert set(x[key])=={'1','2','3'},(name,key)
            for gen,value in x[key].items():numeric(value,(name,key,gen))
        assert set(x['needs_by_good'])==set(GOODS),(name,'needs_by_good')
        for good,need in x['needs_by_good'].items():
            for key in ('external','fulfilled'):numeric(need[key],(name,good,key))
            assert 0<=need['fulfilled']<=need['external']
        if name in NAMES:
            for key in ('score','economic','industry','trade'):numeric(x[key],(name,key))
            assert 'industry_capacity_score' in x,('missing industry capacity',name)
            numeric(x['industry_capacity_score'],(name,'industry_capacity_score'))
            assert math.isclose(x['industry_capacity_score']+x['industry_use_score'],x['industry'],abs_tol=1e-9)
        else:
            assert x['score'] is None and x['economic'] is None and x['industry'] is None
            assert 'industry_capacity_score' in x and x['industry_capacity_score'] is None,(name,'diagnostic scores unavailable')
    world=result['world']
    for key in REQUIRED_WORLD+ADVICE_REQUIRED_WORLD:
        assert key in world,('missing required world scalar',key)
        numeric(world[key],('world',key))
    for key in WORLD_GOOD_COUNTS:count_map(world,key,GOODS)
    for key in ADVICE_REQUIRED_WORLD:
        assert world[key]==sum(x[key] for x in result['countries'].values()),('world total',key)
    assert sum(x['exports'] for x in result['countries'].values())==world['trade_units']
    assert sum(x['imports'] for x in result['countries'].values())==world['trade_units']
    for channel in CHANNELS:
        assert sum(x['channel_stats'][channel]['sales_cash'] for x in result['countries'].values())==sum(
            x['channel_stats'][channel]['purchase_cash'] for x in result['countries'].values()),('channel cash balance',channel)
    assert set(world['end_prices'])==set(GOODS)
    assert set(world['machine_launch_rounds'])=={'2','3'}
    for key,value in world['end_prices'].items():numeric(value,('price',key))
    for key,value in world['machine_launch_rounds'].items():
        assert type(value) is int and 1<=value<=10,('launch round',key,value)
    assert world['countries']==9
    return result


def build_tasks(n=200,stress_n=30):
    tasks=[('main',mode,seed,None,'normal') for mode in MODES for seed in range(44000,44000+n)]
    tasks += [('stress',mode,seed,focal,style) for mode in STRESS_MODES
              for focal,style in STRESS_SCENARIOS for seed in range(46000,46000+stress_n)]
    assert len(tasks)==len(set(tasks))
    return tasks


def run_one(task):
    phase,mode,seed,focal,style=task
    game=Game(seed,variant=mode,focal=focal,style='normal' if style=='no_trade' else style,
              trade_enabled=style!='no_trade')
    result=normalize_and_validate(game.run())
    for key in ('offer_price_mismatches','listing_plan_violations','uncovered_investments'):
        assert result['world'][key]==0,(mode,seed,focal,style,key)
    if mode!='baseline':
        assert result['world']['protected_offer_violations']==0,(mode,seed,focal,style,'protected stock')
    if style=='no_raw':
        actor=result['countries'][focal]
        assert actor['import_goods']['ore']==actor['import_goods']['fuel']==0
    record={'phase':phase,'mode':mode,'seed':seed,'focal':focal,'style':style,**result}
    ledger=game.cash_ledger if phase=='main' else None
    trace=game.trace() if phase=='main' and seed==44000 else None
    return record,ledger,trace


def flat(obj,prefix=''):
    result={}
    for key,value in obj.items():
        path=f'{prefix}.{key}' if prefix else key
        if isinstance(value,dict):result.update(flat(value,path))
        elif type(value) in (int,float):
            numeric(value,path)
            result[path]=value
    return result


def stats(values):
    assert values
    mean=statistics.mean(values)
    error=statistics.stdev(values)/math.sqrt(len(values)) if len(values)>1 else 0
    return {'n':len(values),'mean':mean,'ci95':[mean-1.96*error,mean+1.96*error],
            'min':min(values),'max':max(values)}


def grouped(rows):
    flattened=[flat({'countries':row['countries'],'world':row['world']}) for row in rows]
    keys=set(flattened[0])
    for row in flattened:assert set(row)==keys,'inconsistent numeric schema; do not silently drop metrics'
    return {'n':len(rows),'metrics':{key:stats([row[key] for row in flattened]) for key in sorted(keys)}}


def pair(a,b,focal=None):
    left={row['seed']:flat({'countries':row['countries'],'world':row['world']}) for row in a}
    right={row['seed']:flat({'countries':row['countries'],'world':row['world']}) for row in b}
    assert len(left)==len(a) and len(right)==len(b) and left.keys()==right.keys()
    seeds=sorted(left)
    keys=set(left[seeds[0]])
    for seed in seeds:
        assert set(left[seed])==keys and set(right[seed])==keys,'paired metric schemas differ'
    result={key:stats([right[seed][key]-left[seed][key] for seed in seeds]) for key in sorted(keys)}
    if focal in NAMES:
        result['world.other_original_five_happy']=stats([
            statistics.mean(right[seed][f'countries.{name}.happy']-left[seed][f'countries.{name}.happy']
                            for name in NAMES if name!=focal) for seed in seeds])
    return result


def summarize(rows,metadata):
    groups=defaultdict(list)
    for row in rows:groups[(row['phase'],row['mode'],row['focal'],row['style'])].append(row)
    experiments={':'.join(map(str,key)):grouped(group) for key,group in groups.items()}
    pairs={}
    for a,b in MAIN_PAIRS:
        pairs[f'main:{a}->{b}']=pair(groups[('main',a,None,'normal')],groups[('main',b,None,'normal')])
    for mode in STRESS_MODES:
        control=groups[('stress',mode,None,'normal')]
        for focal,style in STRESS_SCENARIOS:
            if style=='normal':continue
            suffix='no_trade' if style=='no_trade' else f'{focal}:{style}'
            pairs[f'stress:{mode}:{suffix}']=pair(control,groups[('stress',mode,focal,style)],focal)
    for a,b in STRESS_PAIRS:
        for focal,style in STRESS_SCENARIOS:
            pairs[f'stress:{a}->{b}:{focal}:{style}']=pair(
                groups[('stress',a,focal,style)],groups[('stress',b,focal,style)],focal)
    return {'metadata':metadata,'experiments':experiments,'paired':pairs}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--n',type=int,default=200)
    parser.add_argument('--stress-n',type=int,default=30)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if not 2<=args.n<=2000 or not 2<=args.stress_n<=2000:
        parser.error('use 2..2000 seeds per group without overlapping designated seed bands')
    if args.workers<1:parser.error('workers must be positive')
    tasks=build_tasks(args.n,args.stress_n)
    sources=hashes(SOURCE_FILES)
    tests=hashes(TEST_FILES)
    if args.dry_run:
        print(json.dumps({'planned_games':len(tasks),'main_games':len(MODES)*args.n,
            'stress_games':len(STRESS_MODES)*len(STRESS_SCENARIOS)*args.stress_n,
            'main_seed_range':[44000,44000+args.n-1],
            'stress_seed_range':[46000,46000+args.stress_n-1],
            'main_pairs':len(MAIN_PAIRS),'stress_own_control_pairs':len(STRESS_MODES)*(len(STRESS_SCENARIOS)-1),
            'stress_between_mode_pairs':len(STRESS_PAIRS)*len(STRESS_SCENARIOS),'executed_games':0},ensure_ascii=False))
        return
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    for name in ('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz',
                 'runs.partial.jsonl.gz','round_ledgers.partial.jsonl.gz','round_ledgers.jsonl.gz'):
        if (output/name).exists():raise FileExistsError(f'Preserve existing validation output; choose a new --output-dir: {output/name}')
    assert ADVICE_SCHEMA_READY,'recommendation summary contract has not been frozen'
    test_manifest_path=ROOT/'advice_results'/'tests_manifest.json'
    test_manifest=json.loads(test_manifest_path.read_text())
    assert test_manifest['passed'] is True and test_manifest['test_count']>168
    assert test_manifest['inherited_tests']==168
    assert test_manifest['test_sha256']==tests,'tests changed after recorded verification'
    assert test_manifest['economic_source_sha256']==hashes(ECONOMIC_FILES),'economic source changed after recorded tests'
    config={'main_seed_range':[44000,44000+args.n-1],
        'stress_seed_range':[46000,46000+args.stress_n-1],'excluded_pilot_range':[42000,42029],
        'excluded_test_seed_band':[42100,42199],
        'planned_games':len(tasks),'modes':{name:asdict(policy) for name,policy in MODES.items()},
        'baseline_reference':'v6 coupled unchanged',
        'physical_mode':'coupled','physical_policy':asdict(PHYSICAL_MODES['coupled']),
        'baseline_ai_policy':asdict(POLICIES['balanced']),'options':asdict(BASE_OPTIONS),
        'credits_per_raw':CREDITS_PER_RAW,'upkeep_uses':UPKEEP_USES,
        'original_countries':CONFIG,'new_countries':ADDITIONS,'rounds':9,'countries':9,
        'source_sha256':sources,'source_sha256_before':sources,'test_sha256_before':tests,
        'tests_manifest_sha256':hashlib.sha256(test_manifest_path.read_bytes()).hexdigest(),
        'tests_completed':test_manifest['test_count'],
        'advice_required_country':ADVICE_REQUIRED_COUNTRY,'advice_required_world':ADVICE_REQUIRED_WORLD,
        'channels':CHANNELS,'channel_fields':CHANNEL_FIELDS,
        'stress_modes':STRESS_MODES,
        'stress_scenarios':STRESS_SCENARIOS,'main_pairs':MAIN_PAIRS,'stress_mode_pairs':STRESS_PAIRS,
        'normalization':'Only documented sparse goods counts and absent industry levels receive zero; missing mandatory fields fail.',
        'primary_checks':['cash/goods/ownership/escrow and material credit conservation',
            'zero uncovered investments under inherited balanced policy',
            'advice-to-final-price and public-listing-volume consistency',
            'active advice variants never expose their protected units in public offers',
            'all-goods actual production/use/inventory and trade channels',
            'all-nine welfare/cash and productive investments; no score-based fitting'],
        'limitations':['serial rule-based agents, not a multiplayer app or student study',
            'cheap means half of reference quote; purchasing and investment remain active',
            'no_raw rejects both cash and barter ore/fuel imports for the designated actor',
            'v6 coupled physical rules, starting conditions, price update and scoring remain unchanged',
            'listing caps apply to public-market orders only; direct cash/barter remain available',
            'recommendations use own information and permitted public data, not future outcomes or private buyer wallets',
            'unchanged diagnostic scoring has an output-sensitive utilization denominator',
            'confidence intervals describe seed variation inside this model only',
            'machine launch round 10 is the sentinel for no launch within nine rounds']}
    (output/'pre_run_plan.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    started=time.monotonic()
    rows=[]
    traces={}
    with ProcessPoolExecutor(max_workers=args.workers) as pool, \
         gzip.open(output/'runs.partial.jsonl.gz','wt') as run_file, \
         gzip.open(output/'round_ledgers.partial.jsonl.gz','wt') as ledger_file:
        for i,(record,ledger,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            rows.append(record)
            run_file.write(json.dumps(record,ensure_ascii=False)+'\n')
            if ledger is not None:
                ledger_file.write(json.dumps({'mode':record['mode'],'seed':record['seed'],'rows':ledger},ensure_ascii=False)+'\n')
            if trace is not None:traces[record['mode']]=trace
            if i%200==0:print(f'{i}/{len(tasks)} games complete; {time.monotonic()-started:.1f}s',flush=True)
    assert len(rows)==len(tasks)==len({(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows})
    after=hashes(SOURCE_FILES)
    tests_after=hashes(TEST_FILES)
    assert sources==after,'source changed during formal execution'
    assert tests==tests_after,'test definitions changed during formal execution'
    assert set(traces)==set(MODES)
    assert all(row['world']['uncovered_investments']==0 for row in rows)
    metadata={**config,'source_sha256_after':after,'test_sha256_after':tests_after,
        'source_unchanged':True,'completed_games':len(rows),'main_games':len(MODES)*args.n,
        'stress_games':len(rows)-len(MODES)*args.n,
        'verification_calls':sum(row['world']['verify_calls'] for row in rows),'verification_failures':0,
        'elapsed_seconds':time.monotonic()-started,'pilot_excluded':True,
        'trace_and_unit_test_games_excluded':True}
    summary=summarize(rows,metadata)
    for name in ('runs','round_ledgers'):
        (output/f'{name}.partial.jsonl.gz').replace(output/f'{name}.jsonl.gz')
    with gzip.open(output/'first_seed_traces.json.gz','wt') as trace_file:
        json.dump(traces,trace_file,ensure_ascii=False)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (output/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(f'DONE {len(rows)} games, {metadata["verification_calls"]} invariant calls, {metadata["elapsed_seconds"]:.2f}s',flush=True)


if __name__=='__main__':
    main()

