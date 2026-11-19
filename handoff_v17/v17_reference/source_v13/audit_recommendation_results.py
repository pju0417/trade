"""Independent v7 saved-record audit and strategy-score decomposition.

No economic engine, runner or tests are imported or mutated. The inherited
auditor checks physical units, raw consumption, prepaid work and cash records.
This file adds channel accounting and separates capacity/use industry points.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
from audit_machinery_results import Audit as PhysicalAudit, read_json, read_lines, mode, identity, GOODS, ORIGINAL

CHANNELS = ('market', 'direct', 'barter')
CHANNEL_FIELDS = ('sold_units', 'bought_units', 'sales_cash', 'purchase_cash')
MAIN_GOOD = {'Tropia':'banana', 'Grainia':'wheat', 'Oilia':'fuel', 'Mechania':'machine',
             'Mineria':'ore', 'Technia':'electronics', 'Novia':'electronics',
             'Agrea':'banana', 'Ferria':'ore'}
INITIAL_PRICE = dict(zip(GOODS, (10, 10, 30, 20, 50, 80)))
POLICIES = {'baseline':(False, False, False), 'price':(True, False, False),
            'listing':(True, True, False), 'planning':(False, False, True),
            'responsive':(True, False, True), 'combined':(True, True, True)}


def half_up(value):
    return max(1, math.floor(value + .5))


def stats(values):
    values = list(values)
    if not values:
        return None
    mean = statistics.mean(values)
    error = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0
    return {'n':len(values), 'mean':mean, 'ci95':[mean-error, mean+error],
            'min':min(values), 'max':max(values)}


def score_parts(country):
    made = sum(country['produced'].values())
    used = sum(country['use_by_good'].values())
    use_points = 10 * used / max(1, made)
    industry = country['industry']
    return {
        'cash':country['cash'], 'economic':country['economic'],
        'happy_points':country['happy']/4, 'trade':country['trade'],
        'industry_capacity_points':None if industry is None else industry-use_points,
        'industry_use_points':use_points, 'industry_total':industry,
        'score':country['score'], 'investment':country['investment'],
        'revenue':country['revenue'], 'purchases':country['purchases'],
        'produced_units':made, 'used_produced_units':used,
        'useful_exports':country['useful_exports'],
        'economic_at_25':int(country['economic'] is not None and country['economic'] >= 25-1e-9),
    }


def channel_ledger(trace):
    answer = defaultdict(lambda:{c:{f:0 for f in CHANNEL_FIELDS} for c in CHANNELS})
    for tx in trace['transactions']:
        channel = tx['channel']
        for leg in tx['legs']:
            answer[leg['seller']][channel]['sold_units'] += len(leg['ids'])
            answer[leg['buyer']][channel]['bought_units'] += len(leg['ids'])
        if tx['cash']:
            buyer, seller, amount = tx['cash']
            answer[seller][channel]['sales_cash'] += amount
            answer[buyer][channel]['purchase_cash'] += amount
    return dict(answer)


class Audit(PhysicalAudit):
    def __init__(self):
        super().__init__()
        self.trace_channels = {}
        self.recommendation_schemas = Counter()

    def run_summary(self, row):
        super().run_summary(row)
        key = identity(row)
        self.equal(row['world']['machine_upkeep_ore'], 0, 'v7_no_maintenance_rule', key)
        for name, c in row['countries'].items():
            parts = score_parts(c)
            self.check(parts['used_produced_units'] <= parts['produced_units'], 'used_not_more_than_produced', (key, name))
            self.check(0 <= parts['industry_use_points'] <= 10+1e-9, 'industry_use_bound', (key, name))
            if c['industry'] is not None:
                self.check(-1e-9 <= parts['industry_capacity_points'] <= 15+1e-9,
                           'industry_capacity_bound', (key, name))
                self.equal(c['score'], c['economic'] + c['trade'] + c['happy']/4
                           + parts['industry_capacity_points'] + parts['industry_use_points'],
                           'score_reconstruction', (key, name))
            for reported, derived in (('industry_use_score', 'industry_use_points'),
                                      ('industry_capacity_score', 'industry_capacity_points'),
                                      ('economic_at_cap', 'economic_at_25'),
                                      ('all_goods_unique_used', 'used_produced_units')):
                self.equal(c[reported], parts[derived], 'reported_score_component', (key, name, reported))
            self.equal(c['offer_price_mismatches'], 0, 'no_applied_price_mismatch', (key, name))
            self.equal(c['listing_plan_violations'], 0, 'no_listing_cap_mismatch', (key, name))
            if mode(row) != 'baseline':
                self.equal(c['protected_offer_violations'], 0, 'protected_stock_recalled', (key, name))
            self.equal(sum(c['listed_by_good'].values()), c['listed'], 'listed_goods_sum', (key, name))
            for good in GOODS:
                self.check(0 <= c['listed_by_good'].get(good, 0) <= c['end_stock_by_good'][good],
                           'listing_is_part_of_physical_stock', (key, name, good))
            if 'channel_stats' in c:
                self.counts['countries_with_channel_summary'] += 1
                channels = c['channel_stats']
                self.equal(set(channels), set(CHANNELS), 'summary_channel_names', (key, name))
                for channel in CHANNELS:
                    for field in CHANNEL_FIELDS:
                        value = channels[channel][field]
                        self.check(type(value) is int and value >= 0, 'channel_nonnegative_integer', (key, name, channel, field))
                self.equal(sum(x['sold_units'] for x in channels.values()), c['exports'], 'channel_export_sum', (key, name))
                self.equal(sum(x['bought_units'] for x in channels.values()), c['imports'], 'channel_import_sum', (key, name))
                self.equal(sum(x['sales_cash'] for x in channels.values()), c['revenue'], 'channel_revenue_sum', (key, name))
                self.equal(sum(x['purchase_cash'] for x in channels.values()), c['purchases'], 'channel_purchase_sum', (key, name))
                self.equal(channels['barter']['sales_cash'] + channels['barter']['purchase_cash'], 0,
                           'barter_has_no_imputed_cash', (key, name))
        for field in ('grade_recalls', 'planning_decisions', 'planning_holds', 'public_offer_units',
                      'all_goods_unique_used', 'offer_price_mismatches', 'listing_plan_violations',
                      'protected_offer_violations'):
            self.equal(sum(c[field] for c in row['countries'].values()), row['world'][field],
                       'world_recommendation_metric_sum', (key, field))
        for good in GOODS:
            self.check(0 <= row['world']['aged_unused_goods'].get(good, 0)
                       <= row['world']['remaining_goods'].get(good, 0), 'aged_unused_within_stock', (key, good))

    def trace(self, trace, result, context):
        super().trace(trace, result, context)
        channels = channel_ledger(trace)
        self.trace_channels[str(context)] = channels
        for name, c in result['countries'].items():
            actual = channels.get(name, {k:{f:0 for f in CHANNEL_FIELDS} for k in CHANNELS})
            if 'channel_stats' in c:
                self.equal(actual, c['channel_stats'], 'actual_trace_channels', (context, name))
        self.audit_recommendations(trace, result, context)

    def audit_recommendations(self, trace, result, context):
        """Re-derive decisions from stored past transactions and physical IDs.

        This is a record audit, not a second economic engine. It independently
        checks observation windows, own realized sales, public sell-through,
        prices, listing caps/selection, forecast arithmetic and candidate choice.
        Exact private-free rival snapshots and future operating requirements are
        not reconstructed from final logs; no optimality claim follows.
        """
        rows = trace['recommendations']
        public = trace['public_offers']
        plans = trace['listing_plans']
        recalls = trace['grade_recalls']
        units = {int(k):v for k,v in trace['units'].items()}
        countries = result['countries']
        prices_on, limited_on, planning_on = POLICIES[mode(result)]
        for name, value in (('recommendations', rows), ('public_offers', public),
                            ('listing_plans', plans), ('grade_recalls', recalls)):
            self.check(isinstance(value, list), 'trace_record_list', (context, name))
        production = {(p['round'], p['country'], p['industry']):p for p in trace['production']}
        ledgers = {(p['round'], p['country']):p for p in trace['cash_ledger']}
        offers = {}
        investments = {}
        focuses = {}
        plans_by_key = {}
        public_by_key = {}
        country_counts = defaultdict(Counter)
        own_sales_cache = {}
        owned_cache = {}

        def style(name):
            return result.get('style', 'normal') if name == result.get('focal') else 'normal'

        def own_sales(name, good, through, generation=None):
            key = (name, good, through, generation)
            if key in own_sales_cache:
                return own_sales_cache[key]
            start = max(1, through-1)
            sold = set(); buyers = set(); paid = []
            for tx in trace['transactions']:
                if not start <= tx['round'] <= through:
                    continue
                for leg in tx['legs']:
                    if leg['seller'] != name:
                        continue
                    ids = [uid for uid in leg['ids'] if units[uid]['good'] == good
                           and (generation is None or units[uid]['gen'] == generation)]
                    if ids:
                        sold.update(ids); buyers.add(leg['buyer'])
                        if tx['cash']:
                            paid.extend([tx['cash'][2]/len(leg['ids'])] * len(ids))
            answer = {'units':len(sold), 'buyers':len(buyers),
                      'rate':len(sold)/max(1, through-start+1),
                      'cash_price':statistics.median(paid) if paid else None}
            own_sales_cache[key] = answer
            return answer

        def owned_before_trade(round_number, name):
            key = (round_number, name)
            if key in owned_cache:
                return owned_cache[key]
            owners = {uid:u['origin'] for uid,u in units.items() if u['born'] <= round_number}
            for tx in trace['transactions']:
                if tx['round'] >= round_number:
                    continue
                for leg in tx['legs']:
                    for uid in leg['ids']:
                        owners[uid] = leg['buyer']
            for uid,u in units.items():
                if u['owner'] is None and u['use_round'] is not None:
                    already_consumed = u['use_round'] < round_number or (
                        u['use_round'] == round_number and u['use_purpose'] in ('production', 'maintenance'))
                    if already_consumed:
                        owners[uid] = None
            answer = {uid for uid,owner in owners.items() if owner == name}
            owned_cache[key] = answer
            return answer

        def quote(good, generation, round_number):
            base = INITIAL_PRICE[good] if round_number == 1 else trace['prices'][round_number-2][good]
            if good in ('machine', 'electronics'):
                global_gen = max(u['gen'] for u in units.values()
                                 if u['good'] == good and u['born'] <= round_number)
                base *= (1, 1.4, 1.8)[generation-1] * .75**max(0, global_gen-generation)
            return half_up(base)

        def common(row, kind):
            r, name = row['round'], row['country']
            self.check(type(r) is int and 1 <= r <= 9, 'recommendation_round', (context, kind, r))
            self.check(name in countries, 'recommendation_country', (context, kind, name))
            return r, name

        for p in public:
            r, name = common(p, 'public_offer')
            key = (r, name, p['good'], p['generation'])
            self.check(key not in public_by_key, 'public_offer_key_unique', (context, key))
            public_by_key[key] = p
            self.equal(len(p['ids']), len(set(p['ids'])), 'public_ids_unique', (context, key))
            country_counts[name]['public_offer_units'] += len(p['ids'])
        for p in plans:
            r, name = common(p, 'listing_plan')
            key = (r, name, p['good'])
            self.check(key not in plans_by_key, 'listing_plan_key_unique', (context, key))
            plans_by_key[key] = p
            self.equal(p['limited'], limited_on, 'listing_policy_flag', (context, key))
            self.equal(len(p['actual_ids']), len(set(p['actual_ids'])), 'live_listing_ids_unique', (context, key))
            self.equal(len(p['surplus_ids']), len(set(p['surplus_ids'])), 'surplus_ids_unique', (context, key))
            self.check(set(p['surplus_ids']) <= owned_before_trade(r, name), 'surplus_is_own_current_stock', (context, key))
            self.check(set(p['actual_ids']) <= owned_before_trade(r, name), 'listed_is_own_current_stock', (context, key))
            # surplus_ids is recorded before a cap cancels surplus listings;
            # protected_ids is taken afterward. Equal-grade newly free stock
            # may replace another protected UID without changing protection.
            reassigned = bool(set(p['surplus_ids']) & set(p['protected_ids']))
            self.check(not reassigned or p['limited'], 'only_capped_relisting_reassigns_protected_uid', (context, key))
            self.counts['post_cap_equal_grade_protection_reassignments'] += int(reassigned)
            overlap = bool(set(p['actual_ids']) & set(p['protected_ids']))
            country_counts[name]['protected_offer_violations'] += int(overlap and mode(result) != 'baseline')
            self.counts['baseline_reserved_uid_overlap_diagnostic'] += int(overlap and mode(result) == 'baseline')
            if mode(result) != 'baseline':
                self.check(not overlap, 'no_protected_uid_publicly_offered', (context, key))
            within = not p['limited'] or len(p['actual_ids']) == p['target']
            self.equal(p['within_plan'], within, 'within_plan_independently_recomputed', (context, key))
            country_counts[name]['listing_plan_violations'] += int(not within)
            if p['limited']:
                history = own_sales(name, p['good'], r-1)
                expected = min(len(p['surplus_ids']), 10, max(2, 1+math.ceil(2*history['rate'])))
                self.equal(p['target'], expected, 'listing_total_cap_from_own_past_sales', (context, key))
                chosen = []
                for generation in sorted({units[i]['gen'] for i in p['surplus_ids']}, reverse=True):
                    ids = sorted((i for i in p['surplus_ids'] if units[i]['gen'] == generation),
                                 key=lambda i:(units[i]['born'], i))
                    if ids and len(chosen) < expected:
                        chosen.append(ids[0])
                rest = sorted((i for i in p['surplus_ids'] if i not in chosen), key=lambda i:(units[i]['born'], i))
                chosen.extend(rest[:max(0, expected-len(chosen))])
                self.equal(set(p['actual_ids']), set(chosen), 'listing_generation_trial_then_oldest', (context, key))
            else:
                self.equal(p['target'], len(p['actual_ids']), 'unlimited_observed_quantity', (context, key))

        for row in rows:
            self.counts['recommendation_rows'] += 1
            self.check(isinstance(row, dict), 'recommendation_is_object', context)
            if not isinstance(row, dict):
                continue
            self.recommendation_schemas[','.join(sorted(row))] += 1
            kind = row['kind']; r, name = common(row, kind)
            expected_through = r if kind == 'focus' else r-1
            self.equal(row['through_round'], expected_through, 'permitted_information_cutoff', (context, kind, r, name))
            self.counts[f'{kind}_recommendations'] += 1
            if kind == 'offer':
                good, gen = row['good'], row['generation']
                key = (r, name, good, gen)
                self.check(key not in offers, 'offer_recommendation_unique', (context, key))
                offers[key] = row
                p = public_by_key.get(key)
                self.check(p is not None, 'offer_has_public_snapshot', (context, key))
                if p is not None:
                    self.equal(row['actual_ids'], p['ids'], 'offer_public_ids_match', (context, key))
                    self.equal(row['actual_prices'], p['prices'], 'offer_public_prices_match', (context, key))
                for uid in row['actual_ids']:
                    self.check(uid in units and units[uid]['good'] == good and units[uid]['gen'] == gen
                               and units[uid]['born'] <= r, 'offered_uid_grade_and_date', (context, key, uid))
                self.equal(row['price_applied'], prices_on, 'price_policy_flag', (context, key))
                self.equal(row['public_quantity_limited'], limited_on, 'offer_listing_policy_flag', (context, key))
                advice = row['recommendation']
                self.equal(advice['through_round'], r-1, 'price_advice_cutoff', (context, key))
                self.equal(advice['reference'], quote(good, gen, r), 'current_reference_quote', (context, key))
                exposures = {(p['round'], uid) for p in public if p['country'] == name and p['good'] == good
                             and p['generation'] == gen and max(1, r-2) <= p['round'] < r for uid in p['ids']}
                cleared = {(tx['round'], uid) for tx in trace['transactions'] if max(1, r-2) <= tx['round'] < r
                           for leg in tx['legs'] if leg['seller'] == name for uid in leg['ids']
                           if (tx['round'], uid) in exposures}
                self.equal(advice['past_offered'], len(exposures), 'same_round_public_exposures', (context, key))
                self.equal(advice['past_sold'], len(cleared), 'public_exposures_actually_cleared', (context, key))
                self.equal(advice['past_all_sales'], own_sales(name, good, r-1, gen)['units'],
                           'all_channel_history_separate_from_public_fill', (context, key))
                unused = [uid for uid in row['actual_ids'] if units[uid]['use_round'] is None
                          or units[uid]['use_round'] > r or (units[uid]['use_round'] == r
                          and units[uid]['use_purpose'] not in ('production', 'equipment', 'maintenance'))]
                expected_age = max((r-units[uid]['born'] for uid in unused), default=0)
                self.equal(advice['age'], expected_age, 'age_of_unused_stock_at_listing', (context, key))
                fill = len(cleared)/len(exposures) if exposures else None
                factor, reason = 1., 'reference_trial'
                if expected_age >= 4 and exposures and fill < .5:
                    factor, reason = .6, 'persistent_unsold'
                elif expected_age >= 2 and exposures and fill < .75:
                    factor, reason = .8, 'unsold_stock'
                elif exposures and fill >= .9:
                    factor, reason = 1.05, 'recent_sales_strong'
                price = half_up(advice['reference']*factor)
                rival = advice['rival_best']
                if rival is not None:
                    self.check(type(rival) is int and rival > 0, 'recorded_rival_price_valid', (context, key))
                    if rival < price:
                        price = rival; reason += ';match_public_offer'
                price = max(half_up(advice['reference']*.5), price)
                if style(name) == 'cheap':
                    price, reason = half_up(advice['reference']*.5), 'fixed_half_reference'
                self.equal(advice['price'], price, 'advice_price_arithmetic', (context, key))
                self.equal(advice['reason'], reason, 'price_reason_matches_rule', (context, key))
                self.check(all(type(x) is int and x > 0 for x in row['actual_prices']), 'positive_integer_prices', (context, key))
                mismatch = row['price_applied'] and row['actual_prices'] != [price]
                country_counts[name]['offer_price_mismatches'] += int(mismatch)
                self.check(not mismatch, 'recommended_price_actually_applied', (context, key))
            elif kind == 'investment':
                key = (r, name)
                self.check(key not in investments, 'one_investment_plan_per_round', (context, key))
                investments[key] = row
                self.check(planning_on and r <= 7, 'investment_advice_mode_and_time', (context, key))
                country_counts[name]['planning_decisions'] += 1
                country_counts[name]['planning_holds'] += int(row['selected'] is None)
                candidates = row['candidates']
                self.equal(len(candidates), len({c['good'] for c in candidates}), 'investment_candidates_unique', (context, key))
                for candidate in candidates:
                    g = candidate['good']; ctx = (context, key, g)
                    self.equal(candidate['through_round'], r-1, 'investment_candidate_cutoff', ctx)
                    rem = 9-r
                    self.equal(candidate['remaining_rounds'], rem, 'investment_horizon', ctx)
                    history = own_sales(name, g, r-1)
                    self.equal(candidate['sales_forecast'], history['rate']*rem, 'investment_own_sales_forecast', ctx)
                    stock = sum(units[i]['good'] == g for i in owned_before_trade(r, name))
                    if g in ('banana', 'wheat'):
                        stock = max(0, stock-(1+int(r >= 5)+int(r >= 8)))
                        domestic = sum(1+int(rr >= 5)+int(rr >= 8) for rr in range(r+1, 10))
                        self.equal(candidate['future_domestic'], domestic, 'own_future_food_need', ctx)
                    elif g == 'electronics':
                        self.equal(candidate['future_domestic'], 2, 'own_final_electronics_need', ctx)
                    self.equal(candidate['stock_after_current_use'], stock, 'investment_own_available_stock', ctx)
                    old_output, new_output = candidate['old_output_forecast'], candidate['new_output_forecast']
                    gap = max(0, candidate['future_domestic']+candidate['sales_forecast']-stock-old_output)
                    useful = min(max(0, new_output-old_output), gap)
                    self.equal(candidate['marginal_useful_units'], useful, 'incremental_use_not_total_output', ctx)
                    before = production.get((r, name, g))
                    oldgen = before['tech'] if before else 1
                    level = before['level'] if before else 0
                    newgen = min(3, level+1) if g in ('machine', 'electronics') else 1
                    oldquote = quote(g, oldgen, r)
                    realizable = min(oldquote, history['cash_price'] if history['cash_price'] is not None else oldquote)
                    self.equal(candidate['capacity_value'], useful*realizable, 'capacity_value_at_observed_own_cash_price', ctx)
                    trial = 0.; quality = 0.
                    if newgen > oldgen:
                        newquote = quote(g, newgen, r)
                        stream = min(candidate['sales_forecast'], new_output)
                        trial = min(max(0, new_output-stream), .5*history['buyers'] if history['buyers'] else 1.)
                        quality = stream*max(0, newquote-realizable)+trial*newquote+(rem if g == 'electronics' else 0)
                    self.equal(candidate['quality_trial_units'], trial, 'bounded_new_grade_trial', ctx)
                    self.equal(candidate['quality_opportunity_value'], quality, 'uncertain_grade_value_arithmetic', ctx)
                    self.equal(candidate['uncertain_new_generation'], newgen > oldgen, 'uncertainty_flag', ctx)
                    values = ('development_cost', 'prerequisite_value', 'additional_operating_value')
                    for field in values:
                        value = candidate[field]
                        self.check(type(value) in (int, float) and math.isfinite(value) and value >= 0,
                                   'nonnegative_finite_opportunity_cost', (ctx, field))
                    score = (candidate['capacity_value']+quality)/max(1, sum(candidate[f] for f in values))
                    score += .3 if g == MAIN_GOOD[name] else 0
                    if level == 0:
                        score *= .8
                    self.equal(candidate['opportunity_score'], score, 'opportunity_score_arithmetic', ctx)
                    self.equal(candidate['eligible'], score >= .45, 'opportunity_threshold_not_cash_payback', ctx)
                winner = max(candidates, key=lambda c:(c['opportunity_score'], c['good'])) if candidates else None
                selected = winner['good'] if winner and (winner['eligible'] or style(name) == 'invest') else None
                self.equal(row['selected'], selected, 'best_eligible_investment_candidate', (context, key))
            elif kind == 'focus':
                key = (r, name)
                self.check(key not in focuses, 'one_focus_plan_per_round', (context, key))
                focuses[key] = row
                self.check(planning_on and r <= 8, 'focus_mode_and_time', (context, key))
                candidates = row['candidates']
                self.check(bool(candidates), 'focus_has_choice', (context, key))
                self.equal(len(candidates), len({c['good'] for c in candidates}), 'focus_candidates_unique', (context, key))
                for candidate in candidates:
                    g = candidate['good']; ctx = (context, key, g)
                    useful = candidate['marginal_useful_units']; total = candidate['bonus']*(9-r)
                    self.check(0 <= useful <= total, 'focus_uses_only_marginal_bonus', ctx)
                    self.check(candidate['base_output'] >= 0 and candidate['bonus'] >= 0, 'focus_nonnegative_output', ctx)
                    self.equal(candidate['value'], useful*quote(g, 1, r), 'focus_value_arithmetic', ctx)
                    self.equal(candidate['excess_value'], max(0, total-useful)*quote(g, 1, r), 'focus_excess_value_arithmetic', ctx)
                winner = max(candidates, key=lambda c:(c['value'], -c['excess_value'], c['good']))
                self.equal(row['selected'], winner['good'], 'focus_selected_best_use_then_least_waste', (context, key))
                self.equal(row['selected'], ledgers[key]['next_focus'], 'recommended_focus_actually_selected', (context, key))
            else:
                self.check(False, 'known_recommendation_kind', (context, kind))

        self.equal(set(offers), set(public_by_key), 'all_public_snapshots_have_advice', context)
        for key, p in plans_by_key.items():
            offer_ids = [uid for gen in (1, 2, 3) for uid in offers.get((*key, gen), {}).get('actual_ids', [])]
            self.equal(set(offer_ids), set(p['actual_ids']), 'all_generation_offers_within_total_plan', (context, key))
            for gen in (1, 2, 3):
                offer = offers.get((*key, gen))
                if offer:
                    self.equal(offer['total_good_target'], p['target'], 'shared_all_grade_listing_target', (context, key, gen))
        recall_keys = set()
        for row in recalls:
            r, name = common(row, 'grade_recall')
            uid = row['unit']; key = (r, name, uid)
            self.check(key not in recall_keys, 'grade_recall_once_per_uid_round', (context, key))
            recall_keys.add(key)
            self.check(uid in owned_before_trade(r, name) and units[uid]['good'] == 'machine'
                       and units[uid]['gen'] >= row['min_gen'], 'grade_recall_qualifies_and_is_owned', (context, key))
            country_counts[name]['grade_recalls'] += 1
        for name, c in countries.items():
            can_list = result.get('style') != 'no_trade' and style(name) != 'idle'
            expected_plans = {(r, name, good) for r in range(1, 10) for good in GOODS} if can_list else set()
            self.equal({key for key in plans_by_key if key[1] == name}, expected_plans,
                       'listing_record_round_coverage', (context, name))
            expected_investment = {(r, name) for r in range(1, 8)} if planning_on and style(name) not in ('idle', 'trade') else set()
            self.equal({key for key in investments if key[1] == name}, expected_investment,
                       'investment_record_round_coverage', (context, name))
            expected_focus = {(r, name) for r in range(1, 9)} if planning_on and style(name) not in ('idle', 'invest') else set()
            self.equal({key for key in focuses if key[1] == name}, expected_focus,
                       'focus_record_round_coverage', (context, name))
            for field in ('grade_recalls', 'planning_decisions', 'planning_holds', 'public_offer_units',
                          'offer_price_mismatches', 'listing_plan_violations', 'protected_offer_violations'):
                self.equal(country_counts[name][field], c[field], 'trace_recommendation_summary', (context, name, field))
            for good in GOODS:
                listed = sum(u['owner'] == name and u['good'] == good and u['order'] is not None for u in units.values())
                self.equal(listed, c['listed_by_good'][good], 'trace_final_held_and_listed', (context, name, good))
                unused = sum(u['owner'] == name and u['good'] == good and not u['used'] for u in units.values())
                self.equal(unused, c['unused_by_good'][good], 'trace_final_unused_stock', (context, name, good))
        self.counts['public_offer_records'] += len(public)
        self.counts['listing_plan_records'] += len(plans)
        self.counts['grade_recall_records'] += len(recalls)


def analysis(rows):
    """All metrics below come from stored records; no counterfactual games."""
    output = {'method_notes':[
        'Industry use points = 10 * all own produced units ever used / all own units produced.',
        'Industry capacity points are the original industry score minus those use points.',
        'Cheap differences pair the same mode and seed with its normal stress control.',
        'Existing-six goals only; added-country scores are not invented.',
        'Channel cash contains actual money transfers; barter receives zero cash value.',
        'Aged unused goods are physical inventory, distinct from current market listings.',
    ], 'main':{}, 'cheap':{}, 'all_goods':{}}
    main = defaultdict(list)
    for row in rows:
        if row.get('phase') == 'main':
            main[mode(row)].append(row)
    for m, selected in main.items():
        output['main'][m] = {'n':len(selected), 'countries':{}}
        for name in selected[0]['countries']:
            parts = [score_parts(r['countries'][name]) for r in selected]
            values = {field:stats(x[field] for x in parts) for field in parts[0]
                      if all(x[field] is not None for x in parts)}
            if all('channel_stats' in r['countries'][name] for r in selected):
                values['channels'] = {channel:{field:stats(r['countries'][name]['channel_stats'][channel][field]
                                                       for r in selected) for field in CHANNEL_FIELDS} for channel in CHANNELS}
            output['main'][m]['countries'][name] = values
        output['all_goods'][m] = {
            good:{field:stats(r['world'][field].get(good, 0) for r in selected)
                  for field in ('production', 'consumed', 'remaining_goods', 'aged_unused_goods', 'trade_goods')}
            for good in GOODS}
        for good in GOODS:
            output['all_goods'][m][good]['used_own_produced_units'] = stats(
                sum(c['use_by_good'][good] for c in r['countries'].values()) for r in selected)
            output['all_goods'][m][good]['listed_units'] = stats(
                sum(c['listed_by_good'][good] for c in r['countries'].values()) for r in selected)
    stress = [r for r in rows if r.get('phase') == 'stress']
    for m in sorted({mode(r) for r in stress}):
        control = {r['seed']:r for r in stress if mode(r) == m and r['style'] == 'normal' and r.get('focal') is None}
        output['cheap'][m] = {}
        for name in ORIGINAL:
            selected = [r for r in stress if mode(r) == m and r['style'] == 'cheap' and r.get('focal') == name]
            if not selected:
                continue
            old = [score_parts(control[r['seed']]['countries'][name]) for r in selected]
            new = [score_parts(r['countries'][name]) for r in selected]
            fields = [f for f in old[0] if all(x[f] is not None for x in old+new)]
            entry = {'n':len(selected),
                'normal':{f:stats(x[f] for x in old) for f in fields},
                'cheap':{f:stats(x[f] for x in new) for f in fields},
                'paired_delta':{f:stats(b[f]-a[f] for a,b in zip(old,new)) for f in fields},
                'normal_economic_cap_count':sum(x['economic_at_25'] for x in old),
                'cheap_economic_cap_count':sum(x['economic_at_25'] for x in new)}
            if all('channel_stats' in r['countries'][name] and 'channel_stats' in control[r['seed']]['countries'][name]
                   for r in selected):
                entry['channel_paired_delta'] = {ch:{f:stats(r['countries'][name]['channel_stats'][ch][f]
                                                                  - control[r['seed']]['countries'][name]['channel_stats'][ch][f]
                                                                  for r in selected)
                                                          for f in CHANNEL_FIELDS} for ch in CHANNELS}
            output['cheap'][m][name] = entry
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, default=Path(__file__).parent/'advice_results')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    folder = args.results.resolve()
    folder.mkdir(exist_ok=True)
    audit = Audit()
    report = {'scope':'Independent v7 saved-record audit; no core or simulation execution.', 'warnings':[]}
    run_path = folder/'runs.jsonl.gz'
    if not run_path.exists():
        report.update(status='pending_final_results', pending=['runs.jsonl.gz', 'round_ledgers.jsonl.gz', 'first_seed_traces.json.gz'])
    else:
        rows = read_lines(run_path)
        keys = [identity(r) for r in rows]
        audit.equal(len(keys), len(set(keys)), 'unique_game_keys')
        for row in rows:
            audit.run_summary(row)
        report['completed_runs'] = len(rows)
        report['groups'] = {str(k):n for k,n in Counter((r.get('phase'),mode(r),r.get('style')) for r in rows).items()}
        main_rows = {(mode(r),r['seed']):r for r in rows if r.get('phase') == 'main'}
        path = folder/'round_ledgers.jsonl.gz'
        if path.exists():
            groups = read_lines(path)
            ledger_keys = [(mode(group), group['seed']) for group in groups]
            audit.equal(len(ledger_keys), len(set(ledger_keys)), 'unique_ledger_game_keys')
            audit.equal(set(ledger_keys), set(main_rows), 'all_main_games_have_round_ledgers')
            for group in groups:
                key = (mode(group), group['seed'])
                audit.ledger(group['rows'], main_rows[key], key)
            audit.equal(len(groups), len(main_rows), 'main_ledger_coverage')
        else:
            report['warnings'].append('Detailed round ledgers absent; not audited.')
        path = folder/'first_seed_traces.json.gz'
        if path.exists():
            traces = read_json(path)
            traced_modes = []
            for name, stored in traces.items():
                trace = stored.get('trace', stored)
                m = mode(stored) or name
                traced_modes.append(m)
                seed = stored.get('seed')
                matching = [r for (mm,ss),r in main_rows.items() if mm == m and (seed is None or ss == seed)]
                result = min(matching, key=lambda r:r['seed'])
                audit.trace(trace, result, (m,result['seed']))
            audit.equal(len(traced_modes), len(set(traced_modes)), 'unique_representative_trace_modes')
            audit.equal(set(traced_modes), {m for m,s in main_rows}, 'one_representative_trace_each_mode')
        else:
            report['warnings'].append('Detailed physical/credit/recommendation traces absent; not audited.')
        manifest_path = folder/'run_manifest.json'
        if manifest_path.exists():
            manifest = read_json(manifest_path)
            audit.equal(len(rows), manifest['completed_games'], 'manifest_game_count')
            audit.equal(len(rows), manifest['planned_games'], 'all_planned_games_completed')
            if all(k in manifest for k in ('modes', 'main_seed_range', 'stress_modes', 'stress_scenarios', 'stress_seed_range')):
                first, last = manifest['main_seed_range']
                expected_keys = {('main', m, s, None, 'normal') for m in manifest['modes'] for s in range(first, last+1)}
                first, last = manifest['stress_seed_range']
                expected_keys |= {('stress', m, s, focal, style) for m in manifest['stress_modes']
                                  for focal,style in manifest['stress_scenarios'] for s in range(first, last+1)}
                audit.equal(set(keys), expected_keys, 'complete_preregistered_mode_seed_scenario_schedule')
            for filename, digest in manifest.get('source_sha256', {}).items():
                audit.equal(hashlib.sha256((folder.parent/filename).read_bytes()).hexdigest(), digest, 'source_hash', filename)
        report['analysis'] = analysis(rows)
        report['detailed_trace_channels'] = audit.trace_channels
        report['recommendation_schemas'] = dict(audit.recommendation_schemas)
        report['recommendation_audit_scope'] = {
            'recomputed':['observation cutoffs and representative trace coverage',
                'all-channel actual unit/cash transfers',
                'public exposure and completed-sales UID pairs, separate from unlisted barter',
                'reference quote, age, recommended-price arithmetic and applied price',
                'total public listing cap, grade trial and oldest-stock selection',
                'actual posted/protected UID disjointness for active modes; baseline identity-overlap diagnostic only',
                'own historical sales forecast, current stock and marginal useful units',
                'quality trial bound, opportunity-value arithmetic, threshold and winning candidate',
                'focus candidate value/waste arithmetic and actual selected focus',
                'grade recall qualification, final held/listed/unused stock and summary counters'],
            'limits':['Detailed physical/credit/advice checks cover saved representative traces only.',
                'Recorded rival_best is validated as a price input; exact sequential rival offer snapshots are not saved.',
                'surplus_ids precedes capped relisting; protected_ids follows it. Equal-grade free-stock substitution is not a protected-listing violation.',
                'Forecast future output and operating requirements are policy heuristics; no forward economic optimality proof.',
                'Past-sales continuation is not a guarantee of repeat buying; the trial bound does not bound the whole sales stream.',
                'Every active mode also includes protected-stock recall; contrasts are not pure single-feature interventions.',
                'Passing record checks does not establish balance fairness, learning outcomes or multiplayer correctness.']}
        report['status'] = 'failed' if audit.errors else 'partial' if report['warnings'] else 'passed'
    report['audit_counts'] = dict(audit.counts)
    report['checks_evaluated'] = audit.checks
    report['errors'] = audit.errors
    target = args.out or folder/'independent_audit.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                default=lambda value:sorted(value, key=repr) if isinstance(value, set) else repr(value)),
                      encoding='utf-8')
    print(json.dumps({'status':report['status'], 'counts':report['audit_counts'],
                      'errors':len(audit.errors), 'report':str(target)}, ensure_ascii=False))
    return 1 if audit.errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
