"""Independent v9 saved-record audit. Never imports or runs a game engine.

The unchanged v8 cash/raw/price audit is retained with its policy lookup mapped
to bridge. New checks reconstruct development, phase-correct import provenance,
latest-stage output attribution and all development metrics from saved records.
Only this audit's own JSON output is written.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

from audit_raw_results import Audit as RawAudit
from audit_machinery_results import read_json, read_lines, mode, identity, ORIGINAL
from audit_recommendation_results import analysis as score_analysis, stats

POLICIES = {'baseline':(False, False), 'supply':(True, False),
            'gate':(False, True), 'combined':(True, True)}
DURABLES = ('machine', 'electronics')
BEFORE_TRADE_USES = ('equipment', 'production', 'maintenance')
MACHINE_REFUSALS = {'no_high_machine':2, 'no_machine':1}
INVEST = {'banana':75, 'wheat':75, 'ore':95, 'fuel':95, 'machine':165, 'electronics':220}
GROWTH_GOALS = dict(zip(ORIGINAL, (.90, .90, .48, .25, .48, .27)))
MAIN_INDUSTRY = dict(zip(ORIGINAL, ('banana','wheat','fuel','machine','ore','electronics')),
                     Novia='electronics', Agrea='banana', Ferria='ore')
INITIAL_MACHINE_BASE = {'Mechania':2, 'Technia':1}
METRICS = (
    'upgrades', 'machine_required_upgrades', 'imported_machine_upgrades',
    'foreign_machine_upgrades', 'unique_imported_machines_development',
    'unique_foreign_machines_development', 'productive_upgrades',
    'used_output_upgrades', 'foreign_machine_productive_upgrades',
    'foreign_machine_used_output_upgrades', 'foreign_machine_output_units',
    'foreign_machine_output_used_units', 'foreign_machine_export_used_units',
    'bought_high_machines', 'bought_high_machine_unique',
    'foreign_produced_high_bought_unique', 'bought_high_machine_used_unique',
    'bought_high_machine_developed_unique', 'high_machine_purchase_cash',
    'sold_high_machines', 'high_machine_sales_cash', 'high_machine_produced',
    'high_machine_used', 'high_machine_useful_exports', 'high_machine_public_unique',
    'high_machine_ending_stock', 'high_machine_unused_stock',
    'g3_electronics_output', 'g3_electronics_used', 'g3_machine_output',
    'g3_machine_used', 'machine_condition_blocks',
)


def use_key(event):
    return event['round'], event['country'], event['uid'], event['purpose']


def development_cost(country, good, from_level):
    value = INVEST[good] * (1 if from_level < 2 else 1.5 if from_level == 2 else 2)
    if good == 'machine':
        value *= .75 if country == 'Mechania' else 1.25 if country == 'Technia' else 1
    return int(math.floor(value / 5 + .5)) * 5


class Audit(RawAudit):
    def __init__(self):
        super().__init__()
        self.chain_examples = []
        self.score_coverage = Counter()

    def run_summary(self, row):
        # v9's mode names describe supply/gate, not v8 raw policy changes.
        super().run_summary({**row, 'mode':'bridge'})
        key = identity(row)
        declared = row['world']['development_policy']
        self.equal((declared['sale_buffer'], declared['prior_machine']), POLICIES[mode(row)],
                   'declared_development_policy', key)
        self.equal(row['world']['development_variant'], mode(row), 'development_mode_identity', key)
        self.equal(row['world']['raw_policy'], {'machine_credits':2, 'starter':'two_cycles'},
                   'all_modes_keep_v8_bridge', key)
        for name, country in row['countries'].items():
            ctx = (key, name); d = country['development']
            self.equal(set(d), set(METRICS), 'complete_development_schema', ctx)
            for field, value in d.items():
                self.check(type(value) is int and value >= 0, 'development_nonnegative_integer', (ctx, field))
            self.equal(d['upgrades'], country['upgrades'], 'development_matches_legacy_upgrades', ctx)
            inequalities = (
                ('machine_required_upgrades','upgrades'), ('imported_machine_upgrades','machine_required_upgrades'),
                ('foreign_machine_upgrades','imported_machine_upgrades'),
                ('unique_imported_machines_development','imported_machine_upgrades'),
                ('unique_foreign_machines_development','foreign_machine_upgrades'),
                ('used_output_upgrades','productive_upgrades'), ('productive_upgrades','upgrades'),
                ('foreign_machine_used_output_upgrades','foreign_machine_productive_upgrades'),
                ('foreign_machine_productive_upgrades','foreign_machine_upgrades'),
                ('foreign_machine_export_used_units','foreign_machine_output_used_units'),
                ('foreign_machine_output_used_units','foreign_machine_output_units'),
                ('bought_high_machine_unique','bought_high_machines'),
                ('foreign_produced_high_bought_unique','bought_high_machine_unique'),
                ('bought_high_machine_used_unique','bought_high_machine_unique'),
                ('bought_high_machine_developed_unique','bought_high_machine_used_unique'),
                ('high_machine_useful_exports','high_machine_used'), ('high_machine_used','high_machine_produced'),
                ('high_machine_unused_stock','high_machine_ending_stock'),
                ('g3_electronics_used','g3_electronics_output'), ('g3_machine_used','g3_machine_output'),
            )
            for lower, upper in inequalities:
                self.check(d[lower] <= d[upper], 'development_subset_bound', (ctx, lower, upper))
            self.equal(d['high_machine_produced'], sum(country['machine_produced_by_gen'][str(g)] for g in (2,3)),
                       'high_production_matches_legacy_grades', ctx)
            self.equal(d['high_machine_ending_stock'], sum(country['machine_stock_by_gen'][str(g)] for g in (2,3)),
                       'high_stock_matches_legacy_grades', ctx)
            self.check(d['bought_high_machines'] <= country['import_goods']['machine'], 'high_imports_within_all_machine_imports', ctx)
            self.check(d['sold_high_machines'] <= country['export_goods']['machine'], 'high_exports_within_all_machine_exports', ctx)
            self.check(d['high_machine_purchase_cash'] <= country['purchase_by_good']['machine'], 'high_spending_within_all_machine_spending', ctx)
            self.check(d['high_machine_sales_cash'] <= country['sale_by_good']['machine'], 'high_revenue_within_all_machine_revenue', ctx)
            if name in ORIGINAL:
                expected = 15 * max(0, min(1, country['capacity_growth']/GROWTH_GOALS[name]))
                self.equal(country['industry_capacity_score'], expected, 'unchanged_industry_capacity_formula', ctx)
            else:
                for field in ('economic','industry','score'):
                    self.equal(country[field], None, 'extra_countries_not_rank_calibrated', (ctx,field))
            if row.get('focal') == name and row.get('style') in MACHINE_REFUSALS:
                self.equal(d['bought_high_machines'], 0, 'no_forbidden_high_machine_imports', ctx)
                self.equal(d['imported_machine_upgrades'], 0, 'no_refused_machine_development_imports', ctx)
                if row['style'] == 'no_machine':
                    self.equal(country['import_goods']['machine'], 0, 'no_machine_imports_any_grade', ctx)
        for field in METRICS:
            self.equal(row['world']['development'][field], sum(c['development'][field] for c in row['countries'].values()),
                       'world_development_metric_sum', (key,field))
        world = row['world']['development']
        self.equal(world['bought_high_machines'], world['sold_high_machines'], 'high_machine_trade_conservation', key)
        self.equal(world['high_machine_purchase_cash'], world['high_machine_sales_cash'], 'high_machine_cash_conservation', key)
        if row.get('style') == 'no_trade':
            for field in ('bought_high_machines','foreign_machine_upgrades','high_machine_purchase_cash'):
                self.equal(world[field], 0, 'no_trade_has_no_imported_chain', (key,field))

    def trace(self, trace, result, context):
        super().trace(trace, result, context)
        self.audit_development_trace(trace, result, context)

    def audit_development_trace(self, trace, result, context):
        units = {int(k):v for k,v in trace['units'].items()}
        txs = trace['transactions']; uses = trace['development_uses']
        events = trace['development']; outputs = trace['development_outputs']
        attempts = trace['development_attempts']; reported_chains = trace['development_chains']
        self.equal(trace['development_policy'], result['world']['development_policy'], 'trace_development_policy', context)
        self.equal(len(uses), len({use_key(e) for e in uses}), 'unique_development_use_snapshot_keys', context)
        use_by_key = {use_key(e):e for e in uses}
        uses_by_uid = defaultdict(list)
        transfer_history = defaultdict(list)
        for idx, tx in enumerate(txs):
            for leg in tx['legs']:
                self.equal(len({(units[i]['good'],units[i]['gen']) for i in leg['ids']}), 1,
                           'transaction_leg_homogeneous_for_grade_cash', (context,idx))
                for uid in leg['ids']:
                    transfer_history[uid].append((tx['round'],idx,leg['seller'],leg['buyer']))
        reconstructed_import = {}
        foreign_used = set()
        for event in uses:
            uid = event['uid']; unit = units[uid]; ctx = (context,use_key(event))
            for local, physical in (('good','good'),('generation','gen'),('born','born'),('origin','origin')):
                self.equal(event[local], unit[physical], 'use_snapshot_physical_identity', (ctx,local))
            before_trade = event['purpose'] in BEFORE_TRADE_USES
            eligible = [x for x in transfer_history[uid] if x[0] < event['round']
                        or (x[0] == event['round'] and not before_trade)]
            last = eligible[-1] if eligible else None
            owner = last[3] if last else unit['origin']
            imported = last[1] if last else None
            self.equal(event['country'], owner, 'use_owner_from_phase_correct_transfers', ctx)
            self.equal(event['import_transaction'], imported, 'import_at_use_not_final_import_snapshot', ctx)
            self.check(unit['born'] < event['round'] if before_trade else unit['born'] <= event['round'],
                       'use_respects_production_and_trade_phase', ctx)
            reconstructed_import[use_key(event)] = imported
            if unit['origin'] != owner and imported is not None:
                foreign_used.add(uid)
            uses_by_uid[uid].append(event)
        for uid, unit in units.items():
            actual = uses_by_uid.get(uid, [])
            self.equal(unit['used'], bool(actual), 'unit_used_flag_from_all_use_snapshots', (context,uid))
            if actual:
                first = actual[0]
                self.equal((unit['use_round'],unit['use_country'],unit['use_purpose']),
                           (first['round'],first['country'],first['purpose']), 'first_use_fields_match_chronology', (context,uid))
        raw_keys = {use_key(e) for e in trace['raw_use']}
        self.equal({use_key(e) for e in uses if e['good'] in ('ore','fuel')}, raw_keys,
                   'all_raw_use_snapshots_match_independent_raw_log', context)
        for need in trace['needs_ledger']:
            purpose = ('equipment' if need['purpose'].startswith('equipment:') else
                       'production' if need['purpose'].startswith('production:') else
                       'maintenance' if need['purpose'] == 'equipment_maintenance' else need['purpose'])
            for uid in need['used_ids']:
                self.check((need['round'],need['country'],uid,purpose) in use_by_key,
                           'need_actual_uid_has_matching_use_snapshot', (context,need['round'],need['country'],uid,purpose))

        self.equal([e['event_id'] for e in events], list(range(len(events))), 'development_event_ids_are_contiguous', context)
        self.equal(len(events), len({(e['round'],e['country']) for e in events}), 'one_development_per_country_round', context)
        legacy = {(e['round'],e['country'],e['industry']):e for e in trace['investments']}
        self.equal(set(legacy), {(e['round'],e['country'],e['industry']) for e in events}, 'all_legacy_investments_have_event', context)
        machine_events = []
        for event in events:
            ctx = (context,event['event_id']); country=event['country']; good=event['industry']; old=event['from_level']
            self.equal(event['to_level'], old+1, 'development_one_level', ctx)
            self.check(0 <= old <= 3 and 1 <= event['round'] <= 7, 'development_valid_level_and_round', ctx)
            ore = (0 if old<2 else 1 if old==2 else 2) + int(good in DURABLES and old>=2)
            grade = 2 if old>=3 or (result['world']['development_policy']['prior_machine'] and good in DURABLES and old==2) else 0
            self.equal((event['ore_required'],event['machine_min_gen']), (ore,grade), 'development_requirements_recomputed', ctx)
            self.equal(event['cash_cost'], development_cost(country,good,old), 'unchanged_development_cash_cost', ctx)
            prior = legacy[(event['round'],country,good)]
            self.equal((event['to_level'],event['cash_cost']), (prior['new_level'],prior['cash_cost']), 'development_matches_legacy_investment', ctx)
            raws = [e['uid'] for e in trace['raw_use'] if e['round']==event['round'] and e['country']==country
                    and e['good']=='ore' and e['purpose']=='development']
            self.equal(event['ore_ids'], raws, 'research_raw_uid_exact_match', ctx)
            self.equal(len(raws), ore, 'research_raw_quantity_exact', ctx)
            self.equal(bool(event['machine']), bool(grade), 'required_machine_present', ctx)
            if event['machine']:
                machine = event['machine']; machine_events.append(machine)
                self.equal(machine, use_by_key.get((event['round'],country,machine['uid'],'development')),
                           'development_machine_exact_use_time_snapshot', ctx)
                self.check(machine['good']=='machine' and machine['generation']>=grade, 'development_uses_qualified_machine', ctx)
                self.check(units[machine['uid']]['owner'] is not None, 'development_does_not_destroy_reusable_machine', ctx)
                self.score_coverage['machine_development_events'] += 1
                covered = any(n['round']==event['round'] and n['country']==country and n['good']=='machine'
                              and n['purpose']=='development' and machine['uid'] in n['used_ids'] for n in trace['needs_ledger'])
                self.score_coverage['machine_development_with_need_record'] += int(covered)
                self.score_coverage['machine_development_without_need_record'] += int(not covered)
        self.equal({use_key(e) for e in machine_events}, {use_key(e) for e in uses if e['good']=='machine' and e['purpose']=='development'},
                   'all_machine_development_uses_attached_to_successful_event', context)
        ledger = {(r['round'],r['country']):r for r in trace['cash_ledger']}
        # Reconstruct the actual supply target from preceding ownership/sales,
        # independently of the recorded material plan and declared output.
        for row in trace['machine_output']:
            r=row['round'];name=row['country'];gen=row['planned_generation'];ctx=(context,r,name)
            focus=MAIN_INDUSTRY[name] if r==1 else ledger[(r-1,name)]['next_focus']
            factory=next(p for p in trace['production'] if p['round']==r and p['country']==name and p['industry']=='machine')
            capacity=INITIAL_MACHINE_BASE.get(name,1)+factory['level']-1+int(focus=='machine')
            self.equal(row['capacity'],capacity,'machine_actual_capacity_from_level_focus',ctx)
            held=0
            for uid,u in units.items():
                if u['good']!='machine' or u['gen']<gen or u['born']>=r:continue
                earlier=[x for x in transfer_history[uid] if x[0]<r]
                owner=earlier[-1][3] if earlier else u['origin']
                held+=owner==name
            history_rounds=range(max(1,r-2),r)
            sales=sum(1 for tx in txs if tx['round'] in history_rounds for leg in tx['legs'] if leg['seller']==name
                      for uid in leg['ids'] if units[uid]['good']=='machine' and units[uid]['origin']==name and units[uid]['gen']==gen)
            extra=int(result['world']['development_policy']['sale_buffer'] and gen>=2 and focus not in DURABLES)
            target=1+math.ceil(sales/max(1,len(history_rounds)))+extra
            first=not any(u['origin']==name and u['good']=='machine' and u['gen']==gen and 0<u['born']<r for u in units.values())
            wanted=max(0,target-held)
            if first:wanted=max(1,wanted)
            self.equal(row['planned'],min(capacity,wanted),'machine_stock_target_from_prior_physical_state',ctx)
            self.equal(factory['planned_quantity'],row['planned'],'factory_and_machine_planned_quantity_match',ctx)
        initial_levels = defaultdict(dict)
        for p in trace['production']:
            if p['round']==1: initial_levels[p['country']][p['industry']]=p['level']
        for name in result['countries']:
            current = dict(initial_levels[name])
            for r in range(1,10):
                for e in events:
                    if e['country']!=name or e['round']!=r: continue
                    self.equal(e['from_level'], current.get(e['industry'],0), 'development_level_history', (context,e['event_id']))
                    current[e['industry']]=e['to_level']
                self.equal(current, ledger[(r,name)]['levels'], 'end_round_levels_from_initial_plus_development', (context,r,name))

        production = {(p['round'],p['country'],p['industry']):p for p in trace['production']}
        self.equal(len(production), len(trace['production']), 'production_factory_round_unique', context)
        self.equal({(p['round'],p['country'],p['industry']) for p in outputs}, set(production), 'every_factory_has_output_attribution_record', context)
        self.equal(len(outputs), len(production), 'no_duplicate_output_attribution_rows', context)
        stage_outputs = defaultdict(list); attributed=[]
        for row in outputs:
            key=(row['round'],row['country'],row['industry']); ctx=(context,key); p=production[key]
            actual=sorted(uid for uid,u in units.items() if (u['born'],u['origin'],u['good'])==key)
            self.equal(row['ids'],actual,'output_ids_reconstructed_from_unit_births',ctx)
            self.equal((row['level'],row['funded']), (p['level'],p['funded']), 'output_matches_actual_factory_result', ctx)
            earlier=[e for e in events if e['round']<row['round'] and e['country']==row['country'] and e['industry']==row['industry']]
            latest=max(earlier,key=lambda e:e['round']) if earlier else None
            self.equal(row['development_event_id'],latest['event_id'] if latest else None,'only_latest_prior_stage_attributed',ctx)
            if latest:
                self.equal(row['level'],latest['to_level'],'attributed_output_at_upgraded_level',ctx)
                if p['funded']:stage_outputs[latest['event_id']].extend(actual)
            if row['industry'] in DURABLES and p['funded']:
                for uid in actual:
                    self.equal(units[uid]['gen'],min(3,row['level']),'funded_durable_output_has_actual_technology', (ctx,uid))
            attributed.extend(actual)
        self.equal(len(attributed),len(set(attributed)),'physical_output_never_multiple_counted',context)
        self.equal(set(attributed),{uid for uid,u in units.items() if u['born']>0},'all_new_physical_output_accounted',context)
        assigned=[uid for ids in stage_outputs.values() for uid in ids]
        self.equal(len(assigned),len(set(assigned)),'funded_output_has_at_most_one_development',context)
        chains=[]
        for event in events:
            ids=sorted(stage_outputs[event['event_id']]); machine=event['machine']
            imported=bool(machine and reconstructed_import[use_key(machine)] is not None)
            foreign=bool(imported and machine['origin']!=event['country'])
            chain={**event,'imported_machine':imported,'foreign_machine':foreign,'output_ids':ids,
                   'used_output_ids':[i for i in ids if uses_by_uid.get(i)],
                   'foreign_used_output_ids':[i for i in ids if i in foreign_used]}
            chains.append(chain)
            if foreign and len(self.chain_examples)<12:
                self.chain_examples.append({'game':context,'event_id':event['event_id'],'country':event['country'],
                    'round':event['round'],'industry':event['industry'],'level':event['to_level'],
                    'machine_uid':machine['uid'],'machine_origin':machine['origin'],
                    'machine_import_round':txs[machine['import_transaction']]['round'],
                    'output_units':len(ids),'used_units':len(chain['used_output_ids']),
                    'foreign_used_units':len(chain['foreign_used_output_ids'])})
        self.equal(reported_chains,chains,'entire_chains_independently_reconstructed',context)

        for name,country in result['countries'].items():
            local=[e for e in chains if e['country']==name]; foreign=[e for e in local if e['foreign_machine']]
            bought=[];sold=[];purchase_cash=0;sales_cash=0
            for tx in txs:
                for leg in tx['legs']:
                    high=[i for i in leg['ids'] if units[i]['good']=='machine' and units[i]['gen']>=2]
                    if leg['buyer']==name:
                        bought.extend(high)
                        if high and tx['cash']:purchase_cash+=tx['cash'][2]
                    if leg['seller']==name:
                        sold.extend(high)
                        if high and tx['cash']:sales_cash+=tx['cash'][2]
            imported_used={e['uid'] for e in uses if e['country']==name and e['good']=='machine' and e['generation']>=2
                           and reconstructed_import[use_key(e)] is not None}
            made={uid for uid,u in units.items() if u['origin']==name and u['born']>0}
            high={i for i in made if units[i]['good']=='machine' and units[i]['gen']>=2}
            g3e={i for i in made if units[i]['good']=='electronics' and units[i]['gen']==3}
            g3m={i for i in high if units[i]['gen']==3}
            held_high={i for i,u in units.items() if u['owner']==name and u['good']=='machine' and u['gen']>=2}
            foreign_output={i for e in foreign for i in e['output_ids']}
            used=set(uses_by_uid)
            derived={
                'upgrades':len(local), 'machine_required_upgrades':sum(bool(e['machine']) for e in local),
                'imported_machine_upgrades':sum(e['imported_machine'] for e in local),
                'foreign_machine_upgrades':len(foreign),
                'unique_imported_machines_development':len({e['machine']['uid'] for e in local if e['imported_machine']}),
                'unique_foreign_machines_development':len({e['machine']['uid'] for e in foreign}),
                'productive_upgrades':sum(bool(e['output_ids']) for e in local),
                'used_output_upgrades':sum(bool(e['used_output_ids']) for e in local),
                'foreign_machine_productive_upgrades':sum(bool(e['output_ids']) for e in foreign),
                'foreign_machine_used_output_upgrades':sum(bool(e['used_output_ids']) for e in foreign),
                'foreign_machine_output_units':len(foreign_output),
                'foreign_machine_output_used_units':len(foreign_output & used),
                'foreign_machine_export_used_units':len(foreign_output & foreign_used),
                'bought_high_machines':len(bought), 'bought_high_machine_unique':len(set(bought)),
                'foreign_produced_high_bought_unique':len({i for i in bought if units[i]['origin']!=name and units[i]['born']>0}),
                'bought_high_machine_used_unique':len(set(bought)&imported_used),
                'bought_high_machine_developed_unique':len({e['machine']['uid'] for e in local if e['imported_machine'] and e['machine']['generation']>=2}),
                'high_machine_purchase_cash':purchase_cash,'sold_high_machines':len(sold),'high_machine_sales_cash':sales_cash,
                'high_machine_produced':len(high),'high_machine_used':len(high & used),
                'high_machine_useful_exports':len(high & foreign_used),
                'high_machine_public_unique':len({i for e in trace['public_offers'] if e['country']==name and e['good']=='machine' and e['generation']>=2 for i in e['ids']}),
                'high_machine_ending_stock':len(held_high),'high_machine_unused_stock':len(held_high-used),
                'g3_electronics_output':len(g3e),'g3_electronics_used':len(g3e & used),
                'g3_machine_output':len(g3m),'g3_machine_used':len(g3m & used),
                'machine_condition_blocks':sum(e['country']==name and e['missing_machine'] for e in attempts),
            }
            self.equal(derived,country['development'],'all32_development_metrics_from_physical_records',(context,name))
            self.equal(sum(e['cash_cost'] for e in local),country['investment'],'development_cash_sum',(context,name))
            self.equal(sum(e['ore_required'] for e in local),country['research_raw']['ore'],'development_raw_sum',(context,name))
            self.equal(len([e for e in uses if e['country']==name and e['purpose']=='equipment']),country['equipment_use_episodes'],
                       'equipment_use_snapshots_match_old_summary',(context,name))
        self.equal(len(attempts),len({(e['round'],e['country']) for e in attempts}),'unique_failed_attempt_observation',context)
        for attempt in attempts:
            key=(attempt['round'],attempt['country']); ctx=(context,key)
            self.check(key not in {(e['round'],e['country']) for e in events},'attempt_is_not_successful_development',ctx)
            self.check(attempt['required_machine_grade'] in (0,2),'attempt_machine_grade_valid',ctx)
            self.check(not attempt['missing_machine'] or attempt['required_machine_grade']>0,'missing_machine_has_actual_condition',ctx)
        self.counts['development_events']+=len(events)
        self.counts['development_output_batches']+=len(outputs)
        self.counts['development_use_snapshots']+=len(uses)
        self.counts['development_attempt_observations']+=len(attempts)
        self.counts['foreign_machine_development_chains']+=sum(e['foreign_machine'] for e in chains)


def summarize(rows):
    output={}
    for m in POLICIES:
        selected=[r for r in rows if r['phase']=='main' and mode(r)==m]
        if not selected:continue
        entry={'n':len(selected),'world':{},'countries':{}}
        for field in METRICS:
            entry['world'][field]=stats(r['world']['development'][field] for r in selected)
        for name in selected[0]['countries']:
            entry['countries'][name]={field:stats(r['countries'][name]['development'][field] for r in selected) for field in METRICS}
        output[m]=entry
    return output


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path(__file__).parent/'development_results')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();folder=args.results.resolve()
    folder.mkdir(exist_ok=True)
    audit=Audit();report={'scope':'Independent v9 saved-record audit; no economic engine is imported or executed.','warnings':[]}
    required=('runs.jsonl.gz','round_ledgers.jsonl.gz','raw_round_ledgers.jsonl.gz','first_seed_traces.json.gz','run_manifest.json')
    missing=[name for name in required if not (folder/name).exists()]
    if missing:
        report.update(status='pending_final_results',pending=missing)
    else:
        rows=read_lines(folder/'runs.jsonl.gz');keys=[identity(r) for r in rows]
        audit.equal(len(keys),len(set(keys)),'unique_game_keys')
        by_key={identity(r):r for r in rows}
        for row in rows:audit.run_summary(row)
        main_rows={(mode(r),r['seed']):r for r in rows if r['phase']=='main'}
        for filename,method in (('round_ledgers.jsonl.gz',audit.ledger),('raw_round_ledgers.jsonl.gz',audit.raw_ledger)):
            groups=read_lines(folder/filename);ledger_keys=[(mode(g),g['seed']) for g in groups]
            audit.equal(len(ledger_keys),len(set(ledger_keys)),'unique_main_ledger_keys',filename)
            audit.equal(set(ledger_keys),set(main_rows),'all_main_games_have_ledger',filename)
            for group in groups:
                key=(mode(group),group['seed']);method(group['rows'],main_rows[key],key)
        traced=[]
        for label,stored in read_json(folder/'first_seed_traces.json.gz').items():
            key=identity(stored);audit.check(key in by_key,'trace_is_completed_game',(label,key))
            if key not in by_key:continue
            traced.append(key);audit.trace(stored.get('trace',stored),by_key[key],key)
        audit.equal(len(traced),len(set(traced)),'unique_detailed_trace_games')
        manifest=read_json(folder/'run_manifest.json')
        for field in ('completed_games','planned_games'):
            audit.equal(len(rows),manifest[field],'manifest_game_count',field)
        a,b=manifest['main_seed_range'];c,d=manifest['stress_seed_range']
        expected={('main',m,s,None,'normal') for m in manifest['modes'] for s in range(a,b+1)}
        expected|={('stress',m,s,f,st) for m in manifest['stress_modes'] for f,st in manifest['stress_scenarios'] for s in range(c,d+1)}
        audit.equal(set(keys),expected,'complete_preregistered_schedule')
        for key in traced:
            audit.equal(key[2],a if key[0]=='main' else c,'representative_first_seed_only',key)
        audit.equal({k[1] for k in traced if k[0]=='main'},set(manifest['modes']),'all_main_modes_have_trace')
        if 'representative_traces_planned' in manifest:
            audit.equal(len(traced),manifest['representative_traces_planned'],'planned_trace_count')
        if 'representative_trace_styles' in manifest:
            expected_traces={('main',m,a,None,'normal') for m in manifest['modes']}
            expected_traces|={('stress',m,c,f,st) for m in manifest['stress_modes'] for f,st in manifest['stress_scenarios']
                              if st in manifest['representative_trace_styles']}
            audit.equal(set(traced),expected_traces,'complete_declared_representative_traces')
        for filename,digest in manifest['source_sha256'].items():
            audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(),digest,'frozen_source_hash',filename)
        report.update(completed_runs=len(rows),groups={str(k):v for k,v in Counter((r['phase'],mode(r),r['style']) for r in rows).items()},
                      analysis=summarize(rows),advice_score_analysis=score_analysis(rows),chain_examples=audit.chain_examples,
                      legacy_score_coverage=dict(audit.score_coverage))
        report['method_notes']=[
            'All cash/raw/price checks reuse the unchanged v8 record audit with only raw-policy lookup mapped to bridge.',
            'Use-time import provenance is reconstructed from transaction order and phase, never the final unit.last_import for reusable goods.',
            'Each funded output UID belongs only to the latest earlier development event for that country and industry.',
            'Development chains establish chronological actual use; their output is not an estimated incremental causal benefit.',
            'Foreign-produced and imported are distinct: own-origin returned equipment has import history without foreign origin.',
            'high_machine_public_unique includes qualifying owned resale offers; it is not restricted to own new production.',
            'World *_unique metrics sum per-country distinct counts; cross-country resale can count one physical UID in several countries.',
            'machine_condition_blocks observes an unmet condition which may coexist with cash, household or input shortfalls.',
            'Legacy machine development marks actual use but does not add a machine development need row; the old coverage denominator omits that need.',
            'legacy_score_coverage counts only the saved detailed traces, not every formal game.',
            'Old stock valuation, score caps, industry-use denominator and original-six diagnostic goals are unchanged.',
        ]
        report['audit_scope']={
            'summaries':'All saved games: cash/raw/grade/score and development totals, bounds, refusal invariants.',
            'round_ledgers':'All saved main games: cash and raw continuity, actual starts/flows/use/stocks.',
            'detailed_traces':'Saved representative games only: physical UIDs, price advice, use-time ownership/imports, stage transitions, funded output and all32 metrics.',
            'not_claimed':['Economic or educational fairness, observed student learning, classroom timing or multiplayer stability.',
                           'Complete UID-level checks for games without detailed traces.',
                           'A development chain as proof of incremental production or profit caused by the imported machine.',
                           'Independent rival-price snapshots beyond arithmetic checks on saved observations.']}
        report['status']='failed' if audit.errors else 'passed'
    report['audit_counts']=dict(audit.counts);report['checks_evaluated']=audit.checks;report['errors']=audit.errors
    target=args.out or folder/'independent_audit.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=lambda v:sorted(v,key=repr) if isinstance(v,set) else repr(v)),encoding='utf-8')
    print(json.dumps({'status':report['status'],'counts':report['audit_counts'],'checks':audit.checks,'errors':len(audit.errors),'report':str(target)},ensure_ascii=False))
    return int(bool(audit.errors))


if __name__=='__main__':
    raise SystemExit(main())
