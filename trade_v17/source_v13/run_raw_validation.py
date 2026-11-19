"""Frozen v8 raw-resource comparison; importing this module starts no games.

Main: seven raw policies x 200 seeds (54000..54199) = 1400 games.
Stress: baseline/starter/bridge/recipe/coupled x 23 scenarios x 30 seeds
(56000..56029) = 3450 games. Pilot 52000..52029 and tests 521xx are excluded.
Default total: 4850 games. Use --dry-run to inspect the schedule without running.
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
from itertools import combinations
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from raw_engine import Game, RAW_MODES as MODES, REFUSAL_STYLES, RAW_GOODS, SOURCE_KINDS
from machinery_engine import MODES as PHYSICAL_MODES, CREDITS_PER_RAW, UPKEEP_USES
from budget_engine import POLICIES
from expansion_engine import BASE_OPTIONS, ADDITIONS, CONFIG, NAMES, GOODS

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'raw_results'
ECONOMIC_FILES=('reference_engine.py','core_engine.py','engine.py','expansion_engine.py',
                'budget_engine.py','budget_trace.py','machinery_engine.py','recommendation_engine.py','raw_engine.py')
SOURCE_FILES=ECONOMIC_FILES+('run_raw_validation.py',)
TEST_FILES=('test_previous.py','test_fixes.py','test_costs.py','test_expansion.py',
            'test_budget.py','test_machinery.py','test_recommendation.py','test_raw_resources.py')
STRESS_MODES=('baseline','starter','bridge','recipe','coupled')
MAIN_PAIRS=(('baseline','starter'),('baseline','bridge'),('baseline','recipe'),
            ('baseline','coupled'),('baseline','no_starter'),('baseline','strict_no_starter'),
            ('starter','coupled'),('recipe','coupled'),('no_starter','starter'),
            ('strict_no_starter','coupled'),('no_starter','strict_no_starter'),
            ('recipe','strict_no_starter'),('starter','bridge'))
STRESS_PAIRS=tuple(combinations(STRESS_MODES,2))
STRESS_SCENARIOS=tuple((n,s) for n in NAMES for s in ('cheap','idle'))+((None,'normal'),(None,'no_trade'))+tuple((n,s) for n in ('Mechania','Technia','Novia') for s in REFUSAL_STYLES)
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
RAW_COUNTS=('consumed','production','research','imported_used')+SOURCE_KINDS
RAW_MAPS=('starter_raw','raw_import_rounds','first_raw_import_round','raw_importing',
          'initial_raw_left','raw_unmet_production')
RAW_COUNTRY_SCALARS=('first_two_happy','first_two_food_short','first_two_production_failures',
    'first_round_happy','first_round_production_failures','start_asset_value','end_asset_value',
    'cash_plus_stock_value','machine_free_basic','machine_g2','machine_g3','electronics_g2','electronics_g3')
RAW_WORLD_SUMS=('first_two_food_short','first_two_production_failures','first_round_production_failures',
    'machine_free_basic','machine_g2','machine_g3','electronics_g2','electronics_g3')
RAW_WORLD_MAPS=('starter_raw','initial_raw_left','raw_importing','raw_import_rounds','raw_unmet_production')
RAW_FLOW_FIELDS=('imports','exports','purchases','sales','opening_stock','produced','stock','unmet_production')


def nonnegative_integer(value,label):
    assert type(value) is int and value>=0,(label,value)


def validate_raw_summary(result):
    countries=result['countries'];world=result['world']
    assert 'raw_policy' in world and set(world['raw_policy'])=={'machine_credits','starter'}
    assert world['raw_policy'] in [asdict(policy) for policy in MODES.values()]
    for name,x in countries.items():
        for key in RAW_COUNTRY_SCALARS:
            assert key in x,('missing raw country scalar',name,key)
            numeric(x[key],(name,key))
        for key in RAW_MAPS:
            assert key in x and set(x[key])==set(RAW_GOODS),(name,key,'missing raw map')
            for good,value in x[key].items():nonnegative_integer(value,(name,key,good))
        assert 'raw_use' in x and set(x['raw_use'])==set(RAW_GOODS),(name,'raw_use')
        for good,counts in x['raw_use'].items():
            assert set(counts)==set(RAW_COUNTS),(name,good,'raw source fields')
            for key,value in counts.items():nonnegative_integer(value,(name,good,key))
            assert counts['consumed']==counts['production']+counts['research']==sum(counts[k] for k in SOURCE_KINDS)
            assert counts['imported_used']<=counts['consumed']
            assert counts['production']==x['production_raw'][good] and counts['research']==x['research_raw'][good]
            assert x['raw_importing'][good] in (0,1)
            assert 0<=x['raw_import_rounds'][good]<=9
            assert 1<=x['first_raw_import_round'][good]<=10
            assert (x['first_raw_import_round'][good]==10)==(x['raw_importing'][good]==0)
            assert bool(x['raw_import_rounds'][good])==bool(x['raw_importing'][good])
        assert 0<=x['first_round_happy']<=100 and 0<=x['first_two_happy']<=100
        assert 0<=x['first_two_food_short']<=2
        assert x['first_round_production_failures']<=x['first_two_production_failures']
        for good in ('machine','electronics'):
            assert x[good+'_g2'] in (0,1) and x[good+'_g3'] in (0,1)
            assert x[good+'_g3']<=x[good+'_g2']
        assert math.isclose(x['end_asset_value'],x['cash_plus_stock_value']+.45*x['investment'],abs_tol=1e-9)
    for key in RAW_WORLD_SUMS:
        assert key in world,('missing raw world scalar',key)
        numeric(world[key],('world',key))
        assert world[key]==sum(x[key] for x in countries.values()),('world sum',key)
    for key in RAW_WORLD_MAPS:
        assert key in world and set(world[key])==set(RAW_GOODS),('world',key)
        for good in RAW_GOODS:
            nonnegative_integer(world[key][good],('world',key,good))
            assert world[key][good]==sum(x[key][good] for x in countries.values())
    assert 'raw_use' in world and set(world['raw_use'])==set(RAW_GOODS)
    for good in RAW_GOODS:
        assert set(world['raw_use'][good])==set(RAW_COUNTS)
        for key in RAW_COUNTS:
            assert world['raw_use'][good][key]==sum(x['raw_use'][good][key] for x in countries.values())
        assert world['initial_raw_left'][good]<=world['starter_raw'][good]
    for key in ('first_round_happy','first_two_happy'):
        assert key in world
        numeric(world[key],('world',key))
        assert math.isclose(world[key],statistics.mean(x[key] for x in countries.values()),abs_tol=1e-9)
    for key,field in (('initial_asset_value','start_asset_value'),('end_asset_value','end_asset_value')):
        assert key in world
        numeric(world[key],('world',key))
        assert math.isclose(world[key],sum(x[field] for x in countries.values()),abs_tol=1e-9)
    return result


def validate_raw_ledger(game,result):
    rows=game.raw_round_ledger
    expected={(name,r) for name in game.cs for r in range(1,10)}
    cells=[(row['country'],row['round']) for row in rows]
    assert len(rows)==81 and set(cells)==expected
    cash={(row['country'],row['round']):row for row in game.cash_ledger}
    assert set(cash)==expected and len(game.cash_ledger)==81
    previous={(name,g):game.starter_allocation[name][g] for name in game.cs for g in RAW_GOODS}
    by_country=defaultdict(list)
    for row in rows:
        name,r=row['country'],row['round'];by_country[name].append(row)
        assert row['cash']==cash[(name,r)]['cash_end'] and row['happy']==cash[(name,r)]['happy']
        assert type(row['food_met']) is bool
        assert set(row['goods'])==set(RAW_GOODS)
        for good,x in row['goods'].items():
            assert set(x)==set(RAW_COUNTS+RAW_FLOW_FIELDS)|{'machine_credits_by_grade'}
            for key in RAW_COUNTS+RAW_FLOW_FIELDS:nonnegative_integer(x[key],(name,r,good,key))
            assert x['opening_stock']==previous[(name,good)]
            assert x['stock']==x['opening_stock']+x['produced']+x['imports']-x['exports']-x['consumed']
            previous[(name,good)]=x['stock']
            assert x['consumed']==x['production']+x['research']==sum(x[k] for k in SOURCE_KINDS)
            assert x['imported_used']<=x['consumed']
            assert x['purchases']==cash[(name,r)]['purchase_by_good'][good]
            assert x['sales']==cash[(name,r)]['sale_by_good'][good]
            assert set(x['machine_credits_by_grade'])=={'1','2','3'}
            for value in x['machine_credits_by_grade'].values():
                assert type(value) is int and 0<=value<game.raw_policy.machine_credits
    for name,selected in by_country.items():
        assert [row['round'] for row in selected]==list(range(1,10))
        x=result['countries'][name]
        assert x['first_round_happy']==selected[0]['happy']
        assert x['first_two_happy']==statistics.mean(row['happy'] for row in selected[:2])
        assert x['first_two_food_short']==sum(not row['food_met'] for row in selected[:2])
        assert x['first_round_production_failures']==selected[0]['production_failures']
        assert x['first_two_production_failures']==sum(row['production_failures'] for row in selected[:2])
        for good in RAW_GOODS:
            assert previous[(name,good)]==x['end_stock_by_good'][good]
            for key in RAW_COUNTS:
                assert sum(row['goods'][good][key] for row in selected)==x['raw_use'][good][key]
            for key,summary_key in (('imports','import_goods'),('exports','export_goods'),('purchases','purchase_by_good'),('sales','sale_by_good')):
                assert sum(row['goods'][good][key] for row in selected)==x[summary_key][good]
            assert sum(row['goods'][good]['unmet_production'] for row in selected)==x['raw_unmet_production'][good]
    for r in range(1,10):
        selected=[row for row in rows if row['round']==r]
        for good in RAW_GOODS:
            assert sum(row['goods'][good]['imports'] for row in selected)==sum(row['goods'][good]['exports'] for row in selected)
            assert sum(row['goods'][good]['purchases'] for row in selected)==sum(row['goods'][good]['sales'] for row in selected)


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
    return validate_raw_summary(result)


def build_tasks(n=200,stress_n=30):
    tasks=[('main',mode,seed,None,'normal') for mode in MODES for seed in range(54000,54000+n)]
    tasks += [('stress',mode,seed,focal,style) for mode in STRESS_MODES
              for focal,style in STRESS_SCENARIOS for seed in range(56000,56000+stress_n)]
    assert len(tasks)==len(set(tasks))
    return tasks


def trace_key(record):
    return ':'.join(str(record[k]) for k in ('phase','mode','seed','focal','style'))


def run_one(task):
    phase,mode,seed,focal,style=task
    game=Game(seed,variant=mode,focal=focal,style='normal' if style=='no_trade' else style,
              trade_enabled=style!='no_trade')
    result=normalize_and_validate(game.run())
    assert result['world']['raw_policy']==asdict(MODES[mode])
    for key in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
        assert result['world'][key]==0,(mode,seed,focal,style,key)
    if style in REFUSAL_STYLES:
        actor=result['countries'][focal]
        for good in REFUSAL_STYLES[style]:
            assert actor['import_goods'][good]==actor['purchase_by_good'][good]==actor['raw_use'][good]['imported_used']==0
    validate_raw_ledger(game,result)
    record={'phase':phase,'mode':mode,'seed':seed,'focal':focal,'style':style,**result}
    cash_ledger=game.cash_ledger if phase=='main' else None
    raw_ledger=game.raw_round_ledger if phase=='main' else None
    representative=(phase=='main' and seed==54000) or (phase=='stress' and seed==56000 and style in REFUSAL_STYLES)
    trace={**game.trace(),**{k:record[k] for k in ('phase','mode','seed','focal','style')}} if representative else None
    return record,cash_ledger,raw_ledger,trace


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
            'main_seed_range':[54000,54000+args.n-1],
            'stress_seed_range':[56000,56000+args.stress_n-1],
            'main_pairs':len(MAIN_PAIRS),'stress_own_control_pairs':len(STRESS_MODES)*(len(STRESS_SCENARIOS)-1),
            'stress_between_mode_pairs':len(STRESS_PAIRS)*len(STRESS_SCENARIOS),
            'representative_traces':len(MODES)+len(STRESS_MODES)*9,'executed_games':0},ensure_ascii=False))
        return
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    for name in ('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz',
                 'runs.partial.jsonl.gz','round_ledgers.partial.jsonl.gz','round_ledgers.jsonl.gz',
                 'raw_round_ledgers.partial.jsonl.gz','raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz'):
        if (output/name).exists():raise FileExistsError(f'Preserve existing validation output; choose a new --output-dir: {output/name}')
    assert ADVICE_SCHEMA_READY,'recommendation summary contract has not been frozen'
    test_manifest_path=ROOT/'raw_results'/'tests_manifest.json'
    test_manifest=json.loads(test_manifest_path.read_text())
    assert test_manifest['passed'] is True and test_manifest['test_count']>197
    assert test_manifest['inherited_tests']==197
    assert test_manifest['test_sha256']==tests,'tests changed after recorded verification'
    assert test_manifest['economic_source_sha256']==hashes(ECONOMIC_FILES),'economic source changed after recorded tests'
    assert test_manifest['validation_source_sha256']==sources,'runner/source changed after recorded verification'
    config={'main_seed_range':[54000,54000+args.n-1],
        'stress_seed_range':[56000,56000+args.stress_n-1],'excluded_pilot_range':[52000,52029],
        'excluded_test_seed_band':[52100,52199],
        'planned_games':len(tasks),'modes':{name:asdict(policy) for name,policy in MODES.items()},
        'raw_modes':{name:asdict(policy) for name,policy in MODES.items()},'advice_mode':'price',
        'baseline_reference':'v7 price unchanged',
        'physical_mode':'coupled','physical_policy':asdict(PHYSICAL_MODES['coupled']),
        'baseline_ai_policy':asdict(POLICIES['balanced']),'options':asdict(BASE_OPTIONS),
        'legacy_credits_per_raw':CREDITS_PER_RAW,'upkeep_uses':UPKEEP_USES,
        'original_countries':CONFIG,'new_countries':ADDITIONS,'rounds':9,'countries':9,'main_ledger_rows_planned':len(MODES)*args.n*81,
        'representative_traces_planned':len(MODES)+len(STRESS_MODES)*9,
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
            'raw source classes, raw mass balance, first two rounds and scoped machine credits',
            'all-nine welfare/cash and productive investments; no score-based fitting'],
        'limitations':['serial rule-based agents, not a multiplayer app or student study',
            'cheap means half of reference quote; purchasing and investment remain active',
            'no_ore/no_fuel/no_raw rejects selected raw imports through all three channels for the designated actor',
            'v7 price AI, initial cash, prices and scores unchanged; initial raw grants and machine input intensity vary explicitly',
            'one credit instead of two means higher machine input intensity at unchanged commodity prices; not a global unit redenomination',
            'no-starter policies are boundary diagnostics; initial asset baselines reflect actual grants',
            'listing caps apply to public-market orders only; direct cash/barter remain available',
            'v7 price recommendation scope inherited; inactive investment opportunity estimator is not a v8 decision policy',
            'unchanged diagnostic scoring has an output-sensitive utilization denominator',
            'confidence intervals describe seed variation inside this model only',
            'machine launch round 10 is the sentinel for no launch within nine rounds']}
    (output/'pre_run_plan.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    started=time.monotonic()
    rows=[]
    traces={}
    with ProcessPoolExecutor(max_workers=args.workers) as pool, \
         gzip.open(output/'runs.partial.jsonl.gz','wt') as run_file, \
         gzip.open(output/'round_ledgers.partial.jsonl.gz','wt') as ledger_file, \
         gzip.open(output/'raw_round_ledgers.partial.jsonl.gz','wt') as raw_ledger_file:
        for i,(record,ledger,raw_ledger,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            rows.append(record)
            run_file.write(json.dumps(record,ensure_ascii=False)+'\n')
            if ledger is not None:
                ledger_file.write(json.dumps({'mode':record['mode'],'seed':record['seed'],'rows':ledger},ensure_ascii=False)+'\n')
            if raw_ledger is not None:
                raw_ledger_file.write(json.dumps({'mode':record['mode'],'seed':record['seed'],'rows':raw_ledger},ensure_ascii=False)+'\n')
            if trace is not None:traces[trace_key(record)]=trace
            if i%200==0:print(f'{i}/{len(tasks)} games complete; {time.monotonic()-started:.1f}s',flush=True)
    assert len(rows)==len(tasks)==len({(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows})
    after=hashes(SOURCE_FILES)
    tests_after=hashes(TEST_FILES)
    assert sources==after,'source changed during formal execution'
    assert tests==tests_after,'test definitions changed during formal execution'
    expected_traces={':'.join(map(str,t)) for t in tasks if (t[0]=='main' and t[2]==54000) or (t[0]=='stress' and t[2]==56000 and t[4] in REFUSAL_STYLES)}
    assert set(traces)==expected_traces
    assert all(row['world']['uncovered_investments']==0 for row in rows)
    metadata={**config,'source_sha256_after':after,'test_sha256_after':tests_after,
        'source_unchanged':True,'completed_games':len(rows),'main_games':len(MODES)*args.n,
        'stress_games':len(rows)-len(MODES)*args.n,
        'verification_calls':sum(row['world']['verify_calls'] for row in rows),'verification_failures':0,
        'elapsed_seconds':time.monotonic()-started,'pilot_excluded':True,
        'trace_and_unit_test_games_excluded':True,
        'main_cash_ledger_rows':len(MODES)*args.n*81,'main_raw_ledger_rows':len(MODES)*args.n*81,
        'representative_traces':len(traces)}
    summary=summarize(rows,metadata)
    for name in ('runs','round_ledgers','raw_round_ledgers'):
        (output/f'{name}.partial.jsonl.gz').replace(output/f'{name}.jsonl.gz')
    with gzip.open(output/'first_seed_traces.json.gz','wt') as trace_file:
        json.dump(traces,trace_file,ensure_ascii=False)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (output/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(f'DONE {len(rows)} games, {metadata["verification_calls"]} invariant calls, {metadata["elapsed_seconds"]:.2f}s',flush=True)


if __name__=='__main__':
    main()

