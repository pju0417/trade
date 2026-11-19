"""Independent v11 audit of saved economics, legal public asks and score views.

No economic engine is imported or executed. Frozen v10/v9 audits are reused;
two copied audit methods have explicit behavior/1G-policy lookup adaptations.
Investment readiness and added scoring rows are independently reconstructed
from phase-correct unit ownership, consumption, cash and physical recipes.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_routing_results import Audit as RoutingAudit, POLICIES as ROUTING_POLICIES, EXPAND, grade_required
from audit_development_results import development_cost
from audit_machinery_results import read_json, read_lines, mode, identity, GOODS, ORIGINAL
from audit_recommendation_results import POLICIES as ADVICE_POLICIES, INITIAL_PRICE, MAIN_GOOD, half_up, stats

SCORE_MODES=('legacy','success_only','ready','ready_once')
MINIMUM=('minimum','minimum_passive')
DIAGNOSTICS=('machine_attempts','ready_opportunities','successful_machine_uses','foreign_machine_uses',
             'unique_foreign_development_machines','ready_unfulfilled','blocked_cash','blocked_household',
             'blocked_raw','existing_equipment_overlap','public_minimum_violations','cash_trade_balance')
VIEW_FIELDS=('trade','score','trade_delta','external_need','external_fulfilled','coverage','external_rounds',
             'fulfilled_rounds','added_needed','added_external','added_fulfilled','skipped_existing_credit',
             'imports_part','effects_import_part')
REFUSALS=('no_high_machine','no_machine','no_raw','no_ore','no_fuel')


def eval_identity(row):
    return row.get('phase','pilot'),row.get('scenario',str((row.get('focal'),row.get('style','normal')))),row.get('seed')


def behavior(row,name):
    return row['world']['evaluation_config']['behaviors'].get(name,'normal')


def effective_style(row,name):
    b=behavior(row,name)
    return {'minimum':'normal','minimum_passive':'trade',**{x:'normal' for x in REFUSALS}}.get(b,b)


def inherited_view(row):
    # v11 has one physical routing policy and arbitrary declared participation
    # behaviors; its scenario identifiers are not v10 policy mode names.
    focal=row.get('focal');style=row.get('style','normal')
    if focal is not None:style={'minimum':'normal','minimum_passive':'trade'}.get(behavior(row,focal),style)
    return {**row,'mode':'market_first','style':style}


class Audit(RoutingAudit):
    def __init__(self):
        super().__init__()
        self.evaluation_examples=[]

    def run_summary(self,row):
        super().run_summary(inherited_view(row))
        ctx=eval_identity(row);config=row['world']['evaluation_config']
        if 'behaviors' in row:self.equal(row['behaviors'],config['behaviors'],'identity_keeps_all_behavior_overrides',ctx)
        self.equal(config['legal_public_minimum'],1,'actual_legal_public_price_tick',ctx)
        self.equal(config['scoring_modes'],list(SCORE_MODES),'four_score_views_on_one_trajectory',ctx)
        for field in ('original_scores_unchanged','shadow_scores_do_not_affect_actions','public_prices_only'):
            self.equal(config[field],True,'declared_evaluation_scope',(ctx,field))
        for name,c in row['countries'].items():
            d=c['evaluation'];k=(ctx,name)
            self.equal(set(d),set(DIAGNOSTICS)|{'scores'},'evaluation_country_complete_schema',k)
            for f in DIAGNOSTICS:
                self.check(type(d[f]) is int and (f=='cash_trade_balance' or d[f]>=0),'evaluation_count_or_cash_balance_type',(k,f))
            self.equal(d['cash_trade_balance'],c['revenue']-c['purchases'],'cash_trade_balance_is_cash_not_barter_valuation',k)
            self.equal(d['public_minimum_violations'],0,'public_minimum_always_applied',k)
            self.equal(d['successful_machine_uses'],c['development']['machine_required_upgrades'],'observed_uses_match_development_events',k)
            self.equal(d['foreign_machine_uses'],c['development']['foreign_machine_upgrades'],'foreign_development_matches_old_trace_metric',k)
            self.equal(d['unique_foreign_development_machines'],c['development']['unique_foreign_machines_development'],'unique_development_machine_metric',k)
            for lower,upper in (('successful_machine_uses','ready_opportunities'),('ready_opportunities','machine_attempts'),
                                ('foreign_machine_uses','successful_machine_uses'),('existing_equipment_overlap','foreign_machine_uses'),
                                ('unique_foreign_development_machines','foreign_machine_uses')):
                self.check(d[lower]<=d[upper],'evaluation_subset_bound',(k,lower,upper))
            self.equal(set(d['scores']),set(SCORE_MODES),'all_score_views_present',k)
            for scoring,v in d['scores'].items():
                q=(k,scoring);self.equal(set(v),set(VIEW_FIELDS),'score_view_schema',q)
                self.check(0<=v['external_fulfilled']<=v['external_need'],'shadow_need_bound',q)
                self.check(0<=v['fulfilled_rounds']<=v['external_rounds']<=9,'shadow_round_bound',q)
                self.check(0<=v['added_fulfilled']<=v['added_external']<=v['added_needed'],'shadow_added_bound',q)
                self.equal(v['external_need'],c['external_need']+v['added_external'],'shadow_external_addition',q)
                self.equal(v['external_fulfilled'],c['external_fulfilled']+v['added_fulfilled'],'shadow_fulfilled_addition',q)
                coverage=v['external_fulfilled']/v['external_need'] if v['external_need'] else 0
                effects=4*v['fulfilled_rounds']/v['external_rounds'] if v['external_rounds'] else 0
                trade=9*min(1,c['export_help_rounds']/6)+4*min(1,c['useful_partners']/3)+8*coverage+effects
                self.equal(v['coverage'],coverage,'shadow_coverage_arithmetic',q)
                self.equal(v['imports_part'],8*coverage,'unchanged_eight_point_import_formula',q)
                self.equal(v['effects_import_part'],effects,'unchanged_four_point_round_formula',q)
                self.equal(v['trade'],trade,'unchanged_twentyfive_point_trade_formula',q)
                self.equal(v['trade_delta'],trade-c['trade'],'shadow_trade_delta',q)
                self.equal(v['score'],c['score']+trade-c['trade'] if name in ORIGINAL else None,'only_trade_component_changes_in_shadow',q)
                self.check(0<=v['trade']<=25+1e-9,'shadow_trade_maximum_unchanged',q)
                if scoring=='legacy':
                    self.equal(v['trade'],c['trade'],'legacy_evaluation_original_trade',q)
                    self.equal(v['score'],c['score'],'legacy_evaluation_original_total',q)
                    self.equal(v['added_needed'],0,'legacy_adds_no_need',q)
                elif scoring=='success_only':
                    self.equal(v['added_needed'],d['successful_machine_uses'],'success_only_row_count',q)
                    self.equal(v['added_external'],v['added_fulfilled'],'successful_external_need_really_fulfilled',q)
                elif scoring=='ready':
                    self.equal(v['added_needed'],d['ready_opportunities'],'ready_row_count',q)
                    self.equal(v['added_external']-v['added_fulfilled'],d['ready_unfulfilled'],'ready_missing_actual_service_count',q)
                else:
                    self.equal(v['added_needed'],d['ready_opportunities']-d['existing_equipment_overlap'],'ready_once_removes_only_credited_same_unit',q)
                    self.equal(v['skipped_existing_credit'],d['existing_equipment_overlap'],'same_unit_existing_credit_count',q)
            views=d['scores']
            self.check(views['success_only']['trade']+1e-9>=views['legacy']['trade'],'success_only_not_lower_than_legacy',k)
            self.check(views['ready_once']['trade']<=views['ready']['trade']+1e-9<=views['success_only']['trade']+2e-9,
                       'failed_needs_and_duplicate_removal_cannot_increase_score',k)
            if behavior(row,name) in ('idle','minimum_passive'):
                self.equal(c['investment'],0,'passive_actor_does_not_invest',k)
        for f in DIAGNOSTICS:self.equal(row['world']['evaluation'][f],sum(c['evaluation'][f] for c in row['countries'].values()),'evaluation_world_sum',(ctx,f))
        self.equal(row['world']['evaluation']['cash_trade_balance'],0,'international_cash_trade_balances_sum_to_zero',ctx)

    def trace(self,trace,result,context):
        super().trace(trace,inherited_view(result),context)
        self.audit_evaluation_trace(trace,result,context)

    def audit_evaluation_trace(self,trace,result,context):
        attempts=trace['evaluation_attempts'];units={int(k):v for k,v in trace['units'].items()}
        txs=trace['transactions'];events=trace['development'];needs=trace['needs_ledger']
        self.equal(trace['evaluation_behaviors'],result['world']['evaluation_config']['behaviors'],'trace_behavior_declaration',context)
        self.equal(trace['evaluation_legal_minimum'],1,'trace_legal_public_minimum',context)
        self.equal(len(attempts),len({(a['round'],a['country']) for a in attempts}),'one_evaluation_opportunity_per_country_round',context)
        self.equal({(a['round'],a['country']) for a in attempts},{(r,n) for r in range(1,10) for n in result['countries']},
                   'every_actual_investment_phase_observed',context)
        self.equal(sum(n['good']=='machine' and n['purpose']=='development' for n in needs),0,'shadow_does_not_mutate_physical_needs_ledger',context)
        cash={(r['round'],r['country']):r for r in trace['cash_ledger']}
        decisions={(d['round'],d['country']):d for d in trace['routing_decisions']}
        by_event={(e['round'],e['country']):e for e in events}
        levels=defaultdict(dict)
        for p in trace['production']:levels[(p['round'],p['country'])][p['industry']]=p['level']
        transfers=defaultdict(list)
        for idx,t in enumerate(txs):
            for leg in t['legs']:
                for uid in leg['ids']:transfers[uid].append((t['round'],idx,leg['seller'],leg['buyer']))
        exposed_by_round=defaultdict(set)
        for p in trace['public_offers']:exposed_by_round[p['round']].update(p['ids'])

        def last_transfer(uid,r):
            before=[x for x in transfers[uid] if x[0]<=r]
            return before[-1] if before else None

        def before_investment_ids(name,r,good=None,free=False,min_gen=1):
            held=[]
            for uid,u in units.items():
                if u['born']>r or (good and u['good']!=good) or u['gen']<min_gen:continue
                t=last_transfer(uid,r);owner=t[3] if t else u['origin']
                if owner!=name:continue
                if u['good'] not in ('machine','electronics') and u['use_round'] is not None:
                    if u['use_round']<r or (u['use_round']==r and u['use_purpose']!='development'):continue
                listed=uid in exposed_by_round[r] and not any(x[0]==r for x in transfers[uid])
                if free and listed:continue
                held.append(uid)
            return set(held)

        def projected_raw(name,r,own,goal):
            required=Counter()
            if r>=9:return required
            future=dict(own)
            if goal:future[goal]=future.get(goal,0)+1
            for good,lv in future.items():
                if good=='electronics':
                    required['ore' if (r+1)%2 else 'fuel']+=1+int(lv>=3)
                elif good=='machine':
                    gen=min(3,lv);raw='ore' if name=='Mechania' or (r+1)%2 else 'fuel'
                    history=range(max(1,r-1),r+1)
                    sold=sum(1 for tx in txs if tx['round'] in history for leg in tx['legs'] if leg['seller']==name
                             for uid in leg['ids'] if units[uid]['good']=='machine' and units[uid]['origin']==name and units[uid]['gen']==gen)
                    stock=len(before_investment_ids(name,r,'machine',min_gen=gen))
                    target=1+math.ceil(sold/max(1,len(history)))+int(gen>=2 and any(g not in ('machine','electronics') for g in future))
                    wanted=max(0,target-stock)
                    if not any(u['origin']==name and u['good']=='machine' and u['gen']==gen and 0<u['born']<=r for u in units.values()):wanted=max(1,wanted)
                    capacity=(2 if name=='Mechania' else 1)+lv-1+1
                    quantity=min(capacity,wanted)
                    work=max(0,quantity-1) if gen==1 else quantity*(1 if gen==2 else 2)
                    credit=[e['credits_after'] for e in trace['material_events'] if e['country']==name and e['raw']==raw
                            and e['generation']==gen and e['round']<=r]
                    batches=math.ceil(max(0,work-(credit[-1] if credit else 0))/2)
                    if batches:required[raw]+=batches
            return required

        independent=[]
        for a in attempts:
            r=a['round'];name=a['country'];ctx=(context,r,name);own=levels[(r,name)]
            goal=decisions[(r,name)]['selected'];lv=own.get(goal,0) if goal else 0;style=effective_style(result,name)
            legal=bool(1<=r<=7 and style not in ('idle','trade') and goal and lv<4
                       and (goal in own or (goal==EXPAND[name] and r>=3)))
            cost=development_cost(name,goal,lv) if goal else 0
            reserve=0 if style=='invest' else 2*(1+int(r>=5)+int(r>=8))*10+20
            grade=grade_required(own,goal)
            ore=((0 if lv<2 else 1 if lv==2 else 2)+int(goal in ('machine','electronics') and lv>=2)) if goal else 0
            required=projected_raw(name,r,own,goal) if goal else Counter();required['ore']+=ore
            raw={g:len(before_investment_ids(name,r,g,True)) for g in ('ore','fuel')}
            raw_ok=all(raw.get(g,0)>=q for g,q in required.items())
            current_cash=cash[(r,name)]['cash_start']+cash[(r,name)]['sales']-cash[(r,name)]['purchases']+cash[(r,name)]['operating_income']
            cash_ok=current_cash>=cost+reserve
            food_rows=[n for n in needs if n['round']==r and n['country']==name and n['purpose']=='food']
            food_met=len(food_rows)==2 and all(len(n['used_ids'])==n['needed'] for n in food_rows)
            living_needed=math.ceil((2+int(r>=5)+int(r>=8))/2)
            living_free=len(before_investment_ids(name,r,'electronics',True))
            household=style=='invest' or (food_met and living_free>=living_needed)
            qualified=before_investment_ids(name,r,'machine',min_gen=grade) if grade else set()
            free=before_investment_ids(name,r,'machine',True,grade) if grade else set()
            own_qualified={i for i in qualified if units[i]['origin']==name}
            credited=set()
            for n in needs:
                if (n['round'],n['country'],n['good'])!=(r,name,'machine') or not n['purpose'].startswith('equipment:') or not n['fulfilled']:continue
                candidates={i for i in n['used_ids'] if units[i]['origin']!=name and any(t[0]<r and t[3]==name for t in transfers[i])}
                self.equal(len(candidates),n['fulfilled'],'prior_equipment_credit_has_actual_import_at_equipment_time',ctx)
                credited.update(i for i in candidates if units[i]['gen']>=grade)
            blockers=[]
            if not legal:blockers.append('ineligible_goal')
            if not grade:blockers.append('no_machine_requirement')
            if not cash_ok:blockers.append('cash')
            if not household:blockers.append('household')
            if not raw_ok:blockers.append('raw')
            ready=bool(legal and grade and cash_ok and household and raw_ok)
            fields={'goal':goal,'target_level':lv+1 if goal else 0,'cached':True,'legal':legal,'style':style,
                'levels':own,'expand':EXPAND[name],'machine_min_gen':grade,'cash':current_cash,'cash_cost':cost,
                'reserve':reserve,'cash_ok':cash_ok,'food_met':food_met,'living_free':living_free,'living_needed':living_needed,
                'household_ok':household,'raw_free':raw,'research_ore':ore,'raw_ok':raw_ok,'ready':ready,'blockers':blockers}
            for field,value in fields.items():self.equal(a[field],value,'investment_readiness_reconstructed',(ctx,field))
            self.equal(Counter(a['raw_required']),required,'projected_operating_plus_research_raw_from_physical_state',ctx)
            for field,value in (('qualified_ids',qualified),('free_qualified_ids',free),('own_qualified_ids',own_qualified),
                                ('prior_credited_equipment_ids',credited)):
                self.equal(set(a[field]),value,'investment_qualified_or_credit_set_reconstructed',(ctx,field))
                self.equal(len(a[field]),len(set(a[field])),'snapshot_uid_list_unique',(ctx,field))
            self.equal([u['uid'] for u in a['qualified_units']],a['qualified_ids'],'qualified_snapshot_covers_exact_ids',ctx)
            for q in a['qualified_units']:
                uid=q['uid'];u=units[uid];last=last_transfer(uid,r)
                self.equal((q['origin'],q['generation'],q['import_transaction']),
                           (u['origin'],u['gen'],last[1] if last else None),'qualified_snapshot_phase_correct_provenance',(ctx,uid))
                self.equal(q['order'] is None,uid in free,'free_vs_listed_qualified_stock',(ctx,uid))
                if q['order'] is not None:self.check(type(q['order']) is int and q['order']>0,'listed_order_identifier_positive',(ctx,uid))
            event=by_event.get((r,name));machine=event['machine'] if event else None
            successful=event is not None;external=int(bool(grade) and not own_qualified)
            fulfilled=int(bool(machine) and external and machine['origin']!=name and machine['import_transaction'] is not None)
            overlap=bool(fulfilled and machine['uid'] in credited)
            actual={'successful':successful,'event_id':event['event_id'] if event else None,'machine_used':machine,
                    'external':external,'fulfilled':fulfilled,'already_credited':overlap}
            for field,value in actual.items():self.equal(a[field],value,'evaluation_outcome_from_real_event',(ctx,field))
            if ready and not successful:self.check(not free,'ready_failure_is_missing_free_machine_only',ctx)
            if machine:self.check(ready,'actual_machine_development_meets_nonmachine_guards',ctx)
            independent.append({**fields,**actual,'round':r,'country':name,'prior_credited_equipment_ids':sorted(credited)})
            if grade and len(self.evaluation_examples)<20:
                self.evaluation_examples.append({'game':context,'round':r,'country':name,'goal':goal,'ready':ready,
                    'successful':successful,'external':external,'fulfilled':fulfilled,'already_credited':overlap,'blockers':blockers})
        derived_rows={}
        for scoring in SCORE_MODES:
            extra=[]
            for a in independent:
                if scoring=='legacy' or not a['machine_min_gen']:continue
                if not (a['successful'] if scoring=='success_only' else a['ready']):continue
                if scoring=='ready_once' and a['already_credited']:continue
                extra.append({'round':a['round'],'country':a['country'],'good':'machine','purpose':'development','needed':1,
                    'external':a['external'],'fulfilled':a['fulfilled'],'used_ids':[a['machine_used']['uid']] if a['machine_used'] else [],
                    'min_gen':a['machine_min_gen'],'goal':a['goal'],'target_level':a['target_level'],'event_id':a['event_id']})
            derived_rows[scoring]=extra
            self.equal(trace['evaluation_rows'][scoring],extra,'shadow_rows_from_independent_ready_and_actual_use',(context,scoring))
            for name,c in result['countries'].items():
                added=[n for n in extra if n['country']==name];all_rows=[n for n in needs if n['country']==name]+added
                ext=sum(n['external'] for n in all_rows);filled=sum(n['fulfilled'] for n in all_rows)
                er={n['round'] for n in all_rows if n['external']};fr={n['round'] for n in all_rows if n['fulfilled']}
                imports=8*filled/ext if ext else 0;effects=4*len(fr)/len(er) if er else 0
                trade=9*min(1,c['export_help_rounds']/6)+4*min(1,c['useful_partners']/3)+imports+effects
                skip=sum(a['country']==name and a['ready'] and a['already_credited'] for a in independent) if scoring=='ready_once' else 0
                view={'trade':trade,'score':c['score']+trade-c['trade'] if name in ORIGINAL else None,'trade_delta':trade-c['trade'],
                    'external_need':ext,'external_fulfilled':filled,'coverage':filled/ext if ext else 0,'external_rounds':len(er),
                    'fulfilled_rounds':len(fr),'added_needed':len(added),'added_external':sum(n['external'] for n in added),
                    'added_fulfilled':sum(n['fulfilled'] for n in added),'skipped_existing_credit':skip,
                    'imports_part':imports,'effects_import_part':effects}
                reported=c['evaluation']['scores'][scoring]
                for field,value in view.items():self.equal(reported[field],value,'complete_shadow_score_from_reconstructed_ledger',(context,name,scoring,field))
        for name,c in result['countries'].items():
            selected=[a for a in independent if a['country']==name and a['machine_min_gen']]
            used=[a['machine_used'] for a in selected if a['machine_used']]
            foreign=[u for u in used if u['origin']!=name and u['import_transaction'] is not None]
            violations=sum(p['country']==name and behavior(result,name) in MINIMUM and p['prices']!=[1] for p in trace['public_offers'])
            derived={'machine_attempts':len(selected),'ready_opportunities':sum(a['ready'] for a in selected),
                'successful_machine_uses':len(used),'foreign_machine_uses':len(foreign),
                'unique_foreign_development_machines':len({u['uid'] for u in foreign}),
                'ready_unfulfilled':sum(a['ready'] and a['external'] and not a['fulfilled'] for a in selected),
                'blocked_cash':sum('cash' in a['blockers'] for a in selected),
                'blocked_household':sum('household' in a['blockers'] for a in selected),
                'blocked_raw':sum('raw' in a['blockers'] for a in selected),
                'existing_equipment_overlap':sum(a['already_credited'] for a in selected),
                'public_minimum_violations':violations,'cash_trade_balance':c['revenue']-c['purchases']}
            self.equal({k:c['evaluation'][k] for k in DIAGNOSTICS},derived,'all_evaluation_diagnostics_from_records',(context,name))
            for tx in txs:
                if tx['channel']!='market' or not tx['cash'] or tx['cash'][1]!=name or behavior(result,name) not in MINIMUM:continue
                self.equal(tx['cash'][2],len(tx['legs'][0]['ids']),'actual_minimum_public_market_payment_is_one_per_item',(context,name,tx['action_id']))
        self.counts['investment_readiness_snapshots']+=len(attempts)
        self.counts['shadow_development_rows_ready']+=len(derived_rows['ready'])
        self.counts['shadow_development_rows_ready_once']+=len(derived_rows['ready_once'])
        self.counts['duplicate_equipment_service_rows_removed']+=len(derived_rows['ready'])-len(derived_rows['ready_once'])

    # Frozen v7 audit, adapted only for declared behaviors and public 1G asks.
    def audit_recommendations(self, trace, result, context):
        """Re-derive decisions from stored past transactions and physical IDs.

        This is a record audit, not a second economic engine. It independently
        checks observation windows, own realized sales, public sell-through,
        prices, listing caps/selection, forecast arithmetic and candidate choice.
        Exact private-free rival snapshots and future operating requirements are
        not reconstructed from final logs; no optimality claim follows.
        """
        rows = trace['recommendations']
        public = trace['public_offers']
        plans = trace['listing_plans']
        recalls = trace['grade_recalls']
        units = {int(k):v for k,v in trace['units'].items()}
        countries = result['countries']
        prices_on, limited_on, planning_on = ADVICE_POLICIES[mode(result)]
        for name, value in (('recommendations', rows), ('public_offers', public),
                            ('listing_plans', plans), ('grade_recalls', recalls)):
            self.check(isinstance(value, list), 'trace_record_list', (context, name))
        production = {(p['round'], p['country'], p['industry']):p for p in trace['production']}
        ledgers = {(p['round'], p['country']):p for p in trace['cash_ledger']}
        offers = {}
        investments = {}
        focuses = {}
        plans_by_key = {}
        public_by_key = {}
        country_counts = defaultdict(Counter)
        own_sales_cache = {}
        owned_cache = {}

        def style(name):
            return effective_style(result, name)

        def own_sales(name, good, through, generation=None):
            key = (name, good, through, generation)
            if key in own_sales_cache:
                return own_sales_cache[key]
            start = max(1, through-1)
            sold = set(); buyers = set(); paid = []
            for tx in trace['transactions']:
                if not start <= tx['round'] <= through:
                    continue
                for leg in tx['legs']:
                    if leg['seller'] != name:
                        continue
                    ids = [uid for uid in leg['ids'] if units[uid]['good'] == good
                           and (generation is None or units[uid]['gen'] == generation)]
                    if ids:
                        sold.update(ids); buyers.add(leg['buyer'])
                        if tx['cash']:
                            paid.extend([tx['cash'][2]/len(leg['ids'])] * len(ids))
            answer = {'units':len(sold), 'buyers':len(buyers),
                      'rate':len(sold)/max(1, through-start+1),
                      'cash_price':statistics.median(paid) if paid else None}
            own_sales_cache[key] = answer
            return answer

        def owned_before_trade(round_number, name):
            key = (round_number, name)
            if key in owned_cache:
                return owned_cache[key]
            owners = {uid:u['origin'] for uid,u in units.items() if u['born'] <= round_number}
            for tx in trace['transactions']:
                if tx['round'] >= round_number:
                    continue
                for leg in tx['legs']:
                    for uid in leg['ids']:
                        owners[uid] = leg['buyer']
            for uid,u in units.items():
                if u['owner'] is None and u['use_round'] is not None:
                    already_consumed = u['use_round'] < round_number or (
                        u['use_round'] == round_number and u['use_purpose'] in ('production', 'maintenance'))
                    if already_consumed:
                        owners[uid] = None
            answer = {uid for uid,owner in owners.items() if owner == name}
            owned_cache[key] = answer
            return answer

        def quote(good, generation, round_number):
            base = INITIAL_PRICE[good] if round_number == 1 else trace['prices'][round_number-2][good]
            if good in ('machine', 'electronics'):
                global_gen = max(u['gen'] for u in units.values()
                                 if u['good'] == good and u['born'] <= round_number)
                base *= (1, 1.4, 1.8)[generation-1] * .75**max(0, global_gen-generation)
            return half_up(base)

        def common(row, kind):
            r, name = row['round'], row['country']
            self.check(type(r) is int and 1 <= r <= 9, 'recommendation_round', (context, kind, r))
            self.check(name in countries, 'recommendation_country', (context, kind, name))
            return r, name

        for p in public:
            r, name = common(p, 'public_offer')
            key = (r, name, p['good'], p['generation'])
            self.check(key not in public_by_key, 'public_offer_key_unique', (context, key))
            public_by_key[key] = p
            self.equal(len(p['ids']), len(set(p['ids'])), 'public_ids_unique', (context, key))
            country_counts[name]['public_offer_units'] += len(p['ids'])
        for p in plans:
            r, name = common(p, 'listing_plan')
            key = (r, name, p['good'])
            self.check(key not in plans_by_key, 'listing_plan_key_unique', (context, key))
            plans_by_key[key] = p
            self.equal(p['limited'], limited_on, 'listing_policy_flag', (context, key))
            self.equal(len(p['actual_ids']), len(set(p['actual_ids'])), 'live_listing_ids_unique', (context, key))
            self.equal(len(p['surplus_ids']), len(set(p['surplus_ids'])), 'surplus_ids_unique', (context, key))
            self.check(set(p['surplus_ids']) <= owned_before_trade(r, name), 'surplus_is_own_current_stock', (context, key))
            self.check(set(p['actual_ids']) <= owned_before_trade(r, name), 'listed_is_own_current_stock', (context, key))
            # surplus_ids is recorded before a cap cancels surplus listings;
            # protected_ids is taken afterward. Equal-grade newly free stock
            # may replace another protected UID without changing protection.
            reassigned = bool(set(p['surplus_ids']) & set(p['protected_ids']))
            self.check(not reassigned or p['limited'], 'only_capped_relisting_reassigns_protected_uid', (context, key))
            self.counts['post_cap_equal_grade_protection_reassignments'] += int(reassigned)
            overlap = bool(set(p['actual_ids']) & set(p['protected_ids']))
            country_counts[name]['protected_offer_violations'] += int(overlap and mode(result) != 'baseline')
            self.counts['baseline_reserved_uid_overlap_diagnostic'] += int(overlap and mode(result) == 'baseline')
            if mode(result) != 'baseline':
                self.check(not overlap, 'no_protected_uid_publicly_offered', (context, key))
            within = not p['limited'] or len(p['actual_ids']) == p['target']
            self.equal(p['within_plan'], within, 'within_plan_independently_recomputed', (context, key))
            country_counts[name]['listing_plan_violations'] += int(not within)
            if p['limited']:
                history = own_sales(name, p['good'], r-1)
                expected = min(len(p['surplus_ids']), 10, max(2, 1+math.ceil(2*history['rate'])))
                self.equal(p['target'], expected, 'listing_total_cap_from_own_past_sales', (context, key))
                chosen = []
                for generation in sorted({units[i]['gen'] for i in p['surplus_ids']}, reverse=True):
                    ids = sorted((i for i in p['surplus_ids'] if units[i]['gen'] == generation),
                                 key=lambda i:(units[i]['born'], i))
                    if ids and len(chosen) < expected:
                        chosen.append(ids[0])
                rest = sorted((i for i in p['surplus_ids'] if i not in chosen), key=lambda i:(units[i]['born'], i))
                chosen.extend(rest[:max(0, expected-len(chosen))])
                self.equal(set(p['actual_ids']), set(chosen), 'listing_generation_trial_then_oldest', (context, key))
            else:
                self.equal(p['target'], len(p['actual_ids']), 'unlimited_observed_quantity', (context, key))

        for row in rows:
            self.counts['recommendation_rows'] += 1
            self.check(isinstance(row, dict), 'recommendation_is_object', context)
            if not isinstance(row, dict):
                continue
            self.recommendation_schemas[','.join(sorted(row))] += 1
            kind = row['kind']; r, name = common(row, kind)
            expected_through = r if kind == 'focus' else r-1
            self.equal(row['through_round'], expected_through, 'permitted_information_cutoff', (context, kind, r, name))
            self.counts[f'{kind}_recommendations'] += 1
            if kind == 'offer':
                good, gen = row['good'], row['generation']
                key = (r, name, good, gen)
                self.check(key not in offers, 'offer_recommendation_unique', (context, key))
                offers[key] = row
                p = public_by_key.get(key)
                self.check(p is not None, 'offer_has_public_snapshot', (context, key))
                if p is not None:
                    self.equal(row['actual_ids'], p['ids'], 'offer_public_ids_match', (context, key))
                    self.equal(row['actual_prices'], p['prices'], 'offer_public_prices_match', (context, key))
                for uid in row['actual_ids']:
                    self.check(uid in units and units[uid]['good'] == good and units[uid]['gen'] == gen
                               and units[uid]['born'] <= r, 'offered_uid_grade_and_date', (context, key, uid))
                self.equal(row['price_applied'], prices_on, 'price_policy_flag', (context, key))
                self.equal(row['public_quantity_limited'], limited_on, 'offer_listing_policy_flag', (context, key))
                advice = row['recommendation']
                self.equal(advice['through_round'], r-1, 'price_advice_cutoff', (context, key))
                self.equal(advice['reference'], quote(good, gen, r), 'current_reference_quote', (context, key))
                exposures = {(p['round'], uid) for p in public if p['country'] == name and p['good'] == good
                             and p['generation'] == gen and max(1, r-2) <= p['round'] < r for uid in p['ids']}
                cleared = {(tx['round'], uid) for tx in trace['transactions'] if max(1, r-2) <= tx['round'] < r
                           for leg in tx['legs'] if leg['seller'] == name for uid in leg['ids']
                           if (tx['round'], uid) in exposures}
                self.equal(advice['past_offered'], len(exposures), 'same_round_public_exposures', (context, key))
                self.equal(advice['past_sold'], len(cleared), 'public_exposures_actually_cleared', (context, key))
                self.equal(advice['past_all_sales'], own_sales(name, good, r-1, gen)['units'],
                           'all_channel_history_separate_from_public_fill', (context, key))
                unused = [uid for uid in row['actual_ids'] if units[uid]['use_round'] is None
                          or units[uid]['use_round'] > r or (units[uid]['use_round'] == r
                          and units[uid]['use_purpose'] not in ('production', 'equipment', 'maintenance'))]
                expected_age = max((r-units[uid]['born'] for uid in unused), default=0)
                self.equal(advice['age'], expected_age, 'age_of_unused_stock_at_listing', (context, key))
                fill = len(cleared)/len(exposures) if exposures else None
                factor, reason = 1., 'reference_trial'
                if expected_age >= 4 and exposures and fill < .5:
                    factor, reason = .6, 'persistent_unsold'
                elif expected_age >= 2 and exposures and fill < .75:
                    factor, reason = .8, 'unsold_stock'
                elif exposures and fill >= .9:
                    factor, reason = 1.05, 'recent_sales_strong'
                price = half_up(advice['reference']*factor)
                rival = advice['rival_best']
                if rival is not None:
                    self.check(type(rival) is int and rival > 0, 'recorded_rival_price_valid', (context, key))
                    if rival < price:
                        price = rival; reason += ';match_public_offer'
                price = max(half_up(advice['reference']*.5), price)
                if style(name) == 'cheap':
                    price, reason = half_up(advice['reference']*.5), 'fixed_half_reference'
                if behavior(result, name) in MINIMUM:
                    self.equal(advice.get('regular_recommendation'), price,
                               'unmodified_regular_recommendation_before_legal_minimum', (context, key))
                    price, reason = 1, 'fixed_legal_public_minimum'
                else:
                    self.check('regular_recommendation' not in advice,
                               'no_undeclared_minimum_price_override', (context, key))
                self.equal(advice['price'], price, 'advice_price_arithmetic', (context, key))
                self.equal(advice['reason'], reason, 'price_reason_matches_rule', (context, key))
                self.check(all(type(x) is int and x > 0 for x in row['actual_prices']), 'positive_integer_prices', (context, key))
                mismatch = row['price_applied'] and row['actual_prices'] != [price]
                country_counts[name]['offer_price_mismatches'] += int(mismatch)
                self.check(not mismatch, 'recommended_price_actually_applied', (context, key))
            elif kind == 'investment':
                key = (r, name)
                self.check(key not in investments, 'one_investment_plan_per_round', (context, key))
                investments[key] = row
                self.check(planning_on and r <= 7, 'investment_advice_mode_and_time', (context, key))
                country_counts[name]['planning_decisions'] += 1
                country_counts[name]['planning_holds'] += int(row['selected'] is None)
                candidates = row['candidates']
                self.equal(len(candidates), len({c['good'] for c in candidates}), 'investment_candidates_unique', (context, key))
                for candidate in candidates:
                    g = candidate['good']; ctx = (context, key, g)
                    self.equal(candidate['through_round'], r-1, 'investment_candidate_cutoff', ctx)
                    rem = 9-r
                    self.equal(candidate['remaining_rounds'], rem, 'investment_horizon', ctx)
                    history = own_sales(name, g, r-1)
                    self.equal(candidate['sales_forecast'], history['rate']*rem, 'investment_own_sales_forecast', ctx)
                    stock = sum(units[i]['good'] == g for i in owned_before_trade(r, name))
                    if g in ('banana', 'wheat'):
                        stock = max(0, stock-(1+int(r >= 5)+int(r >= 8)))
                        domestic = sum(1+int(rr >= 5)+int(rr >= 8) for rr in range(r+1, 10))
                        self.equal(candidate['future_domestic'], domestic, 'own_future_food_need', ctx)
                    elif g == 'electronics':
                        self.equal(candidate['future_domestic'], 2, 'own_final_electronics_need', ctx)
                    self.equal(candidate['stock_after_current_use'], stock, 'investment_own_available_stock', ctx)
                    old_output, new_output = candidate['old_output_forecast'], candidate['new_output_forecast']
                    gap = max(0, candidate['future_domestic']+candidate['sales_forecast']-stock-old_output)
                    useful = min(max(0, new_output-old_output), gap)
                    self.equal(candidate['marginal_useful_units'], useful, 'incremental_use_not_total_output', ctx)
                    before = production.get((r, name, g))
                    oldgen = before['tech'] if before else 1
                    level = before['level'] if before else 0
                    newgen = min(3, level+1) if g in ('machine', 'electronics') else 1
                    oldquote = quote(g, oldgen, r)
                    realizable = min(oldquote, history['cash_price'] if history['cash_price'] is not None else oldquote)
                    self.equal(candidate['capacity_value'], useful*realizable, 'capacity_value_at_observed_own_cash_price', ctx)
                    trial = 0.; quality = 0.
                    if newgen > oldgen:
                        newquote = quote(g, newgen, r)
                        stream = min(candidate['sales_forecast'], new_output)
                        trial = min(max(0, new_output-stream), .5*history['buyers'] if history['buyers'] else 1.)
                        quality = stream*max(0, newquote-realizable)+trial*newquote+(rem if g == 'electronics' else 0)
                    self.equal(candidate['quality_trial_units'], trial, 'bounded_new_grade_trial', ctx)
                    self.equal(candidate['quality_opportunity_value'], quality, 'uncertain_grade_value_arithmetic', ctx)
                    self.equal(candidate['uncertain_new_generation'], newgen > oldgen, 'uncertainty_flag', ctx)
                    values = ('development_cost', 'prerequisite_value', 'additional_operating_value')
                    for field in values:
                        value = candidate[field]
                        self.check(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                                   'nonnegative_finite_opportunity_cost', (ctx, field))
                    score = (candidate['capacity_value']+quality)/max(1, sum(candidate[f] for f in values))
                    score += .3 if g == MAIN_GOOD[name] else 0
                    if level == 0:
                        score *= .8
                    self.equal(candidate['opportunity_score'], score, 'opportunity_score_arithmetic', ctx)
                    self.equal(candidate['eligible'], score >= .45, 'opportunity_threshold_not_cash_payback', ctx)
                winner = max(candidates, key=lambda c:(c['opportunity_score'], c['good'])) if candidates else None
                selected = winner['good'] if winner and (winner['eligible'] or style(name) == 'invest') else None
                self.equal(row['selected'], selected, 'best_eligible_investment_candidate', (context, key))
            elif kind == 'focus':
                key = (r, name)
                self.check(key not in focuses, 'one_focus_plan_per_round', (context, key))
                focuses[key] = row
                self.check(planning_on and r <= 8, 'focus_mode_and_time', (context, key))
                candidates = row['candidates']
                self.check(bool(candidates), 'focus_has_choice', (context, key))
                self.equal(len(candidates), len({c['good'] for c in candidates}), 'focus_candidates_unique', (context, key))
                for candidate in candidates:
                    g = candidate['good']; ctx = (context, key, g)
                    useful = candidate['marginal_useful_units']; total = candidate['bonus']*(9-r)
                    self.check(0 <= useful <= total, 'focus_uses_only_marginal_bonus', ctx)
                    self.check(candidate['base_output'] >= 0 and candidate['bonus'] >= 0, 'focus_nonnegative_output', ctx)
                    self.equal(candidate['value'], useful*quote(g, 1, r), 'focus_value_arithmetic', ctx)
                    self.equal(candidate['excess_value'], max(0, total-useful)*quote(g, 1, r), 'focus_excess_value_arithmetic', ctx)
                winner = max(candidates, key=lambda c:(c['value'], -c['excess_value'], c['good']))
                self.equal(row['selected'], winner['good'], 'focus_selected_best_use_then_least_waste', (context, key))
                self.equal(row['selected'], ledgers[key]['next_focus'], 'recommended_focus_actually_selected', (context, key))
            else:
                self.check(False, 'known_recommendation_kind', (context, kind))

        self.equal(set(offers), set(public_by_key), 'all_public_snapshots_have_advice', context)
        for key, p in plans_by_key.items():
            offer_ids = [uid for gen in (1, 2, 3) for uid in offers.get((*key, gen), {}).get('actual_ids', [])]
            self.equal(set(offer_ids), set(p['actual_ids']), 'all_generation_offers_within_total_plan', (context, key))
            for gen in (1, 2, 3):
                offer = offers.get((*key, gen))
                if offer:
                    self.equal(offer['total_good_target'], p['target'], 'shared_all_grade_listing_target', (context, key, gen))
        recall_keys = set()
        for row in recalls:
            r, name = common(row, 'grade_recall')
            uid = row['unit']; key = (r, name, uid)
            self.check(key not in recall_keys, 'grade_recall_once_per_uid_round', (context, key))
            recall_keys.add(key)
            self.check(uid in owned_before_trade(r, name) and units[uid]['good'] == 'machine'
                       and units[uid]['gen'] >= row['min_gen'], 'grade_recall_qualifies_and_is_owned', (context, key))
            country_counts[name]['grade_recalls'] += 1
        for name, c in countries.items():
            can_list = result.get('style') != 'no_trade' and style(name) != 'idle'
            expected_plans = {(r, name, good) for r in range(1, 10) for good in GOODS} if can_list else set()
            self.equal({key for key in plans_by_key if key[1] == name}, expected_plans,
                       'listing_record_round_coverage', (context, name))
            expected_investment = {(r, name) for r in range(1, 8)} if planning_on and style(name) not in ('idle', 'trade') else set()
            self.equal({key for key in investments if key[1] == name}, expected_investment,
                       'investment_record_round_coverage', (context, name))
            expected_focus = {(r, name) for r in range(1, 9)} if planning_on and style(name) not in ('idle', 'invest') else set()
            self.equal({key for key in focuses if key[1] == name}, expected_focus,
                       'focus_record_round_coverage', (context, name))
            for field in ('grade_recalls', 'planning_decisions', 'planning_holds', 'public_offer_units',
                          'offer_price_mismatches', 'listing_plan_violations', 'protected_offer_violations'):
                self.equal(country_counts[name][field], c[field], 'trace_recommendation_summary', (context, name, field))
            for good in GOODS:
                listed = sum(u['owner'] == name and u['good'] == good and u['order'] is not None for u in units.values())
                self.equal(listed, c['listed_by_good'][good], 'trace_final_held_and_listed', (context, name, good))
                unused = sum(u['owner'] == name and u['good'] == good and not u['used'] for u in units.values())
                self.equal(unused, c['unused_by_good'][good], 'trace_final_unused_stock', (context, name, good))
        self.counts['public_offer_records'] += len(public)
        self.counts['listing_plan_records'] += len(plans)
        self.counts['grade_recall_records'] += len(recalls)

    # Frozen v10 route audit, adapted only for multi-actor behavior lookup.
    def audit_routing_trace(self,trace,result,context):
        decisions=trace['routing_decisions'];routes=trace['routing_routes'];actions=trace['routing_actions']
        events=trace['development'];chains={e['event_id']:e for e in trace['development_chains']}
        units={int(k):v for k,v in trace['units'].items()};txs=trace['transactions'];public=trace['public_offers']
        policy=ROUTING_POLICIES[mode(result)];wait=policy['wait_rounds']
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
                actual_style=effective_style(result,name)
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


def audit_supplemental_overlap(folder,out=None):
    """Read an explicitly identified replay; never add it to the formal count."""
    stored=read_json(folder/'supplemental_overlap_replay.json.gz')
    record=stored['record'];trace=stored['trace'];meta=stored['metadata'];key=eval_identity(record)
    audit=Audit();formal=next((r for r in read_lines(folder/'runs.jsonl.gz') if eval_identity(r)==key),None)
    audit.equal(key,('main','Tropia:cheap',78040),'targeted_overlap_is_existing_formal_case')
    audit.equal(record,formal,'replay_summary_exactly_matches_saved_formal_trajectory',key)
    audit.equal(meta['replay_of_existing_formal_trajectory'],True,'supplement_is_a_replay')
    audit.equal(meta['counted_as_new_trajectory'],False,'replay_adds_no_independent_game')
    audit.equal(meta['formal_unique_trajectories'],4400,'formal_game_count_unchanged')
    audit.equal(meta['original_representative_traces'],39,'original_representative_scope_unchanged')
    audit.equal(meta['additional_targeted_replays'],1,'one_targeted_additional_replay')
    for field in ('phase','mode','scenario','seed','focal','style','behaviors'):
        audit.equal(meta['identity'][field],record[field],'replay_metadata_identity',(key,field))
        audit.equal(trace[field],record[field],'replay_trace_identity',(key,field))
    manifest=read_json(folder/'run_manifest.json')
    audit.equal(meta['engine_sha256'],manifest['source_sha256']['evaluation_engine.py'],'replay_uses_frozen_engine')
    for filename,digest in manifest['source_sha256'].items():
        audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(),digest,'replay_current_source_matches_formal',filename)
    audit.run_summary(record)
    audit.ledger(trace['cash_ledger'],record,key)
    audit.raw_ledger(trace['raw_ledger'],record,key)
    audit.trace(trace,record,key)
    overlap=[a for a in trace['evaluation_attempts'] if a['already_credited']]
    audit.equal(len(overlap),1,'one_actual_overlap_in_targeted_replay')
    examples=[]
    for a in overlap:
        m=a['machine_used'];uid=m['uid']
        equipment=[n for n in trace['needs_ledger'] if n['round']==a['round'] and n['country']==a['country']
                   and n['purpose'].startswith('equipment:') and uid in n['used_ids']]
        ready=[n for n in trace['evaluation_rows']['ready'] if n['round']==a['round'] and n['country']==a['country']]
        once=[n for n in trace['evaluation_rows']['ready_once'] if n['round']==a['round'] and n['country']==a['country']]
        audit.equal(a['country'],'Novia','specified_country_has_real_overlap')
        audit.equal(len(equipment),1,'same_physical_uid_already_has_one_equipment_need')
        audit.equal(sum(n['fulfilled'] for n in equipment),1,'existing_equipment_import_service_was_credited')
        audit.equal(len(ready),1,'ready_sensitivity_adds_duplicate_service_row')
        audit.equal(once,[],'ready_once_omits_only_duplicate_development_row')
        examples.append({'round':a['round'],'country':a['country'],'development_goal':a['goal'],
            'target_level':a['target_level'],'machine':m,'import_transaction':trace['transactions'][m['import_transaction']],
            'existing_equipment_need':equipment,'ready_added_row':ready,'ready_once_added_row':once,
            'country_score_views':record['countries'][a['country']]['evaluation']['scores']})
    report={'status':'failed' if audit.errors else 'passed','scope':'One targeted replay of an existing formal trajectory, separate from the39 representative traces.',
        'formal_unique_trajectories':4400,'original_representative_traces':39,'additional_targeted_replays':1,
        'additional_unique_trajectories':0,'summary_exact_match':record==formal,'formal_identity':key,
        'examples':examples,'audit_counts':dict(audit.counts),'checks_evaluated':audit.checks,'errors':audit.errors,
        'limits':['This confirms one physical overlap case; it does not reconstruct all77 reported overlaps.',
                  'The formal independent audit file and its original counts remain unchanged.']}
    target=out or folder/'supplemental_overlap_audit.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:sorted(v,key=repr) if isinstance(v,set) else repr(v)),encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':audit.checks,'errors':len(audit.errors),'report':str(target)},ensure_ascii=False))
    return int(bool(audit.errors))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path(__file__).parent/'evaluation_results')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--supplemental',action='store_true',help='Audit the saved targeted overlap replay only; preserve formal audit counts.')
    args=parser.parse_args();folder=args.results.resolve();folder.mkdir(exist_ok=True)
    if args.supplemental:return audit_supplemental_overlap(folder,args.out)
    audit=Audit();report={'scope':'Independent v11 saved-record audit; no economic engine import or simulation.','warnings':[]}
    files=('runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','run_manifest.json')
    missing=[f for f in files if not (folder/f).exists()]
    if missing:report.update(status='pending_final_results',pending=missing)
    else:
        rows=read_lines(folder/'runs.jsonl.gz');keys=[eval_identity(r) for r in rows];by_key={eval_identity(r):r for r in rows}
        audit.equal(len(keys),len(set(keys)),'unique_physical_trajectory_identity')
        for row in rows:audit.run_summary(row)
        mains={eval_identity(r):r for r in rows if r['phase']=='main'}
        for filename,method in (('round_ledgers.jsonl.gz',audit.ledger),('raw_round_ledgers.jsonl.gz',audit.raw_ledger)):
            groups=read_lines(folder/filename);gkeys=[eval_identity(g) for g in groups]
            audit.equal(len(gkeys),len(set(gkeys)),'ledger_scenarios_do_not_alias',filename)
            audit.equal(set(gkeys),set(mains),'all_main_trajectories_have_ledger',filename)
            for group in groups:
                key=eval_identity(group)
                for field in ('phase','mode','scenario','seed','focal','style','behaviors'):
                    audit.equal(group[field],mains[key][field],'ledger_retains_complete_scenario_identity',(filename,key,field))
                method(group['rows'],mains[key],key)
        traced=[]
        for label,stored in read_json(folder/'first_seed_traces.json.gz').items():
            key=eval_identity(stored);audit.check(key in by_key,'trace_matches_completed_trajectory',(label,key))
            if key not in by_key:continue
            for field in ('phase','mode','scenario','seed','focal','style','behaviors'):
                audit.equal(stored[field],by_key[key][field],'trace_retains_complete_scenario_identity',(label,field))
            traced.append(key);audit.trace(stored.get('trace',stored),by_key[key],key)
        audit.equal(len(traced),len(set(traced)),'unique_representative_trajectory_traces')
        manifest=read_json(folder/'run_manifest.json')
        for field in ('completed_games','planned_games'):audit.equal(len(rows),manifest[field],'manifest_physical_games',field)
        a,b=manifest['main_seed_range'];c,d=manifest['stress_seed_range']
        main_scenarios=manifest['main_scenarios'];stress_scenarios=manifest['stress_scenarios']
        def scenario_ids(items):
            return [s['scenario'] if isinstance(s,dict) else s for s in items]
        planned_main={'None:normal'}|{f'{name}:{style}' for name in ORIGINAL for style in ('cheap','minimum','idle')}
        planned_stress={'None:normal'}|{f'{name}:{style}' for name in ORIGINAL for style in ('minimum','minimum_passive')}
        planned_stress|={'Mechania:idle','Mechania:idle+Technia:minimum','Mechania:idle+Novia:minimum',
                         'Technia:no_high_machine','Novia:no_high_machine','Technia:no_raw','None:no_trade'}
        audit.equal(set(scenario_ids(main_scenarios)),planned_main,'main_schedule_is_one_control_plus_eighteen_conditions')
        audit.equal(set(scenario_ids(stress_scenarios)),planned_stress,'stress_schedule_includes_two_composite_behaviors')
        audit.equal(manifest['scoring_views_per_trajectory'],4,'four_views_are_not_four_games')
        audit.equal(manifest['shadow_views_are_extra_games'],False,'shadow_views_add_no_physical_trajectories')
        scenario_specs={(phase,s['scenario']):s for phase,items in (('main',main_scenarios),('stress',stress_scenarios)) for s in items}
        for row in rows:
            spec=scenario_specs[(row['phase'],row['scenario'])]
            expected_behaviors=dict(spec['behaviors'])
            if spec['focal'] is not None:expected_behaviors[spec['focal']]=spec['style']
            audit.equal((row['focal'],row['style'],row['behaviors']),
                        (spec['focal'],spec['style'],expected_behaviors),'scenario_executes_declared_all_actor_behaviors',eval_identity(row))
        expected={('main',s,seed) for s in scenario_ids(main_scenarios) for seed in range(a,b+1)}
        expected|={('stress',s,seed) for s in scenario_ids(stress_scenarios) for seed in range(c,d+1)}
        audit.equal(set(keys),expected,'complete_preregistered_physical_schedule')
        expected_traces={('main',s,a) for s in scenario_ids(main_scenarios)}|{('stress',s,c) for s in scenario_ids(stress_scenarios)}
        audit.equal(set(traced),expected_traces,'every_scenario_has_first_seed_trace')
        audit.equal(len(traced),manifest['representative_traces_planned'],'trace_count_matches_plan')
        for filename,digest in manifest['source_sha256'].items():
            audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(),digest,'frozen_source_hash',filename)
        audit.equal(manifest['source_sha256_before'],manifest['source_sha256_after'],'source_hashes_unchanged_during_formal_run')
        audit.equal(manifest['test_sha256_before'],manifest['test_sha256_after'],'test_hashes_unchanged_during_formal_run')
        for filename,digest in manifest['test_sha256_after'].items():
            audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(),digest,'frozen_test_hash',filename)
        report.update(completed_runs=len(rows),groups={str(k):v for k,v in Counter((r['phase'],r.get('scenario')) for r in rows).items()},
            evaluation_examples=audit.evaluation_examples,route_examples=audit.route_examples,
            legacy_score_coverage=dict(audit.score_coverage))
        report['method_notes']=[
            'One economic trajectory produces four simultaneous score views; shadow views are not additional games.',
            'Original needs, trade scores, total scores and all economic actions remain the legacy trajectory.',
            'The legal public ask is 1G per item; direct/barter rules are unchanged and barter has no imputed cash value.',
            'Investment readiness is reconstructed from cash, actual ownership/listing status, household use, unchanged recipes and cached plans.',
            'Domestic qualifying alternatives include listed units; legally usable equipment excludes listed units.',
            'ready_once removes only the same foreign physical UID already credited for equipment this country and round.',
            'A new UID swap, different round or different country is outside that narrow same-service deduplication scope.',
            'Only the existing import coverage/round parts are recomputed; export, partner, economic, industry and welfare formulas are untouched.',
            'All three new country total scores remain None because their growth goals are not calibrated.',
            'Counts from detailed physical/decision/snapshot reconstruction refer only to the saved representative games.',
        ]
        report['audit_scope']={
            'summaries':'All physical runs: inherited accounting, price-policy outcomes, participation, readiness diagnostics and four score views.',
            'round_ledgers':'Every main scenario: independent cash and raw continuity, using scenario IDs.',
            'detailed_traces':'Saved representatives: inherited units, prices, development, routing plus investment-phase readiness, duplicate services and complete shadow score reconstruction.',
            'not_claimed':['Every UID-level path in games without detailed traces.','Financial fairness, an optimal score, observed student behavior or learning.',
                           'The same-UID deduplication as a complete anti-collusion or anti-swap system.','A public price policy changing the legal minimum consideration for every direct multi-unit deal.']}
        report['status']='failed' if audit.errors else 'passed'
    report.update(audit_counts=dict(audit.counts),checks_evaluated=audit.checks,errors=audit.errors)
    target=args.out or folder/'independent_audit.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:sorted(v,key=repr) if isinstance(v,set) else repr(v)),encoding='utf-8')
    print(json.dumps({'status':report['status'],'counts':report['audit_counts'],'checks':audit.checks,'errors':len(audit.errors),'report':str(target)},ensure_ascii=False))
    return int(bool(audit.errors))


if __name__=='__main__':raise SystemExit(main())
