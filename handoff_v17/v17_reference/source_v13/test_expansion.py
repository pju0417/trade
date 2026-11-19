import unittest,copy,math
from dataclasses import replace
from collections import Counter
from expansion_engine import Game,ADDITIONS,BASE_OPTIONS,NAMES,CONFIG,COMBINATIONS,GOODS
from engine import Game as Original

class ExpansionTests(unittest.TestCase):
    def test_original_conditions_preserved(self):
        for scenario in ('six','clones','roles'):
            g=Game(8,scenario)
            for n in NAMES:
                self.assertEqual(g.cs[n].start,CONFIG[n][0]);self.assertEqual(g.cs[n].bases,CONFIG[n][1])
    def test_nine_exactly_three_more(self):
        g=Game(8,'roles');self.assertEqual(len(g.cs),9);self.assertEqual(set(g.cs)-set(NAMES),set(ADDITIONS))
    def test_initial_cash_exact(self):
        a,b=Game(1),Game(1,'roles');self.assertEqual(a.initial_cash,1090);self.assertEqual(b.initial_cash,1625)
        b.verify()
    def test_all_goods_have_real_origin(self):
        g=Game(8008,'roles');g.run()
        self.assertTrue(all(u.origin in g.cs for u in g.units.values()));g.verify()
    def test_clones_balanced_across_twenty_configs(self):
        counts=Counter(n for row in COMBINATIONS for n in row)
        self.assertEqual(set(counts.values()),{10});self.assertEqual(len(COMBINATIONS),20)
    def test_clone_inherits_specialist_cost(self):
        s=next(i for i,ns in enumerate(COMBINATIONS) if 'Mechania' in ns)
        g=Game(s,'clones');n=next(n for n,r in g.role_of.items() if n not in NAMES and r=='Mechania')
        self.assertEqual(g.upgrade_cost(g.cs[n],'machine'),g.upgrade_cost(g.cs['Mechania'],'machine'))
        self.assertEqual(g.resource_requirements(g.cs[n],'machine',2),g.resource_requirements(g.cs['Mechania'],'machine',2))
    def test_upstream_disabled_fix_reproduces_economy(self):
        a=Original(8002,BASE_OPTIONS).run();b=Game(8002,fixes=False).run()
        for n in NAMES:
            for k in ('cash','revenue','purchases','happy','investment','tax','exports','imports','upgrades','score'):
                self.assertAlmostEqual(a['countries'][n][k],b['countries'][n][k],places=8,msg=(n,k))
        for k in ('trade_units','listed','barter','transactions'):
            self.assertEqual(a['world'][k],b['world'][k])
    def test_equipment_target_matches_single_actual_support_slot(self):
        g=Game(1);g.r=2;c=g.cs['Tropia'];c.levels['banana']=2
        self.assertEqual(g.targets(c)['machine'],1)
    def test_second_machine_no_unsupported_recommendation(self):
        g=Game(1);g.r=2;c=g.cs['Tropia'];c.levels['banana']=2
        g.mint(c,'machine',1)
        self.assertEqual(g.need(c,'machine'),0)
        self.assertFalse(any(r['good']=='machine' for r in g.purchase_plan(c)))
    def test_industrial_focus_no_passive_equipment_target(self):
        g=Game(1);g.r=1;c=g.cs['Mechania']
        self.assertEqual(g.equip_slots(c),0);self.assertEqual(g.machine_assignments(c),{})
    def test_development_grade_still_acquirable(self):
        g=Game(1);g.r=3;c=g.cs['Tropia'];c.levels['banana']=3;c.cash=1000
        g.plan_cache[(3,c.name)]='banana'
        self.assertEqual(g.targets(c)['machine'],1)
        rows=[r for r in g.purchase_plan(c) if r['good']=='machine']
        self.assertEqual(rows[0]['min_gen'],2)
    def make_budget_case(self):
        g=Game(1);g.r=8
        for c in g.cs.values():c.style='idle'
        b=g.cs['Mechania'];b.style='normal';b.cash=95
        for food in ('banana','wheat'):g.mint(b,food,1,initial=True)
        g.consume(b,'ore',g.count(b,'ore'),'setup')
        for seller,good,p in [('Technia','electronics',80),('Oilia','ore',20)]:
            z=g.cs[seller];g.mint(z,good,1,initial=True);g.make_order(z,g.ids(z,good),p)
        return g,b
    def test_budget_forecast_matches_execution(self):
        g,b=self.make_budget_case();rows=g.purchase_plan(b)
        self.assertEqual([(r['good'],r['quantity']) for r in rows if r['quantity']], [('ore',1)])
        g.demand_snapshot();self.assertEqual(g.snapshots[-1]['demand'].get('ore'),1)
        self.assertEqual(g.snapshots[-1]['demand'].get('electronics',0),0)
        g.buy_phase(b,0);self.assertEqual(b.imported['ore'],1);self.assertEqual(b.imported['electronics'],0)
    def test_purchase_plan_never_allocates_wallet_twice(self):
        g=Game(8003,'roles');g.r=4;g.production()
        for c in g.cs.values():
            rows=g.purchase_plan(c);self.assertLessEqual(sum(x['budget'] for x in rows),c.cash)
    def test_prediction_does_not_spend_cash_or_goods(self):
        g=Game(1,'roles');g.r=2;c=g.cs['Novia']
        before=copy.deepcopy((g.units,c.cash,c.stock,g.orders,c.bonus_buffer))
        for _ in range(3):g.purchase_plan(c)
        self.assertEqual(before,(g.units,c.cash,c.stock,g.orders,c.bonus_buffer))
    def test_world_food_demand_scales_nine_not_six(self):
        a,b=Game(1),Game(1,'roles');a.r=b.r=5
        self.assertEqual(a.world_potential_need('wheat'),12);self.assertEqual(b.world_potential_need('wheat'),18)
    def test_world_mean_denominator_nine(self):
        g=Game(2,'roles');r=g.run()
        self.assertAlmostEqual(r['world']['happy'],sum(c['happy'] for c in r['countries'].values())/9)
    def test_new_countries_no_invented_calibrated_score(self):
        r=Game(2,'roles').run()
        for n in ADDITIONS:self.assertIsNone(r['countries'][n]['score'])
    def test_same_seed_reproducible(self):
        self.assertEqual(Game(8003,'roles').run(),Game(8003,'roles').run())
    def test_idle_no_hidden_actions(self):
        g=Game(8003,'roles',focal='Technia',style='idle');r=g.run();x=r['countries']['Technia']
        self.assertEqual(x['exports'],0);self.assertEqual(x['imports'],0);self.assertEqual(x['investment'],0)
    def test_no_trade_preserves_production(self):
        g=Game(8001,'roles',trade_enabled=False);r=g.run()
        self.assertEqual(r['world']['transactions'],0);self.assertGreater(sum(g.created.values()),0)
    def test_capital_conservation(self):
        g=Game(8003,'roles');g.run()
        self.assertEqual(sum(c.cash for c in g.cs.values()),g.initial_cash+g.minted-g.sunk)
        self.assertTrue(all(c.cash>=0 for c in g.cs.values()))
    def test_no_storage_or_optional_inputs(self):
        g=Game(8003,'roles');g.run()
        self.assertEqual(sum(g.storage_paid.values()),0);self.assertEqual(sum(g.bonus_raw.values()),0)
    def test_rerun_no_double_trade(self):
        g=Game(8003,'roles');r=g.run();t=len(g.transactions)
        self.assertEqual(g.run(),r);self.assertEqual(t,len(g.transactions))
    def test_plan_does_not_target_larger_machine_inventory_on_growth_alone(self):
        g=Game(8);g.r=8;c=g.cs['Tropia'];c.levels['banana']=4
        self.assertEqual(g.targets(c)['machine'],1)

if __name__=='__main__':unittest.main(verbosity=2)
