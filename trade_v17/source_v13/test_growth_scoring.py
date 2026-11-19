"""v12 pure score transformations, calibration separation and AI exposure.

Synthetic score rows test mathematical boundaries only. They are not simulated
games and never enter the calibration or untouched holdout datasets.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from growth_scoring import (Game, VIEWS, GOAL_METHOD, curve, percentile, rounded_goal,
                            extract_metrics, make_goals, score_metrics, score_record)
from evaluation_engine import Game as V11
from routing_engine import Game as V10
from reference_engine import NAMES

ROOT=Path(__file__).resolve().parent


class GrowthScoringTests(unittest.TestCase):
    def calibration(self):
        conditions=[(None,'normal')]+[(n,s) for n in NAMES for s in ('invest','trade')]
        rows=[]
        for focal,style in conditions:
            for index,seed in enumerate(range(87060,87064)):
                rows.append({'phase':'calibration','mode':'market_first','scenario':f'{focal}:{style}',
                    'seed':seed,'focal':focal,'style':style,'behaviors':{focal:style} if focal else {},
                    'countries':{name:{'growth_metrics':{'asset_gain':(50,100,150,200)[index],
                        'capacity_growth':(.1,.2,.3,.4)[index]}} for name in NAMES}})
        return rows

    def completed(self,seed=87001,focal=None,style='normal'):
        game=Game(seed,focal=focal,style=style)
        result=game.run()
        metrics=extract_metrics(game,result)
        for name,value in metrics.items():result['countries'][name]['growth_metrics']=value
        return game,{'phase':'holdout','mode':'market_first','scenario':f'{focal}:{style}',
                     'seed':seed,'focal':focal,'style':style,'behaviors':dict(game.behaviors),**result}

    def test_all_69_inherited_python_files_are_byte_identical(self):
        expected=json.loads((ROOT/'V11_PROVENANCE.json').read_text())['files']
        self.assertEqual(len(expected),69)
        actual={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in expected}
        self.assertEqual(actual,expected)

    def test_existing_v11_behaviors_preserve_every_economic_field_and_record(self):
        for seed,focal,style in ((87002,None,'normal'),(87003,'Technia','cheap'),
                                  (87004,'Technia','minimum'),(87005,'Mechania','idle')):
            old=V11(seed,focal=focal,style=style);new=Game(seed,focal=focal,style=style)
            self.assertEqual(old.run(),new.run())
            for key in ('units','orders','transactions','cash_ledger','raw_round_ledger','needs_ledger',
                        'development_log','routing_log','evaluation_attempts','price_history'):
                self.assertEqual(getattr(old,key),getattr(new,key),(style,key))

    def test_invest_and_trade_match_inherited_v10_for_every_original_country(self):
        for name in NAMES:
            for style in ('invest','trade'):
                with self.subTest(country=name,style=style):
                    old=V10(87006,'market_first',focal=name,style=style)
                    new=Game(87006,focal=name,style=style)
                    expected=old.run();actual=new.run()
                    for n,fields in expected['countries'].items():
                        for key,value in fields.items():self.assertEqual(value,actual['countries'][n][key],(n,key))
                    for key,value in expected['world'].items():self.assertEqual(value,actual['world'][key],key)
                    for key in ('units','transactions','cash_ledger','raw_round_ledger','needs_ledger',
                                'development_log','route_records','price_history'):
                        self.assertEqual(getattr(old,key),getattr(new,key),(name,style,key))

    def test_invalid_or_conflicting_new_style_is_rejected(self):
        for args in ({'style':'invest'},{'style':'trade'},{'style':'unknown'},
                     {'focal':'Technia','style':'invest','behaviors':{'Technia':'idle'}}):
            with self.assertRaises(ValueError):Game(87007,**args)

    def test_invest_and_trade_do_not_change_permissions_or_costs(self):
        ref=V11(87008)
        for style in ('invest','trade'):
            game=Game(87008,focal='Technia',style=style)
            for key in ('initial_cash','initial_assets','initial_capacity','starter_allocation','opt','config'):
                self.assertEqual(getattr(game,key),getattr(ref,key))
            self.assertEqual(game.behaviors,{'Technia':style})
            for name,c in game.cs.items():
                original=ref.cs[name]
                self.assertEqual(c.expand,original.expand)
                self.assertEqual(c.levels,original.levels)
                for good in c.levels:
                    self.assertEqual(game.upgrade_cost(c,good),ref.upgrade_cost(original,good))
                    self.assertEqual(game.upgrade_requirements(c,good),ref.upgrade_requirements(original,good))

    def test_trade_style_has_real_trade_and_automatic_production_but_no_investment(self):
        game,record=self.completed(87009,'Technia','trade');country=record['countries']['Technia']
        self.assertGreater(country['imports']+country['exports'],0)
        self.assertGreater(sum(country['produced'].values()),0)
        self.assertEqual(country['investment'],0)
        self.assertEqual(country['routing']['routes_started'],0)
        self.assertFalse(any(e['country']=='Technia' for e in game.development_log))

    def test_aggressive_investment_still_requires_real_inputs_and_ends_by_round_seven(self):
        game,record=self.completed(87010,'Mechania','invest')
        self.assertGreater(record['countries']['Mechania']['investment'],0)
        for event in game.development_log:
            if event['country']=='Mechania':
                self.assertLessEqual(event['round'],7)
                self.assertEqual(len(event['ore_ids']),event['ore_required'])
                if event['machine_min_gen']:
                    self.assertGreaterEqual(event['machine']['generation'],event['machine_min_gen'])
        self.assertEqual(record['world']['uncovered_investments'],0)
        game.verify()

    def test_extract_metrics_requires_completed_game(self):
        game=Game(87011)
        with self.assertRaises(ValueError):extract_metrics(game,{})

    def test_extract_metrics_is_pure_and_reconciles_assets_capacity_and_use(self):
        game,record=self.completed(87012)
        before=copy.deepcopy(game.__dict__)
        first=extract_metrics(game,record)
        for _ in range(3):self.assertEqual(first,extract_metrics(game,record))
        self.assertEqual(before,game.__dict__)
        for name,m in first.items():
            c=record['countries'][name]
            self.assertAlmostEqual(m['asset_gain'],m['end_asset_value']-m['start_asset_value'])
            self.assertAlmostEqual(m['stock_value'],m['unused_stock_value']+m['used_stock_value'])
            self.assertAlmostEqual(m['end_asset_value'],m['cash']+m['stock_value']+.45*m['investment'])
            self.assertEqual(m['produced_units'],sum(c['produced'].values()))
            self.assertEqual(m['used_units'],sum(c['use_by_good'].values()))
            self.assertAlmostEqual(m['capacity_growth'],(m['final_capacity']-m['initial_capacity'])/m['initial_capacity'])
            self.assertAlmostEqual(m['utilization_score'],10*m['used_units']/max(1,m['produced_units']))

    def test_hard_curve_boundary_and_clipping(self):
        for value,want in ((-2,0),(0,0),(.5,.5),(1,1),(1.5,1),(2,1),(100,1)):
            self.assertAlmostEqual(curve(value),want)

    def test_two_stage_headroom_has_exact_base_and_challenge_targets(self):
        for value,want in ((-2,0),(0,0),(.5,.4),(1,.8),(1.5,.9),(2,1),(100,1)):
            self.assertAlmostEqual(curve(value,True),want)

    def test_headroom_is_continuous_monotonic_and_bounded(self):
        values=[curve(i/100,True) for i in range(-10,311)]
        self.assertEqual(values,sorted(values))
        self.assertTrue(all(0<=v<=1 for v in values))
        for boundary in (0,1,2):
            self.assertLess(abs(curve(boundary-1e-8,True)-curve(boundary+1e-8,True)),2e-8)

    def test_curves_reject_nonfinite_or_boolean_values(self):
        for value in (float('nan'),float('inf'),-float('inf'),True,None,'1'):
            with self.assertRaises(ValueError):curve(value,True)

    def test_percentile_is_interpolated_not_a_nearest_rank_shortcut(self):
        self.assertEqual(percentile([50,100,150,200]),162.5)
        self.assertEqual(percentile([1,9]),7)
        self.assertEqual(percentile([5]),5)
        with self.assertRaises(ValueError):percentile([])

    def test_goal_floors_and_readable_ceiling_steps(self):
        self.assertEqual(rounded_goal(-100,50,5),50)
        self.assertEqual(rounded_goal(162.5,50,5),165)
        self.assertEqual(rounded_goal(165,50,5),165)
        self.assertAlmostEqual(rounded_goal(.325,.10,.05),.35)
        self.assertAlmostEqual(rounded_goal(.3,.10,.05),.3)
        self.assertAlmostEqual(rounded_goal(-1,.10,.05),.1)

    def test_calibration_selects_exact_equal_policy_samples_and_p75(self):
        rows=self.calibration();goals=make_goals(rows)
        self.assertEqual(goals['calibration']['unique_economic_games'],52)
        self.assertEqual(goals['calibration']['samples_per_country'],12)
        self.assertEqual(goals['calibration']['n_per_policy'],4)
        for name in NAMES:
            self.assertEqual(goals['economic'][name],165)
            self.assertAlmostEqual(goals['industrial'][name],.35)
            self.assertEqual(goals['raw_quantiles']['economic'][name],162.5)
            self.assertAlmostEqual(goals['raw_quantiles']['industrial'][name],.325)

    def test_peer_policy_spillovers_do_not_contaminate_country_target(self):
        rows=self.calibration();goals=make_goals(rows)
        for row in rows:
            if row['focal']:
                for name,values in row['countries'].items():
                    if name!=row['focal']:values['growth_metrics']={'asset_gain':1e9,'capacity_growth':1e6}
        self.assertEqual(goals,make_goals(rows))

    def test_calibration_is_order_independent_pure_and_does_not_alias_method(self):
        rows=self.calibration();before=copy.deepcopy(rows)
        goals=make_goals(rows)
        self.assertEqual(before,rows)
        self.assertEqual(goals,make_goals(list(reversed(rows))))
        goals['method']['policies'].append('idle')
        self.assertEqual(GOAL_METHOD['policies'],['normal','invest','trade'])

    def test_holdout_and_stress_cannot_enter_target_fitting(self):
        for phase in ('holdout','stress'):
            rows=self.calibration();rows[-1]['phase']=phase
            with self.assertRaises(ValueError):make_goals(rows)

    def test_missing_duplicate_or_unpaired_calibration_is_rejected(self):
        rows=self.calibration()
        for altered in (rows[:-1],rows+[copy.deepcopy(rows[0])]):
            with self.assertRaises(ValueError):make_goals(altered)
        altered=copy.deepcopy(rows);altered[-1]['seed']=87099
        with self.assertRaises(ValueError):make_goals(altered)

    def test_wrong_policy_identity_or_extra_style_is_rejected(self):
        rows=self.calibration();wrong=copy.deepcopy(rows);wrong[-1]['focal']='Tropia'
        with self.assertRaises(ValueError):make_goals(wrong)
        wrong=copy.deepcopy(rows);wrong[-1]['style']='idle'
        with self.assertRaises(ValueError):make_goals(wrong)
        extra=copy.deepcopy(rows[0]);extra.update(scenario='Technia:cheap',focal='Technia',style='cheap')
        with self.assertRaises(ValueError):make_goals(rows+[extra])

    def test_target_floors_with_zero_or_negative_calibration_growth(self):
        rows=self.calibration()
        for row in rows:
            for country in row['countries'].values():
                country['growth_metrics']={'asset_gain':-10,'capacity_growth':0}
        goals=make_goals(rows)
        self.assertTrue(all(v==50 for v in goals['economic'].values()))
        self.assertTrue(all(v==.1 for v in goals['industrial'].values()))

    def test_invalid_goal_values_and_method_are_rejected_before_scoring(self):
        _,record=self.completed(87013);valid=make_goals(self.calibration())
        for value in (0,-1,float('nan'),float('inf'),True):
            goals=copy.deepcopy(valid);goals['economic']['Technia']=value
            with self.assertRaises(ValueError):score_record(record,goals)
        goals=copy.deepcopy(valid);goals['method']['quantile']=.9
        with self.assertRaises(ValueError):score_record(record,goals)
        goals=copy.deepcopy(valid);goals['economic']['Novia']=100
        with self.assertRaises(ValueError):score_record(record,goals)

    def test_score_views_are_pure_repeatable_and_preserve_official_fields(self):
        game,record=self.completed(87014);goals=make_goals(self.calibration())
        before=copy.deepcopy(record);goal_before=copy.deepcopy(goals);state=copy.deepcopy(game.__dict__)
        actual=score_record(record,goals)
        self.assertEqual(actual,score_record(record,goals))
        self.assertEqual(record,before);self.assertEqual(goals,goal_before);self.assertEqual(game.__dict__,state)
        for name,fields in before['countries'].items():
            for key,value in fields.items():self.assertEqual(value,actual['countries'][name][key],(name,key))
        for key,value in before['world'].items():self.assertEqual(value,actual['world'][key],key)
        self.assertFalse(actual['world']['growth_evaluation_config']['score_feedback_to_actions'])

    def test_legacy_view_exactly_preserves_official_scores(self):
        _,record=self.completed(87015,'Technia','minimum');scored=score_record(record,make_goals(self.calibration()))
        for name in NAMES:
            country=scored['countries'][name];v=country['growth_evaluation']['legacy']
            for key in ('economic','industry','score'):self.assertEqual(v[key],country[key])
            self.assertEqual(v['trade'],country['trade'])

    def test_extra_three_nations_keep_all_four_candidate_scores_unranked(self):
        _,record=self.completed(87016);scored=score_record(record,make_goals(self.calibration()))
        for name in ('Novia','Agrea','Ferria'):
            self.assertIsNone(scored['countries'][name]['score'])
            self.assertEqual(scored['countries'][name]['growth_evaluation'],dict.fromkeys(VIEWS))

    def test_only_growth_and_capacity_components_change_between_views(self):
        _,record=self.completed(87017);scored=score_record(record,make_goals(self.calibration()))
        for name in NAMES:
            views=scored['countries'][name]['growth_evaluation']
            for view in views.values():
                for key in ('reserve','utilization','wellbeing','trade'):
                    self.assertEqual(view[key],views['legacy'][key])
                self.assertAlmostEqual(view['economic'],view['economic_growth']+view['reserve'])
                self.assertAlmostEqual(view['industry'],view['capacity']+view['utilization'])
                self.assertAlmostEqual(view['score'],view['economic']+view['industry']+view['wellbeing']+view['trade'])
                self.assertLessEqual(0,view['score']);self.assertLessEqual(view['score'],100+1e-9)

    def test_headroom_monotonicity_holds_without_forcing_every_price_strategy_to_lose(self):
        _,record=self.completed(87018);m=record['countries']['Technia']['growth_metrics']
        for value in (-100,0,50,100,150,200,300):
            c=copy.deepcopy(m);c['asset_gain']=value
            a=score_metrics(c,100,.5,True)
            c['asset_gain']=value+1;b=score_metrics(c,100,.5,True)
            self.assertGreaterEqual(b['score'],a['score'])

    def test_five_percent_growth_sensitivity_is_not_five_percent_of_points(self):
        _,record=self.completed(87019);m=record['countries']['Technia']['growth_metrics']
        m['asset_gain']=100;m['capacity_growth']=.5
        hard=score_metrics(m,100,.5,False);head=score_metrics(m,100,.5,True)
        self.assertEqual(hard['economic_5pct_sensitivity'],0)
        self.assertEqual(hard['capacity_5pct_sensitivity'],0)
        self.assertAlmostEqual(head['economic_5pct_sensitivity'],.2)
        self.assertAlmostEqual(head['capacity_5pct_sensitivity'],.15)

    def test_near_cap_and_exact_cap_use_their_own_growth_component_limits(self):
        _,record=self.completed(87020);m=record['countries']['Technia']['growth_metrics']
        m['asset_gain']=175;m['capacity_growth']=.875
        view=score_metrics(m,100,.5,True)
        self.assertEqual(view['economic_growth_near_cap'],1);self.assertEqual(view['capacity_near_cap'],1)
        self.assertEqual(view['economic_growth_at_cap'],0);self.assertEqual(view['capacity_at_cap'],0)
        m['asset_gain']=200;m['capacity_growth']=1
        view=score_metrics(m,100,.5,True)
        self.assertEqual(view['economic_growth_at_cap'],1);self.assertEqual(view['capacity_at_cap'],1)

    def test_nonfinite_evidence_cannot_silently_create_a_score(self):
        _,record=self.completed(87021);goals=make_goals(self.calibration())
        record['countries']['Technia']['growth_metrics']['asset_gain']=float('nan')
        with self.assertRaises(ValueError):score_record(record,goals)

    def test_extreme_holdout_growth_cannot_refit_or_change_frozen_goals(self):
        _,record=self.completed(87022);goals=make_goals(self.calibration());before=copy.deepcopy(goals)
        score_record(record,goals)
        self.assertEqual(goals,before)
        # Explicit hypothetical scoring row, not another economic simulation.
        # A capped legacy score can remain unchanged despite a much larger gain.
        country=record['countries']['Technia'];metrics=country['growth_metrics']
        metrics['asset_gain']=1e6
        country['economic']=20+metrics['reserve_score']
        country['score']=country['economic']+country['industry']+country['happy']/4+country['trade']
        extreme=score_record(record,goals)['countries']['Technia']['growth_evaluation']['targets_headroom']
        self.assertEqual(extreme['economic_target'],goals['economic']['Technia'])
        self.assertEqual(extreme['economic_growth'],20)
        self.assertEqual(goals,before)

    def selection_rows(self):
        rows=self.calibration()
        for row in rows:
            for name,country in row['countries'].items():
                country['growth_evaluation']={view:{'score':50.} for view in VIEWS}
                if row['focal']==name and row['style']=='invest':
                    country['growth_evaluation']['legacy']['score']=60.
                if row['focal']==name and row['style']=='trade':
                    country['growth_evaluation']['headroom']['score']=70.
        return rows

    def test_preselection_is_pure_per_view_and_uses_fixed_tie_order(self):
        from run_growth_validation import select_policies
        rows=self.selection_rows();before=copy.deepcopy(rows)
        selected=select_policies(rows)
        self.assertEqual(rows,before)
        for name in NAMES:
            self.assertEqual(selected['selections']['legacy'][name]['policy'],'invest')
            self.assertEqual(selected['selections']['targets'][name]['policy'],'normal')
            self.assertEqual(selected['selections']['headroom'][name]['policy'],'trade')
            self.assertEqual(selected['selections']['targets_headroom'][name]['policy'],'normal')

    def test_preselection_excludes_peer_policy_payoffs(self):
        from run_growth_validation import select_policies
        rows=self.selection_rows();expected=select_policies(rows)
        for row in rows:
            if row['focal']:
                for name,country in row['countries'].items():
                    if name!=row['focal']:
                        for view in VIEWS:country['growth_evaluation'][view]['score']=1000.
        self.assertEqual(expected,select_policies(rows))

    def test_preselection_rejects_holdout_or_incomplete_data(self):
        from run_growth_validation import select_policies
        rows=self.selection_rows()
        with self.assertRaises(ValueError):select_policies(rows[:-1])
        rows[0]['phase']='holdout'
        with self.assertRaises(ValueError):select_policies(rows)

    def test_exact_protocol_schedule_is_disjoint_and_has54_trace_cases(self):
        from run_growth_validation import build_tasks, representative
        tasks=build_tasks()
        self.assertEqual(len(tasks),4180);self.assertEqual(len(set(tasks)),4180)
        self.assertEqual(sum(t[0]=='calibration' for t in tasks),780)
        self.assertEqual(sum(t[0]=='holdout' for t in tasks),3100)
        self.assertEqual(sum(t[0]=='stress' for t in tasks),300)
        self.assertEqual(sum(representative(t) for t in tasks),54)
        seeds={phase:{t[1] for t in tasks if t[0]==phase} for phase in ('calibration','holdout','stress')}
        self.assertFalse(seeds['calibration'] & seeds['holdout'])
        self.assertFalse(seeds['calibration'] & seeds['stress'])
        self.assertFalse(seeds['holdout'] & seeds['stress'])

    def test_holdout_gate_requires_the_exact_reviewed_freeze_hash(self):
        from run_growth_validation import verify_freeze
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);(out/'freeze_manifest.json').write_text('{}')
            for value in (None,'wrong'):
                with self.assertRaises(ValueError):verify_freeze(out,value)

    def test_goal_mutation_is_rejected_before_any_holdout_execution(self):
        from run_growth_validation import verify_freeze, digest
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            files={'protocol_sha256':'pre_run_plan.json','goals_sha256':'goals.json',
                'selection_sha256':'frozen_selection.json','calibration_runs_sha256':'calibration_runs.jsonl.gz',
                'calibration_traces_sha256':'calibration_traces.json.gz','calibration_manifest_sha256':'calibration_manifest.json',
                'tests_manifest_sha256':'tests_manifest.json'}
            # Minimal constructed gate files: rejection must occur at the
            # changed-goal hash, before parsing or claiming valid game results.
            for name in files.values():(out/name).write_text('unchanged boundary fixture')
            freeze={'schema':'v12-growth-freeze-1','holdout_not_executed':True,
                    **{key:digest(out/name) for key,name in files.items()}}
            (out/'freeze_manifest.json').write_text(json.dumps(freeze))
            approved=digest(out/'freeze_manifest.json')
            (out/'goals.json').write_text('changed after review')
            with self.assertRaises(AssertionError):verify_freeze(out,approved)


if __name__=='__main__':
    unittest.main()
