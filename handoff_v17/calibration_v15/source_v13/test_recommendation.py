"""v7 advice contracts; old 168 tests and economic recipes stay unchanged."""
import copy
import math
import unittest
from unittest.mock import patch

from machinery_engine import Game as V6Game
from recommendation_engine import Game, ADVICE_MODES
from reference_engine import GOODS


class RecommendationTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, ids, amount=10, action='fixture:trade', channel='direct'):
        self.assertTrue(game.settle_transaction(
            [{'seller':seller,'buyer':buyer,'ids':list(ids)}],
            (buyer,seller,amount),channel,action))

    def state(self, game):
        return copy.deepcopy((game.cs,game.units,game.orders,game.transactions,game.material_credit,
            game.upkeep_wear,game.advice_log,game.offer_history,game.listing_plan_log,
            game.grade_recall_log,game.plan_cache,game.minted,game.sunk))

    def test_baseline_preserves_all_v6_fields_and_economic_records(self):
        for seed in (42101,42102):
            with self.subTest(seed=seed):
                old=V6Game(seed,'coupled');new=Game(seed,'baseline')
                expected=old.run();actual=new.run()
                for nation,fields in expected['countries'].items():
                    for key,value in fields.items():
                        self.assertEqual(value,actual['countries'][nation][key],(nation,key))
                for key,value in expected['world'].items():
                    self.assertEqual(value,actual['world'][key],key)
                self.assertEqual(old.cash_ledger,new.cash_ledger)
                self.assertEqual(old.transactions,new.transactions)
                self.assertEqual(old.price_history,new.price_history)

    def test_initial_conditions_and_physical_first_production_are_unchanged(self):
        reference=V6Game(42103,'coupled')
        reference.r=1;reference.production()
        for variant in ADVICE_MODES:
            with self.subTest(variant=variant):
                game=Game(42103,variant)
                self.assertEqual(game.config,reference.config)
                self.assertEqual(game.initial_cash,reference.initial_cash)
                self.assertEqual(game.initial_assets,reference.initial_assets)
                self.assertEqual(game.initial_capacity,reference.initial_capacity)
                self.assertEqual(game.opt,reference.opt)
                game.r=1;game.production()
                self.assertEqual(game.units,reference.units)
                self.assertEqual(game.created,reference.created)
                self.assertEqual(game.operation_inputs,reference.operation_inputs)

    def test_three_advice_apis_are_pure_and_repeatable(self):
        game=Game(42104,'combined');game.r=2
        for name in ('Tropia','Mechania','Novia'):
            country=game.cs[name]
            for good in country.levels:
                with self.subTest(country=name,good=good):
                    ids=game.ids(country,good,False)
                    before=self.state(game)
                    first=(game.price_recommendation(country,good,game.tech_for(country,good)),
                           game.listing_quantity(country,good,ids),game.investment_advice(country,good))
                    second=(game.price_recommendation(country,good,game.tech_for(country,good)),
                            game.listing_quantity(country,good,ids),game.investment_advice(country,good))
                    self.assertEqual(first,second)
                    self.assertEqual(before,self.state(game))
        game.verify()

    def test_rival_private_cash_and_private_trade_price_do_not_change_advice(self):
        answers=[]
        for amount in (10,70):
            game=Game(42105,'responsive');game.r=1
            uid=game.ids(game.cs['Grainia'],'wheat')[0]
            self.transfer(game,'Grainia','Oilia',[uid],amount,'fixture:foreign-trade')
            game.r=2;country=game.cs['Tropia']
            answers.append((game.price_recommendation(country,'banana',1),
                game.listing_quantity(country,'banana',game.ids(country,'banana')),
                game.investment_advice(country,'banana')))
            game.verify()
        self.assertEqual(answers[0],answers[1])

    def test_future_trade_is_not_used_as_past_sales_observation(self):
        game=Game(42106,'combined');game.r=2;country=game.cs['Tropia']
        before=(game.own_sales(country,'banana'),game.price_recommendation(country,'banana',1),
                game.investment_advice(country,'banana'))
        # A future-dated observation is deliberately injected only into the
        # observer input. No game is continued or ledger asserted on this fixture.
        game.transactions.append({'round':3,'channel':'direct',
            'legs':[{'seller':'Tropia','buyer':'Grainia','ids':game.ids(country,'banana')}],
            'cash':('Grainia','Tropia',100),'action_id':'fixture:future-observation'})
        after=(game.own_sales(country,'banana'),game.price_recommendation(country,'banana',1),
               game.investment_advice(country,'banana'))
        self.assertEqual(before,after)
        self.assertEqual(game.own_sales(country,'banana',through_round=99)['units'],0)

    def test_same_item_resold_does_not_multiply_observed_sale_quantity(self):
        game=Game(42107,'price');game.r=1;country=game.cs['Tropia']
        uid=game.ids(country,'banana')[0]
        self.transfer(game,'Tropia','Grainia',[uid],10,'fixture:out')
        self.transfer(game,'Grainia','Tropia',[uid],10,'fixture:return')
        self.transfer(game,'Tropia','Oilia',[uid],10,'fixture:out-again')
        game.r=2
        history=game.own_sales(country,'banana')
        self.assertEqual(history['units'],1)
        self.assertEqual(history['buyers'],2)
        game.verify()

    def test_barter_contributes_sale_units_but_not_observed_cash_price(self):
        game=Game(42108,'price');game.r=1;country=game.cs['Tropia']
        a=game.ids(country,'banana')[0];b=game.ids(game.cs['Grainia'],'wheat')[0]
        self.assertTrue(game.settle_transaction([
            {'seller':'Tropia','buyer':'Grainia','ids':[a]},
            {'seller':'Grainia','buyer':'Tropia','ids':[b]}],None,'barter','fixture:barter'))
        game.r=2;history=game.own_sales(country,'banana')
        self.assertEqual(history['units'],1)
        self.assertIsNone(history['cash_price'])
        game.verify()

    def test_competing_price_survives_all_listing_and_repricing_steps(self):
        game=Game(42109,'price');game.r=1
        rival=game.cs['Grainia'];country=game.cs['Tropia']
        game.mint(rival,'banana',4);game.make_order(rival,game.ids(rival,'banana'),9)
        game.mint(country,'banana',5)
        game.prepare_orders(country)
        offers=[o for o in game.orders.values() if o.seller=='Tropia' and o.good=='banana']
        self.assertTrue(offers)
        self.assertEqual({o.price for o in offers},{9})
        rows=[r for r in game.advice_log if r['kind']=='offer' and r['country']=='Tropia' and r['good']=='banana']
        self.assertTrue(all(r['actual_prices']==[r['recommendation']['price']] for r in rows))
        game.verify()

    def test_cheaper_higher_grade_public_offer_is_a_substitute(self):
        game=Game(42110,'price');game.r=1
        seller=game.cs['Technia'];country=game.cs['Mechania']
        game.mint(seller,'machine',1,gen=2)
        game.make_order(seller,game.ids(seller,'machine',min_gen=2),40)
        advice=game.price_recommendation(country,'machine',1)
        self.assertEqual(advice['rival_best'],40)
        self.assertEqual(advice['price'],40)
        game.verify()

    def test_public_clearance_does_not_count_unlisted_barter_as_cleared_offer(self):
        game=Game(42111,'price');game.r=1;country=game.cs['Tropia']
        game.mint(country,'banana',16)
        game.prepare_orders(country)
        offered={i for r in game.offer_history if r['country']=='Tropia' and r['good']=='banana' for i in r['ids']}
        outside=[i for i in game.get_surplus(country,'banana') if i not in offered][:3]
        self.assertEqual(len(outside),3)
        buyer=game.cs['Grainia'];game.mint(buyer,'wheat',3,initial=True)
        self.assertTrue(game.settle_transaction([
            {'seller':'Tropia','buyer':'Grainia','ids':outside},
            {'seller':'Grainia','buyer':'Tropia','ids':game.ids(buyer,'wheat')[:3]}],
            None,'barter','fixture:unlisted-barter'))
        game.r=2;advice=game.price_recommendation(country,'banana',1)
        self.assertEqual(advice['past_offered'],len(offered))
        self.assertEqual(advice['past_sold'],0)
        self.assertEqual(advice['past_all_sales'],3)
        game.verify()

    def test_duplicate_offer_observation_does_not_double_clearance_denominator(self):
        game=Game(42112,'price');game.r=1;country=game.cs['Tropia']
        game.mint(country,'banana',5);game.prepare_orders(country)
        row=next(r for r in game.offer_history if r['country']=='Tropia' and r['good']=='banana')
        game.r=2;before=game.price_recommendation(country,'banana',1)
        game.offer_history.append(copy.deepcopy(row))
        self.assertEqual(before,game.price_recommendation(country,'banana',1))

    def test_total_public_cap_counts_old_orders_and_new_inventory_together(self):
        game=Game(42113,'listing');country=game.cs['Tropia'];game.r=1
        game.mint(country,'banana',12)
        game.make_order(country,game.ids(country,'banana')[:5],10)
        for round_number in (1,2):
            game.r=round_number
            if round_number==2:game.mint(country,'banana',12)
            game.prepare_orders(country)
            live=[i for o in game.orders.values() if o.seller=='Tropia' and o.good=='banana' for i in o.units]
            plan=[r for r in game.listing_plan_log if r['round']==round_number and r['country']=='Tropia' and r['good']=='banana'][-1]
            self.assertEqual(len(live),2)
            self.assertEqual(len(live),plan['target'])
            self.assertTrue(plan['within_plan'])
        game.verify()

    def test_imported_food_is_not_automatically_relisted(self):
        game=Game(42114,'combined');game.r=1;country=game.cs['Tropia']
        seller=game.cs['Grainia'];foreign=game.ids(seller,'banana')
        self.transfer(game,'Grainia','Tropia',foreign,10,'fixture:food-import')
        game.mint(country,'banana',10)
        game.prepare_orders(country)
        self.assertTrue(all(game.units[i].order is None for i in foreign))
        game.verify()

    def test_required_owned_g2_machine_is_recalled_before_new_import_advice(self):
        game=Game(42115,'price');game.r=3;country=game.cs['Tropia']
        country.levels['banana']=3
        game.plan_cache[(3,country.name)]='banana'
        game.mint(country,'machine',1,gen=1,initial=True)
        game.mint(country,'machine',1,gen=2,initial=True)
        advanced=game.ids(country,'machine',min_gen=2)[0]
        game.make_order(country,[advanced],70)
        game.prepare_orders(country)
        self.assertIsNone(game.units[advanced].order)
        self.assertEqual(game.grade_recall_log[-1]['unit'],advanced)
        self.assertFalse(any(r['good']=='machine' and r['want']>0 for r in game.purchase_plan(country)))
        game.verify()

    def test_best_household_electronics_is_recalled_even_if_old_quantity_is_sufficient(self):
        game=Game(42116,'price');game.r=2;country=game.cs['Tropia']
        game.mint(country,'electronics',1,gen=1,initial=True)
        game.mint(country,'electronics',1,gen=3,initial=True)
        old=game.ids(country,'electronics')[0];best=game.ids(country,'electronics',min_gen=3)[0]
        game.make_order(country,[best],140)
        game.prepare_orders(country)
        self.assertIsNone(game.units[best].order)
        self.assertIsNotNone(game.units[old].order)
        game.verify()

    def test_equal_grade_free_stock_does_not_cause_unnecessary_recall(self):
        game=Game(42130,'price');game.r=2;country=game.cs['Tropia']
        game.mint(country,'electronics',1,gen=2,initial=True)
        listed=game.ids(country,'electronics',min_gen=2)[0]
        game.make_order(country,[listed],100)
        game.mint(country,'electronics',1,gen=2,initial=True)
        free=game.ids(country,'electronics',min_gen=2)[0]
        self.assertNotEqual(free,listed)
        old_order=game.units[listed].order
        cancellations=game.cancelled
        game.prepare_orders(country)
        self.assertEqual(game.units[listed].order,old_order)
        self.assertIsNone(game.units[free].order)
        self.assertEqual(game.cancelled,cancellations)
        self.assertIn(free,game.protected_ids(country,'electronics'))
        self.assertNotIn(listed,game.protected_ids(country,'electronics'))
        game.verify()

    def test_three_available_generations_are_visible_when_quota_allows_three(self):
        game=Game(42117,'listing');game.r=1;country=game.cs['Mechania']
        for gen in (1,2,3):game.mint(country,'machine',3,gen=gen,initial=True)
        self.transfer(game,'Mechania','Tropia',[game.ids(country,'machine')[0]],40,'fixture:past-machine-sale')
        game.r=2;game.prepare_orders(country)
        live=[i for o in game.orders.values() if o.seller=='Mechania' and o.good=='machine' for i in o.units]
        self.assertEqual(len(live),3)
        self.assertEqual({game.units[i].gen for i in live},{1,2,3})
        game.verify()

    def test_protected_food_and_operating_research_resources_stay_available(self):
        game=Game(42118,'listing');game.r=2;country=game.cs['Mechania']
        country.levels['machine']=2;country.machine_tech=2
        game.plan_cache[(2,country.name)]='machine'
        game.mint(country,'ore',8,initial=True)
        targets=game.targets(country);total={g:game.count(country,g,False) for g in GOODS}
        game.prepare_orders(country)
        for good in GOODS:
            self.assertGreaterEqual(game.count(country,good),min(targets[good],total[good]),good)
        for row in game.listing_plan_log:
            if row['country']==country.name:
                self.assertFalse(set(row['actual_ids'])&set(row['protected_ids']))
        game.verify()

    def test_public_cap_does_not_forbid_direct_sale_of_other_surplus(self):
        game=Game(42119,'listing');game.r=1;country=game.cs['Tropia']
        game.mint(country,'banana',12);game.prepare_orders(country)
        live={i for o in game.orders.values() if o.seller=='Tropia' and o.good=='banana' for i in o.units}
        outside=[i for i in game.get_surplus(country,'banana') if i not in live][:3]
        self.assertEqual(len(outside),3)
        self.transfer(game,'Tropia','Grainia',outside,30,'fixture:uncapped-direct')
        self.assertTrue(all(game.units[i].owner=='Grainia' for i in outside))
        self.assertEqual(len(live),2)
        game.verify()

    def test_half_reference_style_changes_price_not_same_state_quantity_or_investment_advice(self):
        observations=[]
        for style in ('normal','cheap'):
            game=Game(42120,'combined',focal='Tropia',style=style);game.r=1
            country=game.cs['Tropia'];game.mint(country,'banana',10)
            qty=game.listing_quantity(country,'banana',game.ids(country,'banana'))
            investment=game.investment_advice(country,'banana')
            advice=game.price_recommendation(country,'banana',1)
            observations.append((qty,investment,advice))
        self.assertEqual(observations[0][:2],observations[1][:2])
        self.assertEqual(observations[1][2]['price'],5)
        self.assertEqual(observations[1][2]['reason'],'fixed_half_reference')
        self.assertGreater(observations[0][2]['price'],5)

    def test_food_focus_forecast_uses_two_bonus_and_actual_fractional_equipment_carry(self):
        game=Game(42121,'planning');game.r=2;country=game.cs['Tropia']
        game.mint(country,'machine',1,gen=1,initial=True)
        game.mint(game.cs['Mechania'],'machine',1,gen=3,initial=True)
        game.global_gen['machine']=3;country.bonus_buffer['banana']=0.6
        self.assertEqual(game.actual_bonus(country,'banana'),2)
        self.assertEqual(game.equipment_bonus(country,'banana'),1)
        expected=game.cycle_output(country,'banana',focused='banana')
        self.assertEqual(expected,7)
        before=country.produced['banana'];game.production()
        self.assertEqual(country.produced['banana']-before,expected)
        self.assertAlmostEqual(country.bonus_buffer['banana'],0.2)
        game.verify()

    def test_no_additional_use_case_holds_investment_instead_of_rewarding_capacity_alone(self):
        game=Game(42122,'planning');game.r=2;country=game.cs['Tropia']
        game.mint(country,'banana',100,initial=True);game.mint(country,'wheat',100,initial=True)
        advice=game.investment_advice(country,'banana')
        self.assertEqual(advice['marginal_useful_units'],0)
        self.assertEqual(advice['capacity_value'],0)
        self.assertFalse(advice['eligible'])
        self.assertIsNone(game.plan(country))
        game.verify()

    def test_first_new_generation_has_finite_uncertain_trial_without_invented_customers(self):
        game=Game(42123,'planning');game.r=1;country=game.cs['Mechania']
        advice=game.investment_advice(country,'machine')
        self.assertTrue(advice['uncertain_new_generation'])
        self.assertGreater(advice['quality_trial_units'],0)
        self.assertLessEqual(advice['quality_trial_units'],1)
        self.assertEqual(advice['sales_forecast'],0)
        for key,value in advice.items():
            if type(value) in (int,float):self.assertTrue(math.isfinite(value),key)
        self.assertFalse(game.transactions)
        self.assertEqual(country.cash,country.start)

    def test_round_eight_and_nine_never_recommend_or_execute_new_investment(self):
        game=Game(42124,'combined');country=game.cs['Mechania']
        for r in (8,9):
            game.r=r
            self.assertIsNone(game.plan(country))
            before=(country.cash,country.investment,country.levels.copy())
            self.assertFalse(game.invest(country,f'fixture:late-investment:{r}'))
            self.assertEqual(before,(country.cash,country.investment,country.levels))
        game.verify()

    def test_investment_advice_and_plan_do_not_recurse_through_targets(self):
        game=Game(42125,'planning');game.r=2;country=game.cs['Mechania']
        with patch.object(game,'targets',side_effect=AssertionError('recursive target dependency')):
            advice=game.investment_advice(country,'machine')
            self.assertIn('opportunity_score',advice)
            game.plan(country)
        game.verify()

    def test_plan_queries_record_one_decision_per_country_round(self):
        game=Game(42126,'planning');game.r=2;country=game.cs['Tropia']
        first=game.plan(country)
        for _ in range(4):
            self.assertEqual(game.plan(country),first)
            game.targets(country)
        rows=[r for r in game.advice_log if r['kind']=='investment' and r['country']=='Tropia' and r['round']==2]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['selected'],first)

    def test_full_run_recommendations_and_channel_ledgers_reconcile(self):
        for variant in ADVICE_MODES:
            with self.subTest(variant=variant):
                game=Game(42127,variant);result=game.run()
                world_sales=0
                for name,country in game.cs.items():
                    x=result['countries'][name];channels=x['channel_stats']
                    self.assertEqual(set(channels),{'market','direct','barter'})
                    self.assertEqual(sum(v['sold_units'] for v in channels.values()),x['exports'])
                    self.assertEqual(sum(v['bought_units'] for v in channels.values()),x['imports'])
                    self.assertEqual(sum(v['sales_cash'] for v in channels.values()),country.revenue)
                    self.assertEqual(sum(v['purchase_cash'] for v in channels.values()),country.purchases)
                    self.assertEqual(channels['barter']['sales_cash'],0)
                    self.assertEqual(channels['barter']['purchase_cash'],0)
                    self.assertEqual(sum(x['listed_by_good'].values()),x['listed'])
                    self.assertEqual(x['all_goods_unique_used'],sum(x['use_by_good'].values()))
                    if x['industry'] is not None:
                        self.assertAlmostEqual(x['industry'],x['industry_use_score']+x['industry_capacity_score'])
                    else:self.assertIsNone(x['industry_capacity_score'])
                    world_sales+=sum(v['sold_units'] for v in channels.values())
                self.assertEqual(world_sales,result['world']['trade_units'])
                for channel in ('market','direct','barter'):
                    self.assertEqual(sum(x['channel_stats'][channel]['sales_cash'] for x in result['countries'].values()),
                                     sum(x['channel_stats'][channel]['purchase_cash'] for x in result['countries'].values()))
                self.assertEqual(result['world']['offer_price_mismatches'],0)
                self.assertEqual(result['world']['listing_plan_violations'],0)
                self.assertEqual(result['world']['uncovered_investments'],0)
                if variant!='baseline':self.assertEqual(result['world']['protected_offer_violations'],0)
                game.verify()

    def test_idle_and_no_trade_do_not_create_hidden_sales_or_offer_actions(self):
        game=Game(42128,'combined',focal='Mechania',style='idle');result=game.run()
        actor=result['countries']['Mechania']
        for key in ('imports','exports','investment','public_offer_units','planning_decisions'):
            self.assertEqual(actor[key],0,key)
        self.assertFalse(any(r['country']=='Mechania' for r in game.grade_recall_log))
        closed=Game(42128,'combined',trade_enabled=False);no_trade=closed.run()
        self.assertFalse(closed.transactions)
        self.assertFalse(closed.offer_history)
        self.assertEqual(no_trade['world']['public_offer_units'],0)
        game.verify();closed.verify()

    def test_completed_run_replay_keeps_recommendation_and_offer_logs_identical(self):
        game=Game(42129,'responsive');first=game.run();trace=copy.deepcopy(game.trace())
        self.assertEqual(first,game.run())
        self.assertEqual(trace,game.trace())


if __name__=='__main__':
    unittest.main(verbosity=2)
