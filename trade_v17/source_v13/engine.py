"""#11 v3: independently switched price, marginal-input and aged-stock experiments.

Pure Python serial economic model, not a classroom web app. All input coefficients
below are DESIGN TRIALS, not empirical estimates. Production safety net, starting
conditions, 9 rounds, durable generations and score formulas remain unchanged.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import Counter, defaultdict
import math
import core_engine as core
from core_engine import NAMES, GOODS, PRICE, FOOD, DURABLES, CONFIG, INVEST, BONUS, clip, half_up5

# (unused rounds free, tenths of G per aged EXCESS trade-unit per round).
# One trade-unit is an abstract game bundle, not one banana vs one real machine.
STORAGE = {'banana': (2,5), 'wheat': (3,2), 'ore': (4,2),
           'fuel': (3,4), 'machine': (3,6), 'electronics': (3,4)}
# Optional extra-output recipe: one physical raw material funds this many bonus
# output units. Residual capacity stays with THIS industry; no free loan or debt.
BONUS_RECIPE = {'banana': ('fuel',6), 'wheat': ('fuel',6),
                'ore': ('fuel',3), 'fuel': ('ore',3),
                'machine': ('ore',1), 'electronics': ('ore',1)}

@dataclass(frozen=True)
class Options(core.Options):
    price_tick: int = 5
    bonus_inputs: bool = False
    storage_fees: bool = False
    stock_discipline: bool = False
    storage_cap: int = 5
    def __post_init__(self):
        if type(self.price_tick) is not int or self.price_tick not in (1,5):
            raise ValueError('price_tick must be 1 or 5')
        if type(self.storage_cap) is not int or not 0 <= self.storage_cap <= 20:
            raise ValueError('storage_cap must be integer 0..20')

class Game(core.Game):
    def __init__(self,*a,**kw):
        # mint is called by super().__init__.
        self.residency = {}
        self.acquisition_events = []
        self.bonus_credit = Counter()
        self.bonus_raw = Counter()
        self.bonus_output = Counter()
        self.cost_events = []
        self.production_log = []
        self.storage_history = []
        self.storage_paid = Counter()
        self.storage_fraction = Counter()
        self.storage_settled = set()
        self.skipped_bonus = Counter()
        self.blocked_bonus = Counter()
        self.operation_inputs = Counter()
        super().__init__(*a,**kw)

    def mint(self,c,g,n,gen=1,initial=False):
        before=self.uid
        result=super().mint(c,g,n,gen,initial)
        for uid in range(before+1,self.uid+1):
            self.residency[uid] = {c.name:max(1,self.r)}
        return result

    def settle_transaction(self,legs,cash,channel,action_id):
        old=len(self.transactions)
        ok=super().settle_transaction(legs,cash,channel,action_id)
        if ok and len(self.transactions)>old:
            for leg in legs:
                for uid in leg['ids']:
                    # New owner gets grace. Returning to an old owner never resets
                    # that owner's original clock (anti round-trip fee avoidance).
                    self.residency[uid].setdefault(leg['buyer'],max(1,self.r))
            self.acquisition_events.append((self.r,action_id))
        return ok

    def consume(self,c,g,n,purpose):
        result=super().consume(c,g,n,purpose)
        self.operation_inputs[(c.name,purpose,g)]+=n
        return result

    def _bonus_preview(self,c,g):
        """Pure forecast: does NOT spend raw resources or fractional output carry."""
        focused=c.focus==g
        extra=(2 if self.opt.smaller_bonus and g in FOOD else BONUS[g]) if focused else 0
        uid=None; remainder=c.bonus_buffer.get(g,0)
        if g not in DURABLES and focused:
            uid=self.machine_assignments(c).get(g)
            if uid:
                gap=min(2,max(0,self.global_gen['machine']-self.units[uid].gen))
                val=remainder+(1 if self.opt.smaller_bonus else 2)*(1,.8,.6)[gap]
                extra+=int(val+1e-9);remainder=val-int(val+1e-9)
        return extra,uid,remainder

    def _overstock(self,c,g):
        # Observable own stock + one-cycle needs only, no access to rivals' cash.
        if g in FOOD: protect=self.food_need(min(9,self.r+1))
        elif g=='electronics': protect=math.ceil(self.pop()/2)
        elif g=='machine': protect=self.equip_slots(c)
        else:
            protect=sum(core.Game.resource_requirements(self,c,h,min(9,self.r+1)).get(g,0)
                        for h in c.levels)
        return self.count(c,g,False)-protect > 2*self.base_quantity(c,g)

    def next_resources(self,c):
        ans=super().next_resources(c)
        if self.r>=9 or not self.opt.bonus_inputs:
            return ans
        for g in c.levels:
            if self.opt.stock_discipline and c.style not in ('idle','invest') and self._overstock(c,g):
                continue
            extra,_,_=self._bonus_preview(c,g)
            raw,yield_n=BONUS_RECIPE[g]
            remaining=max(0,extra-self.bonus_credit[(c.name,g)])
            ans[raw]+=math.ceil(remaining/yield_n)
        return ans

    def _spend_bonus_inputs(self,c,g,wanted):
        raw,yield_n=BONUS_RECIPE[g];key=(c.name,g)
        need=math.ceil(max(0,wanted-self.bonus_credit[key])/yield_n)
        have=min(need,self.count(c,raw))
        if need:
            self.record_need(c,raw,need,f'bonus:{g}',self.ids(c,raw)[:have])
            c.need_slots+=need
        if have:
            self.consume(c,raw,have,'bonus_production')
            self.bonus_credit[key]+=have*yield_n
            self.bonus_raw[(c.name,g,raw)]+=have
        allowed=min(wanted,self.bonus_credit[key])
        self.bonus_credit[key]-=allowed
        self.bonus_output[key]+=allowed
        self.blocked_bonus[key]+=wanted-allowed
        self.cost_events.append({'round':self.r,'country':c.name,'industry':g,
           'kind':'bonus_inputs','raw':raw,'consumed':have,'requested_raw':need,
           'output_requested':wanted,'output_actual':allowed,
           'credit_after':self.bonus_credit[key],
           'raw_value_reference':have*PRICE[raw], 'cash_charged_on_use':0})
        return allowed

    def production(self):
        if not self.opt.bonus_inputs and not self.opt.stock_discipline:
            return super().production()
        if self.r in self.produced_rounds: return False
        staged=[]
        for c in self.cs.values():
            # All regular industrial cycles have first call on shared inputs.
            # Optional bonuses never silently consume another industry's base inputs.
            normal=[]
            for g,lv in c.levels.items():
                req=self.resource_requirements(c,g)
                enough=all(self.count(c,h)>=n for h,n in req.items())
                for h,n in req.items():
                    self.record_need(c,h,n,f'production:{g}',self.ids(c,h)[:n] if enough else [])
                c.need_slots+=sum(req.values())
                if enough:
                    for h,n in req.items(): self.consume(c,h,n,'production')
                    base=self.base_quantity(c,g);gen=self.tech_for(c,g)
                else:
                    base=1;gen=1;c.production_failures+=1
                normal.append((g,base,gen,enough))
            for g,base,gen,enough in normal:
                wanted,uid,remainder=self._bonus_preview(c,g)
                if not enough: wanted=0
                pause=(self.opt.stock_discipline and c.style not in ('idle','invest') and self._overstock(c,g))
                if pause:
                    self.skipped_bonus[(c.name,g)]+=wanted;wanted=0
                extra=self._spend_bonus_inputs(c,g,wanted) if self.opt.bonus_inputs and wanted else wanted
                if uid and extra>0:
                    self.record_need(c,'machine',1,f'equipment:{g}',[uid])
                    self.mark_use(c,uid,'equipment');c.need_slots+=1
                    c.bonus_buffer[g]=remainder
                elif g not in DURABLES and c.focus==g and not pause:
                    self.record_need(c,'machine',1,f'equipment:{g}',[])
                staged.append((c,g,base+extra,gen))
                self.production_log.append({'round':self.r,'country':c.name,'good':g,
                    'base':base,'bonus':extra,'generation':gen,'guaranteed_fallback':not enough,
                    'paused_bonus':pause})
        for c,g,q,gen in staged: self.mint(c,g,q,gen)
        for g in DURABLES:
            observed=max((u.gen for u in self.units.values() if u.good==g),default=1)
            if observed>self.global_gen[g]:self.launch_events.append({'round':self.r,'good':g,'generation':observed})
            self.global_gen[g]=observed
        self.produced_rounds.add(self.r);return True

    def plan(self,c):
        # Narrow agent-side filter, not a prohibition on student investments.
        # Apply only to expensive capacity expansion with an own inventory surplus.
        pg=super().plan(c)
        if (self.opt.stock_discipline and c.style not in ('idle','invest') and pg in c.levels
                and self._overstock(c,pg)):
            self.plan_cache[(self.r,c.name)]=None
            return None
        return pg

    def _protected_ids(self,c):
        protected=set()
        # Real use this round; 'ever used' alone is not enough for permanent exemption.
        for r,n,uid,purpose in self.use_episodes:
            if r==self.r and n==c.name and purpose in ('equipment','living','development'):
                if uid in c.stock and self.units[uid].order is None:
                    protected.add(uid)
        # Still-active life support and equipment are protected between rounds too.
        current_living=sorted(self.ids(c,'electronics'),key=lambda i:(-self.units[i].gen,i))[:math.ceil(self.pop()/2)]
        protected.update(current_living)
        for good,uid in self.machine_assignments(c).items():
            if good==c.focus and good not in DURABLES:protected.add(uid)
        # ONE round of necessities, counted whether listed or in warehouse. Oldest
        # quantities protected first; register/cancel cannot increase exemption.
        need=Counter({g:self.food_need(min(9,self.r+1)) for g in FOOD})
        need.update(self.next_resources(c))
        pg=self.plan(c)
        if pg and c.cash>=self.upgrade_cost(c,pg)+self.reserve(c):
            raw,mg=self.upgrade_requirements(c,pg);need['ore']+=raw
            if mg:
                candidates=self.ids(c,'machine',min_gen=mg)
                if candidates:protected.add(candidates[0])
        for g,num in need.items():
            ids=sorted(self.ids(c,g,False),key=lambda i:(self.residency[i][c.name],i))
            protected.update(ids[:num])
        return protected

    def storage_preview(self,c):
        # No state mutations in this calculator, including the cached plan.
        old_cache=self.plan_cache.copy()
        try: protected=self._protected_ids(c)
        finally:self.plan_cache=old_cache
        eligible=Counter();excluded=Counter();ids=[];tenths=0
        for uid in sorted(c.stock):
            u=self.units[uid];grace,rate=STORAGE[u.good]
            age=self.r-self.residency[uid][c.name]
            if uid in protected or age<grace:
                excluded[u.good]+=1;continue
            eligible[u.good]+=1;ids.append(uid);tenths+=rate
        whole=(tenths+self.storage_fraction[c.name])//10
        paid=min(whole,self.opt.storage_cap,c.cash)
        return {'round':self.r,'country':c.name,'eligible':dict(eligible),
          'excluded':dict(excluded),'unit_ids':ids,'raw_tenths':tenths,
          'fraction_before':self.storage_fraction[c.name], 'uncapped_integer':whole,
          'due':paid,'waived':whole-paid,'fraction_after':(tenths+self.storage_fraction[c.name])%10}

    def charge_storage(self,c):
        if not self.opt.storage_fees:return False
        key=(self.r,c.name)
        if key in self.storage_settled:return False
        if key not in self.settled:raise ValueError('settle consumption and income before storage')
        row=self.storage_preview(c)
        c.cash-=row['due'];self.sunk+=row['due'];self.storage_paid[c.name]+=row['due']
        self.storage_fraction[c.name]=row['fraction_after']
        self.storage_history.append(row);self.storage_settled.add(key)
        return True

    def settle_round(self,c):
        result=super().settle_round(c)
        if result:self.charge_storage(c)
        return result

    def verify(self):
        result=super().verify()
        for n,c in self.cs.items():
            assert c.cash==c.start+c.revenue-c.purchases-c.investment+c.tax-self.storage_paid[n], 'country cash ledger'
            assert 0<=self.storage_fraction[n]<10
        assert self.sunk==sum(c.investment for c in self.cs.values())+sum(self.storage_paid.values()), 'separate sinks'
        for c in self.cs.values():
            for g in GOODS:
                raw,yield_n=BONUS_RECIPE[g];key=(c.name,g)
                assert self.bonus_raw[(c.name,g,raw)]*yield_n == self.bonus_output[key]+self.bonus_credit[key], 'bonus input conservation'
                assert 0<=self.bonus_credit[key]<yield_n
            for uid in c.stock:assert c.name in self.residency[uid]
        assert len(self.storage_history)==len(self.storage_settled)
        return result

    def summary(self):
        result=super().summary()
        for n,c in self.cs.items():
            x=result['countries'][n]
            x['storage_paid']=self.storage_paid[n]
            x['cash_flow']-=self.storage_paid[n]
            x['bonus_input_value']=sum(q*PRICE[g] for (cn,ind,g),q in self.bonus_raw.items() if cn==n)
            x['bonus_units']=sum(q for (cn,g),q in self.bonus_output.items() if cn==n)
            x['blocked_bonus']=sum(q for (cn,g),q in self.blocked_bonus.items() if cn==n)
            x['paused_bonus']=sum(q for (cn,g),q in self.skipped_bonus.items() if cn==n)
            x['food_short_rounds']=9-len(c.satisfied_rounds)
            # Important: these are cash outlays by product, not a claim of COGS.
            x['purchase_by_good']={g:sum(t['cash'][2] for t in self.transactions if t['cash'] and t['cash'][0]==n and self.units[t['legs'][0]['ids'][0]].good==g) for g in GOODS}
            x['inputs_used']={purpose:{g:self.operation_inputs[(n,purpose,g)] for g in ('ore','fuel')} for purpose in ('production','bonus_production','development')}
        w=result['world']
        w['investment']=sum(c.investment for c in self.cs.values())
        w['storage_paid']=sum(self.storage_paid.values());w['external_sinks']=self.sunk
        w['happy']=sum(x['happy'] for x in result['countries'].values())/6
        w['food_short_rounds']=sum(x['food_short_rounds'] for x in result['countries'].values())
        w['unique_used']=sum(u.born>0 and u.used for u in self.units.values())
        w['old_unused']=sum(u.owner is not None and not u.used and self.r-u.born>=2 for u in self.units.values())
        w['score_gap']=max(x['score'] for x in result['countries'].values())-min(x['score'] for x in result['countries'].values())
        w['storage_charge_events']=len(self.storage_history)
        w['bonus_blocked']=sum(self.blocked_bonus.values());w['bonus_paused']=sum(self.skipped_bonus.values())
        w['goods_usable_current']=sum(u.owner is not None and u.used for u in self.units.values())
        w['unique_used_by_good']={g:sum(u.born>0 and u.used and u.good==g for u in self.units.values()) for g in GOODS}
        w['fixed_inventory_value']=sum(self.unit_ref(u) for u in self.units.values() if u.owner is not None)
        w['fixed_unused_value']=sum(self.unit_ref(u) for u in self.units.values() if u.owner is not None and not u.used)
        w['upgrades']=sum(c.upgrades for c in self.cs.values())
        w['production_failures']=sum(c.production_failures for c in self.cs.values())
        w['cash_gap']=max(c.cash for c in self.cs.values())-min(c.cash for c in self.cs.values())
        w['prepaid_bonus_credit']=sum(self.bonus_credit.values())
        w['low_cash_rounds']=sum(x['low_cash_rounds'] for x in result['countries'].values())
        w['extra_raw_inputs']={g:sum(v for (n,industry,h),v in self.bonus_raw.items() if h==g) for g in ('ore','fuel')}
        return result
