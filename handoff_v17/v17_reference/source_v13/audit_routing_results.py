"""Independent v10 record audit; no economic engine is imported or executed.

Reuses frozen v9 cash/raw/price/development audits under its combined policy.
New decisions are reconstructed from own production levels, phase-correct
ownership, completed failed attempts and publicly exposed offers. Main cohort
identity includes focal/style so normal and Mechania-idle ledgers cannot alias.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from audit_development_results import Audit as DevelopmentAudit
from audit_machinery_results import read_json, read_lines, mode, identity
from audit_recommendation_results import stats

POLICIES={
    'baseline':{'wait_rounds':0,'expansion_wait_extra':0,'launch_grace':False,'supplier_focus':False},
    'quick':{'wait_rounds':1,'expansion_wait_extra':0,'launch_grace':False,'supplier_focus':False},
    'patient':{'wait_rounds':2,'expansion_wait_extra':0,'launch_grace':False,'supplier_focus':False},
    'market_first':{'wait_rounds':2,'expansion_wait_extra':1,'launch_grace':True,'supplier_focus':True},
}
EXPAND={'Tropia':'ore','Grainia':'machine','Oilia':'banana','Mechania':'electronics',
        'Mineria':'machine','Technia':'wheat','Novia':'machine','Agrea':'ore','Ferria':'machine'}
REFUSALS=('no_high_machine','no_machine','no_raw','no_ore','no_fuel')
METRICS=(
    'routes_started','routes_completed','routes_unfinished','routes_with_used_goal_output',
    'routes_with_own_machine_goal','routes_with_foreign_machine_goal','intermediate_investments',
    'intermediate_spend','unfinished_intermediate_spend','alternate_plan_rounds','wait_output_rounds',
    'market_resume_rounds','owned_resume_rounds','horizon_block_rounds','redundant_investments_cancelled',
    'market_launch_wait_rounds','supplier_focus_rounds',
    'g3_electronics_produced','g3_electronics_used','first_g3_electronics_production_round',
    'first_g3_electronics_use_round','high_machine_producer',
)
SUMMED=tuple(k for k in METRICS if not k.startswith('first_'))


def grade_required(levels,goal):
    if not goal:return 0
    old=levels.get(goal,0)
    return 2 if old>=3 or (goal in ('machine','electronics') and old==2) else 0


class Audit(DevelopmentAudit):
    def __init__(self):
        super().__init__()
        self.route_examples=[]

    def run_summary(self,row):
        super().run_summary({**row,'mode':'combined'})
        ctx=identity(row)
        self.equal(row['world']['routing_policy'],POLICIES[mode(row)],'routing_policy_declaration',ctx)
        self.equal(row['world']['routing_variant'],mode(row),'routing_mode_identity',ctx)
        self.equal(row['world']['development_policy'],{'sale_buffer':True,'prior_machine':True},'frozen_v9_combined_rules',ctx)
        for name,country in row['countries'].items():
            k=(ctx,name);x=country['routing'];d=country['development']
            self.equal(set(x),set(METRICS),'routing_country_complete_schema',k)
            for field,value in x.items():
                self.check(type(value) is int and value>=0,'routing_nonnegative_integer',(k,field))
            self.equal(x['routes_started'],x['routes_completed']+x['routes_unfinished'],'routing_partition',k)
            self.equal(x['routes_with_own_machine_goal']+x['routes_with_foreign_machine_goal'],x['routes_completed'],
                       'completed_route_machine_origin_partition',k)
            for a,b in (('routes_with_used_goal_output','routes_completed'),('unfinished_intermediate_spend','intermediate_spend'),
                        ('g3_electronics_used','g3_electronics_produced'),('intermediate_investments','alternate_plan_rounds')):
                self.check(x[a]<=x[b],'routing_subset_bound',(k,a,b))
            self.equal(x['g3_electronics_produced'],int(d['g3_electronics_output']>0),'routing_actual_g3_production_indicator',k)
            self.equal(x['g3_electronics_used'],int(d['g3_electronics_used']>0),'routing_actual_g3_use_indicator',k)
            self.equal(x['high_machine_producer'],int(d['high_machine_produced']>0),'actual_high_machine_producer_indicator',k)
            for field,flag in (('first_g3_electronics_production_round','g3_electronics_produced'),
                               ('first_g3_electronics_use_round','g3_electronics_used')):
                self.check(1<=x[field]<=10,'routing_round_sentinel_range',(k,field))
                self.equal(x[field]==10,not bool(x[flag]),'routing_failed_event_sentinel',(k,field))
            self.check(x['first_g3_electronics_production_round']<=x['first_g3_electronics_use_round'],
                       'g3_use_not_before_birth',k)
            self.check(x['intermediate_spend']<=country['investment'],'route_spend_subset_of_real_investment',k)
            if mode(row)=='baseline':
                for field in METRICS[:17]:self.equal(x[field],0,'baseline_has_no_routing_intervention',(k,field))
            if name==row.get('focal') and row.get('style') in ('idle','trade'):
                self.equal(x['routes_started'],0,'disabled_actor_has_no_route',k)
        world=row['world']['routing']
        self.equal(set(world),set(SUMMED)|{'both_electronics_produced','both_electronics_used'},'routing_world_complete_schema',ctx)
        for field in SUMMED:
            self.equal(world[field],sum(c['routing'][field] for c in row['countries'].values()),'routing_world_sum',(ctx,field))
        for field,local in (('both_electronics_produced','g3_electronics_produced'),('both_electronics_used','g3_electronics_used')):
            self.equal(world[field],int(all(row['countries'][n]['routing'][local] for n in ('Technia','Novia'))),
                       'joint_actual_electronics_success',(ctx,field))

    def trace(self,trace,result,context):
        super().trace(trace,result,context)
        self.audit_routing_trace(trace,result,context)

    def audit_routing_trace(self,trace,result,context):
        decisions=trace['routing_decisions'];routes=trace['routing_routes'];actions=trace['routing_actions']
        events=trace['development'];chains={e['event_id']:e for e in trace['development_chains']}
        units={int(k):v for k,v in trace['units'].items()};txs=trace['transactions'];public=trace['public_offers']
        policy=POLICIES[mode(result)];wait=policy['wait_rounds']
        self.equal(trace['routing_policy'],policy,'trace_routing_policy',context)
        self.equal(len(decisions),len({(e['round'],e['country']) for e in decisions}),'routing_decision_once_per_country_round',context)
        by_decision={(e['round'],e['country']):e for e in decisions}
        self.equal(set(by_decision),{(r,n) for r in range(1,10) for n in result['countries']},'all_rounds_have_frozen_routing_decision',context)
        self.equal([r['route_id'] for r in routes],list(range(len(routes))),'routing_ids_contiguous',context)
        self.equal(len(actions),len({(e['round'],e['country']) for e in actions}),'routing_action_once_per_country_round',context)
        transfers=defaultdict(list)
        for idx,t in enumerate(txs):
            for leg in t['legs']:
                for uid in leg['ids']:transfers[uid].append((t['round'],idx,leg['seller'],leg['buyer']))
        levels=defaultdict(dict)
        for p in trace['production']:levels[(p['round'],p['country'])][p['industry']]=p['level']
        launches=[];world_generation=1
        for r in range(1,10):
            observed=max((u['gen'] for u in units.values() if u['good']=='machine' and u['born']<=r),default=1)
            if observed>world_generation:launches.append({'round':r,'good':'machine','generation':observed})
            world_generation=observed
        self.equal([e for e in trace['routing_public_launches'] if e['good']=='machine'],launches,
                   'public_machine_launch_announcements_from_actual_world_output',context)

        def owner(uid,r,after_trade=False):
            h=[t for t in transfers[uid] if t[0]<r or (after_trade and t[0]==r)]
            return h[-1][3] if h else units[uid]['origin']

        def owned_qualified(name,r,grade,after_trade=False):
            return {i for i,u in units.items() if u['born']<=r and u['good']=='machine' and u['gen']>=grade
                    and owner(i,r,after_trade)==name}

        active={};start_records=[]
        for r in range(1,10):
            current=[d for d in decisions if d['round']==r]
            for d in current:
                name=d['country'];ctx=(context,r,name)
                if not wait:
                    self.equal(d['reason'],'baseline','baseline_reason',ctx)
                    self.equal(d['selected'],d['base_plan'],'baseline_plan_is_unchanged',ctx)
                    self.equal(d['route_id'],None,'baseline_route_absent',ctx)
                    continue
                existing=active.get(name);route=routes[existing] if existing is not None else None
                goal=route['goal'] if route else d['base_plan']
                target=route['target_level'] if route else levels[(r,name)].get(goal,0)+1 if goal else 0
                own=levels[(r,name)];grade=grade_required(own,goal)
                held=owned_qualified(name,r,grade) if grade else set()
                effective_wait=wait+(policy['expansion_wait_extra'] if own.get('machine',0)==0 else 0)
                prior=list(range(r-effective_wait,r))
                failed=sorted({e['round'] for e in trace['development_attempts'] if e['country']==name and e['industry']==goal
                               and e['missing_machine'] and e['required_machine_grade']>=grade and e['round'] in prior})
                exposed=sorted({e['round'] for e in public if e['country']!=name and e['good']=='machine'
                                and e['generation']>=(grade or 1) and e['ids'] and e['round'] in prior})
                last_public=any(e['country']!=name and e['good']=='machine' and e['generation']>=(grade or 1)
                                and e['ids'] and e['round']==r-1 for e in public)
                # Yesterday's exposed IDs remain public only if no transaction
                # removed them after that snapshot, even when later returned.
                prior_public={i for e in public if e['country']!=name and e['good']=='machine'
                              and e['generation']>=(grade or 1) and e['round']==r-1 for i in e['ids']}
                live_public={i for i in prior_public if not any(t[0]==r-1 for t in transfers[i])}
                observed=[i for offer in d['public_offers'] for i in offer['ids']]
                self.equal(set(observed),live_public,'current_offers_from_prior_exposure_and_transfers',ctx)
                self.equal(len(observed),len(set(observed)),'current_public_uid_not_duplicated',ctx)
                self.equal(d['public_offer_ids'],sorted(o['oid'] for o in d['public_offers']),'public_order_ids_match_snapshots',ctx)
                self.equal(d['public_offer_prices'],[o['price'] for o in d['public_offers']],'public_prices_match_snapshots',ctx)
                for offer in d['public_offers']:
                    for uid in offer['ids']:
                        u=units[uid]
                        self.check(u['born']<r,'no_peek_at_rival_current_round_unlisted_production',(ctx,uid))
                        self.equal((u['good'],u['gen'],owner(uid,r)),('machine',offer['generation'],offer['seller']),
                                   'current_offer_has_actual_existing_owner_grade',(ctx,uid))
                        price_rows=[e for e in public if e['round']==r-1 and uid in e['ids']]
                        self.check(bool(price_rows) and offer['price'] in price_rows[-1]['prices'],
                                   'current_offer_price_matches_last_public_quote',(ctx,uid))
                actual_style=result.get('style','normal') if name==result.get('focal') else 'normal'
                if actual_style in REFUSALS:actual_style='normal'
                machine_level=own.get('machine',0);steps=max(0,2-machine_level)
                earliest=r+(steps if steps else int(not held))
                legal='machine' in own or (EXPAND[name]=='machine' and r>=3)
                new_launches=[e for e in launches if e['round']==r and e['generation']>=(grade or 1)]
                fields={'goal':goal,'target_level':target,'active_route':route is not None,'machine_min_gen':grade,
                        'own_levels':own,'own_expand':EXPAND[name],'own_style':actual_style,'own_machine_level':machine_level,
                        'prior_rounds':prior,'failed_rounds':failed,'public_history_rounds':exposed,
                        'last_round_public_supply':last_public,'remaining_machine_steps':steps,
                        'earliest_goal_round':earliest,'legal_machine_path':legal,
                        'effective_wait_rounds':effective_wait,'public_generation_launches':new_launches}
                for field,value in fields.items():self.equal(d[field],value,'routing_observation_reconstructed',(ctx,field))
                self.equal(set(d['own_qualified_machine_ids']),held,'own_qualified_including_listed_and_new_own_output',ctx)
                selected=goal;reason='original_goal'
                if actual_style in ('idle','trade') or r>=8:selected=None;reason='investment_disabled'
                elif not goal:selected=None;reason='no_goal'
                elif own.get(goal,0)>=target:selected=None;reason='goal_already_satisfied'
                elif not grade:reason='no_machine_condition'
                elif held:reason='owned_machine_ready'
                elif live_public or (route and last_public):reason='public_supply_present'
                elif policy['launch_grace'] and new_launches:reason='new_generation_market_chance'
                elif not route and (not prior or prior[0]<1 or set(failed)!=set(prior)):reason='waiting_for_completed_attempts'
                elif not route and exposed:reason='recent_public_supply'
                elif not legal:reason='no_legal_machine_path'
                elif earliest>7:reason='too_late_for_self_production'
                elif machine_level>=2:selected=None;reason='await_actual_machine'
                else:selected='machine';reason='continue_route' if route else 'start_route'
                if reason=='goal_already_satisfied' and route:selected=d['base_plan']
                self.equal(d['reason'],reason,'routing_reason_from_actual_evidence',ctx)
                self.equal(d['selected'],selected,'routing_choice_from_actual_evidence',ctx)
                if reason=='start_route':
                    expected_id=len(start_records);start_records.append(d)
                    self.equal(d['route_id'],expected_id,'new_route_matches_decision_order',ctx)
                    active[name]=expected_id
                    record=routes[expected_id]
                    self.equal((record['country'],record['goal'],record['target_level'],record['start_round'],record['starting_machine_level']),
                               (name,goal,target,r,machine_level),'route_start_record',ctx)
                else:
                    self.equal(d['route_id'],existing,'decision_reuses_only_active_route',ctx)
                if reason=='goal_already_satisfied' and route:active.pop(name,None)
            for event in events:
                if event['round']!=r:continue
                d=by_decision[(r,event['country'])]
                self.equal(event['industry'],d['selected'],'actual_investment_uses_frozen_selected_plan',(context,event['event_id']))
                rid=active.get(event['country'])
                if rid is not None:
                    record=routes[rid]
                    if event['industry']==record['goal'] and event['to_level']>=record['target_level']:
                        active.pop(event['country'],None)
            for attempt in trace['development_attempts']:
                if attempt['round']==r:
                    self.equal(attempt['industry'],by_decision[(r,attempt['country'])]['selected'],
                               'failed_attempt_keeps_frozen_plan',(context,r,attempt['country']))
        self.equal(len(start_records),len(routes),'all_routes_have_start_decision',context)
        expected_actions=[]
        for record in routes:
            rid=record['route_id'];name=record['country'];ctx=(context,rid)
            relevant=[e for e in events if e['country']==name and by_decision[(e['round'],name)]['route_id']==rid]
            goals=[e for e in relevant if e['industry']==record['goal'] and e['to_level']>=record['target_level']]
            self.check(len(goals)<=1,'route_goal_completed_once',ctx)
            intermediate=[e for e in relevant if e not in goals]
            for e in intermediate:
                self.check(e['industry']=='machine' and e['to_level']<=2,'intermediate_only_existing_machine_to_g2',(ctx,e['event_id']))
            self.equal(record['intermediate_event_ids'],[e['event_id'] for e in intermediate],'route_intermediate_events_reconstructed',ctx)
            satisfied=[d for d in decisions if d.get('route_id')==rid and d['reason']=='goal_already_satisfied']
            expected_status='completed' if goals else 'already_satisfied' if satisfied else 'unfinished'
            expected_end=goals[0]['round'] if goals else satisfied[0]['round'] if satisfied else 9
            self.equal((record['status'],record['end_round'],record['goal_event_id']),
                       (expected_status,expected_end,goals[0]['event_id'] if goals else None),'route_final_status_from_actual_events',ctx)
            for e in relevant:
                expected_actions.append({'round':e['round'],'country':name,'route_id':rid,'selected':e['industry'],
                    'status':'goal_completed' if e in goals else 'intermediate_completed','event_id':e['event_id'],'cash_cost':e['cash_cost']})
            if len(self.route_examples)<16:
                self.route_examples.append({'game':context,**record,'intermediate_spend':sum(e['cash_cost'] for e in intermediate),
                    'goal_output_units':len(chains[goals[0]['event_id']]['output_ids']) if goals else 0,
                    'used_goal_output_units':len(chains[goals[0]['event_id']]['used_output_ids']) if goals else 0})
        cancelled=[a for a in actions if a['status']=='redundant_cancelled']
        for a in cancelled:
            ctx=(context,a['round'],a['country']);d=by_decision[(a['round'],a['country'])];record=routes[a['route_id']]
            self.equal(a['selected'],'machine','cancel_only_intermediate_machine',ctx)
            self.equal(a['selected'],d['selected'],'cancel_does_not_change_frozen_plan',ctx)
            self.check(record['goal']!='machine' and d['own_machine_level']<2,'cancel_requires_redundant_intermediate',ctx)
            self.check(bool(owned_qualified(a['country'],a['round'],grade_required(d['own_levels'],record['goal']),True)),
                       'cancel_has_actually_acquired_qualified_machine',ctx)
            self.equal((a['cash_cost'],a['event_id']),(0,None),'cancel_spends_and_develops_nothing',ctx)
            self.check(not any(e['round']==a['round'] and e['country']==a['country'] for e in events),'cancel_no_same_round_replan_investment',ctx)
        expected_actions+=cancelled
        self.equal(sorted(actions,key=lambda e:(e['round'],e['country'])),sorted(expected_actions,key=lambda e:(e['round'],e['country'])),
                   'all_route_actions_match_real_development_or_cancel',context)

        focus_rows=trace['routing_focus']
        self.equal(len(focus_rows),len({(e['round'],e['country']) for e in focus_rows}),'supplier_focus_once_per_country_round',context)
        self.check(policy['supplier_focus'] or not focus_rows,'supplier_focus_only_declared_package',context)
        cash_rows={(e['round'],e['country']):e for e in trace['cash_ledger']}
        initial_price={'banana':10,'wheat':10,'fuel':30,'ore':20,'machine':50,'electronics':80}
        for f in focus_rows:
            r=f['round'];name=f['country'];ctx=(context,r,name);record=routes[f['route_id']]
            event=events[f['supporting_event_id']]
            self.equal((event['round'],event['country'],event['industry'],event['to_level']),(r,name,'machine',2),
                       'supplier_focus_after_actual_own_g2_technology_investment',ctx)
            self.check(event['event_id'] in record['intermediate_event_ids'],'focus_belongs_to_active_route_intermediate',ctx)
            self.check(record['start_round']<=r<record['end_round'],'focus_only_before_route_end',ctx)
            self.check(not owned_qualified(name,r,2,True),'supplier_focus_before_qualified_unit_owned',ctx)
            self.equal(f['own_levels'],cash_rows[(r,name)]['levels'],'focus_own_levels_match_actual_investment',ctx)
            choices=[g for g in f['own_levels'] if g not in ('machine','electronics')]
            self.check(bool(choices),'supplier_focus_existing_legal_non_durable_industry',ctx)
            self.check(f['previous_focus'] in f['own_levels'],'previous_focus_is_owned_industry',ctx)
            prices=initial_price if r==1 else trace['prices'][r-2]
            best=max(choices,key=lambda g:(max(1,math.floor(prices[g]+.5))*(2 if g in ('banana','wheat') else 1)
                                          /(1+.3*cash_rows[(r,name)]['stock'][g]),g))
            self.equal(f['selected_focus'],best,'supplier_focus_selected_from_own_stock_and_public_quote',ctx)
            self.equal(cash_rows[(r,name)]['next_focus'],best,'supplier_focus_applied_to_next_actual_cycle',ctx)
            self.equal((f['forecast_quantity'],f['actual_focus_quantity']),(2,2),'focus_uses_existing_two_unit_capacity_and_target',ctx)
            next_machine=[m for m in trace['machine_output'] if m['country']==name and m['round']==r+1]
            self.equal(len(next_machine),1,'supplier_focus_has_next_actual_factory_record',ctx)
            if next_machine:self.equal(next_machine[0]['planned'],2,'supplier_focus_next_planned_output_no_new_rule',ctx)

        for name,country in result['countries'].items():
            local=[e for e in routes if e['country']==name];completed=[e for e in local if e['status']=='completed']
            goals=[chains[e['goal_event_id']] for e in completed]
            middle=[eid for e in local for eid in e['intermediate_event_ids']]
            incomplete=[eid for e in local if e['status']!='completed' for eid in e['intermediate_event_ids']]
            choice=[d for d in decisions if d['country']==name]
            g3=[u for u in units.values() if u['origin']==name and u['born']>0 and u['good']=='electronics' and u['gen']==3]
            values={
                'routes_started':len(local),'routes_completed':len(completed),'routes_unfinished':len(local)-len(completed),
                'routes_with_used_goal_output':sum(bool(e['used_output_ids']) for e in goals),
                'routes_with_own_machine_goal':sum(bool(e['machine']) and e['machine']['origin']==name for e in goals),
                'routes_with_foreign_machine_goal':sum(e['foreign_machine'] for e in goals),
                'intermediate_investments':len(middle),'intermediate_spend':sum(events[i]['cash_cost'] for i in middle),
                'unfinished_intermediate_spend':sum(events[i]['cash_cost'] for i in incomplete),
                'alternate_plan_rounds':sum(d['reason'] in ('start_route','continue_route') for d in choice),
                'wait_output_rounds':sum(d['reason']=='await_actual_machine' for d in choice),
                'market_resume_rounds':sum(d.get('active_route',False) and d['reason']=='public_supply_present' for d in choice),
                'owned_resume_rounds':sum(d.get('active_route',False) and d['reason']=='owned_machine_ready' for d in choice),
                'horizon_block_rounds':sum(d['reason']=='too_late_for_self_production' for d in choice),
                'redundant_investments_cancelled':sum(a['country']==name for a in cancelled),
                'market_launch_wait_rounds':sum(d['reason']=='new_generation_market_chance' for d in choice),
                'supplier_focus_rounds':sum(f['country']==name for f in focus_rows),
                'g3_electronics_produced':int(bool(g3)),'g3_electronics_used':int(any(u['used'] for u in g3)),
                'first_g3_electronics_production_round':min((u['born'] for u in g3),default=10),
                'first_g3_electronics_use_round':min((u['use_round'] for u in g3 if u['used']),default=10),
                'high_machine_producer':int(any(u['origin']==name and u['born']>0 and u['good']=='machine' and u['gen']>=2 for u in units.values())),
            }
            self.equal(values,country['routing'],'all22_route_metrics_reconstructed',(context,name))
        self.counts['routing_decisions']+=len(decisions);self.counts['routing_routes']+=len(routes)
        self.counts['routing_actions']+=len(actions);self.counts['routing_cancelled_actions']+=len(cancelled)
        self.counts['supplier_focus_records']+=len(focus_rows)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path(__file__).parent/'routing_results')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();folder=args.results.resolve();folder.mkdir(exist_ok=True)
    audit=Audit();report={'scope':'Independent v10 saved-record audit; no game engine import or simulation.','warnings':[]}
    required=('runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','run_manifest.json')
    missing=[name for name in required if not (folder/name).exists()]
    if missing:report.update(status='pending_final_results',pending=missing)
    else:
        rows=read_lines(folder/'runs.jsonl.gz');keys=[identity(r) for r in rows];by_key={identity(r):r for r in rows}
        audit.equal(len(keys),len(set(keys)),'unique_full_game_identity')
        for row in rows:audit.run_summary(row)
        mains={identity(r):r for r in rows if r['phase']=='main'}
        for filename,method in (('round_ledgers.jsonl.gz',audit.ledger),('raw_round_ledgers.jsonl.gz',audit.raw_ledger)):
            groups=read_lines(folder/filename);ledger_keys=[identity(g) for g in groups]
            audit.equal(len(ledger_keys),len(set(ledger_keys)),'main_cohorts_never_alias',filename)
            audit.equal(set(ledger_keys),set(mains),'all_main_cohorts_have_ledger',filename)
            for group in groups:
                key=identity(group);method(group['rows'],mains[key],key)
        traced=[]
        for label,stored in read_json(folder/'first_seed_traces.json.gz').items():
            key=identity(stored);audit.check(key in by_key,'trace_matches_completed_game',(label,key))
            if key not in by_key:continue
            traced.append(key);audit.trace(stored.get('trace',stored),by_key[key],key)
        audit.equal(len(traced),len(set(traced)),'unique_representative_traces')
        manifest=read_json(folder/'run_manifest.json')
        for field in ('completed_games','planned_games'):audit.equal(len(rows),manifest[field],'manifest_game_count',field)
        a,b=manifest['main_seed_range'];c,d=manifest['stress_seed_range']
        main_scenarios=manifest['main_scenarios']
        expected={('main',m,s,f,st) for m in manifest['modes'] for s in range(a,b+1) for f,st in main_scenarios}
        expected|={('stress',m,s,f,st) for m in manifest['stress_modes'] for s in range(c,d+1) for f,st in manifest['stress_scenarios']}
        audit.equal(set(keys),expected,'complete_preregistered_multicohort_schedule')
        expected_traces={('main',m,a,f,st) for m in manifest['modes'] for f,st in main_scenarios}
        expected_traces|={('stress',m,c,f,st) for m in manifest['stress_modes'] for f,st in manifest['stress_scenarios'] if st in REFUSALS}
        audit.equal(set(traced),expected_traces,'complete_main_and_refusal_trace_schedule')
        audit.equal(len(traced),manifest['representative_traces_planned'],'trace_count_matches_plan')
        for filename,digest in manifest['source_sha256'].items():
            audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(),digest,'frozen_source_hash',filename)
        groups=defaultdict(list)
        for row in rows:groups[(row['phase'],mode(row),row.get('focal'),row['style'])].append(row)
        report.update(completed_runs=len(rows),groups={str(k):len(v) for k,v in groups.items()},
            route_examples=audit.route_examples,chain_examples=audit.chain_examples,legacy_score_coverage=dict(audit.score_coverage))
        report['routing_main_analysis']={str(k):{
            'n':len(rs),'world':{field:stats(r['world']['routing'][field] for r in rs) for field in rs[0]['world']['routing']},
            'countries':{n:{field:stats(r['countries'][n]['routing'][field] for r in rs) for field in METRICS} for n in rs[0]['countries']}}
            for k,rs in groups.items() if k[0]=='main'}
        report['method_notes']=[
            'All modes retain v9 combined physical/economic rules and original diagnostic scores.',
            'New routing decisions use actual own state and public offers; public offer absence is distinguished from unaffordable public supply.',
            'The inherited base planner retains its existing aggregate estimates; this audit does not claim the entire old AI avoids private aggregate inputs.',
            'Current public inventory is independently reconstructed from preceding public snapshots and actual removals by trades.',
            'Rival current-round production is not observable until public listing; own current-round output is observable.',
            'market_first also sees the existing world generation-launch announcement, independently reconstructed from first physical higher-grade births.',
            'market_first is a combined AI waiting/launch-grace/focus policy; its effect is not attributed solely to waiting time.',
            'One intermediate investment per round remains binding; actual output begins no earlier than the following round.',
            'The entire remaining route is not pre-funded. Earliest-goal round is a technical schedule, not a success guarantee.',
            'Unfinished intermediate spend is actual sunk development expenditure; it is not assumed to have zero residual industrial value.',
            'Failed first-production/use times use sentinel10 and are not conditional means among successful games.',
            'Same-seed model comparisons do not establish human learning or classroom pacing.',
            'legacy_score_coverage counts only saved representative traces and retains the known missing machine-development need row.',
            'Development-chain output is chronological whole-factory production after an upgrade, not incremental causal output.',
        ]
        report['audit_scope']={
            'summaries':'All formal games: inherited accounting, development and route metrics and bounds.',
            'ledgers':'Both main cohorts: separate full identities, cash/raw physical continuity.',
            'detailed_traces':'Saved representatives: inherited physical/price/development checks and independently reconstructed routing evidence, choices, lifecycle, lawful launch focus and22 metrics.',
            'not_claimed':['UID-level reconstruction for games without saved detailed traces.','Optimal AI decisions, equal country difficulty or observed educational effectiveness.',
                           'A route as guaranteed payback, guaranteed demand or incremental causal benefit.','Independent reconstruction of every inherited base-planner valuation.']}
        report['status']='failed' if audit.errors else 'passed'
    report.update(audit_counts=dict(audit.counts),checks_evaluated=audit.checks,errors=audit.errors)
    target=args.out or folder/'independent_audit.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:sorted(v,key=repr) if isinstance(v,set) else repr(v)),encoding='utf-8')
    print(json.dumps({'status':report['status'],'counts':report['audit_counts'],'checks':audit.checks,'errors':len(audit.errors),'report':str(target)},ensure_ascii=False))
    return int(bool(audit.errors))


if __name__=='__main__':raise SystemExit(main())
