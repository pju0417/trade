import copy, unittest
from engine import Game,Options,NAMES,GOODS,CONFIG

class TestFixes(unittest.TestCase):
    def game(self,seed=1):
        return Game(seed,Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True))
    def leg(self,g):
        return [{'seller':'Tropia','buyer':'Grainia','ids':g.ids(g.cs['Tropia'],'banana')[:1]}]
    def unchanged_bad(self,legs,cash,channel='market'):
        g=self.game();before=copy.deepcopy((g.cs,g.units,g.orders))
        self.assertFalse(g.settle_transaction(legs(g) if callable(legs) else legs,cash,channel,'bad'))
        self.assertEqual(before,(g.cs,g.units,g.orders));g.verify()
    def test_third_country_cannot_be_charged(self):
        self.unchanged_bad(self.leg,('Technia','Tropia',10))
    def test_reversed_cash_direction_rejected(self):
        self.unchanged_bad(self.leg,('Tropia','Grainia',10))
    def test_unknown_payer_rejected_without_keyerror(self):
        self.unchanged_bad(self.leg,('Unknown','Tropia',10))
    def test_free_goods_not_a_cash_trade(self):
        self.unchanged_bad(self.leg,None)
    def test_zero_payment_rejected(self):
        self.unchanged_bad(self.leg,('Grainia','Tropia',0))
    def test_boolean_payment_rejected(self):
        self.unchanged_bad(self.leg,('Grainia','Tropia',True))
    def test_invalid_channel_rejected(self):
        self.unchanged_bad(self.leg,('Grainia','Tropia',10),'unknown')
    def test_empty_cash_transfer_not_trade(self):
        self.unchanged_bad([],('Grainia','Tropia',10))
    def test_unknown_good_id_rejected(self):
        self.unchanged_bad([{'seller':'Tropia','buyer':'Grainia','ids':[99999]}],('Grainia','Tropia',10))
    def test_malformed_leg_rejected(self):
        self.unchanged_bad([{}],('Grainia','Tropia',10))
    def test_barter_requires_reciprocal_parties(self):
        def legs(g):
            return [self.leg(g)[0],{'seller':'Oilia','buyer':'Tropia','ids':g.ids(g.cs['Oilia'],'wheat')[:1]}]
        self.unchanged_bad(legs,None,'barter')
    def test_cash_plus_barter_not_selected_mode(self):
        def legs(g):
            return [self.leg(g)[0],{'seller':'Grainia','buyer':'Tropia','ids':g.ids(g.cs['Grainia'],'wheat')[:1]}]
        self.unchanged_bad(legs,('Grainia','Tropia',10),'barter')
    def test_invalid_mint_raises(self):
        g=self.game();c=g.cs['Tropia']
        for n in (-1,1.5,True):
            with self.assertRaises(ValueError):g.mint(c,'banana',n)
        with self.assertRaises(ValueError):g.mint(c,'banana',1,gen=2)
    def test_use_episode_not_duplicated(self):
        g=self.game();g.r=1;a,b=g.cs['Tropia'],g.cs['Grainia'];g.mint(a,'machine',1)
        uid=g.ids(a,'machine')[0]
        g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':[uid]}],(b.name,a.name,50),'direct','one')
        g.mark_use(b,uid,'equipment');slots=b.import_slots
        g.mark_use(b,uid,'equipment');self.assertEqual(slots,b.import_slots)
        g.r=2;g.mark_use(b,uid,'equipment');self.assertEqual(slots+1,b.import_slots)
    def test_failed_use_does_not_poison_later_use(self):
        g=self.game();g.r=1;c=g.cs['Tropia'];g.mint(c,'electronics',1);uid=g.ids(c,'electronics')[0]
        g.make_order(c,[uid],80)
        with self.assertRaises(AssertionError):g.mark_use(c,uid,'living')
        g.remove_order_ids([uid]);g.mark_use(c,uid,'living');self.assertTrue(g.units[uid].used)
    def test_repeat_investment_action_not_recharged(self):
        g=self.game();g.r=1;c=g.cs['Tropia']
        self.assertTrue(g.invest(c,'i1'));old=(c.cash,c.upgrades)
        self.assertTrue(g.invest(c,'i1'));self.assertEqual(old,(c.cash,c.upgrades))
        self.assertFalse(g.invest(c,'i2'));g.verify()
    def test_repeat_game_run_not_retraded(self):
        g=self.game();a=g.run();n=len(g.transactions)
        self.assertEqual(a,g.run());self.assertEqual(n,len(g.transactions))
    def test_research_without_manufacture_not_global_launch(self):
        g=self.game();g.r=1;c=g.cs['Technia'];c.elec_tech=3
        g.consume(c,'ore',1,'test');g.consume(c,'fuel',1,'test')
        g.production();self.assertEqual(g.global_gen['electronics'],1)
        self.assertTrue(all(g.units[i].gen==1 for i in g.ids(c,'electronics')))
    def test_actual_new_goods_launch(self):
        g=self.game();g.r=1;c=g.cs['Technia'];c.elec_tech=2
        g.mint(c,'ore',4);g.production();self.assertEqual(g.global_gen['electronics'],2)
    def test_domestic_supply_not_import_denominator(self):
        g=self.game();g.r=1;c=g.cs['Tropia']
        g.record_need(c,'banana',2,'food',g.ids(c,'banana'))
        row=g.needs_ledger[-1];self.assertEqual(row['external'],0)
    def test_listing_domestic_goods_cannot_inflate_opportunities(self):
        g=self.game();g.r=1;c=g.cs['Tropia'];g.make_order(c,g.ids(c,'banana'),10)
        g.record_need(c,'banana',2,'food',[]);self.assertEqual(g.needs_ledger[-1]['external'],0)
    def test_foreign_food_use_credit_bounded_by_need(self):
        g=self.game();g.r=1;a,b=g.cs['Tropia'],g.cs['Grainia'];g.consume(b,'banana',2,'test')
        ids=g.ids(a,'banana')
        g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':ids}],(b.name,a.name,20),'direct','d')
        g.record_need(b,'banana',1,'food',ids)
        self.assertEqual(g.needs_ledger[-1]['fulfilled'],1)
    def test_imported_unused_stock_not_credited(self):
        g=self.game();g.r=1;a,b=g.cs['Tropia'],g.cs['Grainia'];g.mint(a,'electronics',1)
        ids=g.ids(a,'electronics');g.settle_transaction([{'seller':a.name,'buyer':b.name,'ids':ids}],(b.name,a.name,80),'direct','d')
        g.record_need(b,'electronics',1,'living',[]);self.assertEqual(g.needs_ledger[-1]['fulfilled'],0)
    def test_plan_frozen_within_round(self):
        g=self.game();g.r=3;c=g.cs['Mechania'];first=g.plan(c)
        g.mint(g.cs['Technia'],'electronics',30)
        self.assertEqual(first,g.plan(c))
    def test_no_new_country_or_unlimited_electronics_source(self):
        g=Game(10,Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True),focal='Technia',style='idle')
        g.run();self.assertEqual(set(g.cs),set(NAMES))
        self.assertTrue(all(u.origin in NAMES for u in g.units.values()))
        self.assertEqual(g.cs['Technia'].imports if hasattr(g.cs['Technia'],'imports') else sum(g.cs['Technia'].imported.values()),0)
        self.assertEqual(g.cs['Technia'].investment,0)
    def test_expansion_cost_is_paid(self):
        g=Game(5,Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True),focal='Technia',style='idle')
        g.run();c=g.cs['Mechania']
        if 'electronics' in c.levels:self.assertGreaterEqual(c.investment,220)
        g.verify()
    def test_new_model_reproducible(self):
        self.assertEqual(self.game(80).run(),self.game(80).run())


class TestScores(unittest.TestCase):
    def test_scoring_does_not_move_cash_or_goods(self):
        from scoring import apply
        opt=Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True)
        g=Game(44,opt);r=g.run();cash={n:c.cash for n,c in g.cs.items()};stock={n:set(c.stock) for n,c in g.cs.items()}
        goals={'economic':{n:200 for n in NAMES},'industrial':{n:1 for n in NAMES}}
        apply(r,goals)
        self.assertEqual(cash,{n:c.cash for n,c in g.cs.items()});self.assertEqual(stock,{n:set(c.stock) for n,c in g.cs.items()})
        self.assertTrue(all(0<=x['score_v3']<=100 for x in r['countries'].values()))
    def test_unused_import_not_automatically_trade_credit(self):
        g=Game(33,Options(planning=True,negotiations=True,price_v2=True,saturation_aware=True,smaller_bonus=True))
        g.run()
        for n,x in g.summary()['countries'].items():
            self.assertLessEqual(x['fulfilled_external'],x['external_opportunities'])
            self.assertTrue(0<=x['trade']<=25)
    def test_goal_calibration_has_positive_denominators(self):
        from scoring import make_goals
        rows=[{'countries':{n:{'evaluated_progress':-10,'growth':0} for n in NAMES}} for _ in range(4)]
        goals=make_goals(rows)
        self.assertTrue(all(v>0 for v in goals['economic'].values()))
        self.assertTrue(all(v>0 for v in goals['industrial'].values()))
    def test_unchanged_initial_conditions(self):
        g=Game(1,Options())
        for n,c in g.cs.items():
            self.assertEqual(c.start,CONFIG[n][0]);self.assertEqual(c.bases,CONFIG[n][1])

if __name__=='__main__':unittest.main(verbosity=2)
