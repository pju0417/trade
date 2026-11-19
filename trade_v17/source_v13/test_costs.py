"""Focused v3 regression tests. All numbers are game-design parameters."""
import unittest, copy, json, subprocess, sys
from pathlib import Path
from dataclasses import replace
from engine import Game,Options,NAMES,GOODS,PRICE,STORAGE,BONUS_RECIPE

BASE=Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True)
class CostTests(unittest.TestCase):
    def game(self,**kw):return Game(7,replace(BASE,**kw))
    def clear(self,g,c):
        for good in GOODS:
            ids=g.ids(c,good,False);g.remove_order_ids(ids)
            if ids:g.consume(c,good,len(ids),'test_setup')
    def old_stock(self,good,n=5,**kw):
        g=self.game(storage_fees=True,**kw);c=g.cs['Tropia'];c.style='idle';self.clear(g,c)
        g.r=1;g.mint(c,good,n);return g,c
    def test_price_1g_discount(self):
        g=self.game(price_tick=1)
        self.assertEqual([g.round_price(PRICE[h]*.9) for h in ('banana','machine','electronics')],[9,45,72])
    def test_5g_legacy_discount(self):
        g=self.game();self.assertEqual(g.round_price(10*.9),10)
    def test_sale_no_fee(self):
        g=self.game(price_tick=1);a,b=g.cs['Tropia'],g.cs['Grainia'];uid=g.ids(a,'banana')[0]
        before=(a.cash,b.cash);oid=g.make_order(a,[uid],9)
        self.assertEqual(g.market_buy(b,'banana',1,9),1)
        self.assertEqual((a.cash,b.cash),(before[0]+9,before[1]-9));g.verify()
    def test_1g_request_validation(self):
        g=self.game(price_tick=1);c=g.cs['Tropia']
        for v in (0,-1,True,1.5):
            with self.assertRaises(ValueError):g.make_order(c,g.ids(c,'banana'),v)
    def test_upgrade_cost_not_changed_by_tick(self):
        a=self.game(price_tick=5);b=self.game(price_tick=1)
        for n in NAMES:
            for h in a.cs[n].levels:self.assertEqual(a.upgrade_cost(a.cs[n],h),b.upgrade_cost(b.cs[n],h))
    def test_invalid_options(self):
        for kw in ({'price_tick':True},{'price_tick':2},{'storage_cap':-1},{'storage_cap':False}):
            with self.assertRaises(ValueError):Options(**kw)
    def test_price_update_never_reprices_order(self):
        g=self.game(price_tick=1);g.r=1;c=g.cs['Tropia'];o=g.make_order(c,g.ids(c,'banana'),9)
        g.demand_snapshot();g.update_prices();self.assertEqual(g.orders[o].price,9)
    def test_baseline_exact_reproduction(self):
        script='from engine import Game,Options;import json;print(json.dumps(Game(3000,Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True)).run()))'
        old=json.loads(subprocess.check_output([sys.executable,'-c',script],cwd=Path(__file__).parent/'baseline'))
        new=Game(3000,BASE).run()
        def compare(a,b):
            for k,v in a.items():
                if isinstance(v,dict):compare(v,b[k])
                else:self.assertEqual(v,b[k],k)
        compare(old,new)
    def test_raw_input_consumption_does_not_charge_cash_twice(self):
        g=self.game(bonus_inputs=True);g.r=1;c=g.cs['Tropia'];g.mint(c,'fuel',1)
        cash=c.cash;g.production();self.assertEqual(c.cash,cash);g.verify()
    def test_bonus_prepayment_carries_forward(self):
        g=self.game(bonus_inputs=True);c=g.cs['Tropia'];g.r=1;g.mint(c,'fuel',1)
        for r in (1,2,3):g.r=r;g.production();g.verify()
        self.assertEqual(g.bonus_raw[('Tropia','banana','fuel')],1)
        self.assertEqual(g.bonus_output[('Tropia','banana')],6)
        self.assertEqual(g.bonus_credit[('Tropia','banana')],0)
    def test_no_fuel_guarantees_farm_base(self):
        g=self.game(bonus_inputs=True);g.r=1;c=g.cs['Tropia'];g.production()
        self.assertEqual(c.produced['banana'],4);self.assertEqual(c.produced['wheat'],2)
    def test_advanced_output_requires_base_inputs(self):
        g=self.game(bonus_inputs=True);g.r=1;c=g.cs['Technia'];c.machine_tech=3;c.elec_tech=3
        for h in ('ore','fuel'):g.consume(c,h,g.count(c,h),'test_setup')
        g.production()
        self.assertEqual(c.produced['electronics'],1)
        self.assertEqual(g.units[g.ids(c,'electronics')[0]].gen,1)
    def test_machine_bonus_has_material_cost(self):
        g=self.game(bonus_inputs=True);g.r=1;c=g.cs['Mechania'];g.mint(c,'ore',1);g.production()
        self.assertEqual(c.produced['machine'],3)
        self.assertEqual(g.operation_inputs[('Mechania','production','ore')],1)
        self.assertEqual(g.operation_inputs[('Mechania','bonus_production','ore')],1);g.verify()
    def test_forecast_bonus_resources(self):
        g=self.game(bonus_inputs=True);c=g.cs['Tropia'];g.r=1
        self.assertEqual(g.next_resources(c)['fuel'],1)
    def test_forecast_is_pure(self):
        g=self.game(bonus_inputs=True);g.r=2;c=g.cs['Tropia'];g.mint(c,'machine',1)
        old=copy.deepcopy((g.bonus_credit,c.bonus_buffer,c.stock,c.cash))
        for _ in range(3):g.next_resources(c)
        self.assertEqual(old,(g.bonus_credit,c.bonus_buffer,c.stock,c.cash))
    def test_overstock_pauses_bonus_not_base(self):
        g=self.game(stock_discipline=True);g.r=1;c=g.cs['Tropia'];g.mint(c,'banana',50)
        before=c.produced['banana'];g.production();self.assertEqual(c.produced['banana']-before,4)
        self.assertGreater(g.skipped_bonus[('Tropia','banana')],0)
    def test_student_invest_style_not_forced_to_pause(self):
        g=self.game(stock_discipline=True);g.r=1;c=g.cs['Tropia'];c.style='invest';g.mint(c,'banana',50)
        before=c.produced['banana'];g.production();self.assertGreater(c.produced['banana']-before,4)
    def test_production_and_credit_idempotency(self):
        g=self.game(bonus_inputs=True);g.r=1;g.mint(g.cs['Tropia'],'fuel',1);g.production()
        old=(g.uid,dict(g.bonus_credit),len(g.cost_events));g.production();self.assertEqual(old,(g.uid,dict(g.bonus_credit),len(g.cost_events)))
    def test_banana_grace_two_settlements(self):
        g,c=self.old_stock('banana',5)
        for r in (1,2):g.r=r;self.assertEqual(g.storage_preview(c)['due'],0)
        g.r=3;self.assertEqual(g.storage_preview(c)['eligible']['banana'],4)
        self.assertEqual(g.storage_preview(c)['due'],2)
    def test_wheat_longer_grace(self):
        g,c=self.old_stock('wheat',10);g.r=3;self.assertEqual(g.storage_preview(c)['due'],0)
        g.r=4;self.assertGreater(g.storage_preview(c)['due'],0)
    def test_ore_longer_grace(self):
        g,c=self.old_stock('ore',10);g.r=4;self.assertEqual(g.storage_preview(c)['due'],0)
        g.r=5;self.assertEqual(g.storage_preview(c)['due'],2)
    def test_listing_cancel_does_not_reset_age(self):
        g,c=self.old_stock('banana',8);g.r=4
        before=g.storage_preview(c);o=g.make_order(c,g.ids(c,'banana'),10)
        self.assertEqual(before,g.storage_preview(c));g.remove_order_ids(g.orders[o].units.copy())
        self.assertEqual(before,g.storage_preview(c))
    def test_new_owner_grace_and_return_no_reset(self):
        g,c=self.old_stock('banana',8,price_tick=1);b=g.cs['Grainia'];g.r=4;uid=g.ids(c,'banana')[0]
        self.assertTrue(g.settle_transaction([{'seller':c.name,'buyer':b.name,'ids':[uid]}],(b.name,c.name,9),'direct','out'))
        self.assertEqual(g.residency[uid][b.name],4)
        self.assertTrue(g.settle_transaction([{'seller':b.name,'buyer':c.name,'ids':[uid]}],(c.name,b.name,9),'direct','back'))
        self.assertEqual(g.residency[uid][c.name],1)
    def test_rejected_transaction_leaves_age_unchanged(self):
        g,c=self.old_stock('banana',8);g.r=4;old=copy.deepcopy(g.residency)
        self.assertFalse(g.settle_transaction([{'seller':c.name,'buyer':'Grainia','ids':[9999]}],('Grainia',c.name,10),'market','bad'))
        self.assertEqual(old,g.residency)
    def test_used_machine_exempt(self):
        g,c=self.old_stock('machine',1);g.r=5;g.mark_use(c,g.ids(c,'machine')[0],'equipment')
        self.assertEqual(g.storage_preview(c)['due'],0)
    def test_unused_machine_is_not_permanently_exempt(self):
        g,c=self.old_stock('machine',8);g.r=5
        row=g.storage_preview(c);self.assertGreater(row['eligible'].get('machine',0),0)
    def test_active_living_goods_exempt(self):
        g,c=self.old_stock('electronics',2);g.r=5
        self.assertEqual(g.storage_preview(c)['due'],0)
    def test_ever_used_but_sold_goods_no_active_exemption(self):
        g,c=self.old_stock('electronics',8);g.r=1;uid=g.ids(c,'electronics')[0];g.mark_use(c,uid,'living')
        g.r=5;g.make_order(c,g.ids(c,'electronics'),80)
        self.assertIn(uid,g.storage_preview(c)['unit_ids'])
    def test_next_round_food_protected(self):
        g,c=self.old_stock('banana',5);g.r=7
        self.assertEqual(g.storage_preview(c)['eligible'].get('banana'),2) # next need = 3
    def test_price_changes_do_not_change_storage(self):
        g,c=self.old_stock('banana',20);g.r=4;old=g.storage_preview(c)
        g.prices['banana']=200;self.assertEqual(old,g.storage_preview(c))
    def test_storage_cap_and_no_debt(self):
        g,c=self.old_stock('ore',200);g.r=5;g.settle_round(c)
        self.assertEqual(g.storage_paid[c.name],5);self.assertGreater(g.storage_history[-1]['waived'],0);g.verify()
    def test_no_storage_double_charge(self):
        g,c=self.old_stock('ore',100);g.r=5;g.settle_round(c);cash=c.cash
        self.assertFalse(g.settle_round(c));self.assertFalse(g.charge_storage(c));self.assertEqual(c.cash,cash)
    def test_fee_after_income_and_consumption(self):
        g,c=self.old_stock('ore',100);g.r=5
        with self.assertRaises(ValueError):g.charge_storage(c)
        g.settle_round(c);self.assertGreaterEqual(c.cash,0);g.verify()
    def test_storage_preview_has_no_side_effects(self):
        g,c=self.old_stock('banana',20);g.r=4
        old=copy.deepcopy((g.cs,g.units,g.orders,g.plan_cache,g.storage_fraction,g.sunk))
        g.storage_preview(c);g.storage_preview(c)
        self.assertEqual(old,(g.cs,g.units,g.orders,g.plan_cache,g.storage_fraction,g.sunk))
    def test_storage_does_not_destroy_goods(self):
        g,c=self.old_stock('ore',100);g.r=5;g.settle_round(c)
        self.assertEqual(g.count(c,'ore'),100)
    def test_no_fee_by_default(self):
        g=self.game();x=g.run();self.assertEqual(x['world']['storage_paid'],0)
    def test_fee_cash_identity(self):
        g=self.game(price_tick=1,bonus_inputs=True,storage_fees=True,stock_discipline=True);x=g.run();g.verify()
        self.assertEqual(sum(z['cash'] for z in x['countries'].values()),g.initial_cash+g.minted-g.sunk)
        self.assertEqual(x['world']['investment']+x['world']['storage_paid'],g.sunk)
    def test_idle_still_never_trades(self):
        opt=replace(BASE,price_tick=1,bonus_inputs=True,storage_fees=True,stock_discipline=True)
        g=Game(4,opt,focal='Mechania',style='idle');r=g.run()['countries']['Mechania']
        self.assertEqual(r['imports']+r['exports']+r['investment'],0)
    def test_all_switches_deterministic(self):
        opt=replace(BASE,price_tick=1,bonus_inputs=True,storage_fees=True,stock_discipline=True)
        self.assertEqual(Game(24,opt).run(),Game(24,opt).run())

if __name__=='__main__':unittest.main(verbosity=2)
