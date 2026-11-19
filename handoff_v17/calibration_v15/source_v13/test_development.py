"""v9 development chain boundaries; inherited 230 tests stay unchanged.

Fixtures mint real goods and fund wallets with recorded trades. Deliberately
constructed industry levels are local boundary fixtures, never formal results.
"""
from __future__ import annotations
import copy
import unittest

from development_engine import Game
from raw_engine import Game as V8
from reference_engine import GOODS, DURABLES

MODES=('baseline','supply','gate','combined')


class DevelopmentTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, ids, amount=10, action='fixture:transfer', channel='direct'):
        cash=None if channel=='barter' else (buyer,seller,amount)
        self.assertTrue(game.settle_transaction(
            [{'seller':seller,'buyer':buyer,'ids':list(ids)}],cash,channel,action))

    def money_to(self,game,name,target):
        actor=game.cs[name]
        for donor in game.cs.values():
            if donor.name==name or actor.cash>=target:continue
            amount=min(donor.cash,max(0,target-actor.cash))
            if not amount:continue
            game.mint(actor,'wheat',1,initial=True)
            self.transfer(game,name,donor.name,[game.ids(actor,'wheat')[-1]],amount,
                          f'fixture:fund:{name}:{donor.name}:{len(game.transactions)}')
        self.assertGreaterEqual(actor.cash,target)

    def economic_state(self,game):
        return copy.deepcopy((game.cs,game.units,game.orders,game.transactions,
            game.material_credit,game.raw_use_log,game.initial,game.created,
            game.destroyed,game.minted,game.sunk,game.applied,game.action_payload))

    def research_case(self,variant='combined',grade=None,origin='Mechania'):
        game=Game(58110,variant);game.r=2;c=game.cs['Technia']
        c.levels['electronics']=2;c.elec_tech=2
        self.money_to(game,c.name,800)
        game.mint(c,'ore',5,initial=True);game.mint(c,'fuel',3,initial=True)
        game.mint(c,'electronics',1,initial=True)
        uid=None
        if grade:
            seller=game.cs[origin]
            game.r=1;game.mint(seller,'machine',1,gen=grade)
            uid=game.uid;game.r=2
            if origin!=c.name:self.transfer(game,origin,c.name,[uid],10,'fixture:research-machine')
        game.plan_cache[(2,c.name)]='electronics'
        game.settle_round(c)
        self.assertIn(2,c.satisfied_rounds)
        return game,c,uid

    def test_invalid_variant_is_rejected(self):
        with self.assertRaises(ValueError):Game(58101,'unknown')

    def test_new_refusal_styles_require_valid_focal_country(self):
        for style in ('no_high_machine','no_machine'):
            with self.subTest(style=style),self.assertRaises(ValueError):
                Game(58102,'baseline',style=style)
            with self.subTest(style=style),self.assertRaises(ValueError):
                Game(58102,'baseline',focal='Unknown',style=style)

    def test_baseline_preserves_v8_bridge_economy_and_records(self):
        for seed in (58103,58104):
            old=V8(seed,'bridge');new=Game(seed,'baseline')
            expected=old.run();actual=new.run()
            for name,fields in expected['countries'].items():
                for key,value in fields.items():
                    self.assertEqual(value,actual['countries'][name][key],(name,key))
            for key,value in expected['world'].items():
                self.assertEqual(value,actual['world'][key],key)
            for key in ('transactions','cash_ledger','price_history','units','production_trace',
                        'machine_output_log','material_events','raw_use_log','raw_round_ledger'):
                self.assertEqual(getattr(old,key),getattr(new,key),key)

    def test_all_modes_preserve_starting_conditions_prices_and_cash_costs(self):
        old=V8(58105,'bridge')
        for mode in MODES:
            game=Game(58105,mode)
            for key in ('config','initial_capacity','initial_assets','initial_cash',
                        'starter_allocation','prices','opt','global_gen'):
                self.assertEqual(getattr(old,key),getattr(game,key),(mode,key))
            for name,c in game.cs.items():
                other=old.cs[name]
                self.assertEqual(c.cash,other.cash)
                self.assertEqual(c.levels,other.levels)
                for good in GOODS:
                    self.assertEqual(game.count(c,good,False),old.count(other,good,False))
                    for level in (0,1,2,3):
                        previous=c.levels.get(good);old_previous=other.levels.get(good)
                        c.levels[good]=other.levels[good]=level
                        self.assertEqual(game.upgrade_cost(c,good),old.upgrade_cost(other,good),(mode,name,good,level))
                        if previous is None:c.levels.pop(good)
                        else:c.levels[good]=previous
                        if old_previous is None:other.levels.pop(good)
                        else:other.levels[good]=old_previous
            game.verify()

    def test_gate_changes_only_durable_entry_to_level_three(self):
        old=V8(58106,'bridge')
        for mode in MODES:
            game=Game(58106,mode)
            for good in GOODS:
                for level in (0,1,2,3):
                    c=game.cs['Technia'];other=old.cs['Technia']
                    c.levels[good]=other.levels[good]=level
                    expected=old.upgrade_requirements(other,good)
                    if mode in ('gate','combined') and good in DURABLES and level==2:
                        expected=(expected[0],2)
                    self.assertEqual(game.upgrade_requirements(c,good),expected,(mode,good,level))

    def test_supply_legacy_g1_quantity_is_unchanged(self):
        for focus in ('machine','wheat'):
            old=V8(58107,'bridge');new=Game(58107,'supply')
            old.cs['Mechania'].focus=new.cs['Mechania'].focus=focus
            for actual in (False,True):
                self.assertEqual(old.machine_quantity(old.cs['Mechania'],2,actual),
                                 new.machine_quantity(new.cs['Mechania'],2,actual))

    def test_supply_reserves_one_g2_domestic_slot_and_one_sale_slot(self):
        for mode,expected in (('baseline',1),('gate',1),('supply',2),('combined',2)):
            game=Game(58108,mode);c=game.cs['Mechania']
            c.levels['machine']=2;c.machine_tech=2;c.focus='wheat'
            self.assertEqual(game.machine_quantity(c,2),expected)
            self.assertEqual(game.machine_quantity(c,2,True),expected)
            game.r=1;game.mint(c,'machine',1,gen=2)
            self.assertEqual(game.machine_quantity(c,2),expected-1)
            self.assertEqual(game.machine_quantity(c,2,True),expected-1)

    def test_supply_forecast_covers_later_focus_changes(self):
        for grade in (2,3):
            game=Game(58109,'supply');c=game.cs['Mechania']
            c.levels['machine']=grade;c.machine_tech=grade
            for focus in c.levels:
                c.focus=focus
                self.assertGreaterEqual(game.machine_quantity(c,2),game.machine_quantity(c,2,True))
            c.focus='machine'
            self.assertEqual(game.machine_quantity(c,2,True),1)
            self.assertEqual(game.machine_quantity(c,2),2)

    def test_supply_adds_no_slot_for_country_with_only_durable_industries(self):
        game=Game(58111,'supply');c=game.cs['Mechania']
        c.levels={'machine':2};c.machine_tech=2;c.focus='machine'
        self.assertEqual(game.machine_quantity(c,2),1)
        self.assertEqual(game.machine_quantity(c,2,True),1)

    def test_supply_accounts_for_listed_used_and_imported_qualifying_stock(self):
        for source in ('own','listed','used','imported'):
            game=Game(58112,'supply');game.r=1;c=game.cs['Mechania']
            c.levels['machine']=2;c.machine_tech=2;c.focus='wheat'
            if source=='imported':
                seller=game.cs['Technia'];game.mint(seller,'machine',2,gen=2)
                self.transfer(game,seller.name,c.name,game.ids(seller,'machine',min_gen=2),10,'fixture:stock')
                # Mark an earlier own generation launch to isolate stock counting.
                game.mint(c,'machine',1,gen=2)
                self.transfer(game,c.name,'Novia',[game.uid],1,'fixture:launch-sale')
            else:
                game.mint(c,'machine',2,gen=2)
                ids=game.ids(c,'machine',min_gen=2)
                if source=='listed':game.make_order(c,ids,50)
                if source=='used':
                    for uid in ids:game.mark_use(c,uid,'equipment')
            # Same-round fixture sale does not enter previous-round demand at r1.
            self.assertEqual(game.machine_quantity(c,1),0,source)
            game.verify()

    def test_supply_extra_output_requires_real_raw_material_and_keeps_carry(self):
        game=Game(58113,'supply');game.r=2;c=game.cs['Mechania']
        c.levels['machine']=2;c.machine_tech=2;c.focus='wheat'
        game.mint(c,'ore',1,initial=True)
        game.production()
        self.assertEqual(game.count(c,'machine',min_gen=2),2)
        self.assertEqual(game.operation_inputs[(c.name,'production','ore')],1)
        self.assertEqual(game.material_credit[(c.name,'ore',2)],0)
        self.assertEqual(c.production_failures,0)
        game.verify()

    def test_supply_shortage_never_creates_unpaid_advanced_machine(self):
        game=Game(58114,'combined');game.r=2;c=game.cs['Mechania']
        c.levels['machine']=2;c.machine_tech=2;c.focus='wheat'
        self.assertEqual(game.count(c,'ore'),0)
        game.production()
        self.assertEqual(game.count(c,'machine',min_gen=2),0)
        self.assertEqual(c.produced['machine'],1)
        self.assertEqual(c.production_failures,1)
        game.verify()

    def test_gate_blocks_level_three_without_qualifying_machine_atomically(self):
        for grade in (None,1):
            game,c,uid=self.research_case('combined',grade)
            before=self.economic_state(game)
            self.assertFalse(game.invest(c,'fixture:blocked-grade'))
            # Attempts/blocks are diagnostic counters, not economic effects.
            self.assertEqual((c.cash,c.levels,c.stock,game.sunk,game.destroyed,game.raw_use_log),
                             (before[0][c.name].cash,before[0][c.name].levels,before[0][c.name].stock,
                              before[10],before[8],before[5]))
            self.assertEqual(c.elec_tech,2)
            game.verify()

    def test_baseline_keeps_original_level_three_rule(self):
        game,c,uid=self.research_case('baseline')
        self.assertTrue(game.invest(c,'fixture:old-rule'))
        self.assertEqual(c.elec_tech,3)
        game.verify()

    def test_gate_accepts_reusable_g2_or_g3_and_preserves_machine(self):
        for grade in (2,3):
            game,c,uid=self.research_case('gate',grade)
            old_count=game.count(c,'machine');before=game.count(c,'ore')
            self.assertTrue(game.invest(c,'fixture:qualified'))
            self.assertEqual((c.levels['electronics'],c.elec_tech),(3,3))
            self.assertEqual(game.count(c,'ore'),before-2)
            self.assertEqual(game.count(c,'machine'),old_count)
            self.assertEqual(game.units[uid].owner,c.name)
            self.assertIn((2,c.name,uid,'development'),game.use_episodes)
            self.assertFalse(any(u.origin==c.name and u.good=='electronics' and u.gen==3 for u in game.units.values()))
            game.r=3;game.production()
            self.assertTrue(any(u.origin==c.name and u.good=='electronics' and u.gen==3 and u.born==3 for u in game.units.values()))
            game.verify()

    def test_listed_high_grade_machine_cannot_be_spent_by_direct_investment(self):
        game,c,uid=self.research_case('combined',2)
        game.make_order(c,[uid],60)
        self.assertFalse(game.invest(c,'fixture:listed-grade'))
        self.assertEqual(c.elec_tech,2)
        game.prepare_orders(c)
        self.assertIsNone(game.units[uid].order)
        self.assertTrue(game.invest(c,'fixture:recalled-grade'))
        game.verify()

    def test_successful_development_command_replay_has_no_second_charge_or_use(self):
        game,c,uid=self.research_case('combined',2)
        self.assertTrue(game.invest(c,'fixture:once'))
        before=self.economic_state(game);episodes=copy.deepcopy(game.use_episodes)
        self.assertTrue(game.invest(c,'fixture:once'))
        self.assertFalse(game.invest(c,'fixture:twice'))
        self.assertEqual(before,self.economic_state(game))
        self.assertEqual(episodes,game.use_episodes)
        game.verify()

    def test_failed_grade_command_does_not_turn_into_success_on_replay(self):
        game,c,uid=self.research_case('combined')
        self.assertFalse(game.invest(c,'fixture:missing'))
        game.mint(c,'machine',1,gen=2,initial=True)
        self.assertFalse(game.invest(c,'fixture:missing'))
        self.assertEqual(c.elec_tech,2)
        self.assertTrue(game.invest(c,'fixture:new-command'))
        game.verify()

    def test_machine_refusal_is_atomic_in_all_channels(self):
        for style in ('no_high_machine','no_machine'):
            for channel in ('market','direct','barter'):
                game=Game(58115,'combined',focal='Technia',style=style);game.r=1
                seller=game.cs['Mechania'];buyer=game.cs['Technia']
                game.mint(seller,'machine',1,gen=2);uid=game.uid
                legs=[{'seller':seller.name,'buyer':buyer.name,'ids':[uid]}]
                cash=(buyer.name,seller.name,20)
                if channel=='barter':
                    legs.append({'seller':buyer.name,'buyer':seller.name,'ids':[game.ids(buyer,'wheat')[0]]})
                    cash=None
                before=self.economic_state(game)
                self.assertFalse(game.settle_transaction(legs,cash,channel,'fixture:refusal'))
                self.assertEqual(before,self.economic_state(game),(style,channel))
                game.verify()

    def test_no_high_machine_allows_g1_and_own_advanced_production(self):
        game=Game(58116,'combined',focal='Technia',style='no_high_machine');game.r=1
        seller=game.cs['Mechania'];buyer=game.cs['Technia']
        self.transfer(game,seller.name,buyer.name,[game.ids(seller,'machine')[0]],10,'fixture:g1')
        buyer.levels['machine']=2;buyer.machine_tech=2;buyer.focus='machine'
        game.mint(buyer,'ore',1,initial=True)
        game.production()
        self.assertGreater(game.count(buyer,'machine',min_gen=2),0)
        game.verify()

    def test_machine_refusal_does_not_block_exports_or_other_countries(self):
        game=Game(58117,'combined',focal='Technia',style='no_high_machine');game.r=1
        c=game.cs['Technia'];game.mint(c,'machine',1,gen=3);uid=game.uid
        self.transfer(game,c.name,'Novia',[uid],10,'fixture:export')
        self.transfer(game,'Novia','Mechania',[uid],10,'fixture:other-import')
        game.verify()

    def test_all_variants_keep_idle_and_no_trade_meanings(self):
        for mode in MODES:
            game=Game(58118,mode,focal='Technia',style='idle');result=game.run()
            actor=result['countries']['Technia']
            self.assertEqual((actor['imports'],actor['exports'],actor['investment']),(0,0,0))
            self.assertGreater(sum(actor['produced'].values()),0)
            self.assertGreater(actor['tax'],0)
            no_trade=Game(58119,mode,trade_enabled=False);result=no_trade.run()
            self.assertEqual(result['world']['transactions'],0)
            self.assertGreater(sum(result['world']['production'].values()),0)


    def test_invalid_command_ids_have_no_instrumentation_or_economic_side_effect(self):
        game,c,uid=self.research_case('combined',2)
        before=copy.deepcopy((self.economic_state(game),game.development_log,
                              game.development_attempt_log,game.development_use_log))
        for value in ('',0,False,[],{}):
            self.assertFalse(game.invest(c,value))
            self.assertEqual(before,(self.economic_state(game),game.development_log,
                                    game.development_attempt_log,game.development_use_log))

    def test_purchase_without_development_has_no_completed_chain(self):
        game,c,uid=self.research_case('combined',2)
        self.assertEqual(game.development_chains(),[])
        self.assertEqual(game.development_log,[])
        self.assertFalse(any(e['uid']==uid and e['purpose']=='development' for e in game.development_use_log))
        game.verify()

    def test_chain_requires_later_funded_output_and_actual_use(self):
        game,c,uid=self.research_case('combined',2)
        game.production()  # output made before the upgrade in this same round
        before_ids={i for i,u in game.units.items() if u.origin==c.name and u.good=='electronics'}
        self.assertTrue(game.invest(c,'fixture:chain'))
        chain=game.development_chains()[0]
        self.assertEqual(chain['output_ids'],[])
        self.assertTrue(chain['imported_machine']);self.assertTrue(chain['foreign_machine'])
        game.r=3;game.production()
        chain=game.development_chains()[0]
        self.assertTrue(chain['output_ids'])
        self.assertFalse(before_ids & set(chain['output_ids']))
        self.assertEqual(chain['used_output_ids'],[])
        unit=chain['output_ids'][0]
        self.transfer(game,c.name,'Ferria',[unit],10,'fixture:chain-output')
        game.settle_round(game.cs['Ferria'])
        chain=game.development_chains()[0]
        self.assertIn(unit,chain['used_output_ids'])
        self.assertIn(unit,chain['foreign_used_output_ids'])
        before=copy.deepcopy((game.development_output_log,game.development_use_log,chain))
        self.assertFalse(game.production())
        self.assertFalse(game.settle_round(game.cs['Ferria']))
        self.assertEqual(before,(game.development_output_log,game.development_use_log,game.development_chains()[0]))
        game.verify()

    def test_fallback_output_does_not_complete_advanced_development_chain(self):
        game,c,uid=self.research_case('combined',2)
        self.assertTrue(game.invest(c,'fixture:research'))
        self.transfer(game,c.name,'Mineria',game.ids(c,'ore'),1,'fixture:remove-raw')
        game.r=3;game.production()
        rows=[r for r in game.development_output_log if r['country']==c.name and r['industry']=='electronics']
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['funded'])
        self.assertTrue(rows[0]['ids'])
        self.assertEqual({game.units[i].gen for i in rows[0]['ids']},{1})
        self.assertEqual(game.development_chains()[0]['output_ids'],[])
        game.verify()

    def test_reused_machine_counts_distinct_developments_without_duplicate_output(self):
        game,c,uid=self.research_case('combined',2)
        self.assertTrue(game.invest(c,'fixture:level3'))
        game.r=3;game.production();game.settle_round(c)
        self.money_to(game,c.name,800)
        game.mint(c,'ore',4,initial=True);game.mint(c,'fuel',3,initial=True)
        game.plan_cache[(3,c.name)]='electronics'
        self.assertTrue(game.invest(c,'fixture:level4'))
        game.r=4;game.production()
        chains=game.development_chains()
        self.assertEqual(len(chains),2)
        self.assertEqual({e['machine']['uid'] for e in chains},{uid})
        self.assertEqual(sum(e['foreign_machine'] for e in chains),2)
        self.assertTrue(chains[0]['output_ids']);self.assertTrue(chains[1]['output_ids'])
        self.assertFalse(set(chains[0]['output_ids'])&set(chains[1]['output_ids']))
        self.assertEqual({game.units[i].born for i in chains[0]['output_ids']},{3})
        self.assertEqual({game.units[i].born for i in chains[1]['output_ids']},{4})
        self.assertEqual(len([e for e in game.development_use_log if e['uid']==uid and e['purpose']=='development']),2)
        game.verify()

    def test_historical_import_snapshot_survives_later_resale(self):
        game,c,uid=self.research_case('combined',2)
        self.assertTrue(game.invest(c,'fixture:before-resale'))
        original=game.development_log[0]['machine']['import_transaction']
        game.r=3;self.transfer(game,c.name,'Novia',[uid],10,'fixture:resale')
        self.assertNotEqual(game.units[uid].last_import,original)
        self.assertEqual(game.development_log[0]['machine']['import_transaction'],original)
        self.assertTrue(game.development_chains()[0]['foreign_machine'])
        game.verify()

    def test_reimported_own_machine_is_imported_but_not_foreign_origin(self):
        game,c,uid=self.research_case('combined',2,origin='Technia')
        self.transfer(game,c.name,'Novia',[uid],10,'fixture:own-export')
        self.transfer(game,'Novia',c.name,[uid],10,'fixture:own-return')
        self.assertTrue(game.invest(c,'fixture:returned-machine'))
        chain=game.development_chains()[0]
        self.assertTrue(chain['imported_machine'])
        self.assertFalse(chain['foreign_machine'])
        self.assertEqual(chain['machine']['origin'],c.name)
        game.verify()

    def test_new_metrics_preserve_unranked_extra_countries_and_old_score(self):
        game=Game(58120,'combined');result=game.run()
        self.assertEqual(result['world']['development']['upgrades'],sum(c.upgrades for c in game.cs.values()))
        for name,x in result['countries'].items():
            self.assertEqual(x['development']['upgrades'],x['upgrades'])
            if name in ('Novia','Agrea','Ferria'):
                self.assertIsNone(x['score']);self.assertIsNone(x['economic']);self.assertIsNone(x['industry'])
            else:
                self.assertAlmostEqual(x['score'],x['economic']+x['industry']+x['trade']+x['happy']/4)
                self.assertAlmostEqual(x['industry'],x['industry_capacity_score']+x['industry_use_score'])
        before=copy.deepcopy((game.development_log,game.development_output_log,game.development_use_log))
        self.assertEqual(game.run(),result)
        self.assertEqual(before,(game.development_log,game.development_output_log,game.development_use_log))


if __name__=='__main__':unittest.main(verbosity=2)
