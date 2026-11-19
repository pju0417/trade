"""Meaningful v13 policy, recipe, accounting and staged-experiment boundaries.

Constructed scarce-wallet/recipe states are test fixtures, never pilot or formal
games. The existing 375 tests and the 76 inherited Python files remain intact.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from causal_engine import Game, MODES
from growth_scoring import Game as V12Game
from reference_engine import GOODS, NAMES

ROOT = Path(__file__).resolve().parent


class CausalTests(unittest.TestCase):
    def transfer(self, game, seller, buyer, good, amount, action):
        uid = game.ids(game.cs[seller], good)[0]
        self.assertTrue(game.settle_transaction(
            [{'seller': seller, 'buyer': buyer, 'ids': [uid]}],
            (buyer, seller, amount), 'direct', action))

    def scarce_wallet(self, mode, cash=85, electronics_price=70):
        game = Game(98010, mode=mode)
        game.r = 2
        actor = game.cs['Technia']
        self.transfer(game, 'Grainia', actor.name, 'wheat', actor.cash-cash, 'fixture:wallet')
        for good in ('ore', 'fuel'):
            game.consume(actor, good, game.count(actor, good), 'fixture')
        game.plan_cache[(2, actor.name)] = None
        game.plan(actor)
        for seller, good, price in (('Novia', 'electronics', electronics_price), ('Mineria', 'ore', 20)):
            nation = game.cs[seller]
            game.mint(nation, good, 4, initial=True)
            game.make_order(nation, game.ids(nation, good), price)
        return game, actor

    @staticmethod
    def unchanged_projection(result):
        result = copy.deepcopy(result)
        for country in result['countries'].values():
            country.pop('causal', None)
            country.pop('economic_decomposition', None)
        result['world'] = {k: v for k, v in result['world'].items() if not k.startswith('causal_')}
        return result

    def test_all_76_inherited_python_files_are_byte_identical(self):
        expected = json.loads((ROOT / 'V12_PROVENANCE.json').read_text())['files']
        self.assertEqual(len(expected), 76)
        self.assertEqual(expected, {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in expected})

    def test_baseline_preserves_v12_economy_and_full_transaction_history(self):
        conditions = ((None, 'normal', {}), ('Technia', 'minimum', {}),
                      ('Mechania', 'idle', {'Technia': 'minimum'}), ('Mineria', 'invest', {}),
                      ('Technia', 'trade', {}))
        for offset, (focal, style, behaviors) in enumerate(conditions):
            with self.subTest(focal=focal, style=style):
                old = V12Game(98000+offset, focal=focal, style=style, behaviors=behaviors)
                new = Game(98000+offset, mode='baseline', focal=focal, style=style, behaviors=behaviors)
                expected, actual = old.run(), new.run()
                self.assertEqual(expected, self.unchanged_projection(actual))
                for field in ('units', 'orders', 'transactions', 'cash_ledger', 'raw_round_ledger',
                              'needs_ledger', 'development_log', 'route_records', 'routing_log',
                              'evaluation_attempts', 'price_history'):
                    self.assertEqual(getattr(old, field), getattr(new, field), field)

    def test_modes_are_exact_factor_combinations_and_reject_unknown_mode(self):
        expected = {
            'baseline': (False, False, 0), 'operating_first': (True, False, 0),
            'no_durable_boost': (False, True, 0), 'ai_combined': (True, True, 0),
            'electronics_input': (False, False, 1), 'combined_input': (True, True, 1),
        }
        self.assertEqual(set(MODES), set(expected))
        for name, policy in MODES.items():
            self.assertEqual(tuple(asdict(policy).values()), expected[name])
        with self.assertRaises(ValueError):
            Game(98005, mode='unknown')

    def test_initial_conditions_and_first_production_are_identical_in_all_modes(self):
        old = V12Game(98006)
        for mode in MODES:
            game = Game(98006, mode=mode)
            for field in ('opt', 'config', 'initial_cash', 'initial_assets', 'initial_capacity', 'starter_allocation'):
                self.assertEqual(getattr(old, field), getattr(game, field), (mode, field))
            self.assertEqual(old.units, game.units)
        old.r = 1
        old.production()
        for mode in MODES:
            game = Game(98006, mode=mode)
            game.r = 1
            game.production()
            self.assertEqual(old.units, game.units, mode)
            self.assertEqual(old.operation_inputs, game.operation_inputs, mode)
            game.verify()

    def test_ai_factors_change_no_recipe_price_or_upgrade_cost(self):
        old = V12Game(98007)
        for mode in ('operating_first', 'no_durable_boost', 'ai_combined'):
            game = Game(98007, mode=mode)
            for name, actor in game.cs.items():
                before = old.cs[name]
                for good in actor.levels:
                    self.assertEqual(game.upgrade_cost(actor, good), old.upgrade_cost(before, good))
                    self.assertEqual(game.upgrade_requirements(actor, good), old.upgrade_requirements(before, good))
                    for round_number in (1, 2, 9):
                        self.assertEqual(game.resource_requirements(actor, good, round_number), old.resource_requirements(before, good, round_number))
                for good in GOODS:
                    self.assertEqual(game.quote(good), old.quote(good))

    def test_input_factor_adds_one_same_raw_bundle_uniformly_only_from_level_two(self):
        baseline, candidate = Game(98008), Game(98008, mode='electronics_input')
        for name in candidate.cs:
            for level in (1, 2, 3, 4):
                left, right = copy.deepcopy(baseline.cs[name]), copy.deepcopy(candidate.cs[name])
                for actor in (left, right):
                    actor.levels['electronics'] = level
                    actor.bases.setdefault('electronics', 1)
                    actor.elec_tech = min(3, level)
                for round_number in (2, 3, 8, 9):
                    expected = baseline.resource_requirements(left, 'electronics', round_number)
                    actual = candidate.resource_requirements(right, 'electronics', round_number)
                    self.assertEqual(set(actual), set(expected))
                    self.assertEqual(sum(actual.values()) - sum(expected.values()), int(level >= 2), (name, level, round_number))
                    self.assertEqual(candidate.upgrade_requirements(right, 'electronics'), baseline.upgrade_requirements(left, 'electronics'))
                    self.assertEqual(candidate.upgrade_cost(right, 'electronics'), baseline.upgrade_cost(left, 'electronics'))

    def test_input_factor_does_not_touch_machine_material_credits_or_other_industries(self):
        old, new = Game(98009), Game(98009, mode='combined_input')
        for name in old.cs:
            for good in old.cs[name].levels:
                if good == 'electronics':
                    continue
                for round_number in (1, 2, 3):
                    self.assertEqual(old.resource_requirements(old.cs[name], good, round_number), new.resource_requirements(new.cs[name], good, round_number))
        self.assertEqual(old.raw_policy, new.raw_policy)
        self.assertEqual(old.machinery_policy, new.machinery_policy)

    def test_projected_inputs_include_added_raw_before_upgrading_from_level_one(self):
        old, new = Game(98011), Game(98011, mode='electronics_input')
        old.r = new.r = 2
        left, right = old.cs['Technia'], new.cs['Technia']
        self.assertEqual(old.next_resources(left), new.next_resources(right))
        before = old.projected_resources(left, 'electronics')
        after = new.projected_resources(right, 'electronics')
        self.assertEqual(after['ore'], before['ore'] + 1)
        self.assertEqual(after['fuel'], before['fuel'])
        old.r = new.r = 9
        self.assertEqual(old.projected_resources(left, 'electronics'), {})
        self.assertEqual(new.projected_resources(right, 'electronics'), {})

    def test_scarce_wallet_reserves_operating_budget_before_living_electronics(self):
        allocations = {}
        for mode in ('baseline', 'operating_first'):
            game, actor = self.scarce_wallet(mode)
            plan = game.purchase_plan(actor)
            allocations[mode] = {row['good']: row['budget'] for row in plan if row['kind'] != 'replacement'}
            self.assertLessEqual(sum(r['budget'] for r in plan), actor.cash)
        self.assertEqual(allocations['baseline']['electronics'], 70)
        self.assertEqual(allocations['baseline']['ore'], 0)
        self.assertEqual(allocations['operating_first']['electronics'], 0)
        self.assertEqual(allocations['operating_first']['ore'], 20)

    def test_reserved_budget_changes_real_market_purchase_without_new_negotiation_order(self):
        for mode, expected in (('baseline', 'electronics'), ('operating_first', 'ore')):
            game, actor = self.scarce_wallet(mode)
            # Disable negotiation symmetrically in this market-only fixture so
            # barter does not remove the constructed cash scarcity.
            game.opt = replace(game.opt, negotiations=False)
            before = actor.imported.copy()
            game.buy_phase(actor, 0)
            self.assertEqual(actor.imported[expected] - before[expected], 1)
            other = 'ore' if expected == 'electronics' else 'electronics'
            self.assertEqual(actor.imported[other] - before[other], 0)
            game.verify()

    def test_operating_and_development_allocations_merge_into_one_raw_execution_row(self):
        game, actor = self.scarce_wallet('operating_first', electronics_price=50)
        target = {g: game.count(actor, g) for g in GOODS}
        target.update(ore=3, electronics=1)
        with patch.object(game, 'targets', return_value=target), patch.object(game, 'next_resources', return_value={'ore': 1}):
            rows = game.purchase_plan(actor)
            raw = [r for r in rows if r['good'] == 'ore']
            self.assertEqual(len(raw), 1)
            self.assertEqual(raw[0]['want'], 3)
            self.assertEqual(raw[0]['quantity'], 1)
            self.assertEqual(raw[0]['budget'], 20)
            ordinary = [r['good'] for r in rows if r['kind'] != 'replacement']
            self.assertEqual(ordinary, ['electronics', 'ore'])

    def test_research_only_shortage_does_not_receive_operating_priority(self):
        plans = []
        for mode in ('baseline', 'operating_first'):
            game, actor = self.scarce_wallet(mode)
            target = {g: game.count(actor, g) for g in GOODS}
            target.update(ore=2, electronics=1)
            with patch.object(game, 'targets', return_value=target), patch.object(game, 'next_resources', return_value={}):
                plans.append(game.purchase_plan(actor))
        self.assertEqual(plans[0], plans[1])
        self.assertEqual(next(r for r in plans[1] if r['good'] == 'ore')['budget'], 0)

    def test_food_is_budgeted_before_both_operating_inputs_and_living_goods(self):
        game, actor = self.scarce_wallet('operating_first', cash=20)
        target = {g: game.count(actor, g) for g in GOODS}
        target.update(wheat=target['wheat'] + 3, banana=target['banana'] + 3, ore=1, electronics=1)
        with patch.object(game, 'targets', return_value=target), patch.object(game, 'next_resources', return_value={'ore': 1}):
            rows = game.purchase_plan(actor)
        self.assertTrue(all(r['good'] == 'wheat' for r in rows if r['budget']))
        self.assertEqual(sum(r['budget'] for r in rows), 20)

    def test_purchase_budget_is_repeatable_and_economic_state_pure(self):
        game, actor = self.scarce_wallet('ai_combined')
        first = game.purchase_plan(actor)
        before = copy.deepcopy(game.__dict__)
        self.assertEqual(first, game.purchase_plan(actor))
        self.assertEqual(before, game.__dict__)
        self.assertFalse(game.causal_buy_log)

    def test_combined_raw_row_limits_barter_to_original_total_shortage(self):
        game, actor = self.scarce_wallet('operating_first', cash=15)
        target = {g: game.count(actor, g) for g in GOODS}
        target.update(ore=2)
        calls = []
        def barter(country, good, want, **kwargs):
            calls.append((good, want, kwargs['budget']))
            return want if good == 'ore' else 0
        with patch.object(game, 'targets', return_value=target), patch.object(game, 'next_resources', return_value={'ore': 1}), \
             patch.object(game, 'negotiate', side_effect=barter), patch.object(game, 'market_buy', return_value=0):
            game.buy_phase(actor, 0)
        self.assertEqual([x for x in calls if x[0] == 'ore'], [('ore', 2, 0)])
        self.assertEqual(len([r for r in game.causal_buy_log[-1]['rows'] if r['good'] == 'ore']), 1)

    def test_optional_replacement_remains_last_and_qualifying_machine_grade_is_kept(self):
        game = Game(98012, mode='operating_first')
        game.r = 3
        actor = game.cs['Technia']
        actor.levels['electronics'] = 2
        actor.elec_tech = 2
        game.plan_cache[(3, actor.name)] = 'electronics'
        game.plan(actor)
        game.mint(actor, 'electronics', 1, gen=1, initial=True)
        game.global_gen['electronics'] = 3
        rows = game.purchase_plan(actor)
        machine = [r for r in rows if r['good'] == 'machine']
        self.assertTrue(machine)
        self.assertEqual(machine[0]['min_gen'], 2)
        self.assertEqual(rows[-1]['kind'], 'replacement')
        self.assertEqual(rows[-1]['good'], 'electronics')

    def test_no_boost_removes_only_early_durable_multiplier(self):
        game = Game(98013, mode='no_durable_boost')
        game.r = 3
        actor = game.cs['Technia']
        game.plan(actor)
        candidates = game.causal_plan_log[-1]['candidates']
        self.assertEqual({r['good'] for r in candidates}, set(actor.levels))
        for row in candidates:
            if row['good'] in ('machine', 'electronics'):
                self.assertEqual(row['original_boost'], 1.8)
                expected_difference = .8 * row['base_price'] * row['marginal'] * row['remaining'] / row['cost'] / row['saturation'] * row['expansion_factor']
                self.assertAlmostEqual(row['original_score_same_state'] - row['score'], expected_difference)
            else:
                self.assertEqual(row['original_score_same_state'], row['score'])

    def test_late_durable_multiplier_and_existing_plan_cache_are_not_rewritten(self):
        game = Game(98014, mode='no_durable_boost')
        game.r = 3
        actor = game.cs['Technia']
        actor.levels['electronics'] = 3
        actor.elec_tech = 3
        first = game.plan(actor)
        row = next(c for c in game.causal_plan_log[-1]['candidates'] if c['good'] == 'electronics')
        self.assertEqual(row['original_boost'], 1)
        self.assertEqual(row['original_score_same_state'], row['score'])
        before = copy.deepcopy((game.plan_cache, game.routing_log, game.causal_plan_log))
        self.assertEqual(first, game.plan(actor))
        self.assertEqual(before, (game.plan_cache, game.routing_log, game.causal_plan_log))

    def test_no_boost_keeps_routing_base_and_selected_plan_separate(self):
        game = Game(98015, mode='ai_combined')
        game.r = 2
        actor = game.cs['Technia']
        selected = game.plan(actor)
        self.assertEqual(game.routing_log[-1]['base_plan'], game.causal_plan_log[-1]['selected_base'])
        self.assertEqual(selected, game.routing_log[-1]['selected'])
        self.assertEqual(selected, game.plan_cache[(2, actor.name)])

    def test_late_round_and_trade_idle_styles_do_not_gain_investment_plans(self):
        for style in ('trade', 'idle'):
            game = Game(98016, mode='ai_combined', focal='Technia', style=style)
            game.r = 3
            self.assertIsNone(game.plan(game.cs['Technia']))
            self.assertFalse(game.causal_plan_log)
        game = Game(98016, mode='no_durable_boost')
        game.r = 8
        self.assertIsNone(game.plan(game.cs['Technia']))
        self.assertFalse(game.causal_plan_log)

    def test_raw_refusal_filters_are_not_bypassed_by_priority_policy(self):
        game = Game(98017, mode='operating_first', focal='Technia', style='no_raw')
        game.r = 3
        actor = game.cs['Technia']
        for good in ('ore', 'fuel'):
            game.consume(actor, good, game.count(actor, good), 'fixture')
        self.assertFalse(any(row['good'] in ('ore', 'fuel') for row in game.purchase_plan(actor)))

    def test_new_modes_preserve_no_trade_and_idle_action_boundaries(self):
        for mode in ('ai_combined', 'combined_input'):
            game = Game(98018, mode=mode, trade_enabled=False)
            result = game.run()
            self.assertEqual(result['world']['transactions'], 0)
            game = Game(98019, mode=mode, focal='Mineria', style='idle')
            result = game.run()['countries']['Mineria']
            self.assertEqual(result['imports'] + result['exports'] + result['investment'], 0)
            self.assertGreater(sum(result['produced'].values()), 0)

    def test_post_game_decomposition_reconciles_cash_outputs_and_raw_inputs(self):
        game = Game(98020, mode='combined_input')
        result = game.run()
        before = copy.deepcopy(game.__dict__)
        self.assertEqual(result, game.summary())
        self.assertEqual(before, game.__dict__)
        for name, country in result['countries'].items():
            decomposition = country['economic_decomposition']
            self.assertEqual(sum(v['cash_sales'] for v in decomposition.values()), country['revenue'])
            self.assertEqual(sum(v['cash_purchases'] for v in decomposition.values()), country['purchases'])
            self.assertEqual(sum(v['investment_cash'] for v in decomposition.values()), country['investment'])
            for good, values in decomposition.items():
                self.assertEqual(values['produced'], country['produced'].get(good, 0))
                self.assertEqual(values['used'], country['use_by_good'][good])
                self.assertAlmostEqual(sum(values['cash_sales_by_generation'].values()), values['cash_sales'])
                self.assertAlmostEqual(sum(values['cash_sale_origin'].values()), values['cash_sales'])
            for raw in ('ore', 'fuel'):
                self.assertEqual(sum(v['production_raw_inputs'][raw] for v in decomposition.values()), country['production_raw'][raw])

    def test_full_game_diagnostics_count_selected_all_industry_opportunities(self):
        from run_causal_validation import validate_causal_records
        game = Game(98021, mode='ai_combined')
        result = game.run()
        validate_causal_records(game, result)
        self.assertTrue(any(c['causal']['legal_planned_attempts'] > c['evaluation']['machine_attempts'] for c in result['countries'].values()))
        for name, country in result['countries'].items():
            self.assertEqual(country['causal']['successful_attempts'], country['upgrades_total'])

    def test_actual_new_recipe_and_fixed_targets_pass_all_inherited_ledger_checks(self):
        from run_causal_validation import run_one
        for mode in ('baseline', 'operating_first', 'no_durable_boost', 'ai_combined', 'electronics_input', 'combined_input'):
            record, cash, raw, trace = run_one(('main', mode, 98022, 'None:normal', None, 'normal', ()))
            self.assertEqual(len(cash['rows']), 81)
            self.assertEqual(len(raw['rows']), 81)
            self.assertIsNone(trace)
            self.assertEqual(record['world']['uncovered_investments'], 0)
            for name, country in record['countries'].items():
                self.assertEqual(set(country['growth_evaluation']), {'targets'})
                if name not in NAMES:
                    self.assertIsNone(country['score'])
                    self.assertIsNone(country['growth_evaluation']['targets'])

    def test_exact_staged_schedule_is_unique_and_keeps_test_seeds_separate(self):
        from run_causal_validation import build_tasks, representative
        tasks = build_tasks()
        self.assertEqual(len(tasks), 5100)
        self.assertEqual(len(set(tasks)), 5100)
        self.assertEqual(sum(representative(task) for task in tasks), 156)
        expected = {'pilot_ai': 120, 'pilot_economic': 60, 'main': 600, 'stress': 4320}
        for phase, count in expected.items():
            self.assertEqual(sum(task[0] == phase for task in tasks), count)
        self.assertFalse(any(98000 <= task[2] <= 98099 for task in tasks))
        stress = {t[3] for t in tasks if t[0] == 'stress'}
        self.assertEqual(len(stress), 24)
        self.assertIn('Mineria:idle+Grainia:normal+Technia:minimum', stress)

    def test_factorial_contrast_preserves_all_four_same_seed_terms(self):
        from run_causal_validation import comparison_definitions
        groups = {f'main:{mode}:None:normal': [] for mode in MODES}
        definitions = comparison_definitions(groups)
        self.assertEqual(definitions['main:ai_interaction:None:normal']['terms'], {
            'main:ai_combined:None:normal': 1, 'main:operating_first:None:normal': -1,
            'main:no_durable_boost:None:normal': -1, 'main:baseline:None:normal': 1})
        self.assertEqual(definitions['main:ai_combined->combined_input:None:normal']['terms'], {
            'main:ai_combined:None:normal': -1, 'main:combined_input:None:normal': 1})

    def test_wrong_approval_cannot_launch_later_stages_or_overwrite_saved_runs(self):
        from run_causal_validation import economic_pilot, verify_freeze, preserve_absent
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'ai_pilot_manifest.json').write_text('{}')
            (path / 'freeze_manifest.json').write_text('{}')
            with self.assertRaises(AssertionError):
                economic_pilot(path, 1, 'unreviewed')
            with self.assertRaises(AssertionError):
                verify_freeze(path, 'unreviewed')
            with self.assertRaises(FileExistsError):
                preserve_absent(path, ['ai_pilot_manifest.json'])
            self.assertFalse((path / 'economic_pilot_start.json').exists())


if __name__ == '__main__':
    unittest.main()
