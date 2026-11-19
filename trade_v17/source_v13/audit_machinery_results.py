"""Independent, read-only v6 result audit; does not import or run the game.

Usage: python3 audit_machinery_results.py --results machinery_results
The audit writes only its own JSON report. Missing final files are reported as
pending, not represented as a completed audit. Pilot games are kept separate.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

GOODS = ('banana', 'wheat', 'fuel', 'ore', 'machine', 'electronics')
RAW = ('ore', 'fuel')
ORIGINAL = ('Tropia', 'Grainia', 'Oilia', 'Mechania', 'Mineria', 'Technia')


def read_json(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def read_lines(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def mode(row):
    return row.get('mode', row.get('variant'))


def identity(row):
    return (row.get('phase', 'pilot'), mode(row), row.get('seed'),
            row.get('focal'), row.get('style', 'normal'))


class Audit:
    def __init__(self):
        self.checks = 0
        self.errors = []
        self.counts = Counter()

    def check(self, condition, label, detail=None):
        self.checks += 1
        if not condition:
            self.errors.append({'check': label, 'detail': detail})

    def equal(self, actual, expected, label, detail=None):
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            ok = math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8)
        else:
            ok = actual == expected
        self.check(ok, label, {'context': detail, 'actual': actual, 'expected': expected})

    def run_summary(self, row):
        key = identity(row)
        countries = row['countries']
        world = row['world']
        self.counts['run_summaries'] += 1
        self.equal(len(countries), 9, 'country_count', key)
        for name, c in countries.items():
            context = (key, name)
            self.equal(c['cash'], c['start_cash'] + c['revenue'] - c['purchases']
                       - c['investment'] + c['tax'], 'country_cash', context)
            self.equal(sum(c['purchase_by_good'].values()), c['purchases'], 'purchase_sum', context)
            self.equal(sum(c['sale_by_good'].values()), c['revenue'], 'sale_sum', context)
            self.equal(sum(c['export_used_by_good'].values()), c['useful_exports'], 'useful_export_sum', context)
            self.equal(sum(c['end_stock_by_good'].values()), c['stock'], 'stock_sum', context)
            self.equal(sum(c['machine_produced_by_gen'].values()), c['produced'].get('machine', 0), 'machine_grade_production', context)
            self.equal(sum(c['machine_stock_by_gen'].values()), c['end_stock_by_good']['machine'], 'machine_grade_stock', context)
            self.check(c['cash'] >= 0, 'nonnegative_cash', context)
            self.check(0 <= c['equipment_extra_output'] <= c['equipment_use_episodes'] <= 9,
                       'equipment_output_bound', context)
            for raw in RAW:
                self.check(c['production_raw'][raw] >= 0 and c['research_raw'][raw] >= 0,
                           'nonnegative_raw_consumption', context)
        self.equal(sum(c['cash'] for c in countries.values()), world['cash_total'], 'world_cash_sum', key)
        self.equal(world['cash_total'], world['initial_cash'] + world['tax'] - world['investment'], 'world_cash_conservation', key)
        self.equal(sum(c['tax'] for c in countries.values()), world['tax'], 'world_income_sum', key)
        self.equal(sum(c['investment'] for c in countries.values()), world['investment'], 'world_investment_sum', key)
        self.equal(sum(c['imports'] for c in countries.values()), world['trade_units'], 'trade_import_count', key)
        self.equal(sum(c['exports'] for c in countries.values()), world['trade_units'], 'trade_export_count', key)
        self.equal(statistics.mean(c['happy'] for c in countries.values()), world['happy'], 'world_happiness', key)
        self.equal(max(c['cash'] for c in countries.values()) - min(c['cash'] for c in countries.values()),
                   world['all_country_cash_gap'], 'nine_country_gap', key)
        for good in GOODS:
            self.equal(sum(c['produced'].get(good, 0) for c in countries.values()),
                       world['production'].get(good, 0), 'world_production_sum', (key, good))
            self.equal(sum(c['end_stock_by_good'][good] for c in countries.values()),
                       world['remaining_goods'].get(good, 0), 'world_inventory_sum', (key, good))
        for field in ('equipment_use_episodes', 'equipment_extra_output', 'machine_upkeep_ore',
                      'material_work_left', 'machine_unique_used', 'machine_missing_episodes'):
            self.equal(sum(c[field] for c in countries.values()), world[field], 'world_metric_sum', (key, field))

    def ledger(self, rows, result, context):
        self.counts['ledger_games'] += 1
        self.counts['ledger_rows'] += len(rows)
        self.equal(len(rows), 81, 'ledger_row_count', context)
        self.equal(len({(r['round'], r['country']) for r in rows}), 81, 'ledger_row_uniqueness', context)
        for name, country in result['countries'].items():
            selected = sorted((r for r in rows if r['country'] == name), key=lambda r:r['round'])
            self.equal([r['round'] for r in selected], list(range(1, 10)), 'ledger_rounds', (context, name))
            if not selected:
                continue
            self.equal(selected[0]['cash_start'], country['start_cash'], 'ledger_initial_cash', (context, name))
            self.equal(selected[-1]['cash_end'], country['cash'], 'ledger_final_cash', (context, name))
            for before, after in zip(selected, selected[1:]):
                self.equal(before['cash_end'], after['cash_start'], 'ledger_continuity', (context, name, after['round']))
            for r in selected:
                ctx = (context, name, r['round'])
                self.equal(r['cash_end'], r['cash_start'] + r['sales'] - r['purchases']
                           - r['investment'] + r['operating_income'], 'round_cash', ctx)
                self.equal(sum(r['purchase_by_good'].values()), r['purchases'], 'round_purchase_goods', ctx)
                self.equal(sum(r['sale_by_good'].values()), r['sales'], 'round_sale_goods', ctx)
            for local, final in (('sales', 'revenue'), ('purchases', 'purchases'),
                                 ('investment', 'investment'), ('operating_income', 'tax')):
                self.equal(sum(r[local] for r in selected), country[final], 'ledger_total', (context, name, final))
            self.equal(statistics.mean(r['happy'] for r in selected), country['happy'], 'ledger_happiness', (context, name))

    def trace(self, trace, result, context):
        """Reconcile original unit records, transactions, consumption and credit chains."""
        self.counts['detailed_traces'] += 1
        units = {int(k):v for k,v in trace['units'].items()}
        txs = trace['transactions']
        world = result['world']
        countries = result['countries']
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
            self.equal(key, (e['country'], e['raw'], e['generation']), 'credit_key_scope', context)
            self.equal(e['credits_before'], credits[key], 'credit_chain_before', (context, key))
            expected_spent = max(0, e['quantity'] - 1) if e['generation'] == 1 else e['quantity'] * (1 if e['generation'] == 2 else 2)
            self.equal(e['credits_spent'], expected_spent, 'recipe_work_cost', (context, key))
            self.equal(e['credits_after'], e['credits_before'] + 2 * e['raw_spent'] - e['credits_spent'], 'prepaid_material_balance', (context, key))
            self.check(0 <= e['credits_after'] < 2, 'credit_remainder_bound', (context, key))
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


def pilot_table(rows):
    answer = {}
    for m in sorted({mode(r) for r in rows}):
        selected = [r for r in rows if mode(r) == m]
        fields = ('cash', 'happy', 'equipment_use_episodes', 'equipment_extra_output',
                  'machine_upkeep_ore', 'upkeep_blocked', 'useful_exports')
        answer[m] = {'n':len(selected), 'countries':{
            name:{field:statistics.mean(r['countries'][name][field] for r in selected) for field in fields}
            for name in selected[0]['countries']}}
    return answer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=Path(__file__).parent/'machinery_results')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    folder = args.results.resolve()
    audit = Audit()
    report = {'scope':'Independent saved-record audit; no game engine imported or executed.', 'warnings':[]}
    pilot = folder/'pilot.json'
    if pilot.exists():
        pilot_rows = read_json(pilot)
        report['pilot'] = pilot_table(pilot_rows)
        report['pilot_games'] = len(pilot_rows)
    path = folder/'runs.jsonl.gz'
    if not path.exists():
        report.update(status='pending_final_results', pending=['runs.jsonl.gz', 'round_ledgers.jsonl.gz', 'first_seed_traces.json.gz'])
    else:
        runs = read_lines(path)
        keys = [identity(r) for r in runs]
        audit.equal(len(keys), len(set(keys)), 'unique_game_keys')
        for row in runs:
            audit.run_summary(row)
        report['completed_runs'] = len(runs)
        report['groups'] = {str(k):v for k,v in Counter((r.get('phase'), mode(r), r.get('style')) for r in runs).items()}
        main_rows = {(mode(r), r['seed']):r for r in runs if r.get('phase') == 'main'}
        ledger_path = folder/'round_ledgers.jsonl.gz'
        if ledger_path.exists():
            ledgers = read_lines(ledger_path)
            for group in ledgers:
                k = (mode(group), group['seed'])
                audit.ledger(group['rows'], main_rows[k], k)
            audit.equal(len(ledgers), len(main_rows), 'main_ledger_coverage')
        else:
            report['warnings'].append('Detailed round ledger unavailable; not audited.')
        trace_path = folder/'first_seed_traces.json.gz'
        if trace_path.exists():
            traces = read_json(trace_path)
            for name, trace in traces.items():
                if 'trace' in trace:
                    payload = trace['trace']; m = mode(trace) or name; seed = trace.get('seed')
                else:
                    payload = trace; m = name; seed = None
                choices = [r for (mm,ss),r in main_rows.items() if mm == m and (seed is None or ss == seed)]
                result = min(choices, key=lambda r:r['seed'])
                audit.trace(payload, result, (m, result['seed']))
        else:
            report['warnings'].append('Detailed unit/credit traces unavailable; not audited.')
        manifest_path = folder/'run_manifest.json'
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            audit.equal(len(runs), manifest['completed_games'], 'manifest_game_count')
            for filename, digest in manifest.get('source_sha256', {}).items():
                source = folder.parent/filename
                audit.equal(hashlib.sha256(source.read_bytes()).hexdigest(), digest, 'source_hash', filename)
        report['status'] = 'passed' if not audit.errors and not report['warnings'] else 'failed' if audit.errors else 'partial'
    report['audit_counts'] = dict(audit.counts)
    report['checks_evaluated'] = audit.checks
    report['errors'] = audit.errors
    target = args.out or folder/'independent_audit.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status':report['status'], 'counts':report['audit_counts'],
                      'errors':len(audit.errors), 'report':str(target)}, ensure_ascii=False))
    return 1 if audit.errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
