"""v11: public 1G asks and shadow accounting for development-machine services.

The frozen v10 market_first economy is inherited. Only selected actors' public
asks change in minimum scenarios. Shadow score views never feed back into
orders, budgets, investment, physical needs or the original score fields.
"""
from __future__ import annotations
from collections import Counter
import math

from routing_engine import Game as V10
from reference_engine import NAMES

SCORING_MODES = ('legacy', 'success_only', 'ready', 'ready_once')
PRICE_BEHAVIORS = ('normal', 'cheap', 'minimum', 'minimum_passive', 'idle')
BEHAVIORS = PRICE_BEHAVIORS + ('no_high_machine', 'no_raw')
MINIMUM_BEHAVIORS = ('minimum', 'minimum_passive')
DIAGNOSTICS = (
    'machine_attempts', 'ready_opportunities', 'successful_machine_uses',
    'foreign_machine_uses', 'unique_foreign_development_machines',
    'ready_unfulfilled', 'blocked_cash', 'blocked_household', 'blocked_raw',
    'existing_equipment_overlap', 'public_minimum_violations',
    'cash_trade_balance',
)


class Game(V10):
    def __init__(self, seed=0, focal=None, style='normal', trade_enabled=True, behaviors=None):
        if style not in BEHAVIORS:
            raise ValueError('unknown evaluation behavior')
        if style != 'normal' and focal is None:
            raise ValueError('non-normal behavior requires focal country')
        selected = dict(behaviors or {})
        if any(v not in PRICE_BEHAVIORS for v in selected.values()):
            raise ValueError('secondary overrides support ordinary price/participation behaviors only')
        if focal is not None:
            if focal in selected and selected[focal] != style:
                raise ValueError('conflicting focal behavior')
            selected[focal] = style
        self.behaviors = selected
        self.evaluation_attempts = []
        self.evaluation_index = {}
        parent_style = self.parent_style(style)
        super().__init__(seed, variant='market_first', focal=focal, style=parent_style,
                         trade_enabled=trade_enabled)
        if any(n not in self.cs for n in selected):
            raise ValueError('unknown country')
        for name, behavior in selected.items():
            if behavior in PRICE_BEHAVIORS:
                self.cs[name].style = self.parent_style(behavior)

    @staticmethod
    def parent_style(behavior):
        return {'minimum':'normal', 'minimum_passive':'trade'}.get(behavior, behavior)

    def price_recommendation(self, c, good, gen, ids=None):
        advice = super().price_recommendation(c, good, gen, ids)
        if self.behaviors.get(c.name) in MINIMUM_BEHAVIORS:
            return {**advice, 'regular_recommendation':advice['price'],
                    'price':self.opt.price_tick, 'reason':'fixed_legal_public_minimum'}
        return advice

    def investment_snapshot(self, c):
        """Read only a frozen plan and current own inventory, without planning."""
        key = (self.r, c.name)
        cached = key in self.plan_cache
        goal = self.plan_cache.get(key)
        level = c.levels.get(goal, 0) if goal else 0
        legal = bool(1 <= self.r <= 7 and c.style not in ('idle', 'trade') and goal and
                     level < 4 and (goal in c.levels or (goal == c.expand and self.r >= 3)))
        cost = self.upgrade_cost(c, goal) if goal else 0
        reserve = 0 if c.style == 'invest' else self.reserve(c)
        ore, grade = self.upgrade_requirements(c, goal) if goal else (0, 0)
        required = Counter(self.projected_resources(c, goal)) if goal else Counter()
        required['ore'] += ore
        raw = {g:self.count(c, g) for g in ('ore', 'fuel')}
        raw_ok = all(raw.get(g, self.count(c, g)) >= q for g,q in required.items())
        cash_ok = c.cash >= cost + reserve
        food_met = self.r in c.satisfied_rounds
        living_needed = math.ceil(self.pop()/2)
        living_free = self.count(c, 'electronics')
        household_ok = (not self.policy.household_guard or c.style == 'invest' or
                        (food_met and living_free >= living_needed))
        qualified = self.ids(c, 'machine', False, min_gen=grade) if grade else []
        free = [i for i in qualified if self.units[i].order is None]
        own = [i for i in qualified if self.units[i].origin == c.name]
        credited = set()
        for row in self.needs_ledger:
            if (row['round'], row['country'], row['good']) != (self.r, c.name, 'machine'):
                continue
            if not row['purpose'].startswith('equipment:') or not row['fulfilled']:
                continue
            candidates = [i for i in row['used_ids'] if self.units[i].origin != c.name and
                          self.units[i].last_import is not None]
            # Current physical policy has one equipment slot. A wider future
            # multi-slot policy must retain an explicit credit allocation.
            assert len(candidates) == row['fulfilled'], 'ambiguous equipment credit allocation'
            credited.update(i for i in candidates if self.units[i].gen >= grade)
        blockers = []
        if not cached:blockers.append('no_cached_plan')
        if not legal:blockers.append('ineligible_goal')
        if not grade:blockers.append('no_machine_requirement')
        if not cash_ok:blockers.append('cash')
        if not household_ok:blockers.append('household')
        if not raw_ok:blockers.append('raw')
        ready = bool(cached and legal and grade and cash_ok and household_ok and raw_ok)
        return {
            'round':self.r, 'country':c.name, 'goal':goal, 'target_level':level+1 if goal else 0,
            'cached':cached, 'legal':legal, 'style':c.style, 'levels':dict(c.levels), 'expand':c.expand,
            'machine_min_gen':grade, 'cash':c.cash, 'cash_cost':cost, 'reserve':reserve,
            'cash_ok':cash_ok, 'food_met':food_met, 'living_free':living_free,
            'living_needed':living_needed, 'household_ok':household_ok,
            'raw_free':raw, 'raw_required':dict(required), 'research_ore':ore, 'raw_ok':raw_ok,
            'qualified_ids':qualified, 'free_qualified_ids':free, 'own_qualified_ids':own,
            'qualified_units':[{'uid':i, 'origin':self.units[i].origin,
                'generation':self.units[i].gen, 'order':self.units[i].order,
                'import_transaction':self.units[i].last_import} for i in qualified],
            'prior_credited_equipment_ids':sorted(credited), 'ready':ready, 'blockers':blockers,
        }

    def invest(self, c, action_id=None):
        if action_id is not None and (not isinstance(action_id, str) or not action_id):
            return False
        key = (self.r, c.name)
        if (action_id is not None and action_id in self.invest_actions) or key in self.invested_rounds:
            return super().invest(c, action_id)
        # Standalone investment commands retain v10's normal plan selection.
        # The classroom round runner has already frozen this plan. The read-only
        # snapshot helper itself never selects or changes a plan.
        if key not in self.plan_cache:
            self.plan(c)
        snapshot = self.investment_snapshot(c)
        before = len(self.development_log)
        result = super().invest(c, action_id)
        event = self.development_log[-1] if len(self.development_log) > before else None
        machine = event['machine'] if event else None
        row = {**snapshot, 'successful':bool(event), 'event_id':event['event_id'] if event else None,
               'machine_used':dict(machine) if machine else None,
               'external':int(bool(snapshot['machine_min_gen']) and not snapshot['own_qualified_ids']),
               'fulfilled':0, 'already_credited':False}
        if machine:
            row['fulfilled'] = int(row['external'] and machine['origin'] != c.name and
                                   machine['import_transaction'] is not None)
            row['already_credited'] = bool(row['fulfilled'] and machine['uid'] in snapshot['prior_credited_equipment_ids'])
        # One country-round is one development opportunity, not one per click.
        # A later genuinely successful new command can fulfill an earlier failed
        # opportunity. Replayed command IDs return above without changing it.
        old_index = self.evaluation_index.get(key)
        if old_index is None:
            self.evaluation_index[key] = len(self.evaluation_attempts)
            self.evaluation_attempts.append(row)
        else:
            old = self.evaluation_attempts[old_index]
            if row['successful'] or (row['ready'] and not old['successful']) or not old['ready']:
                self.evaluation_attempts[old_index] = row
        return result

    def evaluation_rows(self, mode):
        if mode not in SCORING_MODES:raise ValueError('unknown scoring mode')
        if mode == 'legacy':return []
        out = []
        for a in self.evaluation_attempts:
            if not a['machine_min_gen']:continue
            if not (a['successful'] if mode == 'success_only' else a['ready']):continue
            if mode == 'ready_once' and a['already_credited']:continue
            out.append({'round':a['round'], 'country':a['country'], 'good':'machine',
                'purpose':'development', 'needed':1, 'external':a['external'],
                'fulfilled':a['fulfilled'], 'used_ids':[a['machine_used']['uid']] if a['machine_used'] else [],
                'min_gen':a['machine_min_gen'], 'goal':a['goal'], 'target_level':a['target_level'],
                'event_id':a['event_id']})
        return out

    def evaluation_scores(self, name, mode, base_country):
        added = [r for r in self.evaluation_rows(mode) if r['country'] == name]
        rows = [r for r in self.needs_ledger if r['country'] == name] + added
        ext = sum(r['external'] for r in rows)
        fulfilled = sum(r['fulfilled'] for r in rows)
        er = {r['round'] for r in rows if r['external']}
        fr = {r['round'] for r in rows if r['fulfilled']}
        export_part = min(1, base_country['export_help_rounds']/6)
        partners_part = 4*min(1, base_country['useful_partners']/3)
        imports_part = 8*fulfilled/ext if ext else 0
        effects_part = 4*len(fr)/len(er) if er else 0
        trade = 5*export_part + imports_part + partners_part + effects_part + 4*export_part
        score = base_country['score'] + (trade - base_country['trade']) if name in NAMES else None
        skipped = sum(a['country'] == name and a['ready'] and a['already_credited']
                      for a in self.evaluation_attempts) if mode == 'ready_once' else 0
        return {'trade':trade, 'score':score, 'trade_delta':trade-base_country['trade'],
            'external_need':ext, 'external_fulfilled':fulfilled,
            'coverage':fulfilled/ext if ext else 0,
            'external_rounds':len(er), 'fulfilled_rounds':len(fr),
            'added_needed':len(added), 'added_external':sum(r['external'] for r in added),
            'added_fulfilled':sum(r['fulfilled'] for r in added), 'skipped_existing_credit':skipped,
            'imports_part':imports_part, 'effects_import_part':effects_part}

    def verify(self):
        result = super().verify()
        keys = [(a['round'],a['country']) for a in self.evaluation_attempts]
        assert len(keys) == len(set(keys)) == len(self.evaluation_index)
        for a in self.evaluation_attempts:
            assert 0 <= a['fulfilled'] <= a['external'] <= int(bool(a['machine_min_gen']))
            if a['machine_used']:
                assert a['successful'] and a['ready']
                u = a['machine_used']
                assert u['uid'] in a['free_qualified_ids'] and u['generation'] >= a['machine_min_gen']
            if a['ready'] and not a['successful']:
                assert not a['free_qualified_ids'], 'ready failure had a qualifying free machine'
            if a['already_credited']:
                assert a['fulfilled'] and a['machine_used']['uid'] in a['prior_credited_equipment_ids']
        return result

    def summary(self):
        result = super().summary()
        for name,x in result['countries'].items():
            a = [row for row in self.evaluation_attempts if row['country'] == name and row['machine_min_gen']]
            used = [row['machine_used'] for row in a if row['machine_used']]
            foreign = [u for u in used if u['origin'] != name and u['import_transaction'] is not None]
            violations = sum(e['country'] == name and self.behaviors.get(name) in MINIMUM_BEHAVIORS and
                e['prices'] != [self.opt.price_tick] for e in self.offer_history)
            diagnostic = {
                'machine_attempts':len(a), 'ready_opportunities':sum(row['ready'] for row in a),
                'successful_machine_uses':len(used), 'foreign_machine_uses':len(foreign),
                'unique_foreign_development_machines':len({u['uid'] for u in foreign}),
                'ready_unfulfilled':sum(row['ready'] and row['external'] and not row['fulfilled'] for row in a),
                'blocked_cash':sum('cash' in row['blockers'] for row in a),
                'blocked_household':sum('household' in row['blockers'] for row in a),
                'blocked_raw':sum('raw' in row['blockers'] for row in a),
                'existing_equipment_overlap':sum(row['already_credited'] for row in a),
                'public_minimum_violations':violations,
                'cash_trade_balance':x['revenue']-x['purchases'],
            }
            assert set(diagnostic) == set(DIAGNOSTICS)
            views = {mode:self.evaluation_scores(name,mode,x) for mode in SCORING_MODES}
            assert math.isclose(views['legacy']['trade'],x['trade'],abs_tol=1e-10)
            for mode,v in views.items():
                assert 0 <= v['trade'] <= 25 + 1e-10
                assert v['score'] is None or 0 <= v['score'] <= 100 + 1e-10
            x['evaluation'] = {**diagnostic, 'scores':views}
        result['world']['evaluation'] = {k:sum(x['evaluation'][k] for x in result['countries'].values()) for k in DIAGNOSTICS}
        result['world']['evaluation_config'] = {
            'baseline':'v10 market_first', 'behaviors':dict(self.behaviors),
            'legal_public_minimum':self.opt.price_tick, 'scoring_modes':list(SCORING_MODES),
            'original_scores_unchanged':True, 'shadow_scores_do_not_affect_actions':True,
            'public_prices_only':True,
        }
        return result

    def trace(self):
        result = super().trace()
        result.update(evaluation_attempts=self.evaluation_attempts,
                      evaluation_rows={m:self.evaluation_rows(m) for m in SCORING_MODES},
                      evaluation_behaviors=dict(self.behaviors),
                      evaluation_legal_minimum=self.opt.price_tick)
        return result
