"""v11 paired public-price stress and posthoc development-machine scoring.

Main: one normal control plus six original countries x cheap/minimum/idle,
each on 200 paired seeds78000..78199: 3,800 unique economic trajectories.
Stress: 20 conditions x30 seeds80000..80029: 600 more trajectories.
The four shadow scoring views reuse each trajectory; they are not extra games.
Importing this module does not run tests, simulations, or write any files.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import time
import unittest
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from evaluation_engine import Game, SCORING_MODES, DIAGNOSTICS, MINIMUM_BEHAVIORS
from routing_engine import MODES as ROUTING_MODES
from run_routing_validation import (
    normalize_and_validate as normalize_routing, validate_routing_records,
    ECONOMIC_FILES as OLD_ECONOMIC_FILES, TEST_FILES as OLD_TEST_FILES,
)
from run_development_validation import validate_development_records
from run_raw_validation import validate_raw_ledger, grouped, pair
from expansion_engine import BASE_OPTIONS, CONFIG, ADDITIONS, NAMES

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'evaluation_results'
ECONOMIC_FILES = OLD_ECONOMIC_FILES+('evaluation_engine.py',)
SOURCE_FILES = ECONOMIC_FILES+('run_raw_validation.py','run_development_validation.py',
                             'run_routing_validation.py','run_evaluation_validation.py')
TEST_FILES = OLD_TEST_FILES+('test_evaluation.py',)
INHERITED_TESTS = 298
MAIN_START = 78000
STRESS_START = 80000
PILOT_RANGE = (74000,74009)
TEST_RANGE = (75100,75199)
IDENTITY_FIELDS = ('phase','mode','scenario','seed','focal','style','behaviors')
SCORE_KEYS = ('trade','score','trade_delta','external_need','external_fulfilled','coverage',
              'external_rounds','fulfilled_rounds','added_needed','added_external','added_fulfilled',
              'skipped_existing_credit','imports_part','effects_import_part')
SCORE_COUNTS = ('external_need','external_fulfilled','external_rounds','fulfilled_rounds',
                'added_needed','added_external','added_fulfilled','skipped_existing_credit')


def scenario(focal=None, style='normal', behaviors=()):
    """Hashable stable condition; secondary overrides are explicit, not hidden."""
    behaviors = tuple(sorted(behaviors))
    label = f'{focal}:{style}'+''.join(f'+{n}:{s}' for n,s in behaviors)
    return label,focal,style,behaviors


MAIN_SCENARIOS = (scenario(),)+tuple(scenario(n,s) for n in NAMES for s in ('cheap','minimum','idle'))
STRESS_SCENARIOS = (scenario(),)+tuple(scenario(n,s) for n in NAMES for s in ('minimum','minimum_passive'))+(
    scenario('Mechania','idle'),
    scenario('Mechania','idle',(('Technia','minimum'),)),
    scenario('Mechania','idle',(('Novia','minimum'),)),
    scenario('Technia','no_high_machine'),scenario('Novia','no_high_machine'),
    scenario('Technia','no_raw'),scenario(None,'no_trade'),
)


def hashes(files):
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}


def scenario_manifest(scenarios):
    return [{'scenario':sid,'focal':focal,'style':style,'behaviors':dict(overrides)}
            for sid,focal,style,overrides in scenarios]


def build_tasks(n=200, stress_n=30):
    tasks = [(phase,seed,*condition)
             for phase,start,count,conditions in (('main',MAIN_START,n,MAIN_SCENARIOS),
                                                  ('stress',STRESS_START,stress_n,STRESS_SCENARIOS))
             for condition in conditions for seed in range(start,start+count)]
    assert len(tasks)==len(set(tasks))
    assert len(MAIN_SCENARIOS)==19 and len(STRESS_SCENARIOS)==20
    return tasks


def representative(task):
    return task[1] == (MAIN_START if task[0]=='main' else STRESS_START)


def trace_key(record):
    return f'{record["phase"]}:{record["mode"]}:{record["scenario"]}:{record["seed"]}'


def close(actual,expected,label):
    assert math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-9),(label,actual,expected)


def normalize_and_validate(result):
    result = normalize_routing(result)
    world = result['world']
    assert world['routing_variant']=='market_first'
    assert world['routing_policy']==asdict(ROUTING_MODES['market_first'])
    config = world['evaluation_config']
    assert config['baseline']=='v10 market_first'
    assert config['legal_public_minimum']==1
    assert config['scoring_modes']==list(SCORING_MODES)
    assert config['original_scores_unchanged'] and config['shadow_scores_do_not_affect_actions'] and config['public_prices_only']
    for name,country in result['countries'].items():
        diagnostic = country['evaluation']
        assert set(diagnostic)==set(DIAGNOSTICS)|{'scores'},(name,'evaluation diagnostic schema')
        for key in DIAGNOSTICS:
            value = diagnostic[key]
            assert type(value) is int,(name,key,value)
            assert value>=0 or key=='cash_trade_balance',(name,key,value)
        assert diagnostic['public_minimum_violations']==0
        assert diagnostic['cash_trade_balance']==country['revenue']-country['purchases']
        assert diagnostic['unique_foreign_development_machines']<=diagnostic['foreign_machine_uses']<=diagnostic['successful_machine_uses']<=diagnostic['ready_opportunities']<=diagnostic['machine_attempts']<=7
        assert diagnostic['ready_unfulfilled']<=diagnostic['ready_opportunities']
        assert diagnostic['existing_equipment_overlap']<=diagnostic['foreign_machine_uses']
        views = diagnostic['scores']
        assert set(views)==set(SCORING_MODES)
        for mode,v in views.items():
            assert set(v)==set(SCORE_KEYS),(name,mode,'score schema')
            for key in SCORE_COUNTS:assert type(v[key]) is int and v[key]>=0,(name,mode,key,v[key])
            for key,value in v.items():
                if value is None:assert key=='score' and name not in NAMES
                else:assert type(value) in (int,float) and math.isfinite(value),(name,mode,key,value)
            assert 0<=v['external_fulfilled']<=v['external_need']
            assert 0<=v['added_fulfilled']<=v['added_external']<=v['added_needed']<=7
            assert 0<=v['fulfilled_rounds']<=v['external_rounds']<=9
            assert 0<=v['coverage']<=1
            assert 0<=v['trade']<=25+1e-9 and 0<=v['imports_part']<=8 and 0<=v['effects_import_part']<=4
            close(v['external_need'],country['external_need']+v['added_external'],(name,mode,'need'))
            close(v['external_fulfilled'],country['external_fulfilled']+v['added_fulfilled'],(name,mode,'fulfilled'))
            close(v['trade']-country['trade'],v['trade_delta'],(name,mode,'trade delta'))
            close(v['coverage'],v['external_fulfilled']/v['external_need'] if v['external_need'] else 0,(name,mode,'coverage'))
            if name in NAMES:
                assert 0<=v['score']<=100+1e-9
                close(v['score'],country['score']+v['trade_delta'],(name,mode,'total'))
            else:assert v['score'] is None
            if mode=='legacy':
                assert v['trade']==country['trade'] and v['score']==country['score']
                assert v['trade_delta']==v['added_needed']==v['added_external']==v['added_fulfilled']==v['skipped_existing_credit']==0
            elif mode!='ready_once':assert v['skipped_existing_credit']==0
        assert views['ready_once']['added_needed']+views['ready_once']['skipped_existing_credit']==views['ready']['added_needed']
        assert views['ready_once']['added_external']+views['ready_once']['skipped_existing_credit']==views['ready']['added_external']
        assert views['ready_once']['added_fulfilled']+views['ready_once']['skipped_existing_credit']==views['ready']['added_fulfilled']
    assert set(world['evaluation'])==set(DIAGNOSTICS)
    for key in DIAGNOSTICS:
        assert world['evaluation'][key]==sum(x['evaluation'][key] for x in result['countries'].values()),('world evaluation sum',key)
    assert world['evaluation']['cash_trade_balance']==0
    return result


def validate_evaluation_records(game,result):
    """Check snapshots, actual action links and each shadow score on every game.

    Current owned stock cannot reconstruct past ownership. That stronger check is
    reserved for the independent replay of the39 saved full representative traces.
    """
    attempts = game.evaluation_attempts
    assert len(attempts)==81
    assert {(a['round'],a['country']) for a in attempts}=={(r,n) for r in range(1,10) for n in game.cs}
    assert len(game.evaluation_index)==81
    expected_rows = {m:[] for m in SCORING_MODES}
    for index,a in enumerate(attempts):
        assert game.evaluation_index[(a['round'],a['country'])]==index
        legal = bool(1<=a['round']<=7 and a['style'] not in ('idle','trade') and a['goal'] and
                     a['levels'].get(a['goal'],0)<4 and
                     (a['goal'] in a['levels'] or (a['goal']==a['expand'] and a['round']>=3)))
        assert a['legal']==legal
        assert a['cash_ok']==(a['cash']>=a['cash_cost']+a['reserve'])
        assert a['household_ok']==(a['food_met'] and a['living_free']>=a['living_needed'])
        assert a['raw_ok']==all(a['raw_free'].get(g,0)>=q for g,q in a['raw_required'].items())
        ready = bool(a['cached'] and legal and a['machine_min_gen'] and a['cash_ok'] and a['household_ok'] and a['raw_ok'])
        assert a['ready']==ready
        qualified = a['qualified_units']
        assert [u['uid'] for u in qualified]==a['qualified_ids']
        assert len(a['qualified_ids'])==len(set(a['qualified_ids']))
        assert [u['uid'] for u in qualified if u['order'] is None]==a['free_qualified_ids']
        assert [u['uid'] for u in qualified if u['origin']==a['country']]==a['own_qualified_ids']
        for u in qualified:
            physical = game.units[u['uid']]
            assert physical.good=='machine' and physical.gen==u['generation']>=a['machine_min_gen']
            assert physical.origin==u['origin']
            if u['import_transaction'] is not None:
                tx = game.transactions[u['import_transaction']]
                assert tx['round']<=a['round']
                assert any(leg['buyer']==a['country'] and u['uid'] in leg['ids'] for leg in tx['legs'])
        assert a['external']==int(bool(a['machine_min_gen']) and not a['own_qualified_ids'])
        machine = a['machine_used']
        assert a['fulfilled']==int(bool(a['external'] and machine and machine['origin']!=a['country'] and machine['import_transaction'] is not None))
        assert a['already_credited']==bool(a['fulfilled'] and machine['uid'] in a['prior_credited_equipment_ids'])
        if a['successful']:
            event = game.development_log[a['event_id']]
            assert (event['round'],event['country'],event['industry'],event['to_level'])==(a['round'],a['country'],a['goal'],a['target_level'])
            assert event['cash_cost']==a['cash_cost']
            assert event['machine']==machine
        else:assert a['event_id'] is None and machine is None
        if machine:
            assert ready and machine['uid'] in a['free_qualified_ids']
        elif ready:assert not a['free_qualified_ids']
        for uid in a['prior_credited_equipment_ids']:
            assert any(row['round']==a['round'] and row['country']==a['country'] and row['good']=='machine' and
                       row['purpose'].startswith('equipment:') and row['fulfilled'] and uid in row['used_ids']
                       for row in game.needs_ledger)
        for mode in SCORING_MODES[1:]:
            include = bool(a['machine_min_gen'] and (a['successful'] if mode=='success_only' else ready))
            if mode=='ready_once' and a['already_credited']:include=False
            if include:
                expected_rows[mode].append({'round':a['round'],'country':a['country'],'good':'machine',
                    'purpose':'development','needed':1,'external':a['external'],'fulfilled':a['fulfilled'],
                    'used_ids':[machine['uid']] if machine else [],'min_gen':a['machine_min_gen'],
                    'goal':a['goal'],'target_level':a['target_level'],'event_id':a['event_id']})
    for mode in SCORING_MODES:assert game.evaluation_rows(mode)==expected_rows[mode]
    for name,country in result['countries'].items():
        a = [r for r in attempts if r['country']==name and r['machine_min_gen']]
        diag = country['evaluation']
        assert diag['machine_attempts']==len(a)
        assert diag['ready_opportunities']==sum(r['ready'] for r in a)
        assert diag['successful_machine_uses']==sum(bool(r['machine_used']) for r in a)
        foreign = [r['machine_used'] for r in a if r['machine_used'] and r['machine_used']['origin']!=name and r['machine_used']['import_transaction'] is not None]
        assert diag['foreign_machine_uses']==len(foreign)
        assert diag['unique_foreign_development_machines']==len({u['uid'] for u in foreign})
        assert diag['ready_unfulfilled']==sum(r['ready'] and r['external'] and not r['fulfilled'] for r in a)
        for label in ('cash','household','raw'):assert diag['blocked_'+label]==sum(label in r['blockers'] for r in a)
        assert diag['existing_equipment_overlap']==sum(r['already_credited'] for r in a)
        if game.behaviors.get(name) in MINIMUM_BEHAVIORS:
            assert all(row['prices']==[game.opt.price_tick] for row in game.offer_history if row['country']==name)
            assert all(row['actual_prices']==[game.opt.price_tick] and row['recommendation']['price']==game.opt.price_tick
                       for row in game.advice_log if row['country']==name and row['kind']=='offer')
        for mode in SCORING_MODES:
            rows = [r for r in game.needs_ledger+expected_rows[mode] if r['country']==name]
            ext = sum(r['external'] for r in rows);filled = sum(r['fulfilled'] for r in rows)
            er = {r['round'] for r in rows if r['external']};fr = {r['round'] for r in rows if r['fulfilled']}
            score = diag['scores'][mode]
            assert (score['external_need'],score['external_fulfilled'],score['external_rounds'],score['fulfilled_rounds'])==(ext,filled,len(er),len(fr))
            imports = 8*filled/ext if ext else 0;effects = 4*len(fr)/len(er) if er else 0
            expected = 9*min(1,country['export_help_rounds']/6)+4*min(1,country['useful_partners']/3)+imports+effects
            close(score['trade'],expected,(name,mode,'independent score'))
            close(score['imports_part'],imports,(name,mode,'import part'))
            close(score['effects_import_part'],effects,(name,mode,'effect part'))


def run_one(task):
    phase,seed,sid,focal,style,overrides = task
    game = Game(seed,focal=focal,style='normal' if style=='no_trade' else style,
                trade_enabled=style!='no_trade',behaviors=dict(overrides))
    result = normalize_and_validate(game.run())
    for key in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
        assert result['world'][key]==0,(seed,sid,key)
    for name,behavior in game.behaviors.items():
        actor = result['countries'][name]
        if behavior=='idle':assert actor['imports']==actor['exports']==actor['investment']==actor['routing']['routes_started']==0
        if behavior=='minimum_passive':assert actor['investment']==actor['routing']['routes_started']==0
    if style=='no_trade':assert result['world']['transactions']==0
    if style=='no_raw':
        actor = result['countries'][focal]
        for good in ('ore','fuel'):assert actor['import_goods'][good]==actor['purchase_by_good'][good]==actor['raw_use'][good]['imported_used']==0
    if style=='no_high_machine':
        assert all(not(leg['buyer']==focal and any(game.units[i].good=='machine' and game.units[i].gen>=2 for i in leg['ids']))
                   for tx in game.transactions for leg in tx['legs'])
    validate_raw_ledger(game,result)
    validate_development_records(game,result)
    validate_routing_records(game,result)
    validate_evaluation_records(game,result)
    identity = {'phase':phase,'mode':'market_first','scenario':sid,'seed':seed,'focal':focal,'style':style,
                'behaviors':dict(game.behaviors)}
    record = {**identity,**result}
    cash = {**identity,'rows':game.cash_ledger} if phase=='main' else None
    raw = {**identity,'rows':game.raw_round_ledger} if phase=='main' else None
    trace = {**game.trace(),**identity} if representative(task) else None
    return record,cash,raw,trace


def summarize(rows,metadata):
    groups = defaultdict(list)
    for row in rows:groups[(row['phase'],row['scenario'])].append(row)
    experiments = {f'{phase}:market_first:{sid}':grouped(group) for (phase,sid),group in groups.items()}
    pairs = {}
    for phase,conditions in (('main',MAIN_SCENARIOS),('stress',STRESS_SCENARIOS)):
        control = groups[(phase,'None:normal')]
        for sid,focal,style,overrides in conditions:
            if sid=='None:normal':continue
            pairs[f'{phase}:market_first:{sid}'] = pair(control,groups[(phase,sid)],focal)
    for name in NAMES:
        pairs[f'main:market_first:{name}:cheap->minimum'] = pair(
            groups[('main',f'{name}:cheap')],groups[('main',f'{name}:minimum')],name)
    for name in ('Technia','Novia'):
        sid = f'Mechania:idle+{name}:minimum'
        pairs[f'stress:market_first:Mechania:idle->{sid}'] = pair(
            groups[('stress','Mechania:idle')],groups[('stress',sid)],name)
    return {'metadata':metadata,'experiments':experiments,'paired':pairs}


def run_tests(output):
    before = hashes(SOURCE_FILES);test_hashes = hashes(TEST_FILES);started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromNames([Path(n).stem for n in TEST_FILES])
    with (output/'tests.log').open('w') as stream:
        result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    manifest = {'passed':result.wasSuccessful(),'test_count':result.testsRun,'inherited_tests':INHERITED_TESTS,
        'new_tests':result.testsRun-INHERITED_TESTS,'failures':len(result.failures),'errors':len(result.errors),
        'skipped':len(result.skipped),'elapsed_seconds':time.monotonic()-started,
        'test_sha256':test_hashes,'economic_source_sha256':hashes(ECONOMIC_FILES),'validation_source_sha256':before,
        'source_unchanged':before==hashes(SOURCE_FILES),'tests_unchanged':test_hashes==hashes(TEST_FILES)}
    (output/'tests_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    assert manifest['passed'] and manifest['test_count']>INHERITED_TESTS and not manifest['skipped'],manifest
    assert manifest['source_unchanged'] and manifest['tests_unchanged']
    print(f'TESTS {manifest["test_count"]} passed, {manifest["elapsed_seconds"]:.2f}s',flush=True)
    return manifest


def verified_test_manifest(output):
    path = output/'tests_manifest.json'
    if not path.exists():return run_tests(output)
    manifest = json.loads(path.read_text())
    assert manifest['passed'] and manifest['test_count']>INHERITED_TESTS and manifest['inherited_tests']==INHERITED_TESTS
    assert manifest['failures']==manifest['errors']==manifest['skipped']==0
    assert manifest['test_sha256']==hashes(TEST_FILES),'tests changed after recorded verification'
    assert manifest['economic_source_sha256']==hashes(ECONOMIC_FILES),'economic code changed after recorded verification'
    assert manifest['validation_source_sha256']==hashes(SOURCE_FILES),'runner changed after recorded verification'
    assert manifest['source_unchanged'] and manifest['tests_unchanged']
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--n',type=int,default=200);parser.add_argument('--stress-n',type=int,default=30)
    parser.add_argument('--workers',type=int,default=4);parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--dry-run',action='store_true');parser.add_argument('--tests-only',action='store_true')
    args = parser.parse_args()
    if not 2<=args.n<=2000 or not 2<=args.stress_n<=2000:parser.error('use2..2000 seeds without overlapping seed bands')
    if args.workers<1:parser.error('workers must be positive')
    tasks = build_tasks(args.n,args.stress_n)
    main_games = len(MAIN_SCENARIOS)*args.n
    if args.dry_run:
        print(json.dumps({'planned_games':len(tasks),'main_games':main_games,'stress_games':len(tasks)-main_games,
            'main_seed_range':[MAIN_START,MAIN_START+args.n-1],'stress_seed_range':[STRESS_START,STRESS_START+args.stress_n-1],
            'main_scenarios':scenario_manifest(MAIN_SCENARIOS),'stress_scenarios':scenario_manifest(STRESS_SCENARIOS),
            'scoring_views_per_trajectory':len(SCORING_MODES),'representative_traces':sum(representative(t) for t in tasks),
            'main_ledger_rows':main_games*81,'executed_games':0}));return
    output = args.output_dir.resolve();output.mkdir(parents=True,exist_ok=True)
    for name in ('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz','runs.partial.jsonl.gz',
                 'round_ledgers.jsonl.gz','round_ledgers.partial.jsonl.gz','raw_round_ledgers.jsonl.gz',
                 'raw_round_ledgers.partial.jsonl.gz','first_seed_traces.json.gz'):
        if (output/name).exists():raise FileExistsError(f'Preserve validation output; choose a new output directory: {output/name}')
    if args.tests_only:run_tests(output);return
    tests = verified_test_manifest(output)
    sources = hashes(SOURCE_FILES);test_hashes = hashes(TEST_FILES)
    config = {
        'main_seed_range':[MAIN_START,MAIN_START+args.n-1],'stress_seed_range':[STRESS_START,STRESS_START+args.stress_n-1],
        'excluded_pilot_range':PILOT_RANGE,'excluded_test_seed_band':TEST_RANGE,'planned_games':len(tasks),
        'main_scenarios':scenario_manifest(MAIN_SCENARIOS),'stress_scenarios':scenario_manifest(STRESS_SCENARIOS),
        'scoring_modes':list(SCORING_MODES),'scoring_views_per_trajectory':len(SCORING_MODES),
        'economic_variants':['market_first'],'baseline_reference':'frozen v10 routing_engine.Game(market_first)',
        'routing_policy':asdict(ROUTING_MODES['market_first']),'options':asdict(BASE_OPTIONS),
        'original_countries':CONFIG,'new_countries':ADDITIONS,'rounds':9,'countries':9,
        'main_ledger_rows_planned':main_games*81,'representative_traces_planned':sum(representative(t) for t in tasks),
        'source_sha256':sources,'source_sha256_before':sources,'test_sha256_before':test_hashes,
        'tests_manifest_sha256':hashlib.sha256((output/'tests_manifest.json').read_bytes()).hexdigest(),
        'tests_completed':tests['test_count'],'inherited_tests':INHERITED_TESTS,
        'ledger_identity_fields':list(IDENTITY_FIELDS),'unique_trajectory_identity_fields':['phase','scenario','seed'],
        'main_normal_control_reused':True,'shadow_views_are_extra_games':False,
        'primary_endpoints':['public1G vs half-reference and normal: focal/other-country cash, welfare, actual trade and development',
            'legacy score ranking compared with frozen-trajectory development-machine coverage views',
            'ready failed needs, actual foreign equipment use, same-round credit overlap and reusable physical IDs',
            'Mechania idle with Technia/Novia minimum selling: actual G3 output/use and unfinished development'],
        'limitations':['serial automatic agents, not classroom pacing, observed learning or multiplayer validation',
            'minimum changes public asks only; normal direct negotiation and barter valuation remain active',
            'minimum keeps normal buying/investing; minimum_passive additionally disables voluntary investment',
            'idle keeps automatic production and satisfaction-based income while voluntary trade/investment stops',
            'shadow score views do not change original score fields or influence any action',
            'development-machine need counts only a frozen plan passing non-machine AI guards',
            'ready_once removes an added need only when the actual foreign UID already earned same-round equipment credit',
            'one 200-seed normal control is reused across18 main comparisons, not counted six times',
            'four score views are calculations on4,400 trajectories, not17,600 independent simulations',
            'original-six economic/industry targets remain uncalibrated for nine-country worlds; added-three total staysNone',
            'seed confidence intervals describe model variation, not a student population estimate'],
    }
    (output/'pre_run_plan.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    started = time.monotonic();rows = [];traces = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool, \
         gzip.open(output/'runs.partial.jsonl.gz','wt') as runs, \
         gzip.open(output/'round_ledgers.partial.jsonl.gz','wt') as cash_file, \
         gzip.open(output/'raw_round_ledgers.partial.jsonl.gz','wt') as raw_file:
        for index,(record,cash,raw,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
            rows.append(record);runs.write(json.dumps(record,ensure_ascii=False)+'\n')
            if cash is not None:cash_file.write(json.dumps(cash,ensure_ascii=False)+'\n')
            if raw is not None:raw_file.write(json.dumps(raw,ensure_ascii=False)+'\n')
            if trace is not None:traces[trace_key(record)] = trace
            if index%200==0:print(f'{index}/{len(tasks)} trajectories complete; {time.monotonic()-started:.1f}s',flush=True)
    assert len(rows)==len(tasks)==len({(r['phase'],r['scenario'],r['seed']) for r in rows})
    assert sources==hashes(SOURCE_FILES) and test_hashes==hashes(TEST_FILES),'source/tests changed during formal run'
    expected_traces = {f'{phase}:market_first:{sid}:{seed}' for phase,seed,sid,focal,style,overrides in tasks if representative((phase,seed,sid,focal,style,overrides))}
    assert set(traces)==expected_traces
    metadata = {**config,'source_sha256_after':hashes(SOURCE_FILES),'test_sha256_after':hashes(TEST_FILES),'source_unchanged':True,
        'completed_games':len(rows),'main_games':main_games,'stress_games':len(rows)-main_games,
        'verification_calls':sum(r['world']['verify_calls'] for r in rows),'verification_failures':0,
        'elapsed_seconds':time.monotonic()-started,'pilot_excluded':True,'trace_and_unit_test_games_excluded':True,
        'main_cash_ledger_rows':main_games*81,'main_raw_ledger_rows':main_games*81,'representative_traces':len(traces)}
    summary = summarize(rows,metadata)
    for name in ('runs','round_ledgers','raw_round_ledgers'):
        (output/f'{name}.partial.jsonl.gz').replace(output/f'{name}.jsonl.gz')
    with gzip.open(output/'first_seed_traces.json.gz','wt') as stream:json.dump(traces,stream,ensure_ascii=False)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    (output/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(f'DONE {len(rows)} unique trajectories, {metadata["verification_calls"]} invariant calls, {metadata["elapsed_seconds"]:.2f}s',flush=True)


if __name__=='__main__':
    main()
