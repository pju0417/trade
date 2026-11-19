"""v6 behavioral boundaries; prior 141 tests and their expectations stay intact.

These fixtures create physical goods through mint(), and transfer money through
recorded transactions. They do not overwrite cash and then assert a valid ledger.
"""
import copy
import unittest
from collections import Counter, defaultdict

from budget_trace import Game as V5Game
from machinery_engine import Game, MODES, CREDITS_PER_RAW


class MachineryTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, ids, amount=10, action='fixture:trade'):
        self.assertTrue(game.settle_transaction(
            [{'seller':seller,'buyer':buyer,'ids':list(ids)}],
            (buyer,seller,amount),'direct',action))

    def machine_actor(self, mode='coupled', level=2):
        game=Game(32101,mode)
        game.r=1
        country=game.cs['Mechania']
        country.levels['machine']=level
        country.machine_tech=min(level,3)
        return game,country

    def credit_case(self):
        # G1 with two actual outputs: the free basic unit plus one prepaid unit.
        game,country=self.machine_actor('recipe',level=1)
        country.focus='wheat'
        game.production()
        self.assertEqual(game.material_credit[('Mechania','ore',1)],1)
        self.assertEqual(game.count(country,'ore'),0)
        return game,country

    def support_case(self):
        game=Game(32102,'service')
        country=game.cs['Tropia']
        game.mint(country,'machine',1,initial=True)
        uid=game.ids(country,'machine')[0]
        for round_number in (1,2):
            game.r=round_number
            game.production()
        self.assertEqual(game.upkeep_wear[uid],2)
        return game,country,uid

    def test_baseline_preserves_v5_balanced_every_existing_summary_field(self):
        for seed in (32103,32104):
            with self.subTest(seed=seed):
                old=V5Game(seed,'balanced')
                new=Game(seed,'baseline')
                expected=old.run()
                result=new.run()
                for nation,fields in expected['countries'].items():
                    for key,value in fields.items():
                        self.assertEqual(value,result['countries'][nation][key],(nation,key))
                for key,value in expected['world'].items():
                    self.assertEqual(value,result['world'][key],key)
                self.assertEqual(old.transactions,new.transactions)
                self.assertEqual(old.cash_ledger,new.cash_ledger)
                self.assertEqual(old.price_history,new.price_history)

    def test_all_modes_preserve_initial_conditions_and_potential_capacity(self):
        expected=V5Game(32105,'balanced')
        for mode in MODES:
            with self.subTest(mode=mode):
                game=Game(32105,mode)
                self.assertEqual(expected.initial_cash,game.initial_cash)
                self.assertEqual(expected.initial_assets,game.initial_assets)
                self.assertEqual(expected.initial_capacity,game.initial_capacity)
                self.assertEqual(expected.config,game.config)
                self.assertEqual(expected.opt,game.opt)

    def test_forecasts_are_repeatable_and_do_not_spend_goods_or_credits(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                game=Game(32106,mode)
                game.r=1
                game.production()
                for country in game.cs.values():
                    before=copy.deepcopy((country,game.units,game.orders,game.transactions,
                        game.material_credit,game.material_events,game.upkeep_wear,game.upkeep_log))
                    first=(game.next_resources(country),game.projected_resources(country))
                    for _ in range(3):
                        self.assertEqual(first,(game.next_resources(country),game.projected_resources(country)))
                    self.assertEqual(before,(country,game.units,game.orders,game.transactions,
                        game.material_credit,game.material_events,game.upkeep_wear,game.upkeep_log))
                game.verify()

    def test_one_paid_bundle_prepays_extra_output_without_double_cash_charge(self):
        game,country=self.credit_case()
        self.assertEqual(country.produced['machine'],2)
        self.assertEqual(game.operation_inputs[('Mechania','production','ore')],1)
        self.assertEqual(country.cash,country.start)
        game.r=2
        before=country.produced['machine']
        game.production()
        self.assertEqual(country.produced['machine']-before,2)
        self.assertEqual(game.operation_inputs[('Mechania','production','ore')],1)
        self.assertEqual(game.material_credit[('Mechania','ore',1)],0)
        game.verify()

    def test_credits_do_not_pay_for_a_new_generation(self):
        game,country=self.credit_case()
        country.levels['machine']=2
        country.machine_tech=2
        game.r=2
        plan=game.material_plan(country,2,quantity=1)
        self.assertEqual(plan['required'],{'ore':1})
        self.assertEqual(plan['credits_before'],0)
        game.production()
        row=[r for r in game.machine_output_log if r['round']==2 and r['country']=='Mechania'][0]
        self.assertEqual((row['status'],row['produced'],row['generation']),('fallback',1,1))
        self.assertEqual(game.material_credit[('Mechania','ore',1)],1)
        game.verify()

    def test_credits_stay_with_producer_after_product_transfer(self):
        game,country=self.credit_case()
        uid=next(i for i in game.ids(country,'machine') if game.units[i].born==1)
        self.transfer(game,'Mechania','Novia',[uid],10,'fixture:credit-transfer')
        buyer=game.cs['Novia']
        buyer.levels['machine']=1
        buyer.bases['machine']=2
        plan=game.material_plan(buyer,3,quantity=2)
        self.assertEqual(plan['required'],{'ore':1})
        self.assertEqual(plan['credits_before'],0)
        self.assertEqual(game.material_credit[('Mechania','ore',1)],1)
        game.verify()

    def test_raw_type_credits_do_not_cross_alternating_input_cycles(self):
        game=Game(32107,'recipe')
        country=game.cs['Technia']
        country.focus='machine'
        game.mint(country,'ore',1,initial=True)
        game.r=1
        game.production()
        self.assertEqual(game.material_credit[('Technia','ore',1)],1)
        plan=game.material_plan(country,2,quantity=2)
        self.assertEqual(plan['required'],{'fuel':1})
        self.assertEqual(plan['credits_before'],0)
        self.assertEqual(game.material_credit[('Technia','ore',1)],1)
        game.verify()

    def test_zero_plan_pauses_without_creating_free_basic_machine(self):
        for mode in ('quantity','coupled','service'):
            with self.subTest(mode=mode):
                game,country=self.machine_actor(mode,level=1)
                game.production()
                before=(country.produced['machine'],game.operation_inputs[('Mechania','production','ore')])
                game.r=2
                self.assertEqual(game.machine_quantity(country,2,actual=True),0)
                game.production()
                row=[r for r in game.machine_output_log if r['round']==2 and r['country']=='Mechania'][0]
                self.assertEqual((row['status'],row['produced'],row['raw_used']),('paused',0,{}))
                self.assertEqual(before,(country.produced['machine'],game.operation_inputs[('Mechania','production','ore')]))
                game.verify()

    def test_listing_and_recalling_stock_do_not_restart_production_allowance(self):
        game,country=self.machine_actor(level=1)
        game.production()
        game.r=2
        ids=game.ids(country,'machine')
        game.make_order(country,ids,50)
        self.assertEqual(game.machine_quantity(country,2,actual=True),0)
        game.remove_order_ids(ids)
        self.assertEqual(game.machine_quantity(country,2,actual=True),0)
        game.verify()

    def test_first_new_generation_can_be_manufactured_despite_old_stock(self):
        game,country=self.machine_actor(level=2)
        game.mint(country,'machine',40,gen=1,initial=True)
        self.assertEqual(game.machine_quantity(country,1,actual=True),1)
        game.production()
        row=[r for r in game.machine_output_log if r['country']=='Mechania'][0]
        self.assertEqual((row['status'],row['produced'],row['generation']),('regular',1,2))
        self.assertEqual(row['raw_used'],{'ore':1})
        self.assertEqual(game.global_gen['machine'],2)
        game.verify()

    def test_raw_shortage_falls_back_to_g1_and_never_launches_new_generation(self):
        for level in (2,3):
            with self.subTest(level=level):
                game,country=self.machine_actor(level=level)
                game.consume(country,'ore',game.count(country,'ore'),'fixture')
                game.production()
                row=[r for r in game.machine_output_log if r['country']=='Mechania'][0]
                self.assertEqual((row['status'],row['produced'],row['generation']),('fallback',1,1))
                self.assertEqual(row['raw_used'],{})
                self.assertFalse(any(e['country']=='Mechania' for e in game.material_events))
                self.assertEqual(game.global_gen['machine'],1)
                game.verify()

    def test_listed_raw_is_unavailable_for_manufacture(self):
        game,country=self.machine_actor(level=2)
        game.make_order(country,game.ids(country,'ore'),20)
        game.production()
        row=[r for r in game.machine_output_log if r['country']=='Mechania'][0]
        self.assertEqual(row['status'],'fallback')
        self.assertEqual(game.count(country,'ore',False),1)
        self.assertEqual(game.count(country,'ore'),0)
        game.verify()

    def test_current_round_new_ore_cannot_fund_same_round_machine(self):
        game,country=self.machine_actor(level=2)
        # Put ore first so immediate-mint implementations would fail this test.
        country.levels={'ore':1,'machine':2,'wheat':1}
        country.bases={'ore':1,'machine':2,'wheat':2}
        game.consume(country,'ore',game.count(country,'ore'),'fixture')
        game.production()
        row=[r for r in game.machine_output_log if r['country']=='Mechania'][0]
        self.assertEqual((row['status'],row['generation']),('fallback',1))
        self.assertEqual(game.count(country,'ore'),1)
        game.verify()

    def test_quantity_only_diagnostic_exposes_paid_basic_while_coupled_does_not(self):
        for mode,expected in (('quantity',True),('coupled',False)):
            with self.subTest(mode=mode):
                game,country=self.machine_actor(mode,level=1)
                game.production()
                row=[r for r in game.machine_output_log if r['country']=='Mechania'][0]
                self.assertEqual(row['produced'],1)
                self.assertEqual(row['g1_paid_for_only_basic'],expected)
                game.verify()

    def test_actual_focus_output_never_exceeds_forecast_ceiling(self):
        game,country=self.machine_actor('recipe',level=3)
        country.focus='wheat'
        planned=game.material_plan(country,2)
        for focus in ('wheat','machine'):
            country.focus=focus
            actual=game.material_plan(country,2,game.machine_quantity(country,2,actual=True))
            self.assertLessEqual(actual['quantity'],planned['quantity'])
            self.assertLessEqual(actual['raw_spent'],planned['raw_spent'])

    def test_recent_own_sales_ignore_rival_sales_and_keep_one_stock_plan(self):
        game,country=self.machine_actor(level=2)
        game.production()
        uid=next(i for i in game.ids(country,'machine') if game.units[i].gen==2)
        game.r=2
        self.transfer(game,'Mechania','Tropia',[uid],40,'fixture:own-sale')
        self.assertEqual(game.own_machine_sales(country,3,2),0.5)
        before=game.machine_quantity(country,3)
        other=game.cs['Technia']
        game.mint(other,'machine',5,gen=2,initial=True)
        self.transfer(game,'Technia','Grainia',game.ids(other,'machine',min_gen=2),10,'fixture:rival-sale')
        self.assertEqual(game.own_machine_sales(country,3,2),0.5)
        self.assertEqual(game.machine_quantity(country,3),before)
        game.verify()

    def test_paused_machine_does_not_take_focus_from_productive_industry(self):
        old=V5Game(32114,'balanced')
        baseline=Game(32114,'baseline')
        coupled=Game(32114,'coupled')
        for game in (old,baseline,coupled):
            game.r=1
            country=game.cs['Mechania']
            # A made-but-unsold machine closes the launch allowance; stock
            # already covers the next round's local machine target.
            game.mint(country,'machine',1)
            country.focus='machine'
        self.assertEqual(coupled.machine_quantity(coupled.cs['Mechania'],2),0)
        for game in (old,baseline,coupled):
            game.choose_focus(game.cs['Mechania'])
            game.verify()
        self.assertEqual(old.cs['Mechania'].focus,'machine')
        self.assertEqual(baseline.cs['Mechania'].focus,old.cs['Mechania'].focus)
        self.assertEqual(coupled.cs['Mechania'].focus,'wheat')

    def test_maintenance_shortage_only_pauses_equipment_extra_bonus(self):
        game,country,uid=self.support_case()
        before=country.produced.copy()
        failures=country.production_failures
        game.r=3
        game.production()
        self.assertEqual(country.produced['banana']-before['banana'],6)
        self.assertEqual(country.produced['wheat']-before['wheat'],2)
        self.assertEqual(game.upkeep_wear[uid],2)
        self.assertEqual(game.units[uid].owner,country.name)
        self.assertIn(uid,country.stock)
        self.assertEqual(country.production_failures,failures)
        event=[e for e in game.upkeep_log if e['round']==3 and e['unit']==uid][0]
        self.assertTrue(event['due'])
        self.assertFalse(event['serviced'])
        self.assertEqual(event['ore_used'],0)
        self.assertFalse(any(r==3 and n==country.name and i==uid and p=='equipment' for r,n,i,p in game.use_episodes))
        game.verify()

    def test_paid_third_use_resets_wear_and_retains_bonus(self):
        game,country,uid=self.support_case()
        game.mint(country,'ore',1,initial=True)
        before=country.produced['banana']
        cash=country.cash
        game.r=3
        game.production()
        self.assertEqual(country.produced['banana']-before,7)
        self.assertEqual(game.upkeep_wear[uid],0)
        self.assertEqual(game.operation_inputs[('Tropia','maintenance','ore')],1)
        self.assertEqual(country.cash,cash)
        game.verify()

    def test_wear_is_bound_to_uid_through_relisting_and_transfer(self):
        game,country,uid=self.support_case()
        game.make_order(country,[uid],50)
        game.remove_order_ids([uid])
        self.assertEqual(game.upkeep_wear[uid],2)
        self.transfer(game,'Tropia','Grainia',[uid],50,'fixture:worn-transfer')
        self.assertEqual(game.upkeep_wear[uid],2)
        buyer=game.cs['Grainia']
        game.mint(buyer,'ore',1,initial=True)
        game.r=3
        game.production()
        event=[e for e in game.upkeep_log if e['round']==3 and e['unit']==uid][0]
        self.assertEqual(event['country'],'Grainia')
        self.assertEqual((event['wear_before'],event['ore_used'],event['wear_after']),(2,1,0))
        game.verify()

    def test_spare_listed_and_industrial_focus_machines_do_not_accumulate_wear(self):
        game=Game(32108,'service')
        country=game.cs['Tropia']
        game.mint(country,'machine',1,gen=1,initial=True)
        game.mint(country,'machine',1,gen=2,initial=True)
        old=game.ids(country,'machine')[0]
        new=game.ids(country,'machine',min_gen=2)[0]
        game.make_order(country,[old],50)
        industrial=game.cs['Mechania']
        industrial_uid=game.ids(industrial,'machine')[0]
        game.r=1
        game.production()
        self.assertEqual(game.upkeep_wear[old],0)
        self.assertEqual(game.upkeep_wear[new],1)
        self.assertEqual(game.upkeep_wear[industrial_uid],0)
        self.assertFalse(any(e['unit']==old or e['unit']==industrial_uid for e in game.upkeep_log))
        game.verify()

    def test_maintenance_forecast_is_separate_from_development_materials(self):
        game=Game(32109,'service')
        country=game.cs['Grainia']
        country.levels['wheat']=2
        game.mint(country,'machine',1,initial=True)
        uid=game.ids(country,'machine')[0]
        for round_number in (1,2):
            game.r=round_number
            game.production()
        self.transfer(game,'Grainia','Mechania',[game.ids(country,'wheat')[0]],100,'fixture:funding-sale')
        game.plan_cache[(2,country.name)]='wheat'
        game.mint(country,'electronics',1,initial=True)
        game.settle_round(country)
        self.assertEqual(game.upkeep_wear[uid],2)
        self.assertEqual(dict(game.projected_resources(country,'wheat')),{'ore':1})
        self.assertEqual(game.upgrade_requirements(country,'wheat')[0],1)
        self.assertEqual(game.targets(country)['ore'],2)
        game.mint(country,'ore',1,initial=True)
        self.assertFalse(game.invest(country,'fixture:not-double-usable'))
        self.assertEqual(game.funding_blocks[-1]['missing_after_development'],{'ore':1})
        game.mint(country,'ore',1,initial=True)
        self.assertTrue(game.invest(country,'fixture:separately-funded'))
        self.assertEqual(game.count(country,'ore'),1)
        game.r=3
        game.production()
        self.assertEqual(game.operation_inputs[('Grainia','development','ore')],1)
        self.assertEqual(game.operation_inputs[('Grainia','maintenance','ore')],1)
        self.assertEqual(game.upkeep_wear[uid],0)
        game.verify()

    def test_no_raw_agent_refuses_cash_and_barter_without_affecting_others(self):
        game=Game(32110,'coupled',focal='Mechania',style='no_raw')
        game.r=1
        actor=game.cs['Mechania']
        actor.levels['machine']=2
        actor.machine_tech=2
        seller=game.cs['Mineria']
        game.mint(seller,'ore',1,initial=True)
        raw=game.ids(seller,'ore')[0]
        food=game.ids(actor,'wheat')[0]
        before=copy.deepcopy((game.cs,game.units,game.transactions))
        self.assertFalse(game.settle_transaction(
            [{'seller':'Mineria','buyer':'Mechania','ids':[raw]}],
            ('Mechania','Mineria',20),'direct','fixture:no-raw-cash'))
        self.assertFalse(game.settle_transaction(
            [{'seller':'Mineria','buyer':'Mechania','ids':[raw]},
             {'seller':'Mechania','buyer':'Mineria','ids':[food]}],
            None,'barter','fixture:no-raw-barter'))
        self.assertEqual(before,(game.cs,game.units,game.transactions))
        self.assertFalse(any(row['good'] in ('ore','fuel') for row in game.purchase_plan(actor)))
        self.transfer(game,'Mineria','Novia',[raw],20,'fixture:others-may-buy')
        game.verify()

    def test_actual_output_and_physical_material_logs_reconcile(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                game=Game(32111,mode)
                result=game.run()
                for name,country in game.cs.items():
                    logs=[e for e in game.machine_output_log if e['country']==name]
                    self.assertEqual(sum(e['produced'] for e in logs),country.produced['machine'])
                    self.assertEqual(sum(int(e['status']=='fallback') for e in logs),result['countries'][name]['machine_fallbacks'])
                    for raw in ('ore','fuel'):
                        expected=sum(p['required'].get(raw,0) for p in game.production_trace
                                     if p['country']==name and p['funded'])
                        self.assertEqual(expected,game.operation_inputs[(name,'production',raw)])
                by_key=defaultdict(list)
                for event in game.material_events:
                    by_key[tuple(event['key'])].append(event)
                for key,events in by_key.items():
                    balance=0
                    for event in events:
                        self.assertEqual(event['credits_before'],balance)
                        balance+=CREDITS_PER_RAW*event['raw_spent']-event['credits_spent']
                        self.assertEqual(event['credits_after'],balance)
                    self.assertEqual(balance,game.material_credit[key])
                    self.assertEqual(CREDITS_PER_RAW*sum(e['raw_spent'] for e in events),
                                     sum(e['credits_spent'] for e in events)+balance)
                game.verify()

    def test_production_replay_does_not_duplicate_credits_wear_or_output(self):
        game,country,uid=self.support_case()
        before=copy.deepcopy((game.uid,game.material_credit,game.material_events,game.upkeep_wear,
                              game.upkeep_log,game.machine_output_log,game.production_trace))
        self.assertFalse(game.production())
        self.assertEqual(before,(game.uid,game.material_credit,game.material_events,game.upkeep_wear,
                                 game.upkeep_log,game.machine_output_log,game.production_trace))
        game.verify()

    def test_no_raw_full_run_imports_no_operating_materials(self):
        game=Game(32112,'coupled',focal='Mechania',style='no_raw')
        result=game.run()
        actor=result['countries']['Mechania']
        self.assertEqual(actor['import_goods'].get('ore',0),0)
        self.assertEqual(actor['import_goods'].get('fuel',0),0)
        self.assertEqual(actor['purchase_by_good']['ore'],0)
        self.assertEqual(actor['purchase_by_good']['fuel'],0)
        self.assertGreater(actor['machine_produced_by_gen']['1'],0)
        game.verify()

    def test_completed_run_replay_does_not_duplicate_new_instrumentation(self):
        game=Game(32113,'service')
        result=game.run()
        trace=copy.deepcopy(game.trace())
        self.assertEqual(game.run(),result)
        self.assertEqual(game.trace(),trace)


if __name__=='__main__':
    unittest.main(verbosity=2)
