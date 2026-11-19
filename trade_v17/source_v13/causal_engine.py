"""v13 controlled causes on the preserved v12 economy.

The two AI factors are budget order and the existing early-durable investment
multiplier. The optional physical factor adds one existing raw bundle to each
electronics production cycle at industry level >= 2. It applies to every
producer, preserves level-one starter allowances, and introduces no cash fee.
No score, price floor, subsidy, compulsory buyer, or student action is added.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import math

from growth_scoring import Game as V12Game
from reference_engine import GOODS, FOOD, DURABLES, PRICE


@dataclass(frozen=True)
class CausalPolicy:
    operating_first: bool = False
    remove_durable_boost: bool = False
    electronics_extra_raw: int = 0


MODES = {
    'baseline': CausalPolicy(),
    'operating_first': CausalPolicy(operating_first=True),
    'no_durable_boost': CausalPolicy(remove_durable_boost=True),
    'ai_combined': CausalPolicy(True, True),
    'electronics_input': CausalPolicy(electronics_extra_raw=1),
    'combined_input': CausalPolicy(True, True, 1),
}
AI_MODES = tuple(MODES)[:4]
ECONOMIC_MODES = tuple(MODES)[4:]


class Game(V12Game):
    def __init__(self, seed=0, mode='baseline', focal=None, style='normal',
                 trade_enabled=True, behaviors=None):
        if mode not in MODES:
            raise ValueError('unknown causal variant')
        self.causal_mode = mode
        self.causal_policy = MODES[mode]
        self.causal_initializing = True
        self.causal_plan_log = []
        self.causal_buy_log = []
        self.causal_buy_capture = None
        super().__init__(seed, focal=focal, style=style,
                         trade_enabled=trade_enabled, behaviors=behaviors)
        self.causal_initializing = False
        # These are the audited execution settings, not new official decisions.
        assert self.policy.living_first and self.policy.household_guard
        assert not self.policy.stock_guard and not self.advice_policy.planning
        assert self.opt.budget_plans and not self.opt.storage_fees

    def resource_requirements(self, c, g, r=None):
        required = dict(super().resource_requirements(c, g, r))
        if (self.causal_policy.electronics_extra_raw and g == 'electronics'
                and c.levels.get(g, 0) >= 2):
            assert len(required) == 1 and set(required) <= {'ore', 'fuel'}
            raw = next(iter(required))
            required[raw] += self.causal_policy.electronics_extra_raw
        return required

    def _unboosted_base_plan(self, c):
        """The original core plan, changing only its 1.8 multiplier to 1.

        Seed its existing cache BEFORE entering the original filter/routing
        chain. This leaves all upstream waiting, alternate development,
        household and material protection in place.
        """
        choices = [g for g, lv in c.levels.items() if lv < 4]
        if c.expand not in c.levels and self.r >= 3:
            choices.append(c.expand)
        evidence = []
        for g in choices:
            cost = self.upgrade_cost(c, g)
            need = self.world_potential_need(g)
            surplus = sum(len(o.units) for o in self.orders.values() if o.good == g)
            rem = 9 - self.r
            marginal = 2 if g in FOOD else 1
            saturation = 1 + max(0, surplus - need) / max(1, need * 2)
            original_boost = 1.8 if g in DURABLES and c.levels.get(g, 0) < 3 else 1
            common = PRICE[g] * marginal * rem / cost / saturation
            main_bonus = .30 if g == c.main else 0
            expansion_factor = .8 if g not in c.levels else 1
            adaptive = 0.
            if self.flag('adaptive_expansion') and g not in c.levels:
                short = (sum(self.count(z, g, False) < math.ceil(self.pop()/2)
                             for z in self.cs.values()) if g == 'electronics' else 0)
                if short >= 3 and surplus == 0 and rem >= 3:
                    adaptive = min(1.8, short * .22)
            value = (common + main_bonus) * expansion_factor + adaptive
            original = (common * original_boost + main_bonus) * expansion_factor + adaptive
            evidence.append({'good': g, 'cost': cost, 'need': need,
                'surplus': surplus, 'remaining': rem, 'marginal': marginal,
                'saturation': saturation, 'base_price': PRICE[g],
                'original_boost': original_boost, 'main_bonus': main_bonus,
                'expansion_factor': expansion_factor, 'adaptive': adaptive,
                'score': value, 'original_score_same_state': original})
        winner = max(evidence, key=lambda x: (x['score'], x['good'])) if evidence else None
        selected = winner['good'] if winner else None
        if (winner and self.opt.saturation_aware and c.style != 'invest'
                and winner['score'] < .45):
            selected = None
        self.causal_plan_log.append({'round': self.r, 'country': c.name,
            'style': c.style, 'levels': dict(c.levels), 'candidates': evidence,
            'selected_base': selected, 'threshold': .45,
            'threshold_applies': bool(self.opt.saturation_aware and c.style != 'invest')})
        return selected

    def plan(self, c):
        if (self.causal_policy.remove_durable_boost and not self.causal_initializing
                and self.flag('budget_plans') and c.style not in ('idle', 'trade')
                and self.r < 8 and (self.r, c.name) not in self.plan_cache):
            self.plan_cache[(self.r, c.name)] = self._unboosted_base_plan(c)
        return super().plan(c)

    def purchase_plan(self, c):
        if not self.causal_policy.operating_first:
            return super().purchase_plan(c)
        if c.style == 'idle' or not self.opt.trade_enabled:
            return []
        wallet = c.cash
        target = self.targets(c)
        rows = []
        virtual = {g: self.count(c, g) for g in GOODS}
        initial_stock = dict(virtual)
        grades = {g: [self.units[i].gen for i in self.ids(c, g)] for g in DURABLES}
        project = self.plan(c)
        mg = self.upgrade_requirements(c, project)[1] if project else 0
        operating = self.next_resources(c)

        def add(good, want, min_gen=1, kind='need', hold=0, raw_goal=None):
            nonlocal wallet
            if want <= 0:
                return
            offers = [o.price for o in self.orders.values()
                      if o.good == good and o.gen >= min_gen and o.seller != c.name]
            price = min(offers) if offers else self.quote(good, min_gen)
            cushion = 0 if c.style == 'invest' or good in FOOD else 15
            quantity = min(want, max(0, wallet-cushion-hold)//price)
            budget = quantity * price
            row = {'good': good, 'want': want, 'quantity': quantity,
                   'unit_price': price, 'budget': budget, 'min_gen': min_gen, 'kind': kind}
            if raw_goal is not None:
                row['raw_goal'] = raw_goal
            rows.append(row)
            wallet -= budget
            virtual[good] += quantity
            if good in DURABLES:
                grades[good] += [min_gen] * quantity

        # Keep food first in the virtual wallet. Reserve ONLY currently installed
        # next-cycle inputs before living goods; research and expansion extras
        # remain later. Actual negotiation order is preserved below.
        for good in FOOD:
            add(good, max(0, target[good]-virtual[good]))
        for good in ('ore', 'fuel'):
            goal = min(target[good], operating.get(good, 0))
            add(good, max(0, goal-virtual[good]), kind='operating', raw_goal=goal)
        add('electronics', max(0, target['electronics']-virtual['electronics']))
        for good in ('ore', 'fuel'):
            add(good, max(0, target[good]-virtual[good]),
                kind='additional_raw', raw_goal=target[good])
        want = max(0, target['machine']-virtual['machine'])
        grade = mg if mg else 1
        if mg and max(grades['machine'], default=0) < mg:
            want = max(1, want)
        hold = (self.upgrade_cost(c, project)+self.reserve(c)) if mg else self.prep_budget(c)
        add('machine', want, grade, hold=hold)
        if self.flag('upgrade_living_goods') and self.r <= 7:
            used = sorted(grades['electronics'], reverse=True)[:math.ceil(self.pop()/2)]
            if len(used) == math.ceil(self.pop()/2) and used and min(used) < self.global_gen['electronics']:
                add('electronics', 1, min(used)+1, 'replacement',
                    self.reserve(c)+self.prep_budget(c))
        allocation = deepcopy(rows)
        merged = []
        for good in ('wheat', 'banana', 'electronics', 'ore', 'fuel', 'machine'):
            selected = [r for r in rows if r['good'] == good and r['kind'] != 'replacement']
            if not selected:
                continue
            if good in ('ore', 'fuel'):
                assert len({r['unit_price'] for r in selected}) == 1
                merged.append({'good': good, 'want': max(0, target[good]-initial_stock[good]),
                    'quantity': sum(r['quantity'] for r in selected),
                    'unit_price': selected[0]['unit_price'],
                    'budget': sum(r['budget'] for r in selected), 'min_gen': 1, 'kind': 'need'})
            else:
                assert len(selected) == 1
                merged.append(selected[0])
        merged.extend(r for r in rows if r['kind'] == 'replacement')
        rows = merged
        # Retain the inherited refusal filters if a compatible diagnostic uses
        # them later. Current public-price/participation scenarios do not do so.
        if c.name == getattr(self, 'machine_refusal_country', None):
            rows = [r for r in rows if not (r['good'] == 'machine'
                    and r['min_gen'] >= self.machine_refusal_grade)]
        if c.name == getattr(self, 'raw_refusal_country', None):
            rows = [r for r in rows if r['good'] not in self.raw_refusal_goods]
        if c.name == getattr(self, 'refuse_raw_country', None):
            rows = [r for r in rows if r['good'] not in ('ore', 'fuel')]
        assert sum(r['budget'] for r in rows) <= c.cash
        capture = self.causal_buy_capture
        if capture is not None and capture['country'] == c.name:
            capture.update(target=dict(target), operating=dict(operating),
                initial_stock=initial_stock, allocation=allocation, rows=deepcopy(rows))
        return rows

    def buy_phase(self, c, sweep):
        if not self.causal_policy.operating_first:
            return super().buy_phase(c, sweep)
        assert self.causal_buy_capture is None
        capture = {'round': self.r, 'country': c.name, 'sweep': sweep,
            'cash_before': c.cash, 'purchases_before': c.purchases,
            'transaction_start': len(self.transactions), 'rows': [], 'allocation': []}
        self.causal_buy_capture = capture
        try:
            # One original row per raw good, original transaction tags and
            # original execution order: no extra barter/negotiation opportunity.
            return super().buy_phase(c, sweep)
        finally:
            capture.update(cash_after=c.cash, purchases_after=c.purchases,
                           transaction_end=len(self.transactions))
            self.causal_buy_capture = None
            self.causal_buy_log.append(capture)

    def summary(self):
        result = super().summary()
        for name, c in result['countries'].items():
            attempts = [a for a in self.evaluation_attempts if a['country'] == name]
            legal = [a for a in attempts if a['legal']]
            feasible = [a for a in legal if a['cash_ok'] and a['household_ok']
                        and a['raw_ok'] and (not a['machine_min_gen'] or a['free_qualified_ids'])]
            c['causal'] = {
                'cash_trade_balance': c['revenue']-c['purchases'],
                'cash_before_investment_balance': c['revenue']-c['purchases']+c['tax'],
                'cash_change': c['cash']-c['start_cash'],
                'legal_planned_attempts': len(legal),
                'cash_ready_attempts': sum(a['cash_ok'] for a in legal),
                'feasible_planned_attempts': len(feasible),
                'successful_attempts': sum(a['successful'] for a in legal),
                'no_upgrade': int(c['upgrades_total'] == 0),
                'blocked_cash_attempts': sum(not a['cash_ok'] for a in legal),
                'blocked_household_attempts': sum(not a['household_ok'] for a in legal),
                'blocked_raw_attempts': sum(not a['raw_ok'] for a in legal),
                'blocked_machine_attempts': sum(bool(a['machine_min_gen']) and not a['free_qualified_ids'] for a in legal),
            }
            by_good = {}
            for good in GOODS:
                levels = (1, 2, 3) if good in DURABLES else (1,)
                cash_by_gen = {str(g): 0. for g in levels}
                sold_by_gen = {str(g): 0 for g in levels}
                receipts = {'own_produced': 0., 'own_initial': 0., 'resold_foreign': 0.}
                for tx in self.transactions:
                    for leg in tx['legs']:
                        if leg['seller'] != name or self.units[leg['ids'][0]].good != good:
                            continue
                        first = self.units[leg['ids'][0]]
                        sold_by_gen[str(first.gen)] += len(leg['ids'])
                        if not tx['cash']:
                            continue
                        amount = tx['cash'][2]
                        cash_by_gen[str(first.gen)] += amount
                        share = amount / len(leg['ids'])
                        for uid in leg['ids']:
                            u = self.units[uid]
                            key = ('resold_foreign' if u.origin != name else
                                   'own_initial' if u.born == 0 else 'own_produced')
                            receipts[key] += share
                raw = {g: sum(row['required'].get(g, 0) for row in self.production_trace
                              if row['country'] == name and row['industry'] == good and row['funded'])
                       for g in ('ore', 'fuel')}
                by_good[good] = {
                    'cash_sales': c['sale_by_good'][good],
                    'cash_purchases': c['purchase_by_good'][good],
                    'investment_cash': sum(e['cash_cost'] for e in self.development_log
                                           if e['country'] == name and e['industry'] == good),
                    'produced': c['produced'].get(good, 0),
                    'used': c['use_by_good'][good],
                    'useful_exports': c['export_used_by_good'][good],
                    'production_raw_inputs': raw,
                    'cash_sales_by_generation': cash_by_gen,
                    'transferred_units_by_generation': sold_by_gen,
                    'cash_sale_origin': receipts,
                }
            assert sum(x['investment_cash'] for x in by_good.values()) == c['investment']
            for raw in ('ore', 'fuel'):
                assert sum(x['production_raw_inputs'][raw] for x in by_good.values()) == c['production_raw'][raw]
            c['economic_decomposition'] = by_good
        result['world']['causal_mode'] = self.causal_mode
        result['world']['causal_policy'] = asdict(self.causal_policy)
        result['world']['causal_plan_rows'] = len(self.causal_plan_log)
        result['world']['causal_buy_rows'] = len(self.causal_buy_log)
        result['world']['causal_scope'] = {
            'official_score_unchanged': True,
            'storage_enabled': self.opt.storage_fees,
            'extra_manufacturing_cash_fee': 0, 'sales_fee': 0,
            'student_rules_changed': bool(self.causal_policy.electronics_extra_raw),
            'changes_are_candidates': True,
            'opportunity_scope': 'AI selected project, not every possible legal investment',
        }
        return result

    def trace(self):
        result = super().trace()
        result['causal_plan_log'] = self.causal_plan_log
        result['causal_buy_log'] = self.causal_buy_log
        return result
