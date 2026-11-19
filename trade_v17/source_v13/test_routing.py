"""v10 route decisions and real investment/use boundaries.

The inherited 260 tests remain untouched. Fixtures mint physical goods and move
cash through valid transactions; hand-built prior observations are explicitly
limited to deterministic router-boundary tests, not formal game outcomes.
"""
from __future__ import annotations
import copy
import unittest

from routing_engine import Game, MODES
from development_engine import Game as V9
from reference_engine import GOODS


class RoutingTests(unittest.TestCase):
    def transfer(self,g,seller,buyer,ids,amount=10,action='fixture:transfer'):
        self.assertTrue(g.settle_transaction([{'seller':seller,'buyer':buyer,'ids':list(ids)}],
                                            (buyer,seller,amount),'direct',action))

    def fund(self,g,name,target=800):
        c=g.cs[name]
        for donor in g.cs.values():
            if donor.name==name or c.cash>=target:continue
            amount=min(donor.cash,target-c.cash)
            if amount:
                g.mint(c,'wheat',1,initial=True)
                self.transfer(g,name,donor.name,[g.uid],amount,f'fixture:fund:{name}:{donor.name}:{len(g.transactions)}')
        self.assertGreaterEqual(c.cash,target)

    def case(self,variant='quick',name='Technia',round_number=4,failures=None):
        g=Game(66101,variant);g.r=round_number;c=g.cs[name]
        c.levels['electronics']=2;c.elec_tech=2
        self.fund(g,name)
        for good,n in (('ore',8),('fuel',8),('banana',10),('wheat',10),('electronics',1)):
            g.mint(c,good,n,initial=True)
        # Explicit historical observations: failed attempts, no public high-grade offers.
        if failures is None:failures=list(range(max(1,round_number-2),round_number))
        for r in failures:
            g.development_attempt_log.append({'round':r,'country':name,'industry':'electronics',
                'required_machine_grade':2,'missing_machine':True,'cash':c.cash,
                'development_cost':g.upgrade_cost(c,'electronics'),'ore_required':2,
                'ore_held':g.count(c,'ore'),'note':'constructed own past observation'})
        return g,c

    def economy(self,g):
        return copy.deepcopy((g.cs,g.units,g.orders,g.transactions,g.material_credit,
            g.initial,g.created,g.destroyed,g.minted,g.sunk,g.raw_use_log,g.development_log,g.development_use_log))

    def machine(self,g,owner,grade=2,initial=False):
        g.mint(g.cs[owner],'machine',1,gen=grade,initial=initial)
        return g.uid

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):Game(66102,'unknown')

    def test_baseline_preserves_v9_combined_every_economic_field_and_record(self):
        for seed,focal,style in ((66103,None,'normal'),(66104,'Mechania','idle')):
            old=V9(seed,'combined',focal=focal,style=style)
            new=Game(seed,'baseline',focal=focal,style=style)
            expected=old.run();actual=new.run()
            for n,x in expected['countries'].items():
                for k,v in x.items():self.assertEqual(v,actual['countries'][n][k],(n,k))
            for k,v in expected['world'].items():self.assertEqual(v,actual['world'][k],k)
            for k in ('transactions','cash_ledger','raw_round_ledger','price_history','units',
                      'production_trace','development_log','development_output_log','development_use_log'):
                self.assertEqual(getattr(old,k),getattr(new,k),k)
            self.assertEqual(new.route_records,[])

    def test_modes_keep_initial_cash_permissions_recipes_costs_and_scores(self):
        old=V9(66105,'combined')
        for mode in MODES:
            g=Game(66105,mode)
            for attr in ('initial_cash','initial_assets','initial_capacity','config','opt','prices','starter_allocation'):
                self.assertEqual(getattr(g,attr),getattr(old,attr),(mode,attr))
            for n,c in g.cs.items():
                original=old.cs[n]
                self.assertEqual(c.expand,original.expand)
                self.assertEqual(c.levels,original.levels)
                for good in c.levels:
                    self.assertEqual(g.upgrade_cost(c,good),old.upgrade_cost(original,good))
                    self.assertEqual(g.upgrade_requirements(c,good),old.upgrade_requirements(original,good))
                    self.assertEqual(g.resource_requirements(c,good,2),old.resource_requirements(original,good,2))
            g.verify()

    def test_helper_is_pure_including_decision_and_goal_state(self):
        for mode in ('quick','patient'):
            g,c=self.case(mode)
            before=copy.deepcopy((self.economy(g),g.routing_log,g.routing_seen,g.route_records,
                g.active_routes,g.route_actions,g.plan_cache,g.development_attempt_log,g.offer_history))
            advice=g.routing_advice(c,'electronics')
            for _ in range(5):self.assertEqual(advice,g.routing_advice(c,'electronics'))
            self.assertEqual(before,(self.economy(g),g.routing_log,g.routing_seen,g.route_records,
                g.active_routes,g.route_actions,g.plan_cache,g.development_attempt_log,g.offer_history))

    def test_new_helper_ignores_rival_hidden_cash_stock_technology_and_style(self):
        g,c=self.case();before=g.routing_advice(c,'electronics')
        other=copy.deepcopy(g)
        for n,z in other.cs.items():
            if n==c.name:continue
            z.cash+=999;z.style='idle';z.machine_tech=3;z.elec_tech=3
            z.levels['machine']=3
            other.mint(z,'machine',3,gen=3,initial=True)
        # No offer was created, so these private changes must not change advice.
        self.assertEqual(before,other.routing_advice(other.cs[c.name],'electronics'))

    def test_quick_and_patient_require_completed_rounds_not_query_count(self):
        for mode,expected in (('quick','machine'),('patient','electronics')):
            g,c=self.case(mode,failures=[3])
            for _ in range(8):self.assertEqual(g.routing_advice(c,'electronics')['selected'],expected)
            self.assertEqual(len(g.development_attempt_log),1)
        g,c=self.case('patient',failures=[2,3])
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'machine')

    def test_failed_rounds_must_be_consecutive_for_same_own_goal(self):
        for failures in ([1,3],[1,2],[2]):
            g,c=self.case('patient',failures=failures)
            self.assertEqual(g.routing_advice(c,'electronics')['selected'],'electronics')
        g,c=self.case('patient',failures=[2,3])
        g.development_attempt_log[-1]['country']='Novia'
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'electronics')
        g.development_attempt_log[-1]['country']=c.name
        g.development_attempt_log[-1]['industry']='machine'
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'electronics')

    def test_old_or_g1_public_supply_does_not_create_false_current_supply(self):
        g,c=self.case('patient')
        uid=self.machine(g,'Mechania',1)
        g.offer_history.append({'round':3,'country':'Mechania','good':'machine','generation':1,'ids':[uid]})
        high=self.machine(g,'Mechania',2)
        g.offer_history.append({'round':1,'country':'Mechania','good':'machine','generation':2,'ids':[high]})
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'machine')

    def test_recent_public_high_supply_delays_start_even_when_offer_was_bought(self):
        g,c=self.case('patient');uid=self.machine(g,'Mechania',2)
        g.offer_history.append({'round':3,'country':'Mechania','good':'machine','generation':2,'ids':[uid]})
        row=g.routing_advice(c,'electronics')
        self.assertEqual(row['selected'],'electronics');self.assertEqual(row['reason'],'recent_public_supply')

    def test_current_qualified_public_offer_resumes_original_goal(self):
        for grade in (2,3):
            g,c=self.case();uid=self.machine(g,'Mechania',grade)
            oid=g.make_order(g.cs['Mechania'],[uid],70)
            row=g.routing_advice(c,'electronics')
            self.assertEqual(row['selected'],'electronics');self.assertEqual(row['reason'],'public_supply_present')
            self.assertEqual(row['public_offer_ids'],[oid])
            self.assertEqual(row['public_offer_prices'],[70])

    def test_expensive_public_offer_is_explicit_supply_not_supply_absence(self):
        g,c=self.case();uid=self.machine(g,'Mechania',2)
        g.make_order(g.cs['Mechania'],[uid],100000)
        row=g.routing_advice(c,'electronics')
        self.assertEqual(row['reason'],'public_supply_present')
        self.assertEqual(row['selected'],'electronics')
        self.assertGreater(row['public_offer_prices'][0],c.cash)

    def test_own_and_foreign_qualified_equipment_both_resume_goal(self):
        for origin,listed in (('Technia',False),('Mechania',False),('Mechania',True)):
            g,c=self.case();uid=self.machine(g,origin,2)
            if origin!=c.name:self.transfer(g,origin,c.name,[uid],10,'fixture:own-or-import')
            if listed:g.make_order(c,[uid],70)
            row=g.routing_advice(c,'electronics')
            self.assertEqual(row['selected'],'electronics');self.assertEqual(row['reason'],'owned_machine_ready')
            self.assertIn(uid,row['own_qualified_machine_ids'])

    def test_router_adds_no_new_factory_expansion_permission(self):
        g=Game(66106,'quick');g.r=4;c=g.cs['Tropia'];c.levels['banana']=3
        g.development_attempt_log.append({'round':3,'country':c.name,'industry':'banana',
            'missing_machine':True,'required_machine_grade':2})
        row=g.routing_advice(c,'banana')
        self.assertFalse(row['legal_machine_path'])
        self.assertEqual(row['selected'],'banana');self.assertEqual(row['reason'],'no_legal_machine_path')

    def test_existing_expansion_waits_until_round_three(self):
        g,c=self.case(name='Novia',round_number=2,failures=[1])
        self.assertFalse(g.routing_advice(c,'electronics')['legal_machine_path'])
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'electronics')
        g.r=3;g.development_attempt_log[-1]['round']=2
        self.assertTrue(g.routing_advice(c,'electronics')['legal_machine_path'])
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'machine')

    def test_horizon_counts_machine_steps_and_original_goal_deadline(self):
        for name,last in (('Technia',6),('Novia',5)):
            for r,expected in ((last,'machine'),(last+1,'electronics')):
                g,c=self.case(name=name,round_number=r)
                row=g.routing_advice(c,'electronics')
                self.assertEqual(row['selected'],expected,(name,r,row))
                self.assertEqual(row['earliest_goal_round'],r+(1 if name=='Technia' else 2))
                if r>last:self.assertEqual(row['reason'],'too_late_for_self_production')

    def test_existing_lv2_without_physical_machine_waits_instead_of_new_upgrade(self):
        g,c=self.case();c.levels['machine']=2;c.machine_tech=2
        row=g.routing_advice(c,'electronics')
        self.assertIsNone(row['selected']);self.assertEqual(row['reason'],'await_actual_machine')
        self.assertEqual(row['remaining_machine_steps'],0)
        self.assertEqual(row['earliest_goal_round'],5)

    def test_machine_goal_cannot_route_cyclically_into_level_three(self):
        g,c=self.case();c.levels['machine']=2;c.machine_tech=2
        row=g.routing_advice(c,'machine',active=True)
        self.assertEqual(row['reason'],'await_actual_machine');self.assertIsNone(row['selected'])

    def test_idle_trade_and_final_rounds_disable_router_investments(self):
        for style in ('idle','trade'):
            g,c=self.case();c.style=style
            self.assertIsNone(g.routing_advice(c,'electronics')['selected'])
        for r in (8,9):
            g,c=self.case(round_number=r)
            self.assertIsNone(g.routing_advice(c,'electronics')['selected'])

    def test_plan_records_one_decision_and_route_per_country_round(self):
        g,c=self.case();before=self.economy(g)
        self.assertEqual(g.plan(c),'machine')
        for _ in range(8):
            self.assertEqual(g.plan(c),'machine')
            g.targets(c);g.purchase_plan(c)
        self.assertEqual(before,self.economy(g))
        self.assertEqual(len(g.routing_log),1);self.assertEqual(len(g.route_records),1)
        self.assertEqual(g.route_records[0]['goal'],'electronics')
        self.assertEqual(g.route_records[0]['target_level'],3)
        g.verify()

    def test_goal_persists_through_actual_intermediate_then_original_development(self):
        g,c=self.case();self.assertEqual(g.plan(c),'machine');g.settle_round(c)
        self.assertTrue(g.invest(c,'fixture:intermediate'))
        self.assertEqual(c.levels['machine'],2)
        self.assertEqual(g.route_records[0]['status'],'active')
        self.assertEqual(c.levels['electronics'],2)
        g.r=5;g.production();g.settle_round(c)
        self.assertEqual(g.plan(c),'electronics')
        self.assertTrue(g.invest(c,'fixture:goal'))
        route=g.route_records[0]
        self.assertEqual(route['status'],'completed');self.assertEqual(route['end_round'],5)
        self.assertNotIn(c.name,g.active_routes)
        self.assertEqual(c.levels['machine'],2);self.assertEqual(c.elec_tech,3)
        self.assertEqual(len(route['intermediate_event_ids']),1)
        event=g.development_log[route['goal_event_id']]
        self.assertEqual(event['machine']['origin'],c.name)
        g.r=6;g.production();g.settle_round(c)
        chain=g.development_chains()[route['goal_event_id']]
        self.assertTrue(chain['used_output_ids'])
        g.verify()

    def test_novia_existing_expansion_takes_two_steps_then_resumes_same_goal(self):
        g,c=self.case(name='Novia',round_number=3)
        for r,expected in ((3,1),(4,2)):
            g.r=r
            if r>3:g.production()
            g.settle_round(c);self.assertEqual(g.plan(c),'machine')
            self.assertTrue(g.invest(c,f'fixture:novia-step:{r}'))
            self.assertEqual(c.levels['machine'],expected)
            self.assertEqual(g.route_records[0]['goal'],'electronics')
        g.r=5;g.production();g.settle_round(c)
        self.assertEqual(g.plan(c),'electronics')
        self.assertTrue(g.invest(c,'fixture:novia-goal'))
        route=g.route_records[0]
        self.assertEqual(route['status'],'completed')
        self.assertEqual([g.development_log[i]['to_level'] for i in route['intermediate_event_ids']],[1,2])
        g.verify()

    def test_intermediate_investment_preserves_living_and_input_guards(self):
        for shortage in ('electronics','ore'):
            g,c=self.case();self.assertEqual(g.plan(c),'machine')
            if shortage=='electronics':
                self.transfer(g,c.name,'Ferria',g.ids(c,'electronics'),1,'fixture:no-living')
            else:
                self.transfer(g,c.name,'Ferria',g.ids(c,'ore'),1,'fixture:no-input')
            g.settle_round(c);before=(c.cash,c.investment,dict(c.levels),g.sunk)
            self.assertFalse(g.invest(c,'fixture:guarded'))
            self.assertEqual(before,(c.cash,c.investment,c.levels,g.sunk))
            self.assertEqual(g.route_records[0]['intermediate_event_ids'],[])
            g.verify()

    def test_intermediate_cannot_borrow_or_overdraw_cash(self):
        g,c=self.case();self.assertEqual(g.plan(c),'machine')
        seller=g.cs['Ferria'];g.mint(seller,'wheat',1,initial=True)
        self.transfer(g,seller.name,c.name,[g.uid],c.cash-5,'fixture:spend-cash')
        g.settle_round(c);before=(c.cash,c.investment,dict(c.levels))
        self.assertFalse(g.invest(c,'fixture:cash-guard'))
        self.assertEqual(before,(c.cash,c.investment,c.levels))
        self.assertGreaterEqual(c.cash,0);g.verify()

    def test_public_supply_return_interrupts_self_route_without_forcing_extra_steps(self):
        g,c=self.case();self.assertEqual(g.plan(c),'machine')
        g.r=5;uid=self.machine(g,'Mechania',2)
        g.make_order(g.cs['Mechania'],[uid],60)
        self.assertEqual(g.plan(c),'electronics')
        self.assertEqual(g.routing_log[-1]['reason'],'public_supply_present')
        self.assertEqual(g.route_records[0]['intermediate_event_ids'],[])
        self.assertEqual(g.route_records[0]['goal'],'electronics')

    def test_midround_acquisition_cancels_redundant_spend_and_replay(self):
        g,c=self.case();self.assertEqual(g.plan(c),'machine')
        uid=self.machine(g,'Mechania',2)
        self.transfer(g,'Mechania',c.name,[uid],10,'fixture:newly-arrived')
        g.settle_round(c);before=(c.cash,c.investment,dict(c.levels),g.sunk)
        self.assertFalse(g.invest(c,'fixture:cancel'))
        self.assertFalse(g.invest(c,'fixture:cancel'))
        self.assertFalse(g.invest(c,'fixture:cancel-again'))
        self.assertEqual(before,(c.cash,c.investment,c.levels,g.sunk))
        self.assertEqual(len(g.route_actions),1)
        self.assertEqual(g.route_actions[0]['status'],'redundant_cancelled')
        self.assertEqual(g.plan(c),'machine')
        g.r=5;g.production();self.assertEqual(g.plan(c),'electronics')
        g.settle_round(c);self.assertTrue(g.invest(c,'fixture:resume-next'))
        self.assertEqual(g.route_records[0]['status'],'completed')
        self.assertEqual(g.route_records[0]['intermediate_event_ids'],[])
        g.verify()

    def test_successful_intermediate_and_goal_commands_are_idempotent(self):
        g,c=self.case();g.plan(c);g.settle_round(c)
        self.assertTrue(g.invest(c,'fixture:once'))
        before=copy.deepcopy((self.economy(g),g.route_records,g.route_actions,g.routing_log))
        self.assertTrue(g.invest(c,'fixture:once'))
        self.assertFalse(g.invest(c,'fixture:other'))
        self.assertEqual(before,(self.economy(g),g.route_records,g.route_actions,g.routing_log))
        g.verify()

    def test_invalid_action_ids_do_not_create_route_or_change_state(self):
        g,c=self.case();before=copy.deepcopy((self.economy(g),g.routing_log,g.route_records,g.active_routes))
        for action in ('',0,False,[],{}):
            self.assertFalse(g.invest(c,action))
            self.assertEqual(before,(self.economy(g),g.routing_log,g.route_records,g.active_routes))

    def test_final_state_routes_and_real_g3_outcomes_are_reproducible(self):
        for mode in ('quick','patient'):
            g=Game(66107,mode,focal='Mechania',style='idle');result=g.run()
            self.assertEqual(result,Game(66107,mode,focal='Mechania',style='idle').run())
            self.assertFalse(g.active_routes)
            for name,x in result['countries'].items():
                r=x['routing']
                self.assertEqual(r['routes_started'],r['routes_completed']+r['routes_unfinished'])
                self.assertLessEqual(r['routes_with_used_goal_output'],r['routes_completed'])
                self.assertLessEqual(r['g3_electronics_used'],r['g3_electronics_produced'])
                if name in ('Novia','Agrea','Ferria'):self.assertIsNone(x['score'])
            self.assertEqual(result,g.run())

    def test_no_high_or_no_raw_preferences_are_not_bypassed_by_routes(self):
        for mode in ('quick','patient'):
            for name,style in (('Technia','no_high_machine'),('Novia','no_raw')):
                g=Game(66108,mode,focal=name,style=style);result=g.run();actor=result['countries'][name]
                if style=='no_high_machine':self.assertEqual(actor['development']['bought_high_machines'],0)
                else:
                    self.assertEqual(actor['import_goods'].get('ore',0),0)
                    self.assertEqual(actor['import_goods'].get('fuel',0),0)
                self.assertEqual(result['world']['uncovered_investments'],0)
                g.verify()

    def test_idle_and_no_trade_still_preserve_original_meanings(self):
        for mode in ('quick','patient'):
            g=Game(66109,mode,focal='Technia',style='idle');r=g.run()['countries']['Technia']
            self.assertEqual((r['imports'],r['exports'],r['investment']),(0,0,0))
            self.assertEqual(r['routing']['routes_started'],0)
            self.assertGreater(r['tax'],0)
            no_trade=Game(66110,mode,trade_enabled=False);r=no_trade.run()
            self.assertEqual(r['world']['transactions'],0)
            self.assertGreater(sum(r['world']['production'].values()),0)


    def test_market_first_wait_depends_only_on_own_existing_machine_industry(self):
        g,c=self.case('market_first',name='Technia',failures=[2,3])
        row=g.routing_advice(c,'electronics')
        self.assertEqual(row['effective_wait_rounds'],2);self.assertEqual(row['selected'],'machine')
        g,c=self.case('market_first',name='Novia',failures=[2,3])
        row=g.routing_advice(c,'electronics')
        self.assertEqual(row['effective_wait_rounds'],3);self.assertEqual(row['selected'],'electronics')
        g.development_attempt_log.append({'round':1,'country':c.name,'industry':'electronics',
            'missing_machine':True,'required_machine_grade':2})
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'machine')

    def test_market_first_grace_uses_current_public_machine_launch_only(self):
        g,c=self.case('market_first')
        event={'round':g.r,'good':'machine','generation':2}
        g.launch_events.append(event)
        row=g.routing_advice(c,'electronics')
        self.assertEqual(row['reason'],'new_generation_market_chance')
        self.assertEqual(row['selected'],'electronics')
        self.assertEqual(row['public_generation_launches'],[event])
        g.launch_events[0]={'round':g.r-1,'good':'machine','generation':2}
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'machine')
        g.launch_events[0]={'round':g.r,'good':'electronics','generation':3}
        self.assertEqual(g.routing_advice(c,'electronics')['selected'],'machine')

    def test_unlisted_new_machine_is_not_a_public_launch_announcement(self):
        g,c=self.case('market_first');before=g.routing_advice(c,'electronics')
        self.machine(g,'Mechania',3)
        self.assertEqual(g.routing_advice(c,'electronics'),before)
        self.assertEqual(g.launch_events,[])

    def test_supplier_focus_uses_legal_industry_within_reserved_output_and_raw(self):
        g,c=self.case('market_first')
        self.assertEqual(g.plan(c),'machine')
        predicted=dict(g.projected_resources(c,'machine'))
        g.settle_round(c);self.assertTrue(g.invest(c,'fixture:supplier-step'))
        cash=c.cash;investment=c.investment;before_levels=dict(c.levels)
        g.choose_focus(c)
        self.assertEqual(c.focus,'wheat')
        self.assertEqual((c.cash,c.investment,c.levels),(cash,investment,before_levels))
        self.assertEqual(len(g.route_focus_log),1)
        row=g.route_focus_log[0]
        self.assertLessEqual(row['actual_focus_quantity'],row['forecast_quantity'])
        needed=g.resource_requirements(c,'machine',5)
        for raw,n in needed.items():self.assertLessEqual(n,predicted.get(raw,0))
        g.r=5;failures=c.production_failures;g.production()
        self.assertEqual(c.production_failures,failures)
        self.assertEqual(g.count(c,'machine',min_gen=2),2)
        g.prepare_orders(c)
        offered=[i for o in g.orders.values() if o.seller==c.name and o.good=='machine' and o.gen==2 for i in o.units]
        self.assertEqual(len(offered),1)
        g.verify()

    def test_supplier_focus_queries_do_not_count_same_launch_cycle_twice(self):
        g,c=self.case('market_first');g.plan(c);g.settle_round(c)
        self.assertTrue(g.invest(c,'fixture:focus-once'))
        g.choose_focus(c);after=self.economy(g);observations=copy.deepcopy(g.route_focus_log)
        g.choose_focus(c)
        self.assertEqual(after,self.economy(g))
        self.assertEqual(observations,g.route_focus_log)
        g.verify()

    def test_supplier_focus_is_limited_to_actual_lv2_intermediate_launch_cycle(self):
        g,c=self.case('market_first')
        g.choose_focus(c);self.assertFalse(g.route_focus_log)
        g.plan(c);g.settle_round(c);self.assertTrue(g.invest(c,'fixture:lv2'))
        g.choose_focus(c);self.assertEqual(len(g.route_focus_log),1)
        g.r=5;g.production();g.choose_focus(c)
        self.assertEqual(len(g.route_focus_log),1)
        g.verify()

    def test_supplier_focus_is_not_added_without_legal_support_industry(self):
        g,c=self.case('market_first');c.levels.pop('wheat')
        g.plan(c);g.settle_round(c);self.assertTrue(g.invest(c,'fixture:durable-only'))
        g.choose_focus(c)
        self.assertIn(c.focus,('machine','electronics'))
        self.assertFalse(g.route_focus_log)
        self.assertNotIn('wheat',c.levels)
        g.verify()

    def test_held_qualifying_machine_suppresses_unneeded_supplier_focus(self):
        g,c=self.case('market_first');g.plan(c);g.settle_round(c)
        self.assertTrue(g.invest(c,'fixture:before-arrival'))
        uid=self.machine(g,'Mechania',2)
        self.transfer(g,'Mechania',c.name,[uid],10,'fixture:late-equipment')
        g.choose_focus(c)
        self.assertFalse(g.route_focus_log)
        g.verify()


if __name__=='__main__':unittest.main(verbosity=2)
