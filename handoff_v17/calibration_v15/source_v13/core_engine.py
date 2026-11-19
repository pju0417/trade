"""#11 economic engine v2: audited commands, budgeted plans, opportunity scoring.

Standard-library-only serial model, NOT an authenticated multiplayer server.
Reference engine is preserved byte-for-byte. Changes have independent flags.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter, defaultdict
import math, json, statistics
import reference_engine as ref
from reference_engine import NAMES, GOODS, PRICE, FOOD, DURABLES, CONFIG, INVEST, BONUS, clip, half_up5

@dataclass(frozen=True)
class Options(ref.Options):
    budget_plans: bool = True
    adaptive_expansion: bool = True
    upgrade_living_goods: bool = True
    production_reserve: bool = False

class Game(ref.Game):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.needs_ledger = []
        self.use_episodes = set()
        self.invested_rounds = set()
        self.invest_actions = {}
        self.invest_payloads = {}
        self.plan_cache = {}
        self.construction_reserves = {}
        self.replacement_purchases = Counter()
        self.last_need_round = -1
        self.next_resources_cache = {}
        self.round_plan_diagnostics = []
        self.launch_events = []
        self.audit_checks = 0

    def flag(self, key):
        return getattr(self.opt, key, False)

    def settle_transaction(self, legs, cash, channel, action_id):
        """Validate shape, identities, consideration and escrow before mutations.

        This economic command assumes authenticated callers. It is not a public API.
        Gifts and mixed money+barter were not selected by the user; reject them.
        """
        if not isinstance(action_id, str) or not action_id:
            return False
        if channel not in ('market', 'direct', 'barter') or not isinstance(legs, list):
            return False
        if len(legs) != (2 if channel == 'barter' else 1):
            return False
        for leg in legs:
            if not isinstance(leg, dict) or set(leg) != {'seller', 'buyer', 'ids'}:
                return False
            if leg['seller'] not in self.cs or leg['buyer'] not in self.cs or leg['seller'] == leg['buyer']:
                return False
            ids = leg['ids']
            if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in self.units for i in ids):
                return False
            if len({(self.units[i].good, self.units[i].gen) for i in ids}) != 1:
                return False
        all_ids = [i for leg in legs for i in leg['ids']]
        if len(all_ids) != len(set(all_ids)):
            return False
        if channel == 'barter':
            if cash is not None:
                return False
            a, b = legs
            if (a['seller'], a['buyer']) != (b['buyer'], b['seller']):
                return False
            if self.units[a['ids'][0]].good == self.units[b['ids'][0]].good:
                return False
        else:
            if not isinstance(cash, (tuple, list)) or len(cash) != 3:
                return False
            payer, payee, amount = cash
            leg = legs[0]
            if (payer, payee) != (leg['buyer'], leg['seller']):
                return False
            if type(amount) is not int or amount <= 0 or amount % getattr(self.opt, "price_tick", 5):
                return False
        # The parent performs idempotency before checking ownership/cash again.
        return super().settle_transaction(legs, cash, channel, action_id)

    def make_order(self, c, ids, price):
        if type(price) is not int:
            raise ValueError("price must be an integer, not boolean")
        return super().make_order(c, ids, price)

    def mint(self, c, g, n, gen=1, initial=False):
        if g not in GOODS or type(n) is not int or n < 0 or type(gen) is not int or gen not in (1, 2, 3):
            raise ValueError('invalid production quantity, product or generation')
        if g not in DURABLES and gen != 1:
            raise ValueError('raw goods have no technology generation')
        return super().mint(c, g, n, gen, initial)

    def mark_use(self, c, uid, purpose):
        # One physical durable may support multiple episodes on different rounds,
        # never several times in a single episode merely because a button repeats.
        key = (self.r, c.name, uid, purpose)
        if key in self.use_episodes:
            return
        result = super().mark_use(c, uid, purpose)
        self.use_episodes.add(key)
        return result

    def record_need(self, c, good, quantity, purpose, used_ids=(), min_gen=1):
        """Needed externally = real demand minus qualifying domestic-origin stock.

        Own listed stock still counts as an available domestic alternative for
        scoring; listing it does not manufacture a rewarded import shortage.
        Consumption is recorded before inventory is removed.
        """
        if quantity <= 0:
            return
        own = sum(self.units[i].origin == c.name for i in self.ids(c, good, False, min_gen))
        external = max(0, quantity - own)
        imported_used = sum(self.units[i].origin != c.name and self.units[i].last_import is not None for i in used_ids)
        fulfilled = min(external, imported_used)
        self.needs_ledger.append({'round': self.r, 'country': c.name, 'good': good,
                                  'purpose': purpose, 'needed': quantity,
                                  'external': external, 'fulfilled': fulfilled,
                                  'used_ids': list(used_ids)})

    def consume(self, c, g, n, purpose):
        # Explicit need records for requested-but-unavailable amounts are made by
        # production/settlement. Development records only resources genuinely used.
        if purpose == 'development':
            self.record_need(c, g, n, purpose, self.ids(c, g)[:n])
        return super().consume(c, g, n, purpose)

    def plan(self, c):
        if not self.flag('budget_plans'):
            return super().plan(c)
        if c.style in ('idle', 'trade') or self.r >= 8:
            return None
        key = (self.r, c.name)
        if key in self.plan_cache:
            return self.plan_cache[key]
        choices = [g for g, lv in c.levels.items() if lv < 4]
        if c.expand not in c.levels and self.r >= 3:
            choices.append(c.expand)
        if not choices:
            self.plan_cache[key] = None
            return None
        scores = []
        for g in choices:
            cost = self.upgrade_cost(c, g)
            need = self.world_potential_need(g)
            surplus = sum(len(o.units) for o in self.orders.values() if o.good == g)
            rem = 9 - self.r
            marginal = 2 if g in FOOD else 1
            tech = 1.8 if g in DURABLES and c.levels.get(g, 0) < 3 else 1
            saturation = 1 + max(0, surplus - need) / max(1, need * 2)
            score = (PRICE[g] * marginal * rem * tech / cost) / saturation
            score += .30 if g == c.main else 0
            if g not in c.levels:
                score *= .8
            if self.flag('adaptive_expansion') and g not in c.levels:
                # Existing expansion path only. React to publicly visible unmet
                # need FLAGS (not private quantities) and absence of market offers,
                # never to an idle-state cheat.
                short = sum(self.count(z, g, False) < math.ceil(self.pop()/2)
                            for z in self.cs.values()) if g == 'electronics' else 0
                if short >= 3 and surplus == 0 and rem >= 3:
                    score += min(1.8, short * .22)
            scores.append((score, g))
        score, g = max(scores)
        if self.opt.saturation_aware and c.style != 'invest' and score < .45:
            g = None
        self.plan_cache[key] = g
        return g

    def reserve(self, c):
        if not self.flag('production_reserve'):
            return super().reserve(c)
        if self.r >= 9:
            return 20
        next_round = self.r+1
        food = 0
        for g in FOOD:
            own_output = self.base_quantity(c,g) if g in c.levels else 0
            deficit = max(0,self.food_need(next_round)-self.count(c,g,False)-own_output)
            food += deficit*self.quote(g)
        inputs = sum(max(0,n-self.count(c,g,False))*self.quote(g)
                     for g,n in self.next_resources(c).items())
        # Genuine emergency cushion; domestic food does not require buying food
        # twice. This is an automatic-agent safety policy, not a student lockout.
        return max(20,food+inputs+20)

    def prep_budget(self, c):
        g = self.plan(c)
        if not self.flag('budget_plans') or not g:
            return 0
        # Protect a real, affordable project or save toward the existing
        # electronics expansion if there is a public market shortage.
        cost = self.upgrade_cost(c, g)
        food_reserve = sum(max(0, self.food_need() - self.count(c, f)) * self.quote(f) for f in FOOD)
        ore, mg = self.upgrade_requirements(c, g)
        material_cost = max(0, ore - self.count(c, 'ore')) * self.quote('ore')
        if mg and not self.count(c, 'machine', min_gen=mg):
            material_cost += self.quote('machine', mg)
        saving_expansion = self.flag('adaptive_expansion') and g not in c.levels and g == 'electronics'
        if saving_expansion or c.cash >= cost + self.reserve(c) + material_cost:
            return min(cost, max(0, c.cash - food_reserve - 25))
        return 0

    def targets(self, c):
        t = super().targets(c)
        if self.flag('budget_plans'):
            # No machine shopping simply because a country has industries:
            # support applies to one focused non-industrial facility. Retain
            # already-held equipment for grade/research conditions as before.
            nonindustrial = any(g not in DURABLES for g in c.levels)
            pg = self.plan(c)
            mg = self.upgrade_requirements(c, pg)[1] if pg else 0
            t['machine'] = (self.equip_slots(c) if nonindustrial else 0)
            if mg:
                t['machine'] = max(t['machine'], 1)
        return t

    def buy_phase(self, c, sweep):
        if not self.flag('budget_plans'):
            return super().buy_phase(c, sweep)
        if c.style == 'idle' or not self.opt.trade_enabled:
            return
        for g in ('wheat', 'banana', 'electronics', 'ore', 'fuel', 'machine'):
            want = self.need(c, g)
            if want <= 0:
                continue
            essentials = sum(max(0, self.food_need() - self.count(c, f))*self.quote(f) for f in FOOD if f != g)
            # Basic food, currently missing living goods and actual production
            # inputs take priority. Research savings only restrict optional kit.
            hold = 0
            if g == 'machine':
                hold = self.prep_budget(c)
            keep = 0 if c.style == 'invest' else essentials + (0 if g in FOOD else 15) + hold
            budget = max(0, c.cash - keep)
            if self.opt.negotiations and g not in FOOD and (budget < self.quote(g)*want or sweep % 2 == 1):
                want -= self.negotiate(c, g, want, budget=budget, tag=f'pre{sweep}')
            if want:
                want -= self.market_buy(c, g, want, max(0, c.cash-keep), tag=f'market{sweep}')
            if want:
                self.negotiate(c, g, want, budget=max(0, c.cash-keep), tag=f'post{sweep}')
        pg = self.plan(c)
        if pg:
            _, mg = self.upgrade_requirements(c, pg)
            if mg and not self.count(c, 'machine', min_gen=mg):
                budget = max(0, c.cash-self.upgrade_cost(c, pg)-self.reserve(c))
                got = self.market_buy(c, 'machine', 1, budget, min_gen=mg)
                if not got:
                    self.negotiate(c, 'machine', 1, mg, budget)
        if self.flag('upgrade_living_goods') and self.r <= 7:
            want = math.ceil(self.pop()/2)
            ids = sorted(self.ids(c, 'electronics'), key=lambda i: (-self.units[i].gen, i))[:want]
            # Quantities already protected; replace at most one old unit per
            # sweep only when it yields actual service improvement and is affordable.
            if len(ids) == want and ids:
                oldest = min(self.units[i].gen for i in ids)
                if oldest < self.global_gen['electronics']:
                    budget = max(0, c.cash-self.reserve(c)-self.prep_budget(c))
                    got = self.market_buy(c, 'electronics', 1, budget, min_gen=oldest+1, tag='replacement')
                    self.replacement_purchases[c.name] += got

    def production(self):
        if self.r in self.produced_rounds:
            return False
        staged = []
        for c in self.cs.values():
            machines = self.machine_assignments(c)
            for g, lv in c.levels.items():
                base = self.base_quantity(c, g)
                bonus = BONUS[g] if c.focus == g else 0
                if self.opt.smaller_bonus and g in FOOD and bonus:
                    bonus = 2
                gen = self.tech_for(c, g)
                req = self.resource_requirements(c, g)
                enough = all(self.count(c, h) >= n for h,n in req.items())
                for h,n in req.items():
                    self.record_need(c, h, n, f'production:{g}', self.ids(c,h)[:n] if enough else [])
                c.need_slots += sum(req.values())
                if not enough:
                    base, bonus, gen = 1, 0, 1
                    c.production_failures += 1
                else:
                    for h,n in req.items():
                        self.consume(c, h, n, 'production')
                if g not in DURABLES and c.focus == g:
                    uid = machines.get(g)
                    self.record_need(c, 'machine', 1, f'equipment:{g}', [uid] if uid else [])
                    if uid:
                        self.mark_use(c, uid, 'equipment'); c.need_slots += 1
                        gap = min(2, max(0, self.global_gen['machine']-self.units[uid].gen))
                        eff = (1, .8, .6)[gap]
                        carry = c.bonus_buffer.get(g, 0)+(1 if self.opt.smaller_bonus else 2)*eff
                        extra = int(carry+1e-9); c.bonus_buffer[g] = carry-extra; bonus += extra
                staged.append((c,g,max(1,base+bonus),gen))
        for c,g,n,gen in staged:
            self.mint(c,g,n,gen)
        # Research capability alone does not obsolete others' machines.
        # Launch only when a unit of that generation has actually been produced.
        for g in DURABLES:
            observed = max((u.gen for u in self.units.values() if u.good==g), default=1)
            if observed > self.global_gen[g]:
                self.launch_events.append({'round':self.r,'good':g,'generation':observed})
            self.global_gen[g] = observed
        self.produced_rounds.add(self.r)
        return True

    def settle_round(self, c):
        if (self.r,c.name) in self.settled:
            return False
        for g in FOOD:
            n = min(self.food_need(),self.count(c,g))
            self.record_need(c,g,self.food_need(),'food',self.ids(c,g)[:n])
        want = math.ceil(self.pop()/2)
        ids = sorted(self.ids(c,'electronics'),key=lambda i:(-self.units[i].gen,i))[:want]
        self.record_need(c,'electronics',want,'living',ids)
        return super().settle_round(c)

    def invest(self, c, action_id=None):
        key = (self.r,c.name)
        if action_id is not None:
            if not isinstance(action_id,str) or not action_id:
                return False
            if action_id in self.invest_actions:
                return self.invest_payloads[action_id] == key and self.invest_actions[action_id]
        if key in self.invested_rounds:
            return False
        # Existing staged-development rules, single authoritatively resolved
        # investment decision per country per round in this simulator.
        result = super().invest(c)
        if result:
            self.invested_rounds.add(key)
        if action_id is not None:
            self.invest_actions[action_id] = result
            self.invest_payloads[action_id] = key
        return result

    def run(self):
        if len(self.round_history) == 9:
            return self.summary()
        for r in range(1,10):
            self.r = r; self.round_useful = Counter()
            self.production();self.verify()
            # Freeze all investment plans against the same post-production state.
            if self.flag('budget_plans'):
                for c in self.cs.values():
                    self.plan(c)
            for c in self.order_actors('listing'):
                self.prepare_orders(c)
            self.demand_snapshot()
            for sweep in range(self.opt.round_sweeps):
                for c in self.order_actors(f'buy{sweep}'):
                    self.buy_phase(c,sweep)
            self.verify()
            for c in self.cs.values():
                self.settle_round(c)
            for c in self.order_actors('invest'):
                self.invest(c,action_id=f'invest:{r}:{c.name}')
            for c in self.cs.values():
                self.choose_focus(c);c.cash_rounds.append(c.cash)
            self.update_prices();self.verify()
            self.round_history.append({'round':r,'cash':{n:c.cash for n,c in self.cs.items()},
              'listed':sum(len(o.units) for o in self.orders.values()),'transactions':len(self.transactions)})
        return self.summary()

    def verify(self):
        ok = super().verify();self.audit_checks += 1
        assert all(0 <= row['fulfilled'] <= row['external'] <= row['needed'] for row in self.needs_ledger)
        return ok

    def summary(self):
        result = super().summary()
        for n,c in self.cs.items():
            rows = [r for r in self.needs_ledger if r['country']==n]
            ext = sum(r['external'] for r in rows)
            filled = sum(r['fulfilled'] for r in rows)
            ext_rounds = {r['round'] for r in rows if r['external']>0}
            filled_rounds = {r['round'] for r in rows if r['fulfilled']>0}
            export_rounds = {r for u in self.units.values() if u.origin==n and u.born>0
                             for r,_ in self.foreign_uses[u.uid]}
            partners = set(c.useful_partners)
            for uid in self.foreign_uses:
                if self.units[uid].origin==n:
                    partners.update(k for _,k in self.foreign_uses[uid])
            export_score = 5*min(1,len(export_rounds)/6)
            import_score = 8*filled/ext if ext else 0
            diverse_score = 4*min(1,len(partners)/3)
            effect_score = (4*len(filled_rounds)/len(ext_rounds) if ext_rounds else 0) + 4*min(1,len(export_rounds)/6)
            new_trade = export_score+import_score+diverse_score+effect_score
            x=result['countries'][n]
            x['previous_score'] = x['score']
            x['previous_trade'] = x['trade']
            x['trade'] = new_trade
            x['score'] += new_trade-x['previous_trade']
            x['external_opportunities'] = ext
            x['fulfilled_external'] = filled
            x['external_coverage'] = filled/ext if ext else 0
            x['trade_parts'] = {'exports':export_score,'imports':import_score,'partners':diverse_score,'effects':effect_score}
            x['electronics_expanded'] = int('electronics' in c.levels and 'electronics' not in CONFIG[n][1])
            x['expansion_round'] = min((r for r,g,lv in c.upgrade_rounds if g=='electronics' and lv==1),default=0)
            x['replacements'] = self.replacement_purchases[n]
            x['true_asset_gain'] = c.cash+self.stock_value(c)+.45*c.investment-self.initial_assets[n]
            # Diagnostic only; tax is still paid and remains actual spendable cash.
            x['growth_ex_base_income'] = x['true_asset_gain']-10*len(c.happiness)
            x['fixed_base_income'] = 10*len(c.happiness)
            x['reserve_target'] = self.reserve(c)
            x['reserve_cash_score'] = clip(c.cash/self.reserve(c)*5,0,5)
            x['unallocated_stock_value'] = sum(self.unit_ref(self.units[i])*.15 for i in c.stock if self.units[i].order is not None or not self.units[i].used)
            active_ids = {i for r,cn,i,p in self.use_episodes if r==9 and cn==n and p in ('living','equipment')}
            active_value = sum(self.unit_ref(self.units[i])*.5 for i in active_ids if i in c.stock and self.units[i].order is None)
            x['active_asset_value'] = active_value
            x['evaluated_progress'] = c.cash+active_value+.45*c.investment-c.start-x['fixed_base_income']
            x['initial_capacity'] = self.initial_capacity[n]
            x['final_capacity'] = self.capacity(c)
        result['world']['verify_calls'] = self.audit_checks
        result['world']['external_opportunities'] = sum(x['external_opportunities'] for x in result['countries'].values())
        result['world']['fulfilled_external'] = sum(x['fulfilled_external'] for x in result['countries'].values())
        result['world']['electronics_expansions'] = sum(x['electronics_expanded'] for x in result['countries'].values())
        result['world']['launches'] = self.launch_events
        return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=0);a=p.parse_args()
    opts=Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True,specialist_cost=False)
    g=Game(a.seed,opts)
    print(json.dumps(g.run(),ensure_ascii=False,indent=2))
