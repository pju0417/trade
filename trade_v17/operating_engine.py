"""National operating-resource experiments on the preserved v13 economy.

Whole physical bundles are settled on fixed public dates. This is an explicit
periodic-settlement abstraction, not fractional prepaid service or daily energy
use. No starting grant, price, production recipe or scoring formula is changed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, asdict
import math
from pathlib import Path
import statistics
import sys

SOURCE=Path(__file__).resolve().parent/'source_v13'
if str(SOURCE) not in sys.path:sys.path.insert(0,str(SOURCE))
from causal_engine import Game as PreviousGame
from reference_engine import FOOD, DURABLES, GOODS

RAW=('ore','fuel')


@dataclass(frozen=True)
class OperatingPolicy:
    fuel_rounds: tuple[int,...]
    ore_rounds: tuple[int,...]
    fuel_penalty: int=8
    ore_penalty: int=4


PROFILES={
    'none':OperatingPolicy((),()),
    'light':OperatingPolicy((3,6,9),(4,8)),
    'regular':OperatingPolicy((2,4,6,8),(3,6,9)),
    'daily':OperatingPolicy(tuple(range(1,10)),(3,6,9)),
}


class Game(PreviousGame):
    def __init__(self,seed=0,mode='baseline',operating_profile='none',focal=None,
                 style='normal',trade_enabled=True,behaviors=None):
        if operating_profile not in PROFILES:raise ValueError('Unknown operating profile')
        self.operating_profile=operating_profile
        self.operating_policy=PROFILES[operating_profile]
        self.operating_ledger=[]
        self.operating_use_log=[]
        self.operating_plan_log=[]
        self._operating_initializing=True
        super().__init__(seed,mode=mode,focal=focal,style=style,
                         trade_enabled=trade_enabled,behaviors=behaviors)
        self._operating_initializing=False

    def operating_required(self,c,r=None,unsettled=True):
        r=self.r if r is None else r
        if (self._operating_initializing or r<1 or r>9 or
                (unsettled and (r,c.name) in self.settled)):
            return {'ore':0,'fuel':0}
        return {g:int(r in getattr(self.operating_policy,g+'_rounds')) for g in RAW}

    def targets(self,c):
        base=super().targets(c)
        due=self.operating_required(c)
        return {g:base[g]+due.get(g,0) for g in GOODS}

    def world_potential_need(self,g):
        base=super().world_potential_need(g)
        if self._operating_initializing or self.operating_profile=='none' or g not in RAW or self.r>=9:
            return base
        # Public remaining obligations averaged per future round; no target/plan
        # recursion and no price-based refitting. All nations have the same dates.
        remaining=range(max(1,self.r+1),10)
        per_country=sum(r in getattr(self.operating_policy,g+'_rounds') for r in remaining)
        return base+len(self.cs)*per_country/max(1,9-self.r)

    def purchase_plan(self,c):
        due=self.operating_required(c)
        if self.operating_profile=='none' or not any(due.values()):return super().purchase_plan(c)
        if c.style=='idle' or not self.opt.trade_enabled:return []
        target=self.targets(c);initial={g:self.count(c,g) for g in GOODS}
        virtual=dict(initial);wallet=c.cash;rows=[];by_good={};requested=Counter()
        grades={g:[self.units[i].gen for i in self.ids(c,g)] for g in DURABLES}
        project=self.plan(c);mg=self.upgrade_requirements(c,project)[1] if project else 0

        def allocate(g,want,min_gen=1,kind='need',hold=0,basic=False):
            nonlocal wallet
            if want<=0:return
            offers=[o.price for o in self.orders.values() if o.good==g and o.gen>=min_gen and o.seller!=c.name]
            price=min(offers) if offers else self.quote(g,min_gen)
            cushion=0 if basic or c.style=='invest' or g in FOOD else 15
            qty=min(want,max(0,wallet-cushion-hold)//price);budget=qty*price
            part={'purpose':kind,'want':want,'quantity':qty,'budget':budget}
            if kind!='replacement' and g in by_good:
                row=by_good[g]
                assert row['unit_price']==price and row['min_gen']==min_gen
                row['want']+=want;row['quantity']+=qty;row['budget']+=budget
                row['budget_parts'].append(part)
                if kind!=row['kind']:row['kind']='national_and_need'
            else:
                row={'good':g,'want':want,'quantity':qty,'unit_price':price,'budget':budget,
                     'min_gen':min_gen,'kind':kind,'budget_parts':[part]}
                rows.append(row)
                if kind!='replacement':by_good[g]=row
            requested[g]+=want;wallet-=budget;virtual[g]+=qty
            if g in DURABLES:grades[g]+=[min_gen]*qty

        for g in FOOD:allocate(g,max(0,target[g]-initial[g]))
        for g in ('fuel','ore'):
            allocate(g,max(0,due[g]-initial[g]),kind='national',basic=True)
        for g in ('electronics','ore','fuel','machine'):
            # Subtract previously REQUESTED basic quantities, not affordable
            # quantities: an unaffordable request must not be counted twice.
            want=max(0,target[g]-initial[g]-requested[g])
            grade=mg if g=='machine' and mg else 1
            if g=='machine' and mg and max(grades[g],default=0)<mg:want=max(1,want)
            hold=0
            if g=='machine':hold=self.upgrade_cost(c,project)+self.reserve(c) if mg else self.prep_budget(c)
            allocate(g,want,grade,hold=hold)
        if self.flag('upgrade_living_goods') and self.r<=7:
            want=math.ceil(self.pop()/2);used=sorted(grades['electronics'],reverse=True)[:want]
            if len(used)==want and used and min(used)<self.global_gen['electronics']:
                allocate('electronics',1,min(used)+1,'replacement',self.reserve(c)+self.prep_budget(c))
        assert sum(x['budget'] for x in rows)<=c.cash
        assert len([x['good'] for x in rows if x['kind']!='replacement'])==len(set(x['good'] for x in rows if x['kind']!='replacement'))
        for g in RAW:
            if g in by_good:assert by_good[g]['want']==max(0,target[g]-initial[g])
        self.operating_plan_log.append({'round':self.r,'country':c.name,'cash':c.cash,
            'profile':self.operating_profile,'due':due,'available':initial,'target':target,
            'legacy_target':{g:target[g]-due.get(g,0) for g in GOODS},'rows':deepcopy(rows)})
        return rows

    def _raw_counts(self,name,good,round_number=None):
        values=super()._raw_counts(name,good,round_number)
        values['national']=sum(e['country']==name and e['good']==good and e['purpose']=='national'
            and (round_number is None or e['round']==round_number) for e in self.raw_use_log)
        assert values['consumed']==values['production']+values['research']+values['national']
        return values

    def settle_round(self,c):
        if (self.r,c.name) in self.settled:return False
        due=self.operating_required(c)
        pre={'cash':c.cash,'tax':c.tax,'minted':self.minted,'need_slots':c.need_slots}
        available={g:self.count(c,g) for g in RAW}
        owned={g:self.count(c,g,False) for g in RAW}
        own={g:sum(self.units[i].origin==c.name for i in self.ids(c,g,False)) for g in RAW}
        old_use=len(self.raw_use_log)
        # Preserve the complete prior household settlement and income, then make
        # exactly one same-round correction to that income after the new needs.
        # This avoids copying or skipping inherited food/living need semantics.
        result=super().settle_round(c)
        assert result is True
        base_happy=c.happy;base_tax=c.tax-pre['tax']
        used_ids={};evidence={};consumed={};missing={}
        for g in RAW:
            ids=self.ids(c,g)[:due[g]];used_ids[g]=list(ids)
            evidence[g]=[{'uid':i,'good':self.units[i].good,'origin':self.units[i].origin,
                'born':self.units[i].born,'owner_before':self.units[i].owner,
                'order_before':self.units[i].order,'last_import':self.units[i].last_import} for i in ids]
            self.record_need(c,g,due[g],'national',ids)
            actual=self.consume(c,g,len(ids),'national') if ids else []
            assert actual==ids
            c.need_slots+=due[g]
            consumed[g]=len(ids);missing[g]=due[g]-len(ids)
        penalty=sum(getattr(self.operating_policy,g+'_penalty')*missing[g]/due[g]
                    for g in RAW if due[g])
        final_happy=round(max(0,base_happy-penalty),6)
        final_tax=10+int(math.floor(final_happy/10+.5))
        difference=final_tax-base_tax
        c.happy=final_happy;c.happiness[-1]=final_happy
        c.tax+=difference;c.cash+=difference;self.minted+=difference
        self._observe_cash()
        for e in self.raw_use_log[old_use:]:
            if e['purpose']=='national':self.operating_use_log.append(dict(e))
        row={'round':self.r,'country':c.name,'profile':self.operating_profile,
             'required':due,'consumed':consumed,'missing':missing,
             'available_before':available,'stock_before':owned,
             'stock_after':{g:self.count(c,g,False) for g in RAW},
             'own_origin_before':own,'used_ids':used_ids,'used_unit_evidence':evidence,
             'base_happy':base_happy,'happy':final_happy,'penalty':penalty,
             'base_tax':base_tax,'round_income':final_tax,'tax_effect':difference,
             'cash_before':pre['cash'],'cash_after':c.cash,
             'tax_before':pre['tax'],'tax_after':c.tax,
             'minted_before':pre['minted'],'minted_after':self.minted,
             'need_slots_before':pre['need_slots'],'need_slots_after':c.need_slots}
        assert row['cash_after']-row['cash_before']==final_tax
        assert row['tax_after']-row['tax_before']==final_tax
        assert row['minted_after']-row['minted_before']==final_tax
        assert all(row['stock_before'][g]-row['stock_after'][g]==consumed[g] for g in RAW)
        self.operating_ledger.append(row)
        return True

    def verify(self):
        result=super().verify()
        assert len(self.operating_ledger)==len({(e['round'],e['country']) for e in self.operating_ledger})
        assert len(self.operating_use_log)==len({e['uid'] for e in self.operating_use_log})
        for e in self.operating_use_log:
            u=self.units[e['uid']]
            assert u.owner is None and u.used and u.use_purpose=='national'
        return result

    def summary(self):
        result=super().summary()
        for name,c in self.cs.items():
            rows=[e for e in self.operating_ledger if e['country']==name]
            assert len(rows)==9
            q={key:{g:sum(e[key][g] for e in rows) for g in RAW}
               for key in ('required','consumed','missing')}
            q.update(shortage_rounds={g:sum(e['missing'][g]>0 for e in rows) for g in RAW},
                any_shortage_rounds=sum(any(e['missing'].values()) for e in rows),
                penalty_total=sum(e['penalty'] for e in rows),
                penalty_mean=statistics.mean(e['penalty'] for e in rows),
                base_happy_mean=statistics.mean(e['base_happy'] for e in rows),
                final_happy_mean=statistics.mean(e['happy'] for e in rows),
                tax_effect=sum(e['tax_effect'] for e in rows))
            result['countries'][name]['national_operation']=q
            result['countries'][name]['national_operation_origin_used']={g:sum(u.origin==name and u.born>0 and u.good==g and u.used and u.use_purpose=='national' for u in self.units.values()) for g in RAW}
        world={key:{g:sum(x['national_operation'][key][g] for x in result['countries'].values()) for g in RAW}
               for key in ('required','consumed','missing','shortage_rounds')}
        world.update({k:sum(x['national_operation'][k] for x in result['countries'].values())
                      for k in ('any_shortage_rounds','penalty_total','tax_effect')})
        world['profile']=self.operating_profile
        result['world']['national_operation']=world
        result['world']['national_operation_scope']={
            'policy':asdict(self.operating_policy),'physical_rule_changed':self.operating_profile!='none',
            'whole_bundle_scheduled_settlement':True,'population_scaled':False,
            'new_score_feedback':False,'extra_starting_grants':False,
            'daily_profile_stress_tested':False,
            'note':'Periodic basic-operation demand, separate from production and development; original score targets retained.'}
        return result

    def trace(self):
        out=super().trace()
        out.update(operating_ledger=self.operating_ledger,operating_use=self.operating_use_log,
                   operating_plans=self.operating_plan_log,operating_profile=self.operating_profile,
                   operating_policy=asdict(self.operating_policy))
        return out
