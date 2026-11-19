"""v8 resource boundaries; original 197 tests are retained unchanged.

Fixtures use real goods and recorded transfers. Deliberately corrupted states
are tested for rejection, never passed off as valid accounting.
"""
import copy
import math
import unittest
from collections import Counter, defaultdict

from raw_engine import Game, RawPolicy, RAW_MODES, REFUSAL_STYLES, RAW_GOODS, SOURCE_KINDS
from recommendation_engine import Game as V7
from machinery_engine import CREDITS_PER_RAW
from reference_engine import GOODS


class RawResourceTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, ids, amount=10, action='fixture:transfer', channel='direct'):
        self.assertTrue(game.settle_transaction(
            [{'seller':seller,'buyer':buyer,'ids':list(ids)}],
            (buyer,seller,amount),channel,action))

    def state(self, game):
        return copy.deepcopy((game.cs,game.units,game.orders,game.transactions,
            game.material_credit,game.material_events,game.raw_use_log,
            game.raw_round_ledger,game.production_trace,game.machine_output_log,
            game.initial,game.created,game.destroyed,game.minted,game.sunk))

    def gen2_case(self, variant='baseline'):
        game=Game(52110,variant);game.r=1;country=game.cs['Mechania']
        country.levels['machine']=2;country.machine_tech=2
        if not game.count(country,'ore'):game.mint(country,'ore',1,initial=True)
        game.production()
        self.assertEqual(country.produced['machine'],1)
        self.assertEqual(game.count(country,'machine',min_gen=2),1)
        return game,country

    def research_case(self, variant, ore):
        game=Game(52111,variant);game.r=2;country=game.cs['Mechania']
        country.levels['machine']=2;country.machine_tech=2
        self.transfer(game,'Mechania','Tropia',game.ids(country,'wheat')[:1],100,'fixture:funding')
        game.mint(country,'electronics',1,initial=True)
        game.mint(country,'ore',ore-game.count(country,'ore'),initial=True)
        game.plan_cache[(2,'Mechania')]='machine'
        game.settle_round(country)
        self.assertIn(2,country.satisfied_rounds)
        return game,country

    def test_invalid_profiles_and_refusal_targets_are_rejected(self):
        for value in (0,-1,3,True,1.0,'2'):
            with self.subTest(credits=value),self.assertRaises(ValueError):RawPolicy(value,'legacy')
        with self.assertRaises(ValueError):RawPolicy(2,'unknown')
        with self.assertRaises(ValueError):Game(52101,'unknown')
        for style in REFUSAL_STYLES:
            with self.subTest(style=style),self.assertRaises(ValueError):Game(52101,'baseline',style=style)

    def test_baseline_exactly_preserves_v7_price_economy_and_records(self):
        for seed in (52102,52103):
            old=V7(seed,'price');new=Game(seed,'baseline')
            expected=old.run();actual=new.run()
            for name,fields in expected['countries'].items():
                for key,value in fields.items():self.assertEqual(value,actual['countries'][name][key],(name,key))
            for key,value in expected['world'].items():
                if key!='v7_note':self.assertEqual(value,actual['world'][key],key)
            for key in ('transactions','cash_ledger','price_history','units','production_trace','machine_output_log'):
                self.assertEqual(getattr(old,key),getattr(new,key),key)
            self.assertEqual(len(old.material_events),len(new.material_events))
            for a,b in zip(old.material_events,new.material_events):
                for key,value in a.items():self.assertEqual(value,b[key])

    def test_profiles_preserve_cash_food_equipment_capacity_and_price_ai(self):
        old=V7(52104,'price')
        for variant in RAW_MODES:
            game=Game(52104,variant)
            self.assertEqual(game.initial_cash,1625)
            for key in ('config','initial_capacity','opt','prices','global_gen'):
                self.assertEqual(getattr(game,key),getattr(old,key),(variant,key))
            self.assertEqual(game.advice_variant,'price')
            self.assertEqual(game.mode,'coupled')
            for name,country in game.cs.items():
                self.assertEqual(country.cash,old.cs[name].cash)
                self.assertEqual(country.levels,old.cs[name].levels)
                for good in ('banana','wheat','machine','electronics'):
                    self.assertEqual(game.count(country,good,False),old.count(old.cs[name],good,False))
            game.verify()

    def test_initial_allocations_are_initial_goods_and_assets_match_real_grants(self):
        industrial={'Mechania','Technia','Novia'}
        for variant,policy in RAW_MODES.items():
            game=Game(52105,variant)
            for name,country in game.cs.items():
                expected={g:int(name in industrial) if policy.starter=='legacy' else
                    int(name in ('Technia','Novia') and (policy.starter=='two_cycles' or
                        policy.starter=='first_cycle' and g=='ore')) for g in RAW_GOODS}
                self.assertEqual(game.starter_allocation[name],expected,(variant,name))
                self.assertEqual(game.initial_assets[name],country.cash+game.stock_value(country))
                self.assertFalse(country.produced)
                for good in RAW_GOODS:
                    self.assertTrue(all(game.units[i].born==0 for i in game.ids(country,good,False)))
            for good in RAW_GOODS:
                self.assertEqual(game.initial[good],sum(x[good] for x in game.starter_allocation.values()))
                self.assertEqual(game.created[good],0)
                self.assertEqual(game.destroyed[good],0)
            self.assertFalse(game.raw_use_log)
            self.assertFalse(game.transactions)
            game.verify()

    def test_first_cycle_preserves_first_output_but_no_starter_reveals_shortage(self):
        reference=Game(52106,'baseline');reference.r=1;reference.production()
        for variant in ('starter','coupled'):
            game=Game(52106,variant);game.r=1;game.production()
            for name in game.cs:
                self.assertEqual(game.cs[name].produced,reference.cs[name].produced,(variant,name))
                self.assertEqual(game.cs[name].production_failures,0)
            self.assertEqual(sum(e['good']=='ore' for e in game.raw_use_log),2)
            self.assertEqual(game.count(game.cs['Mechania'],'ore'),0)
            game.verify()
        for variant in ('no_starter','strict_no_starter'):
            game=Game(52106,variant);game.r=1;game.production()
            self.assertEqual({n for n,c in game.cs.items() if c.production_failures},{'Technia','Novia'})
            self.assertFalse(game.raw_use_log)
            self.assertEqual(game.cs['Mechania'].produced['machine'],1)
            game.verify()

    def test_first_cycle_grant_does_not_claim_to_fund_second_round_fuel(self):
        for variant in ('starter','coupled'):
            game=Game(52107,variant)
            for r in (1,2):game.r=r;game.production()
            for name in ('Technia','Novia'):
                rows=[e for e in game.production_trace if e['round']==2 and e['country']==name and e['industry']=='electronics']
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['required'],{'fuel':1})
                self.assertFalse(rows[0]['funded'])
            game.verify()

    def test_bridge_covers_two_starting_cycles_without_machine_upgrade_subsidy(self):
        game=Game(52129,'bridge')
        self.assertEqual(game.starter_allocation['Mechania'],{'ore':0,'fuel':0})
        for r in (1,2):
            game.r=r;game.production()
        for name in ('Technia','Novia'):
            self.assertEqual(game.cs[name].production_failures,0)
            for raw in RAW_GOODS:
                self.assertEqual(game.operation_inputs[(name,'production',raw)],1)
                self.assertEqual(game.count(game.cs[name],raw),0)
        actor=game.cs['Mechania']
        self.assertEqual(game.projected_resources(actor,'machine')['ore'],1)
        self.assertEqual(game.count(actor,'ore'),0)
        game.verify()

    def test_policy_is_instance_local_and_does_not_patch_upstream_constant(self):
        answers=[]
        for variant in ('baseline','recipe','baseline','coupled','baseline'):
            game=Game(52108,variant);country=game.cs['Mechania']
            country.levels['machine']=3;country.machine_tech=3
            answers.append(game.material_plan(country,2,quantity=2)['raw_spent'])
        self.assertEqual(answers,[2,4,2,4,2])
        self.assertEqual(CREDITS_PER_RAW,2)

    def test_electronics_and_development_recipes_do_not_change_with_machine_intensity(self):
        reference=V7(52109,'price')
        for variant in RAW_MODES:
            game=Game(52109,variant)
            for name in ('Technia','Novia'):
                for level in (1,2,3):
                    country=game.cs[name];original=reference.cs[name]
                    country.levels['electronics']=original.levels['electronics']=level
                    for r in (1,2,3):
                        self.assertEqual(game.resource_requirements(country,'electronics',r),
                                         reference.resource_requirements(original,'electronics',r))
                    self.assertEqual(game.upgrade_requirements(country,'electronics'),reference.upgrade_requirements(original,'electronics'))
                    self.assertEqual(game.upgrade_cost(country,'electronics'),reference.upgrade_cost(original,'electronics'))

    def test_paid_material_carry_funds_later_output_without_second_cash_charge(self):
        for variant,raw_second,total,carry in (('baseline',1,2,1),('recipe',2,3,0)):
            game,country=self.gen2_case(variant)
            uid=game.ids(country,'machine',min_gen=2)[0]
            self.transfer(game,'Mechania','Tropia',[uid],10,'fixture:machine-sale')
            game.mint(country,'ore',raw_second,initial=True)
            game.r=2;cash=country.cash;before=country.produced['machine']
            game.production()
            self.assertEqual(country.produced['machine']-before,2)
            self.assertEqual(game.operation_inputs[('Mechania','production','ore')],total)
            self.assertEqual(game.material_credit[('Mechania','ore',2)],carry)
            self.assertEqual(country.cash,cash)
            game.verify()

    def test_old_generation_carry_cannot_fund_new_generation(self):
        game,country=self.gen2_case('baseline')
        self.assertEqual(game.material_credit[('Mechania','ore',2)],1)
        country.levels['machine']=3;country.machine_tech=3;game.r=2
        plan=game.material_plan(country,2,quantity=1)
        self.assertEqual((plan['credits_before'],plan['raw_spent']),(0,1))
        game.production()
        row=[e for e in game.machine_output_log if e['round']==2 and e['country']=='Mechania'][0]
        self.assertEqual((row['status'],row['generation'],row['produced']),('fallback',1,1))
        self.assertEqual(game.material_credit[('Mechania','ore',2)],1)
        game.verify()

    def test_raw_carry_does_not_cross_alternating_input_types(self):
        game=Game(52112,'baseline');game.r=1;country=game.cs['Technia']
        country.levels['machine']=2;country.machine_tech=2
        game.mint(country,'ore',1,initial=True);game.production()
        self.assertEqual(game.material_credit[('Technia','ore',2)],1)
        plan=game.material_plan(country,2,quantity=1)
        self.assertEqual((plan['raw'],plan['credits_before'],plan['raw_spent']),('fuel',0,1))
        game.verify()

    def test_material_carry_stays_with_country_after_product_sale(self):
        game,country=self.gen2_case('baseline')
        self.transfer(game,'Mechania','Novia',game.ids(country,'machine',min_gen=2),10,'fixture:credit-product-sale')
        buyer=game.cs['Novia'];buyer.levels['machine']=2;buyer.bases['machine']=1;buyer.machine_tech=2
        plan=game.material_plan(buyer,3,quantity=1)
        self.assertEqual(plan['credits_before'],0)
        self.assertEqual(plan['raw_spent'],1)
        self.assertEqual(game.material_credit[('Mechania','ore',2)],1)
        game.verify()

    def test_pause_does_not_spend_carry_or_create_free_g1(self):
        for variant in ('baseline','recipe'):
            game,country=self.gen2_case(variant);game.r=2
            before=(country.produced.copy(),game.material_credit.copy(),len(game.raw_use_log))
            game.production()
            row=[e for e in game.machine_output_log if e['round']==2 and e['country']=='Mechania'][0]
            self.assertEqual((row['status'],row['produced'],row['raw_used']),('paused',0,{}))
            self.assertEqual(country.produced['machine'],before[0]['machine'])
            self.assertEqual(game.material_credit[('Mechania','ore',2)],before[1][('Mechania','ore',2)])
            self.assertFalse(any(e['round']==2 and e['country']=='Mechania' for e in game.raw_use_log))
            game.verify()

    def test_first_new_grade_needs_paid_material_even_with_large_old_inventory(self):
        for variant,required in (('starter',1),('coupled',2)):
            game=Game(52113,variant);game.r=1;country=game.cs['Mechania']
            country.levels['machine']=3;country.machine_tech=3
            game.mint(country,'machine',40,gen=1,initial=True)
            game.mint(country,'ore',required,initial=True)
            game.production()
            self.assertEqual(game.count(country,'machine',min_gen=3),1)
            self.assertEqual(game.operation_inputs[('Mechania','production','ore')],required)
            self.assertEqual(game.material_credit[('Mechania','ore',3)],0)
            game.verify()

    def test_listed_raw_cannot_be_used_as_free_production_material(self):
        game=Game(52114,'recipe');game.r=1;country=game.cs['Mechania']
        country.levels['machine']=2;country.machine_tech=2
        raw=game.ids(country,'ore');game.make_order(country,raw,20)
        game.production()
        self.assertEqual(country.production_failures,1)
        self.assertEqual(game.count(country,'machine',min_gen=2),0)
        self.assertTrue(all(game.units[i].owner=='Mechania' and game.units[i].order is not None for i in raw))
        self.assertFalse(any(e['country']=='Mechania' for e in game.raw_use_log))
        game.verify()

    def test_current_round_ore_is_not_available_to_earlier_or_later_same_round_factory(self):
        for raw_first in (False,True):
            game=Game(52115,'strict_no_starter');game.r=1;country=game.cs['Mechania']
            country.bases['ore']=1;country.machine_tech=2
            country.levels={'ore':1,'machine':2,'wheat':1} if raw_first else {'machine':2,'wheat':1,'ore':1}
            game.production()
            self.assertEqual(game.count(country,'ore'),1)
            self.assertEqual(game.count(country,'machine',min_gen=2),0)
            self.assertEqual(country.production_failures,1)
            self.assertFalse(any(e['country']=='Mechania' for e in game.raw_use_log))
            game.verify()

    def test_forecasts_do_not_spend_goods_credits_or_make_future_output(self):
        for variant in RAW_MODES:
            game=Game(52116,variant);game.r=1;game.production()
            for country in game.cs.values():
                before=self.state(game)
                first=(game.next_resources(country),game.projected_resources(country,'machine'))
                for _ in range(3):self.assertEqual(first,(game.next_resources(country),game.projected_resources(country,'machine')))
                self.assertEqual(before,self.state(game))
            game.verify()

    def test_actual_focus_cannot_exceed_reserved_machine_materials(self):
        for variant in RAW_MODES:
            game=Game(52117,variant);country=game.cs['Mechania'];game.r=2
            country.levels['machine']=3;country.machine_tech=3
            forecast=game.material_plan(country,3)
            for focus in country.levels:
                country.focus=focus
                actual=game.material_plan(country,3,game.machine_quantity(country,3,actual=True))
                self.assertLessEqual(actual['quantity'],forecast['quantity'])
                self.assertLessEqual(actual['raw_spent'],forecast['raw_spent'])

    def test_research_materials_cannot_also_fund_next_production(self):
        for variant,missing in (('baseline',1),('recipe',2)):
            game,country=self.research_case(variant,ore=2)
            before=(country.cash,country.levels.copy(),country.stock.copy(),len(game.raw_use_log))
            self.assertFalse(game.invest(country,'fixture:unfunded'))
            self.assertEqual(before,(country.cash,country.levels,country.stock,len(game.raw_use_log)))
            self.assertEqual(game.funding_blocks[-1]['missing_after_development'],{'ore':missing})
            game.verify()

    def test_funded_development_leaves_separate_inputs_for_actual_new_grade(self):
        for variant,post in (('baseline',1),('recipe',2)):
            game,country=self.research_case(variant,ore=2+post)
            self.assertTrue(game.invest(country,'fixture:funded'))
            self.assertEqual(game.count(country,'ore'),post)
            research={e['uid'] for e in game.raw_use_log if e['country']=='Mechania' and e['purpose']=='development'}
            self.assertEqual(len(research),2)
            before=self.state(game);self.assertTrue(game.invest(country,'fixture:funded'))
            self.assertEqual(before,self.state(game))
            game.r=3;game.production()
            produced={e['uid'] for e in game.raw_use_log if e['country']=='Mechania' and e['purpose']=='production'}
            self.assertEqual(len(produced),post)
            self.assertFalse(research&produced)
            self.assertEqual(game.count(country,'machine',min_gen=3),1)
            game.verify()

    def test_all_raw_source_classes_are_logged_without_inventing_cash(self):
        game=Game(52118,'baseline');game.r=1;country=game.cs['Mechania']
        self.transfer(game,'Technia','Mechania',game.ids(game.cs['Technia'],'ore'),10,'fixture:initial-foreign')
        game.mint(country,'ore',1)
        other=game.cs['Mineria'];game.mint(other,'ore',1)
        self.transfer(game,'Mineria','Mechania',game.ids(other,'ore'),10,'fixture:produced-foreign')
        cash=country.cash;game.consume(country,'ore',4,'production')
        counts=game._raw_counts('Mechania','ore')
        self.assertEqual({k:counts[k] for k in SOURCE_KINDS},{k:1 for k in SOURCE_KINDS})
        self.assertEqual((counts['consumed'],counts['production'],counts['research'],counts['imported_used']),(4,4,0,2))
        self.assertEqual(country.cash,cash)
        game.verify()

    def test_own_returned_raw_is_own_origin_and_a_recorded_import(self):
        game=Game(52119,'baseline');game.r=1;country=game.cs['Mechania']
        uid=game.ids(country,'ore')[0]
        self.transfer(game,'Mechania','Tropia',[uid],10,'fixture:out')
        self.transfer(game,'Tropia','Mechania',[uid],10,'fixture:return')
        game.consume(country,'ore',1,'production')
        counts=game._raw_counts('Mechania','ore')
        self.assertEqual(counts['initial_own'],1)
        self.assertEqual(counts['initial_foreign'],0)
        self.assertEqual(counts['imported_used'],1)
        game.verify()

    def test_cash_channels_refuse_only_selected_imports_atomically(self):
        for style,blocked in REFUSAL_STYLES.items():
            for good in blocked:
                for channel in ('market','direct'):
                    game=Game(52120,'starter',focal='Mechania',style=style);game.r=1
                    seller=game.cs['Mineria'];game.mint(seller,good,1,initial=True)
                    ids=game.ids(seller,good)
                    if channel=='market':game.make_order(seller,ids,20)
                    before=self.state(game)
                    self.assertFalse(game.settle_transaction([{'seller':'Mineria','buyer':'Mechania','ids':ids}],
                        ('Mechania','Mineria',20),channel,'fixture:blocked'))
                    self.assertEqual(before,self.state(game))
                    game.verify()

    def test_barter_refusal_does_not_partially_transfer_the_other_leg(self):
        for style,blocked in REFUSAL_STYLES.items():
            for good in blocked:
                game=Game(52121,'starter',focal='Mechania',style=style);game.r=1
                seller=game.cs['Mineria'];actor=game.cs['Mechania'];game.mint(seller,good,1,initial=True)
                before=self.state(game)
                self.assertFalse(game.settle_transaction([
                    {'seller':'Mineria','buyer':'Mechania','ids':game.ids(seller,good)},
                    {'seller':'Mechania','buyer':'Mineria','ids':game.ids(actor,'wheat')[:1]}],
                    None,'barter','fixture:blocked-barter'))
                self.assertEqual(before,self.state(game))
                game.verify()

    def test_refusal_does_not_block_other_goods_other_countries_or_exports(self):
        for style,good in (('no_ore','fuel'),('no_fuel','ore')):
            game=Game(52122,'starter',focal='Mechania',style=style);game.r=1
            seller=game.cs['Mineria'];game.mint(seller,good,1,initial=True)
            self.transfer(game,'Mineria','Mechania',game.ids(seller,good),10,'fixture:allowed-raw')
            denied=REFUSAL_STYLES[style][0];game.mint(seller,denied,1,initial=True)
            self.transfer(game,'Mineria','Novia',game.ids(seller,denied),10,'fixture:other-country')
            actor=game.cs['Mechania'];game.mint(actor,denied,1,initial=True)
            self.transfer(game,'Mechania','Tropia',game.ids(actor,denied),10,'fixture:export-allowed')
            self.transfer(game,'Tropia','Mechania',game.ids(game.cs['Tropia'],'banana')[:1],10,'fixture:food-allowed')
            game.verify()

    def test_purchase_plan_excludes_refused_inputs_for_each_industrial_country(self):
        for name in ('Mechania','Technia','Novia'):
            for style,blocked in REFUSAL_STYLES.items():
                game=Game(52123,'no_starter',focal=name,style=style);game.r=1
                country=game.cs[name]
                rows=game.purchase_plan(country)
                self.assertFalse(any(row['good'] in blocked for row in rows))
                self.assertTrue(any(row['good'] not in RAW_GOODS for row in rows))
                game.verify()

    def test_raw_refusal_full_runs_keep_actual_imports_zero_not_initial_raw_zero(self):
        for name in ('Mechania','Technia','Novia'):
            for style,blocked in REFUSAL_STYLES.items():
                game=Game(52124,'baseline',focal=name,style=style);result=game.run()
                country=result['countries'][name]
                for good in blocked:
                    self.assertEqual(country['import_goods'].get(good,0),0)
                    self.assertEqual(country['purchase_by_good'][good],0)
                    self.assertEqual(country['raw_use'][good]['imported_used'],0)
                    self.assertEqual(country['first_raw_import_round'][good],10)
                    self.assertEqual(country['raw_importing'][good],0)
                self.assertEqual(country['starter_raw'],{'ore':1,'fuel':1})

    def test_all_modes_raw_ledgers_sources_credit_chain_and_first_two_metrics_reconcile(self):
        from run_raw_validation import normalize_and_validate, validate_raw_ledger
        for variant,policy in RAW_MODES.items():
            game=Game(52125,variant);result=game.run()
            normalized=normalize_and_validate(copy.deepcopy(result))
            validate_raw_ledger(game,normalized)
            self.assertEqual(len(game.raw_round_ledger),81)
            self.assertEqual(len({(r['country'],r['round']) for r in game.raw_round_ledger}),81)
            balances={(name,good):game.starter_allocation[name][good] for name in game.cs for good in RAW_GOODS}
            for row in game.raw_round_ledger:
                name,r=row['country'],row['round']
                for good,x in row['goods'].items():
                    self.assertEqual(x['opening_stock'],balances[(name,good)])
                    made=sum(u.origin==name and u.good==good and u.born==r for u in game.units.values())
                    self.assertEqual(x['produced'],made)
                    balances[(name,good)]+=made+x['imports']-x['exports']-x['consumed']
                    self.assertEqual(balances[(name,good)],x['stock'])
                    self.assertEqual(x['consumed'],x['production']+x['research'])
                    self.assertEqual(x['consumed'],sum(x[k] for k in SOURCE_KINDS))
                    self.assertEqual(set(x['machine_credits_by_grade']),{'1','2','3'})
                    self.assertTrue(all(0<=v<policy.machine_credits for v in x['machine_credits_by_grade'].values()))
            credit=Counter()
            for event in game.material_events:
                key=tuple(event['key'])
                self.assertEqual(credit[key],event['credits_before'])
                credit[key]+=policy.machine_credits*event['raw_spent']-event['credits_spent']
                self.assertEqual(credit[key],event['credits_after'])
            self.assertEqual(credit,game.material_credit)
            for name,country in game.cs.items():
                x=result['countries'][name];rows=[r for r in game.raw_round_ledger if r['country']==name]
                self.assertEqual(x['first_two_happy'],sum(r['happy'] for r in rows[:2])/2)
                self.assertEqual(x['first_two_food_short'],sum(not r['food_met'] for r in rows[:2]))
                self.assertEqual(x['first_two_production_failures'],sum(r['production_failures'] for r in rows[:2]))
                self.assertEqual(x['first_round_happy'],rows[0]['happy'])
                self.assertEqual(x['start_asset_value'],game.initial_assets[name])
                self.assertEqual(x['end_asset_value'],x['cash_plus_stock_value']+.45*x['investment'])
                for good in RAW_GOODS:
                    u=x['raw_use'][good]
                    self.assertEqual(u['consumed'],sum(r['goods'][good]['consumed'] for r in rows))
                    self.assertEqual(u['production'],x['production_raw'][good])
                    self.assertEqual(u['research'],x['research_raw'][good])
                    self.assertEqual(sum(r['goods'][good]['imports'] for r in rows),x['import_goods'].get(good,0))
                    self.assertEqual(sum(r['goods'][good]['purchases'] for r in rows),x['purchase_by_good'][good])
            self.assertEqual(result['world']['protected_offer_violations'],0)
            self.assertEqual(result['world']['offer_price_mismatches'],0)
            self.assertEqual(result['world']['uncovered_investments'],0)

    def test_parameter_aware_verification_rejects_invalid_carry(self):
        game=Game(52126,'recipe');key=('Mechania','ore',2)
        game.material_credit[key]=1
        with self.assertRaises(AssertionError):game.verify()
        game.material_credit[key]=0;game.verify()

    def test_parameter_aware_verification_still_enforces_money_conservation(self):
        game=Game(52127,'recipe');country=game.cs['Mechania'];country.cash+=1
        with self.assertRaises(AssertionError):game.verify()
        country.cash-=1;game.verify()

    def test_round_nine_reserves_no_next_cycle_and_does_not_liquidate_carry(self):
        game,country=self.gen2_case('baseline');game.r=9
        before=self.state(game)
        self.assertEqual(game.next_resources(country),{})
        self.assertEqual(game.projected_resources(country,'machine'),{})
        self.assertEqual(game.material_credit[('Mechania','ore',2)],1)
        self.assertEqual(before,self.state(game))

    def test_production_and_completed_run_replay_do_not_duplicate_raw_records(self):
        game,country=self.gen2_case('recipe');before=self.state(game)
        self.assertFalse(game.production());self.assertEqual(before,self.state(game))
        completed=Game(52128,'coupled');result=completed.run();trace=copy.deepcopy(completed.trace())
        self.assertEqual(result,completed.run())
        self.assertEqual(trace,completed.trace())


if __name__=='__main__':
    unittest.main(verbosity=2)
