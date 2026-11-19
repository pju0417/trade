"""Independent v8 saved-record audit; never imports or executes the game.

Inherited v7 record checks are reused with the declared price-advice mode.
The v6 physical-record audit is copied with only its material-credit constant
parameterized. Raw inventory, provenance and starter assets are then checked
against saved units, transactions and per-round records.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from audit_machinery_results import read_json, read_lines, mode, identity, GOODS, ORIGINAL
from audit_recommendation_results import Audit as RecommendationAudit, channel_ledger, analysis as advice_analysis, INITIAL_PRICE

RAW = ('ore', 'fuel')
SOURCES = ('initial_own', 'initial_foreign', 'produced_own', 'produced_foreign')
REFUSALS = {'no_ore':('ore',), 'no_fuel':('fuel',), 'no_raw':RAW}
POLICIES = {'baseline':(2, 'legacy'), 'starter':(2, 'first_cycle'), 'bridge':(2, 'two_cycles'),
            'recipe':(1, 'legacy'), 'coupled':(1, 'first_cycle'),
            'no_starter':(2, 'none'), 'strict_no_starter':(1, 'none')}
ECON_GOALS = dict(zip(ORIGINAL, (250, 240, 140, 160, 140, 160)))
RAW_COUNT_FIELDS = ('consumed', 'production', 'research', 'imported_used')+SOURCES
RAW_FLOW_FIELDS = ('imports', 'exports', 'purchases', 'sales')


def price_result(row):
    """Only advice lookup metadata changes; all recorded game values stay intact."""
    return {**row, 'mode':'price'}


def starter_expected(profile, name):
    if profile == 'legacy' and name in ('Mechania', 'Technia', 'Novia'):
        return {'ore':1, 'fuel':1}
    if profile in ('first_cycle', 'two_cycles') and name in ('Technia', 'Novia'):
        return {'ore':1, 'fuel':int(profile == 'two_cycles')}
    return {'ore':0, 'fuel':0}


def raw_counts(uses):
    return {'consumed':len(uses),
            'production':sum(e['purpose'] == 'production' for e in uses),
            'research':sum(e['purpose'] == 'development' for e in uses),
            'imported_used':sum(e['import_transaction'] is not None for e in uses),
            **{source:sum(e['source'] == source for e in uses) for source in SOURCES}}


class Audit(RecommendationAudit):
    def __init__(self):
        super().__init__()
        self.cash_snapshots = {}

    def ledger(self, rows, result, context):
        super().ledger(rows, result, context)
        for row in rows:
            self.cash_snapshots[(context,row['round'],row['country'])] = (
                row['cash_end'],row['happy'],tuple(row['stock'][g] for g in RAW))

    def run_summary(self, row):
        super().run_summary(price_result(row))
        key = identity(row)
        expected = POLICIES[mode(row)]
        policy = row['world']['raw_policy']
        self.equal((policy['machine_credits'], policy['starter']), expected, 'declared_raw_policy', key)
        self.equal(row['world']['planning_decisions'], 0, 'all_modes_keep_v7_price_planning', key)
        for name, c in row['countries'].items():
            ctx = (key, name)
            self.equal(c['starter_raw'], starter_expected(policy['starter'], name), 'starter_contract', ctx)
            for raw in RAW:
                use = c['raw_use'][raw]
                self.equal(sum(use[source] for source in SOURCES), use['consumed'], 'source_partition', (ctx, raw))
                self.equal(use['production']+use['research'], use['consumed'], 'raw_purpose_partition', (ctx, raw))
                self.equal(use['production'], c['production_raw'][raw], 'raw_production_purpose', (ctx, raw))
                self.equal(use['research'], c['research_raw'][raw], 'raw_research_purpose', (ctx, raw))
                self.check(0 <= use['imported_used'] <= use['consumed'], 'imported_use_subset', (ctx, raw))
                self.check(use['initial_foreign']+use['produced_foreign'] <= use['imported_used'],
                           'foreign_origin_has_import_history', (ctx, raw))
                self.check(0 <= c['raw_import_rounds'][raw] <= 9, 'import_round_bound', (ctx, raw))
                self.equal(c['raw_importing'][raw], int(c['import_goods'].get(raw, 0)>0), 'raw_import_indicator', (ctx, raw))
                self.equal(c['first_raw_import_round'][raw] <= 9, bool(c['raw_importing'][raw]), 'import_sentinel', (ctx, raw))
                self.check(0 <= c['initial_raw_left'][raw] <= c['end_stock_by_good'][raw], 'initial_goods_currently_held', (ctx, raw))
                if row.get('focal') == name and raw in REFUSALS.get(row.get('style'), ()):
                    self.equal(c['import_goods'].get(raw, 0), 0, 'refused_raw_never_imported', (ctx, raw))
            self.equal(c['end_asset_value'], c['cash_plus_stock_value']+.45*c['investment'], 'asset_definition', ctx)
            self.check(c['start_asset_value'] >= c['start_cash'], 'initial_assets_include_actual_grants', ctx)
            if name in ORIGINAL:
                expected_econ = min(20, max(0, (c['end_asset_value']-c['start_asset_value'])/ECON_GOALS[name]*20))
                # Frozen v7 price reserves use 2*food_need(9)*10+20 = 80G.
                expected_econ += min(5, max(0, c['cash']/80*5))
                self.equal(c['economic'], expected_econ, 'economic_score_actual_starter_anchor', ctx)
            for good, field in (('machine','machine_gen'), ('electronics','elec_gen')):
                for grade in (2,3):
                    self.equal(c[f'{good}_g{grade}'], int(c['end_levels'].get(good, 0)>0 and c[field] >= grade),
                               'technology_success_indicator', (ctx, good, grade))
        world = row['world']; countries = row['countries']
        for field in ('starter_raw', 'initial_raw_left', 'raw_importing', 'raw_import_rounds', 'raw_unmet_production'):
            for raw in RAW:
                self.equal(world[field][raw], sum(c[field][raw] for c in countries.values()), 'raw_world_map_sum', (key, field, raw))
        for raw in RAW:
            for field in RAW_COUNT_FIELDS:
                self.equal(world['raw_use'][raw][field], sum(c['raw_use'][raw][field] for c in countries.values()),
                           'raw_world_use_sum', (key, raw, field))
            self.equal(world['starter_raw'][raw]+world['production'][raw],
                       world['raw_use'][raw]['consumed']+world['remaining_goods'][raw], 'world_raw_physical_conservation', (key, raw))
        for field in ('first_two_food_short', 'first_two_production_failures', 'first_round_production_failures',
                      'machine_free_basic', 'machine_g2', 'machine_g3', 'electronics_g2', 'electronics_g3'):
            self.equal(world[field], sum(c[field] for c in countries.values()), 'raw_world_scalar_sum', (key, field))
        for field in ('first_two_happy', 'first_round_happy'):
            self.equal(world[field], statistics.mean(c[field] for c in countries.values()), 'early_happy_mean', (key, field))
        self.equal(world['initial_asset_value'], sum(c['start_asset_value'] for c in countries.values()), 'world_start_asset_sum', key)
        self.equal(world['end_asset_value'], sum(c['end_asset_value'] for c in countries.values()), 'world_end_asset_sum', key)

    def raw_ledger(self, rows, result, context, detailed=False):
        prefix = 'detailed_raw' if detailed else 'raw'
        self.counts[prefix+'_ledger_games'] += 1
        self.counts[prefix+'_ledger_rows'] += len(rows)
        self.equal(len(rows), 81, 'raw_ledger_row_count', context)
        self.equal(len({(r['round'], r['country']) for r in rows}), 81, 'raw_ledger_unique_round_country', context)
        size = result['world']['raw_policy']['machine_credits']
        for name, c in result['countries'].items():
            selected = sorted((r for r in rows if r['country'] == name), key=lambda r:r['round'])
            self.equal([r['round'] for r in selected], list(range(1,10)), 'raw_ledger_rounds', (context, name))
            if not detailed:
                for row in selected:
                    self.equal((row['cash'],row['happy'],tuple(row['goods'][g]['stock'] for g in RAW)),
                               self.cash_snapshots[(context,row['round'],name)], 'raw_ledger_agrees_with_separate_cash_ledger',
                               (context,row['round'],name))
            for raw in RAW:
                previous = c['starter_raw'][raw]
                for row in selected:
                    g = row['goods'][raw]; ctx = (context, row['round'], name, raw)
                    self.equal(g['opening_stock'], previous, 'raw_stock_continuity', ctx)
                    self.equal(g['stock'], g['opening_stock']+g['produced']+g['imports']-g['exports']-g['consumed'],
                               'per_round_raw_physical_conservation', ctx)
                    self.equal(g['production']+g['research'], g['consumed'], 'round_raw_purpose_partition', ctx)
                    self.equal(sum(g[s] for s in SOURCES), g['consumed'], 'round_raw_source_partition', ctx)
                    for field in RAW_COUNT_FIELDS+RAW_FLOW_FIELDS+('opening_stock','produced','stock','unmet_production'):
                        self.check(type(g[field]) is int and g[field] >= 0, 'raw_ledger_nonnegative_integer', (ctx, field))
                    self.equal(set(g['machine_credits_by_grade']), {'1','2','3'}, 'raw_grade_credit_keys', ctx)
                    for generation, credit in g['machine_credits_by_grade'].items():
                        self.check(type(credit) is int and 0 <= credit < size, 'raw_per_grade_credit_bound', (ctx, generation))
                    previous = g['stock']
                self.equal(previous, c['end_stock_by_good'][raw], 'raw_ledger_final_stock', (context, name, raw))
                for field in RAW_COUNT_FIELDS:
                    self.equal(sum(r['goods'][raw][field] for r in selected), c['raw_use'][raw][field],
                               'raw_ledger_use_total', (context, name, raw, field))
                for local, summary in (('imports','import_goods'), ('exports','export_goods'),
                                       ('purchases','purchase_by_good'), ('sales','sale_by_good'), ('produced','produced')):
                    self.equal(sum(r['goods'][raw][local] for r in selected), c[summary].get(raw,0),
                               'raw_ledger_flow_total', (context, name, raw, local))
                import_rounds = [r['round'] for r in selected if r['goods'][raw]['imports']]
                self.equal(len(import_rounds), c['raw_import_rounds'][raw], 'raw_import_rounds_from_ledger', (context, name, raw))
                self.equal(min(import_rounds, default=10), c['first_raw_import_round'][raw], 'first_import_round_from_ledger', (context, name, raw))
                self.equal(sum(r['goods'][raw]['unmet_production'] for r in selected), c['raw_unmet_production'][raw],
                           'observed_industry_input_shortfalls', (context, name, raw))
            self.equal(sum(sum(v for v in selected[-1]['goods'][g]['machine_credits_by_grade'].values()) for g in RAW),
                       c['material_work_left'], 'final_credit_from_raw_ledger', (context, name))
            first_two = selected[:2]
            self.equal(statistics.mean(r['happy'] for r in first_two), c['first_two_happy'], 'first_two_happy_from_ledger', (context,name))
            self.equal(sum(not r['food_met'] for r in first_two), c['first_two_food_short'], 'first_two_food_from_ledger', (context,name))
            self.equal(sum(r['production_failures'] for r in first_two), c['first_two_production_failures'], 'first_two_failures_from_ledger', (context,name))
            self.equal(selected[0]['happy'], c['first_round_happy'], 'first_round_happy_from_ledger', (context,name))
            self.equal(selected[0]['production_failures'], c['first_round_production_failures'], 'first_round_failures_from_ledger', (context,name))
            self.equal(sum(r['production_failures'] for r in selected), c['production_failures'], 'all_failures_from_raw_ledger', (context,name))

    def physical_trace(self, trace, result, context):
        """Reconcile original unit records, transactions, consumption and credit chains."""
        self.counts['detailed_traces'] += 1
        units = {int(k):v for k,v in trace['units'].items()}
        txs = trace['transactions']
        world = result['world']
        countries = result['countries']
        size = result['world']['raw_policy']['machine_credits']
        self.equal(len(txs), world['transactions'], 'trace_transaction_count', context)
        self.equal(len({t['action_id'] for t in txs}), len(txs), 'transaction_id_uniqueness', context)
        for good in GOODS:
            initial = sum(u['good'] == good and u['born'] == 0 for u in units.values())
            produced = sum(u['good'] == good and u['born'] > 0 for u in units.values())
            consumed = sum(u['good'] == good and u['owner'] is None for u in units.values())
            held = sum(u['good'] == good and u['owner'] is not None for u in units.values())
            self.equal(initial + produced, consumed + held, 'physical_unit_balance', (context, good))
            self.equal(produced, world['production'].get(good, 0), 'trace_production', (context, good))
            self.equal(consumed, world['consumed'].get(good, 0), 'trace_consumption', (context, good))
            self.equal(held, world['remaining_goods'].get(good, 0), 'trace_stock', (context, good))
        money_in, money_out, trade_imports, trade_exports = Counter(), Counter(), Counter(), Counter()
        for t in txs:
            if t['cash']:
                buyer, seller, value = t['cash']
                money_in[seller] += value
                money_out[buyer] += value
            for leg in t['legs']:
                trade_imports[leg['buyer']] += len(leg['ids'])
                trade_exports[leg['seller']] += len(leg['ids'])
        for name, country in countries.items():
            self.equal(money_in[name], country['revenue'], 'trace_revenue', (context, name))
            self.equal(money_out[name], country['purchases'], 'trace_purchases', (context, name))
            self.equal(trade_imports[name], country['imports'], 'trace_imports', (context, name))
            self.equal(trade_exports[name], country['exports'], 'trace_exports', (context, name))
            for good in GOODS:
                self.equal(sum(u['owner'] == name and u['good'] == good for u in units.values()),
                           country['end_stock_by_good'][good], 'trace_country_stock', (context, name, good))
                self.equal(sum(u['origin'] == name and u['born'] > 0 and u['good'] == good and u['used'] for u in units.values()),
                           country['use_by_good'][good], 'trace_country_used', (context, name, good))
            for raw in RAW:
                for purpose, field in (('production', 'production_raw'), ('development', 'research_raw')):
                    n = sum(u['good'] == raw and u['owner'] is None and u['use_country'] == name
                            and u['use_purpose'] == purpose for u in units.values())
                    self.equal(n, country[field][raw], 'raw_consumption_purpose', (context, name, raw, purpose))
            upkeep = sum(u['good'] == 'ore' and u['owner'] is None and u['use_country'] == name
                         and u['use_purpose'] == 'maintenance' for u in units.values())
            self.equal(upkeep, country['machine_upkeep_ore'], 'maintenance_physical_consumption', (context, name))
        used_raw_ids = []
        for need in trace['needs_ledger']:
            if need['good'] not in RAW:
                continue
            for uid in need['used_ids']:
                u = units[uid]
                self.check(u['owner'] is None and u['good'] == need['good'], 'raw_need_has_consumed_unit', (context, uid))
                self.equal(u['use_country'], need['country'], 'raw_need_consumer', (context, uid))
                self.equal(u['use_round'], need['round'], 'raw_need_round', (context, uid))
                if need['purpose'].startswith('production:') or need['purpose'] == 'equipment_maintenance':
                    self.check(u['born'] < need['round'], 'no_same_round_raw_production_use', (context, uid))
                used_raw_ids.append(uid)
        consumed_raw_ids = {uid for uid,u in units.items() if u['good'] in RAW and u['owner'] is None}
        self.equal(len(used_raw_ids), len(set(used_raw_ids)), 'no_repeated_raw_consumption', context)
        self.equal(set(used_raw_ids), consumed_raw_ids, 'all_consumed_raw_has_need_record', context)

        machine_rows = {(r['round'], r['country']):r for r in trace['machine_output']}
        self.equal(len(machine_rows), len(trace['machine_output']), 'machine_row_uniqueness', context)
        credits, material_raw = Counter(), Counter()
        for e in trace['material_events']:
            key = tuple(e['key'])
            self.equal(e['credits_per_raw'], size, 'instance_credit_size', (context, key))
            self.equal(e['raw_spent'], math.ceil(max(0, e['credits_spent']-e['credits_before'])/size), 'minimal_physical_raw_batches', (context, key))
            self.equal(key, (e['country'], e['raw'], e['generation']), 'credit_key_scope', context)
            self.equal(e['credits_before'], credits[key], 'credit_chain_before', (context, key))
            expected_spent = max(0, e['quantity'] - 1) if e['generation'] == 1 else e['quantity'] * (1 if e['generation'] == 2 else 2)
            self.equal(e['credits_spent'], expected_spent, 'recipe_work_cost', (context, key))
            self.equal(e['credits_after'], e['credits_before'] + size * e['raw_spent'] - e['credits_spent'], 'prepaid_material_balance', (context, key))
            self.check(0 <= e['credits_after'] < size, 'credit_remainder_bound', (context, key))
            self.equal(e['raw_spent'], sum(e['required'].values()), 'material_raw_requirement', (context, key))
            output = machine_rows[(e['round'], e['country'])]
            self.equal(e['quantity'], output['produced'], 'material_funds_actual_output', (context, key))
            self.equal(e['raw_spent'], output['raw_used'].get(e['raw'], 0), 'material_matches_physical_recipe', (context, key))
            self.check(output['status'] != 'fallback', 'fallback_has_no_paid_recipe', (context, key))
            credits[key] = e['credits_after']
            material_raw[(e['country'], e['raw'])] += e['raw_spent']
        for name, country in countries.items():
            self.equal(sum(v for (n,raw,gen),v in credits.items() if n == name), country['material_work_left'], 'final_material_credit', (context, name))
        if trace['material_events']:
            for name in countries:
                for raw in RAW:
                    actual = sum(len(n['used_ids']) for n in trace['needs_ledger']
                                 if n['country'] == name and n['purpose'] == 'production:machine' and n['good'] == raw)
                    self.equal(material_raw[(name, raw)], actual, 'machine_material_vs_consumed_raw', (context, name, raw))
        for r in trace['machine_output']:
            if r['status'] == 'paused':
                self.check(r['produced'] == 0 and not r['raw_used'], 'pause_is_not_free_output', context)
            if r['status'] == 'fallback':
                self.check(r['generation'] == 1 and r['produced'] == 1 and not r['raw_used'], 'fallback_basic_only', context)

        wear = Counter()
        for e in trace['upkeep']:
            uid = e['unit']
            self.equal(e['wear_before'], wear[uid], 'wear_uid_continuity', (context, uid))
            self.equal(e['due'], e['wear_before'] >= 2, 'service_due_third_use', (context, uid))
            expected = (0 if e['due'] else e['wear_before'] + 1) if e['serviced'] else e['wear_before']
            self.equal(e['wear_after'], expected, 'wear_after_service', (context, uid))
            self.equal(e['ore_used'], int(e['due'] and e['serviced']), 'service_raw_charge', (context, uid))
            self.check(units[uid]['good'] == 'machine' and units[uid]['born'] < e['round'], 'service_existing_machine', (context, uid))
            wear[uid] = e['wear_after']
        for name, country in countries.items():
            eq = [e for e in trace['equipment_output'] if e['country'] == name]
            self.equal(sum(e['supported'] for e in eq), country['equipment_use_episodes'], 'actual_equipment_services', (context, name))
            self.equal(sum(e['extra_output'] for e in eq), country['equipment_extra_output'], 'actual_equipment_bonus', (context, name))
            self.equal(sum(e['ore_used'] for e in trace['upkeep'] if e['country'] == name), country['machine_upkeep_ore'], 'service_raw_log', (context, name))
        self.counts['trace_units'] += len(units)
        self.counts['material_events'] += len(trace['material_events'])
        self.counts['upkeep_events'] += len(trace['upkeep'])

    def trace(self, trace, result, context):
        self.physical_trace(trace, result, context)
        channels = channel_ledger(trace)
        self.trace_channels[str(context)] = channels
        for name, country in result['countries'].items():
            self.equal(channels.get(name, {ch:{f:0 for f in ('sold_units','bought_units','sales_cash','purchase_cash')}
                                            for ch in ('market','direct','barter')}), country['channel_stats'],
                       'actual_trace_channels', (context,name))
        self.audit_recommendations(trace, price_result(result), context)
        self.audit_raw_trace(trace, result, context)

    def audit_raw_trace(self, trace, result, context):
        units = {int(k):v for k,v in trace['units'].items()}
        uses = trace['raw_use']; rows = trace['raw_ledger']
        self.equal(trace['raw_policy'], result['world']['raw_policy'], 'trace_raw_policy', context)
        self.equal(len(uses), len({e['uid'] for e in uses}), 'each_raw_uid_consumed_once', context)
        self.equal({e['uid'] for e in uses}, {uid for uid,u in units.items() if u['good'] in RAW and u['owner'] is None},
                   'raw_log_covers_all_consumed_uid', context)
        self.counts['raw_consumption_events'] += len(uses)
        for e in uses:
            u = units[e['uid']]; ctx = (context,e['uid'])
            for field in ('good','born','origin'):
                self.equal(e[field], u[field], 'raw_use_unit_identity', (ctx,field))
            for local, unit in (('round','use_round'), ('country','use_country'), ('purpose','use_purpose'), ('import_transaction','last_import')):
                self.equal(e[local], u[unit], 'raw_use_unit_provenance', (ctx,local))
            source = ('initial_' if u['born'] == 0 else 'produced_')+('own' if u['origin'] == e['country'] else 'foreign')
            self.equal(e['source'], source, 'raw_origin_source_classification', ctx)
            if e['import_transaction'] is not None:
                tx = trace['transactions'][e['import_transaction']]
                self.check(tx['round'] <= e['round'] and any(leg['buyer'] == e['country'] and e['uid'] in leg['ids'] for leg in tx['legs']),
                           'raw_last_import_is_real_preceding_transfer', ctx)
        self.raw_ledger(rows, result, context, detailed=True)
        cash_rows = {(r['round'],r['country']):r for r in trace['cash_ledger']}
        credits = Counter()
        material_by_round = defaultdict(list)
        for e in trace['material_events']:
            material_by_round[e['round']].append(e)
        for row in sorted(rows, key=lambda r:(r['round'],r['country'])):
            r,name = row['round'],row['country']; ctx=(context,r,name)
            self.equal(row['cash'], cash_rows[(r,name)]['cash_end'], 'raw_cash_ledger_matches_cash_ledger', ctx)
            self.equal(row['happy'], cash_rows[(r,name)]['happy'], 'raw_happy_matches_cash_ledger', ctx)
            food = [n for n in trace['needs_ledger'] if n['round']==r and n['country']==name and n['purpose']=='food']
            self.equal({n['good'] for n in food}, {'banana','wheat'}, 'recorded_household_food_needs', ctx)
            expected_food_met = all(len(n['used_ids']) == n['needed'] for n in food)
            self.equal(row['food_met'], expected_food_met, 'food_met_from_consumed_uid', ctx)
            living = [n for n in trace['needs_ledger'] if n['round']==r and n['country']==name and n['purpose']=='living']
            self.equal(len(living), 1, 'one_household_electronics_need', ctx)
            if living:
                world_grade = max(u['gen'] for u in units.values() if u['good']=='electronics' and u['born']<=r)
                effective = sum((1,.8,.6)[min(2,max(0,world_grade-units[uid]['gen']))] for uid in living[0]['used_ids'])
                expected_happy = round(35+20*sum(len(n['used_ids'])/n['needed'] for n in food)
                                       +25*min(1,effective/living[0]['needed']),6)
                self.equal(row['happy'], expected_happy, 'happiness_from_food_and_equipment_use', ctx)
                self.equal(cash_rows[(r,name)]['operating_income'],10+math.floor(expected_happy/10+.5),
                           'satisfaction_income_from_actual_use', ctx)
            for good,field in (('machine','machine_generation'),('electronics','electronics_generation')):
                self.equal(row[field],min(3,max(1,cash_rows[(r,name)]['levels'].get(good,0))),
                           'raw_ledger_tech_matches_industry_level', (ctx,good))
            for raw in RAW:
                g = row['goods'][raw]
                local_uses = [e for e in uses if e['round']==r and e['country']==name and e['good']==raw]
                for field,value in raw_counts(local_uses).items():
                    self.equal(g[field], value, 'raw_round_use_from_uid', (ctx,raw,field))
                made = sum(u['origin']==name and u['good']==raw and u['born']==r for u in units.values())
                self.equal(g['produced'], made, 'raw_round_minted_uid_count', (ctx,raw))
                flows = Counter()
                for tx in trace['transactions']:
                    if tx['round'] != r:continue
                    for leg in tx['legs']:
                        if units[leg['ids'][0]]['good'] != raw:continue
                        if leg['buyer']==name:flows['imports'] += len(leg['ids'])
                        if leg['seller']==name:flows['exports'] += len(leg['ids'])
                    if tx['cash'] and units[tx['legs'][0]['ids'][0]]['good']==raw:
                        payer,payee,amount = tx['cash']
                        if payer==name:flows['purchases'] += amount
                        if payee==name:flows['sales'] += amount
                for field in RAW_FLOW_FIELDS:
                    self.equal(g[field], flows[field], 'raw_round_actual_transaction_flow', (ctx,raw,field))
                production = [p for p in trace['production'] if p['round']==r and p['country']==name]
                unmet = sum(max(0,p['required'].get(raw,0)-p['available_before'][raw]) for p in production)
                self.equal(g['unmet_production'], unmet, 'raw_shortfall_is_industry_snapshot_sum', (ctx,raw))
                self.equal(g['stock'], cash_rows[(r,name)]['stock'][raw], 'raw_end_stock_matches_cash_ledger', (ctx,raw))
                for generation in (1,2,3):
                    bank_key = (name,raw,generation)
                    events = [e for e in trace['material_events'] if tuple(e['key'])==bank_key and e['round']<=r]
                    credit = events[-1]['credits_after'] if events else 0
                    self.equal(g['machine_credits_by_grade'][str(generation)], credit, 'raw_credit_snapshot_matches_material_events', (ctx,raw,generation))
            failures = sum(not p['funded'] for p in trace['production'] if p['round']==r and p['country']==name)
            self.equal(row['production_failures'], failures, 'raw_failures_match_production_trace', ctx)
        for name,c in result['countries'].items():
            expected_initial = {raw:sum(u['origin']==name and u['good']==raw and u['born']==0 for u in units.values()) for raw in RAW}
            self.equal(trace['starter_allocation'][name], expected_initial, 'actual_initial_raw_uid_allocation', (context,name))
            self.equal(c['starter_raw'], expected_initial, 'summary_initial_raw_uid_allocation', (context,name))
            initial_assets = c['start_cash']+sum(INITIAL_PRICE[u['good']]*(1,1.4,1.8)[u['gen']-1]*.15
                                               for u in units.values() if u['origin']==name and u['born']==0)
            stock_value = sum(INITIAL_PRICE[u['good']]*(1,1.4,1.8)[u['gen']-1]
                              *(.5 if u['used'] and u['good'] in ('machine','electronics') else .15)
                              for u in units.values() if u['owner']==name)
            self.equal(c['start_asset_value'], initial_assets, 'initial_asset_value_from_actual_grants', (context,name))
            self.equal(c['cash_plus_stock_value'], c['cash']+stock_value, 'end_asset_value_from_actual_held_units', (context,name))
            for raw in RAW:
                initial_left = sum(u['owner']==name and u['good']==raw and u['born']==0 for u in units.values())
                self.equal(c['initial_raw_left'][raw], initial_left, 'initial_goods_held_include_foreign_starters', (context,name,raw))
                self.equal(c['raw_use'][raw], raw_counts([e for e in uses if e['country']==name and e['good']==raw]),
                           'raw_summary_from_uid_use_events', (context,name,raw))
            free_basic = sum(e['country']==name and e['generation']==1 and e['produced']==1
                             and not e['raw_used'] and e['status']=='regular' for e in trace['machine_output'])
            self.equal(c['machine_free_basic'], free_basic, 'free_regular_g1_separate_from_fallback', (context,name))


def summarize_raw(rows):
    """Descriptive and paired diagnostics from completed records only."""
    def stats(values):
        values = list(values)
        mean = statistics.mean(values)
        error = 1.96*statistics.stdev(values)/math.sqrt(len(values)) if len(values)>1 else 0
        return {'n':len(values), 'mean':mean, 'ci95':[mean-error,mean+error], 'min':min(values), 'max':max(values)}
    selected_fields = ('cash','happy','revenue','purchases','investment','score','economic','industry_capacity_score',
        'industry_use_score','useful_exports','machine_g2','machine_g3','electronics_g2','electronics_g3',
        'first_two_happy','first_two_food_short','first_two_production_failures','funding_blocks',
        'start_asset_value','end_asset_value','cash_plus_stock_value','material_work_left','machine_free_basic')
    output = {'main':{}, 'refusal_paired':{}, 'method_notes':[
        'All policy rows inherit v7 price advice; only declared starter grants and machine input intensity vary.',
        'Starter-source provenance is independent of imported_used; returned own-origin units can have import history.',
        'initial_raw_left means any currently held born=0 raw, including starters imported from another country.',
        'unmet_production is an industry-by-industry observed deficit, not a joint optimal procurement calculation.',
        'Asset values are the unchanged scoring valuation, not realizable liquidation proceeds.',
        'Refusal controls match the same mode and seed; no_raw/no_ore/no_fuel reject imports, not initial or domestic raw.',
        'Machine material-work is prepaid, grade/raw/country-scoped, and is not a cash subsidy or extra saleable inventory.',
    ]}
    for m in sorted({mode(r) for r in rows if r['phase']=='main'}):
        runs = [r for r in rows if r['phase']=='main' and mode(r)==m]
        entry = {'n':len(runs), 'countries':{}}
        for name in runs[0]['countries']:
            c = [r['countries'][name] for r in runs]
            entry['countries'][name] = {field:stats(x[field] for x in c) for field in selected_fields
                                       if all(x[field] is not None for x in c)}
            for field in ('starter_raw','initial_raw_left','raw_importing','raw_import_rounds','first_raw_import_round','raw_unmet_production'):
                entry['countries'][name][field] = {g:stats(x[field][g] for x in c) for g in RAW}
            entry['countries'][name]['raw_use'] = {g:{field:stats(x['raw_use'][g][field] for x in c) for field in RAW_COUNT_FIELDS} for g in RAW}
        output['main'][m] = entry
    controls = {(mode(r),r['seed']):r for r in rows if r['phase']=='stress' and r['style']=='normal' and r.get('focal') is None}
    for m in sorted({mode(r) for r in rows if r['phase']=='stress'}):
        output['refusal_paired'][m] = {}
        for name in ('Mechania','Technia','Novia'):
            for style in REFUSALS:
                selected = [r for r in rows if r['phase']=='stress' and mode(r)==m and r.get('focal')==name and r['style']==style]
                if not selected:continue
                before = [controls[(m,r['seed'])]['countries'][name] for r in selected]
                after = [r['countries'][name] for r in selected]
                entry = {field:stats(b[field]-a[field] for a,b in zip(before,after)) for field in selected_fields
                         if all(x[field] is not None for x in before+after)}
                entry['raw_use_delta'] = {g:{field:stats(b['raw_use'][g][field]-a['raw_use'][g][field]
                                                        for a,b in zip(before,after)) for field in RAW_COUNT_FIELDS} for g in RAW}
                output['refusal_paired'][m][name+':'+style] = entry
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=Path(__file__).parent/'raw_results')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    folder = args.results.resolve(); folder.mkdir(exist_ok=True)
    audit = Audit()
    report = {'scope':'Independent v8 saved-record audit; no engine or simulation execution.', 'warnings':[]}
    required = ('runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz',
                'first_seed_traces.json.gz','run_manifest.json')
    missing = [filename for filename in required if not (folder/filename).exists()]
    path = folder/'runs.jsonl.gz'
    if missing:
        report.update(status='pending_final_results', pending=missing)
    else:
        rows = read_lines(path)
        keys = [identity(r) for r in rows]
        audit.equal(len(keys), len(set(keys)), 'unique_game_keys')
        by_key = {identity(r):r for r in rows}
        for row in rows:audit.run_summary(row)
        report['completed_runs'] = len(rows)
        report['groups'] = {str(key):count for key,count in Counter((r['phase'],mode(r),r['style']) for r in rows).items()}
        main_rows = {(mode(r),r['seed']):r for r in rows if r['phase']=='main'}
        for filename, method in (('round_ledgers.jsonl.gz',audit.ledger), ('raw_round_ledgers.jsonl.gz',audit.raw_ledger)):
            path = folder/filename
            if not path.exists():
                report['warnings'].append(filename+' unavailable; not audited.'); continue
            groups = read_lines(path)
            ledger_keys = [(mode(g),g['seed']) for g in groups]
            audit.equal(len(ledger_keys), len(set(ledger_keys)), 'unique_ledger_game_keys', filename)
            audit.equal(set(ledger_keys), set(main_rows), 'all_main_games_have_ledger', filename)
            for group in groups:
                key = (mode(group),group['seed'])
                method(group['rows'], main_rows[key], key)
        traced_keys = []
        path = folder/'first_seed_traces.json.gz'
        if path.exists():
            for label,stored in read_json(path).items():
                key = identity(stored)
                audit.check(key in by_key, 'trace_matches_completed_game', (label,key))
                if key not in by_key:continue
                traced_keys.append(key)
                audit.trace(stored.get('trace',stored), by_key[key], key)
            audit.equal(len(traced_keys), len(set(traced_keys)), 'unique_detailed_trace_game_keys')
        else:
            report['warnings'].append('Detailed traces unavailable; physical UID/credit/advice/provenance checks not performed.')
        manifest_path = folder/'run_manifest.json'
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            for field in ('completed_games','planned_games'):
                audit.equal(len(rows), manifest[field], 'manifest_game_count', field)
            main_first,main_last = manifest['main_seed_range']
            stress_first,stress_last = manifest['stress_seed_range']
            expected_keys = {('main',m,s,None,'normal') for m in manifest['modes'] for s in range(main_first,main_last+1)}
            expected_keys |= {('stress',m,s,focal,style) for m in manifest['stress_modes']
                              for focal,style in manifest['stress_scenarios'] for s in range(stress_first,stress_last+1)}
            audit.equal(set(keys), expected_keys, 'complete_preregistered_game_schedule')
            expected_traces = {('main',m,main_first,None,'normal') for m in manifest['modes']}
            expected_traces |= {('stress',m,stress_first,focal,style) for m in manifest['stress_modes']
                                for focal,style in manifest['stress_scenarios'] if style in REFUSALS}
            audit.equal(set(traced_keys), expected_traces, 'complete_representative_main_and_refusal_traces')
            for filename,digest in manifest['source_sha256'].items():
                audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(),digest,'frozen_source_hash',filename)
        else:
            report['warnings'].append('Final manifest absent; schedule and source hashes not audited.')
        report['analysis'] = summarize_raw(rows)
        report['advice_score_analysis'] = advice_analysis(rows)
        report['audit_scope'] = {
            'summaries':'All saved games: cash, goods, channels, score components, raw use, starter policy and source totals.',
            'round_ledgers':'All saved main games: cash ledger and per-country raw inventory continuity, production, trade and consumption.',
            'detailed_traces':'Saved representative main and import-refusal games: physical UID, prepaid work, actual advice and raw provenance.',
            'not_claimed':['Economic fairness, an optimum raw recipe, observed student learning or multiplayer stability.',
                'Complete UID-level checking of games for which no detailed trace was saved.',
                'Liquidation value of inventory or guaranteed realization of the fixed investment valuation.',
                'Independently observed sequential rival-price snapshots; price arithmetic uses that recorded scalar.']}
        report['status'] = 'failed' if audit.errors else 'partial' if report['warnings'] else 'passed'
    report['audit_counts'] = dict(audit.counts)
    report['checks_evaluated'] = audit.checks
    report['errors'] = audit.errors
    target = args.out or folder/'independent_audit.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,
                                default=lambda value:sorted(value,key=repr) if isinstance(value,set) else repr(value)),encoding='utf-8')
    print(json.dumps({'status':report['status'],'counts':report['audit_counts'],'checks':audit.checks,
                      'errors':len(audit.errors),'report':str(target)},ensure_ascii=False))
    return int(bool(audit.errors))


if __name__ == '__main__':
    raise SystemExit(main())
