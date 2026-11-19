"""Behavioral boundaries for v5 AI policies; economy rules remain unchanged.

Fixture cash changes use real, recorded purchases/sales. No test quietly changes
a wallet and then treats the resulting ledger as a valid simulated economy.
"""
import copy
import unittest

from budget_engine import Game, POLICIES
from budget_trace import Game as TraceGame
from expansion_engine import Game as V4Game


class BudgetPolicyTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, good, amount, action):
        unit = game.ids(game.cs[seller], good)[0]
        self.assertTrue(game.settle_transaction(
            [{'seller':seller, 'buyer':buyer, 'ids':[unit]}],
            (buyer, seller, amount), 'direct', action))

    def research_case(self, variant='funded', ore=2):
        game = Game(8101, variant)
        game.r = 2
        country = game.cs['Mechania']
        # A deliberately constructed Lv.2 fixture. Fund it by a recorded sale.
        country.levels['machine'] = 2
        country.machine_tech = 2
        self.transfer(game, 'Mechania', 'Tropia', 'wheat', 100, 'fixture:sale')
        if ore > game.count(country, 'ore'):
            game.mint(country, 'ore', ore-game.count(country, 'ore'), initial=True)
        game.plan_cache[(2, country.name)] = 'machine'
        return game, country

    def priority_case(self, variant):
        game = Game(8102, variant)
        game.r = 8
        country = game.cs['Mechania']
        # Pay 120G in an actual recorded trade, leaving the required scarce 95G.
        self.transfer(game, 'Tropia', 'Mechania', 'banana', 120, 'fixture:purchase')
        game.mint(country, 'wheat', 1, initial=True)
        game.consume(country, 'ore', game.count(country, 'ore'), 'fixture')
        for seller, good, price in [('Technia','electronics',80), ('Oilia','ore',20)]:
            actor = game.cs[seller]
            game.mint(actor, good, 1, initial=True)
            game.make_order(actor, game.ids(actor, good), price)
        return game, country

    def test_baseline_exactly_reproduces_v4(self):
        for seed in (8103, 8104):
            with self.subTest(seed=seed):
                self.assertEqual(V4Game(seed, 'roles').run(), Game(seed, 'baseline').run())

    def test_instrumentation_does_not_change_decisions(self):
        for variant in ('baseline', 'living', 'balanced', 'stock_guard'):
            with self.subTest(variant=variant):
                plain = Game(8105, variant)
                traced = TraceGame(8105, variant)
                result = plain.run()
                observed = traced.run()
                for nation, fields in result['countries'].items():
                    for key, value in fields.items():
                        self.assertEqual(value, observed['countries'][nation][key], (variant,nation,key))
                for key, value in result['world'].items():
                    self.assertEqual(value, observed['world'][key], (variant,key))
                self.assertEqual(plain.transactions, traced.transactions)

    def test_projected_resources_are_pure_and_include_new_factory(self):
        game = Game(8106, 'funded')
        game.r = 2
        country = game.cs['Mechania']
        before = copy.deepcopy((country, game.units, game.orders, game.initial_cash, game.minted))
        self.assertEqual(dict(game.projected_resources(country, 'machine')), {'ore':2})
        self.assertEqual(dict(game.projected_resources(country, 'electronics')), {'ore':2})
        self.assertEqual(before, (country, game.units, game.orders, game.initial_cash, game.minted))

    def test_research_and_post_upgrade_inputs_are_separate_targets(self):
        game, country = self.research_case(ore=2)
        # Lv.3 research consumes two ore; the following G3 cycle needs three.
        self.assertEqual(game.upgrade_requirements(country, 'machine')[0], 2)
        self.assertEqual(game.projected_resources(country, 'machine')['ore'], 3)
        self.assertEqual(game.targets(country)['ore'], 5)
        game.verify()

    def test_development_materials_cannot_also_fund_next_production(self):
        game, country = self.research_case(ore=2)
        before = copy.deepcopy((country.cash, country.levels, country.stock, game.sunk))
        self.assertFalse(game.invest(country, 'fixture:blocked'))
        self.assertEqual(before, (country.cash, country.levels, country.stock, game.sunk))
        self.assertEqual(game.funding_blocks[-1]['missing_after_development'], {'ore':3})
        game.verify()

    def test_funded_investment_leaves_actual_inputs_and_can_produce(self):
        game, country = self.research_case(ore=5)
        self.assertTrue(game.invest(country, 'fixture:funded'))
        self.assertEqual(country.levels['machine'], 3)
        self.assertEqual(game.count(country, 'ore'), 3)
        self.assertEqual(game.operation_inputs[('Mechania','development','ore')], 2)
        game.r = 3
        failures = country.production_failures
        game.production()
        made = [u for u in game.units.values() if u.origin=='Mechania' and u.good=='machine' and u.born==3]
        self.assertGreater(len(made), 1)
        self.assertEqual({u.gen for u in made}, {3})
        self.assertEqual(country.production_failures, failures)
        self.assertEqual(game.operation_inputs[('Mechania','production','ore')], 3)
        game.verify()

    def test_listed_raw_material_is_not_available_to_fund_investment(self):
        game, country = self.research_case(ore=5)
        game.make_order(country, game.ids(country,'ore'), 20)
        self.assertEqual(game.count(country,'ore',False), 5)
        self.assertEqual(game.count(country,'ore'), 0)
        self.assertFalse(game.invest(country, 'fixture:listed'))
        game.verify()

    def test_successful_investment_command_is_idempotent(self):
        game, country = self.research_case(ore=5)
        self.assertTrue(game.invest(country, 'fixture:once'))
        before = copy.deepcopy((country, game.sunk, game.units, game.needs_ledger))
        self.assertTrue(game.invest(country, 'fixture:once'))
        self.assertFalse(game.invest(country, 'fixture:different-command'))
        self.assertEqual(before, (country, game.sunk, game.units, game.needs_ledger))
        game.verify()

    def test_failed_command_replay_does_not_change_into_a_new_investment(self):
        game, country = self.research_case(ore=2)
        self.assertFalse(game.invest(country, 'fixture:failed'))
        game.mint(country,'ore',3,initial=True)
        before = (country.cash, country.investment, len(game.funding_blocks))
        self.assertFalse(game.invest(country, 'fixture:failed'))
        self.assertEqual(before, (country.cash, country.investment, len(game.funding_blocks)))
        self.assertTrue(game.invest(country, 'fixture:new-attempt'))
        game.verify()

    def test_invalid_investment_ids_are_rejected_before_policy_side_effects(self):
        game,country=self.research_case(ore=2)
        before=copy.deepcopy((country,game.funding_blocks,game.invest_actions,game.invest_payloads))
        for action_id in ('',0,False,[],{}):
            with self.subTest(action_id=action_id):
                self.assertFalse(game.invest(country,action_id))
                self.assertEqual(before,(country,game.funding_blocks,game.invest_actions,game.invest_payloads))
        game.verify()

    def test_household_guard_requires_food_and_basic_quantity_not_newest_generation(self):
        for food_met,living_met,expected in ((False,True,False),(True,False,False),(True,True,True)):
            with self.subTest(food=food_met,living=living_met):
                game,country=self.research_case('balanced',ore=5)
                if not food_met:
                    game.consume(country,'banana',game.count(country,'banana'),'fixture')
                if living_met:
                    game.mint(country,'electronics',1,gen=1,initial=True)
                # The world has G3. G1 still meets the basic quantity safeguard.
                game.global_gen['electronics']=3
                game.settle_round(country)
                self.assertEqual(game.r in country.satisfied_rounds,food_met)
                investment_before=country.investment
                self.assertEqual(game.invest(country,'fixture:household'),expected)
                if expected:
                    self.assertGreater(country.investment,investment_before)
                    self.assertFalse(game.household_blocks)
                else:
                    self.assertEqual(country.investment,investment_before)
                    self.assertEqual(game.household_blocks[-1]['food_met'],food_met)
                    self.assertEqual(game.household_blocks[-1]['living_quantity_met'],living_met)
                game.verify()

    def test_living_priority_resolves_real_scarce_budget_differently(self):
        for variant, expected in [('funded','ore'), ('living','electronics')]:
            with self.subTest(variant=variant):
                game, country = self.priority_case(variant)
                self.assertEqual(country.cash, 95)
                plan = game.purchase_plan(country)
                paid = [(row['good'],row['quantity']) for row in plan if row['quantity']]
                self.assertEqual(paid, [(expected,1)])
                before = country.imported.copy()
                game.buy_phase(country,0)
                self.assertEqual(country.imported[expected]-before[expected], 1)
                other = 'electronics' if expected=='ore' else 'ore'
                self.assertEqual(country.imported[other]-before[other], 0)
                game.verify()

    def test_optional_living_replacement_stays_after_operating_inputs(self):
        game = Game(8107, 'living')
        game.r = 2
        country = game.cs['Mechania']
        game.plan_cache[(2,country.name)] = None
        game.consume(country,'ore',game.count(country,'ore'),'fixture')
        game.mint(country,'electronics',1,gen=1,initial=True)
        game.global_gen['electronics'] = 2
        rows = game.purchase_plan(country)
        kinds = [(row['good'],row['kind']) for row in rows]
        self.assertIn(('ore','need'), kinds)
        self.assertIn(('electronics','replacement'), kinds)
        self.assertLess(kinds.index(('ore','need')), kinds.index(('electronics','replacement')))
        game.verify()

    def test_prediction_preserves_economic_state_and_allocates_wallet_once(self):
        for variant in POLICIES:
            with self.subTest(variant=variant):
                game = Game(8108,variant)
                game.r = 3
                game.production()
                for country in game.cs.values():
                    before = copy.deepcopy((country,game.units,game.orders,game.transactions,game.sunk,game.minted))
                    first = game.purchase_plan(country)
                    self.assertEqual(first,game.purchase_plan(country))
                    self.assertLessEqual(sum(row['budget'] for row in first),country.cash)
                    self.assertTrue(all(row['budget']>=0 and 0<=row['quantity']<=row['want'] for row in first))
                    self.assertEqual(before,(country,game.units,game.orders,game.transactions,game.sunk,game.minted))
                game.verify()

    def test_stock_guard_counts_current_stock_not_old_models(self):
        game = Game(8109,'stock_guard')
        game.r = 2
        country = game.cs['Mechania']
        country.levels['machine']=2
        country.machine_tech=2
        game.mint(country,'machine',30,gen=1,initial=True)
        self.assertFalse(game.excessive_current_stock(country,'machine'))
        game.mint(country,'machine',8,gen=2,initial=True)
        self.assertFalse(game.excessive_current_stock(country,'machine'))
        game.mint(country,'machine',1,gen=2,initial=True)
        self.assertTrue(game.excessive_current_stock(country,'machine'))
        game.verify()

    def test_stock_guard_postpones_same_industry_inputs_and_investment(self):
        game = Game(8110,'stock_guard')
        game.r=2
        country=game.cs['Mechania']
        country.levels['machine']=2
        country.machine_tech=2
        game.mint(country,'machine',9,gen=2,initial=True)
        game.plan_cache[(2,country.name)]='machine'
        self.assertIsNone(game.plan(country))
        self.assertEqual(game.next_resources(country)['ore'],0)
        self.assertFalse(game.invest(country,'fixture:stock-block'))
        game.verify()

    def test_stock_guard_preserves_other_industry_input_need(self):
        game=Game(8111,'stock_guard')
        game.r=2
        country=game.cs['Mechania']
        country.style='trade'
        country.levels.update(machine=2,electronics=1)
        country.bases['electronics']=1
        country.machine_tech=2
        game.mint(country,'machine',9,gen=2,initial=True)
        self.assertEqual(game.next_resources(country)['ore'],1)
        self.assertEqual(game.targets(country)['ore'],1)
        game.verify()

    def test_stock_guard_does_not_remove_guaranteed_g1_production(self):
        game=Game(8112,'stock_guard')
        game.r=3
        country=game.cs['Mechania']
        country.levels['machine']=2
        country.machine_tech=2
        game.mint(country,'machine',9,gen=2,initial=True)
        game.consume(country,'ore',game.count(country,'ore'),'fixture')
        game.production()
        made=[u for u in game.units.values() if u.origin=='Mechania' and u.good=='machine' and u.born==3]
        self.assertEqual(len(made),1)
        self.assertEqual(made[0].gen,1)
        self.assertEqual(country.production_failures,1)
        game.verify()

    def test_round_cash_ledgers_and_usage_reconcile(self):
        game=TraceGame(8113,'living')
        result=game.run()
        self.assertEqual(len(game.cash_ledger),9*9)
        for name,country in game.cs.items():
            rows=[r for r in game.cash_ledger if r['country']==name]
            self.assertEqual([r['round'] for r in rows],list(range(1,10)))
            self.assertEqual(rows[0]['cash_start'],country.start)
            self.assertEqual(rows[-1]['cash_end'],country.cash)
            for previous,current in zip(rows,rows[1:]):
                self.assertEqual(previous['cash_end'],current['cash_start'])
            self.assertEqual(sum(r['sales'] for r in rows),country.revenue)
            self.assertEqual(sum(r['purchases'] for r in rows),country.purchases)
            self.assertEqual(sum(r['investment'] for r in rows),country.investment)
            self.assertEqual(sum(r['operating_income'] for r in rows),country.tax)
            self.assertEqual(sum(result['countries'][name]['purchase_by_good'].values()),country.purchases)
            self.assertEqual(sum(result['countries'][name]['sale_by_good'].values()),country.revenue)
        self.assertEqual(result['world']['uncovered_investments'],0)
        self.assertTrue(all(row['next_cycle_covered'] for row in game.investment_trace))
        game.verify()

    def test_idle_actor_has_no_hidden_trade_or_investment(self):
        game=TraceGame(8114,'stock_guard',focal='Mechania',style='idle')
        result=game.run()
        actor=result['countries']['Mechania']
        for key in ('imports','exports','investment','purchases','revenue'):
            self.assertEqual(actor[key],0,key)
        self.assertFalse(any(row['country']=='Mechania' for row in game.investment_trace))
        self.assertFalse(any(row['country']=='Mechania' for row in game.funding_blocks))
        self.assertEqual(actor['input_deferral_rounds'],0)
        self.assertGreater(sum(actor['produced'].values()),0)
        self.assertGreater(actor['tax'],0)
        game.verify()

    def test_completed_run_replay_does_not_duplicate_trace(self):
        game=TraceGame(8115,'funded')
        first=game.run()
        trace=copy.deepcopy(game.trace())
        self.assertEqual(first,game.run())
        self.assertEqual(trace,game.trace())


if __name__=='__main__':
    unittest.main(verbosity=2)
