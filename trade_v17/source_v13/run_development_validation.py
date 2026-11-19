"""Frozen v9 2x2 comparison. Importing starts no tests or simulations.

Main: 4 variants x 200 paired seeds 60000..60199 = 800 games.
Stress: 4 variants x 19 scenarios x 30 paired seeds 62000..62029 = 2280.
Pilot 58000..58029 and unit-test 58100..58199 seeds are excluded.
Default formal total: 3080. Chronological chains are not causal effect estimates.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import statistics
import time
import unittest
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from development_engine import Game, MODES, DEVELOPMENT_METRICS, MACHINE_REFUSALS
from raw_engine import RAW_MODES, REFUSAL_STYLES
from run_raw_validation import normalize_and_validate as normalize_raw, validate_raw_ledger, flat, grouped, pair
from expansion_engine import BASE_OPTIONS, ADDITIONS, CONFIG, NAMES
from machinery_engine import MODES as PHYSICAL_MODES
from budget_engine import POLICIES

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'development_results'
ECONOMIC_FILES=('reference_engine.py','core_engine.py','engine.py','expansion_engine.py',
                'budget_engine.py','budget_trace.py','machinery_engine.py',
                'recommendation_engine.py','raw_engine.py','development_engine.py')
SOURCE_FILES=ECONOMIC_FILES+('run_raw_validation.py','run_development_validation.py')
TEST_FILES=('test_previous.py','test_fixes.py','test_costs.py','test_expansion.py','test_budget.py',
            'test_machinery.py','test_recommendation.py','test_raw_resources.py','test_development.py')
STRESS_MODES=tuple(MODES)
STRESS_SCENARIOS=tuple((n,s) for n in NAMES for s in ('cheap','idle'))+((None,'normal'),(None,'no_trade'))+(
    ('Technia','no_high_machine'),('Novia','no_high_machine'),('Mechania','no_high_machine'),
    ('Technia','no_ore'),('Mechania','no_raw'))
MAIN_PAIRS=(('baseline','supply'),('baseline','gate'),('baseline','combined'),
            ('supply','combined'),('gate','combined'))
STRESS_PAIRS=(('baseline','combined'),)
MAIN_START=60000
STRESS_START=62000
REFUSALS=set(REFUSAL_STYLES)|set(MACHINE_REFUSALS)


def hashes(files):
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}


def build_tasks(n=200,stress_n=30):
    tasks=[('main',mode,seed,None,'normal') for mode in MODES for seed in range(MAIN_START,MAIN_START+n)]
    tasks += [('stress',mode,seed,focal,style) for mode in STRESS_MODES for focal,style in STRESS_SCENARIOS
              for seed in range(STRESS_START,STRESS_START+stress_n)]
    assert len(tasks)==len(set(tasks))
    return tasks


def trace_key(record):
    return ':'.join(str(record[k]) for k in ('phase','mode','seed','focal','style'))


def representative(task):
    phase,mode,seed,focal,style=task
    return (phase=='main' and seed==MAIN_START) or (phase=='stress' and seed==STRESS_START and style in REFUSALS)


def normalize_and_validate(result):
    result=normalize_raw(result)
    world=result['world']
    assert world['raw_policy']==asdict(RAW_MODES['bridge'])
    assert world['development_variant'] in MODES
    assert world['development_policy']==asdict(MODES[world['development_variant']])
    for name,x in result['countries'].items():
        d=x['development']
        assert set(d)==set(DEVELOPMENT_METRICS),(name,'development metric schema')
        for key,value in d.items():
            assert type(value) is int and value>=0,(name,key,value)
        assert d['upgrades']==x['upgrades']
        assert d['foreign_machine_upgrades']<=d['imported_machine_upgrades']<=d['machine_required_upgrades']<=d['upgrades']
        assert d['unique_foreign_machines_development']<=d['foreign_machine_upgrades']
        assert d['unique_imported_machines_development']<=d['imported_machine_upgrades']
        assert d['used_output_upgrades']<=d['productive_upgrades']<=d['upgrades']
        assert d['foreign_machine_used_output_upgrades']<=d['foreign_machine_productive_upgrades']<=d['foreign_machine_upgrades']
        assert d['foreign_machine_export_used_units']<=d['foreign_machine_output_used_units']<=d['foreign_machine_output_units']
        assert d['bought_high_machine_developed_unique']<=d['bought_high_machine_used_unique']<=d['bought_high_machine_unique']<=d['bought_high_machines']
        assert d['foreign_produced_high_bought_unique']<=d['bought_high_machine_unique']
        assert d['high_machine_useful_exports']<=d['high_machine_used']<=d['high_machine_produced']
        assert d['high_machine_unused_stock']<=d['high_machine_ending_stock']
        for good in ('machine','electronics'):
            assert d[f'g3_{good}_used']<=d[f'g3_{good}_output']<=x['produced'][good]
        if name in NAMES:
            assert math.isclose(x['score'],x['economic']+x['industry']+x['trade']+x['happy']/4,abs_tol=1e-9)
        else:
            assert x['score'] is None and x['industry'] is None and x['economic'] is None
    assert set(world['development'])==set(DEVELOPMENT_METRICS)
    for key in DEVELOPMENT_METRICS:
        assert world['development'][key]==sum(x['development'][key] for x in result['countries'].values()),('world sum',key)
    d=world['development']
    assert d['bought_high_machines']==d['sold_high_machines']
    assert d['high_machine_purchase_cash']==d['high_machine_sales_cash']
    assert d['g3_machine_output']==sum(x['machine_produced_by_gen']['3'] for x in result['countries'].values())
    return result


def validate_development_records(game,result):
    """Cross-check summaries against authoritative actions and physical UID paths.

    This runs in every formal game; persisted full trace reconstruction is still
    limited to the 24 explicitly selected representative games.
    """
    events=game.development_log
    by_action={(e['round'],e['country'],e['industry'],e['to_level']):e for e in events}
    expected={(r,name,g,level) for name,c in game.cs.items() for r,g,level in c.upgrade_rounds}
    assert len(events)==len(by_action) and set(by_action)==expected
    assert sum(e['cash_cost'] for e in events)==game.sunk
    for name,c in game.cs.items():
        assert sum(e['cash_cost'] for e in events if e['country']==name)==c.investment
    all_output=[i for row in game.development_output_log for i in row['ids']]
    assert len(all_output)==len(set(all_output))
    assert set(all_output)=={i for i,u in game.units.items() if u.born>0}
    uses={(e['round'],e['country'],e['uid'],e['purpose']):e for e in game.development_use_log}
    assert len(uses)==len(game.development_use_log) and set(uses)==game.use_episodes
    raw_development={e['uid']:e for e in game.raw_use_log if e['purpose']=='development'}
    ore_ids=[i for event in events for i in event['ore_ids']]
    assert len(ore_ids)==len(set(ore_ids)) and set(ore_ids)==set(raw_development)
    for event in events:
        for uid in event['ore_ids']:
            raw=raw_development[uid]
            assert (raw['round'],raw['country'],raw['good'])==(event['round'],event['country'],'ore')
        machine=event['machine']
        if machine:
            assert uses[(event['round'],event['country'],machine['uid'],'development')]==machine
            assert machine['generation']>=event['machine_min_gen']
            idx=machine['import_transaction']
            if idx is not None:
                assert type(idx) is int and 0<=idx<len(game.transactions)
                tx=game.transactions[idx]
                assert tx['round']<=event['round']
                assert any(leg['buyer']==event['country'] and machine['uid'] in leg['ids'] for leg in tx['legs'])
    for row in game.development_output_log:
        prior=[e for e in events if e['country']==row['country'] and e['industry']==row['industry'] and e['round']<row['round']]
        expected_id=prior[-1]['event_id'] if prior else None
        assert row['development_event_id']==expected_id
    chains=game.development_chains()
    used_chains=[i for e in chains for i in e['output_ids']]
    assert len(used_chains)==len(set(used_chains))
    for chain in chains:
        eid=chain['event_id']
        ids={i for row in game.development_output_log if row['development_event_id']==eid and row['funded'] for i in row['ids']}
        assert set(chain['output_ids'])==ids
        assert set(chain['used_output_ids'])=={i for i in ids if game.units[i].used}
        assert set(chain['foreign_used_output_ids'])=={i for i in ids if game.foreign_uses.get(i)}
    for name,x in result['countries'].items():
        own=[e for e in chains if e['country']==name]
        d=x['development']
        assert d['machine_required_upgrades']==sum(e['machine'] is not None for e in own)
        assert d['productive_upgrades']==sum(bool(e['output_ids']) for e in own)
        assert d['used_output_upgrades']==sum(bool(e['used_output_ids']) for e in own)
        assert d['foreign_machine_upgrades']==sum(e['foreign_machine'] for e in own)
        assert d['unique_foreign_machines_development']==len({e['machine']['uid'] for e in own if e['foreign_machine']})


def run_one(task):
    phase,mode,seed,focal,style=task
    game=Game(seed,variant=mode,focal=focal,style='normal' if style=='no_trade' else style,trade_enabled=style!='no_trade')
    result=normalize_and_validate(game.run())
    assert result['world']['development_policy']==asdict(MODES[mode])
    for key in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
        assert result['world'][key]==0,(mode,seed,focal,style,key)
    if style in REFUSAL_STYLES:
        actor=result['countries'][focal]
        for good in REFUSAL_STYLES[style]:
            assert actor['import_goods'][good]==actor['purchase_by_good'][good]==actor['raw_use'][good]['imported_used']==0
    if style in MACHINE_REFUSALS:
        grade=MACHINE_REFUSALS[style]
        assert all(not (leg['buyer']==focal and any(game.units[i].good=='machine' and game.units[i].gen>=grade for i in leg['ids']))
                   for tx in game.transactions for leg in tx['legs'])
        assert result['countries'][focal]['development']['bought_high_machines']==0
    if style=='idle':
        actor=result['countries'][focal]
        assert actor['imports']==actor['exports']==actor['investment']==0
    if style=='no_trade':assert result['world']['transactions']==0
    validate_raw_ledger(game,result)
    validate_development_records(game,result)
    record={'phase':phase,'mode':mode,'seed':seed,'focal':focal,'style':style,**result}
    ledger=game.cash_ledger if phase=='main' else None
    raw_ledger=game.raw_round_ledger if phase=='main' else None
    trace={**game.trace(),**{key:record[key] for key in ('phase','mode','seed','focal','style')}} if representative(task) else None
    return record,ledger,raw_ledger,trace


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
            pairs[f'stress:{a}->{b}:{focal}:{style}']=pair(groups[('stress',a,focal,style)],groups[('stress',b,focal,style)],focal)
    return {'metadata':metadata,'experiments':experiments,'paired':pairs}


def run_tests(output):
    before=hashes(SOURCE_FILES);test_hashes=hashes(TEST_FILES)
    start=time.monotonic()
    suite=unittest.defaultTestLoader.loadTestsFromNames([Path(name).stem for name in TEST_FILES])
    with (output/'tests.log').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    manifest={'passed':result.wasSuccessful(),'test_count':result.testsRun,'inherited_tests':230,
              'new_tests':result.testsRun-230,'failures':len(result.failures),'errors':len(result.errors),
              'skipped':len(result.skipped),'elapsed_seconds':time.monotonic()-start,
              'test_sha256':test_hashes,'economic_source_sha256':hashes(ECONOMIC_FILES),
              'validation_source_sha256':before,'source_unchanged':before==hashes(SOURCE_FILES),
              'tests_unchanged':test_hashes==hashes(TEST_FILES)}
    (output/'tests_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    assert manifest['passed'] and manifest['test_count']>230 and not manifest['skipped'],manifest
    assert manifest['source_unchanged'] and manifest['tests_unchanged']
    print(f'TESTS {manifest["test_count"]} passed, {manifest["elapsed_seconds"]:.2f}s',flush=True)
    return manifest


def verified_test_manifest(output):
    path=output/'tests_manifest.json'
    if not path.exists():return run_tests(output)
    manifest=json.loads(path.read_text())
    assert manifest['passed'] and manifest['test_count']>230 and manifest['inherited_tests']==230
    assert manifest['failures']==manifest['errors']==manifest['skipped']==0
    assert manifest['test_sha256']==hashes(TEST_FILES),'tests changed after recorded verification'
    assert manifest['economic_source_sha256']==hashes(ECONOMIC_FILES),'economic code changed after recorded verification'
    assert manifest['validation_source_sha256']==hashes(SOURCE_FILES),'runner changed after recorded verification'
    assert manifest['source_unchanged'] and manifest['tests_unchanged']
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--n',type=int,default=200)
    parser.add_argument('--stress-n',type=int,default=30)
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--tests-only',action='store_true')
    args=parser.parse_args()
    if not 2<=args.n<=2000 or not 2<=args.stress_n<=2000:parser.error('use 2..2000 seeds without overlapping seed bands')
    if args.workers<1:parser.error('workers must be positive')
    tasks=build_tasks(args.n,args.stress_n)
    if args.dry_run:
        print(json.dumps({'planned_games':len(tasks),'main_games':len(MODES)*args.n,
            'stress_games':len(STRESS_MODES)*len(STRESS_SCENARIOS)*args.stress_n,
            'main_seed_range':[MAIN_START,MAIN_START+args.n-1],
            'stress_seed_range':[STRESS_START,STRESS_START+args.stress_n-1],
            'representative_traces':sum(representative(t) for t in tasks),'executed_games':0},ensure_ascii=False));return
    output=args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz','runs.partial.jsonl.gz',
                 'round_ledgers.partial.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.partial.jsonl.gz',
                 'raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz'):
        if (output/name).exists():raise FileExistsError(f'Preserve validation output; choose a new output directory: {output/name}')
    if args.tests_only:
        run_tests(output);return
    tests=verified_test_manifest(output)
    sources=hashes(SOURCE_FILES);test_hashes=hashes(TEST_FILES)
    config={'main_seed_range':[MAIN_START,MAIN_START+args.n-1],
        'stress_seed_range':[STRESS_START,STRESS_START+args.stress_n-1],
        'excluded_pilot_range':[58000,58029],'excluded_test_seed_band':[58100,58199],
        'planned_games':len(tasks),'modes':{name:asdict(policy) for name,policy in MODES.items()},
        'raw_mode':'bridge','raw_policy':asdict(RAW_MODES['bridge']),'advice_mode':'price',
        'baseline_reference':'v8 bridge unchanged','physical_mode':'coupled',
        'physical_policy':asdict(PHYSICAL_MODES['coupled']),
        'baseline_ai_policy':asdict(POLICIES['balanced']),'options':asdict(BASE_OPTIONS),
        'original_countries':CONFIG,'new_countries':ADDITIONS,'rounds':9,'countries':9,
        'main_ledger_rows_planned':len(MODES)*args.n*81,
        'representative_traces_planned':sum(representative(t) for t in tasks),
        'source_sha256':sources,'source_sha256_before':sources,'test_sha256_before':test_hashes,
        'tests_manifest_sha256':hashlib.sha256((output/'tests_manifest.json').read_bytes()).hexdigest(),
        'tests_completed':tests['test_count'],'stress_modes':STRESS_MODES,'stress_scenarios':STRESS_SCENARIOS,
        'main_pairs':MAIN_PAIRS,'stress_mode_pairs':STRESS_PAIRS,
        'normalization':'v8 required schema retained; all v9 development metrics required with integer counts; no missing metric imputation.',
        'primary_checks':['cash/goods/ownership/listing and material-credit conservation',
            'zero uncovered investments; v7 price and protected-listing checks retained',
            'successful development reconciles to cash, consumed ore and historical machine UID',
            'every produced UID assigned to exactly one factory batch and at most one most-recent development',
            'only funded later output completes production chain, only real use completes use chain',
            'high-machine refusal blocks all import channels for focal actor while own output remains legal',
            'additional-country scores remain unavailable; inherited scoring formulas unchanged'],
        'limitations':['serial rule-based agents, not multiplayer or student-classroom validation',
            'cheap means half-reference asks; buying and investment continue',
            'idle means no voluntary trade/investment; automatic production and operating income continue',
            'supply adds a domestic support slot to existing sales-stock target only for G2/G3',
            'gate is experimental new durable Lv3 requirement; not already-confirmed classroom rule',
            'development chains establish observed chronological links, not incremental causal gains',
            'missing-machine attempts can coexist with cash, food or raw shortages; not isolated causes',
            'score caps and output-sensitive utilization denominator remain unchanged',
            'seed confidence intervals are model variation only; no classroom learning effect measured']}
    (output/'pre_run_plan.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    started=time.monotonic();rows=[];traces={}
    with ProcessPoolExecutor(max_workers=args.workers) as pool, \
         gzip.open(output/'runs.partial.jsonl.gz','wt') as run_file, \
         gzip.open(output/'round_ledgers.partial.jsonl.gz','wt') as ledger_file, \
         gzip.open(output/'raw_round_ledgers.partial.jsonl.gz','wt') as raw_file:
        for i,(record,ledger,raw_ledger,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            rows.append(record);run_file.write(json.dumps(record,ensure_ascii=False)+'\n')
            if ledger is not None:ledger_file.write(json.dumps({'mode':record['mode'],'seed':record['seed'],'rows':ledger},ensure_ascii=False)+'\n')
            if raw_ledger is not None:raw_file.write(json.dumps({'mode':record['mode'],'seed':record['seed'],'rows':raw_ledger},ensure_ascii=False)+'\n')
            if trace is not None:traces[trace_key(record)]=trace
            if i%200==0:print(f'{i}/{len(tasks)} games complete; {time.monotonic()-started:.1f}s',flush=True)
    assert len(rows)==len(tasks)==len({(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows})
    assert sources==hashes(SOURCE_FILES),'source changed during formal execution'
    assert test_hashes==hashes(TEST_FILES),'test definitions changed during formal execution'
    assert set(traces)=={':'.join(map(str,t)) for t in tasks if representative(t)}
    metadata={**config,'source_sha256_after':hashes(SOURCE_FILES),'test_sha256_after':hashes(TEST_FILES),
        'source_unchanged':True,'completed_games':len(rows),'main_games':len(MODES)*args.n,
        'stress_games':len(rows)-len(MODES)*args.n,
        'verification_calls':sum(r['world']['verify_calls'] for r in rows),'verification_failures':0,
        'elapsed_seconds':time.monotonic()-started,'pilot_excluded':True,'trace_and_unit_test_games_excluded':True,
        'main_cash_ledger_rows':len(MODES)*args.n*81,'main_raw_ledger_rows':len(MODES)*args.n*81,
        'representative_traces':len(traces)}
    summary=summarize(rows,metadata)
    for name in ('runs','round_ledgers','raw_round_ledgers'):
        (output/f'{name}.partial.jsonl.gz').replace(output/f'{name}.jsonl.gz')
    with gzip.open(output/'first_seed_traces.json.gz','wt') as stream:json.dump(traces,stream,ensure_ascii=False)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (output/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(f'DONE {len(rows)} games, {metadata["verification_calls"]} invariant calls, {metadata["elapsed_seconds"]:.2f}s',flush=True)


if __name__=='__main__':main()
