"""v6: actual machine output, variable materials, and optional use-based service.

Experimental game abstractions, not estimated real-world coefficients.
Unchanged v5 balanced is the exact baseline. Potential industrial capacity,
prices, starting countries, investment rules/costs and score formulas stay v5.
No automatic buyer, scrap refund, loan or forced equipment replacement exists.
"""
from __future__ import annotations
from collections import Counter
from copy import copy
from dataclasses import dataclass
import math, statistics
from budget_trace import Game as V5
from reference_engine import GOODS, FOOD, DURABLES, BONUS


@dataclass(frozen=True)
class MachineryPolicy:
    demand_output: bool = False
    variable_materials: bool = False
    upkeep: bool = False


MODES = {
    'baseline': MachineryPolicy(),
    'quantity': MachineryPolicy(demand_output=True),
    'recipe': MachineryPolicy(variable_materials=True),
    'coupled': MachineryPolicy(demand_output=True, variable_materials=True),
    'service': MachineryPolicy(demand_output=True, variable_materials=True, upkeep=True),
}
# Game trial only: two material-work credits per physical raw bundle.
# G1's first unit is the inherited free basic-production allowance. G2 uses
# one credit/unit; G3 uses two. Credits are prepaid, pinned to producer/raw/grade.
CREDITS_PER_RAW = 2
UPKEEP_USES = 3


class Game(V5):
    def __init__(self,seed=0,mode='baseline',focal=None,style='normal',trade_enabled=True):
        if mode not in MODES:raise ValueError('unknown machinery mode')
        self.mode = mode
        self.machinery_policy = MODES[mode]
        self.refuse_raw_country = focal if style == 'no_raw' else None
        self.material_credit = Counter()
        self.material_events = []
        self.machine_output_log = []
        self.equipment_output_log = []
        self.upkeep_wear = Counter()
        self.upkeep_log = []
        self.replacement_screen = []
        super().__init__(seed,variant='balanced',focal=focal,
                         style='normal' if style=='no_raw' else style,
                         trade_enabled=trade_enabled)

    def own_machine_sales(self,c,production_round,gen):
        """Own completed trade only; no rival inventory, cash or future orders."""
        rounds = range(max(1,production_round-2),production_round)
        count = 0
        for tx in self.transactions:
            if tx['round'] not in rounds:continue
            for leg in tx['legs']:
                if leg['seller'] != c.name:continue
                count += sum(self.units[i].good=='machine' and self.units[i].origin==c.name
                             and self.units[i].gen==gen for i in leg['ids'])
        return count / max(1,len(rounds))

    def machine_quantity(self,c,production_round,actual=False):
        """One stock plan used by buying, hypothetical investment and production.

        Planning reserves up to the focus-capable ceiling. Actual output is
        bounded by the focus selected for that production round. Hence a later
        focus change cannot require MORE materials than the reserved plan.
        """
        if 'machine' not in c.levels or production_round>9:return 0
        maximum = self.base_quantity(c,'machine')+BONUS['machine']
        cap = self.base_quantity(c,'machine')+(BONUS['machine'] if c.focus=='machine' else 0) if actual else maximum
        if not self.machinery_policy.demand_output:return cap
        gen = self.tech_for(c,'machine')
        target = 1+math.ceil(self.own_machine_sales(c,production_round,gen))
        # Includes listed, previously-used and imported qualifying stock. Relist
        # and cancellation cannot conceal stock or restart the launch allowance.
        available = self.count(c,'machine',False,min_gen=gen)
        want = max(0,target-available)
        first = not any(u.origin==c.name and u.good=='machine' and u.gen==gen and u.born>0
                        for u in self.units.values())
        if first:want=max(1,want)
        return min(cap,want)

    def material_plan(self,c,production_round,quantity=None):
        if quantity is None:quantity=self.machine_quantity(c,production_round)
        gen = self.tech_for(c,'machine')
        old = super().resource_requirements(c,'machine',production_round)
        raw = next(iter(old))
        key = (c.name,raw,gen)
        if not quantity:
            return {'quantity':0,'generation':gen,'raw':raw,'required':{},'key':key,
                    'credits_before':self.material_credit[key],'credits_spent':0,
                    'raw_spent':0,'credits_after':self.material_credit[key]}
        if not self.machinery_policy.variable_materials:
            return {'quantity':quantity,'generation':gen,'raw':raw,'required':dict(old),'key':key,
                    'credits_before':0,'credits_spent':0,'raw_spent':old[raw],'credits_after':0}
        spent = max(0,quantity-1) if gen==1 else quantity*(1 if gen==2 else 2)
        before = self.material_credit[key]
        batches = math.ceil(max(0,spent-before)/CREDITS_PER_RAW)
        return {'quantity':quantity,'generation':gen,'raw':raw,
                'required':{raw:batches} if batches else {},'key':key,
                'credits_before':before,'credits_spent':spent,'raw_spent':batches,
                'credits_after':before+CREDITS_PER_RAW*batches-spent}

    def resource_requirements(self,c,g,r=None):
        if self.mode=='baseline' or g!='machine':return super().resource_requirements(c,g,r)
        r=self.r if r is None else r
        return self.material_plan(c,r)['required']

    def upkeep_requirement(self,c,forecast=False):
        if not self.machinery_policy.upkeep:return Counter()
        # Forecast may precede next focus selection. Reserve for one possible
        # nonindustrial support slot; unused physical raw stays in inventory.
        possible = any(g not in DURABLES for g in c.levels) if forecast else c.focus in c.levels and c.focus not in DURABLES
        if not possible:return Counter()
        ids=sorted(self.ids(c,'machine'),key=lambda i:(-self.units[i].gen,i))
        if ids and self.upkeep_wear[ids[0]]>=UPKEEP_USES-1:return Counter({'ore':1})
        return Counter()

    def next_resources(self,c):
        if self.mode=='baseline':return super().next_resources(c)
        if self.r>=9:return Counter()
        need=Counter()
        for good in c.levels:need.update(self.resource_requirements(c,good,self.r+1))
        need.update(self.upkeep_requirement(c,forecast=True))
        return need

    def projected_resources(self,c,project=None):
        if self.mode=='baseline':return super().projected_resources(c,project)
        if self.r>=9:return Counter()
        p=copy(c);p.levels=dict(c.levels);p.bases=dict(c.bases)
        if project:
            level=p.levels.get(project,0)+1;p.levels[project]=level;p.bases.setdefault(project,1)
            if project=='machine':p.machine_tech=min(3,level)
            if project=='electronics':p.elec_tech=min(3,level)
        need=Counter()
        for good in p.levels:need.update(self.resource_requirements(p,good,self.r+1))
        need.update(self.upkeep_requirement(p,forecast=True))
        return need

    def settle_transaction(self,legs,cash,channel,action_id):
        # A diagnostic agent preference, not a ban for other countries. Reject
        # both money and barter imports so this stress really means no raw input.
        if self.refuse_raw_country and isinstance(legs,list):
            for leg in legs:
                if isinstance(leg,dict) and leg.get('buyer')==self.refuse_raw_country:
                    ids=leg.get('ids',[])
                    if not isinstance(ids,list):return False
                    if any(i in self.units and self.units[i].good in ('ore','fuel')
                           for i in ids if type(i) is int):return False
        return super().settle_transaction(legs,cash,channel,action_id)

    def purchase_plan(self,c):
        rows=super().purchase_plan(c)
        if c.name==self.refuse_raw_country:return [r for r in rows if r['good'] not in ('ore','fuel')]
        return rows

    def production(self):
        if self.mode=='baseline':
            if self.r in self.produced_rounds:return super().production()
            first_uid=self.uid
            result=super().production()
            for c in self.cs.values():
                if c.focus in c.levels and c.focus not in DURABLES:
                    good=c.focus
                    extra=sum(u.origin==c.name and u.good==good for i,u in self.units.items() if i>first_uid)
                    focused_bonus=2 if self.opt.smaller_bonus and good in FOOD else BONUS[good]
                    extra-=self.base_quantity(c,good)+focused_bonus
                    supported=any(r==self.r and n==c.name and p=='equipment' for r,n,i,p in self.use_episodes)
                    self.equipment_output_log.append({'round':self.r,'country':c.name,'industry':good,
                        'supported':supported,'extra_output':max(0,extra)})
                if 'machine' not in c.levels:continue
                rows=[r for r in self.production_trace if r['round']==self.r and r['country']==c.name and r['industry']=='machine']
                row=rows[-1]
                made=[u for i,u in self.units.items() if i>first_uid and u.origin==c.name and u.good=='machine']
                cap=self.base_quantity(c,'machine')+(BONUS['machine'] if c.focus=='machine' else 0)
                gen=made[0].gen
                self.machine_output_log.append({'round':self.r,'country':c.name,'generation':gen,
                    'planned_generation':self.tech_for(c,'machine'),'capacity':cap,'planned':cap,
                    'produced':len(made),'status':'regular' if row['funded'] else 'fallback',
                    'raw_required':row['required'],'raw_used':row['required'] if row['funded'] else {},
                    'g1_paid_for_only_basic':bool(len(made)==1 and gen==1 and row['required'] and row['funded'])})
            return result
        if self.r in self.produced_rounds:return False
        staged=[]
        # Complete every country's input/equipment decision before minting any
        # new output: same-round new ore can never fund another country's output.
        for c in self.cs.values():
            assignments=self.machine_assignments(c)
            for good,level in c.levels.items():
                base=self.base_quantity(c,good)
                bonus=BONUS[good] if c.focus==good else 0
                if self.opt.smaller_bonus and good in FOOD and bonus:bonus=2
                gen=self.tech_for(c,good)
                cap=base+bonus
                q=self.machine_quantity(c,self.r,actual=True) if good=='machine' else cap
                materials=self.material_plan(c,self.r,q) if good=='machine' else None
                req=materials['required'] if materials is not None else self.resource_requirements(c,good)
                available={g:self.count(c,g) for g in GOODS}
                enough=all(available[g]>=n for g,n in req.items())
                self.production_trace.append({'round':self.r,'country':c.name,'industry':good,
                    'level':level,'tech':gen,'required':dict(req),'available_before':available,
                    'funded':enough,'following_input_deferral':False,
                    'planned_quantity':q,'potential_quantity':cap,'planned_pause':q==0})
                for raw,n in req.items():
                    self.record_need(c,raw,n,f'production:{good}',self.ids(c,raw)[:n] if enough else [])
                c.need_slots+=sum(req.values())
                status='paused' if q==0 else 'regular'
                produced=q
                if not enough:
                    produced=1;gen=1;bonus=0
                    c.production_failures+=1;status='fallback'
                else:
                    for raw,n in req.items():self.consume(c,raw,n,'production')
                    if materials is not None and self.machinery_policy.variable_materials:
                        self.material_credit[materials['key']]=materials['credits_after']
                        self.material_events.append({'round':self.r,'country':c.name,**materials})
                if good not in DURABLES and c.focus==good:
                    uid=assignments.get(good)
                    supported=bool(uid)
                    extra=0
                    if uid and self.machinery_policy.upkeep:
                        before=self.upkeep_wear[uid]
                        due=before>=UPKEEP_USES-1
                        serviced=not due or self.count(c,'ore')>=1
                        if due:
                            chosen=self.ids(c,'ore')[:1] if serviced else []
                            self.record_need(c,'ore',1,'equipment_maintenance',chosen)
                            if serviced:self.consume(c,'ore',1,'maintenance')
                        if serviced:self.upkeep_wear[uid]=0 if due else before+1
                        supported=serviced
                        self.upkeep_log.append({'round':self.r,'country':c.name,'industry':good,'unit':uid,
                            'wear_before':before,'due':due,'serviced':serviced,'ore_used':int(due and serviced),
                            'wear_after':self.upkeep_wear[uid]})
                    self.record_need(c,'machine',1,f'equipment:{good}',[uid] if supported else [])
                    if supported:
                        self.mark_use(c,uid,'equipment');c.need_slots+=1
                        gap=min(2,max(0,self.global_gen['machine']-self.units[uid].gen))
                        carry=c.bonus_buffer.get(good,0)+(1 if self.opt.smaller_bonus else 2)*(1,.8,.6)[gap]
                        extra=int(carry+1e-9);c.bonus_buffer[good]=carry-extra;produced+=extra
                    self.equipment_output_log.append({'round':self.r,'country':c.name,'industry':good,
                        'supported':supported,'extra_output':extra})
                staged.append((c,good,produced,gen))
                if good=='machine':
                    self.machine_output_log.append({'round':self.r,'country':c.name,'generation':gen,
                        'planned_generation':self.tech_for(c,good),'capacity':cap,'planned':q,
                        'produced':produced,'status':status,'raw_required':dict(req),
                        'raw_used':dict(req) if enough else {},
                        'g1_paid_for_only_basic':bool(q==1 and gen==1 and sum(req.values()) and enough)})
        for c,g,q,gen in staged:
            if q:self.mint(c,g,q,gen)
        for good in DURABLES:
            observed=max((u.gen for u in self.units.values() if u.good==good),default=1)
            if observed>self.global_gen[good]:self.launch_events.append({'round':self.r,'good':good,'generation':observed})
            self.global_gen[good]=observed
        self.produced_rounds.add(self.r)
        return True

    def choose_focus(self,c):
        if not self.machinery_policy.demand_output or c.style in ('idle','invest'):
            return super().choose_focus(c)
        if not self.opt.planning:return super().choose_focus(c)
        target=self.targets(c)
        def value(good):
            bonus=BONUS[good]
            if good=='machine':
                # A paused/stock-limited plant gains nothing from a focus slot.
                # Keep the rule's capacity bonus; correct only the agent choice.
                planned=self.machine_quantity(c,min(9,self.r+1))
                bonus=max(0,planned-self.base_quantity(c,good))
            return (self.quote(good)*bonus/(1+self.count(c,good,False)*.3)
                    +max(0,target[good]-self.count(c,good,False))*10)
        c.focus=max(c.levels,key=value)

    def screen_replacement(self,c):
        """Diagnostic yield-only screen, NO purchase and NO promised sales.

        Even every extra output is valued at today's reference, with no demand
        discount. A positive number is not proof of profitable replacement.
        Current focus and normal working condition are held fixed. This is not
        an upper bound on every replacement motive (maintenance, research or
        later focus changes are excluded). No hypothetical resale receipt.
        """
        if self.r>=9 or c.style=='idle' or c.focus not in c.levels or c.focus in DURABLES:return
        ids=sorted(self.ids(c,'machine'),key=lambda i:(-self.units[i].gen,i))
        if not ids:return
        old=self.units[ids[0]].gen
        offers=[o for o in self.orders.values() if o.good=='machine' and o.seller!=c.name and o.gen>old]
        for grade in sorted({o.gen for o in offers}):
            price=min(o.price for o in offers if o.gen==grade)
            horizon=9-self.r
            def output(gen):
                gap=min(2,max(0,self.global_gen['machine']-gen))
                return math.floor(c.bonus_buffer.get(c.focus,0)+horizon*(1,.8,.6)[gap]+1e-9)
            extra=max(0,output(grade)-output(old))
            value=extra*self.quote(c.focus)
            self.replacement_screen.append({'round':self.r,'country':c.name,'industry':c.focus,
                'old_generation':old,'new_generation':grade,'horizon':horizon,
                'extra_units_upper_bound':extra,'output_value_upper_bound':value,
                'listed_price':price,'possible_on_yield_alone':value>price,
                'cash_affordable':c.cash>=price+self.reserve(c)})

    def update_prices(self):
        result=super().update_prices()
        for c in self.cs.values():self.screen_replacement(c)
        return result

    def verify(self):
        result=super().verify()
        assert all(type(v) is int and 0<=v<CREDITS_PER_RAW for v in self.material_credit.values())
        assert all(type(v) is int and 0<=v<UPKEEP_USES for v in self.upkeep_wear.values())
        for e in self.material_events:
            assert e['credits_after']==e['credits_before']+CREDITS_PER_RAW*e['raw_spent']-e['credits_spent']
        if self.mode!='baseline':
            assert all(x['produced']==0 and not x['raw_used'] for x in self.machine_output_log if x['status']=='paused')
            assert all(x['generation']==1 and x['produced']==1 for x in self.machine_output_log if x['status']=='fallback')
            assert all(x['produced']<=x['capacity'] for x in self.machine_output_log)
        return result

    def summary(self):
        result=super().summary()
        for n,c in self.cs.items():
            x=result['countries'][n]
            logs=[r for r in self.machine_output_log if r['country']==n]
            x['machine_pauses']=sum(r['status']=='paused' for r in logs)
            x['machine_planned']=sum(r['planned'] for r in logs)
            x['machine_capacity_total']=sum(r['capacity'] for r in logs)
            x['machine_fallbacks']=sum(r['status']=='fallback' for r in logs)
            x['paid_for_basic_only']=sum(r['g1_paid_for_only_basic'] for r in logs)
            x['machine_upkeep_ore']=self.operation_inputs[(n,'maintenance','ore')]
            x['upkeep_blocked']=sum(r['country']==n and r['due'] and not r['serviced'] for r in self.upkeep_log)
            x['material_work_left']=sum(v for (name,raw,gen),v in self.material_credit.items() if name==n)
            x['machine_needed_episodes']=sum(r['needed'] for r in self.needs_ledger if r['country']==n and r['good']=='machine')
            x['machine_missing_episodes']=sum(max(0,r['needed']-len(r['used_ids'])) for r in self.needs_ledger if r['country']==n and r['good']=='machine')
            x['imported_machine_used']=sum(self.units[i].good=='machine' for i in c.useful_imports)
            x['machine_stock_by_gen']={str(gen):sum(self.units[i].good=='machine' and self.units[i].gen==gen for i in c.stock) for gen in (1,2,3)}
            x['machine_produced_by_gen']={str(gen):sum(u.good=='machine' and u.origin==n and u.born>0 and u.gen==gen for u in self.units.values()) for gen in (1,2,3)}
            x['machine_unique_used']=x['use_by_good']['machine']
            x['machine_unique_used_including_initial']=sum(u.good=='machine' and u.origin==n and u.used for u in self.units.values())
            x['equipment_use_episodes']=sum(1 for r,k,i,p in self.use_episodes if r<=self.r and k==n and p=='equipment')
            x['equipment_extra_output']=sum(row['extra_output'] for row in self.equipment_output_log if row['country']==n)
            x['upgrades_total']=c.upgrades
        w=result['world']
        for key in ('machine_pauses','machine_planned','machine_capacity_total','machine_fallbacks',
                    'paid_for_basic_only','machine_upkeep_ore','upkeep_blocked','machine_needed_episodes',
                    'machine_missing_episodes','machine_unique_used','machine_unique_used_including_initial',
                    'equipment_use_episodes','equipment_extra_output','imported_machine_used','material_work_left'):
            w[key]=sum(x[key] for x in result['countries'].values())
        w['all_country_cash_gap']=max(c.cash for c in self.cs.values())-min(c.cash for c in self.cs.values())
        w['machine_launch_rounds']={str(gen):min((u.born for u in self.units.values() if u.good=='machine' and u.gen==gen and u.born>0),default=10) for gen in (2,3)}
        w['replacement_screen_count']=len(self.replacement_screen)
        w['replacement_screen_positive']=sum(x['possible_on_yield_alone'] for x in self.replacement_screen)
        w['replacement_screen_positive_affordable']=sum(x['possible_on_yield_alone'] and x['cash_affordable'] for x in self.replacement_screen)
        w['v6_score_note']='Original-six diagnostic goals unchanged. Reduced output changes utilization denominator; do not equate score gain with fairness.'
        return result

    def trace(self):
        out=super().trace()
        out.update(machine_output=self.machine_output_log,material_events=self.material_events,
                   equipment_output=self.equipment_output_log,
                   upkeep=self.upkeep_log,replacement_screen=self.replacement_screen,
                   units={i:vars(u) for i,u in self.units.items()})
        return out
