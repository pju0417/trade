"""Meaningful v17 boundaries plus exactly six old/new complete-game pairs.

Only test_z_none_profile_full_history_compatibility calls Game.run(). All other
tests are explicitly isolated fixtures, including one-round score snapshots.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import unittest

from operating_engine import Game, PreviousGame, PROFILES
from expansion_engine import Game as ScoringBase
from reference_engine import GOODS, FOOD

ROOT=Path(__file__).resolve().parent
EXECUTIONS=[]
PAIRS=[]
FIXTURES=0


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class OperatingTests(unittest.TestCase):
    def fixture(self,profile='daily',name='Mineria',r=3):
        global FIXTURES
        FIXTURES+=1
        g=Game(128900+FIXTURES,operating_profile=profile);g.r=r
        c=g.cs[name];g.plan_cache[(r,name)]=None
        return g,c

    def transfer(self,g,seller,buyer,ids,amount=1):
        self.assertTrue(g.settle_transaction([{'seller':seller,'buyer':buyer,'ids':list(ids)}],
            (buyer,seller,amount),'direct',f'fixture-transfer-{len(g.transactions)}'))

    def set_wallet_by_purchase(self,g,c,amount):
        self.assertGreaterEqual(c.cash,amount)
        if c.cash==amount:return
        seller=g.cs['Novia' if c.name!='Novia' else 'Ferria']
        g.mint(seller,'machine',1,initial=True)
        self.transfer(g,seller.name,c.name,[g.uid],c.cash-amount)
        self.assertEqual(c.cash,amount)

    def full_living(self,g,c):
        want=math.ceil(g.pop()/2)
        if g.count(c,'electronics')<want:g.mint(c,'electronics',want-g.count(c,'electronics'),initial=True)
        for good in FOOD:
            if g.count(c,good)<g.food_need():g.mint(c,good,g.food_need()-g.count(c,good),initial=True)

    def assert_old_projection(self,old,new,path='root'):
        if isinstance(old,dict):
            self.assertIsInstance(new,dict,path)
            self.assertTrue(set(old)<=set(new),(path,'missing old keys',set(old)-set(new)))
            for k,v in old.items():self.assert_old_projection(v,new[k],path+'.'+str(k))
        elif isinstance(old,(list,tuple)):
            self.assertIsInstance(new,type(old),path);self.assertEqual(len(old),len(new),path)
            for i,(a,b) in enumerate(zip(old,new)):self.assert_old_projection(a,b,path+f'[{i}]')
        else:self.assertEqual(old,new,path)

    def test_a_public_schedules_and_boundaries(self):
        expected={'none':((),()),'light':((3,6,9),(4,8)),
                  'regular':((2,4,6,8),(3,6,9)),'daily':(tuple(range(1,10)),(3,6,9))}
        self.assertEqual(set(PROFILES),set(expected))
        for profile,(fuel,ore) in expected.items():
            g,c=self.fixture(profile)
            for r in range(0,11):
                self.assertEqual(g.operating_required(c,r,False),{'ore':int(r in ore),'fuel':int(r in fuel)})
            g.settled.add((3,c.name))
            self.assertEqual(g.operating_required(c,3),{'ore':0,'fuel':0})
        with self.assertRaises(ValueError):Game(1,operating_profile='unknown')

    def test_b_partial_consumption_shortage_income_once(self):
        for have_ore,have_fuel,penalty,expected_happy,income in (
            (0,0,12,88,19),(1,0,8,92,19),(0,1,4,96,20),(1,1,0,100,20)):
            with self.subTest(ore=have_ore,fuel=have_fuel):
                g,c=self.fixture();self.full_living(g,c)
                g.mint(c,'ore',have_ore,initial=True);g.mint(c,'fuel',have_fuel,initial=True)
                before=(c.cash,c.tax,g.minted)
                self.assertTrue(g.settle_round(c));row=g.operating_ledger[-1]
                self.assertEqual(row['consumed'],{'ore':have_ore,'fuel':have_fuel})
                self.assertEqual(row['penalty'],penalty);self.assertEqual(c.happy,expected_happy)
                self.assertEqual(c.happiness,[expected_happy])
                self.assertEqual((c.cash-before[0],c.tax-before[1],g.minted-before[2]),(income,)*3)
                self.assertEqual(row['base_happy'],100);self.assertEqual(row['round_income'],income)
                snapshot=deepcopy((g.cs,g.units,g.raw_use_log,g.operating_ledger,g.operating_use_log,
                                   g.needs_ledger,g.destroyed,g.minted,g.settled))
                self.assertFalse(g.settle_round(c))
                self.assertEqual(snapshot,(g.cs,g.units,g.raw_use_log,g.operating_ledger,g.operating_use_log,
                                           g.needs_ledger,g.destroyed,g.minted,g.settled))
                self.assertTrue(g.verify())

    def test_c_physical_foreign_initial_and_produced_use(self):
        g,c=self.fixture(name='Tropia');self.full_living(g,c)
        initial=g.cs['Oilia'];produced=g.cs['Mineria']
        g.mint(initial,'fuel',1,initial=True);fuel=g.uid
        g.mint(produced,'ore',1);ore=g.uid
        self.transfer(g,initial.name,c.name,[fuel]);self.transfer(g,produced.name,c.name,[ore])
        self.assertTrue(g.settle_round(c))
        for good,uid,born in (('fuel',fuel,0),('ore',ore,3)):
            unit=g.units[uid]
            self.assertEqual((unit.owner,unit.used,unit.use_purpose),(None,True,'national'))
            self.assertEqual(unit.born,born)
            rows=[x for x in g.needs_ledger if x['country']==c.name and x['good']==good and x['purpose']=='national']
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['used_ids'],[uid])
            self.assertEqual((rows[0]['needed'],rows[0]['external'],rows[0]['fulfilled']),(1,1,1))
            uses=[x for x in g.raw_use_log if x['uid']==uid]
            self.assertEqual(len(uses),1);self.assertEqual(uses[0]['purpose'],'national')
            self.assertIn(uid,c.useful_imports)
        self.assertEqual(g._raw_counts(c.name,'fuel')['initial_foreign'],1)
        self.assertEqual(g._raw_counts(c.name,'ore')['produced_foreign'],1)
        for good in ('ore','fuel'):
            x=g._raw_counts(c.name,good)
            self.assertEqual(x['consumed'],x['production']+x['research']+x['national'])
            self.assertEqual(x['national'],1)
        self.assertTrue(g.verify())

    def test_d_current_target_once_and_no_round_ten(self):
        g,c=self.fixture(profile='regular',name='Technia',r=9)
        old=PreviousGame.targets(g,c);new=g.targets(c)
        self.assertEqual({k:new[k]-old[k] for k in GOODS},
                         {k:int(k=='ore') for k in GOODS})
        self.full_living(g,c);g.settle_round(c)
        self.assertEqual(g.targets(c),PreviousGame.targets(g,c))
        self.assertEqual(g.operating_required(c,10),{'ore':0,'fuel':0})
        self.assertEqual(g.next_resources(c),{})

    def test_e_protect_and_recall_own_listed_essentials(self):
        g,c=self.fixture();g.mint(c,'ore',3);g.mint(c,'fuel',2)
        for good in ('ore','fuel'):g.make_order(c,g.ids(c,good),g.quote(good))
        g.prepare_orders(c)
        for good in ('ore','fuel'):
            self.assertGreaterEqual(g.count(c,good),1)
            protected=g.protected_ids(c,good)
            self.assertTrue(protected)
            self.assertTrue(all(g.units[i].order is None for i in protected))
            self.assertFalse(set(g.get_surplus(c,good))&protected)
        self.assertTrue(g.verify())

    def test_f_unaffordable_basic_want_is_not_double_counted(self):
        g,c=self.fixture(name='Technia')
        for good in ('ore','fuel'):
            ids=g.ids(c,good)
            if ids:self.transfer(g,c.name,'Mineria',ids)
        self.set_wallet_by_purchase(g,c,0)
        target=g.targets(c);initial={k:g.count(c,k) for k in GOODS};rows=g.purchase_plan(c)
        self.assertEqual(sum(x['budget'] for x in rows),0)
        for good in ('ore','fuel'):
            selected=[x for x in rows if x['good']==good]
            self.assertEqual(len(selected),1)
            self.assertEqual(selected[0]['want'],max(0,target[good]-initial[good]))
            self.assertEqual(selected[0]['quantity'],0)
        fuel=next(x for x in rows if x['good']=='fuel')
        self.assertEqual(fuel['want'],2)
        self.assertEqual(len(fuel['budget_parts']),2)
        self.assertTrue(g.verify())

    def test_g_food_budget_first_and_merged_budget_bound(self):
        g,c=self.fixture(name='Tropia')
        for good in FOOD:self.transfer(g,c.name,'Mineria',g.ids(c,good))
        self.set_wallet_by_purchase(g,c,30)
        rows=g.purchase_plan(c)
        self.assertEqual([r['good'] for r in rows[:2]],list(FOOD))
        self.assertEqual([r['budget'] for r in rows[:2]],[10,10])
        self.assertEqual(sum(r['budget'] for r in rows),20)
        self.assertLessEqual(sum(r['budget'] for r in rows),c.cash)
        self.assertTrue(all(r['quantity']==0 for r in rows if r['good'] in ('ore','fuel')))
        nonreplacement=[r['good'] for r in rows if r['kind']!='replacement']
        self.assertEqual(len(nonreplacement),len(set(nonreplacement)))
        self.assertTrue(g.verify())

    def test_h_no_duplicate_credit_or_extra_industry_bonus(self):
        # One-round scoring fixture, not a completed game or an outcome sample.
        g,c=self.fixture();g.mint(c,'ore',1);uid=g.uid
        for actor in g.cs.values():g.settle_round(actor)
        value=ScoringBase.summary(g)['countries'][c.name]
        self.assertEqual(value['capacity_growth'],0)
        self.assertEqual(value['produced'],{'ore':1})
        self.assertEqual(value['industry'],10.0)
        self.assertEqual(g.units[uid].use_purpose,'national')
        state=deepcopy((g.use_episodes,g.foreign_uses,c.import_slots,g.round_useful))
        g.mark_use(c,uid,'national')
        self.assertEqual(state,(g.use_episodes,g.foreign_uses,c.import_slots,g.round_useful))
        self.assertEqual(ScoringBase.summary(g)['countries'][c.name]['industry'],10.0)
        self.assertTrue(g.verify())

    def test_i_idle_still_settles_national_obligations(self):
        g,c=self.fixture();c.style='idle';g.mint(c,'ore',1,initial=True)
        self.assertEqual(g.purchase_plan(c),[])
        g.settle_round(c);row=g.operating_ledger[-1]
        self.assertEqual(row['consumed'],{'ore':1,'fuel':0})
        self.assertEqual(row['missing'],{'ore':0,'fuel':1})
        self.assertEqual(row['penalty'],8)
        self.assertTrue(g.verify())

    def test_z_none_profile_full_history_compatibility(self):
        cases=[('baseline',None,'normal',True),('electronics_input','Technia','minimum',True),
               ('baseline','Mineria','minimum_passive',True),('electronics_input','Tropia','idle',True),
               ('baseline','Grainia','invest',True),('electronics_input',None,'normal',False)]
        for i,(mode,focal,style,trade) in enumerate(cases):
            seed=129000+i;options=dict(seed=seed,mode=mode,focal=focal,style=style,trade_enabled=trade)
            with self.subTest(seed=seed,mode=mode,style=style,trade=trade):
                old=PreviousGame(**options);new=Game(**options,operating_profile='none')
                results=[]
                for kind,game in (('previous',old),('v17_none',new)):
                    entry={'seed':seed,'mode':mode,'focal':focal,'style':style,'trade_enabled':trade,
                           'engine':kind,'completed':False};EXECUTIONS.append(entry)
                    value=game.run();entry['completed']=game.r==9 and len(game.round_history)==9
                    self.assertTrue(entry['completed']);results.append(value)
                self.assert_old_projection(results[0],results[1])
                self.assert_old_projection(old.trace(),new.trace(),'trace')
                self.assertEqual(old.units,new.units);self.assertEqual(old.transactions,new.transactions)
                self.assertEqual(old.cash_ledger,new.cash_ledger)
                self.assertEqual(len(new.operating_ledger),81)
                self.assertEqual(new.operating_use_log,[])
                self.assertTrue(all(not any(r['required'].values()) and r['tax_effect']==0 for r in new.operating_ledger))
                PAIRS.append({'seed':seed,'mode':mode,'style':style,'matched':True})


if __name__=='__main__':
    engine_before=digest(ROOT/'operating_engine.py')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(OperatingTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    completed=sum(x['completed'] for x in EXECUTIONS)
    passed=result.wasSuccessful() and completed==12 and len(PAIRS)==6
    receipt={'schema':'v17-operating-semantic-tests-1','status':'PASS' if passed else 'FAIL',
             'completed_at':datetime.now(timezone.utc).isoformat(),'tests':result.testsRun,
             'failures':len(result.failures),'errors':len(result.errors),
             'completed_economic_games':completed,'new_economic_games':completed,
             'economic_execution_attempts':len(EXECUTIONS),'backcompat_pairs':len(PAIRS),
             'isolated_fixture_instances':FIXTURES,'fixtures_are_completed_games':False,
             'engine_sha256':engine_before,'engine_after_sha256':digest(ROOT/'operating_engine.py'),
             'test_sha256':digest(__file__),'protocol_sha256':digest(ROOT/'OPERATING_PROTOCOL_V17.json'),
             'executions':EXECUTIONS,'matched_pairs':PAIRS,
             'scope':'Exact recursive old-field projections of countries, world and full trace; added zero-operation instrumentation allowed. No candidate performance analysis.'}
    if receipt['engine_sha256']!=receipt['engine_after_sha256']:
        receipt['status']='FAIL';receipt['source_change_error']=True;passed=False
    path=ROOT/'semantic_tests.json'
    if path.exists():raise RuntimeError('Preserve prior semantic receipt before rerunning')
    path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('executions','matched_pairs')},ensure_ascii=False))
    raise SystemExit(not passed)
