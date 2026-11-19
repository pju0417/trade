"""v7: observable sales advice and marginal-use planning, on frozen v6 coupled.

No physical recipe, initial condition, market reference formula, legal student
action, negotiation protocol or score formula is changed. Forecast coefficients
are game-design trials, not fitted real-world estimates or guaranteed sales.
"""
from __future__ import annotations
from collections import Counter
from copy import copy
from dataclasses import dataclass
import math, statistics
from machinery_engine import Game as V6
from reference_engine import GOODS, FOOD, DURABLES, BONUS


@dataclass(frozen=True)
class AdvicePolicy:
    prices: bool=False
    listing_budget: bool=False
    planning: bool=False


ADVICE_MODES={
    'baseline':AdvicePolicy(),
    'price':AdvicePolicy(prices=True),
    'listing':AdvicePolicy(prices=True,listing_budget=True),
    'planning':AdvicePolicy(planning=True),
    'responsive':AdvicePolicy(prices=True,planning=True),
    'combined':AdvicePolicy(prices=True,listing_budget=True,planning=True),
}
HISTORY_ROUNDS=2
MIN_LISTING=2
MAX_LISTING=10


class Game(V6):
    def __init__(self,seed=0,variant='baseline',focal=None,style='normal',trade_enabled=True):
        if variant not in ADVICE_MODES:raise ValueError('unknown advice variant')
        self.advice_variant=variant
        self.advice_policy=ADVICE_MODES[variant]
        self.advice_log=[]
        self.offer_history=[]
        self.listing_plan_log=[]
        self.grade_recall_log=[]
        self.advice_plan_logged=set()
        super().__init__(seed,mode='coupled',focal=focal,style=style,trade_enabled=trade_enabled)

    def own_sales(self,c,good,gen=None,through_round=None):
        """Self-known completed legs only, never another country's budget/stock.

        Same UID sold again is counted once per observation window. A barter
        is a sale quantity but never becomes a cash-price observation.
        """
        through=self.r-1 if through_round is None else through_round
        through=min(through,self.r)
        start=max(1,through-HISTORY_ROUNDS+1)
        seen=set();prices=[];buyers=set()
        for tx in self.transactions:
            if not start<=tx['round']<=through:continue
            for leg in tx['legs']:
                if leg['seller']!=c.name:continue
                ids=[i for i in leg['ids'] if self.units[i].good==good and
                     (gen is None or self.units[i].gen==gen)]
                if not ids:continue
                buyers.add(leg['buyer']);seen.update(ids)
                if tx['cash']:
                    prices.extend([tx['cash'][2]/len(leg['ids'])]*len(ids))
        rounds=max(0,through-start+1)
        return {'through_round':through,'rounds':rounds,'units':len(seen),
                'rate':len(seen)/max(1,rounds),'cash_price':statistics.median(prices) if prices else None,
                'buyers':len(buyers)}

    def price_recommendation(self,c,good,gen,ids=None):
        ref=self.quote(good,gen)
        history=self.own_sales(c,good,gen)
        if ids is None:ids=[i for i in self.ids(c,good,False) if self.units[i].gen==gen]
        age=max((self.r-self.units[i].born for i in ids if not self.units[i].used),default=0)
        exposures={(row['round'],i) for row in self.offer_history if row['country']==c.name
                    and row['good']==good and row['generation']==gen
                    and max(1,self.r-HISTORY_ROUNDS)<=row['round']<self.r for i in row['ids']}
        cleared={(tx['round'],i) for tx in self.transactions
                 if max(1,self.r-HISTORY_ROUNDS)<=tx['round']<self.r
                 for leg in tx['legs'] if leg['seller']==c.name for i in leg['ids']
                 if (tx['round'],i) in exposures}
        offered=len(exposures)
        fill=len(cleared)/offered if offered else None
        factor=1.;reason='reference_trial'
        if age>=4 and offered and fill<.5:factor=.60;reason='persistent_unsold'
        elif age>=2 and offered and fill<.75:factor=.80;reason='unsold_stock'
        elif offered and fill>=.9:factor=1.05;reason='recent_sales_strong'
        price=self.round_price(ref*factor)
        # A higher grade at a lower price is also an eligible substitute.
        rivals=[o.price for o in self.orders.values() if o.seller!=c.name and o.good==good
                and o.gen>=gen and o.units]
        if rivals and min(rivals)<price:
            price=min(rivals);reason+=';match_public_offer'
        # This is a recommendation floor, never a legal student price floor.
        price=max(self.round_price(ref*.5),price)
        if c.style=='cheap':price=self.round_price(ref*.5);reason='fixed_half_reference'
        return {'reference':ref,'price':price,'reason':reason,'age':age,
                'past_offered':offered,'past_sold':len(cleared),'past_all_sales':history['units'],
                'through_round':self.r-1,'rival_best':min(rivals) if rivals else None}

    def listing_quantity(self,c,good,surplus_ids):
        history=self.own_sales(c,good)
        # Total LIVE public quantity, not another fresh allowance every round.
        # Direct negotiation/barter may still offer the other legitimate surplus.
        target=max(MIN_LISTING,1+math.ceil(2*history['rate']))
        return min(len(surplus_ids),MAX_LISTING,target)

    def _recall_qualified_machine(self,c):
        project=self.plan(c)
        grade=self.upgrade_requirements(c,project)[1] if project else 0
        if not grade or self.count(c,'machine',min_gen=grade):return
        ids=self.ids(c,'machine',False,min_gen=grade)
        if not ids:return
        chosen=max(ids,key=lambda i:(self.units[i].gen,-i))
        if self.units[chosen].order is not None:
            self.remove_order_ids([chosen]);self.cancelled+=1
            self.grade_recall_log.append({'round':self.r,'country':c.name,'unit':chosen,'min_gen':grade})

    def protected_ids(self,c,good):
        # Equal-grade free units already cover the same need; do not introduce
        # an unrelated FIFO stock-rotation rule just by choosing an older UID.
        owned=sorted(self.ids(c,good,False),
                     key=lambda i:(-self.units[i].gen,self.units[i].order is not None,i))
        return set(owned[:self.targets(c)[good]])

    def get_surplus(self,c,good,min_gen=1):
        if self.advice_variant=='baseline':return super().get_surplus(c,good,min_gen)
        protected=self.protected_ids(c,good)
        return [i for i in sorted(self.ids(c,good,False),key=lambda i:(-self.units[i].gen,i))
                if i not in protected and self.units[i].gen>=min_gen]

    def prepare_orders(self,c):
        if self.advice_variant!='baseline' and c.style!='idle' and self.opt.trade_enabled:
            self._recall_qualified_machine(c)
            # Match get_surplus(): protect the best qualifying OWN units across
            # both free and already-listed stock, before choosing new offers.
            for good in GOODS:
                recall=[i for i in self.protected_ids(c,good) if self.units[i].order is not None]
                if recall:self.remove_order_ids(recall);self.cancelled+=len(recall)
        super().prepare_orders(c)
        if c.style=='idle' or not self.opt.trade_enabled:return
        for good in GOODS:
            surplus=[i for i in self.get_surplus(c,good)
                     if self.units[i].origin==c.name or good in DURABLES]
            if self.advice_policy.listing_budget:
                qty=self.listing_quantity(c,good,surplus)
                # Show one of each available generation first; then oldest stock.
                chosen=[]
                for grade in sorted({self.units[i].gen for i in surplus},reverse=True):
                    batch=sorted((i for i in surplus if self.units[i].gen==grade),key=lambda i:(self.units[i].born,i))
                    if batch and len(chosen)<qty:chosen.append(batch[0])
                remaining=sorted((i for i in surplus if i not in chosen),key=lambda i:(self.units[i].born,i))
                chosen+=remaining[:max(0,qty-len(chosen))]
                live=[i for i in self.ids(c,good,False) if self.units[i].order is not None]
                remove=[i for i in live if i not in chosen]
                if remove:self.remove_order_ids(remove);self.cancelled+=len(remove)
                for grade in (1,2,3):
                    new=[i for i in chosen if self.units[i].gen==grade and self.units[i].order is None]
                    if new:self.make_order(c,new,self.quote(good,grade))
            else:
                qty=sum(len(o.units) for o in self.orders.values() if o.seller==c.name and o.good==good)
            for grade in (1,2,3):
                orders=[o for o in self.orders.values() if o.seller==c.name and o.good==good and o.gen==grade]
                ids=[i for o in orders for i in o.units]
                if not ids:continue
                advice=self.price_recommendation(c,good,grade,ids)
                if self.advice_policy.prices:
                    for order in orders:
                        if order.price!=advice['price']:order.price=advice['price'];self.repriced+=1
                self.offer_history.append({'round':self.r,'country':c.name,'good':good,'generation':grade,
                                           'ids':list(ids),'prices':sorted({o.price for o in orders})})
                self.advice_log.append({'kind':'offer','round':self.r,'country':c.name,'good':good,
                    'generation':grade,'through_round':self.r-1,'recommendation':advice,
                    'price_applied':self.advice_policy.prices,'total_good_target':qty,
                    'public_quantity_limited':self.advice_policy.listing_budget,
                    'actual_ids':list(ids),'actual_prices':sorted({o.price for o in orders}),
                    'scope':'public_market_only; direct_and_barter_unchanged'})
            active=[i for o in self.orders.values() if o.seller==c.name and o.good==good for i in o.units]
            protected=set(self.ids(c,good,False))-set(self.get_surplus(c,good))
            self.listing_plan_log.append({'round':self.r,'country':c.name,'good':good,
                'limited':self.advice_policy.listing_budget,'target':qty,'actual_ids':active,
                'surplus_ids':surplus,'protected_ids':sorted(protected),
                'within_plan':not self.advice_policy.listing_budget or len(active)==qty})

    def actual_bonus(self,c,good):
        return 2 if self.opt.smaller_bonus and good in FOOD else BONUS[good]

    def equipment_bonus(self,c,good):
        if good in DURABLES:return 0
        ids=self.ids(c,'machine')
        if not ids:return 0
        uid=max(ids,key=lambda i:(self.units[i].gen,-i))
        gap=min(2,max(0,self.global_gen['machine']-self.units[uid].gen))
        return math.floor(c.bonus_buffer.get(good,0)+(1,.8,.6)[gap]+1e-9)

    def cycle_output(self,c,good,focused=None):
        if good not in c.levels:return 0
        focus=c.focus if focused is None else focused
        base=self.base_quantity(c,good)
        bonus=self.actual_bonus(c,good)+self.equipment_bonus(c,good) if focus==good else 0
        if good=='machine':
            p=copy(c);p.focus=focus
            return self.machine_quantity(p,min(9,self.r+1),actual=True)
        return base+bonus

    def future_domestic(self,c,good):
        """Planning-free own need; deliberately no targets(), plan() or rivals."""
        rounds=range(self.r+1,10)
        if good in FOOD:return sum(self.food_need(r) for r in rounds)
        if good=='electronics':return math.ceil(self.pop(9)/2) if self.r<9 else 0
        if good=='machine':return int(self.r<9 and any(g not in DURABLES for g in c.levels))
        return sum(self.resource_requirements(c,g,r).get(good,0) for r in rounds for g in c.levels)

    def _stock_after_current_use(self,c,good):
        stock=self.count(c,good,False)
        if good in FOOD and (self.r,c.name) not in self.settled:stock=max(0,stock-self.food_need())
        return stock

    def investment_advice(self,c,good):
        """Marginal-use opportunity score, NOT a guaranteed cash payback rule.

        The inherited .45 threshold and .30 specialization preference remain.
        Past own customers give a bounded, uncertain new-generation opportunity;
        they are never compelled or funded to buy again.
        """
        rem=max(0,9-self.r)
        current=c.levels.get(good,0)
        p=copy(c);p.levels=dict(c.levels);p.bases=dict(c.bases)
        p.levels[good]=current+1;p.bases.setdefault(good,1)
        if good=='machine':p.machine_tech=min(3,current+1)
        if good=='electronics':p.elec_tech=min(3,current+1)
        oldgen=self.tech_for(c,good);newgen=self.tech_for(p,good)
        history=self.own_sales(c,good)
        stock=self._stock_after_current_use(c,good)
        domestic=self.future_domestic(c,good)
        external=history['rate']*rem
        base_output=self.cycle_output(c,good)*rem
        after_output=self.cycle_output(p,good)*rem
        ordinary_gap=max(0,domestic+external-stock-base_output)
        useful_extra=min(max(0,after_output-base_output),ordinary_gap)
        quote=self.quote(good,oldgen)
        observed=history['cash_price'] if history['cash_price'] is not None else quote
        realizable=min(quote,observed)
        capacity_value=useful_extra*realizable
        quality_value=0.;trial=0.;uncertain=False
        if newgen>oldgen:
            newprice=self.quote(good,newgen)
            # Price uplift only on an evidenced ordinary sales stream.
            stream=min(external,after_output)
            quality_value=stream*max(0,newprice-realizable)
            # At most half of the last two rounds' known customers, plus a
            # single introductory trial if no customers are known yet.
            trial=min(max(0,after_output-stream),history['buyers']*.5 if history['buyers'] else 1.)
            quality_value+=trial*newprice
            if good=='electronics':quality_value+=rem  # at most 1G/round quality-income opportunity
            uncertain=True
        research,mg=self.upgrade_requirements(c,good)
        development_cost=self.upgrade_cost(c,good)
        prerequisite_cost=research*self.quote('ore')
        if mg and not self.count(c,'machine',False,min_gen=mg):prerequisite_cost+=self.quote('machine',mg)
        old_raw=self.projected_resources(c);new_raw=self.projected_resources(c,good)
        operating_extra=sum(max(0,new_raw[g]-old_raw[g])*self.quote(g) for g in ('ore','fuel'))*rem
        if good=='machine':
            # Adaptive plants do not run every remaining cycle. This opportunity
            # estimate uses output demand, while actual purchases still use the
            # exact v6 next-cycle material plan and funded-development guard.
            credits=0 if newgen==1 else 1 if newgen==2 else 2
            new_units=min(after_output,max(0,external+trial+domestic-self.count(c,'machine',False,min_gen=newgen)))
            raw=self.material_plan(p,min(9,self.r+1))['raw']
            operating_extra=math.ceil(new_units*credits/2)*self.quote(raw)
        cost=development_cost+prerequisite_cost+operating_extra
        benefit=capacity_value+quality_value
        score=benefit/max(1,cost)+(.30 if good==c.main else 0)
        if current==0:score*=.8
        return {'good':good,'through_round':self.r-1,'remaining_rounds':rem,
            'stock_after_current_use':stock,'future_domestic':domestic,'sales_forecast':external,
            'old_output_forecast':base_output,'new_output_forecast':after_output,
            'marginal_useful_units':useful_extra,'capacity_value':capacity_value,
            'quality_opportunity_value':quality_value,'quality_trial_units':trial,
            'uncertain_new_generation':uncertain,'development_cost':development_cost,
            'prerequisite_value':prerequisite_cost,'additional_operating_value':operating_extra,
            'opportunity_score':score,'eligible':score>=.45,
            'reason':'quality_opportunity' if quality_value else 'additional_use' if useful_extra else 'existing_supply_sufficient'}

    def plan(self,c):
        if not self.advice_policy.planning:return super().plan(c)
        if c.style in ('idle','trade') or self.r>=8:return None
        key=(self.r,c.name)
        if key in self.plan_cache:return self.plan_cache[key]
        choices=[g for g,lv in c.levels.items() if lv<4]
        if c.expand not in c.levels and self.r>=3:choices.append(c.expand)
        rows=[self.investment_advice(c,g) for g in choices]
        winner=max(rows,key=lambda r:(r['opportunity_score'],r['good'])) if rows else None
        selected=winner['good'] if winner and (winner['eligible'] or c.style=='invest') else None
        self.plan_cache[key]=selected
        self.advice_log.append({'kind':'investment','round':self.r,'country':c.name,
            'through_round':self.r-1,'selected':selected,'candidates':rows,
            'reason':'selected_opportunity' if selected else 'no_additional_use_case'})
        return selected

    def choose_focus(self,c):
        if not self.advice_policy.planning or c.style in ('idle','invest'):
            return super().choose_focus(c)
        if self.r>=9:return
        options=[];rem=9-self.r
        for good in c.levels:
            history=self.own_sales(c,good,through_round=self.r)
            base=self.base_quantity(c,good)
            if good=='machine':
                p=copy(c);p.focus=''
                base=self.machine_quantity(p,self.r+1,actual=True)
            output=self.cycle_output(c,good,focused=good)
            bonus=max(0,output-base)
            stock=self._stock_after_current_use(c,good)
            gap=max(0,self.future_domestic(c,good)+history['rate']*rem-stock-base*rem)
            useful=min(bonus*rem,gap)
            value=useful*self.quote(good)
            # No abstain option was added to the physical focus rule. If every
            # bonus is excess, prefer the smallest unwanted reference-value load.
            waste=max(0,bonus*rem-useful)*self.quote(good)
            options.append({'good':good,'base_output':base,'bonus':bonus,
                'marginal_useful_units':useful,'value':value,'excess_value':waste})
        best=max(options,key=lambda r:(r['value'],-r['excess_value'],r['good']))
        previous=c.focus;c.focus=best['good']
        self.advice_log.append({'kind':'focus','round':self.r,'country':c.name,
            'through_round':self.r,'previous':previous,'selected':c.focus,'candidates':options})

    def summary(self):
        result=super().summary()
        for name,c in self.cs.items():
            x=result['countries'][name]
            stats={ch:{'sold_units':0,'bought_units':0,'sales_cash':0,'purchase_cash':0}
                   for ch in ('market','direct','barter')}
            for tx in self.transactions:
                channel=tx['channel']
                for leg in tx['legs']:
                    if leg['seller']==name:stats[channel]['sold_units']+=len(leg['ids'])
                    if leg['buyer']==name:stats[channel]['bought_units']+=len(leg['ids'])
                if tx['cash']:
                    payer,payee,amount=tx['cash']
                    if payee==name:stats[channel]['sales_cash']+=amount
                    if payer==name:stats[channel]['purchase_cash']+=amount
            x['channel_stats']=stats
            x['grade_recalls']=sum(r['country']==name for r in self.grade_recall_log)
            x['planning_decisions']=sum(r['country']==name and r['kind']=='investment' for r in self.advice_log)
            x['planning_holds']=sum(r['country']==name and r['kind']=='investment' and r['selected'] is None for r in self.advice_log)
            x['public_offer_units']=sum(len(r['ids']) for r in self.offer_history if r['country']==name)
            x['all_goods_unique_used']=sum(x['use_by_good'].values())
            x['industry_use_score']=10*x['all_goods_unique_used']/max(1,sum(x['produced'].values()))
            x['industry_capacity_score']=x['industry']-x['industry_use_score'] if x['industry'] is not None else None
            x['economic_at_cap']=int(x['economic'] is not None and abs(x['economic']-25)<1e-9)
            x['offer_price_mismatches']=sum(row['country']==name and row['kind']=='offer'
                and row['price_applied'] and row['actual_prices']!=[row['recommendation']['price']]
                for row in self.advice_log)
            x['listing_plan_violations']=sum(row['country']==name and not row['within_plan'] for row in self.listing_plan_log)
            # Legacy UID preference overlaps are not necessarily a shortage:
            # another free, equal-grade unit can satisfy the same requirement.
            x['protected_offer_violations']=sum(self.advice_variant!='baseline' and row['country']==name
                and bool(set(row['actual_ids'])&set(row['protected_ids'])) for row in self.listing_plan_log)
            x['listed_by_good']={good:sum(len(o.units) for o in self.orders.values() if o.seller==name and o.good==good) for good in GOODS}
        for key in ('grade_recalls','planning_decisions','planning_holds','public_offer_units','all_goods_unique_used'):
            result['world'][key]=sum(x[key] for x in result['countries'].values())
        for key in ('offer_price_mismatches','listing_plan_violations','protected_offer_violations'):
            result['world'][key]=sum(x[key] for x in result['countries'].values())
        result['world']['v7_note']='Agent advice only; v6 coupled physics, all initial conditions and diagnostic scoring are unchanged.'
        return result

    def trace(self):
        result=super().trace()
        result.update(recommendations=self.advice_log,public_offers=self.offer_history,
                      grade_recalls=self.grade_recall_log,listing_plans=self.listing_plan_log)
        return result
