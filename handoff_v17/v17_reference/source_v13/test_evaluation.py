"""v11 public minimum-price and shadow-development accounting boundaries.

The inherited 298 tests are untouched. Constructed level/plan fixtures isolate
investment boundaries; they are never counted as complete game simulations.
Goods and transfers in those fixtures still use real physical IDs and commands.
"""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import patch

from evaluation_engine import Game, SCORING_MODES, DIAGNOSTICS
from routing_engine import Game as V10
from reference_engine import GOODS, NAMES


class EvaluationTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, ids, amount=10, action=None):
        action = action or f'fixture:transfer:{len(game.transactions)}'
        self.assertTrue(game.settle_transaction(
            [{'seller':seller, 'buyer':buyer, 'ids':list(ids)}],
            (buyer, seller, amount), 'direct', action))

    def fund(self, game, name, target=800):
        country = game.cs[name]
        for donor in game.cs.values():
            if donor.name == name or country.cash >= target:
                continue
            amount = min(donor.cash, target-country.cash)
            if amount:
                game.mint(country, 'wheat', 1, initial=True)
                self.transfer(game, name, donor.name, [game.uid], amount)
        self.assertGreaterEqual(country.cash, target)

    def case(self, name='Technia', round_number=4, style='normal', level=2):
        game = Game(75101, focal=name, style=style)
        game.r = round_number
        country = game.cs[name]
        country.levels['electronics'] = level
        country.elec_tech = min(3, level)
        self.fund(game, name)
        for good, quantity in (('ore',20),('fuel',20),('wheat',20),('banana',20),('electronics',3)):
            game.mint(country, good, quantity, initial=True)
        game.plan_cache[(game.r, name)] = 'electronics'
        self.assertTrue(game.settle_round(country))
        return game, country

    def machine(self, game, owner, grade=2):
        game.mint(game.cs[owner], 'machine', 1, gen=grade, initial=True)
        return game.uid

    def foreign_machine(self, game, buyer='Technia', grade=2, seller='Mechania'):
        uid = self.machine(game, seller, grade)
        self.transfer(game, seller, buyer, [uid])
        return uid

    def without_evaluation(self, result):
        result = copy.deepcopy(result)
        for country in result['countries'].values():
            country.pop('evaluation', None)
        result['world'].pop('evaluation', None)
        result['world'].pop('evaluation_config', None)
        return result

    def test_unknown_behaviors_and_conflicting_overrides_rejected(self):
        for kwargs in ({'style':'unknown'}, {'style':'minimum'},
                       {'focal':'Technia','style':'minimum','behaviors':{'Technia':'idle'}},
                       {'behaviors':{'Atlantis':'minimum'}},
                       {'behaviors':{'Technia':'no_raw'}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Game(75102, **kwargs)

    def test_normal_cheap_idle_and_refusal_economies_equal_frozen_v10(self):
        for seed, focal, style in ((75103,None,'normal'), (75104,'Technia','cheap'),
                                    (75105,'Mechania','idle'), (75106,'Technia','no_raw'),
                                    (75107,'Novia','no_high_machine')):
            with self.subTest(style=style):
                old = V10(seed, 'market_first', focal=focal, style=style)
                new = Game(seed, focal=focal, style=style)
                expected, actual = old.run(), new.run()
                self.assertEqual(expected, self.without_evaluation(actual))
                for attribute in ('units','orders','transactions','cash_ledger','raw_round_ledger',
                                  'needs_ledger','production_trace','development_log','development_use_log',
                                  'development_output_log','price_history','route_records','route_actions'):
                    self.assertEqual(getattr(old,attribute), getattr(new,attribute), attribute)

    def test_minimum_behavior_keeps_all_physical_cost_and_permission_rules(self):
        old = V10(75108, 'market_first')
        for style in ('minimum','minimum_passive'):
            game = Game(75108, focal='Technia', style=style)
            for attr in ('initial_cash','initial_assets','initial_capacity','config','opt','prices','starter_allocation'):
                self.assertEqual(getattr(old,attr), getattr(game,attr), (style,attr))
            for name, c in game.cs.items():
                ref = old.cs[name]
                self.assertEqual(c.levels,ref.levels)
                self.assertEqual(c.expand,ref.expand)
                for good in c.levels:
                    self.assertEqual(game.upgrade_cost(c,good),old.upgrade_cost(ref,good))
                    self.assertEqual(game.upgrade_requirements(c,good),old.upgrade_requirements(ref,good))
                    self.assertEqual(game.resource_requirements(c,good,2),old.resource_requirements(ref,good,2))
            game.r = old.r = 1
            game.production()
            reference = V10(75108, 'market_first');reference.r = 1;reference.production()
            self.assertEqual(game.units,reference.units)

    def test_minimum_is_one_tick_not_half_reference_and_advice_is_pure(self):
        game = Game(75109, focal='Technia', style='minimum');game.r = 3
        country = game.cs['Technia']
        before = copy.deepcopy(game.__dict__)
        for good in GOODS:
            for generation in ((1,2,3) if good in ('machine','electronics') else (1,)):
                advice = game.price_recommendation(country,good,generation)
                self.assertEqual(advice['price'],1)
                self.assertEqual(advice['reason'],'fixed_legal_public_minimum')
                self.assertGreater(advice['regular_recommendation'],advice['price'])
        self.assertEqual(before,game.__dict__)

    def test_minimum_public_orders_and_all_recommendation_logs_match(self):
        game = Game(75110, focal='Tropia', style='minimum');game.r = 1
        country = game.cs['Tropia']
        for good in GOODS:game.mint(country,good,15,initial=True)
        protected = {good:game.protected_ids(country,good) for good in GOODS}
        game.prepare_orders(country)
        offers = [o for o in game.orders.values() if o.seller == country.name]
        self.assertTrue(offers)
        self.assertTrue(all(o.price == 1 for o in offers))
        for row in game.offer_history:
            self.assertEqual(row['prices'],[1])
            self.assertFalse(set(row['ids']) & protected[row['good']])
        for row in game.advice_log:
            if row['kind'] == 'offer':
                self.assertEqual(row['recommendation']['price'],1)
                self.assertEqual(row['actual_prices'],[1])
        game.verify()

    def test_minimum_changes_price_without_unprotecting_or_oversupplying_stock(self):
        games = [Game(75111,focal='Tropia',style=s) for s in ('normal','minimum')]
        chosen = []
        for game in games:
            game.r = 1;country = game.cs['Tropia']
            game.mint(country,'banana',25,initial=True)
            game.prepare_orders(country)
            chosen.append({o.good:sorted(i for q in game.orders.values() if q.good==o.good and q.seller==country.name for i in q.units)
                           for o in game.orders.values() if o.seller==country.name})
        self.assertEqual(chosen[0],chosen[1])
        self.assertEqual(games[0].listing_plan_log,games[1].listing_plan_log)

    def test_legal_minimum_order_settles_exact_integer_unit_price(self):
        game = Game(75112, focal='Tropia', style='minimum');game.r = 1
        country = game.cs['Tropia'];game.mint(country,'banana',12,initial=True)
        game.prepare_orders(country)
        buyer = game.cs['Grainia'];before = buyer.cash
        got = game.market_buy(buyer,'banana',2,2)
        self.assertEqual(got,2)
        self.assertEqual(before-buyer.cash,2)
        self.assertEqual(game.transactions[-1]['cash'],('Grainia','Tropia',2))
        game.verify()

    def test_illegal_order_prices_stay_illegal_under_minimum_behavior(self):
        game = Game(75113,focal='Tropia',style='minimum');game.r = 1
        country = game.cs['Tropia'];uid = game.ids(country,'banana')[0]
        for price in (0,-1,False,True,0.5,1.0,'1',None):
            before = copy.deepcopy((game.orders,game.units,game.cs))
            with self.assertRaises(ValueError):game.make_order(country,[uid],price)
            self.assertEqual(before,(game.orders,game.units,game.cs))
        self.assertTrue(game.make_order(country,[uid],1))

    def test_public_minimum_does_not_reprice_direct_counteroffers(self):
        amounts = []
        for style in ('normal','minimum'):
            game = Game(75114,focal='Tropia',style=style);game.r = 1
            uid = game.ids(game.cs['Tropia'],'banana')[0]
            def supply(country,good,min_gen=1):
                return [uid] if (country.name,good)==('Tropia','banana') else []
            with patch.object(game,'get_surplus',side_effect=supply), patch.object(game,'need',return_value=0):
                self.assertEqual(game.negotiate(game.cs['Grainia'],'banana',1,budget=100),1)
            self.assertEqual(game.transactions[-1]['channel'],'direct')
            amounts.append(game.transactions[-1]['cash'][2])
            self.assertGreater(amounts[-1],game.opt.price_tick)
        self.assertEqual(amounts[0],amounts[1])

    def test_public_minimum_does_not_change_barter_reference_valuation(self):
        transfers = []
        for style in ('normal','minimum'):
            game = Game(75115,focal='Tropia',style=style);game.r = 1
            banana = game.ids(game.cs['Tropia'],'banana')[0]
            wheat = game.ids(game.cs['Grainia'],'wheat')[0]
            def supply(country,good,min_gen=1):
                return {('Tropia','banana'):[banana],('Grainia','wheat'):[wheat]}.get((country.name,good),[])
            def demand(country,good):return int((country.name,good)==('Tropia','wheat'))
            with patch.object(game,'get_surplus',side_effect=supply),patch.object(game,'need',side_effect=demand):
                self.assertEqual(game.negotiate(game.cs['Grainia'],'banana',1,budget=100),1)
            self.assertEqual(game.transactions[-1]['channel'],'barter')
            self.assertIsNone(game.transactions[-1]['cash'])
            transfers.append(game.transactions[-1])
        self.assertEqual(transfers[0],transfers[1])

    def test_secondary_behavior_changes_only_selected_countries(self):
        game = Game(75116,focal='Mechania',style='idle',behaviors={'Technia':'minimum'})
        self.assertEqual(game.cs['Mechania'].style,'idle')
        self.assertEqual(game.cs['Technia'].style,'normal')
        self.assertEqual(game.price_recommendation(game.cs['Technia'],'electronics',1)['price'],1)
        self.assertGreater(game.price_recommendation(game.cs['Novia'],'electronics',1)['price'],1)
        self.assertEqual(game.behaviors,{'Technia':'minimum','Mechania':'idle'})

    def test_passive_minimum_keeps_buying_but_cannot_invest(self):
        game,country = self.case(style='minimum_passive')
        self.assertEqual(country.style,'trade')
        self.assertFalse(game.investment_snapshot(country)['legal'])
        self.assertFalse(game.invest(country,'fixture:passive'))
        self.assertEqual(country.investment,0)
        seller = game.cs['Tropia'];game.mint(seller,'banana',1,initial=True)
        game.make_order(seller,[game.uid],1)
        self.assertEqual(game.market_buy(country,'banana',1,1),1)
        self.assertEqual(game.evaluation_rows('ready'),[])

    def test_snapshot_does_not_create_plan_or_touch_caches(self):
        game = Game(75117);game.r = 3;country = game.cs['Technia']
        before = copy.deepcopy(game.__dict__)
        first = game.investment_snapshot(country)
        for _ in range(5):self.assertEqual(first,game.investment_snapshot(country))
        self.assertIn('no_cached_plan',first['blockers'])
        self.assertFalse(first['ready'])
        self.assertEqual(before,game.__dict__)

    def test_cached_snapshot_is_pure_and_machine_absence_is_ready_need(self):
        game,country = self.case()
        before = copy.deepcopy(game.__dict__)
        snapshot = game.investment_snapshot(country)
        self.assertEqual(snapshot['machine_min_gen'],2)
        self.assertEqual(snapshot['free_qualified_ids'],[])
        self.assertTrue(snapshot['ready'])
        self.assertEqual(snapshot['blockers'],[])
        self.assertEqual(before,game.__dict__)

    def test_missing_machine_attempt_is_in_ready_but_not_success_only(self):
        game,country = self.case()
        self.assertFalse(game.invest(country,'fixture:missing'))
        self.assertEqual(game.evaluation_rows('legacy'),[])
        self.assertEqual(game.evaluation_rows('success_only'),[])
        for mode in ('ready','ready_once'):
            row, = game.evaluation_rows(mode)
            self.assertEqual((row['needed'],row['external'],row['fulfilled']),(1,1,0))
            self.assertEqual(row['used_ids'],[])
        game.verify()

    def test_cash_shortage_does_not_manufacture_machine_opportunity(self):
        game,country = self.case()
        target = game.upgrade_cost(country,'electronics')+game.reserve(country)-1
        game.mint(game.cs['Ferria'],'ore',1,initial=True)
        self.transfer(game,'Ferria',country.name,[game.uid],country.cash-target)
        self.assertFalse(game.invest(country,'fixture:cash-short'))
        attempt, = game.evaluation_attempts
        self.assertIn('cash',attempt['blockers']);self.assertFalse(attempt['ready'])
        self.assertEqual(game.evaluation_rows('ready'),[])

    def test_food_and_living_guards_exclude_unready_machine_demand(self):
        for reason in ('food','electronics'):
            game,country = self.case()
            if reason=='food':country.satisfied_rounds.discard(game.r)
            else:
                ids = game.ids(country,'electronics')
                self.transfer(game,country.name,'Ferria',ids,1)
            self.assertFalse(game.invest(country,'fixture:household-short'))
            attempt, = game.evaluation_attempts
            self.assertIn('household',attempt['blockers'])
            self.assertEqual(game.evaluation_rows('ready'),[])

    def test_research_plus_next_production_raw_inputs_are_required(self):
        for good in ('ore','fuel'):
            game,country = self.case(round_number=3)
            snapshot = game.investment_snapshot(country)
            need = snapshot['raw_required'].get(good,0)
            self.assertGreater(need,0)
            keep = need-1
            ids = game.ids(country,good)[keep:]
            self.transfer(game,country.name,'Ferria',ids,1)
            after = game.investment_snapshot(country)
            self.assertFalse(after['raw_ok'])
            self.assertFalse(game.invest(country,'fixture:raw-short'))
            self.assertEqual(game.evaluation_rows('ready'),[])

    def test_exact_cash_and_raw_thresholds_remain_eligible(self):
        game,country = self.case()
        snapshot = game.investment_snapshot(country)
        for good,need in snapshot['raw_required'].items():
            excess = game.ids(country,good)[need:]
            if excess:self.transfer(game,country.name,'Ferria',excess,1)
        target = snapshot['cash_cost']+snapshot['reserve']
        uid = game.ids(game.cs['Ferria'],'wheat')[0]
        self.transfer(game,'Ferria',country.name,[uid],country.cash-target)
        self.assertTrue(game.investment_snapshot(country)['ready'])
        self.assertFalse(game.invest(country,'fixture:threshold'))
        self.assertEqual(len(game.evaluation_rows('ready')),1)

    def test_no_requirement_late_round_and_ineligible_goal_are_not_needs(self):
        for round_number,level,goal in ((4,1,'electronics'),(8,2,'electronics'),(4,2,'banana')):
            game,country = self.case(round_number=round_number,level=level)
            game.plan_cache[(game.r,country.name)] = goal
            snapshot = game.investment_snapshot(country)
            self.assertFalse(snapshot['ready'])
            self.assertTrue('no_machine_requirement' in snapshot['blockers'] or 'ineligible_goal' in snapshot['blockers'])

    def test_own_qualified_machine_is_used_without_external_credit(self):
        game,country = self.case();uid = self.machine(game,country.name,2)
        self.assertTrue(game.invest(country,'fixture:own-machine'))
        attempt, = game.evaluation_attempts
        self.assertEqual(attempt['machine_used']['uid'],uid)
        self.assertEqual((attempt['external'],attempt['fulfilled']),(0,0))
        for mode in SCORING_MODES[1:]:
            row, = game.evaluation_rows(mode)
            self.assertEqual((row['external'],row['fulfilled']),(0,0))
        game.verify()

    def test_imported_machine_use_is_actual_fulfilled_development_need(self):
        game,country = self.case();uid = self.foreign_machine(game)
        self.assertTrue(game.invest(country,'fixture:foreign-machine'))
        row, = game.evaluation_rows('ready_once')
        self.assertEqual((row['external'],row['fulfilled']),(1,1))
        self.assertEqual(row['used_ids'],[uid])
        self.assertIn(uid,country.stock)
        self.assertEqual(game.development_log[0]['machine']['uid'],uid)
        self.assertFalse(any(r['good']=='machine' and r['purpose']=='development' for r in game.needs_ledger))
        game.verify()

    def test_imported_machine_presence_alone_is_not_fulfillment(self):
        game,country = self.case();uid = self.foreign_machine(game)
        game.make_order(country,[uid],70)
        self.assertFalse(game.invest(country,'fixture:listed-import'))
        row, = game.evaluation_rows('ready')
        self.assertEqual((row['external'],row['fulfilled']),(1,0))
        self.assertEqual(row['used_ids'],[])

    def test_listed_own_machine_does_not_fabricate_external_shortage(self):
        game,country = self.case();uid = self.machine(game,country.name,2)
        game.make_order(country,[uid],70)
        self.assertFalse(game.invest(country,'fixture:listed-own'))
        row, = game.evaluation_rows('ready')
        self.assertEqual((row['external'],row['fulfilled']),(0,0))

    def test_low_generation_domestic_alternative_does_not_mask_high_need(self):
        game,country = self.case();uid = self.foreign_machine(game)
        self.assertTrue(any(game.units[i].origin==country.name and game.units[i].gen==1 for i in country.stock if game.units[i].good=='machine'))
        self.assertTrue(game.invest(country,'fixture:grade-specific'))
        row, = game.evaluation_rows('ready_once')
        self.assertEqual((row['external'],row['fulfilled'],row['used_ids']),(1,1,[uid]))

    def test_returned_own_origin_machine_is_not_foreign_import_service(self):
        game,country = self.case();uid = self.machine(game,country.name,2)
        self.transfer(game,country.name,'Ferria',[uid],1)
        self.transfer(game,'Ferria',country.name,[uid],1)
        self.assertTrue(game.invest(country,'fixture:return-own'))
        attempt, = game.evaluation_attempts
        self.assertIsNotNone(attempt['machine_used']['import_transaction'])
        self.assertEqual((attempt['external'],attempt['fulfilled']),(0,0))

    def test_same_machine_reused_in_next_round_is_one_import_two_real_uses(self):
        game,country = self.case();uid = self.foreign_machine(game)
        self.assertTrue(game.invest(country,'fixture:reuse-first'))
        game.r = 5;game.plan_cache[(5,country.name)] = 'electronics'
        self.assertTrue(game.settle_round(country))
        self.assertTrue(game.invest(country,'fixture:reuse-second'))
        rows = game.evaluation_rows('ready_once')
        self.assertEqual(len(rows),2)
        self.assertEqual({r['used_ids'][0] for r in rows},{uid})
        self.assertEqual(sum(r['fulfilled'] for r in rows),2)
        self.assertEqual(country.imported['machine'],1)
        self.assertEqual(len(country.useful_imports & {uid}),1)
        game.verify()

    def test_ready_once_skips_same_round_machine_already_credited_as_equipment(self):
        game,country = self.case()
        self.transfer(game,country.name,'Ferria',game.ids(country,'machine'),1)
        uid = self.foreign_machine(game)
        game.record_need(country,'machine',1,'equipment:wheat',[uid])
        game.mark_use(country,uid,'equipment')
        self.assertEqual(game.needs_ledger[-1]['fulfilled'],1)
        self.assertTrue(game.invest(country,'fixture:equipment-overlap'))
        self.assertTrue(game.evaluation_attempts[0]['already_credited'])
        self.assertEqual(len(game.evaluation_rows('ready')),1)
        self.assertEqual(game.evaluation_rows('ready_once'),[])

    def test_uncredited_equipment_use_does_not_erase_development_credit(self):
        game,country = self.case();uid = self.foreign_machine(game)
        game.record_need(country,'machine',1,'equipment:wheat',[uid])
        game.mark_use(country,uid,'equipment')
        self.assertEqual(game.needs_ledger[-1]['fulfilled'],0)
        self.assertTrue(game.invest(country,'fixture:no-equipment-credit'))
        self.assertFalse(game.evaluation_attempts[0]['already_credited'])
        row, = game.evaluation_rows('ready_once')
        self.assertEqual(row['fulfilled'],1)

    def test_previous_round_or_different_machine_credit_is_not_overlap(self):
        for prior_round in (False,True):
            game,country = self.case()
            self.transfer(game,country.name,'Ferria',game.ids(country,'machine'),1)
            uid = self.foreign_machine(game)
            used = uid if prior_round else self.foreign_machine(game,grade=1)
            game.record_need(country,'machine',1,'equipment:wheat',[used])
            if prior_round:game.needs_ledger[-1]['round'] = 3
            self.assertTrue(game.invest(country,'fixture:nonoverlap'))
            self.assertFalse(game.evaluation_attempts[0]['already_credited'])
            self.assertEqual(len(game.evaluation_rows('ready_once')),1)

    def test_recorded_import_transaction_survives_later_resale(self):
        game,country = self.case();uid = self.foreign_machine(game)
        self.assertTrue(game.invest(country,'fixture:historical-use'))
        before = copy.deepcopy(game.evaluation_attempts)
        self.transfer(game,country.name,'Ferria',[uid],1)
        self.assertNotEqual(game.units[uid].last_import,before[0]['machine_used']['import_transaction'])
        self.assertEqual(game.evaluation_attempts,before)
        self.assertEqual(game.evaluation_rows('ready_once')[0]['fulfilled'],1)

    def test_invalid_action_ids_do_not_instrument_or_plan(self):
        game = Game(75118);game.r = 4;country = game.cs['Technia']
        before = copy.deepcopy(game.__dict__)
        for action in ([],{},False,True,7,''):
            self.assertFalse(game.invest(country,action))
            self.assertEqual(before,game.__dict__)

    def test_failed_replay_stays_failed_then_new_command_fulfills_one_opportunity(self):
        game,country = self.case()
        self.assertFalse(game.invest(country,'fixture:failed'))
        self.foreign_machine(game)
        before = copy.deepcopy(game.evaluation_attempts)
        self.assertFalse(game.invest(country,'fixture:failed'))
        self.assertEqual(before,game.evaluation_attempts)
        self.assertTrue(game.invest(country,'fixture:new-command'))
        self.assertEqual(len(game.evaluation_attempts),1)
        self.assertEqual(len(game.evaluation_index),1)
        row, = game.evaluation_rows('ready_once')
        self.assertEqual((row['external'],row['fulfilled']),(1,1))

    def test_success_replay_and_second_command_do_not_duplicate_need_or_cost(self):
        game,country = self.case();self.foreign_machine(game)
        self.assertTrue(game.invest(country,'fixture:success'))
        before = copy.deepcopy(game.__dict__)
        self.assertTrue(game.invest(country,'fixture:success'))
        self.assertEqual(before,game.__dict__)
        self.assertFalse(game.invest(country,'fixture:second-investment'))
        self.assertEqual(before,game.__dict__)

    def test_repeated_missing_machine_queries_are_one_round_opportunity(self):
        game,country = self.case()
        for i in range(5):self.assertFalse(game.invest(country,f'fixture:failure-{i}'))
        self.assertEqual(len(game.evaluation_attempts),1)
        self.assertEqual(len(game.evaluation_rows('ready')),1)
        self.assertEqual(game.evaluation_rows('ready')[0]['fulfilled'],0)

    def test_shadow_score_queries_are_pure_and_original_fields_stay_unchanged(self):
        game = Game(75119);result = game.run()
        before = copy.deepcopy(game.__dict__)
        fields = copy.deepcopy(result)
        for name,base in result['countries'].items():
            for mode in SCORING_MODES:
                self.assertEqual(game.evaluation_scores(name,mode,base),base['evaluation']['scores'][mode])
        self.assertEqual(before,game.__dict__)
        self.assertEqual(fields,result)
        self.assertEqual(result,game.summary())

    def test_shadow_scores_are_bounded_and_extra_countries_are_not_ranked(self):
        game = Game(75120,focal='Technia',style='minimum');result = game.run()
        for name,country in result['countries'].items():
            self.assertEqual(set(country['evaluation'])-{'scores'},set(DIAGNOSTICS))
            scores = country['evaluation']['scores']
            self.assertEqual(scores['legacy']['trade'],country['trade'])
            self.assertAlmostEqual(scores['legacy']['score'] or 0,country['score'] or 0)
            for mode,view in scores.items():
                self.assertLessEqual(0,view['external_fulfilled'])
                self.assertLessEqual(view['external_fulfilled'],view['external_need'])
                self.assertGreaterEqual(view['trade'],0);self.assertLessEqual(view['trade'],25)
                self.assertGreaterEqual(view['coverage'],0);self.assertLessEqual(view['coverage'],1)
                if name in NAMES:
                    self.assertGreaterEqual(view['score'],0);self.assertLessEqual(view['score'],100)
                    self.assertAlmostEqual(view['score']-country['score'],view['trade_delta'])
                else:self.assertIsNone(view['score'])
            self.assertEqual(scores['legacy']['added_needed'],0)
        self.assertEqual(result['world']['evaluation']['public_minimum_violations'],0)

    def test_empty_import_denominator_and_maximum_trade_boundary(self):
        game = Game(75121)
        base = {'export_help_rounds':0,'useful_partners':0,'trade':0,'score':0}
        for mode in SCORING_MODES:
            self.assertEqual(game.evaluation_scores('Technia',mode,base)['trade'],0)
        game.needs_ledger = [{'round':1,'country':'Technia','good':'wheat','purpose':'food',
                            'needed':1,'external':1,'fulfilled':1,'used_ids':[]}]
        base = {'export_help_rounds':9,'useful_partners':8,'trade':25,'score':100}
        for mode in SCORING_MODES:
            view = game.evaluation_scores('Technia',mode,base)
            self.assertEqual(view['trade'],25)
            self.assertEqual(view['score'],100)
            self.assertEqual(view['imports_part'],8)
            self.assertEqual(view['effects_import_part'],4)

    def test_unknown_shadow_mode_rejected_without_mutation(self):
        game = Game(75122);before = copy.deepcopy(game.__dict__)
        with self.assertRaises(ValueError):game.evaluation_rows('unknown')
        self.assertEqual(before,game.__dict__)


if __name__ == '__main__':
    unittest.main()
