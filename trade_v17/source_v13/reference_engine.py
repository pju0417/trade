"""Auditable #11 trade-game simulation. Pure Python 3.10+, no external dependencies.

This is a turn-resolution logic model, not a multiplayer web application.
The initial conditions and base costs are copied from the supplied sim.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import Counter, defaultdict
import hashlib, json, math, statistics
from typing import Optional

GOODS = ('banana','wheat','fuel','ore','machine','electronics')
NAMES = ('Tropia','Grainia','Oilia','Mechania','Mineria','Technia')
PRICE = dict(zip(GOODS,(10,10,30,20,50,80)))
CONFIG = {
 'Tropia': (170, {'banana':4,'wheat':2}, 'banana','ore'),
 'Grainia': (170, {'wheat':3,'banana':2}, 'wheat','machine'),
 'Oilia': (175, {'fuel':1,'ore':1,'banana':1}, 'fuel','banana'),
 'Mechania': (215, {'machine':2,'wheat':2}, 'machine','electronics'),
 'Mineria': (175, {'ore':1,'fuel':1}, 'ore','machine'),
 'Technia': (185, {'electronics':1,'machine':1,'wheat':1}, 'electronics','wheat')}
INVEST = {'banana':75,'wheat':75,'ore':95,'fuel':95,'machine':165,'electronics':220}
BONUS = {'banana':3,'wheat':3,'ore':1,'fuel':1,'machine':1,'electronics':1}
# Country-specific goals: fixed in all experiments, deliberately NOT fitted to test wins.
ECON_GOAL = dict(zip(NAMES,(250,240,140,160,140,160)))
GROWTH_GOAL = dict(zip(NAMES,(.90,.90,.48,.25,.48,.27)))
FOOD = ('wheat','banana')
DURABLES = ('machine','electronics')

def half_up5(x: float) -> int:
 return max(5,int(math.floor(x/5+.5))*5)

def clip(x,lo,hi): return min(hi,max(lo,x))

@dataclass
class Unit:
 uid:int; good:str; origin:str; gen:int; born:int; owner:Optional[str]
 order:Optional[int]=None
 used:bool=False
 use_country:Optional[str]=None
 use_round:Optional[int]=None
 use_purpose:Optional[str]=None
 last_import:Optional[int]=None

@dataclass
class Order:
 oid:int; seller:str; good:str; gen:int; price:int; units:list[int]

@dataclass
class Nation:
 name:str; cash:int; start:int; bases:dict; main:str; expand:str; style:str
 levels:dict=field(default_factory=dict)
 stock:set=field(default_factory=set)
 focus:str=''
 machine_tech:int=1; elec_tech:int=1
 happy:float=70.; happiness:list=field(default_factory=list)
 cash_rounds:list=field(default_factory=list)
 upgrades:int=0; attempts:int=0; blocked:int=0
 revenue:int=0; purchases:int=0; investment:int=0; tax:int=0
 produced:Counter=field(default_factory=Counter)
 imported:Counter=field(default_factory=Counter)
 exported:Counter=field(default_factory=Counter)
 used:Counter=field(default_factory=Counter)
 partners:set=field(default_factory=set)
 export_rounds:set=field(default_factory=set)
 useful_partners:set=field(default_factory=set)
 useful_imports:set=field(default_factory=set)
 helpful_rounds:set=field(default_factory=set)
 satisfied_rounds:set=field(default_factory=set)
 need_slots:int=0; import_slots:int=0
 external_need_units:int=0;external_need_rounds:set=field(default_factory=set)
 production_failures:int=0
 machines_used:set=field(default_factory=set)
 bonus_buffer:dict=field(default_factory=dict)
 upgrade_rounds:list=field(default_factory=list)

@dataclass(frozen=True)
class Options:
 # agent modes change decisions, not permissions, prices, or resources available to students
 planning:bool=False
 negotiations:bool=False
 price_v2:bool=False
 saturation_aware:bool=False
 trade_enabled:bool=True
 round_sweeps:int=2
 # controlled alternative, NOT final game decision
 affordability:bool=False
 smaller_bonus:bool=False
 specialist_cost:bool=False

class Game:
 def __init__(self, seed=0, options=None, focal=None, style='normal', all_style=None, log=False):
  self.seed=seed; self.opt=options or Options(); self.r=0; self.log=log
  self.cs={}
  for name,(cash,bases,main,expand) in CONFIG.items():
   st=all_style or (style if name==focal else 'normal')
   self.cs[name]=Nation(name,cash,cash,bases.copy(),main,expand,st,
       levels={g:1 for g in bases},focus=main)
  self.units={};self.orders={};self.uid=0;self.oid=0
  self.prices=PRICE.copy();self.global_gen={g:1 for g in DURABLES}
  self.minted=0;self.sunk=0;self.initial_cash=sum(c.cash for c in self.cs.values())
  self.created=Counter();self.destroyed=Counter();self.initial=Counter()
  self.transactions=[];self.applied={};self.settled=set();self.produced_rounds=set()
  self.use_by_country=set();self.foreign_uses=defaultdict(set);self.action_payload={}
  self.events=[];self.trust=defaultdict(int);self.trust_rounds=set()
  self.counteroffers=0;self.counter_accepted=0;self.barters=0
  self.cancelled=0;self.repriced=0
  self.price_history=[];self.round_history=[];self.bound_hits=Counter()
  self.round_useful=Counter();self.snapshots=[]
  for c in self.cs.values():
   for g in ('banana','wheat'): self.mint(c,g,2,initial=True)
   if c.name in ('Mechania','Technia'):
    self.mint(c,'ore',1,initial=True);self.mint(c,'fuel',1,initial=True)
    self.mint(c,'machine',1,initial=True)
  self.initial_assets={n:c.cash+self.stock_value(c) for n,c in self.cs.items()}
  self.initial_capacity={n:self.capacity(c) for n,c in self.cs.items()}

 def noise(self,*parts):
  """Keyed randomness: variants get the same draw for the same decision key."""
  text='|'.join(map(str,(self.seed,)+parts))
  return int.from_bytes(hashlib.blake2b(text.encode(),digest_size=8).digest(),'big')/2**64

 def order_actors(self,tag):
  return sorted(self.cs.values(),key=lambda c:self.noise(self.r,tag,c.name))

 def mint(self,c,g,n,gen=1,initial=False):
  for _ in range(n):
   self.uid+=1;u=Unit(self.uid,g,c.name,gen,0 if initial else self.r,c.name)
   self.units[u.uid]=u;c.stock.add(u.uid)
  (self.initial if initial else self.created)[g]+=n
  if not initial:c.produced[g]+=n

 def ids(self,c,g=None,free=True,min_gen=1):
  return [uid for uid in sorted(c.stock) if (g is None or self.units[uid].good==g)
      and self.units[uid].gen>=min_gen and (not free or self.units[uid].order is None)]

 def count(self,c,g,free=True,min_gen=1):return len(self.ids(c,g,free,min_gen))

 def round_price(self, value):
  tick=getattr(self.opt,"price_tick",5)
  return max(tick,int(math.floor(value/tick+.5))*tick)

 def quote(self,g,gen=1):
  p=self.prices[g]
  if g in DURABLES:p*=({1:1.,2:1.4,3:1.8}[gen])*(.75**max(0,self.global_gen[g]-gen))
  return self.round_price(p)

 def unit_ref(self,u):
  return PRICE[u.good]*({1:1,2:1.4,3:1.8}[u.gen] if u.good in DURABLES else 1)

 def stock_value(self,c):
  # Common valuation at t=0 and t=end; no claim that inventory can actually be sold.
  return sum(self.unit_ref(self.units[i])*(.50 if self.units[i].used and self.units[i].good in DURABLES else .15)
             for i in c.stock)

 def food_need(self,r=None):
  r=self.r if r is None else r
  return 1+(r>=5)+(r>=8)

 def pop(self,r=None):
  r=self.r if r is None else r
  return 2+(r>=5)+(r>=8)

 def tech_for(self,c,g):return c.machine_tech if g=='machine' else c.elec_tech if g=='electronics' else 1

 def resource_requirements(self,c,g,r=None):
  """Keep supplied model's operating resource schedule for comparable diagnostics.
  These are per-industry production-cycle costs, NOT per finished item.
  """
  r=self.r if r is None else r;lv=c.levels[g]
  if g not in DURABLES:return {}
  reqg='ore' if r%2 else 'fuel'
  if g=='machine' and c.name=='Mechania':reqg='ore'
  req=1+(lv>=3)
  if g=='machine' and c.machine_tech>=2:req+=1
  return {reqg:req}

 def next_resources(self,c):
  if self.r>=9:return Counter()
  ans=Counter()
  for g in c.levels:ans.update(self.resource_requirements(c,g,self.r+1))
  return ans

 def base_quantity(self,c,g,lv=None):
  lv=c.levels[g] if lv is None else lv
  return c.bases.get(g,1)+(lv-1)*(2 if g in FOOD else 1)

 def capacity(self,c):
  # Fixed base-price weights prevent new reference prices alone creating industrial growth.
  return sum(PRICE[g]*self.base_quantity(c,g) for g in c.levels)

 def equip_slots(self,c):
  # Same durable support upper bound as provided rule, but actually assigned once.
  return max(1,min(2,max(c.levels.values())))

 def machine_assignments(self,c):
  machines=sorted(self.ids(c,'machine'),key=lambda i:(-self.units[i].gen,i))[:self.equip_slots(c)]
  industries=sorted(c.levels,key=lambda g:(g!=c.focus,g!=c.main,g))
  return {g:i for g,i in zip(industries,machines)}

 def mark_use(self,c,uid,purpose):
  u=self.units[uid]
  if u.order is not None:raise AssertionError('listed item cannot be used')
  if u.owner!=c.name:raise AssertionError('use by non-owner')
  if not u.used:
   u.used=True;u.use_country=c.name;u.use_round=self.r;u.use_purpose=purpose
  if (uid,c.name) not in self.use_by_country:
   self.use_by_country.add((uid,c.name))
   if u.origin!=c.name and u.last_import is not None:
    self.foreign_uses[uid].add((self.r,c.name))
    c.useful_imports.add(uid);c.helpful_rounds.add(self.r)
    t=self.transactions[u.last_import]
    for leg in t['legs']:
     if uid in leg['ids']:c.useful_partners.add(leg['seller'])
  if u.origin!=c.name and u.last_import is not None:
   # Use-episodes are bounded by actual food/resource/equipment demand each round.
   c.import_slots+=1;c.helpful_rounds.add(self.r)
  self.round_useful[u.good]+=1

 def consume(self,c,g,n,purpose):
  selected=self.ids(c,g)[:n]
  if len(selected)!=n:raise ValueError('insufficient available resources')
  for uid in selected:
   self.mark_use(c,uid,purpose);c.stock.remove(uid);self.units[uid].owner=None
  self.destroyed[g]+=n;c.used[g]+=n
  return selected

 def remove_order_ids(self,ids):
  for uid in ids:
   u=self.units[uid]
   if u.order is not None:
    o=self.orders[u.order];o.units.remove(uid);u.order=None
    if not o.units:del self.orders[o.oid]

 def make_order(self,c,ids,price):
  if not ids:return None
  if len(set(ids))!=len(ids):raise ValueError('duplicate unit in order')
  us=[self.units[i] for i in ids]
  if any(u.owner!=c.name or u.order is not None for u in us):raise ValueError('unavailable stock')
  if len({(u.good,u.gen) for u in us})!=1:raise ValueError('mixed generation order')
  tick=getattr(self.opt,'price_tick',5)
  if type(price) is not int or price<tick or price%tick:raise ValueError('invalid price tick')
  self.oid+=1;oid=self.oid
  self.orders[oid]=Order(oid,c.name,us[0].good,us[0].gen,price,list(ids))
  for u in us:u.order=oid
  return oid

 def settle_transaction(self,legs,cash,channel,action_id):
  """All-or-nothing prevalidation. This simulates, does NOT test database concurrency."""
  payload=json.dumps((legs,cash,channel),sort_keys=True)
  if action_id in self.applied:
   return self.action_payload[action_id]==payload and self.applied[action_id]
  seen=set()
  for leg in legs:
   s,b=leg['seller'],leg['buyer']
   if s==b or s not in self.cs or b not in self.cs:return False
   if not leg['ids']:return False
   for uid in leg['ids']:
    if uid in seen or uid not in self.units:return False
    u=self.units[uid]
    if u.owner!=s or uid not in self.cs[s].stock:return False
    seen.add(uid)
  if cash:
   payer,payee,amount=cash
   if not isinstance(amount,int) or amount<0 or self.cs[payer].cash<amount:return False
  # Validation complete: no partial swap if either side lacks stock/cash.
  if cash:
   payer,payee,amount=cash;self.cs[payer].cash-=amount;self.cs[payee].cash+=amount
   self.cs[payer].purchases+=amount;self.cs[payee].revenue+=amount
  idx=len(self.transactions)
  for leg in legs:
   s=self.cs[leg['seller']];b=self.cs[leg['buyer']]
   self.remove_order_ids(leg['ids'])
   for uid in leg['ids']:
    u=self.units[uid];s.stock.remove(uid);b.stock.add(uid);u.owner=b.name;u.last_import=idx
    s.exported[u.good]+=1;b.imported[u.good]+=1
   s.partners.add(b.name);b.partners.add(s.name);s.export_rounds.add(self.r)
  tx={'round':self.r,'channel':channel,'legs':legs,'cash':cash,'action_id':action_id}
  self.transactions.append(tx);self.applied[action_id]=True;self.action_payload[action_id]=payload
  if channel=='barter':self.barters+=1
  if channel in ('direct','barter'):
   pair=tuple(sorted((legs[0]['seller'],legs[0]['buyer'])))
   key=(self.r,pair)
   if key not in self.trust_rounds:
    self.trust_rounds.add(key);self.trust[pair]=min(100,self.trust[pair]+10)
  return True

 def upgrade_cost(self,c,g):
  lv=c.levels.get(g,0)
  cost=INVEST[g]*(1 if lv<2 else 1.5 if lv==2 else 2)
  if g=='machine' and c.name=='Mechania':cost*=.75
  if g=='machine' and c.name=='Technia':cost*=1.25
  if self.opt.affordability and g in DURABLES:cost*=.8
  if self.opt.specialist_cost and g=='machine':
   if c.name=='Mechania':cost=(90,130,180)[min(2,max(0,lv-1))]
   elif c.name=='Technia':cost=(135,190,245)[min(2,max(0,lv-1))]
  return half_up5(cost)

 def upgrade_requirements(self,c,g):
  lv=c.levels.get(g,0)
  ore=0 if lv<2 else (1 if lv==2 else 2)
  if g in DURABLES and lv>=2:ore+=1
  # preserve staged development: Lv2 cash only; Lv3 resources; Lv4 previous gen machine.
  return ore, (2 if lv>=3 else 0)

 def plan(self,c):
  if c.style in ('idle','trade') or self.r>=8:return None
  choices=[g for g,lv in c.levels.items() if lv<4]
  if c.expand not in c.levels and self.r>=3:choices.append(c.expand)
  if not choices:return None
  if not self.opt.planning:
   return sorted(choices,key=lambda g:(g!=c.main,c.levels.get(g,0)>=3,
                      self.noise(self.r,'investment',c.name,g)))[0]
  # Purpose-driven: prioritize specialization, weigh demand, achievable horizon, and reserve.
  scores=[]
  for g in choices:
   lv=c.levels.get(g,0);cost=self.upgrade_cost(c,g)
   rem=9-self.r
   world_demand=self.world_potential_need(g)
   surplus=sum(len(o.units) for o in self.orders.values() if o.good==g)
   benefit=PRICE[g]*(2 if g in FOOD else 1)*rem
   techbonus=1.8 if g in DURABLES and lv<3 and self.tech_for(c,g)<=self.global_gen[g] else 1
   saturation=1+max(0,surplus-world_demand)/max(1,world_demand*2)
   score=(benefit*techbonus/cost)/saturation + (.30 if g==c.main else 0)
   if g not in c.levels:score*=.8
   scores.append((score,g))
  score,g=max(scores)
  if self.opt.saturation_aware and c.style!='invest' and score<.45:return None
  return g

 def world_potential_need(self,g):
  if g in FOOD:return 6*self.food_need(min(9,self.r+1))
  if g in ('ore','fuel'):return sum(self.next_resources(c)[g] for c in self.cs.values())+2
  if g=='machine':return sum(self.equip_slots(c) for c in self.cs.values())/3+3
  return sum(math.ceil(self.pop()/2) for c in self.cs.values())

 def targets(self,c):
  t={g:0 for g in GOODS}
  for g in FOOD:t[g]=self.food_need()
  t['electronics']=math.ceil(self.pop()/2)
  t['machine']=self.equip_slots(c)
  if self.opt.planning:
   t.update({**t,**self.next_resources(c)})
   # consumed resources need a next-cycle buffer; no arbitrary resource demand for every country
   pg=self.plan(c)
   if pg:
    cost=self.upgrade_cost(c,pg);ore,mg=self.upgrade_requirements(c,pg)
    if c.cash>=cost+20:
     t['ore']+=ore
     if mg:t['machine']=max(t['machine'],1)
  else:
   for g in ('ore','fuel'):
    if c.main in DURABLES or max(c.levels.values())>=3:t[g]=1+(max(c.levels.values())>=3)
  return t

 def need(self,c,g):return max(0,self.targets(c)[g]-self.count(c,g))

 def reserve(self,c):
  # One FOOD round buffer in addition to planned resources; no borrowing/free goods.
  return 2*self.food_need()*10+20

 def prepare_orders(self,c):
  if c.style=='idle' or not self.opt.trade_enabled:return
  t=self.targets(c)
  if self.opt.planning:
   # recall only domestic necessities, not all listings; preserve others until owner reprices
   for g in GOODS:
    missing=max(0,t[g]-self.count(c,g))
    if missing:
     ids=sorted(self.ids(c,g,False),key=lambda i:(-self.units[i].gen,i))
     recall=[i for i in ids if self.units[i].order is not None][:missing]
     self.remove_order_ids(recall);self.cancelled+=len(recall)
  else:
   # correctness: fixed policy may be poor, but cannot use listed products internally
   pass
  for g in GOODS:
   free=self.ids(c,g)
   # retain highest-grade durables; cheap changes price ONLY, never protected quantities
   ordered=sorted(free,key=lambda i:(-self.units[i].gen,i))
   keep=t[g];sell=ordered[keep:]
   if self.opt.planning:
    # imported products serve planned needs; no agent-driven speculative resale loop
    sell=[i for i in sell if self.units[i].origin==c.name or self.units[i].good in DURABLES]
   sell=sell[:10]
   for gen in (1,2,3):
    ids=[i for i in sell if self.units[i].gen==gen]
    if not ids:continue
    price=self.quote(g,gen)
    if c.style=='cheap':price=self.round_price(price*.5)
    elif self.opt.planning:
     competition=[o.price for o in self.orders.values() if o.good==g and o.gen==gen and o.seller!=c.name]
     factor=.9 if competition and min(competition)<price else 1
     price=self.round_price(price*factor)
    else:
     factor=(.85,.95,1,1,1.05,1.15)[min(5,int(self.noise(self.r,'ask',c.name,g,gen)*6))]
     price=self.round_price(price*factor)
    self.make_order(c,ids,price)
  if self.opt.planning:
   for o in self.orders.values():
    if o.seller!=c.name:continue
    age=min(self.r-self.units[i].born for i in o.units)
    target=self.round_price(self.quote(o.good,o.gen)*(.5 if c.style=='cheap' else .9 if age>=2 else 1))
    if o.price!=target:o.price=target;self.repriced+=1

 def get_surplus(self,c,g,min_gen=1):
  all_ids=sorted(self.ids(c,g,False),key=lambda i:(-self.units[i].gen,i))
  keep=self.targets(c)[g]
  reserved=set(all_ids[:keep])
  return [i for i in all_ids if i not in reserved and self.units[i].gen>=min_gen]

 def market_buy(self,c,g,n,budget,min_gen=1,tag='market'):
  if c.style=='idle' or not self.opt.trade_enabled:return 0
  got=0;spent=0
  offers=sorted([o for o in self.orders.values() if o.good==g and o.gen>=min_gen and o.seller!=c.name],
                key=lambda o:(o.price,self.noise(self.r,tag,c.name,o.seller,o.oid)))
  for o in offers:
   if got>=n:break
   if o.oid not in self.orders:continue
   qty=min(n-got,len(o.units),c.cash//o.price,(budget-spent)//o.price)
   if qty<=0:continue
   ids=o.units[:qty];action=f'market:{self.r}:{len(self.transactions)}:{o.oid}:{c.name}'
   if self.settle_transaction([{'seller':o.seller,'buyer':c.name,'ids':ids}],
                  (c.name,o.seller,qty*o.price),'market',action):got+=qty;spent+=qty*o.price
  return got

 def negotiate(self,c,g,n,min_gen=1,budget=None,tag='direct'):
  if not self.opt.negotiations or not self.opt.trade_enabled or c.style=='idle' or n<=0:return 0
  budget=c.cash if budget is None else min(budget,c.cash)
  candidates=sorted([z for z in self.cs.values() if z is not c and z.style!='idle'],
                    key=lambda z:self.noise(self.r,tag,c.name,g,z.name))
  for s in candidates:
   supply=self.get_surplus(s,g,min_gen)
   if not supply:continue
   uid=supply[0];ref=self.quote(g,self.units[uid].gen)
   # Barter must fulfil an actual unmet need on BOTH sides; each leg carries provenance.
   for h in GOODS:
    if h==g or self.need(s,h)<=0:continue
    give=self.get_surplus(c,h)
    if not give:continue
    hv=self.quote(h,self.units[give[0]].gen)
    # Integer pack sizes; bounded attempts, mutually acceptable relative reference value.
    for q in range(1,min(n,len(supply),3)+1):
     k=max(1,int(math.floor(q*ref/hv+.5)))
     if k>len(give) or k>self.need(s,h):continue
     ratio=k*hv/(q*ref)
     if not .75<=ratio<=1.33:continue
     legs=[{'seller':s.name,'buyer':c.name,'ids':supply[:q]},
           {'seller':c.name,'buyer':s.name,'ids':give[:k]}]
     act=f'barter:{self.r}:{len(self.transactions)}'
     if self.settle_transaction(legs,None,'barter',act):return q
  # Check every viable barter partner before falling back to cash negotiation.
  for s in candidates:
   supply=self.get_surplus(s,g,min_gen)
   if not supply:continue
   uid=supply[0];ref=self.quote(g,self.units[uid].gen)
   # Buyer proposes discount; seller counteroffer protects own demand and budget.
   desired=self.round_price(ref*.8)
   pair=tuple(sorted((s.name,c.name)))
   concession=.05*min(1,self.trust[pair]/60)
   ask=self.round_price(ref*(.95-concession))
   self.counteroffers+=1
   qty=min(n,len(supply),budget//ask,c.cash//ask)
   if qty<=0:continue
   act=f'direct:{self.r}:{len(self.transactions)}'
   if self.settle_transaction([{'seller':s.name,'buyer':c.name,'ids':supply[:qty]}],
               (c.name,s.name,qty*ask),'direct',act):
    self.counter_accepted+=1;return qty
  return 0

 def buy_phase(self,c,sweep):
  if c.style=='idle' or not self.opt.trade_enabled:return
  for g in ('wheat','banana','ore','fuel','machine','electronics'):
   want=self.need(c,g)
   if want<=0:continue
   essential=sum(max(0,self.food_need()-self.count(c,f))*self.quote(f) for f in FOOD if f!=g)
   keep=0 if c.style=='invest' else essential+(0 if g in FOOD else 15)
   budget=max(0,c.cash-keep)
   # Demand is needs constrained by the budget; failed clicks do not raise prices.
   if self.opt.negotiations and g not in FOOD and (budget<self.quote(g)*want or sweep%2==1):
    got=self.negotiate(c,g,want,budget=budget,tag=f'pre{sweep}');want-=got
   if want:
    got=self.market_buy(c,g,want,budget=max(0,c.cash-keep),tag=f'market{sweep}');want-=got
   if want:self.negotiate(c,g,want,budget=max(0,c.cash-keep),tag=f'post{sweep}')
  # Purposeful grade replacement; remove unused old devices only in the NEXT sale phase.
  if self.opt.planning and self.r<=7:
   pg=self.plan(c)
   if pg:
    _,mg=self.upgrade_requirements(c,pg)
    if mg and not self.count(c,'machine',min_gen=mg):
     budget=max(0,c.cash-self.upgrade_cost(c,pg)-self.reserve(c))
     got=self.market_buy(c,'machine',1,budget,min_gen=mg)
     if not got:self.negotiate(c,'machine',1,min_gen=mg,budget=budget)

 def production(self):
  if self.r in self.produced_rounds:return False
  staged=[]
  for c in self.cs.values():
   # plan shared equipment allocations ONCE before any new machine output
   machines=self.machine_assignments(c)
   allocated={uid for good,uid in machines.items() if good not in DURABLES and good==c.focus}
   for uid in allocated:
    self.mark_use(c,uid,'equipment');c.need_slots+=1
   for g,lv in c.levels.items():
    base=self.base_quantity(c,g);bonus=BONUS[g] if c.focus==g else 0
    if self.opt.smaller_bonus and g in FOOD and bonus:bonus=2
    gen=self.tech_for(c,g)
    req=self.resource_requirements(c,g)
    c.need_slots+=sum(req.values())
    enough=all(self.count(c,h)>=n for h,n in req.items())
    if not enough:
     # Critical repair: guaranteed fallback is BASIC generation, never free newest products.
     base=1;bonus=0;gen=1;c.production_failures+=1
    else:
     for h,n in req.items():self.consume(c,h,n,'production')
    if g not in DURABLES and c.focus==g and g in machines:
     u=self.units[machines[g]];gap=max(0,self.global_gen['machine']-u.gen)
     eff=(1,.8,.6)[min(2,gap)]
     # deterministic carry avoids 1.6 rounding back to 2 and making grade differences disappear
     carry=c.bonus_buffer.get(g,0)+(1 if self.opt.smaller_bonus else 2)*eff
     extra=int(carry+1e-9);c.bonus_buffer[g]=carry-extra;bonus+=extra
    staged.append((c,g,max(1,base+bonus),gen))
  for c,g,n,gen in staged:self.mint(c,g,n,gen)
  self.produced_rounds.add(self.r);return True

 def settle_round(self,c):
  key=(self.r,c.name)
  if key in self.settled:return False
  food=[]
  for g in FOOD:
   need=self.food_need();n=min(need,self.count(c,g));self.consume(c,g,n,'food')
   c.need_slots+=need;food.append(n/need)
  want=math.ceil(self.pop()/2)
  ids=sorted(self.ids(c,'electronics'),key=lambda i:(-self.units[i].gen,i))[:want]
  eff=0
  for uid in ids:
   u=self.units[uid];gap=min(2,max(0,self.global_gen['electronics']-u.gen))
   eff+=(1,.8,.6)[gap];self.mark_use(c,uid,'living')
  c.need_slots+=want
  coverage=min(1,eff/want)
  c.happy=round(35+40*sum(food)/2+25*coverage,6)
  c.happiness.append(c.happy)
  if min(food)>=1:c.satisfied_rounds.add(self.r)
  tax=10+int(math.floor(c.happy/10+.5));c.cash+=tax;c.tax+=tax;self.minted+=tax
  self.settled.add(key);return True

 def invest(self,c):
  if c.style in ('idle','trade') or self.r>=8:return False
  g=self.plan(c)
  if g is None:return False
  choices=[g]
  if not self.opt.planning:
   # retain original fallback to cheap secondary industries for diagnosis
   choices+=[h for h in c.levels if h!=g and c.levels[h]<4]
  for g in choices:
   if c.levels.get(g,0)>=4:continue
   cost=self.upgrade_cost(c,g);reserve=0 if c.style=='invest' else (self.reserve(c) if self.opt.planning else 80 if self.r<=5 else 125)
   if c.cash<cost+reserve:continue
   c.attempts+=1;ore,mg=self.upgrade_requirements(c,g)
   equip=self.ids(c,'machine',min_gen=mg or 1)
   if self.count(c,'ore')<ore or (mg and not equip):c.blocked+=1;continue
   if ore:self.consume(c,'ore',ore,'development')
   if mg:self.mark_use(c,equip[0],'development')
   c.cash-=cost;c.investment+=cost;self.sunk+=cost
   lv=c.levels.get(g,0)+1;c.levels[g]=lv;c.bases.setdefault(g,1)
   c.upgrades+=1;c.upgrade_rounds.append((self.r,g,lv))
   if g=='machine':c.machine_tech=min(3,lv)
   if g=='electronics':c.elec_tech=min(3,lv)
   # effective next production; global generation is updated only at next round start
   return True
  return False

 def choose_focus(self,c):
  if c.style=='idle':return
  if c.style=='invest':c.focus=max(c.levels,key=lambda g:self.quote(g));return
  if not self.opt.planning:
   c.focus=max(c.levels,key=lambda g:self.quote(g)*BONUS[g]/(1+self.count(c,g)*.25)+self.noise(self.r,'focus',c.name,g)*5)
  else:
   c.focus=max(c.levels,key=lambda g:self.quote(g)*BONUS[g]/(1+self.count(c,g,False)*.3)
                +max(0,self.targets(c)[g]-self.count(c,g,False))*10)

 def update_prices(self):
  for g in GOODS:
   old=self.prices[g];supply=sum(len(o.units) for o in self.orders.values() if o.good==g)
   if not self.opt.price_v2:
    demand=sum(min(self.need(c,g),c.cash//max(5,old)) for c in self.cs.values())
    step=5 if old<=50 else 10
    new=old+step if demand>supply*1.1 and demand>0 else old-step if supply>demand*1.6 and supply>1 else old
    self.prices[g]=clip(new,max(5,PRICE[g]*.7),PRICE[g]*1.3)
   else:
    # Compare START-of-round executable demand/supply, plus completed sales. Do not
    # compare consumed inventory at end of round to a full history of unsold offers.
    snap=self.snapshots[-1]
    d=snap['demand'].get(g,0);s=snap['supply'].get(g,0)
    pressure=(d-s)/max(1,d+s)
    target=PRICE[g]*(1+.30*pressure)
    self.prices[g]=clip(.65*old+.35*target,PRICE[g]*.7,PRICE[g]*1.3)
   if abs(self.prices[g]-PRICE[g]*.7)<1e-6 or abs(self.prices[g]-PRICE[g]*1.3)<1e-6:self.bound_hits[g]+=1
  self.price_history.append(self.prices.copy())

 def demand_snapshot(self):
  d=Counter();s=Counter()
  for o in self.orders.values():s[o.good]+=len(o.units)
  # Allocate each nation's purchasing budget ONCE, rather than reuse it for each good.
  for c in self.cs.values():
   if c.style=='idle':continue
   budget=c.cash
   raw_need=sum(self.need(c,h) for h in GOODS)
   c.external_need_units+=raw_need
   if raw_need:c.external_need_rounds.add(self.r)
   for g in ('wheat','banana','ore','fuel','machine','electronics'):
    n=min(self.need(c,g),budget//self.quote(g));d[g]+=n;budget-=n*self.quote(g)
  self.snapshots.append({'round':self.r,'demand':dict(d),'supply':dict(s)})

 def verify(self):
  assert sum(c.cash for c in self.cs.values())==self.initial_cash+self.minted-self.sunk,'cash conservation'
  assert all(c.cash>=0 for c in self.cs.values()),'negative cash'
  seen=set();obs=Counter();listed=set()
  for c in self.cs.values():
   for uid in c.stock:
    assert uid not in seen,'duplicated unit ownership';seen.add(uid)
    u=self.units[uid];assert u.owner==c.name,'owner mismatch';obs[u.good]+=1
  for u in self.units.values():
   assert (u.owner is None)==(u.uid not in seen),'missing unit'
  for o in self.orders.values():
   for uid in o.units:
    assert uid not in listed,'double listing';listed.add(uid)
    u=self.units[uid]
    assert (u.owner,u.order,u.good,u.gen)==(o.seller,o.oid,o.good,o.gen),'escrow mismatch'
  assert listed=={u.uid for u in self.units.values() if u.order is not None},'orphan escrow'
  for g in GOODS:assert obs[g]==self.initial[g]+self.created[g]-self.destroyed[g],f'goods {g}'
  return True

 def run(self):
  for r in range(1,10):
   self.r=r;self.round_useful=Counter()
   self.global_gen={'machine':max(c.machine_tech for c in self.cs.values()),
                    'electronics':max(c.elec_tech for c in self.cs.values())}
   self.production();self.verify()
   for c in self.order_actors('listing'):self.prepare_orders(c)
   self.demand_snapshot()
   for sweep in range(self.opt.round_sweeps):
    for c in self.order_actors(f'buy{sweep}'):self.buy_phase(c,sweep)
   self.verify()
   for c in self.cs.values():self.settle_round(c)
   for c in self.order_actors('invest'):self.invest(c)
   for c in self.cs.values():self.choose_focus(c);c.cash_rounds.append(c.cash)
   self.update_prices();self.verify()
   self.round_history.append({'round':r,'cash':{n:c.cash for n,c in self.cs.items()},
       'listed':sum(len(o.units) for o in self.orders.values()),'transactions':len(self.transactions)})
  return self.summary()

 def summary(self):
  scores={};used_origin=Counter();made_origin=Counter();useful_exports=defaultdict(set)
  for u in self.units.values():
   if u.born>0:
    made_origin[u.origin]+=1
    if u.used:used_origin[u.origin]+=1
    if self.foreign_uses.get(u.uid):useful_exports[u.origin].add(u.uid)
  # Legacy uses exact supplied formula on this engine's ledger, not baseline averages.
  for n,c in self.cs.items():
   own_sold=sum(1 for t in self.transactions for leg in t['legs'] if leg['seller']==n
                for uid in leg['ids'] if self.units[uid].origin==n)
   own_consumed=sum(1 for u in self.units.values() if u.origin==n and u.good in FOOD and u.used and u.owner is None and u.use_country==n)
   stock=len(c.stock);sold=sum(c.exported.values());bought=sum(c.imported.values())
   ware=sum(self.quote(self.units[i].good,self.units[i].gen)*(.15 if self.units[i].order else .22) for i in c.stock)
   old_assets=c.cash+ware+sum(INVEST[g]*.45*(lv-1) for g,lv in c.levels.items())
   old_initial=c.start+40+(40 if n in ('Mechania','Technia') else 0)
   old_econ=min(20,max(0,(old_assets-old_initial)/ECON_GOAL[n]*20))+min(5,c.cash/150*5)
   hp=statistics.mean(c.happiness)/4
   old_trade=min(5,sold/15*5)+min(8,bought/15*8)+min(4,len(c.partners)/3*4)+min(8,(bought+own_sold)/30*8)
   denom={'Tropia':1.6,'Grainia':1.6,'Oilia':1.4,'Mechania':1.4,'Mineria':1.4,'Technia':1.3}[n]
   old_ind=min(15,c.upgrades/denom*15)+min(10,(own_sold+own_consumed)/max(1,sum(c.produced.values()))*10)
   # Audited score v2: a candidate ONLY; no country-specific per-run reward patches.
   assets=c.cash+self.stock_value(c)+.45*c.investment
   growth=assets-self.initial_assets[n]
   econ=clip(growth/ECON_GOAL[n]*20,0,20)+clip(c.cash/self.reserve(c)*5,0,5)
   # Meaningful exported units used abroad; capped round variety; no cash-price scoring.
   eu=useful_exports[n]
   er={r for i in eu for r,_ in self.foreign_uses[i]}
   useful_origins={self.units[i].origin for i in c.useful_imports}
   trade=(5*min(1,len(er)/6)+8*min(1,len(c.helpful_rounds)/8)
          +4*min(1,len(c.useful_partners|useful_origins)/3)
          +8*min(1,len(c.useful_imports)/max(1,c.need_slots*.35)))
   capgrowth=(self.capacity(c)-self.initial_capacity[n])/self.initial_capacity[n]
   utilized=used_origin[n]/max(1,made_origin[n])
   ind=15*clip(capgrowth/GROWTH_GOAL[n],0,1)+10*utilized
   scores[n]={'cash':c.cash,'stock':stock,'listed':sum(1 for i in c.stock if self.units[i].order),
     'happy':statistics.mean(c.happiness),'revenue':c.revenue,'purchases':c.purchases,
     'investment':c.investment,'tax':c.tax,'cash_flow':c.revenue-c.purchases-c.investment,
     'exports':sold,'imports':bought,'upgrades':c.upgrades,'attempts':c.attempts,'blocked':c.blocked,
     'machine_gen':c.machine_tech,'elec_gen':c.elec_tech,'production_failures':c.production_failures,
     'economic':econ,'wellbeing':hp,'trade':trade,'industry':ind,'score':econ+hp+trade+ind,
     'legacy_score':old_econ+hp+old_trade+old_ind,'legacy_industry':old_ind,
     'utilization':utilized,'growth':capgrowth,'import_help_rounds':len(c.helpful_rounds),
     'export_help_rounds':len(er),'useful_imports':len(c.useful_imports),'partners':len(c.partners),
     'low_cash_rounds':sum(x<20 for x in c.cash_rounds),
     'external_need_units':c.external_need_units,'external_need_rounds':len(c.external_need_rounds),
     'produced':dict(c.produced),'export_goods':dict(c.exported),'import_goods':dict(c.imported)}
  leg_goods=Counter()
  for t in self.transactions:
   for leg in t['legs']:
    for uid in leg['ids']:leg_goods[self.units[uid].good]+=1
  world={'transactions':len(self.transactions),'trade_units':sum(leg_goods.values()),
    'barter':self.barters,'counteroffers':self.counteroffers,'counter_accepted':self.counter_accepted,
    'listed':sum(len(o.units) for o in self.orders.values()),'inventory':sum(len(c.stock) for c in self.cs.values()),
    'cash_total':sum(c.cash for c in self.cs.values()),'tax':self.minted,'investment':self.sunk,
    'produced':dict(self.created),'consumed':dict(self.destroyed),'trade_goods':dict(leg_goods),
    'remaining_goods':dict(Counter(u.good for u in self.units.values() if u.owner)),
    'used_durable_stock':sum(u.owner is not None and u.good in DURABLES and u.used for u in self.units.values()),
    'end_prices':self.prices.copy(),'bound_hits':dict(self.bound_hits),
    'cancelled_units':self.cancelled,'reprices':self.repriced,'verifications':27,
    'useful_imports':sum(len(c.useful_imports) for c in self.cs.values())}
  return {'countries':scores,'world':world}

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=0);a=p.parse_args()
 g=Game(a.seed,Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True))
 print(json.dumps(g.run(),indent=2))
