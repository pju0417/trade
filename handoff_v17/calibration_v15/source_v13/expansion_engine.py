"""#11 controlled 6-vs-9 country experiment. Serial, rule-based agents only.
Upstream economic engine is not edited. Same 1G-price profile, 9 rounds, no
storage fee / optional bonus input / specialist discount / free market buyer.
New country parameters are design hypotheses, not empirically fitted facts.
"""
from __future__ import annotations
import math
from collections import Counter
from itertools import combinations
from copy import deepcopy
import statistics
from engine import Game as Upstream, Options
from reference_engine import Nation, CONFIG, NAMES, GOODS, FOOD, DURABLES, PRICE, BONUS, ECON_GOAL, GROWTH_GOAL, clip, half_up5

BASE_OPTIONS=Options(planning=True,negotiations=True,price_v2=True,
    saturation_aware=True,smaller_bonus=True,price_tick=1)
ADDITIONS={
 'Novia':(185,{'electronics':1,'wheat':1},'electronics','machine'),
 'Agrea':(175,{'banana':2,'fuel':1},'banana','ore'),
 'Ferria':(175,{'ore':1,'wheat':2},'ore','machine'),
}
LABELS=dict(zip(NAMES,('트로피아','그레니아','오일리아','메카니아','미네리아','테크니아')),
 Novia='노비아',Agrea='아그레아',Ferria='페리아')
COMBINATIONS=tuple(combinations(NAMES,3))

class Game(Upstream):
    def __init__(self,seed=0,scenario='six',focal=None,style='normal',
                 fixes=True,trade_enabled=True):
        from dataclasses import replace
        if scenario not in ('six','clones','roles'):
            raise ValueError('scenario must be six, clones or roles')
        self.scenario=scenario;self.fixed_plans=fixes
        self.role_of={n:n for n in NAMES}
        self.config=deepcopy(CONFIG)
        self.purchase_plans=[]
        super().__init__(seed,replace(BASE_OPTIONS,trade_enabled=trade_enabled),focal=focal,style=style)
        if scenario=='clones':
            extra={f'Clone{i+1}':deepcopy(CONFIG[role]) for i,role in enumerate(COMBINATIONS[seed%20])}
            self.role_of.update({f'Clone{i+1}':role for i,role in enumerate(COMBINATIONS[seed%20])})
        elif scenario=='roles':
            extra=deepcopy(ADDITIONS)
            self.role_of.update({n:n for n in extra})
        else:extra={}
        for name,(cash,bases,main,expand) in extra.items():
            self.config[name]=(cash,bases.copy(),main,expand)
            c=Nation(name,cash,cash,bases.copy(),main,expand,
                style if name==focal else 'normal',levels={g:1 for g in bases},focus=main)
            self.cs[name]=c
            for good in FOOD:self.mint(c,good,2,initial=True)
            # The same one-cycle starter allowance for any initial industrial nation.
            if any(g in DURABLES for g in bases):
                self.mint(c,'ore',1,initial=True);self.mint(c,'fuel',1,initial=True)
                self.mint(c,'machine',1,initial=True)
            self.initial_assets[name]=c.cash+self.stock_value(c)
            self.initial_capacity[name]=self.capacity(c)
            self.initial_cash+=cash
        self.verify()

    def resource_requirements(self,c,g,r=None):
        role=self.role_of.get(c.name,c.name)
        if role!='Mechania' or c.name=='Mechania':return super().resource_requirements(c,g,r)
        if g!='machine':return super().resource_requirements(c,g,r)
        return {'ore':1+(c.levels[g]>=3)+(c.machine_tech>=2)}

    def upgrade_cost(self,c,g):
        role=self.role_of.get(c.name,c.name)
        if c.name in NAMES or role not in ('Mechania','Technia') or g!='machine':
            return super().upgrade_cost(c,g)
        from reference_engine import INVEST
        lv=c.levels.get(g,0)
        cost=INVEST[g]*(1 if lv<2 else 1.5 if lv==2 else 2)*(.75 if role=='Mechania' else 1.25)
        return half_up5(cost)

    def equip_slots(self,c):
        if not self.fixed_plans:return super().equip_slots(c)
        # Only one focused non-industrial facility actually receives equipment
        # output in the current simulator. Do not invent a second passive benefit.
        return int(c.focus in c.levels and c.focus not in DURABLES)

    def machine_assignments(self,c):
        if not self.fixed_plans:return super().machine_assignments(c)
        if not self.equip_slots(c):return {}
        ids=sorted(self.ids(c,'machine'),key=lambda i:(-self.units[i].gen,i))
        return {c.focus:ids[0]} if ids else {}

    def targets(self,c):
        t=super().targets(c)
        if self.fixed_plans:
            pg=self.plan(c)
            research=int(bool(pg and self.upgrade_requirements(c,pg)[1]))
            t['machine']=max(self.equip_slots(c),research)
        return t

    def world_potential_need(self,g):
        if len(self.cs)==6:return super().world_potential_need(g)
        n=len(self.cs)
        if g in FOOD:return n*self.food_need(min(9,self.r+1))
        if g in ('ore','fuel'):return sum(self.next_resources(c)[g] for c in self.cs.values())+n/3
        if g=='machine':return sum(self.equip_slots(c) for c in self.cs.values())/3+n/2
        return sum(math.ceil(self.pop()/2) for c in self.cs.values())

    def purchase_plan(self,c):
        """One pure budgeting function for forecast AND order execution.
        Price estimate uses publicly listed cheapest qualifying quote, or reference
        when none is listed. Unfilled/changed availability may prevent execution.
        Barter is allowed even when allocated cash is zero. No budget injection.
        """
        if c.style=='idle' or not self.opt.trade_enabled:return []
        wallet=c.cash;t=self.targets(c);plan=[]
        virtual={g:self.count(c,g) for g in GOODS}
        grades={g:[self.units[i].gen for i in self.ids(c,g)] for g in DURABLES}
        pg=self.plan(c);mg=self.upgrade_requirements(c,pg)[1] if pg else 0
        def add(g,want,min_gen=1,kind='need',hold=0):
            nonlocal wallet
            if want<=0:return
            offers=[o.price for o in self.orders.values() if o.good==g and o.gen>=min_gen and o.seller!=c.name]
            price=min(offers) if offers else self.quote(g,min_gen)
            cushion=0 if c.style=='invest' or g in FOOD else 15
            cap=max(0,wallet-cushion-hold)
            qty=min(want,cap//price)
            budget=qty*price
            plan.append({'good':g,'want':want,'quantity':qty,'unit_price':price,
                         'budget':budget,'min_gen':min_gen,'kind':kind})
            wallet-=budget;virtual[g]+=qty
            if g in DURABLES:grades[g]+= [min_gen]*qty
        # Priority is explicit and identical in market demand and buying. Preserve
        # next-cycle production before optional life-quality replacement/support.
        for g in ('wheat','banana','ore','fuel','electronics','machine'):
            need=max(0,t[g]-virtual[g])
            grade=mg if g=='machine' and mg else 1
            if g=='machine' and mg and max(grades[g],default=0)<mg:need=max(1,need)
            hold=0
            if g=='machine':
                hold=(self.upgrade_cost(c,pg)+self.reserve(c)) if mg else self.prep_budget(c)
            add(g,need,grade,hold=hold)
        if self.flag('upgrade_living_goods') and self.r<=7:
            needed=math.ceil(self.pop()/2)
            used=sorted(grades['electronics'],reverse=True)[:needed]
            if len(used)==needed and used and min(used)<self.global_gen['electronics']:
                add('electronics',1,min(used)+1,'replacement',self.reserve(c)+self.prep_budget(c))
        assert sum(x['budget'] for x in plan)<=c.cash
        return plan

    def demand_snapshot(self):
        if not self.fixed_plans:return super().demand_snapshot()
        d=Counter();s=Counter();plans={}
        for o in self.orders.values():s[o.good]+=len(o.units)
        for c in self.cs.values():
            rows=self.purchase_plan(c);plans[c.name]=rows
            if c.style=='idle':continue
            raw=sum(self.need(c,h) for h in GOODS)
            c.external_need_units+=raw
            if raw:c.external_need_rounds.add(self.r)
            for row in rows:d[row['good']]+=row['quantity']
        self.snapshots.append({'round':self.r,'demand':dict(d),'supply':dict(s)})
        self.purchase_plans.append({'round':self.r,'plans':plans})

    def buy_phase(self,c,sweep):
        if not self.fixed_plans:return super().buy_phase(c,sweep)
        for row in self.purchase_plan(c):
            g=row['good'];want=row['want'];mg=row['min_gen'];budget=min(c.cash,row['budget'])
            got=0;start=c.purchases
            if self.opt.negotiations and g not in FOOD and (row['quantity']<want or sweep%2):
                got=self.negotiate(c,g,want,min_gen=mg,budget=budget,tag=f'pre{sweep}')
            left=want-got;remaining=max(0,budget-(c.purchases-start))
            if left:
                q=self.market_buy(c,g,left,min(remaining,c.cash),min_gen=mg,tag=f'market{sweep}')
                got+=q;left-=q
            if left:
                remaining=max(0,budget-(c.purchases-start))
                got+=self.negotiate(c,g,left,min_gen=mg,budget=min(c.cash,remaining),tag=f'post{sweep}')
            if row['kind']=='replacement':self.replacement_purchases[c.name]+=got

    def summary(self):
        """Count-agnostic metrics. Existing six goals kept; new nations NOT ranked.
        The original six scores are diagnostic only (not calibrated for nine).
        Raw transactions, ultimate use, conserved cash and shortages are primary.
        """
        countries={};tradegoods=Counter();flow=Counter()
        for t in self.transactions:
            for leg in t['legs']:
                flow[(leg['seller'],leg['buyer'])]+=len(leg['ids'])
                for uid in leg['ids']:tradegoods[self.units[uid].good]+=1
        for name,c in self.cs.items():
            produced=[u for u in self.units.values() if u.origin==name and u.born>0]
            used=[u for u in produced if u.used]
            exported_used=[u for u in produced if self.foreign_uses.get(u.uid)]
            er={r for u in exported_used for r,_ in self.foreign_uses[u.uid]}
            rows=[x for x in self.needs_ledger if x['country']==name]
            ext=sum(x['external'] for x in rows);filled=sum(x['fulfilled'] for x in rows)
            eround={x['round'] for x in rows if x['external']};fround={x['round'] for x in rows if x['fulfilled']}
            partners=set(c.useful_partners)
            for u in exported_used:partners.update(n for _,n in self.foreign_uses[u.uid])
            trade=(5*min(1,len(er)/6)+(8*filled/ext if ext else 0)+4*min(1,len(partners)/3)
                   +(4*len(fround)/len(eround) if eround else 0)+4*min(1,len(er)/6))
            capgrowth=(self.capacity(c)-self.initial_capacity[name])/self.initial_capacity[name]
            assets=c.cash+self.stock_value(c)+.45*c.investment
            econ=(clip((assets-self.initial_assets[name])/ECON_GOAL[name]*20,0,20)
                  +clip(c.cash/self.reserve(c)*5,0,5)) if name in NAMES else None
            ind=(15*clip(capgrowth/GROWTH_GOAL[name],0,1)+10*len(used)/max(1,len(produced))) if name in NAMES else None
            happy=statistics.mean(c.happiness)
            owned=[self.units[i] for i in c.stock]
            useful_origins={self.units[i].origin for i in c.useful_imports if self.units[i].good=='electronics'}
            counts={g:{'external':sum(x['external'] for x in rows if x['good']==g),
                       'fulfilled':sum(x['fulfilled'] for x in rows if x['good']==g)} for g in GOODS}
            flow_new_out=sum(q for (a,b),q in flow.items() if a==name and b not in NAMES)
            countries[name]={
              'cash':c.cash,'happy':happy,'revenue':c.revenue,'purchases':c.purchases,
              'investment':c.investment,'tax':c.tax,'start_cash':c.start,
              'exports':sum(c.exported.values()),'imports':sum(c.imported.values()),
              'export_goods':dict(c.exported),'import_goods':dict(c.imported),
              'useful_exports':len(exported_used),'useful_imports':len(c.useful_imports),
              'useful_partners':len(partners),'export_help_rounds':len(er),
              'external_need':ext,'external_fulfilled':filled,'coverage':filled/ext if ext else 0,
              'needs_by_good':counts,'stock':len(c.stock),'listed':sum(u.order is not None for u in owned),
              'aged_unused':sum(not u.used and self.r-u.born>=2 for u in owned),
              'food_short_rounds':9-len(c.satisfied_rounds),'low_cash_rounds':sum(x<20 for x in c.cash_rounds),
              'produced':dict(c.produced),'production_failures':c.production_failures,
              'upgrades':c.upgrades,'upgrade_rounds':c.upgrade_rounds,
              'machine_gen':c.machine_tech,'elec_gen':c.elec_tech,
              'capacity_growth':capgrowth,'economic':econ,'industry':ind,'trade':trade,
              'score':econ+ind+happy/4+trade if name in NAMES else None,
              'export_to_added':flow_new_out,
              'real_electronics_suppliers':len(useful_origins),
            }
        n=len(self.cs);orig=[countries[k] for k in NAMES]
        active=[u for u in self.units.values() if u.owner is not None]
        world={
          'countries':n,'transactions':len(self.transactions),'trade_units':sum(tradegoods.values()),
          'trade_units_per_country':sum(tradegoods.values())/n,
          'listed':sum(len(o.units) for o in self.orders.values()),
          'inventory':len(active),'aged_unused':sum(not u.used and self.r-u.born>=2 for u in active),
          'aged_unused_per_country':sum(not u.used and self.r-u.born>=2 for u in active)/n,
          'aged_unused_fraction':sum(not u.used and self.r-u.born>=2 for u in active)/max(1,len(active)),
          'happy':statistics.mean(x['happy'] for x in countries.values()),
          'original_happy':statistics.mean(x['happy'] for x in orig),
          'original_cash':statistics.mean(x['cash'] for x in orig),
          'original_cash_gap':max(x['cash'] for x in orig)-min(x['cash'] for x in orig),
          'original_happy_gap':max(x['happy'] for x in orig)-min(x['happy'] for x in orig),
          'original_exports':statistics.mean(x['exports'] for x in orig),
          'original_useful_exports':statistics.mean(x['useful_exports'] for x in orig),
          'original_coverage':sum(x['external_fulfilled'] for x in orig)/max(1,sum(x['external_need'] for x in orig)),
          'original_food_short':statistics.mean(x['food_short_rounds'] for x in orig),
          'original_aged_unused':statistics.mean(x['aged_unused'] for x in orig),
          'original_production_failures':statistics.mean(x['production_failures'] for x in orig),
          'original_diagnostic_score':statistics.mean(x['score'] for x in orig),
          'barter':self.barters,'counter_accepted':self.counter_accepted,
          'initial_cash':self.initial_cash,'cash_total':sum(c.cash for c in self.cs.values()),
          'tax':self.minted,'investment':self.sunk,'verify_calls':self.audit_checks,
          'production':dict(self.created),'consumed':dict(self.destroyed),'trade_goods':dict(tradegoods),
          'end_prices':self.prices.copy(),
          'remaining_goods':dict(Counter(u.good for u in active)),
          'aged_unused_goods':dict(Counter(u.good for u in active if not u.used and self.r-u.born>=2)),
          'electronics_origins_used':len({u.origin for u in self.units.values() if u.good=='electronics' and u.used}),
          'score_note':'New country goals are not calibrated; scores only diagnostic for original six.'}
        return {'countries':countries,'world':world}
