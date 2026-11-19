"""Independent v13 saved-result causal audit; no engine or runner imports.

The frozen v11/v12 cash, UID, routing and score audits are reused.  The copied
readiness reconstruction below has exactly one declared physical extension:
electronics at Lv2+ may require one additional existing raw bundle per cycle.
The simulation itself is never replayed by this auditor.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_evaluation_results import (Audit as EvaluationAudit, SCORE_MODES,
    effective_style, behavior, MINIMUM, REFUSALS, DIAGNOSTICS)
from audit_routing_results import EXPAND, grade_required
from audit_development_results import development_cost
from audit_machinery_results import ORIGINAL, GOODS, read_json, read_lines

CAUSAL_POLICIES={
    'baseline':{'operating_first':False,'remove_durable_boost':False,'electronics_extra_raw':0},
    'operating_first':{'operating_first':True,'remove_durable_boost':False,'electronics_extra_raw':0},
    'no_durable_boost':{'operating_first':False,'remove_durable_boost':True,'electronics_extra_raw':0},
    'ai_combined':{'operating_first':True,'remove_durable_boost':True,'electronics_extra_raw':0},
    'electronics_input':{'operating_first':False,'remove_durable_boost':False,'electronics_extra_raw':1},
    'combined_input':{'operating_first':True,'remove_durable_boost':True,'electronics_extra_raw':1},
}
AI_MODES=tuple(CAUSAL_POLICIES)[:4]
ECONOMIC_MODES=tuple(CAUSAL_POLICIES)[4:]
PRICE={'banana':10,'wheat':10,'ore':20,'fuel':30,'machine':50,'electronics':80}
BASES={
    'Tropia':{'banana':4,'wheat':2},'Grainia':{'wheat':3,'banana':2},
    'Oilia':{'fuel':1,'ore':1,'banana':1},'Mechania':{'machine':2,'wheat':2},
    'Mineria':{'ore':1,'fuel':1},'Technia':{'electronics':1,'machine':1,'wheat':1},
    'Novia':{'electronics':1,'wheat':1},'Agrea':{'banana':2,'fuel':1},'Ferria':{'ore':1,'wheat':2},
}
MAIN_GOODS=dict(zip(ORIGINAL,('banana','wheat','fuel','machine','ore','electronics')),
               Novia='electronics',Agrea='banana',Ferria='ore')
CAUSAL_FIELDS=('cash_trade_balance','cash_before_investment_balance','cash_change',
    'legal_planned_attempts','cash_ready_attempts','feasible_planned_attempts','successful_attempts',
    'no_upgrade','blocked_cash_attempts','blocked_household_attempts','blocked_raw_attempts','blocked_machine_attempts')
IDENTITY_FIELDS=('phase','mode','scenario','seed','focal','style','behaviors')
GOALS_SHA256='47e78fe6a9cebab256bb52a3b7dbef9c9b46cec4363d15700290ddfa2e4620d5'
OLD_ECONOMIC=dict(zip(ORIGINAL,(250,240,140,160,140,160)))
OLD_INDUSTRIAL=dict(zip(ORIGINAL,(.90,.90,.48,.25,.48,.27)))
FROZEN_ECONOMIC=dict(zip(ORIGINAL,(305,265,245,230,185,895)))
FROZEN_INDUSTRIAL=dict(zip(ORIGINAL,(.35,.4,.85,.45,.6,1.5)))


def identity(row):return row['phase'],row['mode'],row['scenario'],row['seed']

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(a,b):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-9)

def cap(x):return min(1,max(0,x))


class TraceState:
    """Rebuild the pre-consumption trading state from original UID transfers.

    No economic model functions are called. Production precedes all trading;
    household consumption, research and income occur after both buy sweeps.
    Public offer histories are snapshots after each owner's listing phase.
    """
    def __init__(self,trace,result):
        self.trace=trace;self.result=result
        self.units={int(k):v for k,v in trace['units'].items()}
        self.tx=trace['transactions'];self.public=trace['public_offers']
        self.cash={(r['round'],r['country']):r for r in trace['cash_ledger']}
        self.levels=defaultdict(dict)
        for p in trace['production']:self.levels[(p['round'],p['country'])][p['industry']]=p['level']
        self.decisions={(d['round'],d['country']):d for d in trace['routing_decisions']}
        self._held={};self._raw={}

    def cutoff(self,r):
        return next((i for i,t in enumerate(self.tx) if t['round']>=r),len(self.tx))

    def listed(self,r,cut,pre_listing=False):
        source_round=r-1 if pre_listing else r
        ids={uid for p in self.public if p['round']==source_round for uid in p['ids']}
        moved={uid for t in self.tx[:cut] if t['round']>=source_round for leg in t['legs'] for uid in leg['ids']}
        return ids-moved

    def held(self,name,r,cut,free=False,pre_listing=False):
        key=(name,r,cut,free,pre_listing)
        if key in self._held:return self._held[key]
        owners={uid:u['origin'] for uid,u in self.units.items() if u['born']<=r}
        for t in self.tx[:cut]:
            for leg in t['legs']:
                for uid in leg['ids']:owners[uid]=leg['buyer']
        for uid,u in self.units.items():
            if u['owner'] is None and u['use_round'] is not None:
                if u['use_round']<r or (u['use_round']==r and u['use_purpose'] in ('production','maintenance')):
                    owners[uid]=None
        listed=self.listed(r,cut,pre_listing) if free else set()
        value=tuple(sorted(uid for uid,owner in owners.items() if owner==name and uid not in listed))
        self._held[key]=value
        return value

    def stock(self,name,r,cut,free=False,pre_listing=False):
        counts=Counter(self.units[i]['good'] for i in self.held(name,r,cut,free,pre_listing))
        return {g:counts[g] for g in GOODS}

    def focus(self,name,r):
        return MAIN_GOODS[name] if r==1 else self.cash[(r-1,name)]['next_focus']

    def quote(self,g,gen,r):
        base=PRICE[g] if r==1 else self.trace['prices'][r-2][g]
        if g in ('machine','electronics'):
            world=max(u['gen'] for u in self.units.values() if u['good']==g and u['born']<=r)
            base*= (1,1.4,1.8)[gen-1]*.75**max(0,world-gen)
        return max(1,math.floor(base+.5))

    def price(self,name,g,gen,r,cut):
        moved={uid for t in self.tx[:cut] if t['round']==r for leg in t['legs'] for uid in leg['ids']}
        prices=[price for p in self.public if p['round']==r and p['country']!=name
                and p['good']==g and p['generation']>=gen and set(p['ids'])-moved for price in p['prices']]
        return min(prices) if prices else self.quote(g,gen,r)

    def cash_at(self,name,r,cut):
        net=0
        for t in self.tx[:cut]:
            if t['round']!=r or not t['cash']:continue
            buyer,seller,value=t['cash'];net+=value*int(seller==name)-value*int(buyer==name)
        return self.cash[(r,name)]['cash_start']+net

    def purchases_at(self,name,cut):
        return sum(t['cash'][2] for t in self.tx[:cut] if t['cash'] and t['cash'][0]==name)

    def raw(self,name,r,cut,project=None,pre_listing=False):
        key=(name,r,cut,project,pre_listing)
        if key in self._raw:return self._raw[key].copy()
        if r>=9:return Counter()
        levels=dict(self.levels[(r,name)])
        if project:levels[project]=levels.get(project,0)+1
        held=self.held(name,r,cut,False,pre_listing);answer=Counter()
        extra=CAUSAL_POLICIES[self.result['mode']]['electronics_extra_raw']
        for good,lv in levels.items():
            if good=='electronics':answer['ore' if (r+1)%2 else 'fuel']+=1+int(lv>=3)+extra*int(lv>=2)
            if good!='machine':continue
            gen=min(3,lv);raw='ore' if name=='Mechania' or (r+1)%2 else 'fuel'
            rounds=range(max(1,r-1),r+1)
            sales=sum(1 for t in self.tx[:cut] if t['round'] in rounds for leg in t['legs'] if leg['seller']==name
                      for uid in leg['ids'] if self.units[uid]['origin']==name and self.units[uid]['good']=='machine' and self.units[uid]['gen']==gen)
            target=1+math.ceil(sales/len(rounds))+int(gen>=2 and any(g not in ('machine','electronics') for g in levels))
            stock=sum(self.units[i]['good']=='machine' and self.units[i]['gen']>=gen for i in held)
            wanted=max(0,target-stock)
            launched=any(u['origin']==name and u['good']=='machine' and u['gen']==gen and 0<u['born']<=r for u in self.units.values())
            if not launched:wanted=max(1,wanted)
            maximum=BASES[name].get('machine',1)+lv-1+1
            quantity=min(maximum,wanted)
            work=max(0,quantity-1) if gen==1 else quantity*(1 if gen==2 else 2)
            credits=[e['credits_after'] for e in self.trace['material_events'] if e['country']==name and e['raw']==raw and e['generation']==gen and e['round']<=r]
            required=math.ceil(max(0,work-(credits[-1] if credits else 0))/2)
            if required:answer[raw]+=required
        self._raw[key]=answer.copy()
        return answer

    def world_need(self,g,r):
        names=self.result['countries'];cut=self.cutoff(r)
        if g in ('wheat','banana'):return len(names)*(1+int(min(9,r+1)>=5)+int(min(9,r+1)>=8))
        if g in ('ore','fuel'):return sum(self.raw(n,r,cut,pre_listing=True)[g] for n in names)+len(names)/3
        if g=='machine':
            equipped=sum(self.focus(n,r) in self.levels[(r,n)] and self.focus(n,r) not in ('machine','electronics') for n in names)
            return equipped/3+len(names)/2
        return len(names)*math.ceil((2+int(r>=5)+int(r>=8))/2)


class Audit(EvaluationAudit):
    def mapping(self,actual,expected,label,context=None):
        self.equal(set(actual),set(expected),label+'_schema',context)
        for field,value in expected.items():
            if field in actual:self.equal(actual[field],value,label,(context,field))

    def run_summary(self,row):
        super().run_summary(row)
        k=identity(row);policy=CAUSAL_POLICIES[row['mode']];world=row['world']
        self.equal(world['causal_mode'],row['mode'],'causal_mode_identity',k)
        self.equal(world['causal_policy'],policy,'predeclared_single_factor_policies',k)
        expected_scope={'official_score_unchanged':True,'storage_enabled':False,
            'extra_manufacturing_cash_fee':0,'sales_fee':0,
            'student_rules_changed':bool(policy['electronics_extra_raw']),
            'changes_are_candidates':True,
            'opportunity_scope':'AI selected project, not every possible legal investment'}
        self.equal(world['causal_scope'],expected_scope,'causal_scope_keeps_cost_and_score_baseline',k)
        for name,c in row['countries'].items():
            q=(k,name);x=c['causal'];self.equal(set(x),set(CAUSAL_FIELDS),'causal_country_schema',q)
            for field,value in x.items():
                self.check(type(value) is int,'causal_diagnostics_integral',(q,field))
                if field not in ('cash_trade_balance','cash_before_investment_balance','cash_change'):
                    self.check(value>=0,'nonnegative_attempt_counts',(q,field))
            self.equal(x['cash_trade_balance'],c['revenue']-c['purchases'],'trade_cash_is_not_net_profit',q)
            self.equal(x['cash_before_investment_balance'],c['revenue']-c['purchases']+c['tax'],'preinvestment_balance',q)
            self.equal(x['cash_change'],c['cash']-c['start_cash'],'actual_cash_change',q)
            self.equal(x['cash_before_investment_balance']-c['investment'],x['cash_change'],'investment_explains_cash_delta',q)
            self.equal(x['successful_attempts'],c['upgrades_total'],'successful_attempts_are_actual_upgrades',q)
            self.equal(x['no_upgrade'],int(c['upgrades_total']==0),'no_upgrade_indicator',q)
            self.equal(x['cash_ready_attempts']+x['blocked_cash_attempts'],x['legal_planned_attempts'],'cash_ready_partition',q)
            self.check(0<=x['successful_attempts']<=x['feasible_planned_attempts']<=x['cash_ready_attempts']<=x['legal_planned_attempts']<=7,
                       'opportunities_are_selected_legal_rounds_not_all_choices',q)
            for field in ('blocked_household_attempts','blocked_raw_attempts','blocked_machine_attempts'):
                self.check(x[field]<=x['legal_planned_attempts'],'overlapping_blocker_bound',(q,field))
            if name not in ORIGINAL:self.equal(c['score'],None,'extra_three_have_no_improvised_score',q)
            self.counts['causal_country_summaries']+=1
        self.audit_fixed_score_reference(row)
        self.audit_decomposition_summary(row)

    def audit_fixed_score_reference(self,row):
        k=identity(row)
        self.equal(row['world']['growth_reference_config'],{
            'source':'frozen_v12_targets','goals_sha256':GOALS_SHA256,'views':['targets'],
            'refitted':False,'official_score_unchanged':True,'score_feedback_to_actions':False,
            'ranked_countries':list(ORIGINAL)},'old_targets_only_no_new_calibration',k)
        for name,c in row['countries'].items():
            m=c['growth_metrics'];bases=BASES[name];q=(k,name)
            initial=sum(PRICE[g]*n for g,n in bases.items())
            final=sum(PRICE[g]*(bases.get(g,1)+(lv-1)*(2 if g in ('wheat','banana') else 1))
                      for g,lv in c['end_levels'].items() if lv>0)
            produced=sum(c['produced'].values());used=sum(c['use_by_good'].values())
            expected={'start_asset_value':c['start_asset_value'],'end_asset_value':c['end_asset_value'],
                'asset_gain':c['end_asset_value']-c['start_asset_value'],'cash':c['cash'],'tax':c['tax'],
                'investment':c['investment'],'stock_value':c['cash_plus_stock_value']-c['cash'],
                'initial_capacity':initial,'final_capacity':final,'capacity_growth':(final-initial)/initial,
                'reserve_target':80,'reserve_score':5*cap(c['cash']/80),'produced_units':produced,'used_units':used,
                'utilization':used/max(1,produced),'utilization_score':10*used/max(1,produced),
                'wellbeing_score':c['happy']/4,'trade_score':c['trade']}
            self.equal(set(m),set(expected)|{'unused_stock_value','used_stock_value'},'reference_metrics_schema',q)
            for f,v in expected.items():self.equal(m[f],v,'growth_metric_arithmetic',(q,f))
            self.equal(m['unused_stock_value']+m['used_stock_value'],m['stock_value'],'stock_valuation_partition',q)
            self.equal(m['end_asset_value'],m['cash']+m['stock_value']+.45*m['investment'],'unchanged_asset_definition',q)
            start=c['start_cash']+6+sum(c['starter_raw'][g]*PRICE[g]*.15 for g in ('ore','fuel'))
            if any(g in ('machine','electronics') for g in bases):start+=7.5
            self.equal(m['start_asset_value'],start,'initial_asset_uses_actual_unchanged_grants',q)
            self.equal(set(c['growth_evaluation']),{'targets'},'only_one_fixed_reference_view',q)
            if name not in ORIGINAL:
                self.equal(c['growth_evaluation']['targets'],None,'no_target_invention_for_added_countries',q)
                continue
            er=m['asset_gain']/FROZEN_ECONOMIC[name];ir=m['capacity_growth']/FROZEN_INDUSTRIAL[name]
            eg=20*cap(er);capacity=15*cap(ir);economic=eg+m['reserve_score'];industry=capacity+m['utilization_score']
            reference={'economic_target':FROZEN_ECONOMIC[name],'industrial_target':FROZEN_INDUSTRIAL[name],
                'economic_ratio':er,'industrial_ratio':ir,'economic_growth':eg,'reserve':m['reserve_score'],
                'economic':economic,'capacity':capacity,'utilization':m['utilization_score'],'industry':industry,
                'wellbeing':m['wellbeing_score'],'trade':c['trade'],'score':economic+industry+c['happy']/4+c['trade'],
                'economic_growth_at_cap':int(eg>=20-1e-9),'capacity_at_cap':int(capacity>=15-1e-9),
                'economic_growth_near_cap':int(eg>=19-1e-9),'capacity_near_cap':int(capacity>=14.25-1e-9),
                'economic_at_cap':int(economic>=25-1e-9),
                'economic_5pct_sensitivity':20*(cap(max(0,er)*1.05)-cap(er)),
                'capacity_5pct_sensitivity':15*(cap(max(0,ir)*1.05)-cap(ir))}
            self.mapping(c['growth_evaluation']['targets'],reference,'frozen_v12_target_formula',(q,'targets'))
            official_economic=20*cap(m['asset_gain']/OLD_ECONOMIC[name])+m['reserve_score']
            official_capacity=15*cap(m['capacity_growth']/OLD_INDUSTRIAL[name])
            self.equal(c['economic'],official_economic,'official_economic_formula_unchanged',q)
            self.equal(c['industry_capacity_score'],official_capacity,'official_capacity_formula_unchanged',q)
            self.equal(c['industry'],official_capacity+m['utilization_score'],'official_utilization_formula_unchanged',q)
            self.equal(c['score'],official_economic+official_capacity+m['utilization_score']+c['happy']/4+c['trade'],
                       'official_total_keeps_legacy_trade_and_targets',q)
            self.counts['frozen_target_reference_views']+=1
        self.equal(row['world']['causal_score_spread'],max(row['countries'][n]['score'] for n in ORIGINAL)-min(row['countries'][n]['score'] for n in ORIGINAL),
                   'official_score_spread_excludes_added_three',k)
        values=[row['countries'][n]['growth_evaluation']['targets']['score'] for n in ORIGINAL]
        self.equal(row['world']['v12_targets_score_spread'],max(values)-min(values),'reference_score_spread_excludes_added_three',k)

    def audit_decomposition_summary(self,row):
        k=identity(row)
        for name,c in row['countries'].items():
            goods=c['economic_decomposition'];self.equal(set(goods),set(GOODS),'all_products_decomposed',(k,name))
            for g,x in goods.items():
                q=(k,name,g)
                for f,expected in (('cash_sales',c['sale_by_good'][g]),('cash_purchases',c['purchase_by_good'][g]),
                    ('produced',c['produced'].get(g,0)),('used',c['use_by_good'][g]),('useful_exports',c['export_used_by_good'][g])):
                    self.equal(x[f],expected,'decomposition_matches_primary_summary',(q,f))
                generations={'1','2','3'} if g in ('machine','electronics') else {'1'}
                self.equal(set(x['cash_sales_by_generation']),generations,'cash_generation_schema',q)
                self.equal(set(x['transferred_units_by_generation']),generations,'transfer_generation_schema',q)
                self.equal(set(x['cash_sale_origin']),{'own_produced','own_initial','resold_foreign'},'sales_provenance_schema',q)
                self.equal(sum(x['cash_sales_by_generation'].values()),x['cash_sales'],'generation_cash_partition',q)
                self.equal(sum(x['cash_sale_origin'].values()),x['cash_sales'],'sale_origin_cash_partition',q)
                self.equal(sum(x['transferred_units_by_generation'].values()),c['export_goods'].get(g,0),'cash_and_barter_unit_partition',q)
                self.check(0<=x['useful_exports']<=x['used']<=x['produced'],'use_is_bounded_by_own_production',q)
                for raw in ('ore','fuel'):
                    self.check(type(x['production_raw_inputs'][raw]) is int and x['production_raw_inputs'][raw]>=0,'physical_inputs_are_units',(q,raw))
                self.counts['product_decompositions']+=1
            self.equal(sum(x['investment_cash'] for x in goods.values()),c['investment'],'investment_by_industry_sums', (k,name))
            for raw in ('ore','fuel'):
                self.equal(sum(x['production_raw_inputs'][raw] for x in goods.values()),c['production_raw'][raw],
                           'physical_input_by_industry_sums',(k,name,raw))

    def trace(self,trace,result,context):
        self.causal_state=TraceState(trace,result)
        super().trace(trace,result,context)
        self.audit_causal_physical(trace,result,context)
        self.audit_causal_plans(trace,result,context)
        self.audit_causal_budgets(trace,result,context)
        self.audit_decomposition_trace(trace,result,context)

    def audit_causal_physical(self,trace,result,context):
        policy=CAUSAL_POLICIES[result['mode']]
        self.equal(trace['upkeep'],[],'no_new_upkeep_in_causal_comparison',context)
        for factory in trace['production']:
            good=factory['industry'];r=factory['round'];level=factory['level'];name=factory['country']
            if good=='machine':continue  # inherited credit/UID audit checks its unchanged recipe
            required=({'ore' if r%2 else 'fuel':1+int(level>=3)+int(level>=2)*policy['electronics_extra_raw']}
                      if good=='electronics' else {})
            self.equal(factory['required'],required,'only_declared_electronics_cycle_raw_changes',(context,r,name,good))
            enough=all(factory['available_before'].get(g,0)>=q for g,q in required.items())
            self.equal(factory['funded'],enough,'production_funded_by_recorded_precycle_stock',(context,r,name,good))
            if good=='electronics':self.counts['electronics_recipe_rows']+=1
        for name,c in result['countries'].items():
            all_attempts=[a for a in trace['evaluation_attempts'] if a['country']==name]
            legal=[a for a in all_attempts if a['legal']]
            feasible=[a for a in legal if a['cash_ok'] and a['household_ok'] and a['raw_ok']
                      and (not a['machine_min_gen'] or a['free_qualified_ids'])]
            expected={
                'cash_trade_balance':c['revenue']-c['purchases'],
                'cash_before_investment_balance':c['revenue']-c['purchases']+c['tax'],
                'cash_change':c['cash']-c['start_cash'],
                'legal_planned_attempts':len(legal),'cash_ready_attempts':sum(a['cash_ok'] for a in legal),
                'feasible_planned_attempts':len(feasible),'successful_attempts':sum(a['successful'] for a in legal),
                'no_upgrade':int(c['upgrades_total']==0),'blocked_cash_attempts':sum(not a['cash_ok'] for a in legal),
                'blocked_household_attempts':sum(not a['household_ok'] for a in legal),
                'blocked_raw_attempts':sum(not a['raw_ok'] for a in legal),
                'blocked_machine_attempts':sum(bool(a['machine_min_gen']) and not a['free_qualified_ids'] for a in legal),
            }
            self.mapping(c['causal'],expected,'actual_opportunity_counts_from_independently_verified_snapshots',(context,name))

    def audit_causal_plans(self,trace,result,context):
        policy=CAUSAL_POLICIES[result['mode']];plans=trace['causal_plan_log']
        self.equal(result['world']['causal_plan_rows'],len(plans),'plan_rows_from_trace',context)
        self.equal(len(plans),len({(x['round'],x['country']) for x in plans}),'one_base_plan_snapshot_per_country_round',context)
        if not policy['remove_durable_boost']:
            self.equal(plans,[],'baseline_plan_path_untouched',context)
        levels={(p['round'],p['country'],p['industry']):p['level'] for p in trace['production']}
        for p in plans:
            r=p['round'];name=p['country'];q=(context,r,name)
            self.check(1<=r<=7 and p['style'] not in ('idle','trade'),'no_new_late_or_passive_plans',q)
            own={g:lv for (round_no,n,g),lv in levels.items() if (round_no,n)==(r,name)}
            self.equal(p['levels'],own,'investment_plan_uses_existing_levels',q)
            choices={g for g,lv in own.items() if lv<4}
            if EXPAND[name] not in own and r>=3:choices.add(EXPAND[name])
            self.equal({x['good'] for x in p['candidates']},choices,'unchanged_investment_permissions',q)
            calculated=[]
            for x in p['candidates']:
                g=x['good'];cost=development_cost(name,g,own.get(g,0));remaining=9-r
                marginal=2 if g in ('wheat','banana') else 1
                saturation=1+max(0,x['surplus']-x['need'])/max(1,2*x['need'])
                base=PRICE[g]*marginal*remaining/cost/saturation
                boost=1.8 if g in ('machine','electronics') and own.get(g,0)<3 else 1
                bonus=.30 if MAIN_GOODS[name]==g else 0;factor=.8 if g not in own else 1
                expected={'cost':cost,'remaining':remaining,'marginal':marginal,'saturation':saturation,
                    'base_price':PRICE[g],'original_boost':boost,'main_bonus':bonus,'expansion_factor':factor,
                    'score':(base+bonus)*factor+x['adaptive'],
                    'original_score_same_state':(base*boost+bonus)*factor+x['adaptive']}
                for f,v in expected.items():self.equal(x[f],v,'remove_only_durable_multiplier',(q,g,f))
                state=self.causal_state;cut=state.cutoff(r)
                need=state.world_need(g,r)
                surplus=sum(state.units[uid]['good']==g for uid in state.listed(r,cut,True))
                self.equal(x['need'],need,'unchanged_world_need_from_prelisting_state',(q,g))
                self.equal(x['surplus'],surplus,'prelisting_surplus_from_old_orders_and_transfers',(q,g))
                short=(sum(state.stock(n,r,cut,False,True)['electronics']<math.ceil((2+int(r>=5)+int(r>=8))/2)
                           for n in result['countries']) if g=='electronics' else 0)
                adaptive=min(1.8,short*.22) if g not in own and short>=3 and surplus==0 and r<=6 else 0
                self.equal(x['adaptive'],adaptive,'existing_expansion_signal_unchanged',(q,g))
                if x['adaptive']:
                    self.check(g=='electronics' and g not in own and r<=6 and x['surplus']==0,
                               'existing_expansion_flag_scope',(q,g))
                    self.check(0<x['adaptive']<=1.8,'existing_expansion_bonus_bound',(q,g))
                calculated.append((expected['score'],g))
            winner=max(calculated) if calculated else None
            threshold_applies=p['style']!='invest'
            selected=(winner[1] if winner and (not threshold_applies or winner[0]>=.45) else None)
            self.equal(p['threshold'],.45,'unchanged_normal_investment_threshold',q)
            self.equal(p['threshold_applies'],threshold_applies,'unchanged_invest_style_exception',q)
            self.equal(p['selected_base'],selected,'base_plan_selected_from_unboosted_scores',q)
            self.counts['causal_plan_snapshots']+=1

    def audit_causal_budgets(self,trace,result,context):
        policy=CAUSAL_POLICIES[result['mode']];captures=trace['causal_buy_log'];state=self.causal_state
        self.equal(result['world']['causal_buy_rows'],len(captures),'budget_capture_count',context)
        if not policy['operating_first']:
            self.equal(captures,[],'baseline_purchase_path_untouched',context)
            return
        expected_keys={(r,n,s) for r in range(1,10) for n in result['countries'] for s in (0,1)}
        self.equal({(p['round'],p['country'],p['sweep']) for p in captures},expected_keys,'every_original_buy_sweep_captured',context)
        self.equal(len(captures),len(expected_keys),'no_extra_negotiation_sweeps',context)
        previous_end=0
        for p in captures:
            r=p['round'];name=p['country'];cut=p['transaction_start'];end=p['transaction_end'];q=(context,r,name,p['sweep'])
            self.equal(cut,previous_end,'buy_windows_cover_transactions_without_overlap',q)
            self.check(0<=cut<=end<=len(state.tx),'valid_transaction_window',q)
            previous_end=end
            self.equal(p['cash_before'],state.cash_at(name,r,cut),'buyer_cash_from_prior_money_transfers',q)
            self.equal(p['cash_after'],state.cash_at(name,r,end),'buyer_ending_cash_from_money_transfers',q)
            self.equal(p['purchases_before'],state.purchases_at(name,cut),'buyer_prior_purchases_from_transactions',q)
            self.equal(p['purchases_after'],state.purchases_at(name,end),'buyer_ending_purchases_from_transactions',q)
            style=effective_style(result,name)
            inactive=style=='idle' or result['style']=='no_trade'
            if inactive:
                self.equal(p['rows'],[],'idle_or_trade_disabled_has_no_budget_rows',q)
                self.equal(p['allocation'],[],'idle_or_trade_disabled_has_no_allocation',q)
                self.equal(cut,end,'inactive_buy_phase_has_no_transactions',q)
                continue
            free=state.stock(name,r,cut,True);own=state.levels[(r,name)]
            self.equal(p['initial_stock'],free,'budget_uses_actual_free_unlisted_stock',q)
            food_need=1+int(r>=5)+int(r>=8);living_need=math.ceil((2+int(r>=5)+int(r>=8))/2)
            project=state.decisions[(r,name)]['selected'];lv=own.get(project,0) if project else 0
            cost=development_cost(name,project,lv) if project else 0
            grade=grade_required(own,project)
            research=(0 if lv<2 else 1 if lv==2 else 2)+int(project in ('machine','electronics') and lv>=2) if project else 0
            operating=state.raw(name,r,cut)
            self.equal(Counter(p['operating']),operating,'reserved_operating_need_from_installed_capacity_only',q)
            target=dict.fromkeys(GOODS,0);target.update(wheat=food_need,banana=food_need,electronics=living_need)
            target.update(operating)
            target['machine']=max(int(state.focus(name,r) in own and state.focus(name,r) not in ('machine','electronics')),int(bool(grade)))
            if project and p['cash_before']>=cost+20:
                target['ore']+=research;post=state.raw(name,r,cut,project)
                for raw in ('ore','fuel'):target[raw]=max(target[raw],post[raw]+(research if raw=='ore' else 0))
            self.equal(p['target'],target,'same_total_purchase_targets_not_invented_raw_demand',q)
            reserve=2*food_need*10+20
            held=state.held(name,r,cut,True)
            grades={g:[state.units[i]['gen'] for i in held if state.units[i]['good']==g] for g in ('machine','electronics')}
            prep=0
            if project:
                food_reserve=sum(max(0,food_need-free[g])*state.quote(g,1,r) for g in ('wheat','banana'))
                material=max(0,research-free['ore'])*state.quote('ore',1,r)
                if grade and max(grades['machine'],default=0)<grade:material+=state.quote('machine',grade,r)
                saving_expansion=project not in own and project=='electronics'
                if saving_expansion or p['cash_before']>=cost+reserve+material:
                    prep=min(cost,max(0,p['cash_before']-food_reserve-25))
            wallet=p['cash_before'];virtual=dict(free);expected=[]

            def allocate(g,want,mg=1,kind='need',hold=0,raw_goal=None):
                nonlocal wallet
                if want<=0:return
                price=state.price(name,g,mg,r,cut)
                cushion=0 if style=='invest' or g in ('wheat','banana') else 15
                quantity=min(want,max(0,wallet-hold-cushion)//price)
                budget=quantity*price
                row={'good':g,'want':want,'quantity':quantity,'unit_price':price,'budget':budget,'min_gen':mg,'kind':kind}
                if raw_goal is not None:row['raw_goal']=raw_goal
                expected.append(row);wallet-=budget;virtual[g]+=quantity
                if g in grades:grades[g]+=[mg]*quantity

            for g in ('wheat','banana'):allocate(g,max(0,target[g]-virtual[g]))
            for g in ('ore','fuel'):
                goal=min(target[g],operating[g]);allocate(g,max(0,goal-virtual[g]),kind='operating',raw_goal=goal)
            allocate('electronics',max(0,target['electronics']-virtual['electronics']))
            for g in ('ore','fuel'):allocate(g,max(0,target[g]-virtual[g]),kind='additional_raw',raw_goal=target[g])
            want=max(0,target['machine']-virtual['machine'])
            if grade and max(grades['machine'],default=0)<grade:want=max(1,want)
            allocate('machine',want,grade or 1,hold=cost+reserve if grade else prep)
            used=sorted(grades['electronics'],reverse=True)[:living_need]
            world_grade=max(u['gen'] for u in state.units.values() if u['good']=='electronics' and u['born']<=r)
            if r<=7 and len(used)==living_need and used and min(used)<world_grade:
                allocate('electronics',1,min(used)+1,'replacement',reserve+prep)
            self.equal(p['allocation'],expected,'virtual_wallet_reservations_independently_rebuilt',q)
            final=[]
            for g in ('wheat','banana','electronics','ore','fuel','machine'):
                parts=[x for x in expected if x['good']==g and x['kind']!='replacement']
                if not parts:continue
                if g in ('ore','fuel'):
                    final.append({'good':g,'want':max(0,target[g]-free[g]),'quantity':sum(x['quantity'] for x in parts),
                        'unit_price':parts[0]['unit_price'],'budget':sum(x['budget'] for x in parts),'min_gen':1,'kind':'need'})
                else:final.append(parts[0])
            final.extend(x for x in expected if x['kind']=='replacement')
            refusal=behavior(result,name)
            if refusal in ('no_machine','no_high_machine'):
                final=[x for x in final if not (x['good']=='machine' and x['min_gen']>=(1 if refusal=='no_machine' else 2))]
            if refusal in ('no_raw','no_ore','no_fuel'):
                blocked={'ore','fuel'} if refusal=='no_raw' else {refusal[3:]}
                final=[x for x in final if x['good'] not in blocked]
            self.equal(p['rows'],final,'same_execution_order_single_merged_raw_row',q)
            for g in ('ore','fuel'):
                self.check(sum(x['good']==g for x in p['rows'])<=1,'no_duplicate_raw_negotiation_row',(q,g))
            self.check(sum(x['budget'] for x in final)<=p['cash_before'],'one_finite_shared_budget',q)
            actual_spend=Counter()
            for tx in state.tx[cut:end]:
                self.equal(tx['round'],r,'buy_window_stays_in_round',q)
                if tx['cash']:
                    payer,payee,value=tx['cash']
                    self.equal(payer,name,'captured_actor_is_cash_buyer',q)
                    actual_spend[state.units[tx['legs'][0]['ids'][0]]['good']]+=value
            for g in GOODS:
                self.check(actual_spend[g]<=sum(x['budget'] for x in final if x['good']==g),
                           'actual_cash_spend_bounded_by_reserved_product_budget',(q,g))
            self.counts['causal_budget_snapshots']+=1
        self.equal(previous_end,len(state.tx),'all_transactions_in_original_buy_sweeps',context)

    def audit_decomposition_trace(self,trace,result,context):
        units=self.causal_state.units;cash=defaultdict(Counter);flows=defaultdict(Counter);origin=defaultdict(Counter)
        for t in trace['transactions']:
            for leg in t['legs']:
                classes={(units[i]['good'],units[i]['gen']) for i in leg['ids']}
                self.equal(len(classes),1,'each_transaction_leg_has_one_good_and_grade',(context,t['action_id']))
                g,gen=next(iter(classes));name=leg['seller'];key=(name,g)
                flows[key][str(gen)]+=len(leg['ids'])
                if t['cash']:
                    payer,payee,amount=t['cash']
                    self.equal((payer,payee),(leg['buyer'],name),'cash_transfer_matches_single_sales_leg',(context,t['action_id']))
                    cash[key][str(gen)]+=amount
                    for uid in leg['ids']:
                        u=units[uid]
                        category='resold_foreign' if u['origin']!=name else 'own_initial' if u['born']==0 else 'own_produced'
                        origin[key][category]+=amount/len(leg['ids'])
        for name,c in result['countries'].items():
            held=[u for u in units.values() if u['owner']==name];unused=used=0
            for u in held:
                ref=PRICE[u['good']]*((1,1.4,1.8)[u['gen']-1] if u['good'] in ('machine','electronics') else 1)
                if u['used']:used+=ref*(.5 if u['good'] in ('machine','electronics') else .15)
                else:unused+=ref*.15
            self.equal(c['growth_metrics']['unused_stock_value'],unused,'unused_asset_value_from_owned_uids',(context,name))
            self.equal(c['growth_metrics']['used_stock_value'],used,'used_asset_value_from_owned_uids',(context,name))
            for g,x in c['economic_decomposition'].items():
                key=(name,g);q=(context,name,g)
                grades=('1','2','3') if g in ('machine','electronics') else ('1',)
                self.equal(x['cash_sales_by_generation'],{gen:cash[key][gen] for gen in grades},'actual_cash_by_product_grade',q)
                self.equal(x['transferred_units_by_generation'],{gen:flows[key][gen] for gen in grades},'actual_cash_and_barter_units_by_grade',q)
                self.equal(x['cash_sale_origin'],{kind:origin[key][kind] for kind in ('own_produced','own_initial','resold_foreign')},
                           'sale_cash_split_by_uid_origin_not_assumed_factory_profit',q)
                raw={h:sum(len(n['used_ids']) for n in trace['needs_ledger']
                           if n['country']==name and n['purpose']==f'production:{g}' and n['good']==h) for h in ('ore','fuel')}
                self.equal(x['production_raw_inputs'],raw,'industry_inputs_are_actually_consumed_uids',q)
                investment=sum(e['cash_cost'] for e in trace['development'] if e['country']==name and e['industry']==g)
                self.equal(x['investment_cash'],investment,'industry_investment_from_real_events',q)
                self.counts['detailed_product_decompositions']+=1

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
                    required['ore' if (r+1)%2 else 'fuel']+=1+int(lv>=3)+int(lv>=2)*CAUSAL_POLICIES[result['mode']]['electronics_extra_raw']
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


def scenario(focal=None,style='normal',secondary=()):
    secondary=tuple(sorted(secondary))
    return f'{focal}:{style}'+''.join(f'+{n}:{s}' for n,s in secondary),focal,style,secondary


NORMAL=(scenario(),)
STRESS=NORMAL+tuple(scenario(n,s) for n in ORIGINAL for s in ('minimum','idle'))+(
    scenario('Technia','cheap'),scenario('Mechania','idle',(('Technia','minimum'),)),
    scenario('Mechania','idle',(('Novia','minimum'),)),
    scenario('Mineria','idle',(('Technia','minimum'),('Grainia','normal'))),
    scenario('Technia','idle',(('Mineria','minimum'),('Grainia','normal'))),
    scenario('Grainia','idle',(('Technia','minimum'),('Mineria','normal'))),scenario(None,'no_trade'),
)+tuple(scenario(n,s) for n in ('Mineria','Technia') for s in ('invest','trade'))
PHASES={
    'pilot_ai':(96000,30,AI_MODES,NORMAL),'pilot_economic':(96000,30,ECONOMIC_MODES,NORMAL),
    'main':(100000,100,tuple(CAUSAL_POLICIES),NORMAL),'stress':(102000,30,tuple(CAUSAL_POLICIES),STRESS),
}
MODE_PAIRS=(('baseline','operating_first'),('baseline','no_durable_boost'),('baseline','ai_combined'),
    ('baseline','electronics_input'),('ai_combined','combined_input'),('baseline','combined_input'))


def deep_equal(audit,actual,expected,label,context=()):
    if isinstance(expected,dict):
        audit.equal(set(actual),set(expected),label+'_keys',context)
        for key,value in expected.items():
            if key in actual:deep_equal(audit,actual[key],value,label,(*context,key))
    elif isinstance(expected,(tuple,list)):
        audit.equal(len(actual),len(expected),label+'_length',context)
        for i,(x,y) in enumerate(zip(actual,expected)):deep_equal(audit,x,y,label,(*context,i))
    else:audit.equal(actual,expected,label,context)


def check_schedule(audit,rows,phases):
    expected={}
    for phase in phases:
        start,n,modes,conditions=PHASES[phase]
        for mode in modes:
            for sid,focal,style,secondary in conditions:
                behaviors=dict(secondary)
                if focal is not None:behaviors[focal]=style
                for seed in range(start,start+n):
                    expected[(phase,mode,sid,seed)]={'phase':phase,'mode':mode,'scenario':sid,'seed':seed,
                        'focal':focal,'style':style,'behaviors':behaviors}
    actual={identity(row):row for row in rows}
    audit.equal(len(actual),len(rows),'unique_complete_scenario_identity')
    audit.equal(set(actual),set(expected),'exact_preregistered_modes_seeds_and_conditions')
    for key,row in actual.items():
        if key in expected:
            for field,value in expected[key].items():audit.equal(row[field],value,'identity_preserves_full_behavior_profile',(key,field))
    return actual


def check_sources_and_stages(audit,folder,stage):
    root=Path(__file__).resolve().parent
    provenance=read_json(root/'V12_PROVENANCE.json')
    audit.equal(len(provenance['files']),76,'inherited_v12_source_count')
    for name,digest in provenance['files'].items():audit.equal(sha(root/name),digest,'v12_source_byte_preserved',name)
    audit.equal(sha(root/'V12_FROZEN_GOALS.json'),GOALS_SHA256,'exact_previous_goal_file_not_refitted')
    goals=read_json(root/'V12_FROZEN_GOALS.json')
    audit.equal(goals['economic'],FROZEN_ECONOMIC,'fixed_economic_targets')
    audit.equal(goals['industrial'],FROZEN_INDUSTRIAL,'fixed_capacity_targets')
    rules=read_json(root/'rules_audit.json')
    audit.equal(rules['provenance']['manifest_sha256'],sha(root/'V12_PROVENANCE.json'),'rules_audit_links_unchanged_baseline')
    audit.equal(rules['provenance']['mismatches'],[],'rules_audit_found_no_source_change')
    opts=rules['runtime_settings']['options']
    for field,value in (('price_tick',1),('storage_fees',False),('bonus_inputs',False),('stock_discipline',False)):
        audit.equal(opts[field],value,'declared_existing_cost_baseline',field)
    audit.equal(rules['runtime_settings']['machinery_policy']['upkeep'],False,'no_hidden_maintenance_cost')
    for item in rules['sources']:
        if item['path'].startswith('trade_v13/'):
            audit.equal(sha(root/item['path'][len('trade_v13/'):]),item['sha256'],'rules_primary_current_source_hash',item['id'])
    declared=read_json(root/'CAUSAL_PROTOCOL_V13.json');plan=read_json(folder/'pre_run_plan.json')
    audit.equal(plan['declared_protocol'],declared,'executed_plan_contains_exact_declared_protocol')
    audit.equal(plan['declared_protocol_sha256'],sha(root/'CAUSAL_PROTOCOL_V13.json'),'declared_protocol_hash')
    audit.equal(plan['mode_policies'],CAUSAL_POLICIES,'six_predeclared_factor_settings')
    audit.equal(plan['fixed_goals_sha256'],GOALS_SHA256,'plan_keeps_old_targets')
    for key,value in (('pilot_ai_games',120),('pilot_economic_games',60),('pilot_games',180),('main_games',600),
        ('stress_games',4320),('formal_games',4920),('planned_games',5100),('formal_ledger_rows_per_type',398520),
        ('representative_traces',156),('countries',9),('rounds',9),('fixed_targets_refitted',False),
        ('pilot_not_formal_evidence',True),('formal_after_reviewed_freeze',True)):
        audit.equal(plan[key],value,'fixed_experiment_contract',key)
    audit.equal(plan['unique_identity_fields'],['phase','mode','scenario','seed'],'complete_identity_contract')
    audit.equal(plan['ranked_countries'],list(ORIGINAL),'original_six_only_ranked')
    audit.equal(plan['mode_comparisons'],[list(x) for x in MODE_PAIRS],'declared_mode_contrasts')
    audit.equal(plan['interaction'],{'ai_combined':1,'operating_first':-1,'no_durable_boost':-1,'baseline':1},'declared_factorial_interaction')
    for phase,(start,n,modes,conditions) in PHASES.items():
        p=plan['phases'][phase]
        audit.equal(p['seed_range'],[start,start+n-1],'declared_disjoint_phase_seeds',phase)
        audit.equal(p['n_per_condition'],n,'declared_phase_sample_size',phase)
        audit.equal(p['modes'],list(modes),'declared_phase_modes',phase)
        expected=[{'scenario':sid,'focal':focal,'style':style,'behaviors':dict(overrides)} for sid,focal,style,overrides in conditions]
        audit.equal(p['scenarios'],expected,'declared_phase_full_scenarios',phase)
    tests=read_json(folder/'tests_manifest.json')
    for field in ('passed','source_unchanged','tests_unchanged','inherited_unchanged'):
        audit.equal(tests[field],True,'recorded_regression_pass',field)
    for field in ('failures','errors','skipped'):audit.equal(tests[field],0,'no_failed_or_skipped_tests',field)
    audit.equal(tests['inherited_tests'],375,'all_inherited_tests_kept')
    audit.check(tests['test_count']>375,'new_boundary_tests_executed')
    current={'source_sha256':{n:sha(root/n) for n in tests['source_sha256']},
        'test_sha256':{n:sha(root/n) for n in tests['test_sha256']},
        'inherited_source_sha256':provenance['files'],'goals_sha256':GOALS_SHA256,
        'declared_protocol_sha256':sha(root/'CAUSAL_PROTOCOL_V13.json'),
        'run_plan_sha256':sha(folder/'pre_run_plan.json'),'tests_manifest_sha256':sha(folder/'tests_manifest.json')}
    for field in ('source_sha256','test_sha256','inherited_source_sha256'):
        audit.equal(tests[field],current[field],'tested_files_still_unchanged',field)
    ai=read_json(folder/'ai_pilot_manifest.json')
    for field,value in current.items():audit.equal(ai[field],value,'ai_pilot_used_tested_frozen_inputs',field)
    audit.equal(ai['completed_games'],120,'ai_pilot_count')
    audit.equal(ai['formal_games'],0,'ai_pilot_not_formal')
    audit.equal(ai['economic_pilot_not_executed'],True,'economic_pilot_was_not_run_at_first_stage_receipt')
    for key,file in (('runs_sha256','ai_pilot_runs.jsonl.gz'),('traces_sha256','ai_pilot_traces.json.gz')):
        audit.equal(ai[key],sha(folder/file),'unchanged_ai_pilot_records',file)
    audit.check(datetime.fromisoformat(ai['started_at'])<=datetime.fromisoformat(ai['completed_at']),'ai_pilot_timestamps')
    if stage=='ai-pilot':return plan,ai
    economic=read_json(folder/'economic_pilot_manifest.json');start=read_json(folder/'economic_pilot_start.json')
    freeze=read_json(folder/'freeze_manifest.json')
    for obj,label in ((economic,'economic_pilot'),(start,'economic_start'),(freeze,'formal_freeze')):
        for field,value in current.items():audit.equal(obj[field],value,'same_source_tests_targets_through_stages',(label,field))
    for obj in (economic,start):audit.equal(obj['approved_ai_pilot_sha256'],sha(folder/'ai_pilot_manifest.json'),'input_candidate_started_only_with_reviewed_ai_receipt')
    audit.equal(economic['economic_pilot_start_sha256'],sha(folder/'economic_pilot_start.json'),'input_pilot_start_receipt_hash')
    audit.equal(economic['completed_games'],60,'input_pilot_only_two_candidate_modes')
    audit.equal(economic['formal_games'],0,'input_pilot_not_formal')
    audit.equal(economic['pilot_games_total'],180,'both_pilots_total')
    for key,file in (('runs_sha256','economic_pilot_runs.jsonl.gz'),('traces_sha256','economic_pilot_traces.json.gz')):
        audit.equal(economic[key],sha(folder/file),'unchanged_input_pilot_records',file)
    links=(('ai_pilot_manifest_sha256','ai_pilot_manifest.json'),('economic_pilot_manifest_sha256','economic_pilot_manifest.json'),
        ('economic_pilot_start_sha256','economic_pilot_start.json'),('pilot_summary_sha256','pilot_summary.json'))
    for key,file in links:audit.equal(freeze[key],sha(folder/file),'frozen_reviewed_pilot_artifact',file)
    for key in ('pilot_runs_sha256','pilot_traces_sha256'):
        for file,digest in freeze[key].items():audit.equal(sha(folder/file),digest,'frozen_pilot_original_files',file)
    audit.equal(freeze['formal_not_executed'],True,'freeze_created_before_formal_execution')
    audit.equal(freeze['pilot_games'],180,'freeze_preserves_pilot_sample')
    audit.equal(freeze['formal_games_planned'],4920,'formal_sample_fixed_before_run')
    ordered=[ai['completed_at'],start['started_at'],economic['completed_at'],freeze['created_at']]
    audit.check(all(datetime.fromisoformat(a)<=datetime.fromisoformat(b) for a,b in zip(ordered,ordered[1:])),
                'ai_review_then_input_pilot_then_formal_freeze',ordered)
    if stage=='full':
        formal=read_json(folder/'formal_start.json');manifest=read_json(folder/'run_manifest.json')
        for obj,label in ((formal,'formal_start'),(manifest,'final_manifest')):
            for field,value in current.items():audit.equal(obj[field],value,'formal_execution_keeps_frozen_inputs',(label,field))
        audit.equal(formal['approved_freeze_sha256'],sha(folder/'freeze_manifest.json'),'formal_uses_reviewed_freeze')
        audit.equal(manifest['freeze_sha256'],sha(folder/'freeze_manifest.json'),'final_links_original_freeze')
        audit.equal(manifest['formal_start_sha256'],sha(folder/'formal_start.json'),'final_links_start_receipt')
        audit.equal(manifest['source_sha256_after'],current['source_sha256'],'source_unchanged_after_final')
        audit.equal(manifest['test_sha256_after'],current['test_sha256'],'tests_unchanged_after_final')
        audit.equal(manifest['tests_completed'],tests['test_count'],'final_uses_same_test_receipt')
        audit.equal(manifest['verification_failures'],0,'no_failed_invariant_checks')
        audit.equal(manifest['test_games_excluded'],True,'test_runs_excluded_from_sample')
        audit.equal(manifest['posthoc_reference_is_extra_game'],False,'score_reference_does_not_add_games')
        audit.check(datetime.fromisoformat(freeze['created_at'])<=datetime.fromisoformat(formal['started_at'])<=datetime.fromisoformat(manifest['completed_at']),
                    'formal_runs_after_freeze')
        review=read_json(folder/'independent_pilot_audit.json')
        audit.equal(review['status'],'passed','pilot_independent_audit_passed_before_formal')
        audit.equal(review['freeze_sha256'],sha(folder/'freeze_manifest.json'),'pilot_audit_reviewed_same_freeze')
        audit.check(datetime.fromisoformat(review['completed_at'])<=datetime.fromisoformat(formal['started_at']),
                    'pilot_independent_review_precedes_formal_start')
    return plan,freeze


def flatten(value,prefix=''):
    answer={}
    if isinstance(value,dict):
        for key,child in value.items():answer.update(flatten(child,f'{prefix}.{key}' if prefix else key))
    elif type(value) in (int,float):answer[prefix]=value
    return answer


def metric_statistics(values):
    values=list(values);count=len(values);mean=math.fsum(values)/count
    # A second numerical implementation of the declared sample-standard-error
    # formula. fsum avoids cancellation without repeating the runner's Fraction
    # based statistics internals for over a million saved summary metrics.
    spread=math.sqrt(math.fsum((x-mean)**2 for x in values)/(count-1)/count) if count>1 else 0
    return {'n':len(values),'mean':mean,'ci95':[mean-1.96*spread,mean+1.96*spread],'min':min(values),'max':max(values)}


def expected_contrasts(group_keys):
    definitions={}
    cohorts=[(phase,sid) for phase,conditions in (('main',NORMAL),('stress',STRESS)) for sid,*_ in conditions]
    if any(key.startswith('pilot_ai:') for key in group_keys):cohorts.insert(0,('pilot','None:normal'))
    def key(phase,mode,sid):
        if phase=='pilot':phase='pilot_ai' if mode in AI_MODES else 'pilot_economic'
        return f'{phase}:{mode}:{sid}'
    for phase,sid in cohorts:
        for left,right in MODE_PAIRS:
            a,b=key(phase,left,sid),key(phase,right,sid)
            if {a,b}<=group_keys:definitions[f'{phase}:{left}->{right}:{sid}']={'kind':'mode','terms':{a:-1,b:1}}
        terms={key(phase,m,sid):w for m,w in (('ai_combined',1),('operating_first',-1),('no_durable_boost',-1),('baseline',1))}
        if set(terms)<=group_keys:definitions[f'{phase}:ai_interaction:{sid}']={'kind':'interaction','terms':terms}
    for mode in CAUSAL_POLICIES:
        control=f'stress:{mode}:None:normal'
        if control not in group_keys:continue
        for sid,*_ in STRESS[1:]:definitions[f'stress:{mode}:{sid}']={'kind':'behavior','terms':{control:-1,f'stress:{mode}:{sid}':1}}
        for name in ('Technia','Novia'):
            sid=f'Mechania:idle+{name}:minimum'
            definitions[f'stress:{mode}:Mechania:idle->{sid}']={'kind':'compound_behavior','terms':{
                f'stress:{mode}:Mechania:idle':-1,f'stress:{mode}:{sid}':1}}
    return definitions


def audit_summary_file(audit,rows,summary,plan):
    groups=defaultdict(list)
    for row in rows:groups[f'{row["phase"]}:{row["mode"]}:{row["scenario"]}'].append(row)
    audit.equal(set(summary['experiments']),set(groups),'all_declared_groups_summarized')
    required={'causal','economic_decomposition','growth_metrics','growth_evaluation','routing','sale_by_good','purchase_by_good'}
    audit.check(required<=set(plan['country_summary_fields']),'causal_product_and_reference_metrics_not_dropped')
    vectors={};seeds={}
    for key,group in groups.items():
        group=sorted(group,key=lambda r:r['seed']);seeds[key]=[r['seed'] for r in group]
        samples=[]
        for row in group:
            selected={'countries':{n:{f:c[f] for f in plan['country_summary_fields']} for n,c in row['countries'].items()},
                'world':{f:row['world'][f] for f in plan['world_summary_fields']}}
            samples.append(flatten(selected))
        fields=set(samples[0])
        for sample in samples:audit.equal(set(sample),fields,'consistent_numeric_schema_each_group',key)
        vectors[key]={field:[sample[field] for sample in samples] for field in fields}
        actual=summary['experiments'][key]
        audit.equal(actual['n'],len(group),'aggregate_group_size',key)
        audit.equal(set(actual['metrics']),fields,'aggregate_metric_schema',key)
        for field,values in vectors[key].items():
            deep_equal(audit,actual['metrics'][field],metric_statistics(values),'independent_group_statistic',(key,field))
            audit.counts['group_metric_statistics']+=1
    definitions=expected_contrasts(set(groups))
    audit.equal(summary['contrast_definitions'],definitions,'exact_predeclared_paired_contrasts')
    audit.equal(set(summary['paired']),set(definitions),'no_missing_or_added_reported_contrasts')
    for key,definition in definitions.items():
        terms=definition['terms'];reference=seeds[next(iter(terms))]
        for group in terms:audit.equal(seeds[group],reference,'contrast_pairs_same_seeds',(key,group))
        fields=set.intersection(*(set(vectors[group]) for group in terms))
        audit.equal(set(summary['paired'][key]),fields,'contrast_numeric_schema',key)
        for field in fields:
            delta=[sum(weight*vectors[group][field][i] for group,weight in terms.items()) for i in range(len(reference))]
            deep_equal(audit,summary['paired'][key][field],metric_statistics(delta),'independent_paired_or_interaction_statistic',(key,field))
            audit.counts['paired_metric_statistics']+=1
    audit.counts['experiment_groups']+=len(groups);audit.counts['paired_contrasts']+=len(definitions)


def audit_saved_records(audit,rows,traces,phases,folder,full=False):
    lookup=check_schedule(audit,rows,phases)
    for row in rows:audit.run_summary(row)
    expected_traces={f'{phase}:{mode}:{sid}:{seed}' for phase,mode,sid,seed in lookup if seed==PHASES[phase][0]}
    audit.equal(set(traces),expected_traces,'predeclared_first_seed_traces_only')
    for key,t in traces.items():
        k=identity(t);row=lookup[k]
        for field in IDENTITY_FIELDS:audit.equal(t[field],row[field],'detailed_trace_full_identity',(k,field))
        audit.equal(t['result'],row,'detailed_trace_embeds_exact_saved_summary',k)
        audit.trace(t,row,key)
    if full:
        formal_keys={k for k in lookup if k[0] in ('main','stress')}
        for filename,method in (('round_ledgers.jsonl.gz',audit.ledger),('raw_round_ledgers.jsonl.gz',audit.raw_ledger)):
            seen=set();count=0
            with gzip.open(folder/filename,'rt') as stream:
                for line in stream:
                    obj=json.loads(line);k=identity(obj)
                    audit.check(k not in seen,'primary_ledger_identity_unique',(filename,k));seen.add(k)
                    audit.check(k in formal_keys,'ledger_is_formal_declared_trajectory',(filename,k))
                    row=lookup[k]
                    for field in IDENTITY_FIELDS:audit.equal(obj[field],row[field],'primary_ledger_complete_identity',(filename,k,field))
                    method(obj['rows'],row,k);count+=len(obj['rows'])
            audit.equal(seen,formal_keys,'all_formal_games_have_primary_ledger',filename)
            audit.equal(count,398520,'formal_country_round_ledger_row_count',filename)
        for prefix,phase in (('ai_pilot','pilot_ai'),('economic_pilot','pilot_economic')):
            for original in read_lines(folder/f'{prefix}_runs.jsonl.gz'):
                audit.equal(lookup[identity(original)],original,'final_file_preserves_frozen_pilot_raw_row',identity(original))
    return lookup


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path(__file__).parent/'causal_results')
    parser.add_argument('--stage',choices=('ai-pilot','pilot','full'),default='full')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();folder=args.results.resolve();root=Path(__file__).resolve().parent
    required=['pre_run_plan.json','tests_manifest.json','ai_pilot_manifest.json','ai_pilot_runs.jsonl.gz',
        'ai_pilot_traces.json.gz','ai_pilot_summary.json']
    if args.stage!='ai-pilot':required+=['economic_pilot_manifest.json','economic_pilot_start.json','economic_pilot_runs.jsonl.gz',
        'economic_pilot_traces.json.gz','pilot_summary.json','freeze_manifest.json']
    if args.stage=='full':required+=['run_manifest.json','formal_start.json','runs.jsonl.gz','first_seed_traces.json.gz',
        'round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','summary.json','independent_pilot_audit.json']
    missing=[name for name in required if not (folder/name).exists()]
    if missing:
        print(json.dumps({'status':'pending_final_results','stage':args.stage,'missing':missing}));return 0
    audit=Audit();started=datetime.now(timezone.utc).isoformat()
    plan,freeze=check_sources_and_stages(audit,folder,args.stage)
    if args.stage=='full':
        rows=read_lines(folder/'runs.jsonl.gz');traces=read_json(folder/'first_seed_traces.json.gz')
        phases=tuple(PHASES);summary=read_json(folder/'summary.json');manifest=read_json(folder/'run_manifest.json')
    else:
        rows=read_lines(folder/'ai_pilot_runs.jsonl.gz');traces=read_json(folder/'ai_pilot_traces.json.gz')
        phases=('pilot_ai',);summary=read_json(folder/'ai_pilot_summary.json');manifest=read_json(folder/'ai_pilot_manifest.json')
        if args.stage=='pilot':
            rows+=read_lines(folder/'economic_pilot_runs.jsonl.gz');traces.update(read_json(folder/'economic_pilot_traces.json.gz'))
            phases+=('pilot_economic',);summary=read_json(folder/'pilot_summary.json');manifest=read_json(folder/'economic_pilot_manifest.json')
    audit.equal(summary['metadata'],manifest,'summary_metadata_exact_run_receipt')
    audit_saved_records(audit,rows,traces,phases,folder,full=args.stage=='full')
    audit_summary_file(audit,rows,summary,plan)
    if args.stage=='full':
        audit.equal(manifest['completed_games'],len(rows),'all_saved_games_count')
        audit.equal(manifest['formal_games'],sum(r['phase'] in ('main','stress') for r in rows),'formal_games_count')
        audit.equal(manifest['verification_calls'],sum(r['world']['verify_calls'] for r in rows),'recorded_invariant_call_sum')
        audit.equal(manifest['formal_verification_calls'],sum(r['world']['verify_calls'] for r in rows if r['phase'] in ('main','stress')),
                    'formal_only_invariant_call_sum')
    else:
        audit.equal(manifest['verification_calls'],sum(r['world']['verify_calls'] for r in rows if r['phase']==phases[-1]),'stage_invariant_call_sum')
    output=args.out or folder/({'ai-pilot':'independent_ai_pilot_audit.json','pilot':'independent_pilot_audit.json','full':'independent_audit.json'}[args.stage])
    report={'schema':'v13-independent-causal-audit-1','status':'failed' if audit.errors else 'passed','stage':args.stage,
        'started_at':started,'completed_at':datetime.now(timezone.utc).isoformat(),'checks_evaluated':audit.checks,
        'errors':audit.errors,'audit_counts':dict(audit.counts),'unique_games_audited':len(rows),
        'pilot_games_audited':sum(r['phase'].startswith('pilot') for r in rows),
        'formal_games_audited':sum(r['phase'] in ('main','stress') for r in rows),'detailed_traces':len(traces),
        'inherited_source_files':76,'fixed_goals_sha256':GOALS_SHA256,
        'rules_audit_sha256':sha(root/'rules_audit.json'),'auditor_sha256':sha(Path(__file__)),
        'freeze_sha256':sha(folder/'freeze_manifest.json') if (folder/'freeze_manifest.json').exists() else None,
        'formal_started_at_audit':(folder/'formal_start.json').exists(),
        'scope':{'summaries':'All saved trajectories: cash, physical totals, causal opportunities, product decomposition, unchanged legacy scores and fixed v12 reference.',
            'primary_ledgers':'All formal main and stress games only; both cash and raw country-round ledgers.' if args.stage=='full' else 'Pilot representative detailed traces include their 81 cash and raw country-round rows; no full pilot primary-ledger files are claimed.',
            'detailed':'Predeclared first-seed traces only: UID provenance, physical use, development and routing, operating budget reservations, investment weighting, actual sales/input decomposition.',
            'statistics':'All saved experiment means, ranges and 95% intervals; same-seed policy, behavior and factorial-interaction contrasts.',
            'not_claimed':['No economic engine rerun by this auditor.','No UID reconstruction for unsaved detailed trajectories.',
                'No proof of optimal automatic decisions, equal country difficulty, student learning or classroom pacing.',
                'Cash sales minus purchases is not manufacturing profit; physical raw use is not cost-of-goods-sold.',
                'The six-mode design is a complete 2x2 AI comparison plus two input comparisons, not a full eight-cell three-factor experiment.']},
        'artifacts_checked':{name:sha(folder/name) for name in required}}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda x:sorted(x,key=repr) if isinstance(x,set) else repr(x))+'\n')
    print(json.dumps({'status':report['status'],'stage':args.stage,'checks':audit.checks,'errors':len(audit.errors),
        'games':len(rows),'traces':len(traces),'report':str(output)},ensure_ascii=False),flush=True)
    return int(bool(audit.errors))


if __name__=='__main__':raise SystemExit(main())
