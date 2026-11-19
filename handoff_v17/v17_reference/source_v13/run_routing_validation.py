"""v10 frozen AI-routing validation; importing runs no games or tests.

Primary: each mode x normal / Mechania-idle x 200 paired seeds68000..68199.
Stress: each mode x20 conditions x30 paired seeds70000..70029.
With four modes this is1600+2400=4000 formal games. Pilot64000..64029
and test66100..66199 are separate. Primary identities include focal/style.
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

from routing_engine import Game, MODES, ROUTING_METRICS
from development_engine import MODES as DEVELOPMENT_MODES, MACHINE_REFUSALS
from raw_engine import RAW_MODES, REFUSAL_STYLES
from run_development_validation import normalize_and_validate as normalize_development, validate_development_records
from run_raw_validation import validate_raw_ledger, grouped, pair
from expansion_engine import BASE_OPTIONS, ADDITIONS, CONFIG, NAMES
from machinery_engine import MODES as PHYSICAL_MODES
from budget_engine import POLICIES

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'routing_results'
ECONOMIC_FILES=('reference_engine.py','core_engine.py','engine.py','expansion_engine.py',
 'budget_engine.py','budget_trace.py','machinery_engine.py','recommendation_engine.py',
 'raw_engine.py','development_engine.py','routing_engine.py')
SOURCE_FILES=ECONOMIC_FILES+('run_raw_validation.py','run_development_validation.py','run_routing_validation.py')
TEST_FILES=('test_previous.py','test_fixes.py','test_costs.py','test_expansion.py','test_budget.py',
 'test_machinery.py','test_recommendation.py','test_raw_resources.py','test_development.py','test_routing.py')
MAIN_SCENARIOS=((None,'normal'),('Mechania','idle'))
STRESS_SCENARIOS=tuple((n,s) for n in NAMES for s in ('cheap','idle'))+((None,'normal'),(None,'no_trade'))+(
 ('Technia','no_high_machine'),('Novia','no_high_machine'),('Mechania','no_high_machine'),
 ('Technia','no_raw'),('Mechania','no_raw'),('Novia','no_raw'))
MAIN_START=68000
STRESS_START=70000
REFUSAL_STYLES_ALL=set(REFUSAL_STYLES)|set(MACHINE_REFUSALS)
MAIN_PAIRS=tuple(('baseline',m) for m in MODES if m!='baseline')+tuple(('patient',m) for m in MODES if m not in ('baseline','patient','quick'))
STRESS_PAIRS=tuple(('baseline',m) for m in MODES if m!='baseline')
WORLD_ROUTING_KEYS=tuple(k for k in ROUTING_METRICS if not k.startswith('first_'))+('both_electronics_produced','both_electronics_used')


def hashes(files):return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}


def build_tasks(n=200,stress_n=30):
 tasks=[('main',mode,seed,focal,style) for mode in MODES for focal,style in MAIN_SCENARIOS for seed in range(MAIN_START,MAIN_START+n)]
 tasks += [('stress',mode,seed,focal,style) for mode in MODES for focal,style in STRESS_SCENARIOS for seed in range(STRESS_START,STRESS_START+stress_n)]
 assert len(tasks)==len(set(tasks))
 return tasks


def representative(task):
 phase,mode,seed,focal,style=task
 return (phase=='main' and seed==MAIN_START) or (phase=='stress' and seed==STRESS_START and style in REFUSAL_STYLES_ALL)


def trace_key(record):return ':'.join(str(record[k]) for k in ('phase','mode','seed','focal','style'))


def normalize_and_validate(result):
 result=normalize_development(result);world=result['world']
 assert world['development_variant']=='combined'
 assert world['development_policy']==asdict(DEVELOPMENT_MODES['combined'])
 assert world['routing_variant'] in MODES
 assert world['routing_policy']==asdict(MODES[world['routing_variant']])
 for name,x in result['countries'].items():
  r=x['routing']
  assert set(r)==set(ROUTING_METRICS),(name,'routing schema')
  for key,value in r.items():assert type(value) is int and value>=0,(name,key,value)
  assert r['routes_started']==r['routes_completed']+r['routes_unfinished']
  assert r['routes_with_used_goal_output']<=r['routes_completed']
  assert r['routes_with_own_machine_goal']+r['routes_with_foreign_machine_goal']==r['routes_completed']
  assert r['intermediate_investments']<=r['alternate_plan_rounds']
  assert r['supplier_focus_rounds']<=r['intermediate_investments']
  assert r['unfinished_intermediate_spend']<=r['intermediate_spend']<=x['investment']
  for key in ('g3_electronics_produced','g3_electronics_used','high_machine_producer'):assert r[key] in (0,1)
  assert r['g3_electronics_used']<=r['g3_electronics_produced']<=x['electronics_g3']
  assert bool(r['g3_electronics_produced'])==bool(x['development']['g3_electronics_output'])
  assert bool(r['g3_electronics_used'])==bool(x['development']['g3_electronics_used'])
  assert bool(r['high_machine_producer'])==bool(x['development']['high_machine_produced'])
  for key,flag in (('first_g3_electronics_production_round','g3_electronics_produced'),('first_g3_electronics_use_round','g3_electronics_used')):
   assert 1<=r[key]<=10
   assert (r[key]==10)==(r[flag]==0)
  assert r['first_g3_electronics_production_round']<=r['first_g3_electronics_use_round']
 assert set(world['routing'])==set(WORLD_ROUTING_KEYS)
 for key in WORLD_ROUTING_KEYS:
  if key.startswith('both_'):continue
  assert world['routing'][key]==sum(x['routing'][key] for x in result['countries'].values()),('routing world sum',key)
 for key,field in (('both_electronics_produced','g3_electronics_produced'),('both_electronics_used','g3_electronics_used')):
  assert world['routing'][key]==int(all(result['countries'][n]['routing'][field] for n in ('Technia','Novia')))
 return result


def validate_routing_records(game,result):
 """Reconcile recorded decisions, permitted route steps and actual use paths.

 Historical ownership/public exposure is independently reconstructed from the
 persisted representative traces by the separate audit; no current-state
 shortcut is used to claim every prior public offer still exists.
 """
 expected={(r,n) for r in range(1,10) for n in game.cs}
 assert len(game.routing_log)==81 and {(r['round'],r['country']) for r in game.routing_log}==expected
 assert not game.active_routes
 assert [r['route_id'] for r in game.route_records]==list(range(len(game.route_records)))
 chains={e['event_id']:e for e in game.development_chains()}
 routed_events=[];cancelled=set()
 for row in game.routing_log:
  key=(row['round'],row['country'])
  if key in game.plan_cache:assert row['selected']==game.plan_cache[key]
  if row['reason']=='baseline':continue
  assert all(r<row['round'] for r in row['prior_rounds']+row['failed_rounds']+row['public_history_rounds'])
  assert set(row['failed_rounds'])<=set(row['prior_rounds'])
  assert set(row['public_history_rounds'])<=set(row['prior_rounds'])
  for offer in row['public_offers']:
   assert offer['seller']!=row['country'] and offer['generation']>=row['machine_min_gen']
   assert type(offer['price']) is int and offer['price']>0
   assert offer['ids']
   for uid in offer['ids']:
    u=game.units[uid];assert u.good=='machine' and u.gen==offer['generation']
  for uid in row['own_qualified_machine_ids']:
   u=game.units[uid];assert u.good=='machine' and u.gen>=row['machine_min_gen']
  if row['reason'] in ('start_route','continue_route'):
   assert row['selected']=='machine' and row['own_machine_level']<2
   assert row['legal_machine_path'] and row['earliest_goal_round']<=7
   assert not row['own_qualified_machine_ids'] and not row['public_offer_ids']
  if row['reason']=='start_route':
   assert row['failed_rounds']==row['prior_rounds'] and not row['public_history_rounds']
  expected_launches=[dict(e) for e in game.launch_events if e['good']=='machine' and e['generation']>=(row['machine_min_gen'] or 1) and e['round']==row['round']]
  assert row['public_generation_launches']==expected_launches
  if row['reason']=='new_generation_market_chance':assert expected_launches and row['selected']==row['goal']
 focus_keys=[(e['round'],e['country']) for e in game.route_focus_log]
 assert len(focus_keys)==len(set(focus_keys))
 for focus in game.route_focus_log:
  event=game.development_log[focus['supporting_event_id']]
  route=game.route_records[focus['route_id']]
  assert focus['supporting_event_id'] in route['intermediate_event_ids']
  assert (event['round'],event['country'],event['industry'],event['to_level'])==(focus['round'],focus['country'],'machine',2)
  assert focus['selected_focus'] in focus['own_levels'] and focus['selected_focus'] not in ('machine','electronics')
  assert focus['actual_focus_quantity']<=focus['forecast_quantity']
 for action in game.route_actions:
  route=game.route_records[action['route_id']]
  assert action['country']==route['country']
  if action['status']=='redundant_cancelled':
   assert action['event_id'] is None and action['cash_cost']==0
   cancelled.add((action['round'],action['country']))
   continue
  event=game.development_log[action['event_id']]
  assert (event['round'],event['country'],event['industry'],event['cash_cost'])==(action['round'],action['country'],action['selected'],action['cash_cost'])
  assert event['round']>=route['start_round'] and event['round']<=7
  if action['status']=='intermediate_completed':
   assert event['industry']=='machine' and event['to_level']<=2
   assert event['event_id'] in route['intermediate_event_ids']
  else:
   assert action['status']=='goal_completed'
   assert route['goal_event_id']==event['event_id'] and route['status']=='completed'
  routed_events.append(event['event_id'])
 assert len(routed_events)==len(set(routed_events))
 assert cancelled==game.route_cancelled
 for route in game.route_records:
  assert route['status'] in ('completed','unfinished','already_satisfied')
  assert route['start_round']<=route['end_round']<=9
  own=game.cs[route['country']]
  if route['status']=='completed':
   event=game.development_log[route['goal_event_id']]
   assert event['industry']==route['goal'] and event['to_level']>=route['target_level']
   assert event['round']==route['end_round']<=7
   assert event['machine'] is not None
  levels=[game.development_log[eid]['to_level'] for eid in route['intermediate_event_ids']]
  assert levels==list(range(route['starting_machine_level']+1,route['starting_machine_level']+1+len(levels)))
  assert all(level<=2 for level in levels)
 for name,x in result['countries'].items():
  routes=[r for r in game.route_records if r['country']==name]
  completed=[r for r in routes if r['status']=='completed']
  intermediate=[game.development_log[i] for r in routes for i in r['intermediate_event_ids']]
  assert x['routing']['routes_started']==len(routes)
  assert x['routing']['routes_completed']==len(completed)
  assert x['routing']['intermediate_investments']==len(intermediate)
  assert x['routing']['intermediate_spend']==sum(e['cash_cost'] for e in intermediate)
  assert x['routing']['supplier_focus_rounds']==sum(e['country']==name for e in game.route_focus_log)
  assert x['routing']['routes_with_used_goal_output']==sum(bool(chains[r['goal_event_id']]['used_output_ids']) for r in completed)
  g3=[u for u in game.units.values() if u.origin==name and u.born>0 and u.good=='electronics' and u.gen==3]
  assert x['routing']['first_g3_electronics_production_round']==min((u.born for u in g3),default=10)
  assert x['routing']['first_g3_electronics_use_round']==min((u.use_round for u in g3 if u.used),default=10)


def run_one(task):
 phase,mode,seed,focal,style=task
 game=Game(seed,variant=mode,focal=focal,style='normal' if style=='no_trade' else style,trade_enabled=style!='no_trade')
 result=normalize_and_validate(game.run())
 assert result['world']['routing_variant']==mode
 for key in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations','uncovered_investments'):
  assert result['world'][key]==0,(mode,seed,focal,style,key)
 if style in REFUSAL_STYLES:
  actor=result['countries'][focal]
  for good in REFUSAL_STYLES[style]:assert actor['import_goods'][good]==actor['purchase_by_good'][good]==actor['raw_use'][good]['imported_used']==0
 if style in MACHINE_REFUSALS:
  grade=MACHINE_REFUSALS[style]
  assert all(not(leg['buyer']==focal and any(game.units[i].good=='machine' and game.units[i].gen>=grade for i in leg['ids'])) for tx in game.transactions for leg in tx['legs'])
 if style=='idle':
  a=result['countries'][focal];assert a['imports']==a['exports']==a['investment']==a['routing']['routes_started']==0
 if style=='no_trade':assert result['world']['transactions']==0
 validate_raw_ledger(game,result);validate_development_records(game,result);validate_routing_records(game,result)
 record={'phase':phase,'mode':mode,'seed':seed,'focal':focal,'style':style,**result}
 identity={k:record[k] for k in ('phase','mode','seed','focal','style')}
 cash={**identity,'rows':game.cash_ledger} if phase=='main' else None
 raw={**identity,'rows':game.raw_round_ledger} if phase=='main' else None
 trace={**game.trace(),**identity} if representative(task) else None
 return record,cash,raw,trace


def summarize(rows,metadata):
 groups=defaultdict(list)
 for r in rows:groups[(r['phase'],r['mode'],r['focal'],r['style'])].append(r)
 experiments={':'.join(map(str,key)):grouped(group) for key,group in groups.items()};pairs={}
 for a,b in MAIN_PAIRS:
  for focal,style in MAIN_SCENARIOS:
   pairs[f'main:{a}->{b}:{focal}:{style}']=pair(groups[('main',a,focal,style)],groups[('main',b,focal,style)],focal)
 for mode in MODES:
  pairs[f'main:{mode}:Mechania:idle']=pair(groups[('main',mode,None,'normal')],groups[('main',mode,'Mechania','idle')],'Mechania')
  control=groups[('stress',mode,None,'normal')]
  for focal,style in STRESS_SCENARIOS:
   if style=='normal':continue
   suffix='no_trade' if style=='no_trade' else f'{focal}:{style}'
   pairs[f'stress:{mode}:{suffix}']=pair(control,groups[('stress',mode,focal,style)],focal)
 # Limit between-policy stress summaries to the preferred-later candidate, not
 # every possible metric/pair combination. Raw runs retain all policies.
 if 'market_first' in MODES:
  for focal,style in STRESS_SCENARIOS:
   pairs[f'stress:baseline->market_first:{focal}:{style}']=pair(groups[('stress','baseline',focal,style)],groups[('stress','market_first',focal,style)],focal)
 return {'metadata':metadata,'experiments':experiments,'paired':pairs}


def run_tests(output):
 before=hashes(SOURCE_FILES);test_hashes=hashes(TEST_FILES);started=time.monotonic()
 suite=unittest.defaultTestLoader.loadTestsFromNames([Path(n).stem for n in TEST_FILES])
 with (output/'tests.log').open('w') as stream:res=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 m={'passed':res.wasSuccessful(),'test_count':res.testsRun,'inherited_tests':260,'new_tests':res.testsRun-260,
 'failures':len(res.failures),'errors':len(res.errors),'skipped':len(res.skipped),'elapsed_seconds':time.monotonic()-started,
 'test_sha256':test_hashes,'economic_source_sha256':hashes(ECONOMIC_FILES),'validation_source_sha256':before,
 'source_unchanged':before==hashes(SOURCE_FILES),'tests_unchanged':test_hashes==hashes(TEST_FILES)}
 (output/'tests_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 assert m['passed'] and m['test_count']>260 and not m['skipped'],m
 assert m['source_unchanged'] and m['tests_unchanged']
 print(f'TESTS {m["test_count"]} passed, {m["elapsed_seconds"]:.2f}s',flush=True)
 return m


def verified_test_manifest(output):
 p=output/'tests_manifest.json'
 if not p.exists():return run_tests(output)
 m=json.loads(p.read_text())
 assert m['passed'] and m['test_count']>260 and m['inherited_tests']==260
 assert m['failures']==m['errors']==m['skipped']==0
 assert m['test_sha256']==hashes(TEST_FILES),'tests changed after recorded verification'
 assert m['economic_source_sha256']==hashes(ECONOMIC_FILES),'economic code changed after recorded verification'
 assert m['validation_source_sha256']==hashes(SOURCE_FILES),'runner changed after recorded verification'
 assert m['source_unchanged'] and m['tests_unchanged']
 return m


def main():
 p=argparse.ArgumentParser();p.add_argument('--n',type=int,default=200);p.add_argument('--stress-n',type=int,default=30)
 p.add_argument('--workers',type=int,default=4);p.add_argument('--output-dir',type=Path,default=OUT)
 p.add_argument('--dry-run',action='store_true');p.add_argument('--tests-only',action='store_true');a=p.parse_args()
 if not 2<=a.n<=2000 or not 2<=a.stress_n<=2000:p.error('use2..2000 seeds without overlapping seed bands')
 if a.workers<1:p.error('workers must be positive')
 tasks=build_tasks(a.n,a.stress_n);main_games=len(MODES)*len(MAIN_SCENARIOS)*a.n
 if a.dry_run:
  print(json.dumps({'planned_games':len(tasks),'main_games':main_games,'stress_games':len(tasks)-main_games,
   'main_seed_range':[MAIN_START,MAIN_START+a.n-1],'stress_seed_range':[STRESS_START,STRESS_START+a.stress_n-1],
   'main_scenarios':MAIN_SCENARIOS,'representative_traces':sum(representative(t) for t in tasks),'executed_games':0}));return
 out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
 for name in ('pre_run_plan.json','run_manifest.json','summary.json','runs.jsonl.gz','runs.partial.jsonl.gz','round_ledgers.jsonl.gz',
  'round_ledgers.partial.jsonl.gz','raw_round_ledgers.jsonl.gz','raw_round_ledgers.partial.jsonl.gz','first_seed_traces.json.gz'):
  if (out/name).exists():raise FileExistsError(f'Preserve validation output; choose a new output directory: {out/name}')
 if a.tests_only:run_tests(out);return
 tests=verified_test_manifest(out);sources=hashes(SOURCE_FILES);test_hashes=hashes(TEST_FILES)
 config={'main_seed_range':[MAIN_START,MAIN_START+a.n-1],'stress_seed_range':[STRESS_START,STRESS_START+a.stress_n-1],
 'excluded_pilot_range':[64000,64029],'excluded_test_seed_band':[66100,66199],
 'planned_games':len(tasks),'modes':{n:asdict(v) for n,v in MODES.items()},'main_scenarios':MAIN_SCENARIOS,
 'stress_modes':tuple(MODES),'stress_scenarios':STRESS_SCENARIOS,
 'representative_trace_styles':sorted(REFUSAL_STYLES_ALL & {s for _,s in STRESS_SCENARIOS}),
 'raw_mode':'bridge','raw_policy':asdict(RAW_MODES['bridge']),'advice_mode':'price',
 'development_mode':'combined','development_policy':asdict(DEVELOPMENT_MODES['combined']),
 'baseline_reference':'v9 combined unchanged','physical_mode':'coupled','physical_policy':asdict(PHYSICAL_MODES['coupled']),
 'baseline_ai_policy':asdict(POLICIES['balanced']),'options':asdict(BASE_OPTIONS),
 'original_countries':CONFIG,'new_countries':ADDITIONS,'rounds':9,'countries':9,
 'main_ledger_rows_planned':main_games*81,'representative_traces_planned':sum(representative(t) for t in tasks),
 'source_sha256':sources,'source_sha256_before':sources,'test_sha256_before':test_hashes,
 'tests_manifest_sha256':hashlib.sha256((out/'tests_manifest.json').read_bytes()).hexdigest(),'tests_completed':tests['test_count'],
 'main_pairs':MAIN_PAIRS,'stress_mode_pairs':[('baseline','market_first')] if 'market_first' in MODES else [],
 'ledger_identity_fields':['phase','mode','seed','focal','style'],
 'primary_endpoints':['Technia and Novia actual G3 electronics production and use, individually and jointly',
  'original route goal completion and post-development actual use, not machine factory opening alone',
  'unfinished intermediate spending and earliest actual production/use timing',
  'normal-market high-machine trade, supplier sales, welfare and cash; no score-based fitting'],
 'normalization':'All v9 requirements retained; v10 routing metrics strict, first-round sentinel10 excluded from world sums.',
 'limitations':['serial automatic agents, not classroom or multiplayer validation',
  'new router uses own state, completed own failures and public offers/launches; inherited planner may use aggregate needs',
  'prices, investment permissions/costs, physical recipes, output limits and scores unchanged',
  'all-future route costs are not pre-funded; each actual step keeps living and operating-input guards',
  'public unaffordable offers count as supply presence; this stage does not solve high asking prices',
  'market_first combines a longer novice wait/public launch grace and a temporary legal focus choice; not isolated effects',
  'cheap means half-reference public prices with buying/investing still active',
  'idle forbids voluntary trade/investment but keeps automatic production and operating income',
  'completed development chains are chronological links, not incremental causal gains',
  'first-round value10 is no event within9rounds, not an observed tenth-round action',
  'seed confidence intervals are model variation only; not student population estimates']}
 (out/'pre_run_plan.json').write_text(json.dumps(config,ensure_ascii=False,indent=2));started=time.monotonic();rows=[];traces={}
 with ProcessPoolExecutor(max_workers=a.workers) as pool,gzip.open(out/'runs.partial.jsonl.gz','wt') as rf, \
 gzip.open(out/'round_ledgers.partial.jsonl.gz','wt') as cf,gzip.open(out/'raw_round_ledgers.partial.jsonl.gz','wt') as of:
  for i,(record,cash,raw,trace) in enumerate(pool.map(run_one,tasks,chunksize=4),1):
   rows.append(record);rf.write(json.dumps(record,ensure_ascii=False)+'\n')
   if cash is not None:cf.write(json.dumps(cash,ensure_ascii=False)+'\n')
   if raw is not None:of.write(json.dumps(raw,ensure_ascii=False)+'\n')
   if trace is not None:traces[trace_key(record)]=trace
   if i%200==0:print(f'{i}/{len(tasks)} games complete; {time.monotonic()-started:.1f}s',flush=True)
 assert len(rows)==len(tasks)==len({(r['phase'],r['mode'],r['seed'],r['focal'],r['style']) for r in rows})
 assert sources==hashes(SOURCE_FILES) and test_hashes==hashes(TEST_FILES),'source/tests changed during formal execution'
 assert set(traces)=={':'.join(map(str,t)) for t in tasks if representative(t)}
 metadata={**config,'source_sha256_after':hashes(SOURCE_FILES),'test_sha256_after':hashes(TEST_FILES),'source_unchanged':True,
 'completed_games':len(rows),'main_games':main_games,'stress_games':len(rows)-main_games,
 'verification_calls':sum(r['world']['verify_calls'] for r in rows),'verification_failures':0,
 'elapsed_seconds':time.monotonic()-started,'pilot_excluded':True,'trace_and_unit_test_games_excluded':True,
 'main_cash_ledger_rows':main_games*81,'main_raw_ledger_rows':main_games*81,'representative_traces':len(traces)}
 summary=summarize(rows,metadata)
 for n in ('runs','round_ledgers','raw_round_ledgers'):(out/f'{n}.partial.jsonl.gz').replace(out/f'{n}.jsonl.gz')
 with gzip.open(out/'first_seed_traces.json.gz','wt') as f:json.dump(traces,f,ensure_ascii=False)
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(out/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
 print(f'DONE {len(rows)} games, {metadata["verification_calls"]} invariant calls, {metadata["elapsed_seconds"]:.2f}s',flush=True)


if __name__=='__main__':main()
