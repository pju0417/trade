"""v5 controlled AI budget policies. All physical/economic game rules stay v4.

No special grants, forced buyers, price or score changes. 'stock_guard' is an
EXPERIMENT, not a new production rule: automatic agents may postpone input
shopping, and the unchanged G1 safety-production rule still applies.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from copy import copy
import math
from expansion_engine import Game as V4Game
from reference_engine import GOODS, FOOD, DURABLES, BONUS


@dataclass(frozen=True)
class Policy:
    funded_development: bool = False
    living_first: bool = False
    household_guard: bool = False
    stock_guard: bool = False


POLICIES = {
    'baseline': Policy(),
    'funded': Policy(funded_development=True),
    'living': Policy(funded_development=True, living_first=True),
    'balanced': Policy(funded_development=True, living_first=True, household_guard=True),
    'stock_guard': Policy(funded_development=True, living_first=True, stock_guard=True),
}


class Game(V4Game):
    def __init__(self, seed=0, variant='baseline', focal=None, style='normal',
                 trade_enabled=True):
        if variant not in POLICIES:
            raise ValueError('unknown policy')
        self.variant = variant
        self.policy = POLICIES[variant]
        self.funding_blocks = []
        self.household_blocks = []
        self.input_deferrals = set()
        self.stock_plan_cache = {}
        super().__init__(seed, 'roles', focal=focal, style=style,
                         fixes=True, trade_enabled=trade_enabled)

    def projected_resources(self, c, project=None):
        """Pure next-cycle requirements AFTER a proposed investment.

        Development materials are separate, consumed before these inputs.
        The physical production recipe is inherited unchanged from v4.
        """
        if self.r >= 9:
            return Counter()
        p = copy(c)
        p.levels = dict(c.levels)
        if project:
            level = p.levels.get(project, 0) + 1
            p.levels[project] = level
            if project == 'machine':
                p.machine_tech = min(3, level)
            if project == 'electronics':
                p.elec_tech = min(3, level)
        need = Counter()
        for good in p.levels:
            need.update(self.resource_requirements(p, good, self.r + 1))
        return need

    def excessive_current_stock(self, c, good):
        if good not in DURABLES or good not in c.levels:
            return False
        # Do not mistake an obsolete stockpile for available new-grade products.
        grade = self.tech_for(c, good)
        unused = sum(self.units[i].origin == c.name and not self.units[i].used
                     and self.units[i].gen >= grade
                     for i in self.ids(c, good, False))
        protected = math.ceil(self.pop()/2) if good == 'electronics' else self.equip_slots(c)
        cycle = self.base_quantity(c, good) + (BONUS[good] if c.focus == good else 0)
        return max(0, unused - protected) > 2 * cycle

    def next_resources(self, c):
        if not self.policy.stock_guard or c.style in ('idle', 'invest'):
            return super().next_resources(c)
        if self.r >= 9:
            return Counter()
        need = Counter()
        for good in c.levels:
            if self.excessive_current_stock(c, good):
                continue
            need.update(self.resource_requirements(c, good, self.r+1))
        return need

    def plan(self, c):
        if not self.policy.stock_guard or c.style in ('idle', 'invest'):
            return super().plan(c)
        key = (self.r, c.name)
        if key not in self.stock_plan_cache:
            project = super().plan(c)
            if project and self.excessive_current_stock(c, project):
                project = None
            self.stock_plan_cache[key] = project
            self.plan_cache[key] = project
        return self.stock_plan_cache[key]

    def targets(self, c):
        t = super().targets(c)
        if not self.policy.funded_development:
            return t
        project = self.plan(c)
        # Preserve the v4 research-shopping affordability gate; the only change
        # is to count the subsequent production recipe as well as development.
        if project and c.cash >= self.upgrade_cost(c, project) + 20:
            post = self.projected_resources(c, project)
            research_ore, _ = self.upgrade_requirements(c, project)
            for raw in ('ore', 'fuel'):
                t[raw] = max(t[raw], post[raw] + (research_ore if raw == 'ore' else 0))
        return t

    def purchase_plan(self, c):
        if not self.policy.living_first:
            return super().purchase_plan(c)
        if c.style == 'idle' or not self.opt.trade_enabled:
            return []
        wallet = c.cash
        t = self.targets(c)
        plan = []
        virtual = {g:self.count(c, g) for g in GOODS}
        grades = {g:[self.units[i].gen for i in self.ids(c, g)] for g in DURABLES}
        project = self.plan(c)
        mg = self.upgrade_requirements(c, project)[1] if project else 0

        def add(good, want, min_gen=1, kind='need', hold=0):
            nonlocal wallet
            if want <= 0:
                return
            offers = [o.price for o in self.orders.values()
                      if o.good == good and o.gen >= min_gen and o.seller != c.name]
            price = min(offers) if offers else self.quote(good, min_gen)
            cushion = 0 if c.style == 'invest' or good in FOOD else 15
            qty = min(want, max(0, wallet-cushion-hold)//price)
            budget = qty * price
            plan.append({'good':good, 'want':want, 'quantity':qty, 'unit_price':price,
                         'budget':budget, 'min_gen':min_gen, 'kind':kind})
            wallet -= budget
            virtual[good] += qty
            if good in DURABLES:
                grades[good] += [min_gen] * qty

        # A controlled order change only. An unfilled household quantity comes
        # before operating inputs; optional newer-model replacement stays last.
        for good in ('wheat', 'banana', 'electronics', 'ore', 'fuel', 'machine'):
            want = max(0, t[good]-virtual[good])
            grade = mg if good == 'machine' and mg else 1
            if good == 'machine' and mg and max(grades[good], default=0) < mg:
                want = max(1, want)
            hold = 0
            if good == 'machine':
                hold = (self.upgrade_cost(c,project)+self.reserve(c)) if mg else self.prep_budget(c)
            add(good, want, grade, hold=hold)
        if self.flag('upgrade_living_goods') and self.r <= 7:
            used = sorted(grades['electronics'], reverse=True)[:math.ceil(self.pop()/2)]
            if len(used) == math.ceil(self.pop()/2) and used and min(used) < self.global_gen['electronics']:
                add('electronics', 1, min(used)+1, 'replacement', self.reserve(c)+self.prep_budget(c))
        assert sum(x['budget'] for x in plan) <= c.cash
        return plan

    def buy_phase(self, c, sweep):
        if self.policy.stock_guard and c.style not in ('idle', 'invest') and self.r < 9:
            target = self.targets(c)
            full = self.projected_resources(c)
            for good in c.levels:
                recipe = self.resource_requirements(c,good,self.r+1)
                reduced = any(target[raw] < full[raw] and self.count(c,raw) < full[raw]
                              for raw in recipe)
                if self.excessive_current_stock(c, good) and reduced:
                    self.input_deferrals.add((self.r, c.name, good))
        return super().buy_phase(c, sweep)

    def invest(self, c, action_id=None):
        if action_id is not None and (not isinstance(action_id,str) or not action_id):
            return False
        if not self.policy.funded_development:
            return super().invest(c, action_id)
        if action_id is not None and action_id in self.invest_actions:
            return super().invest(c, action_id)
        if (self.r,c.name) in self.invested_rounds or c.style in ('idle','trade') or self.r >= 8:
            return super().invest(c, action_id)
        project = self.plan(c)
        if project:
            reserve = 0 if c.style == 'invest' else self.reserve(c)
            if c.cash >= self.upgrade_cost(c,project)+reserve:
                if self.policy.household_guard and c.style != 'invest':
                    food_met = self.r in c.satisfied_rounds
                    living_met = self.count(c,'electronics') >= math.ceil(self.pop()/2)
                    if not food_met or not living_met:
                        self.household_blocks.append({'round':self.r,'country':c.name,
                            'project':project,'food_met':food_met,'living_quantity_met':living_met})
                        if action_id is not None:
                            self.invest_actions[action_id] = False
                            self.invest_payloads[action_id] = (self.r,c.name)
                        return False
                required = self.projected_resources(c, project)
                research, _ = self.upgrade_requirements(c, project)
                required['ore'] += research
                missing = {g:q-self.count(c,g) for g,q in required.items() if self.count(c,g) < q}
                if missing:
                    self.funding_blocks.append({'round':self.r,'country':c.name,
                        'project':project,'missing_after_development':missing})
                    # This is an automatic-agent decision, NOT a new legal
                    # investment constraint for student commands in a web app.
                    if action_id is not None:
                        self.invest_actions[action_id] = False
                        self.invest_payloads[action_id] = (self.r,c.name)
                    return False
        return super().invest(c, action_id)
