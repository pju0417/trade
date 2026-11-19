"""Regression tests for economic invariants and named failure modes."""
import unittest, copy, json
from engine import Game, Options, NAMES, GOODS

class TestEngine(unittest.TestCase):
 def opts(self):return Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True)
 def game(self):return Game(7,self.opts())
 def test_listed_electronics_not_domestic_use(self):
  g=self.game();g.r=1;c=g.cs['Tropia'];g.mint(c,'electronics',1)
  g.make_order(c,g.ids(c,'electronics'),80);g.settle_round(c)
  self.assertEqual(c.happy,75);g.verify()
 def test_listed_machine_not_equipment(self):
  g=self.game();g.r=1;c=g.cs['Tropia'];g.mint(c,'machine',1)
  g.make_order(c,g.ids(c,'machine'),50)
  self.assertEqual(g.machine_assignments(c),{});g.production();g.verify()
 def test_missing_resources_cannot_mint_advanced_goods(self):
  g=self.game();g.r=1;c=g.cs['Technia'];c.machine_tech=c.elec_tech=3
  for h in ('ore','fuel'):g.consume(c,h,g.count(c,h),'test')
  g.production()
  for h in ('machine','electronics'):
   self.assertTrue(all(g.units[i].gen==1 for i in g.ids(c,h)))
  g.verify()
 def test_duplicate_unit_in_order_rejected(self):
  g=self.game();c=g.cs['Tropia'];uid=g.ids(c,'banana')[0]
  with self.assertRaises(ValueError):g.make_order(c,[uid,uid],10)
 def test_duplicate_listing_rejected(self):
  g=self.game();c=g.cs['Tropia'];ids=g.ids(c,'banana');g.make_order(c,ids,10)
  with self.assertRaises(ValueError):g.make_order(c,ids,10)
 def test_price_multiple_of_five(self):
  g=self.game();c=g.cs['Tropia']
  for p in (-1,0,7,12.5):
   with self.assertRaises(ValueError):g.make_order(c,g.ids(c,'banana'),p)
 def test_failed_barter_rolls_back_both_legs(self):
  g=self.game();a,b='Tropia','Grainia';uid=g.ids(g.cs[a],'banana')[0]
  before=copy.deepcopy((g.units,g.cs,g.orders))
  legs=[{'seller':a,'buyer':b,'ids':[uid]}, {'seller':b,'buyer':a,'ids':[999999]}]
  self.assertFalse(g.settle_transaction(legs,None,'barter','bad'))
  self.assertEqual(before,(g.units,g.cs,g.orders))
 def test_barter_both_legs_recorded(self):
  g=self.game();a,b=g.cs['Tropia'],g.cs['Grainia'];i=g.ids(a,'banana')[0];j=g.ids(b,'wheat')[0]
  cash=a.cash+b.cash
  self.assertTrue(g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[i]}, {'seller':b.name,'buyer':a.name,'ids':[j]}],None,'barter','swap'))
  self.assertEqual(a.cash+b.cash,cash)
  self.assertEqual((a.exported['banana'],a.imported['wheat'],b.exported['wheat'],b.imported['banana']),(1,1,1,1))
  g.verify()
 def test_repeated_action_id_is_idempotent(self):
  g=self.game();a,b=g.cs['Tropia'],g.cs['Grainia'];i=g.ids(a,'banana')[0]
  legs=[{'seller':a.name,'buyer':b.name,'ids':[i]}];cash=(b.name,a.name,10)
  self.assertTrue(g.settle_transaction(legs,cash,'market','once'))
  after=(a.cash,b.cash,len(g.transactions))
  self.assertTrue(g.settle_transaction(legs,cash,'market','once'))
  self.assertEqual(after,(a.cash,b.cash,len(g.transactions)));g.verify()
 def test_same_id_different_payload_rejected(self):
  g=self.game();a,b=g.cs['Tropia'],g.cs['Grainia'];i,j=g.ids(a,'banana')
  self.assertTrue(g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[i]}],(b.name,a.name,10),'market','id'))
  self.assertFalse(g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[j]}],(b.name,a.name,10),'market','id'))
 def test_last_unit_cannot_be_bought_twice(self):
  g=self.game();a=g.cs['Tropia'];uid=g.ids(a,'banana')[0];g.make_order(a,[uid],10)
  self.assertTrue(g.settle_transaction([{'seller':a.name,'buyer':'Grainia','ids':[uid]}],('Grainia',a.name,10),'market','first'))
  self.assertFalse(g.settle_transaction([{'seller':a.name,'buyer':'Oilia','ids':[uid]}],('Oilia',a.name,10),'market','second'));g.verify()
 def test_no_negative_cash(self):
  g=self.game();uid=g.ids(g.cs['Tropia'],'banana')[0]
  self.assertFalse(g.settle_transaction([{'seller':'Tropia','buyer':'Grainia','ids':[uid]}],('Grainia','Tropia',9999),'market','rich'))
  g.verify()
 def test_production_once_per_round(self):
  g=self.game();g.r=1;self.assertTrue(g.production());count=g.uid
  self.assertFalse(g.production());self.assertEqual(count,g.uid);g.verify()
 def test_settlement_once_per_round(self):
  g=self.game();g.r=1;c=g.cs['Tropia'];self.assertTrue(g.settle_round(c));cash=c.cash
  self.assertFalse(g.settle_round(c));self.assertEqual(c.cash,cash);g.verify()
 def test_equipment_not_used_twice(self):
  g=self.game();c=g.cs['Tropia'];g.mint(c,'machine',1);mapping=g.machine_assignments(c)
  self.assertEqual(len(mapping),1);self.assertEqual(len(mapping),len(set(mapping.values())))
 def test_idle_never_transacts_or_invests(self):
  for n in NAMES:
   g=Game(10,self.opts(),focal=n,style='idle');x=g.run()['countries'][n]
   self.assertEqual(x['imports']+x['exports']+x['investment'],0)
 def test_cheap_preserves_domestic_quantity(self):
  g=Game(1,self.opts(),focal='Tropia',style='cheap');g.r=1;g.production();c=g.cs['Tropia'];g.prepare_orders(c)
  for h in ('banana','wheat'):self.assertGreaterEqual(g.count(c,h),g.food_need())
 def test_machine_with_no_output_effect_not_utilized(self):
  g=self.game();g.r=1;c=g.cs['Technia'];c.focus='electronics'
  ids=g.ids(c,'machine');g.production()
  self.assertFalse(any(g.units[i].used for i in ids))
 def test_returned_product_not_used_twice_in_industry(self):
  g=self.game();g.r=1;a,b=g.cs['Tropia'],g.cs['Grainia'];g.mint(a,'machine',1);uid=g.ids(a,'machine')[0]
  g.mark_use(a,uid,'equipment')
  g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[uid]}],(b.name,a.name,10),'market','one')
  g.mark_use(b,uid,'equipment')
  g.settle_transaction([{'seller':b.name,'buyer':a.name,'ids':[uid]}],(a.name,b.name,10),'market','two')
  g.mark_use(a,uid,'equipment')
  self.assertTrue(g.units[uid].used);self.assertEqual(len(b.useful_imports),1)
  self.assertEqual(len(g.foreign_uses[uid]),1);g.verify()
 def test_generation_immutable_after_upgrade(self):
  g=self.game();c=g.cs['Mechania'];uid=g.ids(c,'machine')[0];c.machine_tech=3
  self.assertEqual(g.units[uid].gen,1)
 def test_negotiation_can_release_listed_goods(self):
  g=self.game();g.r=1;a,b=g.cs['Tropia'],g.cs['Grainia']
  g.mint(a,'banana',6);g.mint(b,'wheat',6)
  g.consume(a,'wheat',2,'test');g.consume(b,'banana',2,'test')
  g.prepare_orders(a);g.prepare_orders(b)
  result=g.negotiate(a,'wheat',1)
  self.assertEqual(result,1);self.assertEqual(g.barters,1);g.verify()
 def test_generation_minimum_honored(self):
  g=self.game();g.r=1;a,b=g.cs['Tropia'],g.cs['Mechania'];g.mint(b,'machine',3,1);g.prepare_orders(b)
  self.assertEqual(g.market_buy(a,'machine',1,1000,min_gen=2),0)
 def test_reference_update_does_not_reprice_user_orders(self):
  g=self.game();g.r=1;c=g.cs['Tropia'];oid=g.make_order(c,g.ids(c,'banana'),15)
  g.demand_snapshot();g.update_prices();self.assertEqual(g.orders[oid].price,15)
 def test_no_trade_counterfactual(self):
  g=Game(12,Options(planning=True,price_v2=True,trade_enabled=False));x=g.run()
  self.assertEqual(x['world']['transactions'],0);self.assertEqual(x['world']['useful_imports'],0)
 def test_deterministic_seed(self):
  self.assertEqual(Game(23,self.opts()).run(),Game(23,self.opts()).run())
 def test_multiple_scenarios_invariants(self):
  for seed in range(10):
   for style in ('normal','cheap','idle','invest','trade'):
    g=Game(seed,self.opts(),focal=NAMES[seed%6],style=style);g.run();self.assertTrue(g.verify())

if __name__=='__main__':unittest.main(verbosity=2)
