"""v8: starter resources and MACHINE-ONLY material efficiency on v7 price.

The 2-to-1 credit experiment increases machine input intensity at unchanged
bundle prices. It is NOT a global half-size commodity redenomination.
Electronics recipes, development materials, cash, pricing, agents and scores
are inherited. No automatic buyer, subsidy, forced use or new score exists.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import math
import statistics

from recommendation_engine import Game as V7
from budget_trace import Game as PhysicalChecks
from machinery_engine import UPKEEP_USES
from reference_engine import GOODS

RAW_GOODS = ('ore', 'fuel')
SOURCE_KINDS = ('initial_own', 'initial_foreign', 'produced_own', 'produced_foreign')


@dataclass(frozen=True)
class RawPolicy:
    machine_credits: int = 2
    starter: str = 'legacy'

    def __post_init__(self):
        if type(self.machine_credits) is not int or self.machine_credits not in (1, 2):
            raise ValueError('machine credits must be 1 or 2')
        if self.starter not in ('legacy', 'first_cycle', 'two_cycles', 'none'):
            raise ValueError('unknown starter profile')


RAW_MODES = {
    'baseline': RawPolicy(2, 'legacy'),
    'starter': RawPolicy(2, 'first_cycle'),
    'bridge': RawPolicy(2, 'two_cycles'),
    'recipe': RawPolicy(1, 'legacy'),
    'coupled': RawPolicy(1, 'first_cycle'),
    'no_starter': RawPolicy(2, 'none'),
    'strict_no_starter': RawPolicy(1, 'none'),
}
REFUSAL_STYLES = {'no_ore': ('ore',), 'no_fuel': ('fuel',), 'no_raw': RAW_GOODS}


class Game(V7):
    def __init__(self, seed=0, variant='baseline', focal=None, style='normal', trade_enabled=True):
        if variant not in RAW_MODES:
            raise ValueError('unknown raw-resource variant')
        self.raw_variant = variant
        self.raw_policy = RAW_MODES[variant]
        self.raw_initializing = True
        self.raw_use_log = []
        self.raw_round_ledger = []
        self.starter_allocation = {}
        self.raw_refusal_country = focal if style in REFUSAL_STYLES else None
        self.raw_refusal_goods = REFUSAL_STYLES.get(style, ())
        super().__init__(seed, variant='price', focal=focal,
                         style='normal' if style in REFUSAL_STYLES else style,
                         trade_enabled=trade_enabled)
        self.raw_initializing = False
        if self.raw_refusal_goods and self.raw_refusal_country not in self.cs:
            raise ValueError('resource refusal requires a valid focal country')
        if self.raw_policy.starter in ('first_cycle', 'two_cycles'):
            # Production precedes trading. Supply exactly round-one actual
            # requirements. The bridge additionally funds the second cycle at
            # the STARTING technology/focus, never a prospective upgrade.
            for c in self.cs.values():
                required = Counter()
                cycles = (1,2) if self.raw_policy.starter == 'two_cycles' else (1,)
                for cycle in cycles:
                    for good in c.levels:
                        if good == 'machine':
                            q = self.machine_quantity(c, cycle, actual=True)
                            required.update(self.material_plan(c, cycle, q)['required'])
                        else:
                            required.update(self.resource_requirements(c, good, cycle))
                for raw in RAW_GOODS:
                    if required[raw]:
                        self.mint(c, raw, required[raw], initial=True)
        self.starter_allocation = {
            n: {g:self.count(c, g, False) for g in RAW_GOODS} for n,c in self.cs.items()
        }
        # Same asset formula, using the goods actually granted. No compensating
        # cash is added; this baseline shift is reported separately from scores.
        self.initial_assets = {n:c.cash+self.stock_value(c) for n,c in self.cs.items()}

    def mint(self, c, g, n, gen=1, initial=False):
        if initial and self.raw_initializing and g in RAW_GOODS and self.raw_policy.starter != 'legacy':
            n = 0
        return super().mint(c, g, n, gen, initial)

    def material_plan(self, c, production_round, quantity=None):
        # Parent chooses raw by round/specialization, generation and scoped key.
        # Recompute only the batch/credit arithmetic; never change a module global.
        plan = super().material_plan(c, production_round, quantity)
        before = plan['credits_before']
        spent = plan['credits_spent']
        size = self.raw_policy.machine_credits
        batches = math.ceil(max(0, spent-before)/size)
        plan.update(required={plan['raw']:batches} if batches else {},
                    raw_spent=batches, credits_after=before+size*batches-spent,
                    credits_per_raw=size)
        return plan

    def purchase_plan(self, c):
        rows = super().purchase_plan(c)
        if c.name == self.raw_refusal_country:
            return [row for row in rows if row['good'] not in self.raw_refusal_goods]
        return rows

    def settle_transaction(self, legs, cash, channel, action_id):
        if self.raw_refusal_country and isinstance(legs, list):
            for leg in legs:
                if isinstance(leg, dict) and leg.get('buyer') == self.raw_refusal_country:
                    ids = leg.get('ids', [])
                    if not isinstance(ids, list):
                        return False
                    if any(type(i) is int and i in self.units and
                           self.units[i].good in self.raw_refusal_goods for i in ids):
                        return False
        return super().settle_transaction(legs, cash, channel, action_id)

    def consume(self, c, g, n, purpose):
        selected = super().consume(c, g, n, purpose)
        if g in RAW_GOODS:
            for uid in selected:
                u = self.units[uid]
                source = ('initial_' if u.born == 0 else 'produced_') + ('own' if u.origin == c.name else 'foreign')
                self.raw_use_log.append({
                    'round':self.r, 'country':c.name, 'good':g, 'purpose':purpose,
                    'uid':uid, 'born':u.born, 'origin':u.origin, 'source':source,
                    'import_transaction':u.last_import,
                })
        return selected

    def _raw_counts(self, name, good, round_number=None):
        uses = [e for e in self.raw_use_log if e['country']==name and e['good']==good
                and (round_number is None or e['round']==round_number)]
        return {
            'consumed':len(uses),
            'production':sum(e['purpose']=='production' for e in uses),
            'research':sum(e['purpose']=='development' for e in uses),
            'imported_used':sum(e['import_transaction'] is not None for e in uses),
            **{source:sum(e['source']==source for e in uses) for source in SOURCE_KINDS},
        }

    def update_prices(self):
        result = super().update_prices()
        for name,c in self.cs.items():
            production = [e for e in self.production_trace if e['country']==name and e['round']==self.r]
            previous = next((row for row in reversed(self.raw_round_ledger) if row['country']==name), None)
            flows = {g:{'imports':0, 'exports':0, 'purchases':0, 'sales':0} for g in RAW_GOODS}
            for tx in self.transactions:
                if tx['round'] != self.r:
                    continue
                for leg in tx['legs']:
                    good = self.units[leg['ids'][0]].good
                    if good not in RAW_GOODS:
                        continue
                    if leg['buyer']==name:flows[good]['imports'] += len(leg['ids'])
                    if leg['seller']==name:flows[good]['exports'] += len(leg['ids'])
                if tx['cash']:
                    payer,payee,amount = tx['cash']
                    good = self.units[tx['legs'][0]['ids'][0]].good
                    if good in RAW_GOODS:
                        if payer==name:flows[good]['purchases'] += amount
                        if payee==name:flows[good]['sales'] += amount
            self.raw_round_ledger.append({
                'round':self.r, 'country':name, 'cash':c.cash, 'happy':c.happy,
                'food_met':self.r in c.satisfied_rounds,
                'production_failures':sum(not e['funded'] for e in production),
                'machine_generation':c.machine_tech, 'electronics_generation':c.elec_tech,
                'goods':{g:{**self._raw_counts(name,g,self.r), **flows[g],
                            'opening_stock':previous['goods'][g]['stock'] if previous else self.starter_allocation[name][g],
                            'produced':sum(u.origin==name and u.good==g and u.born==self.r for u in self.units.values()),
                            'stock':self.count(c,g,False),
                            'machine_credits_by_grade':{str(grade):self.material_credit[(name,g,grade)] for grade in (1,2,3)},
                            'unmet_production':sum(max(0,e['required'].get(g,0)-e['available_before'][g]) for e in production)}
                         for g in RAW_GOODS},
            })
        return result

    def verify(self):
        # Reuse all v1-v5 money/goods/escrow/need checks. v6's sole fixed-size
        # credit checker is reproduced below with the instance parameter.
        # v7 introduces no verify override. No invariant is silently disabled.
        result = PhysicalChecks.verify(self)
        size = self.raw_policy.machine_credits
        assert all(type(v) is int and 0 <= v < size for v in self.material_credit.values())
        assert all(type(v) is int and 0 <= v < UPKEEP_USES for v in self.upkeep_wear.values())
        for e in self.material_events:
            assert e['credits_per_raw'] == size
            assert e['credits_after'] == e['credits_before']+size*e['raw_spent']-e['credits_spent']
        assert all(e['produced']==0 and not e['raw_used'] for e in self.machine_output_log if e['status']=='paused')
        assert all(e['generation']==1 and e['produced']==1 for e in self.machine_output_log if e['status']=='fallback')
        assert all(e['produced']<=e['capacity'] for e in self.machine_output_log)
        assert len({e['uid'] for e in self.raw_use_log}) == len(self.raw_use_log)
        for e in self.raw_use_log:
            u = self.units[e['uid']]
            assert u.good==e['good'] and u.owner is None and u.used
            assert (u.use_round,u.use_country,u.use_purpose)==(e['round'],e['country'],e['purpose'])
        return result

    def summary(self):
        result = super().summary()
        for name,c in self.cs.items():
            x = result['countries'][name]
            rows = [r for r in self.raw_round_ledger if r['country']==name]
            x['starter_raw'] = dict(self.starter_allocation[name])
            x['raw_use'] = {g:self._raw_counts(name,g) for g in RAW_GOODS}
            x['raw_import_rounds'] = {g:sum(r['goods'][g]['imports']>0 for r in rows) for g in RAW_GOODS}
            x['first_raw_import_round'] = {g:min((r['round'] for r in rows if r['goods'][g]['imports']),default=10) for g in RAW_GOODS}
            x['raw_importing'] = {g:int(any(r['goods'][g]['imports'] for r in rows)) for g in RAW_GOODS}
            x['initial_raw_left'] = {g:sum(self.units[i].good==g and self.units[i].born==0 for i in c.stock) for g in RAW_GOODS}
            x['raw_unmet_production'] = {g:sum(r['goods'][g]['unmet_production'] for r in rows) for g in RAW_GOODS}
            x['first_two_happy'] = statistics.mean(r['happy'] for r in rows if r['round']<=2)
            x['first_two_food_short'] = sum(not r['food_met'] for r in rows if r['round']<=2)
            x['first_two_production_failures'] = sum(r['production_failures'] for r in rows if r['round']<=2)
            x['first_round_happy'] = rows[0]['happy']
            x['first_round_production_failures'] = rows[0]['production_failures']
            x['start_asset_value'] = self.initial_assets[name]
            x['end_asset_value'] = c.cash+self.stock_value(c)+.45*c.investment
            x['cash_plus_stock_value'] = c.cash+self.stock_value(c)
            x['machine_free_basic'] = sum(e['country']==name and e['generation']==1 and e['produced']==1 and not e['raw_used'] and e['status']=='regular' for e in self.machine_output_log)
            for good in ('machine','electronics'):
                tech = self.tech_for(c,good)
                for grade in (2,3):
                    x[f'{good}_g{grade}'] = int(good in c.levels and tech>=grade)
            for g in RAW_GOODS:
                assert x['raw_use'][g]['production']==x['production_raw'][g]
                assert x['raw_use'][g]['research']==x['research_raw'][g]
                assert sum(r['goods'][g]['imports'] for r in rows)==x['import_goods'].get(g,0)
        w = result['world']
        for key in ('starter_raw','initial_raw_left','raw_importing','raw_import_rounds','raw_unmet_production'):
            w[key] = {g:sum(c[key][g] for c in result['countries'].values()) for g in RAW_GOODS}
        w['raw_use'] = {g:{key:sum(c['raw_use'][g][key] for c in result['countries'].values())
                            for key in self._raw_counts(next(iter(self.cs)),g)} for g in RAW_GOODS}
        for key in ('first_two_food_short','first_two_production_failures','first_round_production_failures',
                    'machine_free_basic','machine_g2','machine_g3','electronics_g2','electronics_g3'):
            w[key] = sum(c[key] for c in result['countries'].values())
        for key in ('first_two_happy','first_round_happy'):
            w[key] = statistics.mean(c[key] for c in result['countries'].values())
        w['initial_asset_value'] = sum(c['start_asset_value'] for c in result['countries'].values())
        w['end_asset_value'] = sum(c['end_asset_value'] for c in result['countries'].values())
        w['raw_policy'] = asdict(self.raw_policy)
        w['v7_note'] = 'v7 price advice inherited; v8 explicitly varies starter resources and machine-only material efficiency.'
        w['v8_note'] = 'Raw bundle prices, electronics/research recipes and all score formulas unchanged. No-starter profiles are boundary diagnostics.'
        return result

    def trace(self):
        result = super().trace()
        result.update(raw_use=self.raw_use_log, raw_ledger=self.raw_round_ledger,
                      starter_allocation=self.starter_allocation,
                      raw_policy=asdict(self.raw_policy))
        return result
